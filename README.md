# /cards — 연극 카드뉴스 자동 제작·발행 스킬

Claude Code(또는 oh-my-claudecode)에서 `/cards` 한 번으로 **연극 최신 뉴스 → 카드 3장 캐러셀 → Instagram 발행**까지 자동화하는 스킬.

## 무엇을 하나
1. **수집** — 언론사 문화 RSS에서 "연극" 기사 1건 선택, 대표 사진(og:image, 광고 제외) 다운로드
2. **카피** — Claude가 기사 본문을 읽고 제목·요약·캡션 작성(`copy.json`)
3. **렌더** — 카드 3장(1080×1350) 생성. 3장 모두 같은 기사 사진을 배경으로 공유(통일감), Pretendard 폰트
   - 카드1 히어로: 사진 + 핵심 제목
   - 카드2 요약: 사진 위 진한 오버레이 + 핵심요약 3줄 + 코멘트
   - 카드3 마무리: 마무리 문구 + 계정 핸들 + CTA
4. **호스팅** — imgbb 업로드로 공개 URL 확보(Instagram API는 공개 URL 필요)
5. **발행** — graph.instagram.com으로 캐러셀 1건 게시

## 설치
이 폴더를 `.claude/skills/cards/` 에 둔다. 의존성:
```
python -m pip install -r scripts/requirements.txt
```

## 필요 설정
프로젝트 루트(스킬 상위)에 `.env` (이 repo에는 커밋되지 않음 — `.gitignore`):
```
IG_USER_ID=...
IG_ACCESS_TOKEN=...        # Instagram Graph API (graph.instagram.com) 토큰
IMGBB_API_KEY=...          # https://api.imgbb.com
```
`config.yaml` — RSS 피드, 브랜드 색/문구, 계정 핸들, 폰트 경로.

## 사용
```
/cards                # 최신 기사로 제작 → 미리보기 → 확인 후 발행
/cards <기사URL>      # 특정 기사로 제작
/cards --auto         # 확인 없이 발행
/cards --dry-run      # 렌더·호스팅까지만(게시 안 함)
```

## 로고(선택)
프로필용 원형 엠블럼 로고를 ChatGPT(codex OAuth) 이미지 생성으로 뽑는다. `~/.codex/auth.json`(codex login) 필요:
```
python scripts/gen_logo.py --variants 3   # → output/logo/logo_*.png
```

## 라이선스
번들 폰트 Pretendard © orioncactus, SIL Open Font License 1.1.
