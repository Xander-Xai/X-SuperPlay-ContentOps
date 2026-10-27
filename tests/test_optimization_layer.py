"""Optimization-layer policy tests.

The layer must refuse an adoption that has no linkable source, no evidence, or a
GPU dependency. It must also keep the data flywheel honest: MEASURE and LEARN
stay blocked until a real published URL and metrics exist.

Run: python tests/test_optimization_layer.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.optimization import (  # noqa: E402
    OptimizationError,
    build_report,
    evaluate_candidate,
    load_backlog,
    load_flywheel,
    load_policy,
    load_signals,
    rank_backlog,
    score_candidate,
)


def _cycle():
    return load_policy(), load_signals(), load_backlog(), load_flywheel()


def _candidate(candidate_id: str = "CAND-001") -> dict:
    backlog = load_backlog()
    for candidate in backlog["candidates"]:
        if candidate["id"] == candidate_id:
            return copy.deepcopy(candidate)
    raise AssertionError(f"{candidate_id} missing from the backlog")


def test_current_cycle_is_valid():
    policy, signals, backlog, flywheel = _cycle()
    report = build_report(policy, signals, backlog, flywheel)
    assert report["signal_count"] == len(signals["signals"])
    assert report["candidate_count"] == len(backlog["candidates"])
    assert report["ranked"]


def test_priority_formula():
    policy, _, _, _ = _cycle()
    candidate = _candidate("CAND-001")
    assert score_candidate(candidate, policy) == 12


def test_adopt_requires_github():
    policy, _, _, _ = _cycle()
    candidate = _candidate("CAND-001")
    candidate["repo"] = None
    evaluated = evaluate_candidate(candidate, policy)
    assert evaluated["effective_decision"] == "DEFER"
    assert any("GitHub" in reason for reason in evaluated["downgrade_reasons"])


def test_adopt_requires_evidence():
    policy, _, _, _ = _cycle()
    candidate = _candidate("CAND-001")
    candidate["evidence"] = 1
    evaluated = evaluate_candidate(candidate, policy)
    assert evaluated["effective_decision"] == "DEFER"
    assert any("below the floor" in reason for reason in evaluated["downgrade_reasons"])


def test_gpu_candidate_cannot_adopt():
    policy, _, _, _ = _cycle()
    candidate = _candidate("CAND-001")
    candidate["gpu_required"] = True
    evaluated = evaluate_candidate(candidate, policy)
    assert evaluated["effective_decision"] == "DEFER"
    assert any("GPU" in reason for reason in evaluated["downgrade_reasons"])


def test_rank_puts_the_body_motion_first():
    policy, signals, backlog, flywheel = _cycle()
    ranked = build_report(policy, signals, backlog, flywheel)["ranked"]
    assert ranked[0]["id"] == "CAND-001"
    assert ranked[0]["effective_decision"] == "ADOPT"


def test_actions_rank_before_deferrals():
    policy, signals, backlog, flywheel = _cycle()
    ranked = build_report(policy, signals, backlog, flywheel)["ranked"]
    order = [item["effective_decision"] for item in ranked]
    actionable = {"ADOPT", "EXTEND", "BUILD"}
    first_deferral = next(
        (index for index, decision in enumerate(order) if decision in {"DEFER", "REJECT"}),
        len(order),
    )
    assert all(decision in actionable for decision in order[:first_deferral])
    assert order[first_deferral:] and all(
        decision in {"DEFER", "REJECT"} for decision in order[first_deferral:]
    )
    ids = [item["id"] for item in ranked]
    assert ids.index("CAND-002") < ids.index("CAND-004")


def test_unknown_signal_is_refused():
    policy, signals, backlog, flywheel = _cycle()
    backlog["candidates"][0]["signal_ids"] = ["SIG-DOES-NOT-EXIST"]
    try:
        build_report(policy, signals, backlog, flywheel)
    except OptimizationError as exc:
        assert exc.code == "UNKNOWN_SIGNAL"
    else:
        raise AssertionError("an unknown signal was accepted")


def test_unknown_decision_is_refused():
    policy, _, _, _ = _cycle()
    candidate = _candidate("CAND-003")
    candidate["decision"] = "MAYBE"
    try:
        evaluate_candidate(candidate, policy)
    except OptimizationError as exc:
        assert exc.code == "UNKNOWN_DECISION"
    else:
        raise AssertionError("an unknown decision was accepted")


def test_flywheel_measure_and_learn_are_blocked():
    policy, signals, backlog, flywheel = _cycle()
    report = build_report(policy, signals, backlog, flywheel)
    blocked = {entry["stage"] for entry in report["blocked_stages"]}
    assert {"MEASURE", "LEARN"} <= blocked


def test_no_adopted_candidate_requires_gpu():
    policy, signals, backlog, flywheel = _cycle()
    ranked = build_report(policy, signals, backlog, flywheel)["ranked"]
    for item in ranked:
        if item["effective_decision"] == "ADOPT":
            assert item["gpu_required"] is False


def main() -> int:
    failures = []
    tests = (
        test_current_cycle_is_valid,
        test_priority_formula,
        test_adopt_requires_github,
        test_adopt_requires_evidence,
        test_gpu_candidate_cannot_adopt,
        test_rank_puts_the_body_motion_first,
        test_actions_rank_before_deferrals,
        test_unknown_signal_is_refused,
        test_unknown_decision_is_refused,
        test_flywheel_measure_and_learn_are_blocked,
        test_no_adopted_candidate_requires_gpu,
    )
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
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print("\nAll optimization-layer tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
