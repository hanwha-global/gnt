"""수집 규칙과 DART 파이프라인을 네트워크 없이 검증한다."""
import io
import json
import os
import sys
import unittest
import zipfile
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import gnd  # noqa: E402
import update_dart  # noqa: E402


class RulesTest(unittest.TestCase):
    def test_fund_like_names_are_excluded(self):
        for name in ["미래에셋 글로벌 펀드", "Kiwoom BVI 1 Limited", "Hana Global Trust", "신한다이닝제일차 주식회사",
                     "ABC Opportunity Fund LP", "특정금전신탁(주4)", "XYZ Vehicle Ltd"]:
            self.assertEqual(gnd.classify_entity(name)[0], "제외", name)

    def test_operating_companies_are_kept(self):
        for name in ["SF Credit Partners, LLC", "NH Absolute Return Partners Pte. Ltd.",
                     "PT Ciptadana Sekuritas Asia", "Pinetree Securities Corporation"]:
            self.assertEqual(gnd.classify_entity(name)[0], "법인", name)

    def test_country_guess(self):
        cases = {
            "Mirae Asset Securities Mongolia UTsK LLC": "몽골",
            "NH Investment & Securities(H.K.) Ltd.": "홍콩",
            "KIS Vietnam Securities Corporation": "베트남",
            "PT Korea Investment & Sekuritas Indonesia": "인도네시아",
            "Pinetree Securities Pte. Ltd.": "싱가포르",
            "Korea Investment & Securities America, Inc.": "미국",
            "하나지분투자관리(심천)유한공사": "중국",
        }
        for name, country in cases.items():
            self.assertEqual(gnd.guess_country(name), country, name)

    def test_domestic_names_are_not_overseas(self):
        self.assertFalse(gnd.is_overseas_name("한국증권금융"))
        self.assertFalse(gnd.is_overseas_name("밸류플러스미드스트림 주식회사"))
        self.assertTrue(gnd.is_overseas_name("Shinhan Securities Asia Ltd. (Hong Kong)"))

    def test_report_parsing(self):
        self.assertEqual(update_dart.parse_report("반기보고서 (2026.06)"), ("2026", "11012", "2026 반기보고서"))
        self.assertEqual(update_dart.parse_report("분기보고서 (2026.03)")[1], "11013")
        self.assertEqual(update_dart.parse_report("[기재정정]사업보고서 (2025.12)")[1], "11011")
        self.assertEqual(update_dart.to_num("(1,234)"), -1234)
        self.assertIsNone(update_dart.to_num("-"))


