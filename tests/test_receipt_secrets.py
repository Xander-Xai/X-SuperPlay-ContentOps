from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import check_receipt_secrets as checker  # noqa: E402


def _receipt(root: Path, name: str, payload: dict) -> Path:
    path = root / "projects" / "demo" / "receipts" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class ReceiptSecretTests(unittest.TestCase):
    def test_raw_provider_ids_balances_and_fingerprints_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = _receipt(root, "a.json", {
                "voice_id": "founder_v1_live",
                "task_id": "task-123456",
                "trace_id": "0712345678",
                "file_id": "file-123456",
                "payg_key_fingerprint": "2ac10c6e9029",
                "money": {"cash_balance": "0.00", "voucher_balance": 15.0},
            })
            found = checker.scan(root, paths=[path])
            kinds = {kind for _, _, kind in found}
            self.assertEqual(kinds, {"provider_id", "key_fingerprint", "balance"})
            self.assertEqual(len(found), 7, found)

    def test_hashes_and_redacted_values_are_not_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = _receipt(root, "b.json", {
                "voice_id": "a" * 64,
                "voice_id_hash": "b" * 64,
                "task_id": "<redacted>",
                "trace_id": None,
                "payg_key_fingerprint": "REDACTED",
                "cash_balance": "not-a-number",
            })
            self.assertEqual(checker.scan(root, paths=[path]), [])

    def test_a_key_like_value_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = _receipt(root, "c.json", {"note": "sk-" + "a" * 24})
            found = checker.scan(root, paths=[path])
            self.assertIn((path.relative_to(root).as_posix(), "<text>", "credential_value"),
                          found)

    def test_a_new_field_fails_against_a_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = _receipt(root, "d.json", {"voice_id": "v1"})
            baseline = root / "baseline.json"
            baseline.write_text(json.dumps({"schema": checker.SCHEMA, "files": {}}),
                                encoding="utf-8")
            result = checker.check(root, baseline=baseline, paths=[path])
            self.assertFalse(result["ok"])
            self.assertEqual(result["new"][0]["kind"], "provider_id")

    def test_a_baselined_field_passes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = _receipt(root, "e.json", {"voice_id": "v1"})
            violations = checker.scan(root, paths=[path])
            baseline = root / "baseline.json"
            baseline.write_text(json.dumps(checker._baseline_payload(violations)),
                                encoding="utf-8")
            result = checker.check(root, baseline=baseline, paths=[path])
            self.assertTrue(result["ok"], result)

    def test_the_committed_baseline_has_no_values(self) -> None:
        text = checker.DEFAULT_BASELINE.read_text(encoding="utf-8")
        self.assertNotIn("founder_v1", text)
        self.assertNotIn("2ac10c6e9029", text)
        data = json.loads(text)
        self.assertEqual(data["schema"], checker.SCHEMA)


if __name__ == "__main__":
    unittest.main()
