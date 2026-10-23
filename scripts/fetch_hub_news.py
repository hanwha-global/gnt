"""해외 거점(증권사 × 진출 국가)별 최근 1년 뉴스: Google News RSS(키·LLM 불필요), fetch_news.py와 같은 매체 화이트리스트.

국내 탭 '해외법인 5개년 손익 추이' 표의 거점 뉴스 칸에 쓴다(엑셀 양식에서 손으로 찾아 적던 법인별 사업 전략 메모를 대신함).
- 거점: 사이트 법인 집계(consolidated.json의 금융업 영업법인·중간지주)와 관계사·지분투자 법인의 (증권사, 나라)
- 제목에 증권사(약칭·영문 포함)와 그 나라(도시·영문 포함)가 함께 있어야 한다. 국문 기사는 법인·진출 관련 단어도 있어야 한다
- 같은 그룹의 다른 회사(미래에셋자산운용, 한국투자신탁운용 등)와 시황·홍보성 기사는 뺀다

결과: site/data/domestic/hub_news.json. 매일 06:30 news.yml이 돌린다. 수집이 비면 이전 파일을 유지한다.
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
from fetch_news import ALIASES, ENGLISH, NOISE, norm_title, trusted  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "site" / "data" / "domestic"
OUT = DATA / "hub_news.json"
KST = timezone(timedelta(hours=9))
KEEP_DAYS = 365
PER_HUB = 5

# 나라 → 제목에서 알아볼 표기(국문·한자 약칭·도시·영문). 인도는 인도네시아와 겹치지 않게 정규식으로 본다
PLACES = {
    "미국": r"미국|美|뉴욕|월가|미주|\bU\.?S\.?A?\b|America|New York", "홍콩": r"홍콩|Hong ?Kong", "영국": r"영국|英|런던|London|\bU\.?K\.?\b",
    "베트남": r"베트남|호찌민|호치민|하노이|Vietnam", "인도네시아": r"인도네시아|인니|印尼|자카르타|Indonesia|Jakarta",
    "인도": r"인도(?!네시아)|印(?!尼)|뭄바이|India|Mumbai",
    # '선전'은 '해외법인 선전(善戰)'과 겹쳐 지명으로 쓰일 때만, '中'은 '中企' 같은 낱말은 빼고
    "중국": r"중국|中(?![企小東])|상하이|상해|베이징|북경|선전(?=시|\s?법인|\s?사무소|\()|심천|深圳|China|Shanghai|Beijing|Shenzhen",
    "싱가포르": r"싱가포르|싱가폴|Singapore", "일본": r"일본|日|도쿄|Japan|Tokyo", "브라질": r"브라질|상파울루|Brazil",
    "몽골": r"몽골|울란바토르|Mongolia", "그리스": r"그리스|Greece", "태국": r"태국|방콕|Thailand", "캄보디아": r"캄보디아|Cambodia",
    "아랍에미리트": r"아랍에미리트|UAE|두바이|아부다비|Dubai|Abu Dhabi", "사우디아라비아": r"사우디|Saudi",
}
EN_PLACE = {"미국": "US", "홍콩": "Hong Kong", "영국": "UK", "베트남": "Vietnam", "인도네시아": "Indonesia", "인도": "India",
            "중국": "China", "싱가포르": "Singapore", "일본": "Japan", "브라질": "Brazil", "몽골": "Mongolia"}
# 국문 약칭(fetch_news.ALIASES에 더해 '○○證' 표기)
KO_ALIASES = {"미래에셋증권": ["미래에셋證"], "KB증권": ["KB證"], "삼성증권": ["삼성證"], "하나증권": ["하나證"], "토스증권": ["토스證"],
              "키움증권": ["키움證"], "한국투자증권": ["한국투자證", "한투證"], "신한투자증권": ["신한증권"], "NH투자증권": ["NH증권"],
              "한화투자증권": ["한화증권"]}
# 기사에서 정식 이름보다 많이 쓰는 이름은 검색어로도 한 번 더 찾는다
KO_QUERY = {"신한투자증권": "신한증권"}
# 영문 제목에서 증권사를 알아보는 현지 법인 표기(fetch_news.ENGLISH에 더해)
EN_ALIASES = {"미래에셋증권": ["Mirae Asset Sekuritas", "Mirae Asset Securities"], "KB증권": ["KB Valbury", "KB Securities"],
              "NH투자증권": ["NH Korindo", "NH Securities"], "한국투자증권": ["KIS Vietnam", "KIS Indonesia"],
              "신한투자증권": ["Shinhan Sekuritas", "Shinhan Securities"], "한화투자증권": ["Pinetree", "Ciptadana"],
              "키움증권": ["Kiwoom Sekuritas", "Kiwoom"], "삼성증권": ["Samsung Securities"], "하나증권": ["Hana Securities"],
              "토스증권": ["Toss Securities"]}
# '미국·싱가포르 이어 일본 법인 설립'의 '미국·싱가포르 이어'(이미 진출한 나라 나열)는 그 나라 기사가 아니다
PRIOR = re.compile(r"(?:(?:" + "|".join(PLACES.values()) + r")\s?[·,]?\s?)+(?:에\s?)?이어")
# 국문 기사: 거점(법인) 이야기라는 표시
HUB_WORDS = re.compile(r"법인|현지|자회사|지점|사무소|진출|인수|설립|증자|출자|라이선스|인가|거점|지주|합작|매각|철수|지분")
# 약칭 바로 뒤에 붙으면 같은 그룹의 다른 회사(예: 미래에셋자산운용, 한국투자신탁운용)
AFFILIATE = re.compile(r"\s?(자산운용|운용|생명|캐피탈|은행|카드|벤처|파트너스|금융지주|금융그룹|손해|화재|리츠|신탁|저축|글로벌인디|컨설팅"
                       r"|공사|리얼에셋|밸류|AC|액셀러레이터|인베스트먼트|프라이빗|PE|히어로즈)")
# 나라 이름이 든 잡음 규칙은 거점 뉴스에서 뺀다. 키움 히어로즈(야구) 기사도 뺀다
HUB_NOISE = [n for n in NOISE if not re.search(r"베트남|中|중국", n)] + ["환전", "계좌 개설", "히어로즈", "KBO", "MLB", "야구"]


def hubs():
    """(증권사, 나라) 거점 목록: 종속회사 전수 목록이 있는 회사는 그 목록, 없으면 기준 데이터."""
    out = set()
    cons = DATA / "consolidated.json"
    firms = json.loads(cons.read_text(encoding="utf-8")).get("firms", {}) if cons.exists() else {}
    for firm, c in firms.items():
        out |= {(firm, x["country"]) for x in c.get("overseas", []) if x.get("class") in ("영업법인", "지주회사") and x.get("country")}
    seed = json.loads((DATA / "seed.json").read_text(encoding="utf-8"))
    for e in seed["entities"]:
        if e.get("name") and e["kind"] == "법인" and e["status"] == "운영" and e.get("country") and (
                e["relation"] in ("관계사", "지분투자") or e["firm"] not in firms):
            out.add((e["firm"], e["country"]))
    return sorted(out)


def firm_names(firm):
    return [firm, *ALIASES.get(firm, []), *KO_ALIASES.get(firm, [])], [*([ENGLISH[firm]] if firm in ENGLISH else []), *EN_ALIASES.get(firm, [])]


def queries(firm, country):
    qs = [(f"{n} {country}", "ko") for n in (firm, *([KO_QUERY[firm]] if firm in KO_QUERY else []))]
    if firm in ENGLISH and country in EN_PLACE:
        qs.append((f'"{ENGLISH[firm]}" {EN_PLACE[country]}', "en"))
    return qs


def rss_url(q, lang):
    hl, gl, ceid = ("ko", "KR", "KR:ko") if lang == "ko" else ("en-US", "US", "US:en")
    return "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": f"{q} when:{KEEP_DAYS}d", "hl": hl, "gl": gl, "ceid": ceid})


def names_firm(title, ko, en):
    """제목에 증권사가 나오는지: 국문 약칭은 같은 그룹 다른 회사(…자산운용 등)로 이어지거나 다른 낱말 속(신한투자의 '한투')이면 아니다."""
    for n in ko:
        for m in re.finditer(r"(?<![가-힣])" + re.escape(n), title):
            if n.endswith("증권") or not AFFILIATE.match(title[m.end():]):
                return True
    t = title.lower()
    return any(n.lower() in t for n in en)


def relevant(title, firm, country):
    ko, en = firm_names(firm)
    if any(n.lower() in title.lower() for n in HUB_NOISE) or not names_firm(title, ko, en):
        return False
    if not re.search(PLACES.get(country, re.escape(country)), PRIOR.sub(" ", title)):
        return False
    return bool(HUB_WORDS.search(title)) or not re.search(r"[가-힣]", title)


def parse(xml_bytes, firm, country, since):
    items = []
    for it in ET.fromstring(xml_bytes).iter("item"):
        title = (it.findtext("title") or "").strip()
        src = (it.findtext("source") or "").strip()
        for _ in range(2):
            if src and title.endswith(f" - {src}"):
                title = title[: -len(src) - 3].strip()
        if re.search(r"[가-힣]", src) and not re.search(r"[가-힣]", title):
            continue  # 국내 매체 영문판(같은 기사)
        try:
            when = parsedate_to_datetime(it.findtext("pubDate")).astimezone(KST)
        except Exception:
            continue
        if when < since or not trusted(src) or not relevant(title, firm, country):
            continue
        items.append({"date": when.strftime("%Y-%m-%d"), "title": title, "src": src, "url": (it.findtext("link") or "").strip()})
    return items


def distinct(found):
    """최신순, 같은 제목은 하나만. 같은 일을 여러 매체가 쓴 기사(하루 안팎)는 첫 기사만 둬서 칸에 서로 다른 소식이 오게 한다."""
    seen, items = set(), []
    for x in sorted(found, key=lambda x: x["date"], reverse=True):
        k, d = norm_title(x["title"]), datetime.strptime(x["date"], "%Y-%m-%d")
        if k in seen or any(abs((d - datetime.strptime(y["date"], "%Y-%m-%d")).days) <= 1 for y in items):
            continue
        seen.add(k)
        items.append(x)
    return items


def main():
    now = datetime.now(KST)
    since = now - timedelta(days=KEEP_DAYS)
    prev = json.loads(OUT.read_text(encoding="utf-8")).get("hubs", {}) if OUT.exists() else {}
    out, errors, total = {}, [], 0
    for firm, country in hubs():
        key = f"{firm}|{country}"
        found = []
        for q, lang in queries(firm, country):
            try:
                found += parse(net.get(rss_url(q, lang), timeout=25), firm, country, since)
            except Exception as e:
                errors.append(f"{q}: {e}")
        # 이전 수집분도 기간 안이면 같은 규칙으로 다시 걸러 이어 붙인다(검색 결과에서 밀려난 기사 보존)
        found += [x for x in prev.get(key, []) if x.get("date", "") >= since.strftime("%Y-%m-%d") and trusted(x.get("src"))
                  and relevant(x["title"], firm, country)]
        items = distinct(found)
        if items:
            out[key] = items[:PER_HUB]
            total += len(out[key])
    if not total:
        print("수집된 기사 없음: 이전 파일 유지", errors[:3])
        return 0
    OUT.write_text(json.dumps({"updated_at": now.isoformat(timespec="minutes"), "source": "Google News RSS · 매체 화이트리스트",
                               "keep_days": KEEP_DAYS, "hubs": out, "errors": errors[:10]}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved {OUT.name}: 거점 {len(out)}곳 · 기사 {total}건 (오류 {len(errors)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
