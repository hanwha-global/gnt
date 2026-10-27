"""해외법인 5개년 손익 추이: 해마다의 사업보고서(토스는 감사보고서)와 최근 반기보고서 원문의 '종속기업 요약재무정보'에서
법인별 영업수익·순이익을 모은다(DART, LLM 미사용).

- 법인: 사이트 법인 집계와 같은 목록(금융업 영업법인·중간지주, 손자회사 포함, fetch_sub_fin.seeds_by_firm)과
  관계사·지분투자 참고 행(관계기업 요약재무정보에 실린 것만, 법인 수·ROE에는 넣지 않음)
- 기간: 최근 사업연도 5개(FY) + 그 뒤 반기(1H, 같은 표를 반기보고서에도 싣는 회사만)
- 보고서마다 접수번호와 원문 표 값을 sub_trend_raw.json에 저장해 새 보고서·정정본만 원문을 받는다. 그래서 공시 시즌
  (3·4·8월) 매일 돌려도 목록 조회 몇 번이면 끝난다. 표 읽는 규칙을 바꾸면 PARSER를 올려 저장분을 모두 다시 받는다(다시 받기 전까지는 예전 값 유지).
- 새 보고서를 받았거나 ROE(sub_fin.json)가 아직 최신 사업보고서를 반영하지 못했으면 GITHUB_OUTPUT에 new_reports=true를
  남긴다(filing-season.yml이 법인 목록·ROE 수집을 다시 돌리는 신호. 그날 실패해도 다음 날 다시 돈다).

출력: site/data/domestic/sub_trend.json(화면용), sub_trend_raw.json(보고서별 표 값)
사용: python scripts/fetch_sub_trend.py            # DART 확인·수집 후 화면용 파일 생성
      python scripts/fetch_sub_trend.py --rebuild  # 원문을 다시 받지 않고 저장된 표로 화면용 파일만 다시 만든다(키 불필요)
"""
import json
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from keys import get_key  # noqa: E402
import net  # noqa: E402
from fetch_sub_fin import (API, DATA, attach_parents, document_texts, find_entity, mark_consolidated, parse_doc,  # noqa: E402
                           parse_parents, pick, seeds_by_firm, summarize)
from gnd import tokens  # noqa: E402
from update_dart import parse_report  # noqa: E402

OUT = DATA / "sub_trend.json"
RAW = DATA / "sub_trend_raw.json"
YEARS = 5
ASSOC = r"관계기업|공동기업"
PARSER = 2  # parse_doc 규칙 버전(2: 반기보고서 '당반기' 표, 순영업손익). 바뀌면 저장된 보고서를 모두 다시 읽는다


def listing(key, corp_code, ty, today):
    """회사의 최근 YEARS+1년 공시 목록(정정 전 원본 포함, 최신순)."""
    rows = []
    for page in (1, 2, 3):
        data = net.get_json(f"{API}/list.json", {"crtfc_key": key, "corp_code": corp_code, "pblntf_ty": ty,
                                                 "bgn_de": f"{today.year - YEARS - 1}0101", "end_de": today.strftime("%Y%m%d"),
                                                 "page_no": page, "page_count": 100})
        if data.get("status") not in ("000", "013"):
            raise RuntimeError(f"DART list.json {data.get('status')}: {data.get('message')}")
        rows += data.get("list") or []
        if len(data.get("list") or []) < 100:
            break
    return sorted(rows, key=lambda r: (r.get("rcept_dt", ""), r.get("rcept_no", "")), reverse=True)


def periods_of(rows, audit=False):
    """공시 목록 → {'FY2025'|'1H2026': {rcept_no(최신 제출본), label, rcept_dt, first_dt(처음 제출일)}}."""
    out = {}
    for r in rows:
        nm = r.get("report_nm", "")
        if audit:  # 사업보고서를 내지 않는 회사: 연결감사보고서를 먼저, 없으면 감사보고서
            m = re.search(r"감사보고서\s*\((\d{4})\.12\)", nm)
            if not m:
                continue
            per, label = f"FY{m.group(1)}", f"{m.group(1)} 감사보고서"
            rank = 1 if "연결" in nm else 0
        else:
            p = parse_report(nm)
            if not p or p[1] not in ("11011", "11012"):
                continue
            per, label, rank = ("FY" if p[1] == "11011" else "1H") + p[0], p[2], 0
        cur = out.get(per)
        if cur is None or rank > cur["rank"]:
            out[per] = {"rcept_no": r["rcept_no"], "label": label, "rcept_dt": r["rcept_dt"], "first_dt": r["rcept_dt"], "rank": rank}
        elif rank == cur["rank"]:
            cur["first_dt"] = min(cur["first_dt"], r["rcept_dt"])
    return {k: {x: v for x, v in rep.items() if x != "rank"} for k, rep in out.items()}


