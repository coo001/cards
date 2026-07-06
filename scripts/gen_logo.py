"""@acts_news 프로필용 원형 엠블럼 로고를 ChatGPT(codex)로 생성. 변형 여러 개 → 골라서 사용.

인스타 프로필은 원형으로 크롭되므로, 중요한 요소는 중앙 원 안에 배치되도록 프롬프트에 명시.
"""
import argparse
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image

from common import PROJECT_ROOT, emit, load_config

BASE = (
    "A circular emblem logo badge for a Korean theater-news Instagram account. "
    "Centered, perfectly symmetric circular badge that fills most of a square canvas, "
    "on a solid deep navy #141B2E background. Design lives INSIDE the circle so it stays intact when cropped to a circle. "
    "Colors: red #E5484D and white on navy. Modern, premium, high-contrast, flat vector, crisp clean lines, "
    "readable when small. The wordmark ACTS in bold clean sans-serif white capital letters, "
    "and a small line of text reading THEATER NEWS. "
    "Correct spelling, no gibberish, no watermark, no photograph."
)

VARIANTS = [
    " Central motif: minimalist comedy-and-tragedy theater masks in red and white line-art above the ACTS wordmark.",
    " Central motif: a stage with an open red curtain and a single white spotlight beam above the ACTS wordmark.",
    " Central motif: a bold red monogram letter A styled like a spotlight/stage, with the ACTS wordmark below.",
]


def to_square(data, size=1080):
    im = Image.open(BytesIO(data)).convert("RGB")
    w, h = im.size
    s = min(w, h)
    im = im.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s))
    return im.resize((size, size), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config")
    ap.add_argument("--out-dir", default=str(PROJECT_ROOT / "output" / "logo"))
    ap.add_argument("--variants", type=int, default=3)
    args = ap.parse_args()

    cfg = load_config(args.config)
    ch = cfg["chatgpt"]
    sys.path.insert(0, ch["backend_dir"])
    import codex_backend

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    done, failed = [], []
    for i in range(min(args.variants, len(VARIANTS))):
        prompt = BASE + VARIANTS[i]
        try:
            data = codex_backend.generate_image(
                prompt, size="1024x1024", output_format="png",
                quality=ch.get("quality", "high"), effort=ch.get("effort", "high"),
                timeout=300,
            )
            p = out_dir / f"logo_{i+1}.png"
            to_square(data).save(p, "PNG")
            done.append(str(p))
        except Exception as exc:
            failed.append({"variant": i + 1, "error": str(exc)[:300]})
            print(f"[warn] logo {i+1} 생성 실패: {exc}")

    emit({"out_dir": str(out_dir), "logos": done, "failed": failed})


if __name__ == "__main__":
    main()
