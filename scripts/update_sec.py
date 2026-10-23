"""미국 주요 증권사 순위: SEC EDGAR XBRL(companyfacts)에서 자본·순이익을 수집한다(키 불필요).

실패한 회사는 이전 값을 유지하므로 일부 수집 실패가 전체 빌드를 깨지 않는다.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from net import get_json  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "site" / "data" / "global" / "us_sec.json"

FIRMS = [
    ("Goldman Sachs", "0000886982", "IB·트레이딩"),
    ("Morgan Stanley", "0000895421", "IB·WM"),
    ("Charles Schwab", "0000316709", "리테일 브로커리지"),
    ("Interactive Brokers", "0001381197", "온라인 브로커리지"),
    ("Raymond James", "0000720005", "WM·IB"),
    ("Jefferies", "0000096223", "IB"),
    ("Robinhood", "0001783879", "모바일 브로커리지"),
    ("Stifel", "0000720672", "WM·IB"),
    ("LPL Financial", "0001397911", "독립 어드바이저 플랫폼"),
]

EQUITY_TAGS = ["StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "StockholdersEquity"]
NI_TAGS = ["NetIncomeLoss", "ProfitLoss"]
REV_TAGS = ["RevenuesNetOfInterestExpense", "Revenues"]


def latest(facts, tags, annual=False):
    """여러 태그 중 가장 최근 기간 값을 고른다(같은 기간이면 앞선 태그 우선)."""
    best = None
    for tag in tags:
        for u in facts.get("us-gaap", {}).get(tag, {}).get("units", {}).get("USD", []):
            if annual:
                if u.get("form") not in ("10-K", "10-K/A") or not u.get("start"):
                    continue
                days = (datetime.fromisoformat(u["end"]) - datetime.fromisoformat(u["start"])).days
                if days < 350:
                    continue
            if best is None or u["end"] > best["end"]:
                best = {"value": u["val"], "end": u["end"], "form": u.get("form"), "tag": tag}
    return best


# SEC는 연락처(이메일)가 든 User-Agent가 없으면 403을 준다. 필요하면 SEC_USER_AGENT로 바꾼다.
SEC_UA = os.environ.get("SEC_USER_AGENT") or \
    "HanwhaGlobalNetworkDashboard jeongpilchoi1992-hash@users.noreply.github.com"


def fetch(cik):
    facts = get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
                     headers={"User-Agent": SEC_UA, "Accept": "application/json"})["facts"]
    return {
        "equity": latest(facts, EQUITY_TAGS),
        "net_income_fy": latest(facts, NI_TAGS, annual=True),
        "revenue_fy": latest(facts, REV_TAGS, annual=True),
    }


def main():
    prev = {}
    if OUT.exists():
        prev = {r["name"]: r for r in json.loads(OUT.read_text(encoding="utf-8")).get("rows", [])}
    rows, errors = [], []
    for name, cik, model in FIRMS:
        row = {"name": name, "cik": cik, "model": model}
        try:
            row.update(fetch(cik))
            row["ok"] = True
        except Exception as e:  # 네트워크·스키마 변경 시 이전 값 유지
            errors.append(f"{name}: {e}")
            row.update({k: v for k, v in prev.get(name, {}).items() if k not in row})
            row["ok"] = False
        rows.append(row)
    rows.sort(key=lambda r: -((r.get("equity") or {}).get("value") or 0))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "SEC EDGAR XBRL companyfacts (10-K/10-Q)",
        "unit": "USD", "rows": rows, "errors": errors,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"SEC: {sum(r['ok'] for r in rows)}/{len(rows)} ok", *errors, sep="\n")


if __name__ == "__main__":
    main()
