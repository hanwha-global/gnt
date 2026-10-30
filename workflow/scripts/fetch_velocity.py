"""미국 진출 페이지 'Velocity Clearing(한화생명 75%)' 자동 수집(키·LLM 불필요). 못 받은 항목은 이전 값을 그대로 둔다.

- FINRA BrokerCheck 공개 API: 등록(SEC·SRO·주) 수, 업무 종류 수, 규제 공시 건수, 직접 소유자·임원, 회사 규모 분류.
  상세 보고서 PDF에서 SRO(거래소) 목록과 업무 종류도 읽는다(pypdf 필요, API 개수와 같을 때만 바꾼다).
  PDF는 개수가 바뀌었거나 마지막으로 읽은 지 7일이 지났을 때만 받는다.
- SEC EDGAR submissions API: 연차 감사보고서(X-17A-5) 목록. 새 보고서가 올라오면 공개분 PDF에서
  재무상태표(총자산·부채·회원 지분)와 순자본 주석을 읽는다(pypdf 필요, 대차 합계가 맞을 때만 반영).
- 회사 누리집(who-we-are): 감사보고서보다 새 반기 미감사 재무상태표 PDF가 있으면 같은 방식으로 읽는다.
- SEC XBRL companyconcept: 미국 상장 브로커리지의 자본·총자산을 Velocity 최근 재무 날짜와 같은 날로(화면이 순위를 낸다),
  같은 날로 끝나는 최근 12개월 순이익(ROE용, 자본과 같은 범위: 비지배지분 포함 자본이면 ProfitLoss).
  결산일이 같으면 값이 바뀌지 않으므로 7일에 한 번만 다시 받는다(못 받은 회사가 있으면 매번).
- 한화생명 DART 정기보고서(velocity_dart.py, DART_API_KEY): 미국 법인 손익(종속기업 요약재무정보)·출자(타법인 출자현황).
- Google News RSS: 'Velocity Clearing', '한화생명 벨로시티' 기사.

출력: workflow/data/velocity.json. 사람이 원문을 읽고 쓴 인수 경과·라이선스 설명은 workflow/data/us_entry.json 의 velocity.
사용: python workflow/scripts/fetch_velocity.py
"""
import io
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import unquote, urljoin

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import net  # noqa: E402
from fetch_news import rss_url  # noqa: E402
from update_sec import EQUITY_TAGS, SEC_UA  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import velocity_dart  # noqa: E402

OUT = ROOT / "workflow" / "data" / "velocity.json"
KST = timezone(timedelta(hours=9))
CRD, CIK = "126588", "0001225460"
BC_API = f"https://api.brokercheck.finra.org/search/firm/{CRD}"
BC_PDF = f"https://files.brokercheck.finra.org/firm/firm_{CRD}.pdf"
SUBMISSIONS = f"https://data.sec.gov/submissions/CIK{CIK}.json"
CONCEPT = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json"
SEC_H = {"User-Agent": SEC_UA, "Accept": "application/json"}
SITE = "https://www.velocityclearingllc.com/who-we-are/"  # 감사·반기 재무상태표 링크가 있는 회사 소개 쪽

# 미국 상장 브로커리지: 미국 본사 NYSE·NYSE American·나스닥 상장사 중 증권 중개·청산·시장조성·자산관리 중개가 주업인 회사.
# 자문 전업 IB(Evercore·Lazard 등), 거래소·전자거래 플랫폼, 보험·자산운용 겸업사, 외국 본사 상장사는 넣지 않는다
PEERS = [
    ("Goldman Sachs", "GS", "0000886982", "IB·트레이딩"),
    ("Morgan Stanley", "MS", "0000895421", "IB·WM"),
    ("Charles Schwab", "SCHW", "0000316709", "리테일 브로커리지"),
    ("Interactive Brokers", "IBKR", "0001381197", "온라인 브로커리지"),
    ("Raymond James", "RJF", "0000720005", "WM·IB"),
    ("Jefferies", "JEF", "0000096223", "IB"),
    ("Robinhood", "HOOD", "0001783879", "모바일 브로커리지"),
    ("Stifel", "SF", "0000720672", "WM·IB"),
    ("LPL Financial", "LPLA", "0001397911", "독립 어드바이저 플랫폼"),
    ("StoneX", "SNEX", "0000913760", "기관 청산·중개"),
    ("Virtu Financial", "VIRT", "0001592386", "시장조성·체결"),
    ("BGC Group", "BGC", "0001094831", "기관 중개"),
    ("Piper Sandler", "PIPR", "0001230245", "IB·기관 중개"),
    ("Oppenheimer", "OPY", "0000791963", "WM·IB"),
    ("Cohen & Company", "COHN", "0001270436", "채권 중개·IB"),
    ("Siebert Financial", "SIEB", "0000065596", "리테일 브로커리지"),
]
ASSET_TAGS = ["Assets"]

