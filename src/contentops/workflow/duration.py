"""Duration plan: how a target length is divided, and when it cannot be.

A target duration is not a plan. If thirty seconds are split across twenty
lines, every shot is a flash frame; if they are split across two, the cut is a
slide deck. The composer accepts whatever storyboard it is given, so the
constraint has to exist before the render.

This module divides a target into a bounded number of shots, each within a
minimum and maximum, and refuses when the budget cannot be met without violating
one of them. It is arithmetic only: no audio, no renderer, no provider.

What is not claimed
-------------------
A valid plan does not prove the narration will fit. It proves the requested
length can be cut into legal shots at the requested line count; measured
narration remains the later gate.
"""

from __future__ import annotations

from typing import Any, Dict

from .contract import WorkflowError

SCHEMA = "contentops.duration-plan/v1"

#: Below this a cut is a flash frame rather than a shot.
MIN_SHOT_S = 1.5
#: Above this a still outlives the sentence it illustrates.
MAX_SHOT_S = 12.0


def plan_duration(target_sec: float, line_count: int, *,
                  min_shot_s: float = MIN_SHOT_S,
                  max_shot_s: float = MAX_SHOT_S) -> Dict[str, Any]:
    """Divide ``target_sec`` into ``line_count`` legal shots.

    Raises ``WorkflowError`` with ``DURATION_UNSATISFIABLE`` when the budget
    cannot be met without going below ``min_shot_s`` or above ``max_shot_s``.
    """
    try:
        target = float(target_sec)
        lines = int(line_count)
    except (TypeError, ValueError):
        raise WorkflowError("DURATION_INPUT", "target and line count must be numbers")
    if target <= 0 or lines <= 0:
        raise WorkflowError("DURATION_INPUT", "target and line count must be positive")
    if not (0 < min_shot_s <= max_shot_s):
        raise WorkflowError("DURATION_BOUNDS", "min_shot_s must be positive and <= max_shot_s")

    if lines * min_shot_s > target:
        raise WorkflowError(
            "DURATION_UNSATISFIABLE",
            f"{lines} lines cannot fit in {target:.3f}s at a {min_shot_s:.1f}s minimum",
        )
    if lines * max_shot_s < target:
        raise WorkflowError(
            "DURATION_UNSATISFIABLE",
            f"{target:.3f}s cannot be covered by {lines} lines at a {max_shot_s:.1f}s maximum",
        )

    per_line = round(target / lines, 3)
    shots = [{"index": i, "duration_s": per_line} for i in range(lines)]
    # Put the rounding remainder on the last shot so the sum is exact.
    covered = round(per_line * lines, 3)
    shots[-1]["duration_s"] = round(shots[-1]["duration_s"] + (round(target, 3) - covered), 3)
    if shots[-1]["duration_s"] < min_shot_s or shots[-1]["duration_s"] > max_shot_s:
        raise WorkflowError(
            "DURATION_UNSATISFIABLE",
            "the rounding remainder pushes the final shot outside the legal range",
        )
    return {
        "schema": SCHEMA,
        "target_s": round(target, 3),
        "line_count": lines,
        "min_shot_s": min_shot_s,
        "max_shot_s": max_shot_s,
        "shots": shots,
        "production_ready": False,
    }


def validate_duration(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a duration plan, returning it unchanged on success."""
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise WorkflowError("DURATION_SCHEMA", f"expected schema {SCHEMA}")
    shots = payload.get("shots")
    if not isinstance(shots, list) or not shots:
        raise WorkflowError("DURATION_SHOTS", "shots must be a non-empty list")
    total = 0.0
    for shot in shots:
        try:
            value = float(shot.get("duration_s"))
        except (TypeError, ValueError):
            raise WorkflowError("DURATION_SHOT_VALUE", "every shot needs a numeric duration")
        if value <= 0:
            raise WorkflowError("DURATION_SHOT_VALUE", "shot durations must be positive")
        total += value
    if abs(total - float(payload.get("target_s", -1))) > 0.002:
        raise WorkflowError("DURATION_SUM", "shot durations do not sum to the target")
    if payload.get("production_ready") is not False:
        raise WorkflowError("DURATION_PRODUCTION_READY", "a plan may not claim production readiness")
    return payload
