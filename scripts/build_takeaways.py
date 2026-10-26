"""진출국 전략 Takeaways: 당사 현지법인이 있는 나라마다 실행 방향 3~4줄을 규칙으로 만든다(LLM 미사용).

한눈에 보기 맨 위 박스가 읽는다. 사이트가 이미 매일·매주 모으는 공개 자료만 쓴다.
- 당사 해외자회사 손익·출자: hanwha/data/dart_subs.json (DART)
- 지수·환율·정책금리·결정 일정: hanwha/data/markets.json, macro.json, rate_calendar.json
- 나라별 구조 뉴스(MSCI·FTSE 등): site/data/global/macro_news.json
- 한국계 경쟁사 현지 뉴스: site/data/domestic/hub_news.json, news.json
- 현지 점유율·상장 증권사: site/data/global/markets.json, listed.json, (있으면) insight/data/landscape.json, idx_share.json

규칙마다 '언제 발동하는지'와 '근거 한 줄(숫자마다 기준 시점)'을 정해 두고, 나라마다 점수가 높은 순으로
카테고리가 겹치지 않게 3~4개를 고른다. 문구는 '…검토할 만합니다/점검합니다'로 끝나는 자동 의견이며
회사의 공식 입장이 아니다.

매일 아침(news.yml) 돈다. 그 나라에 큰 변화가 있을 때만 문구를 바꾸고, 없으면 이전 문구를 그대로 두고
확인 시각만 남긴다. 큰 변화: 새 DART 보고서, 고른 규칙·구간의 변화, 3일 안의 새 구조·경쟁사·당사 뉴스,
정책금리 변경, 지수·환율 급변, 마지막 갱신 후 14일 경과.

    python scripts/build_takeaways.py            # 갱신
    python scripts/build_takeaways.py --print    # 파일은 쓰지 않고 결과만 출력
"""
import hashlib
import json
import math
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
OUT_REL = "site/data/domestic/takeaways.json"
SPEC_VERSION = 1
KST = timezone(timedelta(hours=9))
MAX_STALE_DAYS = 14
NEWS_FRESH_DAYS = 3
HOME = "한화투자증권"

COUNTRIES = ["VN", "ID", "SG"]
KOR = {"VN": "베트남", "ID": "인도네시아", "SG": "싱가포르"}
KEYS = {"VN": ["VN"], "ID": ["CSA", "CAM"], "SG": ["SG"]}       # dart_subs·entities 키
BROKER = {"VN": "VN", "ID": "CSA", "SG": "SG"}                    # 나라별 당사 증권 법인
IX = {"VN": "VN-Index", "ID": "IDX(자카르타)", "SG": "STI(싱가포르)"}
IX_SHORT = {"VN": "VN-Index", "ID": "IDX", "SG": "STI"}
CCY = {"VN": "VND", "ID": "IDR", "SG": "SGD"}
CCY_NAME = {"VND": "동", "IDR": "루피아", "SGD": "싱가포르달러"}
LAND = {"VN": "vn", "ID": "id", "SG": "sg"}
EXCHANGE = {"VN": "HOSE·HNX", "ID": "IDX", "SG": "SGX"}

LEVERS = {"M&A·지분", "자본", "구조조정·비용", "마케팅·고객"}
RISK = "리스크·규제"

# 나라 귀속(제목 기준): 피드가 아니라 제목으로 정한다(인니 기사가 싱가포르 피드에 들어오는 일이 있음)
C_RE = {
    "VN": re.compile(r"vietnam|viet nam|베트남|vn-?index|\bhose\b", re.I),
    "ID": re.compile(r"indonesia|인도네시아|인니|\bidx\b|\bjci\b|jakarta", re.I),
    "SG": re.compile(r"singapore|싱가포르|\bsti\b|\bsgx\b", re.I),
}
MAS_RE = re.compile(r"\bMAS\b")
OFF_WATCH = re.compile(r"off (the )?watch ?list|keeps .{0,30} off", re.I)
NEUTRAL = re.compile(r"\brebut|\bdefends?\b|\bdenies\b|반박", re.I)
NEG_RE = re.compile(r"downgrad|standalone|\brout\b|manipulat|outflow|sell-?off|plunge|angst|turmoil|강등|급락|이탈|폭락|sanction|delist", re.I)
POS_RE = re.compile(r"upgrad|inclusion|편입|승격|상향|reclassif|index options?|derivativ|옵션|파생", re.I)
DERIV_RE = re.compile(r"option|derivativ|옵션|파생", re.I)
CAPITAL_RE = re.compile(r"증자|자본금|자본 ?확충|곳간|인수|지분|합병|M&A|점유율 ?전쟁|stake|acquir", re.I)
CAPITAL_HEAD_RE = re.compile(r"자본금|증자|자본 ?확충")
REG_RE = re.compile(r"manipulat|sanction|\bfine[ds]?\b|penalt|fraud|scam|과징금|과태료|제재|경영유의|적발|위반|사기|보안", re.I)
RWA_RE = re.compile(r"RWA|토큰|STO|디지털자산|가상자산|tokeni", re.I)
BANK_RE = re.compile(r"BIDV|VietinBank|Vietcombank|Agribank|Mandiri|\bBRI\b|\bBNI\b|\bBCA\b|Danareksa", re.I)
BROKER_NAME_RE = re.compile(r"securities|sekuritas|증권", re.I)
NOT_BROKER_RE = re.compile(r"\(주1\)|asset management|investment management|fund|reksa|realty|ETF|capbridge", re.I)
# 영문 구조 뉴스 제목 → 짧은 한글 라벨(없으면 '{매체} 보도')
LABELS = [
    (re.compile(r"index options?", re.I), "지수옵션 도입 계획"),
    (re.compile(r"(R&I|rating).*upgrad|upgrad.*(R&I|BBB)", re.I), "신용등급 상향"),
    (re.compile(r"market upgrade", re.I), "시장 승격 이후 과제"),
    (re.compile(r"MSCI.*downgrad|downgrad.*MSCI", re.I), "MSCI 강등 검토"),
    (re.compile(r"manipulat", re.I), "시세조종 대책 강화"),
    (re.compile(r"bond premia", re.I), "회사채 가산금리 6년 최고"),
    (re.compile(r"off (the )?watch ?list", re.I), "FTSE 관찰대상 제외 유지"),
    (re.compile(r"FTSE.*(upgrad|inclusion)|(upgrad|inclusion).*FTSE", re.I), "FTSE 승격"),
]


# ---------- 작은 도구 ----------
def load(root, rel):
    p = root / rel
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return None


def d(s):
    """'2026-10-26' · '20261026' · '2026.10.26' → date."""
    m = re.search(r"(\d{4})[-.]?(\d{2})[-.]?(\d{2})", str(s or ""))
    return date(*map(int, m.groups())) if m else None


def md(x):
    x = d(x) if not isinstance(x, date) else x
    return f"{x.month}/{x.day}" if x else ""


def eok(v):
    """백만원 → '12.3억원'."""
    return f"{v / 100:,.1f}억원"


def sgn(v, digits=1):
    return f"{v:+.{digits}f}%"


def month_end(ym):
    y, m = map(int, ym.split("-")[:2])
    return date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)


def rep_name(period):
    name = ((period or {}).get("report") or {}).get("name", "")
    m = re.match(r"(?:\[\w+\])?(.+?)\s*\((\d{4}\.\d{2})\)", name)
    return f"{m.group(2)} {m.group(1)}" if m else name


def news_label(title, src):
    for rx, label in LABELS:
        if rx.search(title):
            return label
    if re.search(r"[가-힣]", title):
        q = re.search(r"[‘'\"“]([^’'\"”]{4,30})[’'\"”]", title)
        return q.group(1) if q else (title[:22] + "…" if len(title) > 22 else title)
    return f"{src} 보도"


def polarity(title):
    if OFF_WATCH.search(title):
        return 1
    if NEUTRAL.search(title):
        return 0
    if NEG_RE.search(title):
        return -1
    if POS_RE.search(title):
        return 1
    return 0


def countries_of(title):
    cs = [c for c in ("VN", "ID") if C_RE[c].search(title)]
    if not cs and (C_RE["SG"].search(title) or MAS_RE.search(title)):
        cs.append("SG")
    return cs