def fake_corp_zip():
    xml = ("<result><list><corp_code>00148610</corp_code><corp_name>한화투자증권</corp_name>"
           "<stock_code>003530</stock_code><modify_date>20260101</modify_date></list></result>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("CORPCODE.xml", xml)
    return buf.getvalue()


def fake_json(url, params=None, headers=None):
    path = url.rsplit("/", 1)[-1]
    if path == "list.json" and params.get("pblntf_ty") == "A":
        return {"status": "000", "list": [
            {"report_nm": "반기보고서 (2026.06)", "rcept_no": "20260814000001", "rcept_dt": "20260814"},
            {"report_nm": "사업보고서 (2025.12)", "rcept_no": "20260320000001", "rcept_dt": "20260320"}]}
    if path == "list.json":
        return {"status": "000", "list": [
            {"report_nm": "타법인주식및출자증권취득결정", "rcept_no": "20260901000001", "rcept_dt": "20260901"},
            {"report_nm": "임원ㆍ주요주주특정증권등소유상황보고서", "rcept_no": "20260902000001", "rcept_dt": "20260902"}]}
    if path == "fnlttSinglAcnt.json":
        return {"status": "000", "list": [
            {"fs_div": "CFS", "account_nm": "자본총계", "thstrm_amount": "2,000,000,000,000"},
            {"fs_div": "CFS", "account_nm": "당기순이익", "thstrm_amount": "50,000,000,000",
             "thstrm_add_amount": "90,000,000,000"}]}
    if path == "otrCprInvstmntSttus.json":
        if params["reprt_code"] != "11011":
            return {"status": "013", "message": "조회된 데이타가 없습니다."}
        return {"status": "000", "list": [
            {"inv_prm": "Pinetree Securities Corporation", "trmend_blce_qota_rt": "100", "invstmnt_purps": "경영참여",
             "recent_bsns_year_fnnr_sttus_tot_assets": "500,000", "recent_bsns_year_fnnr_sttus_thstrm_ntpf": "-1,000"},
            {"inv_prm": "Hanwha New Market Securities Ltd.", "trmend_blce_qota_rt": "100", "invstmnt_purps": "경영참여"},
            {"inv_prm": "Theori Inc.", "trmend_blce_qota_rt": "3.4", "invstmnt_purps": "단순투자"},
            {"inv_prm": "PT Ciptadana Sekuritas Asia(Call-Put옵션평가분)", "invstmnt_purps": "경영참여"},
            {"inv_prm": "Global Opportunity Fund LP", "trmend_blce_qota_rt": "30"},
            {"inv_prm": "한국거래소", "trmend_blce_qota_rt": "3"}]}
    raise AssertionError(path)


class DartRunTest(unittest.TestCase):
    def test_run_with_mocked_dart(self):
        with mock.patch.object(update_dart, "FIRMS", ["한화투자증권"]), \
                mock.patch.object(update_dart.net, "get", return_value=fake_corp_zip()), \
                mock.patch.object(update_dart.net, "get_json", side_effect=fake_json):
            res = update_dart.run("dummy", today=date(2026, 10, 20))
        self.assertEqual(res["errors"], [])
        f = res["firms"]["한화투자증권"]
        self.assertEqual(f["financials"]["equity"], 2_000_000)
        self.assertEqual(f["financials"]["net_income"], 90_000)
        self.assertEqual(f["financials_report"]["label"], "2026 반기보고서")
        self.assertEqual(f["holdings_report"]["label"], "2025 사업보고서")
        names = [h["name"] for h in f["overseas_direct"]]
        self.assertIn("Pinetree Securities Corporation", names)
        self.assertNotIn("한국거래소", names)
        self.assertEqual([e["name"] for e in f["excluded"]], ["Global Opportunity Fund LP"])
        self.assertEqual(f["overseas_direct"][0]["seed_name"], "Pinetree Securities Corporation")
        self.assertEqual(f["new_candidates"], ["Hanwha New Market Securities Ltd."])
        self.assertEqual(len(res["feed"]), 1)

    def test_weekly_diff(self):
        h = lambda n: {"name": n, "purpose": "경영참여", "share_pct": 100}
        prev = {"updated_at": "2026-10-13", "feed": [{"url": "u1"}], "firms": {
            "A": {"financials": {"equity": 10}, "financials_report": {"label": "2026 반기보고서"},
                  "overseas_direct": [h("Old Ltd")], "new_candidates": []},
            "B": {"financials": {"equity": 20}, "financials_report": {"label": "2026 반기보고서"},
                  "overseas_direct": [], "new_candidates": []}}}
        cur = {"feed": [{"url": "u2"}, {"url": "u1"}], "firms": {
            "A": {"financials": {"equity": 30}, "financials_report": {"label": "2026 3분기보고서"},
                  "overseas_direct": [h("New Ltd")], "new_candidates": ["New Ltd"]},
            "B": {"financials": {"equity": 20}, "financials_report": {"label": "2026 반기보고서"},
                  "overseas_direct": [], "new_candidates": []}}}
        d = update_dart.weekly_diff(prev, cur)
        self.assertEqual(d["entities_added"], [{"firm": "A", "name": "New Ltd"}])
        self.assertEqual(d["entities_removed"], [{"firm": "A", "name": "Old Ltd"}])
        self.assertEqual(d["candidates_added"], [{"firm": "A", "name": "New Ltd"}])
        self.assertEqual(d["new_reports"], [{"firm": "A", "label": "2026 3분기보고서"}])
        self.assertEqual({m["firm"] for m in d["rank_moves"]}, {"A", "B"})
        self.assertEqual(d["new_filings"], [{"url": "u2"}])
        self.assertIsNone(update_dart.weekly_diff(None, cur))
        # 주중(공시 시즌) 갱신은 지난 주간 수집본을 압축해 들고 있어, 주간 비교가 같은 결과를 낸다
        self.assertEqual(update_dart.weekly_diff(update_dart.diff_snapshot(prev), cur), d)

    def test_no_key_is_a_noop(self):
        with mock.patch.dict("os.environ", {"DART_API_KEY": ""}):
            update_dart.main()  # 예외 없이 종료


class SeedDataTest(unittest.TestCase):
    def test_seed_is_consistent(self):
        seed = json.loads((ROOT / "site/data/domestic/seed.json").read_text(encoding="utf-8"))
        firms = {f["firm"] for f in seed["firms"]}
        config = json.loads((ROOT / "site/data/config.json").read_text(encoding="utf-8"))
        self.assertEqual(firms, {f["name"] for f in config["firms"]}, "config.json과 seed.json의 회사 목록이 다름")
        for e in seed["entities"]:
            self.assertIn(e["firm"], firms)
            self.assertTrue(e["country"])
            self.assertEqual(e["kind"], "법인", e["name"])



class LiveNamesTest(unittest.TestCase):
    """2026-10 첫 DART 수집에서 나온 실제 법인명으로 매칭·제외 규칙을 고정한다."""

    def seeds(self, firm):
        seed = json.loads((ROOT / "site/data/domestic/seed.json").read_text(encoding="utf-8"))
        return [e for e in seed["entities"] if e["firm"] == firm and e["name"]]

    def test_renamed_or_abbreviated_subsidiaries_match_seed(self):
        cases = [
            ("한국투자증권", "KI&S Europe, Ltd. (런던현지법인)", "Korea Investment & Securities Europe, Ltd."),
            ("한국투자증권", "KI&S Singapore, Pte. Inc. (싱가폴현지법인)", "Korea Investment & Securities Singapore Pte. Ltd."),
            ("한국투자증권", "KIS US", "Korea Investment& Securities US, Inc."),
            ("한국투자증권", "KIS Indonesia. (인도네시아현지법인)", "PT Korea Investment & Sekuritas Indonesia"),
            ("신한투자증권", "Shinhan Investment Asia Ltd.", "Shinhan Securities Asia Ltd."),
            ("신한투자증권", "Shinhan Investment America Inc.", "Shinhan Securities America Inc."),
            ("NH투자증권", "NH nvestment & Securities Europe Ltd", "NH Investment & Securities Europe Ltd.\xa0"),
        ]
        for firm, name, want in cases:
            got = update_dart.match(self.seeds(firm), name, gnd.guess_country(name))
            self.assertEqual((got or "").strip(), want.strip(), name)

    def test_similar_names_resolve_by_country_and_minority_stakes_do_not_borrow_seed(self):
        seeds = self.seeds("한화투자증권")
        self.assertEqual(update_dart.match(seeds, "Pinetree Securities Pte.Ltd.", "싱가포르"), "Pinetree Securities Pte. Ltd.")
        self.assertEqual(update_dart.match(seeds, "Pinetree Securities Corporation", None), "Pinetree Securities Corporation")
        self.assertIsNone(update_dart.match(seeds, "CapBridgeHoldings Pte.Ltd.", "싱가포르", control=False))

    def test_funds_and_instruments_are_not_candidates(self):
        for name in ["The baring Asia Private Equity VII", "Blackstone Capital Partners Asia II", "Ardian Co-Investment V",
                     "Dyal IV Offshore", "IMM Global Hydrogen LPF", "BRVLotusFundIII(PEF)", "한화-NP CHINA 1호",
                     "[심천중한산업기금]", "Octave Tech Investment L25 LLC", "BlackstoneCapitalPartnersVIL.P.",
                     "Indies Special Opportunities IV", "Blackstone Real Estate Debt Strategies IV"]:
            self.assertEqual(gnd.classify_entity(name)[0], "제외", name)
        self.assertEqual(gnd.clean_holding_name("Point2 Technology Inc.(CPS)"), "Point2 Technology Inc.")
        self.assertEqual(gnd.clean_holding_name("Planeta PTE LTD 보통주"), "Planeta PTE LTD")


class SecTest(unittest.TestCase):
    def test_latest_prefers_newest_period_and_full_year(self):
        import update_sec
        facts = {"us-gaap": {
            "StockholdersEquity": {"units": {"USD": [{"val": 10, "end": "2026-06-30", "form": "10-Q"}]}},
            "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": {
                "units": {"USD": [{"val": 9, "end": "2020-12-31", "form": "10-K"}]}},
            "NetIncomeLoss": {"units": {"USD": [
                {"val": 5, "start": "2025-01-01", "end": "2025-12-31", "form": "10-K", "fp": "FY"},
                {"val": 1, "start": "2025-10-01", "end": "2025-12-31", "form": "10-K", "fp": "FY"}]}},
        }}
        self.assertEqual(update_sec.latest(facts, update_sec.EQUITY_TAGS)["value"], 10)
        self.assertEqual(update_sec.latest(facts, update_sec.NI_TAGS, annual=True)["value"], 5)


if __name__ == "__main__":
    unittest.main()


class SubFinTest(unittest.TestCase):
    def test_summarize_skips_spv_and_duplicates(self):
        import fetch_sub_fin as f
        seeds = [{"name": "PT Kiwoom Sekuritas Indonesia", "country": "인도네시아"},
                 {"name": "PT Kiwoom Investment Management", "country": "인도네시아"}]
        subs = {"PT Kiwoom securities Indonesia": {"equity": 100.0, "ni": 5.0, "country": "인도네시아"},
                "PT Kiwoom sekuritas Indonesia": {"equity": 100.0, "ni": 5.0, "country": "인도네시아"},
                "PT Kiwoom Investment Management": {"equity": 10.0, "ni": -1.0, "country": "인도네시아"},
                "MAPS WAIKIKI HOTEL, LLC.": {"equity": 50.0, "ni": -40.0, "country": "미국"}}
        r = f.summarize(subs, seeds)
        self.assertEqual(r["n"], 2)
        self.assertEqual(r["equity"], 110.0)
        self.assertEqual(r["roe"], round(4 / 110 * 100, 2))

    def test_holding_company_children_are_counted_once(self):
        """중간지주(별도재무제표 행) 자본에서 함께 합산되는 자회사 자본 × 지분율을 빼고, 순이익은 그대로 둔다."""
        import fetch_sub_fin as f
        seeds = [{"name": n} for n in ("Mirae Asset Securities (HK) Limited", "Mirae Asset Securities (Vietnam) JSC",
                                       "Mirae Asset Securities Mongolia UTsK LLC", "Mirae Asset Securities Finance (HK) Limited",
                                       "Mirae Asset Securities Holdings (USA) Inc.", "Mirae Asset Securities (USA) Inc.",
                                       "Korea Investment & Securities Asia, Ltd.")]
        subs = {"Mirae Asset Securities (HK) Limited": {"equity": 1000.0, "ni": 50.0, "parent": "미래에셋증권 주식회사", "own": 100.0},
                "Mirae Asset Securities (Vietnam) JSC": {"equity": 300.0, "ni": 20.0, "parent": "Mirae Asset Securities (HK)Limited", "own": 99.9},
                "Mirae Asset Securities Mongolia UTsK LLC": {"equity": 10.0, "ni": 1.0, "parent": "Mirae Asset Securities (HK)Limited", "own": 80.0},
                "Mirae Asset Securities Finance (HK) Limited": {"equity": -5.0, "ni": -1.0, "parent": "Mirae Asset Securities (HK)Limited", "own": 100.0},
                "Mirae Asset Securities Holdings (USA) Inc.": {"equity": 700.0, "ni": 1.0, "parent": "미래에셋증권 주식회사", "own": 100.0},
                "Mirae Asset Securities (USA) Inc.": {"equity": 900.0, "ni": 90.0, "parent": "Mirae Asset SecuritiesHoldings (USA) Inc"},
                "Korea Investment & Securities Asia, Ltd.": {"equity": 100.0, "ni": 3.0, "parent": "한국투자증권㈜", "own": 100.0}}
        r = f.summarize(subs, seeds)
        overlap = 300 * 0.999 + 10 * 0.8 + 700  # 음수 자본 자회사는 빼지 않고, 순수 지주는 자기 자본까지만 뺀다
        self.assertAlmostEqual(r["overlap"], round(overlap, 1))
        self.assertEqual(r["equity"], round(3005 - overlap, 1))
        self.assertEqual(r["ni"], 164.0)
        self.assertEqual(r["holdcos"], ["Mirae Asset Securities (HK) Limited", "Mirae Asset Securities Holdings (USA) Inc."])

    def test_parent_structure_from_tables_and_footnotes(self):
        """투자회사 칸이 병합된 표(미래에셋·한투·KB 형식)와 'A의 투자회사는 B' 각주(키움 형식)에서 모회사를 읽는다."""
        import fetch_sub_fin as f
        mirae = _html_table([
            ["(1) 연결대상 종속기업의 개요 당기말과 전기말 현재 연결대상 종속기업의 내역은 다음과 같습니다. 투자회사", "피투자회사",
             "주요영업활동", "법인설립 및영업소재지", "소유지분율 및의결권비율(%)"],
            ["제 57(당)기말", "제 56(전)기말"],
            ["미래에셋증권 주식회사", "Mirae Asset Securities (HK) Limited", "증권중개 및 투자업", "홍콩", "100.00", "100.00"],
            ["Mirae Asset Capital Markets (India) Private Limited", "증권중개 및 투자업", "인도", "100.00", "100.00"],
            ["Mirae Asset Securities (HK)Limited", "Mirae Asset Securities (Vietnam) JSC", "증권중개 및 투자업", "베트남", "99.90", "99.90"],
            ["Mirae Asset Securities Mongolia UTsK LLC", "투자업 및 투자자문업", "몽골", "83.16", "83.16"],
            ["미래에셋해외부동산전문투자형사모투자신탁제6-1호"],
            ["OPPCI Mahajunga Holding", "SCI Mahajunga", "부동산투자 및 임대업", "프랑스", "85.00", "85.00"]])
        kis = _html_table([
            ["투 자 기 업", "피 투 자 기 업", "제 54(당)기", "제 53(전)기"], ["지분율(%)", "지분율(%)"],
            ["한국투자증권㈜", "Korea Investment& Securities US, Inc.", "100.00", "100.00"],
            ["Korea Investment & Securities US, Inc.", "Korea Investment & Securities America, Inc.", "100.00", "100.00"]])
        kb = _html_table([
            ["투자회사", "회사명", "업종", "지분율 (%)", "소재지", "사용재무제표일"],
            ["지배기업", "KB Securities Hong Kong Ltd.", "투자자문,증권매매", "100.00", "홍콩", "12월"],
            ["PT. KB Valbury Sekuritas", "투자자문,증권매매", "65.00", "인도네시아", "12월"],
            ["KB Securities Hong Kong Ltd.", "Global Investment Opportunity Limited", "금융 및 부동산투자업", "100.00", "말레이시아", "12월"]])
        hana = _html_table([
            ["투자기업", "피투자기업", "지역", "업종", "투자주식수", "지분율"],
            ["하나증권", "하나지분투자관리(심천)유한공사", "중국", "자산운용업", "100,200,000", "50.10%"]])
        direct = _html_table([["구 분", "피투자회사", "소재지", "지분율", "장부금액"],
                              ["종속기업(주1)", "Kiwoom Securities Holdings USA Inc.", "미국", "100%", "29,121,650"]])
        kiwoom = _html_table([
            ["(주5)", "Kiwoom Asia Master Fund의 투자회사는 Kiwoom Asia Feeder Fund입니다."],
            ["(주6)", "Kiwoom Securities USA Inc.의 투자회사는 Kiwoom Securities Holdings USA Inc.입니다."]])
        p = f.parse_parents([mirae + kis, kb + hana + direct + kiwoom])
        self.assertEqual(p["Mirae Asset Securities (HK) Limited"], ("미래에셋증권 주식회사", 100.0))
        self.assertEqual(p["Mirae Asset Capital Markets (India) Private Limited"], ("미래에셋증권 주식회사", 100.0))
        self.assertEqual(p["Mirae Asset Securities Mongolia UTsK LLC"], ("Mirae Asset Securities (HK)Limited", 83.16))
        self.assertEqual(p["SCI Mahajunga"], ("OPPCI Mahajunga Holding", 85.0))
        self.assertEqual(p["Korea Investment & Securities America, Inc."], ("Korea Investment & Securities US, Inc.", 100.0))
        self.assertNotIn("PT. KB Valbury Sekuritas", p)  # '지배기업' 구분 칸은 모회사 이름이 아니라 직접 출자로 둔다
        self.assertEqual(p["Global Investment Opportunity Limited"], ("KB Securities Hong Kong Ltd.", 100.0))
        self.assertEqual(p["하나지분투자관리(심천)유한공사"], ("하나증권", 50.1))
        self.assertEqual(p["Kiwoom Securities USA Inc."], ("Kiwoom Securities Holdings USA Inc.", None))
        self.assertNotIn("Kiwoom Securities Holdings USA Inc.", p)  # 별도재무제표 직접 출자 표의 '종속기업(주1)' 구분 칸
        subs = f.attach_parents({"Kiwoom Securities USA Inc.": {"equity": 1.0, "ni": 0.0},
                                 "Mirae Asset Securities Mongolia UTsK LLC": {"equity": 1.0, "ni": 0.0}}, p)
        self.assertEqual(subs["Kiwoom Securities USA Inc."]["parent"], "Kiwoom Securities Holdings USA Inc.")
        self.assertEqual(subs["Mirae Asset Securities Mongolia UTsK LLC"]["own"], 83.16)
        toss = ("요약 재무정보 (단위: 천원)" + _html_table([["회사명", "자산", "부채", "자본", "영업수익", "당기순손익", "총포괄손익"],
                                                    ["Toss Securities Holdings US Inc.(*)", "9,987,694", "8,077,343", "1,910,351", "771", "(6,220,341)", "(6,487,286)"]])
                + "(*) Toss Securities Holdings US Inc. 및 그 종속기업이 포함된 중간지배기업의 연결재무정보입니다.(2) 전기말")
        subs = f.mark_consolidated({"Toss Securities Holdings US Inc.(*)": {"equity": 1910.4, "ni": -6220.3},
                                    "Toss Securities Global Pte. Ltd.": {"equity": 136.3, "ni": -7.2}}, [toss])
        self.assertTrue(subs["Toss Securities Holdings US Inc.(*)"].get("consolidated"))
        self.assertNotIn("consolidated", subs["Toss Securities Global Pte. Ltd."])


class MacroNewsTest(unittest.TestCase):
    def test_pick_prefers_index_reclassification_and_needs_country_and_macro_words(self):
        import fetch_macro_news as m
        names = m.COUNTRIES["ID"][1]
        items = [
            {"date": "2026-10-20", "title": "Indonesia stocks edge higher", "src": "Reuters", "url": "u1"},
            {"date": "2026-10-16", "title": "MSCI proposes Indonesia downgrade from emerging market", "src": "Reuters", "url": "u2"},
            {"date": "2026-10-19", "title": "Jakarta traffic eases", "src": "Reuters", "url": "u3"},
            {"date": "2026-10-18", "title": "Vietnam stocks rally", "src": "Reuters", "url": "u4"},
        ]
        got = m.pick(items, names)
        self.assertEqual([x["url"] for x in got], ["u2", "u1"])
        self.assertTrue(got[0]["priority"])
        self.assertTrue(m.trusted("Reuters") and not m.trusted("some blog"))

    def test_worldmap_has_countries_used_by_overview(self):
        wm = json.loads((ROOT / "site" / "data" / "global" / "worldmap.json").read_text(encoding="utf-8"))
        for iso in ["840", "360", "704", "826", "356", "156", "392", "076", "300", "496"]:
            self.assertIn(iso, wm["countries"])


class AutoEntityTest(unittest.TestCase):
    def test_financial_subsidiaries_are_added_others_stay_candidates(self):
        base = {"purpose": "경영참여", "share_pct": 100.0}
        self.assertEqual(gnd.auto_new_entity({**base, "name": "Kiwoom Securities Holdings USA Inc.", "country_guess": "미국"}), (True, None))
        self.assertEqual(gnd.auto_new_entity({**base, "name": "진우(북경)투자자문유한공사", "country_guess": "중국"}), (True, None))
        self.assertEqual(gnd.auto_new_entity({**base, "name": "Zharyk Zhol Company 2007. LLP", "country_guess": "카자흐스탄"}), (False, "업종 확인 필요"))
        self.assertEqual(gnd.auto_new_entity({**base, "name": "ABC Global Fund I", "country_guess": "미국"})[0], False)
        self.assertEqual(gnd.auto_new_entity({"purpose": "단순투자", "share_pct": 100.0, "name": "X Securities", "country_guess": "미국"})[0], False)


def _html_table(rows):
    return "<TABLE>" + "".join("<TR>" + "".join(f"<TD>{c}</TD>" for c in r) + "</TR>" for r in rows) + "</TABLE>"


class SubsidiaryListTest(unittest.TestCase):
    """비상장사·감사보고서의 주석 표(신한·토스 형식)와 둘로 나뉜 요약재무 표를 읽는다."""

    def test_note_tables_and_split_summary(self):
        from fetch_consolidated import classify, parse_consolidated
        from fetch_sub_fin import parse_doc
        shinhan = ("(2) 종속기업의 현황 1) 종속기업" + _html_table([
            ["투자회사", "피투자회사", "소재지", "업종", "결산월", "투자주식수(주)", "지분율"],
            ["신한투자증권", "Shinhan Securities America Inc.", "미국", "금융투자업", "12월", "25,000", "100%"],
            ["Shinhan Securities Asia Ltd.", "홍콩", "금융투자업", "12월", "762,000,000", "100%"],
            ["신한투자증권", "디큐브공간제일차", "한국", "자산유동화", "12월", "-", "0%"]])
            + "(4) 요약 재무정보 1) 종속기업의 요약재무상태표 (단위 : 백만원)" + _html_table([
            ["회사명", "제27(당)기", "제26(전)기"], ["자산총계", "부채총계", "자본총계", "자산총계", "부채총계", "자본총계"],
            ["Shinhan Securities Asia Ltd.", "177,081", "784", "176,297", "178,586", "1,270", "177,316"]])
            + "2) 종속기업의 요약포괄손익계산서 (단위 : 백만원)" + _html_table([
            ["회사명", "제27(당)기", "제26(전)기"], ["영업수익", "당기순손익", "총포괄손익", "영업수익", "당기순손익", "총포괄손익"],
            ["Shinhan Securities Asia Ltd.", "11,647", "3,563", "(1,019)", "14,683", "4,202", "26,673"]]))
        toss = ("1.2 종속기업의 현황 연결대상 종속기업의 현황은 다음과 같습니다." + _html_table([
            ["회사명", "업종", "지분율(%)", "소재지", "결산월"], ["당기말", "전기말"],
            ["Toss Securities Global Pte. Ltd.(*3)", "투자업", "100.00%", "-", "싱가포르", "12월"]]))
        rows = {r["name"]: r for r in parse_consolidated([shinhan, toss])}
        self.assertEqual(rows["Shinhan Securities America Inc."]["country"], "미국")
        self.assertEqual(rows["Shinhan Securities Asia Ltd."]["country"], "홍콩")
        self.assertEqual(rows["Toss Securities Global Pte. Ltd."]["country"], "싱가포르")
        self.assertEqual(rows["디큐브공간제일차"]["country"], "한국")
        self.assertEqual(classify("Shinhan Securities Asia Ltd.", "금융투자업")[0], "영업법인")
        self.assertEqual(classify("Toss Securities Holdings US Inc.", "투자업")[0], "지주회사")
        fin = parse_doc([shinhan])["Shinhan Securities Asia Ltd."]
        self.assertEqual((fin["equity"], fin["ni"]), (176297.0, 3563.0))

    def test_finalize_rule_and_dedupe(self):
        from fetch_consolidated import finalize
        rows = [
            {"name": "Pinetree Securities Pte.Ltd㈜", "country": "싱가포르", "business": "증권업", "assets": 5078.0, "table": "list"},
            {"name": "Pinetree Securities Pte.Ltd.", "country": "싱가포르", "business": "금융투자업", "assets": None, "table": "note"},
            {"name": "Pinetree Securities Corporation", "country": "베트남", "business": "금융투자업", "table": "note"},
            {"name": "PT Ciptadana Asset Management", "country": "인도네시아", "business": "자산운용업", "table": "note"},
            {"name": "Zharyk Zhol Company 2007. LLP", "country": "카자흐스탄", "business": "부동산투자(SPC)", "table": "list"},
            {"name": "Kiwoom BVI One Limited", "country": "영국령버진아일랜드", "business": "기타금융", "table": "list"},
            {"name": "Kiwoom Securities Holdings USA Inc.", "country": "미국", "business": "기타금융", "table": "list"},
            {"name": "Sharekhan Commodities Private Limited", "country": "인도", "business": "휴면", "table": "list"},
            {"name": "증권중개 및 투자업", "country": "홍콩", "business": "홍콩", "table": "note"},
            {"name": "Mirae Asset Technology Innovation Center (Shenzhen) Co., Ltd", "country": "홍콩", "business": "기타", "table": "list"},
        ]
        seeds = [{"name": "Pinetree Securities Pte. Ltd.", "country": "싱가포르"}]
        out = {x["name"]: x for x in finalize(rows, seeds)}
        self.assertEqual(len(out), 8)  # 싱가포르 중복 하나, 업종이 상호 칸에 밀린 행 하나 제외
        sg = next(x for x in out.values() if x["country"] == "싱가포르")
        self.assertEqual((sg["assets"], sg["seed_name"], sg["class"]), (5078.0, "Pinetree Securities Pte. Ltd.", "영업법인"))
        self.assertEqual(out["PT Ciptadana Asset Management"]["class"], "영업법인")
        self.assertEqual(out["Pinetree Securities Corporation"]["class"], "영업법인")
        for n in ("Zharyk Zhol Company 2007. LLP", "Kiwoom BVI One Limited", "Sharekhan Commodities Private Limited"):
            self.assertEqual(out[n]["class"], "제외", n)
        self.assertEqual(out["Kiwoom Securities Holdings USA Inc."]["class"], "지주회사")
        self.assertEqual(out["Mirae Asset Technology Innovation Center (Shenzhen) Co., Ltd"]["country"], "중국")


class KeysTest(unittest.TestCase):
    """API 키: 환경변수 → .env → 터미널에서만 숨김 입력. CI에서는 절대 묻지 않는다."""

    def test_order_and_no_prompt_in_ci(self):
        import tempfile
        from pathlib import Path
        import keys
        with tempfile.TemporaryDirectory() as d, mock.patch.object(keys, "ROOT", Path(d)), \
                mock.patch("getpass.getpass", return_value="typed") as gp:
            env = {k: v for k, v in os.environ.items() if k not in ("DART_API_KEY", "CI", "GITHUB_ACTIONS", "GND_NO_PROMPT")}
            with mock.patch.dict("os.environ", env, clear=True):
                with mock.patch.object(keys, "can_prompt", return_value=True):
                    self.assertEqual(keys.get_key("DART_API_KEY"), "typed")   # 없으면 묻는다
                    self.assertEqual(os.environ["DART_API_KEY"], "typed")       # 같은 실행에선 다시 안 묻는다
                    del os.environ["DART_API_KEY"]
                    (Path(d) / ".env").write_text('# 주석\nDART_API_KEY="from-file"\n', encoding="utf-8")
                    self.assertEqual(keys.get_key("DART_API_KEY"), "from-file")  # .env 가 입력보다 먼저
                    del os.environ["DART_API_KEY"]
                    (Path(d) / ".env").unlink()
                os.environ["CI"] = "true"
                self.assertFalse(keys.can_prompt())
                self.assertEqual(keys.get_key("DART_API_KEY"), "")              # CI: 묻지 않고 빈 값
            with mock.patch.dict("os.environ", {"DART_API_KEY": ""}):
                self.assertEqual(keys.get_key("DART_API_KEY"), "")              # 정의된 빈 값은 그대로(Actions Secret 없음)
            self.assertEqual(gp.call_count, 1)


class SubTrendTest(unittest.TestCase):
    """해외법인 5개년 손익 추이: 보고서 고르기, 연도별 법인 짝짓기, 영업수익 칸."""

    def test_periods_keep_latest_filing_and_first_date(self):
        import fetch_sub_trend as t
        rows = [{"report_nm": "[기재정정]사업보고서 (2025.12)", "rcept_no": "3", "rcept_dt": "20260515"},
                {"report_nm": "반기보고서 (2026.06)", "rcept_no": "4", "rcept_dt": "20260814"},
                {"report_nm": "사업보고서 (2025.12)", "rcept_no": "2", "rcept_dt": "20260317"},
                {"report_nm": "분기보고서 (2026.03)", "rcept_no": "5", "rcept_dt": "20260515"},
                *({"report_nm": f"사업보고서 ({y}.12)", "rcept_no": f"y{y}", "rcept_dt": f"{y + 1}0320"} for y in range(2019, 2025))]
        p = t.periods_of(sorted(rows, key=lambda r: r["rcept_dt"], reverse=True))
        self.assertEqual(p["FY2025"]["rcept_no"], "3")          # 정정본 원문을 쓰고
        self.assertEqual(p["FY2025"]["first_dt"], "20260317")   # 공시 일정은 처음 제출일로
        self.assertNotIn("1Q2026", p)
        self.assertEqual(t.window(p), ["FY2021", "FY2022", "FY2023", "FY2024", "FY2025", "1H2026"])
        p.pop("FY2025")  # 아직 사업보고서가 안 나온 회사: 1H2026은 최근 사업연도(FY2024)보다 뒤라 그대로 둔다
        self.assertEqual(t.window(p), ["FY2020", "FY2021", "FY2022", "FY2023", "FY2024", "1H2026"])
        audit = t.periods_of([{"report_nm": "감사보고서 (2025.12)", "rcept_no": "a", "rcept_dt": "20260401"},
                              {"report_nm": "연결감사보고서 (2025.12)", "rcept_no": "b", "rcept_dt": "20260331"}], audit=True)
        self.assertEqual(audit["FY2025"]["rcept_no"], "b")      # 연결감사보고서를 먼저
        self.assertEqual(t.norm_date("1998년 10월 01일"), "1998.10.01")
        self.assertEqual(t.norm_date("2019-11-01"), "2019.11.01")

    def test_build_matches_years_holdcos_and_reference_rows(self):
        import fetch_sub_trend as t
        seeds = {"미래에셋증권": [{"name": "Mirae Asset Securities (HK) Limited", "country": "홍콩"},
                                {"name": "Mirae Asset Securities (Vietnam) JSC", "country": "베트남"}]}
        refs = {"하나증권": [{"name": "BIDV Securities Joint Stock Company (BSC)", "country": "베트남"}]}
        rep = lambda dt, subs, assoc=None: {"rcept_no": dt, "label": "", "rcept_dt": dt, "first_dt": dt, "subs": subs, "assoc": assoc or {}}  # noqa: E731
        raw = {"firms": {
            "미래에셋증권": {
                "FY2024": rep("20250317", {"Mirae Asset Securities (HK) Ltd.": {"rev": 100.0, "ni": -5.0, "equity": 900.0},
                                           "Mirae Asset Securities (Vietnam) JSC": {"rev": 50.0, "ni": 3.0, "equity": 200.0}}),
                "FY2025": rep("20260310", {"Mirae Asset Securities (HK) Limited": {"rev": 120.0, "ni": 8.0, "equity": 1000.0, "parent": "미래에셋증권 주식회사"},
                                           "Mirae Asset Securities (Vietnam) JSC": {"rev": 60.0, "ni": 4.0, "equity": 210.0,
                                                                                    "parent": "Mirae Asset Securities (HK)Limited", "own": 99.9}}),
                "1H2026": rep("20260814", {})},
            "하나증권": {"FY2025": rep("20260320", {}, {"BIDV Securities Joint Stock Company": {"rev": 70.0, "ni": 19.0, "equity": 300.0}})},
            "토스증권": {"FY2025": {**rep("20260401", {}), "label": "2025 감사보고서"}}}}
        with mock.patch.object(t, "seeds_by_firm", return_value=seeds), mock.patch.object(t, "ref_seeds", return_value=refs), \
                mock.patch.object(t, "entity_meta", return_value={}):
            out = t.build(raw)
        self.assertEqual(out["periods"], ["FY2024", "FY2025", "1H2026"])
        self.assertEqual(out["filing"]["FY2025"], {"label": "", "first": "20260310", "last": "20260401", "n": 3})
        ents = {e["name"]: e for e in out["firms"]["미래에셋증권"]["entities"]}
        hk, vn = ents["Mirae Asset Securities (HK) Limited"], ents["Mirae Asset Securities (Vietnam) JSC"]
        self.assertEqual(hk["values"]["FY2024"], {"rev": 100.0, "ni": -5.0})  # 표기가 다른 지난해 행도 같은 법인
        self.assertTrue(hk["holding"])
        self.assertEqual(hk["children"], 1)
        self.assertEqual((vn["parent_entity"], vn["own"]), ("Mirae Asset Securities (HK) Limited", 99.9))
        self.assertEqual(out["firms"]["미래에셋증권"]["reports"]["1H2026"]["rows"], 0)  # 반기 표가 없는 회사
        self.assertTrue(out["firms"]["토스증권"]["audit"])                         # 감사보고서만 내는 회사(반기보고서 없음)
        self.assertNotIn("audit", out["firms"]["미래에셋증권"])
        bidv = out["firms"]["하나증권"]["entities"][0]
        self.assertTrue(bidv["ref"])
        self.assertEqual(bidv["values"]["FY2025"]["ni"], 19.0)

    def test_summary_table_revenue_column(self):
        from fetch_sub_fin import parse_doc
        toss = "요약 재무정보 종속기업 (단위: 천원)" + _html_table([
            ["회사명", "자산", "부채", "자본", "영업수익", "당기순손익", "총포괄손익"],
            ["Toss Securities Global Pte. Ltd.", "9,987,694", "8,077,343", "1,910,351", "2,771,000", "(6,220,341)", "(6,487,286)"]])
        assoc = "관계기업의 요약재무정보 (단위: 백만원)" + _html_table([
            ["회사명", "자산", "부채", "매출액", "당기순이익"], ["BIDV Securities Joint Stock Company", "1,000", "700", "70", "19"]])
        r = parse_doc([toss])["Toss Securities Global Pte. Ltd."]
        self.assertEqual((r["rev"], r["ni"]), (2771.0, -6220.3))
        self.assertNotIn("BIDV Securities Joint Stock Company", parse_doc([assoc]))  # 관계기업 표는 따로 읽는다
        a = parse_doc([assoc], marker=r"관계기업|공동기업")["BIDV Securities Joint Stock Company"]
        self.assertEqual((a["rev"], a["ni"], a["equity"]), (70.0, 19.0, 300.0))
        # 영업수익 칸 없이 순영업손익만 싣는 회사(삼성증권)
        samsung = "당기말 현재 종속기업의 요약 재무상태 및 경영성과 (단위: 천원)" + _html_table([
            ["회사명", "자산총계", "부채총계", "순영업손익", "순손익", "총포괄손익"],
            ["Samsung Securities (America) Inc.", "59,934,293", "1,606,705", "7,277,966", "1,888,058", "469,444"]])
        r = parse_doc([samsung])["Samsung Securities (America) Inc."]
        self.assertEqual((r["rev"], r["ni"], r["rev_net"]), (7278.0, 1888.1, True))
        self.assertNotIn("rev_net", parse_doc([toss])["Toss Securities Global Pte. Ltd."])


    def test_half_year_tables_skip_prior_period(self):
        from fetch_sub_fin import parse_doc
        table = lambda rev, ni: _html_table([  # noqa: E731
            ["회사명", "자산", "부채", "자본", "영업수익", "반기순이익"],
            ["Toss Securities Global Pte. Ltd.", "1,000", "800", "200", rev, ni]])
        # 반기보고서는 '당반기/전반기'로 쓴다. 전반기 표가 먼저 나와도 당반기 값을 쓴다
        prior_first = "종속기업의 요약재무정보 ② 전반기 (단위: 백만원)" + table("8", "1") + "① 당반기 (단위: 백만원)" + table("10", "2")
        current_first = "종속기업의 요약재무정보 ① 당반기 (단위: 백만원)" + table("10", "2") + "② 전반기 (단위: 백만원)" + table("8", "1")
        for doc in (prior_first, current_first):
            r = parse_doc([doc])["Toss Securities Global Pte. Ltd."]
            self.assertEqual((r["rev"], r["ni"]), (10.0, 2.0))

    def test_collect_keeps_visible_half_year_and_refetches_old_parser(self):
        import tempfile
        import fetch_sub_trend as t
        rep = lambda nm, no: {"report_nm": nm, "rcept_no": no, "rcept_dt": "20" + no[:6]}  # noqa: E731
        annual = lambda y: rep(f"사업보고서 ({y}.12)", f"{(y + 1) % 100:02d}0310{y}")  # noqa: E731
        lists = {"a": [annual(y) for y in range(2021, 2027)] + [rep("반기보고서 (2026.06)", "260814h1")],
                 "b": [annual(y) for y in range(2021, 2026)] + [rep("반기보고서 (2026.06)", "260814h1")]}
        old = lambda r, parser=t.PARSER: {"rcept_no": r["rcept_no"], "label": "", "rcept_dt": r["rcept_dt"], "first_dt": r["rcept_dt"],  # noqa: E731
                                          "parser": parser, "subs": {}, "assoc": {}}
        per = lambda r: t.periods_of([r]).popitem()[0]  # noqa: E731
        raw = {"firms": {f: {per(r): old(r) for r in rows if "2026.12" not in r["report_nm"]} for f, rows in lists.items()}}
        raw["firms"]["b"]["FY2025"]["parser"] = t.PARSER - 1  # 예전 규칙으로 읽은 보고서
        fetched = []
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "dart_latest.json").write_text(json.dumps({"firms": {"a": {"corp_code": "a"}, "b": {"corp_code": "b"}}}), encoding="utf-8")
            with mock.patch.object(t, "DATA", Path(tmp)), mock.patch.object(t, "listing", side_effect=lambda k, c, ty, d: lists[c] if ty == "A" else []), \
                    mock.patch.object(t, "document_texts", side_effect=lambda k, no: fetched.append(no) or []):
                new, errors = t.collect("k", raw, date(2027, 3, 12))
        self.assertEqual((errors, len(new)), ([], 1))                          # 새 보고서는 a의 FY2026 하나(규칙만 바뀐 재수집은 새 보고서 아님)
        self.assertEqual(sorted(fetched), ["2603102025", "2703102026"])
        self.assertIn("1H2026", raw["firms"]["a"])                             # b가 FY2026을 내기 전까지 1H 열이 남으니 a의 1H도 둔다
        self.assertNotIn("FY2021", raw["firms"]["a"])
        self.assertEqual(raw["firms"]["b"]["FY2025"]["parser"], t.PARSER)

    def test_renamed_entity_bridges_only_unique_match(self):
        import fetch_sub_trend as t
        rows = {"Shinhan Securities America Inc.": {"ni": 1.0}, "Shinhan Securities Vietnam Co., Ltd.": {"ni": 2.0, "seed_name": "x"}}
        picked = t.renamed(rows, {}, [{"name": "Shinhan Investment America Inc."}])
        self.assertIs(picked["Shinhan Investment America Inc."], rows["Shinhan Securities America Inc."])
        # 구분 단어가 같은 기준 법인이 둘이면 어느 쪽인지 모르니 잇지 않는다
        rows = {"Shinhan Securities America Inc.": {"ni": 1.0}}
        twins = [{"name": "Shinhan Investment America Inc."}, {"name": "Shinhan America Inc."}]
        self.assertEqual(t.renamed(rows, {}, twins), {})


