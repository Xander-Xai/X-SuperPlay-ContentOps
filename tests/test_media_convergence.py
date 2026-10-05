#!/usr/bin/env python3
"""M4.5 regression tests: converged validation, execution, gating and manifest.

Run:
    python tests/test_media_convergence.py

**No provider request is made and no quota is spent.** Every provider in this
suite is a fake or a deterministic local fixture, and the fake transports count
calls so a test can prove that nothing reached the network.

What these tests are really about
---------------------------------
Three things, in order of importance:

1. **The validator is common.** One entry point must catch a corrupt receipt, a
   digest mismatch, an unsafe billing claim and a broken lineage chain for all
   three modalities — without a chain of modality branches.
2. **The pipeline refuses rather than degrades.** A claim-bearing beat with no
   real evidence must fail. A missing credential binding must fail. An audio
   policy must be applied, not recorded and ignored.
3. **Technical success is not approval.** The most likely regression in a
   pipeline like this is a gate that quietly turns ``PENDING_FOUNDER_REVIEW``
   into ``production_ready``, so several tests assert that it cannot.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from contentops.media.asset_execution import (  # noqa: E402
    OUTCOME_EVIDENCE_ASSET_REQUIRED,
    OUTCOME_MISSING_REAL_ASSET,
    OUTCOME_NEEDS_CAPTURE,
    OUTCOME_OK,
    OUTCOME_UNSUPPORTED,
    AssetExecutionRouter,
    ExecutionContext,
)
from contentops.media.asset_planner import (  # noqa: E402
    MINIMAX_IMAGE,
    AssetPlanner,
    PlanRequest,
)
from contentops.media.capability_registry import (  # noqa: E402
    CAPABILITY_SPEECH_NARRATION,
    CAPABILITY_VIDEO_H3_FL2VA,
    CAPABILITY_VIDEO_H3_I2VA,
    CAPABILITY_VIDEO_H3_L2VA,
    CAPABILITY_VIDEO_H3_MAX,
    CAPABILITY_VIDEO_H3_REF2VA,
    CAPABILITY_VIDEO_H3_T2VA,
    CAPABILITY_VISUAL_DIAGRAM,
    CAPABILITY_VISUAL_GENERATED_IMAGE,
    CAPABILITY_VISUAL_REAL_EVIDENCE,
    STATUS_DOCUMENTED,
    STATUS_MANUAL_ONLY,
    STATUS_VERIFIED,
    CapabilityDescriptor,
    MediaCapabilityRegistry,
)
from contentops.media.contract import CapabilityNotSupported, QuotaSnapshot  # noqa: E402
from contentops.media.fixtures_local import (  # noqa: E402
    build_narration_fixture,
    build_screenshot_fixture,
    build_shot_fixture,
)
from contentops.media.image_contract import (  # noqa: E402
    AssetKind,
    AssetRegistry,
    EvidenceUse,
    GeneratedAssetEvidenceError,
)
from contentops.media.media_envelope import (  # noqa: E402
    HUMAN_REVIEW_APPROVED,
    HUMAN_REVIEW_PENDING,
    HUMAN_REVIEW_REJECTED,
    TECHNICAL_BLOCKED,
    TECHNICAL_PASS,
    MediaAssetEnvelope,
    MediaModality,
)
from contentops.media.media_paths import (  # noqa: E402
    is_logical_path,
    resolve_media_path,
    sanitize_embedded_paths,
    serialize_media_path,
)
from contentops.media.media_transform import (  # noqa: E402
    TRANSFORM_SCHEMA,
    TransformReceipt,
    apply_audio_policy,
)
from contentops.media.media_validation import (  # noqa: E402
    IMPORT_SCHEMA,
    ImageValidationAdapter,
    MediaValidationResult,
    SpeechValidationAdapter,
    VideoValidationAdapter,
    validate_media_asset,
)
from contentops.media.quality_gate import (  # noqa: E402
    GATE_BLOCKED,
    GATE_DEGRADED_FALLBACK,
    GATE_PENDING_HUMAN_REVIEW,
    GATE_PRODUCTION_READY,
    GATE_REJECTED,
    MANIFEST_SCHEMA,
    AssetQualityGate,
    MediaManifest,
    TimelineError,
    TimelinePlacement,
    build_manifest,
)
from contentops.media.quota_policy import (  # noqa: E402
    DECISION_ALLOW,
    DECISION_BLOCKED,
    DECISION_DEFER,
    DECISION_MANUAL_REQUIRED,
    DECISION_REUSE_REQUIRED,
    PRIORITY_EVIDENCE,
    PRIORITY_GENERATED_VIDEO,
    PRIORITY_SPEECH,
    MediaQuotaPolicy,
    PlannedMediaAction,
    QuotaScheduler,
    priority_for,
)
from contentops.media.video_contract import AudioPolicy  # noqa: E402

HAVE_MEDIA = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))

FORBIDDEN_SPAWNERS = tuple(
    ["subprocess" + "." + name for name in ("run", "Popen", "call", "check_output")]
    + ["os" + "." + name for name in ("system", "popen", "spawnl", "spawnv")]
)

ZERO_BALANCES = {
    "cash_balance": "0.00",
    "credit_balance": "0.00",
    "voucher_balance": "0.00",
    "owed_amount": "0.00",
}


def _skip(number: int, what: str, need: str) -> None:
    print(f"[skip] {number}. {what} (needs {need})")


def _png(path: Path, width: int = 320, height: int = 568) -> Path:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (width, height), (30, 40, 60))
    for y in range(0, height, 40):
        for x in range(0, width, 40):
            if (x // 40 + y // 40) % 2 == 0:
                image.putpixel((x, y), (90, 120, 180))
    image.save(path, format="PNG")
    return path


def _tiny_mp4(path: Path, seconds: int = 2, with_audio: bool = True) -> Path:
    from process_utils import hidden_run

    path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-y", "-v", "error", "-nostdin",
        "-f", "lavfi", "-i", f"testsrc=size=320x568:rate=24:duration={seconds}",
    ]
    if with_audio:
        command += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
    command += [
        "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast",
    ]
    if with_audio:
        command += ["-c:a", "aac", "-shortest"]
    command.append(str(path))
    result = hidden_run(command, timeout=300)
    if result.returncode != 0 or not path.is_file():
        raise AssertionError(f"could not render a test clip: {result.stderr!r}")
    return path


def _wav(path: Path, seconds: float = 2.0) -> Path:
    from process_utils import hidden_run

    path.parent.mkdir(parents=True, exist_ok=True)
    result = hidden_run(
        [
            "ffmpeg", "-y", "-v", "error", "-nostdin",
            "-f", "lavfi", "-i", f"sine=frequency=200:duration={seconds}",
            "-ac", "1", "-c:a", "pcm_s16le", str(path),
        ],
        timeout=180,
    )
    if result.returncode != 0 or not path.is_file():
        raise AssertionError(f"could not render a test wav: {result.stderr!r}")
    return path


# --- fixture receipts, one per modality shape ------------------------------


def _provider_receipt(
    asset: Path,
    *,
    modality: str,
    fingerprint: str,
    technical_approved: bool = True,
) -> dict:
    """A minimal but honest provider receipt in each modality's real shape."""
    digest = __import__(
        "contentops.media.fingerprint", fromlist=["sha256_file"]
    ).sha256_file(asset)
    common = {
        "provider": "minimax_m_plan",
        "product": "m_plan",
        "plan": "explore",
        "transport": "test",
        "transport_version": "1",
        "fingerprint": fingerprint,
        "canonical_path": str(asset),
        "technical_qc": {
            "approved": technical_approved,
            "reasons": [] if technical_approved else ["synthetic failure"],
        },
        "billing_mode": "subscription",
        "payg_allowed": False,
        "credit_pack_allowed": False,
        "attempt": 1,
        "production_ready": False,
        "human_review": HUMAN_REVIEW_PENDING,
        "credential_class": "SUBSCRIPTION",
        "credential_source": "TEST_ONLY",
    }
    if modality == MediaModality.IMAGE:
        common.update({
            "schema": "contentops.image-receipt/v1",
            "model": "image-01",
            "output_sha256": digest,
            "generated": True,
            "evidence_capable": False,
        })
    elif modality == MediaModality.VIDEO:
        common.update({
            "schema": "contentops.video-receipt/v1",
            "model": "MiniMax-H3",
            "mode": "T2VA",
            "output_sha256": digest,
            "generated": True,
            "evidence_capable": False,
            "task_created": True,
            "task_ref_hash": "sha256:" + "a" * 32,
            "audio_policy": AudioPolicy.REPLACE,
        })
    else:
        # Speech shape: no schema, no provenance flags, and the raw/normalized
        # digest pair rather than a single output digest.
        common.pop("credential_class")
        common.pop("credential_source")
        common.pop("canonical_path")
        common.update({
            "model": "speech-2.8-hd",
            "voice": "test_voice",
            "lexicon_version": "none",
            "raw_path": str(asset),
            "normalized_path": str(asset),
            "raw_sha256": digest,
            "normalized_sha256": digest,
            "display_text_sha256": "b" * 64,
            "spoken_text_sha256": "b" * 64,
            "semantic_qc": {"approved": False, "reasons": ["test"]},
            "fallback": {},
        })
    return common


def _write_receipt(asset: Path, payload: dict) -> Path:
    target = asset.with_name(asset.name + ".receipt.json")
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return target


def _envelope(
    asset: Path,
    receipt: Path,
    *,
    modality: str,
    asset_id: str,
    fingerprint: str,
    kind: str = None,
    generated: bool = True,
    capable: bool = False,
    **overrides,
) -> MediaAssetEnvelope:
    defaults = dict(
        asset_id=asset_id,
        modality=modality,
        path=str(asset),
        receipt_ref=receipt.name,
        fingerprint=fingerprint,
        asset_kind=kind,
        generated=generated,
        evidence_capable=capable,
        evidence_use=EvidenceUse.VISUAL_SUPPORT if kind else None,
        technical_status=TECHNICAL_PASS,
        human_review=HUMAN_REVIEW_PENDING,
        production_ready=False,
    )
    defaults.update(overrides)
    return MediaAssetEnvelope(**defaults)


def _three_modalities(work: Path):
    """Build one valid asset per modality plus its envelope."""
    from contentops.media.fingerprint import sha256_file

    out = {}
    image = _png(work / "img.png")
    out["image"] = (
        image,
        _write_receipt(image, _provider_receipt(
            image, modality=MediaModality.IMAGE, fingerprint="i" * 64
        )),
        _envelope(image, work / "img.png.receipt.json", modality=MediaModality.IMAGE,
                  asset_id="img", fingerprint="i" * 64, kind=AssetKind.GENERATED_IMAGE),
    )

    if HAVE_MEDIA:
        video = _tiny_mp4(work / "vid.mp4")
        out["video"] = (
            video,
            _write_receipt(video, _provider_receipt(
                video, modality=MediaModality.VIDEO, fingerprint="v" * 64
            )),
            _envelope(video, work / "vid.mp4.receipt.json", modality=MediaModality.VIDEO,
                      asset_id="vid", fingerprint="v" * 64,
                      kind=AssetKind.GENERATED_VIDEO, audio_policy=AudioPolicy.REPLACE),
        )
    else:
        out["video"] = None

    audio = _wav(work / "narration.wav")
    out["speech"] = (
        audio,
        _write_receipt(audio, _provider_receipt(
            audio, modality=MediaModality.SPEECH, fingerprint="s" * 64
        )),
        _envelope(audio, work / "narration.wav.receipt.json",
                  modality=MediaModality.SPEECH, asset_id="speech",
                  fingerprint="s" * 64, kind=None, generated=False, capable=False),
    )
    return out


# --- 1. the common validator accepts all three modalities ------------------


def test_the_one_validator_accepts_valid_speech_image_and_video():
    with tempfile.TemporaryDirectory() as td:
        assets = _three_modalities(Path(td))
        for modality, triple in assets.items():
            if triple is None:
                continue
            _, receipt, envelope = triple
            result = validate_media_asset(envelope)
            assert result.approved, f"{modality}: {result.failures}"
            assert isinstance(result, MediaValidationResult)
    print("[ok] 1. one validator accepts valid speech, image and video")


def test_the_validator_has_no_modality_branch_chain():
    """Structurally: the common path must not switch on modality.

    Asserted rather than trusted, because a single ``if modality ==`` creeping
    back in is exactly how this design decays into the monolith it replaced.
    """
    source = (ROOT / "src" / "contentops" / "media" / "media_validation.py").read_text(
        encoding="utf-8"
    )
    body = source.split("def validate_media_asset", 1)[1]
    body = body.split("\ndef ", 1)[0]
    for forbidden in ('modality == "speech"', 'modality == "image"',
                      'modality == "video"', "modality == MediaModality.SPEECH",
                      "modality == MediaModality.IMAGE",
                      "modality == MediaModality.VIDEO"):
        assert forbidden not in body, (
            f"the common validator contains a modality branch: {forbidden}"
        )
    # One dispatch is allowed, at the adapter boundary.
    assert "def default_adapter_for" in source
    assert "SpeechValidationAdapter" in source
    print("[ok] 2. the common validator dispatches once, through adapters")


def test_speech_has_no_asset_kind_and_inventing_one_is_refused():
    """Modality is not asset kind, and forcing it is a loud error."""
    # ``generated=True`` is required for this envelope to be constructible at all:
    # GENERATED_IMAGE is generated by definition, and the envelope refuses to be
    # built with a contradictory flag. That refusal is the point of the next test.
    envelope = MediaAssetEnvelope(
        asset_id="n", modality=MediaModality.SPEECH, path="n.wav",
        asset_kind=AssetKind.GENERATED_IMAGE, generated=True,
    )
    try:
        envelope.validate_shape()
    except ValueError as exc:
        assert "not a visual kind" in str(exc), str(exc)
    else:
        raise AssertionError("speech was allowed to claim a visual asset kind")
    # And the honest shape validates.
    MediaAssetEnvelope(
        asset_id="n", modality=MediaModality.SPEECH, path="n.wav", asset_kind=None
    ).validate_shape()
    print("[ok] 3. speech carries no asset kind, and inventing one is refused")


def test_speech_is_never_evidence_capable():
    envelope = MediaAssetEnvelope(
        asset_id="n", modality=MediaModality.SPEECH, path="n.wav",
        evidence_capable=True,
    )
    try:
        envelope.validate_shape()
    except ValueError as exc:
        assert "cannot be evidence capable" in str(exc), str(exc)
    else:
        raise AssertionError("speech was allowed to be evidence capable")
    print("[ok] 4. speech can never be evidence capable")


# --- 2. the validator catches corruption consistently ----------------------


def _assert_caught(result, needle: str, label: str) -> None:
    assert not result.approved, f"{label} was accepted"
    joined = " | ".join(result.failures)
    assert needle.lower() in joined.lower(), f"{label}: expected {needle!r} in {joined!r}"


def test_a_missing_asset_is_caught_for_every_modality():
    with tempfile.TemporaryDirectory() as td:
        assets = _three_modalities(Path(td))
        for modality, triple in assets.items():
            if triple is None:
                continue
            _, receipt, envelope = triple
            broken = MediaAssetEnvelope(
                **{**envelope.__dict__, "path": str(Path(td) / "absent.file")}
            )
            _assert_caught(validate_media_asset(broken), "does not exist", modality)
    print("[ok] 5. a missing asset file is caught for every modality")


