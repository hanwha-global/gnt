"""증권사별 해외 종속기업 ROE: 최근 사업보고서 원문의 '종속기업 요약재무정보' 표를 읽는다(DART, LLM 미사용).

타법인출자현황에는 자본이 없어 ROE를 못 구한다. 사업보고서 본문(연결재무제표 주석)의 종속기업 요약재무정보에는
법인별 자산·부채·당기순이익이 있어, 자본 = 자산 − 부채로 두고 증권사별 해외 종속기업 합계로
가중평균 ROE(= 순이익 합계 ÷ 자본 합계)를 낸다. 손자회사도 이 표에 나오므로 직접 출자 여부와 관계없이 잡힌다.
표의 법인별 값은 각자의 별도재무제표 기준이라 중간지주(예: 미래에셋 홍콩법인) 자본에는 자회사 투자가 들어 있다.
그래서 같은 보고서의 지분 구조(투자회사 | 피투자회사 표, 'A의 투자회사는 B' 각주)로 모회사를 찾아
중간지주 자본에서 자회사 자본 × 지분율(중간지주 자본 한도)을 빼고 한 번만 센다.

입력: site/data/domestic/dart_latest.json 의 financials_annual_report(사업보고서 접수번호).
출력: site/data/domestic/sub_fin.json. DART_API_KEY가 없거나 표를 못 찾은 회사는 이전 값을 유지한다.
"""
import html
import io
import json
import os
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from keys import get_key  # noqa: E402
import net  # noqa: E402
from gnd import classify_entity, guess_country, is_overseas_name  # noqa: E402
from update_dart import match  # noqa: E402

API = "https://opendart.fss.or.kr/api"
DATA = Path(__file__).resolve().parents[1] / "site" / "data" / "domestic"
OUT = DATA / "sub_fin.json"
UNITS = {"백만원": 1, "천원": 1e-3, "원": 1e-6}


def clean(cell):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", cell))).strip()


def tables(text, with_after=False):
    """문서의 (표 앞 텍스트, 행 목록[, 표 뒤 텍스트]). DART 문서는 TD/TH/TE/TU 셀을 섞어 쓴다."""
    for m in re.finditer(r"<TABLE\b.*?</TABLE>", text, flags=re.S | re.I):
        before = clean(text[max(0, m.start() - 800):m.start()])
        rows = []
        for tr in re.findall(r"<TR\b.*?</TR>", m.group(0), flags=re.S | re.I):
            cells = [clean(c) for c in re.findall(r"<(?:TD|TH|TE|TU)\b[^>]*>(.*?)</(?:TD|TH|TE|TU)>", tr, flags=re.S | re.I)]
            if any(cells):
                rows.append(cells)
        if with_after:  # 표 뒤 각주(중간지배기업의 연결 여부, 지분 보유 법인 등)
            yield before, rows, clean(re.split(r"<TABLE\b", text[m.end():m.end() + 3000], flags=re.I)[0])[:600]
        else:
            yield before, rows


def to_num(s):
    s = (s or "").replace(",", "").replace(" ", "")
    neg = (s.startswith("(") and s.endswith(")")) or s.startswith("-") or s.startswith("△")
    s = s.strip("()-△")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


def find_col(header, *needles, avoid=()):
    for i, h in enumerate(header):
        h2 = h.replace(" ", "")
        if any(n in h2 for n in needles) and not any(a in h2 for a in avoid):
            return i
    return None


