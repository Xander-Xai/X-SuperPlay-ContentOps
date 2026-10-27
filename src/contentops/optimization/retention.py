"""Deterministic retention checks for an account cut.

These are the measurable parts of a visual/ops review: how long one visual
holds, whether the hook is short, whether captions are burned, and whether the
package has a cover and a CTA. They do not judge taste; they expose the parts a
viewer would feel as "stuck".
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def longest_visual_run(shots: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Longest run of consecutive shots that show the same visual asset."""
    longest = 0.0
    longest_key = None
    current_key = None
    current = 0.0
    for shot in shots:
        key = shot.get("image") or shot.get("video")
        duration = float(shot.get("duration") or 0.0)
        if key == current_key:
            current += duration
        else:
            if current > longest:
                longest, longest_key = current, current_key
            current_key, current = key, duration
    if current > longest:
        longest, longest_key = current, current_key
    return {"seconds": round(longest, 3), "asset": longest_key}


def evaluate_retention(
    *,
    storyboard: Dict[str, Any],
    spec: Dict[str, Any],
    captions_burned: bool,
    caption_cues: int,
    intro_duration: float,
    cover_exists: bool,
) -> Dict[str, Any]:
    retention = spec.get("retention") or {}
    max_hold = float(retention.get("max_static_hold_s", 10.0))
    max_hook = float(retention.get("max_hook_s", 3.0))
    run = longest_visual_run(storyboard.get("shots") or [])
    checks: List[Dict[str, Any]] = [
        {
            "id": "hook_short_enough",
            "ok": intro_duration <= max_hook + 0.5,
            "intro_s": round(intro_duration, 3),
            "max_s": max_hook,
        },
        {
            "id": "static_hold",
            "ok": run["seconds"] <= max_hold,
            "longest_s": run["seconds"],
            "max_s": max_hold,
            "asset": run["asset"],
        },
        {
            "id": "captions",
            "ok": bool(captions_burned) and caption_cues > 0,
            "burned": bool(captions_burned),
            "cues": caption_cues,
        },
        {"id": "cover", "ok": bool(cover_exists)},
        {"id": "cta", "ok": bool(spec.get("cta"))},
    ]
    failures = [check["id"] for check in checks if not check["ok"]]
    return {
        "schema": "contentops.retention-check/v1",
        "account": spec.get("account"),
        "overall": "PASS" if not failures else "WARN",
        "longest_visual_run_s": run["seconds"],
        "caption_cues": caption_cues,
        "captions_burned": bool(captions_burned),
        "checks": checks,
        "failures": failures,
    }
