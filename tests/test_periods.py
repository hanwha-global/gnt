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

    def test_only_recent_or_missing_young_periods_are_refetched(self):
        import fetch_fin_hist as f
        pers = f.periods(date(2026, 10, 27))
        today = date(2026, 10, 27)
        self.assertTrue(f.needs(pers[0], {"equity": 1}, 0, today))
        self.assertFalse(f.needs(pers[5], {"equity": 1}, 5, today))
        self.assertTrue(f.needs(pers[2], None, 2, today))       # 1Q26 미제출: 다시 확인
        self.assertFalse(f.needs(pers[-1], None, len(pers) - 1, today))  # 오래된 빈 기간은 그대로

    def test_build_counts_filers_per_period(self):
        import fetch_fin_hist as f
        pers = f.periods(date(2026, 10, 27))[:2]
        out = f.build(pers, {"A": {"2026-11012": {"equity": 1}}, "B": {}}, [])
        self.assertEqual([(p["label"], p["bs"], p["months"], p["n"]) for p in out["periods"]], [("1H26", "26.6말", 6, 1)])
        self.assertEqual(list(out["firms"]), ["A"])


class BrokerHistTest(unittest.TestCase):
    def test_history_keeps_latest_and_fetches_missing_periods_once(self):
        import broker_rank as b
        latest = {"period": "2026 반기보고서", "as_of": "2026-06-30", "bsns_year": "2026", "reprt_code": "11012",
                  "rows": [{"name": "가", "dart_name": "가", "corp_code": "A", "listed": True, "equity_ofs": 10}]}
        with tempfile.TemporaryDirectory() as d:
            hist = Path(d) / "h.json"
            calls = []

            def fake(key, period, cands=None, min_rows=None):
                calls.append(period)
                return {**latest, "period": f"{period[0]} {b.LABEL[period[1]]}", "as_of": f"{period[0]}-x", "bsns_year": period[0], "reprt_code": period[1]}
            with mock.patch.object(b, "HIST", hist), mock.patch.object(b, "collect", side_effect=fake):
                b.history("k", latest, today=date(2026, 10, 27))
                n = len(calls)
                b.history("k", latest, today=date(2026, 10, 27))
            saved = json.loads(hist.read_text(encoding="utf-8"))["periods"]
        self.assertEqual(n, 13)                  # 2023~2026 기한 지난 14개 기간 중 최신 하나는 이미 있음
        self.assertEqual(len(calls), n)          # 두 번째 실행은 받지 않음
        self.assertEqual(len(saved), 14)
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