class HubNewsTest(unittest.TestCase):
    def test_title_needs_firm_country_and_hub_words(self):
        import fetch_hub_news as h
        self.assertTrue(h.relevant("미래에셋증권, 홍콩법인에 3000억 증자", "미래에셋증권", "홍콩"))
        self.assertTrue(h.relevant("미래에셋, 인도 현지법인 쉐어칸 인수 마무리", "미래에셋증권", "인도"))
        self.assertFalse(h.relevant("미래에셋, 인도네시아 법인 리테일 1위", "미래에셋증권", "인도"))       # 인도 ≠ 인도네시아
        self.assertTrue(h.relevant("미래에셋, 인도네시아 법인 리테일 1위", "미래에셋증권", "인도네시아"))
        self.assertFalse(h.relevant("미래에셋자산운용, 홍콩법인 ETF 상장", "미래에셋증권", "홍콩"))       # 같은 그룹 운용사
        self.assertFalse(h.relevant("한국투자신탁운용 베트남 법인 설립", "한국투자증권", "베트남"))
        self.assertFalse(h.relevant("KB증권, 미국 주식 소수점 이벤트", "KB증권", "미국"))               # 법인 이야기가 아님
        self.assertTrue(h.relevant("KB Securities Vietnam posts record profit", "KB증권", "베트남"))     # 영문은 증권사·나라만
        self.assertTrue(h.relevant("한화투자증권, 싱가포르 법인 Pinetree 인가 확대", "한화투자증권", "싱가포르"))
        self.assertFalse(h.relevant("신한투자증권 베트남 법인 증자", "한국투자증권", "베트남"))           # '신한투자' 속 '한투'
        self.assertTrue(h.relevant("신한투자증권 베트남 법인 증자", "신한투자증권", "베트남"))
        self.assertFalse(h.relevant("NH투자증권, 해외법인 선전에 3분기 순익 증가", "NH투자증권", "중국"))  # 선전(善戰) ≠ 선전(深圳)
        self.assertFalse(h.relevant("미래에셋증권, 中企 해외진출 지원", "미래에셋증권", "중국"))
        self.assertTrue(h.relevant("한국투자증권, 선전 법인 설립 인가", "한국투자증권", "중국"))
        self.assertFalse(h.relevant("한국투자공사, 美 사모대출 지분 인수", "한국투자증권", "미국"))
        self.assertFalse(h.relevant("키움 히어로즈 송성문, 미국 진출 선언", "키움증권", "미국"))
        self.assertTrue(h.relevant("KB證 베트남법인 증자", "KB증권", "베트남"))
        self.assertTrue(h.relevant("한국투자증권, 印尼 법인 증자", "한국투자증권", "인도네시아"))
        self.assertFalse(h.relevant("한국투자증권, 印尼 법인 증자", "한국투자증권", "인도"))
        # 기사에서 흔히 쓰는 짧은 이름
        self.assertTrue(h.relevant("신한증권 뉴욕법인, 키움증권 품으로…현지당국 인가만 남았다", "신한투자증권", "미국"))
        self.assertTrue(h.relevant("NH증권 싱가포르 법인 증자", "NH투자증권", "싱가포르"))
        # '… 이어'로 나열한 이미 진출한 나라는 그 나라 기사가 아니다
        t = "[단독] 토스증권 글로벌무대 넓힌다…미국·싱가포르 이어 일본 법인 설립"
        self.assertEqual([c for c in ("미국", "싱가포르", "일본") if h.relevant(t, "토스증권", c)], ["일본"])
        self.assertTrue(h.relevant("한국투자증권, 홍콩에 이어 베트남 법인 증자", "한국투자증권", "베트남"))
        self.assertFalse(h.relevant("한국투자증권, 홍콩에 이어 베트남 법인 증자", "한국투자증권", "홍콩"))
        self.assertIn(("신한증권 미국", "ko"), h.queries("신한투자증권", "미국"))
        self.assertLessEqual({("한화증권 인니", "ko"), ("한화투자증권 인도네시아", "ko"), ("칩타다나", "ko")}, set(h.queries("한화투자증권", "인도네시아")))
        self.assertTrue(h.relevant("칩타다나증권, 인니 IPO 주관 실적 1위", "한화투자증권", "인도네시아"))  # 증권사 이름 없이 현지 법인 한글 이름
        self.assertFalse(h.relevant("칩타다나증권, 인니 IPO 주관 실적 1위", "한화투자증권", "베트남"))

    def test_same_event_from_several_outlets_kept_once(self):
        import fetch_hub_news as h
        a = lambda d, t: {"date": d, "title": t, "src": "연합뉴스", "url": t}  # noqa: E731
        got = h.distinct([a("2026-04-15", "미래에셋증권, 홍콩서 디지털자산 라이선스 획득"),
                          a("2026-04-16", "Mirae Asset Securities wins Hong Kong license"),
                          a("2026-04-15", "미래에셋증권, 국내 최초 홍콩 디지털자산 리테일 진출"),
                          a("2025-12-04", "미래에셋, 홍콩법인 증자")])
        self.assertEqual([x["date"] for x in got], ["2026-04-16", "2025-12-04"])


    def test_energy_stocks_are_not_holding_company(self):
        import fetch_hub_news as h
        t = '하나증권 "미국 이란 종전협상 기대감에 국제유가 하락, 항공·에너지주 투심 개선 전망"'
        self.assertFalse(h.relevant(t, "하나증권", "미국"))       # '에너지주'의 '지주'
        self.assertTrue(h.relevant("하나증권, 미국 지주사 지분 인수", "하나증권", "미국"))


