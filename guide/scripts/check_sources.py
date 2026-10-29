"""해외진출 유의사항·해외지분투자 Workflow 탭: 반기 1회 법령·규정 원문 변경 점검(LLM 미사용, 표준 라이브러리만).

두 탭 데이터(guide/data/countries.json, workflow/data/steps.json)와 Workflow 별첨 1(workflow/data/us_entry.json)이 인용한 출처를 다시 열어 바뀌었는지 본다.
- 해외 공식 원문(감독당국·법령 사이트): 본문 텍스트 해시를 지난번 값과 비교한다. FINRA 규칙은 조문 끝의 개정 이력 줄,
  쪽마다 갱신일을 게시하는 SFC는 그 날짜, eCFR(미 연방규정)은 공식 API의 개정 이력으로 비교한다(쪽 꾸밈 변경 오탐·접근 제한 화면 방지).
- 그 밖의 출처(로펌 해설·기사·세율 요약): 링크가 살아 있는지만 본다(본문이 자주 바뀌어 해시 비교는 오탐이 많음).
- --baseline-only(병합 때): 기준값이 없는 새 출처만 열어 기준값을 잡는다. 비교·이슈는 반기 점검에서만 한다.
- 국내 법령·고시: 국가법령정보센터 Open API(LAW_OC 시크릿)가 있으면 시행일·공포일을 비교한다. 없으면 건너뛴다.
- 'assert'가 붙은 단계(예: 자본시장법 제418조 '7일')는 조문 원문에서 문구를 찾아 확인되면 화면의 요확인을 자동으로 지운다.

결과는 guide/data/source_status.json 에 쌓는다. 바뀐 출처가 있으면 해당 행에 '개정 감지·검토 필요'를 띄우고,
--issue 경로에 GitHub 이슈 본문을 써서 워크플로가 이슈를 연다. 요약 문구는 자동으로 고치지 않는다(사람이 원문을 읽고 수정).
"""
import argparse
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from keys import get_key  # noqa: E402  API 키: 환경변수 → 로컬 .env → 터미널 실행 시 숨김 입력
from net import get  # noqa: E402

GUIDE = ROOT / "guide" / "data" / "countries.json"
STEPS = ROOT / "workflow" / "data" / "steps.json"
US = ROOT / "workflow" / "data" / "us_entry.json"  # 별첨 1 · 미국 진출(출처 URL별 점검 결과를 화면이 직접 읽음)
OUT = ROOT / "guide" / "data" / "source_status.json"
KST = timezone(timedelta(hours=9))

# 본문 해시로 변경을 보는 공식 원문 사이트(감독당국·법령집). 나머지는 링크 확인만.
OFFICIAL_HOSTS = [
    "ssc.gov.vn", "hethongphapluat.com", "peraturan.bpk.go.id", "ojk.go.id", "mas.gov.sg", "sso.agc.gov.sg", "adgm.com",
    "finra.org", "ecfr.gov", "sec.gov", "fsa.go.jp", "sfc.hk", "elegislation.gov.hk", "csrc.gov.cn", "fca.org.uk",
    "dpiit.gov.in", "rbi.org.in", "sebi.gov.in", "frc.mn", "mse.mn", "bcb.gov.br", "sec.or.th", "serc.gov.kh",
    "nysenate.gov",
]
# 해시 계산 방식이 바뀌면 올린다(지난 값과 비교하지 않고 기준값을 다시 잡음)
# 3: FINRA 규칙은 개정 이력 줄, SFC는 게시 갱신일, eCFR는 공식 API 개정 이력으로 비교
#    (2026-10-29 이슈 #20: 내용은 그대로인데 쪽 꾸밈만 바뀐 오탐. eCFR 본문 쪽은 자동 접속에 같은 접근 제한 화면을 줌)
#    본문 해시 방식은 2와 같아서, 그 출처들은 2026-10-29 기준값을 그대로 v 3으로 옮겼다
SIG_V = 3

# 같은 사이트를 몰아서 열면 막는 곳이 있다(FINRA: 429). 사이트별 최소 간격(초), 목록에 없으면 1초
GAP = {"finra.org": 6.0}
PERMANENT = ("HTTP 400", "HTTP 401", "HTTP 403", "HTTP 404")  # 다시 열어도 같은 오류
LIMITED = ("HTTP 429", "HTTP 503")  # 속도 제한: 45초 쉬고 한 번 더
# SEC는 연락처(이메일)가 든 User-Agent가 없으면 403(scripts/update_sec.py 와 같은 값)
SEC_UA = os.environ.get("SEC_USER_AGENT") or \
    "HanwhaGlobalNetworkDashboard jeongpilchoi1992-hash@users.noreply.github.com"
