"""Mechanism regressions: a video project must not degrade into text cards.

These tests lock in the workflow fixes that stop the recurring defects:
  * narration never silently falls back to the SAPI mechanical voice
  * the account's reviewed render_variant overrides a dark-blue brand palette
  * B-roll planning prefers real/generated stills and grades evidence by rights
  * screen callouts are semantic keywords, never a duplicate of the subtitle
  * shot durations come from measured narration, not a fixed guess

Run: python tests/test_broll_workflow_mechanism.py
"""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import m5_production  # noqa: E402
import plan_broll  # noqa: E402
from contentops.media import motion_planner  # noqa: E402


def test_narration_default_is_minimax_not_sapi():
    """A missing account DNA must never degrade to the offline voice."""
    source = inspect.getsource(m5_production.build)
    segment = source[source.index("provider = (narration_provider"):]
    segment = segment[:segment.index("narration = run_stage")]
    assert 'or "minimax"' in segment
    assert 'or "sapi"' not in segment
    sig = inspect.signature(m5_production.stage_narration)
    assert sig.parameters["provider"].default == "minimax"
    # SAPI must remain a reachable explicit diagnostic path, never deleted.
    assert "sapi" in str(m5_production.stage_narration.__doc__)


def test_account_render_variant_overrides_brand_palette():
    """An account can choose its video canvas without editing code."""
    source = inspect.getsource(motion_planner.build_auto_plan)
    assert 'profile.get("render_variant")' in source
    assert "render_variant" in source
    assert "AUTO_MOTION_STALE_STYLE_VARIANT" not in source or (
        "style_variant not in video_variants" in source)  # new path replaces the stale hard-block


def test_video_accounts_declare_a_reviewed_render_variant():
    for slug, expected in (
        ("x-superplay-future-intelligence", "graphite-paper"),
        ("x-superplay-1024", "warm-editorial"),
    ):
        data = json.loads((ROOT / "config/accounts" / f"{slug}.json").read_text(encoding="utf-8"))
        profile = data["visual"]["motion"]["motion_profile"]
        assert profile.get("render_variant") == expected
        assert expected in profile["style_variants"]


def test_callout_is_a_keyword_never_a_subtitle_duplicate():
    """The old defect printed the same sentence twice on screen."""
    line = {"narration": "如果你想学习Agent开发，来，我们聊聊怎么要怎么做？"}
    callout = plan_broll._callout(line)
    assert len(callout) <= 6
    assert "，" not in callout and "？" not in callout
    assert callout != line["narration"][:len(callout)]
    assert "Agent" in callout or "学" in callout

    line2 = {"narration": "项目能不能按说明跑起来，第二，结果能不能评测"}
    assert plan_broll._callout(line2) == "能不能跑"


def test_evidence_grade_is_a_rights_fact_not_a_media_type():
    """A locally authored card labelled REAL_SCREENSHOT is not real evidence."""
    import tempfile

    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        (project / "sources").mkdir()
        (project / "assets/processed").mkdir(parents=True)
        image = project / "assets/processed/a.png"
        image.write_bytes(b"fake png")
        sha = "0" * 64
        manifest = {
            "schema": "contentops.m5-assets/v1",
            "assets": [
                {"id": "REAL-1", "type": "REAL_SCREENSHOT", "permission": "LICENSED",
                 "license": "CC-BY-4.0", "sha256": sha,
                 "repo_path": f"{project.as_posix()}/assets/processed/a.png"},
                {"id": "CARD-1", "type": "REAL_SCREENSHOT", "permission": "CREATED_BY_OWNER",
                 "sha256": sha, "repo_path": f"{project.as_posix()}/assets/processed/a.png"},
            ],
        }
        (project / "sources/assets.json").write_text(json.dumps(manifest), encoding="utf-8")
        stills = plan_broll._usable_stills(project)
        grades = {s["id"]: s["grade"] for s in stills}
        assert grades["REAL-1"] == "real"
        # A locally authored card mislabelled REAL_SCREENSHOT is excluded from
        # the B-roll pool entirely -- it is slide art, not a picture.
        assert "CARD-1" not in grades


def test_illustrative_card_is_not_routed_as_evidence():
    factual = {"narration": "这份 README 把学习路线和项目实践串在一起"}
    opinion = {"narration": "我认为应该先想清楚目标"}
    assert plan_broll._route_kind(factual, {"grade": "illustrative"}) == "info_graphic"
    assert plan_broll._route_kind(factual, {"grade": "real"}) == "evidence_shot"
    # An opinion line stays an info graphic even if a real still is bound --
    # showing a screen under an opinion is a category error.
    assert plan_broll._route_kind(opinion, {"grade": "real"}) == "info_graphic"


def test_shot_durations_come_from_measured_narration():
    narration = {"lines": [
        {"line_id": "A", "start": 0.0, "duration": 5.0},
        {"line_id": "B", "start": 6.0, "duration": 4.0},
        {"line_id": "C", "start": 11.0, "duration": 3.0},
    ]}
    slots = plan_broll._line_slot(narration)
    assert slots["A"]["duration"] == 6.0  # to next start, not spoken duration
    assert slots["B"]["duration"] == 5.0
    assert slots["C"]["duration"] == 3.0  # last line uses its own duration


def test_planner_propagates_render_variant_to_every_spec():
    """Without this, every shot falls back to the dark-blue AI palette."""
    source = inspect.getsource(plan_broll.build_plan)
    assert '"style_variant": built_variant' in source
    assert "no reviewed render_variant" in source
    assert "render_variant" in source


def test_materialized_plan_declares_clip_backend():
    source = inspect.getsource(plan_broll.materialize)
    assert "backend: remotion" in source
    assert "shot_plan: motion/broll-plan.json" in source
    assert plan_broll.PLAN_SCHEMA == "contentops.m5-motion-shots/v1"


def main() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"{len(tests)} tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
