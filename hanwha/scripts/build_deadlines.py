"""대외보고 기한을 자동으로 계산해 regulatory.json의 todo와 일정 파일(.ics)을 만든다.

사용법: python hanwha/scripts/build_deadlines.py [기준일 YYYY-MM-DD]

- 반복 기한: 분기·반기·사업보고서(자본시장법), 연간사업실적보고서(해외진출규정, 결산 후 5개월),
  현지 감사보고서 확보(내부 마일스톤).
- 수동 항목: regulatory.json의 "manual" (증자·신규사업 변경보고처럼 사건이 생길 때 담당자가 추가).
- 완료 처리: 정기보고서는 DART 접수 목록(dart_subs.json의 filed)으로 자동 완료. 나머지는 regulatory.json의 "done_ids"에 항목 id를 넣는다.
주말은 다음 월요일로 미루며 공휴일은 반영하지 않는다. LLM을 쓰지 않는다.
"""
import calendar
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "data" / "regulatory.json"
DART = ROOT / "data" / "dart_subs.json"
FILED_ID = {"1Q": "1Q", "1H": "2Q", "9M": "3Q", "FY": "FY"}  # dart_subs.json 기간 → periodic 항목 id
ICS = ROOT / "downloads" / "hanwha_regulatory.ics"
ENTITIES = "해외자회사 4사"  # 베트남 법인(PTSV)·싱가포르 법인(PTSS)·인도네시아 증권(CSA)·인도네시아 운용(CAM)
HORIZON_DAYS = 400   # 앞으로 이 기간 안의 반복 기한만 만든다
KEEP_PAST_DAYS = 60  # 지난 기한은 이 기간까지만 남긴다(미완료면 '기한 경과'로 보임)


def biz(d):
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d


def add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    return dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def recurring(today):
    out = []
    for y in (today.year - 1, today.year, today.year + 1):
        periods = [
            (f"{y}-1Q", "1분기보고서", dt.date(y, 3, 31), 45),
            (f"{y}-2Q", "반기보고서", dt.date(y, 6, 30), 45),
            (f"{y}-3Q", "3분기보고서", dt.date(y, 9, 30), 45),
            (f"{y}-FY", "사업보고서", dt.date(y, 12, 31), 90),
        ]
        for pid, name, end, days in periods:
            raw = end + dt.timedelta(days=days)
            due = biz(raw)
            out.append({"id": f"periodic-{pid}", "entity": "한화투자증권", "item": f"{y} {name} 해외자회사·타법인출자현황 반영",
                        "due": due.isoformat(), "basis": f"자본시장법 제159·160조, 기간 종료 후 {days}일" + (" (주말 → 다음 영업일)" if due != raw else ""),
                        "law": "공시", "note": "종속기업 요약재무정보·지분율·장부가 점검", "auto": True})
        fy_end = dt.date(y, 12, 31)
        out.append({"id": f"annual-FY{y}", "entity": ENTITIES, "item": f"FY{y} 연간사업실적보고서",
                    "due": biz(add_months(fy_end, 5)).isoformat(), "basis": "해외진출규정 제7조 ①3, 결산 후 5개월",
                    "law": "해외진출규정", "note": "현지 감사 재무제표(BS·PL·자본변동표) 첨부", "auto": True})
        out.append({"id": f"audit-FY{y}", "entity": ENTITIES, "item": f"FY{y} 현지 감사보고서 확보 (내부 마일스톤)",
                    "due": biz(add_months(fy_end, 4)).isoformat(), "basis": "연간사업실적보고 1개월 전",
                    "law": "내부", "note": "감사 지연 시 연간사업실적보고 기한을 놓치지 않도록 법인에 미리 요청", "auto": True})
    return out


def status_of(item, done_ids, today):
    if item.get("status") == "done" or item["id"] in done_ids:
        return "done"
    if item.get("due") and item["due"] < today.isoformat():
        return "overdue"
    return item.get("status") if item.get("status") in ("check",) else "upcoming"


def ics(items, today):
    def esc(s):
        return str(s).replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Hanwha GlobalNetwork//Regulatory//KO", "CALSCALE:GREGORIAN",
             "X-WR-CALNAME:한화투자증권 해외법인 대외보고", "X-WR-TIMEZONE:Asia/Seoul"]
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for it in items:
        if not it.get("due") or it["status"] == "done":
            continue
        d = dt.date.fromisoformat(it["due"])
        lines += ["BEGIN:VEVENT", f"UID:{it['id']}@hanwha-global-network", f"DTSTAMP:{stamp}",
                  f"DTSTART;VALUE=DATE:{d:%Y%m%d}", f"DTEND;VALUE=DATE:{d + dt.timedelta(days=1):%Y%m%d}",
                  f"SUMMARY:{esc(('[내부] ' if it.get('law') == '내부' else '[대외보고] ') + it['entity'] + ' ' + it['item'])}",
                  f"DESCRIPTION:{esc(it['basis'] + ' / ' + it.get('note', ''))}"]
        for days in (14, 3):
            lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{esc(it['item'])} D-{days}",
                      f"TRIGGER:-P{days}D", "END:VALARM"]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def main(today=None):
    today = dt.date.fromisoformat(today) if today else dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
    reg = json.loads(REG.read_text(encoding="utf-8"))
    done_ids = set(reg.get("done_ids", []))
    filed = {}  # DART에 접수된 정기보고서는 자동으로 완료
    if DART.exists():
        for f in json.loads(DART.read_text(encoding="utf-8")).get("filed", []):
            pid = f"periodic-{f['year']}-{FILED_ID.get(f['period'], '')}"
            filed[pid] = f
    done_ids |= set(filed)
    lo, hi = (today - dt.timedelta(days=KEEP_PAST_DAYS)).isoformat(), (today + dt.timedelta(days=HORIZON_DAYS)).isoformat()
    items = [x for x in recurring(today) if lo <= x["due"] <= hi]
    items += [{**m, "auto": False} for m in reg.get("manual", [])]
    for it in items:
        it["status"] = status_of(it, done_ids, today)
        if it["id"] in filed:
            d = filed[it["id"]]["rcept_dt"]
            it["note"] = f"DART 접수 {d[:4]}-{d[4:6]}-{d[6:]} (자동 확인)"
    # 지난 기한 중 완료된 반복 항목은 목록을 가볍게 하려고 뺀다(수동 항목은 남김)
    items = [x for x in items if not (x["auto"] and x["status"] == "done" and x["due"] < today.isoformat())]
    items.sort(key=lambda x: (x.get("due") or "9999-12-31", x["id"]))
    reg["todo"] = items
    reg["generated"] = today.isoformat()
    REG.write_text(json.dumps(reg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ICS.parent.mkdir(parents=True, exist_ok=True)
    ICS.write_text(ics(items, today), encoding="utf-8")
    soon = [x for x in items if x["status"] != "done" and x.get("due") and x["due"] <= (today + dt.timedelta(days=30)).isoformat()]
    print(f"todo {len(items)}건 · 30일 이내/경과 {len(soon)}건 → {REG.name}, {ICS.name}")
    return items


if __name__ == "__main__":
    main(*sys.argv[1:2])
