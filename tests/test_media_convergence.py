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
import shutil
import sys
import tempfile
from pathlib import Path

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
from contentops.media.media_transform import (  # noqa: E402
    TRANSFORM_SCHEMA,
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
    envelope = MediaAssetEnvelope(
        asset_id="n", modality=MediaModality.SPEECH, path="n.wav",
        asset_kind=AssetKind.GENERATED_IMAGE,
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
        as_import = MediaAssetEnvelope(
            **{**envelope.__dict__, "generated": False}
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
        adapted = MediaAssetEnvelope(**{**envelope.__dict__, "generated": False})
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
        assert receipt.generated is False, "a local transform claimed to be a generation"
        assert receipt.derived is True
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
            generated=False,
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
            asset_kind=AssetKind.GENERATED_VIDEO, generated=False,
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
        payload["generated"] = True
        payload["derived"] = False
        receipt_file.write_text(json.dumps(payload), encoding="utf-8")

        derived = MediaAssetEnvelope(
            asset_id="derived", modality=MediaModality.VIDEO,
            path=application.output_path, derived_from="source",
            transform_receipt_ref=receipt_file.name,
            asset_kind=AssetKind.GENERATED_VIDEO, generated=False,
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
            asset_kind=AssetKind.GENERATED_VIDEO, generated=False,
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
