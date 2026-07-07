"""기사를 skipped.json에 추가 → 이후 fetch_news가 다시 선택하지 않게 한다.

같은 사건을 다룬 다른 URL/헤드라인 기사도 시그니처로 함께 걸러진다.

사용:
  python skip_article.py --out-dir <out_dir>          # out_dir/article.json 사용
  python skip_article.py --url <URL> --title "<제목>"  # 직접 지정
"""
import argparse
import datetime as dt
from pathlib import Path

from common import (SKIPPED_PATH, STATE_DIR, content_sig, emit, load_json,
                    save_json)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", help="article.json이 있는 폴더")
    ap.add_argument("--url")
    ap.add_argument("--title", default="")
    ap.add_argument("--reason", default="user-skip")
    args = ap.parse_args()

    art = {}
    if args.out_dir:
        art = load_json(Path(args.out_dir) / "article.json", default={}) or {}
    url = args.url or art.get("url")
    title = args.title or art.get("title") or ""
    if not url and not title:
        raise SystemExit("--out-dir 또는 --url/--title 중 하나가 필요합니다.")

    sig = art.get("sig") or content_sig(title, art.get("snippet", ""), art.get("body", ""))

    skipped = load_json(SKIPPED_PATH, default=[]) or []
    if url and any(s.get("url") == url for s in skipped):
        emit({"skipped": url, "already": True, "count": len(skipped)})
        return
    skipped.append({
        "url": url,
        "title": title,
        "sig": sig,
        "reason": args.reason,
        "date": dt.date.today().isoformat(),
    })
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    save_json(SKIPPED_PATH, skipped)
    emit({"skipped": url or title, "works": sig["works"], "count": len(skipped)})


if __name__ == "__main__":
    main()