# 쪽마다 갱신일('Last update: 22 Jan 2020' 또는 meta 날짜)을 게시하는 감독당국: 그 날짜로 비교
DATED = ["sfc.hk"]
DATE_RE = r"\d{4}-\d{2}-\d{2}|\d{1,2}\s+[A-Za-z]{3,9}\.?\s+\d{4}"
# FINRA 규칙 조문 끝의 개정 이력('Amended by SR-FINRA-2020-011 eff. Sept. 1, 2021.'): 조문이 바뀌면 줄이 늘어난다
AMEND = re.compile(r"(?i)\b(?:amended|adopted|deleted|renumbered|redesignated)\b[\w ,]{0,40}?\bby SR-.{0,200}?\beff\.\s.{0,30}?\b(?:19|20)\d{2}\b")
# 봇 차단·확인 화면은 200으로 와도 원문이 아니다(해시하면 오탐 또는 '변경 없음' 착시)
CHALLENGE = re.compile(r"(?i)just a moment\.\.\.|attention required|access denied|request rejected|enable javascript and cookies"
                       r"|aggressive automated scraping|programmatic access to these sites")
_last, _throttled = {}, set()

# 국가법령정보센터 Open API로 시행일을 보는 국내 법령·고시. key 는 출처 제목에서 찾는 말.
KR_LAWS = [
    {"name": "자본시장과 금융투자업에 관한 법률", "target": "law", "key": ["자본시장법", "자본시장과 금융투자업"]},
    {"name": "자본시장과 금융투자업에 관한 법률 시행령", "target": "law", "key": ["시행령 제371조", "시행령 제171조"]},
    {"name": "외국환거래법", "target": "law", "key": ["외국환거래법"]},
    {"name": "국제조세조정에 관한 법률", "target": "law", "key": ["국제조세조정", "국조법"]},
    {"name": "외국환거래규정", "target": "admrul", "key": ["외국환거래규정"]},
    {"name": "금융회사등의 해외진출에 관한 규정", "target": "admrul", "key": ["해외진출규정", "해외진출에 관한 규정"]},
    {"name": "금융투자업규정", "target": "admrul", "key": ["금융투자업규정"]},
]
DRF = "https://www.law.go.kr/DRF"


def host(u):
    return urllib.parse.urlsplit(u).hostname or ""


def is_official(u):
    """공식 원문 페이지인지. 감독당국 첫 화면(경로 1단 이하, 예: csrc.gov.cn/csrc_en/)은 새 소식마다 바뀌므로 링크만 본다."""
    h = host(u)
    parts = urllib.parse.urlsplit(u)
    home = not parts.query and len([x for x in parts.path.split("/") if x]) <= 1
    return not home and any(h == d or h.endswith("." + d) for d in OFFICIAL_HOSTS)