class Data:
    """규칙이 읽는 입력. 없는 파일은 None(규칙이 알아서 건너뜀)."""

    def __init__(self, root, today, prev_state=None):
        self.root, self.today = root, today
        self.mk = load(root, "hanwha/data/markets.json") or {}
        self.macro = load(root, "hanwha/data/macro.json") or {}
        self.subs = load(root, "hanwha/data/dart_subs.json") or {}
        ents = load(root, "hanwha/data/entities.json") or {}
        self.ents = {e["key"]: e for e in ents.get("entities", [])}
        self.cal = load(root, "hanwha/data/rate_calendar.json") or {}
        self.reg = load(root, "hanwha/data/regulatory.json") or {}
        self.mnews = load(root, "site/data/global/macro_news.json") or {}
        self.hub = (load(root, "site/data/domestic/hub_news.json") or {}).get("hubs", {})
        self.news = (load(root, "site/data/domestic/news.json") or {}).get("items", [])
        self.gmk = {m["id"]: m for m in (load(root, "site/data/global/markets.json") or {}).get("markets", [])}
        self.listed = (load(root, "site/data/global/listed.json") or {}).get("markets", {})
        self.dl = load(root, "site/data/domestic/dart_latest.json") or {}
        self.subfin = (load(root, "site/data/domestic/sub_fin.json") or {}).get("firms", {})
        self.land = (load(root, "insight/data/landscape.json") or {}).get("markets")
        self.idx = load(root, "insight/data/idx_share.json")
        self.digi = load(root, "digital/data/regulation.json")
        periods = self.subs.get("periods") or []
        self.L = periods[-1] if periods else None
        fy = [p for p in periods if p.get("period") == "FY"]
        self.B = fy[-1] if fy else None
        self.state = prev_state or {}
        # 뉴스 보관함: 피드는 나라당 몇 건만 남기므로, 본 기사를 state.seen 에 모아 국면을 이어 간다
        self.archive = dict(self.state.get("seen", {}))

    # 당사 법인
    def label(self, key):
        return self.ents.get(key, {}).get("label") or key

    def labels(self, keys):
        return "·".join(self.label(k) for k in keys)

    def sub(self, period, key):
        return ((period or {}).get("subs") or {}).get(key) or {}

    def ix(self, c):
        return next((i for i in self.mk.get("indices", []) if i.get("name") == IX[c]), None)

    def policy(self, c):
        return next((t for t in (self.mk.get("policy") or {}).get("table", []) if t.get("key") == c), None)

    def age(self, s):
        x = d(s)
        return (self.today - x).days if x else 10 ** 6

    # 뉴스 풀: 현재 피드 + 보관함
    def macro_items(self):
        pool = {}
        for v in (self.mnews.get("countries") or {}).values():
            for it in v.get("items", []):
                pool.setdefault(it["url"], {**it, "kind": "macro"})
        for url, it in self.archive.items():
            if it.get("kind") == "macro":
                pool.setdefault(url, it)
        return list(pool.values())

    def news_items(self):
        pool = {it["url"]: {**it, "kind": "news"} for it in self.news if it.get("url")}
        for url, it in self.archive.items():
            if it.get("kind") == "news":
                pool.setdefault(url, it)
        return list(pool.values())

    def hub_items(self, c, home=None):
        out = []
        for k, items in self.hub.items():
            firm, _, country = k.partition("|")
            if country != KOR[c] or (home is True and firm != HOME) or (home is False and firm == HOME):
                continue
            out += [{**it, "firm": firm, "kind": "hub"} for it in items]
        return out


def cand(rule, category, weight, text, evidence, keys, variant="", bucket=(), driver=None, links=(), **extra):
    return {"rule": rule, "variant": variant, "category": category, "weight": weight, "text": text,
            "evidence": [e for e in evidence if e], "keys": list(keys), "bucket": list(bucket),
            "driver": driver.isoformat() if isinstance(driver, date) else driver,
            "links": [l for l in links if l and l.get("url")], **extra}


def link(it, label=None):
    return {"label": label or news_label(it["title"], it.get("src", "")), "url": it["url"], "title": it["title"]}


# ---------- 규칙 ----------
def struct(D, c):
    """구조 뉴스 국면: POS(시장 지위 상향) · NEG(강등·급락) · None."""
    items = [it for it in D.macro_items() if it.get("priority") and D.age(it.get("date")) <= 30 and c in countries_of(it["title"])]
    for it in items:
        it["pol"] = polarity(it["title"])
    pos = sorted([i for i in items if i["pol"] > 0], key=lambda i: i["date"], reverse=True)
    neg = sorted([i for i in items if i["pol"] < 0], key=lambda i: i["date"], reverse=True)
    ix = D.ix(c)
    m1 = (ix or {}).get("chg", {}).get("1M")
    dd = drawdown(ix, 13)
    if neg and (len(pos) - len(neg) <= -2 or (m1 is not None and m1 <= -10) or (dd is not None and dd <= -0.20)):
        return "NEG", pos, neg
    if len(pos) >= 2 and not neg and (m1 is None or m1 > -10):
        return "POS", pos, neg
    return None, pos, neg


def drawdown(ix, months):
    if not ix or not ix.get("monthly"):
        return None
    peak = max(v for _, v in ix["monthly"][-months:])
    return ix["close"] / peak - 1 if peak else None


def peak_month(ix, months):
    return max(ix["monthly"][-months:], key=lambda kv: kv[1])[0]


def own_and_peers(D, c):
    """(당사 행, 한국계 동종 행들, 현지 상장사 ROE 목록, 출처 라벨). 현지통화 자본, FY 기준."""
    key = BROKER[c]
    if D.land and LAND[c] in D.land:
        rows = D.land[LAND[c]]["rows"]
        own = next((r for r in rows if r.get("kind") == "korean" and r.get("firm") == HOME and r.get("broker")), None)
        peers = [r for r in rows if r.get("kind") == "korean" and r.get("broker") and r.get("firm") != HOME and r.get("equity")]
        if peers:
            top = max(r["equity"] for r in peers)
            peers = [r for r in peers if r["equity"] >= 0.01 * top]
        loc = [r["roe"] for r in rows if r.get("kind") == "local" and r.get("roe") is not None and not r.get("stale")]
        if own:
            return {"equity": own["equity"], "equity_krw": own.get("equity_krw"), "roe": own.get("roe"), "asof": own.get("asof")}, \
                [{"equity": r["equity"], "equity_krw": r.get("equity_krw"), "firm": r["firm"]} for r in peers], loc, "land"
    # 대체: 종속기업 요약재무(DART FY2025, 백만원)와 현지 상장사(listed.json)
    sB = D.sub(D.B, key)
    if not sB.get("assets"):
        return None, [], [], ""
    eq = sB["assets"] - sB["liab"]
    own = {"equity": eq, "equity_krw": eq / 100, "roe": sB["ni"] / eq * 100 if sB.get("ni") is not None and eq else None, "asof": f"{D.B['year']}-12-31"}
    peers = []
    for firm, f in D.subfin.items():
        if firm == HOME:
            continue
        for name, s in (f.get("subs") or {}).items():
            if s.get("country") != KOR[c] or not BROKER_NAME_RE.search(name) or NOT_BROKER_RE.search(name) or not s.get("equity") or not s.get("rev"):
                continue
            peers.append({"equity": s["equity"], "equity_krw": s["equity"] / 100, "firm": firm})
    loc = [r["ni"] / r["equity"] * 100 for r in (D.listed.get(LAND[c]) or {}).get("rows", [])
           if r.get("equity") and r.get("ni") is not None and not r.get("stale")]
    return own, peers, loc, "subfin"


def injection(D, key):
    """최근 출자(DART 타법인출자현황 기중 취득). 이후 보고서가 비워도 365일 기억한다."""
    inv = D.subs.get("invest") or {}
    row = (inv.get("rows") or {}).get(key) or {}
    rep = inv.get("report") or {}
    if (row.get("chg_amount") or 0) > 0:
        return {"amount": row["chg_amount"], "rcept_no": rep.get("rcept_no"), "rcept_dt": rep.get("rcept_dt"),
                "report": rep_name({"report": rep}), "period": (D.L or {}).get("label")}
    old = (D.state.get("injection") or {}).get(key)
    if old and D.age(old.get("rcept_dt")) <= 365:
        return old
    return None


def loss(D, key):
    s = D.sub(D.L, key)
    return s.get("ni") is not None and s["ni"] < 0


