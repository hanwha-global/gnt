"""해외자회사 출자내역 엑셀 → hanwha/data/investments.json (회차별 출자 이력, 수동 갱신).

사용법: python hanwha/scripts/build_investments.py "<Final Project>/(한화증권) 해외자회사_출자내역_병합.xlsx"

DART 타법인 출자현황에는 회차별 송금일·현지통화 금액이 없어 이 표만 내부 출자내역을 쓴다(사용자 결정 2026-10-23).
화면에는 '내부 출자내역 기준(수동)'으로 표시한다. 출자가 있을 때(증자·인수) 엑셀을 고친 뒤 다시 실행한다.
공개 저장소에 올리므로 다음 열은 절대 옮기지 않는다: 비고(계좌·SWIFT), 기안 번호, 주수·주당가격, USD 송금액·환율.
"""
import datetime as dt
import json
import re
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "investments.json"
KEYMAP = {"베트남": "VN", "싱가포르": "SG", "인니 CSA": "CSA", "인니 CAM": "CAM"}
KEEP = ("투자내역", "해외직접투자신고일", "송금일", "취득방법", "통화", "현지통화 투자액", "송금액(원화)/취득원가", "인수 후 지분비율")


def report_date(v):
    """'19년3월27일', '2022년10월25일', '21년2월4일(사후보고)', '-' → ('2019-03-27', 사후보고 여부)."""
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d"), False
    s = str(v or "")
    m = re.search(r"(\d{2,4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일", s)
    if not m:
        return None, "사후보고" in s
    y = int(m.group(1))
    y = y + 2000 if y < 100 else y
    return dt.date(y, int(m.group(2)), int(m.group(3))).isoformat(), "사후보고" in s


def rows_of(path):
    import openpyxl  # 테스트(Actions)에서는 report_date만 쓰므로 필요할 때만 불러온다

    ws = openpyxl.load_workbook(path, data_only=True).worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    hdr = rows[0]
    missing = [c for c in KEEP if c not in hdr]
    if missing:
        sys.exit(f"출자내역 엑셀에 열이 없음: {missing}")
    out = []
    for r in rows[1:]:
        if not r[0]:
            continue
        key = next((v for p, v in KEYMAP.items() if str(r[0]).startswith(p)), None)
        if not key:
            sys.exit(f"법인을 알 수 없는 행: {r[0]}")
        d = {c: r[hdr.index(c)] for c in KEEP}  # 필요한 열만 꺼낸다
        rep, post = report_date(d["해외직접투자신고일"])
        krw = d["송금액(원화)/취득원가"] or 0
        out.append({
            "key": key, "type": str(d["투자내역"]).replace("(사후보고)", "").strip(), "method": d["취득방법"],
            "report_date": rep, "post_report": post or "사후보고" in str(d["투자내역"]),
            "remit_date": d["송금일"].strftime("%Y-%m-%d") if hasattr(d["송금일"], "strftime") else None,
            "ccy": d["통화"], "local_amt": d["현지통화 투자액"] or 0,
            "krw_mn": round(krw / 1e6, 1), "stake_after": d["인수 후 지분비율"],
        })
    return out


def main(path):
    rows = rows_of(path)
    out = {"source": "해외자회사 출자내역(내부 관리대장)", "manual": True,
           "updated": dt.date.today().isoformat(), "unit": "현지통화 원 단위 · 원화 백만원 · 지분율 비율", "rows": rows}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"saved {OUT.name}: {len(rows)}건")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1])
