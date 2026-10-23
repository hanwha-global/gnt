# 한화투자증권 글로벌네트워크 현황 (hanwha/)

대시보드의 세 번째 섹션입니다. `hanwha/index.html`은 정적 페이지이며 `data/*.json`만 읽습니다.
**공개 자료로만 동작합니다.** 해외자회사 숫자는 모두 DART 공시이고, 출자 이력 표 하나만 내부 출자내역을 손으로 옮긴 값입니다(사용자 결정 2026-10-23).

| 탭 | 데이터 | 만드는 스크립트 |
|---|---|---|
| 해외자회사 실적 (DART 공시) | `data/dart_subs.json`, `data/entities.json` | `scripts/fetch_dart_subs.py` (Actions, `DART_API_KEY` secret) |
| 해외법인·출자 현황 | 위 두 파일 + `data/investments.json`(출자 이력, 수동) | 위와 같음 + `scripts/build_investments.py` |
| 필수 대외보고 일정·체크리스트 | `data/regulatory.json`, `downloads/hanwha_regulatory.ics` | `scripts/build_deadlines.py`. 정기보고서는 DART 접수로 자동 완료, 사건 항목은 `manual`, 그 밖의 완료는 `done_ids` |
| YTD Macro (금리·지수·환율) | `data/markets.json`, `data/rate_calendar.json` | `scripts/fetch_markets.py`, `scripts/build_rate_calendar.py` |
| 다운로드 (엑셀·1장 보고서) | `downloads/해외자회사_공시실적.xlsx`, `downloads/해외자회사_공시실적_1장보고서.docx·pdf` | `scripts/build_downloads.py` |

## 자동 갱신 (LLM·토큰 없음)

`.github/workflows/hanwha-markets.yml`이 평일 07:30·16:30(KST)에 다음을 실행하고 바뀐 파일만 커밋·재배포합니다.

1. `fetch_markets.py`: 지수·환율·정책금리.
2. `fetch_dart_subs.py`: 최근 550일 DART 정기보고서 목록을 읽어 **가장 최근 사업보고서**와 **그 뒤 가장 최근 분기·반기보고서**의 연결재무제표 주석 「종속기업 요약재무정보」(자산·부채·영업수익·당기순이익)와 「타법인 출자현황」(최초 취득·기초·증감·기말 장부가·지분율)을 받습니다.
   새 보고서의 출자현황이 아직 비어 있으면 직전 정기보고서로, 호출이 모두 실패하면 직전 파일 값으로 물러섭니다. 요약재무 표를 못 읽으면 숫자는 그대로 두고 접수 목록만 고칩니다.
   3분기보고서(분기 종료 후 45일, 2026년은 11/16 기한)가 올라오면 다음 실행에서 화면이 1H26 → 9M26으로 바뀌고 ROE 연환산 배수(×2 → ×12/9)도 따라 바뀝니다. 사업보고서(3월)가 올라오면 FY 열이 새 연도로 바뀝니다.
3. `build_deadlines.py`: 12개월 대외보고 일정. DART에 접수된 정기보고서 항목은 자동으로 완료 처리됩니다.
4. `build_downloads.py --check`: 공시 기준(보고서 접수번호, 공시 숫자, 다음 공시 항목, 출자내역, 기준 정보, 스크립트)이 바뀐 날만 엑셀·1장 보고서를 다시 만듭니다(LibreOffice로 PDF). 기준은 `downloads/basis.json`이고, 화면의 다운로드 기준 문구도 이 파일에서 읽습니다.
   다운로드를 만들다 실패하면 반쯤 바뀐 파일은 되돌리고 시장·공시 데이터만 커밋하며, 다음 실행에서 다시 만듭니다.

`update-data.yml`(주간)도 `fetch_dart_subs.py`와 `build_deadlines.py`를 한 번 더 돌립니다.

## 숫자 규칙

