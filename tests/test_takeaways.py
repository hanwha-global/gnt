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
            "가증권": {"report": "2025 사업보고서", "subs": {"Ga Securities Vietnam": {"country": "베트남", "equity": 1000, "rev": 100, "ni": 10}}},
            "나증권": {"report": "2025 사업보고서", "subs": {"Na Securities Vietnam": {"country": "베트남", "equity": 1500, "rev": 100, "ni": 20},
                             "Na Asset Management Vietnam": {"country": "베트남", "equity": 9000, "rev": 50, "ni": 5}}},
            "다증권": {"report": "2025 사업보고서", "subs": {"Da Securities Vietnam JSC": {"country": "베트남", "equity": 2000, "rev": 100, "ni": 15}}}}},
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

    def test_one_country_failure_keeps_previous_block_and_pending_triggers(self):
        first = self.run_at(TODAY, {})
        day1, day2 = TODAY + timedelta(days=1), TODAY + timedelta(days=2)
        # 실패한 날: 새 공시·인니 금리 인하·새 인니 기사가 함께 들어옴
        self.files["hanwha/data/dart_subs.json"]["periods"][-1]["report"]["rcept_no"] = "Q3"
        self.files["hanwha/data/markets.json"]["policy"]["table"][0]["now"] = 5.5
        self.files["site/data/global/macro_news.json"]["countries"]["ID"]["items"].insert(
            0, {"date": day1.isoformat(), "title": "Indonesia stocks plunge as MSCI downgrade looms", "src": "Reuters", "url": "u-id-new", "priority": True})
        write(self.root, self.files)
        real = bt.evaluate

        def broken(D, c, *a, **k):
            if c == "ID":
                raise ValueError("가상 오류")
            return real(D, c, *a, **k)
        bt.evaluate = broken
        try:
            res = self.run_at(day1, first)
        finally:
            bt.evaluate = real
        self.assertTrue(res["errors"] and res["errors"][0].startswith("ID"))
        self.assertEqual(res["countries"]["ID"]["bullets"], first["countries"]["ID"]["bullets"])
        self.assertEqual(res["countries"]["ID"]["last_check"], "확인 실패")
        self.assertEqual(res["state"]["countries"]["ID"], first["state"]["countries"]["ID"])
        self.assertTrue(any(r.startswith("DART") for r in res["countries"]["VN"]["reason"]))
        # 다음 날 복구되면 실패한 날 놓친 공시·금리·기사가 그대로 잡힌다
        again = self.run_at(day2, res)
        reasons = " ".join(again["countries"]["ID"]["reason"] or [])
        self.assertEqual(again["countries"]["ID"]["last_check"], "갱신")
        self.assertIn("DART", reasons)
        self.assertIn("정책금리 5.75% → 5.50%", again["countries"]["ID"]["reason"] + [reasons])

    def test_one_day_gap_does_not_let_another_rule_take_the_slot(self):
        # 인니는 4줄이 꽉 차 있고 교차판매(R06) 등이 밀려 있다. 루피아 환율이 하루 빠져 R04가 안 잡혀도 문구는 그대로
        first = self.run_at(TODAY, {})
        self.assertIn("R06", [x["rule"] for x in first["countries"]["ID"]["candidates"]])
        good = copy.deepcopy(self.files["hanwha/data/macro.json"])
        gap = copy.deepcopy(good)
        del gap["fx"]["IDR"]
        write(self.root, {"hanwha/data/macro.json": gap})
        d1 = self.run_at(TODAY + timedelta(days=1), first)
        self.assertEqual(d1["countries"]["ID"]["last_check"], "큰 변화 없음", d1["countries"]["ID"].get("reason"))
        self.assertIn("R04", self.rules(d1, "ID"))
        write(self.root, {"hanwha/data/macro.json": good})
        d2 = self.run_at(TODAY + timedelta(days=2), d1)
        self.assertEqual(d2["countries"]["ID"]["last_check"], "큰 변화 없음", d2["countries"]["ID"].get("reason"))
        self.assertEqual(d2["countries"]["ID"]["bullets"], first["countries"]["ID"]["bullets"])

    def test_same_day_rerun_counts_one_miss(self):
        first = self.run_at(TODAY, {})
        del self.files["site/data/domestic/hub_news.json"]["hubs"]["한화투자증권|싱가포르"]
        write(self.root, self.files)
        day = TODAY + timedelta(days=1)
        morning = bt.run(root=self.root, now=at(day, 6), prev=first)
        noon = bt.run(root=self.root, now=at(day, 12), prev=morning)  # 수동 실행
        self.assertEqual(noon["countries"]["SG"]["last_check"], "큰 변화 없음")
        self.assertIn("R18", self.rules(noon, "SG"))
        nxt = self.run_at(day + timedelta(days=1), noon)
        self.assertNotIn("R18", self.rules(nxt, "SG"))

    def test_evidence_only_values_do_not_rewrite(self):
        # 베트남 지수 1주 등락이 3%선을 오가도(마케팅 근거에만 쓰임) 문구를 바꾸지 않는다
        first = self.run_at(TODAY, {})
        prev = first
        for i, w in enumerate((2.9, 3.1, 2.9), start=1):
            self.files["hanwha/data/markets.json"]["indices"][0]["chg"]["1W"] = w
            write(self.root, self.files)
            prev = self.run_at(TODAY + timedelta(days=i), prev)
            self.assertEqual(prev["countries"]["VN"]["last_check"], "큰 변화 없음", (w, prev["countries"]["VN"].get("reason")))

    def test_quiet_day_keeps_regime_with_bullets(self):
        # 베트남 호재 기사가 30일을 넘겨 국면이 풀린 첫날: 줄(R07)은 하루 유예로 남으니 '시장 지위 상향' 표시도 남는다
        for it, n in zip(self.files["site/data/global/macro_news.json"]["countries"]["VN"]["items"], (28, 27)):
            it["date"] = ds(n)
        write(self.root, self.files)
        first = self.run_at(TODAY, {})
        self.assertEqual(first["countries"]["VN"]["regime"], "POS")
        res = self.run_at(TODAY + timedelta(days=3), first)
        self.assertEqual(res["countries"]["VN"]["last_check"], "큰 변화 없음", res["countries"]["VN"].get("reason"))
        self.assertIn("R07", self.rules(res, "VN"))
        self.assertEqual(res["countries"]["VN"]["regime"], "POS")

    def test_archived_news_keeps_working(self):
        # 피드에서 빠진 구조 기사는 보관함에서 다시 읽는다(url 포함)
        first = self.run_at(TODAY, {})
        self.assertTrue(all("url" not in v for v in first["state"]["seen"].values()))
        self.files["site/data/global/macro_news.json"]["countries"]["ID"]["items"] = []
        write(self.root, self.files)
        res = self.run_at(TODAY + timedelta(days=1), first)
        self.assertEqual(res["errors"], [])
        r08 = self.rules(res, "ID").get("R08")
        self.assertIsNotNone(r08)
        self.assertTrue(all(l["url"].startswith("u-id") for l in r08["links"]))
        # 다른 나라 기사는 보관하지 않는다
        self.assertNotIn("u-hub-in", first["state"]["seen"])

    def test_repeated_year_to_date_injection_keeps_first_date(self):
        first = self.run_at(TODAY, {})
        self.assertEqual(first["state"]["injection"]["SG"]["rcept_dt"], "20260813")
        later = date(2026, 11, 20)
        inv = self.files["hanwha/data/dart_subs.json"]["invest"]
        inv["report"] = {"name": "분기보고서 (2026.09)", "rcept_no": "Q3", "rcept_dt": "20261116"}  # 3분기에도 같은 누적 출자
        write(self.root, self.files)
        res = self.run_at(later, first)
        self.assertEqual(res["state"]["injection"]["SG"]["rcept_dt"], "20260813")

    def test_null_index_change_does_not_crash(self):
        self.files["hanwha/data/markets.json"]["indices"][2]["chg"]["1W"] = None
        self.files["hanwha/data/markets.json"]["indices"][0]["chg"]["1W"] = None
        write(self.root, self.files)
        res = self.run_at(TODAY, {})
        self.assertEqual(res["errors"], [])
        for c in ("VN", "ID", "SG"):
            self.assertGreaterEqual(len(res["countries"][c]["bullets"]), 3, c)

    def test_pinned_host_absorbs_merged_rule(self):
        # 베트남 3줄(R01 인수·R07·R12). 경쟁사 요약재무가 하루 빠져 R01이 안 잡혀도 R02가 따로 들어와 문구를 바꾸지 않는다
        mk = self.files["hanwha/data/markets.json"]
        mk["indices"][0]["chg"]["1W"] = 0
        self.files["site/data/global/markets.json"]["markets"][0]["tables"] = []
        write(self.root, self.files)
        first = self.run_at(TODAY, {})
        self.assertEqual(sorted(self.rules(first, "VN")), ["R01", "R07", "R12"])
        (self.root / "site/data/domestic/sub_fin.json").unlink()
        d1 = self.run_at(TODAY + timedelta(days=1), first)
        self.assertEqual(d1["countries"]["VN"]["last_check"], "큰 변화 없음", d1["countries"]["VN"].get("reason"))
        write(self.root, {"site/data/domestic/sub_fin.json": self.files["site/data/domestic/sub_fin.json"]})
        d2 = self.run_at(TODAY + timedelta(days=2), d1)
        d3 = self.run_at(TODAY + timedelta(days=3), d2)
        for r in (d2, d3):
            self.assertEqual(r["countries"]["VN"]["last_check"], "큰 변화 없음", r["countries"]["VN"].get("reason"))

    def test_fallback_lines_are_not_pinned_or_duplicated(self):
        f = self.files
        f["hanwha/data/dart_subs.json"]["periods"][-1]["subs"]["VN"]["ni"] = 50
        del f["site/data/domestic/sub_fin.json"]["firms"]["다증권"]
        del f["site/data/domestic/hub_news.json"]["hubs"]["미래에셋증권|베트남"]
        f["site/data/global/macro_news.json"]["countries"]["VN"]["items"] = []
        f["hanwha/data/markets.json"]["indices"][0]["chg"]["1W"] = 0
        f["site/data/global/markets.json"]["markets"][0]["tables"] = []
        write(self.root, f)
        first = self.run_at(TODAY, {})
        self.assertTrue(any(b["rule"].startswith("F") for b in first["countries"]["VN"]["bullets"]))
        f["hanwha/data/markets.json"]["policy"]["table"][1]["now"] = 4.25
        write(self.root, f)
        prev = first
        for i in (1, 2, 3):
            prev = self.run_at(TODAY + timedelta(days=i), prev)
            rules = [b["rule"] for b in prev["countries"]["VN"]["bullets"]]
            self.assertEqual(len(rules), len(set(rules)), rules)
            if i > 1:
                self.assertEqual(prev["countries"]["VN"]["last_check"], "큰 변화 없음", prev["countries"]["VN"].get("reason"))

    def test_regime_flip_does_not_keep_opposite_line(self):
        first = self.run_at(TODAY, {})
        day = TODAY + timedelta(days=1)
        self.files["site/data/global/macro_news.json"]["countries"]["VN"]["items"].insert(
            0, {"date": day.isoformat(), "title": "Vietnam stocks plunge as foreign outflow deepens", "src": "Reuters", "url": "u-vn-neg", "priority": True})
        self.files["hanwha/data/markets.json"]["indices"][0]["chg"]["1M"] = -12
        write(self.root, self.files)
        res = self.run_at(day, first)
        vn = res["countries"]["VN"]
        self.assertEqual(vn["regime"], "NEG")
        self.assertNotIn("R07", self.rules(res, "VN"))
        self.assertIn("R08", self.rules(res, "VN"))
        # 걸린 결정을 말하는 기사가 없으니 '시장 불안 진정'을 기준으로
        self.assertTrue(self.rules(res, "VN")["R08"]["text"].startswith("시장 불안 진정"))
        again = self.run_at(day + timedelta(days=1), res)
        self.assertEqual(again["countries"]["VN"]["last_check"], "큰 변화 없음", again["countries"]["VN"].get("reason"))

    def test_shock_state_survives_a_data_gap(self):
        self.files["hanwha/data/markets.json"]["indices"][2]["chg"]["1D"] = -5.0
        write(self.root, self.files)
        first = self.run_at(TODAY, {})
        gap = copy.deepcopy(self.files["hanwha/data/markets.json"])
        gap["indices"][2]["chg"] = {k: None for k in gap["indices"][2]["chg"]}
        write(self.root, {"hanwha/data/markets.json": gap})
        d1 = self.run_at(TODAY + timedelta(days=1), first)
        write(self.root, {"hanwha/data/markets.json": self.files["hanwha/data/markets.json"]})
        d2 = self.run_at(TODAY + timedelta(days=2), d1)
        self.assertEqual(d2["countries"]["SG"]["last_check"], "큰 변화 없음", d2["countries"]["SG"].get("reason"))

    def test_news_seen_in_failed_rerun_is_caught_next_check(self):
        first = self.run_at(TODAY, {})
        day = TODAY + timedelta(days=1)
        morning = bt.run(root=self.root, now=at(day, 7), prev=first)
        self.files["site/data/global/macro_news.json"]["countries"]["ID"]["items"].insert(
            0, {"date": day.isoformat(), "title": "Indonesia stocks plunge as MSCI downgrade looms", "src": "Reuters", "url": "u-id-pm", "priority": True})
        write(self.root, self.files)
        real = bt.evaluate
        bt.evaluate = lambda D, c, *a, **k: (_ for _ in ()).throw(ValueError("x")) if c == "ID" else real(D, c, *a, **k)
        try:
            noon = bt.run(root=self.root, now=at(day, 13), prev=morning)
        finally:
            bt.evaluate = real
        nxt = self.run_at(day + timedelta(days=1), noon)
        self.assertTrue(any(r.startswith("새 뉴스") for r in nxt["countries"]["ID"]["reason"] or []), nxt["countries"]["ID"].get("reason"))

    def test_weekly_fx_line_keeps_its_variant_on_rerun(self):
        self.files["hanwha/data/macro.json"]["fx"]["SGD"]["ytd_pct"] = -11
        self.files["hanwha/data/markets.json"]["fx"]["rows"][3]["chg_1w"] = -3.3
        write(self.root, self.files)
        first = bt.run(root=self.root, now=at(TODAY, 7), prev={})
        r09 = self.rules(first, "SG").get("R09")
        self.assertIsNotNone(r09)
        self.assertEqual(r09["variant"], "week")
        self.assertIn("단기 약세", r09["text"])
        self.assertIn("최근 1주", " ".join(r09["evidence"]))
        again = bt.run(root=self.root, now=at(TODAY, 8), prev=first)
        self.assertEqual(again["countries"]["SG"]["last_check"], "큰 변화 없음", again["countries"]["SG"].get("reason"))

    def test_period_labels_follow_the_latest_report(self):
        subs = self.files["hanwha/data/dart_subs.json"]
        sub = lambda a, l, r, n: {"unit": "백만원", "assets": a, "liab": l, "rev": r, "ni": n}
        subs["periods"].append({"label": "9M26", "period": "9M", "year": "2026", "months": 9,
                                "report": {"name": "분기보고서 (2026.09)", "rcept_no": "Q3", "rcept_dt": "20261114"},
                                "subs": {"VN": sub(1100, 680, 165, 8), "CSA": sub(480, 190, 60, -8), "CAM": sub(45, 5, 15, -4), "SG": sub(160, 5, 4, -14)}})
        write(self.root, self.files)
        res = self.run_at(date(2026, 11, 20), {})
        text = json.dumps(res["countries"], ensure_ascii=False)
        self.assertNotIn("반기 환산", text)
        self.assertIn("9개월 환산", text)

    def test_annual_report_compares_with_previous_year_from_state(self):
        first = self.run_at(TODAY, {})
        self.assertIn("2025", first["state"]["fy"])
        subs = self.files["hanwha/data/dart_subs.json"]
        sub = lambda a, l, r, n: {"unit": "백만원", "assets": a, "liab": l, "rev": r, "ni": n}
        subs["periods"] = [{"label": "FY2026", "period": "FY", "year": "2026", "months": 12,
                            "report": {"name": "사업보고서 (2026.12)", "rcept_no": "F2", "rcept_dt": "20270310"},
                            "subs": {"VN": sub(1100, 650, 230, 30), "CSA": sub(470, 190, 80, -15), "CAM": sub(45, 5, 20, -5), "SG": sub(160, 5, 5, -24)}}]
        write(self.root, self.files)
        res = self.run_at(date(2027, 3, 12), first)
        sg = self.rules(res, "SG")["R11"]
        self.assertIn("FY2025 순손실", " ".join(sg["evidence"]))
        # 인니 증권은 FY2025 흑자 → FY2026 적자: 적자 전환 줄이 살아 있다
        self.assertIn("적자 전환", json.dumps(res["countries"]["ID"], ensure_ascii=False))

    def test_share_trend_window_and_english_competitor_news(self):
        # 5월에는 1~6월 평균이 최근 3개월과 겹치므로, 겹치지 않는 실제 구간으로 적는다
        idx = {"last_day": "2027-05-19", "trend": {
            "KI": {"pts": [["2027-01", 0.50], ["2027-02", 0.55], ["2027-03", 0.80], ["2027-04", 0.95], ["2027-05", 0.9]]},
            "XL": {"pts": [["2027-01", 10.0], ["2027-02", 11.0], ["2027-03", 12.0], ["2027-04", 12.5], ["2027-05", 12.0]]}}}
        write(self.root, {"insight/data/idx_share.json": idx})
        D = bt.Data(self.root, date(2027, 5, 20))
        fact = bt.r17_share_gap(D, "ID")["fact"]
        self.assertIn("2~4월 평균", fact)
        self.assertIn("1월 0.50%", fact)
        self.assertNotIn("1~6월", fact)
        # 영문 경쟁사 기사도 빈 따옴표 없이 '매체 날짜 보도'로
        self.files["site/data/domestic/hub_news.json"]["hubs"]["미래에셋증권|베트남"] = [
            {"date": ds(1), "title": "KB Securities Vietnam to raise stake, eyes top-10 HOSE share", "src": "The Korea Herald", "url": "u-en"}]
        write(self.root, self.files)
        ev = bt.r02_peer_capital(bt.Data(self.root, TODAY), "VN")["evidence"][0]
        self.assertNotIn("''", ev)
        self.assertEqual(ev, "The Korea Herald 10/25 보도(최근 45일)")   # 한 건이면 날짜를 두 번 쓰지 않는다

    def neg_vn(self, m1=-11, age=10):
        """베트남에 악재 기사 한 건 + 지수 1개월 급락(구조적 악재 국면)."""
        self.files["site/data/global/macro_news.json"]["countries"]["VN"]["items"] = [
            {"date": ds(age), "title": "Vietnam stocks plunge as foreign outflow deepens", "src": "Reuters", "url": "u-vn-neg", "priority": True}]
        self.files["hanwha/data/markets.json"]["indices"][0]["chg"]["1M"] = m1
        write(self.root, self.files)

    def test_pinned_risk_line_keeps_gating_on_a_gap_day(self):
        # 1개월 등락이 -10% 문턱을 오가도, 유예 중인 리스크 줄의 국면으로 인수 보류 문구가 유지된다(매일 다시 쓰지 않음)
        self.neg_vn()
        prev = self.run_at(TODAY, {})
        self.assertEqual(self.rules(prev, "VN")["R01"]["variant"], "acquire-gated")
        for i, m1 in enumerate((-9.5, -10.5, -9.5, -10.5), 1):
            self.files["hanwha/data/markets.json"]["indices"][0]["chg"]["1M"] = m1
            write(self.root, self.files)
            prev = self.run_at(TODAY + timedelta(days=i), prev)
            vn = prev["countries"]["VN"]
            self.assertEqual(vn["last_check"], "큰 변화 없음", (i, vn.get("reason")))
            self.assertEqual(vn["regime"], "NEG")

    def test_fading_regime_rewrites_once(self):
        # 마지막 악재 기사가 30일을 넘기면: 하루 유예 뒤 한 번만 다시 쓴다(인수 보류 해제와 리스크 줄 삭제가 같은 날)
        self.neg_vn(m1=-12, age=29)
        prev = self.run_at(TODAY, {})
        changed = []
        for i in (1, 2, 3):
            prev = self.run_at(TODAY + timedelta(days=i), prev)
            if prev["countries"]["VN"]["last_check"] == "갱신":
                changed.append(i)
        self.assertEqual(len(changed), 1, changed)
        vn = self.rules(prev, "VN")
        self.assertNotIn("R08", vn)
        self.assertEqual(vn["R01"]["variant"], "acquire")
        # 호재 국면이 저물 때도 공격적 마케팅과 시장 지위 줄이 같은 날 함께 바뀐다
        self.files = fixture()
        for it, n in zip(self.files["site/data/global/macro_news.json"]["countries"]["VN"]["items"], (29, 28)):
            it["date"] = ds(n)
        self.files["hanwha/data/dart_subs.json"]["periods"][-1]["subs"]["VN"]["ni"] = 15
        write(self.root, self.files)
        prev = self.run_at(TODAY, {})
        self.assertEqual(self.rules(prev, "VN")["MKT"]["variant"], "aggressive")
        changed = []
        for i in (1, 2, 3):
            prev = self.run_at(TODAY + timedelta(days=i), prev)
            if prev["countries"]["VN"]["last_check"] == "갱신":
                changed.append(i)
        self.assertEqual(len(changed), 1, changed)

    def test_gap_on_a_news_day_keeps_unrelated_line(self):
        # 루피아 환율이 빠진 날 인니 악재 기사가 함께 와도, 환율로 정해지는 인수 비용 줄(R04)은 하루 자리를 지킨다
        first = self.run_at(TODAY, {})
        self.assertIn("R04", self.rules(first, "ID"))
        good = copy.deepcopy(self.files["hanwha/data/macro.json"])
        gap = copy.deepcopy(good)
        del gap["fx"]["IDR"]
        day1 = TODAY + timedelta(days=1)
        self.files["site/data/global/macro_news.json"]["countries"]["ID"]["items"].insert(
            0, {"date": day1.isoformat(), "title": "Indonesia stocks tumble as foreign outflow deepens", "src": "Reuters", "url": "u-id-x", "priority": True})
        write(self.root, {"hanwha/data/macro.json": gap, "site/data/global/macro_news.json": self.files["site/data/global/macro_news.json"]})
        d1 = self.run_at(day1, first)
        self.assertEqual(d1["countries"]["ID"]["last_check"], "갱신")
        self.assertIn("R04", self.rules(d1, "ID"))
        write(self.root, {"hanwha/data/macro.json": good})
        d2 = self.run_at(day1 + timedelta(days=1), d1)
        self.assertEqual(d2["countries"]["ID"]["last_check"], "큰 변화 없음", d2["countries"]["ID"].get("reason"))

    def test_acquire_gated_line_keeps_hysteresis(self):
        self.neg_vn()
        self.files["hanwha/data/dart_subs.json"]["periods"][0]["subs"]["VN"]["ni"] = 29   # FY ROE 7.25% vs 현지 중간값 10.5%
        write(self.root, self.files)
        first = self.run_at(TODAY, {})
        self.assertEqual(self.rules(first, "VN")["R01"]["variant"], "acquire-gated")
        # 현지 상장사 ROE가 조금 내려 0.70~0.75배 사이로: 게시 중인 인수 줄은 유지
        self.files["site/data/global/listed.json"]["markets"]["vn"]["rows"] = [
            {"equity": 100, "ni": 10}, {"equity": 100, "ni": 11.5}, {"equity": 100, "ni": 8}, {"equity": 100, "ni": 10.5}]
        write(self.root, self.files)
        res = self.run_at(TODAY + timedelta(days=1), first)
        self.assertEqual(res["countries"]["VN"]["last_check"], "큰 변화 없음", res["countries"]["VN"].get("reason"))

    def test_missing_dart_file_is_a_gap_not_a_new_report(self):
        # 공시 파일이 빠지거나 깨진 날은 판단하지 않고(확인 실패, 이전 문구 유지), 돌아온 날도 새 보고서로 보지 않는다
        first = self.run_at(TODAY, {})
        keep = (self.root / "hanwha/data/dart_subs.json").read_bytes()
        for broken in (None, "{"):
            if broken is None:
                (self.root / "hanwha/data/dart_subs.json").unlink()
            else:
                (self.root / "hanwha/data/dart_subs.json").write_text(broken, encoding="utf-8")
            d1 = self.run_at(TODAY + timedelta(days=1), first)
            (self.root / "hanwha/data/dart_subs.json").write_bytes(keep)
            d2 = self.run_at(TODAY + timedelta(days=2), d1)
            for c in ("VN", "ID", "SG"):
                self.assertEqual(d1["countries"][c]["last_check"], "확인 실패")
                self.assertEqual(d1["countries"][c]["bullets"], first["countries"][c]["bullets"])
                self.assertEqual(d2["countries"][c]["last_check"], "큰 변화 없음", (c, d2["countries"][c].get("reason")))

    def test_resolved_or_decided_downgrade_ends_pending_wording(self):
        first = self.run_at(TODAY, {})
        self.assertTrue(self.rules(first, "ID")["R08"]["text"].startswith("MSCI 결정"))
        day = TODAY + timedelta(days=1)
        items = self.files["site/data/global/macro_news.json"]["countries"]["ID"]["items"]
        for title, label in (("MSCI decides not to downgrade Indonesia", "MSCI 강등 우려 해소"),
                             ("MSCI downgrades Indonesia to frontier market status", "MSCI 강등 결정")):
            write(self.root, {"site/data/global/macro_news.json": {"countries": {"ID": {"items": [
                {"date": day.isoformat(), "title": title, "src": "Reuters", "url": "u-" + label, "priority": True}] + items}}}})
            res = self.run_at(day, first)
            id_ = res["countries"]["ID"]
            self.assertEqual(id_["last_check"], "갱신", title)
            self.assertIn(f"새 뉴스: {label}", id_["reason"])
            text = " ".join(b["text"] for b in id_["bullets"])
            self.assertNotIn("MSCI 결정", text, title)

    def test_peer_margin_uses_the_peer_report_year(self):
        first = self.run_at(TODAY, {})
        sub = lambda a, l, r, n: {"unit": "백만원", "assets": a, "liab": l, "rev": r, "ni": n}
        self.files["hanwha/data/dart_subs.json"]["periods"] = [
            {"label": "FY2026", "period": "FY", "year": "2026", "months": 12,
             "report": {"name": "사업보고서 (2026.12)", "rcept_no": "F2", "rcept_dt": "20270310"},
             "subs": {"VN": sub(1100, 650, 220, 9), "CSA": sub(470, 190, 80, -15), "CAM": sub(45, 5, 20, -5), "SG": sub(160, 5, 5, -24)}}]
        for f in self.files["site/data/domestic/sub_fin.json"]["firms"].values():
            f["report"] = "2026 사업보고서"
        write(self.root, self.files)
        res = self.run_at(date(2027, 3, 20), first)
        ev = " ".join(self.rules(res, "VN")["R12"]["evidence"])
        self.assertIn("순이익률 FY2026 4.1% vs 한국계 흑자 3사 FY2026 중간값 15.0%", ev)
        self.assertNotIn("FY2025 중간값", ev)

    def two_days(self, first, day_files, gaps=(), restore=None):
        """하루째: day_files 반영 + gaps 파일 삭제, 이틀째: 지운 파일 복구. (하루째, 이틀째) 결과."""
        day = TODAY + timedelta(days=1)
        write(self.root, day_files)
        for rel in gaps:
            (self.root / rel).unlink()
        d1 = self.run_at(day, first)
        write(self.root, {rel: self.files[rel] for rel in gaps})
        return d1, self.run_at(day + timedelta(days=1), d1)

    def test_pinned_lines_follow_todays_regime(self):
        # 악재가 새로 뜬 날 경쟁사 자료가 빠져 인수 줄이 유예돼도 '보류' 문구로, 다음 날은 그대로
        first = self.run_at(TODAY, {})
        self.assertEqual(self.rules(first, "VN")["R01"]["variant"], "acquire")
        mn = self.files["site/data/global/macro_news.json"]
        mn["countries"]["VN"]["items"].insert(0, {"date": (TODAY + timedelta(days=1)).isoformat(), "title": "Vietnam stocks plunge as foreign outflow deepens",
                                                  "src": "Reuters", "url": "u-vn-neg", "priority": True})
        self.files["hanwha/data/markets.json"]["indices"][0]["chg"]["1M"] = -11
        d1, d2 = self.two_days(first, {"site/data/global/macro_news.json": mn, "hanwha/data/markets.json": self.files["hanwha/data/markets.json"]},
                               gaps=("site/data/domestic/sub_fin.json",))
        vn = self.rules(d1, "VN")
        self.assertIn("R08", vn)
        self.assertEqual(vn["R01"]["variant"], "acquire-gated")
        self.assertIn("이후로 미루고", vn["R01"]["text"])
        self.assertEqual(d2["countries"]["VN"]["last_check"], "큰 변화 없음", d2["countries"]["VN"].get("reason"))

    def test_pinned_marketing_is_not_aggressive_under_bad_news(self):
        self.files["hanwha/data/dart_subs.json"]["periods"][-1]["subs"]["VN"]["ni"] = 15
        write(self.root, self.files)
        first = self.run_at(TODAY, {})
        self.assertEqual(self.rules(first, "VN")["MKT"]["variant"], "aggressive")
        mn = self.files["site/data/global/macro_news.json"]
        mn["countries"]["VN"]["items"].insert(0, {"date": (TODAY + timedelta(days=1)).isoformat(), "title": "Vietnam stocks plunge as foreign outflow deepens",
                                                  "src": "Reuters", "url": "u-vn-neg", "priority": True})
        self.files["hanwha/data/markets.json"]["indices"][0]["chg"]["1M"] = -11
        d1, d2 = self.two_days(first, {"site/data/global/macro_news.json": mn, "hanwha/data/markets.json": self.files["hanwha/data/markets.json"]},
                               gaps=("site/data/global/markets.json",))
        vn = self.rules(d1, "VN")
        self.assertIn("R08", vn)
        self.assertNotEqual(vn["MKT"]["variant"], "aggressive")
        self.assertNotIn("공격적", vn["MKT"]["text"])
        self.assertEqual(d2["countries"]["VN"]["last_check"], "큰 변화 없음", d2["countries"]["VN"].get("reason"))

    def test_event_line_is_not_blocked_by_a_pinned_line(self):
        # 동 약세 줄(리스크)이 환율 공백으로 유예 중이어도, 새 악재 기사의 리스크 줄이 그날 바로 나온다
        self.files["hanwha/data/macro.json"]["fx"]["VND"]["ytd_pct"] = -15
        self.files["site/data/global/markets.json"]["markets"][0]["tables"] = []
        write(self.root, self.files)
        first = self.run_at(TODAY, {})
        self.assertIn("R09", self.rules(first, "VN"))
        mn = self.files["site/data/global/macro_news.json"]
        mn["countries"]["VN"]["items"].insert(0, {"date": (TODAY + timedelta(days=1)).isoformat(), "title": "Vietnam stocks plunge as foreign outflow deepens",
                                                  "src": "Reuters", "url": "u-vn-neg", "priority": True})
        self.files["hanwha/data/markets.json"]["indices"][0]["chg"]["1M"] = -11
        gap = copy.deepcopy(self.files["hanwha/data/macro.json"])
        del gap["fx"]["VND"]
        d1, d2 = self.two_days(first, {"site/data/global/macro_news.json": mn, "hanwha/data/markets.json": self.files["hanwha/data/markets.json"],
                                       "hanwha/data/macro.json": gap})
        self.assertIn("R08", self.rules(d1, "VN"))
        self.assertNotIn("R09", self.rules(d1, "VN"))
        write(self.root, {"hanwha/data/macro.json": self.files["hanwha/data/macro.json"]})
        d3 = self.run_at(TODAY + timedelta(days=3), d2)
        for res in (d2, d3):
            self.assertEqual(res["countries"]["VN"]["last_check"], "큰 변화 없음", res["countries"]["VN"].get("reason"))

    def test_pinned_loss_line_keeps_its_cost_ratio(self):
        # 적자 법인의 비용/매출 배수는 상태에 남아, 유예 중인 적자 줄로도 마케팅 지출 제안을 막는다
        self.files["hanwha/data/dart_subs.json"]["periods"][-1]["subs"]["VN"]["ni"] = -400
        write(self.root, self.files)
        first = self.run_at(TODAY, {})
        meta = first["state"]["countries"]["VN"]["meta"]
        self.assertGreaterEqual(meta["R11"]["cir"], 3)
        self.assertNotIn("MKT", self.rules(first, "VN"))
        # 다음 날 같은 법인이 흑자로 보이는 자료(가상)로 적자 줄이 안 잡혀도, 유예 줄의 배수로 판단
        self.files["hanwha/data/dart_subs.json"]["periods"][-1]["subs"]["VN"]["ni"] = 5
        write(self.root, self.files)
        D = bt.Data(self.root, TODAY + timedelta(days=1), first["state"])
        pub = {b["rule"]: b for b in first["countries"]["VN"]["bullets"]}
        chosen, _, fired, _ = bt.evaluate(D, "VN", pub, pinned=[{**pub["R11"], **meta["R11"]}])
        self.assertNotIn("MKT", [b["rule"] for b in chosen])
        self.assertNotIn("MKT", fired)   # 조정으로 뺀 줄은 '발동'으로 세지 않는다(게시 중이면 유예 뒤 빠진다)

    def test_same_day_decision_beats_pending_article(self):
        first = self.run_at(TODAY, {})
        day = (TODAY + timedelta(days=1)).isoformat()
        items = self.files["site/data/global/macro_news.json"]["countries"]["ID"]["items"]
        C = {"date": day, "title": "MSCI downgrades Indonesia to frontier market status", "src": "Reuters", "url": "u-C", "priority": True}
        P = {"date": day, "title": "Indonesia stocks tumble as MSCI downgrade risk weighs on banks", "src": "Bloomberg", "url": "u-P", "priority": True}
        write(self.root, {"site/data/global/macro_news.json": {"countries": {"ID": {"items": [C, P] + items}}}})
        d1 = self.run_at(TODAY + timedelta(days=1), first)
        self.assertTrue(self.rules(d1, "ID")["R08"]["text"].startswith("시장 불안 진정"))
        # 이튿날 피드에서 결정 기사가 빠지고 보관함에만 남아도 같은 판단
        write(self.root, {"site/data/global/macro_news.json": {"countries": {"ID": {"items": [P] + items}}}})
        d2 = self.run_at(TODAY + timedelta(days=2), d1)
        self.assertEqual(d2["countries"]["ID"]["last_check"], "큰 변화 없음", d2["countries"]["ID"].get("reason"))

    def test_gap_day_event_does_not_reshuffle_lines(self):
        # 환율 공백으로 인수 보류 줄이 유예된 날 금리 변경·감독 제재 기사가 와도, 평소 점수에서 지는 줄이 끼어들지 않는다
        first = self.run_at(TODAY, {})
        want = set(self.rules(first, "ID"))
        day = (TODAY + timedelta(days=1)).isoformat()
        gap = copy.deepcopy(self.files["hanwha/data/macro.json"])
        del gap["fx"]["IDR"]
        mk = copy.deepcopy(self.files["hanwha/data/markets.json"])
        mk["policy"]["table"][0].update(now=6.0, month="2026-10")
        mn = copy.deepcopy(self.files["site/data/global/macro_news.json"])
        mn["countries"]["ID"]["items"].insert(0, {"date": day, "title": "Indonesia's OJK fines three brokers over client fraud",
                                                  "src": "Reuters", "url": "u-ojk", "priority": True})
        for event in ({"hanwha/data/markets.json": mk}, {"site/data/global/macro_news.json": mn}):
            write(self.root, {**self.files, **event, "hanwha/data/macro.json": gap})
            d1 = self.run_at(TODAY + timedelta(days=1), first)
            self.assertEqual(set(self.rules(d1, "ID")), want, (list(event), d1["countries"]["ID"].get("reason")))
            write(self.root, {"hanwha/data/macro.json": self.files["hanwha/data/macro.json"]})
            d2 = self.run_at(TODAY + timedelta(days=2), d1)
            self.assertEqual(set(self.rules(d2, "ID")), want, list(event))
            self.assertEqual(d2["countries"]["ID"]["last_check"], "큰 변화 없음", d2["countries"]["ID"].get("reason"))

    def test_follow_up_after_decided_downgrade_stays_decided(self):
        # 강등이 결정된 뒤의 후속 기사('… after MSCI downgrade')로 'MSCI 결정 전까지'가 되살아나지 않는다
        first = self.run_at(TODAY, {})
        items = self.files["site/data/global/macro_news.json"]["countries"]["ID"]["items"]
        day1, day2 = (TODAY + timedelta(days=1)).isoformat(), (TODAY + timedelta(days=2)).isoformat()
        C = {"date": day1, "title": "MSCI downgrades Indonesia to frontier market status", "src": "Reuters", "url": "u-C", "priority": True}
        write(self.root, {"site/data/global/macro_news.json": {"countries": {"ID": {"items": [C] + items}}}})
        d1 = self.run_at(TODAY + timedelta(days=1), first)
        self.assertTrue(self.rules(d1, "ID")["R08"]["text"].startswith("시장 불안 진정"))
        for n, title in enumerate(("Indonesian stocks plunge after MSCI downgrade", "MSCI 강등 충격에 인니 증시 폭락")):
            F = {"date": day2, "title": title, "src": "Bloomberg", "url": f"u-F{n}", "priority": True}
            write(self.root, {"site/data/global/macro_news.json": {"countries": {"ID": {"items": [F, C] + items}}}})
            d2 = self.run_at(TODAY + timedelta(days=2), d1)
            text = " ".join(b["text"] for b in d2["countries"]["ID"]["bullets"])
            self.assertNotIn("MSCI 결정", text, title)
            self.assertNotIn("MSCI 강등 검토", " ".join(" ".join(b["evidence"]) for b in d2["countries"]["ID"]["bullets"]), title)

    def test_decision_wording_from_headlines(self):
        # 결정 전 기사는 'MSCI 결정 전까지', 우려 해소·확정 기사는 그날 바로 걷힌다(한글 제목 포함)
        first = self.run_at(TODAY, {})
        day = TODAY + timedelta(days=1)
        items = self.files["site/data/global/macro_news.json"]["countries"]["ID"]["items"]
        for title, label, still in (("MSCI Moves Closer to Downgrading Indonesia as Free-Float Fix Stalls", "MSCI 강등 검토", True),
                                    ("MSCI, 인니 강등 결정 내년으로 연기", "MSCI 강등 검토", True),
                                    ("MSCI retains Indonesia's emerging market status", "MSCI 강등 우려 해소", False),
                                    ("Indonesia dodges MSCI downgrade", "MSCI 강등 우려 해소", False),
                                    ("인도네시아 증시, MSCI 강등은 피했다", "MSCI 강등 우려 해소", False),
                                    ("MSCI, 인도네시아 강등 확정…외국인 자금 대규모 이탈 전망", "MSCI 강등 결정", False)):
            write(self.root, {"site/data/global/macro_news.json": {"countries": {"ID": {"items": [
                {"date": day.isoformat(), "title": title, "src": "연합뉴스", "url": "u-" + title, "priority": True}] + items}}}})
            id_ = self.run_at(day, first)["countries"]["ID"]
            self.assertIn(f"새 뉴스: {label}", " ".join(id_.get("reason") or []), title)
            text = " ".join(b["text"] for b in id_["bullets"])
            self.assertEqual("MSCI 결정" in text, still, title)

    def test_pending_needs_a_decision_story_after_the_last_decision(self):
        neg = lambda t, dt: {"title": t, "date": dt, "same": []}
        # 승격이 이미 발효된 뒤 '승격 후 외국인 매도가 커질 수 있다'는 걸린 재분류가 아니다
        self.assertFalse(bt.pending([], [neg("Foreign selling could deepen as Vietnam stocks slump after FTSE upgrade", "2026-11-25"),
                                         neg("베트남 증시, FTSE 승격 후 외국인 이탈 지속 전망", "2026-11-24")], "FTSE"))
        self.assertTrue(bt.pending([], [neg("Why is Indonesia facing a rare MSCI downgrade", "2026-10-23")], "MSCI"))
        for t in ("인도네시아 MSCI 강등 결정은 내년 6월", "MSCI 강등 결정 D-30…인도네시아 증시 긴장", "MSCI 인도네시아 강등 결정 6개월 유예"):
            self.assertTrue(bt.pending([], [neg(t, "2026-10-28")], "MSCI"), t)
        # 결정 뒤 후속 기사만 있으면 결정 전 경고 기사는 세지 않는다 · 결정 뒤 새 검토 기사는 다시 걸린 결정
        old = neg("Why is Indonesia facing a rare MSCI downgrade", "2026-10-23")
        done = neg("MSCI downgrades Indonesia to frontier market status", "2026-10-28")
        self.assertFalse(bt.pending([], [neg("Indonesia vows reforms after MSCI downgrade", "2026-10-29"), done, old], "MSCI"))
        self.assertTrue(bt.pending([], [neg("MSCI could cut Indonesia further in next review", "2026-11-20"), done, old], "MSCI"))
        # MSCI 가 결정하고 FTSE 검토가 남은 기사는 FTSE 쪽이 걸린 결정
        both = [neg("MSCI downgrades Indonesia to frontier; FTSE Russell to review in March", "2026-10-28")]
        self.assertFalse(bt.pending([], both, "MSCI"))
        self.assertTrue(bt.pending([], both, "FTSE"))
        # FTSE 가 관찰대상 제외를 유지한 뒤라도, 날짜가 잡힌 다음 결정은 다시 걸린 결정
        kept = [neg("FTSE Russell Keeps Indonesia Off Watchlist", "2026-10-26")]
        for t in ("MSCI cuts Indonesia to frontier status; FTSE Russell decision due in March", "FTSE 인니 재분류 결정은 내년 3월"):
            self.assertTrue(bt.pending(kept, [neg(t, "2026-10-28")], "FTSE"), t)
        for t in ("MSCI's decision on Indonesia sparks outflows", "MSCI 결정은 과했다…인니 정부 반발", "Indonesian stocks slide due to MSCI downgrade"):
            self.assertFalse(bt.pending([], [neg(t, "2026-10-30"), done], "MSCI"), t)

    def test_report_name_and_polarity_helpers(self):
        self.assertEqual(bt.rep_name({"report": {"name": "반기보고서 (2026.06)"}}), "2026.06 반기보고서")
        self.assertEqual(bt.rep_name({"report": {"name": "[기재정정]분기보고서 (2025.09)"}}), "2025.09 분기보고서")
        self.assertEqual(bt.polarity("FTSE Russell Keeps Indonesia Off Watchlist"), 1)
        self.assertEqual(bt.news_label("FTSE Russell Keeps Indonesia Off Watchlist"), "FTSE 관찰대상 제외 유지")
        # 승격 관찰대상에서 빠진 것·성장률 전망·신용등급 상향은 '시장 지위 상향'이 아니다
        self.assertEqual(bt.polarity("MSCI keeps Vietnam off watch list for potential upgrade"), 0)
        self.assertEqual(bt.polarity("Singapore upgrades 2026 GDP growth forecast"), 0)
        self.assertEqual(bt.polarity("Vietnam strengthens global credit standing with R&I upgrade to BBB"), 0)
        self.assertEqual(bt.polarity("Vietnam Plans Index Options for Next Year After FTSE Upgrade"), 1)
        self.assertEqual(bt.josa("FTSE 재분류", "과", "와"), "와")
        self.assertEqual(bt.josa("MSCI 결정", "과", "와"), "과")
        self.assertEqual(bt.josa("싱가포르 법인(PTSS)", "은", "는"), "은")
        self.assertEqual(bt.cite({"title": "Indonesian stocks slide", "src": "Reuters", "date": "2026-10-25"}), "Reuters 10/25 보도")
        # 승격 지연 기사·부인 기사·외교 제재 기사는 호재·악재로 세지 않는다
        for t in ("GIC, Temasek deny allegations of pressuring MSCI to downgrade Indonesia", "Vietnam misses out on FTSE upgrade again",
                  "FTSE Russell keeps Vietnam on watch list, delays upgrade decision", "US imposes sanctions on Vietnamese shipping firms over Iran oil",
                  "Indonesia scraps free-float rule after MSCI downgrade threat"):
            self.assertEqual(bt.polarity(t), 0, t)
        # 강등 우려가 걷힌 기사는 '관찰대상 제외 유지'처럼 안도(+1, 시장 지위 상향은 아님)
        for t in ("MSCI decides not to downgrade Indonesia, keeps emerging market status", "Indonesian stocks rally as MSCI shelves downgrade",
                  "Indonesia avoids MSCI downgrade", "MSCI spares Indonesia from downgrade", "Indonesia stocks rebound as MSCI downgrade fears fade",
                  "MSCI keeps Indonesia in emerging markets", "MSCI rules out Indonesia downgrade", "Indonesia escapes MSCI downgrade"):
            self.assertEqual(bt.polarity(t), 1, t)
            self.assertTrue(bt.relief(t), t)
            self.assertEqual(bt.news_label(t), "MSCI 강등 우려 해소", t)
        # 피하려 애쓰는 기사·하락 기사는 아직 악재('to avoid', 'drop … fears', 'withdraw funds')
        for t in ("Indonesia scrambles to avoid MSCI downgrade", "Indonesia races to avoid a downgrade by MSCI",
                  "Indonesia stocks drop on MSCI downgrade fears", "Foreign investors withdraw funds amid MSCI downgrade"):
            self.assertEqual(bt.polarity(t), -1, t)
            self.assertNotEqual(bt.news_label(t), "MSCI 강등 우려 해소", t)
        # 급락 뒤 반등 기사는 악재가 아니다 · 'emerging market upgrade' 순항 기사는 호재
        self.assertEqual(bt.polarity("Vietnam stocks rebound from slump as foreign funds return after FTSE upgrade"), 1)
        self.assertEqual(bt.polarity("Vietnam stock market remains on track for emerging market upgrade by FTSE"), 1)
        self.assertEqual(bt.news_label("Vietnam stock market remains on track for emerging market upgrade by FTSE"), "FTSE 승격")
        # '승격 지연' 라벨: 'commission'의 miss·'installs'의 stall·강등 기사에는 붙지 않는다
        self.assertEqual(bt.news_label("Vietnam misses out on FTSE upgrade again"), "FTSE 승격 지연")
        self.assertEqual(bt.news_label("Vietnam's securities commission welcomes FTSE upgrade"), "FTSE 승격")
        self.assertEqual(bt.news_label("Vietnam installs new trading system ahead of FTSE inclusion"), "FTSE 승격")
        self.assertEqual(bt.news_label("MSCI delays Indonesia downgrade decision"), "MSCI 강등 검토")
        self.assertEqual(bt.news_label("MSCI dismisses Indonesia's complaints over downgrade review"), "MSCI 강등 검토")
        # 이미 내려진 강등과 걸려 있는 강등
        self.assertEqual(bt.news_label("MSCI downgrades Indonesia to frontier market status"), "MSCI 강등 결정")
        self.assertTrue(bt.confirmed("Indonesia downgraded to standalone by MSCI"))
        self.assertFalse(bt.confirmed("Indonesia could be downgraded by MSCI"))
        # 제재 기사: 감독기관이 낸 것만(외교 제재·'fine-tune'·'SGX-listed' 제외)
        for t in ("US imposes sanctions on Vietnamese shipping firms over Iran oil", "MAS fine-tunes Singapore dollar policy as inflation eases",
                  "US sanctions Singapore-based SGX-listed shipping firm, shares tumble", "OJK fine-tunes short-selling rules",
                  "美, 이란 제재 위반 싱가포르 해운사 제재"):
            self.assertFalse(bt.reg_hit(t), t)
        for t in ("MAS fines Singapore brokerage firm for AML lapses", "SGX RegCo fines broker for lapses", "금감원, 베트남 법인 내부통제 제재",
                  "OJK sanctions Indonesian brokerage over margin breaches", "베트남 증권위원회, 한국계 증권사에 과징금"):
            self.assertTrue(bt.reg_hit(t), t)
        # 부정한 안도('won't rule out')는 위협, 한 절을 넘는 안도·업그레이드 재분류 보류·상승 유지는 강등 우려 해소가 아니다
        for t in ("MSCI won't rule out downgrading Indonesia", "MSCI does not rule out Indonesia downgrade",
                  "MSCI refuses to rule out downgrade of Indonesian stocks", "MSCI 강등 피해 우려에 인도네시아 증시 급락"):
            self.assertEqual(bt.polarity(t), -1, t)
        self.assertEqual(bt.news_label("FTSE Russell spares Indonesia; MSCI downgrade decision looms"), "MSCI 강등 검토")
        self.assertNotIn("해소", bt.news_label("MSCI shelves Vietnam reclassification review"))
        self.assertNotIn("해소", bt.news_label("Vietnam stocks retain gains as emerging market upgrade takes effect"))
        self.assertEqual(bt.news_label("MSCI spares Indonesia from downgrade; FTSE review next"), "MSCI 강등 우려 해소")
        for t in ("인도네시아, MSCI 강등 피했다", "인도네시아 증시, MSCI 강등 면했다", "MSCI, 인니 강등 결정 철회",
                  "Indonesia downgrade fears easing as MSCI signals patience", "Fears of MSCI downgrade ease as Indonesia unveils reforms"):
            self.assertEqual(bt.news_label(t), "MSCI 강등 우려 해소", t)
        # 강등 확정: 지수 회사가 주어이거나 프런티어·독립시장 이동. 앞두고·연기·임박·증권사 투자의견 하향은 아님
        for t in ("MSCI downgrades Indonesia to frontier after annual market classification review", "MSCI downgrades Indonesia to standalone in May",
                  "MSCI downgrades Indonesian stocks to frontier market", "MSCI cuts Indonesia to frontier in annual review", "MSCI, 인도네시아 프런티어로 강등",
                  "MSCI downgrades Indonesia to frontier; outflows could top $2 billion"):
            self.assertTrue(bt.confirmed(t), t)
            self.assertEqual(bt.news_label(t), "MSCI 강등 결정", t)
        for t in ("MSCI 강등 결정 앞두고 인니 증시 급락", "MSCI, 인니 강등 결정 연기", "MSCI, 인도네시아 강등 결정 임박",
                  "MSCI 강등 결정 여부에 인도네시아 증시 출렁", "Goldman downgrades Indonesia to neutral amid MSCI turmoil"):
            self.assertFalse(bt.confirmed(t), t)
        self.assertEqual(bt.polarity("Jakarta stocks rebound from MSCI downgrade rout"), -1)
        # 한글 제재·위반·벌금은 외교 제재만 아니면, 'treasury'·'미국' 언급은 외교 제재로 보지 않는다
        for t in ("NH투자증권 싱가포르법인, 공시 위반으로 제재", "KB증권 베트남법인, 증권법 위반으로 벌금 부과",
                  "SSC fines securities firm over treasury bond disclosure", "금감원, 미래에셋 베트남법인 제재…미국 법인도 검사"):
            self.assertTrue(bt.reg_hit(t), t)
        self.assertFalse(bt.reg_hit("US Treasury sanctions Singapore firms over Iran"))
        # 인용구가 여럿이면 자본·제재 관련 말, 없으면 가장 긴 것
        self.assertEqual(bt.news_label("오랜 준비 끝 '기지개'...베트남서 본격 '곳간 전쟁' 나선 증권사들"), "곳간 전쟁")
        self.assertEqual(bt.more(1, "구조 뉴스", "최근 30일"), "(구조 뉴스, 최근 30일)")
        self.assertEqual(bt.more(3, "구조 뉴스", "최근 30일"), " 등 구조 뉴스 3건(최근 30일)")
        self.assertEqual(bt.polarity("GIC, Temasek rebut allegations of pressuring MSCI to downgrade Indonesia"), 0)
        self.assertEqual(bt.polarity("Why is Indonesia facing a rare MSCI downgrade"), -1)
        self.assertEqual(bt.countries_of("Indonesia stock exchange chief defends MSCI after ex-minister alleges Singapore interference"), ["ID"])

    def test_decision_and_regulator_headlines(self):
        # 'moves closer to·cuts weight of'는 결정이 아니다 · 한글은 같은 절의 연기·유예·보류만 결정을 뒤집는다
        for t in ("MSCI Moves Closer to Downgrading Indonesia as Free-Float Fix Stalls", "MSCI moves to curb Indonesia exposure as downgrade risk grows",
                  "Indonesian stocks slump after MSCI cuts weight of Barito, Amman", "MSCI, FTSE moves weigh on Indonesian stocks amid downgrade fears",
                  "MSCI, 인니 강등 결정 내년으로 연기", "MSCI 인도네시아 강등 결정 6개월 유예", "MSCI, 인니 강등 결정 일단 보류",
                  "인도네시아 MSCI 강등 결정은 내년 6월", "MSCI 강등 결정 D-30…인니 증시 긴장", "MSCI, 인니 프런티어 강등 가능성",
                  "Indonesia fights to keep emerging market status as MSCI downgrade looms"):
            self.assertFalse(bt.confirmed(t), t)
            self.assertNotIn(bt.news_label(t),("MSCI 강등 결정", "FTSE 강등 결정", "MSCI 강등 우려 해소"), t)
        for t in ("MSCI, 인도네시아 강등 확정…외국인 자금 대규모 이탈 전망", "MSCI, 인도네시아 프런티어 강등 확정…정부 대응책 검토",
                  "MSCI 인니 강등 확정…FTSE도 강등 가능성", "MSCI, 인도네시아 프런티어 시장으로 강등", "인도네시아, 결국 MSCI 강등",
                  "MSCI cuts Indonesia to frontier status; FTSE Russell decision due in March",
                  "MSCI downgrades Indonesia to frontier; FTSE Russell to review in March",
                  "Indonesia stocks tumble as MSCI downgrades market, FTSE review looms"):
            self.assertTrue(bt.confirmed(t), t)
            self.assertEqual(bt.news_label(t), "MSCI 강등 결정", t)   # 결정한 쪽(가장 가까운 앞쪽 기관)
        # 결정 뒤 후속 기사는 '강등 여파'(경고·우려 기사는 아님)
        for t in ("Indonesian stocks plunge after MSCI downgrade", "Indonesia vows reforms after MSCI downgrade", "MSCI 강등 충격에 인니 증시 폭락"):
            self.assertEqual(bt.news_label(t), "MSCI 강등 여파", t)
            self.assertEqual(bt.decided_by(t), "MSCI", t)
        for t in ("Indonesian stocks plunge after MSCI downgrade warning", "Indonesia stocks drop on MSCI downgrade fears", "MSCI 강등 충격 우려에 인니 증시 급락"):
            self.assertEqual(bt.news_label(t), "MSCI 강등 검토", t)
            self.assertEqual(bt.decided_by(t), "", t)
        # 신흥시장 유지·강등 회피 결정은 우려 해소('to keep·to avert'처럼 애쓰는 기사는 아님)
        for t in ("MSCI retains Indonesia's emerging market status", "Indonesia retains MSCI emerging market status",
                  "MSCI keeps Indonesia's emerging market status", "MSCI keeps Indonesia in its emerging markets index",
                  "MSCI retains Indonesia as emerging market", "Indonesia dodges MSCI downgrade", "Indonesia averts MSCI downgrade",
                  "MSCI decides against Indonesia downgrade", "MSCI drops plan to downgrade Indonesia", "MSCI Won't Downgrade Indonesia After Free-Float Reforms",
                  "인도네시아 증시, MSCI 강등은 피했다", "MSCI 강등 일단 피했다", "MSCI 강등 우려 해소에 급등", "MSCI 강등 피한 인도네시아 증시 급등",
                  "MSCI says Indonesia to remain in emerging markets"):
            self.assertEqual(bt.polarity(t), 1, t)
            self.assertEqual(bt.news_label(t), "MSCI 강등 우려 해소", t)
        for t in ("Indonesia fights to keep emerging market status as MSCI downgrade looms", "Indonesia moves to avert MSCI downgrade"):
            self.assertEqual(bt.polarity(t), -1, t)
        # 경쟁사 증자 기사는 강등 이야기가 곁들여져도 그 기사로 적는다
        self.assertEqual(bt.news_label("인니 MSCI 강등 경고 속 KB증권 현지법인 ‘자본 확충’"), "자본 확충")
        self.assertNotEqual(bt.news_label("MSCI 강등 위기 인니서…미래에셋, 현지법인 1000억 증자"), "MSCI 강등 검토")
        # 미국·통상 제재는 감독 제재가 아니다 · 감독기관의 과징금·인가 취소·영업정지·견책은 감독 제재
        for t in ("美 ‘우회수출’ 제재 우려에 베트남 증시 급락", "미국 제재에 인도네시아 니켈주 급락", "베트남, 美 관세 제재 피하려 환적 단속 강화",
                  "美, 北 IT 인력 자금세탁 도운 베트남 기업 제재", "트럼프 행정부, 베트남 우회수출 제재 착수",
                  "IDX suspends trading of 5 stocks after unusual price moves", "베트남 공장 영업정지 처분", "Indonesia bans nickel ore exports"):
            self.assertFalse(bt.reg_hit(t), t)
        for t in ("Indonesia's financial regulator penalises brokers for insider trading", "Indonesia's OJK revokes licence of brokerage over client fund misuse",
                  "Vietnam's securities watchdog suspends trading at brokerage after breaches", "Singapore's MAS reprimands brokerage over failures in AML controls",
                  "SGX RegCo reprimands broker for lapses", "인니 OJK, 증권사 3곳 영업정지", "Vietnam's SSC penalizes brokerage for violations"):
            self.assertTrue(bt.reg_hit(t), t)


    def test_gap_day_pinned_line_holds_its_place_against_event_lines(self):
        # 지수 공백으로 'MSCI 결정 전까지' 줄이 유예된 날 제재 기사가 와도, 평소 점수에서 지는 줄이 그 자리를 차지하지 않는다
        items = self.files["site/data/global/macro_news.json"]["countries"]["ID"]["items"]
        self.files["site/data/global/macro_news.json"]["countries"]["ID"]["items"] = [i for i in items if "manipulation" not in i["title"]]
        write(self.root, self.files)
        first = self.run_at(TODAY, {})
        want = [b["rule"] for b in first["countries"]["ID"]["bullets"]]
        self.assertEqual(want[0], "R08")
        day = TODAY + timedelta(days=1)
        hub = copy.deepcopy(self.files["site/data/domestic/hub_news.json"])
        hub["hubs"]["미래에셋증권|인도네시아"] = [{"date": day.isoformat(), "title": "미래에셋증권 인니법인, OJK 과태료 제재", "src": "가상일보", "url": "u-hub-ojk"}]
        mn = copy.deepcopy(self.files["site/data/global/macro_news.json"])
        mn["countries"]["ID"]["items"].insert(0, {"date": day.isoformat(), "title": "Indonesian stocks slip as OJK fines three brokers over client fraud",
                                                  "src": "Reuters", "url": "u-ojk", "priority": False})
        for event in ({"site/data/domestic/hub_news.json": hub}, {"site/data/global/macro_news.json": mn}):
            write(self.root, self.files)
            d1, d2 = self.two_days(first, event, gaps=("hanwha/data/markets.json",))
            self.assertEqual([b["rule"] for b in d1["countries"]["ID"]["bullets"]], want, (list(event), d1["countries"]["ID"].get("reason")))
            self.assertEqual(d2["countries"]["ID"]["last_check"], "큰 변화 없음", (list(event), d2["countries"]["ID"].get("reason")))

    def test_relief_on_a_gap_day_rewrites_the_risk_line_once(self):
        # 지수 공백 날 강등 우려 해소 기사가 와도 리스크 줄은 '시장 불안 진정 전까지'로 고쳐 쓰고, 다음 날은 그대로
        first = self.run_at(TODAY, {})
        day = TODAY + timedelta(days=1)
        mn = copy.deepcopy(self.files["site/data/global/macro_news.json"])
        mn["countries"]["ID"]["items"].insert(0, {"date": day.isoformat(), "title": "MSCI retains Indonesia's emerging market status",
                                                  "src": "Reuters", "url": "u-rel", "priority": True})
        d1, d2 = self.two_days(first, {"site/data/global/macro_news.json": mn}, gaps=("hanwha/data/markets.json",))
        id_ = self.rules(d1, "ID")
        self.assertEqual(list(id_), [b["rule"] for b in first["countries"]["ID"]["bullets"]])
        self.assertTrue(id_["R08"]["text"].startswith("시장 불안 진정"))
        self.assertNotIn("MSCI 결정", " ".join(b["text"] for b in d1["countries"]["ID"]["bullets"]))
        self.assertEqual(d2["countries"]["ID"]["last_check"], "큰 변화 없음", d2["countries"]["ID"].get("reason"))

    def test_gap_day_keeps_the_weight_of_an_unrelated_line(self):
        # 점유율 자료 공백 날 경쟁사 제재 기사가 와도, 어제 점수로 뽑힌 마케팅 줄이 밀려나지 않는다
        self.files["hanwha/data/dart_subs.json"]["periods"][-1]["subs"]["VN"]["ni"] = 3
        write(self.root, self.files)
        first = self.run_at(TODAY, {})
        want = [b["rule"] for b in first["countries"]["VN"]["bullets"]]
        self.assertEqual(len(want), 4)
        self.assertIn("MKT", want)
        hub = copy.deepcopy(self.files["site/data/domestic/hub_news.json"])
        hub["hubs"]["미래에셋증권|베트남"].insert(0, {"date": (TODAY + timedelta(days=1)).isoformat(), "title": "미래에셋증권 베트남법인, 증권위 과징금 제재",
                                                 "src": "가상일보", "url": "u-hub-vn-fine"})
        d1, d2 = self.two_days(first, {"site/data/domestic/hub_news.json": hub}, gaps=("site/data/global/markets.json",))
        self.assertEqual([b["rule"] for b in d1["countries"]["VN"]["bullets"]], want, d1["countries"]["VN"].get("reason"))
        self.assertEqual(d2["countries"]["VN"]["last_check"], "큰 변화 없음", d2["countries"]["VN"].get("reason"))

    def test_outflow_forecast_after_a_decision_is_not_a_new_decision(self):
        # 강등 결정 뒤 '… could trigger outflows' 같은 전망 기사로 'MSCI 결정 전까지'가 되살아나지 않는다
        first = self.run_at(TODAY, {})
        items = self.files["site/data/global/macro_news.json"]["countries"]["ID"]["items"]
        res, seq = first, []
        for n, title in enumerate(("MSCI downgrades Indonesia to frontier market status", "Indonesian stocks plunge after MSCI downgrade",
                                   "MSCI's downgrade could trigger $2 billion of outflows from Indonesia")):
            seq.insert(0, {"date": (TODAY + timedelta(days=n + 1)).isoformat(), "title": title, "src": "Reuters", "url": f"u-s{n}", "priority": True})
            write(self.root, {"site/data/global/macro_news.json": {"countries": {"ID": {"items": seq + items}}}})
            res = self.run_at(TODAY + timedelta(days=n + 1), res)
            self.assertNotIn("MSCI 결정", " ".join(b["text"] for b in res["countries"]["ID"]["bullets"]), title)
        neg = lambda t, dt: {"title": t, "date": dt, "same": []}
        done = neg("MSCI downgrades Indonesia to frontier market status", "2026-10-28")
        for t in ("MSCI's downgrade could trigger $2 billion of outflows from Indonesia", "Indonesia faces $2 billion outflow as MSCI downgrade takes effect",
                  "MSCI 강등 후 인니 증시 외국인 이탈 우려 확산", "MSCI 강등 이후 인도네시아 증시 반등 가능성은"):
            self.assertFalse(bt.pending([], [neg(t, "2026-10-30"), done], "MSCI"), t)

    def test_hedged_relief_and_proposed_decision_headlines(self):
        # 해소를 바라거나 애쓰는 기사·전망·촉구는 우려 해소가 아니다
        for t in ("인니, MSCI 강등 우려 해소 위해 유동주식 비율 상향", "인니 정부, MSCI 강등 우려 해소 나서", "MSCI 강등 우려 해소 역부족",
                  "MSCI 강등 우려 해소 기대에 인니 증시 반등", "MSCI 강등 우려 해소될까", "OJK, MSCI 강등 리스크 해소 총력", "MSCI 강등 공포 진정 안 돼…인니 증시 연일 급락",
                  "Bank Indonesia keeps rates steady as EM selloff deepens on MSCI downgrade fears", "Foreign funds keep dumping Indonesian stocks as emerging market MSCI downgrade looms",
                  "Indonesia retains appeal as EM bets sour on MSCI downgrade risk", "Indonesia unveils free-float reforms to retain MSCI emerging market status",
                  "Indonesia set to retain MSCI emerging market status", "Indonesia likely to retain MSCI emerging market status", "Indonesia expects to keep MSCI emerging market status",
                  "Vietnam keeps rates steady as EM peers cut; FTSE upgrade in focus", "Indonesia hopes MSCI won't downgrade market after free-float reforms",
                  "Indonesian stocks rise as bets grow MSCI won't downgrade", "Analysts bet MSCI won't downgrade Indonesia", "Why MSCI probably won't downgrade Indonesia",
                  "MSCI shouldn't downgrade Indonesia, minister says", "Indonesia shouldn't be downgraded by MSCI, minister says",
                  "Indonesia confident it won't be downgraded by MSCI", "MSCI 강등 철회 촉구"):
            self.assertFalse(bt.relief(t), t)
            self.assertNotEqual(bt.news_label(t), "MSCI 강등 우려 해소", t)
        for t in ("MSCI Keeps Indonesia as Emerging Market", "MSCI decides not to downgrade Indonesia", "MSCI drops plan to cut Indonesia to frontier",
                  "MSCI 강등 우려 해소…인니 증시 급등", "MSCI keeps Indonesia in the EM index"):
            self.assertTrue(bt.relief(t), t)
            self.assertEqual(bt.news_label(t), "MSCI 강등 우려 해소", t)
        # 제안·의견수렴·가정('시·땐·되면')·'확정적'·'가닥'·계획은 결정이 아니다
        for t in ("MSCI, 인도네시아 프런티어 시장 강등 의견수렴 착수", "MSCI, 인니 프런티어 시장 강등 제안", "MSCI 인니 프런티어 강등 시 외국인 30조 이탈",
                  "MSCI 인니 프런티어 강등 땐 외국인 30조 이탈", "인니 MSCI 강등 확정되면 외국인 이탈", "MSCI 인니 강등 확정적", "MSCI, 강등 결정에 앞서 의견 수렴",
                  "MSCI 인니 강등 결정으로 가닥", "MSCI moves to downgrade Indonesia to frontier status", "MSCI drops plan to cut Indonesia to frontier",
                  "MSCI plans to cut Indonesia to frontier"):
            self.assertFalse(bt.confirmed(t), t)
            self.assertNotIn(bt.news_label(t), ("MSCI 강등 결정", "FTSE 강등 결정"), t)
        for t in ("MSCI demotes Indonesia to frontier market status", "Indonesia demoted to frontier market by MSCI", "MSCI confirms Indonesia downgrade",
                  "MSCI finalises Indonesia downgrade", "MSCI announces Indonesia downgrade to frontier", "Indonesia's MSCI downgrade becomes official"):
            self.assertTrue(bt.confirmed(t), t)
            self.assertEqual(bt.news_label(t), "MSCI 강등 결정", t)
        self.assertEqual(bt.news_label("FTSE Russell follows MSCI in downgrading Indonesia to frontier"), "FTSE 강등 결정")
        # 불확실성·전망 기사는 '여파'가 아니고, 발효 기사는 여파
        for t in ("Indonesian stocks drop on MSCI downgrade uncertainty", "Indonesia bonds sink on MSCI downgrade prospects",
                  "Indonesian stocks slide on MSCI downgrade anxiety", "Indonesia stocks fall on MSCI downgrade possibility"):
            self.assertEqual(bt.decided_by(t), "", t)
            self.assertNotIn("여파", bt.news_label(t), t)
        self.assertEqual(bt.decided_by("Indonesia faces $2 billion outflow as MSCI downgrade takes effect"), "MSCI")
        # 거래소의 공매도 금지·종목 거래정지·외교 수입금지는 감독 제재가 아니고, 개인·증권사 대상 금지는 제재
        for t in ("Indonesia's IDX extends short-selling ban as stocks slump", "IDX lifts short-selling ban", "OJK extends short selling ban until March",
                  "IDX extends short-selling ban to calm market after MSCI rout", "MAS to ban crypto incentives for retail investors",
                  "IDX Composite falls after US bans Indonesian shrimp imports", "Vietnam's HOSE suspends trading of securities of three firms",
                  "Vietnam's HOSE bans margin trading on 70 stocks"):
            self.assertFalse(bt.reg_hit(t), t)
        for t in ("MAS bans former trader from capital markets for 5 years", "OJK revokes licence of brokerage", "SSC suspends securities firm for three months"):
            self.assertTrue(bt.reg_hit(t), t)
        # 관찰대상 제외 라벨은 그 말을 한 기관 · 인니 재분류 검토는 악재(베트남 승격 재분류는 아님)
        self.assertEqual(bt.news_label("FTSE Russell keeps Indonesia off watch list despite MSCI downgrade warning"), "FTSE 관찰대상 제외 유지")
        for t in ("MSCI launches consultation on potential reclassification of Indonesia", "MSCI proposes to reclassify Indonesia as frontier market",
                  "MSCI postpones Indonesia reclassification decision"):
            self.assertEqual(bt.polarity(t), -1, t)
            self.assertEqual(bt.news_label(t), "MSCI 강등 검토", t)
        self.assertEqual(bt.polarity("Vietnam reclassification to secondary emerging confirmed by FTSE"), 1)

if __name__ == "__main__":
    unittest.main()
