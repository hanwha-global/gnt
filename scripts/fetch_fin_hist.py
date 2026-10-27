"""국내 증권사 재무 기간별 이력: 정기보고서(사업·반기·분기) 주요계정을 기간마다 모은다(DART fnlttSinglAcnt, LLM 미사용).

한눈에 보기 '국내 증권사 재무 현황'과 글로벌 › 한국 자기자본 순위의 기간 선택(드롭다운)용이다. 기본 화면(최신)은 여전히
dart_latest.json(update_dart.py)을 쓰고, 이 파일은 사용자가 고른 기간의 값을 전 사 같은 보고서로 보여 줄 때만 쓴다.

- 대상: site/data/config.json 의 회사(고유번호는 dart_latest.json에서 읽음). 정기보고서가 없는 회사(토스)는 비어 있다.
- 기간: 최근 YEARS개 사업연도의 1분기·반기·3분기·사업보고서 중 기말이 지난 것.
- 값: 연결(없으면 별도) 자산·부채·자본(기말), 영업이익·당기순이익(그 보고서의 누적, 백만원).
- 저장된 기간은 다시 받지 않는다. 한 번도 묻지 않은 기간(첫 실행·새 회사·지난번 호출 오류)은 받고, 이미 물었는데 비어 있던
  기간(empty)은 기말 후 400일 안에만 다시 확인한다. 최근 RECENT개 기간(정정 공시가 잦은 구간)은 매번 확인한다.

출력: site/data/domestic/fin_hist.json. DART_API_KEY가 없으면 아무것도 바꾸지 않는다.
"""
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from keys import get_key  # noqa: E402
from update_dart import DATA, FIRMS, api, to_num  # noqa: E402

OUT = DATA / "fin_hist.json"
YEARS = 5
RECENT = 2
END = {"11013": (3, 31), "11012": (6, 30), "11014": (9, 30), "11011": (12, 31)}
MONTHS = {"11013": 3, "11012": 6, "11014": 9, "11011": 12}
WANT = {"자산총계": "assets", "부채총계": "liabilities", "자본총계": "equity", "영업이익": "op_income", "당기순이익": "net_income"}


def label(year, code):
    yy = str(year)[2:]
    return {"11011": f"FY{year}", "11012": f"1H{yy}", "11013": f"1Q{yy}", "11014": f"3Q{yy}"}[code]


def periods(today):
    """기말이 지난 기간, 최신 먼저: [{key, year, reprt_code, end}]."""
    out = []
    for y in range(today.year - YEARS + 1, today.year + 1):
        for code, (m, d) in END.items():
            end = date(y, m, d)
            if end < today:
                out.append({"key": f"{y}-{code}", "year": str(y), "reprt_code": code, "end": end})
    return sorted(out, key=lambda p: p["end"], reverse=True)


def financials(rows):
    """fnlttSinglAcnt 행 → 연결(없으면 별도) 주요계정(백만원). 손익은 누적(thstrm_add_amount)이 있으면 그 값."""
    by_div = {}
    for r in rows:
        by_div.setdefault(r.get("fs_div"), []).append(r)
    picked = by_div.get("CFS") or by_div.get("OFS") or []
    out = {"fs_div": "연결" if by_div.get("CFS") else "별도"}
    for r in picked:
        k = WANT.get(r.get("account_nm", "").replace(" ", "").split("(")[0])
        if k and k not in out:
            add = to_num(r.get("thstrm_add_amount")) if k in ("op_income", "net_income") else None
            v = add if add is not None else to_num(r.get("thstrm_amount"))
            out[k] = round(v / 1e6) if v is not None else None
    if picked:
        out["rcept_no"] = picked[0].get("rcept_no")
    return out if out.get("equity") is not None else None


def needs(per, have, idx, today, tried=False):
    """have: 저장된 값, tried: 전에 물었는데 비어 있던 기간인지."""
    if idx < RECENT:
        return True
    if have is not None:
        return False
    if not tried:
        return True
    return (today - per["end"]).days < 400


def collect(key, prev, today):
    dart = json.loads((DATA / "dart_latest.json").read_text(encoding="utf-8"))
    pers = periods(today)
    keys = {p["key"] for p in pers}
    firms, empty, errors, calls = {}, {}, [], 0
    for firm in FIRMS:
        code = dart.get("firms", {}).get(firm, {}).get("corp_code")
        old = prev.get("firms", {}).get(firm, {})
        cur = firms[firm] = {p["key"]: old[p["key"]] for p in pers if p["key"] in old}
        none = empty[firm] = set(prev.get("empty", {}).get(firm, [])) & keys
        if not code:
            continue
        for i, p in enumerate(pers):
            if not needs(p, cur.get(p["key"]), i, today, p["key"] in none):
                continue
            try:
                got = financials(api("fnlttSinglAcnt.json", key, corp_code=code, bsns_year=p["year"], reprt_code=p["reprt_code"]))
                calls += 1
            except Exception as e:  # 한 기간 실패는 이전 값을 두고 넘어간다(묻지 않은 것으로 남아 다음 실행에서 다시 받음)
                errors.append(f"{firm} {label(p['year'], p['reprt_code'])}: {e}")
                continue
            if got:
                cur[p["key"]] = got
                none.discard(p["key"])
            elif p["key"] not in cur:
                none.add(p["key"])
    return pers, firms, empty, errors, calls


def build(pers, firms, errors, empty=None):
    rows = []
    for p in pers:
        n = sum(1 for f in firms.values() if p["key"] in f)
        if n:
            rows.append({"key": p["key"], "year": p["year"], "reprt_code": p["reprt_code"], "label": label(p["year"], p["reprt_code"]),
                         "bs": f"{p['year'][2:]}.{p['end'].month}말", "months": MONTHS[p["reprt_code"]], "end": p["end"].isoformat(), "n": n})
    return {"updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": "DART 정기보고서 주요계정(fnlttSinglAcnt), 연결 우선", "unit": "백만원",
            "periods": rows, "firms": {f: v for f, v in firms.items() if v},
            "empty": {f: sorted(v) for f, v in (empty or {}).items() if v}, "errors": errors}


def main():
    key = get_key("DART_API_KEY")
    if not key:
        print("DART_API_KEY 없음: fin_hist.json 갱신 건너뜀")
        return 0
    prev = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    today = date.today()
    pers, firms, empty, errors, calls = collect(key, prev, today)
    out = build(pers, firms, errors, empty)
    if not out["periods"] and prev.get("periods"):
        print("받은 기간이 없어 이전 파일 유지")
        return 0
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{OUT.name}: 호출 {calls}건 · 기간 " + ", ".join(f"{p['label']}({p['n']})" for p in out["periods"]) + f" · 오류 {len(errors)}건")
    for e in errors[:10]:
        print("  !", e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