def parse_doc(texts, marker="종속"):
    """종속기업 요약재무정보 표에서 해외 법인 행을 {name: {assets, liab, equity, rev, ni}}(백만원)로 모은다.

    당기 표가 전기 표보다 먼저 나오므로 같은 이름은 처음 값을 쓴다. 표 앞 글에 marker('종속', 관계기업 표는
    '관계기업|공동기업')가 있는 표만 본다. rev는 영업수익(매출)이다.
    재무상태(자산·부채)와 손익(순이익)을 표 두 개로 나눠 싣는 회사(신한투자증권 등)도 있어 항목별로 합친다.
    """
    part = {}
    for text in texts:
        for before, rows in tables(text):
            if len(rows) < 2 or not re.search(marker, before + " ".join(rows[0])):
                continue
            # 전기·비교 표는 건너뛴다. 반기·분기보고서는 '당반기/전반기'로 쓴다('당반기'에는 '당기'가 없다)
            tail = before[-120:]
            if re.search(r"전기|전반기|전분기|비교기간", tail) and not re.search(r"당기|당반기|당분기", tail):
                continue
            hi = next((i for i, r in enumerate(rows[:4])
                       if (find_col(r, "자산") is not None and find_col(r, "부채") is not None)
                       or find_col(r, "당기순", "순이익", "순손익", "당기손익", avoid=("포괄",)) is not None), None)
            if hi is None:
                continue
            header = rows[hi]
            unit = next((u for u in UNITS if re.search(r"단위\s*[:：]?\s*" + u, before + " " + " ".join(rows[0]))), "원")
            cols = {"assets": find_col(header, "자산", avoid=("순자산",)), "liab": find_col(header, "부채"),
                    "equity": find_col(header, "자본", "순자산"),
                    "rev": find_col(header, "영업수익", "매출", "수익", avoid=("포괄", "순수익", "기타")),
                    "ni": find_col(header, "당기순", "순이익", "순손익", "당기손익", avoid=("포괄",))}
            # 영업수익 칸이 없고 순영업손익(순영업수익)만 싣는 회사(삼성증권)는 그 값을 쓰고 표시해 둔다
            net = cols["rev"] is None and find_col(header, "순영업손익", "순영업수익") is not None
            if net:
                cols["rev"] = find_col(header, "순영업손익", "순영업수익")
            for r in rows[hi + 1:]:
                name = (r[0] if r else "").strip()
                if not name or re.search(r"합계|소계|^계$|^합 ?계", name):
                    continue
                if not is_overseas_name(name) or classify_entity(name)[0] != "법인":
                    continue
                shift = len(header) - len(r)  # 병합 셀로 칸이 모자라면 오른쪽 정렬
                val = lambda c: None if c is None or c - shift < 1 or c - shift >= len(r) else to_num(r[c - shift])  # noqa: E731,B023
                p = part.setdefault(name, {})
                for k, c in cols.items():
                    x = val(c)
                    if x is not None and p.get(k) is None:
                        p[k] = round(x * UNITS[unit], 1)
                        if k == "rev" and net:
                            p["rev_net"] = True
    out = {}
    for name, p in part.items():
        v = {k: p.get(k) for k in ("assets", "liab", "equity", "rev", "ni")} | ({"rev_net": True} if p.get("rev_net") else {})
        if v["equity"] is None and v["assets"] is not None and v["liab"] is not None:
            v["equity"] = round(v["assets"] - v["liab"], 1)
        if v["ni"] is None or v["equity"] is None:
            continue
        out[name] = {**v, "country": guess_country(name)}
    return out


def pct(cell):
    """'100.00', '99.9%' 같은 지분율 칸만 숫자로(주식 수 '25,000' 등은 None)."""
    m = re.fullmatch(r"(\d{1,3}(?:\.\d+)?)\s*%?", (cell or "").strip())
    return float(m.group(1)) if m and float(m.group(1)) <= 100 else None


def parse_parents(texts):
    """지분 구조 {피투자 법인: (투자 법인, 지분율 %)}. 중간지주 아래 법인을 한 번만 세는 데 쓴다.

    연결 주석 종속기업 현황의 '투자회사 | 피투자회사' 표(투자회사 칸이 병합돼 한 칸 모자란 행은 윗행의 투자회사)와
    'A의 투자회사는 B입니다' 각주(키움증권 형식)를 읽는다. 같은 법인은 처음 나온 값(당기 연결 주석)을 쓴다.
    """
    out = {}
    for text in texts:
        for _, rows in tables(text):
            hdr = next(((k, j) for k, r in enumerate(rows[:3]) for j in range(1, len(r))
                        if re.fullmatch(r"피투자(회사|기업)명?", r[j].replace(" ", "")) or (r[j].replace(" ", "") in ("회사명", "종속기업명", "기업명")
                                                                                  and re.search(r"투자(회사|기업)$", r[j - 1].replace(" ", "")))), None)
            if not hdr:
                continue
            k, j = hdr
            oc = find_col(rows[k], "지분율", "소유지분", "의결권")
            body = rows[k + 1:]
            width = max((len(r) for r in body), default=0)
            inv = None
            for r in body:
                if len(r) >= width and len(r) > j:
                    inv, sub, shift = r[j - 1], r[j], 0
                elif len(r) == width - 1 and inv and len(r) >= j:
                    sub, shift = r[j - 1], 1  # 투자회사 칸이 병합된 행
                else:
                    continue
                own = pct(r[oc - shift]) if oc is not None and oc > j and oc - shift < len(r) else None
                if own is None:
                    own = next((v for v in map(pct, r[j + 1 - shift:]) if v is not None), None)
                # '종속기업'·'지배기업' 같은 구분 칸(별도재무제표의 직접 출자 표 등)은 모회사 이름이 아니다
                label = re.sub(r"\((?:\*|주)[\d,\s]*\)|\s", "", inv)
                if sub and sub not in out and not re.fullmatch(r"(종속|관계|공동|지배)기업|구분|당사", label):
                    out[sub] = (inv, own)
        flat = clean(text)
        for m in re.finditer(r"의\s*투자(?:회사|기업)는\s*(.{3,150}?)\s*(?:입니다|이며|이고)", flat):
            head = re.split(r"\((?:주|\*)\s*\d+\)|니다\.", flat[max(0, m.start() - 300):m.start()])[-1]
            for sub in re.split(r",\s*|\s+및\s+", head.strip()):
                if sub and sub not in out:
                    out[sub] = (m.group(1).strip(), None)
    return out


