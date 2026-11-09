"""Publication backfill contract tests.

A backfill receipt is a person's claim that a real publication happened.
These tests prove the module refuses to write that claim down without the
fields that make it auditable: the real URL, the time, the version, and who
is putting their name on it. Nothing here touches a network.

Run: python tests/test_publish_backfill.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.publish.backfill import (  # noqa: E402
    STATUS_RECORDED,
    STATUS_VERIFIED,
    BackfillError,
    iter_backfills,
    mark_readback_failed,
    record_backfill,
    summary,
    verify_readback,
)

NOW = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)
PAST = "2026-11-09T10:00:00+08:00"


def _payload(**overrides):
    base = {
        "platform": "bilibili",
        "content_id": "20261109-001",
        "post_url": "https://www.bilibili.com/video/BV1ab411W7xQ",
        "published_at": PAST,
        "confirmed_by": "founder",
        "artifact_sha256": "a" * 64,
    }
    base.update(overrides)
    return base


def test_record_writes_an_auditable_receipt():
    with tempfile.TemporaryDirectory() as tmp:
        document = record_backfill(_payload(), Path(tmp), now=NOW)
        path = document["receipt"]
        stored = json.loads(Path(path).read_text(encoding="utf-8"))
        assert stored["status"] == STATUS_RECORDED
        assert stored["post_url"].startswith("https://www.bilibili.com/video/")
        assert stored["published_version"]["artifact_sha256"] == "a" * 64
        assert stored["confirmed_by"] == "founder"
        assert "readback" not in stored  # no readback yet


def test_record_refuses_missing_bindings():
    cases = {
        "CONTENT_ID_REQUIRED": _payload(content_id=""),
        "POST_URL_REQUIRED": _payload(post_url=""),
        "CONFIRMED_BY_REQUIRED": _payload(confirmed_by=""),
    }
    for expected_code, payload in cases.items():
        with tempfile.TemporaryDirectory() as tmp:
            try:
                record_backfill(payload, Path(tmp), now=NOW)
            except BackfillError as exc:
                assert exc.code == expected_code, (expected_code, exc.code, exc.detail)
            else:
                raise AssertionError(f"{expected_code} was not raised")


def test_record_refuses_a_url_that_is_not_this_platforms():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            record_backfill(
                _payload(platform="douyin",
                         post_url="https://www.bilibili.com/video/BV1ab411W7xQ"),
                Path(tmp), now=NOW)
        except BackfillError as exc:
            assert exc.code == "POST_URL_INVALID", exc.code
        else:
            raise AssertionError("a bilibili URL was accepted as douyin")


def test_record_refuses_somebody_elses_x_post_shape():
    with tempfile.TemporaryDirectory() as tmp:
        for url in (
            "http://x.com/handle/status/123",
            "https://x.com/handle/profile",
            "https://example.com/handle/status/123456789",
        ):
            try:
                record_backfill(_payload(platform="x", post_url=url), Path(tmp), now=NOW)
            except BackfillError as exc:
                assert exc.code == "POST_URL_INVALID", (url, exc.detail)
            else:
                raise AssertionError(f"{url} was accepted as an X status URL")


def test_record_binds_the_x_handle_to_the_url():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            record_backfill(_payload(
                platform="x", account_handle="mysuperplay",
                post_url="https://x.com/someoneelse/status/1234567890123456789"),
                Path(tmp), now=NOW)
        except BackfillError as exc:
            assert exc.code == "POST_URL_HANDLE_MISMATCH", exc.code
        else:
            raise AssertionError("a URL from another account was accepted")

        document = record_backfill(_payload(
            platform="x", account_handle="@mysuperplay",
            post_url="https://x.com/mysuperplay/status/1234567890123456789"),
            Path(tmp), now=NOW)
        assert document["account_handle"] == "@mysuperplay"


def test_record_refuses_future_publication():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            record_backfill(_payload(published_at="2027-01-01T00:00:00Z"), Path(tmp), now=NOW)
        except BackfillError as exc:
            assert exc.code == "PUBLISHED_AT_IN_FUTURE", exc.code
        else:
            raise AssertionError("a future publication time was accepted")


def test_record_refuses_a_second_receipt_for_the_same_publication():
    with tempfile.TemporaryDirectory() as tmp:
        record_backfill(_payload(), Path(tmp), now=NOW)
        try:
            record_backfill(_payload(), Path(tmp), now=NOW)
        except BackfillError as exc:
            assert exc.code == "BACKFILL_DUPLICATE", exc.code
        else:
            raise AssertionError("duplicate backfill was accepted")


def test_record_refuses_malformed_version_fields():
    with tempfile.TemporaryDirectory() as tmp:
        for field, value, expected in (
            ("artifact_sha256", "zz" * 32, "VERSION_HASH_INVALID"),
            ("source_commit", "not a commit", "SOURCE_COMMIT_INVALID"),
        ):
            try:
                record_backfill(_payload(**{field: value}), Path(tmp), now=NOW)
            except BackfillError as exc:
                assert exc.code == expected, (expected, exc.code)
            else:
                raise AssertionError(f"{field}={value!r} was accepted")


def test_record_must_agree_with_the_package_receipt():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        package = project / "receipts" / "x-package-20261109-001.json"
        package.parent.mkdir(parents=True)
        package.write_text(json.dumps({
            "content_id": "20261109-999",
            "built_at": "2026-11-09T09:00:00Z",
        }), encoding="utf-8")
        try:
            record_backfill(
                _payload(package_receipt_ref="receipts/x-package-20261109-001.json"),
                project / "receipts" / "publish_backfill",
                project=project, now=NOW)
        except BackfillError as exc:
            assert exc.code == "PACKAGE_CONTENT_ID_MISMATCH", exc.code
        else:
            raise AssertionError("a receipt for different content was accepted")

        package.write_text(json.dumps({
            "content_id": "20261109-001",
            "built_at": "2026-11-09T18:00:00+08:00",
        }), encoding="utf-8")
        try:
            record_backfill(
                _payload(package_receipt_ref="receipts/x-package-20261109-001.json"),
                project / "receipts" / "publish_backfill",
                project=project, now=NOW)
        except BackfillError as exc:
            assert exc.code == "PUBLISHED_BEFORE_PACKAGE", exc.code
        else:
            raise AssertionError("published before the package existed was accepted")


def test_verify_readback_is_the_only_path_to_verified():
    with tempfile.TemporaryDirectory() as tmp:
        recorded = record_backfill(_payload(), Path(tmp), now=NOW)
        path = recorded["receipt"]
        try:
            verify_readback(path, method="MANUAL_INSPECT", evidence_ref="", now=NOW)
        except BackfillError as exc:
            assert exc.code == "READBACK_INVALID", exc.code
        else:
            raise AssertionError("a VERIFIED readback without evidence was accepted")

        verified = verify_readback(
            path, method="SCREENSHOT", evidence_ref="screenshots/live.png",
            now=datetime(2026, 11, 10, 9, 0, 0, tzinfo=timezone.utc))
        assert verified["status"] == STATUS_VERIFIED
        assert verified["readback"]["method"] == "SCREENSHOT"
        # idempotent: a second verify returns the stored receipt
        again = verify_readback(path, method="SCREENSHOT", evidence_ref="screenshots/live.png")
        assert again["status"] == STATUS_VERIFIED


def test_failed_readback_is_recorded_not_hidden():
    with tempfile.TemporaryDirectory() as tmp:
        recorded = record_backfill(_payload(), Path(tmp), now=NOW)
        path = recorded["receipt"]
        document = mark_readback_failed(
            path, method="MANUAL_INSPECT",
            note="URL shows an account-suspended page", now=NOW)
        assert document["status"] == STATUS_RECORDED
        assert document["readback"]["status"] == "FAILED"
        assert "suspended" in document["readback"]["note"]


def test_summary_reports_what_survives_an_audit():
    with tempfile.TemporaryDirectory() as tmp:
        record_backfill(_payload(), Path(tmp), now=NOW)
        record_backfill(_payload(platform="x", content_id="20261109-002",
                                 post_url="https://x.com/handle/status/1234567890123456789"),
                        Path(tmp), now=NOW)
        report = summary(Path(tmp))
        assert report["total"] == 2
        assert report["published_recorded"] == 2
        assert report["published_verified"] == 0
        assert report["by_platform"]["bilibili"][STATUS_RECORDED] == 1
        assert len(iter_backfills(Path(tmp))) == 2


def test_cli_records_and_lists(tmp_root: Path) -> None:
    project = tmp_root / "project"
    (project / "receipts").mkdir(parents=True)
    record_cmd = [
        sys.executable, str(ROOT / "scripts" / "publish_backfill.py"),
        "--record", "--project", str(project),
        "--platform", "gzh", "--id", "20261109-003",
        "--url", "https://mp.weixin.qq.com/s/abcDEF123_-",
        "--published-at", PAST, "--confirmed-by", "founder",
    ]
    done = subprocess.run(record_cmd, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    list_cmd = [sys.executable, str(ROOT / "scripts" / "publish_backfill.py"),
                "--list", "--project", str(project)]
    done = subprocess.run(list_cmd, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert "gzh 20261109-003 PUBLISHED_RECORDED" in done.stdout
    # the same record command again is a duplicate: exit 1 with the code on stderr
    done = subprocess.run(record_cmd, capture_output=True, text=True)
    assert done.returncode == 1, (done.returncode, done.stderr)
    assert "BACKFILL_DUPLICATE" in done.stderr


def main() -> int:
    tests = (
        test_record_writes_an_auditable_receipt,
        test_record_refuses_missing_bindings,
        test_record_refuses_a_url_that_is_not_this_platforms,
        test_record_refuses_somebody_elses_x_post_shape,
        test_record_binds_the_x_handle_to_the_url,
        test_record_refuses_future_publication,
        test_record_refuses_a_second_receipt_for_the_same_publication,
        test_record_refuses_malformed_version_fields,
        test_record_must_agree_with_the_package_receipt,
        test_verify_readback_is_the_only_path_to_verified,
        test_failed_readback_is_recorded_not_hidden,
        test_summary_reports_what_survives_an_audit,
    )
    failures = []
    for fn in tests:
        try:
            fn()
            print(f"[ok] {fn.__name__}")
        except AssertionError as exc:
            failures.append((fn.__name__, str(exc)))
            print(f"[FAIL] {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append((fn.__name__, repr(exc)))
            print(f"[ERR ] {fn.__name__}: {exc!r}")
    # CLI smoke test needs a scratch dir of its own
    try:
        with tempfile.TemporaryDirectory() as tmp:
            test_cli_records_and_lists(Path(tmp))
        print("[ok] test_cli_records_and_lists")
    except AssertionError as exc:
        failures.append(("test_cli_records_and_lists", str(exc)))
        print(f"[FAIL] test_cli_records_and_lists: {exc}")
    except Exception as exc:  # noqa: BLE001
        failures.append(("test_cli_records_and_lists", repr(exc)))
        print(f"[ERR ] test_cli_records_and_lists: {exc!r}")
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print("\nAll publish backfill tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
