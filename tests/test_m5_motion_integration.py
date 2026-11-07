"""M5 must be able to place a video shot, and must never substitute a still or a
different voice when the declared one is unavailable.

The failure this prevents, twice over:

- M5 built its own storyboard with ``image`` and a literal ``"motion": "static"``,
  so a rendered clip in the manifest could not reach the composer at all;
- asking for a narration source the build could not reach returned a SAPI track
  that looked like a success.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from types import SimpleNamespace
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import m5_production  # noqa: E402
import produce_video  # noqa: E402
import huashu_motion_adapter  # noqa: E402
from contentops.media import storyboard_adapter as adapter  # noqa: E402


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _assets(temp: Path, *, video: bool = True) -> dict:
    media = temp / "work" / "media"
    media.mkdir(parents=True, exist_ok=True)
    name = "beat-00.mp4" if video else "beat-00.png"
    (media / name).write_bytes(b"placeholder bytes")
    return {"A1": {"repo_path": f"work/media/{name}",
                   "type": "video" if video else "screenshot"}}


def _lines():
    return [{"asset_id": "A1", "caption": "第一句", "narration": "第一句", "claim": "C1"}]


def _timings(seconds=5.0):
    return [{"duration": seconds}]


def test_a_video_asset_reaches_the_storyboard_as_a_clip():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        shots = adapter.build_shots(lines=_lines(), narration_lines=_timings(),
                                    assets=_assets(project), repo_root=project)
        assert shots[0]["video"] == "work/media/beat-00.mp4"
        assert shots[0]["source_type"] == "video"


def test_a_still_asset_is_not_labelled_a_clip():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        shots = adapter.build_shots(lines=_lines(), narration_lines=_timings(),
                                    assets=_assets(project, video=False), repo_root=project)
        assert "video" not in shots[0]
        assert shots[0]["image"] == "work/media/beat-00.png"


def test_the_composer_key_and_the_receipt_key_agree():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        shots = adapter.build_shots(lines=_lines(), narration_lines=_timings(4.25),
                                    assets=_assets(project), repo_root=project)
        assert shots[0]["duration"] == shots[0]["duration_s"] == 4.25


def test_a_missing_asset_stops_the_build():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        assets = _assets(project)
        (project / "work" / "media" / "beat-00.mp4").unlink()
        try:
            adapter.build_shots(lines=_lines(), narration_lines=_timings(),
                                assets=assets, repo_root=project)
        except adapter.StoryboardContractError as exc:
            assert "missing on disk" in str(exc), exc
        else:
            raise AssertionError("a missing clip must not silently become a still")


def test_a_non_positive_duration_stops_the_build():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        try:
            adapter.build_shots(lines=_lines(), narration_lines=_timings(0),
                                assets=_assets(project), repo_root=project)
        except adapter.StoryboardContractError:
            pass
        else:
            raise AssertionError("a zero-length shot must be refused")


def test_misaligned_lines_and_timings_stop_the_build():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        try:
            adapter.build_shots(lines=_lines(), narration_lines=[],
                                assets=_assets(project), repo_root=project)
        except adapter.StoryboardContractError as exc:
            assert "not aligned" in str(exc), exc
        else:
            raise AssertionError("an unaligned timeline must be refused")


def test_the_same_asset_can_support_multiple_timeline_placements():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        lines = _lines() + _lines()
        shots = adapter.build_shots(lines=lines, narration_lines=_timings() + _timings(),
                                    assets=_assets(project), repo_root=project)
        assert len(shots) == 2
        assert [shot["asset_id"] for shot in shots] == ["A1", "A1"]
        assert shots[0]["source"] == shots[1]["source"]
        assert shots[0]["shot_id"] != shots[1]["shot_id"]


def _script():
    return {"lines": _lines()}


def test_an_unreachable_narration_provider_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        try:
            m5_production.stage_narration(project, _script(), provider="minimax")
        except m5_production.M5Blocked as exc:
            assert "refusing to fall back" in str(exc), exc
        else:
            raise AssertionError("an unavailable provider must not silently use SAPI")


def test_existing_narration_without_a_receipt_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        audio = project / "voice.wav"
        audio.write_bytes(b"RIFF")
        try:
            m5_production.stage_narration(project, _script(), provider="existing",
                                          narration_audio=audio)
        except m5_production.M5Blocked as exc:
            assert "narration-receipt" in str(exc), exc
        else:
            raise AssertionError("audio without provenance must be refused")


def test_existing_narration_bound_to_another_script_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        audio = project / "voice.wav"
        audio.write_bytes(b"RIFF")
        receipt = project / "narration.json"
        receipt.write_text(json.dumps({"text_sha256": _sha("other script"),
                                       "lines": _timings()}), encoding="utf-8")
        try:
            m5_production.stage_narration(project, _script(), provider="existing",
                                          narration_audio=audio,
                                          narration_receipt=receipt)
        except m5_production.M5Blocked as exc:
            assert "not bound to the current script" in str(exc), exc
        else:
            raise AssertionError("audio that speaks another script must be refused")


def test_existing_narration_without_line_timings_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        audio = project / "voice.wav"
        audio.write_bytes(b"RIFF")
        text = "\n".join(line["narration"] for line in _lines())
        receipt = project / "narration.json"
        receipt.write_text(json.dumps({"text_sha256": _sha(text)}), encoding="utf-8")
        try:
            m5_production.stage_narration(project, _script(), provider="existing",
                                          narration_audio=audio,
                                          narration_receipt=receipt)
        except m5_production.M5Blocked as exc:
            assert "per-line timings" in str(exc), exc
        else:
            raise AssertionError("audio without timings cannot drive subtitles")


def test_existing_narration_that_matches_is_reused_without_a_provider_call():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        audio = project / "voice.wav"
        with wave.open(str(audio), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(8000)
            handle.writeframes(b"\x00\x00" * 4000)  # 0.5 s of silence
        text = "\n".join(line["narration"] for line in _lines())
        receipt = project / "narration.json"
        receipt.write_text(json.dumps({
            "engine": "speech-2.8-hd", "voice": "fixture",
            "text_sha256": _sha(text), "lines": _timings(0.5),
        }), encoding="utf-8")
        payload = m5_production.stage_narration(
            project, _script(), provider="existing",
            narration_audio=audio, narration_receipt=receipt)
        assert payload["voice_provider"] == "existing"
        assert payload["text_sha256"] == _sha(text)
        assert payload["network"] is False
        assert (project / "assets" / "voice" / "narration.wav").is_file()
        assert payload["duration_s"] > 0


def test_producer_reuses_current_qc_pass_without_rebuilding():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp).resolve()
        project = root / "projects" / "demo-project"
        (project / "script").mkdir(parents=True)
        (project / "sources").mkdir()
        (project / "project.yaml").write_text("id: demo-project\nsource_refs: []\n", encoding="utf-8")
        (project / "script" / "script.json").write_text("{}", encoding="utf-8")
        (project / "script" / "claims.json").write_text("{}", encoding="utf-8")
        (project / "sources" / "assets.json").write_text('{"assets": []}', encoding="utf-8")
        old_root, old_build = produce_video.ROOT, produce_video.m5_production.build
        calls = []

        build_options = []

        def fake_build(target, **options):
            calls.append(target)
            build_options.append(options)
            (target / "final").mkdir(parents=True, exist_ok=True)
            (target / "final" / "demo-project.mp4").write_bytes(b"rendered bytes")
            report = {"overall": "PASS", "graded_target": "project://final/demo-project.mp4"}
            (target / "receipts").mkdir(exist_ok=True)
            (target / "receipts" / "qc-report-demo-project.json").write_text(
                json.dumps(report), encoding="utf-8")
            return {"stages": {"compose": {"state": "OK"}, "qc": {"overall": "PASS"}},
                    "human_review": "PENDING_FOUNDER_REVIEW"}

        produce_video.ROOT = Path(str(root).swapcase()) if sys.platform == "win32" else root
        produce_video.m5_production.build = fake_build
        try:
            assert produce_video._relative_to_root(project) == Path("projects/demo-project")
            first = produce_video.produce(project)
            second = produce_video.produce(project)
            assert build_options == [{"require_copy_review": False}]
            assert first["state"] == "QC_PASSED" and first["reused"] is False
            assert second["state"] == "QC_PASSED" and second["reused"] is True
            assert second["resumed_from_run_id"] == first["run_id"]
            assert second["rendered"] is True and second["technical_qc"] == "PASS"
            assert second["production_ready"] is False and second["published"] is False
            assert len(second["runs"]) == 2
            assert second["runs"][0]["run_id"] == first["run_id"]
            assert second["runs"][0]["elapsed_seconds"] == first["elapsed_seconds"]
            assert second["runs"][1]["reused"] is True
            assert len(calls) == 1
            assert second["human_review"] == "PENDING_FOUNDER_REVIEW"
        finally:
            produce_video.ROOT = old_root
            produce_video.m5_production.build = old_build


def test_producer_review_mode_keeps_the_human_copy_gate():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp).resolve()
        project = root / "projects" / "demo-project"
        (project / "script").mkdir(parents=True)
        (project / "sources").mkdir()
        (project / "project.yaml").write_text("id: demo-project\nsource_refs: []\n", encoding="utf-8")
        (project / "script" / "script.json").write_text("{}", encoding="utf-8")
        (project / "script" / "claims.json").write_text("{}", encoding="utf-8")
        (project / "sources" / "assets.json").write_text('{"assets": []}', encoding="utf-8")
        old_root, old_check, old_build = (
            produce_video.ROOT,
            produce_video.m5_production.copy_review.require_approved,
            produce_video.m5_production.build,
        )
        calls = []

        def refuse_review(_project):
            raise produce_video.m5_production.copy_review.CopyReviewRequired(
                "NOT_REVIEWED", "approve copy")

        def unexpected_build(_project, **_options):
            calls.append("build")
            raise AssertionError("render must not proceed before explicit review")

        produce_video.ROOT = root
        produce_video.m5_production.copy_review.require_approved = refuse_review
        produce_video.m5_production.build = unexpected_build
        try:
            try:
                produce_video.produce(project, mode="REVIEW")
            except produce_video.m5_production.M5Blocked as exc:
                assert "NOT_REVIEWED" in str(exc)
            else:
                raise AssertionError("REVIEW mode must require a recorded approval")
            saved = json.loads((project / "receipts" / "produce-video.json").read_text(encoding="utf-8"))
            assert saved["state"] == "BLOCKED"
            assert calls == []
        finally:
            produce_video.ROOT = old_root
            produce_video.m5_production.copy_review.require_approved = old_check
            produce_video.m5_production.build = old_build


def test_configured_motion_runs_each_placement_through_managed_adapter():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        plan = {"shots": [
            {"id": "line-1", "asset_id": "motion-A1", "spec": "motion/one.json"},
            {"id": "line-2", "asset_id": "motion-A2", "spec": "motion/two.json"},
        ]}
        plan_path = project / "motion" / "plan.json"
        plan_path.parent.mkdir()
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        script_path = project / "script" / "script.json"
        script_path.parent.mkdir()
        original_script = {"lines": [{"id": "line-1", "asset_id": "A1"},
                                      {"id": "line-2", "asset_id": "A2"}]}
        script_path.write_text(json.dumps(original_script), encoding="utf-8")
        commands = []
        old_run = m5_production.hidden_run

        def fake_run(command, **_options):
            commands.append(command)
            payload = {"execution": {"state": "EXECUTED",
                                     "adapter_receipt": {"asset_id": "ok"}},
                       "receipt": "receipts/executions/test.json"}
            return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

        m5_production.hidden_run = fake_run
        try:
            result = m5_production.stage_motion(
                project, {"motion": {"backend": "huashu-art-motion",
                                     "shot_plan": "motion/plan.json"}},
                {"lines": [{"id": "line-1", "asset_id": "A1"},
                           {"id": "line-2", "asset_id": "A2"}]},
                require_copy_review=False)
            assert result == {"state": "OK", "backend": "huashu-art-motion", "shots": 2}
            assert len(commands) == 2
            assert all("--mode" in command and command[command.index("--mode") + 1] == "AUTO"
                       for command in commands)
            receipt = json.loads((project / "receipts" / "motion-stage.json").read_text())
            assert [row["placement_id"] for row in receipt["shots"]] == ["line-1", "line-2"]
            assert json.loads(script_path.read_text()) == original_script
            assert [command[command.index("--asset-id") + 1] for command in commands] == [
                "motion-A1", "motion-A2"]
        finally:
            m5_production.hidden_run = old_run


def test_motion_stage_refuses_an_unmapped_plan_before_rendering():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        plan_path = project / "plan.json"
        plan_path.write_text(json.dumps({"shots": [
            {"id": "other", "asset_id": "A1", "spec": "one.json"}]}),
            encoding="utf-8")
        try:
            m5_production.stage_motion(
                project, {"motion": {"backend": "huashu-art-motion",
                                     "shot_plan": "plan.json"}},
                {"lines": [{"id": "line-1", "asset_id": "A1"}]},
                require_copy_review=False)
        except m5_production.M5Blocked as exc:
            assert "does not map" in str(exc)
        else:
            raise AssertionError("an unmapped animation must not run")


def test_huashu_render_cache_requires_matching_inputs_and_output_hash():
    verify_root = ROOT / ".verify-tmp"
    verify_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=verify_root) as temp:
        project = Path(temp)
        for relative, payload in {
            "script/script.json": {"lines": [{"id": "P-01", "asset_id": "A1",
                                                "claim": "C-01"}]},
            "script/claims.json": {"claims": [{"id": "C-01", "artifacts": ["E-01"]}]},
            "sources/source-refs.json": {"refs": [{"id": "E-01"}]},
            "motion.json": {"duration": 4, "width": 1080, "height": 1920,
                             "fps": 30, "cues": [{"start": 0, "end": 4}]},
        }.items():
            path = project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload), encoding="utf-8")
        output = project / "assets" / "generated" / "huashu" / "A1.mp4"
        output.parent.mkdir(parents=True)
        output.write_bytes(b"verified motion output")
        spec_path = project / "motion.json"
        runtime = {"skill_id": "huashu-art-motion", "version": "1.2.0"}
        inputs = {
            "script": huashu_motion_adapter._sha(project / "script/script.json"),
            "claims": huashu_motion_adapter._sha(project / "script/claims.json"),
            "source_refs": huashu_motion_adapter._sha(project / "sources/source-refs.json"),
            "spec": huashu_motion_adapter._sha(spec_path),
        }
        digest = huashu_motion_adapter._sha(output)
        receipt = {
            "schema": "contentops.video-receipt/v1",
            "asset_id": "A1", "placement_id": "P-01",
            "runtime": runtime, "input_sha256": inputs,
            "fingerprint": huashu_motion_adapter._motion_fingerprint(
                inputs, runtime, "P-01"),
            "output": {"repo_path": output.relative_to(ROOT).as_posix(),
                       "output_sha256": digest},
            "technical_qc": {"approved": True, "black_frame_segments": []},
        }
        receipt_path = project / "receipts" / "huashu-A1.json"
        receipt_path.parent.mkdir(parents=True)
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

        cached = huashu_motion_adapter._cached_render(
            project, "A1", "P-01", "motion.json", runtime)
        assert cached is not None
        assert cached["output"] == output

        output.write_bytes(b"changed output")
        assert huashu_motion_adapter._cached_render(
            project, "A1", "P-01", "motion.json", runtime) is None


def main() -> int:
    tests = (test_a_video_asset_reaches_the_storyboard_as_a_clip,
             test_a_still_asset_is_not_labelled_a_clip,
             test_the_composer_key_and_the_receipt_key_agree,
             test_a_missing_asset_stops_the_build,
             test_a_non_positive_duration_stops_the_build,
             test_misaligned_lines_and_timings_stop_the_build,
             test_the_same_asset_can_support_multiple_timeline_placements,
             test_an_unreachable_narration_provider_is_refused,
             test_existing_narration_without_a_receipt_is_refused,
             test_existing_narration_bound_to_another_script_is_refused,
             test_existing_narration_without_line_timings_is_refused,
             test_existing_narration_that_matches_is_reused_without_a_provider_call,
             test_producer_reuses_current_qc_pass_without_rebuilding,
             test_producer_review_mode_keeps_the_human_copy_gate,
             test_configured_motion_runs_each_placement_through_managed_adapter,
             test_motion_stage_refuses_an_unmapped_plan_before_rendering,
             test_huashu_render_cache_requires_matching_inputs_and_output_hash)
    for test in tests:
        test()
        print(f"[ok] {test.__name__}")
    print(f"All {len(tests)} M5 motion-integration tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
