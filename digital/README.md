# 디지털자산 규제 요약 탭 (`digital/`)

대시보드의 '디지털자산 규제' 탭(iframe)과 '한눈에 보기' 카드가 이 폴더를 읽는다.

| 파일 | 내용 | 갱신 |
|---|---|---|
| `data/regulation.json` | 7개 핵심 시장(KR·US·JP·VN·SG·ID·AE) + 참고(EU·UK·HK) × 7개 주제 현황, 이슈, 연혁, 다가오는 일정 | 사람이 출처 확인 후 수정(`checked`·`verified_at` 날짜도 함께) |
| `data/feed.json` | 시장별 최근 30일 발표·기사(Google News RSS, 미 관보 API) | `scripts/fetch_feed.py`, 매일 07시 `digital-daily.yml`(LLM 미사용) |
| `data/detected.json` | 시장별 감독당국 공식 도메인 발표(최근 120일) + 주제 분류 + 시장별 자동 확인일 | `scripts/detect_updates.py`, 매일 07시 `digital-daily.yml` |
| `data/summary.json` | '한눈에 보기' 카드용 다가오는 일정 8개 | `scripts/build_summary.py`, 매일 07시 |

- 사람 검증일 이후 감지된 공식 발표는 현황표 칸에 "● 신규 공식 발표"로 표시된다. 판정 문구는 자동으로 바뀌지 않으니 출처를 보고 regulation.json을 고친 뒤 `checked`를 올린다.
- 자동 확인이 8일 넘게 안 된 시장은 ⚠. D-day도 화면에서 매번 계산한다.
- 출발점: 기존 Weekly Dashboard(2026-10-16 검증본) + 2026-10-20 추가 확인.
