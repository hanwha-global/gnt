"""Velocity Clearing 손익·출자: 한화생명(088350) DART 정기보고서에서 미국 법인 행을 읽는다(LLM 미사용).

- 연결재무제표 주석 '종속기업 요약재무정보': 한화생명 미국 중간지주(HLI US Inv, LLC)·Nexus Clearing·VCT Holdings·Velocity
  행의 자산·부채·영업수익·당기순손익(백만원, 그 보고서 기간 누적). 인수 완료(2025-07-30) 뒤 정기보고서(2025년 3분기부터)마다
  저장하고, 이미 읽은 보고서(접수번호)는 다시 받지 않는다. 원문은 받았는데 표가 없던 보고서는 skip에 적어 다시 받지 않는다.
- 같은 주석의 종속기업 현황 표: 지분율.
- 별도재무제표 주석 '종속기업투자의 내역' 표: 한화생명이 직접 출자한 미국 법인의 장부금액(당기말·전기말)·지분율.
- Open DART '타법인 출자현황': 한화생명이 직접 출자한 미국 법인의 최초 취득일·금액, 기초·기말 장부가액, 지분율.
키(DART_API_KEY)가 없거나 받기·읽기에 실패하면 이전 값을 그대로 둔다. fetch_velocity.py가 부른다.
"""
import io
import json
import os
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import net  # noqa: E402
from fetch_sub_fin import UNITS, clean, find_col, tables, to_num  # noqa: E402
from keys import get_key  # noqa: E402

API = "https://opendart.fss.or.kr/api"
STOCK = "088350"  # 한화생명 종목코드(고유번호는 corpCode.xml에서 찾아 저장)
SINCE = "2025-09-30"  # 인수 완료(2025-07-30) 뒤 첫 정기보고서 기간 끝
KST = timezone(timedelta(hours=9))
# 공시 표기 → 키. VCT Holdings II(나머지 25% 보유, 한화 계열 아님)는 빼고 본다
ENT = [
    ("hold", re.compile(r"\bhli\s*us\b|hanwha\s*life\s*(?:us|u\.s\.)\s*inv", re.I)),
    ("nexus", re.compile(r"nexus\s*clearing|넥서스", re.I)),
    ("vct", re.compile(r"\bvct\s*holdings?\b(?!\s*,?\s*ii\b)", re.I)),
    ("vel", re.compile(r"velocity\s*clearing|벨로시티", re.I)),
]
PERIOD = {"03": "1Q", "06": "1H", "09": "9M", "12": "FY"}
MONTHS = {"1Q": 3, "1H": 6, "9M": 9, "FY": 12}
END = {"1Q": "03-31", "1H": "06-30", "9M": "09-30", "FY": "12-31"}
REPRT = {"1Q": "11013", "1H": "11012", "9M": "11014", "FY": "11011"}  # Open DART 정기보고서 코드
INVEST = {  # 타법인 출자현황 응답 필드 → 이름(금액 백만원, 지분율 %)
    "frst_acqs_de": "first_date", "invstmnt_purps": "purpose", "frst_acqs_amount": "first_amount",
    "bsis_blce_qota_rt": "begin_stake", "bsis_blce_acntbk_amount": "begin_book",
    "incrs_dcrs_acqs_dsps_amount": "chg_amount", "incrs_dcrs_evl_lstmn": "chg_valuation",
    "trmend_blce_qota_rt": "end_stake", "trmend_blce_acntbk_amount": "end_book",
    "recent_bsns_year_fnnr_sttus_tot_assets": "recent_assets", "recent_bsns_year_fnnr_sttus_thstrm_ntpf": "recent_ni",
}
AMOUNTS = ("first_amount", "begin_book", "chg_amount", "chg_valuation", "end_book", "recent_assets", "recent_ni")
DEBUG = bool(os.environ.get("VELOCITY_DART_DEBUG"))


def ent(name):
    """법인명 → 키(hold·nexus·vct·vel). 미국 법인 행이 아니면 None."""
    return next((k for k, rx in ENT if rx.search(name or "")), None)


def plain(name):
    """표의 법인명에서 각주 표시((*1), (주2))를 뗀다."""
    return re.sub(r"\s*\((?:\*|주)\s*[\d,\s]*\)", "", name or "").strip()


def label(year, period):
    """화면 기간 이름: 3Q25 · FY2025 · 1Q26 · 1H26(메인 화면 표기와 같게 9개월 누적도 3Q)."""
    return f"FY{year}" if period == "FY" else f"{'3Q' if period == '9M' else period}{str(year)[2:]}"


