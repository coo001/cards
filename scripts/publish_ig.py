"""imgbb 공개 URL 3장 → Instagram 캐러셀 1건 발행 (graph.instagram.com).

절차: 아이템 컨테이너 3개 생성 → 캐러셀 컨테이너 생성 → 상태 FINISHED 대기 → media_publish.
--dry-run: 컨테이너까지만 만들고 실제 발행은 하지 않음 (검증용, 게시 안 됨).
"""
import argparse
import datetime as dt
import os
import time
from pathlib import Path

import requests

from common import STATE_DIR, emit, load_config, load_json, save_json

POSTED_PATH = STATE_DIR / "posted.json"


def api_base(cfg):
    ver = os.getenv("GRAPH_API_VERSION") or cfg["instagram"]["graph_version"]
    return f"https://graph.instagram.com/{ver}"


def post(url, params):
    r = requests.post(url, data=params, timeout=60)
    if r.status_code != 200:
        raise SystemExit(f"IG API 오류: {r.status_code} {r.text[:500]}\nURL={url}")
    return r.json()


def get(url, params):
    r = requests.get(url, params=params, timeout=60)
    if r.status_code != 200:
        raise SystemExit(f"IG API 오류: {r.status_code} {r.text[:500]}\nURL={url}")
    return r.json()


def create_item(base, uid, token, image_url):
    res = post(f"{base}/{uid}/media", {
        "image_url": image_url,
        "is_carousel_item": "true",
        "access_token": token,
    })
    return res["id"]


def create_carousel(base, uid, token, children, caption):
    res = post(f"{base}/{uid}/media", {
        "media_type": "CAROUSEL",
        "children": ",".join(children),
        "caption": caption,
        "access_token": token,
    })
    return res["id"]


def wait_finished(base, container_id, token, timeout=90):
    """컨테이너가 발행 가능(FINISHED) 상태가 될 때까지 대기."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        res = get(f"{base}/{container_id}", {"fields": "status_code", "access_token": token})
        code = res.get("status_code")
        if code == "FINISHED":
            return
        if code == "ERROR":
            raise SystemExit(f"컨테이너 처리 실패(ERROR): {container_id}")
        time.sleep(3)
    raise SystemExit(f"컨테이너 처리 시간 초과: {container_id}")


def mark_posted(article):
    posted = load_json(POSTED_PATH, default=[]) or []
    posted.append({
        "url": article.get("url"),
        "title": article.get("title"),
        "date": dt.date.today().isoformat(),
    })
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    save_json(POSTED_PATH, posted)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--config")
    ap.add_argument("--dry-run", action="store_true", help="컨테이너까지만 생성, 실제 발행 안 함")
    args = ap.parse_args()

    cfg = load_config(args.config)
    out_dir = Path(args.out_dir)
    uid = os.getenv("IG_USER_ID")
    token = os.getenv("IG_ACCESS_TOKEN")
    if not uid or not token:
        raise SystemExit(".env에 IG_USER_ID 또는 IG_ACCESS_TOKEN이 없습니다.")

    urls = load_json(out_dir / "urls.json")
    copy = load_json(out_dir / "copy.json")
    article = load_json(out_dir / "article.json", default={})
    if not urls:
        raise SystemExit("urls.json 없음 — upload_imgbb.py를 먼저 실행하세요.")
    if not copy:
        raise SystemExit("copy.json 없음.")
    caption = copy.get("caption", "")

    base = api_base(cfg)
    children = []
    for u in urls:
        cid = create_item(base, uid, token, u)
        wait_finished(base, cid, token)
        children.append(cid)

    carousel_id = create_carousel(base, uid, token, children, caption)
    wait_finished(base, carousel_id, token)

    if args.dry_run:
        emit({"dry_run": True, "carousel_id": carousel_id, "children": children,
              "note": "실제 발행은 하지 않음"})
        return

    published = post(f"{base}/{uid}/media_publish", {
        "creation_id": carousel_id,
        "access_token": token,
    })
    media_id = published["id"]

    permalink = None
    try:
        info = get(f"{base}/{media_id}", {"fields": "permalink", "access_token": token})
        permalink = info.get("permalink")
    except SystemExit:
        pass

    mark_posted(article)
    emit({"media_id": media_id, "permalink": permalink, "out_dir": str(out_dir)})


if __name__ == "__main__":
    main()
