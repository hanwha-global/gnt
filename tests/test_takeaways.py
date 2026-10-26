"""진출국 전략 Takeaways(build_takeaways.py)를 가상 숫자로 검증한다(네트워크·실데이터 없음)."""
import copy
import json
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import build_takeaways as bt  # noqa: E402

TODAY = date(2026, 10, 26)


def ds(n):
    return (TODAY - timedelta(days=n)).isoformat()


def monthly(peak, last):
    ms = [f"2025-{m:02d}" for m in range(10, 13)] + [f"2026-{m:02d}" for m in range(1, 11)]
    vals = [peak * 0.9] * len(ms)
    vals[3] = peak
    vals[-1] = last
    return [[m, v] for m, v in zip(ms, vals)]


def fixture():
    """가상 데이터: 베트남은 흑자·소형, 인니는 강등 우려·두 법인 적자, 싱가포르는 증자 후 적자 확대."""
    sub = lambda a, l, r, n: {"unit": "백만원", "assets": a, "liab": l, "rev": r, "ni": n}
    return {
        "hanwha/data/entities.json": {"entities": [
            {"key": "VN", "label": "베트남 법인(PTSV)", "focus": "리테일 브로커리지, 신용공여(마진론), IB",
             "notes": [["시장", "FTSE Russell 신흥시장 편입이 2026-09-21 발효됐습니다."]]},
            {"key": "CSA", "label": "인도네시아 증권(CSA)", "focus": "브로커리지, 신용공여, IB·인수", "notes": []},
            {"key": "SG", "label": "싱가포르 법인(PTSS)", "focus": "투자자문·IB", "notes": []},
            {"key": "CAM", "label": "인도네시아 운용(CAM)", "focus": "자산운용", "notes": []}]},
        "hanwha/data/dart_subs.json": {
            "periods": [
                {"label": "FY2025", "period": "FY", "year": "2025", "months": 12,
                 "report": {"name": "사업보고서 (2025.12)", "rcept_no": "F1", "rcept_dt": "20260310"},
                 "subs": {"VN": sub(1000, 600, 200, 20), "CSA": sub(500, 200, 100, 10), "CAM": sub(50, 5, None, None), "SG": sub(60, 10, 8, -10)}},
                {"label": "1H26", "period": "1H", "year": "2026", "months": 6,
                 "report": {"name": "반기보고서 (2026.06)", "rcept_no": "H1", "rcept_dt": "20260813"},
                 "subs": {"VN": sub(1100, 680, 110, 5), "CSA": sub(480, 190, 40, -5), "CAM": sub(45, 5, 10, -3), "SG": sub(160, 5, 3, -9)}}],
            "invest": {"report": {"name": "반기보고서 (2026.06)", "rcept_no": "H1", "rcept_dt": "20260813"},
                       "rows": {"SG": {"chg_amount": 100}, "CAM": {"first_date": "2025.12.19"}, "VN": {}, "CSA": {}}}},
        "hanwha/data/markets.json": {
            "indices": [
                {"name": "VN-Index", "date": ds(3), "close": 1000, "monthly": monthly(1060, 1000),
                 "chg": {"1D": 0.5, "1W": 4.0, "1M": -1.0, "3M": 4.4, "6M": -5.0, "YTD": -1.0}},
                {"name": "IDX(자카르타)", "date": ds(3), "close": 600, "monthly": monthly(1000, 600),
                 "chg": {"1D": 0.5, "1W": 1.0, "1M": -15.0, "3M": -14.0, "6M": -26.0, "YTD": -37.0}},
                {"name": "STI(싱가포르)", "date": ds(3), "close": 500, "monthly": monthly(520, 500),
                 "chg": {"1D": 0.1, "1W": 0.1, "1M": -5.0, "3M": -3.0, "6M": 9.0, "YTD": 16.0}}],
            "fx": {"rows": [{"ccy": "USD", "chg_1w": -1.7}, {"ccy": "VND", "chg_1w": -1.7}, {"ccy": "IDR", "chg_1w": -2.4}, {"ccy": "SGD", "chg_1w": -1.3}]},
            "policy": {"table": [{"key": "ID", "name": "인니 BI", "month": "2026-09", "now": 5.75, "d1y_bp": 100},
                                 {"key": "VN", "name": "베트남 SBV", "month": "2026-10", "now": 4.5, "d1y_bp": 0}]}},
        "hanwha/data/macro.json": {"fx": {
            "USD": {"name": "원/미국달러", "last": ["20261026", 1300], "ytd_pct": -7.7},
            "VND": {"name": "원/베트남동(100동)", "last": ["20261026", 5.1], "ytd_pct": -6.2},
            "IDR": {"name": "원/인도네시아루피아(100루피아)", "last": ["20261026", 7.3], "ytd_pct": -14.8},
            "SGD": {"name": "원/싱가포르달러", "last": ["20261026", 1030], "ytd_pct": -7.2}},
            "kr_base_rate": [["202609", 3.0]]},
        "hanwha/data/rate_calendar.json": {"events": [{"date": "2026-11-18", "bank": "ID", "name": "인니 BI"}]},
        "hanwha/data/regulatory.json": {"todo": [{"id": "periodic-2026-3Q", "due": "2026-11-16", "status": "upcoming", "item": "2026 3분기보고서 해외자회사 반영"}]},
        "site/data/global/macro_news.json": {"countries": {
            "ID": {"items": [
                {"date": ds(0), "title": "Indonesia strengthens measures against stock manipulation after market rout", "src": "Reuters", "url": "u-id-1", "priority": True},
                {"date": ds(3), "title": "Why is Indonesia facing a rare MSCI downgrade and what's at stake?", "src": "CNA", "url": "u-id-2", "priority": True}]},
            "VN": {"items": [
                {"date": ds(7), "title": "Vietnam Plans Index Options for Next Year After FTSE Upgrade", "src": "Bloomberg", "url": "u-vn-1", "priority": True},
                {"date": ds(6), "title": "Market upgrade is just the beginning: Vietnamese companies face tougher test", "src": "VIR", "url": "u-vn-2", "priority": True}]},
            "SG": {"items": [{"date": ds(3), "title": "Singapore shares edge higher", "src": "Business Times", "url": "u-sg-1", "priority": False}]}}},
        "site/data/global/markets.json": {"markets": [
            {"id": "vn", "flag": "VN", "tables": [{"title": "HOSE 브로커리지 시장점유율 (2Q26)", "basis": "2026-07 HOSE 발표", "rows": [
                {"name": "A", "value": 12.0}, {"name": "B", "value": 9.0, "note": "사상 최고"}, {"name": "C", "value": 3.5, "note": "설립 이후 최고"},
                {"name": "KIS", "value": 3.0, "korean": "한국투자증권"}, {"name": "Mirae", "value": 2.9, "korean": "미래에셋증권"}]}]},
            {"id": "id", "flag": "ID", "tables": [{"basis": "2026.1~6, IDX 집계", "rows": [{"name": "Stockbit Sekuritas Digital (XL)", "value": 500.0}]}]},
            {"id": "sg", "flag": "SG"}]},
        "site/data/global/listed.json": {"markets": {"vn": {"rows": [
            {"equity": 100, "ni": 10}, {"equity": 100, "ni": 12}, {"equity": 100, "ni": 8}, {"equity": 100, "ni": 11}]}}},
        "site/data/domestic/hub_news.json": {"hubs": {
            "미래에셋증권|베트남": [{"date": ds(20), "title": "미래에셋증권 베트남법인, '자본금 확대' 위해 증자", "src": "가상일보", "url": "u-hub-1"}],
            "미래에셋증권|인도": [{"date": ds(2), "title": "미래에셋 인도 법인 증자", "src": "가상일보", "url": "u-hub-in"}],
            "한화투자증권|싱가포르": [{"date": ds(100), "title": "가상코인, 한화투자증권 싱가포르 법인과 RWA 협력", "src": "가상일보", "url": "u-hub-sg"}]}},
        "site/data/domestic/news.json": {"items": []},
        "site/data/domestic/dart_latest.json": {"firms": {"한화투자증권": {"financials": {"equity": 2_000_000}, "financials_report": {"label": "2026 반기보고서"}}}},
        "site/data/domestic/sub_fin.json": {"firms": {
            "가증권": {"subs": {"Ga Securities Vietnam": {"country": "베트남", "equity": 1000, "rev": 100, "ni": 10}}},
            "나증권": {"subs": {"Na Securities Vietnam": {"country": "베트남", "equity": 1500, "rev": 100, "ni": 20},
                             "Na Asset Management Vietnam": {"country": "베트남", "equity": 9000, "rev": 50, "ni": 5}}},
            "다증권": {"subs": {"Da Securities Vietnam JSC": {"country": "베트남", "equity": 2000, "rev": 100, "ni": 15}}}}},
        "digital/data/regulation.json": {"markets": [{"code": "SG", "status": {"sto": {"lv": "ok", "short": "SFA"}}}]},
    }