def window(pers, base=None):
    """최근 사업연도 5개 + 그보다 뒤인 반기 하나(시간순). base를 주면 그 사업연도보다 뒤인 반기를 남긴다."""
    fy = sorted((p for p in pers if p.startswith("FY")), reverse=True)[:YEARS]
    base = base or (fy[0] if fy else None)
    h1 = sorted(p for p in pers if p.startswith("1H") and base and int(p[2:]) > int(base[2:]))[-1:]
    return sorted(fy + h1, key=lambda p: (p[2:], p[:2] == "FY"))


def page_periods(raw):
    """화면 열: 전 사 최근 사업연도 5개 + 반기. 3월처럼 일부 회사만 새 사업보고서를 낸 동안에는 아직 안 낸 회사의
    최근 반기를 남긴다(예: FY2022~FY2026과 1H2026)."""
    latest = [max(p for p in st if p.startswith("FY")) for st in raw["firms"].values() if any(p.startswith("FY") for p in st)]
    return window({p for st in raw["firms"].values() for p in st}, base=min(latest) if latest else None)


def renamed(rows, picked, seeds):
    """이름이 바뀐 법인(예: Shinhan Investment America → Shinhan Securities America): 그 해 짝이 없는 기준 법인과
    짝이 없는 행의 구분 단어(브랜드·지명, Securities·Investment 같은 일반어 제외)가 같고 서로 하나뿐이면 같은 법인으로 본다."""
    key = lambda n: frozenset({"brazil" if t == "brasil" else t for t in tokens(n)} - {"wealth", "management", "ltda"})  # noqa: E731
    free = [n for n, r in rows.items() if not r.get("seed_name")]
    for e in seeds:
        if e["name"] in picked:
            continue
        k = key(e["name"])
        hits = [n for n in free if key(n) == k]
        rivals = [x for x in seeds if x["name"] not in picked and key(x["name"]) == k]
        if len(k) >= 2 and len(hits) == 1 and len(rivals) == 1:
            picked[e["name"]] = rows[hits[0]]
            rows[hits[0]]["seed_name"] = e["name"]
            free.remove(hits[0])
    return picked


def slim(rows):
    keep = ("rev", "rev_net", "ni", "equity", "parent", "own", "consolidated")
    return {n: {k: v[k] for k in keep if v.get(k) is not None} for n, v in rows.items()}


def collect(key, raw, today):
    """새 보고서(접수번호가 바뀐 정정본 포함)만 원문을 받아 raw를 고친다. 받은 보고서 목록을 돌려준다."""
    dart = json.loads((DATA / "dart_latest.json").read_text(encoding="utf-8"))
    new, errors, wants = [], [], {}
    for firm, d in dart.get("firms", {}).items():
        if not d.get("corp_code"):
            continue
        try:
            pers = periods_of(listing(key, d["corp_code"], "A", today))
            if not any(p.startswith("FY") for p in pers):
                pers = periods_of(listing(key, d["corp_code"], "F", today), audit=True)
        except Exception as e:  # 한 회사가 실패해도 나머지는 계속
            errors.append(f"{firm}: {e}")
            continue
        store = raw["firms"].setdefault(firm, {})
        want = wants[firm] = window(pers)
        for per in want:
            rep = pers[per]
            # 같은 보고서라도 표 읽는 규칙(PARSER)이 바뀌었으면 다시 받는다. 받기 전까지는 예전 값을 둔다
            if store.get(per, {}).get("rcept_no") == rep["rcept_no"] and store[per].get("parser", raw.get("parser")) == PARSER:
                store[per].update(first_dt=rep["first_dt"])
                continue
            try:
                texts = document_texts(key, rep["rcept_no"])
                subs = mark_consolidated(attach_parents(parse_doc(texts), parse_parents(texts)), texts)
                assoc = parse_doc(texts, marker=ASSOC)
            except Exception as e:
                errors.append(f"{firm} {per}: {e}")
                continue
            fresh = store.get(per, {}).get("rcept_no") != rep["rcept_no"]
            store[per] = {**rep, "parser": PARSER, "subs": slim(subs), "assoc": slim({n: v for n, v in assoc.items() if n not in subs})}
            if fresh:
                new.append(f"{firm} {rep['label']}")
            print(f"{firm} {rep['label']}: 해외 종속기업 {len(subs)}개, 관계기업 {len(assoc)}개")
    # 기간 밖 보고서는 지우되, 화면에 아직 보이는 반기는 둔다(3월에 새 사업보고서를 낸 회사도 1H 열이 남아 있는 동안 값이 보이게)
    page = set(page_periods(raw))
    for firm, want in wants.items():
        store = raw["firms"][firm]
        for per in [p for p in store if p not in want and p not in page]:
            del store[per]
    return new, errors


