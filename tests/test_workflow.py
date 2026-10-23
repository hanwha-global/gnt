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


if __name__ == "__main__":
    unittest.main()