def flows(D, key):
    """(rev_g, cost_g, cir): 최신 기간과 FY의 반기·연 환산 비교."""
    L, B = D.sub(D.L, key), D.sub(D.B, key)
    if None in (L.get("rev"), L.get("ni"), B.get("rev"), B.get("ni")) or not L.get("rev") or not B.get("rev"):
        return None
    f = D.L["months"] / 12
    rev_g = L["rev"] / (B["rev"] * f) - 1
    cost_B = B["rev"] - B["ni"]
    cost_g = (L["rev"] - L["ni"]) / (cost_B * f) - 1 if cost_B > 0 else None
    cir = (L["rev"] - L["ni"]) / L["rev"]
    return rev_g, cost_g, cir


def r01_scale(D, c, ctx):
    key = BROKER[c]
    if injection(D, key) or loss(D, key):
        return None
    own, peers, loc, src = own_and_peers(D, c)
    if not own or len(peers) < 3:
        return None
    med = median(p["equity"] for p in peers)
    ratio = own["equity"] / med
    published = ctx["published"].get("R01")
    if ratio >= (0.55 if published else 0.50):
        return None
    allr = sorted([own["equity"]] + [p["equity"] for p in peers], reverse=True)
    rank, n_all = allr.index(own["equity"]) + 1, len(allr)
    lroe = median(loc) if len(loc) >= 4 else None
    thr = 0.75 if (published or {}).get("variant") == "acquire" else 0.7
    acquire = lroe is not None and own.get("roe") is not None and own["roe"] < thr * lroe
    lab = D.label(key)
    med_krw = median(p["equity_krw"] for p in peers if p.get("equity_krw") is not None)
    ev = [f"FY{own['asof'][:4]} 자기자본 {own['equity_krw']:,.0f}억원, 한국계 {n_all}사 중 {rank}위(당사 제외 중간값 {med_krw:,.0f}억원, DART)"]
    if acquire:
        ev.append(f"ROE {own['roe']:.1f}% vs 현지 상장사 {len(loc)}곳 중간값 {lroe:.1f}%")
        text = f"{lab}은 증자만으로는 격차가 커, 현지 증권사 지분 인수로 규모·수익을 함께 키우는 방안을 검토할 만합니다."
        return cand("R01", "M&A·지분", 9, text, ev, [key], "acquire", ("acquire", rank, n_all), ratio=ratio)
    text = f"{lab} 자기자본이 한국계 {n_all}사 중 {rank}위라, 증자 규모와 시점을 검토할 만합니다."
    return cand("R01", "자본", 8, text, ev, [key], "inject", ("inject", rank, n_all), ratio=ratio)


def r02_peer_capital(D, c):
    pool = {}
    for it in D.news_items():
        if KOR[c] in it.get("title", "") or (c == "ID" and "인니" in it.get("title", "")):
            if HOME not in (it.get("firms") or []):
                pool[it["url"]] = it
    for it in D.hub_items(c, home=False):
        pool.setdefault(it["url"], it)
    hits, titles = [], set()
    for it in sorted(pool.values(), key=lambda i: i.get("date", ""), reverse=True):
        if D.age(it.get("date")) > 45 or not CAPITAL_RE.search(it.get("title", "")) or HOME in it.get("title", ""):
            continue
        t = re.sub(r"\W", "", it["title"])[:30]
        if t in titles:
            continue
        titles.add(t)
        hits.append(it)
    if not hits:
        return None
    head = next((i for i in hits if CAPITAL_HEAD_RE.search(i["title"])), hits[0])
    dates = sorted(i["date"] for i in hits)
    span = f"{md(dates[0])}~{md(dates[-1])}" if dates[0] != dates[-1] else md(dates[0])
    ev = f"국내 보도 '{news_label(head['title'], head.get('src', ''))}' 등 {len(hits)}건({span}, 최근 45일)"
    key = BROKER[c]
    text = f"한국계 경쟁사의 {KOR[c]} 자본 확충·점유율 경쟁에 맞서 {D.label(key)} 증자 규모와 시점을 검토할 만합니다."
    return cand("R02", "자본", 6, text, [ev], [key], driver=d(dates[-1]), links=[link(head)], urls=[i["url"] for i in hits], hits=hits)


def r03_partner(D, c, fired):
    if not D.land or LAND[c] not in D.land or (fired.get("R01") or {}).get("variant") == "acquire":
        return None
    nb = [r for r in D.land[LAND[c]]["rows"] if r.get("kind") == "local" and r.get("mcap_krw") and r.get("val_stale") is not True
          and not BANK_RE.search(r.get("name", ""))]
    fin = (D.dl.get("firms") or {}).get(HOME, {})
    hw = (fin.get("financials") or {}).get("equity")
    if not nb or not hw:
        return None
    hw_eok = hw / 100
    lo, hi = min(r["mcap_krw"] for r in nb), max(r["mcap_krw"] for r in nb)
    if lo <= 0.5 * hw_eok:
        return None
    pdate = max((r.get("price_date") or "") for r in nb)
    hw_label = (fin.get("financials_report") or {}).get("label", "")
    span = f"{lo / 1e4:.1f}~{hi / 1e4:.1f}조원" if len(nb) > 1 else f"{lo / 1e4:.1f}조원"
    ev = f"{EXCHANGE[c]} 상장 증권사 {len(nb)}곳 시가총액 {span}({md(pdate)} 주가) vs 당사 자기자본 {hw_eok / 1e4:.2f}조원({hw_label} 연결, DART)"
    key = BROKER[c]
    text = f"{D.label(key)}은 현지 상장사 인수 부담이 커, 지분 인수보다 제휴·JV형 확장을 우선 검토할 만합니다."
    return cand("R03", "M&A·지분", 7, text, [ev], [key], bucket=(len(nb),))


def r04_entry(D, c):
    ix = D.ix(c)
    fx = (D.macro.get("fx") or {}).get(CCY[c]) or {}
    dd = drawdown(ix, 13)
    if dd is None or fx.get("ytd_pct") is None or ix["chg"].get("YTD") is None:
        return None
    krw = (1 + ix["chg"]["YTD"] / 100) * (1 + fx["ytd_pct"] / 100) - 1
    if not (dd <= -0.20 and krw <= -0.25):
        return None
    ev = (f"{IX_SHORT[c]} {ix['close']:,.0f}({md(ix['date'])}), 최근 1년 고점({peak_month(ix, 13)} 월말) 대비 {sgn(dd * 100)} · "
          f"{CCY_NAME[CCY[c]]} 원화 대비 연초 이후 {sgn(fx['ytd_pct'])}(ECOS {md(fx['last'][0])}) · 원화 환산 지수 연초 대비 {sgn(krw * 100)}")
    text = f"{KOR[c]} 원화 기준 인수 비용이 크게 낮아진 구간으로, 현지 증권사 인수 후보 실사와 가격 협상 준비를 검토할 만합니다."
    return cand("R04", "M&A·지분", 8, text, [ev], KEYS[c], "open", (math.floor(dd * 10), math.floor(krw * 10)), dd=dd, krw=krw)


def r05_post_injection(D, c):
    out = []
    for key in KEYS[c]:
        inj = injection(D, key)
        L, B = D.sub(D.L, key), D.sub(D.B, key)
        if not inj or not loss(D, key) or not B.get("rev") or not L.get("rev"):
            continue
        eq_L, eq_B = L["assets"] - L["liab"], B["assets"] - B["liab"]
        ry_L = L["rev"] * (12 / D.L["months"]) / eq_L
        ry_B = B["rev"] / eq_B
        if ry_L >= 0.5 * ry_B:
            continue
        ev = (f"{inj.get('period') or D.L['label']} 중 출자 {eok(inj['amount'])}(DART {inj.get('report') or rep_name(D.L)} 타법인출자현황) 후 "
              f"자본 대비 매출 {ry_L * 100:.1f}%({D.L['label']} 연환산) vs FY{D.B['year']} {ry_B * 100:.1f}%")
        text = f"{D.label(key)} 증자 자금은 매출 목표 달성에 맞춰 단계적으로 집행하고 분기마다 성과를 점검합니다."
        out.append(cand("R05", "자본", 7, text, [ev], [key], bucket=(inj["amount"],), driver=d(inj["rcept_dt"]), injection=inj))
    return out


