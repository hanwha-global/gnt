# 글로벌네트워크팀 Weekly Dashboard

한화투자증권 미래전략실 글로벌네트워크팀용 대시보드입니다. 공시자료를 기준으로
**글로벌 · 국내 · 한화투자증권** 세 영역의 해외 네트워크를 한 화면에서 봅니다.

사이트: https://hanwha-global.github.io/gnt/

| 영역 | 내용 | 데이터 | 갱신 |
|---|---|---|---|
| 글로벌 | 권역별 증권사 순위(한국·미국·일본·베트남·싱가포르·인도네시아·아부다비) + 시장별 한국계 현지법인 | DART, SEC EDGAR, 거래소·언론 발표 | 한국·미국 매주 자동 / 그 외 출처·기준일 표기 |
| 국내 | 국가별 진출 현황(법인/사무소 매트릭스), 해외법인 상세(검색·필터·CSV), 최근 공시·변동 감지 | 정기보고서 종속·관계회사, DART 타법인출자현황 | 매주 자동 |
| 한화투자증권 | 해외자회사 공시 실적(DART), 해외법인·출자 현황, 필수 대외보고 To-do | `hanwha/` 폴더 | 별도 작업 |
| 전략 인사이트 | 진출국 스코어카드, 현지 경쟁 구도(상장 증권사 + 한국계 현지법인 자본·ROE·시가총액·P/B), 밸류에이션 비교, 인도네시아·베트남 점유율 | IMF WEO·세계은행, Yahoo Finance, DART, IDX, HOSE(수동) | 평일 매일 자동(`insight.yml`) |

펀드·신탁·투자기구(Vehicle)·SPC는 법인명·업종 규칙(`scripts/gnd.py`)으로 자동 제외합니다.

## 구조

```
site/                 정적 웹(빌드 도구 없음)
  index.html  assets/app.js  assets/styles.css
  data/config.json               대상 회사 목록(이 파일만 바꾸면 다른 부서·계열사용으로 전환)
  data/domestic/seed.json        국내 해외법인 기준 데이터(FY2024 사업보고서 기반)
  data/domestic/dart_latest.json DART 자동 수집 결과(자동 생성)
  data/global/markets.json       권역별 순위(출처·기준일 포함)
  data/global/us_sec.json        SEC 자동 수집 결과(자동 생성)
hanwha/               한화투자증권 탭(있으면 함께 배포)
insight/              전략 인사이트 탭(insight/scripts/fetch_insight.py 가 평일 08:10 KST 데이터 갱신)
digital/              디지털자산 규제 탭(있으면 함께 배포, digital/data/summary.json 은 한눈에 보기 카드로)
workflow/            해외지분투자 Workflow 탭(절차 흐름도·단계별 신고·보고 기한, 정적 참고 자료)
guide/               국가별 해외진출 유의사항 탭(있으면 함께 배포, 감독당국 공식 발표는 guide-daily.yml 이 매일 감지)
scripts/              수집·빌드 스크립트(Python 표준 라이브러리만 사용)
.github/workflows/    pages.yml(빌드·배포), update-data.yml(주간 수집), filing-season.yml(3·4·8월 공시 시즌 매일 확인), news.yml(뉴스)
```

## 자동 업데이트 (LLM 토큰 0)

`update-data.yml`이 매주 월요일 09:00(KST)에 실행됩니다.

1. `scripts/update_dart.py`: 증권사별 최신 정기보고서를 찾아 자본·순이익을 갱신하고, 타법인출자현황에서 해외 직접출자 법인의 지분율·순이익을 갱신합니다. 기준 데이터에 없는 해외 법인은 "신규 후보"로 표시하고, 최근 120일 해외·출자 관련 공시를 피드로 모읍니다.
2. `scripts/update_sec.py`: 미국 상장 증권·IB 9개사의 자본·순이익을 SEC XBRL에서 가져옵니다.
3. `scripts/fetch_sub_trend.py`: 해마다의 사업보고서(토스는 감사보고서)와 최근 반기보고서 주석 '종속기업 요약재무정보'에서 해외법인별 영업수익·순이익 5개년 추이를 모읍니다(국내 탭 '5개년 손익 추이'). 보고서 접수번호를 저장해 새 보고서·정정본만 원문을 받습니다.
4. 바뀐 데이터만 커밋하고 Pages를 다시 배포합니다.

