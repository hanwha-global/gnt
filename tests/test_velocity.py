"""미국 진출 페이지 Velocity Clearing: 수집 스크립트(네트워크 대신 가짜 응답)와 데이터 형식을 검증한다."""
import json
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "workflow" / "scripts"))
sys.path.insert(0, str(ROOT / "guide" / "scripts"))
import fetch_velocity as fv  # noqa: E402
import check_sources  # noqa: E402

V = json.loads((ROOT / "workflow" / "data" / "velocity.json").read_text(encoding="utf-8"))
US = json.loads((ROOT / "workflow" / "data" / "us_entry.json").read_text(encoding="utf-8"))

# BrokerCheck 검색 API 응답(content는 JSON 문자열) 모양
BC_CONTENT = {
    "basicInformation": {"firmId": 126588, "firmName": "VELOCITY CLEARING, LLC", "firmStatus": "Approved", "bdSECNumber": "65894",
                         "finraLastApprovalDate": "08/15/2003", "formedDate": "06/11/2010", "formedState": "Delaware",
                         "firmType": "Limited Liability Company", "firmSize": "Small", "otherNames": ["GUARDIAN TRADING"]},
    "firmAddressDetails": {"officeAddress": {"city": "HAZLET", "state": "NJ"}},
    "registrations": {"approvedSECRegistrationCount": 1, "approvedSRORegistrationCount": 3, "approvedStateRegistrationCount": 53, "businessTypeCount": 3},
    "disclosures": [{"disclosureType": "Regulatory Event", "disclosureCount": 2}],
    "directOwners": [{"legalName": "VCT HOLDINGS, LLC", "position": "SOLE MEMBER"}, {"legalName": "LOGAN, MICHAEL JAMES", "position": "CHIEF EXECUTIVE OFFICER"}],
}
BC_API = json.dumps({"hits": {"hits": [{"_source": {"content": json.dumps(BC_CONTENT)}}]}}).encode()

# 상세 보고서 PDF 글자 모양(실제 보고서 줄 형식)
BC_REPORT = """Self-Regulatory Organization Status Date Effective
FINRA Approved 08/15/2003
24X National Exchange LLC Approved 10/24/2025
Nasdaq Texas, LLC Approved 02/03/2020
©2026 FINRA. All rights reserved. Report about VELOCITY CLEARING, LLC 12
This firm currently conducts 3 types of businesses.
Types of Business
Mutual fund retailer
Trading securities for own account
Other - CLEAR EXCHANGE LISTED AND OTC EQUITY SECURITIES FOR CORRESPONDENTS,EXECUTE
STOCK LOAN TRANSACTIONS. CFTC/NFA REGISTERED INTRODUCING BROKER.
©2026 FINRA. All rights reserved. Report about VELOCITY CLEARING, LLC 13
Pending Final On Appeal
Regulatory Event 0 2 0
©2026 FINRA. All rights reserved. Report about VELOCITY CLEARING, LLC 23
Disclosure 1 of 2
Date Initiated: 09/30/2025
Date Initiated: 11/07/2024
Disclosure 2 of 2
Date Initiated: 03/18/2021
"""

# 연차 감사보고서 공개분(X-17A-5) 글자 모양: 재무상태표 합계 줄, 주석의 공정가치 표(뒤에 나오는 'Total assets'), 순자본 주석
X17 = """Statement of Financial Condition
December 31, 2025
Total assets $ 5,311,159,767
Total liabilities 5,154,380,192
Members’ equity 156,779,575
Total liabilities and member's equity $ 5,311,159,767
Note 4 – Fair Value
Total assets $ 52,006,616
Total liabilities $ 1,737,247
Note 5 – Net Capital
At December 31, 2025, the Company had net capital, as defined, of $136,069,088 which was $129,754,947 in excess of
its required net capital of $6,314,141.
"""

# 회사 누리집(who-we-are) HTML 모양: 절대·상대·스크립트 JSON 안 주소, 재무상태표가 아닌 PDF, PDF가 아닌 감사보고서 링크
SITE_HTML = """<a href="https://media.velocityclearingllc.com/wp-content/uploads/2026/09/04065732/Velocity-Clearing-06.30.2026-Financial-Statement-Unaudited-1.pdf">Unaudited June 30, 2026</a>
<a href="https://vcttechnologiesllccom-my.sharepoint.com/:b:/g/personal/x/IQB3?e=H6">Audited December 31, 2025 Financials</a>
<a href='/wp-content/uploads/2025/09/Velocity-Clearing-6.30.2025-Statement-of-Financial-Condition.pdf'>June 30, 2025</a>
<script>var d={"u":"https:\\/\\/media.velocityclearingllc.com\\/a\\/Form-CRS-06.30.2026.pdf"}</script>"""
H1_URL = "https://media.velocityclearingllc.com/wp-content/uploads/2026/09/04065732/Velocity-Clearing-06.30.2026-Financial-Statement-Unaudited-1.pdf"
X17_H1 = X17.replace("December 31, 2025", "June 30, 2026")