def r06_cross_sell(D, c):
    if c != "ID" or "CAM" not in D.ents:
        return None
    first = d(((D.subs.get("invest") or {}).get("rows") or {}).get("CAM", {}).get("first_date"))
    if not first or (D.today - first).days > 730:
        return None
    pol = D.policy("ID")
    rate_up = bool(pol and (pol.get("d1y_bp") or 0) >= 50 and (pol.get("now") or 0) >= 5.0)
    L = D.sub(D.L, "CAM")
    if not (rate_up or (L.get("ni") is not None and L["ni"] < 0)):
        return None
    nxt = next((e for e in sorted(D.cal.get("events", []), key=lambda e: e["date"]) if e.get("bank") == "ID" and d(e["date"]) >= D.today), None)
    ev = []
    if pol:
        nxt_txt = f", 다음 결정 {md(nxt['date'])}" if nxt else ""
        ev.append(f"BI 기준금리 {pol['now']:.2f}%({pol['month']} 말, 1년 {pol['d1y_bp']:+d}bp{nxt_txt})")
    if L.get("rev") is not None and L.get("ni") is not None:
        ev.append(f"{D.label('CAM')} {D.L['label']} 매출 {eok(L['rev'])}·순{'손실' if L['ni'] < 0 else '이익'} {eok(abs(L['ni']))}(DART)")
    a, b = D.label("CAM"), D.label("CSA")
    if rate_up:
        text = f"BI 고금리 국면에 맞춰 {a} 채권형·MMF를 {b} 고객에게 교차판매하는 방안을 검토할 만합니다."
    else:
        text = f"{a} 펀드를 {b} 고객에게 교차판매하는 목표 설정을 검토할 만합니다."
    return cand("R06", "상품·제휴", 7, text, ev, ["CAM", "CSA"], "rate-up" if rate_up else "base", (pol and pol.get("now"),))


def r07_r08_struct(D, c):
    regime, pos, neg = struct(D, c)
    if not regime:
        return None
    ix = D.ix(c)
    key = BROKER[c]
    if regime == "POS":
        deriv = any(DERIV_RE.search(i["title"]) for i in pos)
        note = next((n[1] for n in D.ents.get(key, {}).get("notes", []) if re.search(r"FTSE|MSCI", n[1])), "")
        nd = re.search(r"\d{4}-\d{2}-\d{2}", note)
        note_short = f"FTSE 신흥시장 편입 {nd.group(0)} 발효" if nd and "FTSE" in note else ""
        head = pos[0]
        ev = [note_short, f"{head.get('src', '')} {md(head['date'])} '{news_label(head['title'], head.get('src', ''))}' 등 구조 뉴스 {len(pos)}건(최근 30일)"]
        if deriv:
            text = f"FTSE 편입에 맞춰 {D.label(key)}의 외국인 기관 영업과 지수옵션 등 파생상품 준비를 검토할 만합니다."
        else:
            text = f"{KOR[c]} 시장 지위 상향에 맞춰 {D.label(key)}의 외국인 기관 영업·영문 리서치 강화를 검토할 만합니다."
        return cand("R07", "상품·제휴", 8, text, ev, [key], "deriv" if deriv else "base", ("POS",), driver=d(head["date"]),
                    links=[link(i) for i in pos[:2]], urls=[i["url"] for i in pos])
    head = neg[0]
    titles = " ".join(i["title"] for i in neg)
    event = "MSCI 결정" if "MSCI" in titles else "FTSE 재분류" if "FTSE" in titles else "시장 불안 진정"
    credit = [k for k in KEYS[c] if "신용공여" in D.ents.get(k, {}).get("focus", "")]
    tail = f" {D.labels(credit)} 신용공여 한도를 점검합니다." if credit else " 리스크 한도를 점검합니다."
    text = f"{event} 전까지 {KOR[c]} 신규 출자·인수 속도를 조절하고{tail}"
    ev = [f"{head.get('src', '')} {md(head['date'])} '{news_label(head['title'], head.get('src', ''))}' 등 부정 구조 뉴스 {len(neg)}건(최근 30일)"]
    if ix:
        ev.append(f"{IX_SHORT[c]} 1개월 {sgn(ix['chg']['1M'])}, 연초 대비 {sgn(ix['chg']['YTD'])}({md(ix['date'])})")
    return cand("R08", RISK, 9, text, ev, KEYS[c], "NEG", ("NEG", event), driver=d(head["date"]),
                links=[link(i) for i in neg[:2]], urls=[i["url"] for i in neg], event=event)


def fx_pair(D, c):
    fx = (D.macro.get("fx") or {})
    y, yu = (fx.get(CCY[c]) or {}).get("ytd_pct"), (fx.get("USD") or {}).get("ytd_pct")
    rows = {r["ccy"]: r for r in (D.mk.get("fx") or {}).get("rows", [])}
    w, wu = (rows.get(CCY[c]) or {}).get("chg_1w"), (rows.get("USD") or {}).get("chg_1w")
    vs_usd = ((1 + y / 100) / (1 + yu / 100) - 1) * 100 if None not in (y, yu) else None
    w_usd = ((1 + w / 100) / (1 + wu / 100) - 1) * 100 if None not in (w, wu) else None
    return y, vs_usd, w_usd


def r09_fx(D, c, ctx):
    y, vs_usd, w_usd = fx_pair(D, c)
    if y is None or vs_usd is None:
        return None
    exit_ok = ctx["published"].get("R09") and vs_usd <= -3
    if not ((y <= -10 and vs_usd <= -5) or (w_usd is not None and w_usd <= -1.5) or exit_ok):
        return None
    fx = D.macro["fx"][CCY[c]]
    unit = re.search(r"\((\d+)\D*\)", fx.get("name", ""))
    ev = f"원/{CCY_NAME[CCY[c]]} {fx['last'][1]:,}원({unit.group(1) + CCY_NAME[CCY[c]] + ' 기준, ' if unit else ''}ECOS {md(fx['last'][0])}), 연초 대비 {sgn(y)}·달러 대비 {sgn(vs_usd)}"
    text = f"{CCY_NAME[CCY[c]]} 약세에 대비해 {D.labels(KEYS[c])} 원화 환산 손익 관리와 환헤지 방안을 점검합니다."
    return cand("R09", RISK, 6, text, [ev], KEYS[c], bucket=(math.floor(y / 5), vs_usd <= -5))


def r10_reg(D, c, struct_urls):
    pool = []
    for it in D.macro_items():
        if c in countries_of(it["title"]) and D.age(it.get("date")) <= 60 and REG_RE.search(it["title"]):
            pool.append(it)
    for it in D.hub_items(c, home=False):
        if D.age(it.get("date")) <= 180 and REG_RE.search(it["title"]):
            pool.append(it)
    for it in D.news_items():
        if KOR[c] in it.get("title", "") and D.age(it.get("date")) <= 60 and REG_RE.search(it["title"]) and HOME not in it["title"]:
            pool.append(it)
    if not pool:
        return None
    pool.sort(key=lambda i: i.get("date", ""), reverse=True)
    if D.age(pool[0]["date"]) > 30:
        return None
    head = next((i for i in pool if i["url"] not in struct_urls), pool[0])
    t = head["title"]
    variant = "시세조종 단속 강화" if re.search(r"manipulat|시세조종", t, re.I) else \
        "고객 대상 사기 증가" if re.search(r"fraud|scam|사기|보안", t, re.I) else "감독당국 제재 사례"
    who = f"{head['firm']} {KOR[c]} 법인 " if head.get("firm") else ""
    ev = f"{who}{head.get('src', '')} {md(head['date'])} '{news_label(t, head.get('src', ''))}' 등 {len(pool)}건"
    text = f"{variant}에 맞춰 {D.labels([k for k in KEYS[c] if 'IB' in D.ents.get(k, {}).get('focus', '') or k == BROKER[c]])} 이상거래 모니터링과 고객 사기 방지 체계를 점검합니다."
    return cand("R10", RISK, 6, text, [ev], [BROKER[c]], variant, (variant,), driver=d(head["date"]), links=[link(head)], urls=[i["url"] for i in pool])


