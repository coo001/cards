---
name: cards
description: 연극 카드뉴스(캐러셀 3장)를 RSS 최신 뉴스에서 자동 생성해 imgbb 호스팅 후 Instagram에 발행. 사용자가 "/cards" 를 입력하거나 연극 카드뉴스 제작·발행을 요청할 때 사용. 특정 기사 URL을 주면 그 기사로 만든다.
---

# /cards — 연극 카드뉴스 자동 제작·발행

RSS에서 연극 최신 기사 1건을 골라 **카드 3장(1080×1350) 캐러셀**을 만들어 Instagram에 발행한다.
카피(제목·정리·캡션)는 **네가(Claude) 직접 작성**한다. 기계적 작업은 번들 스크립트가 처리한다.

경로: `SKILLDIR = C:/dev/insta_card/.claude/skills/cards`, `SCRIPTS = {SKILLDIR}/scripts`

## 인자
- `/cards` — 최신 연극 기사로 제작해 **확인 없이 바로 발행**(사용자에게 질문하지 않고 끝까지 진행)
- `/cards <기사URL>` — 해당 기사로 제작해 바로 발행
- `/cards --dry-run` — 렌더+호스팅까지만, 실제 발행 안 함 (검증용, 게시 안 됨)

**중요(사용자 지시): 이 스킬은 발행 여부를 절대 묻지 않는다. `--dry-run`이 아니면 항상 6단계 발행까지 자동으로 끝낸다.** (`--auto`는 기본 동작과 동일 — 붙여도 됨.)

## 실행 순서

### 0. 의존성 (최초 1회만)
```
python -m pip install -r "C:/dev/insta_card/.claude/skills/cards/scripts/requirements.txt" -q
```
이미 설치돼 있으면 건너뛴다.

### 1. 기사 후보 수집 → **이전 발행본과 대조** → 확정
사용자가 특정 기사 URL을 준 경우엔 이 단계를 건너뛰고 바로 `--url`로 4)만 실행한다.

1) 후보 목록 받기:
```
python "C:/dev/insta_card/.claude/skills/cards/scripts/fetch_news.py" --list
```
`RESULT_JSON`의 `candidates`(순위·title·url·score, 흥미도순·어휘중복 제외됨) + `recent_posted`(최근 발행 title·date·works)를 얻는다.

2) **이전 발행본과 의미로 대조(중요)**: `candidates`를 순위 위에서부터 보며, 각 후보가 `recent_posted`(필요하면 `state/posted.json`도 Read)와 **같은 공연/작품/행사를 다룬 기사인지 의미로 판단**한다. 어휘가 달라도 같은 사건이면(예: 같은 작품의 다른 매체 기사, 같은 공연 소식의 후속) **건너뛴다**. 제목만으로 판단하되 애매하면 그 후보 `url`을 열어(WebFetch나 브라우저) 확인한다. 처음으로 만나는 **"새로운 사건"** 후보를 고른다.

3) 판단 결과 처리:
- 명백히 같은 사건이라 건너뛴 후보는 그때만 넘기고, **확실히 재탕이면** `skip_article.py --url "<url>" --title "<제목>" --reason "<사유>"`로 blocklist(다음부터 자동 제외). 애매하면 blocklist하지 말 것(오판 시 좋은 기사를 영구 제외하게 됨).
- 후보가 전부 기존 사건 재탕이면 **"발행할 새 기사 없음"**으로 보고하고 종료(발행 안 함).

4) 확정 기사 빌드:
```
python "C:/dev/insta_card/.claude/skills/cards/scripts/fetch_news.py" --url "<고른 기사 url>"
```
출력의 `RESULT_JSON`에서 **`out_dir`** 과 기사 정보를 얻는다. `has_image=false`면 카드1은 그라데이션 배경으로 렌더된다(정상).

참고: `--list`/자동선택 모두 이미 발행/제외분과 **어휘 시그니처**(엔트리+본문)로 1차 중복을 거른 뒤, 위 2)의 **의미 대조**가 어휘로 못 잡는 "다른 매체·다른 문장·같은 사건"을 최종 차단한다. 흥미도 스코어(개막·초연·캐스팅·매진 등 하드뉴스 우선, 칼럼·로운드업·타장르 후순위)로 순위가 매겨져 있다.

### 2. 카피 작성 → `{out_dir}/copy.json`
`{out_dir}/article.json`(title·body·snippet·domain)을 Read해서 아래 스키마로 `copy.json`을 Write한다.
**한국어. 과장·낚시성 금지. 사실 기반. 글자 수 제한 준수.**