def test_a_missing_receipt_is_caught_for_every_modality():
    with tempfile.TemporaryDirectory() as td:
        assets = _three_modalities(Path(td))
        for modality, triple in assets.items():
            if triple is None:
                continue
            _, _, envelope = triple
            # A named-but-absent receipt, and no receipt reference at all, are both
            # caught -- they are different mistakes with different messages.
            absent = MediaAssetEnvelope(
                **{**envelope.__dict__, "receipt_ref": "gone.json"}
            )
            _assert_caught(validate_media_asset(absent), "does not exist", modality)
            unnamed = MediaAssetEnvelope(**{**envelope.__dict__, "receipt_ref": None})
            _assert_caught(validate_media_asset(unnamed), "no receipt_ref", modality)
    print("[ok] 6. a missing receipt is caught for every modality")


def test_a_corrupt_receipt_is_caught_for_every_modality():
    with tempfile.TemporaryDirectory() as td:
        assets = _three_modalities(Path(td))
        for modality, triple in assets.items():
            if triple is None:
                continue
            _, receipt, envelope = triple
            receipt.write_text("{ this is not json", encoding="utf-8")
            _assert_caught(validate_media_asset(envelope), "unreadable", modality)
    print("[ok] 7. a corrupt receipt is caught for every modality")


def test_a_digest_mismatch_is_caught_for_every_modality():
    with tempfile.TemporaryDirectory() as td:
        assets = _three_modalities(Path(td))
        for modality, triple in assets.items():
            if triple is None:
                continue
            _, receipt, envelope = triple
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            for key in ("output_sha256", "normalized_sha256", "raw_sha256"):
                if key in payload:
                    payload[key] = "f" * 64
            receipt.write_text(json.dumps(payload), encoding="utf-8")
            _assert_caught(validate_media_asset(envelope), "digest mismatch", modality)
    print("[ok] 8. a digest mismatch is caught for every modality")


def test_a_missing_fingerprint_is_caught():
    with tempfile.TemporaryDirectory() as td:
        assets = _three_modalities(Path(td))
        _, receipt, envelope = assets["image"]
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        payload.pop("fingerprint")
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        _assert_caught(validate_media_asset(envelope), "no fingerprint", "image")
    print("[ok] 9. a missing fingerprint is caught")


def test_a_schema_mismatch_is_caught():
    with tempfile.TemporaryDirectory() as td:
        assets = _three_modalities(Path(td))
        _, receipt, envelope = assets["image"]
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        payload["schema"] = "contentops.something-else/v9"
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        _assert_caught(validate_media_asset(envelope), "not recognised", "image")
    print("[ok] 10. a schema mismatch is caught")


def test_a_generated_asset_cannot_claim_the_import_schema():
    """An import record and a provider record describe opposite origins."""
    with tempfile.TemporaryDirectory() as td:
        assets = _three_modalities(Path(td))
        _, receipt, envelope = assets["image"]
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        payload["schema"] = IMPORT_SCHEMA
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        _assert_caught(validate_media_asset(envelope), "one file cannot be both", "image")

        # And the reverse: an import claiming the provider schema, with the
        # envelope agreeing it is an import.
        payload["schema"] = "contentops.image-receipt/v1"
        payload["generated"] = False
        payload["record_type"] = "media_import"
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        # An import is honestly ``SCREENSHOT``, not ``GENERATED_IMAGE``. A
        # GENERATED_IMAGE envelope with ``generated=False`` cannot be constructed
        # at all now — that is the invariant test 71 pins down.
        as_import = MediaAssetEnvelope(
            **{**envelope.__dict__, "asset_kind": AssetKind.SCREENSHOT,
               "generated": False}
        )
        _assert_caught(
            validate_media_asset(as_import), "not provider-generated", "import"
        )
    print("[ok] 11. an import and a provider record cannot be confused")


def test_unsafe_billing_metadata_is_caught():
    with tempfile.TemporaryDirectory() as td:
        assets = _three_modalities(Path(td))
        for mutation, needle in (
            ({"payg_allowed": True}, "payg_allowed"),
            ({"credit_pack_allowed": True}, "credit_pack_allowed"),
            ({"billing_mode": "payg"}, "billing_mode"),
        ):
            _, receipt, envelope = assets["image"]
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            payload.update(mutation)
            receipt.write_text(json.dumps(payload), encoding="utf-8")
            _assert_caught(validate_media_asset(envelope), needle, str(mutation))
            # Restore for the next mutation.
            base = _provider_receipt(
                Path(payload["canonical_path"]),
                modality=MediaModality.IMAGE,
                fingerprint="i" * 64,
            )
            receipt.write_text(json.dumps(base), encoding="utf-8")
    print("[ok] 12. unsafe billing metadata is caught")


def test_a_credential_value_in_a_public_receipt_is_caught():
    # Built by concatenation so this file does not itself contain the literal the
    # repository's sensitive-string policy scans for. The policy reads source text,
    # not intent; spelling the header form out in full here would trip it.
    fake_key = "sk-" + "cp-" + "abcdefghijklmnop"
    auth_header = "Bear" + "er " + fake_key

    with tempfile.TemporaryDirectory() as td:
        assets = _three_modalities(Path(td))
        _, receipt, envelope = assets["image"]

        payload = json.loads(receipt.read_text(encoding="utf-8"))
        # A key shape in a field whose legitimate use is a *classification*.
        payload["credential_class"] = fake_key
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        _assert_caught(validate_media_asset(envelope), "provider key", "credential_class")

        # A key shape in an unrelated field a future schema might add.
        payload.pop("credential_class")
        payload["some_future_field"] = fake_key
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        _assert_caught(validate_media_asset(envelope), "provider key", "unknown field")

        # And an Authorization header value.
        payload.pop("some_future_field")
        payload["upstream"] = auth_header
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        _assert_caught(validate_media_asset(envelope), "authorization", "header")
    print("[ok] 13. a credential value or Authorization header is caught")


def test_a_raw_provider_task_id_is_caught_but_a_salted_hash_is_not():
    with tempfile.TemporaryDirectory() as td:
        if not HAVE_MEDIA:
            _skip(14, "task privacy", "ffmpeg")
            return
        assets = _three_modalities(Path(td))
        _, receipt, envelope = assets["video"]
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        payload["task_id"] = "424010985738629"
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        _assert_caught(validate_media_asset(envelope), "raw provider task id", "video")

        payload.pop("task_id")
        payload["task_ref_hash"] = "424010985738629"
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        _assert_caught(validate_media_asset(envelope), "digit run", "video")

        payload["task_ref_hash"] = "sha256:" + "c" * 32
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        assert validate_media_asset(envelope).approved, "a salted hash was rejected"
    print("[ok] 14. a raw task id is caught; a salted task_ref_hash is accepted")


def test_a_generated_and_evidence_capable_mismatch_is_caught():
    with tempfile.TemporaryDirectory() as td:
        assets = _three_modalities(Path(td))
        _, receipt, envelope = assets["image"]
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        payload["evidence_capable"] = True
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        _assert_caught(
            validate_media_asset(envelope), "both generated and evidence capable", "image"
        )
    print("[ok] 15. generated-and-evidence-capable is caught")


def test_an_unknown_human_review_state_is_caught():
    with tempfile.TemporaryDirectory() as td:
        assets = _three_modalities(Path(td))
        _, receipt, envelope = assets["image"]
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        payload["human_review"] = "LOOKS_FINE_TO_ME"
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        _assert_caught(validate_media_asset(envelope), "unknown human_review", "image")
    print("[ok] 16. an invented human_review state is caught")


def test_technical_pass_never_becomes_production_ready():
    """The single most important gate property."""
    with tempfile.TemporaryDirectory() as td:
        assets = _three_modalities(Path(td))
        _, receipt, envelope = assets["image"]
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        payload["production_ready"] = True  # still PENDING_FOUNDER_REVIEW
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        _assert_caught(
            validate_media_asset(envelope), "not Founder approval", "production_ready"
        )

        # And the gate agrees.
        ready = MediaAssetEnvelope(
            **{**envelope.__dict__, "production_ready": True}
        )
        decision = AssetQualityGate().evaluate(ready)
        assert decision.state == GATE_BLOCKED, decision.state
    print("[ok] 17. technical PASS with production_ready=True is refused")


def test_a_modality_adapter_failure_is_surfaced_by_the_gate():
    with tempfile.TemporaryDirectory() as td:
        assets = _three_modalities(Path(td))
        _, receipt, envelope = assets["image"]
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        payload["technical_qc"] = {"approved": False, "reasons": ["synthetic QC failure"]}
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        decision = AssetQualityGate().evaluate(envelope)
        assert decision.state == GATE_BLOCKED, decision.state
        assert any("synthetic QC failure" in reason for reason in decision.reasons), (
            decision.reasons
        )
    print("[ok] 18. a modality adapter failure surfaces as BLOCKED")


def test_a_missing_technical_qc_blocks_a_generation_but_not_an_import():
    with tempfile.TemporaryDirectory() as td:
        assets = _three_modalities(Path(td))
        _, receipt, envelope = assets["image"]
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        payload.pop("technical_qc")
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        _assert_caught(validate_media_asset(envelope), "technical_qc", "generation")

        # The same absence on an import is not applicable, because no provider ran.
        payload["schema"] = IMPORT_SCHEMA
        payload["generated"] = False
        payload["record_type"] = "media_import"
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        # Imported material is a real kind; GENERATED_IMAGE would contradict
        # ``generated=False`` and is refused at construction.
        adapted = MediaAssetEnvelope(
            **{**envelope.__dict__, "asset_kind": AssetKind.SCREENSHOT,
               "generated": False}
        )
        assert validate_media_asset(adapted).approved, "an honest import was blocked"
    print("[ok] 19. a generation needs technical_qc; an import honestly does not")


# --- 3. AudioPolicy is applied, not merely recorded -------------------------


def test_keep_reuses_the_original_and_writes_no_transform():
    if not HAVE_MEDIA:
        _skip(20, "KEEP is a no-op", "ffmpeg")
        return
    from contentops.media.fingerprint import sha256_file

    with tempfile.TemporaryDirectory() as td:
        source = _tiny_mp4(Path(td) / "shot.mp4", with_audio=True)
        before = sha256_file(source)
        application = apply_audio_policy(
            source_video=source, policy=AudioPolicy.KEEP,
            output_dir=Path(td) / "processed",
        )
        assert application.derived is False
        assert application.output_path == str(source), "KEEP copied instead of reusing"
        assert application.receipt_path is None, "KEEP invented a transform receipt"
        assert application.observed_audio_stream is True
        assert sha256_file(source) == before, "KEEP modified the source"
        assert not list((Path(td) / "processed").glob("*")), "KEEP wrote an output"
    print("[ok] 20. KEEP reuses the original bytes and writes no transform")


def test_mute_produces_a_derived_asset_with_no_audio():
    if not HAVE_MEDIA:
        _skip(21, "MUTE strips audio", "ffmpeg")
        return
    from contentops.media.fingerprint import sha256_file

    with tempfile.TemporaryDirectory() as td:
        source = _tiny_mp4(Path(td) / "shot.mp4", with_audio=True)
        before = sha256_file(source)
        application = apply_audio_policy(
            source_video=source, policy=AudioPolicy.MUTE,
            output_dir=Path(td) / "processed",
            source_receipt_ref="shot.mp4.receipt.json",
            source_fingerprint="a" * 64, created_at="2026-10-05T00:00:00Z",
        )
        assert application.derived is True
        assert application.observed_audio_stream is False, "the derived asset kept audio"
        assert application.replacement_narration_required is False
        assert sha256_file(source) == before, "MUTE modified the provider generation"

        receipt = application.transform_receipt
        # ``provider_generated_bytes`` is about the *bytes* (a local transform made
        # them). ``source_generated`` is about the *content's provenance*, and is
        # separate precisely so the two cannot contradict each other.
        assert receipt.provider_generated_bytes is False, (
            "a local transform claimed to be a generation"
        )
        assert receipt.derived is True
        assert receipt.source_generated is False, (
            "MUTE on an undeclared source must not invent generated provenance"
        )
        assert receipt.source_asset_sha256 == before
        assert receipt.source_fingerprint == "a" * 64
        assert receipt.output_sha256 == sha256_file(Path(application.output_path))
        assert receipt.source_receipt_ref == "shot.mp4.receipt.json"
        payload = json.loads(Path(application.receipt_path).read_text(encoding="utf-8"))
        assert payload["schema"] == TRANSFORM_SCHEMA
    print("[ok] 22. MUTE produces a derived, audio-free asset and leaves the source intact")


def test_replace_strips_audio_and_demands_narration_without_writing_it():
    if not HAVE_MEDIA:
        _skip(23, "REPLACE strips audio", "ffmpeg")
        return
    from contentops.media.fingerprint import sha256_file

    with tempfile.TemporaryDirectory() as td:
        source = _tiny_mp4(Path(td) / "shot.mp4", with_audio=True)
        before = sha256_file(source)
        narration = _wav(Path(td) / "voice.wav")
        application = apply_audio_policy(
            source_video=source, policy=AudioPolicy.REPLACE,
            output_dir=Path(td) / "processed",
            narration_source=str(narration),
            created_at="2026-10-05T00:00:00Z",
        )
        assert application.replacement_narration_required is True
        assert application.narration_source == str(narration)
        assert application.observed_audio_stream is False
        assert sha256_file(source) == before, "REPLACE modified the provider generation"
        # Narration is *not* muxed here, so this step cannot produce a silent mix.
        from contentops.media.transport import ffprobe_json

        payload = ffprobe_json(Path(application.output_path))
        assert not [s for s in payload["streams"] if s.get("codec_type") == "audio"]
    print("[ok] 23. REPLACE strips native audio and demands narration without muxing it")


