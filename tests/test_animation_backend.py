"""Animation clip backend: selection, account rules, and receipt bounds.

Run: python tests/test_animation_backend.py
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

from contentops.media import animation_backend as ab  # noqa: E402
import m5_production  # noqa: E402


PALETTE = {"bg": "#F4F2ED", "ink": "#18232B", "accent": "#087FA6", "surface": "#FFFFFF"}
READY = {"remotion": True, "huashu-art-motion": True, "manim": False, "motion-canvas": False}


def test_missing_account_is_blocked():
    result = ab.select_backend(account_id="", shot_type="annotation", readiness=READY)
    assert result["state"] == "BLOCKED"
    assert result["code"] == "ACCOUNT_REQUIRED"
    assert result["publish_authorized"] is False


def test_unknown_account_is_blocked():
    result = ab.select_backend(account_id="x-superplay-english", shot_type="annotation",
                               readiness=READY)
    assert result["code"] == "UNKNOWN_ACCOUNT"


def test_explicit_backend_is_not_silently_replaced():
    result = ab.select_backend(
        account_id=ab.ACCOUNT_FUTURE, shot_type="architecture", explicit="remotion",
        readiness={"remotion": False, "huashu-art-motion": True}, purpose="production",
    )
    assert result["code"] == "RUNTIME_NOT_READY"
    assert result["substituted"] is False
    assert result["backend"] is None


def test_declared_compatible_fallback_may_run():
    result = ab.select_backend(
        account_id=ab.ACCOUNT_FUTURE, shot_type="architecture", explicit="motion-canvas",
        readiness={"motion-canvas": False, "remotion": True},
        declared_fallbacks=("remotion",), purpose="production",
    )
    assert result["state"] == "SELECTED"
    assert result["backend"] == "remotion"
    assert result["substituted"] is True
    assert result["fallback_of"] == "motion-canvas"


def test_math_does_not_silently_become_remotion():
    result = ab.select_backend(
        account_id=ab.ACCOUNT_FUTURE, shot_type="math", explicit="manim",
        readiness={"manim": False, "remotion": True},
        declared_fallbacks=("remotion",), purpose="production",
    )
    assert result["code"] == "RUNTIME_NOT_READY"
    assert result["substituted"] is False


def test_future_intelligence_refuses_a_desktop_recording():
    result = ab.select_backend(
        account_id=ab.ACCOUNT_FUTURE, shot_type="architecture", explicit="remotion",
        readiness=READY, input_kind="desktop_recording", purpose="production",
    )
    assert result["code"] == "RECORDING_FORBIDDEN"


def test_1024_production_without_recording_is_blocked():
    result = ab.select_backend(
        account_id=ab.ACCOUNT_1024, shot_type="annotation", explicit="remotion",
        readiness=READY, purpose="production", has_real_recording=False,
    )
    assert result["code"] == "MISSING_REAL_RECORDING"
    gate = ab.production_gate(account_id=ab.ACCOUNT_1024, has_real_recording=False)
    assert gate["state"] == "BLOCKED"
    assert gate["production_ready"] is False


def test_1024_test_render_can_be_selected_and_stays_non_evidence():
    result = ab.select_backend(
        account_id=ab.ACCOUNT_1024, shot_type="annotation", explicit="remotion",
        readiness=READY, purpose="test",
    )
    assert result["state"] == "SELECTED"
    assert result["counts_as_real_recording"] is False
    assert result["evidence_capable"] is False
    assert result["execution_authorized"] is False


def test_future_intelligence_vector_clip_is_technical_only():
    result = ab.select_backend(
        account_id=ab.ACCOUNT_FUTURE, shot_type="architecture", explicit="remotion",
        readiness=READY, purpose="production",
    )
    assert result["backend"] == "remotion"
    gate = ab.production_gate(account_id=ab.ACCOUNT_FUTURE, has_real_recording=False)
    assert gate["code"] == "EXPLANATORY_CLIP"
    assert gate["publish_authorized"] is False


def test_receipt_rejects_a_host_path_and_marks_generated():
    try:
        ab.build_receipt(
            project_id="demo", account_id=ab.ACCOUNT_FUTURE, placement_id="s1",
            asset_id="a1", backend="remotion", template="rag_flow",
            output_path="C:/Temp/clip.mp4", sha256="a" * 64, probe={},
            purpose="test", source_spec="project://motion/spec.json",
            version=ab.REMOTION_VERSION,
        )
    except ab.AnimationError as exc:
        assert exc.code == "PATH"
    else:
        raise AssertionError("host path was accepted")
    receipt = ab.build_receipt(
        project_id="demo", account_id=ab.ACCOUNT_FUTURE, placement_id="s1",
        asset_id="a1", backend="remotion", template="rag_flow",
        output_path="project://assets/generated/remotion/a1.mp4", sha256="ab" * 32,
        probe={"width": 1080, "height": 1920, "codec_name": "h264", "has_audio": False},
        purpose="test", source_spec="project://motion/spec.json",
        version=ab.REMOTION_VERSION,
    )
    assert receipt["generated"] is True
    assert receipt["evidence_capable"] is False
    assert receipt["counts_as_real_recording"] is False
    assert receipt["source_kind"] == "vector_animation"
    assert receipt["production_ready"] is False


def test_unknown_skill_is_not_an_execution_grant():
    missing = ab.resolve_skill("not-a-skill", ab.REMOTION_SKILLS)
    assert missing["code"] == "UNKNOWN_SKILL"
    found = ab.resolve_skill("remotion-render", ["remotion-render"])
    assert found["state"] == "DISCOVERED"
    assert found["execution_authorized"] is False


def test_version_mismatch_and_missing_runtime_are_blocked():
    mismatch = ab.preflight("remotion", {"node": True, "ffmpeg": True, "browser": True,
                                         "node_modules": True, "pinned_version": "9.9.9"})
    assert mismatch["code"] == "VERSION_MISMATCH"
    missing = ab.preflight("remotion", {"node": False, "ffmpeg": True, "browser": True,
                                        "node_modules": False, "pinned_version": ab.REMOTION_VERSION})
    assert missing["code"] == "RUNTIME_MISSING"
    canvas = ab.preflight("motion-canvas", {"node": True, "ffmpeg": True, "headless_export": False})
    assert canvas["code"] == "NO_HEADLESS_EXPORT"


def test_plan_requires_parameters():
    try:
        ab.plan_clip(account_id=ab.ACCOUNT_FUTURE, template="rag_flow", placement_id="s1",
                     asset_id="a1", props={"nodes": ["only-one"], "palette": PALETTE})
    except ab.AnimationError as exc:
        assert exc.code == "PROPS"
    else:
        raise AssertionError("a one-node flow was accepted")
    plan = ab.plan_clip(
        account_id=ab.ACCOUNT_1024, template="annotation", placement_id="s1", asset_id="a1",
        props={"title": "裁切", "left_label": "无关窗口", "right_label": "证据区域",
               "callout": "只留结论", "palette": PALETTE},
    )
    assert plan["composition"] == "AnnotationCard"
    assert plan["counts_as_real_recording"] is False


def test_m5_accepts_remotion_and_still_rejects_an_unknown_name():
    assert m5_production._select_motion_backend({"backend": "remotion"}, None) == "remotion"
    assert m5_production._select_motion_backend({}, "art-motion") == "huashu-art-motion"
    try:
        m5_production._select_motion_backend({"backend": "other"}, "huashu-art-motion")
    except m5_production.M5Blocked as exc:
        assert "unsupported motion backend" in str(exc)
    else:
        raise AssertionError("unknown backend was accepted")


def test_m5_dispatches_an_explicit_remotion_shot_to_the_clip_adapter():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        plan_path = project / "motion" / "plan.json"
        plan_path.parent.mkdir()
        plan_path.write_text(json.dumps({"shots": [{
            "id": "line-1",
            "asset_id": "clip-1",
            "spec": "motion/rag.json",
            "source_asset_id": "src-1",
            "backend": "remotion",
            "purpose": "test",
        }]}), encoding="utf-8")
        commands = []
        old_run = m5_production.hidden_run

        def fake_run(command, **_options):
            commands.append(command)
            payload = {"execution": {"state": "EXECUTED", "reused": False,
                                     "adapter_receipt": "project://receipts/animation-clip-1.json"}}
            return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

        m5_production.hidden_run = fake_run
        try:
            result = m5_production.stage_motion(
                project,
                {"motion": {"backend": "remotion", "shot_plan": "motion/plan.json"}},
                {"lines": [{"id": "line-1", "asset_id": "src-1"}]},
                require_copy_review=False,
            )
        finally:
            m5_production.hidden_run = old_run
    assert result["state"] == "OK"
    assert result["backend"] == "remotion"
    joined = " ".join(commands[0])
    assert "animation_render.py" in joined
    assert "huashu_motion" not in joined
    assert "--purpose" in commands[0] and "test" in commands[0]


def test_m5_does_not_auto_plan_huashu_for_a_clip_backend():
    with tempfile.TemporaryDirectory() as temp:
        try:
            m5_production.stage_motion(
                Path(temp),
                {"motion": {"backend": "remotion"}},
                {"lines": [{"id": "line-1", "asset_id": "src-1"}]},
                require_copy_review=False,
            )
        except m5_production.M5Blocked as exc:
            assert "shot_plan" in str(exc)
        else:
            raise AssertionError("remotion fell through to the Huashu auto-plan")


def test_palette_comes_from_account_dna_not_a_hardcoded_brand():
    dna = {"visual": {"motion": {"motion_profile": {"palette": {
        "bg": "#111111", "ink": "#eeeeee", "accent": "#ff00aa",
    }}}}}
    palette = ab.palette_from_dna(dna)
    assert palette["accent"] == "#ff00aa"


TESTS = [value for name, value in sorted(globals().items())
         if name.startswith("test_") and callable(value)]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
            print(f"ok   {test.__name__}")
        except Exception as exc:  # noqa: BLE001 - the runner reports, it does not hide
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
    total = len(TESTS)
    print(f"{total - failures}/{total} ok")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