def api(path, key, **params):
    d = net.get_json(f"{API}/{path}", {"crtfc_key": key, **params})
    if d.get("status") not in ("000", "013"):  # 013 = 조회된 데이터 없음
        raise RuntimeError(f"{path} {d.get('status')} {d.get('message')}")
    return d.get("list", []) or []


def corp_code(key):
    """종목코드로 DART 고유번호를 찾는다(전체 목록 zip)."""
    raw = net.get(f"{API}/corpCode.xml", {"crtfc_key": key}, timeout=120)
    xml = zipfile.ZipFile(io.BytesIO(raw)).read("CORPCODE.xml")
    for item in ET.fromstring(xml).iter("list"):
        if (item.findtext("stock_code") or "").strip() == STOCK:
            return item.findtext("corp_code").strip()
    raise RuntimeError(f"종목코드 {STOCK} 없음")


def periodic(rows, since=SINCE):
    """list.json 행 → 기간별 최신 접수 1건(정정본 우선), 기간 끝이 since 이후인 것만, 오래된 것부터."""
    best = {}
    for r in rows:
        m = re.search(r"(분기|반기|사업)보고서\s*\((\d{4})\.(\d{2})\)", r.get("report_nm", ""))
        if not m or m.group(3) not in PERIOD:
            continue
        year, period = m.group(2), PERIOD[m.group(3)]
        if f"{year}-{END[period]}" < since:
            continue
        if (year, period) not in best or r["rcept_no"] > best[(year, period)]["rcept_no"]:
            best[(year, period)] = {"year": year, "period": period, "rcept_no": r["rcept_no"], "rcept_dt": r.get("rcept_dt", ""),
                                    "name": re.sub(r"\s+", " ", r["report_nm"]).strip()}
    return sorted(best.values(), key=lambda r: (r["year"], MONTHS[r["period"]]))


def report_info(r):
    return {"name": r["name"], "rcept_no": r["rcept_no"], "rcept_dt": r["rcept_dt"],
            "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={r['rcept_no']}"}


def document(key, rcept_no):
    """정기보고서 원문(zip 안 XML 파일들)의 텍스트 목록."""
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


def pick_col(header, needles, avoid=()):
    """칸 찾기. 3개월·누적 칸이 함께 있으면 누적 칸."""
    hits = [i for i, h in enumerate(header)
            if any(n in h.replace(" ", "") for n in needles) and not any(a in h.replace(" ", "") for a in avoid)]
    return next((i for i in hits if "누적" in header[i]), hits[0] if hits else None)


def unit_of(before, head):
    """표 바로 앞(가장 가까운) '단위: 백만원' 표기, 없으면 머리 행. 모르면 None."""
    for s in (head, before):
        hits = re.findall(r"단위\s*[:：]?\s*(백만원|천원|원)", s)
        if hits:
            return hits[-1] if s is before else hits[0]
    return None


def is_prior(before):
    """전기(비교) 표: 표 앞 글 끝에 전기·전반기·전분기만 있고 당기·당반기·당분기가 없다."""
    tail = before[-120:]
    return bool(re.search(r"전기|전반기|전분기|비교기간", tail)) and not re.search(r"당기|당반기|당분기", tail)


def parse_summary(texts):
    """종속기업 요약재무정보에서 미국 법인 행 → {키: {name, assets, liab, equity, rev, ni, tci}}(백만원).

    당기 표가 전기 표보다 먼저 나오므로 같은 법인은 처음 값을 쓴다. 재무상태(자산·부채)와 손익을 표 두 개로 나눠
    싣는 경우도 있어 항목별로 합친다. 자본 칸이 없으면 자산 − 부채.
    """
    part = {}
    for text in texts:
        for before, rows in tables(text):
            if len(rows) < 2 or is_prior(before) or not any(ent(r[0]) for r in rows[1:] if r):
                continue
            hi = next((i for i, r in enumerate(rows[:4])
                       if (pick_col(r, ("자산",)) is not None and pick_col(r, ("부채",)) is not None)
                       or pick_col(r, ("당기순", "순이익", "순손익", "당기손익", "반기순", "분기순"), ("포괄",)) is not None), None)
            if hi is None:
                continue
            header = rows[hi]
            unit = unit_of(before, " ".join(rows[0]))
            if not unit:
                continue  # 단위를 모르면 쓰지 않는다
            cols = {"assets": pick_col(header, ("자산",), ("순자산",)), "liab": pick_col(header, ("부채",)),
                    "equity": pick_col(header, ("자본", "순자산")),
                    "rev": pick_col(header, ("영업수익", "매출", "수익"), ("포괄", "순수익", "기타")),
                    "ni": pick_col(header, ("당기순", "순이익", "순손익", "당기손익", "반기순", "분기순"), ("포괄",)),
                    "tci": pick_col(header, ("총포괄",))}
            for r in rows[hi + 1:]:
                k = ent(r[0] if r else "")
                if not k:
                    continue
                shift = len(header) - len(r)  # 병합 셀로 칸이 모자라면 오른쪽 정렬
                p = part.setdefault(k, {"name": plain(r[0])})
                for f, c in cols.items():
                    if c is None or c - shift < 1 or c - shift >= len(r) or p.get(f) is not None:
                        continue
                    v = to_num(r[c - shift])
                    if v is not None:
                        p[f] = round(v * UNITS[unit], 1)
    out = {}
    for k, p in part.items():
        if p.get("equity") is None and p.get("assets") is not None and p.get("liab") is not None:
            p["equity"] = round(p["assets"] - p["liab"], 1)
        if p.get("ni") is not None or p.get("assets") is not None:
            out[k] = {f: p.get(f) for f in ("name", "assets", "liab", "equity", "rev", "ni", "tci")}
    return out


