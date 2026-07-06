"""copy.json + article.json → 카드 3장(1080x1350 PNG). 3장 모두 같은 기사 사진을 공유(통일감).

카드1 히어로 : 사진 풀블리드 + 하단 그라데이션 스크림 + 제목/부제
카드2 요약   : 사진 풀블리드 + 진한 오버레이 + 핵심요약 3줄 + 코멘트
카드3 마무리 : 사진 풀블리드 + 진한 오버레이 + 마무리 문구 + 계정 핸들 + CTA
폰트는 Pretendard(번들). 사진이 없으면 네이비 그라데이션으로 폴백.
"""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from common import SKILL_DIR, emit, hex_to_rgb, load_config, load_json


def colors(cfg):
    b = cfg["brand"]
    return {
        "primary": hex_to_rgb(b["primary_color"]),
        "dark": hex_to_rgb(b["primary_dark"]),
        "accent": hex_to_rgb(b["accent_color"]),
        "light": hex_to_rgb(b["text_light"]),
        "muted": hex_to_rgb(b["text_muted"]),
    }


class Fonts:
    def __init__(self, cfg):
        self.paths = cfg["fonts"]
        self._cache = {}

    def _resolve(self, p):
        p = Path(p)
        return str(p if p.is_absolute() else SKILL_DIR / p)

    def get(self, kind, size):
        key = (kind, size)
        if key not in self._cache:
            self._cache[key] = ImageFont.truetype(self._resolve(self.paths[kind]), size)
        return self._cache[key]


def line_h(font, extra=0):
    a, d = font.getmetrics()
    return a + d + extra


def wrap(draw, text, font, max_width):
    lines, cur = [], ""
    for word in text.split(" "):
        test = word if not cur else cur + " " + word
        if draw.textlength(test, font=font) <= max_width:
            cur = test
            continue
        if cur:
            lines.append(cur)
            cur = ""
        if draw.textlength(word, font=font) <= max_width:
            cur = word
        else:
            piece = ""
            for ch in word:
                if draw.textlength(piece + ch, font=font) <= max_width:
                    piece += ch
                else:
                    lines.append(piece)
                    piece = ch
            cur = piece
    if cur:
        lines.append(cur)
    return lines


def balanced_wrap(draw, text, font, max_width):
    """같은 줄 수를 유지하면서 가장 좁은 폭으로 줄바꿈 → 줄 길이 균형(고아 단어 방지)."""
    lines = wrap(draw, text, font, max_width)
    if len(lines) <= 1:
        return lines
    target = len(lines)
    lo, hi, best = 1, max_width, lines
    while lo <= hi:
        mid = (lo + hi) // 2
        w = wrap(draw, text, font, mid)
        if len(w) <= target:
            best, hi = w, mid - 1
        else:
            lo = mid + 1
    return best


def draw_lines(base, lines, font, x, y, fill, gap=8, align="left", W=None, shadow=0):
    """RGBA base에 여러 줄. align=center면 W 필요. shadow>0이면 반투명 검정 소프트 섀도."""
    d = ImageDraw.Draw(base)
    for ln in lines:
        lx = x if align == "left" else (W - d.textlength(ln, font=font)) / 2
        if shadow:
            d.text((lx + 2, y + 3), ln, font=font, fill=(0, 0, 0, shadow))
        d.text((lx, y), ln, font=font, fill=(*fill, 255))
        y += line_h(font) + gap
    return y


def cover_fit(im, w, h):
    sw, sh = im.size
    scale = max(w / sw, h / sh)
    nw, nh = max(int(sw * scale + 0.5), w), max(int(sh * scale + 0.5), h)
    im = im.resize((nw, nh), Image.LANCZOS)
    left, top = (nw - w) // 2, (nh - h) // 2
    return im.crop((left, top, left + w, top + h))


def vertical_gradient(w, h, c_top, c_bottom):
    base = Image.new("RGB", (w, h), c_top)
    top = Image.new("RGB", (w, h), c_bottom)
    mask = Image.new("L", (1, h))
    for y in range(h):
        mask.putpixel((0, y), int(255 * y / max(h - 1, 1)))
    return Image.composite(top, base, mask.resize((w, h)))


def load_photo(article):
    p = article.get("image_local")
    if p and Path(p).exists():
        try:
            return Image.open(p).convert("RGB")
        except Exception:
            return None
    return None


def bottom_scrim(w, h, C, start_frac=0.30, max_alpha=240):
    """카드1용: 아래로 갈수록 진해지는 네이비 그라데이션(사진은 위쪽에 보이게)."""
    scrim = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(scrim)
    start = int(h * start_frac)
    r, g, b = C["dark"]
    for y in range(h):
        if y < start:
            a = int(40 * (y / max(start, 1)))          # 상단 은은한 통일 틴트
        else:
            a = int(40 + (max_alpha - 40) * ((y - start) / (h - start)) ** 1.5)
        d.line([(0, y), (w, y)], fill=(r, g, b, min(a, 255)))
    return scrim


def base_card1(C, photo, W, H):
    if photo is not None:
        base = cover_fit(photo, W, H).convert("RGBA")
    else:
        base = vertical_gradient(W, H, C["accent"], C["dark"]).convert("RGBA")
    return Image.alpha_composite(base, bottom_scrim(W, H, C))


def base_textcard(C, photo, W, H, alpha=206):
    """카드2·3용: 사진 풀블리드 + 진한 네이비 오버레이(전면 가독성)."""
    if photo is not None:
        base = cover_fit(photo, W, H).convert("RGBA")
        ov = Image.new("RGBA", (W, H), (*C["dark"], alpha))
        base = Image.alpha_composite(base, ov)
    else:
        base = vertical_gradient(W, H, C["primary"], C["dark"]).convert("RGBA")
    return base


