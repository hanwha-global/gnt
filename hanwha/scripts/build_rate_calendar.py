"""주요국 금리 결정 일정을 중앙은행 공식 페이지에서 받아 hanwha/data/rate_calendar.json을 다시 만든다.

- 공식 페이지를 읽을 수 있는 은행(Fed·ECB·BoE·BoJ·BoC 등)은 그 날짜를 쓰고 source="공식"으로 둔다.
- 규칙으로 정해지는 일정(중국 LPR: 매월 20일, 휴일이면 다음 영업일)은 source="규칙".
- 읽지 못한 은행은 FALLBACK 목록(사람이 공표 일정을 옮겨 적은 것)을 쓰고 source="보조"로 표시한다.
- 화면은 이번 달과 다음 달을 보여 준다. 파일에는 지난 30일~앞으로 13개월을 모두 담는다.

평일 GitHub Actions(hanwha-markets.yml)에서 실행한다. 표준 라이브러리만 쓰고 LLM 토큰은 쓰지 않는다.
날짜는 결정이 발표되는 한국 날짜(KST)로 적는다. 미국 FOMC는 둘째 날 14:00 ET 발표라 한국 날짜로 다음 날이다.
"""
import datetime as dt
import html
import json
import re
import sys
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "rate_calendar.json"
KST = dt.timezone(dt.timedelta(hours=9))
UA = {"User-Agent": "Mozilla/5.0 (compatible; global-network-dashboard/1.0)"}
MONTHS = {m: i + 1 for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july",
                                          "august", "september", "october", "november", "december"])}
MON_RE = "(" + "|".join(MONTHS) + "|" + "|".join(m[:3] for m in MONTHS) + r")\.?"

BANKS = {
    "US": ("미국 FOMC", "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"),
    "EU": ("ECB", "https://www.ecb.europa.eu/press/calendars/mgcgc/html/index.en.html"),
    "UK": ("영국 BoE", "https://www.bankofengland.co.uk/monetary-policy/upcoming-mpc-dates"),
    "JP": ("일본 BOJ", "https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm"),
    "CA": ("캐나다 BoC", "https://www.bankofcanada.ca/press/upcoming-events/"),
    "KR": ("한국 금통위", "https://www.bok.or.kr/eng/main/contents.do?menuNo=400069"),
    "ID": ("인니 BI", "https://www.bi.go.id/en/fungsi-utama/moneter/rapat-dewan-gubernur/default.aspx"),
    "IN": ("인도 RBI", "https://www.rbi.org.in/Scripts/Annualpolicy.aspx"),
    "CN": ("중국 LPR", None),
}

# 공식 페이지를 못 읽을 때 쓰는 일정(각 은행 공표 기준, KST 발표일). 새해 일정이 공표되면 여기에 추가한다.
FALLBACK = {
    "KR": [("2026-10-22", "통화정책방향 결정"), ("2026-11-26", "연내 마지막 결정회의")],
    "ID": [("2026-10-21", "10/20~21 이사회"), ("2026-11-18", ""), ("2026-12-17", "")],
    "IN": [("2026-12-04", "")],
    "CA": [("2026-10-28", "MPR 발표"), ("2026-12-09", "")],
    "US": [("2026-10-29", "10/27~28"), ("2026-12-10", "12/8~9 · 경제전망(SEP)")],
    "EU": [("2026-10-29", "10/28~29"), ("2026-12-17", "12/16~17 · 경제전망")],
    "UK": [("2026-11-05", "MPR 발표"), ("2026-12-17", "")],
    "JP": [("2026-10-30", "10/29~30"), ("2026-12-18", "12/17~18")],
}


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def text_of(page):
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", page)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", html.unescape(t))


def mnum(s):
    s = s.lower().rstrip(".")
    return MONTHS.get(s) or next(v for k, v in MONTHS.items() if k.startswith(s))


def biz_next(d):
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d


# ---------- 은행별 파서: [(date, note)] ----------
def parse_fed(page):
    """'2026 FOMC Meetings' 구획마다 월·날짜(예: 'October 27-28*')를 읽는다. 발표 KST = 둘째 날 + 1일."""
    out = []
    t = text_of(page)
    for m in re.finditer(r"(20\d\d) FOMC Meetings(.*?)(?=20\d\d FOMC Meetings|$)", t):
        y, body = int(m.group(1)), m.group(2)
        for mm in re.finditer(MON_RE + r"(?:/" + MON_RE + r")?\s+(\d{1,2})\s*-\s*(\d{1,2})(\*)?", body, re.I):
            mon = mnum(mm.group(2) or mm.group(1))
            d2 = int(mm.group(4))
            try:
                day = dt.date(y, mon, d2) + dt.timedelta(days=1)
            except ValueError:
                continue
            out.append((day, f"{mnum(mm.group(1))}/{mm.group(3)}~{d2}" + (" · 경제전망(SEP)" if mm.group(5) else "")))
    return out


def parse_ecb(page):
    """'dd/mm/yyyy ... Monetary policy meeting ... Day 2' 또는 'press conference' 줄을 읽는다."""
    out = []
    t = text_of(page)
    for m in re.finditer(r"(\d{2})/(\d{2})/(20\d\d)\s+(.{0,240}?)(?=\d{2}/\d{2}/20\d\d|$)", t):
        desc = m.group(4).lower()
        if "monetary policy" in desc and ("day 2" in desc or "press conference" in desc):
            out.append((dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))), ""))
    return out


def parse_boe(page):
    """연도 제목 아래 'Thursday 5 February' 형식."""
    out = []
    t = text_of(page)
    year = None
    for tok in re.finditer(r"\b(20\d\d)\b|(Monday|Tuesday|Wednesday|Thursday|Friday)\s+(\d{1,2})\s+" + MON_RE, t, re.I):
        if tok.group(1):
            year = int(tok.group(1))
        elif year:
            try:
                out.append((dt.date(year, mnum(tok.group(4)), int(tok.group(3))), ""))
            except ValueError:
                pass
    return out


