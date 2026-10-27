"""국내 전체 증권사 자기자본·자본금 순위(DART 주요계정, LLM 미사용).

DART 고유번호 목록에서 이름이 '증권'(또는 '금융투자')으로 끝나는 회사를 고르고, 각 회사의
정기보고서 주요계정(fnlttSinglAcnt)에서 자본총계(연결·별도)와 자본금을 읽는다.
정기보고서를 내지 않는 회사(감사보고서만 제출)와 외국계 지점은 DART 주요계정에 없어 빠진다.

기간은 제출 기한(분기·반기 45일, 사업 90일)이 지난 최근 기간을 쓴다. 기한 전에는 일부 회사만
제출해 순위가 흔들리므로 쓰지 않는다. 결산월이 달라 기말일이 다른 회사(3월 결산 등)는 같은 표에
섞지 않는다.

    python scripts/broker_rank.py                      # 최신 기간을 골라 broker_rank.json 저장
    python scripts/broker_rank.py --period 2026 11012  # 기간 지정(11011 사업·11012 반기·11013 1분기·11014 3분기)
    python scripts/broker_rank.py --print-only         # 파일은 쓰지 않고 순위만 출력

지난 기간 순위(글로벌 › 한국 표의 기간 선택)는 broker_rank_hist.json에 쌓는다. 최신 순위에 든 회사만 지난 기간을 받고,
이미 받은 기간은 다시 받지 않는다(최신 기간은 매번 새 결과로 바꾼다).

DART_API_KEY 환경변수가 없으면 아무것도 바꾸지 않고 정상 종료한다.
"""
import io
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from keys import get_key  # noqa: E402
import net  # noqa: E402

API = "https://opendart.fss.or.kr/api"
OUT = Path(__file__).resolve().parents[1] / "site" / "data" / "domestic" / "broker_rank.json"
HIST = OUT.with_name("broker_rank_hist.json")
HIST_YEARS = 4  # 올해 포함 최근 4개 사업연도의 분기·반기·사업보고서
NAME = re.compile(r"(증권|금융투자)$")
NOT_BROKER = re.compile(r"증권금융|예탁|거래소|전산|협회|자산운용|투자자문|선물|저축|보험|캐피탈|신탁|홀딩스|지주")
LABEL = {"11011": "사업보고서", "11012": "반기보고서", "11013": "1분기보고서", "11014": "3분기보고서"}
# 기말(월, 일)과 제출 기한(기말 후 일수)
END = {"11011": (12, 31, 90), "11014": (9, 30, 45), "11012": (6, 30, 45), "11013": (3, 31, 45)}
# DART 정식 한글 이름 → 화면 이름(대시보드 다른 표와 같게)
DISPLAY = {"케이비증권": "KB증권", "아이비케이투자증권": "IBK투자증권", "아이엠증권": "iM증권"}
HOME = "한화투자증권"
MIN_ROWS = 20  # 대형사가 대부분 들어 있는 기간만 쓴다


def api(path, key, **params):
    data = net.get_json(f"{API}/{path}", {"crtfc_key": key, **params})
    status = data.get("status")
    if status == "013":  # 조회된 데이터 없음
        return []
    if status != "000":
        raise RuntimeError(f"DART {path} {status}: {data.get('message')}")
    return data.get("list", [])


def brokers(key):
    """이름으로 고른 증권사 후보: {corp_code: (이름, 종목코드)}."""
    raw = net.get(f"{API}/corpCode.xml", {"crtfc_key": key}, timeout=120)
    xml = zipfile.ZipFile(io.BytesIO(raw)).read("CORPCODE.xml")
    out = {}
    for item in ET.fromstring(xml).iter("list"):
        name = item.findtext("corp_name", "").strip()
        if NAME.search(name) and not NOT_BROKER.search(name):
            out[item.findtext("corp_code")] = (name, item.findtext("stock_code", "").strip())
    return out


