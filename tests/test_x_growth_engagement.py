from __future__ import annotations
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from contentops.x_growth_engagement import brief  # noqa: E402


class EngagementTests(unittest.TestCase):
    def test_brief_uses_provided_context_and_two_distinct_angles(self):
        candidate = {"text": "How can teams verify agent permissions?", "audience": "agent builders", "evidence": [{"url": "https://example.com/policy", "quote": "Grants bind operations."}]}
        result = brief(candidate)
        self.assertEqual(result["source_excerpt"], candidate["text"])
        self.assertEqual(len(result["writing_angles"]), 2)
        self.assertNotEqual(result["writing_angles"][0]["purpose"], result["writing_angles"][1]["purpose"])
        self.assertEqual(result["evidence"][0]["verification"], "USER_SUPPLIED_UNVERIFIED")
        self.assertEqual(result["draft_generation"], "AGENT_REQUIRED")

    def test_missing_context_does_not_invent_a_post(self):
        self.assertEqual(brief({})["status"], "DATA_UNAVAILABLE")

    def test_duplicate_and_unrelated_drafts_are_flagged(self):
        candidate = {"text": "agent permissions and grants", "audience": "agent builders", "drafts": ["Nice post!", "Nice post!"]}
        result = brief(candidate)
        self.assertIn("DUPLICATE_OR_TEMPLATE", result["warnings"])
        self.assertIn("POSSIBLY_UNRELATED", result["warnings"])


if __name__ == "__main__":
    unittest.main()
