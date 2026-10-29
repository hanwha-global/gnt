"""전략 인사이트 탭 데이터(키·LLM 불필요). 섹션마다 따로 실패해도 나머지는 갱신하고, 실패한 값은 이전 값을 유지한다.

1) 진출국 스코어카드  → insight/data/country.json
   IMF World Economic Outlook DataMapper(성장률·물가·1인당 GDP·인구·GDP 전망), 세계은행 WDI(시가총액/GDP·회전율·상장사 수·금융계좌 보유율)
2) 현지 경쟁 구도      → insight/data/landscape.json
   상장 증권사 자본·순이익(site/data/global/listed.json, 매주 수집) + Yahoo Finance 주가·발행주식수(시가총액·P/B)
   + 한국계 현지법인(DART 사업보고서 '종속기업 요약재무정보', site/data/domestic/sub_fin.json·consolidated.json)
   환산 환율: Yahoo Finance 종가(각 결산일·최근 거래일)
3) 인도네시아 증권사 거래대금 점유율 → insight/data/idx_share.json
   IDX(인도네시아거래소) 회원사별 일별 거래 요약. 날짜별로 한 번만 받아 월별 합계로 쌓는다(insight/data/idx_daily.json).
"""
import json
import re
import statistics
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import net  # noqa: E402
from update_listed import MARKETS  # noqa: E402  상장 증권사 목록은 글로벌 탭과 같은 것을 쓴다

DATA = ROOT / "insight" / "data"
NOW = datetime.now(timezone.utc)
BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
           "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9"}