NEWS_Q = [('"Velocity Clearing"', "en"), ("한화생명 벨로시티", "ko")]
NEWS_DAYS = 730
NEWS_MAX = 8
RECHECK_DAYS = 7  # BrokerCheck 보고서 PDF·상장사 값 다시 받는 간격


def mdy(s):
    """BrokerCheck 날짜 '08/15/2003' → '2003-08-15'."""
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", s or "")
    return f"{m.group(3)}-{m.group(1)}-{m.group(2)}" if m else None


def sec_get(url, **kw):
    time.sleep(0.15)  # SEC 공정 접근 기준(초당 10건) 안쪽
    return net.get(url, headers={"User-Agent": SEC_UA, **kw.pop("headers", {})}, **kw)


# ---------- BrokerCheck ----------
def parse_bc(raw):
    """BrokerCheck 검색 API 응답(content는 JSON 문자열) → 화면용 요약."""
    hit = json.loads(raw)["hits"]["hits"][0]["_source"]
    c = json.loads(hit["content"]) if isinstance(hit.get("content"), str) else hit["content"]
    b, reg = c.get("basicInformation") or {}, c.get("registrations") or {}
    return {
        "crd": str(b.get("firmId") or CRD), "name": b.get("firmName"), "status": b.get("firmStatus"),
        "sec_file": f"8-{b['bdSECNumber']}" if b.get("bdSECNumber") else None,
        "finra_since": mdy(b.get("finraLastApprovalDate")), "formed": mdy(b.get("formedDate")), "formed_state": b.get("formedState"),
        "firm_type": b.get("firmType"), "size": b.get("firmSize"), "other_names": b.get("otherNames") or [],
        "address": ", ".join(x for x in [(c.get("firmAddressDetails") or {}).get("officeAddress", {}).get(k) for k in ("city", "state")] if x),
        "counts": {"sec": reg.get("approvedSECRegistrationCount"), "sro": reg.get("approvedSRORegistrationCount"),
                   "states": reg.get("approvedStateRegistrationCount"), "types": reg.get("businessTypeCount")},
        "disclosures": {d.get("disclosureType"): d.get("disclosureCount") for d in c.get("disclosures") or []},
        "officers": [{"name": o.get("legalName"), "position": o.get("position")} for o in c.get("directOwners") or []],
    }


SRO_LINE = re.compile(r"^(.+?)\s+Approved\s+(\d{2}/\d{2}/\d{4})\s*$")


def parse_bc_report(text):
    """상세 보고서 텍스트에서 SRO 목록(FINRA 포함, 승인일)과 업무 종류 목록. 못 찾으면 빈 목록."""
    lines = [x.strip() for x in text.splitlines()]
    sros, types = [], []
    try:
        i = next(k for k, x in enumerate(lines) if x.startswith("Self-Regulatory Organization"))
    except StopIteration:
        i = None
    if i is not None:
        for x in lines[i + 1:]:
            m = SRO_LINE.match(x)
            if m:
                sros.append({"name": m.group(1), "since": mdy(m.group(2))})
            elif sros and (x.startswith("©") or x.startswith("U.S. States")):
                break
    m = re.search(r"currently conducts (\d+) types? of business", text)
    if m:
        k = next((j for j, x in enumerate(lines) if x == "Types of Business" and j > 0 and "conducts" in lines[j - 1]), None)
        if k is not None:
            for x in lines[k + 1:]:
                if not x or x.startswith("©") or x.startswith("www.finra.org"):
                    break
                if x.startswith("Other - ") or not types or not types[-1].startswith("Other - "):
                    types.append(x)
                else:  # 'Other - …' 설명이 여러 줄로 이어진다
                    types[-1] += " " + x
    return sros, types


