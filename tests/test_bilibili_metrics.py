#!/usr/bin/env python3
"""Offline tests for Bilibili public metrics shaping, gating and receipts.

Nothing here talks to Bilibili: no network, no login, no ``bilibili_api``
import at module level. What is pinned is the part a reviewer must trust —
whose account may fetch, which BV wins, what happens when a counter is
missing, and what a receipt may never claim.

Run: python tests/test_bilibili_metrics.py
"""

from __future__ import annotations

import importlib
import sys
import tempfile
import types
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.accounts import load_account  # noqa: E402
from contentops.platforms import bilibili_metrics as bm  # noqa: E402

DNA_FI = load_account(ROOT / "config" / "accounts" / "x-superplay-future-intelligence.json")
DNA_1024 = load_account(ROOT / "config" / "accounts" / "x-superplay-1024.json")


def test_dna_gate_passes_for_the_fi_account() -> None:
    allowed, reason = bm.dna_allows(DNA_FI)
    assert allowed, reason
    assert "bilibili" in reason


def test_dna_gate_refuses_the_1024_account() -> None:
    allowed, reason = bm.dna_allows(DNA_1024)
    assert not allowed
    assert "bilibili" in reason, reason
    assert "douyin" in reason, reason  # the refusal names what the account does have


def test_bvid_chain_prefers_cli_over_project_and_dna() -> None:
    project = {"bilibili_bvid": "BV1projec001"}
    dna = {"bilibili_bvid": "BV1dna000001"}
    bvid, source, _, blockers = bm.resolve_bvid("BV1cli000001", project, dna)
    assert not blockers, blockers
    assert source == "cli"
    assert bvid == "BV1cli000001"


def test_bvid_chain_falls_back_to_project_then_dna() -> None:
    dna = {"platform_bilibili_bvid": "BV1dna000002"}
    bvid, source, _, blockers = bm.resolve_bvid("", {"bilibili_bvid": "BV1projec002"}, dna)
    assert not blockers and source == "project" and bvid == "BV1projec002"
    bvid, source, _, blockers = bm.resolve_bvid("", {}, dna)
    assert not blockers and source == "dna" and bvid == "BV1dna000002"


def test_bvid_chain_blocks_when_no_layer_carries_one() -> None:
    bvid, source, reason, blockers = bm.resolve_bvid("", {}, {})
    assert source == "none" and bvid == ""
    assert blockers and "no BV anywhere" in blockers[0]


def test_malformed_bvid_is_a_blocker_not_a_guess() -> None:
    for bad in ("BVshort", "BV1234567890ABC", "av170001", ""):
        _, _, _, blockers = bm.resolve_bvid(bad, {}, {})
        assert blockers, f"expected a blocker for {bad!r}"
    ok_bvid, _, _, blockers = bm.resolve_bvid("BV1GJ411x7h7", {}, {})
    assert ok_bvid == "BV1GJ411x7h7" and not blockers


def test_shape_keeps_only_real_counters() -> None:
    stat: Dict[str, Any] = {
        "view": 1234, "danmaku": 5, "reply": 6, "favorite": 7,
        "coin": 8, "share": 9, "like": 10,
    }
    metrics, problems = bm.shape_video_stats(stat)
    assert not problems
    assert metrics == stat


def test_shape_never_zero_fills_a_missing_counter() -> None:
    stat = {"view": 1234, "like": 10}  # coin, share, danmaku... absent
    metrics, problems = bm.shape_video_stats(stat)
    assert metrics == {"view": 1234, "like": 10}
    assert "coin" not in metrics and not problems


def test_shape_refuses_non_integer_values_by_name() -> None:
    stat = {"view": "many", "like": 1.5, "coin": True, "share": -3}
    metrics, problems = bm.shape_video_stats(stat)
    assert metrics == {}
    joined = "; ".join(problems)
    assert "stat.view is str" in joined
    assert "stat.like is float" in joined
    assert "stat.coin is bool" in joined
    assert "stat.share is negative" in joined


def test_receipt_mode_follows_the_bvid_source() -> None:
    cli_receipt = bm.build_receipt("acct", "BV1cli000001", "cli", {"view": 1}, "2026-11-09T00:00:00Z")
    assert cli_receipt["mode"] == bm.MODE_TRANSPORT_SMOKE
    dna_receipt = bm.build_receipt("acct", "BV1dna000001", "dna", {"view": 1}, "2026-11-09T00:00:00Z")
    assert dna_receipt["mode"] == bm.MODE_ACCOUNT_DELIVERY


def test_receipt_never_claims_to_modify_the_artefact() -> None:
    receipt = bm.build_receipt("acct", "BV1dna000001", "dna", {"view": 1}, "2026-11-09T00:00:00Z")
    for key in ("modifies_script", "modifies_qc", "modifies_production_ready"):
        assert receipt[key] is False, key
    assert receipt["schema"] == bm.RECEIPT_SCHEMA
    assert receipt["channel"] == "api_public"
    assert receipt["upstream"]["license"] == "MIT"


def test_receipt_records_issues_and_title() -> None:
    receipt = bm.build_receipt(
        "acct", "BV1dna000001", "dna", {"view": 1}, "2026-11-09T00:00:00Z",
        title="一条标题", problems=["stat.share is str"],
    )
    assert receipt["title"] == "一条标题"
    assert receipt["issues"] == ["stat.share is str"]


def test_transport_module_stays_lazy_about_bilibili_api() -> None:
    script = importlib.import_module("bilibili_metrics")
    assert isinstance(script, types.ModuleType)
    assert "bilibili_api" not in sys.modules, "plan must not import the transport"


def test_cli_plan_runs_offline_and_blocks_without_a_bv() -> None:
    import argparse
    import json as json_mod

    from process_utils import hidden_run

    script_path = ROOT / "scripts" / "bilibili_metrics.py"
    proc = hidden_run(
        [sys.executable, str(script_path), "plan", "--account",
         str(ROOT / "config" / "accounts" / "x-superplay-1024.json")],
    )
    assert proc.returncode == 4, proc.stdout + proc.stderr
    payload = json_mod.loads(proc.stdout)
    assert payload["state"] == "BLOCKED"
    assert "bilibili" in " ".join(payload["blockers"])


def test_cli_plan_with_explicit_bv_is_a_smoke_plan() -> None:
    import json as json_mod

    from process_utils import hidden_run

    script_path = ROOT / "scripts" / "bilibili_metrics.py"
    proc = hidden_run(
        [sys.executable, str(script_path), "plan", "--account",
         str(ROOT / "config" / "accounts" / "x-superplay-future-intelligence.json"),
         "--bvid", "BV1GJ411x7h7"],
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json_mod.loads(proc.stdout)
    assert payload["state"] == "PLAN"
    assert payload["mode"] == bm.MODE_TRANSPORT_SMOKE
    assert payload["bvid_source"] == "cli"


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
    print(f"\nAll {len(TESTS)} bilibili metrics tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
