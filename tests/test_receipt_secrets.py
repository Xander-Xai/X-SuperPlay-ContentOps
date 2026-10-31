from __future__ import annotations

import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import check_receipt_secrets as checker  # noqa: E402
from process_utils import hidden_run  # noqa: E402

BASELINE_REL = "reports/audits/receipt-exposure-baseline.json"


def _git(root: Path, *args: str) -> None:
    result = hidden_run(["git", *args], cwd=str(root), text=True, timeout=60)
    if result.returncode != 0:
        raise AssertionError(result.stderr)


def _commit(root: Path) -> None:
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=test", "-c", "user.email=test@example.com",
         "commit", "-m", "base")


def _receipt(root: Path, name: str, payload: dict) -> Path:
    path = root / "projects" / "demo" / "receipts" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _repo(root: Path, payload: dict) -> tuple[Path, Path]:
    _git(root, "init")
    path = _receipt(root, "a.json", payload)
    baseline = root / BASELINE_REL
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text(json.dumps(
        checker._baseline_payload(root, paths=[path]), ensure_ascii=False), encoding="utf-8")
    _commit(root)
    return path, baseline


class ReceiptSecretScanTests(unittest.TestCase):
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


class ReceiptSecretDiffTests(unittest.TestCase):
    def test_invalid_explicit_base_does_not_fall_back(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path, baseline = _repo(root, {"voice_id": "v1"})
            _git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
            with self.assertRaises(checker.CheckError):
                checker.check(root, baseline, paths=[path], base="missing-base-ref")

    def test_invalid_environment_base_does_not_fall_back(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path, baseline = _repo(root, {"voice_id": "v1"})
            _git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
            with patch.dict("os.environ", {"CONTENTOPS_RECEIPT_BASE": "missing-base-ref"}):
                with self.assertRaisesRegex(checker.CheckError, "BASE_REQUIRED"):
                    checker.check(root, baseline, paths=[path])
                self.assertTrue(checker.check(root, baseline, paths=[path], base="HEAD")["ok"])

    def test_empty_explicit_base_and_non_commit_ref_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _repo(root, {"voice_id": "v1"})
            _git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
            for ref in ("", "HEAD^{tree}", "HEAD^"):
                with self.subTest(ref=ref), self.assertRaisesRegex(checker.CheckError, "BASE_REQUIRED"):
                    checker._resolve_base(root, ref)

    def test_changed_sensitive_fields_fail_independently(self) -> None:
        for field, before, after in (("voice_id", "v1", "v2"),
                                     ("cash_balance", "0.00", "9.99"),
                                     ("payg_key_fingerprint", "2ac10c6e9029", "ffffffffffff")):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                path, baseline = _repo(root, {field: before})
                _receipt(root, "a.json", {field: after})
                result = checker.check(root, baseline, paths=[path], base="HEAD")
                self.assertTrue(any(item["field"] == field and item["reason"] == "changed_value"
                                    for item in result["new"]))

    def test_same_value_at_a_baselined_path_passes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path, baseline = _repo(root, {"voice_id": "v1", "money": {"cash_balance": "0.00"}})
            result = checker.check(root, baseline, paths=[path], base="HEAD")
            self.assertTrue(result["ok"], result)

    def test_changed_value_at_a_baselined_path_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path, baseline = _repo(root, {"voice_id": "v1", "money": {"cash_balance": "0.00"}})
            _receipt(root, "a.json", {"voice_id": "v2", "money": {"cash_balance": "9.99"}})
            result = checker.check(root, baseline, paths=[path], base="HEAD")
            self.assertFalse(result["ok"])
            reasons = {item["reason"] for item in result["new"]}
            self.assertIn("changed_value", reasons)

    def test_changed_fingerprint_at_a_baselined_path_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path, baseline = _repo(root, {"payg_key_fingerprint": "2ac10c6e9029"})
            _receipt(root, "a.json", {"payg_key_fingerprint": "ffffffffffff"})
            result = checker.check(root, baseline, paths=[path], base="HEAD")
            self.assertFalse(result["ok"])
            self.assertTrue(any(item["kind"] == "key_fingerprint" for item in result["new"]))

    def test_a_new_field_path_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path, baseline = _repo(root, {"voice_id": "v1"})
            _receipt(root, "a.json", {"voice_id": "v1", "trace_id": "new-trace"})
            result = checker.check(root, baseline, paths=[path], base="HEAD")
            self.assertFalse(result["ok"])
            self.assertTrue(any(item["reason"] == "new_path" for item in result["new"]))

    def test_changed_key_like_text_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path, baseline = _repo(root, {"note": "sk-" + "a" * 24})
            _receipt(root, "a.json", {"note": "sk-" + "b" * 24})
            result = checker.check(root, baseline, paths=[path], base="HEAD")
            self.assertFalse(result["ok"])
            self.assertTrue(any(item["kind"] == "credential_value" for item in result["new"]))

    def test_baseline_growth_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path, baseline = _repo(root, {"voice_id": "v1"})
            payload = json.loads(baseline.read_text(encoding="utf-8"))
            payload["files"]["projects/demo/receipts/new.json"] = ["voice_id::provider_id"]
            baseline.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            result = checker.check(root, baseline, paths=[path], base="HEAD")
            self.assertFalse(result["ok"])
            self.assertTrue(result["growth"])

    def test_malformed_json_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path, baseline = _repo(root, {"voice_id": "v1"})
            path.write_text('{"voice_id": ', encoding="utf-8")
            result = checker.check(root, baseline, paths=[path], base="HEAD")
            self.assertFalse(result["ok"])
            self.assertTrue(any(item["kind"] == "malformed_json" for item in result["new"]))

    def test_a_legacy_v1_baseline_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path, baseline = _repo(root, {"voice_id": "v1"})
            payload = json.loads(baseline.read_text(encoding="utf-8"))
            payload["schema"] = "contentops.receipt-exposure-baseline/v1"
            baseline.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            with self.assertRaises(checker.CheckError) as caught:
                checker.check(root, baseline, paths=[path], base="HEAD")
            self.assertEqual(str(caught.exception), "BASELINE_LEGACY")

    def test_the_committed_baseline_keeps_no_values(self) -> None:
        text = checker.DEFAULT_BASELINE.read_text(encoding="utf-8")
        self.assertNotIn("founder_v1", text)
        self.assertNotIn("2ac10c6e9029", text)
        data = json.loads(text)
        self.assertEqual(data["schema"], checker.SCHEMA)


class ReceiptSecretAdversarialTests(unittest.TestCase):
    """Scenarios the phase-2 review requires beyond the original suite."""

    def test_credential_in_url_userinfo_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = _receipt(root, "url.json",
                            {"source_url": "https://user:s3cr3t@example.com/a/b"})
            found = checker.scan(root, paths=[path])
            self.assertIn(
                (path.relative_to(root).as_posix(), "<text>", "credential_value"), found)

    def test_signed_query_url_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = _receipt(root, "signed.json", {
                "source_url": "https://b.example.com/x"
                              "?X-Amz-Signature=abc&X-Amz-Credential=def"})
            found = checker.scan(root, paths=[path])
            self.assertIn(
                (path.relative_to(root).as_posix(), "<text>", "credential_value"), found)

    def test_a_plain_url_is_not_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = _receipt(root, "plain.json",
                            {"source_url": "https://example.com/plain/path?page=2"})
            self.assertEqual(checker.scan(root, paths=[path]), [])

    def test_changed_array_element_path_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path, baseline = _repo(root, {"attempts": [{"voice_id": "v1"}]})
            _receipt(root, "a.json", {"attempts": [{"voice_id": "v2"}]})
            result = checker.check(root, baseline, paths=[path], base="HEAD")
            self.assertFalse(result["ok"])
            self.assertTrue(any(item["reason"] == "changed_value" for item in result["new"]))

    def test_multiple_receipt_files_changed_are_all_reported(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _git(root, "init")
            a = _receipt(root, "a.json", {"voice_id": "v1"})
            b = _receipt(root, "b.json", {"task_id": "t1"})
            baseline = root / BASELINE_REL
            baseline.parent.mkdir(parents=True, exist_ok=True)
            baseline.write_text(json.dumps(
                checker._baseline_payload(root, paths=[a, b]), ensure_ascii=False),
                encoding="utf-8")
            _commit(root)
            _receipt(root, "a.json", {"voice_id": "v2"})
            _receipt(root, "b.json", {"task_id": "t2"})
            result = checker.check(root, baseline, paths=[a, b], base="HEAD")
            files = {item["file"] for item in result["new"]}
            self.assertEqual(files, {a.relative_to(root).as_posix(),
                                     b.relative_to(root).as_posix()})

    def test_a_benign_new_field_passes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path, baseline = _repo(root, {"voice_id": "v1"})
            _receipt(root, "a.json", {"voice_id": "v1", "note": "plain human text"})
            result = checker.check(root, baseline, paths=[path], base="HEAD")
            self.assertTrue(result["ok"], result)

    def test_non_utf8_receipt_is_detected_not_crashed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = root / "projects" / "demo" / "receipts" / "latin.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'{"voice_id": "v1", "label": "\xe9t\xe9"}')
            found = checker.scan(root, paths=[path])
            self.assertIn(
                (path.relative_to(root).as_posix(), "voice_id", "provider_id"), found)

    def test_windows_style_paths_are_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = root / "projects" / "demo" / "receipts" / "a.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}", encoding="utf-8")

            class _Result:
                returncode = 0
                stdout = b"projects\\demo\\receipts\\a.json\0"

            with patch.object(checker, "hidden_run", return_value=_Result()):
                tracked = checker._tracked_receipts(root)
            self.assertEqual(tracked, [path])

    def test_token_used_as_url_username_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            path = _receipt(
                root, "tokuser.json",
                {"source_url": "https://abcDEF1234567890xyzTOKEN42@example.com/a"})
            found = checker.scan(root, paths=[path])
            self.assertIn(
                (path.relative_to(root).as_posix(), "<text>", "credential_value"), found)

    def test_email_userinfo_and_email_query_are_not_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for name, url in (
                ("mailuser.json", "https://verylongemailaddressname@example.com/a"),
                ("mailq.json", "https://example.com/x?email=a@b.com"),
                ("shortuser.json", "https://user@example.com/a"),
            ):
                with self.subTest(url=url):
                    path = _receipt(root, name, {"source_url": url})
                    self.assertEqual(checker.scan(root, paths=[path]), [])


if __name__ == "__main__":
    unittest.main()
