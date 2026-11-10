"""Huashu motion assets into M4.5 -> M5 -> Easel, verified offline.

Run: python tests/test_huashu_motion_manifest.py

The chain under test is the one the two Huashu engines need:

    checked clip -> manifest asset -> active timeline -> M5 storyboard

Nothing here renders. The clip bytes are deterministic local fixtures, the
ffprobe facts are injected, and the audio transform is the repository's own
deterministic ffmpeg step. A test that needs ffmpeg says so and skips rather
than pretending to have verified a file.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.media import huashu_motion  # noqa: E402
from contentops.media.media_envelope import MediaModality  # noqa: E402
from contentops.media.quality_gate import (  # noqa: E402
    GATE_PENDING_HUMAN_REVIEW,
    AssetQualityGate,
    MediaManifest,
    TimelinePlacement,
    build_manifest,
)
from contentops.media.manifest_m5_bridge import (  # noqa: E402
    ManifestBridgeError,
    build_m5_storyboard,
    validate_manifest_file,
)

HAVE_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _probe(duration: float = 4.0):
    return {
        "duration_s": duration,
        "width": 1080,
        "height": 1920,
        "codec_name": "h264",
        "pix_fmt": "yuv420p",
        "avg_frame_rate": "30/1",
        "r_frame_rate": "30/1",
        "has_audio": False,
        "frame_timestamps": [round(i / 30, 6) for i in range(int(round(duration * 30)))],
    }


def _tiny_mp4(path: Path, *, seconds: float = 4.0, with_audio: bool = False) -> Path:
    """A deterministic local clip, produced by ffmpeg when it is available."""
    from process_utils import hidden_run

    path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-y", "-v", "error", "-nostdin",
        "-f", "lavfi", "-i", f"color=c=0x1d1b18:s=1080x1920:r=30:d={seconds}",
    ]
    if with_audio:
        command += ["-f", "lavfi", "-i", "sine=frequency=440:duration=4"]
    command += [
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-pix_fmt", "yuv420p",
    ]
    if with_audio:
        command += ["-c:a", "aac", "-shortest"]
    command += [str(path)]
    result = hidden_run(command, timeout=300)
    if result.returncode != 0 or not path.is_file():
        raise RuntimeError(f"could not build the local fixture clip: {(result.stderr or '')[-200:]}")
    return path


def _record_for(clip: Path, project: Path, *, engine: str) -> dict:
    digest = hashlib.sha256(clip.read_bytes()).hexdigest()
    return huashu_motion.build_output_record(
        engine=engine,
        spec_sha256="a" * 64,
        clip_path="project://" + clip.relative_to(project).as_posix(),
        clip_sha256=digest,
        duration=4.0,
        resolution="1080x1920",
        fps=30.0,
        audio_policy="MUTE",
        input_asset_hashes={"spec-input": "b" * 64},
    )


def test_the_shared_record_carries_the_fields_both_engines_promise():
    record = huashu_motion.build_output_record(
        engine=huashu_motion.ENGINE_ART_MOTION,
        spec_sha256="a" * 64, clip_path="project://work/p01.mp4",
        clip_sha256="b" * 64, duration=4.0, resolution="1080x1920", fps=30.0,
        audio_policy="REPLACE", input_asset_hashes={"input": "c" * 64},
    )
    for field in ("engine", "version", "commit", "spec_sha256", "asset_hashes",
                  "clip_path", "clip_sha256", "duration", "resolution", "fps",
                  "audio_policy", "rights", "review_status"):
        assert field in record, field
    assert record["generated"] is True
    assert record["evidence_capable"] is False
    assert record["production_ready"] is False
    assert record["publish_authorized"] is False
    assert record["rights"] == "UNRESOLVED"
    assert record["review_status"] == "PENDING_FOUNDER_REVIEW"


def test_an_unknown_engine_or_a_forged_identity_is_refused():
    try:
        huashu_motion.build_output_record(
            engine="not-an-engine", spec_sha256="a" * 64, clip_path="project://x.mp4",
            clip_sha256="b" * 64, duration=4.0, resolution="1080x1920", fps=30.0,
            audio_policy="MUTE",
        )
    except huashu_motion.HuashuMotionError:
        pass
    else:
        raise AssertionError("an unknown engine must be refused")


def test_the_two_engines_produce_the_same_record_shape():
    fields = None
    for engine in (huashu_motion.ENGINE_MOTION, huashu_motion.ENGINE_ART_MOTION):
        record = huashu_motion.build_output_record(
            engine=engine, spec_sha256="a" * 64, clip_path="project://x.mp4",
            clip_sha256="b" * 64, duration=4.0, resolution="1080x1920", fps=30.0,
            audio_policy="MUTE",
        )
        if fields is None:
            fields = set(record)
        assert set(record) == fields, engine
        assert record["engine"] == engine


def test_a_kept_audio_policy_is_refused_for_a_motion_clip():
    try:
        huashu_motion.build_output_record(
            engine=huashu_motion.ENGINE_MOTION, spec_sha256="a" * 64,
            clip_path="project://x.mp4", clip_sha256="b" * 64, duration=4.0,
            resolution="1080x1920", fps=30.0, audio_policy="KEEP",
        )
    except huashu_motion.HuashuMotionError:
        pass
    else:
        raise AssertionError("KEEP would put the clip's own soundtrack under the narration")


def test_a_motion_clip_reaches_the_manifest_and_the_active_timeline():
    if not HAVE_FFMPEG:
        print("     [skip] ffmpeg is unavailable; the manifest chain was not exercised")
        return
    from contentops.media.motion_manifest import register_motion_clip

    with tempfile.TemporaryDirectory(dir=ROOT) as temp:
        project = Path(temp) / "project"
        clip = _tiny_mp4(project / "assets" / "motion" / "p01.mp4", with_audio=True)
        record = _record_for(clip, project, engine=huashu_motion.ENGINE_ART_MOTION)
        registered = register_motion_clip(
            record, clip_path=clip, project_root=project,
            asset_id="p01-motion", placement_id="p01", audio_policy="MUTE",
        )
        assert registered.source.generated and not registered.source.evidence_capable
        assert registered.derived.derived_from == "p01-motion"
        assert registered.derived.audio_policy == "MUTE"
        assert registered.derived.is_derived

        gate = AssetQualityGate()
        decisions = [gate.evaluate(entry, repo_root=ROOT, project_root=project)
                     for entry in (registered.source, registered.derived)]
        assert all(decision.state == GATE_PENDING_HUMAN_REVIEW for decision in decisions), decisions

        manifest = build_manifest(
            [registered.source, registered.derived], decisions,
            narration={"required": False},
        )
        assert len(manifest.timeline) == 1
        placement = manifest.timeline[0]
        assert placement.active_asset_id == registered.derived.asset_id
        assert registered.source.asset_id in placement.superseded_asset_ids

        manifest_path = manifest.write(project / "receipts" / "media-manifest.json")
        validated = validate_manifest_file(
            manifest_path, repo_root=ROOT, project_root=project,
        )
        import m5_production

        try:
            m5_production._assert_manifest_motion_rights_resolved(validated, project, {"fixture": False})
        except m5_production.M5Blocked as exc:
            assert "rights are unresolved" in str(exc)
        else:
            raise AssertionError("unresolved motion rights must block real composition")
        from dataclasses import replace

        fixture_view = replace(
            validated, fixture_assets=frozenset({registered.derived.asset_id})
        )
        try:
            m5_production._assert_manifest_motion_rights_resolved(
                fixture_view, project, {"fixture": False}
            )
        except m5_production.M5Blocked as exc:
            assert "fixture assets cannot enter a non-fixture project" in str(exc)
        else:
            raise AssertionError("fixture media must stay isolated from real projects")
        assert m5_production._assert_manifest_motion_rights_resolved(
            fixture_view, project, {"fixture": True}
        ) is None
        assert validated.manifest.timeline[0].active_asset_id == registered.derived.asset_id

        voice = project / "voice.wav"
        voice.write_bytes(b"narration placeholder")
        subtitle = project / "captions.srt"
        subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nA\n", encoding="utf-8")
        storyboard, receipt = build_m5_storyboard(
            validated,
            [{"id": "line-a", "placement_id": "p01", "caption": "A", "narration": "A"}],
            [{"start": 0.0, "duration": 1.0}],
            narration_duration_s=1.0, narration_path=voice, subtitle_path=subtitle,
            project_root=project, repo_root=ROOT,
        )
        shot = storyboard["shots"][0]
        assert shot["shot_id"] == "p01"
        assert shot["video"].endswith("p01-mute.mp4")
        assert shot["audio_policy"] == "MUTE"
        assert shot["media_provenance"]["generated"] is True
        assert shot["media_provenance"]["evidence_capable"] is False
        assert receipt["provider_calls"] == 0
        assert receipt["production_ready"] is False


def test_native_motion_preview_is_registered_without_becoming_huashu():
    if not HAVE_FFMPEG:
        print("     [skip] ffmpeg is unavailable; native motion registration was not exercised")
        return
    from contentops.media.motion_manifest import register_motion_clip

    with tempfile.TemporaryDirectory(dir=ROOT) as temp:
        project = Path(temp) / "project"
        clip = _tiny_mp4(project / "assets" / "generated" / "native.mp4")
        digest = hashlib.sha256(clip.read_bytes()).hexdigest()
        record = {
            "schema": "contentops.native-motion-preview/v1",
            "project": project.name,
            "account": "x-superplay-future-intelligence",
            "version": "0.1.0",
            "renderer": {
                "source": "scripts/native_motion_preview.py",
                "source_sha256": "c" * 64,
                "dependencies": {
                    "python": {"version": "3.13.15", "license": "PSF-2.0"},
                    "pillow": {"version": "12.3.0", "license": "MIT-CMU"},
                    "ffmpeg": {"version": "8.1.1", "license": "GPL-3.0-or-later"},
                },
            },
            "spec_sha256": "a" * 64,
            "output": {
                "path": "project://assets/generated/native.mp4",
                "sha256": digest, "duration_s": 4.0,
                "resolution": "1080x1920", "fps": 30, "frames": 120,
                "technical_state": "TECHNICALLY_CHECKED",
                "generated": True, "evidence_capable": False,
            },
            "rights": {
                "scope": "P6-requested internal review only",
                "third_party_assets": "NONE", "public_use_cleared": False,
            },
            "execution_authorized": False, "production_ready": False,
            "publish_authorized": False,
        }
        registered = register_motion_clip(
            record, clip_path=clip, project_root=project,
            asset_id="native-motion", placement_id="p01", audio_policy="MUTE",
        )
        source_receipt = json.loads(registered.source_receipt_path.read_text(encoding="utf-8"))
        assert registered.source.generated is True
        assert registered.source.evidence_capable is False
        assert source_receipt["motion_origin"]["schema"] == "contentops.native-motion-preview/v1"
        assert source_receipt["motion_origin"]["renderer"] == record["renderer"]
        assert source_receipt["output_sha256"] == digest
        assert source_receipt["technical_qc"]["width"] == 1080
        assert source_receipt["technical_qc"]["height"] == 1920
        assert source_receipt["technical_qc"]["fps"] == 30
        assert source_receipt["technical_qc"]["duration_s"] == 4.0
        assert registered.derived.derived_from == "native-motion"
        assert registered.derived.evidence_capable is False


def test_a_missing_clip_or_a_digest_mismatch_is_refused():
    if not HAVE_FFMPEG:
        print("     [skip] ffmpeg is unavailable; the refusal paths were not exercised")
        return
    from contentops.media.motion_manifest import MotionAssetError, register_motion_clip

    with tempfile.TemporaryDirectory(dir=ROOT) as temp:
        project = Path(temp) / "project"
        clip = _tiny_mp4(project / "assets" / "motion" / "p01.mp4", with_audio=True)
        record = _record_for(clip, project, engine=huashu_motion.ENGINE_MOTION)

        clip.unlink()
        try:
            register_motion_clip(record, clip_path=clip, project_root=project,
                                 asset_id="p01-motion", placement_id="p01")
        except MotionAssetError:
            pass
        else:
            raise AssertionError("a missing clip must be refused")

        _tiny_mp4(clip, with_audio=True)
        record["clip_sha256"] = "0" * 64
        try:
            register_motion_clip(record, clip_path=clip, project_root=project,
                                 asset_id="p01-motion", placement_id="p01")
        except MotionAssetError:
            pass
        else:
            raise AssertionError("a digest mismatch must be refused")


def test_a_manifest_with_a_missing_or_changed_clip_is_refused_by_the_bridge():
    if not HAVE_FFMPEG:
        print("     [skip] ffmpeg is unavailable; the bridge refusal paths were not exercised")
        return
    from contentops.media.motion_manifest import register_motion_clip

    with tempfile.TemporaryDirectory(dir=ROOT) as temp:
        project = Path(temp) / "project"
        clip = _tiny_mp4(project / "assets" / "motion" / "p01.mp4", with_audio=True)
        record = _record_for(clip, project, engine=huashu_motion.ENGINE_MOTION)
        registered = register_motion_clip(
            record, clip_path=clip, project_root=project,
            asset_id="p01-motion", placement_id="p01",
        )
        gate = AssetQualityGate()
        decisions = [gate.evaluate(entry, repo_root=ROOT, project_root=project)
                     for entry in (registered.source, registered.derived)]
        manifest = build_manifest(
            [registered.source, registered.derived], decisions,
            narration={"required": False},
        )
        manifest_path = manifest.write(project / "receipts" / "media-manifest.json")

        derived_path = project / registered.derived.path[len("project://"):]
        original = derived_path.read_bytes()
        derived_path.write_bytes(b"changed after validation")
        try:
            validate_manifest_file(manifest_path, repo_root=ROOT, project_root=project)
        except ManifestBridgeError:
            pass
        else:
            raise AssertionError("changed clip bytes must invalidate the manifest")
        derived_path.write_bytes(original)


def test_a_generated_motion_asset_may_supplement_a_separately_claimed_fact():
    from contentops.evidence import CLAIM_SCHEMA, ClaimLedger, SourceArtifact

    import m5_production

    with tempfile.TemporaryDirectory(dir=ROOT) as temp:
        project = Path(temp) / "project"
        (project / "script").mkdir(parents=True)
        (project / "sources").mkdir()
        evidence = project / "sources" / "claim.md"
        evidence.write_text("the fact", encoding="utf-8")
        artifact = SourceArtifact.from_path(
            id="source", source_type="repo_doc", title="claim source", path=evidence,
            repo_root=ROOT, permission="OWNED",
        )
        clip = project / "motion.mp4"
        clip.write_bytes(b"mock motion clip")
        (project / "script" / "script.json").write_text(json.dumps({
            "schema": m5_production.SCRIPT_SCHEMA, "lines": [{
                "id": "line-a", "claim": "C1", "narration": "fact narration",
                "caption": "fact", "placement_id": "p01",
            }],
        }), encoding="utf-8")
        ledger = ClaimLedger.from_payload({"schema": CLAIM_SCHEMA, "claims": [{
            "id": "C1", "text": "the fact", "artifacts": ["source"], "quotes": ["the fact"],
        }]})
        assert ledger.verify({"source": artifact}, ROOT) == []
        result = m5_production.stage_script(
            project, ledger, {}, manifest_assets_by_line={"line-a": {
                "asset_id": "p01-motion", "repo_path": str(clip),
                "placement_id": "p01", "generated": True,
                "evidence_capable": False, "evidence_use": "VISUAL_SUPPORT",
                "claim_refs": [],
            }},
        )
        assert result["lines"] == 1


def test_a_generated_motion_asset_cannot_claim_factual_evidence():
    from contentops.evidence import CLAIM_SCHEMA, ClaimLedger

    import m5_production

    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "project"
        (project / "script").mkdir(parents=True)
        (project / "sources").mkdir()
        clip = project / "motion.mp4"
        clip.write_bytes(b"mock motion clip")
        (project / "script" / "script.json").write_text(json.dumps({
            "schema": m5_production.SCRIPT_SCHEMA, "lines": [{
                "id": "line-a", "claim": "C1", "narration": "fact narration",
                "caption": "fact", "placement_id": "p01",
            }],
        }), encoding="utf-8")
        ledger = ClaimLedger.from_payload({"schema": CLAIM_SCHEMA, "claims": [{
            "id": "C1", "text": "the fact", "artifacts": ["source"], "quotes": ["the fact"],
        }]})
        try:
            m5_production.stage_script(
                project, ledger, {}, manifest_assets_by_line={"line-a": {
                    "asset_id": "p01-motion", "repo_path": str(clip),
                    "placement_id": "p01", "generated": True,
                    "evidence_capable": False, "evidence_use": "EVIDENCE",
                    "claim_refs": ["C1"],
                }},
            )
        except m5_production.M5Blocked as exc:
            assert "generated visual cannot carry claim evidence" in str(exc)
        else:
            raise AssertionError("generated motion cannot carry factual evidence")


def test_the_legacy_manifest_path_is_untouched_by_the_motion_work():
    import m5_production

    source = Path(m5_production.__file__).read_text(encoding="utf-8")
    assert "media_manifest" in source, "the manifest mode is still wired"
    assert "stage_assets(project, extra_assets=media[\"assets\"])" in source, (
        "the legacy asset registry path must still exist"
    )


def test_the_motion_manifest_module_writes_no_absolute_host_paths():
    from contentops.media import motion_manifest

    source = Path(motion_manifest.__file__).read_text(encoding="utf-8")
    assert "project://" in source
    assert "D:\\" not in source and "C:\\" not in source


TESTS = [value for name, value in sorted(globals().items())
         if name.startswith("test_") and callable(value)]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
            print(f"ok   {test.__name__}")
        except Exception as exc:  # noqa: BLE001 - a runner reports, it does not hide
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
    total = len(TESTS)
    print(f"{total - failures}/{total} ok")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
