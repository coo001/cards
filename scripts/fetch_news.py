"""RSS(또는 직접 URL)에서 연극 기사 1건을 선택 → 대표 이미지/본문 추출 → article.json 저장.

발행 완료 표시는 publish_ig.py가 하므로, 여기서는 이미 발행된 기사만 건너뛴다.
"""
import argparse
import datetime as dt
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup
from PIL import Image

from common import STATE_DIR, emit, load_config, load_json, out_dir_for, save_json

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    )
}
POSTED_PATH = STATE_DIR / "posted.json"


def posted_keys():
    posted = load_json(POSTED_PATH, default=[]) or []
    keys = set()
    for p in posted:
        if p.get("url"):
            keys.add(p["url"])
        if p.get("title"):
            keys.add(p["title"])
    return keys


def entry_image(entry):
    for key in ("media_content", "media_thumbnail"):
        media = entry.get(key)
        if media:
            url = media[0].get("url")
            if url:
                return url
    for enc in entry.get("enclosures", []) or []:
        if str(enc.get("type", "")).startswith("image") and enc.get("href"):
            return enc["href"]
    for link in entry.get("links", []) or []:
        if link.get("rel") == "enclosure" and str(link.get("type", "")).startswith("image"):
            return link.get("href")
    return None


def fetch_html(url):
    r = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
    r.raise_for_status()
    return r.url, r.text


def extract_meta(html, base_url):
    soup = BeautifulSoup(html, "html.parser")

    def meta(*names):
        for n in names:
            tag = soup.find("meta", property=n) or soup.find("meta", attrs={"name": n})
            if tag and tag.get("content"):
                return tag["content"].strip()
        return None

    img = meta("og:image", "twitter:image", "twitter:image:src")
    if img:
        if img.startswith("//"):
            img = "https:" + img
        elif img.startswith("/"):
            img = urljoin(base_url, img)
    title = meta("og:title", "twitter:title")
    if not title and soup.title and soup.title.string:
        title = soup.title.string.strip()
    desc = meta("og:description", "twitter:description", "description")
    paras = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    paras = [p for p in paras if len(p) > 30]
    body = "\n".join(paras[:12])[:2000]
    return {"image": img, "title": title, "desc": desc, "body": body}


def _abs_url(u, base):
    if not u:
        return None
    u = u.strip()
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return urljoin(base, u)
    return u if u.startswith("http") else None


AD_HINTS = ("interactive", "/ad/", "/ads/", "adfit", "banner", "promotion",
            "sponsor", "/ranking/", "event", "/promo", "logo", "icon")


def meta_images(html, base_url, entry):
    """편집상 대표컷 후보: RSS 썸네일 → og:image → twitter:image."""
    out, seen = [], set()

    def add(u):
        au = _abs_url(u, base_url)
        if au and au not in seen:
            seen.add(au)
            out.append(au)

    if entry:
        add(entry_image(entry))
    if html:
        soup = BeautifulSoup(html, "html.parser")
        for prop in ("og:image", "og:image:secure_url", "twitter:image", "twitter:image:src"):
            tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            if tag and tag.get("content"):
                add(tag["content"])
    return out


def body_images(html, base_url):
    out, seen = [], set()
    if not html:
        return out
    soup = BeautifulSoup(html, "html.parser")
    for sel in ("article img", "figure img", "#article img", ".article_body img"):
        for img in soup.select(sel):
            u = _abs_url(img.get("src") or img.get("data-src"), base_url)
            if u and u not in seen:
                seen.add(u)
                out.append(u)
    for img in soup.find_all("img"):
        u = _abs_url(img.get("src") or img.get("data-src"), base_url)
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _valid_area(content):
    """이미지 크기·비율 검사 통과 시 area 반환, 아니면 None."""
    try:
        w, h = Image.open(BytesIO(content)).size
    except Exception:
        return None
    if w < 500 or h < 300:
        return None
    ar = w / h
    if ar < 0.5 or ar > 2.8:                # 배너·띠 등 극단 비율 제외
        return None
    return w * h


def _ext_of(r):
    ct = r.headers.get("Content-Type", "").lower()
    return ".png" if "png" in ct else ".webp" if "webp" in ct else ".jpg"


def pick_image(meta_imgs, body_imgs, dest_base, limit=10):
    """1) og/twitter/RSS 대표컷을 최우선 사용(광고 아님·검증 통과 시 즉시).
    2) 없으면 본문 이미지 중 광고성 URL 제외 후 가장 큰 것."""
    for u in meta_imgs:
        if any(h in u.lower() for h in AD_HINTS):
            continue
        try:
            r = requests.get(u, headers=HEADERS, timeout=15)
            r.raise_for_status()
            if _valid_area(r.content):
                dest = Path(dest_base).with_suffix(_ext_of(r))
                dest.write_bytes(r.content)
                return u, str(dest)
        except Exception:
            continue

    best = None
    for u in body_imgs[:limit]:
        if any(h in u.lower() for h in AD_HINTS):
            continue
        try:
            r = requests.get(u, headers=HEADERS, timeout=15)
            r.raise_for_status()
            area = _valid_area(r.content)
            if area and (best is None or area > best[0]):
                best = (area, u, r.content, _ext_of(r))
        except Exception:
            continue
    if best:
        dest = Path(dest_base).with_suffix(best[3])
        dest.write_bytes(best[2])
        return best[1], str(dest)
    return None, None


