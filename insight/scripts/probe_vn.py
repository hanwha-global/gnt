"""임시 점검: 베트남 증권사 재무 공개 API 응답 구조 확인(PR CI 로그용). 확인 후 삭제."""
import json
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import net  # noqa: E402

V = "https://api-finfo.vndirect.com.vn/v4"


def show(label, url):
    try:
        d = net.get_json(url)
        txt = json.dumps(d, ensure_ascii=False)
        print(f"== {label} OK {len(txt)}B\n{txt[:2500]}\n")
        return d
    except Exception as e:
        print(f"== {label} FAIL {e}\n")


q = lambda s: urllib.parse.quote(s)
show("ratios SSI", f"{V}/ratios/latest?filter=ratioCode:MARKETCAP,PRICE_TO_BOOK,BVPS_CR,ROAE_TR_AVG5Q,OUTSTANDING_SHARES&where=code:SSI&order=reportDate&fields=ratioCode,value,reportDate")
show("ratios PSI (HNX)", f"{V}/ratios/latest?filter=ratioCode:MARKETCAP,PRICE_TO_BOOK,BVPS_CR,ROAE_TR_AVG5Q,OUTSTANDING_SHARES&where=code:PSI&order=reportDate&fields=ratioCode,value,reportDate")
show("ratios PHS (UPCoM)", f"{V}/ratios/latest?filter=ratioCode:MARKETCAP,PRICE_TO_BOOK,BVPS_CR,ROAE_TR_AVG5Q,OUTSTANDING_SHARES&where=code:PHS&order=reportDate&fields=ratioCode,value,reportDate")
d = show("fs SSI annual", f"{V}/financial_statements?q={q('code:SSI~reportType:ANNUAL')}&sort=fiscalDate:desc&size=400")
if d and d.get("data"):
    mts = sorted({r.get("modelType") for r in d["data"]})
    print("modelTypes", mts, "fiscalDates", sorted({r.get("fiscalDate") for r in d["data"]})[-4:])
    for mt in mts:
        show(f"models {mt}", f"{V}/financial_models?q={q(f'modelType:{mt}')}&sort=displayOrder:asc&size=400")
show("stocks securities", f"{V}/stocks?q={q('type:STOCK~status:LISTED')}&fields=code,companyNameEng,floor,industryName&size=3")
show("industry SSI", f"{V}/industry_classification?q={q('codeList:SSI')}")
for t in ("SSI", "PHS"):
    show(f"tcbs v2 {t}", f"https://apipubaws.tcbs.com.vn/tcanalysis/v1/finance/{t}/balancesheet?yearly=1&isAll=true")
    show(f"stockanalysis {t}", f"https://stockanalysis.com/api/symbol/a/HOSE-{t}/financials?type=balance-sheet")
