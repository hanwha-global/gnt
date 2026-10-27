"""기간 선택(드롭다운)용 이력 수집을 네트워크 없이 검증한다. 숫자는 모두 가상 값."""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "hanwha" / "scripts"))


class FinHistTest(unittest.TestCase):
    def test_periods_are_past_period_ends_newest_first(self):
        import fetch_fin_hist as f
        keys = [p["key"] for p in f.periods(date(2026, 10, 27))]
        self.assertEqual(keys[:4], ["2026-11014", "2026-11012", "2026-11013", "2025-11011"])
        self.assertEqual(keys[-1], "2022-11013")

    def test_financials_prefer_consolidated_and_cumulative_pl(self):
        import fetch_fin_hist as f
        row = lambda div, acc, amt, add=None: {"fs_div": div, "account_nm": acc, "thstrm_amount": amt, "thstrm_add_amount": add, "rcept_no": "R1"}  # noqa: E731
        got = f.financials([row("CFS", "자산총계", "9,000,000,000"), row("CFS", "자본총계", "1,000,000,000"),
                            row("CFS", "당기순이익(손실)", "10,000,000", "40,000,000"), row("OFS", "자본총계", "5")])
        self.assertEqual(got, {"fs_div": "연결", "assets": 9000, "equity": 1000, "net_income": 40, "rcept_no": "R1"})
        self.assertIsNone(f.financials([]))

    def test_only_recent_unasked_or_young_empty_periods_are_refetched(self):
        import fetch_fin_hist as f
        pers = f.periods(date(2026, 10, 27))
        today = date(2026, 10, 27)
        self.assertTrue(f.needs(pers[0], {"equity": 1}, 0, today))
        self.assertFalse(f.needs(pers[5], {"equity": 1}, 5, today))
        self.assertTrue(f.needs(pers[-1], None, len(pers) - 1, today))               # 한 번도 묻지 않은 기간: 받는다
        self.assertTrue(f.needs(pers[2], None, 2, today, tried=True))                # 1Q26 비어 있었음: 400일 안이라 다시 확인
        self.assertFalse(f.needs(pers[-1], None, len(pers) - 1, today, tried=True))  # 오래된 빈 기간은 그대로

    def test_first_run_backfills_every_past_period_then_only_recent(self):
        import fetch_fin_hist as f
        today = date(2026, 10, 27)
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "dart_latest.json").write_text(json.dumps({"firms": {"한화투자증권": {"corp_code": "C1"}}}), encoding="utf-8")
            calls = []

            def fake(path, key, corp_code, bsns_year, reprt_code):
                calls.append((bsns_year, reprt_code))
                if (bsns_year, reprt_code) in (("2026", "11014"), ("2022", "11013")):
                    return []  # 미제출·자료 없음
                return [{"fs_div": "CFS", "account_nm": "자본총계", "thstrm_amount": "1000000", "rcept_no": "R"}]
            with mock.patch.object(f, "DATA", Path(d)), mock.patch.object(f, "FIRMS", ["한화투자증권"]), mock.patch.object(f, "api", side_effect=fake):
                pers, firms, empty, errors, n1 = f.collect("k", {}, today)
                out = f.build(pers, firms, errors, empty)
                _, _, _, _, n2 = f.collect("k", out, today)
        self.assertEqual(n1, len(pers))                 # 19개 기간 모두 한 번씩
        self.assertEqual(len(out["periods"]), len(pers) - 2)
        self.assertEqual(out["empty"], {"한화투자증권": ["2022-11013", "2026-11014"]})
        self.assertEqual(n2, 2)                         # 두 번째 실행은 최근 2개(아직 빈 3Q26 포함)만

    def test_build_counts_filers_per_period(self):
        import fetch_fin_hist as f
        pers = f.periods(date(2026, 10, 27))[:2]
        out = f.build(pers, {"A": {"2026-11012": {"equity": 1}}, "B": {}}, [])
        self.assertEqual([(p["label"], p["bs"], p["months"], p["n"]) for p in out["periods"]], [("1H26", "26.6말", 6, 1)])
        self.assertEqual(list(out["firms"]), ["A"])


