"""해외 시장(일본·베트남·싱가포르·인도네시아) 상장 증권사 자기자본·순이익 순위를 자동 수집한다(키·LLM 불필요).

1) Yahoo Finance 재무 시계열(연간 자본총계·순이익)  2) 실패하면 stockanalysis.com 재무상태표 페이지
두 곳 모두 실패한 회사는 이전 값을 유지하고 stale=True로 표시한다. 단위는 시장별 표시 단위로 맞춘다.
결과: site/data/global/listed.json. 아부다비는 상장 증권사가 없어 대상이 아니다(화면에 수동 표시).
"""
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import net  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "site" / "data" / "global" / "listed.json"

# 시장: (표시 단위, 원 통화 → 표시 단위 나눗수, Yahoo 접미사, stockanalysis 거래소, [(이름, 티커, 비고)])
MARKETS = {
    "jp": ("십억엔", 1e9, ".T", "tyo", [
        ("Nomura Holdings", "8604", ""), ("SBI Holdings", "8473", ""), ("Daiwa Securities Group", "8601", ""),
        ("Okasan Securities Group", "8609", ""), ("Tokai Tokyo Financial", "8616", ""), ("Monex Group", "8698", "온라인"),
        ("Matsui Securities", "8628", "온라인"), ("IwaiCosmo Holdings", "8707", ""), ("GMO Financial Holdings", "7177", "온라인"),
        ("Ichiyoshi Securities", "8624", ""), ("Marusan Securities", "8613", ""), ("Aizawa Securities Group", "8708", "")]),
    "vn": ("조동", 1e12, ".VN", "hose", [
        ("Techcombank Securities (TCBS)", "TCX", ""), ("VPBank Securities", "VPX", ""), ("SSI Securities", "SSI", ""),
        ("VPS Securities", "VCK", ""), ("VIX Securities", "VIX", ""), ("VNDirect", "VND", ""), ("Vietcap Securities", "VCI", ""),
        ("HSC Securities", "HCM", ""), ("BIDV Securities", "BSI", ""), ("FPT Securities", "FTS", ""),
        ("VietinBank Securities", "CTS", ""), ("SaiGon-Hanoi Securities", "SHS", "HNX"), ("MB Securities", "MBS", "HNX")]),
    "sg": ("백만 S$", 1e6, ".SI", "sgx", [
        ("UOB-Kay Hian Holdings", "U10", ""), ("iFAST Corporation", "AIY", "온라인 플랫폼")]),
    "id": ("십억 루피아", 1e9, ".JK", "idx", [
        ("Trimegah Sekuritas", "TRIM", ""), ("Panin Sekuritas", "PANS", ""), ("Yulie Sekuritas", "YULE", ""),
        ("Reliance Sekuritas", "RELI", ""), ("Minna Padi Investama Sekuritas", "PADI", "")]),
}
SA_EXCHANGE = {"HNX": "hnx"}


def yahoo(symbol):
    """연간 자본총계·순이익의 최신 값 → (equity, ni, fy_end, url). 원 통화 단위."""
    now = int(time.time())
    url = (f"https://query2.finance.yahoo.com/ws/fundamentals-timeseries/v1/finance/timeseries/{symbol}"
           f"?type=annualStockholdersEquity,annualNetIncome&period1={now - 4 * 365 * 86400}&period2={now}")
    data = net.get_json(url)
    out = {}
    for r in data.get("timeseries", {}).get("result", []):
        t = (r.get("meta", {}).get("type") or [None])[0]
        pts = [p for p in (r.get(t) or []) if p and p.get("reportedValue")]
        if pts:
            last = max(pts, key=lambda p: p["asOfDate"])
            out[t] = (last["reportedValue"]["raw"], last["asOfDate"])
    if "annualStockholdersEquity" not in out:
        raise RuntimeError("Yahoo: 자본총계 없음")
    eq, d = out["annualStockholdersEquity"]
    ni = out.get("annualNetIncome", (None, None))[0]
    return eq, ni, d, f"https://finance.yahoo.com/quote/{symbol}/balance-sheet"


SA_SCALE = {"thousands": 1e3, "millions": 1e6, "billions": 1e9}


def stockanalysis(exchange, ticker):
    """재무상태표·손익계산서 페이지의 표에서 최신 연간 값을 읽는다. 원 통화 단위."""
    def page(kind):
        url = f"https://stockanalysis.com/quote/{exchange}/{ticker}/financials/" + (f"{kind}/" if kind else "")
        return url, net.get(url, timeout=30).decode("utf-8", "replace")

    def row(html, *labels):
        for lab in labels:
            m = re.search(r">\s*" + re.escape(lab) + r"\s*<.*?</tr>", html, flags=re.S)
            if m:
                cells = re.findall(r"<td[^>]*>\s*([-\d.,()]+)\s*<", m.group(0))
                for c in cells:
                    v = c.replace(",", "")
                    neg = v.startswith("(") or v.startswith("-")
                    try:
                        return -float(v.strip("()-")) if neg else float(v.strip("()-"))
                    except ValueError:
                        continue
        return None

    url, bs = page("balance-sheet")
    sm = re.search(r"in (thousands|millions|billions)", bs, flags=re.I)
    scale = SA_SCALE.get(sm.group(1).lower(), 1e6) if sm else 1e6
    eq = row(bs, "Shareholders' Equity", "Total Shareholders' Equity", "Shareholders&#39; Equity", "Total Equity")
    if eq is None:
        raise RuntimeError("stockanalysis: 자본 행 없음")
    fy = re.search(r"FY ?(\d{4})", bs)
    _, inc = page("")
    ni = row(inc, "Net Income", "Net Income to Common")
    return eq * scale, (None if ni is None else ni * scale), (fy.group(0).replace(" ", "") if fy else ""), url


def main():
    prev = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"markets": {}}
    result = {"updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "source": "Yahoo Finance 재무 시계열 · stockanalysis.com(각 사 공시 기반)", "markets": {}, "errors": []}
    for mid, (unit, div, ysfx, sa_ex, firms) in MARKETS.items():
        old = {r["ticker"]: r for r in prev.get("markets", {}).get(mid, {}).get("rows", [])}
        rows = []
        for name, ticker, note in firms:
            got, errs = None, []
            for how in ("yahoo", "sa"):
                try:
                    if how == "yahoo":
                        eq, ni, asof, url = yahoo(ticker + (".HN" if note == "HNX" else ysfx))
                    else:
                        eq, ni, asof, url = stockanalysis(SA_EXCHANGE.get(note, sa_ex), ticker)
                    got = {"name": name, "ticker": ticker, "note": note, "equity": round(eq / div, 2),
                           "ni": None if ni is None else round(ni / div, 2), "asof": asof, "url": url, "via": how,
                           "checked": result["updated_at"][:10], "stale": False}
                    break
                except Exception as e:
                    errs.append(f"{how}: {e}"[:120])
            if got:
                rows.append(got)
            elif ticker in old:
                rows.append({**old[ticker], "stale": True})
                result["errors"].append(f"{mid} {ticker}: 이전 값 유지 ({'; '.join(errs)})")
            else:
                result["errors"].append(f"{mid} {ticker}: {'; '.join(errs)}")
        rows.sort(key=lambda r: -(r["equity"] or 0))
        result["markets"][mid] = {"unit": unit, "rows": rows}
        print(f"{mid}: {sum(not r['stale'] for r in rows)}/{len(firms)} 수집")
    for e in result["errors"]:
        print("  !", e)
    if not any(m["rows"] for m in result["markets"].values()):
        print("수집 결과 없음: 이전 파일 유지")
        return 0
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
