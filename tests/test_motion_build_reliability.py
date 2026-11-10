"""Reliability tests for motion render reuse and composer envelopes."""
from __future__ import annotations

import hashlib
import inspect
import json
import tempfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_motion_film as motion  # noqa: E402
from contentops.media import huashu_motion  # noqa: E402


def test_unverified_cache_never_skips_render():
    source = inspect.getsource(motion.build)
    assert "cache unverified; rendering again" in source
    assert "_render_is_reusable" not in source
    assert "staged.unlink" not in source


def test_compose_envelope_must_be_success_json():
    envelope = {"status": "OK", "output": {"path": "film.mp4"}}
    assert motion._compose_outcome("notice\n" + json.dumps(envelope, indent=2)) == (True, envelope)
    assert motion._compose_outcome("ffmpeg notice\nnot json") == (False, None)
    assert motion._compose_outcome('{"status":"BLOCKED"}') == (False, {"status": "BLOCKED"})
    assert motion._compose_outcome(json.dumps(envelope) + "\ntrailing error") == (False, None)


def test_composer_output_is_bound_to_the_actual_file():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        output = project / "final" / "easel.mp4"
        output.parent.mkdir()
        output.write_bytes(b"actual render")
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        result = {"output": {"path": "project://final/easel.mp4", "sha256": digest}}
        assert motion._compose_output_matches(project, result)
        output.write_bytes(b"modified render")
        assert not motion._compose_output_matches(project, result)
        assert not motion._compose_output_matches(project, {"output": {"path": "project://../outside", "sha256": digest}})


def test_art_motion_runtime_requires_exact_clean_upstream_checkout():
    lock = {
        "schema": "contentops.huashu-art-motion-baseline/v1",
        "capability": "huashu-art-motion",
        "repository": "https://github.com/alchaincyf/huashu-art-motion.git",
        "version": "1.2.0",
        "commit": "8f0a349a18b4bdf802b8d58715a2259c3e1ce709",
        "entrypoint": "scripts/engine/render.py",
        "clip_schema": "scripts/engine/clip_schema.json",
        "font_registry": "scripts/engine/lib/fonts/index.json",
        "cjk_font": "scripts/engine/lib/fonts/NotoSerifJP-600.woff",
        "execution_authorized": False,
    }
    with tempfile.TemporaryDirectory() as temp:
        runtime = Path(temp) / "runtime"
        (runtime / "scripts" / "engine").mkdir(parents=True)
        (runtime / "scripts" / "engine" / "render.py").write_text("# pinned entrypoint\n", encoding="utf-8")
        (runtime / "LICENSE").write_text("MIT\n", encoding="utf-8")
        engine = runtime / "scripts" / "engine"
        (engine / "clip_schema.json").write_text("{}\n", encoding="utf-8")
        fonts = engine / "lib" / "fonts"
        fonts.mkdir(parents=True)
        (fonts / "index.json").write_text(
            json.dumps([["NotoSerifJP-600.woff", "Noto Serif JP", "normal", "600"]]),
            encoding="utf-8",
        )
        (fonts / "NotoSerifJP-600.woff").write_bytes(b"font fixture")

        values = {
            ("rev-parse", "HEAD"): lock["commit"],
            ("remote", "get-url", "origin"): lock["repository"],
            ("status", "--porcelain", "--untracked-files=all"): "",
        }
        def git_probe(_root, *args):
            value = values.get(tuple(args), "")
            return 0, value

        result = motion.verify_art_motion_runtime(runtime, lock=lock, git_probe=git_probe)
        assert result["status"] == "TRUSTED_RUNTIME", result
        assert result["engine"] == runtime / "scripts" / "engine" / "render.py"
        assert motion.art_motion_execution_blocker(lock) == "EXECUTION_NOT_AUTHORIZED"
        assert motion.art_motion_execution_blocker({
            "execution_authorized": True,
            "authorization_record": "forged local assertion",
        }) == "MANAGED_EXECUTION_GATE_REQUIRED"
        values[("rev-parse", "HEAD")] = "0" * 40
        assert motion.verify_art_motion_runtime(runtime, lock=lock, git_probe=git_probe)["status"] == "BLOCKED"
        values[("rev-parse", "HEAD")] = lock["commit"]
        values[("status", "--porcelain", "--untracked-files=all")] = " M scripts/engine/render.py"
        assert motion.verify_art_motion_runtime(runtime, lock=lock, git_probe=git_probe)["status"] == "BLOCKED"
        values[("status", "--porcelain", "--untracked-files=all")] = ""
        values[("remote", "get-url", "origin")] = "https://example.invalid/fork.git"
        assert motion.verify_art_motion_runtime(runtime, lock=lock, git_probe=git_probe)["status"] == "BLOCKED"