def to_num(v):
    s = str(v or "").replace(",", "").strip()
    if s in ("", "-"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    try:
        n = float(s.strip("()"))
    except ValueError:
        return None
    return -n if neg else n


def pick(rows):
    """주요계정 행 → 자본총계·자본금(연결 cfs, 별도 ofs, 백만원)과 기말일(as_of)."""
    want = {"자본총계": "equity", "자본금": "capital"}
    out = {}
    for r in rows:
        k = want.get(re.sub(r"\s|\(.*", "", r.get("account_nm", "")))
        div = {"CFS": "cfs", "OFS": "ofs"}.get(r.get("fs_div"))
        v = to_num(r.get("thstrm_amount"))
        if k and div and v is not None and f"{k}_{div}" not in out:
            out[f"{k}_{div}"] = round(v / 1e6)
            d = re.search(r"(\d{4})\.(\d{2})\.(\d{2})", r.get("thstrm_dt", ""))
            if d and "as_of" not in out:
                out["as_of"] = "-".join(d.groups())
    return out


def periods(today, years=3, limit=2):
    """제출 기한이 지난 기간을 기말이 최근인 것부터: [(연도, 보고서 코드, 기말일)]."""
    out = []
    for y in range(today.year, today.year - years, -1):
        for code, (m, d, days) in END.items():
            end = date(y, m, d)
            if end + timedelta(days=days + 2) <= today:  # 기한 다음 영업일쯤 DART에 다 올라온다
                out.append((str(y), code, end))
    return sorted(out, key=lambda p: p[2], reverse=True)[:limit]


def collect(key, period=None, today=None, cands=None, min_rows=None):
    cands = cands or brokers(key)
    if period:
        m, d, _ = END[period[1]]
        tries = [(period[0], period[1], date(int(period[0]), m, d))]
    else:
        tries = periods(today or date.today())
    for year, code, end in tries:
        rows, errors, other = [], [], []
        for corp, (name, stock) in sorted(cands.items(), key=lambda kv: kv[1][0]):
            try:
                got = pick(api("fnlttSinglAcnt.json", key, corp_code=corp, bsns_year=year, reprt_code=code))
            except Exception as e:  # 한 회사 실패가 전체를 막지 않게
                errors.append(f"{name}: {e}")
                continue
            if got.get("equity_cfs") is None and got.get("equity_ofs") is None:
                continue
            if got.get("as_of") and got["as_of"] != end.isoformat():  # 결산월이 다른 회사
                other.append(f"{name}({got['as_of']})")
                continue
            got.pop("as_of", None)
            rows.append({"name": DISPLAY.get(name, name), "dart_name": name, "corp_code": corp, "listed": bool(stock), **got})
        if len(rows) >= (min_rows or MIN_ROWS):
            return {"period": f"{year} {LABEL[code]}", "as_of": end.isoformat(), "bsns_year": year, "reprt_code": code,
                    "candidates": len(cands), "rows": rows, "other_fiscal": other, "errors": errors}
    return None


def slim(res):
    return {k: res[k] for k in ("period", "as_of", "bsns_year", "reprt_code", "rows")}


def history(key, res, today=None):
    """broker_rank_hist.json: 기간별 순위 행. 최신 결과는 그대로 넣고, 빈 지난 기간은 최신 순위에 든 회사만 받는다."""
    today = today or date.today()
    hist = json.loads(HIST.read_text(encoding="utf-8")) if HIST.exists() else {"periods": []}
    have = {(p["bsns_year"], p["reprt_code"]): p for p in hist.get("periods", [])}
    have[(res["bsns_year"], res["reprt_code"])] = slim(res)
    cands = {r["corp_code"]: (r["dart_name"], "1" if r.get("listed") else "") for r in res["rows"]}
    for year, code, _ in periods(today, years=HIST_YEARS, limit=99):
        if (year, code) in have:
            continue
        got = collect(key, (year, code), cands=cands, min_rows=max(10, len(cands) // 2))
        # 호출 오류가 있었거나 당사 행이 빠진 기간은 저장하지 않는다(저장한 기간은 다시 받지 않으므로 다음 실행에서 다시 받게)
        if got and not got["errors"] and any(r["name"] == HOME for r in got["rows"]):
            have[(year, code)] = slim(got)
            print(f"지난 기간 {got['period']}: {len(got['rows'])}곳")
        else:
            print(f"지난 기간 {year} {LABEL[code]}: " + (f"오류 {len(got['errors'])}건, 다음 실행에서 다시 받음" if got else "읽은 회사가 적어 건너뜀"))
    keep = {(y, c) for y, c, _ in periods(today, years=HIST_YEARS, limit=99)} | {(res["bsns_year"], res["reprt_code"])}
    rows = sorted((p for k, p in have.items() if k in keep), key=lambda p: p["as_of"], reverse=True)
    HIST.write_text(json.dumps({"updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                "note": "최신 기간 순위에 든 회사 기준, 별도·연결 자본총계와 자본금(백만원)",
                                "periods": rows}, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")
    print(f"저장: {HIST} ({len(rows)}개 기간)")


def equity(r):
    return r.get("equity_cfs") if r.get("equity_cfs") is not None else r.get("equity_ofs")


def ranked(rows, key):
    xs = [r for r in rows if key(r) is not None]
    return sorted(xs, key=lambda r: -key(r))


def table(title, rows, key, home):
    lines = [f"== {title} ({len(ranked(rows, key))}개사)"]
    for i, r in enumerate(ranked(rows, key), 1):
        mark = " ◀" if r["name"] == home else ""
        lines.append(f"{i:>3}. {r['name']:<14} {key(r) / 1e6:>8.2f}조{mark}")
    return "\n".join(lines)


def main():
    key = get_key("DART_API_KEY")
    if not key:
        print("DART_API_KEY 없음: 건너뜀")
        return
    args = sys.argv[1:]
    period = None
    if "--period" in args:
        i = args.index("--period")
        period = (args[i + 1], args[i + 2])
    res = collect(key, period)
    if not res:
        print(f"주요계정을 읽은 증권사가 {MIN_ROWS}곳 미만: 저장하지 않음")
        return
    home = HOME
    rows = res["rows"]
    print(f"기준: {res['period']}({res['as_of']}) · 후보 {res['candidates']}곳 중 {len(rows)}곳 · 오류 {len(res['errors'])}건")
    print(table("자기자본(별도)", rows, lambda r: r.get("equity_ofs"), home))
    print(table("자기자본(연결, 없으면 별도)", rows, equity, home))
    print(table("자본금(별도)", rows, lambda r: r.get("capital_ofs") if r.get("capital_ofs") is not None else r.get("capital_cfs"), home))
    if res["other_fiscal"]:
        print("결산월이 달라 뺀 회사:", ", ".join(res["other_fiscal"]))
    for e in res["errors"][:20]:
        print("오류:", e)
    if "--print-only" in args:
        return
    res["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    OUT.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"저장: {OUT}")
    if not period:  # 기간을 지정한 수동 실행은 이력에 넣지 않는다
        history(key, res)


if __name__ == "__main__":
    main()
