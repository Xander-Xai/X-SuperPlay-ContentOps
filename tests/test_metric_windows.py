"""Metric window audit tests.

The audit exists so ``0`` and "nobody ever recorded a number" can never be
confused downstream. These tests pin that distinction, the three windows, and
the refusal paths — nothing here fetches, imputes or scrapes a value.

Run: python tests/test_metric_windows.py
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.publish.metric_windows import (  # noqa: E402
    DUE_MISSING,
    NOT_DUE,
    OBSERVED,
    WindowAuditError,
    audit_content,
    parse_timestamp,
    read_snapshots_csv,
    summarize,
)

PUBLISHED = "2026-11-01T10:00:00+08:00"  # 02:00 UTC
NOW = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)


def _row(content_id="20261101-001", observed_at="2026-11-02T03:00:00Z",
         metric_source="manual_export", age_window="T+24H",
         impressions="1200", engagements="45", qualified="0"):
    return {
        "content_id": content_id,
        "observed_at": observed_at,
        "metric_source": metric_source,
        "age_window": age_window,
        "impressions": impressions,
        "engagements": engagements,
        "qualified_signal_count": qualified,
    }


def test_windows_close_at_the_right_hours():
    audit = audit_content("c", PUBLISHED, [], now=datetime(
        2026, 11, 1, 3, 0, 0, tzinfo=timezone.utc))
    assert audit["windows"]["T+24H"]["due_at"] == "2026-11-02T02:00:00Z"
    assert audit["windows"]["T+72H"]["due_at"] == "2026-11-04T02:00:00Z"
    assert audit["windows"]["T+7D"]["due_at"] == "2026-11-08T02:00:00Z"


def test_undue_windows_are_not_owed_yet():
    audit = audit_content("c", PUBLISHED, [], now=datetime(
        2026, 11, 2, 1, 0, 0, tzinfo=timezone.utc))
    assert audit["windows"]["T+24H"]["status"] == NOT_DUE
    assert audit["windows"]["T+72H"]["status"] == NOT_DUE
    assert audit["windows"]["T+7D"]["status"] == NOT_DUE


def test_due_missing_is_a_broken_loop_not_a_zero():
    audit = audit_content("c", PUBLISHED, [], now=NOW)
    assert audit["windows"]["T+24H"]["status"] == DUE_MISSING
    assert audit["windows"]["T+72H"]["status"] == DUE_MISSING
    assert audit["windows"]["T+7D"]["status"] == DUE_MISSING
    assert audit["windows"]["T+24H"]["impressions"] is None


def test_observed_picks_the_first_covering_snapshot():
    rows = [
        _row(observed_at="2026-11-02T03:00:00Z", impressions="500"),
        _row(observed_at="2026-11-04T03:00:00Z", age_window="T+72H", impressions="900"),
        _row(observed_at="2026-11-09T03:00:00Z", age_window="T+7D", impressions="1500"),
    ]
    audit = audit_content("20261101-001", PUBLISHED, rows, now=NOW)
    assert audit["windows"]["T+24H"]["status"] == OBSERVED, audit["windows"]["T+24H"]
    assert audit["windows"]["T+24H"]["impressions"] == 500
    assert audit["windows"]["T+24H"]["metric_source"] == "manual_export"
    assert audit["windows"]["T+72H"]["impressions"] == 900
    assert audit["windows"]["T+7D"]["impressions"] == 1500


def test_zero_is_observed_and_missing_is_missing():
    rows = [_row(impressions="0"), _row(content_id="other", observed_at="2026-11-02T04:00:00Z")]
    audit = audit_content("20261101-001", PUBLISHED, rows, now=NOW)
    window = audit["windows"]["T+24H"]
    assert window["status"] == OBSERVED, window
    assert window["impressions"] == 0
    assert window["impressions_missing"] is False

    blank = _row(impressions="")
    audit = audit_content("20261101-001", PUBLISHED, [blank], now=NOW)
    window = audit["windows"]["T+24H"]
    assert window["status"] == OBSERVED
    assert window["impressions"] is None
    assert window["impressions_missing"] is True


def test_bad_timestamps_are_refused_by_name():
    for value, expected in (("not-a-time", "TIME_INVALID"), ("", "TIME_MISSING")):
        try:
            audit_content("c", value, [], now=NOW)
        except WindowAuditError as exc:
            assert exc.code == expected, (expected, exc.code)
        else:
            raise AssertionError(f"{value!r} was accepted as a timestamp")
    try:
        audit_content("", PUBLISHED, [], now=NOW)
    except WindowAuditError as exc:
        assert exc.code == "CONTENT_ID_REQUIRED"
    else:
        raise AssertionError("an empty content id was accepted")


def test_snapshot_csv_columns_are_enforced():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "snapshots.csv"
        path.write_text("content_id,observed_at,metric_source\n", encoding="utf-8")
        try:
            read_snapshots_csv(path)
        except WindowAuditError as exc:
            assert exc.code == "SNAPSHOTS_CSV_COLUMNS", exc.code
        else:
            raise AssertionError("a snapshots CSV with missing columns was accepted")
        try:
            read_snapshots_csv(Path(tmp) / "absent.csv")
        except WindowAuditError as exc:
            assert exc.code == "SNAPSHOTS_CSV_MISSING"
        else:
            raise AssertionError("a missing snapshots CSV was accepted")


def test_summarize_counts_what_a_weekly_review_acts_on():
    audits = [
        audit_content("20261101-001", PUBLISHED, [_row()], now=NOW),
        audit_content("b", PUBLISHED, [], now=NOW),
    ]
    report = summarize(audits)
    assert report["windows"]["T+24H"][OBSERVED] == 1
    assert report["windows"]["T+24H"][DUE_MISSING] == 1
    # a is missing T+72H and T+7D; b is missing all three windows
    assert report["due_missing_total"] == 5, report


def test_parse_timestamp_reads_naive_as_utc():
    moment = parse_timestamp("2026-11-09T12:00:00")
    assert moment.tzinfo is not None


def test_cli_strict_fails_on_due_missing_windows(tmp_root: Path) -> None:
    posts = tmp_root / "posts.csv"
    with posts.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["content_id", "published_at"])
        writer.writeheader()
        writer.writerow({"content_id": "20261101-001", "published_at": PUBLISHED})
    snapshots = tmp_root / "snapshots.csv"
    with snapshots.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "content_id", "observed_at", "metric_source", "age_window",
            "impressions", "engagements", "qualified_signal_count"])
        writer.writeheader()
        writer.writerow(_row())
    strict = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "metric_window_audit.py"),
         "--posts-csv", str(posts), "--snapshots-csv", str(snapshots),
         "--now", "2026-11-09T12:00:00Z", "--strict"],
        capture_output=True, text=True)
    assert strict.returncode == 1, (strict.returncode, strict.stderr)
    assert "DUE_MISSING" in strict.stderr

    parsed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "metric_window_audit.py"),
         "--posts-csv", str(posts), "--snapshots-csv", str(snapshots),
         "--now", "2026-11-09T12:00:00Z", "--json"],
        capture_output=True, text=True)
    assert parsed.returncode == 0, parsed.stderr
    report = json.loads(parsed.stdout)
    assert report["summary"]["windows"]["T+24H"][OBSERVED] == 1


def main() -> int:
    tests = (
        test_windows_close_at_the_right_hours,
        test_undue_windows_are_not_owed_yet,
        test_due_missing_is_a_broken_loop_not_a_zero,
        test_observed_picks_the_first_covering_snapshot,
        test_zero_is_observed_and_missing_is_missing,
        test_bad_timestamps_are_refused_by_name,
        test_snapshot_csv_columns_are_enforced,
        test_summarize_counts_what_a_weekly_review_acts_on,
        test_parse_timestamp_reads_naive_as_utc,
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
    try:
        with tempfile.TemporaryDirectory() as tmp:
            test_cli_strict_fails_on_due_missing_windows(Path(tmp))
        print("[ok] test_cli_strict_fails_on_due_missing_windows")
    except AssertionError as exc:
        failures.append(("test_cli_strict_fails_on_due_missing_windows", str(exc)))
        print(f"[FAIL] test_cli_strict_fails_on_due_missing_windows: {exc}")
    except Exception as exc:  # noqa: BLE001
        failures.append(("test_cli_strict_fails_on_due_missing_windows", repr(exc)))
        print(f"[ERR ] test_cli_strict_fails_on_due_missing_windows: {exc!r}")
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print("\nAll metric window audit tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