def test_art_motion_runtime_reports_missing_root_and_required_files_precisely():
    lock = {
        "schema": "contentops.huashu-art-motion-baseline/v1",
        "capability": "huashu-art-motion",
        "repository": "https://github.com/alchaincyf/huashu-art-motion.git",
        "version": "1.2.0",
        "commit": "8f0a349a18b4bdf802b8d58715a2259c3e1ce709",
        "entrypoint": "scripts/engine/render.py",
        "clip_schema": "scripts/engine/clip_schema.json",
        "font_registry": "scripts/engine/lib/fonts/index.json",
        "cjk_font": "scripts/engine/lib/fonts/NotoSerifJP-600.woff",
        "execution_authorized": False,
    }
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        missing_root = motion.verify_art_motion_runtime(base / "missing", lock=lock)
        assert missing_root["reason"] == "RUNTIME_ROOT_MISSING"

        runtime = base / "runtime"
        runtime.mkdir()
        assert motion.verify_art_motion_runtime(runtime, lock=lock)["reason"] == "ENTRYPOINT_MISSING"

        engine = runtime / "scripts" / "engine" / "render.py"
        engine.parent.mkdir(parents=True)
        engine.write_text("# pinned entrypoint\\n", encoding="utf-8")
        assert motion.verify_art_motion_runtime(runtime, lock=lock)["reason"] == "LICENSE_MISSING"

        (runtime / "LICENSE").write_text("MIT\\n", encoding="utf-8")
        engine = runtime / "scripts" / "engine"
        (engine / "clip_schema.json").write_text("{}\\n", encoding="utf-8")
        fonts = engine / "lib" / "fonts"
        fonts.mkdir(parents=True)
        (fonts / "index.json").write_text(
            json.dumps([["NotoSerifJP-600.woff", "Noto Serif JP", "normal", "600"]]),
            encoding="utf-8",
        )
        (fonts / "NotoSerifJP-600.woff").write_bytes(b"font fixture")
        values = {
            ("rev-parse", "HEAD"): lock["commit"],
            ("remote", "get-url", "origin"): lock["repository"],
            ("status", "--porcelain", "--untracked-files=all"): "",
        }
        def git_probe(_root, *args):
            return 0, values[tuple(args)]

        values[("rev-parse", "HEAD")] = "0" * 40
        assert motion.verify_art_motion_runtime(runtime, lock=lock, git_probe=git_probe)["reason"] == "COMMIT_MISMATCH"


def test_huashu_motion_runtime_is_pinned_and_checks_git_without_running_om():
    lock = json.loads((ROOT / "runtime" / "huashu-motion.lock.json").read_text(encoding="utf-8"))
    assert lock["version"] == "0.3.1"
    assert lock["commit"] == "52467f99c602b76ba86d511d37acdfe93fa1e16e"
    assert lock["execution_authorized"] is False
    with tempfile.TemporaryDirectory() as temp:
        runtime = Path(temp) / "runtime"
        (runtime / "skills" / "huashu-motion" / "bin").mkdir(parents=True)
        (runtime / "skills" / "huashu-motion" / "bin" / "om").write_text(
            "#!/bin/sh\\n", encoding="utf-8")
        (runtime / "cli").mkdir(parents=True)
        (runtime / "cli" / "om.js").write_text("// pinned dispatcher\\n", encoding="utf-8")
        (runtime / "LICENSE").write_text("MIT\\n", encoding="utf-8")
        values = {
            ("rev-parse", "HEAD"): huashu_motion.COMMIT,
            ("remote", "get-url", "origin"): huashu_motion.REPOSITORY,
            ("status", "--porcelain", "--untracked-files=all"): "",
        }
        def git_probe(_root, *args):
            return 0, values[tuple(args)]
        verified = huashu_motion.verify_runtime(runtime, lock=lock, git_probe=git_probe)
        assert verified["status"] == "TRUSTED_RUNTIME", verified
        values[("rev-parse", "HEAD")] = "0" * 40
        assert huashu_motion.verify_runtime(runtime, lock=lock, git_probe=git_probe)["reason"] == "COMMIT_MISMATCH"


