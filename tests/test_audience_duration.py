"""Audience Lens and duration-policy tests.

Run: python tests/test_audience_duration.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.workflow.audience import validate_audience_insight  # noqa: E402
from contentops.workflow.duration import (  # noqa: E402
    default_policy,
    normalize_policy,
    tier_for_content_type,
    validate_duration,
    validate_script_duration,
)


def _audience(**overrides):
    document = {
        "schema": "contentops.audience-insight/v1",
        "primary_segment": "capability_decider",
        "trigger_context": "刚看到一个模型发布，想知道值不值得试",
        "current_workaround": "刷几条二手评测和群聊截图",
        "pain_or_cost": "花两小时仍然不知道能不能放进真实工作",
        "desired_progress": "十分钟内决定投入还是放弃",
        "proof_needed": "同一任务的前后对比、耗时和失败点",
        "opposition": "怕又是一条营销稿",
        "value_type": "cognitive",
        "emotion_from": "不确定",
        "emotion_to": "有判断",
        "conclusion_status": "validated",
        "sources": [
            {"kind": "direct", "ref": "comment:2026-10-27#c1"},
            {"kind": "secondary", "ref": "doc:changelog"},
        ],
    }
    document.update(overrides)
    return document


def test_a_complete_audience_document_passes():
    assert validate_audience_insight(_audience()) == []


def test_a_missing_proof_requirement_fails():
    errors = validate_audience_insight(_audience(proof_needed=""))
    assert any("proof_needed" in message for message in errors), errors


def test_a_broad_audience_term_fails():
    errors = validate_audience_insight(_audience(trigger_context="所有人都在聊这个"))
    assert any("broad audience term" in message for message in errors), errors


def test_validated_requires_two_sources_and_one_direct():
    one = validate_audience_insight(_audience(sources=[{"kind": "direct", "ref": "x"}]))
    assert any("two independent sources" in message for message in one), one
    indirect = validate_audience_insight(_audience(sources=[
        {"kind": "secondary", "ref": "a"}, {"kind": "secondary", "ref": "b"}]))
    assert any("direct audience signal" in message for message in indirect), indirect


def test_exploratory_requires_a_learnable_question_and_a_cta():
    errors = validate_audience_insight(_audience(conclusion_status="exploratory", sources=[]))
    assert any("learnable_question" in message for message in errors), errors
    assert any("cta" in message for message in errors), errors


def test_an_emotion_arc_needs_two_different_states():
    errors = validate_audience_insight(_audience(emotion_to="不确定"))
    assert any("identical" in message for message in errors), errors


def test_an_unknown_segment_fails():
    errors = validate_audience_insight(_audience(primary_segment="everyone"))
    assert any("primary_segment" in message for message in errors), errors


def test_content_type_resolves_to_its_tier():
    assert tier_for_content_type("tool_test") == "two_minute"
    assert tier_for_content_type("opinion") == "one_minute"
    assert tier_for_content_type("not_a_type") is None


def test_a_duration_inside_the_band_passes():
    assert validate_duration(120, content_type="tool_test") == []


def test_a_duration_outside_the_band_fails():
    errors = validate_duration(200, content_type="tool_test")
    assert any("outside" in message for message in errors), errors


def test_an_unknown_content_type_fails():
    errors = validate_duration(60, content_type="not_a_type")
    assert any("no duration tier" in message for message in errors), errors


def test_tier_and_content_type_must_agree():
    errors = validate_duration(120, content_type="tool_test", tier="three_minute")
    assert any("maps to" in message for message in errors), errors


def test_a_custom_policy_overrides_the_defaults():
    policy = normalize_policy({
        "schema": "contentops.duration-policy/v1",
        "tiers": [{"id": "short", "target_seconds": 30,
                   "allowed_range_seconds": [20, 40]}],
        "content_type_defaults": {"tool_test": "short"},
    })
    assert validate_duration(30, content_type="tool_test", policy=policy) == []


def test_a_policy_with_a_target_outside_its_band_is_refused():
    try:
        normalize_policy({
            "schema": "contentops.duration-policy/v1",
            "tiers": [{"id": "bad", "target_seconds": 90,
                       "allowed_range_seconds": [20, 40]}],
            "content_type_defaults": {},
        })
    except ValueError:
        return
    raise AssertionError("a target outside its own band must be refused")


def test_the_default_policy_is_returned_when_none_is_supplied():
    assert default_policy()["schema"] == "contentops.duration-policy/v1"


def test_a_script_without_a_content_type_is_not_guess_graded():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "script.json"
        path.write_text(json.dumps({"target_seconds": 300}), encoding="utf-8")
        assert validate_script_duration(path) == []


def test_a_script_target_is_checked_against_its_content_type():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "script.json"
        path.write_text(json.dumps({"content_type": "tool_test", "target_seconds": 200}),
                        encoding="utf-8")
        errors = validate_script_duration(path)
    assert any("outside" in message for message in errors), errors


def main() -> int:
    tests = (
        test_a_complete_audience_document_passes,
        test_a_missing_proof_requirement_fails,
        test_a_broad_audience_term_fails,
        test_validated_requires_two_sources_and_one_direct,
        test_exploratory_requires_a_learnable_question_and_a_cta,
        test_an_emotion_arc_needs_two_different_states,
        test_an_unknown_segment_fails,
        test_content_type_resolves_to_its_tier,
        test_a_duration_inside_the_band_passes,
        test_a_duration_outside_the_band_fails,
        test_an_unknown_content_type_fails,
        test_tier_and_content_type_must_agree,
        test_a_custom_policy_overrides_the_defaults,
        test_a_policy_with_a_target_outside_its_band_is_refused,
        test_the_default_policy_is_returned_when_none_is_supplied,
        test_a_script_without_a_content_type_is_not_guess_graded,
        test_a_script_target_is_checked_against_its_content_type,
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
    print("\nAll audience and duration tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
