"""국가별 해외진출 유의사항 탭: 데이터 형식과 감지 파서를 네트워크 없이 검증한다."""
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "guide" / "scripts"))

import check_sources  # noqa: E402
import detect_entry_rules  # noqa: E402

G = json.loads((ROOT / "guide" / "data" / "countries.json").read_text(encoding="utf-8"))
FIELDS = ["own", "lic", "cap", "local", "fx"]


class GuideDataTest(unittest.TestCase):
    def test_dashboard_markets_present(self):
        codes = {c["code"] for c in G["countries"]}
        for code in ["US", "JP", "VN", "SG", "ID", "AE", "HK", "CN", "GB", "IN"]:
            self.assertIn(code, codes)

    def test_every_field_has_source_and_date(self):
        for c in G["countries"]:
            datetime.strptime(c["checked"], "%Y-%m-%d")
            self.assertIn(c["lv"], G["meta"]["legend"], c["code"])
            self.assertTrue(c["sources"], c["code"])
            for s in c["sources"]:
                self.assertTrue(s["u"].startswith("http"), s)
                self.assertTrue(s["d"], s)
            for f in [c[k] for k in FIELDS] + c["quirks"]:
                self.assertTrue(f["v"], c["code"])
                self.assertIsInstance(f["ok"], bool)
                self.assertTrue(f["src"], c["code"])
                for i in f["src"]:
                    self.assertLess(i, len(c["sources"]), c["code"])

    def test_every_country_is_watched(self):
        for c in G["countries"]:
            self.assertIn(c["code"], detect_entry_rules.OFFICIAL, c["code"])

    def test_open_flags_say_why(self):
        for c in G["countries"]:
            for f in [c[k] for k in FIELDS] + c["quirks"]:
                if not f["ok"]:
                    self.assertTrue(f.get("why"), c["code"])  # 화면에 요확인 사유를 보여 준다

    def test_korea_side_lives_in_workflow_tab(self):
        self.assertNotIn("korea", G)  # 한국 측 절차는 workflow/ 가 원본(중복 금지)


class DetectTest(unittest.TestCase):
    RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>OJK issues rule on foreign ownership of securities companies - OJK</title><link>https://news.google.com/a</link>