def write(root, files):
    for rel, obj in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def at(day, hour=7):
    return datetime(day.year, day.month, day.day, hour, 0, tzinfo=bt.KST)


class TakeawaysTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.files = fixture()
        write(self.root, self.files)

    def tearDown(self):
        self.tmp.cleanup()

    def run_at(self, day, prev):
        return bt.run(root=self.root, now=at(day), prev=prev)

    def rules(self, res, c):
        return {b["rule"]: b for b in res["countries"][c]["bullets"]}

    def test_first_run_picks_levers_per_country(self):
        res = self.run_at(TODAY, {})
        self.assertEqual(res["errors"], [])
        vn, id_, sg = (self.rules(res, c) for c in ("VN", "ID", "SG"))
        # 베트남: 소형·저ROE → 지분 인수, FTSE 편입·옵션 → 파생 준비, 비용 증가 > 매출 증가 → 비용 상한, 마케팅은 타깃형
        self.assertEqual(vn["R01"]["variant"], "acquire")
        self.assertIn("자본금 확대", " ".join(vn["R01"]["evidence"]))  # 경쟁사 증자 기사가 근거로 합쳐짐
        self.assertEqual(vn["R07"]["variant"], "deriv")
        self.assertIn("R12", vn)
        self.assertEqual(vn["MKT"]["variant"], "targeted")
        # 인니: 강등·급락 → 리스크 한 줄, 두 법인 적자 → 통합, 인수는 게이트, 마케팅은 재배분
        self.assertEqual(id_["R08"]["variant"], "NEG")
        self.assertIn("MSCI", id_["R08"]["text"])
        self.assertIn("R13", id_)
        self.assertEqual(id_["R04"]["variant"], "gated")
        self.assertEqual(id_["MKT"]["variant"], "reallocate")
        self.assertNotIn("R11", id_)  # R13에 합쳐짐
        # 싱가포르: 적자 확대 → 조직 재편, 증자 후 매출 부진 → 단계 집행, RWA 보도 → 저비용 사업화, 마케팅 지출 제안 없음
        self.assertEqual(sg["R11"]["variant"], "widen")
        self.assertIn("R05", sg)
        self.assertIn("R18", sg)
        self.assertNotIn("MKT", sg)
        for c in ("VN", "ID", "SG"):
            bl = res["countries"][c]["bullets"]
            cats = [b["category"] for b in bl if b["rule"] != "F3"]
            self.assertTrue(3 <= len(bl) <= 4, (c, bl))
            self.assertGreaterEqual(len(set(cats)), 2)
            self.assertLessEqual(cats.count(bt.RISK), 1)
            for b in bl:
                self.assertTrue(b["evidence"], b)
                self.assertNotRegex(b["text"] + " ".join(b["evidence"]), r"추정|요확인|N/A|None|nan")
                self.assertNotIn("—", b["text"])
                self.assertTrue(any(lab in b["text"] for lab in res["countries"][c]["entities"]) or bt.KOR[c] in b["text"], b["text"])
            self.assertEqual(res["countries"][c]["reason"], ["첫 생성"])

    def test_never_cost_cuts_and_aggressive_spending_for_one_entity(self):
        res = self.run_at(TODAY, {})
        for c in ("VN", "ID", "SG"):
            texts = " ".join(b["text"] for b in res["countries"][c]["bullets"])
            if "공격적" in texts:
                self.assertNotRegex(texts, r"축소|효율화|비용 상한")

    def test_quiet_day_keeps_previous_text(self):
        first = self.run_at(TODAY, {})
        second = self.run_at(TODAY + timedelta(days=1), first)
        for c in ("VN", "ID", "SG"):
            a, b = first["countries"][c], second["countries"][c]
            self.assertEqual(b["last_check"], "큰 변화 없음", (c, b.get("reason")))
            self.assertEqual(a["bullets"], b["bullets"])
            self.assertEqual(b["changed_at"], TODAY.isoformat())
        self.assertNotEqual(first["checked_at"], second["checked_at"])

    def test_big_news_refreshes_only_that_country(self):
        first = self.run_at(TODAY, {})
        day = TODAY + timedelta(days=1)
        self.files["site/data/global/macro_news.json"]["countries"]["ID"]["items"].insert(
            0, {"date": day.isoformat(), "title": "Indonesia stocks plunge as MSCI downgrade looms", "src": "Reuters", "url": "u-id-new", "priority": True})
        write(self.root, self.files)
        res = self.run_at(day, first)
        self.assertEqual(res["countries"]["ID"]["last_check"], "갱신")
        self.assertTrue(any(r.startswith("새 뉴스") for r in res["countries"]["ID"]["reason"]))
        self.assertEqual(res["countries"]["VN"]["last_check"], "큰 변화 없음")
        self.assertEqual(res["countries"]["SG"]["last_check"], "큰 변화 없음")

    def test_unrelated_country_news_is_not_a_trigger(self):
        # '미래에셋증권|인도'는 인도네시아가 아니다
        first = self.run_at(TODAY, {})
        self.files["site/data/domestic/hub_news.json"]["hubs"]["미래에셋증권|인도"].insert(
            0, {"date": TODAY.isoformat(), "title": "미래에셋 인도 법인 추가 증자", "src": "가상일보", "url": "u-hub-in-2"})
        write(self.root, self.files)
        res = self.run_at(TODAY + timedelta(days=1), first)
        self.assertEqual(res["countries"]["ID"]["last_check"], "큰 변화 없음")

    def test_new_dart_report_refreshes_all(self):
        first = self.run_at(TODAY, {})
        self.files["hanwha/data/dart_subs.json"]["periods"][-1]["report"]["rcept_no"] = "Q3"
        write(self.root, self.files)
        res = self.run_at(TODAY + timedelta(days=1), first)
        for c in ("VN", "ID", "SG"):
            self.assertEqual(res["countries"][c]["last_check"], "갱신")
            self.assertTrue(any(r.startswith("DART") for r in res["countries"][c]["reason"]))

    def test_policy_rate_change_and_staleness(self):
        first = self.run_at(TODAY, {})
        self.files["hanwha/data/markets.json"]["policy"]["table"][1]["now"] = 4.25
        write(self.root, self.files)
        res = self.run_at(TODAY + timedelta(days=1), first)
        self.assertIn("정책금리 4.50% → 4.25%", res["countries"]["VN"]["reason"])
        self.files = fixture()
        write(self.root, self.files)
        res = self.run_at(TODAY + timedelta(days=15), first)
        self.assertTrue(any("정기 갱신" in r for r in res["countries"]["SG"]["reason"]))

    def test_rule_must_miss_twice_before_it_drops(self):
        first = self.run_at(TODAY, {})
        del self.files["site/data/domestic/hub_news.json"]["hubs"]["한화투자증권|싱가포르"]
        write(self.root, self.files)
        once = self.run_at(TODAY + timedelta(days=1), first)
        self.assertEqual(once["countries"]["SG"]["last_check"], "큰 변화 없음")
        self.assertIn("R18", self.rules(once, "SG"))
        twice = self.run_at(TODAY + timedelta(days=2), once)
        self.assertEqual(twice["countries"]["SG"]["last_check"], "갱신")
        self.assertNotIn("R18", self.rules(twice, "SG"))
        self.assertTrue(any("디지털자산 협력" in r for r in twice["countries"]["SG"]["reason"]))

    def test_market_shock_triggers_once(self):
        first = self.run_at(TODAY, {})
        self.files["hanwha/data/markets.json"]["indices"][2]["chg"]["1D"] = -5.0
        write(self.root, self.files)
        hit = self.run_at(TODAY + timedelta(days=1), first)
        self.assertIn("지수·환율 급변", hit["countries"]["SG"]["reason"])
        again = self.run_at(TODAY + timedelta(days=2), hit)
        self.assertEqual(again["countries"]["SG"]["last_check"], "큰 변화 없음")

    def test_missing_inputs_degrade_without_errors(self):
        for rel in ("site/data/global/macro_news.json", "site/data/domestic/sub_fin.json", "digital/data/regulation.json", "hanwha/data/macro.json"):
            (self.root / rel).unlink()
        res = self.run_at(TODAY, {})
        self.assertEqual(res["errors"], [])
        for c in ("VN", "ID", "SG"):
            self.assertGreaterEqual(len(res["countries"][c]["bullets"]), 3, c)

    def test_one_country_failure_keeps_previous_block(self):
        first = self.run_at(TODAY, {})
        broken = copy.deepcopy(self.files["hanwha/data/markets.json"])
        broken["indices"][1]["monthly"] = [["2026-10", "x"]]  # 인니 지수 깨짐
        write(self.root, {"hanwha/data/markets.json": broken})
        res = self.run_at(TODAY + timedelta(days=1), first)
        self.assertTrue(res["errors"] and res["errors"][0].startswith("ID"))
        self.assertEqual(res["countries"]["ID"]["bullets"], first["countries"]["ID"]["bullets"])

    def test_report_name_and_polarity_helpers(self):
        self.assertEqual(bt.rep_name({"report": {"name": "반기보고서 (2026.06)"}}), "2026.06 반기보고서")
        self.assertEqual(bt.rep_name({"report": {"name": "[기재정정]분기보고서 (2025.09)"}}), "2025.09 분기보고서")
        self.assertEqual(bt.polarity("FTSE Russell Keeps Indonesia Off Watchlist"), 1)
        self.assertEqual(bt.polarity("GIC, Temasek rebut allegations of pressuring MSCI to downgrade Indonesia"), 0)
        self.assertEqual(bt.polarity("Why is Indonesia facing a rare MSCI downgrade"), -1)
        self.assertEqual(bt.countries_of("Indonesia stock exchange chief defends MSCI after ex-minister alleges Singapore interference"), ["ID"])


if __name__ == "__main__":
    unittest.main()