def r11_loss(D, c):
    out = []
    ix = D.ix(c)
    for key in KEYS[c]:
        L, B = D.sub(D.L, key), D.sub(D.B, key)
        if not loss(D, key) or B.get("ni") is None:
            continue
        fl = flows(D, key)
        cir = fl[2] if fl else None
        widen = B["ni"] < 0 and (L["ni"] * 12 / D.L["months"] < B["ni"] or (cir is not None and cir >= 3.0))
        flip = B["ni"] > 0
        if not (flip or widen):
            continue
        lab = D.label(key)
        b_txt = f"순이익 {eok(B['ni'])}" if B["ni"] >= 0 else f"순손실 {eok(-B['ni'])}"
        ev = [f"{D.L['label']} 순손실 {eok(-L['ni'])}(FY{D.B['year']} {b_txt}), 매출 {eok(L['rev'])}(DART {rep_name(D.L)})"]
        if fl and ix and ix["chg"].get("YTD", 0) >= 5 and ix["chg"].get("6M", 0) >= 0 and fl[0] <= -0.10:
            ev.append(f"{IX_SHORT[c]} 연초 대비 {sgn(ix['chg']['YTD'])}({md(ix['date'])})에도 매출은 FY{D.B['year']} 반기 환산 대비 {sgn(fl[0] * 100)}")
        if flip:
            text = f"{lab} 적자 전환에 따라 고정비 중심의 인력·조직 효율화를 검토할 만합니다."
            out.append(cand("R11", "구조조정·비용", 9, text, ev, [key], "flip", ("flip",), driver=d(D.L["report"].get("rcept_dt")), cir=cir, rev_g=fl and fl[0]))
        else:
            focus = D.ents.get(key, {}).get("focus", "").split(",")[0].strip() or "핵심"
            mult = f"비용이 매출의 {cir:.1f}배라" if cir is not None and cir >= 3 else "적자 폭이 커져"
            text = f"{lab}은 {mult}, 성과가 나는 {focus} 중심으로 조직 축소·재편을 검토할 만합니다."
            out.append(cand("R11", "구조조정·비용", 9, text, ev, [key], "widen", ("widen",), driver=d(D.L["report"].get("rcept_dt")), cir=cir, rev_g=fl and fl[0]))
    return out


def peer_margin(D, c):
    ms = []
    for firm, f in D.subfin.items():
        if firm == HOME:
            continue
        for name, s in (f.get("subs") or {}).items():
            if s.get("country") == KOR[c] and BROKER_NAME_RE.search(name) and not NOT_BROKER_RE.search(name) and (s.get("rev") or 0) > 0 and (s.get("ni") or 0) > 0:
                ms.append(s["ni"] / s["rev"])
    return (median(ms), len(ms)) if len(ms) >= 3 else (None, len(ms))


def r12_jaws(D, c, ctx):
    out = []
    for key in KEYS[c]:
        L = D.sub(D.L, key)
        fl = flows(D, key)
        if not fl or L.get("ni") is None or L["ni"] <= 0 or fl[1] is None:
            continue
        rev_g, cost_g, _ = fl
        jaws = (rev_g - cost_g) * 100
        published = (ctx["published"].get("R12") or {})
        if not ((jaws <= -5 and cost_g > 0) or (published and jaws <= -2)):
            continue
        ev = [f"{D.L['label']} 비용 {sgn(cost_g * 100)} vs 매출 {sgn(rev_g * 100)}(FY{D.B['year']} 반기 환산 대비, DART)"]
        m_p, n = peer_margin(D, c)
        if m_p is not None:
            ev.append(f"순이익률 {L['ni'] / L['rev'] * 100:.1f}% vs 한국계 흑자 {n}사 중간값 {m_p * 100:.1f}%(FY{D.B['year']})")
        text = f"{D.label(key)} 비용 증가율을 매출 증가율 이하로 묶는 비용 상한 관리를 검토할 만합니다."
        out.append(cand("R12", "구조조정·비용", 8, text, ev, [key], bucket=(math.floor(jaws / 5),), driver=d(D.L["report"].get("rcept_dt")), jaws=jaws))
    return out


def r13_shared(D, c):
    keys = [k for k in KEYS[c] if loss(D, k)]
    if len(keys) < 2:
        return None
    Ls = [D.sub(D.L, k) for k in keys]
    sum_ni = sum(s["ni"] for s in Ls)
    sum_rev = sum(s["rev"] or 0 for s in Ls)
    sum_cost = sum((s["rev"] or 0) - s["ni"] for s in Ls)
    ev = [f"{D.L['label']} 두 법인 순손실 {eok(-sum_ni)}, 비용 {eok(sum_cost)} vs 매출 {eok(sum_rev)}(DART {rep_name(D.L)})"]
    for k in keys:
        B = D.sub(D.B, k)
        if B.get("ni") is not None and B["ni"] > 0:
            ev.append(f"{D.label(k)} FY{D.B['year']} 순이익 {eok(B['ni'])}에서 적자 전환")
    text = f"{D.labels(keys)} 백오피스·IT·준법 통합으로 중복 고정비 축소를 검토할 만합니다."
    return cand("R13", "구조조정·비용", 9, text, ev, keys, bucket=(len(keys), round(sum_ni / 500)), driver=d(D.L["report"].get("rcept_dt")))


def r14_volume(D, c):
    if c != "ID":
        return None
    ix = D.ix(c)
    fl = flows(D, BROKER[c])
    adtv = None
    if D.idx and D.idx.get("month") and D.idx.get("ytd"):
        mo, yt = D.idx["month"], D.idx["ytd"]
        if mo.get("days") and yt.get("days"):
            adtv = (mo["total"] / mo["days"]) / (yt["total"] / yt["days"]) - 1
    ytd = (ix or {}).get("chg", {}).get("YTD")
    if not ((adtv is not None and adtv <= -0.15) or (ytd is not None and ytd <= -20)) or not fl or fl[0] >= 0:
        return None
    if adtv is not None:
        fact = f"IDX {D.idx['month']['month']} 일평균 거래대금 연초 이후 평균 대비 {sgn(adtv * 100, 0)}(IDX 회원사 집계)"
    else:
        fact = f"{IX_SHORT[c]} 연초 대비 {sgn(ytd)}({md(ix['date'])})"
    text = f"{D.label(BROKER[c])} 영업망은 유지하되 성과연동 보상 등 변동비 전환을 검토할 만합니다."
    return cand("R14", "구조조정·비용", 6, text, [fact], [BROKER[c]], bucket=(adtv is not None and adtv <= -0.15,), fact=fact)


def r15_momentum(D, c, regime):
    if c not in ("VN", "ID") or regime == "NEG" or "브로커리지" not in D.ents.get(BROKER[c], {}).get("focus", ""):
        return None
    ix = D.ix(c)
    if not ix:
        return None
    ch = ix["chg"]
    dd = drawdown(ix, 12)
    tier = "A" if ch.get("3M", -99) >= 5 and ch.get("1M", -99) >= 0 else \
        "B" if ch.get("1W", -99) >= 3 and ch.get("3M", -99) >= 0 and dd is not None and dd >= -0.08 else None
    if not tier:
        return None
    fact = f"{IX_SHORT[c]} 1주 {sgn(ch['1W'])}·3개월 {sgn(ch['3M'])}({md(ix['date'])}), {peak_month(ix, 12)} 고점 대비 {sgn(dd * 100)}"
    return cand("R15", "마케팅·고객", 5, "", [fact], [BROKER[c]], tier, (tier,), fact=fact)