def ref_seeds():
    """관계사·지분투자 참고 행(엑셀 양식의 하나증권 BIDV·Wedbush 등). 법인 수·ROE에는 넣지 않는다."""
    seed = json.loads((DATA / "seed.json").read_text(encoding="utf-8"))
    out = {}
    for e in seed["entities"]:
        if e.get("name") and e["kind"] == "법인" and e["status"] == "운영" and e["relation"] in ("관계사", "지분투자"):
            out.setdefault(e["firm"], []).append(e)
    return out


def norm_date(s):
    """'1998년 10월 01일', '2019-11-01', '2008.1.2' → 'YYYY.MM.DD'(일·월이 없으면 있는 데까지). 연도가 없으면 그대로."""
    nums = re.findall(r"\d+", s or "")
    if not nums or len(nums[0]) != 4:
        return s or None
    return ".".join([nums[0], *(n.zfill(2) for n in nums[1:3])])


def entity_meta():
    """업종·설립일: 종속회사 전수 목록(consolidated.json) → 기준 데이터(seed.json) 순."""
    meta = {}
    seed = json.loads((DATA / "seed.json").read_text(encoding="utf-8"))
    for e in seed["entities"]:
        if e.get("name"):
            meta[(e["firm"], e["name"])] = {"business": e.get("business"), "established": e.get("established")}
    cons_path = DATA / "consolidated.json"
    if cons_path.exists():
        for firm, c in json.loads(cons_path.read_text(encoding="utf-8")).get("firms", {}).items():
            for x in c.get("overseas", []):
                m = meta.setdefault((firm, x.get("seed_name") or x["name"]), {})
                m["business"] = x.get("business") or m.get("business")
                m["established"] = x.get("established") or m.get("established")
                m["holding"] = x.get("class") == "지주회사"
    return meta


def period_roe(rows, seeds, per):
    """그 보고서의 가중평균 ROE(국내 탭 기간 선택용). sub_fin.json과 같은 규칙(fetch_sub_fin.summarize: 사이트 네트워크 법인만,
    중간지주의 자회사 몫 제외)을 그 기간 표에 적용하고, 반기는 순이익을 연환산(× 2)한다. 법인 목록은 현재 네트워크 기준."""
    rows = {n: dict(v) for n, v in rows.items() if v.get("equity") is not None and v.get("ni") is not None}
    r = summarize(rows, seeds) if rows else None
    if not r or not r["n"]:
        return None
    months = 6 if per.startswith("1H") else 12
    r["months"] = months
    r["roe"] = round(r["ni"] * 12 / months / r["equity"] * 100, 2) if r["equity"] > 0 else None
    return r