def find_entity(name, names):
    """표마다 조금씩 다른 표기(띄어쓰기·각주 표시·법인 형태)를 같은 법인으로 본다: 정규화 이름이 같으면 그 법인,
    아니면 12자 이상 앞부분이 맞는 법인이 하나뿐일 때 그 법인."""
    from fetch_consolidated import key_name
    norm = lambda x: key_name(re.sub(r"\((?:\*|주)\s*[\d,\s]*\)", "", x or ""))  # noqa: E731
    k = norm(name)
    if not k:
        return None
    keys = {n: norm(n) for n in names}
    exact = [n for n, nk in keys.items() if nk == k]
    if exact:
        return exact[0]
    hits = [n for n, nk in keys.items() if nk and len(min(nk, k, key=len)) >= 12 and (nk.startswith(k) or k.startswith(nk))]
    return hits[0] if len(hits) == 1 else None


def attach_parents(subs, parents):
    """요약재무 행마다 지분 구조의 투자 법인(parent)과 지분율(own, %)을 붙인다(--resummarize도 이 값으로 다시 계산)."""
    for name, s in subs.items():
        hit = find_entity(name, parents)
        if hit:
            s["parent"], s["own"] = parents[hit]
    return subs


def mark_consolidated(subs, texts):
    """'X 및 그 종속기업이 포함된 중간지배기업의 연결재무정보' 각주(토스 형식)가 붙은 행은 자회사까지 든 연결 값이다.
    이런 중간지주 아래 법인은 따로 행이 없어도 ROE에 들어 있다(화면 '빠진 법인'에서 뺀다)."""
    for text in texts:
        flat = clean(text)
        for m in re.finditer(r"및\s*그\s*종속기업(?:이|을)\s*포함(?:된|한)[^.]{0,40}?연결\s*재무", flat):
            head = re.split(r"\((?:주|\*)\s*\d*\)|니다\.", flat[max(0, m.start() - 200):m.start()])[-1].strip()
            hit = find_entity(head, subs)
            if hit:
                subs[hit]["consolidated"] = True
    return subs


def debug_dump(firm, texts, out=sys.stdout):
    """원인 확인용: '종속'이 들어간 요약재무·지분율 표의 앞 글, 모든 행, 표 뒤 각주를 찍는다(공시 원문 그대로)."""
    for text in texts:
        for before, rows, after in tables(text, with_after=True):
            head = " ".join(" ".join(r) for r in rows[:3])
            if len(rows) < 2 or "종속" not in before + head or not re.search(r"자산|순이익|순손익|지분율|소유", head):
                continue
            print(f"[{firm}] 앞: ...{before[-200:]}", file=out)
            for r in rows:
                print("    | " + " | ".join(c[:40] for c in r[:10]), file=out)
            print(f"    뒤: {after}", file=out)