def r16_digital(D, c):
    if c == "ID":
        if D.idx and D.idx.get("month"):
            rows = {r["code"]: r for r in D.idx["month"]["rows"]}
            dig = sum((rows.get(k) or {}).get("share", 0) for k in ("XL", "XC", "PD"))
            xl = rows.get("XL") or {}
            if dig < 15 and xl.get("rank") != 1:
                return None
            ki = rows.get("KI")
            fact = f"IDX {D.idx['month']['month']} 거래대금 점유율 디지털 3사 {dig:.1f}%(Stockbit {xl.get('rank')}위 {xl.get('share', 0):.1f}%)" + \
                (f" vs {D.label('CSA')} {ki['share']:.2f}%({ki['rank']}위)" if ki else "")
            drv = month_end(D.idx["month"]["month"]) + timedelta(days=1)
            return cand("R16", "마케팅·고객", 7, "", [fact], ["CSA"], bucket=(round(dig), xl.get("rank")), driver=drv, fact=fact)
        t = ((D.gmk.get("id") or {}).get("tables") or [{}])[0]
        top = (t.get("rows") or [{}])[0]
        if not re.search(r"Digital", top.get("name", "")):
            return None
        fact = f"IDX 거래대금 1위는 디지털 증권사 {top['name'].split(' (')[0]}({top['value']:,.1f}조 루피아, {t.get('basis', '')})"
        return cand("R16", "마케팅·고객", 7, "", [fact], ["CSA"], bucket=(top["name"],), fact=fact)
    if c == "VN":
        t = ((D.gmk.get("vn") or {}).get("tables") or [None])[0]
        if not t:
            return None
        bm = re.search(r"(\d{4})-(\d{2})", t.get("basis", ""))
        if not bm or (D.today - month_end(bm.group(0))).days > 120:
            return None
        rec = [r for r in t["rows"] if re.search(r"최고", r.get("note", ""))]
        if len(rec) < 2:
            return None
        q = re.search(r"\((\w+)\)", t.get("title", ""))
        fact = f"HOSE {q.group(1) if q else ''} 점유율 {rec[0]['name'].split(' (')[0]} {rec[0]['value']}%·{rec[1]['name']} {rec[1]['value']}%로 최고치({t['basis']})"
        return cand("R16", "마케팅·고객", 7, "", [fact], ["VN"], bucket=(t["basis"],), driver=month_end(bm.group(0)), fact=fact)
    return None


def r17_share_gap(D, c):
    if c == "VN":
        t = ((D.gmk.get("vn") or {}).get("tables") or [None])[0]
        if not t or any(re.search(r"Pinetree", r["name"], re.I) for r in t["rows"]):
            return None
        kr = [r for r in t["rows"] if r.get("korean")]
        if not kr:
            return None
        q = re.search(r"\((\w+)\)", t.get("title", ""))
        thr = min(r["value"] for r in t["rows"])
        fact = f"HOSE {q.group(1) if q else ''} 10위 진입선 {thr}%에 한국계 {len(kr)}곳, {D.label('VN')}은 10위 밖({t['basis']})"
        return cand("R17", "마케팅·고객", 6, "", [fact], ["VN"], "vn", (t["basis"],), fact=fact, korean=len(kr))
    if c == "ID" and D.idx and D.idx.get("trend"):
        tr = D.idx["trend"]
        own = tr.get("KI")
        if not own:
            return None
        cur = (D.idx.get("last_day") or "")[:7]

        def clean(pts):
            xs = [p for p in pts if p[0] != cur]
            if not xs:
                return [], None
            m0 = median(p[1] for p in xs)
            out = [p for p in xs if p[1] <= 3 * m0]
            return out, [p[0] for p in xs if p[1] > 3 * m0]
        pts, outl = clean(own["pts"])
        if len(pts) < 4:
            return None
        mshare = median(p[1] for p in pts)
        peer_top = max((median(p[1] for p in clean(v["pts"])[0]) for k, v in tr.items() if k != "KI" and clean(v["pts"])[0]), default=None)
        if not peer_top or not (mshare < 1.0 and mshare / peer_top < 0.33):
            return None
        s3 = sum(p[1] for p in pts[-3:]) / 3
        h1 = [p[1] for p in pts if p[0][5:7] <= "06" and p[0][:4] == pts[-1][0][:4]]
        s1h = sum(h1) / len(h1) if h1 else None
        delta = s3 - s1h if s1h is not None else 0
        variant = "improving" if delta >= 0.15 else "falling" if delta <= -0.15 else "flat"
        months = f"{int(pts[-3][0][5:7])}~{int(pts[-1][0][5:7])}월"
        fact = f"{D.label('CSA')} IDX 점유율 {months} 평균 {s3:.2f}%" + (f", 1~6월 {s1h:.2f}%" if s1h is not None else "") + \
            (f"({', '.join(o[5:7].lstrip('0') + '월' for o in outl)} 일회성 제외, IDX 회원사 집계)" if outl else "(IDX 회원사 집계)")
        return cand("R17", "마케팅·고객", 6, "", [fact], ["CSA"], variant, (variant,), fact=fact)
    return None


def r18_rwa(D, c):
    hits = [i for i in D.hub_items(c, home=True) if D.age(i.get("date")) <= 180 and RWA_RE.search(i.get("title", ""))]
    if not hits:
        return None
    m = next((x for x in (D.digi or {}).get("markets", []) if x.get("code") == c), None)
    sto = ((m or {}).get("status") or {}).get("sto") or {}
    if D.digi is not None and sto.get("lv") != "ok":
        return None
    head = sorted(hits, key=lambda i: i["date"], reverse=True)[0]
    key = BROKER[c]
    ev = [f"{head.get('src', '')} {d(head['date']).isoformat()} '{head['title']}'"]
    if sto:
        ev.append(f"{KOR[c]} 토큰증권 제도 {sto.get('short', '')} 시행 중(디지털자산 규제 탭)")
    biz = D.ents.get(key, {}).get("focus", "")
    text = f"보도된 RWA 협력을 {D.label(key)} {biz or '자문·IB'} 상품으로 잇는 저비용 사업화를 검토할 만합니다."
    return cand("R18", "상품·제휴", 5, text, ev, [key], bucket=(head["url"],), driver=d(head["date"]), links=[link(head, "보도")], urls=[head["url"]])


def fallbacks(D, c):
    out = []
    key = BROKER[c]
    own, peers, _, _ = own_and_peers(D, c)
    L = D.sub(D.L, key)
    if own and peers and L.get("assets"):
        eq_now = (L["assets"] - L["liab"]) / 100
        allr = sorted([eq_now] + [p["equity_krw"] for p in peers if p.get("equity_krw") is not None], reverse=True)
        rank = allr.index(eq_now) + 1
        med = median(p["equity_krw"] for p in peers if p.get("equity_krw") is not None)
        ev = f"{D.L['label']} 자기자본 {eq_now:,.0f}억원(DART) vs 한국계 동종 중간값 {med:,.0f}억원(FY{own['asof'][:4]})"
        text = f"{D.label(key)} 자기자본은 한국계 {len(allr)}사 중 {rank}위로, 분기 공시마다 격차 추이를 점검합니다."
        out.append(cand("F1", "자본", 2, text, [ev], [key], bucket=(rank,)))
    if L.get("assets") and L.get("ni") is not None:
        roe = L["ni"] * (12 / D.L["months"]) / (L["assets"] - L["liab"]) * 100
        pol = D.policy(c) if c != "SG" else None
        if c == "SG":
            kr = (D.macro.get("kr_base_rate") or [[None, None]])[-1]
            bank, rate, mon = "한국은행 기준금리", kr[1], f"{kr[0][:4]}-{kr[0][4:]}" if kr[0] else ""
        else:
            bank, rate, mon = pol and pol["name"], pol and pol["now"], pol and pol["month"]
        if rate is not None and roe < rate:
            ev = f"{D.L['label']} 연환산 ROE {roe:.1f}%(기말 자본 기준, DART) vs {bank} {rate:.2f}%({mon} 말)"
            text = f"{D.label(key)} 연환산 ROE가 기준금리에 못 미쳐, 자본 효율 목표 설정을 검토할 만합니다."
            out.append(cand("F2", "구조조정·비용", 2, text, [ev], [key], bucket=(roe < 0,)))
    due = sorted((t for t in D.reg.get("todo", []) if t.get("status") != "done" and str(t.get("id", "")).startswith("periodic-") and t.get("due")),
                 key=lambda t: t["due"])
    nxt = next((e for e in sorted(D.cal.get("events", []), key=lambda e: e["date"]) if e.get("bank") == c and d(e["date"]) >= D.today), None)
    if due:
        t = due[0]
        name = re.sub(r"^한화투자증권\s*", "", t.get("item") or t.get("title") or "정기보고서").split(" 해외")[0]
        extra = f"와 {nxt['name']} 결정({md(nxt['date'])})" if nxt else ""
        text = f"다음 판단 시점은 {name}(기한 {md(t['due'])}){extra} 반영 후입니다."
        out.append(cand("F3", "일정", 1, text, ["대외보고 기한(한화투자증권 탭)" + (" · 중앙은행 결정 일정" if nxt else "")], [key]))
    return out