<pubDate>Mon, 19 Oct 2026 03:00:00 GMT</pubDate><source url="https://www.ojk.go.id">OJK</source></item>
<item><title>OJK foreign ownership news - Some Blog</title><link>https://news.google.com/b</link>
<pubDate>Mon, 19 Oct 2026 03:00:00 GMT</pubDate><source url="https://blog.example.com">Some Blog</source></item>
<item><title>OJK holds sports day - OJK</title><link>https://news.google.com/c</link>
<pubDate>Mon, 19 Oct 2026 03:00:00 GMT</pubDate><source url="https://ojk.go.id">OJK</source></item>
</channel></rss>"""

    def test_keeps_only_official_and_relevant(self):
        now = datetime(2026, 10, 21, tzinfo=timezone.utc)
        out = detect_entry_rules.parse(self.RSS, "ID", now)
        self.assertEqual([x["title"] for x in out], ["OJK issues rule on foreign ownership of securities companies"])
        self.assertEqual(out[0]["date"], "2026-10-19")

    def test_merge_dedupes(self):
        now = datetime(2026, 10, 21, tzinfo=timezone.utc)
        a = {"date": "2026-10-19", "title": "X", "url": "u", "src": "s"}
        self.assertEqual(len(detect_entry_rules.merge([a], [dict(a)], now)), 1)


class SourceCheckTest(unittest.TestCase):
    """반기 원문 점검: 네트워크 대신 가짜 응답으로 변경 감지·점검일 갱신·조문 대조를 본다."""

    def _run(self, prev, sigs, oc="", laws=None, asserter=None):
        return check_sources.run(
            prev, "2027-01-02", oc,
            fetch=lambda u: sigs.get(u, "same"),
            alive=lambda u: True,
            search=lambda oc, law: (laws or {}).get(law["name"]),
            asserter=asserter or (lambda a, oc, lm: None),
        )

    def test_first_run_sets_baseline_without_changes(self):
        st, newly = self._run({}, {})
        self.assertEqual(newly, [])
        self.assertEqual(st["rows"]["SG"]["checked"], "2027-01-02")
        self.assertNotIn("changed", st["rows"]["SG"])

    def test_changed_official_source_marks_row(self):
        u = next(s["u"] for c in G["countries"] if c["code"] == "SG" for s in c["sources"] if "mas.gov.sg" in s["u"])
        st, _ = self._run({}, {})
        st, newly = self._run(st, {u: "different"})
        self.assertEqual(len(newly), 1)
        self.assertEqual(st["rows"]["SG"]["changed"][0]["u"], u)
        self.assertIn("검토", check_sources.issue_body(newly, "2027-01-02"))

    def test_volatile_page_is_not_reported(self):
        u = next(s["u"] for c in G["countries"] if c["code"] == "SG" for s in c["sources"] if "mas.gov.sg" in s["u"])
        st, _ = self._run({}, {})
        n = iter(range(10 ** 6))
        st, newly = check_sources.run(st, "2027-01-03", "", fetch=lambda x: str(next(n)) if x == u else "same",
                                      alive=lambda x: True, search=lambda oc, law: None, asserter=lambda a, oc, lm: None)
        self.assertEqual(newly, [])
        self.assertEqual(st["sources"][u]["kind"], "가변")

    def test_normalize_drops_times_and_tokens(self):
        a = check_sources.normalize(b"<p>Base capital S$5,000 updated 10:42 token 9f86d081884c7d659a2feaa0c55ad015</p>")
        b = check_sources.normalize(b"<p>Base capital S$5,000 updated 11:07 token 2c26b46b68ffc68ff99b453c1d304134</p>")
        self.assertEqual(a, b)
        self.assertIn("5,000", a)

    def test_regulator_home_pages_are_link_only(self):
        self.assertFalse(check_sources.is_official("http://www.csrc.gov.cn/csrc_en/"))
        self.assertFalse(check_sources.is_official("https://www.sebi.gov.in/"))
        self.assertTrue(check_sources.is_official("https://www.handbook.fca.org.uk/handbook/MIFIDPRU/4/4.html"))

    def test_secondary_links_are_not_hashed(self):
        st, _ = self._run({}, {})
        kinds = {p["kind"] for u, p in st["sources"].items() if "pwc.com" in u}
        self.assertEqual(kinds, {"링크"})

    def test_korean_law_effective_date_change(self):
        law = {"자본시장과 금융투자업에 관한 법률": {"id": "1", "promulgated": "20260101", "effective": "20260701"}}
        st, _ = self._run({}, {}, oc="x", laws=law)
        law2 = {"자본시장과 금융투자업에 관한 법률": {"id": "2", "promulgated": "20261201", "effective": "20270601"}}
        st, newly = self._run(st, {}, oc="x", laws=law2)
        self.assertTrue(any(n[1] == "자본시장과 금융투자업에 관한 법률" for n in newly))
        self.assertIn("changed", st["rows"]["s14"])

    def test_assert_clears_flag_and_article_cut(self):
        st, _ = self._run({}, {}, asserter=lambda a, oc, lm: {"ok": True, "via": "test"})
        self.assertTrue(st["rows"]["s14"]["assert"]["ok"])
        blob = "제417조(승인) 7일 ... 제418조(보고사항) 금융투자업자는 사유 발생일부터 7일 이내 보고 제419조(검사) 30일"
        part = check_sources.article_text(blob, 418)
        self.assertIn("7일", part)
        self.assertNotIn("30일", part)


if __name__ == "__main__":
    unittest.main()