STATUS_HEAD = re.compile(r"Pending\s*Final\s*On\s*Appeal")
STATUS_ROW = re.compile(r"\s*([A-Z][A-Za-z /]*?[A-Za-z])\s+(\d+|N/A)\s+(\d+|N/A)\s+(\d+|N/A)(?![\d/])")


def parse_bc_disclosures(text):
    """상세 보고서의 공시 상태표('Pending Final On Appeal' 다음 '유형 진행 종결 항소' 줄)와 가장 최근 개시일.
    pypdf 글자는 줄바꿈·띄어쓰기가 원문 배치와 다를 수 있어 공백을 하나로 모아 읽는다."""
    s = re.sub(r"\s+", " ", text)
    status = {}
    h = STATUS_HEAD.search(s)
    pos = h.end() if h else len(s)
    while m := STATUS_ROW.match(s, pos):
        n = [0 if g == "N/A" else int(g) for g in m.groups()[1:]]
        status[m.group(1)] = {"pending": n[0], "final": n[1], "appeal": n[2]}
        pos = m.end()
    dates = [mdy(d) for d in re.findall(r"Date Initiated:\s*(\d{2}/\d{2}/\d{4})", text)]
    return status, max(dates) if dates else None


def status_snippet(text):
    """상태표를 못 읽었을 때 실행 기록에 남길 원문 조각(형식이 바뀐 곳을 바로 볼 수 있게)."""
    s = re.sub(r"\s+", " ", text)
    i = s.find("number and status of disclosure")
    return repr(s[i:i + 260]) if i >= 0 else "상태표 안내 문구 없음"


def pdf_text(raw, layout=False):
    """PDF 본문 글자. layout=True는 화면 배치대로(표 칸 순서 유지). pypdf가 없으면 None(그 항목은 이전 값 유지)."""
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    kw = {"extraction_mode": "layout"} if layout else {}
    return "\n".join((p.extract_text(**kw) or "") for p in PdfReader(io.BytesIO(raw)).pages)


def disc_totals(d):
    """공시 유형별 건수(0건 유형은 뺌). 상태표({유형: {pending, final, appeal}})도 합계로."""
    return {t: (sum(v.values()) if isinstance(v, dict) else v) for t, v in (d or {}).items() if v and (not isinstance(v, dict) or sum(v.values()))}


def stale(checked, days=RECHECK_DAYS):
    """마지막 확인일(YYYY-MM-DD)이 없거나 days일 넘게 지났는지."""
    return not checked or checked <= (datetime.now(KST) - timedelta(days=days)).strftime("%Y-%m-%d")


def brokercheck(prev, errors):
    out = dict(prev or {})
    try:
        cur = parse_bc(net.get(BC_API, headers={"Accept": "application/json"}))
        out.update(cur)
        out["checked"] = today()
    except Exception as e:  # noqa: BLE001  네트워크·형식 변경: 이전 값 유지
        errors.append(f"BrokerCheck API: {e}")
        return out
    n = out["counts"]
    same = (len(out.get("sros") or []) == n.get("sro") and len(out.get("types") or []) == n.get("types")
            and disc_totals(out.get("disc_status")) == disc_totals(out["disclosures"]))
    if same and not stale(out.get("sros_checked")) and not stale(out.get("types_checked")):
        return out  # 개수가 그대로면 보고서 PDF는 7일에 한 번
    try:
        raw = net.get(BC_PDF, timeout=60)
        text = pdf_text(raw)
        if text is None:
            errors.append("BrokerCheck 보고서: pypdf 없음(목록은 이전 값)")
            return out
        sros, types = parse_bc_report(text)
        # 목록 개수가 API 개수와 같을 때만 바꾼다(읽기 실패·형식 변경으로 반쪽 목록이 되는 것을 막음)
        if sros and len(sros) == n.get("sro"):
            out["sros"], out["sros_checked"] = sros, today()
        else:
            errors.append(f"BrokerCheck 보고서: SRO {len(sros)}건 ≠ API {n.get('sro')}건(목록은 이전 값)")
        if types and len(types) == n.get("types"):
            out["types"], out["types_checked"] = types, today()
        else:
            errors.append(f"BrokerCheck 보고서: 업무 종류 {len(types)}건 ≠ API {n.get('types')}건(목록은 이전 값)")
        status, latest = parse_bc_disclosures(text)
        if not (status and latest):  # 표 칸이 섞여 나온 경우: 화면 배치대로 다시 읽는다
            text = pdf_text(raw, layout=True)
            status2, latest2 = parse_bc_disclosures(text)
            status, latest = status or status2, latest or latest2
        # 유형별 합계가 API 건수와 같을 때만(진행 중·종결 구분과 가장 최근 개시일)
        if status and disc_totals(status) == disc_totals(out["disclosures"]):
            out["disc_status"], out["disc_latest"] = status, latest
        elif out["disclosures"]:
            errors.append(f"BrokerCheck 보고서: 공시 상태표 {status or '못 읽음'} ≠ API {out['disclosures']}(이전 값)"
                          + ("" if status else f" 원문: {status_snippet(text)}"))
    except Exception as e:  # noqa: BLE001
        errors.append(f"BrokerCheck 보고서: {e}")
    return out