```json
{
  "hero":   { "title": "핵심 제목 (15~20자)", "subtitle": "부제 한 줄 (30자 이내)" },
  "summary": {
    "heading": "카드2 후킹 제목 (16자 이내, 1줄)",
    "lead": "뉴스 배경·맥락 리드 (60자 이내, 2줄 분량)",
    "body": ["키워드 — 설명 (한 항목 32자 이내)", "…", "…"],
    "comment": "관전 포인트/의미 한 줄 (40자 이내)"
  },
  "outro":  { "headline": "" },
  "caption": "핵심요약 3줄\n(줄바꿈)\n#해시태그 5개"
}
```
규칙:
- `hero.title` 15~20자 엄수(너무 길면 카드1에서 3줄로 넘침). `subtitle` 30자 이내.
- **카드2는 '요약'이라는 단어를 쓰지 말고** 뉴스를 **정리**해 보여준다. 상단 키커는 config의 `summary_kicker`로 자동(기본 "한눈에 정리").
- `summary.lead`: 기사 배경·맥락을 2줄 분량으로. "무슨 일인지"를 먼저 잡아준다.
- `summary.body`: 3개 권장(최대 4개). 각 항목은 `키워드 — 설명` 형태 권장(키워드가 볼드·골드로 강조됨). 구분자 `—` 없으면 일반 문장으로 렌더. 항목당 32자 이내, 설명은 한 줄에 들어오게.
- `summary.comment`: 관전 포인트나 뉴스의 의미를 짚는 한 줄.
- `outro.headline` 비우면 config의 기본 마무리 문구 사용. 특별한 소식이면 채운다.
- `caption`: **3줄 요약 + 빈 줄 + 해시태그 정확히 5개**. 해시태그는 `#연극 #공연 #카드뉴스`(기본) + 기사 특화 2개.
- `caption`에 **기사 원문 링크는 직접 넣지 않는다** — 발행 시 `publish_ig.py`가 해시태그 앞에 `🔗 기사 원문\n<url>`을 자동 삽입한다(`with_source_link`).

### 3. 렌더 (3장 모두 Pillow, 같은 기사 사진 공유 = 통일감)
```
python "C:/dev/insta_card/.claude/skills/cards/scripts/render_cards.py" --out-dir "<out_dir>"
```
디자인: 3장 전부 기사 대표 사진을 배경으로 공유(Variant A). 카드1은 하단 그라데이션 스크림 위 제목, 카드2·3은 진한 네이비 오버레이 위 텍스트. 폰트는 Pretendard(번들). `RESULT_JSON`의 `cards`(3개 PNG) 확인.

### 4. (질문 없이 바로 발행으로 진행)
**발행 여부를 묻지 않는다.** 카드 3장 PNG를 Read로 한 번 표시하고 `caption`도 보여준 뒤, **곧바로 5로 진행**한다(AskUserQuestion 쓰지 않음). `--dry-run`이면 렌더까지만 하고 발행은 6에서 `--dry-run`으로 검증만.

### 5. 호스팅
```
python "C:/dev/insta_card/.claude/skills/cards/scripts/upload_imgbb.py" --out-dir "<out_dir>"
```
`RESULT_JSON`의 `urls` 확인.

### 6. 발행
```
python "C:/dev/insta_card/.claude/skills/cards/scripts/publish_ig.py" --out-dir "<out_dir>"
```
`--dry-run`이면 `--dry-run` 붙여 실행(게시 안 됨). 성공 시 `RESULT_JSON`의 `permalink`를 사용자에게 보고.

### 7. 보고
발행 링크(permalink), 저장 폴더(`out_dir`), 사용한 기사 제목/출처를 한 줄로 요약해 보고.

## 주의
- 스크립트 stdout의 마지막 `RESULT_JSON {...}` 줄만 신뢰해 파싱한다. `[warn]`·`[skip]` 줄은 정보/경고(진행 가능).
- 중복 방지: `posted.json`(발행) + `skipped.json`(제외) 기준으로 URL·제목 완전일치 **및** 내용 시그니처(작품명·핵심어)로 같은 사건을 자동 필터. 특정 기사를 빼려면 `skip_article.py --out-dir <dir>` 또는 `--url <URL> --title "<제목>"`.
- IG 발행은 되돌릴 수 없지만, **사용자 지시로 이 스킬은 확인 없이 항상 발행한다.** 잘못 나가는 걸 막는 안전장치는 1단계의 선별 스코어 + 어휘/의미 중복 제외뿐이다. 발행 없이 확인만 하려면 `--dry-run`을 쓴다.
- 설정 변경은 `{SKILLDIR}/config.yaml`(피드·색·계정 핸들·마무리 문구·해시태그). 계정 핸들 `@your_account`는 실제 값으로 교체 필요.
- 필요한 .env 키: `IG_USER_ID`, `IG_ACCESS_TOKEN`, `IMGBB_API_KEY`.
- 로고(프로필 사진)는 `gen_logo.py`로 별도 생성(ChatGPT codex 사용, `~/.codex/auth.json` 필요): `python .../scripts/gen_logo.py --variants 3` → `output/logo/logo_*.png`.