def rss(*items):
    body = "".join(f"<item><title>{t} - {s}</title><link>https://n.example/{i}</link><pubDate>{d}</pubDate><source url='x'>{s}</source></item>"
                   for i, (t, s, d) in enumerate(items))
    return f"<rss><channel>{body}</channel></rss>".encode()


def ago(days):
    return (datetime.now(fv.KST) - timedelta(days=days)).strftime("%Y-%m-%d")


class ParseTest(unittest.TestCase):
    def test_brokercheck_api_summary(self):
        b = fv.parse_bc(BC_API)
        self.assertEqual((b["crd"], b["sec_file"], b["finra_since"], b["size"], b["address"]), ("126588", "8-65894", "2003-08-15", "Small", "HAZLET, NJ"))
        self.assertEqual(b["counts"], {"sec": 1, "sro": 3, "states": 53, "types": 3})
        self.assertEqual(b["disclosures"], {"Regulatory Event": 2})
        self.assertEqual(b["officers"][1], {"name": "LOGAN, MICHAEL JAMES", "position": "CHIEF EXECUTIVE OFFICER"})

    def test_report_lists_and_disclosure_status(self):
        sros, types = fv.parse_bc_report(BC_REPORT)
        self.assertEqual([s["name"] for s in sros], ["FINRA", "24X National Exchange LLC", "Nasdaq Texas, LLC"])
        self.assertEqual(sros[1]["since"], "2025-10-24")
        self.assertEqual(len(types), 3)
        self.assertTrue(types[2].startswith("Other - CLEAR") and types[2].endswith("INTRODUCING BROKER."))  # 여러 줄 설명은 한 항목
        status, latest = fv.parse_bc_disclosures(BC_REPORT)
        self.assertEqual(status, {"Regulatory Event": {"pending": 0, "final": 2, "appeal": 0}})
        self.assertEqual(latest, "2025-09-30")

    def test_disclosure_status_tolerates_pdf_text_layout(self):
        # pypdf 글자는 칸마다 줄이 바뀌거나 머리글 띄어쓰기가 빠질 수 있다. 공시 유형이 여럿이면 줄마다, 해당 없는 칸은 N/A
        split = "matrix of the number and status of disclosure events.\nPendingFinal\nOn Appeal\nRegulatory\nEvent\n0\n19\n0\nCivil Event 0 1 0\nArbitration N/A 2 N/A\n©2026 FINRA. 23\nDate Initiated:\n09/30/2025"
        status, latest = fv.parse_bc_disclosures(split)
        self.assertEqual(status, {"Regulatory Event": {"pending": 0, "final": 19, "appeal": 0}, "Civil Event": {"pending": 0, "final": 1, "appeal": 0},
                                  "Arbitration": {"pending": 0, "final": 2, "appeal": 0}})
        self.assertEqual(latest, "2025-09-30")
        swapped = "number and status of disclosure events. Regulatory Event 0 19 0\nPending Final On Appeal\n©2026 FINRA"
        self.assertEqual(fv.parse_bc_disclosures(swapped)[0], {})  # 머리글 뒤에 줄이 없으면 읽지 않는다(배치대로 다시 읽음)
        self.assertIn("Regulatory Event 0 19 0", fv.status_snippet(swapped))
        self.assertEqual(fv.parse_bc_disclosures("no table here")[0], {})

    def test_site_statement_links(self):
        links = fv.statement_links(SITE_HTML)
        self.assertEqual([(d, u) for d, u, _ in links], [
            ("2026-06-30", H1_URL),
            ("2025-06-30", "https://www.velocityclearingllc.com/wp-content/uploads/2025/09/Velocity-Clearing-6.30.2025-Statement-of-Financial-Condition.pdf"),
        ])  # 최신순, 상대 주소는 누리집 기준 절대 주소로, Form CRS·SharePoint 링크는 뺀다
        self.assertEqual(fv.statement_links("<p>no links</p>"), [])

    def test_annual_report_balance_sheet_and_net_capital(self):
        v = fv.parse_x17a5(X17)
        self.assertEqual((v["assets"], v["liab"], v["equity"]), (5311159767, 5154380192, 156779575))  # 주석 표의 합계가 아니라 재무상태표 값
        self.assertEqual((v["net_capital"], v["excess"], v["required"]), (136069088, 129754947, 6314141))
        self.assertIsNone(fv.parse_x17a5(X17.replace("156,779,575", "156,000,000")))  # 대차가 안 맞으면 버린다
        no_nc = fv.parse_x17a5(X17.replace("$129,754,947", "$129,000,000"))  # 순자본 세 값이 안 맞물리면 순자본만 뺀다
        self.assertEqual(no_nc["equity"], 156779575)
        self.assertNotIn("net_capital", no_nc)

    def test_filings_newest_first_with_amendments(self):
        sub = {"filings": {"recent": {
            "accessionNumber": ["0001225460-22-000003", "0001225460-22-000004", "0001225460-26-000003", "0001225460-26-000001"],
            "filingDate": ["2022-03-01", "2022-03-03", "2026-03-02", "2026-01-15"],
            "reportDate": ["2021-12-31", "2021-12-31", "2025-12-31", ""],
            "form": ["X-17A-5", "X-17A-5/A", "X-17A-5", "17-H"],
            "primaryDocument": ["primary_doc.xml"] * 4}}}
        fs = fv.filings(sub)
        self.assertEqual([f["acc"] for f in fs], ["0001225460-26-000003", "0001225460-22-000004", "0001225460-22-000003"])
        self.assertEqual(fs[0]["folder"], "https://www.sec.gov/Archives/edgar/data/1225460/000122546026000003/")

    def test_value_at_same_date_or_nearest_quarter(self):
        units = [
            {"end": "2025-12-31", "val": 10, "form": "10-K", "filed": "2026-02-20"},
            {"end": "2025-12-31", "val": 11, "form": "10-Q", "filed": "2026-05-01"},  # 다음 분기 보고서의 비교 값(같은 날짜)
            {"end": "2026-03-31", "val": 99, "form": "10-Q", "filed": "2026-05-01"},  # 결산일 뒤
            {"start": "2025-01-01", "end": "2025-12-31", "val": 5, "form": "10-K", "filed": "2026-02-20"},  # 기간 값
            {"end": "2025-12-31", "val": 7, "form": "8-K", "filed": "2026-01-20"},
        ]
        self.assertEqual(fv.value_at(units, "2025-12-31")["value"], 11)
        nov = [{"end": "2025-11-30", "val": 3, "form": "10-K", "filed": "2026-01-28"}, {"end": "2025-08-31", "val": 2, "form": "10-Q", "filed": "2025-10-01"}]
        self.assertEqual(fv.value_at(nov, "2025-12-31")["end"], "2025-11-30")  # 결산월이 다르면 가장 가까운 분기말
        self.assertIsNone(fv.value_at([{"end": "2025-06-30", "val": 1, "form": "10-Q", "filed": "2025-08-01"}], "2025-12-31"))

    def test_news_filters_titles_and_merges(self):
        now = datetime.now(fv.KST).strftime("%a, %d %b %Y 09:00:00 +0900")
        old = (datetime.now(fv.KST) - timedelta(days=900)).strftime("%a, %d %b %Y 09:00:00 +0900")
        en = fv.parse_news(rss(("Velocity Clearing adds exchange", "Business Wire", now), ("Velocity of money rises", "Reuters", now),
                               ("Velocity Clearing old item", "PR", old)), "en", datetime.now(fv.KST) - timedelta(days=fv.NEWS_DAYS))
        self.assertEqual([x["title"] for x in en], ["Velocity Clearing adds exchange"])  # 다른 뜻의 Velocity·2년 지난 기사는 뺀다
        ko = fv.parse_news(rss(("한화생명 벨로시티 인수 1년", "비즈워치", now), ("한화생명 실적 발표", "연합", now)), "ko",
                           datetime.now(fv.KST) - timedelta(days=fv.NEWS_DAYS))
        self.assertEqual(len(ko), 1)
        prev = [{"date": ago(30), "title": "Velocity Clearing adds exchange", "src": "BW", "url": "u", "lang": "en"},
                {"date": ago(800), "title": "아주 오래된 기사", "src": "x", "url": "u", "lang": "ko"}]
        with mock.patch.object(fv.net, "get", side_effect=[rss(("Velocity Clearing adds exchange", "Business Wire", now)), rss()]):
            out = fv.news(prev, [])
        self.assertEqual([x["title"] for x in out], ["Velocity Clearing adds exchange"])


