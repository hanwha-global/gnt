"""국가별 해외진출 유의사항 탭: 데이터 형식과 감지 파서를 네트워크 없이 검증한다."""
import json
import sys
import unittest
from datetime import datetime, timezone
from unittest import mock
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

    def test_finra_rule_compares_amendment_history_only(self):
        u = "https://www.finra.org/rules-guidance/rulebooks/finra-rules/1017"
        body = ("<h1>1017. Application for Approval of Change in Ownership, Control, or Business Operations</h1>"
                "<p>(c)(1) A member shall file an application for approval of a change in ownership or control at least 30 days prior to such change.</p>"
                "<p>Amended by SR-FINRA-2020-011 eff. Sept. 1, 2021.</p><p>Amended by SR-FINRA-2013-015 eff. Feb. 5. 2013.</p>"
                "<p>Amended by SR-FINRA-2012-018 and SR-FINRA-2012-036 eff. Aug. 27, 2012.</p><p>Adopted by SR-NASD-97-28 eff. Aug. 7, 1997.</p>")
        a = check_sources.signature(u, f"<div class='promo'>Annual Conference 2026</div>{body}".encode())
        b = check_sources.signature(u, f"<div class='promo'>FINRA Forward update</div>{body}".encode())
        self.assertEqual(a, b)  # 쪽 꾸밈만 바뀌면 같은 값(이슈 #20 오탐)
        for line in ("Amended by SR-FINRA-2026-001 eff. Jan. 4, 2027.", "Renumbered and amended by SR-FINRA-2026-002 eff. Feb. 1, 2027.",
                     "Deleted by SR-FINRA-2026-003 eff. March 2, 2027."):
            new = body.replace("<p>Adopted", f"<p>{line}</p><p>Adopted")
            self.assertNotEqual(a, check_sources.signature(u, new.encode()), line)  # 개정 줄이 늘면 감지
        with self.assertRaises(RuntimeError):  # 개정 이력이 없는 화면(봇 확인 등)은 해시하지 않는다
            check_sources.signature(u, b"<p>Please wait</p>")
        with self.assertRaises(RuntimeError):
            check_sources.signature("https://www.fca.org.uk/firms/authorisation", b"<title>Just a moment...</title><p>Checking</p>")

    def test_sfc_compares_posted_update_date(self):
        u = "https://www.sfc.hk/en/Regulatory-functions/Intermediaries/Licensing"
        a = check_sources.signature(u, b"<div class='menu'>Strategic Priorities 2024-2026</div><p>Licensing</p><p>Last update: <span>22 Jan 2020</span></p>")
        b = check_sources.signature(u, b"<div class='menu'>New menu item</div><p>Licensing</p><p>Last update: <span>22 Jan 2020</span></p>")
        self.assertEqual((a, b), ("date:22 Jan 2020", "date:22 Jan 2020"))
        m = check_sources.signature("https://sfc.hk/en/x/Types", b'<head><meta name="meta-date" content="2025-12-30"></head><p>RO</p>')
        self.assertEqual(m, "date:2025-12-30")
        self.assertFalse(check_sources.signature(u, b"<p>no date</p>").startswith("date:"))  # 갱신일이 없으면 본문 해시
        tok = b'<meta name="msvalidate.01" content="2019-01-01ABCD"><p>x</p>'
        self.assertFalse(check_sources.signature(u, tok).startswith("date:"))  # 이름에 date가 섞인 검증 토큰은 날짜가 아님
        both = b'<meta name="DC.date.created" content="2019-03-01"><meta property="article:modified_time" content="2025-12-30T09:00:00+08:00">'
        self.assertEqual(check_sources.posted_date(both.decode()), "2019-03-01|2025-12-30")  # 시각은 버리고 날짜만, 둘 다 비교

    def test_ecfr_compares_official_api_versions(self):
        self.assertEqual(check_sources.ecfr_api("https://www.ecfr.gov/current/title-17/section-240.15c3-1"),
                         "https://www.ecfr.gov/api/versioner/v1/versions/title-17.json?section=240.15c3-1")
        self.assertEqual(check_sources.ecfr_api("https://www.ecfr.gov/current/title-31/subtitle-B/chapter-VIII/part-800"),
                         "https://www.ecfr.gov/api/versioner/v1/versions/title-31.json?part=800")
        self.assertIsNone(check_sources.ecfr_api("https://www.sec.gov/answers/brkrdlr.htm"))
        v = {"content_versions": [{"amendment_date": "2016-12-31", "identifier": "240.15c3-1", "removed": False},
                                  {"amendment_date": "2025-03-14", "identifier": "240.15c3-1", "removed": False}]}
        a = check_sources.ecfr_signature(json.dumps(v).encode())
        v["content_versions"].append({"amendment_date": "2027-01-04", "identifier": "240.15c3-1", "removed": False})
        self.assertNotEqual(a, check_sources.ecfr_signature(json.dumps(v).encode()))
        seen = []
        with mock.patch.object(check_sources, "polite_get", lambda x: seen.append(x) or json.dumps(v).encode()):
            check_sources.fingerprint("https://www.ecfr.gov/current/title-17/section-240.17a-11")
        self.assertEqual(seen, ["https://www.ecfr.gov/api/versioner/v1/versions/title-17.json?section=240.17a-11"])
        # 본문 쪽이 주는 접근 제한 화면은 원문으로 해시하지 않는다(5개 조문이 같은 값으로 '변경 없음'처럼 보이던 문제)
        with self.assertRaises(RuntimeError):
            check_sources.signature("https://www.federalregister.gov/x/y", b"<p>Due to aggressive automated scraping of FederalRegister.gov and eCFR.gov, programmatic access to these sites is limited</p>")

    def test_push_run_only_sets_new_baselines(self):
        st, _ = self._run({}, {})
        u = next(s["u"] for c in G["countries"] if c["code"] == "SG" for s in c["sources"] if "mas.gov.sg" in s["u"])
        new = "https://www.ecfr.gov/current/title-17/section-240.15c3-1"
        old = dict(st["sources"][u])
        del st["sources"][new]  # 새로 인용한 출처처럼
        calls = []
        st, newly = check_sources.run(st, "2027-01-09", "x", fetch=lambda x: "different", alive=lambda x: True,
                                      search=lambda oc, law: calls.append("law"),
                                      asserter=lambda a, oc, lm: calls.append("assert"), baseline_only=True)
        self.assertEqual((newly, calls), ([], []))  # 비교·법령 API·조문 대조 없음
        self.assertEqual(st["sources"][u], old)  # 기준값이 있는 출처는 열지 않음
        self.assertEqual((st["sources"][new]["checked"], st["sources"][new]["sig"]), ("2027-01-09", "different"))
        self.assertEqual(st["updated"], "2027-01-02")  # 원문 점검일은 비교한 날 그대로
        link = next(x for x, q in st["sources"].items() if q["kind"] == "링크" and "pwc.com" in x)
        with mock.patch.object(check_sources, "OFFICIAL_HOSTS", check_sources.OFFICIAL_HOSTS + ["pwc.com"]):
            st, _ = check_sources.run(st, "2027-01-10", "", fetch=lambda x: "first", alive=lambda x: True,
                                      search=lambda oc, law: None, asserter=lambda a, oc, lm: None, baseline_only=True)
        self.assertEqual((st["sources"][link]["kind"], st["sources"][link].get("sig")), ("원문", "first"))

    def _net(self, fake_get):
        clock = [1000.0]
        sleeps = []
        def sleep(s):
            sleeps.append(s)
            clock[0] += s
        ctx = [mock.patch.object(check_sources, "get", fake_get), mock.patch.object(check_sources, "_last", {}),
               mock.patch.object(check_sources, "_throttled", set()),
               mock.patch.object(check_sources.time, "sleep", sleep), mock.patch.object(check_sources.time, "monotonic", lambda: clock[0])]
        for c in ctx:
            c.start()
            self.addCleanup(c.stop)
        return sleeps

    def test_rate_limited_site_waits_and_retries(self):
        calls = []
        def fake_get(u, headers=None, retries=3, timeout=30):
            calls.append(u)
            if len(calls) == 1:
                raise RuntimeError("HTTP 429: <!DOCTYPE html><title>Just a moment...</title>")
            return b"ok"
        sleeps = self._net(fake_get)
        self.assertEqual(check_sources.polite_get("https://www.finra.org/rules-guidance/rulebooks/finra-rules/1013"), b"ok")
        self.assertEqual(check_sources.polite_get("https://www.finra.org/rules-guidance/rulebooks/finra-rules/1014"), b"ok")
        self.assertEqual(sleeps, [45, 6.0, 6.0])  # 429 뒤 45초 쉬고 다시, 같은 사이트는 6초 간격

    def test_site_that_keeps_throttling_is_skipped(self):
        calls = []
        def fake_get(u, headers=None, retries=3, timeout=30):
            calls.append(u)
            raise RuntimeError("HTTP 429: busy")
        self._net(fake_get)
        for u in ("https://www.finra.org/rules-guidance/rulebooks/finra-rules/1210", "https://brokercheck.finra.org/"):
            with self.assertRaises(RuntimeError):
                check_sources.polite_get(u)
        self.assertEqual(len(calls), 2)  # 두 번 막힌 사이트의 다음 주소는 열지 않는다

    def test_retry_count_with_real_http_helper(self):
        import io
        import urllib.error
        hits = []
        def urlopen(req, timeout=None):
            hits.append(req.full_url)
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, io.BytesIO(b"<title>Just a moment...</title>"))
        sleeps = self._net(check_sources.get)
        with mock.patch("urllib.request.urlopen", urlopen):
            with self.assertRaises(RuntimeError):
                check_sources.polite_get("https://www.finra.org/rules-guidance/rulebooks/finra-rules/4311")
        self.assertEqual((len(hits), sleeps), (2, [45, 6.0]))  # net.get 의 2초 재시도 없이 2번
        hits.clear()
        sleeps.clear()
        flaky = iter([TimeoutError("timed out")])
        def urlopen2(req, timeout=None):
            hits.append(req.full_url)
            e = next(flaky, None)
            if e:
                raise e
            return io.BytesIO(b"ok")
        with mock.patch("urllib.request.urlopen", urlopen2):
            self.assertEqual(check_sources.polite_get("https://www.fca.org.uk/firms/authorisation"), b"ok")
        self.assertEqual((len(hits), sleeps), (2, [1.0]))  # 일시 오류는 45초 없이 간격(1초)만 두고 한 번 더

    def test_sec_pages_send_contact_user_agent(self):
        seen = {}
        def fake_get(u, headers=None, retries=3, timeout=30):
            seen[u] = headers
            return b"x"
        self._net(fake_get)
        check_sources.polite_get("https://www.sec.gov/answers/brkrdlr.htm")
        check_sources.polite_get("https://www.finra.org/registration-exams-ce/qualification-exams")
        self.assertEqual(seen["https://www.sec.gov/answers/brkrdlr.htm"], {"User-Agent": check_sources.SEC_UA})
        self.assertIsNone(seen["https://www.finra.org/registration-exams-ce/qualification-exams"])

    def test_assert_clears_flag_and_article_cut(self):
        st, _ = self._run({}, {}, asserter=lambda a, oc, lm: {"ok": True, "via": "test"})
        self.assertTrue(st["rows"]["s14"]["assert"]["ok"])
        blob = "제417조(승인) 7일 ... 제418조(보고사항) 금융투자업자는 사유 발생일부터 7일 이내 보고 제419조(검사) 30일"
        part = check_sources.article_text(blob, 418)
        self.assertIn("7일", part)
        self.assertNotIn("30일", part)


if __name__ == "__main__":
    unittest.main()