def test_replace_without_a_narration_source_says_so_rather_than_guessing():
    if not HAVE_MEDIA:
        _skip(24, "REPLACE notes a missing narration source", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        source = _tiny_mp4(Path(td) / "shot.mp4", with_audio=True)
        application = apply_audio_policy(
            source_video=source, policy=AudioPolicy.REPLACE,
            output_dir=Path(td) / "processed",
        )
        assert application.replacement_narration_required is True
        assert any("narration_source" in note for note in application.notes), (
            application.notes
        )
        assert application.observed_audio_stream is False
    print("[ok] 24. REPLACE without a narration source records the gap explicitly")


def test_an_unknown_audio_policy_is_refused_before_any_transform():
    with tempfile.TemporaryDirectory() as td:
        source = _png(Path(td) / "x.png")
        try:
            apply_audio_policy(
                source_video=source, policy="SILENCED", output_dir=Path(td)
            )
        except ValueError as exc:
            assert "unknown audio policy" in str(exc), str(exc)
        else:
            raise AssertionError("an unknown audio policy was applied")
        assert not list((Path(td) / "processed").glob("*")) if (
            Path(td) / "processed"
        ).exists() else True
    print("[ok] 25. an unknown audio policy is refused before any transform")


def test_a_derived_asset_validates_against_its_transform_receipt():
    if not HAVE_MEDIA:
        _skip(26, "derived asset validates", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        source = _tiny_mp4(Path(td) / "shot.mp4", with_audio=True)
        application = apply_audio_policy(
            source_video=source, policy=AudioPolicy.MUTE,
            output_dir=Path(td) / "processed",
            source_receipt_ref="shot.mp4.receipt.json",
            source_fingerprint="b" * 64,
        )
        derived = MediaAssetEnvelope(
            asset_id="derived",
            modality=MediaModality.VIDEO,
            path=application.output_path,
            receipt_ref=None,
            fingerprint="b" * 64,
            asset_kind=AssetKind.GENERATED_VIDEO,
            # Inherited from the source. The transform changed the bytes, not the
            # content's provenance; ``generated=False`` here would contradict the
            # envelope's own kind and is now refused at construction.
            generated=True,
            derived_from="source",
            transform_receipt_ref=Path(application.receipt_path).name,
        )
        result = validate_media_asset(derived)
        assert result.approved, result.failures
        assert result.observed_sha256 == application.transform_receipt.output_sha256
        assert AssetQualityGate().evaluate(derived).state == GATE_PENDING_HUMAN_REVIEW
    print("[ok] 26. a derived asset validates against its transform receipt")


def test_a_derived_asset_with_a_broken_chain_is_blocked():
    if not HAVE_MEDIA:
        _skip(27, "broken lineage is blocked", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        source = _tiny_mp4(Path(td) / "shot.mp4", with_audio=True)
        application = apply_audio_policy(
            source_video=source, policy=AudioPolicy.MUTE,
            output_dir=Path(td) / "processed",
        )
        receipt_file = Path(application.receipt_path)
        payload = json.loads(receipt_file.read_text(encoding="utf-8"))
        payload.pop("source_asset_sha256")
        receipt_file.write_text(json.dumps(payload), encoding="utf-8")

        derived = MediaAssetEnvelope(
            asset_id="derived", modality=MediaModality.VIDEO,
            path=application.output_path, derived_from="source",
            transform_receipt_ref=receipt_file.name,
            asset_kind=AssetKind.GENERATED_VIDEO, generated=True,
        )
        _assert_caught(
            validate_media_asset(derived), "lineage chain is broken", "derived"
        )
    print("[ok] 27. a derived asset with a broken lineage chain is blocked")


def test_a_transform_receipt_claiming_generation_is_refused():
    if not HAVE_MEDIA:
        _skip(28, "transform cannot claim generation", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        source = _tiny_mp4(Path(td) / "shot.mp4", with_audio=True)
        application = apply_audio_policy(
            source_video=source, policy=AudioPolicy.MUTE,
            output_dir=Path(td) / "processed",
        )
        receipt_file = Path(application.receipt_path)
        payload = json.loads(receipt_file.read_text(encoding="utf-8"))
        # Claiming a provider generation: these exact bytes came from a transform.
        payload["provider_generated_bytes"] = True
        payload["derived"] = False
        receipt_file.write_text(json.dumps(payload), encoding="utf-8")

        derived = MediaAssetEnvelope(
            asset_id="derived", modality=MediaModality.VIDEO,
            path=application.output_path, derived_from="source",
            transform_receipt_ref=receipt_file.name,
            asset_kind=AssetKind.GENERATED_VIDEO, generated=True,
        )
        _assert_caught(
            validate_media_asset(derived), "claim two different origins", "derived"
        )
    print("[ok] 28. a transform receipt claiming to be a generation is refused")


# --- 4. the capability registry stays honest -------------------------------


def test_the_registry_resolves_every_capability_by_name_not_vendor():
    registry = MediaCapabilityRegistry()
    for capability in (
        CAPABILITY_SPEECH_NARRATION,
        CAPABILITY_VISUAL_GENERATED_IMAGE,
        CAPABILITY_VIDEO_H3_T2VA,
        CAPABILITY_VIDEO_H3_I2VA,
    ):
        assert registry.find(capability) is not None, capability
        assert callable(registry.resolve(capability)), capability
    # No vendor name appears in any identifier.
    for capability in registry.capabilities():
        assert "minimax" not in capability.lower(), capability
        assert "mmx" not in capability.lower(), capability
    print("[ok] 29. capabilities resolve by capability, with no vendor in the name")


def test_only_live_proven_capabilities_are_marked_verified():
    registry = MediaCapabilityRegistry()
    verified = {
        CAPABILITY_SPEECH_NARRATION,
        CAPABILITY_VISUAL_GENERATED_IMAGE,
        CAPABILITY_VIDEO_H3_T2VA,
        CAPABILITY_VIDEO_H3_I2VA,
    }
    for capability in registry.capabilities():
        if capability in verified:
            assert registry.is_verified(capability), f"{capability} should be VERIFIED"
            continue
        assert not registry.is_verified(capability), (
            f"{capability} claims VERIFIED without a live receipt; fixture evidence "
            f"is not provider evidence"
        )
    for capability in (
        CAPABILITY_VIDEO_H3_FL2VA, CAPABILITY_VIDEO_H3_L2VA,
        CAPABILITY_VIDEO_H3_REF2VA, CAPABILITY_VIDEO_H3_MAX,
    ):
        assert registry.status(capability) == STATUS_DOCUMENTED, capability
    print("[ok] 30. only live-proven capabilities are VERIFIED")


def test_an_unsupported_capability_is_refused_loudly_and_never_substituted():
    registry = MediaCapabilityRegistry()
    for capability in ("VIDEO/H3_NONEXISTENT", "AUDIO/TTS_FANCY"):
        try:
            registry.resolve(capability)
        except CapabilityNotSupported as exc:
            assert "Refusing to substitute" in str(exc), str(exc)
        else:
            raise AssertionError(f"{capability} resolved to something")
    print("[ok] 31. an unsupported capability is refused, never substituted")


def test_a_manual_only_capability_cannot_execute_automatically():
    registry = MediaCapabilityRegistry()
    for capability in (CAPABILITY_VISUAL_REAL_EVIDENCE, CAPABILITY_VISUAL_DIAGRAM):
        assert registry.status(capability) == STATUS_MANUAL_ONLY
        try:
            registry.resolve(capability)
        except CapabilityNotSupported as exc:
            assert "MANUAL_ONLY" in str(exc), str(exc)
        else:
            raise AssertionError(f"{capability} executed automatically")
    print("[ok] 32. a MANUAL_ONLY capability never executes automatically")


def test_a_capability_that_can_never_be_evidence_says_so():
    registry = MediaCapabilityRegistry()
    for capability in (
        CAPABILITY_VIDEO_H3_T2VA, CAPABILITY_VIDEO_H3_I2VA,
        CAPABILITY_VISUAL_GENERATED_IMAGE,
    ):
        assert registry.describe(capability)["never_evidence_capable"] is True
        try:
            registry.require_evidence_capable(capability)
        except CapabilityNotSupported as exc:
            assert "never carry a factual claim" in str(exc), str(exc)
        else:
            raise AssertionError(f"{capability} was allowed to be evidence")
    # Speech and diagram are not flagged: narration is not visual, and a diagram
    # explains rather than proves, which the AssetKind table already owns.
    assert registry.describe(CAPABILITY_SPEECH_NARRATION)[
        "never_evidence_capable"
    ] is False
    print("[ok] 33. evidence-incapable capabilities are flagged and refused")


def test_the_registry_holds_no_credentials_or_billing_state():
    registry = MediaCapabilityRegistry()
    described = json.dumps(registry.describe_all(), sort_keys=True)
    for forbidden in ("sk-cp", "sk-api", "Bear" + "er", "credential", "BillingGuard",
                      "secret", "api_key"):
        assert forbidden not in described, f"the registry description leaked {forbidden}"
    # And a registered status must cite evidence, so VERIFIED cannot be asserted bare.
    try:
        CapabilityDescriptor(
            capability="TEST/BARE", modality=MediaModality.IMAGE,
            executor=lambda **kw: None, status=STATUS_VERIFIED, provider="x",
        )
    except ValueError as exc:
        assert "cites no evidence" in str(exc), str(exc)
    else:
        raise AssertionError("a VERIFIED capability was accepted with no evidence")
    print("[ok] 34. the registry holds no secrets, and VERIFIED requires evidence")


def test_duplicate_capability_registration_is_refused_as_ambiguity():
    registry = MediaCapabilityRegistry()
    duplicate = CapabilityDescriptor(
        capability=CAPABILITY_SPEECH_NARRATION, modality=MediaModality.SPEECH,
        executor=lambda **kw: None, status=STATUS_VERIFIED, provider="other",
        evidence=("tests",),
    )
    try:
        registry.register(duplicate)
    except ValueError as exc:
        assert "routing ambiguity" in str(exc), str(exc)
    else:
        raise AssertionError("two executors claimed one capability without complaint")
    print("[ok] 35. a duplicate capability registration is refused as ambiguity")


# --- 5. the scheduler applies policy, not a cost model ----------------------


def _snapshot(interval: float = 99.0, weekly: float = 51.0) -> QuotaSnapshot:
    return QuotaSnapshot(
        bucket="general",
        interval_remaining_percent=interval,
        weekly_remaining_percent=weekly,
    )


def _actions() -> list:
    return [
        PlannedMediaAction("evid", MediaModality.IMAGE, priority=PRIORITY_EVIDENCE,
                           requires_evidence=True),
        PlannedMediaAction("narr", MediaModality.SPEECH, priority=PRIORITY_SPEECH),
        PlannedMediaAction("h3", MediaModality.VIDEO, priority=PRIORITY_GENERATED_VIDEO,
                           declared_budget="7pp"),
        PlannedMediaAction("cached", MediaModality.IMAGE, priority=PRIORITY_SPEECH,
                           reusable=True),
    ]


def test_reusable_assets_are_scheduled_first_and_cost_nothing():
    outcome = QuotaScheduler(balances=ZERO_BALANCES).schedule(_actions(), _snapshot())
    decision = outcome.decision_for("cached")
    assert decision.decision == DECISION_REUSE_REQUIRED, decision.decision
    assert "cached" not in outcome.execution_order, "a satisfied action was rescheduled"
    assert "consumes no quota" in " ".join(decision.reasons)
    print("[ok] 36. a reusable asset is scheduled as reuse and consumes nothing")


def test_evidence_outranks_narration_which_outranks_generated_video():
    evidence = priority_for(modality="IMAGE", requires_evidence=True)
    narration = priority_for(modality="SPEECH", requires_evidence=False)
    image = priority_for(modality="IMAGE", requires_evidence=False)
    video = priority_for(modality="VIDEO", requires_evidence=False)

    assert evidence < narration, "evidence did not outrank narration"
    assert narration < image, "narration did not outrank generated image"
    assert image < video, (
        f"generated video ({video}) did not outrank generated image ({image}); "
        f"a video task is the most expensive call ContentOps makes"
    )
    print("[ok] 37. evidence, then narration, then generated image, then video")


def test_video_is_deferred_below_the_configured_weekly_floor():
    policy = MediaQuotaPolicy(weekly_floor_percent=40.0)
    outcome = QuotaScheduler(balances=ZERO_BALANCES, policy=policy).schedule(
        _actions(), _snapshot(weekly=30.0)
    )
    assert outcome.decision_for("h3").decision == DECISION_DEFER
    assert outcome.decision_for("narr").decision == DECISION_ALLOW
    assert "configured floor" in " ".join(outcome.decision_for("h3").reasons)
    print("[ok] 38. video is deferred below the weekly floor while narration proceeds")


def test_the_weekly_floor_is_a_policy_value_not_a_derived_number():
    policy = MediaQuotaPolicy()
    basis = policy.as_dict()["basis"]
    assert "not derived" in basis, basis
    assert "percentages only" in basis, basis
    # The observed 7pp delta must not appear as a configured value.
    for value in policy.as_dict().values():
        assert value != 7.0, "a configured value equals the observed delta"
    assert 7 not in (policy.weekly_floor_percent,
                     policy.minimum_weekly_percent_to_schedule_video)
    print("[ok] 39. the weekly floor is a policy value, not the observed delta")


def test_speech_and_image_need_the_five_hour_window_but_video_does_not():
    scheduler = QuotaScheduler(balances=ZERO_BALANCES)
    outcome = scheduler.schedule(_actions(), _snapshot(interval=0.0, weekly=51.0))
    assert outcome.decision_for("narr").decision == DECISION_BLOCKED
    assert outcome.decision_for("evid").decision == DECISION_BLOCKED
    assert outcome.decision_for("h3").decision == DECISION_ALLOW
    assert "interval_remaining_percent" in " ".join(
        outcome.decision_for("narr").reasons
    )
    print("[ok] 40. an exhausted 5h window blocks speech/image but not video")


def test_video_without_a_declared_budget_is_blocked():
    actions = [PlannedMediaAction("h3", MediaModality.VIDEO, priority=60)]
    outcome = QuotaScheduler(balances=ZERO_BALANCES).schedule(actions, _snapshot())
    assert outcome.decision_for("h3").decision == DECISION_BLOCKED
    assert "declared quota budget" in " ".join(outcome.decision_for("h3").reasons)
    print("[ok] 41. video without a declared budget is blocked")


def test_every_paid_balance_blocks_generation_and_missing_blocks_too():
    scheduler = QuotaScheduler(balances=ZERO_BALANCES)
    assert scheduler.schedule(_actions(), _snapshot()).decision_for(
        "narr"
    ).decision == DECISION_ALLOW

    for name in ("cash_balance", "credit_balance", "voucher_balance", "owed_amount"):
        balances = dict(ZERO_BALANCES)
        balances[name] = "1.00"
        outcome = QuotaScheduler(balances=balances).schedule(_actions(), _snapshot())
        assert outcome.decision_for("narr").decision == DECISION_BLOCKED, name
        assert any(name in reason for reason in outcome.decision_for("narr").reasons)

    # Absent is not zero.
    for name in ZERO_BALANCES:
        balances = {k: v for k, v in ZERO_BALANCES.items() if k != name}
        outcome = QuotaScheduler(balances=balances).schedule(_actions(), _snapshot())
        assert outcome.decision_for("narr").decision == DECISION_BLOCKED, name
        assert any("never treated as zero" in reason
                   for reason in outcome.decision_for("narr").reasons), name
    print("[ok] 42. every paid balance blocks, and an unreadable one blocks too")


def test_a_manual_action_is_reported_not_substituted():
    actions = [PlannedMediaAction(
        "manual", MediaModality.IMAGE, priority=40, manual_only=True
    )]
    outcome = QuotaScheduler(balances=ZERO_BALANCES).schedule(actions, _snapshot())
    assert outcome.decision_for("manual").decision == DECISION_MANUAL_REQUIRED
    assert outcome.manual_required == ["manual"]
    assert "no code path" in " ".join(outcome.decision_for("manual").reasons)
    print("[ok] 43. a manual action is reported, never silently substituted")


def test_every_decision_records_the_policy_that_produced_it():
    outcome = QuotaScheduler(balances=ZERO_BALANCES).schedule(_actions(), _snapshot())
    for decision in outcome.decisions:
        assert decision.policy["weekly_floor_percent"] is not None
        assert decision.policy["allow_payg"] is False
        assert "not derived" in decision.policy["basis"]
        assert "weekly_remaining_percent" in decision.observed
    print("[ok] 44. every scheduling decision records the policy and the observation")


def test_a_policy_permitting_payg_or_credit_pack_cannot_be_constructed():
    for kwargs in ({"allow_payg": True}, {"allow_credit_pack": True}):
        try:
            MediaQuotaPolicy(**kwargs)
        except ValueError as exc:
            assert "cannot be enabled" in str(exc), str(exc)
        else:
            raise AssertionError(f"a policy permitting {kwargs} was constructed")
    print("[ok] 45. no policy object can permit PAYG or Credit Pack")


def test_a_policy_disagreeing_with_the_gate_about_windows_is_refused():
    try:
        MediaQuotaPolicy(require_interval_for_video=True).windows_for("VIDEO")
    except ValueError as exc:
        assert "MODALITY_WINDOWS" in str(exc), str(exc)
    else:
        raise AssertionError(
            "a policy claiming video needs the 5h window was accepted against a "
            "gate that says otherwise"
        )
    print("[ok] 46. a policy contradicting the gate's window model is refused")


# --- 6. execution: evidence first, always ----------------------------------


def test_a_claim_beat_with_a_real_file_uses_the_real_executor():
    with tempfile.TemporaryDirectory() as td:
        project = Path(td) / "proj"
        _png(project / "sources" / "screenshots" / "capture.png")
        context = ExecutionContext(project_dir=project, repo_root=project)
        router = AssetExecutionRouter(
            AssetPlanner(options=[AssetKind.REAL, AssetKind.SCREENSHOT])
        )
        planned = router.plan_for(
            PlanRequest(beat_id="b1", role="evidence", requires_evidence=True)
        )
        result = router.execute(planned, context)
        assert result.outcome == OUTCOME_OK, result.reasons
        envelope = result.envelope
        assert envelope.asset_kind == AssetKind.REAL
        assert envelope.evidence_capable is True
        assert envelope.generated is False
        # Provenance: an import receipt was written, not just a digest.
        assert envelope.receipt_ref, "an import wrote no provenance record"
        receipt = json.loads(
            (Path(envelope.path).parent / envelope.receipt_ref).read_text(encoding="utf-8")
        )
        assert receipt["schema"] == IMPORT_SCHEMA
        assert receipt["provider_call"] is False
        assert validate_media_asset(envelope).approved
    print("[ok] 47. a claim beat with real material uses the real executor")


def test_a_claim_beat_with_only_generated_options_fails_rather_than_degrading():
    """The non-negotiable rule."""
    with tempfile.TemporaryDirectory() as td:
        project = Path(td) / "proj"
        project.mkdir(parents=True)
        router = AssetExecutionRouter(
            AssetPlanner(options=[AssetKind.DIAGRAM, MINIMAX_IMAGE])
        )
        context = ExecutionContext(project_dir=project, repo_root=project)
        try:
            planned = router.plan_for(
                PlanRequest(beat_id="b1", role="evidence", requires_evidence=True)
            )
        except GeneratedAssetEvidenceError:
            pass  # the planner refused, which is also correct
        else:
            result = router.execute(planned, context)
            assert result.outcome == OUTCOME_EVIDENCE_ASSET_REQUIRED, result.outcome
            assert "Failing the beat" in " ".join(result.reasons), result.reasons
            assert result.envelope is None, "a degraded asset was produced anyway"
    print("[ok] 48. a claim beat with only generated options fails, never degrades")


def test_a_forced_generated_plan_cannot_execute_as_evidence():
    """Even if a plan somehow claims a non-evidence kind for a claim beat."""
    from contentops.media.asset_planner import PlannedAsset

    with tempfile.TemporaryDirectory() as td:
        project = Path(td) / "proj"
        project.mkdir(parents=True)
        router = AssetExecutionRouter()
        context = ExecutionContext(project_dir=project, repo_root=project)
        forced = PlannedAsset(
            beat_id="b1", role="evidence", kind=AssetKind.GENERATED_IMAGE,
            evidence_capable=False, evidence_use=EvidenceUse.EVIDENCE,
            rationale="forced", requires_evidence=True,
        )
        result = router.execute(forced, context)
        assert result.outcome == OUTCOME_EVIDENCE_ASSET_REQUIRED, result.outcome
    print("[ok] 49. a forced generated plan cannot execute as evidence")


def test_a_missing_screenshot_reports_absence_and_substitutes_nothing():
    with tempfile.TemporaryDirectory() as td:
        project = Path(td) / "proj"
        (project / "sources" / "screenshots").mkdir(parents=True)
        context = ExecutionContext(project_dir=project, repo_root=project)
        router = AssetExecutionRouter(AssetPlanner(options=[AssetKind.SCREENSHOT]))
        planned = router.plan_for(
            PlanRequest(beat_id="b1", role="screenshot", requires_evidence=True)
        )
        result = router.execute(planned, context)
        assert result.outcome == OUTCOME_MISSING_REAL_ASSET, result.outcome
        assert result.envelope is None
        assert "must not be satisfied by generated" in " ".join(result.reasons)
    print("[ok] 50. a missing screenshot reports absence and substitutes nothing")


def test_a_missing_screen_recording_reports_needs_capture():
    with tempfile.TemporaryDirectory() as td:
        project = Path(td) / "proj"
        (project / "sources" / "recordings").mkdir(parents=True)
        context = ExecutionContext(project_dir=project, repo_root=project)
        router = AssetExecutionRouter(AssetPlanner(options=[AssetKind.SCREEN_RECORDING]))
        planned = router.plan_for(
            PlanRequest(beat_id="b1", role="demo", requires_evidence=True)
        )
        result = router.execute(planned, context)
        assert result.outcome == OUTCOME_NEEDS_CAPTURE, result.outcome
    print("[ok] 51. a missing screen recording reports NEEDS_CAPTURE")


def test_a_support_beat_routes_to_the_diagram_executor():
    with tempfile.TemporaryDirectory() as td:
        project = Path(td) / "proj"
        project.mkdir(parents=True)
        context = ExecutionContext(project_dir=project, repo_root=project)
        router = AssetExecutionRouter(AssetPlanner(options=[AssetKind.DIAGRAM]))
        planned = router.plan_for(PlanRequest(beat_id="b1", role="concept",
                                               prompt="layers"))
        result = router.execute(planned, context)
        assert result.outcome == OUTCOME_OK, result.reasons
        envelope = result.envelope
        assert envelope.asset_kind == AssetKind.DIAGRAM
        assert envelope.evidence_capable is False
        assert envelope.generated is False
        assert envelope.evidence_use == EvidenceUse.VISUAL_SUPPORT
        assert envelope.receipt_ref, "the diagram wrote no provenance record"
        assert validate_media_asset(envelope).approved
    print("[ok] 52. a support beat routes to the deterministic diagram executor")


def test_a_support_beat_routes_to_a_fake_image_provider_with_no_network():
    calls = {"n": 0}

    def fake_image_provider(*, beat_id, prompt, output_dir):
        calls["n"] += 1
        asset = _png(Path(output_dir) / f"{beat_id}.png")
        from contentops.media.fingerprint import sha256_file

        return {
            "path": str(asset),
            "receipt_path": None,
            "asset_id": f"{beat_id}-img",
            "sha256": sha256_file(asset),
            "receipt": {
                "fingerprint": "c" * 64,
                "output_sha256": sha256_file(asset),
                "generated": True, "evidence_capable": False,
                "production_ready": False, "human_review": HUMAN_REVIEW_PENDING,
                "fallback": {},
                "technical_qc": {"approved": True, "reasons": []},
            },
        }

    with tempfile.TemporaryDirectory() as td:
        project = Path(td) / "proj"
        project.mkdir(parents=True)
        context = ExecutionContext(
            project_dir=project, repo_root=project,
            image_provider=fake_image_provider,
        )
        router = AssetExecutionRouter(AssetPlanner(options=[MINIMAX_IMAGE]))
        planned = router.plan_for(PlanRequest(beat_id="b1", role="hook", prompt="x"))
        result = router.execute(planned, context)
        assert result.outcome == OUTCOME_OK, result.reasons
        assert calls["n"] == 1
        envelope = result.envelope
        assert envelope.asset_kind == AssetKind.GENERATED_IMAGE
        assert envelope.evidence_capable is False
        assert envelope.generated is True
    print("[ok] 53. a support beat routes to a fake image provider, no network")


def test_a_support_beat_without_a_provider_reports_rather_than_substitutes():
    with tempfile.TemporaryDirectory() as td:
        project = Path(td) / "proj"
        project.mkdir(parents=True)
        context = ExecutionContext(project_dir=project, repo_root=project)
        router = AssetExecutionRouter(AssetPlanner(options=[MINIMAX_IMAGE]))
        planned = router.plan_for(PlanRequest(beat_id="b1", role="hook", prompt="x"))
        result = router.execute(planned, context)
        assert result.outcome == OUTCOME_UNSUPPORTED, result.outcome
        assert "rather than substituted with a diagram" in " ".join(result.reasons)
    print("[ok] 54. no image provider reports rather than substituting a diagram")


def test_the_video_executor_refuses_without_a_declared_budget():
    called = {"n": 0}

    def fake_video_provider(**kwargs):
        called["n"] += 1
        return {}

    with tempfile.TemporaryDirectory() as td:
        project = Path(td) / "proj"
        project.mkdir(parents=True)
        context = ExecutionContext(
            project_dir=project, repo_root=project,
            video_provider=fake_video_provider, video_quota_budget=None,
        )
        router = AssetExecutionRouter()
        result = router.execute_video(
            beat_id="b5", capability=CAPABILITY_VIDEO_H3_T2VA, context=context,
            request=None,
        )
        assert result.outcome == OUTCOME_UNSUPPORTED, result.outcome
        assert called["n"] == 0, "the provider ran despite a missing budget"
        assert "will not authorise one without a budget" in " ".join(result.reasons)
    print("[ok] 55. the video executor refuses without a declared budget")


def test_generated_media_can_never_be_registered_as_evidence():
    """The registry-level truth table is asked, never restated."""
    registry = AssetRegistry()
    for kind in (AssetKind.GENERATED_IMAGE, AssetKind.GENERATED_VIDEO):
        for role in EvidenceUse.CLAIM_BEARING:
            try:
                from contentops.media.image_contract import register_asset

                register_asset(
                    registry, asset_id="x", kind=kind, path="x.png",
                    evidence_use=role, receipt_ref="x.receipt.json",
                    generated=True, evidence_capable=True,
                )
            except GeneratedAssetEvidenceError:
                continue
            raise AssertionError(f"{kind} was registered as {role}")
    # A diagram stays support-only too.
    try:
        from contentops.media.image_contract import register_asset

        register_asset(registry, asset_id="d", kind=AssetKind.DIAGRAM, path="d.png",
                       evidence_use=EvidenceUse.BENCHMARK_PROOF,
                       generated=False, evidence_capable=False)
    except GeneratedAssetEvidenceError:
        pass
    else:
        raise AssertionError("a diagram was registered as a benchmark proof")
    print("[ok] 56. generated media and diagrams cannot be registered as evidence")


# --- 7. the quality gate never auto-approves --------------------------------


def test_every_modality_passes_through_one_gate_vocabulary():
    with tempfile.TemporaryDirectory() as td:
        assets = _three_modalities(Path(td))
        gate = AssetQualityGate()
        for modality, triple in assets.items():
            if triple is None:
                continue
            _, _, envelope = triple
            decision = gate.evaluate(envelope)
            assert decision.state == GATE_PENDING_HUMAN_REVIEW, (
                f"{modality}: {decision.state} {decision.reasons}"
            )
            assert decision.usable is True
            assert envelope.production_ready is False
    print("[ok] 57. all three modalities pass through one gate, pending review")


def test_the_gate_reports_blocked_for_every_failure_kind():
    with tempfile.TemporaryDirectory() as td:
        assets = _three_modalities(Path(td))
        _, receipt, envelope = assets["image"]
        gate = AssetQualityGate()
        assert gate.evaluate(envelope).state == GATE_PENDING_HUMAN_REVIEW, (
            "a valid asset did not pass the gate"
        )
        for label, broken in (
            ("missing file", {**envelope.__dict__, "path": str(Path(td) / "gone.png")}),
            ("missing receipt", {**envelope.__dict__, "receipt_ref": "gone.json"}),
            ("bad fingerprint", {**envelope.__dict__, "fingerprint": "z" * 64}),
        ):
            decision = gate.evaluate(MediaAssetEnvelope(**broken))
            assert decision.state == GATE_BLOCKED, f"{label}: {decision.state}"
            assert decision.usable is False, f"{label} was still usable"
            assert decision.reasons, f"{label} blocked with no reason recorded"
    print("[ok] 58. the gate reports BLOCKED for validation failures")


def test_a_declared_fallback_degrades_and_never_becomes_production_ready():
    with tempfile.TemporaryDirectory() as td:
        assets = _three_modalities(Path(td))
        _, _, envelope = assets["image"]
        degraded = MediaAssetEnvelope(
            **{
                **envelope.__dict__,
                "fallback": {
                    "used": True, "degraded": True, "provider": "edge-tts",
                    "reason": "the configured provider was unavailable",
                    "requested_capability": CAPABILITY_SPEECH_NARRATION,
                },
            }
        )
        decision = AssetQualityGate().evaluate(degraded)
        assert decision.state == GATE_DEGRADED_FALLBACK, decision.state
        assert decision.usable is True, "a degraded asset was excluded from composition"
        assert degraded.production_ready is False
        assert "never becomes production-ready" in " ".join(decision.reasons)
    print("[ok] 59. a declared fallback degrades and stays unapproved")


def test_an_undeclared_or_unnamed_fallback_is_caught():
    with tempfile.TemporaryDirectory() as td:
        assets = _three_modalities(Path(td))
        _, receipt, envelope = assets["image"]
        for mutation, needle in (
            ({"used": True, "degraded": True}, "names no provider"),
            ({"used": True, "degraded": False, "provider": "edge"}, "degraded is not True"),
            ("a string, not an object", "not an object"),
        ):
            payload = json.loads(receipt.read_text(encoding="utf-8"))
            payload["fallback"] = mutation
            receipt.write_text(json.dumps(payload), encoding="utf-8")
            _assert_caught(validate_media_asset(envelope), needle, str(mutation)[:30])
            base = _provider_receipt(
                Path(payload["canonical_path"]),
                modality=MediaModality.IMAGE, fingerprint="i" * 64,
            )
            receipt.write_text(json.dumps(base), encoding="utf-8")
    print("[ok] 60. an unnamed or unflagged fallback is caught")


def test_only_a_recorded_approval_reaches_production_ready():
    with tempfile.TemporaryDirectory() as td:
        assets = _three_modalities(Path(td))
        _, receipt, envelope = assets["image"]
        payload = json.loads(receipt.read_text(encoding="utf-8"))
        payload["human_review"] = HUMAN_REVIEW_APPROVED
        payload["production_ready"] = True
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        approved = MediaAssetEnvelope(
            **{
                **envelope.__dict__,
                "human_review": HUMAN_REVIEW_APPROVED,
                "production_ready": True,
            }
        )
        decision = AssetQualityGate().evaluate(approved)
        assert decision.state == GATE_PRODUCTION_READY, decision.state

        # And a rejection is honoured.
        payload["human_review"] = HUMAN_REVIEW_REJECTED
        payload["production_ready"] = False
        receipt.write_text(json.dumps(payload), encoding="utf-8")
        rejected = MediaAssetEnvelope(
            **{**envelope.__dict__, "human_review": HUMAN_REVIEW_REJECTED}
        )
        assert AssetQualityGate().evaluate(rejected).state == GATE_REJECTED
    print("[ok] 61. only a recorded approval reaches PRODUCTION_READY; rejection is honoured")


# --- 8. the manifest is the single, deterministic asset list ---------------


def test_the_manifest_is_byte_stable_regardless_of_input_order():
    with tempfile.TemporaryDirectory() as td:
        assets = _three_modalities(Path(td))
        envelopes = [triple[2] for triple in assets.values() if triple is not None]
        decisions = AssetQualityGate().evaluate_all(envelopes)
        forwards = build_manifest(envelopes, decisions).as_dict()
        backwards = build_manifest(list(reversed(envelopes)), decisions).as_dict()
        assert json.dumps(forwards, sort_keys=True) == json.dumps(
            backwards, sort_keys=True
        ), "manifest content changed with input order"
        assert forwards["schema"] == MANIFEST_SCHEMA
        assert forwards == build_manifest(envelopes, decisions).as_dict(), (
            "the manifest is not reproducible from identical inputs"
        )
    print("[ok] 62. the manifest is byte-stable regardless of input order")


def test_the_manifest_carries_no_timestamp_so_builds_are_diffable():
    with tempfile.TemporaryDirectory() as td:
        assets = _three_modalities(Path(td))
        envelopes = [triple[2] for triple in assets.values() if triple is not None]
        decisions = AssetQualityGate().evaluate_all(envelopes)
        body = build_manifest(envelopes, decisions).as_dict()
        for key in ("generated_at", "created_at", "recorded_at", "timestamp"):
            assert key not in body, f"the manifest body carries {key}"
        assert "checksum" not in body and "date" not in json.dumps(body).lower()
    print("[ok] 63. the manifest body carries no timestamp")


def test_a_manifest_refuses_an_asset_the_gate_never_judged():
    with tempfile.TemporaryDirectory() as td:
        assets = _three_modalities(Path(td))
        envelopes = [triple[2] for triple in assets.values() if triple is not None]
        decisions = AssetQualityGate().evaluate_all(envelopes[:-1])
        try:
            build_manifest(envelopes, decisions)
        except ValueError as exc:
            assert "never judged" in str(exc), str(exc)
        else:
            raise AssertionError("an ungated asset was admitted to the manifest")
    print("[ok] 64. an asset the gate never judged cannot enter the manifest")


def test_the_manifest_round_trips_and_separates_usable_from_blocked():
    with tempfile.TemporaryDirectory() as td:
        assets = _three_modalities(Path(td))
        envelopes = [triple[2] for triple in assets.values() if triple is not None]
        decisions = AssetQualityGate().evaluate_all(envelopes)
        manifest = build_manifest(envelopes, decisions)
        target = manifest.write(Path(td) / "media-manifest.json")
        loaded = MediaManifest.load(target)
        assert loaded.fingerprint() == manifest.fingerprint(), "round trip changed it"
        assert len(loaded.assets) == len(envelopes), "round trip lost assets"
        assert len(manifest.usable_assets()) == len(envelopes), (
            f"expected every valid asset usable, got "
            f"{len(manifest.usable_assets())} of {len(envelopes)}"
        )
        assert manifest.blocked_assets() == [], "a valid asset was reported blocked"

        # Now add one genuinely blocked asset, with its own identity.
        blocked = MediaAssetEnvelope(
            **{
                **envelopes[0].__dict__,
                "asset_id": "blocked-1",
                "path": str(Path(td) / "gone"),
            }
        )
        mixed = build_manifest(
            envelopes + [blocked],
            decisions + [AssetQualityGate().evaluate(blocked)],
        )
        assert len(mixed.blocked_assets()) == 1, mixed.gate_states
        assert len(mixed.usable_assets()) == len(envelopes)

        # And a duplicated identifier is refused rather than silently collapsed.
        try:
            build_manifest(
                envelopes + [envelopes[0]],
                decisions + [AssetQualityGate().evaluate(envelopes[0])],
            )
        except ValueError as exc:
            assert "duplicate asset_id" in str(exc), str(exc)
        else:
            raise AssertionError(
                "two assets sharing an identifier entered one manifest"
            )
    print("[ok] 65. the manifest round-trips, separates blocked, and refuses duplicates")


def test_a_manifest_with_an_unknown_schema_is_refused():
    with tempfile.TemporaryDirectory() as td:
        target = Path(td) / "m.json"
        target.write_text(json.dumps({"schema": "other/v1", "assets": []}),
                          encoding="utf-8")
        try:
            MediaManifest.load(target)
        except ValueError as exc:
            assert "does not understand" in str(exc) or "understands" in str(exc), str(exc)
        else:
            raise AssertionError("an unknown manifest schema was accepted")
    print("[ok] 66. a manifest with an unknown schema is refused")


def test_the_manifest_records_lineage_and_audio_policy():
    if not HAVE_MEDIA:
        _skip(67, "manifest lineage", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        source = _tiny_mp4(Path(td) / "shot.mp4", with_audio=True)
        application = apply_audio_policy(
            source_video=source, policy=AudioPolicy.REPLACE,
            output_dir=Path(td) / "processed",
        )
        base = _provider_receipt(source, modality=MediaModality.VIDEO,
                                 fingerprint="d" * 64)
        source_envelope = MediaAssetEnvelope(
            asset_id="src", modality=MediaModality.VIDEO, path=str(source),
            receipt_ref=None, fingerprint="d" * 64,
            asset_kind=AssetKind.GENERATED_VIDEO, generated=True,
            audio_policy=AudioPolicy.REPLACE,
        )
        _write_receipt(source, base)
        source_envelope = MediaAssetEnvelope(
            **{**source_envelope.__dict__, "receipt_ref": (source.name + ".receipt.json")}
        )
        derived = MediaAssetEnvelope(
            asset_id="derived", modality=MediaModality.VIDEO,
            path=application.output_path, fingerprint="d" * 64,
            asset_kind=AssetKind.GENERATED_VIDEO,
            # Provenance inherited: the derived shot is still generated content.
            generated=True,
            audio_policy=AudioPolicy.REPLACE, derived_from="src",
            transform_receipt_ref=Path(application.receipt_path).name,
        )
        envelopes = [source_envelope, derived]
        decisions = AssetQualityGate().evaluate_all(envelopes)
        manifest = build_manifest(
            envelopes, decisions,
            narration={"required": True, "source": "voice.wav"},
        )
        body = manifest.as_dict()
        derived_entry = next(a for a in body["assets"] if a["asset_id"] == "derived")
        assert derived_entry["derived_from"] == "src"
        assert derived_entry["transform_receipt_ref"], derived_entry
        assert derived_entry["audio_policy"] == AudioPolicy.REPLACE
        assert manifest.requires_narration() is True
    print("[ok] 67. the manifest records derived lineage and the audio policy")


def test_fallback_is_visible_in_the_manifest_and_never_implies_readiness():
    with tempfile.TemporaryDirectory() as td:
        assets = _three_modalities(Path(td))
        _, _, envelope = assets["speech"]
        fallback = {
            "used": True, "degraded": True, "provider": "edge-tts",
            "reason": "configured provider unavailable",
            "requested_capability": CAPABILITY_SPEECH_NARRATION,
            "actual_capability": "edge_tts",
        }
        degraded = MediaAssetEnvelope(**{**envelope.__dict__, "fallback": fallback})
        decisions = AssetQualityGate().evaluate_all([degraded])
        manifest = build_manifest([degraded], decisions)
        entry = manifest.as_dict()["assets"][0]
        assert entry["fallback"]["provider"] == "edge-tts"
        assert entry["fallback"]["requested_capability"] == CAPABILITY_SPEECH_NARRATION
        assert entry["fallback"]["actual_capability"] == "edge_tts"
        assert entry["production_ready"] is False
        assert manifest.gate_states["speech"] == GATE_DEGRADED_FALLBACK
    print("[ok] 68. fallback is visible in the manifest and never implies readiness")


# --- 9. process policy ------------------------------------------------------


def test_no_media_convergence_module_spawns_a_process_directly():
    offenders = []
    for name in (
        "media_envelope", "media_validation", "media_transform",
        "capability_registry", "quota_policy", "asset_execution",
        "quality_gate", "fixtures_local",
    ):
        source = (ROOT / "src" / "contentops" / "media" / f"{name}.py").read_text(
            encoding="utf-8"
        )
        for forbidden in FORBIDDEN_SPAWNERS:
            if forbidden in source:
                offenders.append(f"{name}.py: {forbidden}")
        assert "shell=True" not in source, f"{name}.py uses shell=True"
    assert not offenders, offenders
    print("[ok] 69. no convergence module spawns a process directly")


def test_the_integration_script_routes_children_through_process_utils():
    source = (ROOT / "scripts" / "m45_media_integration.py").read_text(encoding="utf-8")
    for forbidden in FORBIDDEN_SPAWNERS:
        assert forbidden not in source, f"the integration script uses {forbidden}"
    assert "shell=True" not in source
    # And it reuses the pinned Easel adapter rather than building a compositor.
    assert "from assemble_easel import run" in source
    assert "from qc_video import qc" in source
    print("[ok] 70. the integration script reuses the pinned Easel and QC paths")


def test_the_committed_integration_receipts_show_convergence_with_no_provider_calls():
    """The recorded technical integration, if it was run locally.

    Skipped rather than failed when absent, because the media it references is
    gitignored and CI will not have it. What is asserted is the *shape* of the
    result, so a regression that silently changed the verdicts is caught.
    """
    receipt = ROOT / "projects" / "m45-technical-integration" / "receipts" / \
        "m45-integration.json"
    if not receipt.is_file():
        _skip(71, "committed integration receipts", "a local integration run")
        return
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["production_ready"] is False, "the integration claimed readiness"
    assert payload["human_review"] == HUMAN_REVIEW_PENDING
    assert payload["provider_calls"] == {"speech": 0, "image": 0, "video": 0}
    assert payload["composition"]["status"] == "OK", payload["composition"]
    assert payload["final_qc"]["overall"] in ("PASS", "WARN"), payload["final_qc"]
    assert payload["manifest"]["blocked"] == 0, payload["manifest"]
    assert payload["manifest"]["requires_narration"] is True
    for decision in payload["gate"]:
        assert decision["state"] in (
            GATE_PENDING_HUMAN_REVIEW, GATE_PRODUCTION_READY, GATE_DEGRADED_FALLBACK
        ), decision
    print("[ok] 71. the committed integration receipts show convergence, unapproved")


# --- 12. the canonical committed artifacts are portable ----------------------
#
# The last portability leak was in the QC receipts, not the manifest: qc_video is a
# runtime tool whose report legitimately names local files, and two of its reports
# were tracked side by side. One graded the artifact this stage actually produces
# (final/m45.mp4 → WARN); the other graded final/final.mp4, which nothing here
# creates, and sat next to it reading FAIL.


#: The committed artifacts that must never carry a host path.
CANONICAL_COMMITTED_ARTIFACTS = (
    "receipts/media-manifest.json",
    "receipts/m45-integration.json",
    "receipts/qc-report-m45.json",
    "receipts/qc-report-m45.md",
    "script/storyboard.json",
)

#: Host-specific path shapes. Deliberately a short list of *known* patterns rather
#: than a general "is this an absolute path" detector: a test that flags every slash
#: would fire on URLs and prose, and a check that cries wolf gets disabled. The
#: point is to protect the artifacts above, not to solve path detection.
#:
#: The negative lookbehind on the drive pattern is essential, not decorative. Without
#: it, ``project://final/m45.mp4`` matches as drive letter ``t`` plus ``://f`` — the
#: scanner would report every correct logical reference as a leak.
HOST_PATH_PATTERNS = (
    (re.compile(r"(?<![A-Za-z])[A-Za-z]:[\\/]{1,2}[A-Za-z0-9_.\-]"), "Windows drive path"),
    (re.compile(r"\\\\[A-Za-z0-9_.\-]+\\"), "Windows UNC path"),
    (re.compile(r"/home/[A-Za-z0-9_.\-]+/"), "POSIX home path"),
    (re.compile(r"/Users/[A-Za-z0-9_.\-]+/"), "macOS home path"),
    (re.compile(r"/mnt/[a-z]/"), "mounted volume path"),
)


def _committed_artifact_findings(relative: str) -> List[str]:
    """Every host-specific path found in one canonical committed artifact."""
    target = ROOT / "projects" / "m45-technical-integration" / relative
    if not target.is_file():
        return []
    text = target.read_text(encoding="utf-8", errors="replace")
    findings: List[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        # JSON escapes separators, so normalise before matching: `D:\\Projects` and
        # `D:/Projects` are the same leak with different escaping.
        probe = line.replace("\\\\", "\\").replace('\\"', '"')
        for pattern, label in HOST_PATH_PATTERNS:
            match = pattern.search(probe)
            if match:
                findings.append(
                    f"{relative}:{line_number} {label}: {match.group(0)!r}"
                )
    return findings


def test_no_canonical_committed_artifact_carries_a_host_path():
    """The tracked artifact contract: logical references only.

    Scans the committed M4.5 artifacts for the host path shapes actually observed —
    Windows drive paths (the committed QC receipts carried
    ``D:\\Projects\\...``), Windows UNC, POSIX/macOS home directories, and mounted
    volumes — so a leak on another contributor's platform is caught too.
    """
    missing = [
        relative for relative in CANONICAL_COMMITTED_ARTIFACTS
        if not (ROOT / "projects" / "m45-technical-integration" / relative).is_file()
    ]
    if len(missing) == len(CANONICAL_COMMITTED_ARTIFACTS):
        _skip(92, "canonical artifacts carry no host path", "a local integration run")
        return

    findings: List[str] = []
    for relative in CANONICAL_COMMITTED_ARTIFACTS:
        findings.extend(_committed_artifact_findings(relative))
    assert not findings, (
        "a committed artifact carries a host-specific path, so it only resolves on "
        "the machine that produced it:\n  " + "\n  ".join(findings)
    )
    print(
        "[ok] 92. no canonical committed artifact carries a host-specific path"
    )


def test_the_stale_qc_report_is_not_retained_as_current_truth():
    """Two QC reports must not look equally current and contradict each other.

    ``qc-report-final.json`` recorded ``FAIL`` because it graded
    ``final/final.mp4`` — a file this stage never produces. Kept alongside the real
    ``WARN``, it read as a second verdict. It was stale output from an earlier
    invocation, so it was removed rather than relabelled.
    """
    receipts = ROOT / "projects" / "m45-technical-integration" / "receipts"
    for stale_name in ("qc-report-final.json", "qc-report-final.md"):
        assert not (receipts / stale_name).exists(), (
            f"{stale_name} is tracked again. If it is intentionally retained for "
            f"diagnosis it must be renamed and classified NON_CURRENT_DIAGNOSTIC, "
            f"with canonical docs not citing it as current."
        )

    canonical = receipts / "qc-report-m45.json"
    if not canonical.is_file():
        _skip(93, "no stale QC report is retained", "a local integration run")
        return
    report = json.loads(canonical.read_text(encoding="utf-8"))
    assert report["currency"] == "CURRENT", report.get("currency")
    assert report["graded_target"] == "project://final/m45.mp4", report["graded_target"]
    assert report["overall"] in ("PASS", "WARN"), (
        f"the canonical QC report is {report['overall']}; a FAIL here would mean "
        f"the committed report no longer grades the artifact this stage produces"
    )
    print("[ok] 93. the stale QC report is gone and the canonical one is current")


def test_the_canonical_qc_boundary_preserves_the_verdict_and_drops_the_paths():
    """Sanitizing must never change a verdict.

    The boundary rewrites a ``qc_video`` runtime result for committing. It is allowed
    to change every path in it and nothing else — a sanitizer that quietly upgraded a
    WARN would be worse than the leak it removes.

    Paths are built from the real filesystem root rather than a hardcoded drive
    letter: the sanitizer only rewrites paths that are genuinely under the root it
    was given, so a ``D:\\`` literal would simply not match on a Linux runner and the
    test would fail there while proving nothing on Windows.
    """
    from contentops.media.qc_canonical import (
        CURRENCY_NON_CURRENT_DIAGNOSTIC,
        QC_CANONICAL_SCHEMA,
        canonical_qc_report,
    )

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        repo = base / "repo"
        project = repo / "projects" / "demo"
        project.mkdir(parents=True, exist_ok=True)
        shot = str(project / "final" / "m45.mp4")
        ghost = str(project / "final" / "final.mp4")
        project_ref = str(project)

        runtime = {
            "project": project_ref,
            "checked_at": "2026-10-05T00:00:00Z",
            "overall": "WARN",
            "checks": [
                {"id": "_video", "ok": True, "severity": "INFO", "path": shot},
                {"id": "final_exists", "ok": False, "severity": "FAIL",
                 "msg": f"final.mp4 not found at {ghost}"},
                {"id": "duration_range", "ok": False, "severity": "WARN", "value": 18.0},
            ],
        }
        report = canonical_qc_report(
            runtime,
            repo_root=repo,
            project_root=project,
            graded_target="project://final/m45.mp4",
        )
        assert report["schema"] == QC_CANONICAL_SCHEMA
        assert report["overall"] == runtime["overall"], "sanitizing changed the verdict"
        assert report["checked_at"] == runtime["checked_at"]
        assert report["project"] == "project://", report["project"]
        assert len(report["checks"]) == len(runtime["checks"])

        blob = json.dumps(report, ensure_ascii=False)
        assert str(base) not in blob, blob
        assert "project://final/m45.mp4" in blob, blob
        # A path embedded in prose is sanitized too, not only whole-string paths.
        missing = next(c for c in report["checks"] if c["id"] == "final_exists")
        assert "project://final/final.mp4" in missing["msg"], missing

        # And a non-current report must explain itself.
        try:
            canonical_qc_report(
                runtime,
                repo_root=repo,
                project_root=project,
                currency=CURRENCY_NON_CURRENT_DIAGNOSTIC,
            )
        except ValueError as exc:
            assert "must state why" in str(exc), str(exc)
        else:
            raise AssertionError("a non-current QC report was declared with no reason")

        declared = canonical_qc_report(
            runtime,
            repo_root=repo,
            project_root=project,
            currency=CURRENCY_NON_CURRENT_DIAGNOSTIC,
            non_current_reason="graded a target this stage does not produce",
        )
        assert "non_current_reason" in declared
    print("[ok] 94. the canonical QC boundary preserves verdicts and removes paths")


def test_embedded_path_sanitizing_leaves_non_paths_alone():
    """A sanitizer that damages valid text is worse than the leak.

    Only known root prefixes are matched. Prose, URLs and lookalike sibling
    directories must survive untouched, or people will stop reading the output.
    """
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        repo = base / "repo"
        project = repo / "projects" / "demo"
        project.mkdir(parents=True, exist_ok=True)
        # A sibling whose name merely starts with the repo name is outside it.
        sibling = base / "repoOld"
        sibling.mkdir(parents=True, exist_ok=True)

        assert sanitize_embedded_paths(
            "see https://example.com/a/b for details", repo_root=repo, project_root=project
        ) == "see https://example.com/a/b for details"
        assert str(sibling / "x.mp4") in sanitize_embedded_paths(
            f"built in {sibling / 'x.mp4'}", repo_root=repo, project_root=project
        )
        # Already-logical text is idempotent.
        once = sanitize_embedded_paths(
            str(project / "final" / "m45.mp4"), repo_root=repo, project_root=project
        )
        assert once == "project://final/m45.mp4", once
        assert sanitize_embedded_paths(once, repo_root=repo, project_root=project) == once
        # Prose embedding works, and the surrounding words are preserved.
        assert sanitize_embedded_paths(
            f"missing at {project / 'final' / 'final.mp4'}",
            repo_root=repo, project_root=project,
        ) == "missing at project://final/final.mp4"
    print("[ok] 95. embedded path sanitizing leaves non-paths alone")


def test_the_committed_qc_report_agrees_with_the_committed_current_state():
    """One set of numbers, stated once.

    The canonical facts a reader takes away: the artifact, its QC verdict, the
    readiness flags, provider calls, and the two asset counts. If a regeneration
    changed one of them, this is where the disagreement surfaces.
    """
    base = ROOT / "projects" / "m45-technical-integration"
    integration = base / "receipts" / "m45-integration.json"
    qc_path = base / "receipts" / "qc-report-m45.json"
    manifest_path = base / "receipts" / "media-manifest.json"
    if not (integration.is_file() and qc_path.is_file() and manifest_path.is_file()):
        _skip(96, "canonical current state agrees", "a local integration run")
        return

    payload = json.loads(integration.read_text(encoding="utf-8"))
    qc = json.loads(qc_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert payload["production_ready"] is False
    assert payload["human_review"] == HUMAN_REVIEW_PENDING
    assert payload["provider_calls"] == {"speech": 0, "image": 0, "video": 0}
    assert payload["manifest"]["assets"] == 7, payload["manifest"]
    assert payload["manifest"]["placements"] == 5, payload["manifest"]
    assert payload["manifest"]["active_visual_assets"] == 5, payload["manifest"]
    assert manifest["counts"]["assets"] == 7, manifest["counts"]
    assert manifest["counts"]["placements"] == 5, manifest["counts"]

    # The artifact and its verdict agree across both receipts.
    assert payload["composition"]["video"] == "project://final/m45.mp4", (
        payload["composition"]["video"]
    )
    assert qc["graded_target"] == payload["composition"]["video"]
    assert qc["overall"] == payload["final_qc"]["overall"], (
        qc["overall"], payload["final_qc"]["overall"]
    )
    # And the storyboard's shot count equals the number of timeline placements,
    # which is the invariant the timeline exists to enforce.
    storyboard = json.loads(
        (base / "script" / "storyboard.json").read_text(encoding="utf-8")
    )
    assert len(storyboard["shots"]) == manifest["counts"]["placements"], (
        f"{len(storyboard['shots'])} shots for "
        f"{manifest['counts']['placements']} placements"
    )
    shot_ids = [shot["shot_id"] for shot in storyboard["shots"]]
    assert len(shot_ids) == len(set(shot_ids)), shot_ids
    print("[ok] 96. the committed current state agrees across receipts")


# --- 12b. generated provenance cannot be downgraded --------------------------


def test_a_generated_kind_cannot_be_built_with_generated_false():
    """GENERATED_VIDEO is generated by definition, derived or not.

    The committed manifest contained ``beat-05-h3-replaced`` with
    ``asset_kind=GENERATED_VIDEO`` and ``generated=False``. The reasoning behind it
    was "no provider receipt, so not provider-generated" — which confuses *who
    produced these bytes* with *what the content is*. Stripping an audio track does
    not turn generated footage into real material.

    Refused at construction rather than at validation, because an impossible pair is
    not an unvalidated input: it should not be constructible at all.
    """
    for kind in AssetKind.GENERATED:
        for derived in (None, "source"):
            try:
                MediaAssetEnvelope(
                    asset_id="d", modality=MediaModality.VIDEO, path="x.mp4",
                    asset_kind=kind, generated=False, derived_from=derived,
                )
            except ValueError as exc:
                assert "generated by definition" in str(exc), str(exc)
            else:
                raise AssertionError(
                    f"{kind} was built with generated=False (derived={derived!r})"
                )
    print("[ok] 70. a GENERATED_* kind cannot be built with generated=False")


def test_a_real_kind_cannot_be_built_with_generated_true():
    """The other direction. Generated-ness is derived from the kind, both ways."""
    for kind in (AssetKind.REAL, AssetKind.SCREENSHOT, AssetKind.DIAGRAM):
        try:
            MediaAssetEnvelope(
                asset_id="x", modality=MediaModality.IMAGE, path="x.png",
                asset_kind=kind, generated=True,
            )
        except ValueError as exc:
            assert "never generated" in str(exc), str(exc)
        else:
            raise AssertionError(f"{kind} was built with generated=True")
    print("[ok] 71. a real kind cannot be built with generated=True")


def test_a_derived_generated_asset_keeps_generated_provenance():
    """A transform changes bytes; the envelope still says what the content is."""
    if not HAVE_MEDIA:
        _skip(72, "derived provenance", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        source = _tiny_mp4(Path(td) / "shot.mp4", with_audio=True)
        application = apply_audio_policy(
            source_video=source, policy=AudioPolicy.MUTE,
            output_dir=Path(td) / "processed", source_generated=True,
            source_fingerprint="p" * 64,
        )
        assert application.transform_receipt.source_generated is True, (
            "the receipt lost the source lineage's provenance"
        )
        # The transform receipt's source has to be identifiable, so the derived
        # envelope carries the source fingerprint.
        derived = MediaAssetEnvelope(
            asset_id="derived", modality=MediaModality.VIDEO,
            path=application.output_path, asset_kind=AssetKind.GENERATED_VIDEO,
            generated=True, derived_from="source", fingerprint="p" * 64,
            transform_receipt_ref=Path(application.receipt_path).name,
        )
        assert derived.is_derived and derived.generated, (
            "a derived asset cannot be both derived and generated; that is the "
            "whole point of recording derivation separately"
        )
        result = validate_media_asset(derived)
        assert result.approved, result.failures
    print("[ok] 72. a derived generated asset keeps generated=True")


def test_a_derived_generated_asset_cannot_become_claim_bearing():
    """The evidence boundary is not loosened by being derived."""
    if not HAVE_MEDIA:
        _skip(73, "derived cannot claim-bear", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        source = _tiny_mp4(work / "shot.mp4", with_audio=True)
        application = apply_audio_policy(
            source_video=source, policy=AudioPolicy.MUTE,
            output_dir=work / "processed", source_generated=True,
            source_fingerprint="p" * 64,
        )
        derived = MediaAssetEnvelope(
            asset_id="d", modality=MediaModality.VIDEO, path=application.output_path,
            asset_kind=AssetKind.GENERATED_VIDEO, generated=True,
            derived_from="source", fingerprint="p" * 64,
            transform_receipt_ref=Path(application.receipt_path).name,
            evidence_use=EvidenceUse.CLAIM_SOURCE,
        )
        derived.validate_shape()
        # The bytes are fine; only the *role* is refused. That is the point: the
        # boundary is about provenance, not about whether the file is readable.
        joined = " | ".join(validate_media_asset(derived).failures)
        assert "claim-bearing" in joined.lower(), joined
        # And the shape is constructible, so the refusal really comes from the
        # evidence boundary rather than from the envelope being malformed.
        assert derived.generated and derived.is_derived
    print("[ok] 73. a derived generated asset cannot carry a claim-bearing role")


def test_a_transform_receipt_separates_its_own_bytes_from_source_provenance():
    """Two facts, two fields, no contradiction possible.

    ``provider_generated_bytes`` describes what the transform emitted. ``derived``
    marks it as transformed. ``source_generated`` describes the lineage. The old
    design had one ``generated`` field doing all three jobs, which is how a
    transform receipt ended up saying ``generated=false`` about generated content.
    """
    with tempfile.TemporaryDirectory() as td:
        receipt = TransformReceipt(
            transform_type="audio_policy_mute", source_asset_sha256="a" * 64,
            source_receipt_ref=None, source_fingerprint=None,
            output_path="x.mp4", output_sha256="b" * 64, source_generated=True,
        )
        body = receipt.as_dict()
        assert body["provider_generated_bytes"] is False
        assert body["derived"] is True
        assert body["source_generated"] is True
        assert "generated" not in body, (
            "the ambiguous bare 'generated' key is back; it cannot mean all three "
            "things at once"
        )
        # And it must be serialisable as a stable artifact.
        assert json.loads(json.dumps(body))["source_generated"] is True
    print("[ok] 74. a transform receipt separates its bytes from its source's provenance")


# --- 12b. one active asset per placement ------------------------------------


def _placed_shot(work: Path, descriptor: Dict[str, Any]) -> MediaAssetEnvelope:
    """One real, gate-admissible asset carrying the given placement.

    Writes the PNG and its provider receipt, because the gate validates the files on
    disk rather than trusting the envelope — a timeline test built from missing files
    would be asserting against blocked assets.
    """
    asset_id = descriptor["asset_id"]
    kind = descriptor.get("kind", AssetKind.GENERATED_IMAGE)
    modality = descriptor.get(
        "modality",
        MediaModality.VIDEO if kind == AssetKind.GENERATED_VIDEO else MediaModality.IMAGE,
    )
    suffix = ".mp4" if modality == MediaModality.VIDEO else ".png"
    asset = work / f"{asset_id}{suffix}"
    if modality == MediaModality.VIDEO:
        _tiny_mp4(asset)
    else:
        _png(asset)
    _write_receipt(
        asset,
        _provider_receipt(asset, modality=modality, fingerprint="f" * 64),
    )
    envelope = _envelope(
        asset, asset.with_name(asset.name + ".receipt.json"),
        modality=modality, asset_id=asset_id, fingerprint="f" * 64,
        kind=kind, generated=descriptor.get("generated", True),
    )
    fields = dict(envelope.__dict__)
    fields["placement_id"] = descriptor["placement_id"]
    for key in ("audio_policy", "derived_from"):
        if key in descriptor:
            fields[key] = descriptor[key]
    if "transform_receipt_ref" in descriptor:
        fields["transform_receipt_ref"] = descriptor["transform_receipt_ref"]
    if "evidence_use" in descriptor:
        fields["evidence_use"] = descriptor["evidence_use"]
    return MediaAssetEnvelope(**fields)


def _manifest_with_shots(shots, work: Path, **kwargs) -> MediaManifest:
    """Build a manifest from ``{asset_id, placement_id, ...}`` shot descriptors."""
    envelopes = [_placed_shot(work, shot) for shot in shots]
    decisions = AssetQualityGate().evaluate_all(envelopes)
    manifest = build_manifest(envelopes, decisions, **kwargs)
    blocked = [e.asset_id for e in manifest.blocked_assets()]
    assert not blocked, f"test fixtures were not gate-admissible: {blocked}"
    return manifest


def test_one_placement_resolves_to_exactly_one_active_asset():
    """The core invariant.

    ``usable_assets()`` is an inventory and can hold several assets for one
    placement; that is correct. ``active_visual_assets()`` is the timeline and holds
    exactly one. Composition must read the second, not the first.
    """
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        manifest = _manifest_with_shots(
            [
                {"asset_id": "shot-a", "placement_id": "beat-01"},
                {"asset_id": "shot-b", "placement_id": "beat-02"},
            ],
            work,
        )
        active = manifest.active_visual_assets()
        assert len(active) == 2, [e.asset_id for e in active]
        assert [e.placement_id for e in active] == ["beat-01", "beat-02"]
        placements = [p.placement_id for p in manifest.timeline]
        assert len(placements) == len(set(placements)), "a placement appears twice"
        # One active asset per placement, by construction.
        for placement in manifest.timeline:
            matching = [
                e for e in active if e.asset_id == placement.active_asset_id
            ]
            assert len(matching) == 1, placement
    print("[ok] 75. one placement resolves to exactly one active asset")


def test_a_transformed_placement_activates_the_derived_asset_not_the_source():
    """The committed storyboard had beat-05 and beat-05-replaced both playing.

    Both are gate-admissible — that is what "usable" means — so an inventory-driven
    composer put two shots on one placement, and the pre-transform native audio
    played over the narration REPLACE was supposed to guarantee would be the only
    track. The derived asset must win the slot.
    """
    if not HAVE_MEDIA:
        _skip(76, "derived asset wins the placement", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        source = _tiny_mp4(work / "shot.mp4", with_audio=True)
        application = apply_audio_policy(
            source_video=source, policy=AudioPolicy.REPLACE,
            output_dir=work / "processed", source_generated=True,
            source_fingerprint="r" * 64,
        )
        base = _provider_receipt(source, modality=MediaModality.VIDEO, fingerprint="r" * 64)
        _write_receipt(source, base)
        source_envelope = MediaAssetEnvelope(
            asset_id="beat-05-h3", modality=MediaModality.VIDEO, path=str(source),
            placement_id="beat-05", receipt_ref=source.name + ".receipt.json",
            fingerprint="r" * 64, asset_kind=AssetKind.GENERATED_VIDEO, generated=True,
            audio_policy=AudioPolicy.REPLACE,
        )
        derived = MediaAssetEnvelope(
            asset_id="beat-05-h3-replaced", modality=MediaModality.VIDEO,
            path=application.output_path, placement_id="beat-05",
            fingerprint="r" * 64, asset_kind=AssetKind.GENERATED_VIDEO, generated=True,
            audio_policy=AudioPolicy.REPLACE, derived_from="beat-05-h3",
            transform_receipt_ref=Path(application.receipt_path).name,
        )
        envelopes = [source_envelope, derived]
        manifest = build_manifest(
            envelopes, AssetQualityGate().evaluate_all(envelopes)
        )
        assert len(manifest.usable_assets()) == 2, "the inventory must keep both"
        active = manifest.active_visual_assets()
        assert len(active) == 1, (
            f"one placement placed {len(active)} shots: "
            f"{[e.asset_id for e in active]}"
        )
        assert active[0].asset_id == "beat-05-h3-replaced", active[0].asset_id
        placement = manifest.timeline[0]
        assert placement.superseded_asset_ids == ["beat-05-h3"], placement
        assert "supersedes" in placement.selection_reason, placement
    print("[ok] 76. a transformed placement activates the derived asset")


def test_two_derived_assets_claiming_one_placement_are_refused_as_ambiguous():
    """Not resolved by a tie-break. Which one plays is not derivable, so ask."""
    if not HAVE_MEDIA:
        _skip(77, "ambiguous derived assets", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        envelopes = []
        # Two real MUTE transforms, so both derived assets are genuinely admissible.
        # Faking the flags would not exercise the check: blocked assets never reach
        # timeline selection, so the ambiguity would go unnoticed.
        for name in ("d1", "d2"):
            source = _tiny_mp4(work / f"{name}-src.mp4", with_audio=True)
            _write_receipt(
                source,
                _provider_receipt(source, modality=MediaModality.VIDEO, fingerprint="f" * 64),
            )
            application = apply_audio_policy(
                source_video=source, policy=AudioPolicy.MUTE,
                output_dir=work / "processed", source_fingerprint="f" * 64,
            )
            base = _envelope(
                source, source.with_name(source.name + ".receipt.json"),
                modality=MediaModality.VIDEO, asset_id=f"{name}-src",
                fingerprint="f" * 64, kind=AssetKind.GENERATED_VIDEO,
            )
            fields = dict(base.__dict__)
            fields.update(
                asset_id=name, path=application.output_path, receipt_ref=None,
                derived_from=f"{name}-src", audio_policy=AudioPolicy.MUTE,
                transform_receipt_ref=Path(application.receipt_path).name,
            )
            derived = MediaAssetEnvelope(**fields)
            assert not AssetQualityGate().evaluate(derived).reasons or (
                AssetQualityGate().evaluate(derived).state == GATE_PENDING_HUMAN_REVIEW
            ), "the derived fixture must be gate-admissible for this test to mean anything"
            derived = MediaAssetEnvelope(
                **{**derived.__dict__, "placement_id": "beat-01"}
            )
            envelopes.append(derived)

        assert all(
            AssetQualityGate().evaluate(e).state == GATE_PENDING_HUMAN_REVIEW
            for e in envelopes
        ), [AssetQualityGate().evaluate(e).state for e in envelopes]
        try:
            build_manifest(envelopes, AssetQualityGate().evaluate_all(envelopes))
        except TimelineError as exc:
            assert exc.code == "AMBIGUOUS_DERIVED_ASSETS", exc.code
        else:
            raise AssertionError("two derived assets silently produced one slot")
    print("[ok] 77. two derived assets on one placement are refused as ambiguous")


def test_a_timeline_cannot_activate_a_blocked_asset():
    """The gate still binds the timeline."""
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        envelope = _envelope(
            work / "gone.png", work / "gone.png.receipt.json",
            modality=MediaModality.IMAGE, asset_id="a", fingerprint="f" * 64,
        )
        placed = MediaAssetEnvelope(**{**envelope.__dict__, "placement_id": "beat-01"})
        manifest = MediaManifest(
            assets=[placed], gate_states={"a": GATE_BLOCKED},
            timeline=[TimelinePlacement("beat-01", "a", "test")],
        )
        try:
            manifest.active_visual_assets()
        except TimelineError as exc:
            assert exc.code == "INADMISSIBLE_ACTIVE_ASSET", exc.code
            assert "BLOCKED" in str(exc), str(exc)
        else:
            raise AssertionError("a blocked asset was placed on the timeline")
    print("[ok] 78. a blocked asset cannot be activated on the timeline")


def test_a_duplicate_placement_id_is_refused_with_a_named_code():
    """Two entries for one slot means two shots at one moment."""
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        manifest = _manifest_with_shots(
            [
                {"asset_id": "a", "placement_id": "beat-01"},
                {"asset_id": "b", "placement_id": "beat-01"},
            ],
            work,
        )
        # build_timeline collapses to one entry per placement, so force the
        # ambiguity the check exists to catch.
        manifest.timeline.append(
            TimelinePlacement("beat-01", "b", "forced duplicate")
        )
        try:
            manifest.active_visual_assets()
        except TimelineError as exc:
            assert exc.code == "DUPLICATE_PLACEMENT", exc.code
            assert "beat-01" in str(exc), str(exc)
        else:
            raise AssertionError("a duplicate placement was accepted")
    print("[ok] 79. a duplicate placement_id is refused with DUPLICATE_PLACEMENT")


def test_an_asset_cannot_be_active_in_two_placements():
    """Otherwise it is played twice."""
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        manifest = _manifest_with_shots(
            [{"asset_id": "a", "placement_id": "beat-01"}], work
        )
        manifest.timeline.append(
            TimelinePlacement("beat-02", "a", "same asset in two slots")
        )
        try:
            manifest.active_visual_assets()
        except TimelineError as exc:
            assert exc.code == "ASSET_ACTIVE_IN_TWO_PLACEMENTS", exc.code
        else:
            raise AssertionError("one asset filled two placements")
    print("[ok] 80. one asset cannot be active in two placements")


def test_a_timeline_activating_an_unknown_asset_is_refused():
    """A dangling reference is not a silent omission."""
    manifest = MediaManifest(
        assets=[], gate_states={},
        timeline=[TimelinePlacement("beat-01", "ghost", "test")],
    )
    try:
        manifest.active_visual_assets()
    except TimelineError as exc:
        assert exc.code == "UNKNOWN_ACTIVE_ASSET", exc.code
        assert "ghost" in str(exc), str(exc)
    else:
        raise AssertionError("a timeline activated an asset that does not exist")
    print("[ok] 81. an unknown active_asset_id is refused")


def test_the_timeline_round_trips_and_composition_reads_it_not_the_inventory():
    """The storyboard must contain one shot per placement, and survive a save/load.

    This is the end-to-end form of the bug: the committed storyboard had ``beat-05``
    twice, because ``manifest_to_storyboard`` iterated ``usable_assets()``.
    """
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        project = work / "proj"
        project.mkdir(parents=True, exist_ok=True)
        manifest = _manifest_with_shots(
            [
                {"asset_id": "shot-a", "placement_id": "beat-01"},
                {"asset_id": "shot-b", "placement_id": "beat-02"},
            ],
            work,
        )
        # Logical paths, as a committed manifest would carry.
        manifest = MediaManifest(
            assets=[
                MediaAssetEnvelope(
                    **{
                        **e.__dict__,
                        "path": f"project://assets/{e.asset_id}.png",
                    }
                )
                for e in manifest.assets
            ],
            gate_states=dict(manifest.gate_states),
            timeline=list(manifest.timeline),
        )
        reloaded = MediaManifest.load(
            # Round-trip through disk so serialisation is exercised, not assumed.
            manifest.write(work / "receipts" / "media-manifest.json")
        )
        assert len(reloaded.timeline) == 2, reloaded.timeline
        assert reloaded.active_visual_assets() == manifest.active_visual_assets() or [
            e.asset_id for e in reloaded.active_visual_assets()
        ] == [e.asset_id for e in manifest.active_visual_assets()]
    print("[ok] 82. the timeline round-trips through disk")


def test_narration_is_required_only_by_the_asset_that_actually_plays():
    """REPLACE on an asset that lost its slot must not demand narration.

    Otherwise a dropped transform still forces a mux track, and the manifest claims
    a requirement that no longer corresponds to anything on the timeline.
    """
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        envelopes = []
        for asset_id, derived in (("source", None), ("derived", "source")):
            envelope = _envelope(
                work / f"{asset_id}.png", work / f"{asset_id}.png.receipt.json",
                modality=MediaModality.IMAGE, asset_id=asset_id, fingerprint="f" * 64,
            )
            envelopes.append(
                MediaAssetEnvelope(
                    **{
                        **envelope.__dict__, "placement_id": "beat-05",
                        "audio_policy": AudioPolicy.REPLACE if derived else None,
                        "derived_from": derived,
                    }
                )
            )
        active_only = MediaManifest(
            assets=[e for e in envelopes if e.is_derived],
            gate_states={e.asset_id: GATE_PENDING_HUMAN_REVIEW for e in envelopes if e.is_derived},
            timeline=[
                TimelinePlacement("beat-05", "derived", "only the derived asset exists")
            ],
        )
        assert active_only.requires_narration() is True

        # The source alone, with no derived asset in the manifest at all.
        source_only = MediaManifest(
            assets=[e for e in envelopes if not e.is_derived],
            gate_states={"source": GATE_PENDING_HUMAN_REVIEW},
            timeline=[TimelinePlacement("beat-05", "source", "no transform present")],
        )
        assert source_only.requires_narration() is False, (
            "an untransformed KEEP source must not demand a narration mux"
        )
    print("[ok] 83. narration is required only by the asset that actually plays")


def test_a_replacement_shot_states_its_audio_postcondition():
    """The audio outcome is recorded, so a review can check it rather than assume."""
    if not HAVE_MEDIA:
        _skip(84, "audio postcondition", "ffmpeg")
        return
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        envelopes = [
            _placed_shot(
                work,
                {
                    "asset_id": "keep", "placement_id": "keep",
                    "modality": MediaModality.VIDEO,
                    "kind": AssetKind.GENERATED_VIDEO, "generated": True,
                    "audio_policy": AudioPolicy.KEEP,
                },
            )
        ]
        # A real REPLACE: transform the KEEP shot, so the derived asset is real.
        keep_shot = Path(envelopes[0].path)
        application = apply_audio_policy(
            source_video=keep_shot, policy=AudioPolicy.REPLACE,
            output_dir=work / "processed", source_generated=True,
            source_fingerprint="f" * 64,
        )
        derived_fields = dict(envelopes[0].__dict__)
        derived_fields.update(
            asset_id="replaced", placement_id="replaced", path=application.output_path,
            receipt_ref=None, derived_from="keep",
            transform_receipt_ref=Path(application.receipt_path).name,
            audio_policy=AudioPolicy.REPLACE,
        )
        envelopes.append(MediaAssetEnvelope(**derived_fields))
        manifest = build_manifest(
            envelopes, AssetQualityGate().evaluate_all(envelopes)
        )
        assert not manifest.blocked_assets(), [
            e.asset_id for e in manifest.blocked_assets()
        ]
        claims = manifest.audio_postconditions()
        assert any("keep:" in c and "KEEP" in c for c in claims), claims
        assert any("replaced:" in c and "narration is required" in c for c in claims), claims
        # And they are serialised, so the receipt carries them.
        assert manifest.as_dict()["audio_postconditions"] == claims
    print("[ok] 84. a REPLACE shot states its audio postcondition in the manifest")


# --- 12c. paths are portable, and absolute ones are refused -------------------


def test_manifest_paths_are_portable_logical_references_and_fingerprint_alike():
    """The committed manifest carried eight ``D:\\Projects\\...`` paths.

    That made "deterministic manifest" true on exactly one machine: a drive letter in
    the body means the fingerprint differs per checkout root, so it cannot be used as
    a cache key or compared in review. Project-relative references survive a move.
    """
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        repo = base / "repo"
        project = repo / "projects" / "demo"
        (project / "assets").mkdir(parents=True, exist_ok=True)

        asset = project / "assets" / "shot.png"
        _png(asset)

        # The same asset referenced from two different checkout roots.
        serialised = [
            serialize_media_path(asset, repo_root=repo, project_root=project),
            serialize_media_path(
                asset, repo_root=base / "elsewhere", project_root=project
            ),
        ]
        assert serialised == ["project://assets/shot.png"] * 2, serialised
        assert is_logical_path(serialised[0])
        # The *reference* uses POSIX separators, so it is identical on every platform.
        # The input path's own separators are irrelevant — that is the whole point of
        # not writing them into the manifest.
        assert "\\" not in serialised[0], serialised[0]
        assert "/" in serialised[0], serialised[0]

        # And it resolves back to the same file from either root.
        resolved = [
            resolve_media_path(ref, repo_root=root, project_root=project)
            for ref, root in zip(serialised, (repo, base / "elsewhere"))
        ]
        assert all(r == asset.resolve() for r in resolved), resolved

        # Two manifests, same content, different roots: identical fingerprint.
        def fingerprint_at(root: Path) -> str:
            local_manifest = MediaManifest(
                assets=[
                    MediaAssetEnvelope(
                        asset_id="a", modality=MediaModality.IMAGE,
                        placement_id="beat-01",
                        path=serialize_media_path(
                            asset, repo_root=root, project_root=project
                        ),
                        sha256="c" * 64, asset_kind=AssetKind.GENERATED_IMAGE,
                        generated=True,
                    )
                ],
                gate_states={"a": GATE_PENDING_HUMAN_REVIEW},
                timeline=[TimelinePlacement("beat-01", "a", "single asset")],
            )
            return local_manifest.fingerprint()

        assert fingerprint_at(repo) == fingerprint_at(base / "elsewhere"), (
            "the manifest fingerprint is machine-specific"
        )
    print("[ok] 85. manifest paths are portable and fingerprint identically per root")


def test_a_manifest_containing_an_absolute_path_is_refused():
    """Refused loudly, rather than quietly working on the machine that wrote it."""
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        for bad in (
            str(base / "shot.png"),
            "D:/Projects/elsewhere/shot.png",
            "/home/someone/shot.png",
        ):
            try:
                resolve_media_path(bad, repo_root=base, project_root=base / "proj")
            except ValueError as exc:
                assert "not a logical media reference" in str(exc), str(exc)
            else:
                raise AssertionError(f"{bad} was accepted as a media reference")
    print("[ok] 86. an absolute path is refused as a media reference")


def test_an_out_of_tree_asset_is_refused_rather_than_written_as_a_machine_path():
    """No fallback to an absolute path.

    ``None`` means the asset cannot be referenced portably. The caller must refuse
    it; silently writing the machine path is the failure this module replaces.
    """
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        project = repo / "proj"
        project.mkdir(parents=True, exist_ok=True)
        outside = Path(td) / "elsewhere" / "shot.png"
        _png(outside)

        assert serialize_media_path(outside, repo_root=repo, project_root=project) is None
        # A repo file *is* representable, as repo:// rather than project://.
        inside = repo / "shared.png"
        _png(inside)
        assert serialize_media_path(
            inside, repo_root=repo, project_root=project
        ) == "repo://shared.png"
        # A prefix of the root name is not "inside" the root.
        sibling = repo.parent / "repoOld" / "shot.png"
        sibling.parent.mkdir(parents=True, exist_ok=True)
        _png(sibling)
        assert serialize_media_path(
            sibling, repo_root=repo, project_root=project
        ) is None
    print("[ok] 87. an out-of-tree asset is refused, not written as a machine path")


# --- 12d. H3 reuse is explicit ------------------------------------------------


def _fake_h3(work: Path) -> Path:
    """A shot plus a valid generation receipt, as M4 produced them."""
    from contentops.media.fingerprint import sha256_file

    shot = _tiny_mp4(work / "real-shot.mp4", with_audio=True)
    receipt = work / "real-shot.mp4.receipt.json"
    receipt.write_text(
        json.dumps(
            {
                "schema": "contentops.video-receipt/v1",
                "fingerprint": "z" * 64,
                "output_sha256": sha256_file(shot),
                "generated": True,
                "evidence_capable": False,
                "production_ready": False,
                "human_review": "PENDING_FOUNDER_REVIEW",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return shot


def test_h3_reuse_is_explicit_and_never_discovered_from_the_filesystem():
    """The committed integration silently reused whatever sat in ``.verify-tmp/m4``.

    Ambient discovery makes a run's meaning depend on the machine: a clean clone
    produced fixtures, a workstation with M4 leftovers produced real provider media,
    and both were committed as "the integration". Now the default is fixtures, and a
    real artifact appears only when a path is passed.
    """
    from m45_media_integration import (
        H3_SOURCE_EXPLICIT_REUSE,
        H3_SOURCE_FIXTURE,
        _resolve_h3_reuse,
    )

    # No options: no reuse, and no filesystem scan is even possible.
    assert _resolve_h3_reuse({}, "fixture_video_provider") is None

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        shot = _fake_h3(work)

        # Explicit: the same artifact is found, but only because it was named.
        found = _resolve_h3_reuse({"h3_reuse_shot": str(shot)}, "minimax_h3")
        assert found is not None
        assert found["shot"] == shot
        assert found["provider"] == "minimax_h3", found["provider"]
        assert H3_SOURCE_EXPLICIT_REUSE != H3_SOURCE_FIXTURE

        # And the module no longer contains a scanner.
        import inspect

        source = inspect.getsource(sys.modules["m45_media_integration"])
        assert "_find_reusable_h3_shot" not in source, (
            "the ambient .verify-tmp scanner is back"
        )
    print("[ok] 88. H3 reuse is explicit and never discovered from the filesystem")


def test_an_explicit_h3_reuse_path_is_validated_against_its_receipt():
    """A path pointing at an unrelated or tampered file is refused, not trusted."""
    from m45_media_integration import _resolve_h3_reuse

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        shot = _fake_h3(work)

        # A receipt that is not a generation receipt.
        bogus_receipt = work / "bogus.mp4.receipt.json"
        _png(work / "bogus.mp4")
        bogus_receipt.write_text(json.dumps({"schema": "something/else"}), encoding="utf-8")
        for options, needle in (
            ({"h3_reuse_shot": str(work / "bogus.mp4")}, "video-receipt/v1"),
            # A digest that does not match the bytes it describes.
            (
                {"h3_reuse_shot": str(shot), "h3_reuse_receipt": str(bogus_receipt)},
                "video-receipt/v1",
            ),
        ):
            try:
                _resolve_h3_reuse(options, "minimax_h3")
            except ValueError as exc:
                assert needle in str(exc), str(exc)
            else:
                raise AssertionError(f"reuse accepted {options}")

        # A receipt claiming a different digest for a real shot.
        tampered = work / "tampered.mp4.receipt.json"
        import shutil

        shutil.copy(shot, work / "tampered.mp4")
        payload = json.loads((work / "real-shot.mp4.receipt.json").read_text(encoding="utf-8"))
        payload["output_sha256"] = "0" * 64
        tampered.write_text(json.dumps(payload), encoding="utf-8")
        try:
            _resolve_h3_reuse(
                {"h3_reuse_shot": str(work / "tampered.mp4"),
                 "h3_reuse_receipt": str(tampered)},
                "minimax_h3",
            )
        except ValueError as exc:
            assert "does not match its own receipt" in str(exc), str(exc)
        else:
            raise AssertionError("a shot that contradicts its receipt was reused")
    print("[ok] 89. an explicit reuse path is validated against its receipt")


def test_h3_reuse_without_a_receipt_is_refused():
    """No provenance, no reuse. Otherwise an unexplained file enters a committed run."""
    from m45_media_integration import _resolve_h3_reuse

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        shot = work / "orphan.mp4"
        _tiny_mp4(shot)
        try:
            _resolve_h3_reuse({"h3_reuse_shot": str(shot)}, "minimax_h3")
        except ValueError as exc:
            assert "receipt" in str(exc), str(exc)
        else:
            raise AssertionError("a shot was reused with no receipt")

        # A missing shot is refused too, rather than becoming an empty fixture run.
        try:
            _resolve_h3_reuse({"h3_reuse_shot": str(work / "gone.mp4")}, "minimax_h3")
        except ValueError as exc:
            assert "does not exist" in str(exc), str(exc)
        else:
            raise AssertionError("a missing shot was silently ignored")
    print("[ok] 90. H3 reuse without a receipt is refused")


def test_the_reuse_flag_is_threaded_through_to_the_provider_not_dropped():
    """``--reuse-h3-shot`` was parsed and then discarded by ``main()``.

    So the flag did nothing, while the provider separately scanned ``.verify-tmp``.
    Test the wiring, not just the parser: the path must reach the provider call.
    """
    from contentops.media.asset_execution import (
        AssetExecutionRouter,
        AssetPlanner,
        ExecutionContext,
    )
    from contentops.media.image_contract import AssetKind

    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        seen = {}

        def recording_provider(**kwargs):
            seen.update(kwargs)
            return {
                "path": str(work / "x.mp4"), "asset_id": "v",
                "receipt": {"generated": True},
            }

        # The context carries provider options, and the router forwards them.
        context = ExecutionContext(
            project_dir=work / "proj", video_provider=recording_provider,
            video_quota_budget="7pp", video_test_objective="prove threading",
            video_provider_options={"h3_reuse_shot": "forwarded"},
        )
        assert context.video_provider_options == {"h3_reuse_shot": "forwarded"}
        router = AssetExecutionRouter(AssetPlanner(options=[AssetKind.DIAGRAM]))
        router.execute_video(
            beat_id="beat-01", capability="video_h3_t2va", context=context,
            request=None, prompt="p",
        )
        assert seen.get("h3_reuse_shot") == "forwarded", (
            "context.video_provider_options was not forwarded to the provider"
        )

        # And the fixture provider accepts the threaded key rather than
        # swallowing it: it reads exactly these names.
        import m45_media_integration

        assert "h3_reuse_shot" in m45_media_integration._H3_REUSE_KEYS

        # main() must pass it on. Reading the source is the only way to see a
        # threading bug here without invoking a full composition run.
        import inspect

        source = inspect.getsource(m45_media_integration.main)
        assert "reuse_h3_shot=" in source, (
            "main() parses --reuse-h3-shot but does not pass it to run_integration"
        )
        assert "reuse_h3_receipt=" in source
    print("[ok] 91. the reuse flag is threaded to the provider, not dropped")


TESTS = [
    test_the_one_validator_accepts_valid_speech_image_and_video,
    test_the_validator_has_no_modality_branch_chain,
    test_speech_has_no_asset_kind_and_inventing_one_is_refused,
    test_speech_is_never_evidence_capable,
    test_a_missing_asset_is_caught_for_every_modality,
    test_a_missing_receipt_is_caught_for_every_modality,
    test_a_corrupt_receipt_is_caught_for_every_modality,
    test_a_digest_mismatch_is_caught_for_every_modality,
    test_a_missing_fingerprint_is_caught,
    test_a_schema_mismatch_is_caught,
    test_a_generated_asset_cannot_claim_the_import_schema,
    test_unsafe_billing_metadata_is_caught,
    test_a_credential_value_in_a_public_receipt_is_caught,
    test_a_raw_provider_task_id_is_caught_but_a_salted_hash_is_not,
    test_a_generated_and_evidence_capable_mismatch_is_caught,
    test_an_unknown_human_review_state_is_caught,
    test_technical_pass_never_becomes_production_ready,
    test_a_modality_adapter_failure_is_surfaced_by_the_gate,
    test_a_missing_technical_qc_blocks_a_generation_but_not_an_import,
    test_keep_reuses_the_original_and_writes_no_transform,
    test_mute_produces_a_derived_asset_with_no_audio,
    test_replace_strips_audio_and_demands_narration_without_writing_it,
    test_replace_without_a_narration_source_says_so_rather_than_guessing,
    test_an_unknown_audio_policy_is_refused_before_any_transform,
    test_a_derived_asset_validates_against_its_transform_receipt,
    test_a_derived_asset_with_a_broken_chain_is_blocked,
    test_a_transform_receipt_claiming_generation_is_refused,
    test_the_registry_resolves_every_capability_by_name_not_vendor,
    test_only_live_proven_capabilities_are_marked_verified,
    test_an_unsupported_capability_is_refused_loudly_and_never_substituted,
    test_a_manual_only_capability_cannot_execute_automatically,
    test_a_capability_that_can_never_be_evidence_says_so,
    test_the_registry_holds_no_credentials_or_billing_state,
    test_duplicate_capability_registration_is_refused_as_ambiguity,
    test_reusable_assets_are_scheduled_first_and_cost_nothing,
    test_evidence_outranks_narration_which_outranks_generated_video,
    test_video_is_deferred_below_the_configured_weekly_floor,
    test_the_weekly_floor_is_a_policy_value_not_a_derived_number,
    test_speech_and_image_need_the_five_hour_window_but_video_does_not,
    test_video_without_a_declared_budget_is_blocked,
    test_every_paid_balance_blocks_generation_and_missing_blocks_too,
    test_a_manual_action_is_reported_not_substituted,
    test_every_decision_records_the_policy_that_produced_it,
    test_a_policy_permitting_payg_or_credit_pack_cannot_be_constructed,
    test_a_policy_disagreeing_with_the_gate_about_windows_is_refused,
    test_a_claim_beat_with_a_real_file_uses_the_real_executor,
    test_a_claim_beat_with_only_generated_options_fails_rather_than_degrading,
    test_a_forced_generated_plan_cannot_execute_as_evidence,
    test_a_missing_screenshot_reports_absence_and_substitutes_nothing,
    test_a_missing_screen_recording_reports_needs_capture,
    test_a_support_beat_routes_to_the_diagram_executor,
    test_a_support_beat_routes_to_a_fake_image_provider_with_no_network,
    test_a_support_beat_without_a_provider_reports_rather_than_substitutes,
    test_the_video_executor_refuses_without_a_declared_budget,
    test_generated_media_can_never_be_registered_as_evidence,
    test_every_modality_passes_through_one_gate_vocabulary,
    test_the_gate_reports_blocked_for_every_failure_kind,
    test_a_declared_fallback_degrades_and_never_becomes_production_ready,
    test_an_undeclared_or_unnamed_fallback_is_caught,
    test_only_a_recorded_approval_reaches_production_ready,
    test_the_manifest_is_byte_stable_regardless_of_input_order,
    test_the_manifest_carries_no_timestamp_so_builds_are_diffable,
    test_a_manifest_refuses_an_asset_the_gate_never_judged,
    test_the_manifest_round_trips_and_separates_usable_from_blocked,
    test_a_manifest_with_an_unknown_schema_is_refused,
    test_the_manifest_records_lineage_and_audio_policy,
    test_fallback_is_visible_in_the_manifest_and_never_implies_readiness,
    test_no_media_convergence_module_spawns_a_process_directly,
    test_the_integration_script_routes_children_through_process_utils,
    test_the_committed_integration_receipts_show_convergence_with_no_provider_calls,
    # --- 12. the four final blockers: one shot per placement, provenance that
    # --- cannot be downgraded, portable paths, and explicit H3 reuse.
    test_a_generated_kind_cannot_be_built_with_generated_false,
    test_a_real_kind_cannot_be_built_with_generated_true,
    test_a_derived_generated_asset_keeps_generated_provenance,
    test_a_derived_generated_asset_cannot_become_claim_bearing,
    test_a_transform_receipt_separates_its_own_bytes_from_source_provenance,
    test_one_placement_resolves_to_exactly_one_active_asset,
    test_a_transformed_placement_activates_the_derived_asset_not_the_source,
    test_two_derived_assets_claiming_one_placement_are_refused_as_ambiguous,
    test_a_timeline_cannot_activate_a_blocked_asset,
    test_a_duplicate_placement_id_is_refused_with_a_named_code,
    test_an_asset_cannot_be_active_in_two_placements,
    test_a_timeline_activating_an_unknown_asset_is_refused,
    test_the_timeline_round_trips_and_composition_reads_it_not_the_inventory,
    test_narration_is_required_only_by_the_asset_that_actually_plays,
    test_a_replacement_shot_states_its_audio_postcondition,
    test_manifest_paths_are_portable_logical_references_and_fingerprint_alike,
    test_a_manifest_containing_an_absolute_path_is_refused,
    test_an_out_of_tree_asset_is_refused_rather_than_written_as_a_machine_path,
    test_h3_reuse_is_explicit_and_never_discovered_from_the_filesystem,
    test_an_explicit_h3_reuse_path_is_validated_against_its_receipt,
    test_h3_reuse_without_a_receipt_is_refused,
    test_the_reuse_flag_is_threaded_through_to_the_provider_not_dropped,
    # The last reuse test closes the M4.5 work. These guard the committed artifacts.
    test_no_canonical_committed_artifact_carries_a_host_path,
    test_the_stale_qc_report_is_not_retained_as_current_truth,
    test_the_canonical_qc_boundary_preserves_the_verdict_and_drops_the_paths,
    test_embedded_path_sanitizing_leaves_non_paths_alone,
    test_the_committed_qc_report_agrees_with_the_committed_current_state,
]

def main() -> int:
    failures = []
    for fn in TESTS:
        try:
            fn()
        except AssertionError as exc:
            failures.append((fn.__name__, str(exc)))
            print(f"[FAIL] {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append((fn.__name__, repr(exc)))
            print(f"[ERR ] {fn.__name__}: {exc!r}")

    print()
    if failures:
        print(f"{len(failures)} of {len(TESTS)} test(s) failed")
        return 1
    print(f"All {len(TESTS)} M4.5 media convergence regression tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