# ---------- 조합·선택 ----------
def evaluate(D, c, published):
    """나라 c의 발동 규칙 → 병합·조정 → 선택. (고른 bullet, 탈락 후보, 국면, 감시 url)"""
    ctx = {"published": published}
    fired, extra = {}, []

    def put(x):
        if not x:
            return
        for y in (x if isinstance(x, list) else [x]):
            if y["rule"] in fired:
                extra.append(y)
            else:
                fired[y["rule"]] = y

    put(r01_scale(D, c, ctx))
    r02 = r02_peer_capital(D, c)
    put(r03_partner(D, c, fired))
    r04 = r04_entry(D, c)
    put(r05_post_injection(D, c))
    put(r06_cross_sell(D, c))
    st = r07_r08_struct(D, c)
    regime = ("NEG" if st["rule"] == "R08" else "POS") if st else None
    put(st)
    put(r09_fx(D, c, ctx))
    put(r10_reg(D, c, set(st.get("urls", [])) if st else set()))
    put(r11_loss(D, c))
    put(r12_jaws(D, c, ctx))
    r13 = r13_shared(D, c)
    r14 = r14_volume(D, c)
    mkt = [x for x in (r15_momentum(D, c, regime), r16_digital(D, c), r17_share_gap(D, c)) if x]
    put(r18_rwa(D, c))
    dropped = []
    loss_rules = bool(fired.get("R11")) or bool(r13) or any(x["rule"] == "R11" for x in extra)

    # M1 R02 → R01, 단독은 R01 없고 흑자·쿨다운 아닐 때만
    if r02:
        if "R01" in fired:
            fired["R01"]["evidence"].append(r02["evidence"][0])
            fired["R01"]["links"] += r02["links"]
            fired["R01"]["driver"] = max(filter(None, [fired["R01"]["driver"], r02["driver"]]), default=None)
        elif not loss(D, BROKER[c]) and not injection(D, BROKER[c]):
            fired["R02"] = r02
        else:
            dropped.append(("R02", "당사 법인 적자·증자 직후"))
    gated = regime == "NEG" or loss_rules
    event = (st or {}).get("event") or "시장 불안 진정"
    cond = " ".join(filter(None, [event if regime == "NEG" else "", "손익 회복" if loss_rules else ""])).replace(" 손익", "과 손익") or event
    # M2·M8 R04: R01 acquire 에 합치거나, 게이트면 '실사만' 문구
    if r04:
        if (fired.get("R01") or {}).get("variant") == "acquire":
            fired["R01"]["evidence"].append(r04["evidence"][0])
        else:
            if gated:
                r04["text"] = f"{KOR[c]} 추가 인수는 원화 비용이 낮아졌어도 {cond} 뒤 집행하고, 후보 실사만 먼저 준비할 만합니다."
                r04["variant"] = "gated"
                r04["bucket"][0:0] = ["gated"]
            fired["R04"] = r04
    if (fired.get("R01") or {}).get("variant") == "acquire" and gated:
        r = fired["R01"]
        r["text"] = f"{D.label(BROKER[c])} 지분 인수 후보는 {cond} 뒤 집행을 전제로 실사만 먼저 준비할 만합니다."
        r["variant"] = "acquire-gated"
    # M3·M4 R11 → R13, R14 → R13 > R11 > 단독
    if r13:
        r11s = [x for x in [fired.get("R11")] + extra if x and x["rule"] == "R11"]
        for x in r11s:
            if x["keys"][0] in r13["keys"]:
                dropped.append(("R11", "R13에 합침"))
        if fired.get("R11") and fired["R11"]["keys"][0] in r13["keys"]:
            del fired["R11"]
        extra[:] = [y for y in extra if not (y["rule"] == "R11" and y["keys"][0] in r13["keys"])]
        rest = next((y for y in extra if y["rule"] == "R11"), None)
        if rest and "R11" not in fired:
            fired["R11"] = rest
            extra.remove(rest)
        fired["R13"] = r13
    if r14:
        host = fired.get("R13") or (fired.get("R11") if fired.get("R11") and fired["R11"]["keys"][0] == BROKER[c] else None)
        if host:
            host["evidence"].append(r14["fact"])
        else:
            fired["R14"] = r14
    # M5·M7 마케팅 한 줄
    if mkt:
        key = BROKER[c]
        r11k = next((x for x in [fired.get("R11")] + extra if x and x["rule"] == "R11" and x["keys"][0] == key), None)
        cost_rule = bool(r11k) or bool(fired.get("R13")) or bool(fired.get("R12") and fired["R12"]["keys"][0] == key) or bool(fired.get("R14"))
        mkt.sort(key=lambda x: -x["weight"])
        lab = D.label(key)
        comps = [x["rule"] for x in mkt]
        tierA = any(x["rule"] == "R15" and x["variant"] == "A" for x in mkt)
        if (r11k and r11k["variant"] == "widen") or (r11k and (r11k.get("cir") or 0) >= 3):
            mode = None
            dropped.append(("MKT", "적자 확대 법인이라 마케팅 지출 제안 안 함"))
        elif (r11k and r11k["variant"] == "flip") or fired.get("R13"):
            mode = "reallocate"
            text = f"{lab} 고정비 절감분을 모바일 온보딩·디지털 수수료 프로모션에 재배분해 점유율 회복을 검토할 만합니다."
        elif fired.get("R12") and fired["R12"]["keys"][0] == key:
            mode = "targeted"
            text = f"{lab}은 전면 수수료 인하 대신 은행·핀테크 제휴와 타깃 프로모션으로 신규 고객 유입을 늘리는 방안을 검토할 만합니다."
        elif not cost_rule and (tierA or regime == "POS"):
            mode = "aggressive"
            text = f"{lab} 신규 계좌 유치 이벤트·수수료 프로모션을 공격적으로 확대하는 방안을 검토할 만합니다."
        else:
            mode = "base"
            top = mkt[0]["rule"]
            text = {"R16": f"모바일 온보딩·디지털 채널 제휴로 {lab} 신규 고객 유입 확대를 검토할 만합니다.",
                    "R17": f"{lab}은 한국계 경쟁사와 겹치지 않는 고객군을 겨냥한 타깃 프로모션을 검토할 만합니다.",
                    "R15": f"반등 구간에 맞춰 {lab} 신규 계좌 유치 이벤트를 재개하는 방안을 검토할 만합니다."}[top]
        if mode:
            fired["MKT"] = cand("MKT", "마케팅·고객", mkt[0]["weight"], text, [x["fact"] for x in mkt][:3], [key], mode,
                                tuple(f"{x['rule']}:{x['variant']}:{x['bucket']}" for x in mkt),
                                driver=max(filter(None, (x["driver"] for x in mkt)), default=None), components=comps)

    # 점수와 선택
    def score(x):
        s = x["weight"] + (1 if x["category"] in LEVERS else 0)
        if x.get("driver") and 0 <= (D.today - d(x["driver"])).days <= 7:
            s += 1
        return s
    pool = list(fired.values()) + extra
    for x in pool:
        x["score"] = score(x)
    pool.sort(key=lambda x: (-x["score"], -x["weight"], -(d(x["driver"]).toordinal() if x.get("driver") else 0), x["rule"]))
    chosen, cats = [], {}
    for x in pool:
        if len(chosen) >= 4:
            x["why_not"] = "4개 마감"
            continue
        if cats.get(x["category"]):
            x["why_not"] = "같은 분야 선택됨" if x["category"] != RISK else "리스크 1개 제한"
            continue
        chosen.append(x)
        cats[x["category"]] = 1
    if len(chosen) < 3:
        for x in pool:
            if len(chosen) >= 3:
                break
            if x not in chosen and x["category"] != RISK:
                chosen.append(x)
                x.pop("why_not", None)
    if len(chosen) < 3:
        fb = fallbacks(D, c)
        have = {x["category"] for x in chosen}
        fb.sort(key=lambda x: (x["rule"] == "F3", x["category"] in have, x["rule"]))
        for x in fb:
            if len(chosen) >= 3:
                break
            if x["rule"] == "F3" or x["category"] not in have or len([y for y in chosen if y["rule"] != "F3"]) < 2:
                chosen.append(x)
                have.add(x["category"])
    losers = [{"rule": x["rule"], "variant": x["variant"], "why_not": x.get("why_not", "")} for x in pool if x not in chosen]
    losers += [{"rule": r, "variant": "", "why_not": why} for r, why in dropped]
    fired_ids = {x["rule"] for x in pool}
    return chosen, losers, fired_ids, regime


