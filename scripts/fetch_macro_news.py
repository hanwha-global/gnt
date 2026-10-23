"""국가별 매크로·시장 뉴스: Google News RSS(키 불필요, LLM 미사용)에서 공신력 있는 매체의 주요 헤드라인을 고른다.

한눈에 보기 '이번 주 핵심 포인트'의 국가별 매크로 줄에 붙는다. 국가마다 검색어로 모은 뒤
- 매체 화이트리스트(fetch_news.SOURCES + 해외 매체)에 있는 기사만
- 제목에 그 나라 표기와 시장·거시 단어가 함께 있는 기사만
- 지수 편입·강등(MSCI·FTSE Russell 등) 같은 구조적 뉴스를 먼저, 그다음 최신순으로 국가별 3건까지 남긴다.

결과는 site/data/global/macro_news.json. 매일 news.yml 이 돌린다. 수집이 비면 이전 파일을 유지한다.
"""
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import net  # noqa: E402
from fetch_news import KST, SOURCES, norm_title, rss_url  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "site" / "data" / "global" / "macro_news.json"
KEEP_DAYS = 30
PER_COUNTRY = 3
EXTRA_SOURCES = ["Jakarta Post", "Nikkei Asia", "CNBC", "Associated Press", "AP News", "Wall Street Journal", "The Economist",
                 "South China Morning Post", "Vietnam Investment Review", "VnExpress International", "Business Standard",
                 "The Economic Times", "Mint", "Channel NewsAsia", "CNA", "Euronews", "Barron's", "MarketWatch"]

# 국가: (표시 이름, 제목에 있어야 하는 표기, 검색어)
COUNTRIES = {
    "KR": ("한국", ["korea", "korean", "kospi", "한국", "코스피", "한은", "금통위", "원화", "원·달러", "원/달러"],
           [("MSCI 선진지수 한국", "ko"), ("한국은행 기준금리", "ko"), ("코스피 외국인", "ko"), ("MSCI Korea developed market", "en")]),
    "US": ("미국", ["fed", "fomc", "powell", "u.s.", " us ", "treasury", "wall street", "미국", "연준", "美"],
           [("Fed rate decision", "en"), ("FOMC 금리", "ko"), ("US Treasury yields", "en")]),
    "ID": ("인도네시아", ["indonesia", "jakarta", "rupiah", "bank indonesia", "인도네시아", "인니", "루피아"],
           [("MSCI Indonesia", "en"), ("Indonesia stocks", "en"), ("Bank Indonesia rate", "en"), ("인도네시아 증시", "ko")]),
    "VN": ("베트남", ["vietnam", "viet nam", "vn-index", "베트남"],
           [("FTSE Russell Vietnam upgrade", "en"), ("Vietnam stock market", "en"), ("베트남 증시", "ko")]),
    "JP": ("일본", ["japan", "boj", "bank of japan", "nikkei", "yen", "일본", "엔화", "日"],
           [("Bank of Japan rate", "en"), ("Japan stocks Nikkei", "en")]),
    "CN": ("중국·홍콩", ["china", "chinese", "pboc", "hong kong", "hang seng", "yuan", "중국", "홍콩", "위안", "中"],
           [("China economy stimulus", "en"), ("Hong Kong stocks", "en"), ("PBOC rate", "en")]),
    "SG": ("싱가포르", ["singapore", " mas ", "싱가포르"], [("Singapore economy MAS", "en"), ("Singapore stocks", "en")]),
    "IN": ("인도", ["india", "rbi", "sensex", "nifty", "rupee", "인도"], [("India RBI rate", "en"), ("India stocks Sensex", "en")]),
    "GL": ("글로벌", ["msci", "ftse russell", "emerging market", "신흥국", "신흥시장", "global", "글로벌", "world"],
           [("MSCI market classification", "en"), ("FTSE Russell country classification", "en"), ("emerging markets outflows", "en")]),
}
# 시장·거시 단어(이 중 하나는 제목에 있어야 한다)
MACRO = ["rate", "rates", "stocks", "stock market", "shares", "index", "inflation", "gdp", "currency", "yield", "bond", "tariff",
         "msci", "ftse", "downgrade", "upgrade", "reclassif", "frontier", "standalone", "emerging", "outflow", "inflow", "recession",
         "stimulus", "금리", "증시", "주가", "지수", "환율", "물가", "성장률", "관세", "국채", "외국인", "강등", "승격", "선진지수", "신흥"]