def pct(cell):
    m = re.fullmatch(r"(\d{1,3}(?:\.\d+)?)\s*%?", (cell or "").strip())
    return float(m.group(1)) if m and float(m.group(1)) <= 100 else None


def parse_stakes(texts):
    """종속기업 현황 표의 미국 법인 지분율(%). 같은 법인은 처음 나온 값(당기)."""
    out = {}
    for text in texts:
        for before, rows in tables(text):
            if len(rows) < 2 or is_prior(before):
                continue
            hi = next((i for i, r in enumerate(rows[:3]) if pick_col(r, ("지분율", "소유지분")) is not None), None)
            if hi is None:
                continue
            col = pick_col(rows[hi], ("지분율", "소유지분"))
            for r in rows[hi + 1:]:
                k = ent(r[0] if r else "")
                if not k or k in out:
                    continue
                c = col - max(len(rows[hi]) - len(r), 0)
                v = pct(r[c].replace("%", "")) if 0 < c < len(r) else None
                if v is not None and v > 0:
                    out[k] = v
    return out


BOOK_RX = re.compile(r"종속기업\s*투자\s*(?:의\s*)?(?:내역|현황)")


def parse_book(texts):
    """별도재무제표 주석 '종속기업투자의 내역' 표에서 한화생명이 직접 출자한 미국 법인 행
    → {name, stake, book, prev_book}(백만원). 표가 없으면 None. 당기말·전기말 두 칸이 한 표에 있다."""
    best = None
    for text in texts:
        for before, rows in tables(text):
            if len(rows) < 2 or not BOOK_RX.search(before[-300:]):
                continue
            head = rows[0]
            cur = pick_col(head, ("당기말", "당분기말", "당반기말"), ("지분율",))
            prev = pick_col(head, ("전기말",), ("지분율",))
            sc = pick_col(head, ("지분율",))
            unit = unit_of(before, " ".join(head))
            if cur is None or not unit:
                continue
            for r in rows[1:]:
                if not r or not ent(r[0]):
                    continue
                shift = len(head) - len(r)
                cell = lambda c: r[c - shift] if c is not None and 0 < c - shift < len(r) else None  # noqa: E731
                book = to_num(cell(cur))
                if book is None:
                    continue
                pv = to_num(cell(prev))
                row = {"name": plain(r[0]), "stake": pct((cell(sc) or "").replace("%", "")), "book": round(book * UNITS[unit], 1),
                       "prev_book": None if pv is None else round(pv * UNITS[unit], 1)}
                if not best or row["book"] > best["book"]:
                    best = row
        if best:
            return best
    return best


def invest_rows(rows):
    """타법인 출자현황 응답 → 미국 법인 {키: 값}(금액 백만원). 단위는 표 전체 가장 큰 장부가액으로 정한다:
    한화생명 최대 출자(1천억~10조원)가 1e11 이상이면 원, 1e8 이상이면 천원, 그보다 작으면 백만원."""
    big = max((abs(to_num(r.get("trmend_blce_acntbk_amount")) or 0) for r in rows or []), default=0)
    div, unit = (1e6, "원") if big >= 1e11 else (1e3, "천원") if big >= 1e8 else (1, "백만원")
    out = {}
    for r in rows or []:
        k = ent(r.get("inv_prm", ""))
        if not k:
            continue
        row = {"name": plain(r.get("inv_prm", ""))}
        for f, n in INVEST.items():
            v = (r.get(f) or "").strip()
            if n in AMOUNTS:
                x = to_num(v)
                row[n] = None if x is None else round(x / div, 1)
            elif n in ("first_date", "purpose"):
                row[n] = v if v not in ("", "-") else None
            else:
                row[n] = to_num(v)
        if row.get("first_date") and re.fullmatch(r"\d{4}[.\-]?\d{2}[.\-]?\d{2}", row["first_date"]):
            d = re.sub(r"\D", "", row["first_date"])
            row["first_date"] = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        if k not in out or (row.get("end_book") or 0) > (out[k].get("end_book") or 0):
            out[k] = row
    return out, unit


