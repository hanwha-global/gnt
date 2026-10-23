"""국내 증권사 해외 네트워크 자동 갱신: DART OpenAPI(키 필요, LLM 미사용).

1) 증권사별 최신 정기보고서(사업·반기·분기)를 찾고
2) 주요 재무(자본총계·당기순이익)로 국내 순위를 갱신하고
3) 타법인출자현황에서 해외 직접출자 법인의 지분율·총자산·순이익을 갱신하며
4) 기준 데이터에 없는 해외 법인(펀드·신탁·SPV 제외)을 '신규 후보'로 표시하고
5) 최근 해외 출자 관련 공시를 피드로 모은다.

DART_API_KEY 환경변수가 없으면 아무것도 바꾸지 않고 정상 종료한다.
"""
import io
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from keys import get_key  # noqa: E402
import net  # noqa: E402
from gnd import (auto_new_entity, classify_entity, clean_holding_name, guess_country, is_overseas_name,  # noqa: E402
                 norm_name, tokens)

API = "https://opendart.fss.or.kr/api"
DATA = Path(__file__).resolve().parents[1] / "site" / "data" / "domestic"
CONFIG = Path(__file__).resolve().parents[1] / "site" / "data" / "config.json"
_CFG = json.loads(CONFIG.read_text(encoding="utf-8"))
FIRMS = [f["name"] for f in _CFG["firms"]]  # 대상 회사는 설정 파일 하나로 관리
DART_NAMES = {f["name"]: f.get("dart_name", f["name"]) for f in _CFG["firms"]}
SEED_YEAR = str(_CFG.get("seed_year", 2024))  # 기준 데이터보다 오래된 보고서 값은 쓰지 않는다
REPRT = [("사업보고서", "11011"), ("반기보고서", "11012"), ("분기보고서", None)]
FEED_KEYWORDS = re.compile(r"타법인주식|출자|해외|현지법인|자회사|유상증자|합병|영업양수")


def api(path, key, **params):
    data = net.get_json(f"{API}/{path}", {"crtfc_key": key, **params})
    status = data.get("status")
    if status == "013":  # 조회된 데이터 없음
        return []
    if status != "000":
        raise RuntimeError(f"DART {path} {status}: {data.get('message')}")
    return data.get("list", [])


def corp_codes(key):
    raw = net.get(f"{API}/corpCode.xml", {"crtfc_key": key}, timeout=120)
    xml = zipfile.ZipFile(io.BytesIO(raw)).read("CORPCODE.xml")
    found = {}
    for item in ET.fromstring(xml).iter("list"):
        name = item.findtext("corp_name", "").strip()
        firm = next((f for f in FIRMS if name in (f, DART_NAMES.get(f))), None)
        if firm:
            cur = found.get(firm)
            cand = (item.findtext("stock_code", "").strip() != "", item.findtext("modify_date", ""),
                    item.findtext("corp_code"))
            if cur is None or cand > cur:
                found[firm] = cand
    return {k: v[2] for k, v in found.items()}


def parse_report(report_nm):
    """'반기보고서 (2026.06)' -> (bsns_year, reprt_code, 표시명)."""
    m = re.search(r"(사업|반기|분기)보고서\s*\((\d{4})\.(\d{2})\)", report_nm)
    if not m:
        return None
    kind, year, month = m.group(1), m.group(2), int(m.group(3))
    if kind == "사업":
        return year, "11011", f"{year} 사업보고서"
    if kind == "반기":
        return year, "11012", f"{year} 반기보고서"
    return year, ("11013" if month <= 3 else "11014"), f"{year} {'1' if month <= 3 else '3'}분기보고서"