# 지수 분류·강등·승격처럼 구조적인 뉴스는 먼저 보여 준다
PRIORITY = ["msci", "ftse russell", "reclassif", "frontier", "standalone", "downgrade", "upgrade", "강등", "승격", "선진지수", "관찰대상"]
NOISE = ["추천주", "특징주", "목표가", "목표주가", "[마감시황]", "오늘의 운세", "live:", "live updates", "podcast", "quiz"]
TRUSTED = [s.lower() for s in SOURCES + EXTRA_SOURCES]


def trusted(src):
    s = (src or "").lower()
    return any(t in s for t in TRUSTED)


def relevant(title, names):
    t = f" {title.lower()} "
    if any(n in t for n in NOISE):
        return False
    return any(n in t for n in names) and any(k in t for k in MACRO)


def priority(title):
    t = title.lower()
    return any(k in t for k in PRIORITY)


def parse(xml_bytes, since):
    out = []
    for it in ET.fromstring(xml_bytes).iter("item"):
        title = (it.findtext("title") or "").strip()
        src = (it.findtext("source") or "").strip()
        for _ in range(2):
            if src and title.endswith(f" - {src}"):
                title = title[: -len(src) - 3].strip()
        try:
            when = parsedate_to_datetime(it.findtext("pubDate")).astimezone(KST)
        except Exception:
            continue
        if when < since or not trusted(src):
            continue
        out.append({"date": when.strftime("%Y-%m-%d"), "time": when.strftime("%H:%M"), "title": title, "src": src,
                    "url": (it.findtext("link") or "").strip()})
    return out


def pick(items, names, keep=PER_COUNTRY):
    seen, rows = set(), []
    good = [x for x in items if relevant(x["title"], names)]
    for x in sorted(good, key=lambda x: (priority(x["title"]), x["date"], x.get("time", "")), reverse=True):
        k = norm_title(x["title"])
        if k in seen:
            continue
        seen.add(k)
        rows.append({**x, "priority": priority(x["title"])})
        if len(rows) >= keep:
            break
    return rows


def main():
    now = datetime.now(KST)
    since = now - timedelta(days=KEEP_DAYS)
    prev = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"countries": {}}
    result, errors = {}, []
    for key, (label, names, qs) in COUNTRIES.items():
        found = []
        for q, lang in qs:
            try:
                found += parse(net.get(rss_url(q, lang, KEEP_DAYS), timeout=25), since)
            except Exception as e:
                errors.append(f"{key} {q}: {e}"[:160])
        # 이전 수집분도 기간 안이면 후보에 넣는다(검색 결과에서 밀려난 큰 뉴스 보존)
        found += [x for x in prev.get("countries", {}).get(key, {}).get("items", []) if x.get("date", "") >= since.strftime("%Y-%m-%d")]
        result[key] = {"label": label, "items": pick(found, names)}
    if not any(c["items"] for c in result.values()):
        print("수집된 기사 없음: 이전 파일 유지", errors[:3])
        return 0
    OUT.write_text(json.dumps({"updated_at": now.isoformat(timespec="minutes"), "source": "Google News RSS · 매체 화이트리스트",
                               "countries": result, "errors": errors[:10]}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved {OUT.name}: " + ", ".join(f"{k} {len(v['items'])}" for k, v in result.items()) + f" (오류 {len(errors)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