def debug_dump(name, texts):
    """원인 확인용(VELOCITY_DART_DEBUG): 미국 법인 행이 든 표와 '사업결합' 문단을 실행 기록에 찍는다."""
    for text in texts:
        for before, rows in tables(text):
            if not any(ent(r[0]) for r in rows if r):
                continue
            print(f"  [{name}] 표 앞: …{before[-160:]}")
            for r in rows[:3]:
                print("     머리 | " + " | ".join(c[:24] for c in r[:10]))
            for r in rows:
                if r and ent(r[0]):
                    print("     행   | " + " | ".join(c[:24] for c in r[:10]))
        flat = clean(text)
        for m in list(re.finditer(r"사업결합|이전대가|영업권", flat))[:400]:
            win = flat[max(0, m.start() - 300):m.start() + 500]
            if any(rx.search(win) for _, rx in ENT):
                print(f"  [{name}] 글: …{win}…")
                break


def entry(r, subs, stakes, book=None):
    return {"label": label(r["year"], r["period"]), "year": r["year"], "period": r["period"], "months": MONTHS[r["period"]],
            "end": f"{r['year']}-{END[r['period']]}", "report": report_info(r), "subs": subs, "stakes": stakes, "book": book}


def collect(prev, errors):
    """정기보고서별 미국 법인 행(periods, 오래된 것부터: 요약재무정보·지분율·별도 장부금액)과 타법인 출자현황(invest).
    실패한 부분은 이전 값."""
    P = dict(prev or {})
    key = get_key("DART_API_KEY")
    if not key:
        print("DART_API_KEY 없음: 한화생명 공시(손익·출자)는 이전 값")
        return prev
    try:
        code = P.get("corp_code") or corp_code(key)
        today = datetime.now(KST).date()
        reps = periodic(api("list.json", key, corp_code=code, pblntf_ty="A", page_count=100,
                            bgn_de="20251001", end_de=today.strftime("%Y%m%d")))
    except Exception as e:  # noqa: BLE001  요청 한도·점검·키 오류: 아무것도 바꾸지 않는다
        errors.append(f"DART 목록: {e}")
        return prev
    have = {p["report"]["rcept_no"]: p for p in P.get("periods", [])}
    by_period = {(p["year"], p["period"]): p for p in P.get("periods", [])}
    skip = set(P.get("skip", []))
    periods = []
    for r in reps:
        if r["rcept_no"] in have:
            periods.append(have[r["rcept_no"]])
            continue
        old = by_period.get((r["year"], r["period"]))  # 정정본을 못 읽으면 같은 기간 이전 값
        if r["rcept_no"] in skip:
            if old:
                periods.append(old)
            continue
        try:
            texts = document(key, r["rcept_no"])
        except Exception as e:  # noqa: BLE001  받기 실패는 skip하지 않고 다음에 다시
            errors.append(f"DART 원문 {r['name']}: {e}")
            if old:
                periods.append(old)
            continue
        if DEBUG:
            debug_dump(label(r["year"], r["period"]), texts)
        subs = parse_summary(texts)
        if subs:
            periods.append(entry(r, subs, parse_stakes(texts), parse_book(texts)))
        else:
            skip.add(r["rcept_no"])
            errors.append(f"DART {r['name']}: 종속기업 요약재무정보에 미국 법인 행 없음")
            if old:
                periods.append(old)
    # 타법인 출자현황: 최신 보고서부터, 직전에 읽은 보고서보다 오래된 것은 받지 않는다
    inv = P.get("invest")
    floor = (inv or {}).get("report", {}).get("rcept_no", "")
    for r in sorted(reps, key=lambda r: r["rcept_no"], reverse=True):
        if r["rcept_no"] < floor:
            break
        if inv and r["rcept_no"] == floor:
            break  # 이미 읽은 보고서
        try:
            rows, unit = invest_rows(api("otrCprInvstmntSttus.json", key, corp_code=code, bsns_year=r["year"], reprt_code=REPRT[r["period"]]))
        except Exception as e:  # noqa: BLE001
            errors.append(f"DART 타법인 출자현황 {r['name']}: {e}")
            break
        if rows:
            inv = {"report": report_info(r), "label": label(r["year"], r["period"]), "unit_raw": unit, "rows": rows}
            break
    return {"corp_code": code, "checked": today.isoformat(), "unit": "백만원",
            "periods": periods or P.get("periods", []), "skip": sorted(skip), "invest": inv}
