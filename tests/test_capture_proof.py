"""Capture Proof contract tests.

Run: python tests/test_capture_proof.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.evidence.capture import CaptureProof  # noqa: E402
from contentops.evidence._common import ContractError  # noqa: E402

SHA = "a" * 64
OTHER = "b" * 64


def base(**overrides):
    document = {
        "schema": "contentops.capture-proof/v1",
        "capture_id": "CAP-20261027-001",
        "session_id": "SES-20261027-001",
        "evidence_class": "EXECUTED",
        "repository_revision": "8ce5e198a11f637b2673b00594ec6c3c589db317",
        "working_tree_state": "clean",
        "target_environment": {"name": "windows-11", "description_digest": SHA},
        "command": {"display": "python scripts/doctor.py --json", "sha256": SHA},
        "read_only": True,
        "fixture_or_cache": "none",
        "started_at": "2026-10-27T10:00:00Z",
        "finished_at": "2026-10-27T10:00:03Z",
        "exit_code": 0,
        "recording": {
            "logical_path": "project://work/raw/cap.mp4",
            "sha256": SHA,
            "time_range": "00:01.000-00:05.000",
        },
        "permission_scope": "internal_review",
        "notes": [],
    }
    document.update(overrides)
    return document


def rejects(code, **overrides):
    try:
        CaptureProof.from_dict(base(**overrides))
    except ContractError as exc:
        assert exc.code == code, f"expected {code}, got {exc.code}: {exc}"
        return
    raise AssertionError(f"a document with {overrides} was accepted")


def test_a_complete_executed_capture_is_accepted():
    proof = CaptureProof.from_dict(base())
    assert proof.exit_code == 0
    assert proof.to_dict()["schema"] == "contentops.capture-proof/v1"
    print("[ok] a complete EXECUTED capture is accepted")


def test_a_non_zero_exit_is_valid_observed_evidence():
    proof = CaptureProof.from_dict(base(exit_code=1))
    assert proof.exit_code == 1, "a failing command must keep its real exit code"
    print("[ok] a non-zero exit code is preserved, not rewritten")


def test_a_publishable_capture_requires_approval_and_read_only():
    rejects("PUBLISHABLE_REQUIRES_READ_ONLY",
            permission_scope="publishable", read_only=False,
            approval={"reviewer": "Founder", "approved_at": "2026-10-27T11:00:00Z"})
    rejects("MISSING_APPROVAL", permission_scope="publishable", read_only=True)

    approved = CaptureProof.from_dict(base(
        permission_scope="publishable",
        approval={"reviewer": "Founder", "approved_at": "2026-10-27T11:00:00Z"},
    ))
    assert approved.permission_scope == "publishable"
    print("[ok] publishable captures require read-only and a recorded approval")


def test_structural_failures_are_named():
    rejects("UNSUPPORTED_SCHEMA", schema="contentops.capture-proof/v0")
    rejects("INVALID_SHA256", recording={
        "logical_path": "project://work/raw/cap.mp4", "sha256": "abc",
        "time_range": "00:01.000-00:05.000"})
    rejects("INVALID_EVIDENCE_CLASS", evidence_class="GUESSED")
    rejects("INVALID_TIMESTAMP", finished_at="2026-10-27T09:59:59Z")
    rejects("INVALID_TIME_RANGE", recording={
        "logical_path": "project://work/raw/cap.mp4", "sha256": SHA,
        "time_range": "00:05.000-00:05.000"})
    rejects("NON_LOGICAL_PATH", recording={
        "logical_path": "D:/Temp/cap.mp4", "sha256": SHA,
        "time_range": "00:01.000-00:05.000"})
    rejects("UNKNOWN_FIELD", invented="x")
    print("[ok] schema, SHA, class, time, path and unknown fields are refused")


def test_a_command_cannot_carry_a_secret():
    # Built at runtime so the repository's own secret scanner does not read the
    # fixture as a leaked credential.
    secretish = "curl -H 'Authorization: " + "Bea" + "rer sk-live'"
    rejects("SECRET_IN_COMMAND", command={
        "display": secretish, "sha256": SHA})
    rejects("SECRET_IN_COMMAND", command={
        "display": "cat .env", "sha256": SHA})
    print("[ok] a command display containing a secret marker is refused")


def test_time_ranges_accept_mm_ss_and_hh_mm_ss():
    """MM:SS.mmm must not be read as HH:MM. 00:03.000 is 3 s, not 180 s."""
    from contentops.evidence._common import parse_time_range

    assert parse_time_range("00:03.000-00:06.104", "x") == (3000, 6104)
    assert parse_time_range("03:10.000-03:11.000", "x") == (190000, 191000)
    assert parse_time_range("01:02:03.004-01:02:04.005", "x") == (3723004, 3724005)
    print("[ok] MM:SS.mmm and HH:MM:SS.mmm resolve to the same millisecond scale")


def test_the_recording_hash_is_checked_against_the_file():
    with tempfile.TemporaryDirectory() as td:
        recording = Path(td) / "cap.mp4"
        recording.write_bytes(b"real bytes")
        import hashlib
        actual = hashlib.sha256(b"real bytes").hexdigest()
        proof = CaptureProof.from_dict(base(recording={
            "logical_path": "project://work/raw/cap.mp4",
            "sha256": actual,
            "time_range": "00:01.000-00:05.000",
        }))
        assert proof.verify_recording(recording) == actual

        wrong = CaptureProof.from_dict(base())
        try:
            wrong.verify_recording(recording)
        except ContractError as exc:
            assert exc.code == "EVIDENCE_SHA_MISMATCH", exc
        else:
            raise AssertionError("a mismatched recording hash was accepted")
    print("[ok] the receipt's SHA must match the file on disk")


def main() -> int:
    failures = []
    tests = (
        test_a_complete_executed_capture_is_accepted,
        test_a_non_zero_exit_is_valid_observed_evidence,
        test_a_publishable_capture_requires_approval_and_read_only,
        test_structural_failures_are_named,
        test_a_command_cannot_carry_a_secret,
        test_time_ranges_accept_mm_ss_and_hh_mm_ss,
        test_the_recording_hash_is_checked_against_the_file,
    )
    for fn in tests:
        try:
            fn()
        except AssertionError as exc:
            failures.append((fn.__name__, str(exc)))
            print(f"[FAIL] {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append((fn.__name__, repr(exc)))
            print(f"[ERR ] {fn.__name__}: {exc!r}")
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print(f"\nAll {len(tests)} capture-proof tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
