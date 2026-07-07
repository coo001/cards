"""RSS(또는 직접 URL)에서 연극 기사 1건을 선택 → 대표 이미지/본문 추출 → article.json 저장.

발행 완료 표시는 publish_ig.py가 하므로, 여기서는 이미 발행된 기사만 건너뛴다.
"""
import argparse
import calendar
import datetime as dt
import re
from io import BytesIO
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse

import feedparser
import requests
from bs4 import BeautifulSoup
from PIL import Image

from common import (POSTED_PATH, SKIPPED_PATH, content_sig, emit, load_config,
                    load_json, out_dir_for, save_json, sig_is_dup)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

# 네이버 모바일 뉴스 검색(최신순). RSS로는 안 잡히는 연극 기사까지 폭넓게 수집.
NAVER_MOBILE = "https://m.search.naver.com/search.naver?where=m_news&sort=1&query={q}"
_NAVER_ID_RE = re.compile(r"/article/(?:mnews/)?(\d{3})/(\d+)")


def naver_entries(queries, limit=30):
    """네이버 모바일 뉴스 검색 → n.news.naver.com 기사를 (title, link) 유사 엔트리로 반환."""
    out, seen = [], set()
    for q in queries or []:
        try:
            r = requests.get(NAVER_MOBILE.format(q=quote(q)), headers=HEADERS, timeout=20)
            r.raise_for_status()
        except Exception as exc:
            print(f"[warn] 네이버 검색 실패({q}): {exc}")
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.select("a[href*='n.news.naver.com']"):
            href = (a.get("href") or "").split("?")[0].split("#")[0]
            title = (a.get("title") or a.get_text(" ", strip=True)).strip()
            m = _NAVER_ID_RE.search(href)
            if not m or not title or title == "네이버뉴스":
                continue
            key = (m.group(1), m.group(2))
            if key in seen:
                continue
            seen.add(key)
            out.append(feedparser.util.FeedParserDict({
                "title": title,
                "link": f"https://n.news.naver.com/article/{key[0]}/{key[1]}",
                "summary": "",
            }))
        if len(out) >= limit:
            break
    return out


def naver_press(html):
    """네이버 기사 페이지에서 실제 언론사명 추출(출처 표기용)."""
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    for sel in ("a.media_end_head_top_logo img", "img.media_end_head_top_logo_img",
                "meta[property='og:article:author']", "meta[name='twitter:creator']"):
        el = soup.select_one(sel)
        if el:
            val = (el.get("alt") or el.get("content") or "").strip()
            if val:
                return val
    return None


def skip_keys_and_sigs():
    """발행완료+제외 기사의 (URL/제목 키 집합, 시그니처 목록)."""
    keys, sigs = set(), []
    for path in (POSTED_PATH, SKIPPED_PATH):
        for p in load_json(path, default=[]) or []:
            if p.get("url"):
                keys.add(p["url"])
            if p.get("title"):
                keys.add(p["title"])
            if p.get("sig"):
                sigs.append(p["sig"])
    return keys, sigs


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


# 언론사 본문 컨테이너(네이버 #dic_area 포함). 일반 <p> 긁기보다 우선.
BODY_SELECTORS = ("#dic_area", "#newsct_article", ".newsct_article", "#articeBody",
                  "#articleBodyContents", "#article_body", ".article_body",
                  "#article-view-content-div", "#newsEndContents", "article")


def _extract_body(soup):
    for sel in BODY_SELECTORS:
        node = soup.select_one(sel)
        if not node:
            continue
        for bad in node.select("script, style, figcaption, .end_photo_org, "
                               ".media_end_head, .promotion, .link_news, .reporter_area"):
            bad.decompose()
        text = "\n".join(ln for ln in node.get_text("\n", strip=True).splitlines()
                         if len(ln) > 15)
        if len(text) >= 150:
            return text[:2000]
    paras = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    paras = [p for p in paras if len(p) > 30]
    return "\n".join(paras[:12])[:2000]


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
    return {"image": img, "title": title, "desc": desc, "body": _extract_body(soup)}


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


