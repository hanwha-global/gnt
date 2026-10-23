"""한국은행 ECOS OpenAPI로 YTD Macro(기준금리·환율)를 받아 hanwha/data/macro.json에 저장한다.

GitHub Actions에서 env ECOS_API_KEY(secrets)로 실행한다. 키가 없으면 아무것도 바꾸지 않고 끝낸다.
표준 라이브러리만 사용하며 LLM 토큰은 쓰지 않는다.
"""
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# API 키: 환경변수(Actions Secrets) → 로컬 .env → 터미널 실행 시 숨김 입력(scripts/keys.py)
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from keys import get_key  # noqa: E402

BASE = "https://ecos.bok.or.kr/api"
OUT = Path(__file__).resolve().parents[1] / "data" / "macro.json"
FX_TABLE = "731Y001"  # 주요국 통화의 대원화환율 (일)
FX_TARGETS = {"USD": "미국", "VND": "베트남", "IDR": "인도네시아", "SGD": "싱가포르"}
BASE_RATE = ("722Y001", "0101000", "M")  # 한국은행 기준금리 (월)


def call(key, *parts):
    url = "/".join([BASE] + [urllib.parse.quote(str(p)) for p in (parts[0], key, "json", "kr") + parts[1:]])
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.load(r)


def rows(resp, name):
    return resp.get(name, {}).get("row", [])


def main():
    key = get_key("ECOS_API_KEY")
    if not key:
        print("ECOS_API_KEY 없음: macro.json 갱신 건너뜀")
        return 0
    today = dt.date.today()
    start = dt.date(today.year, 1, 1)
    items = rows(call(key, "StatisticItemList", 1, 200, FX_TABLE), "StatisticItemList")
    fx = {}
    for ccy, word in FX_TARGETS.items():
        item = next((i for i in items if word in i["ITEM_NAME"]), None)
        if not item:
            continue
        data = rows(call(key, "StatisticSearch", 1, 400, FX_TABLE, "D", start.strftime("%Y%m%d"),
                         today.strftime("%Y%m%d"), item["ITEM_CODE"]), "StatisticSearch")
        pts = [(d["TIME"], float(d["DATA_VALUE"])) for d in data if d.get("DATA_VALUE")]
        if not pts:
            continue
        q = lambda m0, m1: [v for t, v in pts if m0 <= int(t[4:6]) <= m1]
        avg = lambda xs: round(sum(xs) / len(xs), 4) if xs else None
        fx[ccy] = {"name": item["ITEM_NAME"], "unit": data[0].get("UNIT_NAME", ""),
                   "first": pts[0], "last": pts[-1], "ytd_pct": round((pts[-1][1] / pts[0][1] - 1) * 100, 2),
                   "avg_1q": avg(q(1, 3)), "avg_2q": avg(q(4, 6)), "avg_3q": avg(q(7, 9)), "avg_4q": avg(q(10, 12))}
    tbl, code, cyc = BASE_RATE
    br = rows(call(key, "StatisticSearch", 1, 24, tbl, cyc, start.strftime("%Y%m"), today.strftime("%Y%m"), code), "StatisticSearch")
    out = {"updated": today.isoformat(), "source": "한국은행 ECOS OpenAPI", "fx": fx,
           "kr_base_rate": [(d["TIME"], float(d["DATA_VALUE"])) for d in br if d.get("DATA_VALUE")]}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved", OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