def latest_reports(key, corp_code, today):
    rows = api("list.json", key, corp_code=corp_code, bgn_de=(today - timedelta(days=500)).strftime("%Y%m%d"),
               end_de=today.strftime("%Y%m%d"), pblntf_ty="A", page_count=100)
    out = []
    for r in rows:  # 최신순
        p = parse_report(r.get("report_nm", ""))
        if p:  # 정정보고서도 같은 기간이면 최신 제출본 하나만 남긴다
            out.append({"bsns_year": p[0], "reprt_code": p[1], "label": p[2],
                        "rcept_no": r["rcept_no"], "rcept_dt": r["rcept_dt"]})
    seen, uniq = set(), []
    for r in out:
        k = (r["bsns_year"], r["reprt_code"])
        if k not in seen:
            seen.add(k)
            uniq.append(r)
    return uniq


def to_num(v):
    if v is None:
        return None
    s = str(v).replace(",", "").strip()
    if s in ("", "-"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    try:
        n = float(s.strip("()"))
    except ValueError:
        return None
    return -n if neg else n


def key_financials(key, corp_code, rep):
    rows = api("fnlttSinglAcnt.json", key, corp_code=corp_code, bsns_year=rep["bsns_year"],
               reprt_code=rep["reprt_code"])
    by_div = {}
    for r in rows:
        by_div.setdefault(r.get("fs_div"), []).append(r)
    picked = by_div.get("CFS") or by_div.get("OFS") or []
    want = {"자산총계": "assets", "부채총계": "liabilities", "자본총계": "equity",
            "영업이익": "op_income", "당기순이익": "net_income"}
    out = {"fs_div": "연결" if by_div.get("CFS") else "별도"}
    for r in picked:
        k = want.get(r.get("account_nm", "").replace(" ", "").split("(")[0])
        if k and k not in out:
            amount = r.get("thstrm_add_amount") if k in ("op_income", "net_income") else None
            v = to_num(amount) if to_num(amount) is not None else to_num(r.get("thstrm_amount"))
            out[k] = round(v / 1e6) if v is not None else None  # 원 -> 백만원
    return out if len(out) > 1 else None


def overseas_holdings(key, corp_code, rep):
    rows = api("otrCprInvstmntSttus.json", key, corp_code=corp_code, bsns_year=rep["bsns_year"],
               reprt_code=rep["reprt_code"])
    out, excluded = [], []
    for r in rows:
        raw = (r.get("inv_prm") or "").replace("\n", " ").strip()
        if not raw or raw in ("합계", "계") or "옵션" in raw:  # 콜·풋옵션 평가분 행은 법인이 아님
            continue
        name = clean_holding_name(raw)
        if not is_overseas_name(name):
            continue
        kind, reason = classify_entity(name)
        mn = lambda v: None if v is None else round(v / 1e6)  # noqa: E731  원 -> 백만원
        item = {
            "name": name, "country_guess": guess_country(name),
            "purpose": r.get("invstmnt_purps"), "first_acquired": r.get("frst_acqs_de"),
            "share_pct": to_num(r.get("trmend_blce_qota_rt")),
            "book_value": mn(to_num(r.get("trmend_blce_acntbk_amount"))),
            "total_assets": mn(to_num(r.get("recent_bsns_year_fnnr_sttus_tot_assets"))),
            "net_income": mn(to_num(r.get("recent_bsns_year_fnnr_sttus_thstrm_ntpf"))),
        }
        (excluded if kind == "제외" else out).append({**item, "exclude_reason": reason} if reason else item)
    return out, excluded


def is_control(h):
    """경영참여 목적의 출자만 자회사·관계사 후보로 본다(단순·일반투자는 제외)."""
    return "경영" in (h.get("purpose") or "")


def match(seeds, name, country=None, control=True):
    """기준 데이터 법인과 같은 법인인지 찾는다.

    0) 표기가 완전히 같은 법인 → 1) 정규화한 이름이 같거나 포함관계 → 2) 구분 토큰이 2개 이상 겹치는 유일한 법인 →
    3) 경영참여 출자이고 같은 나라에 기준 법인이 하나뿐이면 그 법인. 후보가 여럿이면 국가로 좁힌다.
    """
    def narrow(cands):
        if len(cands) > 1 and country:
            same = [s for s in cands if s["country"] == country]
            cands = same or cands
        if len(cands) > 1:
            t = tokens(name)
            best = max(len(t & tokens(s["name"])) for s in cands)
            cands = [s for s in cands if len(t & tokens(s["name"])) == best]
        return cands[0]["name"] if len(cands) == 1 else None

    compact = lambda x: re.sub(r"[^0-9a-z가-힣]+", "", (x or "").lower())  # noqa: E731
    exact = [s for s in seeds if compact(s["name"]) == compact(name)]
    if len(exact) == 1:
        return exact[0]["name"]
    n = norm_name(name)
    by_name = [s for s in seeds if (sn := norm_name(s["name"])) and
               (sn == n or (len(min(sn, n, key=len)) >= 8 and (sn in n or n in sn)))]
    if by_name:
        return narrow(by_name)
    t = tokens(name)
    scored = sorted(((len(t & tokens(s["name"])), i) for i, s in enumerate(seeds)), reverse=True)
    if scored and scored[0][0] >= 2 and (len(scored) == 1 or scored[1][0] < scored[0][0]):
        return seeds[scored[0][1]]["name"]
    same = [s["name"] for s in seeds if control and country and s["country"] == country]
    return same[0] if len(same) == 1 else None


def feed(key, corp_code, firm, today):
    rows = api("list.json", key, corp_code=corp_code, bgn_de=(today - timedelta(days=120)).strftime("%Y%m%d"),
               end_de=today.strftime("%Y%m%d"), page_count=100)
    return [{"firm": firm, "date": r["rcept_dt"], "title": r["report_nm"].strip(),
             "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={r['rcept_no']}"}
            for r in rows if FEED_KEYWORDS.search(r.get("report_nm", ""))]


def run(key, today=None):
    today = today or date.today()
    seed = json.loads((DATA / "seed.json").read_text(encoding="utf-8"))
    seed_by_firm = {}
    for e in seed["entities"]:
        if e.get("name"):
            seed_by_firm.setdefault(e["firm"], []).append(e)

    codes = corp_codes(key)
    result = {"updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "source": "DART OpenAPI (정기보고서 주요재무·타법인출자현황, 공시목록)",
              "firms": {}, "feed": [], "errors": []}
    for firm in FIRMS:
        code = codes.get(firm)
        if not code:
            result["errors"].append(f"{firm}: 고유번호 없음")
            continue
        try:
            reps = latest_reports(key, code, today)
            fresh = [r for r in reps if r["bsns_year"] > SEED_YEAR]
            fin = next(((r, f) for r in fresh if (f := key_financials(key, code, r))), (None, None))
            # 연간 손익 비교용: 가장 최근 사업보고서(같은 회계연도로 전 사 비교)
            ann = next(((r, f) for r in fresh if r["reprt_code"] == "11011"
                        and (f := (fin[1] if r is fin[0] else key_financials(key, code, r)))), (None, None))
            # 타법인출자현황은 사업보고서에만 상세하므로, 최신 보고서 → 최근 사업보고서 순으로 본다
            hold_rep, hold, excl = None, [], []
            for r in sorted(reps, key=lambda r: r["reprt_code"] != "11011"):
                hold, excl = overseas_holdings(key, code, r)
                if hold or excl:
                    hold_rep = r
                    break
            seeds = seed_by_firm.get(firm, [])
            for h in hold:
                h["seed_name"] = match(seeds, h["name"], h["country_guess"], is_control(h))
            result["firms"][firm] = {
                "corp_code": code,
                "financials": fin[1], "financials_report": fin[0],
                "financials_annual": ann[1], "financials_annual_report": ann[0],
                "holdings_report": hold_rep, "overseas_direct": hold, "excluded": excl,
                "new_candidates": [h["name"] for h in hold if not h["seed_name"] and is_control(h)],
            }
            # 새 해외 출자 중 금융업 법인은 바로 네트워크에 반영, 나머지는 사유와 함께 후보로 남긴다
            result["firms"][firm]["new_entities"] = [h["name"] for h in hold if not h["seed_name"] and auto_new_entity(h)[0]]
            result["firms"][firm]["candidate_reasons"] = {h["name"]: auto_new_entity(h)[1] for h in hold
                                                          if not h["seed_name"] and is_control(h) and not auto_new_entity(h)[0]}
            result["feed"] += feed(key, code, firm, today)
        except Exception as e:
            result["errors"].append(f"{firm}: {e}")
    result["feed"].sort(key=lambda r: r["date"], reverse=True)
    return result


def weekly_diff(prev, cur):
    """지난 수집 대비 바뀐 것: 해외법인 증감, 신규 후보, 자기자본 순위, 새 보고서, 새 공시."""
    if not prev or not prev.get("firms"):
        return None
    pf, cf = prev["firms"], cur["firms"]

    def control_names(f):
        return {h["name"] for h in f.get("overseas_direct", []) if is_control(h)}

    def ranks(firms):
        eq = {k: (v.get("financials") or {}).get("equity") for k, v in firms.items()}
        order = sorted((k for k, v in eq.items() if v is not None), key=lambda k: -eq[k])
        return {k: i + 1 for i, k in enumerate(order)}

    out = {"prev_at": prev.get("updated_at"), "entities_added": [], "entities_removed": [],
           "candidates_added": [], "rank_moves": [], "new_reports": [], "new_filings": []}
    for firm, f in cf.items():
        p = pf.get(firm)
        if not p:
            continue
        out["entities_added"] += [{"firm": firm, "name": n} for n in sorted(control_names(f) - control_names(p))]
        out["entities_removed"] += [{"firm": firm, "name": n} for n in sorted(control_names(p) - control_names(f))]
        out["candidates_added"] += [{"firm": firm, "name": n}
                                    for n in f.get("new_candidates", []) if n not in set(p.get("new_candidates", []))]
        new_lbl = (f.get("financials_report") or {}).get("label")
        if new_lbl and new_lbl != (p.get("financials_report") or {}).get("label"):
            out["new_reports"].append({"firm": firm, "label": new_lbl})
    pr, cr = ranks(pf), ranks(cf)
    out["rank_moves"] = [{"firm": k, "from": pr[k], "to": r} for k, r in cr.items() if k in pr and pr[k] != r]
    seen = {r["url"] for r in prev.get("feed", [])}
    out["new_filings"] = [r for r in cur["feed"] if r["url"] not in seen]
    return out


def diff_snapshot(d):
    """weekly_diff가 비교에 쓰는 것만 남긴 지난 주간 수집본(주중 갱신이 주간 비교 기준을 덮지 않게)."""
    if not d or not d.get("firms"):
        return None
    return {"updated_at": d.get("updated_at"), "feed": [{"url": r["url"]} for r in d.get("feed", [])],
            "firms": {k: {"overseas_direct": [{"name": h["name"], "purpose": h.get("purpose")}
                                              for h in f.get("overseas_direct", []) if is_control(h)],
                          "new_candidates": f.get("new_candidates", []),
                          "financials_report": {"label": (f.get("financials_report") or {}).get("label")},
                          "financials": {"equity": (f.get("financials") or {}).get("equity")}}
                      for k, f in d["firms"].items()}}


def main():
    # --midweek: 공시 시즌(filing-season.yml)의 주중 갱신. 주간 변화는 지난 주간 수집 대비로 유지한다
    midweek = "--midweek" in sys.argv[1:]
    key = get_key("DART_API_KEY")
    if not key:
        print("DART_API_KEY 없음: DART 갱신을 건너뜁니다(기존 데이터 유지).")
        return
    out = DATA / "dart_latest.json"
    result = run(key)
    if not result["firms"] and out.exists():
        print("DART 수집 전부 실패: 기존 파일 유지", *result["errors"], sep="\n")
        return
    prev = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
    base = (prev or {}).get("diff_base") or prev
    result["diff"] = weekly_diff(base, result)
    if midweek:
        result["diff_base"] = diff_snapshot(base)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"DART: {len(result['firms'])}개사, 공시 {len(result['feed'])}건", *result["errors"], sep="\n")


if __name__ == "__main__":
    main()