class FetchTest(unittest.TestCase):
    """이전 값 유지와 다시 받는 간격: 바뀐 게 없으면 PDF·상장사 값은 매번 받지 않는다."""

    def test_brokercheck_reads_report_only_when_counts_change_or_week_old(self):
        sros, types = fv.parse_bc_report(BC_REPORT)
        status, latest = fv.parse_bc_disclosures(BC_REPORT)
        prev = {"sros": sros, "types": types, "disc_status": status, "disc_latest": latest,
                "sros_checked": ago(1), "types_checked": ago(1), "disclosures": {"Regulatory Event": 2}}
        with mock.patch.object(fv.net, "get", return_value=BC_API) as g:
            out = fv.brokercheck(prev, [])
        self.assertEqual(g.call_count, 1)  # API만
        self.assertEqual(out["checked"], fv.today())
        with mock.patch.object(fv.net, "get", side_effect=[BC_API, b"%PDF"]) as g, mock.patch.object(fv, "pdf_text", return_value=BC_REPORT):
            out = fv.brokercheck({**prev, "sros_checked": ago(8)}, [])
        self.assertEqual(g.call_count, 2)
        self.assertEqual(out["sros_checked"], fv.today())
        errs = []
        half = BC_REPORT.replace("Nasdaq Texas, LLC Approved 02/03/2020\n", "")
        with mock.patch.object(fv.net, "get", side_effect=[BC_API, b"%PDF"]), mock.patch.object(fv, "pdf_text", return_value=half):
            out = fv.brokercheck({**prev, "sros_checked": ago(8)}, errs)
        self.assertEqual(len(out["sros"]), 3)  # 반쪽 목록은 쓰지 않는다
        self.assertTrue(any("SRO 2건" in e for e in errs))

    def test_brokercheck_status_falls_back_to_layout_text(self):
        prev = {"sros_checked": ago(8), "types_checked": ago(8)}
        swapped = BC_REPORT.replace("Pending Final On Appeal\nRegulatory Event 0 2 0\n", "Regulatory Event 0 2 0\nPending Final On Appeal\n")
        with mock.patch.object(fv.net, "get", side_effect=[BC_API, b"%PDF"]), \
                mock.patch.object(fv, "pdf_text", side_effect=lambda raw, layout=False: BC_REPORT if layout else swapped) as t:
            out = fv.brokercheck(prev, [])
        self.assertEqual(out["disc_status"], {"Regulatory Event": {"pending": 0, "final": 2, "appeal": 0}})
        self.assertEqual(out["disc_latest"], "2025-09-30")
        self.assertEqual(t.call_count, 2)
        errs = []
        with mock.patch.object(fv.net, "get", side_effect=[BC_API, b"%PDF"]), mock.patch.object(fv, "pdf_text", return_value=swapped):
            out = fv.brokercheck({**prev, "disc_status": {"Regulatory Event": {"pending": 0, "final": 2, "appeal": 0}}}, errs)
        self.assertEqual(out["disc_status"]["Regulatory Event"]["final"], 2)  # 둘 다 못 읽으면 이전 값
        self.assertTrue(any("원문:" in e for e in errs))  # 실행 기록에 원문 조각

    def test_interim_statement_from_site(self):
        fy = {"period": "2025-12-31", "equity": 156779575.0}
        errs = []
        with mock.patch.object(fv.net, "get", side_effect=[SITE_HTML.encode(), b"%PDF"]), mock.patch.object(fv, "pdf_text", return_value=X17_H1):
            it = fv.interim(None, fy, errs)
        self.assertEqual((it["period"], it["url"], it["audited"], it["equity"], it["net_capital"]), ("2026-06-30", H1_URL, False, 156779575, 136069088))
        self.assertEqual(errs, [])
        with mock.patch.object(fv.net, "get", return_value=SITE_HTML.encode()) as g:
            again = fv.interim({**it, "checked": ago(3)}, fy, [])
        self.assertEqual(g.call_count, 1)  # 이미 읽은 파일은 다시 받지 않는다
        self.assertEqual((again["equity"], again["checked"]), (it["equity"], fv.today()))
        with mock.patch.object(fv.net, "get", return_value=SITE_HTML.encode()):
            self.assertIsNone(fv.interim(it, {"period": "2026-12-31", "equity": 1.6e8}, []))  # 감사보고서가 더 새것
        with mock.patch.object(fv.net, "get", side_effect=RuntimeError("HTTP 503: x")):
            self.assertIs(fv.interim(it, fy, []), it)  # 누리집 실패: 이전 값
            self.assertIsNone(fv.interim(it, {"period": "2026-12-31"}, []))  # 이전 값도 감사보고서보다 오래되면 버린다
        errs = []
        with mock.patch.object(fv.net, "get", side_effect=[SITE_HTML.encode(), b"%PDF"]), mock.patch.object(fv, "pdf_text", return_value="scan"):
            self.assertIsNone(fv.interim(None, fy, errs))
        self.assertTrue(any("읽지 못함" in e for e in errs))
        thousands = X17_H1.replace("5,311,159,767", "5,311,160").replace("5,154,380,192", "5,154,380").replace("156,779,575", "156,780")
        errs = []
        with mock.patch.object(fv.net, "get", side_effect=[SITE_HTML.encode(), b"%PDF"]), mock.patch.object(fv, "pdf_text", return_value=thousands):
            self.assertIsNone(fv.interim(None, fy, errs))
        self.assertTrue(any("자릿수" in e for e in errs))

    def test_brokercheck_failure_keeps_previous(self):
        errs = []
        with mock.patch.object(fv.net, "get", side_effect=RuntimeError("HTTP 503: x")):
            out = fv.brokercheck({"crd": "126588", "checked": "2026-10-01"}, errs)
        self.assertEqual(out, {"crd": "126588", "checked": "2026-10-01"})
        self.assertTrue(errs)

    def test_edgar_parses_only_new_reports(self):
        sub = {"filings": {"recent": {
            "accessionNumber": ["0001225460-26-000003", "0001225460-25-000001"], "filingDate": ["2026-03-02", "2025-03-03"],
            "reportDate": ["2025-12-31", "2024-12-31"], "form": ["X-17A-5", "X-17A-5"], "primaryDocument": ["p.xml", "p.xml"]}}}
        idx = json.dumps({"directory": {"item": [{"name": "public25.pdf"}, {"name": "primary_doc.xml"}]}}).encode()
        prev = {"fin": [{"period": "2024-12-31", "acc": "0001225460-25-000001", "equity": 122953781.0, "auto": False}]}
        calls = []

        def fake(url, **kw):
            calls.append(url)
            return json.dumps(sub).encode() if "submissions" in url else idx if url.endswith("index.json") else b"%PDF"
        with mock.patch.object(fv, "sec_get", side_effect=fake), mock.patch.object(fv, "pdf_text", return_value=X17):
            out = fv.edgar(prev, [])
        self.assertEqual([f["period"] for f in out["fin"]], ["2025-12-31", "2024-12-31"])
        self.assertEqual(out["fin"][0]["equity"], 156779575)
        self.assertTrue(out["fin"][0]["auto"])
        self.assertEqual(out["fin"][0]["url"], "https://www.sec.gov/Archives/edgar/data/1225460/000122546026000003/public25.pdf")
        self.assertEqual(out["fin"][1]["equity"], 122953781.0)  # 이미 읽은 보고서(같은 접수번호)는 다시 받지 않는다
        self.assertEqual(len([u for u in calls if u.endswith(".pdf")]), 1)
        errs = []
        with mock.patch.object(fv, "sec_get", side_effect=fake), mock.patch.object(fv, "pdf_text", return_value="scan without text"):
            out = fv.edgar(prev, errs)
        self.assertEqual([f["period"] for f in out["fin"]], ["2024-12-31"])  # 못 읽으면 넣지 않고 이전 값만
        self.assertTrue(any("재무상태표" in e for e in errs))
        thousands = X17.replace("5,311,159,767", "5,311,160").replace("5,154,380,192", "5,154,380").replace("156,779,575", "156,780")
        errs = []
        with mock.patch.object(fv, "sec_get", side_effect=fake), mock.patch.object(fv, "pdf_text", return_value=thousands):
            out = fv.edgar(prev, errs)
        self.assertEqual([f["period"] for f in out["fin"]], ["2024-12-31"])  # 천 달러 단위 표는 자릿수가 전년과 달라 넣지 않는다
        self.assertTrue(any("자릿수" in e for e in errs))

    def test_peers_recheck_weekly_and_keep_failed_rows(self):
        rows = [{"name": n, "ticker": t, "cik": c, "model": m, "equity": {"value": 1, "end": "2025-12-31"}, "ok": True} for n, t, c, m in fv.PEERS]
        fresh = {"date": "2025-12-31", "rows": rows, "checked": ago(1)}
        with mock.patch.object(fv, "concept") as c:
            self.assertIs(fv.peers(fresh, "2025-12-31", []), fresh)
        c.assert_not_called()
        errs = []
        with mock.patch.object(fv, "concept", side_effect=RuntimeError("HTTP 503: busy")):
            out = fv.peers({**fresh, "checked": ago(8)}, "2025-12-31", errs)
        self.assertEqual(out["rows"][0]["equity"]["value"], 1)  # 실패한 회사는 같은 날짜의 이전 값
        self.assertFalse(out["rows"][0]["ok"])
        self.assertEqual(len(errs), len(fv.PEERS))


