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


def load(name, default):
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def save(name, obj):
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------- 1) 진출국 스코어카드 ----------
COUNTRIES = [("KOR", "한국"), ("VNM", "베트남"), ("IDN", "인도네시아"), ("SGP", "싱가포르"),
             ("USA", "미국"), ("JPN", "일본"), ("ARE", "아랍에미리트")]
# (키, IMF 지표, 표시명, 단위)
IMF = [("gdp_growth", "NGDP_RPCH", "실질 GDP 성장률", "%"), ("cpi", "PCPIPCH", "소비자물가 상승률", "%"),
       ("gdp_pc", "NGDPDPC", "1인당 GDP", "USD"), ("pop", "LP", "인구", "백만 명"), ("gdp", "NGDPD", "GDP", "십억 USD")]
# (키, 세계은행 지표, 표시명, 단위)
WB = [("mcap_gdp", "CM.MKT.LCAP.GD.ZS", "상장주식 시가총액/GDP", "%"), ("turnover", "CM.MKT.TRNR", "주식 회전율", "%"),
      ("listed", "CM.MKT.LDOM.NO", "상장 국내기업 수", "개"), ("account", "FX.OWN.TOTL.ZS", "금융계좌 보유율(15세+)", "%")]


def imf(indicator, isos, years):
    url = f"https://www.imf.org/external/datamapper/api/v1/{indicator}/{'/'.join(isos)}"
    d = net.get_json(url, {"periods": ",".join(map(str, years))}, headers=BROWSER)
    return d.get("values", {}).get(indicator, {})


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
    errors, ok = [], 0
    for key, ind, _, _ in IMF:
        try:
            vals = imf(ind, isos, [yr - 1, yr, yr + 1])
            for c in isos:
                v = vals.get(c, {})
                if key == "gdp_growth":
                    rows[c][key] = {str(y): v.get(str(y)) for y in (yr - 1, yr, yr + 1)}
                elif v.get(str(yr)) is not None:
                    rows[c][key] = {"v": v[str(yr)], "y": str(yr)}
            ok += 1
        except Exception as e:
            errors.append(f"IMF {ind}: {e}"[:160])
    for key, ind, _, _ in WB:
        try:
            for c, (v, y) in worldbank(ind, isos).items():
                if c in rows:
                    rows[c][key] = {"v": v, "y": y}
            ok += 1
        except Exception as e:
            errors.append(f"세계은행 {ind}: {e}"[:160])
    out = {"updated_at": NOW.isoformat(timespec="seconds") if ok else prev.get("updated_at"),
           "checked_at": NOW.isoformat(timespec="seconds"), "weo_year": yr,
           "fields": {k: {"label": lab, "unit": u, "src": "IMF WEO"} for k, _, lab, u in IMF}
           | {k: {"label": lab, "unit": u, "src": "세계은행 WDI"} for k, _, lab, u in WB},
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
      ("부국증권", "001270"), ("유진투자증권", "001200"), ("LS증권", "078020")]
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
            out[t] = (last["reportedValue"]["raw"], last["asOfDate"])
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

    # 결산일 환율(상장사 자본·한국계 법인 원화 환산)과 최근 환율(시가총액)
    days = sorted({r["asof"] for m in listed.get("markets", {}).values() for r in m.get("rows", []) if r.get("asof")} | {"2025-12-31"})
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
        for r in listed.get("markets", {}).get(mid, {}).get("rows", []):
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
        v, stale = val("kr", code, f"{code}.KS")
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
                       "url": f"https://finance.yahoo.com/quote/{code}.KS/"})
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
                       {"label": "한국계 법인: DART 2025 사업보고서 '종속기업 요약재무정보'", "url": "https://dart.fss.or.kr/"}],
           "markets": markets, "errors": errors}
    save("landscape.json", out)
    for mid, m in markets.items():
        print(f"landscape {mid}: {len(m['rows'])}행, P/B 중앙값 {m['median_pb']}, ROE 중앙값 {m['median_roe']}")
    for e in errors:
        print("  !", e)


# ---------- 3) 인도네시아 거래대금 점유율 ----------
IDX_HOSTS = ["https://www.idx.co.id", "https://idx.co.id"]
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
                errors.append(f"{key}: {e}")
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
    jobs = sys.argv[1:] or ["country", "landscape", "idx"]
    for name, fn in (("country", country), ("landscape", landscape), ("idx", idx_share)):
        if name in jobs:
            try:
                fn()
            except Exception as e:  # 한 섹션 실패가 다른 섹션을 막지 않게
                print(f"{name} 실패: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
