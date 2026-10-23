"""금리·지수·환율(Macro) 데이터를 무료 공개 출처에서 받아 hanwha/data/markets.json에 저장한다.

- 정책금리(월): BIS 중앙은행 정책금리(WS_CBPOL, 키 불필요). 없는 나라는 ECOS 902Y006·722Y001(env ECOS_API_KEY)
- 환율(일): ECOS 731Y001(주요국 통화의 대원화환율, 매매기준율). 실패 시 Yahoo Finance 환율로 대체
- 주가지수·달러인덱스(일): Yahoo Finance chart API (키 불필요). VN-Index는 VNDirect 공개 시세 API

GitHub Actions가 평일 하루 두 번 실행한다. 표준 라이브러리만 쓰고 LLM 토큰은 쓰지 않는다.
한 출처가 실패해도 나머지는 갱신하고, 전부 실패한 항목은 기존 값을 그대로 둔다.
"""
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# API 키: 환경변수(Actions Secrets) → 로컬 .env → 터미널 실행 시 숨김 입력(scripts/keys.py)
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from keys import get_key  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "data" / "markets.json"
KST = dt.timezone(dt.timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (compatible; global-network-dashboard/1.0)"}

# (그룹, 표시명, Yahoo 심볼 후보). 앞 후보가 실패하면 다음 후보를 쓴다.
INDICES = [
    ("국내", "코스피", ["^KS11"]),
    ("국내", "코스닥", ["^KQ11"]),
    ("미국", "S&P 500", ["^GSPC"]),
    ("미국", "NASDAQ Comp.", ["^IXIC"]),
    ("미국", "DJIA", ["^DJI"]),
    ("미국", "Russell 2000", ["^RUT"]),
    ("아시아", "상해종합", ["000001.SS"]),
    ("아시아", "항셍", ["^HSI"]),
    ("아시아", "Nikkei 225", ["^N225"]),
    ("아시아", "VN-Index", ["vndirect:VNINDEX", "^VNINDEX.VN"]),
    ("아시아", "IDX(자카르타)", ["^JKSE"]),
    ("아시아", "STI(싱가포르)", ["^STI"]),
    ("중동·유럽", "FTSE ADX(아부다비)", ["FADGI.FGI", "^FADGI", "FTFADGI.FGI", "^ADI"]),
    ("중동·유럽", "Euro Stoxx 50", ["^STOXX50E"]),
    ("환율", "달러인덱스(DXY)", ["DX-Y.NYB"]),
]
# 월말 MoM 표에 쓰는 지수(표시명)
MOM = ["코스피", "S&P 500", "Euro Stoxx 50", "상해종합", "VN-Index", "IDX(자카르타)"]

# 환율: (코드, 표시명, 단위, ECOS 항목명 검색어, Yahoo 심볼)
FX = [
    ("USD", "미국 달러", 1, "미국달러", "KRW=X"),
    ("EUR", "유로", 1, "유로", "EURKRW=X"),
    ("JPY", "일본 엔", 100, "일본엔", "JPYKRW=X"),
    ("GBP", "영국 파운드", 1, "영국파운드", "GBPKRW=X"),
    ("SGD", "싱가포르 달러", 1, "싱가포르달러", "SGDKRW=X"),
    ("HKD", "홍콩 달러", 1, "홍콩달러", "HKDKRW=X"),
    ("VND", "베트남 동", 100, "베트남동", "VNDKRW=X"),
    ("IDR", "인도네시아 루피아", 100, "인도네시아루피아", "IDRKRW=X"),
]

# 정책금리: (키, 표시명, ECOS 902Y006 항목명 검색어). 한국은 722Y001에서 받는다.
POLICY = [
    ("US", "미국 Fed(중간값)", ["미국"], "US"),
    ("KR", "한국 BOK", None, "KR"),
    ("EU", "유로존 ECB", ["유로"], "XM"),
    ("JP", "일본 BOJ", ["일본"], "JP"),
    ("UK", "영국 BoE", ["영국"], "GB"),
    ("ID", "인니 BI", ["인도네시아"], "ID"),
    ("VN", "베트남 SBV", ["베트남"], "VN"),
    ("CN", "중국 LPR 1Y", ["중국"], "CN"),
    ("IN", "인도 RBI", ["인도"], "IN"),
    ("CA", "캐나다 BoC", ["캐나다"], "CA"),
]


def http_json(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


# ---------- Yahoo ----------
def yahoo(symbol, rng="2y", interval="1d"):
    """[(YYYY-MM-DD, close)] 오름차순. 실패하면 빈 리스트."""
    q = urllib.parse.quote(symbol)
    for host in ("query1", "query2"):
        try:
            d = http_json(f"https://{host}.finance.yahoo.com/v8/finance/chart/{q}?range={rng}&interval={interval}")
            res = d["chart"]["result"][0]
            off = res.get("meta", {}).get("gmtoffset", 0)
            ts, cl = res.get("timestamp") or [], res["indicators"]["quote"][0].get("close") or []
            pts = {}
            for t, c in zip(ts, cl):
                if c is not None:
                    pts[dt.datetime.fromtimestamp(t + off, dt.timezone.utc).date().isoformat()] = round(float(c), 4)
            if pts:
                return sorted(pts.items())
        except Exception as e:  # noqa: BLE001 — 출처 하나의 실패로 전체를 멈추지 않는다
            print(f"  yahoo {symbol} ({host}) 실패: {e}")
    return []


def vndirect(code, since):
    """VNDirect 공개 시세 API(키 불필요)로 VN-Index 일별 종가."""
    url = ("https://api-finfo.vndirect.com.vn/v4/vnmarket_prices?sort=date&size=800&page=1&q="
           + urllib.parse.quote(f"code:{code}~date:gte:{since}"))
    try:
        d = http_json(url)
        pts = sorted({r["date"]: round(float(r["close"]), 2) for r in d.get("data", []) if r.get("close")}.items())
        return pts
    except Exception as e:  # noqa: BLE001
        print(f"  vndirect {code} 실패: {e}")
        return []


def series(sym):
    if sym.startswith("vndirect:"):
        return vndirect(sym.split(":", 1)[1], (dt.date.today() - dt.timedelta(days=730)).isoformat())
    return yahoo(sym)


# BIS·ECOS에 없는 베트남 SBV 재융자금리 변경 이력(공표일, %). 금리가 바뀌면 한 줄 추가한다.
SBV_CHANGES = [("2019-01-01", 6.0), ("2020-03-17", 5.0), ("2020-05-13", 4.5), ("2020-10-01", 4.0),
               ("2022-09-23", 5.0), ("2022-10-25", 6.0), ("2023-04-03", 5.5), ("2023-05-25", 5.0), ("2023-06-19", 4.5)]


def monthly_from_changes(changes, today):
    out, i, rate = [], 0, None
    m = dt.date(2019, 1, 1)
    while m <= today:
        end = add_months(m, 1) - dt.timedelta(days=1)
        while i < len(changes) and changes[i][0] <= end.isoformat():
            rate = changes[i][1]
            i += 1
        if rate is not None:
            out.append((m.strftime("%Y-%m"), rate))
        m = add_months(m, 1)
    return out


def bis_policy(start="2019-01"):
    """BIS 중앙은행 정책금리(WS_CBPOL) 월별. {키: [(YYYY-MM, %)]}"""
    areas = "+".join(a for *_, a in POLICY)
    url = f"https://stats.bis.org/api/v1/data/WS_CBPOL/M.{areas}?startPeriod={start}&format=csv"
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=60) as r:
            text = r.read().decode("utf-8-sig")
    except Exception as e:  # noqa: BLE001
        print(f"  BIS 정책금리 실패: {e}")
        return {}
    import csv
    import io
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        print("  BIS 응답 비어 있음:", text[:200])
        return {}
    area_key = next((c for c in rows[0] if c.upper().startswith("REF_AREA")), "REF_AREA")
    tkey = next((c for c in rows[0] if c.upper().startswith("TIME_PERIOD")), "TIME_PERIOD")
    vkey = next((c for c in rows[0] if c.upper().startswith("OBS_VALUE")), "OBS_VALUE")
    back = {a: k for k, _, _, a in POLICY}
    out = {}
    for r in rows:
        a = (r.get(area_key) or "").split(":")[0].strip()
        if a in back and r.get(vkey) not in (None, "", "NaN"):
            out.setdefault(back[a], []).append((r[tkey][:7], round(float(r[vkey]), 3)))
    for k in out:
        out[k] = sorted(dict(out[k]).items())
    print("  BIS 정책금리:", {k: v[-1] for k, v in out.items()})
    return out


def close_on_or_before(pts, day):
    v = None
    for d, c in pts:
        if d <= day:
            v = (d, c)
        else:
            break
    return v


def add_months(d, n):
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    last = [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return dt.date(y, m, min(d.day, last))


def month_ends(pts):
    out = {}
    for d, c in pts:
        out[d[:7]] = c
    return sorted(out.items())


def perf(pts):
    """일별 종가로 1D~1Y 등락률(%)과 12개월 추이를 만든다."""
    if len(pts) < 2:
        return None
    last_d, last = pts[-1]
    day = dt.date.fromisoformat(last_d)

    def chg(base):
        return round((last / base - 1) * 100, 2) if base else None

    ref = {
        "1D": pts[-2],
        "1W": close_on_or_before(pts, (day - dt.timedelta(days=7)).isoformat()),
        "1M": close_on_or_before(pts, add_months(day, -1).isoformat()),
        "3M": close_on_or_before(pts, add_months(day, -3).isoformat()),
        "6M": close_on_or_before(pts, add_months(day, -6).isoformat()),
        "YTD": close_on_or_before(pts, dt.date(day.year - 1, 12, 31).isoformat()),
        "1Y": close_on_or_before(pts, add_months(day, -12).isoformat()),
    }
    me = month_ends(pts)
    return {"date": last_d, "close": last, "chg": {k: chg(v[1]) if v else None for k, v in ref.items()},
            "spark": [c for _, c in me[-13:]], "monthly": me[-14:]}


# ---------- ECOS ----------
def ecos(key, *parts):
    url = "/".join(["https://ecos.bok.or.kr/api"] + [urllib.parse.quote(str(p)) for p in (parts[0], key, "json", "kr") + parts[1:]])
    d = http_json(url)
    body = d.get(parts[0])
    if not body:
        print(f"  ECOS {parts[0]} {parts[3] if len(parts) > 3 else ''}: {d.get('RESULT', d)}")
        return []
    return body.get("row", [])


def ecos_fx(key, today):
    items = ecos(key, "StatisticItemList", 1, 200, "731Y001")
    print(f"  ECOS 731Y001 항목 {len(items)}개")
    start = (today - dt.timedelta(days=40)).strftime("%Y%m%d")
    out = {}
    for code, _, _, word, _ in FX:
        it = next((i for i in items if word in i["ITEM_NAME"].replace(" ", "")), None)
        if not it:
            print(f"  ECOS 환율 항목 없음: {word}")
            continue
        rows = ecos(key, "StatisticSearch", 1, 100, "731Y001", "D", start, today.strftime("%Y%m%d"), it["ITEM_CODE"])
        pts = [(f"{r['TIME'][:4]}-{r['TIME'][4:6]}-{r['TIME'][6:]}", float(r["DATA_VALUE"].replace(",", ""))) for r in rows if r.get("DATA_VALUE")]
        if pts:
            out[code] = pts
    return out


def ecos_policy(key, today):
    start = "201901"
    end = today.strftime("%Y%m")
    series = {}
    items = ecos(key, "StatisticItemList", 1, 200, "902Y006")
    print("  ECOS 902Y006 항목:", ", ".join(f"{i['ITEM_CODE']}={i['ITEM_NAME']}" for i in items)[:600])
    for k, _, words, _ in POLICY:
        if words is None:
            rows = ecos(key, "StatisticSearch", 1, 400, "722Y001", "M", start, end, "0101000")
        else:
            it = next((i for i in items if any(w == i["ITEM_NAME"].strip() or i["ITEM_NAME"].startswith(w) for w in words)
                       and not (k == "IN" and "인도네시아" in i["ITEM_NAME"])), None)
            if not it:
                continue
            rows = ecos(key, "StatisticSearch", 1, 400, "902Y006", "M", start, end, it["ITEM_CODE"])
        pts = [(f"{r['TIME'][:4]}-{r['TIME'][4:6]}", float(r["DATA_VALUE"])) for r in rows if r.get("DATA_VALUE")]
        if pts:
            series[k] = pts
    return series


def policy_table(series):
    rows = []
    for k, name, _, _ in POLICY:
        s = series.get(k)
        if not s:
            continue
        cur = s[-1][1]
        back = lambda n: s[-1 - n][1] if len(s) > n else None  # noqa: E731
        y1 = back(12)
        rows.append({"key": k, "name": name, "month": s[-1][0], "now": cur, "m3": back(3), "y1": y1,
                     "d1y_bp": round((cur - y1) * 100) if y1 is not None else None})
    return rows


def fx_block(pts_by_ccy, source):
    rows = []
    for code, name, unit, _, _ in FX:
        pts = pts_by_ccy.get(code)
        if not pts:
            continue
        d, v = pts[-1]
        prev = close_on_or_before(pts, (dt.date.fromisoformat(d) - dt.timedelta(days=7)).isoformat())
        rows.append({"ccy": code, "name": name, "unit": unit, "date": d, "krw": round(v, 4),
                     "prev_date": prev[0] if prev else None, "prev": round(prev[1], 4) if prev else None,
                     "chg_1w": round((v / prev[1] - 1) * 100, 2) if prev else None})
    return {"source": source, "date": max((r["date"] for r in rows), default=None), "rows": rows}


def main():
    now = dt.datetime.now(KST)
    today = now.date()
    old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    out = dict(old)
    key = get_key("ECOS_API_KEY")

    # 1) 지수·DXY
    idx = []
    for group, name, cands in INDICES:
        pts, sym = [], None
        for sym in cands:
            pts = series(sym)
            if pts:
                break
        p = perf(pts)
        if p:
            idx.append({"group": group, "name": name, "symbol": sym, **p})
        else:
            prev = next((x for x in old.get("indices", []) if x["name"] == name), None)
            if prev:
                idx.append({**prev, "stale": True})
            print(f"  지수 실패: {name}")
    if idx:
        out["indices"] = idx
        out["indices_source"] = "Yahoo Finance (지연 시세, 종가 기준)"
    dxy = yahoo("DX-Y.NYB", "10y", "1mo")
    if dxy:
        out["dxy_monthly"] = [(d[:7], c) for d, c in dxy if d >= "2019-01"]

    # 2) 환율
    fx, yahoo_ccy = {}, []
    if key:
        try:
            fx = ecos_fx(key, today)
        except Exception as e:  # noqa: BLE001
            print(f"  ECOS 환율 실패: {e}")
    if len(fx) < len(FX):
        for code, _, unit, _, ysym in FX:
            if code in fx:
                continue
            pts = yahoo(ysym, "3mo")
            if not pts and "USD" in fx:  # 원/동 직접 시세가 없으면 USD/동과 원/달러로 교차 계산
                usd = dict(fx["USD"])
                vs = yahoo(f"{code}=X", "3mo")
                pts = [(d, usd[d] / c) for d, c in vs if d in usd and c]
            if pts:
                fx[code] = [(d, c * unit) for d, c in pts]
                yahoo_ccy.append(code)
    if fx:
        src = ("한국은행 ECOS 매매기준율" + (f" (Yahoo Finance: {', '.join(yahoo_ccy)})" if yahoo_ccy else "")
               if len(yahoo_ccy) < len(fx) else "Yahoo Finance")
        out["fx"] = fx_block(fx, src)

    # 3) 정책금리: BIS(키 불필요) 우선, 빠진 나라는 ECOS로 채움
    pol = bis_policy()
    src = ["BIS 중앙은행 정책금리"] if pol else []
    if key and len(pol) < len(POLICY):
        try:
            extra = {k: v for k, v in ecos_policy(key, today).items() if k not in pol}
            if extra:
                pol.update(extra)
                src.append("한국은행 ECOS")
        except Exception as e:  # noqa: BLE001
            print(f"  ECOS 정책금리 실패: {e}")
    if "VN" not in pol:
        pol["VN"] = monthly_from_changes(SBV_CHANGES, today)
        src.append("SBV 공표(수동 이력)")
    if pol:
        pol = {k: pol[k] for k, *_ in POLICY if k in pol}
        out["policy"] = {"source": " · ".join(src) + " (월말 기준)", "series": pol, "table": policy_table(pol)}

    out["updated"] = now.strftime("%Y-%m-%d %H:%M KST")
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved markets.json · 지수 {len(out.get('indices', []))} · 환율 {len(out.get('fx', {}).get('rows', []))}"
          f" · 정책금리 {len(out.get('policy', {}).get('series', {}))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
