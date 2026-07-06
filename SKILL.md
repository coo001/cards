---
name: cards
description: 연극 카드뉴스(캐러셀 3장)를 RSS 최신 뉴스에서 자동 생성해 imgbb 호스팅 후 Instagram에 발행. 사용자가 "/cards" 를 입력하거나 연극 카드뉴스 제작·발행을 요청할 때 사용. 특정 기사 URL을 주면 그 기사로 만든다.
---

# /cards — 연극 카드뉴스 자동 제작·발행

RSS에서 연극 최신 기사 1건을 골라 **카드 3장(1080×1350) 캐러셀**을 만들어 Instagram에 발행한다.
카피(제목·요약·캡션)는 **네가(Claude) 직접 작성**한다. 기계적 작업은 번들 스크립트가 처리한다.

경로: `SKILLDIR = C:/dev/insta_card/.claude/skills/cards`, `SCRIPTS = {SKILLDIR}/scripts`

## 인자
- `/cards` — RSS 최신 기사로 제작 → 미리보기 → **확인 후 발행**
- `/cards <기사URL>` — 해당 기사로 제작
- `/cards --auto` — 확인 없이 바로 발행
- `/cards --dry-run` — 렌더+호스팅까지만, 실제 발행 안 함 (컨테이너만 생성해 검증)

## 실행 순서

### 0. 의존성 (최초 1회만)
```
python -m pip install -r "C:/dev/insta_card/.claude/skills/cards/scripts/requirements.txt" -q
```
이미 설치돼 있으면 건너뛴다.

### 1. 기사 수집
```
python "C:/dev/insta_card/.claude/skills/cards/scripts/fetch_news.py"
```
URL 지정 시 `--url "<기사URL>"` 추가. 출력의 `RESULT_JSON` 줄을 파싱해 **`out_dir`** 과 기사 정보를 얻는다.
`has_image=false`면 대표사진이 없어 카드1은 그라데이션 배경으로 렌더된다(정상). 필요하면 사용자에게 URL 지정을 제안.

### 2. 카피 작성 → `{out_dir}/copy.json`
`{out_dir}/article.json`(title·body·snippet·domain)을 Read해서 아래 스키마로 `copy.json`을 Write한다.
**한국어. 과장·낚시성 금지. 사실 기반. 글자 수 제한 준수.**

```json
{
  "hero":   { "title": "핵심 제목 (15~20자)", "subtitle": "부제 한 줄 (30자 이내)" },
  "summary": {
    "heading": "카드2 상단 제목 (18자 이내)",
    "body": ["요약 1 (45자 이내)", "요약 2", "요약 3"],
    "comment": "마지막 한 줄 코멘트 (40자 이내)"
  },
  "outro":  { "headline": "" },
  "caption": "핵심요약 3줄\n(줄바꿈)\n#해시태그 5개"
}
```
규칙:
- `hero.title` 15~20자 엄수(너무 길면 카드1에서 3줄로 넘침). `subtitle` 30자 이내.
- `summary.body`는 정확히 3줄, 각 줄 기사 핵심 사실.
- `outro.headline` 비우면 config의 기본 마무리 문구 사용. 특별한 소식이면 채운다.
- `caption`: **3줄 요약 + 빈 줄 + 해시태그 정확히 5개**. 해시태그는 `#연극 #공연 #카드뉴스`(기본) + 기사 특화 2개.

### 3. 렌더 (3장 모두 Pillow, 같은 기사 사진 공유 = 통일감)
```
python "C:/dev/insta_card/.claude/skills/cards/scripts/render_cards.py" --out-dir "<out_dir>"
```
디자인: 3장 전부 기사 대표 사진을 배경으로 공유(Variant A). 카드1은 하단 그라데이션 스크림 위 제목, 카드2·3은 진한 네이비 오버레이 위 텍스트. 폰트는 Pretendard(번들). `RESULT_JSON`의 `cards`(3개 PNG) 확인.

### 4. 미리보기 + 확인
`--auto`가 아니면: 카드 3장 PNG를 Read로 표시하고, `caption`을 함께 보여준 뒤
**AskUserQuestion으로 발행 여부 확인**(발행 / 카피수정 후 재렌더 / 취소). `--auto`면 건너뛰고 5로.

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
- 스크립트 stdout의 마지막 `RESULT_JSON {...}` 줄만 신뢰해 파싱한다. `[warn]` 줄은 경고(진행 가능).
- IG 발행은 되돌릴 수 없으므로 `--auto`가 아니면 반드시 4단계 확인을 거친다.
- 설정 변경은 `{SKILLDIR}/config.yaml`(피드·색·계정 핸들·마무리 문구·해시태그). 계정 핸들 `@your_account`는 실제 값으로 교체 필요.
- 필요한 .env 키: `IG_USER_ID`, `IG_ACCESS_TOKEN`, `IMGBB_API_KEY`.
- 로고(프로필 사진)는 `gen_logo.py`로 별도 생성(ChatGPT codex 사용, `~/.codex/auth.json` 필요): `python .../scripts/gen_logo.py --variants 3` → `output/logo/logo_*.png`.