# ---------- EDGAR: 연차 감사보고서(X-17A-5) ----------
def filings(sub):
    """submissions JSON → X-17A-5 공시(최신순). 같은 결산기의 정정본(/A)이 있으면 정정본이 그 해 재무의 출처."""
    r = sub["filings"]["recent"]
    rows = [{k: r[k][i] for k in ("accessionNumber", "filingDate", "reportDate", "form", "primaryDocument")} for i in range(len(r["form"]))]
    out = []
    for x in rows:
        if not x["form"].startswith("X-17A-5"):
            continue
        acc = x["accessionNumber"]
        folder = f"https://www.sec.gov/Archives/edgar/data/{int(CIK)}/{acc.replace('-', '')}/"
        out.append({"form": x["form"], "filed": x["filingDate"], "period": x["reportDate"], "acc": acc,
                    "url": f"{folder}{acc}-index.htm", "folder": folder, "paper": x["primaryDocument"].endswith(".paper")})
    out.sort(key=lambda x: (x["filed"], x["acc"]), reverse=True)
    return out


AMT = r"\$?\s*\(?\s*([\d,]{5,})\s*\)?"


def amount(text, *labels):
    """'Total assets $ 1,234,567' 같은 줄의 금액(달러). 여러 표기 중 처음 맞는 것."""
    for lab in labels:
        m = re.search(rf"(?im)^\s*{lab}\s*[.\s]*{AMT}", text)
        if m:
            return float(m.group(1).replace(",", ""))
    return None


def parse_x17a5(text):
    """공개분 재무상태표와 순자본 주석 → 달러 값. 대차(자산 = 부채 + 지분)가 맞지 않으면 None."""
    t = text.replace("’", "'").replace("‐", "-").replace("‑", "-")
    assets = amount(t, r"Total assets")
    liab = amount(t, r"Total liabilities(?! and)")
    equity = amount(t, r"Total member'?s'? (?:equity|capital)", r"Member'?s'? (?:equity|capital)(?! and)")
    if not (assets and liab is not None and equity):
        return None
    if abs(assets - liab - equity) > max(2.0, assets * 1e-6):  # 달러 단위 표: 합계가 맞아야 한다(반올림 몇 달러만 허용)
        return None
    out = {"assets": assets, "liab": liab, "equity": equity}
    # 순자본 주석: '... had net capital, as defined, of $X which was $Y in excess of its required net capital of $Z'
    # 세 값이 맞물릴 때(순자본 − 초과분 = 요건)만 쓴다
    s = re.sub(r"\s+", " ", t)
    for m in re.finditer(r"net capital[^$]{0,30}\$\s?([\d,]+)[^$]{0,30}\$\s?([\d,]+)[^$]{0,15}in excess of[^$]{0,60}\$\s?([\d,]+)", s, re.I):
        nc, ex, req = (float(g.replace(",", "")) for g in m.groups())
        if abs(nc - ex - req) <= max(2.0, nc * 1e-6):
            out.update({"net_capital": nc, "excess": ex, "required": req})
            break
    return out


def fin_pdf(f):
    """공시 폴더의 공개분 PDF 주소(index.json에서 PDF가 하나이거나 이름에 public이 든 것)."""
    idx = json.loads(sec_get(f["folder"] + "index.json"))
    pdfs = [x["name"] for x in idx.get("directory", {}).get("item", []) if x.get("name", "").lower().endswith(".pdf")]
    pub = [n for n in pdfs if "public" in n.lower()] or pdfs
    return f["folder"] + pub[0] if len(pub) == 1 else None


