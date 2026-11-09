#!/usr/bin/env python3
"""Offline tests for the WeChat data cube channel: ranges, preflight, receipts.

Nothing here talks to WeChat: no token fetch, no credential value, no
``wechatpy`` import at module level. What is pinned is the contract the
official API imposes and the honesty rules the repository already uses —
official range ceilings are refused, a missing field stays missing, and a
receipt never claims to modify the artefact.

Run: python tests/test_wechat_metrics.py
"""

from __future__ import annotations

import importlib
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.platforms import wechat_metrics as wm  # noqa: E402


def _recent(days_back: int) -> str:
    return (date.today() - timedelta(days=days_back)).isoformat()


def test_range_accepts_a_seven_day_window_that_is_fully_past() -> None:
    problems = wm.validate_range(_recent(8), _recent(2), wm.MAX_USER_SUMMARY_DAYS)
    assert not problems, problems


def test_range_refuses_an_eight_day_span_with_the_official_ceiling_named() -> None:
    problems = wm.validate_range(_recent(9), _recent(1), wm.MAX_USER_SUMMARY_DAYS)
    assert any("official ceiling" in p for p in problems), problems


def test_range_refuses_inverted_dates_and_future_ends() -> None:
    problems = wm.validate_range(_recent(2), _recent(8), wm.MAX_USER_SUMMARY_DAYS)
    assert any("after end_date" in p for p in problems), problems
    future = (date.today() + timedelta(days=1)).isoformat()
    problems = wm.validate_range(_recent(2), future, wm.MAX_USER_SUMMARY_DAYS)
    assert any("future" in p for p in problems), problems


def test_range_refuses_malformed_dates_all_at_once() -> None:
    problems = wm.validate_range("2026/11/01", "not-a-date", wm.MAX_USER_SUMMARY_DAYS)
    assert len(problems) == 2, problems  # both named, not just the first


def test_preflight_fails_closed_on_missing_credentials() -> None:
    report = wm.preflight({})
    assert report["ok"] is False
    assert report["ip_whitelist"] == "UNKNOWN"
    assert any("missing credential" in p for p in report["problems"])


def test_preflight_refuses_placeholders_without_echoing_values() -> None:
    report = wm.preflight({"WECHAT_1_APPID": "your_appid", "WECHAT_1_APPSECRET": "real-looking-secret-98765"})
    assert report["ok"] is False
    assert any("placeholder" in p for p in report["problems"])
    blob = repr(report)
    assert "real-looking-secret-98765" not in blob, "preflight must never echo a secret"
    assert "your_appid" not in blob


def test_preflight_passes_on_well_shaped_credentials() -> None:
    report = wm.preflight({"WECHAT_1_APPID": "wx1234567890abcd", "WECHAT_1_APPSECRET": "0123456789abcdef0123456789abcdef"})
    assert report["ok"] is True
    assert report["credentials"]["WECHAT_1_APPID"]["length"] == len("wx1234567890abcd")


def test_normalise_sums_returned_fields_and_names_absent_ones() -> None:
    rows = [
        {"int_page_read_count": 10, "int_page_read_user": 8},
        {"int_page_read_count": 5, "int_page_read_user": 4},
    ]
    out = wm.normalise_metric_rows(rows)
    assert out["metrics"] == {"int_page_read_count": 15, "int_page_read_user": 12}
    assert out["fields_absent"] == ["cumulate_user"], "absent stays absent"


def test_normalise_never_zero_fills_and_refuses_junk_rows() -> None:
    out = wm.normalise_metric_rows([{"int_page_read_count": "many"}, 7])
    assert out["metrics"] == {}
    assert "cumulate_user" in out["fields_absent"]
    assert out["problems"], out


def test_receipt_never_claims_to_modify_the_artefact() -> None:
    receipt = wm.build_receipt(
        "acct", "2026-11-01", "2026-11-02", ["user_summary"], {}, "2026-11-09T00:00:00Z",
        problems=["user_summary: ... errcode=40164 ..."],
    )
    for key in ("modifies_script", "modifies_qc", "modifies_production_ready"):
        assert receipt[key] is False, key
    assert receipt["schema"] == wm.RECEIPT_SCHEMA
    assert receipt["channel"] == "api_official"
    assert receipt["issues"] == ["user_summary: ... errcode=40164 ..."]


def test_transport_module_stays_lazy_about_wechatpy() -> None:
    script = importlib.import_module("wechat_metrics")
    assert script is not None
    # Importing the script module must never pull wechatpy in: the transport
    # import happens inside cmd_fetch, under --execute only.
    import sys as _sys

    assert "wechatpy" not in _sys.modules, "import must stay lazy"


TESTS: List[Tuple[str, Callable[[], None]]] = [
    (name, obj) for name, obj in sorted(globals().items())
    if name.startswith("test_") and callable(obj)
]


def main() -> int:
    failures: List[Tuple[str, str]] = []
    for name, fn in TESTS:
        try:
            fn()
            print(f"[ OK ] {name}")
        except Exception as exc:  # noqa: BLE001
            failures.append((name, repr(exc)))
            print(f"[FAIL] {name}: {exc!r}")
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print(f"\nAll {len(TESTS)} wechat metrics tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