def pill(base, x, y, text, font, fg, bg):
    d = ImageDraw.Draw(base)
    tw = d.textlength(text, font=font)
    th = line_h(font)
    px, py = 28, 14
    d.rounded_rectangle([x, y, x + tw + px * 2, y + th + py * 2],
                        radius=(th + py * 2) // 2, fill=(*bg, 255))
    d.text((x + px, y + py), text, font=font, fill=(*fg, 255))
    return y + th + py * 2


# ---------------- 카드1: 히어로 ----------------
def render_hero(cfg, C, F, copy, article, size):
    W, H = size
    base = base_card1(C, load_photo(article), W, H)
    d = ImageDraw.Draw(base)
    m = 84

    pill(base, m, 80, "연극 뉴스", F.get("semibold", 34), C["dark"], C["accent"])

    title, sub = copy["hero"]["title"], copy["hero"]["subtitle"]
    tf, sf, srcf = F.get("extrabold", 90), F.get("regular", 42), F.get("regular", 28)
    maxw = W - m * 2
    tl = balanced_wrap(d, title, tf, maxw)
    sl = balanced_wrap(d, sub, sf, maxw)
    tg, sg, block, src_h = 4, 4, 30, line_h(srcf) + 16
    th = len(tl) * (line_h(tf) + tg)
    sh = len(sl) * (line_h(sf) + sg)
    y = H - 92 - src_h - sh - block - th
    y = draw_lines(base, tl, tf, m, y, C["light"], tg, shadow=110)
    y += block
    y = draw_lines(base, sl, sf, m, y, C["muted"], sg, shadow=90)
    y += 16
    ImageDraw.Draw(base).text((m, y), f"출처 · {article.get('domain','')}",
                              font=srcf, fill=(*C["muted"], 255))
    return base.convert("RGB")


# ---------------- 카드2: 요약 ----------------
def render_summary(cfg, C, F, copy, article, size):
    W, H = size
    base = base_textcard(C, load_photo(article), W, H)
    d = ImageDraw.Draw(base)
    s = copy["summary"]
    m, maxw = 96, 1080 - 96 * 2
    y = 150

    d.rounded_rectangle([m, y, m + 74, y + 12], radius=6, fill=(*C["accent"], 255))
    y += 40
    d.text((m, y), "핵심 요약", font=F.get("semibold", 38), fill=(*C["accent"], 255))
    y += line_h(F.get("semibold", 38)) + 22

    hf = F.get("extrabold", 62)
    y = draw_lines(base, balanced_wrap(d, s.get("heading", ""), hf, maxw), hf, m, y, C["light"], 4, shadow=90)
    y += 44

    bf = F.get("regular", 44)
    for it in s["body"]:
        cy = y + line_h(bf) // 2 - 9
        d.ellipse([m, cy, m + 18, cy + 18], fill=(*C["accent"], 255))
        y = draw_lines(base, wrap(d, it, bf, maxw - 48), bf, m + 48, y, C["light"], 4, shadow=80)
        y += 26

    comment = s.get("comment")
    if comment:
        cy = H - 208
        d.line([(m, cy), (W - m, cy)], fill=(*C["muted"], 160), width=2)
        draw_lines(base, balanced_wrap(d, comment, F.get("bold", 42), maxw),
                   F.get("bold", 42), m, cy + 32, C["accent"], 4, shadow=80)
    return base.convert("RGB")


# ---------------- 카드3: 마무리 ----------------
def render_outro(cfg, C, F, copy, article, size):
    W, H = size
    base = base_textcard(C, load_photo(article), W, H, alpha=214)
    d = ImageDraw.Draw(base)
    b = cfg["brand"]
    headline = (copy.get("outro") or {}).get("headline") or b["closing_message"]
    m, maxw = 96, 1080 - 96 * 2

    hf = F.get("extrabold", 64)
    hl = balanced_wrap(d, headline, hf, maxw)
    total = len(hl) * (line_h(hf) + 8) + 60 + line_h(F.get("bold", 52)) + 40 + line_h(F.get("regular", 38))
    y = (H - total) // 2

    y = draw_lines(base, hl, hf, m, y, C["light"], 8, align="center", W=W, shadow=90)
    y += 30
    d.rounded_rectangle([(W - 96) // 2, y, (W + 96) // 2, y + 8], radius=4, fill=(*C["accent"], 255))
    y += 54
    y = draw_lines(base, [b["account_handle"]], F.get("bold", 52), 0, y, C["accent"], 0, align="center", W=W, shadow=80)
    y += 26
    draw_lines(base, balanced_wrap(d, b["cta"], F.get("regular", 38), maxw),
               F.get("regular", 38), 0, y, C["muted"], 6, align="center", W=W, shadow=70)
    return base.convert("RGB")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--config")
    ap.add_argument("--copy")
    ap.add_argument("--article")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    cfg = load_config(args.config)
    copy = load_json(args.copy or out_dir / "copy.json")
    article = load_json(args.article or out_dir / "article.json", default={})
    if copy is None:
        raise SystemExit(f"copy.json 없음: {out_dir/'copy.json'}")

    C, F = colors(cfg), Fonts(cfg)
    size = (cfg["render"]["width"], cfg["render"]["height"])
    cards = [
        ("card1.png", render_hero(cfg, C, F, copy, article, size)),
        ("card2.png", render_summary(cfg, C, F, copy, article, size)),
        ("card3.png", render_outro(cfg, C, F, copy, article, size)),
    ]
    paths = []
    for name, img in cards:
        p = out_dir / name
        img.save(p, "PNG")
        paths.append(str(p))
    emit({"out_dir": str(out_dir), "cards": paths})


if __name__ == "__main__":
    main()