- 같은 표 안은 전 사 같은 시점. 표마다 오른쪽 위에 기준 보고서와 단위를 적습니다.
- ROE = 누적 순이익 × (12 ÷ 개월 수) ÷ 기말 자본(자산 − 부채). 지배지분 순이익 = 순이익 × 지분율(타법인 출자현황).
- 요약재무정보는 법인 단위·연결 조정 전 금액입니다. 법인을 취득한 해의 사업보고서에는 재무상태만 있고 손익이 없을 수 있습니다(인도네시아 운용(CAM), 2025-12-19 취득).
- 법인 표시명은 `data/entities.json`의 `label`("베트남 법인(PTSV)" 형식). 법인이 늘면 여기에 한 줄을 넣고 `fetch_dart_subs.py`의 `NAMES`에 공시 표기를 더합니다.

## 출자 이력 (수동)

회차별 송금일·현지통화 금액은 공시에 없어 내부 출자내역에서 옮깁니다. 증자·인수가 있으면 출자내역 엑셀을 고친 뒤:

```bash
python hanwha/scripts/build_investments.py "Final Project/(한화증권) 해외자회사_출자내역_병합.xlsx"
```

옮기는 열은 투자내역·취득방법·해외직접투자신고일·송금일·통화·현지통화 투자액·원화 취득원가·투자 후 지분율뿐입니다. **비고(계좌·SWIFT), 기안 번호, 주수·주당가격, USD 송금액·환율은 옮기지 않습니다.** 화면에는 '내부 출자내역 기준(수동)'으로 표시하고, 법인별 누적 원화 취득원가를 DART 기말 장부가와 나란히 보여 줍니다.

## 공개 범위 (보안)

- 공시 자료와 출자 이력만 저장소에 둡니다. 2026 사업계획·계획 대비 진척률, 현지 결산(사업부문별 손익), K-IFRS 내부 양식, 비공시 특이사항, 주재원 현황은 넣지 않습니다.
- API 키(`DART_API_KEY`, `ECOS_API_KEY`)는 GitHub Secrets에만 둡니다. 코드·커밋·로그에 남기지 않습니다.
- 원천 파일(재무제표, 출자내역 엑셀)은 커밋하지 않습니다.

## YTD Macro 출처 (키 불필요, LLM 없음)

- 주가지수·달러인덱스: Yahoo Finance 지연 시세. VN-Index는 VNDirect 공개 시세.
- 환율: 한국은행 ECOS 매매기준율(`ECOS_API_KEY`), 실패 시 Yahoo Finance. 원/동은 달러 교차로 계산.
- 정책금리: BIS 중앙은행 정책금리(월말). 베트남 SBV는 `fetch_markets.py`의 `SBV_CHANGES`에 변경 이력을 직접 추가.
- 금리 결정 일정: `build_rate_calendar.py`가 평일마다 Fed·ECB·BoE·BoJ·BoC 등 공식 일정 페이지를 읽습니다. 못 읽은 은행은 `FALLBACK` 목록을 쓰고 화면에 "보조"로 표시합니다.

## 대외보고 누락 방지

- `build_deadlines.py`가 법정 기한(분기·반기보고서 45일, 사업보고서 90일, 연간사업실적보고서 결산 후 5개월 등)을 주말 보정해 12개월 일정을 만듭니다.
- `downloads/hanwha_regulatory.ics`를 Outlook·Google 캘린더에 인터넷 일정으로 구독하면 마감 14일·3일 전에 알림이 옵니다.
- `.github/workflows/hanwha-reminders.yml`이 매주 월요일 08:30(KST) 30일 이내·기한 경과 항목을 GitHub 이슈(라벨 `대외보고-알림`)로 올립니다.
- 증자·신규사업 같은 사건은 `regulatory.json`의 `manual`에 추가하고, 단계는 화면의 "이런 일이 생기면"(`playbook`)을 따릅니다.

## 예외 표시

첫 화면 상단에 예외를 모아 보여 줍니다: 공시 데이터 없음, 최신 공시에 빠진 법인, 기한이 지났는데 완료 표시가 없는 대외보고, 시장 데이터 미수집.
