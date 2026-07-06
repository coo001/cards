"""공용 헬퍼: 경로/설정/환경변수 로딩, 색상 변환, 결과 출력."""
import json
from pathlib import Path

import yaml
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent                     # .claude/skills/cards
PROJECT_ROOT = SKILL_DIR.parents[2]               # insta_card
CONFIG_PATH = SKILL_DIR / "config.yaml"
STATE_DIR = SKILL_DIR / "state"
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