def build(raw):
    seeds, refs, meta = seeds_by_firm(), ref_seeds(), entity_meta()
    pers = page_periods(raw)
    firms, filing = {}, {}
    for firm, store in raw["firms"].items():
        ents, order, rev_net = {}, [], False
        for per in pers:
            rep = store.get(per)
            if not rep:
                continue
            f = filing.setdefault(per, {"label": rep["label"], "first": rep["first_dt"], "last": rep["first_dt"], "n": 0})
            f.update(first=min(f["first"], rep["first_dt"]), last=max(f["last"], rep["first_dt"]), n=f["n"] + 1)
            for kind, rows, sd in (("sub", rep["subs"], seeds.get(firm, [])), ("ref", rep.get("assoc", {}), refs.get(firm, []))):
                rows = {n: dict(v) for n, v in rows.items()}
                for seed_name, s in renamed(rows, pick(rows, sd), sd).items():
                    if seed_name not in ents:
                        ents[seed_name] = {"name": seed_name, "country": next((e.get("country") for e in sd if e["name"] == seed_name), None),
                                           "ref": kind == "ref", "values": {}}
                        order.append(seed_name)
                    e = ents[seed_name]
                    e["values"][per] = {"rev": s.get("rev"), "ni": s.get("ni")}
                    rev_net |= bool(s.get("rev_net"))
                    if per.startswith("FY"):  # 지배 구조는 가장 최근 사업연도 표 기준
                        e.update(parent=s.get("parent"), own=s.get("own"), consolidated=bool(s.get("consolidated")))
        # 중간지주: 다른 해외 법인의 모회사인 법인(모회사 이름은 표마다 표기가 조금씩 달라 정규화해 찾는다)
        subs = [x["name"] for x in ents.values() if not x["ref"]]
        for e in ents.values():
            hit = find_entity(e["parent"], subs) if e.get("parent") and not e["ref"] else None
            if hit and hit != e["name"]:
                e["parent_entity"] = hit
                ents[hit]["children"] = ents[hit].get("children", 0) + 1
        out = []
        for name in order:
            e = ents[name]
            m = meta.get((firm, name), {})
            e.update(business=m.get("business"), established=norm_date(m.get("established")),
                     holding=bool(m.get("holding") or e.get("children")))
            out.append(e)
        audit = bool(store) and all(r["label"].endswith("감사보고서") for r in store.values())  # 반기보고서를 내지 않는 회사(토스)
        firms[firm] = {"reports": {p: {k: store[p][k] for k in ("label", "rcept_no", "rcept_dt", "first_dt")} | {"rows": len(store[p]["subs"])}
                                   for p in pers if p in store}, "entities": out,
                       "roe": {p: r for p in pers if p in store and (r := period_roe(store[p]["subs"], seeds.get(firm, []), p))}} \
            | ({"rev_net": True} if rev_net else {}) | ({"audit": True} if audit else {})
    return {"updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": "DART 사업보고서(토스 감사보고서)·반기보고서 연결재무제표 주석 '종속기업·관계기업 요약재무정보'",
            "unit": "백만원", "periods": pers, "filing": filing, "firms": firms}


def roe_behind(raw):
    """ROE(sub_fin.json)가 읽은 사업보고서와 여기 최신 사업연도 보고서가 다른 회사(새 보고서 반영 전이거나 그날 수집 실패)."""
    path = DATA / "sub_fin.json"
    done = json.loads(path.read_text(encoding="utf-8")).get("firms", {}) if path.exists() else {}
    out = []
    for firm, st in raw["firms"].items():
        fy = [p for p in st if p.startswith("FY") and st[p]["subs"]]
        if fy and done.get(firm, {}).get("rcept_no") != st[max(fy)]["rcept_no"]:
            out.append(firm)
    return out


def save(path, obj, indent):
    """시각(updated_at·checked_at)만 바뀐 경우에는 쓰지 않는다(공시 시즌 매일 실행이 빈 커밋·재배포를 만들지 않게)."""
    strip = lambda d: {k: v for k, v in d.items() if k not in ("updated_at", "checked_at")}  # noqa: E731
    if path.exists() and strip(json.loads(path.read_text(encoding="utf-8"))) == strip(obj):
        return False
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=indent), encoding="utf-8")
    return True


def main():
    raw = json.loads(RAW.read_text(encoding="utf-8")) if RAW.exists() else {"firms": {}}
    new, errors = [], []
    if "--rebuild" not in sys.argv:
        key = get_key("DART_API_KEY")
        if key:
            new, errors = collect(key, raw, date.today())
            raw["checked_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            save(RAW, raw, 0)
        else:
            print("DART_API_KEY 없음: 저장된 표로만 다시 만든다")
    for e in errors:
        print("  !", e)
    if not raw["firms"]:
        print("저장된 보고서 없음: sub_trend.json 건너뜀")
        return 0
    out = build(raw)
    out["checked_at"], out["errors"] = raw.get("checked_at"), errors
    save(OUT, out, 1)
    behind = roe_behind(raw)
    print(f"{OUT.name}: {', '.join(out['periods'])} · 새 보고서 {len(new)}건 · 오류 {len(errors)}건"
          + (f" · ROE 미반영 {', '.join(behind)}" if behind else ""))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"new_reports={'true' if new or behind else 'false'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
