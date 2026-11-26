"""Hybrid motion: a clip overlay switches only ready, spec-backed shots.

Regression for the half-built mechanism this round fixed:

* a planning-only orchestration receipt must NOT block the ordinary Huashu
  auto-plan (it is advice, not a render contract);
* a materialized overlay switches only shots that carry a valid clip spec;
* Huashu shots keep their measured duration and authored spec;
* the final shot list passes enforcement and reports a hybrid backend.

Run: python tests/test_hybrid_motion_overlay.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import m5_production as m5  # noqa: E402
import plan_motion  # noqa: E402


def _clip_spec(project: Path, backend: str = "remotion") -> str:
    rel = "motion/orchestrated/S01-HOOK-01.json"
    path = project / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"backend": backend, "template": "title_card",
                                "shot_type": "title_card", "duration_s": 3.0,
                                "props": {"conflict": "冲突", "stakes": "价值"}},
                               ensure_ascii=False), encoding="utf-8")
    return rel


def test_planning_receipt_does_not_block():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        (p / "receipts").mkdir()
        (p / "receipts" / "motion-orchestration.json").write_text(json.dumps({
            "schema": "contentops.animation-orchestration/v1",
            "materialized": False,
            "assignments": [{"placement_id": "s1", "backend": "remotion"}],
        }), encoding="utf-8")
        m5._enforce_orchestration(p, [{"placement_id": "s1", "backend": "huashu-motion"}])
        print("PASS planning receipt does not block")


def test_materialized_mismatch_blocks():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        (p / "receipts").mkdir()
        (p / "receipts" / "motion-orchestration.json").write_text(json.dumps({
            "schema": "contentops.animation-orchestration/v1",
            "materialized": True,
            "assignments": [{"placement_id": "s1", "backend": "remotion"}],
        }), encoding="utf-8")
        try:
            m5._enforce_orchestration(p, [{"placement_id": "s1", "backend": "huashu-motion"}])
        except m5.M5Blocked:
            print("PASS materialized mismatch blocks")
        else:
            raise AssertionError("a materialized mismatch must block")


def test_huashu_family_is_one_skill():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        (p / "receipts").mkdir()
        (p / "receipts" / "motion-orchestration.json").write_text(json.dumps({
            "schema": "contentops.animation-orchestration/v1",
            "materialized": True,
            "assignments": [{"placement_id": "s1", "backend": "huashu-art-motion"}],
        }), encoding="utf-8")
        m5._enforce_orchestration(p, [{"placement_id": "s1", "backend": "huashu-motion"}])
        print("PASS huashu backend family is equivalent")


def test_overlay_switches_only_spec_backed_shots():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        spec_rel = _clip_spec(p)
        (p / "motion" / "orchestrated-plan.json").write_text(json.dumps({
            "schema": "contentops.m5-motion-overlay/v1", "orchestrated": True,
            "shots": [{"placement_id": "S01-HOOK-01", "backend": "remotion",
                       "asset_id": "orch-S01-HOOK-01", "spec": spec_rel}],
        }), encoding="utf-8")
        auto_plan = {"shots": [
            {"placement_id": "S01-HOOK-01", "backend": "huashu-motion", "spec": "old"},
            {"placement_id": "S01-HOOK-02", "backend": "huashu-motion", "spec": "old2"},
        ]}
        switched = m5._apply_clip_overlay(p, auto_plan, [
            {"line_id": "S01-HOOK-01", "duration": 6.2},
            {"line_id": "S01-HOOK-02", "duration": 5.0},
        ])
        assert switched == ["S01-HOOK-01"]
        first, second = auto_plan["shots"]
        assert first["backend"] == "remotion" and first["spec"] == spec_rel
        assert first["duration_s"] == 6.2  # measured, clamped to 2-8
        assert second["backend"] == "huashu-motion" and second["spec"] == "old2"
        print("PASS overlay switches only spec-backed shots")


def test_overlay_rejects_missing_spec():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        (p / "motion").mkdir()
        (p / "motion" / "orchestrated-plan.json").write_text(json.dumps({
            "schema": "contentops.m5-motion-overlay/v1",
            "shots": [{"placement_id": "x", "backend": "remotion",
                       "spec": "motion/nope.json"}],
        }), encoding="utf-8")
        try:
            m5._apply_clip_overlay(p, {"shots": [{"placement_id": "x"}]},
                                   [{"line_id": "x", "duration": 4.0}])
        except m5.M5Blocked:
            print("PASS overlay rejects missing spec")
        else:
            raise AssertionError("a missing overlay spec must block")


def test_editorial_title_props_are_nonempty():
    line = {"narration": "如果你想学习Agent开发，来，我们聊聊怎么要怎么做？"}
    props = plan_motion._editorial_title_props(line)
    assert props and props["conflict"].strip() and props["stakes"].strip()
    assert "source" not in " ".join(props)  # no evidence path smuggled into a card
    print("PASS editorial title props are non-empty claim-free")


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print(f"{len(tests)} tests passed")