def short(e, n=120):
    """오류 문구에서 HTML을 걷어 짧게."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(e))).strip()[:n]


def load(name, default):
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def save(name, obj):
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------- 1) 진출국 스코어카드 ----------
COUNTRIES = [("KOR", "한국"), ("VNM", "베트남"), ("IDN", "인도네시아"), ("SGP", "싱가포르"),
             ("USA", "미국"), ("JPN", "일본"), ("ARE", "아랍에미리트")]
# (키, IMF 지표, 세계은행 대체 지표, 배수, 표시명, 단위). IMF가 막히면 세계은행 실적치(최신 연도)로 채운다.
IMF = [("gdp_growth", "NGDP_RPCH", "NY.GDP.MKTP.KD.ZG", 1, "실질 GDP 성장률", "%"),
       ("cpi", "PCPIPCH", "FP.CPI.TOTL.ZG", 1, "소비자물가 상승률", "%"),
       ("gdp_pc", "NGDPDPC", "NY.GDP.PCAP.CD", 1, "1인당 GDP", "USD"),
       ("pop", "LP", "SP.POP.TOTL", 1e-6, "인구", "백만 명"),
       ("gdp", "NGDPD", "NY.GDP.MKTP.CD", 1e-9, "GDP", "십억 USD")]
# (키, 세계은행 지표, 표시명, 단위)
WB = [("mcap_gdp", "CM.MKT.LCAP.GD.ZS", "상장주식 시가총액/GDP", "%"), ("turnover", "CM.MKT.TRNR", "주식 회전율", "%"),
      ("listed", "CM.MKT.LDOM.NO", "상장 국내기업 수", "개"), ("account", "FX.OWN.TOTL.ZS", "금융계좌 보유율(15세+)", "%")]


def imf(indicator, isos, years):
    url = f"https://www.imf.org/external/datamapper/api/v1/{indicator}/{'/'.join(isos)}"
    last = None
    for hdr in (None, BROWSER):  # IMF 앞단(Akamai)이 일부 요청을 막아 두 방식으로 시도
        try:
            d = net.get_json(url, {"periods": ",".join(map(str, years))}, headers=hdr)
            return d.get("values", {}).get(indicator, {})
        except Exception as e:
            last = e
    raise RuntimeError(str(last))


def worldbank(indicator, isos):
    url = f"https://api.worldbank.org/v2/country/{';'.join(isos)}/indicator/{indicator}"
    d = net.get_json(url, {"format": "json", "mrnev": 1, "per_page": 200})
    if not isinstance(d, list) or len(d) < 2:
        raise RuntimeError(f"세계은행 응답 이상: {str(d)[:120]}")
    return {r["countryiso3code"]: (r["value"], r["date"]) for r in d[1] or [] if r.get("value") is not None}


def country():
    prev = load("country.json", {"rows": {}})
    isos = [c for c, _ in COUNTRIES]
    yr = NOW.year
    rows = {c: dict(prev.get("rows", {}).get(c, {}), iso=c, name=n) for c, n in COUNTRIES}
    errors, ok, fields = [], 0, {}
    for key, ind, wb, mult, lab, unit in IMF:
        try:
            vals = imf(ind, isos, [yr, yr + 1])
            for c in isos:
                v = vals.get(c, {})
                if v.get(str(yr)) is not None:
                    rows[c][key] = {"v": v[str(yr)], "y": str(yr), "src": "IMF"}
                if key == "gdp_growth" and v.get(str(yr + 1)) is not None:
                    rows[c]["gdp_growth_next"] = {"v": v[str(yr + 1)], "y": str(yr + 1), "src": "IMF"}
            fields[key] = {"label": lab, "unit": unit, "src": "IMF WEO 전망"}
            ok += 1
            continue
        except Exception as e:
            errors.append(f"IMF {ind}: {short(e)}")
        try:
            got = worldbank(wb, isos)
            for c, (v, y) in got.items():
                if c in rows:
                    rows[c][key] = {"v": v * mult, "y": y, "src": "WB"}
            fields[key] = {"label": lab, "unit": unit, "src": "세계은행 실적"}
            ok += 1
        except Exception as e:
            errors.append(f"세계은행 {wb}: {e}"[:120])
    for key, ind, lab, unit in WB:
        try:
            for c, (v, y) in worldbank(ind, isos).items():
                if c in rows:
                    rows[c][key] = {"v": v, "y": y, "src": "WB"}
            fields[key] = {"label": lab, "unit": unit, "src": "세계은행"}
            ok += 1
        except Exception as e:
            errors.append(f"세계은행 {ind}: {e}"[:120])
    out = {"updated_at": NOW.isoformat(timespec="seconds") if ok else prev.get("updated_at"),
           "checked_at": NOW.isoformat(timespec="seconds"), "weo_year": yr, "fields": fields,
           "sources": [{"label": "IMF World Economic Outlook (DataMapper)", "url": "https://www.imf.org/external/datamapper"},
                       {"label": "World Bank WDI", "url": "https://data.worldbank.org/"}],
           "rows": rows, "errors": errors}
    save("country.json", out)
    print(f"country: 지표 {ok}/{len(IMF) + len(WB)} 수집", *[f"\n  ! {e}" for e in errors])


# ---------- 2) 현지 경쟁 구도 ----------
# 국내 상장 증권사(밸류에이션 비교용). 지주사는 증권 자회사 비중이 높은 곳만.
KR = [("미래에셋증권", "006800"), ("한국금융지주", "071050"), ("NH투자증권", "005940"), ("삼성증권", "016360"),
      ("키움증권", "039490"), ("대신증권", "003540"), ("한화투자증권", "003530"), ("유안타증권", "003470"),
      ("교보증권", "030610"), ("현대차증권", "001500"), ("SK증권", "001510"), ("다올투자증권", "030210"),
      ("부국증권", "001270"), ("유진투자증권", "001200"), ("LS증권", "078020.KQ")]
MKT = {"vn": ("베트남", "VND"), "id": ("인도네시아", "IDR"), "sg": ("싱가포르", "SGD"), "jp": ("일본", "JPY")}
# 증권사끼리 비교: 이름에 Securities·Sekuritas 가 있는 법인만 순위에 넣고, 운용·IT 법인은 '기타'로 따로 둔다
BROKER = re.compile(r"securit|sekuritas", re.I)


def ychart(symbol, rng="5d"):
    """종가 시계열 [(YYYY-MM-DD, close)]와 meta."""
    last = None
    for host in ("query1", "query2"):
        try:
            d = net.get_json(f"https://{host}.finance.yahoo.com/v8/finance/chart/{symbol}",
                             {"range": rng, "interval": "1d"}, headers=BROWSER)["chart"]["result"][0]
            ts, cl = d.get("timestamp") or [], d["indicators"]["quote"][0].get("close") or []
            pts = [(datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d"), c) for t, c in zip(ts, cl) if c]
            return pts, d.get("meta", {})
        except Exception as e:
            last = e
    raise RuntimeError(f"chart: {last}"[:120])


def yseries(symbol, types):
    now = int(time.time())
    d = net.get_json(f"https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{symbol}",
                     {"type": ",".join(types), "period1": now - 3 * 365 * 86400, "period2": now}, headers=BROWSER)
    out = {}
    for r in d.get("timeseries", {}).get("result", []):
        t = (r.get("meta", {}).get("type") or [None])[0]
        pts = [p for p in (r.get(t) or []) if p and p.get("reportedValue")]
        if pts:
            last = max(pts, key=lambda p: p["asOfDate"])
            out[t] = (last["reportedValue"]["raw"], last["asOfDate"], last.get("currencyCode"))
    return out


def on_or_before(pts, day):
    xs = [v for d, v in pts if d <= day]
    return xs[-1] if xs else None


def fx_table(days):
    """통화별 원화 환산율(1 통화 = ? 원) {ccy: {day: rate, 'now': rate, 'now_date': d}}."""
    usd, _ = ychart("KRW=X", "2y")
    out = {"KRW": {"now": 1.0}}
    for ccy in ("VND", "IDR", "SGD", "JPY", "USD"):
        pts = [(d, 1.0) for d, _ in usd] if ccy == "USD" else ychart(f"{ccy}=X", "2y")[0]
        row = {}
        for day in days:
            a, b = on_or_before(usd, day), on_or_before(pts, day)
            if a and b:
                row[day] = a / b
        a, b = usd[-1][1], pts[-1][1]
        row.update({"now": a / b, "now_date": min(usd[-1][0], pts[-1][0])})
        out[ccy] = row
    return out


def valuation(symbol):
    """시가총액(원 통화)·주가·최근 분기 자본. 주식 수 × 최근 종가."""
    pts, meta = ychart(symbol)
    price = meta.get("regularMarketPrice") or (pts[-1][1] if pts else None)
    s = yseries(symbol, ["quarterlyOrdinarySharesNumber", "annualOrdinarySharesNumber", "quarterlyStockholdersEquity",
                         "annualStockholdersEquity", "annualNetIncome"])
    shares = s.get("quarterlyOrdinarySharesNumber") or s.get("annualOrdinarySharesNumber")
    if not price or not shares:
        raise RuntimeError("주가 또는 주식 수 없음")
    q = s.get("quarterlyStockholdersEquity")
    return {"price": price, "ccy": meta.get("currency"), "price_date": pts[-1][0] if pts else None,
            "mcap": price * shares[0], "q_equity": q[0] if q else None, "q_asof": q[1] if q else None,
            "a_equity": s.get("annualStockholdersEquity", (None,))[0], "a_ni": s.get("annualNetIncome", (None,))[0],
            "a_asof": s.get("annualStockholdersEquity", (None, None))[1]}


# 베트남 상장 증권사(HOSE·HNX·UPCoM) 전체: VNDirect finfo 공개 API(키 불필요). 업종 8777(투자서비스) 회원 중
# 상장 상태이고 최근 연간 재무가 있는 회사만 쓴다. 비상장 증권사는 이 API에 최근 재무가 없어(2020년 무렵에서 끊김) 빠진다.
VND = "https://api-finfo.vndirect.com.vn/v4"
# 증권사 재무 양식(재무상태표 89, 손익 90)의 항목 코드
VND_ITEMS = {"equity": 14000, "paid_in": 14110, "assets": 12700, "loans": 700001,
             "ni": 23000, "ni_all": 23003, "rev": 21001, "brokerage": 621110}


def vnd(path, q=None, **params):
    if q:
        params["q"] = q
    return net.get_json(f"{VND}/{path}", params).get("data", [])


def vnd_fs(code, report_type):
    """기간별 {fiscalDate: {항목: 값}} (원 단위 동)."""
    rows = vnd("financial_statements", f"code:{code}~reportType:{report_type}~modelType:89,90",
               sort="fiscalDate:desc", size=800)
    want = {v: k for k, v in VND_ITEMS.items()}
    out = {}
    for r in rows:
        k = want.get(int(r.get("itemCode") or 0))
        if k and r.get("numericValue") is not None:
            out.setdefault(r["fiscalDate"], {})[k] = r["numericValue"]
    return out


def vnd_hist(code, keys=("brokerage", "ni", "ni_all", "rev"), n=8):
    """분기 손익 이력 {fiscalDate: {항목: 값}} 최근 n분기. 항목 필터가 안 먹으면 손익 양식 전체를 받아 거른다."""
    want = {VND_ITEMS[k]: k for k in keys}
    base = f"code:{code}~reportType:QUARTER~modelType:90"
    rows = vnd("financial_statements", base + "~itemCode:" + ",".join(map(str, want)), sort="fiscalDate:desc", size=200)
    if not rows or any(int(r.get("itemCode") or 0) not in want for r in rows):
        rows = vnd("financial_statements", base, sort="fiscalDate:desc", size=1200)
    out = {}
    for r in rows:
        k = want.get(int(r.get("itemCode") or 0))
        if k and r.get("numericValue") is not None:
            out.setdefault(r["fiscalDate"], {})[k] = r["numericValue"]
    return {d: out[d] for d in sorted(out, reverse=True)[:n]}


def months_between(a, b):
    return (int(a[:4]) - int(b[:4])) * 12 + int(a[5:7]) - int(b[5:7])


def ttm(hist):
    """최근 4개 분기 지배주주 순이익 합(분기가 3개월씩 이어질 때만). (값, 마지막 분기)"""
    ds = sorted(hist, reverse=True)[:4]
    if len(ds) < 4 or any(months_between(ds[i], ds[i + 1]) != 3 for i in range(3)):
        return None, None
    vals = [hist[d].get("ni") if hist[d].get("ni") is not None else hist[d].get("ni_all") for d in ds]
    return (sum(vals), ds[0]) if all(v is not None for v in vals) else (None, None)


def vn_universe():
    """상장 증권사 전체의 최근 연간·분기 재무와 시가총액·P/B. (rows, errors)"""
    errors = []
    ind = vnd("industry_classification", "codeList:SSI")
    codes = next((x["codeList"].split(",") for x in ind if str(x.get("industryCode")) == "8777"), [])
    if not codes:
        raise RuntimeError("VNDirect: 업종 8777 목록 없음")
    info = {}
    for i in range(0, len(codes), 40):
        for r in vnd("stocks", f"code:{','.join(codes[i:i + 40])}", size=100,
                     fields="code,companyName,companyNameEng,floor,status,type"):
            info[r["code"]] = r
    listed = [c for c in codes if info.get(c, {}).get("floor") in ("HOSE", "HNX", "UPCOM")
              and str(info[c].get("status", "")).lower() == "listed" and info[c].get("type") == "STOCK"]
    rows = []
    for c in listed:
        try:
            ann = vnd_fs(c, "ANNUAL")
            years = sorted((d for d in ann if ann[d].get("equity")), reverse=True)
            if not years or years[0] < f"{NOW.year - 1}-12-31":  # 최근 사업연도 재무가 없으면(휴면·상장폐지 예정) 뺀다
                errors.append(f"vn {c}: 최근 연간 재무 없음({years[0] if years else '-'})")
                continue
            cur, prv = ann[years[0]], ann.get(f"{int(years[0][:4]) - 1}{years[0][4:]}", {})
            qtr = vnd_fs(c, "QUARTER")
            qd = max((d for d in qtr if qtr[d].get("equity")), default=None)
            ratio = {r["ratioCode"]: r for r in vnd("ratios/latest", None, filter="ratioCode:MARKETCAP,PRICE_TO_BOOK",
                                                     where=f"code:{c}", order="reportDate", fields="ratioCode,value,reportDate")}
            ni = cur.get("ni") if cur.get("ni") is not None else cur.get("ni_all")
            hist = vnd_hist(c)
            t_ni, t_asof = ttm(hist)
            if c == "SSI":  # 분기 값이 분기분(누적 아님)인지 연간과 맞춰 본다
                y = years[0][:4]
                print("vn SSI 점검: 연간 중개수익", cur.get("brokerage"), "분기 합", sum((v.get("brokerage") or 0) for d, v in hist.items() if d[:4] == y),
                      "분기", sorted(d for d in hist if d[:4] == y))
            rows.append({"q_hist": hist, "ttm_ni": t_ni, "ttm_asof": t_asof,"code": c, "name": info[c].get("companyNameEng") or info[c].get("companyName"), "name_vn": info[c].get("companyName"),
                         "floor": info[c]["floor"], "asof": years[0], "equity": cur["equity"], "equity_prev": prv.get("equity"),
                         "paid_in": cur.get("paid_in"), "assets": cur.get("assets"), "loans": cur.get("loans"), "ni": ni,
                         "rev": cur.get("rev"), "brokerage": cur.get("brokerage"),
                         "q_date": qd, "q_equity": qtr[qd]["equity"] if qd else None, "q_loans": qtr[qd].get("loans") if qd else None,
                         "mcap": ratio.get("MARKETCAP", {}).get("value"), "pb": ratio.get("PRICE_TO_BOOK", {}).get("value"),
                         "price_date": ratio.get("MARKETCAP", {}).get("reportDate")})
        except Exception as e:
            errors.append(f"vn {c}: {short(e, 80)}")
        time.sleep(0.15)
    print(f"vn universe: 업종 {len(codes)}곳 중 상장 {len(listed)}곳, 재무 확보 {len(rows)}곳")
    return rows, errors


def norm(n):
    return re.sub(r"[^0-9a-z가-힣]", "", str(n or "").lower())


def korean_subs():
    """나라별 한국계 현지 영업법인(종속기업 요약재무정보 행이 있는 것만). 금액은 백만원."""
    sf = json.loads((ROOT / "site/data/domestic/sub_fin.json").read_text(encoding="utf-8"))
    cons = json.loads((ROOT / "site/data/domestic/consolidated.json").read_text(encoding="utf-8"))
    by = {}
    for firm, fv in sf.get("firms", {}).items():
        subs = {norm(k): (k, v) for k, v in fv.get("subs", {}).items()}
        for o in cons.get("firms", {}).get(firm, {}).get("overseas", []):
            if o.get("class") != "영업법인" or o.get("country") not in [c for c, _ in MKT.values()]:
                continue
            hit = subs.get(norm(o["name"])) or subs.get(norm(o.get("seed_name")))
            if not hit or hit[1].get("equity") is None:
                continue
            name, v = hit
            by.setdefault(o["country"], []).append({
                "firm": firm, "name": name, "business": o.get("business"), "broker": bool(BROKER.search(name)),
                "equity_mkrw": v["equity"], "ni_mkrw": v.get("ni"), "own": v.get("own"), "report": fv.get("report"),
                "rcept_no": fv.get("rcept_no")})
    return by


def vn_row(d, fx, ccy, div):
    """VNDirect 원자료(동) → 화면 행(현지 표시 단위 = 조동, 원화 억원)."""
    rate, now = fx[ccy].get(d["asof"]) or fx[ccy]["now"], fx[ccy]["now"]
    u = lambda v: None if v is None else round(v / div, 2)
    return {"kind": "local", "name": d["name"], "ticker": d["code"], "note": d["floor"], "asof": d["asof"],
            "equity": u(d["equity"]), "ni": u(d["ni"]), "equity_krw": d["equity"] * rate / 1e8,
            "roe": round(d["ni"] / d["equity"] * 100, 1) if d["ni"] is not None and d["equity"] else None,
            "equity_prev": u(d["equity_prev"]),
            "growth": round((d["equity"] / d["equity_prev"] - 1) * 100, 1) if d["equity_prev"] else None,
            "paid_in": u(d["paid_in"]), "loans": u(d["loans"]), "loans_krw": d["loans"] * rate / 1e8 if d["loans"] else None,
            "brokerage": u(d["brokerage"]), "brokerage_krw": d["brokerage"] * rate / 1e8 if d["brokerage"] else None, "rev": u(d["rev"]),
            "q_date": d["q_date"], "q_equity": u(d["q_equity"]), "q_equity_krw": d["q_equity"] * now / 1e8 if d["q_equity"] else None,
            "mcap": u(d["mcap"]), "mcap_krw": d["mcap"] * now / 1e8 if d["mcap"] else None,
            "pb": round(d["pb"], 2) if d["pb"] else None, "pb_book": "분기", "pb_asof": d["q_date"], "price_date": d["price_date"],
            "ttm_ni": u(d.get("ttm_ni")), "ttm_asof": d.get("ttm_asof"),
            "roe_ttm": round(d["ttm_ni"] / d["q_equity"] * 100, 1) if d.get("ttm_ni") is not None and d.get("q_equity") else None,
            "pe": round(d["mcap"] / d["ttm_ni"], 1) if d.get("mcap") and d.get("ttm_ni") and d["ttm_ni"] > 0 else None,
            "via": "vndirect", "url": f"https://dstock.vndirect.com.vn/tong-quan/{d['code']}", "stale": False}


def vn_brokerage(vn_rows):
    """상장 증권사 분기 중개수수료 수익 점유율(상장사 합계 대비) → vn_brokerage.json. 거래소 발표 상위 10곳 밖을 잇는 자동 지표."""
    cnt = {}
    for r in vn_rows:
        for d, v in r.get("q_hist", {}).items():
            if v.get("brokerage"):
                cnt[d] = cnt.get(d, 0) + 1
    if not cnt:
        return
    top = max(cnt.values())
    qs = sorted(d for d, n in cnt.items() if n >= 0.8 * top)[-6:]  # 대부분이 낸 분기만(늦게 내는 곳 때문에 비율이 튀지 않게)
    tot = {q: sum((r["q_hist"].get(q, {}).get("brokerage") or 0) for r in vn_rows) for q in qs}
    rows = []
    for r in vn_rows:
        rev = {q: r["q_hist"].get(q, {}).get("brokerage") for q in qs}
        share = {q: round(v / tot[q] * 100, 3) for q, v in rev.items() if v and tot[q]}
        if share:
            rows.append({"code": r["code"], "name": r["name"], "floor": r["floor"], "share": share,
                         "rev_bn": {q: round(v / 1e9, 1) for q, v in rev.items() if v}})
    last = qs[-1]
    ytd = [q for q in qs if q[:4] == last[:4]]
    yt = sum(tot[q] for q in ytd)
    for x in rows:
        x["ytd"] = round(sum(x["rev_bn"].get(q, 0) for q in ytd) * 1e9 / yt * 100, 3) if yt else None
    rows.sort(key=lambda x: -(x["share"].get(last) or -1))
    save("vn_brokerage.json", {"updated_at": NOW.isoformat(timespec="seconds"), "quarters": qs, "ytd_quarters": ytd,
                               "reported": {q: cnt[q] for q in qs}, "total_bn": {q: round(tot[q] / 1e9) for q in qs}, "rows": rows,
                               "source": {"label": "VNDirect 공개 재무(각 사 분기 재무제표, 중개수수료 수익)", "url": "https://dstock.vndirect.com.vn/"},
                               "method": "회사별 분기 중개수수료 수익 ÷ 같은 분기 상장 증권사 합계. 거래대금 점유율이 아니며 비상장사는 빠짐"})
    print(f"vn brokerage: 분기 {qs}, 최근 분기 {cnt[last]}곳 보고")


def landscape():
    prev = load("landscape.json", {"markets": {}})
    listed = json.loads((ROOT / "site/data/global/listed.json").read_text(encoding="utf-8"))
    errors = []
    oldval = {f"{m}:{r['ticker']}": r for m, mv in prev.get("markets", {}).items() for r in mv.get("rows", []) if r.get("ticker")}

    def val(mid, ticker, symbol):
        try:
            v = valuation(symbol)
            return v, False
        except Exception as e:
            o = oldval.get(f"{mid}:{ticker}")
            errors.append(f"{mid} {ticker}: {e}{' (이전 값 유지)' if o and o.get('mcap') else ''}"[:160])
            return ({k: o.get(k) for k in ("price", "price_date", "mcap", "q_equity", "q_asof", "ccy")} if o and o.get("mcap") else None), True

    try:
        vn_rows, vn_err = vn_universe()
        errors += vn_err
    except Exception as e:
        vn_rows = []
        errors.append(f"vn 전체 목록: {short(e)} (Yahoo 상장사 목록으로 대체)")
    if vn_rows:
        try:
            vn_brokerage(vn_rows)
        except Exception as e:
            errors.append(f"vn 중개수익 점유율: {short(e)}")
    # 결산일 환율(상장사 자본·한국계 법인 원화 환산)과 최근 환율(시가총액)
    days = sorted({r["asof"] for m in listed.get("markets", {}).values() for r in m.get("rows", []) if r.get("asof")}
                  | {d["asof"] for d in vn_rows} | {"2025-12-31"})
    try:
        fx = fx_table(days)
    except Exception as e:
        errors.append(f"환율: {e}"[:160])
        fx = prev.get("fx")
    if not fx:
        print("landscape: 환율 없음, 이전 파일 유지")
        return
    subs = korean_subs()
    markets = {}
    for mid, (cname, ccy) in MKT.items():
        unit, div, ysfx = MARKETS[mid][0], MARKETS[mid][1], MARKETS[mid][2]
        rows = []
        if mid == "vn" and vn_rows:
            rows = [vn_row(d, fx, ccy, div) for d in vn_rows]
        for r in ([] if rows else listed.get("markets", {}).get(mid, {}).get("rows", [])):
            sym = r["ticker"] + (".HN" if r.get("note") == "HNX" else ysfx)
            v, stale = val(mid, r["ticker"], sym)
            rate = fx[ccy].get(r["asof"]) or fx[ccy]["now"]
            eq_l = r["equity"] * div  # 원 통화
            row = {"kind": "local", "name": r["name"], "ticker": r["ticker"], "note": r.get("note"), "asof": r["asof"],
                   "equity": r["equity"], "ni": r.get("ni"), "equity_krw": eq_l * rate / 1e8,
                   "roe": round(r["ni"] / r["equity"] * 100, 1) if r.get("ni") is not None and r["equity"] else None,
                   "url": r.get("url"), "stale": r.get("stale", False)}
            if v:
                book = v.get("q_equity") or eq_l
                row.update({"price": v.get("price"), "price_date": v.get("price_date"), "mcap": round(v["mcap"] / div, 2),
                            "mcap_krw": v["mcap"] * fx[ccy]["now"] / 1e8, "pb": round(v["mcap"] / book, 2) if book else None,
                            "pb_book": "분기" if v.get("q_equity") else "연간", "pb_asof": v.get("q_asof") or r["asof"],
                            "val_stale": stale})
            rows.append(row)
        ye = fx[ccy].get("2025-12-31") or fx[ccy]["now"]
        for s in subs.get(cname, []):
            eq_l = s["equity_mkrw"] * 1e6 / ye
            rows.append({"kind": "korean", "name": s["name"], "firm": s["firm"], "broker": s["broker"], "business": s["business"],
                         "asof": "2025-12-31", "equity": round(eq_l / div, 2), "ni": None if s["ni_mkrw"] is None else round(s["ni_mkrw"] * 1e6 / ye / div, 2),
                         "equity_krw": s["equity_mkrw"] / 100, "own": s["own"],
                         "roe": round(s["ni_mkrw"] / s["equity_mkrw"] * 100, 1) if s["ni_mkrw"] is not None and s["equity_mkrw"] > 0 else None,
                         "report": s["report"], "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={s['rcept_no']}" if s.get("rcept_no") else None})
        rows.sort(key=lambda x: -(x["equity_krw"] or 0))
        pbs = [x["pb"] for x in rows if x.get("pb") and x["pb"] > 0]
        roes = [x["roe"] for x in rows if x["kind"] == "local" and x.get("roe") is not None]
        markets[mid] = {"country": cname, "ccy": ccy, "unit": unit, "fx_ye": ye, "rows": rows,
                        "median_pb": round(statistics.median(pbs), 2) if pbs else None,
                        "median_roe": round(statistics.median(roes), 1) if roes else None}
    # 국내 상장 증권사(밸류에이션 비교)
    krrows = []
    for name, code in KR:
        sym = code if "." in code else f"{code}.KS"
        code = code.split(".")[0]
        v, stale = val("kr", code, sym)
        if not v:
            continue
        o = oldval.get(f"kr:{code}", {})
        eq = v.get("q_equity") or v.get("a_equity") or o.get("equity_raw")
        a_eq, a_ni = v.get("a_equity") or o.get("a_equity"), v.get("a_ni") if v.get("a_ni") is not None else o.get("a_ni")
        krrows.append({"kind": "kr", "name": name, "ticker": code, "price": v.get("price"), "price_date": v.get("price_date"),
                       "mcap_krw": v["mcap"] / 1e8, "equity_raw": eq, "equity_krw": eq / 1e8 if eq else None,
                       "pb": round(v["mcap"] / eq, 2) if eq else None, "pb_asof": v.get("q_asof") or v.get("a_asof") or o.get("pb_asof"),
                       "a_equity": a_eq, "a_ni": a_ni, "a_asof": v.get("a_asof") or o.get("a_asof"),
                       "roe": round(a_ni / a_eq * 100, 1) if a_eq and a_ni is not None else None, "val_stale": stale,
                       "url": f"https://finance.yahoo.com/quote/{sym}/"})
    krrows.sort(key=lambda x: -(x["mcap_krw"] or 0))
    pbs = [x["pb"] for x in krrows if x.get("pb")]
    roes = [x["roe"] for x in krrows if x.get("roe") is not None]
    markets["kr"] = {"country": "한국", "ccy": "KRW", "unit": "억원", "rows": krrows,
                     "median_pb": round(statistics.median(pbs), 2) if pbs else None,
                     "median_roe": round(statistics.median(roes), 1) if roes else None}
    if not any(m["rows"] for m in markets.values()):
        print("landscape: 결과 없음, 이전 파일 유지")
        return
    out = {"updated_at": NOW.isoformat(timespec="seconds"), "listed_updated_at": listed.get("updated_at"),
           "fx": fx, "fx_source": "Yahoo Finance 종가(USD 교차)",
           "sources": [{"label": "상장사 자본·순이익: Yahoo Finance·stockanalysis.com(각 사 공시 기반)", "url": "https://finance.yahoo.com/"},
                       *([{"label": "베트남 상장 증권사 전체: VNDirect 공개 재무(각 사 감사 재무제표)", "url": "https://dstock.vndirect.com.vn/"}] if vn_rows else []),
                       {"label": "한국계 법인: DART 2025 사업보고서 '종속기업 요약재무정보'", "url": "https://dart.fss.or.kr/"}],
           "markets": markets, "errors": errors}
    save("landscape.json", out)
    for mid, m in markets.items():
        print(f"landscape {mid}: {len(m['rows'])}행, P/B 중앙값 {m['median_pb']}, ROE 중앙값 {m['median_roe']}")
    for e in errors:
        print("  !", e)


# ---------- 2-2) 나라·시장별 상장 증권사 밸류에이션 ----------
# (키, 이름, 묶음, [(회사, Yahoo 심볼, 비고)]). 일본·인니·싱가포르는 글로벌 탭 목록, 베트남은 위 VNDirect 전체 상장사를 그대로 쓴다.
# 증권업 비중이 큰 회사만 넣는다(은행이 중심인 금융지주 제외, 금융지주라도 증권이 주력이면 비고에 표시).
VAL_MARKETS = [
    ("kr", "한국", "국내", [(n, c if "." in c else f"{c}.KS", "") for n, c in KR]),
    ("vn", "베트남", "진출국", None),
    ("id", "인도네시아", "진출국", [(n, f"{t}.JK", b) for n, t, b in MARKETS["id"][4]]),
    ("sg", "싱가포르", "진출국", [(n, f"{t}.SI", b) for n, t, b in MARKETS["sg"][4]]),
    ("jp", "일본", "아시아", [(n, f"{t}.T", b) for n, t, b in MARKETS["jp"][4]]),
    ("cn", "중국(본토 A주)", "아시아", [
        ("CITIC Securities", "600030.SS", ""), ("Huatai Securities", "601688.SS", ""), ("Guotai Haitong Securities", "601211.SS", ""),
        ("China Merchants Securities", "600999.SS", ""), ("GF Securities", "000776.SZ", ""), ("China Galaxy Securities", "601881.SS", ""),
        ("CICC", "601995.SS", ""), ("Shenwan Hongyuan", "000166.SZ", ""), ("CSC Financial", "601066.SS", ""),
        ("Guosen Securities", "002736.SZ", ""), ("Orient Securities", "600958.SS", ""), ("Industrial Securities", "601377.SS", ""),
        ("Changjiang Securities", "000783.SZ", ""), ("Everbright Securities", "601788.SS", ""), ("Zhongtai Securities", "600918.SS", ""),
        ("Founder Securities", "601901.SS", ""), ("East Money Information", "300059.SZ", "온라인")]),
    ("hk", "홍콩", "아시아", [
        ("CITIC Securities (H)", "6030.HK", "본토사 H주"), ("Huatai Securities (H)", "6886.HK", "본토사 H주"),
        ("Guotai Haitong (H)", "2611.HK", "본토사 H주"), ("China Merchants Securities (H)", "6099.HK", "본토사 H주"),
        ("GF Securities (H)", "1776.HK", "본토사 H주"), ("China Galaxy Securities (H)", "6881.HK", "본토사 H주"),
        ("CICC (H)", "3908.HK", "본토사 H주"), ("CSC Financial (H)", "6066.HK", "본토사 H주"), ("Orient Securities (H)", "3958.HK", "본토사 H주"),
        ("Guotai Junan International", "1788.HK", ""), ("Bright Smart Securities", "1428.HK", ""), ("Emperor Capital", "0717.HK", ""),
        ("Get Nice Holdings", "0064.HK", ""), ("Shenwan Hongyuan (H.K.)", "0218.HK", ""), ("Futu Holdings", "FUTU", "온라인, 미국 상장")]),
    ("tw", "대만", "아시아", [
        ("Yuanta Financial Holding", "2885.TW", "증권 주력 금융지주"), ("Capital Securities", "6005.TW", ""), ("President Securities", "2855.TW", ""),
        ("Grand Fortune Securities", "6026.TW", ""), ("Concord Securities", "6016.TWO", ""), ("Horizon Securities", "6015.TWO", "")]),
    ("th", "태국", "아시아", [
        ("Asia Plus Group", "ASP.BK", ""), ("KGI Securities (Thailand)", "KGI.BK", ""), ("Finansia Syrus Securities", "FSS.BK", ""),
        ("UOB Kay Hian Securities (Thailand)", "UOBKH.BK", ""), ("Country Group Holdings", "CGH.BK", ""), ("Globlex Holding", "GBX.BK", ""),
        ("Trinity Watthana", "TNITY.BK", ""), ("AIRA Capital", "AIRA.BK", ""), ("XSpring Capital", "XPG.BK", ""), ("Maybank Securities (Thailand)", "MST.BK", ""),
        ("Seamico Securities", "ZMICO.BK", "")]),
    ("my", "말레이시아", "아시아", [
        ("Kenanga Investment Bank", "6483.KL", ""), ("Hong Leong Capital", "5274.KL", ""), ("Apex Equity Holdings", "5088.KL", ""),
        ("Mercury Securities Group", "0256.KL", "")]),
    ("ph", "필리핀", "아시아", [("COL Financial Group", "COL.PS", "온라인")]),
    ("in", "인도", "아시아", [
        ("Angel One", "ANGELONE.NS", "온라인"), ("Motilal Oswal Financial Services", "MOTILALOFS.NS", ""), ("IIFL Capital Services", "IIFLCAPS.NS", ""),
        ("Nuvama Wealth Management", "NUVAMA.NS", ""), ("JM Financial", "JMFINANCIL.NS", ""), ("Geojit Financial Services", "GEOJITFSL.NS", ""),
        ("5paisa Capital", "5PAISA.NS", "온라인"), ("Share India Securities", "SHAREINDIA.NS", ""), ("SMC Global Securities", "SMCGLOBAL.NS", ""),
        ("Groww (Billionbrains Garage Ventures)", "GROWW.NS", "온라인")]),
    ("us", "미국", "미주·유럽", [
        ("Morgan Stanley", "MS", ""), ("Goldman Sachs", "GS", ""), ("Charles Schwab", "SCHW", ""), ("Interactive Brokers", "IBKR", "온라인"),
        ("Robinhood", "HOOD", "온라인"), ("Raymond James", "RJF", ""), ("LPL Financial", "LPLA", ""), ("Jefferies", "JEF", ""),
        ("Stifel", "SF", ""), ("Evercore", "EVR", "IB 자문"), ("Houlihan Lokey", "HLI", "IB 자문"), ("StoneX", "SNEX", ""),
        ("Piper Sandler", "PIPR", ""), ("Virtu Financial", "VIRT", ""), ("Lazard", "LAZ", "IB 자문"), ("Moelis", "MC", "IB 자문"),
        ("PJT Partners", "PJT", "IB 자문"), ("Oppenheimer", "OPY", "")]),
    ("uk", "영국", "미주·유럽", [
        ("IG Group", "IGG.L", "온라인"), ("Plus500", "PLUS.L", "온라인"), ("AJ Bell", "AJB.L", "온라인"), ("CMC Markets", "CMCX.L", "온라인"),
        ("Peel Hunt", "PEEL.L", "")]),
    ("eu", "유럽(대륙)", "미주·유럽", [
        ("Avanza Bank", "AZA.ST", "온라인, 스웨덴"), ("Nordnet", "SAVE.ST", "온라인, 스웨덴"), ("flatexDEGIRO", "FTK.DE", "온라인, 독일"),
        ("Swissquote", "SQN.SW", "온라인, 스위스"), ("Vontobel", "VONN.SW", "스위스")]),
    ("au", "호주", "미주·유럽", [("Bell Financial Group", "BFG.AX", ""), ("Euroz Hartleys", "EZL.AX", "")]),
]
# 가격 통화가 보조 단위로 나오는 시장(런던 펜스 등)
SUBUNIT = {"GBp": ("GBP", 100), "GBX": ("GBP", 100), "ZAc": ("ZAR", 100), "ILA": ("ILS", 100)}


def fx_now(ccys):
    """1 통화 = ? 원 (최근 종가, USD 교차)."""
    usd, _ = ychart("KRW=X", "5d")
    out = {"KRW": 1.0, "USD": usd[-1][1]}
    for c in sorted(set(ccys) - set(out)):
        try:
            pts, _ = ychart(f"{c}=X", "5d")
            out[c] = usd[-1][1] / pts[-1][1]
        except Exception as e:
            print(f"  환율 {c}: {short(e, 60)}")
    return out


def world_val(symbol):
    """주가·주식 수·최근 분기 자본·최근 4개 분기 순이익(없으면 연간). 금액은 각 통화 원 단위."""
    pts, meta = ychart(symbol)
    price, pccy = meta.get("regularMarketPrice") or (pts[-1][1] if pts else None), meta.get("currency")
    if pccy in SUBUNIT:
        pccy, k = SUBUNIT[pccy]
        price = price / k if price else price
    s = yseries(symbol, ["quarterlyOrdinarySharesNumber", "annualOrdinarySharesNumber", "quarterlyStockholdersEquity",
                         "annualStockholdersEquity", "trailingNetIncome", "annualNetIncome"])
    shares = s.get("quarterlyOrdinarySharesNumber") or s.get("annualOrdinarySharesNumber")
    eq = s.get("quarterlyStockholdersEquity") or s.get("annualStockholdersEquity")
    tn, an = s.get("trailingNetIncome"), s.get("annualNetIncome")
    ni, basis = (tn, "4Q") if tn and (not an or tn[1] >= an[1]) else (an, "연간")  # 최근 4개 분기 합이 없거나 연간보다 오래되면 연간
    if not price or not shares or not eq:
        raise RuntimeError("주가·주식 수·자본 중 없음")
    return {"name_y": meta.get("longName") or meta.get("shortName"), "price": price, "pccy": pccy, "price_date": pts[-1][0] if pts else None,
            "mcap": price * shares[0], "equity": eq[0], "eq_asof": eq[1], "fccy": eq[2] or pccy,
            "ni": ni[0] if ni else None, "ni_asof": ni[1] if ni else None, "ni_basis": basis if ni else None}


def valuation_world():
    prev = load("valuation.json", {"markets": {}})
    old = {f"{m}:{r['symbol']}": r for m, mv in prev.get("markets", {}).items() for r in mv.get("rows", []) if r.get("symbol")}
    land = load("landscape.json", {"markets": {}}).get("markets", {})
    errors, raw = [], {}
    for mid, nm, grp, lst in VAL_MARKETS:
        if lst is None:
            continue
        for name, sym, note in lst:
            try:
                raw[(mid, sym)] = (name, note, world_val(sym))
            except Exception as e:
                errors.append(f"{mid} {sym}: {short(e, 90)}")
            time.sleep(0.25)
    try:
        fx = fx_now({v["pccy"] for _, _, v in raw.values()} | {v["fccy"] for _, _, v in raw.values()})
    except Exception as e:
        print("valuation: 환율 실패, 이전 파일 유지", e)
        return
    markets = {}
    for mid, nm, grp, lst in VAL_MARKETS:
        rows = []
        if lst is None:  # 베트남: landscape.json 의 VNDirect 상장사 값을 그대로
            for r in land.get("vn", {}).get("rows", []):
                if r.get("kind") != "local" or not r.get("mcap_krw"):
                    continue
                eq_krw = r.get("q_equity_krw") or None
                rows.append({"name": r["name"], "symbol": r["ticker"], "note": r.get("note", ""), "mcap_krw": r["mcap_krw"],
                             "equity_krw": eq_krw, "pb": r.get("pb"), "roe": r.get("roe_ttm") if r.get("roe_ttm") is not None else r.get("roe"),
                             "roe_basis": "4Q" if r.get("roe_ttm") is not None else "연간", "pe": r.get("pe"),
                             "eq_asof": r.get("q_date"), "ni_asof": r.get("ttm_asof") or r.get("asof"), "price_date": r.get("price_date"),
                             "ccy": "VND", "url": r.get("url"), "stale": False})
        else:
            for name, sym, note in lst:
                got = raw.get((mid, sym))
                if not got:
                    o = old.get(f"{mid}:{sym}")
                    if o:
                        rows.append({**o, "stale": True})
                    continue
                _, _, v = got
                pr, fr = fx.get(v["pccy"]), fx.get(v["fccy"])
                if not pr or not fr:
                    errors.append(f"{mid} {sym}: 환율 없음({v['pccy']}/{v['fccy']})")
                    continue
                mcap, eqk = v["mcap"] * pr / 1e8, v["equity"] * fr / 1e8
                nik = v["ni"] * fr / 1e8 if v["ni"] is not None else None
                rows.append({"name": name, "name_y": v["name_y"], "symbol": sym, "note": note, "mcap_krw": mcap, "equity_krw": eqk,
                             "pb": round(mcap / eqk, 2) if eqk > 0 else None,
                             "roe": round(nik / eqk * 100, 1) if nik is not None and eqk > 0 else None, "roe_basis": v["ni_basis"],
                             "pe": round(mcap / nik, 1) if nik and nik > 0 else None,
                             "eq_asof": v["eq_asof"], "ni_asof": v["ni_asof"], "price_date": v["price_date"], "ccy": v["pccy"],
                             "fccy": v["fccy"], "url": f"https://finance.yahoo.com/quote/{sym}/", "stale": False})
        rows.sort(key=lambda x: -(x["mcap_krw"] or 0))
        med = lambda k, pos=False: (round(statistics.median(v), 2) if (v := [x[k] for x in rows if x.get(k) is not None and (x[k] > 0 or not pos)]) else None)
        markets[mid] = {"name": nm, "group": grp, "n": len(rows), "mcap_krw": sum(x["mcap_krw"] or 0 for x in rows),
                        "median_pb": med("pb", True), "median_roe": med("roe"), "median_pe": med("pe", True),
                        "eq_asof": max((x["eq_asof"] for x in rows if x.get("eq_asof")), default=None),
                        "price_date": max((x["price_date"] for x in rows if x.get("price_date")), default=None), "rows": rows}
    if not any(m["rows"] for m in markets.values()):
        print("valuation: 결과 없음, 이전 파일 유지")
        return
    save("valuation.json", {"updated_at": NOW.isoformat(timespec="seconds"), "fx": fx, "markets": markets, "errors": errors,
                            "source": {"label": "Yahoo Finance(주가·주식 수·각 사 공시 재무), 베트남은 VNDirect", "url": "https://finance.yahoo.com/"},
                            "method": "P/B = 시가총액(최근 종가 × 발행주식 수) ÷ 최근 분기 자기자본, ROE·P/E = 최근 4개 분기 순이익 기준(없으면 최근 연간), 원화 환산은 최근 환율"})
    for mid, m in markets.items():
        print(f"valuation {mid}: {m['n']}곳 P/B {m['median_pb']} ROE {m['median_roe']} P/E {m['median_pe']} 시총 {round(m['mcap_krw'] / 1e4)}조원")
        for r in m["rows"]:
            print("   ", r["symbol"], "|", r["name"][:28], "|", (r.get("name_y") or "")[:40], "|", r.get("ccy"), r.get("fccy"), "|",
                  round(r["mcap_krw"]), r.get("equity_krw") and round(r["equity_krw"]), r.get("pb"), r.get("roe"), r.get("roe_basis"), r.get("pe"),
                  r.get("eq_asof"), r.get("ni_asof"), "STALE" if r.get("stale") else "")
    for e in errors:
        print("  !", e)


# ---------- 3) 인도네시아 거래대금 점유율 ----------
IDX_HOSTS = ["https://www.idx.co.id", "https://www.idx.id", "https://idx.id"]
# 한국계·당사 표시(회원사명 일부). 회원사 코드는 IDX 응답에서 그대로 쓴다.
IDX_TAGS = [("Ciptadana", "한화투자증권"), ("Mirae", "미래에셋증권"), ("Korea Investment", "한국투자증권"),
            ("NH Korindo", "NH투자증권"), ("KB Valbury", "KB증권"), ("Shinhan", "신한투자증권"), ("Kiwoom", "키움증권"),
            ("Samsung", "삼성증권"), ("Daishin", "대신증권")]


def idx_day(d):
    last = None
    for host in IDX_HOSTS:
        try:
            raw = net.get(f"{host}/primary/TradingSummary/GetBrokerSummary",
                          {"length": 9999, "start": 0, "date": d.strftime("%Y%m%d")},
                          headers={**BROWSER, "Referer": f"{host}/id/data-pasar/ringkasan-perdagangan/ringkasan-broker/"}, retries=2)
            j = json.loads(raw)
            rows = j.get("data") or j.get("Data") or []
            out = {}
            for r in rows:
                code = r.get("IDFirm") or r.get("FirmCode") or r.get("Code")
                val = r.get("Value") if r.get("Value") is not None else r.get("TotalValue")
                if code and val is not None:
                    out[code] = {"name": (r.get("FirmName") or r.get("Name") or "").strip(), "value": float(val)}
            return out
        except Exception as e:
            last = e
    raise RuntimeError(str(last)[:160])


def idx_share():
    cache = load("idx_daily.json", {"days": {}, "names": {}})
    errors, fetched, tried = [], 0, 0
    today = (NOW + timedelta(hours=7)).date()
    start = date(today.year - (1 if today.month == 1 else 0), 1, 1)  # 올해(1월이면 작년부터)
    d = today - timedelta(days=1)
    while d >= start and tried < 400:
        key = d.isoformat()
        if d.weekday() < 5 and key not in cache["days"]:
            tried += 1
            try:
                rows = idx_day(d)
                cache["days"][key] = {c: round(v["value"]) for c, v in rows.items()} if rows else {}
                for c, v in rows.items():
                    cache["names"][c] = v["name"]
                fetched += 1
            except Exception as e:
                errors.append(f"{key}: {short(e)}")
                if len(errors) >= 3 and fetched == 0:
                    break  # 막혔으면 오래 두드리지 않는다
            time.sleep(0.3)
        d -= timedelta(days=1)
    days = {k: v for k, v in cache["days"].items() if v}
    print(f"idx: 새로 {fetched}일, 누적 거래일 {len(days)}일", *[f"\n  ! {e}" for e in errors[:5]])
    save("idx_daily.json", cache)
    if not days:
        prev = load("idx_share.json", {})
        save("idx_share.json", {**prev, "checked_at": NOW.isoformat(timespec="seconds"), "errors": errors[:5]})
        return
    last = max(days)

    def agg(keys):
        tot = {}
        for k in keys:
            for c, v in days[k].items():
                tot[c] = tot.get(c, 0) + v
        s = sum(tot.values()) or 1
        rank = sorted(tot.items(), key=lambda x: -x[1])
        return [{"code": c, "name": cache["names"].get(c, c), "value": v, "share": round(v / s * 100, 2), "rank": i + 1,
                 "korean": next((f for kw, f in IDX_TAGS if kw.lower() in cache["names"].get(c, "").lower()), None)}
                for i, (c, v) in enumerate(rank)], s, len(keys)

    y = last[:4]
    ytd = sorted(k for k in days if k.startswith(y))
    months = sorted({k[:7] for k in ytd})
    full = [m for m in months if m < last[:7]] or months  # 마지막 완결 월
    mlast = full[-1]
    ytd_rows, ytd_total, ytd_n = agg(ytd)
    m_rows, m_total, m_n = agg([k for k in ytd if k.startswith(mlast)])
    trend = {}
    for m in months:
        rows, _, _ = agg([k for k in ytd if k.startswith(m)])
        for r in rows:
            if r["korean"]:
                trend.setdefault(r["code"], {"name": r["name"], "firm": r["korean"], "pts": []})["pts"].append([m, r["share"], r["rank"]])
    save("idx_share.json", {
        "updated_at": NOW.isoformat(timespec="seconds"), "checked_at": NOW.isoformat(timespec="seconds"),
        "source": {"label": "IDX 회원사별 거래 요약(Ringkasan Broker)", "url": "https://www.idx.co.id/id/data-pasar/ringkasan-perdagangan/ringkasan-broker/"},
        "method": "회원사별 매수+매도 거래대금 ÷ 전체 회원사 합계(정규·비정규 시장 포함)",
        "last_day": last, "ytd": {"from": ytd[0], "to": ytd[-1], "days": ytd_n, "total": ytd_total, "rows": ytd_rows[:25] + [r for r in ytd_rows[25:] if r["korean"]]},
        "month": {"month": mlast, "days": m_n, "total": m_total, "rows": m_rows[:25] + [r for r in m_rows[25:] if r["korean"]]},
        "trend": trend, "brokers": len(ytd_rows), "errors": errors[:5]})


def main():
    jobs = sys.argv[1:] or ["country", "landscape", "valuation", "idx"]
    for name, fn in (("country", country), ("landscape", landscape), ("valuation", valuation_world), ("idx", idx_share)):
        if name in jobs:
            try:
                fn()
            except Exception as e:  # 한 섹션 실패가 다른 섹션을 막지 않게
                print(f"{name} 실패: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
