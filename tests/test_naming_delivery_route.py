"""Naming, delivery, visual route, copy strategy and technical-explainer tests.

Run: python tests/test_naming_delivery_route.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.quality.technical_explainer import BEATS, audit_text, validate_script_document  # noqa: E402
from contentops.workflow import copy_strategy, delivery, naming, visual_route  # noqa: E402

SHA = "a" * 64


# --- naming -------------------------------------------------------------

def test_slugify_is_stable_and_portable():
    assert naming.slugify("Hello World!") == "hello-world"
    first = naming.slugify("中文标题")
    second = naming.slugify("中文标题")
    assert first == second and first.startswith("topic-")


def test_content_id_shape_is_enforced():
    assert naming.validate_content_id("douyin-20261028-001-topic-a1b2c3")["sequence"] == "001"
    for bad in ("20261028-001-x", "douyin-20261340-001-x", "douyin-20261028-001-AB"):
        try:
            naming.validate_content_id(bad)
        except ValueError:
            continue
        raise AssertionError(f"{bad!r} should be refused")


def test_next_content_id_allocates_the_first_free_sequence():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "douyin-20261028-001-topic-a1b2c3").mkdir()
        (root / "douyin-20261028-003-topic-d4e5f6").mkdir()
        value = naming.next_content_id("topic", root, "20261028")
        assert value == "douyin-20261028-002-topic", value


def test_package_path_cannot_escape_the_root():
    with tempfile.TemporaryDirectory() as td:
        try:
            naming.package_path(Path(td), "../escape")
        except ValueError:
            return
    raise AssertionError("an escaping package path must be refused")


# --- delivery -----------------------------------------------------------

def _manifest(**overrides):
    document = {
        "schema": "contentops.delivery-manifest/v1",
        "content_id": "douyin-20261028-001-demo",
        "platform": "douyin",
        "files": [{"path": "final.mp4", "sha256": SHA, "role": "video"}],
        "gate": {"contract": "contentops.copy-to-video/v1", "stages_current": True},
        "human_review": "PENDING",
    }
    document.update(overrides)
    return document


def test_a_complete_delivery_manifest_passes():
    assert delivery.validate_manifest(_manifest()) == []


def test_a_delivery_without_a_video_role_fails():
    errors = delivery.validate_manifest(_manifest(files=[
        {"path": "cover.png", "sha256": SHA, "role": "cover"}]))
    assert any("role 'video'" in message for message in errors), errors


def test_an_absolute_delivery_path_fails():
    errors = delivery.validate_manifest(_manifest(files=[
        {"path": "C:/final.mp4", "sha256": SHA, "role": "video"}]))
    assert any("relative" in message for message in errors), errors


def test_delivery_requires_current_stage_gates():
    errors = delivery.validate_manifest(_manifest(
        gate={"contract": "contentops.copy-to-video/v1", "stages_current": False}))
    assert any("stages_current" in message for message in errors), errors


def test_an_unknown_human_review_state_fails():
    errors = delivery.validate_manifest(_manifest(human_review="MAYBE"))
    assert any("human_review" in message for message in errors), errors


# --- visual route -------------------------------------------------------

def _route(**overrides):
    document = {
        "schema": "contentops.visual-route/v1",
        "scenes": [
            {"scene_id": "S1", "text": "终端运行结果", "route": "evidence_screen_recording",
             "evidence": True, "generated": False},
            {"scene_id": "S2", "text": "概念配图", "route": "xiaohei_illustration",
             "evidence": False, "generated": True},
        ],
    }
    document.update(overrides)
    return document


def test_scene_classification_prefers_evidence():
    assert visual_route.classify_scene("终端录屏展示结果") == "evidence_screen_recording"
    assert visual_route.classify_scene("架构链路图") == "architecture_diagram"
    assert visual_route.classify_scene("配图说明概念") == "xiaohei_illustration"


def test_a_consistent_route_plan_passes():
    assert visual_route.validate_route(_route()) == []


def test_a_generated_scene_cannot_carry_an_exact_token():
    errors = visual_route.validate_route(_route(scenes=[
        {"scene_id": "S1", "text": "3 个模块", "route": "concept_illustration",
         "evidence": False, "generated": True}]))
    assert any("exact token" in message for message in errors), errors


def test_three_consecutive_generated_scenes_fail():
    scenes = [{"scene_id": f"S{i}", "text": "概念图", "route": "concept_illustration",
               "evidence": False, "generated": True} for i in range(3)]
    errors = visual_route.validate_route(_route(scenes=scenes))
    assert any("consecutive generated" in message for message in errors), errors


def test_route_flags_must_match_the_route():
    errors = visual_route.validate_route(_route(scenes=[
        {"scene_id": "S1", "text": "录屏", "route": "evidence_screen_recording",
         "evidence": False, "generated": False}]))
    assert any("evidence must be True" in message for message in errors), errors


# --- copy strategy ------------------------------------------------------

def _strategy(**overrides):
    document = {
        "schema": "contentops.copy-strategy/v1",
        "candidate_id": "C-1",
        "shelf": "ai_tool_validation",
        "viewer_job": "decide",
        "angle_id": "live-verification",
        "thesis": "先验证再投入",
        "hook_variants": ["先别急着装", "十分钟给你答案", "这个坑我替你踩"],
        "argument_beats": ["problem", "method", "evidence", "result", "limitation", "conclusion"],
        "claim_ids": ["C-1"],
        "duration_tier": "two_minute",
    }
    document.update(overrides)
    return document


def test_a_complete_strategy_card_passes():
    assert copy_strategy.validate_strategy(_strategy()) == []


def test_an_angle_must_belong_to_its_shelf():
    errors = copy_strategy.validate_strategy(_strategy(shelf="failure_boundary"))
    assert any("belongs to shelf" in message for message in errors), errors


def test_three_distinct_hooks_are_required():
    errors = copy_strategy.validate_strategy(_strategy(hook_variants=["同一个"]))
    assert any("three" in message for message in errors), errors
    duplicate = copy_strategy.validate_strategy(
        _strategy(hook_variants=["同一个"] * 3))
    assert any("distinct" in message for message in duplicate), duplicate


def test_required_argument_beats_are_enforced():
    errors = copy_strategy.validate_strategy(_strategy(argument_beats=["problem"]))
    assert any("missing required beats" in message for message in errors), errors


def test_an_unknown_duration_tier_fails():
    errors = copy_strategy.validate_strategy(_strategy(duration_tier="ten_minute"))
    assert any("duration_tier" in message for message in errors), errors


# --- technical explainer ------------------------------------------------

ALL_BEATS = list(BEATS)


def test_a_non_technical_script_is_not_judged_by_this_gate():
    assert validate_script_document({"content_type": "opinion", "lines": []}) == []


def test_a_complete_technical_explainer_passes():
    text = ("这个机制解决的是显存碎片问题。它按需分配和回收，条件取决于工作负载。"
            "它和相邻能力区别在于调度方式。在并发请求场景下可能提升吞吐。下一步可以复现。")
    assert audit_text(text, ALL_BEATS) == []


def test_missing_beats_fail():
    errors = audit_text("只讲了一句话。", ALL_BEATS[:2])
    assert any("missing declared beats" in message for message in errors), errors


def test_an_unqualified_benefit_fails():
    errors = audit_text("这个方案提升推理吞吐。它解决显存问题。", ALL_BEATS)
    assert any("unqualified benefit" in message for message in errors), errors


def test_a_qualified_benefit_passes():
    errors = audit_text("在相同配置下，这个方案可能提升推理吞吐。", ALL_BEATS)
    assert not any("unqualified benefit" in message for message in errors), errors


def main() -> int:
    tests = (
        test_slugify_is_stable_and_portable,
        test_content_id_shape_is_enforced,
        test_next_content_id_allocates_the_first_free_sequence,
        test_package_path_cannot_escape_the_root,
        test_a_complete_delivery_manifest_passes,
        test_a_delivery_without_a_video_role_fails,
        test_an_absolute_delivery_path_fails,
        test_delivery_requires_current_stage_gates,
        test_an_unknown_human_review_state_fails,
        test_scene_classification_prefers_evidence,
        test_a_consistent_route_plan_passes,
        test_a_generated_scene_cannot_carry_an_exact_token,
        test_three_consecutive_generated_scenes_fail,
        test_route_flags_must_match_the_route,
        test_a_complete_strategy_card_passes,
        test_an_angle_must_belong_to_its_shelf,
        test_three_distinct_hooks_are_required,
        test_required_argument_beats_are_enforced,
        test_an_unknown_duration_tier_fails,
        test_a_non_technical_script_is_not_judged_by_this_gate,
        test_a_complete_technical_explainer_passes,
        test_missing_beats_fail,
        test_an_unqualified_benefit_fails,
        test_a_qualified_benefit_passes,
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
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print("\nAll naming/delivery/route/strategy tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
