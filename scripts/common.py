"""공용 헬퍼: 경로/설정/환경변수 로딩, 색상 변환, 결과 출력, 기사 중복 판정."""
import html
import json
import re
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

# RESULT_JSON(한글 포함) stdout이 Windows 코드페이지로 깨지지 않게 UTF-8 강제.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent                     # .claude/skills/cards
PROJECT_ROOT = SKILL_DIR.parents[2]               # insta_card
CONFIG_PATH = SKILL_DIR / "config.yaml"
STATE_DIR = SKILL_DIR / "state"
POSTED_PATH = STATE_DIR / "posted.json"           # 발행 완료 기사
SKIPPED_PATH = STATE_DIR / "skipped.json"         # 사용자가 제외한 기사(중복 등)
ENV_PATH = PROJECT_ROOT / ".env"

load_dotenv(ENV_PATH)


def load_config(path=None):
    p = Path(path) if path else CONFIG_PATH
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def out_dir_for(date_str):
    d = PROJECT_ROOT / "output" / date_str
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def emit(obj):
    """스킬(Claude)이 파싱할 수 있게 결과를 한 줄 JSON으로 출력."""
    print("RESULT_JSON " + json.dumps(obj, ensure_ascii=False))


def with_source_link(caption, url, label="🔗 기사 원문"):
    """캡션에 기사 원문 링크 삽입(마지막 해시태그 줄 앞). 이미 URL 있으면 그대로."""
    caption = (caption or "").rstrip()
    if not url or url in caption:
        return caption
    block = f"{label}\n{url}"
    lines = caption.split("\n")
    if lines and lines[-1].lstrip().startswith("#"):     # 끝의 해시태그 줄 앞에 삽입
        body = "\n".join(lines[:-1]).rstrip()
        return f"{body}\n\n{block}\n\n{lines[-1].strip()}"
    return f"{caption}\n\n{block}"


# ---------- 기사 중복 판정 (같은 사건을 다룬 다른 URL/헤드라인까지 감지) ----------
_HTML_TAG_RE = re.compile(r"</?[A-Za-z!][^>]*>")            # <p> <img> <br/> 등 라틴 태그만
_WORK_RE = re.compile(r"[<〈《「『‘“]([^<>〈〉《》「」『』’”]{2,40})[>〉》」』’”]")  # <작품명>
_TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_STOP = {"연극", "공연", "무대", "작품", "배우", "관객", "개막", "이번", "오늘",
         "기자", "뉴스", "문화", "서울", "지난", "예정", "대해", "그리고", "위해"}


def _clean(text):
    """엔티티 복원 후 라틴 HTML 태그만 제거(<플리백> 같은 한글 꺾쇠는 보존)."""
    return _HTML_TAG_RE.sub(" ", html.unescape(text or ""))


def work_titles(text):
    """기사에서 <작품명>·‘작품명’ 형태의 제목 집합 추출(연극 기사 식별에 강력)."""
    return {m.strip() for m in _WORK_RE.findall(_clean(text)) if len(m.strip()) >= 2}


def content_sig(title, summary="", body=""):
    """기사 시그니처: 언급된 작품명 집합 + 핵심 토큰 집합."""
    text = _clean(" ".join(t for t in (title, summary, body) if t))
    works = {m.strip() for m in _WORK_RE.findall(text) if len(m.strip()) >= 2}
    tokens = {w for w in _TOKEN_RE.findall(text) if w not in _STOP}
    return {"works": sorted(works), "tokens": sorted(tokens)}


def sig_is_dup(a, b):
    """두 시그니처가 같은 사건을 가리키면 True."""
    if not a or not b:
        return False
    wa, wb = set(a.get("works", [])), set(b.get("works", []))
    shared = wa & wb
    if len(shared) >= 2:                          # 같은 작품 2개 이상 공유 → 동일 사건
        return True
    ta, tb = set(a.get("tokens", [])), set(b.get("tokens", []))
    j = len(ta & tb) / len(ta | tb) if (ta and tb) else 0.0
    if shared and j >= 0.45:                       # 작품 1개 공유 + 본문 유사
        return True
    return j >= 0.62                               # 작품 태그 없어도 본문이 매우 유사
