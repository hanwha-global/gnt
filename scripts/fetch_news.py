"""국내 증권사 해외진출 뉴스: Google News RSS(키 불필요, LLM 미사용)에서 공신력 있는 매체 기사만 모은다.

- 검색어: 증권사별 '해외·현지법인·글로벌' 조합과 업계 전체 검색어
- 매체 화이트리스트(SOURCES)에 있는 기사만 남기고, 제목에 증권사(또는 증권업계)와 해외 관련 단어가 함께 있어야 한다
- 제목이 거의 같은 기사(통신사 전재 등)는 하나만 남긴다

결과는 site/data/domestic/news.json. 매일 아침 GitHub Actions(news.yml)가 돌린다. 수집이 비면 이전 파일을 유지한다.
"""
import json
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import net  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "data" / "domestic" / "news.json"
CONFIG = ROOT / "site" / "data" / "config.json"
KEEP_DAYS = 90
MAX_ITEMS = 60
KST = timezone(timedelta(hours=9))

# 공신력 있는 매체(Google News 표기 기준, 부분 일치). 여기 없는 매체 기사는 버린다.
# 국내 매체(국내 언론사의 영문판 포함)
DOMESTIC = [
    "연합뉴스", "연합인포맥스", "뉴스1", "뉴시스", "한국경제", "한경", "매일경제", "머니투데이", "서울경제", "이데일리",
    "파이낸셜뉴스", "헤럴드경제", "아시아경제", "조선비즈", "조선일보", "중앙일보", "동아일보", "한겨레", "경향신문",
    "한국일보", "서울신문", "국민일보", "문화일보", "세계일보", "아주경제", "이투데이", "더벨", "비즈니스포스트", "뉴데일리",
    "글로벌이코노믹", "데일리안", "머니S", "디지털타임스", "전자신문", "KBS", "MBC", "SBS", "YTN", "SBS Biz", "한국경제TV",
    "MBN", "Korea Times", "Korea Herald", "Korea JoongAng Daily", "Yonhap", "KED Global", "Korea Economic Daily", "BusinessKorea",
    "Pulse by Maeil Business",
]
# 해외 매체·기관: 글로벌 통신·경제지, 진출국의 전국 단위 주요 언론, 감독당국·지수 회사
FOREIGN = [
    "Bloomberg", "Reuters", "Financial Times", "Wall Street Journal", "Nikkei", "CNBC", "The Economist", "Associated Press",
    "AP News", "Barron's", "MarketWatch", "DealStreetAsia", "FinanceAsia", "The Asset", "Euromoney", "The Banker",
    "Asia Asset Management", "Institutional Investor", "Business Times", "The Straits Times", "CNA", "Channel NewsAsia",
    "The Edge Singapore", "South China Morning Post", "Caixin", "Japan Times", "Kyodo",
    # 베트남
    "VnExpress", "Vietnam Investment Review", "Vietnam News", "VietnamPlus", "Tuoi Tre", "Tuổi Trẻ", "Thanh Niên", "Thanh Nien",
    "VnEconomy", "Báo Đầu tư", "Đầu tư Chứng khoán", "Thời báo Tài chính", "Tạp chí Tài chính", "CafeF", "Người Lao Động",
    # 인도네시아
    "Jakarta Globe", "Jakarta Post", "Kontan", "Bisnis", "CNBC Indonesia", "Kompas", "Tempo", "ANTARA", "Investor.id",
    "Katadata", "IDX Channel", "detik",
    # 인도·몽골·브라질·그리스
    "Economic Times", "Mint", "Business Standard", "Moneycontrol", "BusinessLine", "Financial Express", "Montsame", "UB Post",
    "Valor Econômico", "Exame", "Kathimerini",
    # 감독당국·지수 회사(보도자료가 뉴스 검색에 잡히는 경우)
    "MSCI", "FTSE Russell", "Otoritas Jasa Keuangan", "OJK", "Monetary Authority of Singapore", "Securities and Futures Commission",
    "Ủy ban Chứng khoán", "State Securities Commission",
]
SOURCES = DOMESTIC + FOREIGN
# 제목에 있어야 하는 해외 관련 단어
OVERSEAS = ["해외", "현지법인", "현지 법인", "글로벌", "진출", "인수", "법인 설립", "지분 투자", "지분투자", "뉴욕", "홍콩", "런던",
            "싱가포르", "베트남", "인도네시아", "인도", "미국", "일본", "중동", "아부다비", "두바이", "사우디", "몽골", "브라질",
            "태국", "유럽", "월가", "overseas", "global", "abroad", "expansion", "acquisition", "acquire", "subsidiary",
            "vietnam", "indonesia", "hong kong", "new york", "india", "singapore", "london"]
# 홍보·시황성 기사 제외
NOISE = ["이벤트", "경품", "추천주", "특징주", "목표가", "목표주가", "매수 유지", "투자의견", "리포트", "[마감시황]", "시황",
         "해외주식 거래", "해외주식·", "글로벌 데스크", "수수료 혜택", "부고", "인사]", "퇴직연금", "中 증권사", "中증권", "中,", "중국 증권사",
         "베트남 증권사", "AI사업"]
ENGLISH = {"미래에셋증권": "Mirae Asset Securities", "한국투자증권": "Korea Investment & Securities", "NH투자증권": "NH Investment & Securities",
           "삼성증권": "Samsung Securities", "키움증권": "Kiwoom Securities", "KB증권": "KB Securities",
           "신한투자증권": "Shinhan Securities", "하나증권": "Hana Securities", "한화투자증권": "Hanwha Investment & Securities",
           "토스증권": "Toss Securities"}