def _entry_ts(e):
    """정렬용 epoch. struct_time↔datetime.time 혼재로 인한 TypeError 방지."""
    t = e.get("published_parsed") or e.get("updated_parsed")
    if not t:
        return 0.0
    try:
        return calendar.timegm(t)
    except (TypeError, ValueError, OverflowError):
        return 0.0


def gather_entries(feeds):
    entries = []
    for feed_url in feeds:
        try:
            parsed = feedparser.parse(feed_url)
        except Exception as exc:
            print(f"[warn] feed 파싱 실패: {feed_url} ({exc})")
            continue
        entries.extend(parsed.entries)
    entries.sort(key=_entry_ts, reverse=True)     # 최신순 (시각정보 없으면 뒤로)
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


# ---- '연극 흥미도' 스코어: 개막·초연·캐스팅·매진 등 하드뉴스 우선, 칼럼·로운드업·타장르 후순위 ----
_COLUMN_RE = re.compile(r"^\s*[\[〔【][^\]〕】]*의\s")          # [OOO의 코너명] 칼럼형 제목
_NEWS_HINTS = ("개막", "초연", "막을 올", "막 올", "첫 공연", "무대에 오", "무대에 선",
               "무대 오른", "캐스팅", "매진", "앙코르", "연장", "개막박두", "출연")
_DEMOTE_HINTS = ("칼럼", "기고", "오피니언", "이번 주", "이주의", "이 주의", "이달의",
                 "뭐 볼까", "볼만한", "가볼만", "주말 나들이", "추천작", "추천 공연",
                 "공연 소식", "문화 소식", "총정리", "모아보기", "미리보기")
_OFFTOPIC_HINTS = ("예능", "드라마", "영화", "콘서트", "앨범", "가요", "트로트", "아이돌")
_WORKQUOTE_RE = re.compile("[<〈《『「'‘\"“]")


def article_score(title, summary=""):
    """연극 팬 관심 뉴스일수록 높은 점수. 선별 순위용(하드 필터 아님)."""
    t = title or ""
    both = f"{t} {summary or ''}"
    sc = 0.0
    if _COLUMN_RE.search(t):
        sc -= 6
    for w in _DEMOTE_HINTS:
        if w in t:
            sc -= 4
        elif w in both:
            sc -= 1.5
    for w in _OFFTOPIC_HINTS:
        if w in t:
            sc -= 3
    for w in _NEWS_HINTS:
        if w in t:
            sc += 3
        elif w in both:
            sc += 1
    if _WORKQUOTE_RE.search(t):                    # 제목에 작품명 인용부호 → 구체 뉴스 가능성
        sc += 1.5
    return sc


def rank_entries(entries, skip_keys, known_sigs, dedupe=True):
    """중복(완전일치+엔트리 시그니처) 제외 후 '연극 흥미도' 내림차순 정렬(동점이면 최신 우선)."""
    avail = []
    for e in entries:
        title = e.get("title") or ""
        link = e.get("link") or ""
        if dedupe:
            if (link and link in skip_keys) or (title and title in skip_keys):
                continue
            if any(sig_is_dup(content_sig(title, e.get("summary", "")), k) for k in known_sigs):
                print(f"[skip] 중복 추정(엔트리): {title}")
                continue
        avail.append(e)
    avail.sort(key=lambda e: -article_score(e.get("title", ""), e.get("summary", "")))  # stable
    return avail


