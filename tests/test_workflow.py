"""해외지분투자 Workflow 탭: 단계 데이터 형식을 검증한다."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
W = json.loads((ROOT / "workflow" / "data" / "steps.json").read_text(encoding="utf-8"))


class WorkflowDataTest(unittest.TestCase):
    def test_steps_fit_the_diagram(self):
        ids = [s["id"] for s in W["steps"]]
        self.assertEqual(len(ids), len(set(ids)))
        for s in W["steps"]:
            self.assertIn(s["lane"], W["meta"]["lanes"], s["id"])
            self.assertTrue(1 <= s["phase"] <= len(W["meta"]["phases"]), s["id"])
            self.assertTrue(s["title"] and s["when"] and s["body"], s["id"])
            self.assertIsInstance(s["ok"], bool)

    def test_external_steps_have_deadline_and_source(self):
        for s in W["steps"]:
            if s["lane"] == "ext":
                self.assertTrue(s["due"], s["id"])
                self.assertTrue(s["src"], s["id"])
            for r in s["src"]:
                self.assertTrue(r["u"].startswith(("http", "../#")), r)
                self.assertTrue(r["d"], r)

    def test_covers_core_korean_filings(self):
        text = " ".join(s["title"] for s in W["steps"])
        for k in ["NDA", "실사", "이사회", "신고", "송금", "취득보고", "사업실적", "청산"]:
            self.assertIn(k, text)

    def test_open_flags_say_why(self):
        for s in W["steps"]:
            if not s["ok"]:
                self.assertTrue(s.get("why"), s["id"])  # 화면에 요확인 사유를 보여 준다
            if s.get("assert"):
                self.assertTrue(s["assert"]["law"] and s["assert"]["has"] and isinstance(s["assert"]["jo"], int), s["id"])

    def test_no_company_specific_terms(self):
        raw = json.dumps(W, ensure_ascii=False)
        for k in ["하나", "HFG", "지주"]:
            self.assertNotIn(k, raw)


US = json.loads((ROOT / "workflow" / "data" / "us_entry.json").read_text(encoding="utf-8"))


def _src_ids(x):
    """미국 진출 데이터 안의 모든 출처 id(src, *_src 목록)."""
    out = []
    if isinstance(x, dict):
        for k, v in x.items():
            if k == "src" or k.endswith("_src"):
                out += v
            else:
                out += _src_ids(v)
    elif isinstance(x, list):
        for v in x:
            out += _src_ids(v)
    return out


class UsAnnexTest(unittest.TestCase):
    """미국 진출: 출처 연결, 비교표·일정 형식, Workflow 단계 링크."""

    def test_every_reference_resolves_and_every_source_is_used(self):
        used = set(_src_ids({k: v for k, v in US.items() if k != "sources"}))
        self.assertEqual(used - set(US["sources"]), set())
        self.assertEqual(set(US["sources"]) - used, set())  # 쓰지 않는 출처를 목록에 남기지 않는다
        for s in US["sources"].values():
            self.assertTrue(s["u"].startswith("https://"), s)
            self.assertTrue(s["t"] and s["d"], s)

    def test_compare_table_marks_both_paths(self):
        keys = [r["k"] for r in US["compare"]]
        self.assertEqual(len(keys), len(set(keys)))
        for r in US["compare"]:
            if "both" in r:
                continue
            for side in ("est", "acq"):
                self.assertIn(r[side]["s"], "+-=", r["k"])
                self.assertTrue(r[side]["t"], r["k"])
        for side in ("est", "acq"):
            pc = US["pros_cons"][side]
            self.assertTrue(pc["pros"] and pc["cons"] and pc["fit"], side)

    def test_timelines_line_up_and_link_existing_steps(self):
        t = US["timeline"]
        self.assertEqual(len(t["est"]["phases"]), len(t["acq"]["phases"]))
        ids = {s["id"] for s in W["steps"]}
        wf = [it["wf"] for side in ("est", "acq") for p in t[side]["phases"] for it in p["items"] if it.get("wf")]
        wf += [x for r in US["compare"] for x in r.get("both", {}).get("wf", [])] + US["wf_steps"]
        self.assertTrue(wf)
        self.assertEqual(set(wf) - ids, set())

    def test_no_company_specific_terms(self):
        raw = json.dumps(US, ensure_ascii=False)
        for k in ["하나", "HFG", "지주", "요확인", "추정"]:
            self.assertFalse(k in raw, k)

    def test_semiannual_check_covers_annex_sources(self):
        import sys
        sys.path.insert(0, str(ROOT / "guide" / "scripts"))
        import check_sources  # noqa: E402
        rows, _ = check_sources.collect()
        self.assertEqual({s["u"] for s in rows["annex-us"]}, {s["u"] for s in US["sources"].values()})
        self.assertTrue(check_sources.is_official("https://www.nysenate.gov/legislation/laws/BSC/402"))


if __name__ == "__main__":
    unittest.main()