class DataTest(unittest.TestCase):
    """저장된 velocity.json 과 화면 문구(us_entry.json velocity)."""

    def test_saved_data_is_consistent(self):
        b = V["brokercheck"]
        self.assertEqual(len(b["sros"]), b["counts"]["sro"])
        self.assertEqual(len(b["types"]), b["counts"]["types"])
        self.assertEqual(b["sros"][0]["name"], "FINRA")
        self.assertEqual(fv.disc_totals(b.get("disc_status")), fv.disc_totals(b["disclosures"]))
        fin = V["edgar"]["fin"]
        self.assertGreaterEqual(len(fin), 5)
        for f in fin:
            self.assertLess(abs(f["assets"] - f["liab"] - f["equity"]), 1, f["period"])
            self.assertLess(abs(f["net_capital"] - f["excess"] - f["required"]), 1, f["period"])
            self.assertTrue(f["url"].startswith("https://www.sec.gov/Archives/edgar/data/1225460/") and f["url"].endswith(".pdf"))
        self.assertEqual([f["period"] for f in fin], sorted((f["period"] for f in fin), reverse=True))
        filed = [f["filed"] for f in V["edgar"]["filings"]]
        self.assertEqual(filed, sorted(filed, reverse=True))
        for x in V["news"]:
            self.assertTrue(x["date"] and x["title"] and x["url"].startswith("https://"), x)
        p = V.get("peers") or {}
        if p.get("rows"):
            self.assertEqual([r["ticker"] for r in p["rows"]], [t for _, t, _, _ in fv.PEERS])
        it = V.get("interim")
        if it:
            self.assertGreater(it["period"], fin[0]["period"])  # 감사보고서보다 새것만
            self.assertLess(abs(it["assets"] - it["liab"] - it["equity"]), 1)
            if p.get("rows"):
                self.assertEqual(p["date"], it["period"])  # 순위는 가장 최근 재무 날짜

    def test_screen_text_uses_known_auto_fields(self):
        M = US["velocity"]
        self.assertTrue({r["auto"] for r in M["licenses"] if r.get("auto")} <= {"sec", "finra", "sro", "states", "types", "disc"})
        disc = next(r for r in M["licenses"] if r.get("auto") == "disc")
        self.assertRegex(disc["latest"]["d"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual([t["d"] for t in M["timeline"]], sorted(t["d"] for t in M["timeline"]))


class SourceCheckLiveTest(unittest.TestCase):
    def test_live_databases_are_not_checked(self):
        live = ["https://brokercheck.finra.org/firm/summary/126588", "https://files.brokercheck.finra.org/firm/firm_126588.pdf",
                "https://brokercheck.finra.org/", "https://www.sec.gov/edgar/browse/?CIK=1225460",
                "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=1225460"]
        for u in live:
            self.assertTrue(check_sources.LIVE.match(u), u)
        for u in ["https://www.finra.org/rules-guidance/rulebooks/finra-rules/1017", "https://www.sec.gov/answers/brkrdlr.htm",
                  "https://www.sec.gov/Archives/edgar/data/1225460/000122546026000003/public25.pdf", "https://brokercheck.finra.org.example.com/"]:
            self.assertFalse(check_sources.LIVE.match(u), u)

        def no_live(u):
            if check_sources.LIVE.match(u):
                raise AssertionError(u)
            return "same"
        st, _ = check_sources.run({"sources": {"https://brokercheck.finra.org/": {"kind": "링크", "checked": "2026-10-29"}}}, "2027-01-02", "",
                                  fetch=no_live, alive=no_live, search=lambda oc, law: None, asserter=lambda a, oc, lm: None)
        self.assertFalse(any(check_sources.LIVE.match(u) for u in st["sources"]))  # 예전 기록도 지운다


if __name__ == "__main__":
    unittest.main()
