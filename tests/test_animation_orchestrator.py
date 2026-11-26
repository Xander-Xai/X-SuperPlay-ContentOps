"""Hybrid motion planning: several skills, one explicit backend per shot.

What these tests pin:

- different shot kinds get different ready backends (a real hybrid plan);
- an unready backend is never chosen, even when it is the only compatible one;
- an explicit per-shot backend is never silently replaced;
- a default backend is a preference, not a forced single backend;
- account gates (future-intelligence recording, 1024 real recording) hold;
- an unclassified shot with no ready fallback fails closed.

Run: python tests/test_animation_orchestrator.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.media.animation_backend import ACCOUNT_1024, ACCOUNT_FUTURE  # noqa: E402
from contentops.media.animation_orchestrator import (  # noqa: E402
    CLIP_PATH,
    HUASHU_PATH,
    OrchestrationBlocked,
    backend_path,
    plan,
)

ALL_READY = {
    "huashu-art-motion": "READY", "huashu-motion": "READY",
    "remotion": "READY", "motion-canvas": "READY", "manim": "READY",
}


def test_hybrid_plan_uses_several_backends():
    lines = [
        {"id": "s1", "shot_kind": "title_card"},
        {"id": "s2", "shot_kind": "math"},
        {"id": "s3", "shot_kind": "architecture"},
        {"id": "s4", "shot_kind": "code_card"},
    ]
    result = plan(lines, account_id=ACCOUNT_FUTURE, readiness=ALL_READY)
    assert result["hybrid"] is True
    assert len(result["backends"]) >= 2
    by_id = {a["placement_id"]: a for a in result["assignments"]}
    assert by_id["s1"]["backend"] == "remotion"
    assert by_id["s2"]["backend"] == "manim"
    assert by_id["s4"]["backend"] == "remotion"
    assert result["production_ready"] is False


def test_unready_backend_is_never_chosen():
    lines = [{"id": "m", "shot_kind": "math"}]
    readiness = dict(ALL_READY, manim="BLOCKED")
    try:
        plan(lines, account_id=ACCOUNT_FUTURE, readiness=readiness)
    except OrchestrationBlocked as exc:
        assert exc.code == "NO_READY_BACKEND"
    else:
        raise AssertionError("manim is the only math backend and is unready")


def test_explicit_backend_is_not_replaced():
    lines = [{"id": "t", "shot_kind": "title_card", "backend": "huashu-art-motion"}]
    result = plan(lines, account_id=ACCOUNT_FUTURE, readiness=ALL_READY,
                  default_backend="remotion")
    shot = result["assignments"][0]
    assert shot["backend"] == "huashu-art-motion"
    assert shot["explicit"] is True
    assert shot["backend_path"] == HUASHU_PATH


def test_default_is_a_preference_not_a_forced_single_backend():
    lines = [{"id": "m", "shot_kind": "math"}, {"id": "t", "shot_kind": "title_card"}]
    result = plan(lines, account_id=ACCOUNT_FUTURE, readiness=ALL_READY,
                  default_backend="huashu-art-motion")
    by_id = {a["placement_id"]: a for a in result["assignments"]}
    assert by_id["t"]["backend"] == "huashu-art-motion"
    assert by_id["m"]["backend"] == "manim"
    assert result["hybrid"] is True


def test_unready_default_blocks_instead_of_substituting():
    lines = [{"id": "t", "shot_kind": "title_card"}]
    readiness = dict(ALL_READY, **{"huashu-art-motion": "BLOCKED"})
    try:
        plan(lines, account_id=ACCOUNT_FUTURE, readiness=readiness,
             default_backend="huashu-art-motion")
    except OrchestrationBlocked as exc:
        assert exc.code == "DEFAULT_BACKEND_UNREADY"
    else:
        raise AssertionError("unready default must block")


def test_future_account_refuses_recording_input():
    lines = [{"id": "r", "shot_kind": "recording_mark", "input_kind": "screen_recording"}]
    try:
        plan(lines, account_id=ACCOUNT_FUTURE, readiness=ALL_READY)
    except OrchestrationBlocked as exc:
        assert exc.code == "RECORDING_FORBIDDEN"
    else:
        raise AssertionError("recording must be refused for future-intelligence")


def test_1024_requires_real_recording_in_production():
    lines = [{"id": "t", "shot_kind": "title_card"}]
    try:
        plan(lines, account_id=ACCOUNT_1024, readiness=ALL_READY)
    except OrchestrationBlocked as exc:
        assert exc.code == "MISSING_REAL_RECORDING"
    else:
        raise AssertionError("1024 production needs a real recording")
    result = plan(lines, account_id=ACCOUNT_1024, readiness=ALL_READY,
                  purpose="test", has_real_recording=False)
    assert result["assignments"]


def test_unclassified_without_ready_fallback_fails_closed():
    lines = [{"id": "x", "shot_kind": "unclassified"}]
    readiness = {b: "BLOCKED" for b in ALL_READY}
    try:
        plan(lines, account_id=ACCOUNT_FUTURE, readiness=readiness)
    except OrchestrationBlocked as exc:
        assert exc.code == "NO_READY_BACKEND"
    else:
        raise AssertionError("no ready backend must block, not produce a still")


def test_backend_path_distinguishes_huashu_from_clip_renderers():
    assert backend_path("huashu-art-motion") == HUASHU_PATH
    assert backend_path("remotion") == CLIP_PATH
    assert backend_path("manim") == CLIP_PATH


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"{len(tests)} tests passed")