공시 시즌(사업보고서 3월·기한 3/31, 비상장사 감사보고서 4월, 반기보고서 8월·기한 8/14)에는 `filing-season.yml`이 매일 07:00(KST) DART 공시 목록만 확인하고, 새 보고서가 있으면 위 수집을 바로 다시 돌립니다.
거점(증권사 × 나라)별 최근 1년 뉴스는 `scripts/fetch_hub_news.py`가 매일 06:30 `news.yml`에서 모읍니다(Google News RSS, 주요 언론만).
한눈에 보기 맨 위 '진출국 전략 Takeaways'는 같은 아침 실행에서 `scripts/build_takeaways.py`가 만듭니다. 당사 현지법인이 있는 베트남·인도네시아·싱가포르마다 DART 손익·출자, 지수·환율·정책금리, 구조 뉴스(MSCI·FTSE), 한국계 경쟁사 뉴스, 현지 점유율을 규칙(LLM 없음)으로 읽어 지분 인수·증자·구조조정·비용·마케팅·제휴·리스크 중 3~4줄을 고릅니다. 새 DART 보고서, 판단·구간 변화, 3일 안의 새 구조·경쟁사·당사 뉴스, 정책금리 변경, 지수·환율 급변, 14일 경과 중 하나가 있을 때만 그 나라 문구를 바꾸고, 아니면 확인 시각만 남깁니다. 규칙이 하루만 안 잡히면(자료 공백) 이전 줄을 그대로 두고 이틀째 뺍니다. 판단에 쓰는 상태(본 기사·직전 공시·금리)는 `site/data/domestic/takeaways_state.json`에 따로 둡니다.
매주 수집에서는 `scripts/broker_rank.py`가 DART 주요계정으로 국내 전체 증권사 자기자본 순위를 계산합니다(한눈에 보기 '당사 자기자본 순위', 글로벌 › 한국 표).

### 처음 한 번 설정

- (선택) Settings → Secrets and variables → Actions → Variables: `REMINDER_ASSIGNEE` = 대외보고 알림 이슈를 배정할 GitHub 계정(비우면 jeongpilchoi1992-hash)
- Settings → Secrets and variables → Actions: `DART_API_KEY`(필수), `ECOS_API_KEY`(한화 탭 매크로용)
- Settings → Pages → Source: **GitHub Actions**
- Settings → Secrets and variables → Actions → `SEC_USER_AGENT` = `이름 이메일주소` (SEC가 연락처 없는 요청을 403으로 막음. Secrets에 두면 로그에서 가려짐, Variables도 동작)

## 다른 부서·계열사로 확산

대상 회사는 `site/data/config.json` 한 파일로 정합니다. 회사명을 DART 공시명 그대로 바꾸면
코드 수정 없이 같은 대시보드를 쓸 수 있습니다.

- 자산운용사 해외 네트워크: 미래에셋자산운용, 삼성자산운용, 한화자산운용 등
- 보험사 해외 법인: 한화생명, 삼성생명 등
- 그룹 전략·IR 부서: 계열사 해외법인 현황 모니터링

`markets.json`에 시장을 추가하면 권역 탭이 늘어납니다.

## 보안과 사내 적용 조건

- 인증키(DART·ECOS)는 GitHub Secrets에만 두고 코드·커밋·로그에 남기지 않습니다. 키가 없으면 수집 단계는 아무것도 바꾸지 않고 넘어갑니다.
- 사이트에는 공시로 공개된 정보만 올립니다. 비공개 재무 수치와 주재원 인적사항은 공개 저장소에 올리지 않습니다.
- 사내 적용 시에는 다음을 거칩니다.
  - 사내 GitHub Enterprise 또는 사내 웹서버(정적 파일)로 옮겨 사내망에서만 열리게 합니다.
  - 외부 API(DART·SEC·ECOS) 호출 허용을 정보보호부서에서 검토받습니다.
  - 정보보호 심의를 거칩니다. 서버·DB가 없는 정적 페이지라 심의 범위가 작습니다.
- 외부 CDN은 글꼴(Pretendard) 하나뿐이며, 막혀도 시스템 글꼴로 동작합니다.

## 로컬 실행

```bash
python -m unittest discover -s tests
python scripts/build_site.py && python -m http.server -d _site 8000
python scripts/run_local.py --build   # 자동 수집 전 단계를 내 PC에서 실행(필요한 API 키를 숨김 입력창으로 물음)
```

### API 키 (내 PC에서 실행할 때)

- GitHub Actions는 지금처럼 저장소 Secrets(`DART_API_KEY`, `ECOS_API_KEY`, `SEC_USER_AGENT`, `LAW_OC`)를 씁니다. Actions에서는 키를 묻지 않습니다.
- 내 PC에서는 키를 아래 순서로 찾습니다(`scripts/keys.py`).
  1. 환경변수
  2. 저장소 루트의 `.env` 파일: `.env.example`을 `.env`로 복사해 값을 채웁니다. `.env`는 `.gitignore`에 들어 있어 커밋되지 않습니다.
  3. 둘 다 없으면 실행할 때 화면에 보이지 않는 입력창으로 묻습니다. Enter만 누르면 그 단계를 건너뜁니다.
- 입력창에 넣은 값은 그 실행 동안 메모리에만 있고 파일·로그·저장소 어디에도 남지 않습니다.
- `python scripts/run_local.py --only dart`처럼 일부 단계만 돌릴 수 있습니다. 개별 스크립트(`python scripts/update_dart.py` 등)를 직접 실행해도 같은 방식으로 묻습니다.

기준 데이터 재생성: `python scripts/build_seed.py "<국내증권사 리서치 ..._설립취득.xlsx>"` (openpyxl 필요)

## 작업 방식

GitHub(브랜치·PR·Actions)와 Cursor(`.cursor/rules/dashboard.mdc`에 작업 규칙)를 함께 씁니다.
