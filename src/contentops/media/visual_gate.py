"""Interpret the Huashu Art Motion film gate without granting visual approval.

The source tool reports calibrated motion and blank-frame checks. A green or
yellow result is still only an automated screen; human review remains separate.
"""
from __future__ import annotations

from typing import Any, Dict, Mapping


SCHEMA = "contentops.visual-gate/v1"


def evaluate_film_gate(payload: Mapping[str, Any], exit_code: int) -> Dict[str, Any]:
    """Translate film_gate JSON into a fail-closed, receipt-ready result."""
    gate_light = str(payload.get("gate_light") or "").lower()
    verdict = str(payload.get("verdict") or "").lower()
    if gate_light == "red" or verdict == "red":
        state = "FAIL"
    # Huashu Art Motion's film_gate uses verdict="pass" for both green and
    # yellow lights; the light carries the severity. Keep accepting the older
    # green/yellow verdict form for existing fixtures and receipts.
    elif exit_code == 0 and gate_light == "green" and verdict in {"green", "pass"}:
        state = "PASS"
    elif exit_code == 0 and gate_light == "yellow" and verdict in {"yellow", "pass"}:
        state = "WARN"
    else:
        state = "BLOCKED"

    metrics = {
        key: payload.get(key) for key in (
            "duration_s", "shots", "fast_ratio", "fast_ratio_worst_window",
            "blank_run_s", "blue_purple_share", "still_ratio",
            "longest_still_s", "event_rate", "max_event_gap_s", "dead_bg",
            "dead_flat", "gate_metrics", "lights", "explain", "worst_window",
        ) if key in payload
    }
    return {
        "schema": SCHEMA,
        "state": state,
        "gate_light": gate_light or None,
        "exit_code": int(exit_code),
        "metrics": metrics,
        "production_ready": False,
        "publish_authorized": False,
        "human_review": "PENDING_FOUNDER_REVIEW",
    }


def test_evaluate_film_gate_fails_closed_and_keeps_human_review_separate() -> None:
    green = evaluate_film_gate({"gate_light": "green", "verdict": "green",
                                "fast_ratio": 0.08}, 0)
    assert green["state"] == "PASS"
    assert green["production_ready"] is False
    assert green["publish_authorized"] is False
    assert green["human_review"] == "PENDING_FOUNDER_REVIEW"
    assert green["metrics"]["fast_ratio"] == 0.08

    yellow = evaluate_film_gate({"gate_light": "yellow", "verdict": "yellow"}, 0)
    assert yellow["state"] == "WARN"
    assert evaluate_film_gate({"gate_light": "red", "verdict": "red"}, 2)["state"] == "FAIL"
    assert evaluate_film_gate({"gate_light": "green", "verdict": "green"}, 2)["state"] == "BLOCKED"
    assert evaluate_film_gate({"gate_light": "green", "verdict": "yellow"}, 0)["state"] == "BLOCKED"
