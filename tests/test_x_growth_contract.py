import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from contentops.x_growth_contract import ContractError, map_draft_to_x_post


class XGrowthContractTests(unittest.TestCase):
    def setUp(self):
        self.draft = {
            "schema": "contentops.x-organic-growth/v1",
            "account_id": "x-superplay-english",
            "draft": "A measured claim, not an endorsement.",
            "source_url": "https://example.test/evidence",
            "review_status": "UNREVIEWED",
            "publication_status": "NOT_PUBLISHED",
        }

    def test_maps_draft_to_observed_x_post_fields_without_approving_or_publishing(self):
        result = map_draft_to_x_post(self.draft)
        self.assertEqual(result["schema"], "contentops.x-post/v1")
        self.assertEqual(result["account_slug"], "x-superplay-english")
        self.assertEqual(result["post_copy"], {"parts": [self.draft["draft"]]})
        self.assertEqual(result["status"], "draft")
        self.assertIsNone(result["status_url"])
        self.assertEqual(result["review_status"], "UNREVIEWED")
        self.assertEqual(result["provenance"]["source"], self.draft["source_url"])
        self.assertEqual(result["source_draft"], self.draft)

    def test_does_not_mutate_input(self):
        original = copy.deepcopy(self.draft)
        map_draft_to_x_post(self.draft)
        self.assertEqual(self.draft, original)

    def test_rejects_unknown_account(self):
        self.draft["account_id"] = "invented-account"
        with self.assertRaises(ContractError):
            map_draft_to_x_post(self.draft)

    def test_rejects_missing_required_fields(self):
        for key in ("account_id", "draft", "source_url"):
            with self.subTest(key=key):
                value = dict(self.draft)
                del value[key]
                with self.assertRaises(ContractError):
                    map_draft_to_x_post(value)

    def test_rejects_attempt_to_claim_review_or_publication(self):
        for field, value in (("review_status", "APPROVED"),
                             ("publication_status", "PUBLISHED")):
            with self.subTest(field=field):
                draft = dict(self.draft, **{field: value})
                with self.assertRaises(ContractError):
                    map_draft_to_x_post(draft)

    def test_rejects_unknown_fields_instead_of_silently_losing_data(self):
        self.draft["status_url"] = "https://x.com/me/status/123"
        with self.assertRaises(ContractError):
            map_draft_to_x_post(self.draft)

    def test_rejects_credentials_in_source_url(self):
        self.draft["source_url"] = "https://user:pass@example.test/evidence"
        with self.assertRaises(ContractError):
            map_draft_to_x_post(self.draft)

    def test_rejects_blank_draft_and_invalid_source(self):
        for field, value in (("draft", "  "), ("source_url", "not-a-url")):
            with self.subTest(field=field):
                draft = dict(self.draft, **{field: value})
                with self.assertRaises(ContractError):
                    map_draft_to_x_post(draft)


if __name__ == "__main__":
    unittest.main()