def edgar(prev, errors):
    """공시 목록과 재무. 재무는 이미 읽은 보고서(접수번호)는 다시 받지 않는다."""
    out = {"filings": (prev or {}).get("filings", []), "fin": (prev or {}).get("fin", [])}
    try:
        sub = json.loads(sec_get(SUBMISSIONS, headers={"Accept": "application/json"}))
    except Exception as e:  # noqa: BLE001
        errors.append(f"EDGAR 목록: {e}")
        return out
    fs = filings(sub)
    out["filings"] = [{k: f[k] for k in ("form", "filed", "period", "acc", "url")} for f in fs[:8]]
    out["checked"] = today()
    out["former_names"] = [{"name": x["name"], "from": x["from"][:10], "to": x["to"][:10]} for x in sub.get("formerNames") or []]
    have = {x["period"]: x for x in out["fin"]}
    latest_by_period = {}
    for f in fs:  # 최신 제출본(정정 포함)만
        if not f["paper"]:
            latest_by_period.setdefault(f["period"], f)
    for period, f in sorted(latest_by_period.items(), reverse=True)[:2]:  # 최근 2개 결산기만 확인
        old = have.get(period)
        if old and old.get("acc") == f["acc"]:
            continue
        try:
            url = fin_pdf(f)
            text = pdf_text(sec_get(url, timeout=60)) if url else None
            vals = parse_x17a5(text) if text else None
        except Exception as e:  # noqa: BLE001
            errors.append(f"X-17A-5 {period}: {e}")
            continue
        if not vals:
            errors.append(f"X-17A-5 {period}: {'PDF 없음' if not url else 'pypdf 없음' if text is None else '재무상태표를 읽지 못함'}(이전 값 유지)")
            continue
        before = next((x for p, x in sorted(have.items(), reverse=True) if p < period and x.get("equity")), None)
        if before and not 0.2 <= vals["equity"] / before["equity"] <= 5:  # 천 달러 단위 표 등으로 자릿수가 어긋난 경우
            errors.append(f"X-17A-5 {period}: 지분 {vals['equity']:,.0f}이 전년 {before['equity']:,.0f}과 자릿수가 다름(이전 값 유지)")
            continue
        have[period] = {"period": period, "acc": f["acc"], "filed": f["filed"], "url": url, **vals, "auto": True}
    out["fin"] = sorted(have.values(), key=lambda x: x["period"], reverse=True)
    return out