def gather_entries(feeds):
    entries = []
    for feed_url in feeds:
        parsed = feedparser.parse(feed_url)
        for e in parsed.entries:
            entries.append(e)
    # 최신순 정렬 (published_parsed 없으면 뒤로)
    entries.sort(
        key=lambda e: e.get("published_parsed") or e.get("updated_parsed") or dt.time.min,
        reverse=True,
    )
    return entries


def filter_keywords(entries, keywords):
    if not keywords:
        return entries
    out = []
    for e in entries:
        hay = (e.get("title", "") or "") + " " + (e.get("summary", "") or "")
        if any(k in hay for k in keywords):
            out.append(e)
    return out


def pick_entry(entries, skip_keys, dedupe=True):
    for e in entries:
        title = e.get("title")
        link = e.get("link")
        if dedupe and ((link and link in skip_keys) or (title and title in skip_keys)):
            continue
        return e
    return None


def build_article(link, entry, out_dir):
    img_from_entry = entry_image(entry) if entry else None
    final_url, html, meta = link, None, {}
    try:
        final_url, html = fetch_html(link)
        meta = extract_meta(html, final_url)
    except Exception as exc:  # 네트워크/파싱 실패 → RSS 정보만으로 진행
        meta = {"image": None, "title": None, "desc": None, "body": None}
        print(f"[warn] article fetch failed: {exc}")

    title = (entry.get("title") if entry else None) or meta.get("title") or "(제목 없음)"
    snippet = meta.get("desc") or (entry.get("summary") if entry else None) or ""
    body = meta.get("body") or (entry.get("summary") if entry else None) or snippet

    # og/twitter 대표컷 우선, 없으면 본문 이미지(광고 제외) 폴백
    image_url, image_local = None, None
    try:
        image_url, image_local = pick_image(
            meta_images(html, final_url, entry), body_images(html, final_url), out_dir / "hero_src")
    except Exception as exc:
        print(f"[warn] image pick failed: {exc}")
    if image_local is None:                 # 폴백: og:image 단순 다운로드
        fallback = meta.get("image") or img_from_entry
        if fallback:
            try:
                image_local = str(download_image(fallback, out_dir / "hero_src"))
                image_url = fallback
            except Exception as exc:
                print(f"[warn] hero image download failed: {exc}")

    domain = urlparse(final_url).netloc.replace("www.", "")
    return {
        "title": title,
        "url": final_url,
        "domain": domain,
        "image_url": image_url,
        "image_local": image_local,
        "has_image": bool(image_local),
        "snippet": snippet,
        "body": body,
        "published": entry.get("published") if entry else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="RSS 대신 특정 기사 URL 직접 사용")
    ap.add_argument("--config")
    ap.add_argument("--date", help="출력 폴더명 (기본: 날짜_시각 YYYY-MM-DD_HHMMSS)")
    ap.add_argument("--no-dedupe", action="store_true", help="이미 발행된 기사도 다시 선택")
    args = ap.parse_args()

    cfg = load_config(args.config)
    date_str = args.date or dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_dir = out_dir_for(date_str)

    if args.url:
        entry = feedparser.util.FeedParserDict({"link": args.url})
        link = args.url
    else:
        entries = gather_entries(cfg["feeds"])
        if not entries:
            raise SystemExit("RSS에서 기사를 가져오지 못했습니다. 피드 URL/네트워크를 확인하세요.")
        keywords = cfg.get("keywords") or []
        matched = filter_keywords(entries, keywords)
        if not matched:
            raise SystemExit(
                f"키워드 {keywords} 에 맞는 최신 기사가 없습니다. "
                "나중에 다시 시도하거나 config의 feeds/keywords를 조정, 또는 --url로 직접 지정하세요."
            )
        entry = pick_entry(matched, posted_keys(), dedupe=not args.no_dedupe)
        if entry is None:
            raise SystemExit("발행할 새 기사가 없습니다 (모두 발행됨). --no-dedupe 로 재사용 가능.")
        link = entry.get("link")

    article = build_article(link, entry, out_dir)
    save_json(out_dir / "article.json", article)

    emit({
        "out_dir": str(out_dir),
        "article": {
            "title": article["title"],
            "url": article["url"],
            "domain": article["domain"],
            "has_image": article["has_image"],
            "snippet": article["snippet"][:200],
            "body_chars": len(article["body"] or ""),
        },
    })


if __name__ == "__main__":
    main()