def watch_urls(D, c):
    """이 나라의 '큰 뉴스' 후보 url: 구조 뉴스(극성 있는 것), 경쟁사 자본·M&A·제재, 당사 현지 뉴스."""
    out = []
    for it in D.macro_items():
        if it.get("priority") and c in countries_of(it["title"]) and polarity(it["title"]) != 0:
            out.append(it)
        elif c in countries_of(it["title"]) and REG_RE.search(it["title"]):
            out.append(it)
    for it in D.hub_items(c, home=False) + [i for i in D.news_items() if KOR[c] in i.get("title", "")]:
        if (CAPITAL_RE.search(it["title"]) or REG_RE.search(it["title"])) and HOME not in it["title"]:
            out.append(it)
    out += D.hub_items(c, home=True)
    return out


def fingerprint(bullets):
    key = sorted((b["rule"], b["variant"], json.dumps(b["bucket"], ensure_ascii=False)) for b in bullets if b["rule"] != "F3")
    return hashlib.sha1(json.dumps(key, ensure_ascii=False).encode()).hexdigest()[:12]


RULE_NAME = {"R01": "규모 격차", "R02": "경쟁사 자본 확충", "R03": "현지 인수 부담", "R04": "인수 비용", "R05": "증자 후 매출",
             "R06": "교차판매", "R07": "시장 지위 상향", "R08": "구조적 악재", "R09": "환율", "R10": "제재·사기", "R11": "적자",
             "R12": "비용 증가", "R13": "중복 고정비", "R14": "거래대금 감소", "MKT": "점유율·마케팅", "R18": "디지털자산 협력",
             "F1": "자본 격차", "F2": "ROE"}


def run(root=ROOT, now=None, prev=None):
    now = now or datetime.now(KST)
    today = now.date()
    prev = prev if prev is not None else (load(root, OUT_REL) or {})
    state = prev.get("state") or {}
    D = Data(root, today, state)
    out = {"spec_version": SPEC_VERSION, "checked_at": now.isoformat(timespec="minutes"), "countries": {}, "errors": []}
    dart_key = [((D.L or {}).get("report") or {}).get("rcept_no"), ((D.subs.get("invest") or {}).get("report") or {}).get("rcept_no")]
    dart_changed = state.get("dart") is not None and state.get("dart") != dart_key
    new_state = {"dart": dart_key, "spec": SPEC_VERSION, "policy": {}, "miss": {}, "shock": {}, "injection": dict(state.get("injection") or {})}
    for c in COUNTRIES:
        pc = (prev.get("countries") or {}).get(c) or {}
        published = {b["rule"]: b for b in pc.get("bullets", [])}
        try:
            chosen, losers, fired, regime = evaluate(D, c, published)
        except Exception as e:  # 한 나라 실패가 다른 나라를 막지 않게: 이전 블록 유지
            out["errors"].append(f"{c}: {type(e).__name__}: {e}")
            if pc:
                out["countries"][c] = pc
            new_state["miss"][c] = (state.get("miss") or {}).get(c, {})
            continue
        for k in KEYS[c]:
            inj = injection(D, k)
            if inj:
                new_state["injection"][k] = inj
        reasons = []
        if not pc.get("bullets"):
            reasons.append("첫 생성")
        if state.get("spec") not in (None, SPEC_VERSION):
            reasons.append("규칙 개정")
        if dart_changed:
            reasons.append(f"DART {(D.L or {}).get('report', {}).get('name', '새 보고서')} 반영")
        new_map = {b["rule"]: b for b in chosen if b["rule"] != "F3"}
        pub = {r: b for r, b in published.items() if r != "F3"}
        miss = dict((state.get("miss") or {}).get(c, {}))
        for r in list(miss):
            if r in fired:
                del miss[r]
        added = [r for r in new_map if r not in pub or new_map[r]["variant"] != pub[r]["variant"]]
        gone = []
        for r in pub:
            if r in new_map:
                continue
            if r in fired:
                continue  # 아직 발동하지만 더 센 규칙에 밀림: 새 규칙이 들어온 것으로 이미 잡힘
            miss[r] = miss.get(r, 0) + 1
            if miss[r] >= 2:
                gone.append(r)
        if (added or gone) and pc.get("bullets"):
            reasons.append("판단 변화: " + ", ".join([f"+{RULE_NAME.get(r, r)}" for r in added] + [f"−{RULE_NAME.get(r, r)}" for r in gone]))
        moved = [r for r in new_map if r in pub and new_map[r]["variant"] == pub[r]["variant"] and new_map[r]["bucket"] != pub[r].get("bucket")]
        if moved and pc.get("bullets"):
            reasons.append("구간 변화: " + ", ".join(RULE_NAME.get(r, r) for r in moved))
        seen = state.get("seen") or {}
        fresh = [it for it in watch_urls(D, c) if it["url"] not in seen and D.age(it.get("date")) <= NEWS_FRESH_DAYS]
        if fresh and state.get("seen") is not None:
            it = sorted(fresh, key=lambda i: i["date"], reverse=True)[0]
            reasons.append(f"새 뉴스: {news_label(it['title'], it.get('src', ''))}")
        pol = D.policy(c)
        if pol:
            new_state["policy"][c] = pol["now"]
            old = (state.get("policy") or {}).get(c)
            if old is not None and old != pol["now"]:
                reasons.append(f"정책금리 {old:.2f}% → {pol['now']:.2f}%")
        ix = D.ix(c)
        _, _, w_usd = fx_pair(D, c)
        shock = bool(ix and (abs(ix["chg"].get("1W", 0)) >= 7 or ix["chg"].get("1D", 0) <= -4)) or (w_usd is not None and w_usd <= -2)
        new_state["shock"][c] = shock
        if shock and not (state.get("shock") or {}).get(c):
            reasons.append("지수·환율 급변")
        if pc.get("changed_at") and (today - d(pc["changed_at"])).days >= MAX_STALE_DAYS:
            reasons.append(f"정기 갱신({MAX_STALE_DAYS}일)")
        new_state["miss"][c] = {r: n for r, n in miss.items() if r not in new_map}
        block = {"country": KOR[c], "entities": [D.label(k) for k in KEYS[c]], "regime": regime}
        if reasons:
            bullets = [{k: b[k] for k in ("rule", "variant", "category", "text", "evidence", "links", "bucket")} for b in chosen]
            hist = (pc.get("history") or [])[-59:] + [{"date": today.isoformat(), "fp": fingerprint(chosen), "rules": [b["rule"] for b in chosen], "reason": reasons}]
            block.update(bullets=bullets, changed_at=today.isoformat(), reason=reasons[:3], last_check="갱신", candidates=losers, history=hist)
        else:
            block.update({k: pc.get(k) for k in ("bullets", "changed_at", "reason", "candidates", "history")}, last_check="큰 변화 없음")
        out["countries"][c] = block
    out["updated_at"] = max((b.get("changed_at") or "" for b in out["countries"].values()), default="")
    # 본 기사 보관(최근 200일): 다음 실행의 '새 뉴스' 판정과 구조 뉴스 국면 유지용
    seen = dict(state.get("seen") or {})
    first = today.isoformat()
    for it in D.macro_items() + D.news_items() + [i for c in COUNTRIES for i in D.hub_items(c)]:
        if it.get("url") and it["url"] not in seen:
            keep = {k: it.get(k) for k in ("date", "title", "src", "priority", "kind", "firms") if it.get(k) is not None}
            seen[it["url"]] = {**keep, "first_seen": first}
    new_state["seen"] = {u: v for u, v in seen.items() if D.age(v.get("date")) <= 200}
    out["state"] = new_state
    return out


def main():
    res = run()
    if "--print" in sys.argv[1:]:
        for c, b in res["countries"].items():
            print(f"== {b['country']} · {b.get('changed_at')} · {b.get('last_check')} · {', '.join(b.get('reason') or [])}")
            for x in b.get("bullets") or []:
                print(f"  [{x['category']}] {x['text']}\n      근거: {' · '.join(x['evidence'])}")
            for x in b.get("candidates") or []:
                print(f"    (탈락 {x['rule']} {x['variant']}: {x['why_not']})")
        print("errors:", res["errors"])
        return
    p = ROOT / OUT_REL
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(p)
    print(f"저장: {p} · " + " / ".join(f"{b['country']} {b.get('last_check')}" for b in res["countries"].values()))


if __name__ == "__main__":
    main()