# ---------- 회사 누리집: 반기 미감사 재무상태표 ----------
def statement_links(page):
    """누리집 HTML에서 재무상태표 PDF 링크 [(날짜, 주소, 파일 이름)], 최신순. 날짜는 파일 이름의 MM.DD.YYYY."""
    out = set()
    for u in re.findall(r"""["'(]([^"'()<>\s]+?\.pdf)(?=[?#"')])""", page.replace("\\/", "/"), re.I):
        u = urljoin(SITE, u)  # 절대·//·상대 주소 모두
        name = unquote(u.rsplit("/", 1)[-1])
        m = re.search(r"(\d{1,2})[.\-_](\d{1,2})[.\-_](\d{4})", name)
        if m and re.search(r"(?i)financial|statement|condition", name):
            out.add((f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}", u, name))
    return sorted(out, reverse=True)


def interim(prev, fy, errors):
    """감사보고서(fy: 최근 연차 재무)보다 새 재무상태표(반기 미감사). 없거나 감사보고서가 같거나 더 새것이면 None,
    못 받거나 못 읽으면 이전 값."""
    fy_period = (fy or {}).get("period") or ""
    keep = prev if prev and prev.get("period", "") > fy_period else None
    try:
        links = statement_links(net.get(SITE, timeout=30).decode("utf-8", "replace"))
    except Exception as e:  # noqa: BLE001
        errors.append(f"누리집: {e}")
        return keep
    if not links:
        errors.append("누리집: 재무상태표 PDF 링크 없음(이전 값 유지)")
        return keep
    period, url, name = links[0]
    if period <= fy_period:
        return None  # 감사보고서가 같거나 더 새것
    if keep and keep.get("url") == url:
        return {**keep, "checked": today()}  # 이미 읽은 파일
    try:
        text = pdf_text(net.get(url, timeout=60))
    except Exception as e:  # noqa: BLE001
        errors.append(f"누리집 재무상태표 {period}: {e}")
        return keep
    vals = parse_x17a5(text) if text else None
    if not vals:
        errors.append(f"누리집 재무상태표 {period}: {'pypdf 없음' if text is None else '재무상태표를 읽지 못함'}(이전 값 유지)")
        return keep
    if fy and fy.get("equity") and not 0.2 <= vals["equity"] / fy["equity"] <= 5:
        errors.append(f"누리집 재무상태표 {period}: 지분 {vals['equity']:,.0f}이 {fy_period} {fy['equity']:,.0f}과 자릿수가 다름(이전 값 유지)")
        return keep
    # 감사 여부는 파일 이름으로(Unaudited·Audited가 없으면 모름)
    audited = False if re.search(r"(?i)unaudited", name) else True if re.search(r"(?i)audited", name) else None
    return {"period": period, "url": url, **vals, "audited": audited, "checked": today()}


# ---------- 미국 상장 브로커리지(같은 날짜 자본·총자산) ----------
def value_at(units, date, window=92):
    """XBRL 값 목록에서 date 시점 값(10-K·10-Q, 같은 날이 없으면 date 이전 window일 안의 가장 가까운 분기말)."""
    best = None
    for u in units:
        if u.get("form") not in ("10-K", "10-K/A", "10-Q", "10-Q/A") or u.get("start"):
            continue
        end = u["end"]
        if end > date or (datetime.fromisoformat(date) - datetime.fromisoformat(end)).days > window:
            continue
        key = (end, u.get("filed", ""))
        if best is None or key > best[0]:
            best = (key, {"value": u["val"], "end": end, "form": u["form"]})
    return best[1] if best else None


_UNITS = {}


def units_of(cik, tag):
    """companyconcept 값 목록(USD). 그 회사가 안 쓰는 태그(404)는 빈 목록. 한 실행 안에서는 다시 받지 않는다."""
    if (cik, tag) not in _UNITS:
        try:
            _UNITS[(cik, tag)] = json.loads(sec_get(CONCEPT.format(cik=cik, tag=tag)))["units"].get("USD", [])
        except RuntimeError as e:
            if not str(e).startswith("HTTP 404"):
                raise
            _UNITS[(cik, tag)] = []
    return _UNITS[(cik, tag)]


def concept(cik, tags, date):
    """태그 순서대로 date 시점 값(앞 태그 우선)."""
    for tag in tags:
        v = value_at(units_of(cik, tag), date)
        if v:
            return {**v, "tag": tag}
    return None


DUR_FORMS = ("10-K", "10-K/A", "10-Q", "10-Q/A")


def ttm(units, end):
    """end로 끝나는 최근 12개월 값(10-K·10-Q 기간 값). 연간이 end에 끝나면 그 값, 아니면
    직전 연간 + 올해 누적(연간 끝 다음 날부터 end까지) − 전년 같은 기간 누적. 셋 중 하나라도 없으면 None."""
    d = datetime.fromisoformat
    fs = [u for u in units if u.get("start") and u.get("form") in DUR_FORMS and u["end"] <= end]
    days = lambda u: (d(u["end"]) - d(u["start"])).days  # noqa: E731
    last = lambda c: max(c, key=lambda u: u.get("filed", "")) if c else None  # noqa: E731  같은 기간은 가장 최근 제출(정정 반영)
    ann = [u for u in fs if 350 <= days(u) <= 380]
    if not ann:
        return None
    a_end = max(u["end"] for u in ann)
    a = last([u for u in ann if u["end"] == a_end])
    if a_end == end:
        return {"value": a["val"], "end": end, "how": "FY"}
    nxt = d(a_end) + timedelta(days=1)
    cur = last([u for u in fs if u["end"] == end and abs((d(u["start"]) - nxt).days) <= 3])
    if not cur:
        return None
    pre = last([u for u in fs if u["end"] < a_end and abs((d(u["start"]) - d(a["start"])).days) <= 3 and abs(days(u) - days(cur)) <= 5])
    if not pre:
        return None
    return {"value": a["val"] + cur["val"] - pre["val"], "end": end, "how": f"FY {a_end} + YTD {days(cur) + 1}일 − 전년 YTD"}


def ni_ttm(cik, end, nci):
    """자본과 범위가 같은 최근 12개월 순이익: 비지배지분 포함 자본이면 ProfitLoss, 아니면 NetIncomeLoss를 먼저 본다."""
    for tag in (["ProfitLoss", "NetIncomeLoss"] if nci else ["NetIncomeLoss", "ProfitLoss"]):
        v = ttm(units_of(cik, tag), end)
        if v:
            return {**v, "tag": tag}
    return None


def peers(prev, date, errors):
    """Velocity 결산일(date)과 같은 시점의 상장사 자본·총자산. 실패한 회사는 이전 값."""
    P = prev or {}
    tickers = [t for _, t, _, _ in PEERS]
    if (P.get("date") == date and [r.get("ticker") for r in P.get("rows", [])] == tickers
            and all(r.get("ok") and "ni" in r for r in P["rows"]) and not stale(P.get("checked"))):
        return P  # 같은 날짜 값은 바뀌지 않는다: 7일에 한 번만 다시 확인
    old = {r["ticker"]: r for r in P.get("rows", [])} if P.get("date") == date else {}
    rows = []
    for name, ticker, cik, model in PEERS:
        row = {"name": name, "ticker": ticker, "cik": cik, "model": model}
        try:
            row["equity"] = concept(cik, EQUITY_TAGS, date)
            row["assets"] = concept(cik, ASSET_TAGS, date)
            e = row["equity"]
            row["ni"] = ni_ttm(cik, e["end"], e["tag"] != "StockholdersEquity") if e else None
            row["ok"] = bool(row["equity"])
        except Exception as e:  # noqa: BLE001
            errors.append(f"SEC {ticker}: {e}")
            row.update({k: v for k, v in old.get(ticker, {}).items() if k in ("equity", "assets", "ni")})
            row["ok"] = False
        rows.append(row)
    return {"date": date, "rows": rows, "checked": today()}


# ---------- 뉴스 ----------
def parse_news(xml_bytes, lang, since):
    items = []
    for it in ET.fromstring(xml_bytes).iter("item"):
        title, src = (it.findtext("title") or "").strip(), (it.findtext("source") or "").strip()
        if src and title.endswith(f" - {src}"):
            title = title[: -len(src) - 3].strip()
        hit = ("velocity clearing" in title.lower()) if lang == "en" else ("벨로시티" in title)
        if not hit:
            continue
        try:
            when = parsedate_to_datetime(it.findtext("pubDate")).astimezone(KST)
        except Exception:  # noqa: BLE001
            continue
        if when < since:
            continue
        items.append({"date": when.strftime("%Y-%m-%d"), "title": title, "src": src, "url": (it.findtext("link") or "").strip(), "lang": lang})
    return items


def news(prev, errors):
    since = datetime.now(KST) - timedelta(days=NEWS_DAYS)
    found = []
    for q, lang in NEWS_Q:
        try:
            found += parse_news(net.get(rss_url(q, lang, NEWS_DAYS), timeout=25), lang, since)
        except Exception as e:  # noqa: BLE001
            errors.append(f"뉴스 {q}: {e}")
    # 이전 기사와 합쳐 제목이 같은 기사는 하나만, 최신순
    seen, out = set(), []
    for x in sorted(found + list(prev or []), key=lambda x: x["date"], reverse=True):
        k = re.sub(r"[^0-9a-z가-힣]", "", x["title"].lower())[:40]
        if k in seen or x["date"] < since.strftime("%Y-%m-%d"):
            continue
        seen.add(k)
        out.append(x)
    return out[:NEWS_MAX]


def today():
    return datetime.now(KST).strftime("%Y-%m-%d")


def usd(v):
    return "—" if v is None else f"{v:,.0f}"


def report_dart(dt):
    """한화생명 공시 값(백만원): 원문 표와 바로 맞춰 볼 수 있게 그대로."""
    if not dt:
        return
    print(f"DART 한화생명({dt.get('corp_code')}) {dt.get('checked')}: 정기보고서 {len(dt.get('periods', []))}건, 건너뜀 {len(dt.get('skip', []))}건")
    for p in dt.get("periods", []):
        print(f"  {p['label']} {p['report']['name']} ({p['report']['rcept_no']}) 지분율 {p.get('stakes')}")
        for k, v in p["subs"].items():
            print(f"    {k:5} {v.get('name')}: 자산 {usd(v.get('assets'))} · 부채 {usd(v.get('liab'))} · 자본 {usd(v.get('equity'))}"
                  f" · 영업수익 {usd(v.get('rev'))} · 순이익 {usd(v.get('ni'))} · 총포괄 {usd(v.get('tci'))}")
    inv = dt.get("invest") or {}
    if inv:
        print(f"  출자 {inv.get('label')} {inv['report']['name']} (원자료 단위 {inv.get('unit_raw')}): {json.dumps(inv.get('rows'), ensure_ascii=False)}")


def report(bc, ed, it, pe, nw, errors):
    """실행 기록(Actions 로그)에 남길 요약: 숫자를 원문과 맞춰 볼 수 있게."""
    n = bc.get("counts") or {}
    print(f"BrokerCheck {bc.get('checked')}: SEC {n.get('sec')} · SRO {n.get('sro')}(목록 {len(bc.get('sros') or [])}, {bc.get('sros_checked')})"
          f" · 주 {n.get('states')} · 업무 {n.get('types')}(목록 {len(bc.get('types') or [])}) · 공시 {bc.get('disclosures')}"
          f" 상태 {bc.get('disc_status')} 최근 개시 {bc.get('disc_latest')}")
    print(f"EDGAR {ed.get('checked')}: X-17A-5 {len(ed.get('filings', []))}건, 최근 {(ed.get('filings') or [{}])[0].get('filed')}")
    # 재무는 PDF 표와 바로 맞춰 볼 수 있게 달러 그대로
    if it:
        print(f"  누리집 {it['period']} {'감사' if it.get('audited') else '미감사' if it.get('audited') is False else ''}: 자산 {usd(it.get('assets'))}"
              f" · 부채 {usd(it.get('liab'))} · 지분 {usd(it.get('equity'))} · 순자본 {usd(it.get('net_capital'))} − 초과 {usd(it.get('excess'))}"
              f" = 요건 {usd(it.get('required'))} ({it['url']})")
    for f in ed.get("fin", [])[:3]:
        print(f"  {f['period']} {'자동' if f.get('auto') else '확인값'}: 자산 {usd(f.get('assets'))} · 부채 {usd(f.get('liab'))}"
              f" · 지분 {usd(f.get('equity'))} · 순자본 {usd(f.get('net_capital'))} − 초과 {usd(f.get('excess'))} = 요건 {usd(f.get('required'))}")
    rows = (pe or {}).get("rows", [])
    print(f"상장사 {sum(bool(r.get('ok')) for r in rows)}/{len(rows)} ({(pe or {}).get('date')}, {(pe or {}).get('checked')})")
    for r in rows:  # 10-K 표와 바로 맞춰 볼 수 있게 달러 그대로
        e, a, ni = r.get("equity") or {}, r.get("assets") or {}, r.get("ni") or {}
        roe = f"{ni['value'] / e['value'] * 100:.1f}%" if ni.get("value") is not None and e.get("value") else "—"
        print(f"  {r['ticker']:5} 자본 {usd(e.get('value')):>19} ({e.get('end')} {e.get('form')} {e.get('tag')})"
              f" · 총자산 {usd(a.get('value')):>21} ({a.get('end')} {a.get('form')})"
              f" · 순이익 12개월 {usd(ni.get('value')):>16} ({ni.get('tag')} {ni.get('how')}) · ROE {roe}")
    print(f"뉴스 {len(nw)}건", *[f"  {x['date']} {x['title'][:70]}" for x in nw], sep="\n")
    if errors:
        print("오류(이전 값 유지):", *[f"  {e}" for e in errors], sep="\n")


def main():
    prev = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    errors = []
    bc = brokercheck(prev.get("brokercheck"), errors)
    ed = edgar(prev.get("edgar"), errors)
    fy = (ed.get("fin") or [None])[0]
    it = interim(prev.get("interim"), fy, errors)
    date = it["period"] if it else (fy or {}).get("period")  # 순위는 가장 최근 재무 날짜로
    pe = peers(prev.get("peers"), date, errors) if date else prev.get("peers")
    dt = velocity_dart.collect(prev.get("dart"), errors)
    n_err = len(errors)
    nw = news(prev.get("news"), errors)
    news_ok = len(errors) == n_err  # 두 검색이 모두 됐을 때만 확인일을 바꾼다
    out = {"updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "brokercheck": bc, "edgar": ed, "interim": it, "peers": pe, "dart": dt, "news": nw,
           "news_checked": today() if news_ok else prev.get("news_checked"), "errors": errors}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    report(bc, ed, it, pe, nw, errors)
    report_dart(dt)


if __name__ == "__main__":
    main()