def _rss(*items):
    """(제목, 매체, 매체 주소, 날짜) → Google News RSS 모양 바이트."""
    from email.utils import format_datetime
    from datetime import datetime, timezone
    from xml.sax.saxutils import escape, quoteattr
    body = "".join(
        f"<item><title>{escape(t)} - {escape(s)}</title><link>https://news.google.com/a/{i}</link>"
        f"<pubDate>{format_datetime(datetime.fromisoformat(d).replace(tzinfo=timezone.utc))}</pubDate>"
        f"<source url={quoteattr(u)}>{escape(s)}</source></item>" for i, (t, s, u, d) in enumerate(items))
    return f"<rss><channel>{body}</channel></rss>".encode()


class ForeignNewsTest(unittest.TestCase):
    """해외 공신력 있는 매체(도메인)·현지 법인 이름 검색·외국어 제목 규칙·최근 5년 대체."""

    def test_foreign_sites_by_domain(self):
        import fetch_news as n
        self.assertTrue(n.foreign_site("https://www.reuters.com") and n.foreign_site("investasi.kontan.co.id"))
        self.assertFalse(n.foreign_site("finance.biggo.com") or n.foreign_site("pinetree.vn") or n.foreign_site("notreuters.com"))
        self.assertTrue(n.trusted("Reuters") and n.trusted("CafeF", "cafef.vn") and n.trusted("연합뉴스"))
        self.assertFalse(n.trusted("BigGo Finance", "finance.biggo.com"))                       # 모음 사이트
        self.assertFalse(n.trusted("Chứng khoán Pinetree", "pinetree.vn"))                       # 회사 자체 사이트
        self.assertTrue(n.is_foreign("CafeF", "cafef.vn") and n.is_foreign("Bloomberg.com", ""))
        self.assertFalse(n.is_foreign("The Korea Herald", "www.koreaherald.com") or n.is_foreign("연합뉴스", ""))

    def test_language_of_title(self):
        import fetch_news as n
        self.assertEqual([n.lang_of(t) for t in ["미래에셋 인니법인 증자", "Chứng khoán KB Việt Nam báo lãi",
                                                   "Ciptadana Luncurkan PinePick, Platform Trading Saham", "Mirae Asset wins license"]],
                         ["ko", "vi", "id", "en"])
        # 영문 기사의 'Việt Nam'·사람 이름 Dan, 인도네시아어 낱말 하나만 섞인 영문 제목은 영어
        self.assertEqual([n.lang_of(t) for t in ["KB Securities Việt Nam wins award", "Dan Kim joins Mirae Asset as CEO",
                                                   "NH Korindo Sekuritas named best broker for the year", "NH Korindo Sekuritas raih penghargaan di Jakarta"]],
                         ["en", "en", "en", "id"])
        # 인도네시아어 매체 기사는 인도네시아어 흔적 하나로도(영문판·영어 낱말 둘 이상은 영어)
        self.assertEqual([n.lang_of(t, s) for t, s in [("Seremoni Perubahan Nama PT KISI Asset Management", "www.idx.co.id"),
                                                         ("Seremoni Perubahan Nama PT KISI Asset Management", "investor.id"),
                                                         ("Video: Intip Prospek & Ekspansi Bisnis Sekuritas NH Korindo di RI", "www.cnbcindonesia.com"),
                                                         ("Customer Reports Mirae Asset Sekuritas for Alleged Rp71 billion Loss", "en.tempo.co"),
                                                         ("OJK Reveals Alleged Capital Market Crimes Involving Mirae Asset Sekuritas Indonesia", "www.kompas.id"),
                                                         ("Peluncuran Aplikasi NEW HERO - Kiwoom Sekuritas Indonesia", "www.idx.co.id"),
                                                         ("The Rebranding Ceremony of PT KISI Asset Management", "www.idx.co.id")]],
                         ["id", "id", "id", "en", "en", "id", "en"])
        # 같은 기사 판별: 외국어 제목은 앞 28자가 같은 법인 이름이어도 다른 기사로 본다
        self.assertNotEqual(n.norm_title("Mirae Asset Sekuritas Indonesia raih penghargaan"),
                            n.norm_title("Mirae Asset Sekuritas Indonesia luncurkan aplikasi"))
        self.assertEqual(n.norm_title("Chứng khoán KB Việt Nam báo lãi"), n.norm_title("Chứng khoán KB Việt Nam - báo lãi"))

    def test_local_phrases_from_legal_names(self):
        import fetch_news as n
        ph = {p: (amb, ctx) for p, amb, ctx in n.local_phrases("한화투자증권", "인도네시아", ["PT Ciptadana Sekuritas Asia", "PT Ciptadana Asset Management"])}
        self.assertEqual(ph["Ciptadana"], (False, True))              # 한 낱말은 금융 문맥이 있어야
        self.assertEqual(ph["Ciptadana Sekuritas"], (False, False))
        self.assertEqual([p for p, _, _ in n.local_phrases("미래에셋증권", "베트남", ["Mirae Asset Securities (Vietnam) JSC"])],
                         ["Chứng khoán Mirae Asset"])                  # 모회사 영문명은 기존 검색이 맡는다
        self.assertEqual(n.local_phrases("하나증권", "싱가포르", ["Hana Asset Management Asia Pte. Ltd."]),
                         [("Hana Asset Management", True, False)])     # 국내 계열사와 헷갈려 나라 표기가 있어야
        self.assertIn(("BIDV Securities", False, False), n.local_phrases("하나증권", "베트남", ["BIDVSecuritiesJointStockCompany"]))
        self.assertEqual(n.local_queries("한화투자증권", "인도네시아", n.local_phrases("한화투자증권", "인도네시아", ["PT Ciptadana Sekuritas Asia"])),
                         [('"Ciptadana Sekuritas"', "id"), ('"Ciptadana AM"', "id")])  # 한 낱말(Ciptadana)은 검색어로 쓰지 않는다
        self.assertEqual(n.local_queries("하나증권", "싱가포르", n.local_phrases("하나증권", "싱가포르", ["Hana Asset Management Asia Pte. Ltd."])),
                         [])                                                 # 모회사 이름 + 일반 낱말뿐이면 검색어로 쓰지 않는다
        # 현지어 표기(… Sekuritas)는 모회사 이름 + 일반 낱말이어도 그 나라 법인이라 그 나라 판에서 찾는다
        for firm, name, q in [("미래에셋증권", "PT. Mirae Asset Sekuritas Indonesia", "Mirae Asset Sekuritas"),
                              ("신한투자증권", "PT Shinhan Sekuritas Indonesia", "Shinhan Sekuritas"), ("키움증권", "PT Kiwoom sekuritas Indonesia", "Kiwoom sekuritas")]:
            self.assertEqual(n.local_queries(firm, "인도네시아", n.local_phrases(firm, "인도네시아", [name])), [(f'"{q}"', "id")])

    def test_foreign_titles_need_company_news(self):
        import fetch_hub_news as h
        ents = {("NH투자증권", "베트남"): ["NH Securities Vietnam Co., Ltd."], ("NH투자증권", "인도네시아"): ["PT. NH Korindo Sekuritas Indonesia"],
                ("미래에셋증권", "인도"): ["Sharekhan Limited"], ("키움증권", "인도네시아"): ["PT Kiwoom sekuritas Indonesia"],
                ("한화투자증권", "베트남"): ["Pinetree Securities Corporation"], ("한화투자증권", "싱가포르"): ["Pinetree Securities Pte.Ltd"],
                ("하나증권", "싱가포르"): ["Hana Asset Management Asia Pte. Ltd."]}
        ph = h.hub_phrases(ents)
        rel = lambda t, f, c: h.relevant(t, f, c, ph[(f, c)])  # noqa: E731
        self.assertTrue(rel("Chứng khoán NH Việt Nam ra mắt giao dịch Chứng khoán Phái sinh", "NH투자증권", "베트남"))
        self.assertTrue(rel("Chủ Hàn Quốc chốt góp thêm hơn 1,300 tỷ đồng cho NHSV", "NH투자증권", "베트남"))
        self.assertTrue(rel("OJK Bekukan Izin Penjamin Efek NH Korindo Imbas Kasus Bentjok", "NH투자증권", "인도네시아"))
        self.assertTrue(rel("Mirae Asset completes acquisition of Sharekhan, expanding footprint in India", "미래에셋증권", "인도"))
        # 시황·종목 추천·애널리스트 코멘트·종목 페이지
        self.assertFalse(rel("Kiwoom Sekuritas Pertahankan Rekomendasi Buy BBCA, Segini Target Harganya", "키움증권", "인도네시아"))
        self.assertFalse(rel("Silver selloff seems overdone, says Mirae Asset Sharekhan; here's why", "미래에셋증권", "인도"))
        self.assertFalse(rel("WOORICBV:Công ty TNHH Chứng khoán NH Việt Nam (OTC)", "NH투자증권", "베트남"))
        self.assertFalse(rel("Shinhan Pinetree forest walk opens", "한화투자증권", "베트남"))          # 금융 문맥 없음
        self.assertFalse(rel("Pinetree Coffee plans IPO in Vietnam", "한화투자증권", "베트남"))        # IPO·stock은 금융 문맥으로 치지 않는다
        self.assertTrue(rel("Hanwha's Pinetree expands in Vietnam", "한화투자증권", "베트남"))         # 모회사 이름이 같이 있으면 된다
        # 시황 방송·애널리스트 의견은 빼고, 장애(technical outage) 같은 회사 소식은 남긴다
        self.assertFalse(rel("LIVE: Mirae Asset Sharekhan launches new app", "미래에셋증권", "인도"))
        self.assertFalse(rel("Sharekhan upgrades Infosys, raises target", "미래에셋증권", "인도"))
        self.assertTrue(rel("Sharekhan NBFC faces technical outage", "미래에셋증권", "인도"))
        # 판촉(이자·수수료 면제, 세미나, 대학 행사)은 빼고 실적(báo lãi)은 남긴다. 우선주(cổ phiếu ưu đãi)는 자본 소식
        for t in ["Giữa làn sóng tăng lãi suất huy động, Chứng khoán Pinetree tung gói vay margin chỉ tương đương lãi tiết kiệm ngân hàng",
                  "Chứng khoán KB Việt Nam ra mắt chương trình miễn lãi suất margin cho khách hàng", "NHSV ra mắt Hội thảo: Cơ hội gia tăng tài sản",
                  "Chứng khoán KIS triển khai Happy Monday, hoàn 100% phí giao dịch đầu tháng", "KIS Việt Nam triển khai “Vòng quay Chứng sỹ” mùa 5",
                  "Internal Coaching Clinic KSPM Universitas Pancasila Bakal Gandeng KB Valbury Sekuritas"]:
            self.assertFalse(h.foreign_ok(t), t)
        self.assertTrue(h.foreign_ok("Dư nợ cho vay tăng lên gần 8.900 tỷ đồng, Chứng khoán KB Việt Nam báo lãi tăng hơn 15%"))
        self.assertTrue(h.foreign_ok("Chứng khoán Mirae Asset sắp chuyển 113.5 triệu cổ phiếu ưu đãi thành phổ thông"))
        # 국내 영문 매체(Korea Times 등) 제목은 사건 낱말이 없어도 된다(해외 매체는 있어야)
        t = "NH Investment & Securities' Hong Kong unit eyes accelerating growth"
        self.assertTrue(h.relevant(t, "NH투자증권", "홍콩", foreign=False))
        self.assertFalse(h.relevant(t, "NH투자증권", "홍콩", foreign=True))
        # 'US$'는 미국 표기가 아니다
        t = "Mirae Asset Securities Vietnam raises US$50 million in bonds"
        self.assertEqual([c for c in ("미국", "베트남") if h.relevant(t, "미래에셋증권", c)], ["베트남"])
        # 두 나라 법인이 같은 이름(Pinetree)이면 나라 표기나 그 나라 말이어야 한다
        t = "Chiến lược khác biệt của Chứng khoán Pinetree"
        self.assertEqual([c for c in ("베트남", "싱가포르") if rel(t, "한화투자증권", c)], ["베트남"])
        t = "Pinetree Securities launches Singapore wealth platform"
        self.assertEqual([c for c in ("베트남", "싱가포르") if rel(t, "한화투자증권", c)], ["싱가포르"])
        self.assertTrue(rel("Hana Asset Management launches Singapore private credit fund", "하나증권", "싱가포르"))
        self.assertFalse(rel("Hana Asset Management launches new ETF", "하나증권", "싱가포르"))
        self.assertIn(('"Chứng khoán Pinetree"', "vi"), h.queries("한화투자증권", "베트남", ph[("한화투자증권", "베트남")]))

    def test_hub_falls_back_to_latest_within_five_years(self):
        import tempfile
        import fetch_hub_news as h
        ph = {("한화투자증권", "베트남"): [("Chứng khoán Pinetree", False, False)], ("KB증권", "베트남"): [("KBSV", False, False)]}
        old = [("Chiến lược khác biệt của Chứng khoán Pinetree", "VnExpress", "https://vnexpress.net", "2024-12-05"),
               ("Chứng khoán Pinetree hợp tác với FPT", "CafeF", "https://cafef.vn", "2023-03-18"),
               ("Chứng khoán Pinetree ra mắt ứng dụng mới", "CafeF", "https://cafef.vn", "2022-04-14"),
               ("Chứng khoán Pinetree thành lập", "CafeF", "https://cafef.vn", "2019-01-10")]          # 5년 밖
        fresh = [("KBSV báo lãi tăng 15%", "Thời báo Tài chính Việt Nam", "https://thoibaotaichinhvietnam.vn", "2026-07-21")]

        def get(url, timeout=25):
            five = "when%3A1825d" in url
            if "Pinetree" in url:
                return _rss(*(old if five else []))
            return _rss(*(fresh if "KBSV" in url else []))
        with tempfile.TemporaryDirectory() as d, mock.patch.object(h, "OUT", Path(d) / "hub_news.json"), \
                mock.patch.object(h, "hub_phrases", return_value=ph), mock.patch.object(h.net, "get", side_effect=get), \
                mock.patch.object(h.time, "sleep"), mock.patch.object(h, "datetime", wraps=h.datetime) as dt:
            dt.now.return_value = h.datetime(2026, 10, 27, 7, 0, tzinfo=h.KST)
            h.main()
            got = json.loads((Path(d) / "hub_news.json").read_text(encoding="utf-8"))["hubs"]
        pine = got["한화투자증권|베트남"]
        self.assertEqual([x["date"] for x in pine], ["2024-12-05", "2023-03-18"])    # 5년 안 최근 2건만
        self.assertTrue(all(x["old"] and x["foreign"] and x["lang"] == "vi" for x in pine))
        self.assertEqual([(x["date"], x.get("old")) for x in got["KB증권|베트남"]], [("2026-07-21", None)])

    def test_main_feed_takes_foreign_hub_items(self):
        import tempfile
        from datetime import datetime
        import fetch_news as n
        import fetch_hub_news as h
        cnbc = {"src": "CNBC Indonesia", "site": "www.cnbcindonesia.com"}
        hub = {"hubs": {"NH투자증권|인도네시아": [
            {"date": "2026-10-20", "title": "NH Korindo Sekuritas Raih Penghargaan", "url": "a", "foreign": True, **cnbc},
            {"date": "2026-10-19", "title": "NH투자증권 인니법인 증자", "src": "연합뉴스", "url": "b"},
            {"date": "2026-10-18", "title": "NH Korindo Sekuritas Pertahankan Rating Buy BBCA", "url": "e", "foreign": True, **cnbc},  # 지금 규칙으로는 종목 의견
            {"date": "2026-01-02", "title": "NH Korindo rights issue", "src": "Kontan", "site": "kontan.co.id", "url": "c", "foreign": True},
            {"date": "2023-01-02", "title": "NH Korindo old", "src": "Kontan", "url": "d", "foreign": True, "old": True}]}}
        # 이 피드에 이미 실린 거점 기사: 거점 칸(최근 몇 건)에서 밀려나도 기간 안이면 둔다
        prev = [{"date": "2026-09-01", "title": "Gandeng Sinarmas, NH Korindo Sekuritas Pasarkan Reksa Dana", "url": "p", "hub": "NH투자증권|인도네시아",
                 "firms": ["NH투자증권"], **cnbc},
                {"date": "2026-05-01", "title": "NH Korindo Sekuritas Raih Award", "url": "q", "hub": "NH투자증권|인도네시아", **cnbc},
                {"date": "2026-09-02", "title": "NH Korindo Sekuritas buka cabang", "url": "r", **cnbc}]
        ph = {("NH투자증권", "인도네시아"): [("NH Korindo", False, False), ("NH Korindo Sekuritas", False, False)]}
        with tempfile.TemporaryDirectory() as d, mock.patch.object(n, "DATA", Path(d)), mock.patch.object(h, "hub_phrases", return_value=ph):
            (Path(d) / "hub_news.json").write_text(json.dumps(hub), encoding="utf-8")
            got = n.hub_foreign(datetime(2026, 7, 29, tzinfo=n.KST), prev)
        self.assertEqual([(x["url"], x["firms"], x["hub"], x.get("lang")) for x in got],
                         [("a", ["NH투자증권"], "NH투자증권|인도네시아", "id"), ("p", ["NH투자증권"], "NH투자증권|인도네시아", "id")])