def normalize(raw):
    """HTML/PDF 바이트에서 비교용 텍스트만 남긴다(스크립트·태그·공백 제거)."""
    t = raw.decode("utf-8", "replace")
    t = re.sub(r"(?is)<(script|style|noscript|header|footer|nav)\b.*?</\1>", " ", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = html.unescape(t)
    # 방문 때마다 바뀌는 시각·토큰·긴 숫자열(조회수·세션 값)은 비교에서 뺀다
    t = re.sub(r"\b\d{1,2}:\d{2}(:\d{2})?\b|\b[0-9a-fA-F]{16,}\b|\b\d{8,}\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def site(u):
    h = host(u)
    return next((d for d in GAP if h == d or h.endswith("." + d)), h)


def polite_get(u):
    """사이트별 간격을 두고 연다. 429·503이면 45초, 그 밖의 일시 오류는 간격만 두고 한 번 더 연다.
    두 번 다 속도 제한이면 그 사이트는 이번 점검에서 건너뛴다(막힌 사이트를 계속 두드리지 않음)."""
    s = site(u)
    if s in _throttled:
        raise RuntimeError("HTTP 429: 속도 제한(이번 점검 건너뜀)")
    hdr = {"User-Agent": SEC_UA} if s == "sec.gov" or s.endswith(".sec.gov") else None
    for attempt in range(2):
        wait = _last.get(s, float("-inf")) + GAP.get(s, 1.0) - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        try:
            return get(u, headers=hdr, retries=1, timeout=40)  # 재시도는 여기서만(net.get 의 2초 재시도는 끔)
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if attempt or msg.startswith(PERMANENT):
                if attempt and msg.startswith(LIMITED):
                    _throttled.add(s)
                raise
            if msg.startswith(LIMITED):
                time.sleep(45)
        finally:
            _last[s] = time.monotonic()


def posted_date(raw):
    """쪽에 게시된 갱신일: 본문의 'Last update: 22 Jan 2020'과 이름이 date·modified·updated인 meta 날짜(여럿이면 모두)."""
    found = re.findall(rf"(?is)last\s+update[ds]?\s*:?\s*(?:<[^>]+>\s*)*({DATE_RE})", raw)
    for tag in re.findall(r"(?is)<meta\b[^>]*>", raw):
        name = re.search(r"""\b(?:name|property|itemprop)\s*=\s*["']([^"']+)["']""", tag, re.I)
        val = re.search(r"""\bcontent\s*=\s*["']\s*([^"']+)["']""", tag, re.I)
        # msvalidate 같은 이름은 빼고, 값이 날짜일 때만(시각은 버림)
        d = val and re.match(DATE_RE, val.group(1))
        if name and d and re.search(r"(?i)(?:^|[^a-z])(?:date|modified|updated)(?:$|[^a-z])", name.group(1)):
            found.append(d.group(0))
    return "|".join(sorted({" ".join(f.split()) for f in found})) or None


def ecfr_api(u):
    """eCFR 본문 쪽 주소 → 공식 개발자 API(versioner)의 개정 이력 주소. eCFR가 아니면 None."""
    if not host(u).endswith("ecfr.gov"):
        return None
    m = re.search(r"/current/title-(\d+)(?:/.*?)?/(section|part)-([\w.\-]+)$", urllib.parse.urlsplit(u).path)
    return m and f"https://www.ecfr.gov/api/versioner/v1/versions/title-{m.group(1)}.json?{m.group(2)}={m.group(3)}"


def ecfr_signature(raw):
    vs = json.loads(raw).get("content_versions") or []
    rows = sorted(f'{v.get("amendment_date")}|{v.get("identifier")}|{v.get("removed")}' for v in vs)
    if not rows:
        raise RuntimeError("eCFR 개정 이력 없음")
    return "ecfr:" + hashlib.sha256("\n".join(rows).encode()).hexdigest()[:16]


def signature(u, raw):
    """비교용 값. FINRA 규칙은 개정 이력 줄, 갱신일을 게시하는 사이트는 그 날짜, 그 밖에는 본문 텍스트 해시."""
    t = normalize(raw)
    if CHALLENGE.search(t[:3000]):
        raise RuntimeError("봇 확인 화면(원문 아님)")
    if site(u) == "finra.org" and "/rulebooks/" in u:
        lines = AMEND.findall(t)
        if not lines:
            raise RuntimeError("FINRA 개정 이력 줄을 찾지 못함")
        return "amend:" + hashlib.sha256("|".join(lines).encode()).hexdigest()[:16]
    h = host(u)
    if any(h == d or h.endswith("." + d) for d in DATED):
        d = posted_date(raw.decode("utf-8", "replace"))
        if d:
            return "date:" + d
    return hashlib.sha256(t.encode()).hexdigest()[:16]


def fingerprint(u):
    api = ecfr_api(u)
    return ecfr_signature(polite_get(api)) if api else signature(u, polite_get(u))


def has_baseline(u, p):
    """지금 방식(SIG_V)의 기준값이 있는지. 지금 분류로 링크 확인만 하는 출처는 한 번 열렸으면 된다."""
    if not p.get("checked"):
        return False
    if not is_official(u):
        return True
    return p.get("v") == SIG_V and ("sig" in p or p.get("kind") == "가변")


def collect():
    """행(국가 코드 또는 단계 id)별 출처 목록과 assert 목록."""
    g = json.loads(GUIDE.read_text(encoding="utf-8"))
    w = json.loads(STEPS.read_text(encoding="utf-8"))
    rows, asserts = {}, {}
    for c in g["countries"]:
        rows[c["code"]] = [{"t": s["t"], "u": s["u"]} for s in c["sources"]]
    for s in w["steps"]:
        rows[s["id"]] = [{"t": r["t"], "u": r["u"]} for r in s["src"] if r["u"].startswith("http")]
        if s.get("assert"):
            asserts[s["id"]] = s["assert"]
    if US.exists():
        u = json.loads(US.read_text(encoding="utf-8"))
        rows["annex-us"] = [{"t": s["t"], "u": s["u"]} for s in u["sources"].values()]
    return rows, asserts


def law_keys(title):
    return [x["name"] for x in KR_LAWS if any(k in title for k in x["key"])]


# ---------- 국가법령정보센터 Open API ----------
def drf_search(oc, law):
    data = json.loads(get(f"{DRF}/lawSearch.do", {"OC": oc, "target": law["target"], "type": "JSON", "query": law["name"]}))
    root = data.get("LawSearch") or data.get("AdmRulSearch") or {}
    items = root.get("law") or root.get("admrul") or []
    if isinstance(items, dict):
        items = [items]
    nm = law["name"].replace(" ", "")
    for it in items:
        title = (it.get("법령명한글") or it.get("행정규칙명") or "").replace(" ", "")
        if title == nm:
            return {
                "id": it.get("법령일련번호") or it.get("행정규칙일련번호"),
                "promulgated": it.get("공포일자") or it.get("발령일자"),
                "effective": it.get("시행일자"),
            }
    return None


def article_text(blob, jo):
    """법령 본문(JSON 문자열이나 HTML 텍스트)에서 '제N조' 부분만 잘라낸다."""
    m = re.search(rf"제\s*{jo}\s*조\s*\(", blob)
    if not m:
        return ""
    nxt = re.search(rf"제\s*{jo + 1}\s*조\s*\(", blob[m.end():])
    return blob[m.start(): m.end() + (nxt.start() if nxt else 4000)]


def check_assert(a, oc, law_meta):
    """조문에 기대 문구가 있는지. 법령 API가 있으면 원문, 없으면 법령 사본 사이트(alt)로 본다."""
    if oc and law_meta.get(a["law"], {}).get("id"):
        blob = get(f"{DRF}/lawService.do", {"OC": oc, "target": "law", "type": "JSON", "MST": law_meta[a["law"]]["id"]}).decode("utf-8", "replace")
        via = "국가법령정보센터"
    elif a.get("alt"):
        blob = normalize(get(urllib.parse.quote(a["alt"], safe=":/"), retries=2))
        via = host(a["alt"])
    else:
        return None
    part = article_text(blob, a["jo"])
    if not part:
        return None
    return {"ok": a["has"] in part, "via": via}


def run(prev, today, oc, fetch=fingerprint, alive=None, search=drf_search, asserter=check_assert, baseline_only=False):
    alive = alive or (lambda u: bool(polite_get(u)))
    rows, asserts = collect()
    src = prev.get("sources", {})
    laws = prev.get("laws", {})
    newly = []

    # 1) 국내 법령·고시 시행일 비교
    if oc and not baseline_only:
        for law in KR_LAWS:
            p = laws.get(law["name"], {})
            try:
                cur = search(oc, law)
            except Exception as e:  # noqa: BLE001
                p["err"] = str(e)[:120]
                laws[law["name"]] = p
                continue
            if not cur:
                p["err"] = "검색 결과 없음"
                laws[law["name"]] = p
                continue
            sig = f'{cur["effective"]}|{cur["promulgated"]}'
            if p.get("sig") and p["sig"] != sig:
                p["changed_at"] = today
                newly.append(("법령", law["name"], f'시행 {cur["effective"]} · 공포 {cur["promulgated"]}', "https://www.law.go.kr"))
            p.update({"sig": sig, "id": cur["id"], "effective": cur["effective"], "promulgated": cur["promulgated"], "checked": today})
            p.pop("err", None)
            laws[law["name"]] = p

    # 2) 출처 원문
    seen = set()
    for _, lst in rows.items():
        for s in lst:
            u = s["u"]
            if u in seen or host(u).endswith("law.go.kr"):
                continue
            seen.add(u)
            p = src.get(u, {})
            # 병합 때는 기준값이 없는 출처만 연다(며칠 사이 비교는 쪽 꾸밈 변경 오탐이 잦아 반기 점검에서만 비교)
            if baseline_only and has_baseline(u, p):
                continue
            p["kind"] = "원문" if is_official(u) else "링크"
            try:
                if p["kind"] == "원문":
                    # 연달아 두 번 받아 다르면 페이지 자체가 가변: 오탐을 막으려고 링크 확인만 한다
                    sig = fetch(u)
                    if fetch(u) != sig:
                        p["kind"] = "가변"
                        p.pop("sig", None)
                    else:
                        if p.get("sig") and p.get("v") == SIG_V and p["sig"] != sig:
                            p["changed_at"] = today
                            newly.append(("원문", s["t"], u, u))
                        p["sig"], p["v"] = sig, SIG_V
                else:
                    alive(u)
                p["checked"] = today
                p.pop("err", None)
            except Exception as e:  # noqa: BLE001
                p["err"] = str(e)[:120]
            src[u] = p

    # 3) 행별 요약: 마지막 원문 점검일, 개정 감지 목록
    out_rows = {}
    for rid, lst in rows.items():
        changed, ok_dates = [], []
        for s in lst:
            if host(s["u"]).endswith("law.go.kr"):
                for name in law_keys(s["t"]):
                    lp = laws.get(name, {})
                    if lp.get("changed_at"):
                        changed.append({"t": name, "u": s["u"], "at": lp["changed_at"]})
                    if lp.get("checked"):
                        ok_dates.append(lp["checked"])
                continue
            p = src.get(s["u"], {})
            if p.get("changed_at"):
                changed.append({"t": s["t"], "u": s["u"], "at": p["changed_at"]})
            if p.get("checked") and p.get("kind") == "원문":
                ok_dates.append(p["checked"])
        r = {"checked": max(ok_dates) if ok_dates else None}
        if changed:
            r["changed"] = changed
        out_rows[rid] = r

    # 4) 조문 문구 자동 대조
    for rid, a in asserts.items():
        res = None
        if not baseline_only:
            try:
                res = asserter(a, oc, laws)
            except Exception as e:  # noqa: BLE001
                res = {"ok": None, "err": str(e)[:120]}
        if res:
            out_rows.setdefault(rid, {})["assert"] = {**res, "checked": today}
        elif (prev.get("rows", {}).get(rid) or {}).get("assert"):
            out_rows.setdefault(rid, {})["assert"] = prev["rows"][rid]["assert"]

    return {
        "updated": prev.get("updated", today) if baseline_only else today,  # 원문 점검일은 비교한 날만
        "law_api": bool(oc),
        "sources": src,
        "laws": laws,
        "rows": out_rows,
    }, newly


def issue_body(newly, today):
    lines = [f"반기 원문 점검({today})에서 아래 출처가 지난 점검 이후 바뀌었습니다.", "",
             "요약 문구는 자동으로 고치지 않습니다. 원문을 읽고 `guide/data/countries.json`, `workflow/data/steps.json` 또는 `workflow/data/us_entry.json`의 해당 문구와 검증일(`checked`·`verified_at`)을 고치면 화면의 '개정 감지·검토 필요' 표시가 사라집니다.", ""]
    for kind, t, detail, u in newly:
        lines.append(f"- [{kind}] {t}: {detail if kind == '법령' else u}")
    lines += ["", "자동 생성(LLM 미사용): `.github/workflows/source-check.yml`"]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--issue", help="바뀐 출처가 있으면 GitHub 이슈 본문을 쓸 경로")
    ap.add_argument("--baseline-only", action="store_true", help="새 출처의 기준값만 잡는다(비교·이슈 없음, 병합 때)")
    args = ap.parse_args()
    prev = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    today = datetime.now(KST).strftime("%Y-%m-%d")
    oc = get_key("LAW_OC")
    status, newly = run(prev, today, oc, baseline_only=args.baseline_only)
    OUT.write_text(json.dumps(status, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    n_err = sum(1 for p in status["sources"].values() if p.get("err"))
    mode = "baseline only" if args.baseline_only else "compare"
    print(f"{mode} · sources {len(status['sources'])} · errors {n_err} · law api {'on' if oc else 'off'} · changed {len(newly)}")
    if newly and args.issue:
        Path(args.issue).write_text(issue_body(newly, today), encoding="utf-8")


if __name__ == "__main__":
    main()