def test_huashu_motion_operations_are_descriptive_and_default_blocked():
    called = []
    def mock_runner(*args, **kwargs):
        called.append((args, kwargs))
        return {"ok": True}
    for operation in ("check", "still", "render", "qa"):
        plan = huashu_motion.describe_operation(operation)
        assert plan["command"].startswith(f"om {operation}")
        result = huashu_motion.request_operation(
            operation, runtime={"status": "TRUSTED_RUNTIME", "execution_authorized": True},
            runner=mock_runner,
        )
        assert result["status"] == "BLOCKED"
        assert result["execution_status"] == "NOT_EXECUTED"
        assert result["runner_invoked"] is False
    assert called == []


def test_huashu_motion_output_is_hash_bound_silent_and_support_only():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "project"
        output = project / "work" / "shot.mp4"
        output.parent.mkdir(parents=True)
        output.write_bytes(b"synthetic bytes for contract test")
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        probe = {
            "duration_s": 4.0, "width": 1080, "height": 1920,
            "codec_name": "h264", "pix_fmt": "yuv420p",
            "avg_frame_rate": "30/1", "r_frame_rate": "30/1",
            "has_audio": False, "frame_timestamps": [i / 30 for i in range(120)],
        }
        record = huashu_motion.validate_output(
            output, project_root=project, expected_sha256=digest,
            spec_sha256="a" * 64, input_asset_hashes={"input-1": "b" * 64},
            probe=probe, audio_policy="MUTE",
        )
        assert record["clip_sha256"] == digest
        assert record["asset_hashes"] == {"input-1": "b" * 64}
        assert record["generated"] is True and record["evidence_capable"] is False
        assert record["production_ready"] is False
        envelope = huashu_motion.make_envelope(
            record, asset_id="motion-1", placement_id="place-1",
            receipt_ref="motion.mp4.receipt.json", derived_from="motion-source",
            transform_receipt_ref="motion.transform.json",
        )
        assert envelope.generated and not envelope.evidence_capable
        assert envelope.derived_from == "motion-source"
        try:
            huashu_motion.validate_output(
                output, project_root=project, expected_sha256="0" * 64,
                spec_sha256="a" * 64, probe=probe, audio_policy="MUTE",
            )
        except huashu_motion.HuashuMotionError:
            pass
        else:
            raise AssertionError("digest mismatch must be refused")
        try:
            huashu_motion.validate_output(
                output, project_root=project, expected_sha256=digest,
                spec_sha256="a" * 64, probe={**probe, "has_audio": True}, audio_policy="REPLACE",
            )
        except huashu_motion.HuashuMotionError:
            pass
        else:
            raise AssertionError("audio in a MUTE/REPLACE clip must be refused")


def test_art_motion_spec_binds_cjk_font_input_hash_and_vertical_timing():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        project = root / "project"
        runtime = root / "runtime"
        spec_dir = project / "motion" / "specs"
        spec_dir.mkdir(parents=True)
        fonts = runtime / "scripts" / "engine" / "lib" / "fonts"
        fonts.mkdir(parents=True)
        (fonts / "index.json").write_text(
            json.dumps([["NotoSerifJP-600.woff", "Noto Serif JP", "normal", "600"]]),
            encoding="utf-8",
        )
        (fonts / "NotoSerifJP-600.woff").write_bytes(b"pinned font fixture")
        (project / "motion" / "workflow.png").write_bytes(b"mock input asset")
        spec_path = spec_dir / "p01.json"
        spec_path.write_text(json.dumps({
            "grammar": "t2_keynote_ui", "duration": 5, "fps": 30,
            "width": 1080, "height": 1920, "theme": "paper",
            "cues": [{"at": 0, "kind": "title", "text": "任务进入队列",
                      "image": "motion/workflow.png"}],
        }, ensure_ascii=False), encoding="utf-8")
        binding = motion.validate_art_motion_spec(
            spec_path, project_root=project, runtime_root=runtime, render_duration_s=5.0,
        )
        assert binding["resolution"] == "1080x1920" and binding["fps"] == 30
        assert binding["spec_sha256"] == hashlib.sha256(spec_path.read_bytes()).hexdigest()
        assert "motion/workflow.png" in binding["input_asset_hashes"]
        assert binding["font_review_status"] == "CJK_GLYPH_VISUAL_REVIEW_REQUIRED"
        assert binding["audio_policy"] == "REPLACE"

        invalid = json.loads(spec_path.read_text(encoding="utf-8"))
        invalid["width"] = 1920
        spec_path.write_text(json.dumps(invalid, ensure_ascii=False), encoding="utf-8")
        try:
            motion.validate_art_motion_spec(
                spec_path, project_root=project, runtime_root=runtime, render_duration_s=5.0,
            )
        except ValueError as exc:
            assert "1080x1920" in str(exc)
        else:
            raise AssertionError("non-portrait Art Motion spec must be refused")


