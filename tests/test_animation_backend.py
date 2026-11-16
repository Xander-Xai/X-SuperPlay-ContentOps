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
from animation_render import _registered_recording, _trusted_recording, _stage_recording_public, render  # noqa: E402


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


def test_current_account_dna_brand_palette_wins_over_legacy_motion_profile():
    for account in (ab.ACCOUNT_1024, ab.ACCOUNT_FUTURE):
        dna = json.loads((ROOT / "config" / "accounts" / f"{account}.json").read_text(encoding="utf-8"))
        palette = ab.palette_from_dna(dna)
        assert palette["bg"] == "#0F1117"
        assert palette["accent"] == "#38BDF8"
    dna = json.loads((ROOT / "config" / "accounts" / f"{ab.ACCOUNT_1024}.json").read_text(encoding="utf-8"))
    props = {"title": "x", "left_label": "a", "right_label": "b", "callout": "c",
             "palette": {"bg": "#ffffff", "accent": "#000000", "ink": "#000000"}}
    props = {"title": "x", "left_label": "a", "right_label": "b", "callout": "c",
             "palette": {"bg": "#ffffff", "accent": "#000000", "ink": "#000000"}}
    spec = {"template": "annotation", "duration_s": 4, "props": props}
    effective = ab.palette_from_dna(dna)
    from animation_render import _composition_props
    rendered = _composition_props(spec, "test", effective)
    assert rendered["palette"]["bg"] == effective["bg"]
    assert rendered["palette"]["accent"] == effective["accent"]
    assert effective["bg"] == "#0F1117" and effective["accent"] == "#38BDF8"


def test_installed_runtime_cli_and_core_must_match_lock():
    import animation_render
    from unittest import mock

    lock = json.loads((ROOT / "extensions/animation-remotion/package-lock.json").read_text(encoding="utf-8"))
    assert lock["packages"]["node_modules/remotion"]["version"] == ab.REMOTION_VERSION
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        (root / "package-lock.json").write_text(json.dumps(lock), encoding="utf-8")
        cli = root / "node_modules/@remotion/cli/remotion-cli.js"
        core = root / "node_modules/remotion/package.json"
        cli.parent.mkdir(parents=True)
        core.parent.mkdir(parents=True)
        cli.write_text("", encoding="utf-8")
        with mock.patch.object(animation_render, "REMOTION_ROOT", root), \
             mock.patch.object(animation_render, "CLI", cli), \
             mock.patch.object(animation_render, "_which", return_value=True), \
             mock.patch.object(animation_render, "_browser", return_value=Path("browser")), \
             mock.patch.object(animation_render, "hidden_run") as run:
            for cli_version, core_version, expected in (
                (ab.REMOTION_VERSION, ab.REMOTION_VERSION, "READY"),
                ("0.0.0", ab.REMOTION_VERSION, "VERSION_MISMATCH"),
                (ab.REMOTION_VERSION, "0.0.0", "VERSION_MISMATCH"),
                (ab.REMOTION_VERSION, None, "VERSION_MISMATCH"),
            ):
                core.write_text(json.dumps({"version": core_version}), encoding="utf-8")
                run.return_value = SimpleNamespace(returncode=0, stdout=cli_version, stderr="")
                probe = animation_render.environment_probe("remotion")
                assert probe["pinned_version"] == ab.REMOTION_VERSION
                assert probe["installed_cli_version"] == cli_version
                assert probe["installed_core_version"] == core_version
                assert ab.preflight("remotion", probe)["code"] == expected
            cli.unlink()
            probe = animation_render.environment_probe("remotion")
            assert probe["installed_cli_version"] is None
            assert ab.preflight("remotion", probe)["code"] == "RUNTIME_MISSING"


def test_recording_public_staging_is_project_contained_private_and_hash_verified():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "project"
        project.mkdir()
        source = project / "assets" / "recording.mp4"
        source.parent.mkdir()
        source.write_bytes(b"verified recording bytes")
        digest = __import__("hashlib").sha256(source.read_bytes()).hexdigest()
        first_handle, first_public, first_relative = _stage_recording_public(project, source, digest)
        second_handle, second_public, second_relative = _stage_recording_public(project, source, digest)
        try:
            assert first_public != second_public
            assert first_relative == second_relative
            assert first_relative.startswith("recordings/")
            assert (first_public / first_relative).read_bytes() == source.read_bytes()
            assert not first_relative.startswith("file:")
            assert first_public.parent == (project / "work" / "animation").resolve()
        finally:
            first_handle.cleanup()
            second_handle.cleanup()
        assert not first_public.exists() and not second_public.exists()


def test_recording_public_staging_rejects_hash_mismatch_and_path_escape():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "project"
        project.mkdir()
        outside = Path(temp) / "outside.mp4"
        outside.write_bytes(b"outside")
        digest = __import__("hashlib").sha256(outside.read_bytes()).hexdigest()
        for source, expected in ((outside, digest), (outside, "0" * 64)):
            try:
                _stage_recording_public(project, source, expected)
            except ValueError:
                pass
            else:
                raise AssertionError("outside or mismatched recording was staged")


def test_recording_mark_composition_receives_only_public_relative_video_path():
    from animation_render import _composition_props
    spec = {"template": "recording_mark", "duration_s": 3,
            "props": {"title": "t", "note": "n", "box": {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4}}}
    payload = _composition_props(spec, "test", PALETTE, video="recordings/abc.mp4", source_in_seconds=0.5)
    assert payload["video"] == "recordings/abc.mp4"
    assert not payload["video"].startswith(("file:", "/", "C:"))
    assert payload["sourceInSeconds"] == 0.5


