"""임시 점검: VNDirect finfo 증권사 재무 항목·비상장사 커버리지 확인(PR CI 로그용). 확인 후 삭제."""
import json
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import net  # noqa: E402

V = "https://api-finfo.vndirect.com.vn/v4"
q = lambda s: urllib.parse.quote(s)


def get(url):
    try:
        return net.get_json(url)
    except Exception as e:
        print("FAIL", url[:120], e)
        return {}


for mt in (89, 90):
    d = get(f"{V}/financial_models?q={q(f'modelType:{mt}')}&sort=displayOrder:asc&size=400")
    for r in d.get("data", []):
        n = f"{r.get('itemVnName')} | {r.get('itemEnName')}"
        print(f"M{mt} {int(r['itemCode'])} L{r.get('displayLevel')} {n}")

for code in ("HFT", "SSI", "KISVN", "MASC", "ACBS"):
    for rt in ("ANNUAL", "QUARTER"):
        d = get(f"{V}/financial_statements?q={q(f'code:{code}~reportType:{rt}~modelType:89,90')}&sort=fiscalDate:desc&size=600")
        rows = d.get("data", [])
        dates = sorted({r["fiscalDate"] for r in rows})[-6:]
        print(f"FS {code} {rt} n={len(rows)} dates={dates}")
        if code in ("HFT", "SSI") and rows:
            last = max(r["fiscalDate"] for r in rows)
            print("  ", {int(r["itemCode"]): r["numericValue"] for r in rows if r["fiscalDate"] == last and r.get("numericValue")})

for url in (f"{V}/stocks?q={q('code:HFT,KISVN,SSI')}&size=5",
            f"{V}/company_profiles?q={q('code:HFT')}",
            f"{V}/companies?q={q('code:HFT')}",
            f"{V}/stocks?q={q('code:HFT')}&size=5&fields=code,companyName,companyNameEng,floor,type,status"):
    d = get(url)
    print("NAME", url[len(V):len(V) + 40], json.dumps(d, ensure_ascii=False)[:600])