def parse_boj(page):
    """'2026' 표 아래 'October 29 (Thu.), 30 (Fri.)' 형식. 결정일 = 둘째 날."""
    out = []
    t = text_of(page)
    year = None
    pat = r"\b(20\d\d)\b|" + MON_RE + r"\s+(\d{1,2})\s*\(\w+\.?\)\s*,\s*(?:" + MON_RE + r"\s+)?(\d{1,2})\s*\(\w+\.?\)"
    for tok in re.finditer(pat, t, re.I):
        if tok.group(1):
            year = int(tok.group(1))
        elif year:
            mon2 = mnum(tok.group(4) or tok.group(2))
            try:
                out.append((dt.date(year, mon2, int(tok.group(5))), f"{mnum(tok.group(2))}/{tok.group(3)}~{tok.group(5)}"))
            except ValueError:
                pass
    return out


def parse_boc(page):
    """'Interest rate announcement' 근처의 'October 28, 2026'."""
    out = []
    t = text_of(page)
    for m in re.finditer(MON_RE + r"\s+(\d{1,2}),\s+(20\d\d)(.{0,120})", t, re.I):
        if "interest rate announcement" in m.group(4).lower() or "rate announcement" in t[max(0, m.start() - 120):m.start()].lower():
            out.append((dt.date(int(m.group(3)), mnum(m.group(1)), int(m.group(2))), ""))
    return out


def parse_generic(page, keyword):
    """키워드 근처의 'dd Month yyyy' / 'Month dd, yyyy'를 모은다 (BOK·BI·RBI 시도용)."""
    out = []
    t = text_of(page)
    for m in re.finditer(r"(\d{1,2})\s+" + MON_RE + r"\s+(20\d\d)|" + MON_RE + r"\s+(\d{1,2}),\s+(20\d\d)", t, re.I):
        ctx = t[max(0, m.start() - 160):m.end() + 160].lower()
        if keyword not in ctx:
            continue
        try:
            if m.group(1):
                out.append((dt.date(int(m.group(3)), mnum(m.group(2)), int(m.group(1))), ""))
            else:
                out.append((dt.date(int(m.group(6)), mnum(m.group(4)), int(m.group(5))), ""))
        except ValueError:
            pass
    return out


PARSERS = {
    "US": parse_fed, "EU": parse_ecb, "UK": parse_boe, "JP": parse_boj, "CA": parse_boc,
    "KR": lambda p: parse_generic(p, "monetary policy"),
    "ID": lambda p: parse_generic(p, "board of governors"),
    "IN": lambda p: parse_generic(p, "monetary policy committee"),
}


def lpr_dates(start, months):
    out, d = [], dt.date(start.year, start.month, 1)
    for _ in range(months):
        out.append((biz_next(dt.date(d.year, d.month, 20)), "매월 20일(휴일이면 다음 영업일)"))
        d = dt.date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return out


def build(today, fetch=get):
    lo, hi = today - dt.timedelta(days=30), today + dt.timedelta(days=400)
    events, status = [], {}
    for k, (name, url) in BANKS.items():
        got, src = [], "보조"
        if k == "CN":
            got, src = lpr_dates(dt.date(lo.year, lo.month, 1), 15), "규칙"
        elif url:
            try:
                got = PARSERS[k](fetch(url))
                got = [(d, n) for d, n in got if d.year >= today.year - 1]
                if got:
                    src = "공식"
            except Exception as e:  # noqa: BLE001 — 한 은행 실패로 전체를 멈추지 않는다
                print(f"  {k} {url} 실패: {e}")
        fb = [(dt.date.fromisoformat(d), n) for d, n in FALLBACK.get(k, [])]
        if src == "공식":
            # 같은 회의가 두 번 잡히면(예정·확정 표기) 7일 안의 것은 뒤 날짜 하나만 남긴다
            got = sorted(got)
            got = [x for i, x in enumerate(got) if not (i + 1 < len(got) and (got[i + 1][0] - x[0]).days <= 7)]
            notes = {d: n for d, n in fb}
            rows = [(d, n or notes.get(d, ""), src) for d, n in got]
            # 공식 페이지에서 빠진 회의는 보조 목록으로 채운다(공식 날짜와 7일 이상 떨어진 것만)
            rows += [(d, n, "보조") for d, n in fb if all(abs((d - g).days) > 7 for g, _ in got)]
        else:
            rows = [(d, n, src) for d, n in (got or fb)]
        rows = sorted({d: (d, n, s) for d, n, s in rows if lo <= d <= hi}.values())
        status[k] = {"source": src, "count": len(rows), "url": url}
        print(f"  {name}: {src} {len(rows)}건")
        events += [{"date": d.isoformat(), "bank": k, "name": name, "note": n, "source": s} for d, n, s in rows]
    events.sort(key=lambda e: (e["date"], e["bank"]))
    return {"updated": today.isoformat(),
            "note": "중앙은행 공식 일정 페이지를 매일 자동으로 읽는다. '보조'는 공식 페이지를 읽지 못해 공표 일정을 옮겨 적은 목록. 결과는 정책금리 월말 값 변화로 자동 표시.",
            "banks": status, "events": events}


def main():
    today = dt.datetime.now(KST).date()
    out = build(today)
    if not out["events"] and OUT.exists():
        print("일정을 하나도 만들지 못해 기존 파일 유지")
        return 0
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved rate_calendar.json · {len(out['events'])}건 · " + ", ".join(f"{k}:{v['source']}" for k, v in out["banks"].items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