def test_recording_public_staging_applies_only_the_declared_crop_before_exposure():
    from unittest import mock
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "project"
        project.mkdir()
        source = project / "recordings" / "source.mp4"
        source.parent.mkdir()
        source.write_bytes(b"source movie bytes")
        digest = __import__("hashlib").sha256(source.read_bytes()).hexdigest()
        commands = []

        def fake_ffmpeg(command, **_kwargs):
            commands.append(command)
            Path(command[-1]).write_bytes(b"cropped sanitized movie")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        with mock.patch("animation_render.hidden_run", side_effect=fake_ffmpeg):
            handle, public, relative = _stage_recording_public(
                project, source, digest, crop={"x": 12, "y": 34, "width": 320, "height": 480},
            )
        try:
            command = commands[0]
            assert "crop=320:480:12:34" in command[command.index("-vf") + 1]
            staged = public / relative
            assert staged.read_bytes() == b"cropped sanitized movie"
            assert staged.read_bytes() != source.read_bytes()
            assert str(source) == command[command.index("-i") + 1]
            assert str(staged) == command[-1]
        finally:
            handle.cleanup()


def test_motion_check_receipt_omits_host_paths():
    from animation_render import _safe_motion_check
    safe = _safe_motion_check({"state": "TECHNICALLY_CHECKED", "path": r"D:\\private\\project\\clip.mp4",
                               "duration_s": 4.0})
    assert safe == {"state": "TECHNICALLY_CHECKED", "duration_s": 4.0}


def test_registered_recording_needs_crop_source_permission_and_hash(tmp=None):
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        (project / "sources").mkdir()
        asset = {"id": "screen-1", "type": "recording", "origin": "SELF_CAPTURED",
                 "permission": "SELF_CAPTURED_CROPPED", "evidence_capable": True,
                 "crop": {"x": 0, "y": 0, "width": 100, "height": 100},
                 "source_ref": "capture-1", "repo_path": "screen.mp4", "sha256": "a" * 64}
        (project / "sources" / "assets.json").write_text(json.dumps({"assets": [asset]}), encoding="utf-8")
        (project / "sources" / "source-refs.json").write_text(json.dumps({"refs": [{
            "id": "capture-1", "permission": "CREATED_BY_OWNER",
        }]}), encoding="utf-8")
        assert _registered_recording(project, "screen-1") is not None
        asset.pop("crop")
        (project / "sources" / "assets.json").write_text(json.dumps({"assets": [asset]}), encoding="utf-8")
        assert _registered_recording(project, "screen-1") is None


def test_renderer_never_trusts_shot_has_real_recording_true():
    from unittest import mock
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        (project / "motion").mkdir()
        (project / "sources").mkdir()
        (project / "motion" / "spec.json").write_text(json.dumps({
            "backend": "remotion", "template": "annotation", "shot_type": "annotation",
            "duration_s": 4,
            "props": {"title": "t", "left_label": "a", "right_label": "b", "callout": "c"},
        }), encoding="utf-8")
        (project / "sources" / "assets.json").write_text(json.dumps({"assets": []}), encoding="utf-8")
        out = []
        with mock.patch("animation_render._emit", side_effect=lambda payload, code: out.append(payload) or code):
            result = render(project, Path("motion/spec.json"), placement_id="p1", asset_id="a1",
                            account_id=ab.ACCOUNT_1024, purpose="production")
        assert result == 1
        assert out[0]["decision"]["code"] == "MISSING_REAL_RECORDING"


def test_future_intelligence_rejects_recording_mark_input():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        (project / "motion").mkdir()
        (project / "motion" / "spec.json").write_text(json.dumps({
            "backend": "remotion", "template": "recording_mark", "shot_type": "recording_mark",
            "duration_s": 4,
            "props": {"recording_asset_id": "screen-1", "title": "t", "note": "n",
                      "box": {"x": 0.1, "y": 0.1, "w": 0.4, "h": 0.3}},
        }), encoding="utf-8")
        out = []
        from unittest import mock
        with mock.patch("animation_render._emit", side_effect=lambda payload, code: out.append(payload) or code):
            result = render(project, Path("motion/spec.json"), placement_id="p1", asset_id="a1",
                            account_id=ab.ACCOUNT_FUTURE, purpose="production")
        assert result == 1
        assert out[0]["decision"]["code"] == "ACCOUNT_TEMPLATE_FORBIDDEN"


def test_recording_mark_plan_requires_registered_input_reference():
    try:
        ab.plan_clip(account_id=ab.ACCOUNT_1024, template="recording_mark", placement_id="p1",
                     asset_id="a1", duration_s=4,
                     props={"title": "重点", "note": "区域", "recording_asset_id": "screen-1",
                            "box": {"x": 0.1, "y": 0.1, "w": 0.5, "h": 0.5},
                            "palette": ab.palette_from_dna(json.loads((ROOT / "config" / "accounts" / f"{ab.ACCOUNT_1024}.json").read_text(encoding="utf-8")))})
    except ab.AnimationError as exc:
        raise AssertionError(str(exc))
    try:
        ab.plan_clip(account_id=ab.ACCOUNT_1024, template="recording_mark", placement_id="p1",
                     asset_id="a1", duration_s=4,
                     props={"title": "重点", "note": "区域", "box": {"x": 0, "y": 0, "w": 1, "h": 1},
                            "palette": {"bg": "#0F1117", "ink": "#ffffff", "accent": "#38BDF8"}})
    except ab.AnimationError as exc:
        assert exc.code == "PROPS"
    else:
        raise AssertionError("recording mark without an asset id was accepted")


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
            import traceback
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
            traceback.print_exc()
    total = len(TESTS)
    print(f"{total - failures}/{total} ok")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