# 제목에서 증권사를 알아보는 표기(약칭 포함). 설정 파일의 회사 이름은 항상 포함한다.
ALIASES = {"미래에셋증권": ["미래에셋"], "한국투자증권": ["한투", "한국투자"], "NH투자증권": ["NH투자", "NH證"],
           "삼성증권": [], "키움증권": ["키움"], "KB증권": [], "신한투자증권": ["신한투자", "신한證"], "하나증권": [],
           "한화투자증권": ["한화투자", "한화證"], "토스증권": []}


def firms_and_aliases():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    return {f["name"]: [f["name"], *ALIASES.get(f["name"], []), *([ENGLISH[f["name"]]] if f["name"] in ENGLISH else [])]
            for f in cfg["firms"]}


def queries(aliases):
    qs = [("증권사 해외법인", "ko"), ("증권사 해외 진출", "ko"), ("증권사 현지법인", "ko"), ("증권업계 글로벌 사업", "ko"),
          ("Korean brokerage overseas expansion", "en"), ("Korean securities firm acquisition overseas", "en")]
    for firm in aliases:
        qs.append((f"{firm} 해외법인 OR 현지법인 OR 해외 진출", "ko"))
        if firm in ENGLISH:
            qs.append((f'"{ENGLISH[firm]}"', "en"))
    return qs


def rss_url(q, lang, days=60):
    hl, gl, ceid = ("ko", "KR", "KR:ko") if lang == "ko" else ("en-US", "US", "US:en")
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": f"{q} when:{days}d", "hl": hl, "gl": gl, "ceid": ceid})


def trusted(src):
    s = (src or "").lower()
    return any(t.lower() in s for t in SOURCES)


def foreign(src):
    """해외 매체·기관 기사인지(국내 언론사의 영문판은 국내로 본다)."""
    s = (src or "").lower()
    return not re.search(r"[가-힣]", s) and not any(t.lower() in s for t in DOMESTIC) and any(t.lower() in s for t in FOREIGN)


def mentions(title, aliases):
    t = title.lower()
    return [firm for firm, names in aliases.items() if any(n.lower() in t for n in names)]


def relevant(title, firms):
    t = title.lower()
    if any(n.lower() in t for n in NOISE):
        return False
    who = firms or re.search(r"증권사|증권업계|증권가|brokerage|securities firm", t)
    return bool(who) and any(k in t for k in OVERSEAS)


def norm_title(t):
    return re.sub(r"[^0-9a-z가-힣]", "", t.lower())[:28]


def parse(xml_bytes, aliases, since):
    items = []
    for it in ET.fromstring(xml_bytes).iter("item"):
        title = (it.findtext("title") or "").strip()
        src = (it.findtext("source") or "").strip()
        for _ in range(2):  # 'OO - 머니투데이 - 머니투데이' 처럼 매체명이 두 번 붙는 경우
            if src and title.endswith(f" - {src}"):
                title = title[: -len(src) - 3].strip()
        # 국내 매체의 영문 번역판은 같은 기사가 두 번 나오므로 뺀다
        if re.search(r"[가-힣]", src) and not re.search(r"[가-힣]", title):
            continue
        try:
            when = parsedate_to_datetime(it.findtext("pubDate")).astimezone(KST)
        except Exception:
            continue
        if when < since or not trusted(src):
            continue
        firms = mentions(title, aliases)
        if not relevant(title, firms):
            continue
        items.append({"date": when.strftime("%Y-%m-%d"), "time": when.strftime("%H:%M"), "title": title, "src": src,
                      "url": (it.findtext("link") or "").strip(), "firms": firms})
    return items


def main():
    now = datetime.now(KST)
    since = now - timedelta(days=KEEP_DAYS)
    aliases = firms_and_aliases()
    prev = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"items": []}
    found, errors = [], []
    for q, lang in queries(aliases):
        try:
            found += parse(net.get(rss_url(q, lang), timeout=25), aliases, since)
        except Exception as e:
            errors.append(f"{q}: {e}")
    # 이전 수집분도 기간 안이면 이어 붙인다(검색 결과에서 밀려난 기사 보존)
    # 필터 규칙이 바뀌어도 맞도록 이전 기사도 같은 규칙으로 다시 거른다
    found += [x for x in prev.get("items", []) if x.get("date", "") >= since.strftime("%Y-%m-%d") and trusted(x.get("src"))
              and relevant(x["title"], x.get("firms") or []) and not (re.search(r"[가-힣]", x.get("src", "")) and not re.search(r"[가-힣]", x["title"]))]
    seen, items = set(), []
    for x in sorted(found, key=lambda x: (x["date"], x.get("time", "")), reverse=True):
        k = norm_title(x["title"])
        if k in seen:
            continue
        seen.add(k)
        items.append(x)
    items = items[:MAX_ITEMS]
    if not items:
        print("수집된 기사 없음: 이전 파일 유지", errors[:3])
        return 0
    OUT.write_text(json.dumps({"updated_at": now.isoformat(timespec="minutes"), "source": "Google News RSS · 매체 화이트리스트",
                               "sources": SOURCES, "items": items, "errors": errors[:10]}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"saved {OUT.name}: {len(items)}건 (오류 {len(errors)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
