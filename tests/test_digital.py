"""디지털자산 규제 탭: 데이터 형식과 수집 파서를 네트워크 없이 검증한다."""
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "digital" / "scripts"))

import build_summary  # noqa: E402
import detect_updates  # noqa: E402
import fetch_feed  # noqa: E402

REG = json.loads((ROOT / "digital" / "data" / "regulation.json").read_text(encoding="utf-8"))
SEVEN = ["KR", "US", "JP", "VN", "SG", "ID", "AE"]


class RegulationDataTest(unittest.TestCase):
    def test_seven_markets_with_all_topics(self):
        codes = {m["code"]: m for m in REG["markets"]}
        topics = [t["k"] for t in REG["topics"]]
        for code in SEVEN:
            self.assertIn(code, codes)
            self.assertFalse(codes[code]["reference_only"], code)
            self.assertEqual(sorted(codes[code]["status"]), sorted(topics), code)

    def test_every_status_has_source_and_known_level(self):
        for m in REG["markets"]:
            datetime.strptime(m["checked"], "%Y-%m-%d")
            for k, s in m["status"].items():
                self.assertIn(s["lv"], REG["meta"]["legend"], (m["code"], k))
                self.assertTrue(s["url"].startswith("https://"), (m["code"], k))

    def test_dated_items_have_sources(self):
        for u in REG["upcoming"]:
            datetime.strptime(u["date"], "%Y-%m-%d")
            self.assertTrue(u["url"].startswith("https://"), u)
        for m in REG["markets"]:
            for i in m["issues"]:
                self.assertTrue(all(p["url"].startswith("https://") for p in i["points"]), i["title"])

    def test_summary_card_format(self):
        out = build_summary.build(REG, "2026-10-20")
        self.assertLessEqual(len(out["items"]), 8)
        self.assertTrue(out["items"])
        for it in out["items"]:
            self.assertEqual(set(it), {"jurisdiction", "flag", "title", "status", "date", "url"})
            self.assertGreaterEqual(it["date"][:7], "2026-10")


class FeedParserTest(unittest.TestCase):
    RSS = b"""<?xml version="1.0"?><rss><channel>
      <item><title>MAS publishes stablecoin bill - Reuters</title><link>https://example.com/a</link>
        <pubDate>Mon, 19 Oct 2026 03:00:00 GMT</pubDate><source url="https://reuters.com">Reuters</source></item>
      <item><title>Singapore weather update - CNA</title><link>https://example.com/b</link>
        <pubDate>Mon, 19 Oct 2026 03:00:00 GMT</pubDate><source url="https://cna.asia">CNA</source></item>
      <item><title>Old crypto story - X</title><link>https://example.com/c</link>
        <pubDate>Mon, 01 Jun 2026 03:00:00 GMT</pubDate><source url="https://x.com">X</source></item>
    </channel></rss>"""

    def test_keeps_recent_relevant_items_and_strips_source(self):
        now = datetime(2026, 10, 20, tzinfo=timezone.utc)
        items = fetch_feed.parse_rss(self.RSS, "SG", now)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "MAS publishes stablecoin bill")
        self.assertEqual(items[0]["src"], "Reuters")
        self.assertEqual(items[0]["date"], "2026-10-19")

    def test_dedupe_prefers_official(self):
        a = {"date": "2026-10-19", "title": "Same title", "official": True}
        b = {"date": "2026-10-19", "title": "same TITLE"}
        self.assertEqual(fetch_feed.dedupe([b, a]), [a])


if __name__ == "__main__":
    unittest.main()


class DetectUpdatesTest(unittest.TestCase):
    RSS = b"""<?xml version="1.0"?><rss><channel>
      <item><title>MAS consults on stablecoin licensing rules - Monetary Authority of Singapore</title><link>https://example.com/1</link>
        <pubDate>Mon, 19 Oct 2026 03:00:00 GMT</pubDate><source url="https://www.mas.gov.sg">Monetary Authority of Singapore</source></item>
      <item><title>Crypto exchange stablecoin news - Some Blog</title><link>https://example.com/2</link>
        <pubDate>Mon, 19 Oct 2026 03:00:00 GMT</pubDate><source url="https://blog.example.com">Some Blog</source></item>
      <item><title>MAS annual report - Monetary Authority of Singapore</title><link>https://example.com/3</link>
        <pubDate>Mon, 19 Oct 2026 03:00:00 GMT</pubDate><source url="https://www.mas.gov.sg">Monetary Authority of Singapore</source></item>
    </channel></rss>"""

    def test_keeps_only_official_digital_items_with_topics(self):
        now = datetime(2026, 10, 21, tzinfo=timezone.utc)
        items = detect_updates.parse_official(self.RSS, "SG", now)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "MAS consults on stablecoin licensing rules")
        self.assertIn("stable", items[0]["topics"])
        self.assertIn("vasp", items[0]["topics"])

    def test_official_domain_match_is_strict(self):
        self.assertTrue(detect_updates.is_official("KR", "https://www.fsc.go.kr/no010101"))
        self.assertFalse(detect_updates.is_official("KR", "https://fsc.go.kr.example.com"))

    def test_short_keywords_need_word_boundary(self):
        self.assertEqual(detect_updates.classify("FSC stock market update"), [])
        self.assertIn("etf", detect_updates.classify("SEC approves crypto ETF rule"))

    def test_merge_dedupes_and_drops_old(self):
        now = datetime(2026, 10, 21, tzinfo=timezone.utc)
        old = {"date": "2026-01-01", "title": "old", "topics": ["general"]}
        a = {"date": "2026-10-20", "title": "Same", "topics": ["stable"]}
        out = detect_updates.merge([old, dict(a)], [a], now)
        self.assertEqual(out, [a])