def test_art_motion_output_uses_shared_generated_support_contract():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "project"
        output = project / "work" / "p01.mp4"
        output.parent.mkdir(parents=True)
        output.write_bytes(b"mock art-motion output")
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        probe = {
            "duration_s": 4.0, "width": 1080, "height": 1920,
            "codec_name": "h264", "pix_fmt": "yuv420p",
            "avg_frame_rate": "30/1", "r_frame_rate": "30/1",
            "has_audio": False, "frame_timestamps": [i / 30 for i in range(120)],
        }
        binding = {
            "schema": "contentops.huashu-art-motion-render-binding/v1",
            "spec_sha256": "a" * 64,
            "input_asset_hashes": {"workflow": "b" * 64},
            "font_family": "Noto Serif JP",
            "font_review_status": "CJK_GLYPH_VISUAL_REVIEW_REQUIRED",
        }
        record = motion.validate_art_motion_output(
            output, project_root=project, expected_sha256=digest, probe=probe,
            render_binding=binding,
        )
        assert record["clip_path"] == "project://work/p01.mp4"
        assert record["rights"] == "UNRESOLVED"
        assert record["generated"] and not record["evidence_capable"]
        assert not record["production_ready"] and not record["publish_authorized"]
        envelope = motion.make_art_motion_envelope(
            record, asset_id="p01-motion", placement_id="p01",
            receipt_ref="p01.mp4.receipt.json", derived_from="p01-source",
            transform_receipt_ref="p01.transform.json",
        )
        assert envelope.generated and envelope.derived_from == "p01-source"


def test_art_motion_default_runtime_path_is_portable_and_execution_is_blocked():
    assert "C:\\Users\\Administrator" not in str(motion.DEFAULT_ART_MOTION_RUNTIME)
    assert motion.art_motion_execution_blocker({"execution_authorized": False}) == "EXECUTION_NOT_AUTHORIZED"
    assert motion.art_motion_execution_blocker({"execution_authorized": True}) == "MANAGED_EXECUTION_GATE_REQUIRED"


def test_art_motion_resolution_uses_a_distinct_blocked_exception():
    with tempfile.TemporaryDirectory() as temp:
        try:
            motion.resolve_art_motion_engine(Path(temp))
        except motion.MotionExecutionBlocked as exc:
            assert "unsupported art-motion runtime location" in str(exc)
        else:
            raise AssertionError("unapproved runtime path was not blocked")


def main() -> int:
    tests = (test_unverified_cache_never_skips_render,
             test_compose_envelope_must_be_success_json,
             test_composer_output_is_bound_to_the_actual_file,
             test_art_motion_runtime_requires_exact_clean_upstream_checkout,
             test_art_motion_runtime_reports_missing_root_and_required_files_precisely,
             test_huashu_motion_runtime_is_pinned_and_checks_git_without_running_om,
             test_huashu_motion_operations_are_descriptive_and_default_blocked,
             test_huashu_motion_output_is_hash_bound_silent_and_support_only,
             test_art_motion_spec_binds_cjk_font_input_hash_and_vertical_timing,
             test_art_motion_output_uses_shared_generated_support_contract,
             test_art_motion_default_runtime_path_is_portable_and_execution_is_blocked,
             test_art_motion_resolution_uses_a_distinct_blocked_exception)
    for test in tests:
        test()
        print(f"[ok] {test.__name__}")
    print(f"All {len(tests)} motion reliability tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