class BrokerRankTest(unittest.TestCase):
    def test_periods_wait_for_filing_deadline(self):
        import broker_rank as b
        self.assertEqual([p[:2] for p in b.periods(date(2026, 10, 26))], [("2026", "11012"), ("2026", "11013")])
        self.assertEqual(b.periods(date(2026, 11, 16))[0][:2], ("2026", "11014"))  # 3분기 기한(11/14) 뒤 첫 월요일
        self.assertEqual(b.periods(date(2027, 3, 29))[0][:2], ("2026", "11014"))  # 사업보고서 기한 전
        self.assertEqual(b.periods(date(2027, 4, 5))[0][:2], ("2026", "11011"))

    def test_collect_keeps_one_balance_date_and_display_names(self):
        import broker_rank as b
        row = lambda acc, div, amt, dt="2026.06.30 현재": {"account_nm": acc, "fs_div": div, "thstrm_amount": amt, "thstrm_dt": dt}
        data = {
            "A": [row("자본총계", "CFS", "2,263,405,000,000"), row("자본총계", "OFS", "2,267,400,000,000"), row("자본금", "OFS", "1,100,000,000,000")],
            "B": [row("자본총계", "OFS", "8,220,000,000,000")],
            "C": [row("자본총계", "OFS", "1,700,000,000,000", "2026.09.30 현재")],  # 3월 결산사의 '반기'
            "D": [],
        }
        cands = {"A": ("한화투자증권", "003530"), "B": ("케이비증권", ""), "C": ("신영증권", "001720"), "D": ("감사보고서만증권", "")}
        with mock.patch.object(b, "brokers", return_value=cands), mock.patch.object(b, "MIN_ROWS", 2), \
                mock.patch.object(b, "api", side_effect=lambda path, key, corp_code, **k: data[corp_code]):
            res = b.collect("dummy", today=date(2026, 10, 26))
        self.assertEqual((res["period"], res["as_of"]), ("2026 반기보고서", "2026-06-30"))
        self.assertEqual([r["name"] for r in b.ranked(res["rows"], lambda r: r.get("equity_ofs"))], ["KB증권", "한화투자증권"])
        a = next(r for r in res["rows"] if r["corp_code"] == "A")
        self.assertEqual((a["equity_cfs"], a["equity_ofs"], a["capital_ofs"]), (2263405, 2267400, 1100000))
        self.assertEqual(res["other_fiscal"], ["신영증권(2026-09-30)"])
        self.assertNotIn("as_of", a)

    def test_no_key_is_a_noop(self):
        import broker_rank as b
        with mock.patch.dict("os.environ", {"DART_API_KEY": ""}), mock.patch.object(b, "OUT", Path(os.devnull)):
            b.main()