def choose_entry(candidates, skip_keys, known_sigs, dedupe=True):
    """순위대로 훑되, 선택 후보는 본문까지 받아 full-sig로 같은 사건 재확인 후 확정."""
    for cand in rank_entries(candidates, skip_keys, known_sigs, dedupe):
        clink = cand.get("link")
        if dedupe and clink:
            try:                                    # 본문 기반 시그니처로 정밀 중복 재검
                furl, fhtml = fetch_html(clink)
                fmeta = extract_meta(fhtml, furl)
                fsig = content_sig(cand.get("title", ""), fmeta.get("desc", ""), fmeta.get("body", ""))
                if any(sig_is_dup(fsig, k) for k in known_sigs):
                    print(f"[skip] 본문 확인 후 중복: {cand.get('title')}")
                    continue
            except Exception as exc:
                print(f"[warn] 본문 확인 실패({clink}): {exc}")
        print(f"[pick] 선택: {cand.get('title')} "
              f"(score={article_score(cand.get('title',''), cand.get('summary','')):.1f})")
        return cand
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
    if "news.naver.com" in domain:                 # 출처를 실제 언론사명으로
        domain = naver_press(html) or domain
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


def list_candidates(cfg, no_dedupe=False, top=8):
    """선택하지 않고 후보 순위 목록 + 최근 발행목록만 출력.
    Claude가 이 목록을 이전 발행본과 '의미로 대조'해 새 사건 후보를 고른 뒤 --url로 확정한다."""
    keywords = cfg.get("keywords") or []
    matched = filter_keywords(gather_entries(cfg["feeds"]), keywords)
    nav = filter_keywords(naver_entries(cfg.get("naver_queries")), keywords)
    skip_keys, known_sigs = skip_keys_and_sigs()
    ranked = rank_entries(nav + matched, skip_keys, known_sigs, dedupe=not no_dedupe)
    cands = [{
        "rank": i + 1,
        "title": e.get("title", ""),
        "url": e.get("link", ""),
        "score": round(article_score(e.get("title", ""), e.get("summary", "")), 1),
    } for i, e in enumerate(ranked[:top])]
    recent = [{
        "title": p.get("title"),
        "date": p.get("date"),
        "works": (p.get("sig") or {}).get("works", [])[:6],
    } for p in (load_json(POSTED_PATH, default=[]) or [])[-12:]]
    emit({"mode": "list", "candidates": cands, "recent_posted": recent})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="RSS 대신 특정 기사 URL 직접 사용")
    ap.add_argument("--list", action="store_true",
                    help="선택 안 하고 후보 목록+최근 발행목록만 출력(Claude가 대조 후 --url로 확정)")
    ap.add_argument("--config")
    ap.add_argument("--date", help="출력 폴더명 (기본: 날짜_시각 YYYY-MM-DD_HHMMSS)")
    ap.add_argument("--no-dedupe", action="store_true", help="이미 발행된 기사도 다시 선택")
    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.list:
        list_candidates(cfg, no_dedupe=args.no_dedupe)
        return

    date_str = args.date or dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
    out_dir = out_dir_for(date_str)

    if args.url:
        entry = feedparser.util.FeedParserDict({"link": args.url})
        link = args.url
    else:
        keywords = cfg.get("keywords") or []
        matched = filter_keywords(gather_entries(cfg["feeds"]), keywords)
        nav = filter_keywords(naver_entries(cfg.get("naver_queries")), keywords)
        candidates = nav + matched          # 네이버(최신순) 우선 + RSS 문화피드
        if not candidates:
            raise SystemExit(
                f"키워드 {keywords} 에 맞는 최신 기사가 없습니다. "
                "config의 feeds/keywords/naver_queries를 조정하거나 --url로 직접 지정하세요."
            )
        skip_keys, known_sigs = skip_keys_and_sigs()
        entry = choose_entry(candidates, skip_keys, known_sigs, dedupe=not args.no_dedupe)
        if entry is None:
            raise SystemExit(
                "발행할 새 기사가 없습니다 (모두 발행/제외됨). --no-dedupe 로 재사용 가능."
            )
        link = entry.get("link")

    article = build_article(link, entry, out_dir)
    article["sig"] = content_sig(
        article.get("title", ""), article.get("snippet", ""), article.get("body", ""))
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
