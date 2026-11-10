"""Offline contracts for the explicit M4.5-manifest M5 bridge."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from contentops.media.media_envelope import MediaAssetEnvelope, MediaModality  # noqa: E402
from contentops.media.quality_gate import (  # noqa: E402
    GATE_PENDING_HUMAN_REVIEW,
    MediaManifest,
    TimelinePlacement,
)
from contentops.evidence import CLAIM_SCHEMA, ClaimLedger  # noqa: E402
from contentops.media.manifest_m5_bridge import (  # noqa: E402
    ManifestBridgeError,
    ValidatedManifest,
    build_technical_preview_storyboard,
    build_m5_storyboard,
    map_script_to_active_assets,
    validate_manifest_file,
    validate_manifest_structure,
)
import assemble_easel  # noqa: E402
import m5_production  # noqa: E402


def test_easel_adapter_keeps_intermediate_out_of_pinned_runtime():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "project"
        storyboard = project / "script" / "storyboard.json"
        storyboard.parent.mkdir(parents=True)
        storyboard.write_text(json.dumps({"size": "1080x1920", "shots": []}), encoding="utf-8")
        original_resolver = assemble_easel._upstream_assemble
        original_runner = assemble_easel.hidden_run
        outputs = []

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        def fake_run(argv, **kwargs):
            output = Path(argv[-1])
            outputs.append(output.resolve())
            output.write_bytes(b"fixture mp4 bytes")
            return Result()

        try:
            assemble_easel._upstream_assemble = lambda: Path(temp) / "pinned" / "assemble.py"
            assemble_easel.hidden_run = fake_run
            result = assemble_easel.run(project, out_name="isolated")
        finally:
            assemble_easel._upstream_assemble = original_resolver
            assemble_easel.hidden_run = original_runner
        runtime = (ROOT / ".runtime" / "easel").resolve()
        assert result["status"] == "OK"
        assert outputs and not outputs[0].is_relative_to(runtime)
        assert (project / "final" / "isolated.mp4").read_bytes() == b"fixture mp4 bytes"


def _manifest(*, reverse_inventory: bool = False) -> MediaManifest:
    first = MediaAssetEnvelope(
        asset_id="asset-a", modality=MediaModality.IMAGE, placement_id="place-a",
        path="project://assets/a.png", sha256="a" * 64, receipt_ref="a.png.receipt.json",
        asset_kind="REAL", generated=False, evidence_capable=False,
        evidence_use="VISUAL_SUPPORT",
    )
    second = MediaAssetEnvelope(
        asset_id="asset-b", modality=MediaModality.VIDEO, placement_id="place-b",
        path="project://assets/b.mp4", sha256="b" * 64, receipt_ref="b.mp4.receipt.json",
        asset_kind="GENERATED_VIDEO", generated=True, evidence_capable=False,
        evidence_use="VISUAL_SUPPORT", audio_policy="REPLACE",
    )
    assets = [second, first] if reverse_inventory else [first, second]
    return MediaManifest(
        assets=assets,
        gate_states={asset.asset_id: GATE_PENDING_HUMAN_REVIEW for asset in assets},
        timeline=[
            TimelinePlacement("place-a", "asset-a", "real support visual"),
            TimelinePlacement("place-b", "asset-b", "generated support visual"),
        ],
    )


def _minimal_payload():
    return {
        "schema": "contentops.media-manifest/v1",
        "counts": {"by_gate_state": {"asset-a": "PENDING_HUMAN_REVIEW"}},
        "assets": [{
            "asset_id": "asset-a", "modality": "IMAGE", "placement_id": "place-a",
            "path": "project://assets/a.png", "sha256": "a" * 64,
            "receipt_ref": "a.png.receipt.json", "fingerprint": "f" * 64,
            "asset_kind": "REAL", "generated": False, "evidence_capable": False,
            "evidence_use": "VISUAL_SUPPORT", "claim_refs": [],
            "technical_status": "NOT_RUN", "human_review": "PENDING_FOUNDER_REVIEW",
            "production_ready": False, "audio_policy": None, "fallback": {},
            "derived_from": None, "transform_receipt_ref": None,
        }],
        "timeline": [{
            "placement_id": "place-a", "active_asset_id": "asset-a",
            "selection_reason": "explicit",
            "superseded_asset_ids": [],
        }],
    }


def test_structure_rejects_non_boolean_provenance_flags():
    payload = _minimal_payload()
    payload["assets"][0]["generated"] = "false"
    try:
        validate_manifest_structure(payload)
    except ManifestBridgeError:
        pass
    else:
        raise AssertionError("string booleans must not be truthiness-coerced")


def test_structure_rejects_duplicate_asset_ids_and_placement_mismatch():
    payload = _minimal_payload()
    payload["assets"].append(dict(payload["assets"][0]))
    try:
        validate_manifest_structure(payload)
    except ManifestBridgeError:
        pass
    else:
        raise AssertionError("duplicate manifest IDs must be refused")

    payload = _minimal_payload()
    payload["assets"][0]["placement_id"] = "other-place"
    try:
        validate_manifest_structure(payload)
    except ManifestBridgeError:
        pass
    else:
        raise AssertionError("active envelope placement must match the timeline")


def test_structure_rejects_nonvisual_active_assets_and_empty_timelines():
    payload = _minimal_payload()
    payload["assets"][0]["modality"] = "SPEECH"
    try:
        validate_manifest_structure(payload)
    except ManifestBridgeError:
        pass
    else:
        raise AssertionError("speech cannot be activated as a visual shot")

    payload = _minimal_payload()
    payload["timeline"] = []
    try:
        validate_manifest_structure(payload)
    except ManifestBridgeError:
        pass
    else:
        raise AssertionError("empty timeline must not silently compose")


def test_structure_prevents_resurrecting_audio_replaced_source():
    payload = _minimal_payload()
    source = payload["assets"][0]
    source["modality"] = "VIDEO"
    source["asset_kind"] = "GENERATED_VIDEO"
    source["generated"] = True
    source["audio_policy"] = "REPLACE"
    derived = dict(source)
    derived.update({
        "asset_id": "asset-a-replaced", "placement_id": "place-a",
        "path": "project://assets/a-replaced.mp4", "sha256": "b" * 64,
        "receipt_ref": None, "derived_from": "asset-a",
        "transform_receipt_ref": "a-replaced.mp4.transform.json",
    })
    payload["assets"].append(derived)
    payload["counts"]["by_gate_state"]["asset-a-replaced"] = "PENDING_HUMAN_REVIEW"
    payload["timeline"][0]["active_asset_id"] = "asset-a"
    try:
        validate_manifest_structure(payload)
    except ManifestBridgeError:
        pass
    else:
        raise AssertionError("REPLACE source must never return to active timeline")


def test_manifest_script_stage_uses_active_mapping_not_legacy_asset_registry():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "project"
        project.mkdir()
        (project / "script").mkdir()
        active_path = project / "active.png"
        active_path.write_bytes(b"active fixture")
        (project / "sources").mkdir()
        (project / "sources" / "assets.json").write_text(
            json.dumps({"schema": "contentops.m5-assets/v1", "assets": []}),
            encoding="utf-8",
        )
        script = {"schema": m5_production.SCRIPT_SCHEMA, "lines": [{
            "id": "line-a", "claim": "C1", "narration": "fact narration",
            "caption": "fact", "placement_id": "place-a", "asset_id": "legacy-stale",
        }]}
        (project / "script" / "script.json").write_text(json.dumps(script), encoding="utf-8")
        ledger = ClaimLedger.from_payload({"schema": CLAIM_SCHEMA, "claims": [{
            "id": "C1", "text": "the fact", "artifacts": ["source"], "quotes": ["the fact"],
        }]})
        m5_production.stage_script(
            project, ledger, {},
            manifest_assets_by_line={"line-a": {
                "asset_id": "active", "repo_path": str(active_path), "placement_id": "place-a",
            }},
        )
        master = (project / "script" / "master.md").read_text(encoding="utf-8")
        assert str(active_path) in master
        assert "legacy-stale" not in master


def test_manifest_script_stage_allows_visual_support_for_a_verified_claim():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "project"
        (project / "script").mkdir(parents=True)
        (project / "sources").mkdir()
        generated = project / "generated.mp4"
        generated.write_bytes(b"mock generated clip")
        (project / "script" / "script.json").write_text(json.dumps({
            "schema": m5_production.SCRIPT_SCHEMA, "lines": [{
                "id": "line-a", "claim": "C1", "narration": "fact narration",
                "caption": "fact", "placement_id": "place-a",
            }],
        }), encoding="utf-8")
        ledger = ClaimLedger.from_payload({"schema": CLAIM_SCHEMA, "claims": [{
            "id": "C1", "text": "the fact", "artifacts": ["source"], "quotes": ["the fact"],
        }]})
        result = m5_production.stage_script(
            project, ledger, {}, manifest_assets_by_line={"line-a": {
                "asset_id": "motion", "repo_path": str(generated),
                "placement_id": "place-a", "generated": True,
                "evidence_capable": False, "evidence_use": "VISUAL_SUPPORT",
                "claim_refs": [],
            }},
        )
        assert result["lines"] == 1


def test_manifest_script_stage_refuses_generated_asset_claim_evidence():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "project"
        (project / "script").mkdir(parents=True)
        (project / "sources").mkdir()
        generated = project / "generated.mp4"
        generated.write_bytes(b"mock generated clip")
        (project / "script" / "script.json").write_text(json.dumps({
            "schema": m5_production.SCRIPT_SCHEMA, "lines": [{
                "id": "line-a", "claim": "C1", "narration": "fact narration",
                "caption": "fact", "placement_id": "place-a",
            }],
        }), encoding="utf-8")
        ledger = ClaimLedger.from_payload({"schema": CLAIM_SCHEMA, "claims": [{
            "id": "C1", "text": "the fact", "artifacts": ["source"], "quotes": ["the fact"],
        }]})
        try:
            m5_production.stage_script(
                project, ledger, {}, manifest_assets_by_line={"line-a": {
                    "asset_id": "motion", "repo_path": str(generated),
                    "placement_id": "place-a", "generated": True,
                    "evidence_capable": False, "evidence_use": "EVIDENCE",
                    "claim_refs": ["C1"],
                }},
            )
        except m5_production.M5Blocked as exc:
            assert "generated visual cannot carry claim evidence" in str(exc)
        else:
            raise AssertionError("generated assets cannot claim evidence")


def test_manifest_script_stage_refuses_missing_active_mapping():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "project"
        (project / "script").mkdir(parents=True)
        (project / "sources").mkdir()
        (project / "script" / "script.json").write_text(json.dumps({
            "schema": m5_production.SCRIPT_SCHEMA, "lines": [{
                "id": "line-a", "claim": None, "narration": "n", "caption": "c",
                "placement_id": "place-a",
            }],
        }), encoding="utf-8")
        ledger = ClaimLedger.from_payload({"schema": CLAIM_SCHEMA, "claims": []})
        try:
            m5_production.stage_script(
                project, ledger, {}, manifest_assets_by_line={}
            )
        except m5_production.M5Blocked as exc:
            assert "no validated manifest placement mapping" in str(exc)
        else:
            raise AssertionError("manifest mode must not fall back to sources/assets.json")


def _video_manifest(root: Path, policy: str) -> Path:
    from contentops.media.fixtures_local import build_shot_fixture
    from contentops.media.media_transform import apply_audio_policy

    project = root / "project"
    source_path, source_receipt, fingerprint = build_shot_fixture(
        project / "assets" / "shot.mp4", seed=f"audio-{policy}", seconds=4
    )
    source_payload = json.loads(source_receipt.read_text(encoding="utf-8"))
    source_payload["audio_policy"] = "KEEP" if policy == "KEEP" else "REPLACE"
    source_receipt.write_text(json.dumps(source_payload), encoding="utf-8")
    source_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    source = MediaAssetEnvelope(
        asset_id="shot", modality=MediaModality.VIDEO, placement_id="place-a",
        path="project://assets/shot.mp4", sha256=source_digest,
        receipt_ref=source_receipt.name, fingerprint=fingerprint,
        asset_kind="GENERATED_VIDEO", generated=True, evidence_capable=False,
        evidence_use="VISUAL_SUPPORT", human_review="PENDING_FOUNDER_REVIEW",
        production_ready=False, audio_policy="KEEP" if policy == "KEEP" else None,
    )
    if policy == "KEEP":
        assets = [source]
        active = source.asset_id
        superseded = []
        audio_policy = "KEEP"
    else:
        application = apply_audio_policy(
            source_video=source_path, policy=policy, output_dir=project / "assets" / "processed",
            source_receipt_ref=source_receipt.name, source_fingerprint=fingerprint,
            source_generated=True,
        )
        output_path = Path(application.output_path)
        derived = MediaAssetEnvelope(
            asset_id=f"shot-{policy.lower()}", modality=MediaModality.VIDEO,
            placement_id="place-a", path="project://assets/processed/" + output_path.name,
            sha256=application.transform_receipt.output_sha256,
            fingerprint=fingerprint, asset_kind="GENERATED_VIDEO", generated=True,
            evidence_capable=False, evidence_use="VISUAL_SUPPORT",
            human_review="PENDING_FOUNDER_REVIEW", production_ready=False,
            audio_policy=policy, derived_from="shot",
            transform_receipt_ref=Path(application.receipt_path).name,
        )
        assets = [source, derived]
        active = derived.asset_id
        superseded = ["shot"]
        audio_policy = policy
    manifest = MediaManifest(
        assets=assets,
        gate_states={asset.asset_id: GATE_PENDING_HUMAN_REVIEW for asset in assets},
        timeline=[TimelinePlacement("place-a", active, "audio policy selection", superseded)],
        narration={"required": policy == "REPLACE", "source": "project://assets/voice/narration.wav"},
        notes={"fixture": True},
    )
    return manifest.write(project / "receipts" / f"{audio_policy.lower()}-manifest.json")


def test_audio_policy_is_verified_against_active_video_bytes():
    for policy, expected_audio, expected_mode in (
        ("KEEP", True, "native"), ("MUTE", False, "dub"), ("REPLACE", False, "dub")
    ):
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            root = Path(temp)
            project = root / "project"
            path = _video_manifest(root, policy)
            validated = validate_manifest_file(path, repo_root=ROOT, project_root=project)
            active = validated.manifest.timeline[0].active_asset_id
            assert validated.active_audio_present[active] is expected_audio
            voice, subtitle = project / "voice.wav", project / "captions.srt"
            voice.write_bytes(b"voice placeholder")
            subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nA\n", encoding="utf-8")
            storyboard, _ = build_m5_storyboard(
                validated,
                [{"id": "line-a", "placement_id": "place-a", "caption": "A", "narration": "A"}],
                [{"start": 0.0, "duration": 1.0}],
                narration_duration_s=1.0, narration_path=voice, subtitle_path=subtitle,
                project_root=project, repo_root=ROOT, voice_provider="sapi/Microsoft Huihui",
            )
            assert storyboard["voice_provider"] == "sapi/Microsoft Huihui"
            assert storyboard["shots"][0]["audio_mode"] == expected_mode


def _valid_image_manifest(root: Path) -> Path:
    from contentops.media.fixtures_local import build_screenshot_fixture

    project = root / "project"
    asset_path, receipt_path, fingerprint = build_screenshot_fixture(
        project / "assets" / "shot.png", seed="manifest-bridge-test"
    )
    digest = hashlib.sha256(asset_path.read_bytes()).hexdigest()
    envelope = MediaAssetEnvelope(
        asset_id="shot", modality=MediaModality.IMAGE, placement_id="place-a",
        path="project://assets/shot.png", sha256=digest,
        receipt_ref=receipt_path.name, fingerprint=fingerprint, asset_kind="REAL",
        generated=False, evidence_capable=False, evidence_use="VISUAL_SUPPORT",
        human_review="PENDING_FOUNDER_REVIEW", production_ready=False,
    )
    manifest = MediaManifest(
        assets=[envelope],
        gate_states={"shot": GATE_PENDING_HUMAN_REVIEW},
        timeline=[TimelinePlacement("place-a", "shot", "fixture visual")],
        notes={"fixture": True},
    )
    return manifest.write(project / "receipts" / "media-manifest.json")


def test_manifest_files_and_receipts_are_revalidated_and_hashed():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "project"
        manifest_path = _valid_image_manifest(Path(temp))
        validated = validate_manifest_file(
            manifest_path, repo_root=Path(temp), project_root=project
        )
        assert validated.manifest.timeline[0].active_asset_id == "shot"
        assert validated.asset_paths["shot"].is_file()
        assert len(validated.fingerprint) == 64

        validated.asset_paths["shot"].write_bytes(b"tampered")
        try:
            validate_manifest_file(manifest_path, repo_root=Path(temp), project_root=project)
        except ManifestBridgeError:
            pass
        else:
            raise AssertionError("changed asset bytes must invalidate the manifest")


def test_manifest_rejects_traversal_before_following_asset_path():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "project"
        manifest_path = _valid_image_manifest(Path(temp))
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["assets"][0]["path"] = "project://../outside.png"
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        try:
            validate_manifest_file(manifest_path, repo_root=Path(temp), project_root=project)
        except ManifestBridgeError:
            pass
        else:
            raise AssertionError("logical path traversal must be refused")


def test_manifest_rejects_forged_serialized_gate_state():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "project"
        manifest_path = _valid_image_manifest(Path(temp))
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["counts"]["by_gate_state"]["shot"] = "PRODUCTION_READY"
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        try:
            validate_manifest_file(manifest_path, repo_root=Path(temp), project_root=project)
        except ManifestBridgeError:
            pass
        else:
            raise AssertionError("serialized gate state cannot override current validation")


def test_symlink_asset_escape_is_refused_when_symlinks_are_available():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        project = root / "project"
        manifest_path = _valid_image_manifest(root)
        outside = root / "outside.png"
        outside.write_bytes(b"outside")
        link = project / "assets" / "escape.png"
        try:
            link.symlink_to(outside)
        except (OSError, NotImplementedError):
            print("     [skip] symlink creation is unavailable")
            return
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["assets"][0]["path"] = "project://assets/escape.png"
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        try:
            validate_manifest_file(manifest_path, repo_root=root, project_root=project)
        except ManifestBridgeError:
            return
        raise AssertionError("a symlink resolving outside the project must be refused")


def _lines():
    return [
        {"id": "line-a", "placement_id": "place-a", "claim": "C1", "caption": "A", "narration": "A"},
        {"id": "line-b", "placement_id": "place-b", "claim": None, "caption": "B", "narration": "B"},
    ]


def test_storyboard_uses_measured_timing_and_active_video_clip():
    with tempfile.TemporaryDirectory(dir=ROOT) as temp:
        project = Path(temp)
        voice = project / "voice.wav"
        subtitle = project / "captions.srt"
        voice.write_bytes(b"test audio placeholder")
        subtitle.write_text(
            "1\n00:00:00,000 --> 00:00:01,000\nA\n\n"
            "2\n00:00:02,500 --> 00:00:03,500\nB\n", encoding="utf-8"
        )
        (project / "assets").mkdir()
        asset_a = project / "assets" / "a.png"
        asset_b = project / "assets" / "b.mp4"
        asset_a.write_bytes(b"fixture image")
        asset_b.write_bytes(b"fixture video")
        receipt_a, receipt_b = project / "assets" / "a.receipt.json", project / "assets" / "b.receipt.json"
        receipt_a.write_text("{}", encoding="utf-8")
        receipt_b.write_text("{}", encoding="utf-8")
        manifest = _manifest()
        validated = ValidatedManifest(
            manifest=manifest, manifest_path=project / "manifest.json",
            manifest_sha256="c" * 64, fingerprint=manifest.fingerprint(),
            asset_paths={"asset-a": asset_a, "asset-b": asset_b},
            receipt_paths={"asset-a": receipt_a, "asset-b": receipt_b},
            asset_sha256={"asset-a": hashlib.sha256(asset_a.read_bytes()).hexdigest(),
                          "asset-b": hashlib.sha256(asset_b.read_bytes()).hexdigest()},
            receipt_sha256={"asset-a": hashlib.sha256(receipt_a.read_bytes()).hexdigest(),
                            "asset-b": hashlib.sha256(receipt_b.read_bytes()).hexdigest()},
            active_audio_present={"asset-b": False},
            fixture_assets=frozenset({"asset-a", "asset-b"}),
        )
        storyboard, receipt = build_m5_storyboard(
            validated, _lines(),
            [{"start": 0.0, "duration": 1.0}, {"start": 2.5, "duration": 1.0}],
            narration_duration_s=4.0, narration_path=voice, subtitle_path=subtitle,
            project_root=project, repo_root=ROOT,
        )
        assert [shot["shot_id"] for shot in storyboard["shots"]] == ["place-a", "place-b"]
        assert [shot["duration"] for shot in storyboard["shots"]] == [2.5, 1.5]
        assert storyboard["shots"][0]["image"] == (project.relative_to(ROOT) / "assets" / "a.png").as_posix()
        assert storyboard["shots"][1]["video"] == (project.relative_to(ROOT) / "assets" / "b.mp4").as_posix()
        assert storyboard["shots"][1]["audio_mode"] == "dub"
        assert storyboard["shots"][0]["source_type"] == "fixture"
        assert storyboard["shots"][1]["source_type"] == "fixture"
        assert storyboard["shots"][1]["media_provenance"]["generated"] is True
        assert storyboard["media_manifest_fingerprint"] == manifest.fingerprint()
        assert receipt["placements"][1]["active_asset_id"] == "asset-b"


def test_storyboard_refuses_asset_drift_after_manifest_validation():
    with tempfile.TemporaryDirectory(dir=ROOT) as temp:
        root = Path(temp)
        project = root / "project"
        manifest_path = _valid_image_manifest(root)
        validated = validate_manifest_file(
            manifest_path, repo_root=ROOT, project_root=project
        )
        voice, subtitle = project / "voice.wav", project / "captions.srt"
        voice.write_bytes(b"audio")
        subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nA\n", encoding="utf-8")
        validated.asset_paths["shot"].write_bytes(b"changed after validation")
        try:
            build_m5_storyboard(
                validated,
                [{"id": "line-a", "placement_id": "place-a", "caption": "A", "narration": "A"}],
                [{"start": 0.0, "duration": 1.0}],
                narration_duration_s=1.0, narration_path=voice, subtitle_path=subtitle,
                project_root=project, repo_root=ROOT,
            )
        except ManifestBridgeError as exc:
            assert "changed after manifest validation" in str(exc)
        else:
            raise AssertionError("asset changed after validation must be blocked before compose")


def test_storyboard_rejects_narration_timing_count_mismatch():
    with tempfile.TemporaryDirectory(dir=ROOT) as temp:
        project = Path(temp)
        voice, subtitle = project / "voice.wav", project / "captions.srt"
        voice.write_bytes(b"audio")
        subtitle.write_text("1\n00:00:00,000 --> 00:00:01,000\nA\n", encoding="utf-8")
        manifest = _manifest()
        validated = ValidatedManifest(
            manifest, project / "manifest.json", "c" * 64, manifest.fingerprint(),
            {"asset-a": ROOT / "a.png", "asset-b": ROOT / "b.mp4"},
            {"asset-a": ROOT / "a.receipt.json", "asset-b": ROOT / "b.receipt.json"},
            {"asset-a": "a" * 64, "asset-b": "b" * 64},
            {"asset-a": "c" * 64, "asset-b": "d" * 64},
            {"asset-b": False},
        )
        try:
            build_m5_storyboard(
                validated, _lines(), [{"start": 0.0, "duration": 1.0}],
                narration_duration_s=1.0, narration_path=voice, subtitle_path=subtitle,
                project_root=project, repo_root=ROOT,
            )
        except ManifestBridgeError:
            pass
        else:
            raise AssertionError("script, narration and timeline counts must match")


def test_explicit_mapping_uses_placement_ids_not_inventory_order():
    mapped = map_script_to_active_assets(_manifest(reverse_inventory=True), _lines())
    assert [(line["id"], asset.asset_id) for line, asset in mapped] == [
        ("line-a", "asset-a"), ("line-b", "asset-b")
    ]


def test_mapping_rejects_missing_or_duplicate_placement_ids():
    for lines in (
        [{"id": "line-a", "placement_id": "place-a"}],
        [
            {"id": "line-a", "placement_id": "place-a"},
            {"id": "line-b", "placement_id": "place-a"},
        ],
    ):
        try:
            map_script_to_active_assets(_manifest(), lines)
        except ManifestBridgeError:
            pass
        else:
            raise AssertionError("incomplete or duplicate placement mapping must fail closed")


def test_mapping_rejects_unknown_placement_and_asset_id_disagreement():
    for line in (
        {"id": "line-a", "placement_id": "not-in-timeline"},
        {"id": "line-a", "placement_id": "place-a", "asset_id": "asset-b"},
    ):
        lines = [line, _lines()[1]]
        try:
            map_script_to_active_assets(_manifest(), lines)
        except ManifestBridgeError:
            pass
        else:
            raise AssertionError("unknown or conflicting mapping must fail closed")


def test_mapping_rejects_timeline_order_conflicting_with_script_order():
    manifest = _manifest()
    manifest.timeline.reverse()
    try:
        map_script_to_active_assets(manifest, _lines())
    except ManifestBridgeError:
        pass
    else:
        raise AssertionError("script and manifest timeline order must agree explicitly")


def test_mapping_rejects_active_asset_used_in_multiple_placements():
    manifest = _manifest()
    manifest.timeline[1] = TimelinePlacement("place-b", "asset-a", "invalid reuse")
    try:
        map_script_to_active_assets(manifest, _lines())
    except ManifestBridgeError:
        pass
    else:
        raise AssertionError("one active asset cannot silently fill two placements")


def test_technical_preview_storyboard_is_silent_and_uses_active_manifest_asset():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "project"
        repo = Path(temp) / "repo"
        media = project / "assets" / "a.mp4"
        receipt = project / "receipts" / "a.json"
        media.parent.mkdir(parents=True)
        receipt.parent.mkdir(parents=True)
        media.write_bytes(b"technical preview fixture")
        receipt.write_text("{}", encoding="utf-8")
        media_hash = hashlib.sha256(media.read_bytes()).hexdigest()
        receipt_hash = hashlib.sha256(receipt.read_bytes()).hexdigest()
        asset = MediaAssetEnvelope(
            asset_id="asset-a", modality=MediaModality.VIDEO,
            placement_id="place-a", path="project://assets/a.mp4",
            sha256=media_hash, receipt_ref="a.json",
            asset_kind="GENERATED_VIDEO", generated=True,
            evidence_capable=False, evidence_use="VISUAL_SUPPORT",
            audio_policy="MUTE",
        )
        manifest = MediaManifest(
            assets=[asset], gate_states={"asset-a": GATE_PENDING_HUMAN_REVIEW},
            timeline=[TimelinePlacement("place-a", "asset-a", "active")],
        )
        validated = ValidatedManifest(
            manifest=manifest, manifest_path=project / "receipts" / "manifest.json",
            manifest_sha256="m" * 64, fingerprint="f" * 64,
            asset_paths={"asset-a": media}, receipt_paths={"asset-a": receipt},
            asset_sha256={"asset-a": media_hash},
            receipt_sha256={"asset-a": receipt_hash},
            active_audio_present={"asset-a": False},
        )
        with patch("contentops.media.manifest_m5_bridge.ffprobe_json",
                   return_value={"format": {"duration": "1.5"}}):
            storyboard, bridge = build_m5_storyboard(
                validated, [], project_root=project, repo_root=project,
                technical_preview=True,
            )
        assert len(storyboard["shots"]) == 1
        assert storyboard["shots"][0]["video"] == "assets/a.mp4"
        assert storyboard["shots"][0]["duration"] == 1.5
        assert storyboard["shots"][0]["audio_mode"] == "dub"
        assert "narration" not in storyboard and "subtitle" not in storyboard
        assert bridge["technical_sample_status"] == "TECHNICAL_SAMPLE_ONLY"
        assert bridge["production_ready"] is False
        assert bridge["publish_authorized"] is False


def main() -> int:
    tests = [
        test_easel_adapter_keeps_intermediate_out_of_pinned_runtime,
        test_manifest_script_stage_uses_active_mapping_not_legacy_asset_registry,
        test_manifest_script_stage_allows_visual_support_for_a_verified_claim,
        test_manifest_script_stage_refuses_generated_asset_claim_evidence,
        test_manifest_script_stage_refuses_missing_active_mapping,
        test_explicit_mapping_uses_placement_ids_not_inventory_order,
        test_storyboard_uses_measured_timing_and_active_video_clip,
        test_storyboard_refuses_asset_drift_after_manifest_validation,
        test_audio_policy_is_verified_against_active_video_bytes,
        test_storyboard_rejects_narration_timing_count_mismatch,
        test_mapping_rejects_missing_or_duplicate_placement_ids,
        test_mapping_rejects_unknown_placement_and_asset_id_disagreement,
        test_mapping_rejects_timeline_order_conflicting_with_script_order,
        test_mapping_rejects_active_asset_used_in_multiple_placements,
        test_technical_preview_storyboard_is_silent_and_uses_active_manifest_asset,
        test_structure_rejects_non_boolean_provenance_flags,
        test_structure_rejects_duplicate_asset_ids_and_placement_mismatch,
        test_structure_rejects_nonvisual_active_assets_and_empty_timelines,
        test_structure_prevents_resurrecting_audio_replaced_source,
        test_manifest_files_and_receipts_are_revalidated_and_hashed,
        test_manifest_rejects_traversal_before_following_asset_path,
        test_manifest_rejects_forged_serialized_gate_state,
        test_symlink_asset_escape_is_refused_when_symlinks_are_available,
    ]
    for test in tests:
        test()
        print(f"ok   {test.__name__}")
    print(f"\n{len(tests)}/{len(tests)} ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