def audit_report(key, corp_code):
    """정기보고서(사업보고서)를 내지 않는 회사(예: 비상장 증권사)는 최근 감사보고서를 쓴다. 연결이 있으면 연결."""
    import datetime as dt
    today = dt.date.today()
    rows = []
    for p in (1, 2):
        data = net.get_json(f"{API}/list.json", {"crtfc_key": key, "corp_code": corp_code, "pblntf_ty": "F", "page_no": p, "page_count": 100,
                                                 "bgn_de": (today - dt.timedelta(days=560)).strftime("%Y%m%d"), "end_de": today.strftime("%Y%m%d")})
        rows += data.get("list", []) or []
        if len(data.get("list", []) or []) < 100:
            break
    # 최근 사업연도 → 연결 먼저 → 같은 보고서는 가장 나중 제출본(정정 포함). 5개년 추이(fetch_sub_trend.periods_of)와 같은 규칙
    def year(r):
        m = re.search(r"\((\d{4})\.\d{2}\)", r["report_nm"])
        return m.group(1) if m else ""
    rows = [r for r in rows if "감사보고서" in r.get("report_nm", "")]
    rows.sort(key=lambda r: (year(r), "연결" in r["report_nm"], r["rcept_dt"]), reverse=True)
    if not rows:
        return None
    r = rows[0]
    m = re.search(r"\((\d{4})\.(\d{2})\)", r["report_nm"])
    label = f"{m.group(1)} 감사보고서" if m else r["report_nm"]
    return {"rcept_no": r["rcept_no"], "label": label, "report_nm": r["report_nm"]}


def document_texts(key, rcept_no):
    raw = net.get(f"{API}/document.xml", {"crtfc_key": key, "rcept_no": rcept_no}, timeout=180)
    texts = []
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for n in z.namelist():
            b = z.read(n)
            for enc in ("utf-8", "euc-kr", "cp949"):
                try:
                    texts.append(b.decode(enc))
                    break
                except UnicodeDecodeError:
                    continue
    return texts


def loose_match(seeds, name):
    """표기만 다른 같은 법인: 정규화 이름이 같거나 한쪽이 다른 쪽으로 시작(12자 이상)할 때 하나뿐이면 그 법인."""
    from fetch_consolidated import key_name
    k = key_name(name)
    hits = [e["name"] for e in seeds if (sk := key_name(e["name"])) == k
            or (len(min(sk, k, key=len)) >= 12 and (sk.startswith(k) or k.startswith(sk)))]
    return hits[0] if len(hits) == 1 else None


def pick(subs, seeds):
    """요약재무 행을 기준 법인(사이트 네트워크 법인)과 짝지어 {기준 법인명: 행}을 돌려주고 행마다 seed_name을 단다.

    표기가 같은 행을 먼저 짝짓고, 남은 기준 법인만 유사 이름으로 찾는다(손자회사가 모회사로 잘못 붙는 것 방지).
    """
    compact = lambda x: re.sub(r"[^0-9a-z가-힣]+", "", re.sub(r"\(주\d\)", "", (x or "").lower()))  # noqa: E731
    picked = {}
    for name, s in subs.items():
        s["seed_name"] = None
    # 이름이 바뀐 법인은 올해 공시 이름(dart_name)으로 먼저 짝짓는다. 옛 이름 행은 전기 표에서 온 지난해 값이다
    for key in ("dart_name", "name"):
        for name, s in subs.items():
            exact = next((e["name"] for e in seeds if e.get(key) and compact(e[key]) == compact(name)), None)
            if exact and exact not in picked and not s["seed_name"]:
                picked[exact], s["seed_name"] = s, exact
    rest = [e for e in seeds if e["name"] not in picked]
    for name, s in subs.items():
        if s["seed_name"] or not rest:
            continue
        if any((p["equity"], p["ni"]) == (s["equity"], s["ni"]) for p in picked.values()):
            continue  # 같은 법인이 표기만 달리해 두 번 나온 행
        seed = loose_match(rest, name)
        if seed and seed not in picked:
            picked[seed], s["seed_name"] = s, seed
            rest = [e for e in rest if e["name"] != seed]
    return picked


def summarize(subs, seeds, match=pick):
    """해외 현지법인(기준 데이터의 운영 법인)과 맞는 행만 합산한다. 부동산·펀드 SPV, ETF 등은 표에 남기되 제외.
    match: 행과 기준 법인을 짝짓는 함수(지난 보고서는 옛 이름까지 짝짓는 fetch_sub_trend의 matcher를 넘긴다)."""
    picked = match(subs, seeds)
    # 중간지주 행(별도재무제표 기준) 자본에는 자회사 투자가 들어 있다. 자회사가 함께 합산되면 자회사 자본 × 지분율을
    # 중간지주 자본 한도에서 빼 한 번만 센다. 순이익 속 자회사 배당은 공시로 가를 수 없어 그대로 둔다
    rows = {name: s for name, s in subs.items() if s["seed_name"]}
    minus = {}
    for name, s in rows.items():
        p = find_entity(s["parent"], rows) if s.get("parent") else None
        if p and p != name:
            minus[p] = minus.get(p, 0) + max(s["equity"], 0) * (s.get("own") or 100) / 100
    overlap = sum(min(v, max(rows[p]["equity"], 0)) for p, v in minus.items())
    ni = sum(s["ni"] for s in picked.values())
    eq = sum(s["equity"] for s in picked.values()) - overlap
    return {"n": len(picked), "ni": round(ni, 1), "equity": round(eq, 1),
            "roe": round(ni / eq * 100, 2) if eq > 0 else None,
            "overlap": round(overlap, 1), "holdcos": sorted(rows[p]["seed_name"] for p in minus)}


