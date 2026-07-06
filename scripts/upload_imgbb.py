"""렌더된 카드 PNG들을 imgbb에 업로드 → 공개 URL 목록(urls.json) 저장.

Instagram Graph API는 로컬 파일을 못 받고 공개 image_url이 필요하므로 이 단계가 필수.
"""
import argparse
import base64
import os
from pathlib import Path

import requests

from common import emit, save_json

UPLOAD_URL = "https://api.imgbb.com/1/upload"


def upload_one(key, path):
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read())
    r = requests.post(UPLOAD_URL, data={"key": key, "image": b64}, timeout=90)
    if r.status_code != 200:
        raise SystemExit(f"imgbb 업로드 실패({path}): {r.status_code} {r.text[:300]}")
    data = r.json()
    if not data.get("success"):
        raise SystemExit(f"imgbb 응답 오류({path}): {r.text[:300]}")
    return data["data"]["url"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--cards", nargs="*", help="업로드할 PNG 경로(기본: card1~3.png)")
    args = ap.parse_args()

    key = os.getenv("IMGBB_API_KEY")
    if not key:
        raise SystemExit(".env에 IMGBB_API_KEY가 없습니다.")

    out_dir = Path(args.out_dir)
    cards = args.cards or [str(out_dir / f"card{i}.png") for i in (1, 2, 3)]

    urls = []
    for c in cards:
        if not Path(c).exists():
            raise SystemExit(f"카드 파일 없음: {c}")
        urls.append(upload_one(key, c))

    save_json(out_dir / "urls.json", urls)
    emit({"out_dir": str(out_dir), "urls": urls})


if __name__ == "__main__":
    main()