class BrokerHistTest(unittest.TestCase):
    def test_history_keeps_latest_and_fetches_missing_periods_once(self):
        import broker_rank as b
        latest = {"period": "2026 반기보고서", "as_of": "2026-06-30", "bsns_year": "2026", "reprt_code": "11012", "errors": [],
                  "rows": [{"name": "한화투자증권", "dart_name": "한화투자증권", "corp_code": "A", "listed": True, "equity_ofs": 10}]}
        with tempfile.TemporaryDirectory() as d:
            hist = Path(d) / "h.json"
            calls = []

            def fake(key, period, cands=None, min_rows=None):
                calls.append(period)
                if period == ("2024", "11013"):  # 호출 오류가 난 기간은 저장하지 않고 다음 실행에서 다시 받는다
                    return {**latest, "bsns_year": "2024", "reprt_code": "11013", "errors": ["가: 020"]}
                return {**latest, "period": f"{period[0]} {b.LABEL[period[1]]}", "as_of": f"{period[0]}-x", "bsns_year": period[0], "reprt_code": period[1]}
            with mock.patch.object(b, "HIST", hist), mock.patch.object(b, "collect", side_effect=fake):
                b.history("k", latest, today=date(2026, 10, 27))
                n = len(calls)
                b.history("k", latest, today=date(2026, 10, 27))
            saved = json.loads(hist.read_text(encoding="utf-8"))["periods"]
        self.assertEqual(n, 13)                  # 2023~2026 기한 지난 14개 기간 중 최신 하나는 이미 있음
        self.assertEqual(calls[n:], [("2024", "11013")])  # 두 번째 실행은 오류 났던 기간만 다시 받음
        self.assertEqual(len(saved), 13)
        self.assertIn(("2026", "11012"), {(p["bsns_year"], p["reprt_code"]) for p in saved})


class SubTrendRoeTest(unittest.TestCase):
    def test_half_year_roe_is_annualized(self):
        import fetch_sub_trend as t
        rows = {"Alpha Securities Ltd": {"equity": 1000.0, "ni": 30.0}, "Beta Fund": {"equity": 500.0, "ni": 99.0}}
        seeds = [{"name": "Alpha Securities Ltd", "country": "베트남"}]
        self.assertEqual(t.period_roe(rows, seeds, "FY2025")["roe"], 3.0)
        h = t.period_roe(rows, seeds, "1H2026")
        self.assertEqual((h["n"], h["months"], h["roe"]), (1, 6, 6.0))
        self.assertIsNone(t.period_roe({}, seeds, "FY2025"))

    def test_old_names_count_like_the_trend_table(self):
        import fetch_sub_trend as t
        rows = {"Shinhan Investment America Inc.": {"equity": 100.0, "ni": 5.0}, "Shinhan Securities Vietnam Co., Ltd.": {"equity": 100.0, "ni": 1.0}}
        seeds = [{"name": "Shinhan Securities America Inc.", "country": "미국"}, {"name": "Shinhan Securities Vietnam Co., Ltd.", "country": "베트남"}]
        r = t.period_roe(rows, seeds, "FY2021")
        self.assertEqual((r["n"], r["roe"]), (2, 3.0))


class HanwhaHistoryTest(unittest.TestCase):
    def test_history_reuses_saved_reports_and_skips_tableless(self):
        import fetch_dart_subs as h
        rep = lambda no, y, p: {"rcept_no": no, "rcept_dt": no[:8], "report_nm": f"보고서 ({y}.{dict(FY='12', **{'1H': '06', '1Q': '03'})[p]})", "year": y, "period": p}  # noqa: E731
        reps = [rep("20260814000001", "2026", "1H"), rep("20260515000001", "2026", "1Q"), rep("20260310000001", "2025", "FY"), rep("20220310000001", "2021", "FY")]
        sub = {"VN": {"unit": "백만원", "assets": 10.0, "liab": 4.0, "rev": 3.0, "ni": 1.0, "name": "Pinetree Securities Corporation"}}
        prev = {"history": [h.period_entry(reps[2], sub)]}
        fetched = []

        def fake_doc(key, no):
            fetched.append(no)
            return ["<doc>"]
        with mock.patch.object(h, "fetch_doc", side_effect=fake_doc), \
                mock.patch.object(h, "parse_summary", side_effect=lambda t: {}):
            out, skip = h.build_history("k", reps, prev, {}, [(reps[0], sub)], date(2026, 10, 27))
        self.assertEqual([p["label"] for p in out], ["FY2025", "1H26"])
        self.assertEqual(fetched, ["20260515000001"])   # 저장된 FY2025·이번에 받은 1H26은 다시 안 받고, 2021년은 범위 밖
        self.assertEqual(skip, ["20260515000001"])


if __name__ == "__main__":
    unittest.main()