def seeds_by_firm():
    seed = json.loads((DATA / "seed.json").read_text(encoding="utf-8"))
    out = {}
    for e in seed["entities"]:
        if e.get("name") and e["kind"] == "법인" and e["status"] == "운영" and e["relation"] != "지분투자":
            out.setdefault(e["firm"], []).append(e)
    # DART에 새로 나와 자동 반영된 해외 법인(update_dart.py new_entities)도 함께 센다
    dart_path = DATA / "dart_latest.json"
    if dart_path.exists():
        for firm, d in json.loads(dart_path.read_text(encoding="utf-8")).get("firms", {}).items():
            hold = {h["name"]: h for h in d.get("overseas_direct", [])}
            for n in d.get("new_entities", []):
                out.setdefault(firm, []).append({"firm": firm, "name": n, "country": hold.get(n, {}).get("country_guess"),
                                                 "kind": "법인", "status": "운영", "relation": "종속(자회사)"})
    # 종속회사 전수 목록(fetch_consolidated.py)이 있는 회사는 그 목록의 금융업 영업법인·중간지주만 쓴다(사이트 법인 수와 같은 규칙)
    cons_path = DATA / "consolidated.json"
    if cons_path.exists():
        for firm, c in json.loads(cons_path.read_text(encoding="utf-8")).get("firms", {}).items():
            rows = [x for x in c.get("overseas", []) if x.get("class") in ("영업법인", "지주회사")]
            if rows:
                out[firm] = [{"firm": firm, "name": x.get("seed_name") or x["name"], "dart_name": x["name"], "country": x["country"],
                              "kind": "법인", "status": "운영", "relation": "종속(자회사)"} for x in rows]
    return out


def resummarize():
    data = json.loads(OUT.read_text(encoding="utf-8"))
    sb = seeds_by_firm()
    for firm, v in data["firms"].items():
        v.update(summarize(v["subs"], sb.get(firm, [])))
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


def main():
    if "--resummarize" in sys.argv:  # 원문을 다시 받지 않고 저장된 표로 합계만 다시 낸다(키 불필요)
        return resummarize()
    key = get_key("DART_API_KEY")
    if not key:
        print("DART_API_KEY 없음: sub_fin.json 갱신 건너뜀")
        return 0
    dart = json.loads((DATA / "dart_latest.json").read_text(encoding="utf-8"))
    seeds_by = seeds_by_firm()  # 운영 중인 해외 현지법인(펀드·신탁·Vehicle·단순 지분투자 제외)
    prev = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {"firms": {}}
    result = {"updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "source": "DART 사업보고서 연결재무제표 주석 '종속기업 요약재무정보'", "firms": {}, "errors": []}
    debug = set(filter(None, os.environ.get("SUBFIN_DEBUG", "").split(",")))
    for firm, d in dart.get("firms", {}).items():
        rep = d.get("financials_annual_report")
        try:
            if not rep and d.get("corp_code"):
                rep = audit_report(key, d["corp_code"])  # 사업보고서가 없으면 감사보고서 주석
            if not rep:
                result["errors"].append(f"{firm}: 사업보고서·감사보고서 없음")
                continue
            texts = document_texts(key, rep["rcept_no"])
            if firm in debug or "all" in debug:
                debug_dump(firm, texts)
            subs = mark_consolidated(attach_parents(parse_doc(texts), parse_parents(texts)), texts)
        except Exception as e:  # 한 회사가 실패해도 나머지는 계속
            result["errors"].append(f"{firm}: {e}")
            subs = {}
        if subs:
            result["firms"][firm] = {"report": rep["label"], "rcept_no": rep["rcept_no"], **summarize(subs, seeds_by.get(firm, [])), "subs": subs}
        elif firm in prev.get("firms", {}):
            result["firms"][firm] = prev["firms"][firm]
            result["errors"].append(f"{firm}: 표를 못 찾아 이전 값 유지")
        else:
            result["errors"].append(f"{firm}: 종속기업 요약재무정보 표 없음")
        print(f"{firm}: {len(subs)}개 해외 종속기업")
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
