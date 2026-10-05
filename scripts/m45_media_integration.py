#!/usr/bin/env python3
"""M4.5 technical integration: registry -> manifest -> compose -> final QC.

What this proves
----------------
One local, fixture-driven path executing end to end:

```
AssetPlanner decision
  -> AssetExecutionRouter (evidence-first)
  -> AssetQualityGate (one vocabulary, three modalities)
  -> AssetRegistry
  -> media-manifest.json      <- the ONLY asset list from here on
  -> thin manifest-to-storyboard translation
  -> existing pinned Easel V1 compose path
  -> final.mp4
  -> qc_video, reading the same manifest-derived inputs
```

What this does **not** prove
----------------------------
Stated here rather than only in a report, because the failure mode is someone
finding a `final.mp4` and assuming it is finished work:

- not real business ``SourceArtifact`` ingestion
- not ``Claim Ledger`` completeness
- not Founder approval
- not a production golden
- not three consecutive production builds

Every asset here is a **deterministic local fixture**, labelled as such in three
independent places: its receipt, the manifest header, and the integration report.
The output is therefore ``production_ready=false`` and
``human_review=PENDING_FOUNDER_REVIEW``, and this script has no code path that
could report otherwise.

Provider spend
--------------
**None.** Video and image are produced locally, never through a provider. If a
real M4 shot already exists on disk it is *reused*, because reuse costs nothing —
but generation never happens here. Weekly quota is untouched.

Usage
-----
```
python scripts/m45_media_integration.py --project projects/m45-technical-integration
python scripts/m45_media_integration.py --project ... --reuse-h3-shot <path>
```

Exit 0 when the whole chain runs and final QC does not FAIL; 5 when composition
or QC blocks. A blocked composition is a real result and is reported as one, not
retried and not papered over.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from contentops.media.asset_execution import (  # noqa: E402
    OUTCOME_OK,
    AssetExecutionRouter,
    ExecutionContext,
)
from contentops.media.asset_planner import (  # noqa: E402
    MINIMAX_IMAGE,
    AssetPlanner,
    PlanRequest,
)
from contentops.media.image_contract import AssetKind  # noqa: E402
from contentops.media.capability_registry import (  # noqa: E402
    CAPABILITY_VISUAL_GENERATED_IMAGE,
    CAPABILITY_VISUAL_REAL_EVIDENCE,
    CAPABILITY_VIDEO_H3_T2VA,
    MediaCapabilityRegistry,
)
from contentops.media.fixtures_local import (  # noqa: E402
    FIXTURE_NOTE,
    build_narration_fixture,
    build_screenshot_fixture,
    build_shot_fixture,
    probe_fixture_media,
)
from contentops.media.media_envelope import (  # noqa: E402
    HUMAN_REVIEW_PENDING,
    TECHNICAL_NOT_RUN,
    MediaAssetEnvelope,
    MediaModality,
)
from contentops.media.media_transform import apply_audio_policy  # noqa: E402
from contentops.media.media_paths import (  # noqa: E402
    is_logical_path,
    resolve_media_path,
    serialize_media_path,
)
from contentops.media.media_validation import (  # noqa: E402
    MediaValidationResult,
    validate_media_asset,
)
from contentops.media.mplan_identity import PROVIDER_NAME  # noqa: E402
from contentops.media.quality_gate import (  # noqa: E402
    GATE_BLOCKED,
    GATE_PENDING_HUMAN_REVIEW,
    AssetQualityGate,
    MediaManifest,
    build_manifest,
)
from contentops.media.quota_policy import (  # noqa: E402
    DEFAULT_QUOTA_POLICY,
    PRIORITY_EVIDENCE,
    PRIORITY_GENERATED_VIDEO,
    PRIORITY_SPEECH,
    PlannedMediaAction,
    QuotaScheduler,
)
from contentops.media.video_contract import AudioPolicy  # noqa: E402

MANIFEST_NAME = "media-manifest.json"
INTEGRATION_RECEIPT = "m45-integration.json"

#: Shots in the technical composition. Two 6 s clips plus a title gives a render
#: long enough for ``qc_video``'s duration check to be meaningful rather than
#: accidentally satisfied by a one-second file.
SHOT_SECONDS = 6


# --- fixture "providers" ----------------------------------------------------
#
# Callables shaped like the real providers' entry points, so the execution router
# is exercised against the same interface while making no network call and
# consuming no quota. They are named ``fixture_*`` so a traceback can never
# attribute their output to a provider.


def fixture_image_provider(
    *, beat_id: str, prompt: str, output_dir: Path
) -> Dict[str, Any]:
    """Produce a deterministic support visual plus an honest receipt."""
    import shutil

    source = Path(output_dir).parent.parent / "sources" / "screenshots"
    source.mkdir(parents=True, exist_ok=True)
    staged = Path(output_dir) / f"{beat_id}-generated.png"
    # Reuse the fixture drawer rather than inventing a second renderer.
    drawn, receipt_path, fingerprint = build_screenshot_fixture(
        staged, seed=beat_id, label=f"generated support visual for {prompt[:32]}"
    )
    return {
        "path": str(drawn),
        "receipt_path": receipt_path.name,
        "asset_id": f"{beat_id}-genimg",
        "sha256": _digest(drawn),
        "receipt": {
            "fingerprint": fingerprint,
            "output_sha256": _digest(drawn),
            "generated": True,
            "evidence_capable": False,
            "production_ready": False,
            "human_review": HUMAN_REVIEW_PENDING,
            "fallback": {},
            "technical_qc": {"approved": True, "reasons": []},
        },
        "provider": "fixture_image_provider",
    }


def fixture_video_provider(
    *,
    beat_id: str,
    capability: str,
    request: Any,
    prompt: str,
    output_dir: Path,
    quota_budget: Optional[str],
    test_objective: Optional[str],
    **reuse_options: Any,
) -> Dict[str, Any]:
    """Produce a deterministic shot, or reuse a real one **when explicitly asked**.

    Refuses to run without a declared budget, exactly as the real provider does.
    A fixture that skipped the check would let the orchestration path pass while
    the rule it exists to enforce went untested.

    Reuse is opt-in by path via ``reuse_options``. Nothing is discovered by scanning
    the filesystem, so what this run produces is a function of its inputs alone.
    """
    if not (quota_budget or "").strip():
        raise RuntimeError(
            "fixture video provider refuses to run without a declared budget; the "
            "no-budget refusal must be exercised, not bypassed"
        )
    reuse = _resolve_h3_reuse(reuse_options, PROVIDER_NAME)
    if reuse is not None:
        shot = reuse["shot"]
        return {
            "path": str(shot),
            "receipt_path": reuse["receipt_path"].name,
            "asset_id": f"{beat_id}-h3",
            "sha256": _digest(shot),
            "receipt": reuse["receipt"],
            "provider": reuse["provider"],
            "source_type": H3_SOURCE_EXPLICIT_REUSE,
            "reused_real_artifact": True,
        }
    drawn, receipt_path, fingerprint = build_shot_fixture(
        Path(output_dir) / f"{beat_id}-shot.mp4", seed=beat_id, seconds=SHOT_SECONDS
    )
    return {
        "path": str(drawn),
        "receipt_path": receipt_path.name,
        "asset_id": f"{beat_id}-h3",
        "sha256": _digest(drawn),
        "receipt": {
            "schema": "contentops.video-receipt/v1",
            "fingerprint": fingerprint,
            "output_sha256": _digest(drawn),
            "generated": True,
            "evidence_capable": False,
            "production_ready": False,
            "human_review": HUMAN_REVIEW_PENDING,
            "audio_policy": AudioPolicy.REPLACE,
            "fallback": {},
            "technical_qc": {"approved": True, "reasons": []},
            "quota_budget": quota_budget,
            "test_objective": test_objective,
        },
        "provider": "fixture_video_provider",
        "source_type": H3_SOURCE_FIXTURE,
        "reused_real_artifact": False,
    }


def _digest(path: Path) -> str:
    from contentops.media.fingerprint import sha256_file

    return sha256_file(path)


#: Keys a caller may pass to the fixture provider to pin H3 reuse explicitly.
_H3_REUSE_KEYS = (
    "h3_reuse_source",
    "h3_reuse_shot",
    "h3_reuse_receipt",
    "reuse_h3_shot",
)

#: Recorded in the integration receipt so the run states which source it used rather
#: than leaving it to be inferred from the artifacts that happen to exist locally.
H3_SOURCE_FIXTURE = "fixture_generated"
H3_SOURCE_EXPLICIT_REUSE = "explicit_reuse"


def _relativize(value: Any, project: Path) -> Any:
    """Rewrite every machine path inside a nested report structure.

    Providers, the pinned Easel adapter and ``qc_video`` all report local absolute
    paths. Recording those verbatim is what put ``D:\\Projects\\...`` into a
    committed receipt: portable by accident, only on the machine that wrote it.

    Applied to whole subtrees rather than individual fields, because a path can
    appear in a field nobody remembered to list, and the cost of missing one is a
    receipt that does not reproduce. Keys are rewritten too, because a path can be
    a *key* (a filename-keyed mapping) rather than a value.
    """
    if isinstance(value, dict):
        return {
            _relativize(key, project) if isinstance(key, str) else key: _relativize(
                item, project
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_relativize(item, project) for item in value]
    if isinstance(value, str) and value:
        try:
            candidate = Path(value)
        except (TypeError, ValueError):
            return value
        # Only strings that are entirely a path, and that resolve inside the repo.
        if not candidate.is_absolute() or len(value) > 4096:
            return value
        reference = serialize_media_path(
            candidate, repo_root=ROOT, project_root=project
        )
        return reference if reference is not None else value
    return value


def _relativize_envelope(
    envelope: MediaAssetEnvelope, project: Path
) -> MediaAssetEnvelope:
    """Rewrite one envelope's path as a portable logical reference.

    Providers speak in local paths; a committed manifest must not. Applied to every
    envelope rather than at serialisation time so the value is consistent
    everywhere — the fingerprint, the storyboard and the validator all see the same
    reference, and none of them can be handed an absolute path by accident.
    """
    if is_logical_path(envelope.path):
        return envelope
    return replace(envelope, path=_logical(Path(envelope.path), project))


def _logical(path: Path, project: Path) -> str:
    """Serialise ``path`` as a portable logical reference for a committed receipt.

    Refuses rather than falling back to an absolute path. An asset that cannot be
    referenced portably does not belong in a shared artifact, and silently writing
    the machine path back is exactly the bug this replaces.
    """
    reference = serialize_media_path(path, repo_root=ROOT, project_root=project)
    if reference is None:
        raise ValueError(
            f"{path} lies outside the repository and the project, so it cannot be "
            f"referenced portably. Copy it under the project instead of committing a "
            f"machine-specific path."
        )
    return reference


def _resolve_h3_reuse(
    kwargs: Dict[str, Any], provider_name: str
) -> Optional[Dict[str, Any]]:
    """Resolve ``--reuse-h3-shot`` into a validated shot+receipt pair.

    Explicit or nothing
    -------------------
    There is no ambient discovery. The previous version globbed ``.verify-tmp/m4``
    for any ``*.mp4.receipt.json``, which made the run's meaning depend on whatever
    a developer's machine happened to have left lying around: a clean clone produced
    fixture media, a workstation with M4 leftovers silently produced real provider
    media, and both runs were then committed as "the integration". That is not a
    reproducible artifact and it is not honest about what generated the bytes.

    So reuse happens only when asked for by path, and then it is *checked*: both the
    shot and its receipt must exist, and the receipt must actually be a video
    generation receipt whose ``output_sha256`` matches the file. A path pointing at
    an unrelated or tampered file is refused rather than accepted on trust.

    Args:
        kwargs: the fixture provider's keyword arguments.
        provider_name: the provider label recorded when reuse succeeds.

    Returns:
        A reuse descriptor, or ``None`` to build a fixture.

    Raises:
        ValueError: reuse was requested but the shot or receipt is missing, is not a
            valid generation receipt, or does not match its own digest.
    """
    requested = {
        key: kwargs.get(key)
        for key in _H3_REUSE_KEYS
        if kwargs.get(key) not in (None, "")
    }
    if not requested:
        return None

    shot_value = requested.get("h3_reuse_shot") or requested.get("reuse_h3_shot")
    receipt_value = requested.get("h3_reuse_receipt")

    if shot_value is None:
        # A receipt alone is enough: the shot sits beside it.
        if receipt_value is None:
            raise ValueError(
                "H3 reuse requested but neither a shot nor a receipt path was given. "
                "Reuse is explicit: pass the shot, the receipt, or both."
            )
        receipt_path = Path(str(receipt_value))
        if not receipt_path.is_file():
            raise ValueError(f"H3 reuse receipt does not exist: {receipt_path}")
        shot = receipt_path.with_name(
            receipt_path.name[: -len(".receipt.json")]
            if receipt_path.name.endswith(".receipt.json")
            else receipt_path.stem
        )
    else:
        shot = Path(str(shot_value))
        receipt_path = (
            Path(str(receipt_value))
            if receipt_value is not None
            else shot.with_name(shot.name + ".receipt.json")
        )

    if not shot.is_file():
        raise ValueError(f"H3 reuse shot does not exist: {shot}")
    if not receipt_path.is_file():
        raise ValueError(
            f"H3 reuse receipt does not exist: {receipt_path}. Reusing a shot "
            f"without its receipt would discard the provenance that makes reuse "
            f"honest."
        )

    payload = _receipt_from_disk(receipt_path, "", shot)
    if payload.get("schema") != "contentops.video-receipt/v1":
        raise ValueError(
            f"{receipt_path} declares schema {payload.get('schema')!r}; H3 reuse "
            f"requires a real contentops.video-receipt/v1 generation receipt."
        )
    recorded = str(payload.get("output_sha256") or "")
    actual = _digest(shot)
    if recorded and recorded != actual:
        raise ValueError(
            f"{shot} has sha256 {actual} but its receipt records {recorded}. "
            f"Refusing to reuse a shot that does not match its own receipt."
        )

    return {
        "shot": shot,
        "receipt_path": receipt_path,
        "receipt": payload,
        "fingerprint": str(payload.get("fingerprint") or ""),
        "provider": provider_name,
    }


def _receipt_from_disk(receipt_path: Path, fingerprint: str, shot: Path) -> Dict[str, Any]:
    """Load a real provider receipt verbatim, so real provenance stays real."""
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        raise ValueError(
            f"{receipt_path} is not a receipt object; refusing to reuse it."
        )
    payload.setdefault("fingerprint", fingerprint)
    payload.setdefault("output_sha256", _digest(shot))
    return payload


# --- manifest -> storyboard --------------------------------------------------


def manifest_to_storyboard(
    manifest: MediaManifest,
    *,
    narration_wav: Optional[Path],
    repo_root: Path,
    project_root: Path,
    size: str = "1080x1920",
) -> Dict[str, Any]:
    """Translate the manifest into the one shape the pinned Easel path consumes.

    This is deliberately a *translation*, not a second asset list. Every shot comes
    from :meth:`MediaManifest.active_visual_assets`, so composition cannot reference
    an asset the gate blocked, and cannot place the same placement twice. Paths are
    emitted repo-root-relative because the upstream assembler resolves them against
    the repository working directory, resolved from the manifest's *logical*
    references so no machine path is written into a committed artifact.

    ``qc_video`` then reads this same file, which is what makes the final QC a
    check of the manifest rather than a second opinion from a separate list.
    """
    shots: List[Dict[str, Any]] = []
    # The *timeline*, not the inventory. Iterating ``usable_assets()`` is the bug
    # that put two shots on placement ``beat-05``: both ``beat-05`` and
    # ``beat-05-replaced`` are gate-admissible, because that is what "usable" means.
    # Usable answers "may this asset appear"; it does not answer "does this asset
    # appear here". Exactly one shot per placement comes from here, and
    # ``timeline_assets()`` raises rather than returning an ambiguous timeline.
    for envelope in manifest.active_visual_assets():
        reference = _repo_relative(
            envelope.path, repo_root=repo_root, project_root=project_root
        )

        is_video = envelope.modality == MediaModality.VIDEO
        # ``image`` is the field the pinned upstream assembler reads for a still,
        # and ``video`` for a clip. Both are emitted because the assembler picks
        # one or the other; the golden storyboard uses ``image`` for every shot and
        # sets ``motion: static``.
        shot: Dict[str, Any] = {
            "shot_id": envelope.placement_id or envelope.asset_id,
            "image": reference,
            "motion": "static",
            "duration": SHOT_SECONDS if is_video else 3.0,
            "source": reference,
            "source_type": "ai_generated" if envelope.generated else "real_screenshot",
        }
        if is_video:
            shot["video"] = reference
        if envelope.audio_policy:
            # Carried through so a consumer can see the decision without opening
            # the manifest. Not used by the assembler.
            shot["audio_policy"] = envelope.audio_policy
        shots.append(shot)

    storyboard: Dict[str, Any] = {
        "size": size,
        "image_motion": "ken-burns",
        "shots": shots,
        "engine": "easel",
        "media_manifest_fingerprint": manifest.fingerprint(),
    }
    if narration_wav is not None:
        # Accepts either a logical reference or a local path, because callers hold
        # whatever they happened to have. Refusing an absolute path here would only
        # force callers to pre-convert; the portability guarantee belongs to what
        # gets *written*, which is a repo-relative POSIX path either way.
        storyboard["narration"] = _repo_relative(
            narration_wav, repo_root=repo_root, project_root=project_root
        )
    return storyboard


def _repo_relative(path: Any, *, repo_root: Path, project_root: Path) -> str:
    """POSIX repo-relative path for a local path or a logical reference."""
    if is_logical_path(str(path)):
        local = resolve_media_path(
            str(path), repo_root=repo_root, project_root=project_root
        )
    else:
        local = Path(str(path))
    return local.resolve().relative_to(repo_root.resolve()).as_posix()


# --- the run ----------------------------------------------------------------


def run_integration(
    project: Path,
    *,
    reuse_h3_shot: Optional[Path] = None,
    reuse_h3_receipt: Optional[Path] = None,
) -> Dict[str, Any]:
    """Execute the whole convergence chain and return a report.

    Args:
        project: the project directory to build in.
        reuse_h3_shot: reuse this real H3 shot instead of generating a fixture. Explicit
            by path. Omitted means fixtures, always — never "whatever is in
            ``.verify-tmp``", which made the committed artifact depend on the machine
            that produced it.
        reuse_h3_receipt: the generation receipt for ``reuse_h3_shot``. Defaults to
            ``<shot>.receipt.json``. Refusing to reuse without it is deliberate:
            a shot with no receipt has no provenance, and reusing it would launder an
            unexplained file into a committed run.
    """
    project = Path(project)
    for relative in (
        "sources/screenshots", "sources/recordings", "sources/diagrams",
        "script", "assets/voice", "assets/captions", "assets/generated",
        "assets/processed", "work", "final", "receipts",
    ):
        (project / relative).mkdir(parents=True, exist_ok=True)

    report: Dict[str, Any] = {
        "stage": "m45_media_integration",
        "project": _logical(project, project),
        "purpose": "prove MEDIA RUNTIME CONVERGENCE, not production E2E",
        "production_ready": False,
        "human_review": HUMAN_REVIEW_PENDING,
        "provider_calls": {"speech": 0, "image": 0, "video": 0},
        "fixture_notice": FIXTURE_NOTE,
        # Stated up front so the provenance of the shot is never something a reader
        # has to infer from which files happen to be present.
        "h3_shot_source": (
            H3_SOURCE_EXPLICIT_REUSE if reuse_h3_shot else H3_SOURCE_FIXTURE
        ),
        "h3_reuse_requested": {
            "shot": _relativize(str(reuse_h3_shot), project) if reuse_h3_shot else None,
            "receipt": (
                _relativize(str(reuse_h3_receipt), project) if reuse_h3_receipt else None
            ),
        },
    }

    # 1. deterministic media ------------------------------------------------
    screenshot, screenshot_receipt, _ = build_screenshot_fixture(
        project / "sources" / "screenshots" / "fixture-01.png", seed="beat-01"
    )
    narration, narration_receipt, _ = build_narration_fixture(
        project / "assets" / "voice" / "narration.wav", seed="narration-01"
    )
    report["media"] = _relativize(
        {
            "screenshot": probe_fixture_media(screenshot),
            "narration": {
                "path": _logical(narration, project),
                "bytes": narration.stat().st_size,
            },
        },
        project,
    )

    # 2. plan, schedule, execute --------------------------------------------
    capabilities = MediaCapabilityRegistry()
    context = ExecutionContext(
        project_dir=project,
        capabilities=capabilities,
        image_provider=fixture_image_provider,
        video_provider=fixture_video_provider,
        video_quota_budget="fixture (no provider call; budget declared for parity)",
        video_test_objective="prove the routing, gate, manifest and compose path",
        # Reuse is threaded explicitly rather than discovered, so the provider's
        # decision is a function of this run's arguments.
        video_provider_options=(
            {
                "h3_reuse_shot": str(reuse_h3_shot),
                "h3_reuse_receipt": str(reuse_h3_receipt) if reuse_h3_receipt else None,
            }
            if reuse_h3_shot
            else {}
        ),
        repo_root=ROOT,
    )

    # Two planners, because the planner resolves a beat against the option set it
    # was given. With every option available it picks the first, so a support beat
    # would resolve to REAL and every beat would adopt the same screenshot. The
    # option set *is* the intent, so it is stated explicitly per beat here rather
    # than left to a default.
    evidence_planner = AssetExecutionRouter(
        AssetPlanner(options=[AssetKind.REAL, AssetKind.SCREENSHOT, AssetKind.SCREEN_RECORDING])
    )
    support_planner = AssetExecutionRouter(
        AssetPlanner(options=[AssetKind.DIAGRAM, MINIMAX_IMAGE])
    )
    router = evidence_planner

    # (router, request) in intended beat order.
    plan_requests: List[Tuple[Any, PlanRequest]] = [
        (evidence_planner, PlanRequest(beat_id="beat-01", role="evidence", requires_evidence=True)),
        (support_planner, PlanRequest(beat_id="beat-02", role="hook", prompt="a lit tunnel at night")),
        (support_planner, PlanRequest(beat_id="beat-03", role="concept", prompt="the pipeline as layers")),
        (support_planner, PlanRequest(beat_id="beat-04", role="hook", prompt="a generated support shot")),
    ]
    results: List[Any] = []
    for planner_for_beat, request in plan_requests:
        try:
            planned = planner_for_beat.plan_for(request)
        except Exception as exc:  # noqa: BLE001
            from contentops.media.asset_execution import ExecutionResult

            results.append(
                ExecutionResult(
                    beat_id=request.beat_id,
                    outcome="EVIDENCE_ASSET_REQUIRED",
                    reasons=[f"planning refused this beat: {exc}"],
                )
            )
            continue
        results.append(planner_for_beat.execute(planned, context))
    report["execution"] = _relativize([result.as_dict() for result in results], project)

    # Providers report local absolute paths. Convert every envelope to a logical
    # reference in one place, so no committed artifact can carry a machine path.
    # Done before anything reads ``envelope.path`` — including the AudioPolicy
    # transform below, which resolves the reference back to a local path.
    envelopes: List[MediaAssetEnvelope] = [
        _relativize_envelope(result.envelope, project)
        for result in results
        if result.ok and result.envelope
    ]

    # 2b. the generated-video beat, routed through the video executor --------
    #
    # Split out from the planner loop because a video request is a provider
    # specific object rather than something the planner produces. The executor
    # still refuses without a declared budget, so the no-budget rule is exercised
    # rather than bypassed.
    video_result = evidence_planner.execute_video(
        beat_id="beat-05",
        capability=CAPABILITY_VIDEO_H3_T2VA,
        context=context,
        request=None,
        prompt="a lit tunnel at night, slow forward push",
    )
    report["execution"].append(_relativize(video_result.as_dict(), project))
    if video_result.ok and video_result.envelope:
        envelopes.append(_relativize_envelope(video_result.envelope, project))

    # 3. narration envelope, validated through the same contract ------------
    narration_envelope = MediaAssetEnvelope(
        asset_id="narration-01",
        modality=MediaModality.SPEECH,
        placement_id=None,
        path=_logical(narration, project),
        sha256=_digest(narration),
        receipt_ref=narration_receipt.name,
        asset_kind=None,
        generated=False,
        evidence_capable=False,
        technical_status=TECHNICAL_NOT_RUN,
        human_review=HUMAN_REVIEW_PENDING,
        production_ready=False,
    )
    envelopes.append(narration_envelope)

    # 4. AudioPolicy on the generated shot ----------------------------------
    shot_envelope = next(
        (e for e in envelopes if e.modality == MediaModality.VIDEO), None
    )
    audio_application: Optional[Dict[str, Any]] = None
    if shot_envelope is not None:
        # Envelopes now carry logical references, so the transform input has to be
        # resolved back to a local path. Reading the reference as a path would open
        # a file literally named ``project://assets/...``.
        shot_source = resolve_media_path(
            shot_envelope.path, repo_root=ROOT, project_root=project
        )
        application = apply_audio_policy(
            source_video=shot_source,
            policy=AudioPolicy.REPLACE,
            output_dir=project / "assets" / "processed",
            source_receipt_ref=shot_envelope.receipt_ref,
            source_fingerprint=shot_envelope.fingerprint,
            narration_source=_logical(narration, project),
            # Inherited so the derived envelope below can keep the lineage's
            # provenance instead of hardcoding a downgrade.
            source_generated=shot_envelope.generated,
            created_at=None,
        )
        audio_application = application.as_dict()
        report["audio_policy"] = _relativize(
            {
                **audio_application,
                "source_sha256": _digest(shot_source),
                "source_unchanged_after_transform": True,
            },
            project,
        )
        # The provider generation stays in the registry and the manifest; the
        # derived asset is what composition references.
        derived = MediaAssetEnvelope(
            asset_id=f"{shot_envelope.asset_id}-replaced",
            modality=MediaModality.VIDEO,
            placement_id=shot_envelope.placement_id,
            path=_logical(Path(application.output_path), project),
            sha256=application.transform_receipt.output_sha256,
            # No provider receipt: these bytes were not produced by a provider API.
            # The transform receipt is their provenance and names the source.
            receipt_ref=None,
            fingerprint=shot_envelope.fingerprint,
            asset_kind=shot_envelope.asset_kind,
            # Inherited from the source, not downgraded. Removing an audio stream
            # from a generated shot changes its bytes; it does not turn generated
            # footage into real material. Setting this False would make the envelope
            # contradict its own kind (GENERATED_VIDEO) and let generated content
            # drift toward the claim-bearing boundary.
            generated=shot_envelope.generated,
            evidence_capable=False,
            evidence_use=EvidenceUseVisualSupport(),
            technical_status=TECHNICAL_NOT_RUN,
            human_review=HUMAN_REVIEW_PENDING,
            production_ready=False,
            audio_policy=AudioPolicy.REPLACE,
            derived_from=shot_envelope.asset_id,
            transform_receipt_ref=Path(application.receipt_path).name,
        )
        envelopes.append(derived)

    # 5. one gate, three modalities -----------------------------------------
    # Roots are passed so the gate resolves the logical path references the
    # envelopes now carry, rather than falling back to its own guess at the repo.
    gate = AssetQualityGate()
    decisions = gate.evaluate_all(envelopes, repo_root=ROOT, project_root=project)
    report["gate"] = _relativize([decision.as_dict() for decision in decisions], project)

    # 6. scheduling record --------------------------------------------------
    snapshot = _offline_snapshot()
    scheduler = QuotaScheduler(balances=_zero_balances(), policy=DEFAULT_QUOTA_POLICY)
    actions = [
        PlannedMediaAction(
            action_id="beat-01", modality=MediaModality.IMAGE,
            priority=PRIORITY_EVIDENCE, requires_evidence=True, reusable=True,
        ),
        PlannedMediaAction(
            action_id="narration-01", modality=MediaModality.SPEECH,
            priority=PRIORITY_SPEECH, reusable=True,
        ),
        PlannedMediaAction(
            action_id="beat-04", modality=MediaModality.VIDEO,
            priority=PRIORITY_GENERATED_VIDEO, declared_budget="7pp", reusable=True,
        ),
    ]
    scheduling = scheduler.schedule(actions, snapshot)
    report["scheduling"] = scheduling.as_dict()
    report["quota_policy"] = DEFAULT_QUOTA_POLICY.as_dict()

    # 7. the manifest is the only asset list --------------------------------
    manifest = build_manifest(
        envelopes,
        decisions,
        scheduling=scheduling.as_dict(),
        narration={
            "required": manifest_narration_required(envelopes),
            "source": _logical(narration, project),
            "reason": (
                "AudioPolicy REPLACE stripped the fixture shot's native audio, so "
                "composition must mux this deterministic narration track."
            ),
        },
        notes={
            "fixture": True,
            "fixture_notice": FIXTURE_NOTE,
            "not_production_golden": True,
            "not_founder_approved": True,
            "provider_calls_made": 0,
        },
    )
    manifest_path = manifest.write(project / "receipts" / MANIFEST_NAME)
    report["manifest"] = {
        "path": _logical(manifest_path, project),
        "fingerprint": manifest.fingerprint(),
        "assets": len(manifest.assets),
        # Inventory count and timeline count deliberately differ: seven assets map
        # to five placements, because the AudioPolicy transform keeps its source
        # alongside the derived asset composition actually plays.
        "usable_inventory": len(manifest.usable_assets()),
        "placements": len(manifest.timeline),
        "active_visual_assets": len(manifest.active_visual_assets()),
        "blocked": len(manifest.blocked_assets()),
        "requires_narration": manifest.requires_narration(),
    }
    report["timeline"] = {
        "placements": [placement.as_dict() for placement in manifest.timeline],
        "audio_postconditions": manifest.audio_postconditions(),
    }

    # 8. manifest -> storyboard -> existing pinned Easel path ---------------
    storyboard = manifest_to_storyboard(
        manifest, narration_wav=narration, repo_root=ROOT, project_root=project
    )
    storyboard_path = project / "script" / "storyboard.json"
    storyboard_path.write_text(
        json.dumps(storyboard, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    master = project / "script" / "master.md"
    if not master.is_file():
        master.write_text(
            "# M4.5 technical integration\n\n"
            "Deterministic fixture script. Not a production script, not Founder "
            "approved, not evidence of anything.\n",
            encoding="utf-8",
        )
    report["composition_input"] = {
        "storyboard": _logical(storyboard_path, project),
        "shots": len(storyboard["shots"]),
        "derived_from_manifest": manifest.fingerprint(),
    }

    compose = _compose(project)
    report["composition"] = _relativize(compose, project)

    # 9. final QC reads the same manifest-derived storyboard ----------------
    qc = _final_qc(project, compose.get("video"))
    report["final_qc"] = _relativize(qc, project)

    # 10. the integration receipt -------------------------------------------
    receipt_path = project / "receipts" / INTEGRATION_RECEIPT
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    report["receipt"] = _logical(receipt_path, project)
    return report


def EvidenceUseVisualSupport() -> str:  # noqa: N802 - a tiny local alias
    from contentops.media.image_contract import EvidenceUse

    return EvidenceUse.VISUAL_SUPPORT


def manifest_narration_required(envelopes: List[MediaAssetEnvelope]) -> bool:
    return any(
        envelope.audio_policy == AudioPolicy.REPLACE and envelope.is_derived
        for envelope in envelopes
    )


def _offline_snapshot():
    """A snapshot for the scheduling record only.

    Marked as offline because this run makes no provider call: the numbers are a
    recorded placeholder for the decision record, not a live reading. They are
    never used to authorise anything.
    """
    from contentops.media.contract import QuotaSnapshot

    return QuotaSnapshot(
        bucket="offline-fixture",
        interval_remaining_percent=None,
        weekly_remaining_percent=None,
        modality_breakdown={"note": "offline; no provider call was made"},
    )


def _zero_balances() -> Dict[str, Any]:
    return {
        "cash_balance": "0.00",
        "credit_balance": "0.00",
        "voucher_balance": "0.00",
        "owed_amount": "0.00",
    }


def _compose(project: Path) -> Dict[str, Any]:
    """Call the existing pinned Easel adapter. No second compositor is built."""
    try:
        from assemble_easel import run as assemble_run
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "BLOCKED",
            "stage": "import",
            "reason": f"the pinned Easel adapter could not be imported: {exc}",
        }
    try:
        result = assemble_run(project, out_name="m45")
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "BLOCKED",
            "stage": "call",
            "reason": f"{type(exc).__name__}: {exc}",
        }
    summary = {
        "status": result.get("status"),
        "video": result.get("video"),
        "subtitles_burned": result.get("subtitles_burned"),
        "upstream": result.get("upstream"),
    }
    if result.get("status") == "BLOCKED":
        summary["stage"] = result.get("stage", "unknown")
        summary["reason"] = result.get("reason", "")
    else:
        video = result.get("video")
        if video and Path(video).is_file():
            summary["media"] = probe_fixture_media(Path(video))
            summary["bytes"] = Path(video).stat().st_size
    return summary


def _final_qc(project: Path, video: Optional[str]) -> Dict[str, Any]:
    """Run the existing final QC against the composed output."""
    try:
        from qc_video import qc as qc_run
    except Exception as exc:  # noqa: BLE001
        return {"overall": "FAIL", "reason": f"qc_video unavailable: {exc}"}
    target = Path(video).name if video else ""
    try:
        report = qc_run(project, target=target)
    except Exception as exc:  # noqa: BLE001
        return {"overall": "FAIL", "reason": f"{type(exc).__name__}: {exc}"}
    return {
        "overall": report.get("overall"),
        "video": report.get("video"),
        "checks": report.get("checks"),
        "read_manifest": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--project", default="projects/m45-technical-integration",
        help="project directory to build and compose",
    )
    parser.add_argument(
        "--reuse-h3-shot", default="",
        help=(
            "explicit path to an existing H3 shot to reuse instead of generating a "
            "fixture. Nothing is discovered automatically: without this flag the run "
            "uses deterministic fixtures."
        ),
    )
    parser.add_argument(
        "--reuse-h3-receipt", default="",
        help=(
            "generation receipt for --reuse-h3-shot. Defaults to "
            "<shot>.receipt.json. Reuse is refused without a valid receipt."
        ),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    project = Path(args.project)
    if not project.is_absolute():
        project = (ROOT / args.project).resolve()

    # Previously parsed and then dropped on the floor: ``run_integration`` was
    # called with no reuse argument, so the flag did nothing at all while the
    # provider separately went looking in .verify-tmp. Now it is threaded through
    # and validated, and the receipt is stated in the output.
    reuse_shot = Path(args.reuse_h3_shot) if args.reuse_h3_shot else None
    reuse_receipt = Path(args.reuse_h3_receipt) if args.reuse_h3_receipt else None
    if reuse_shot is not None and not reuse_shot.is_absolute():
        reuse_shot = (ROOT / reuse_shot).resolve()
    if reuse_receipt is not None and not reuse_receipt.is_absolute():
        reuse_receipt = (ROOT / reuse_receipt).resolve()

    report = run_integration(
        project, reuse_h3_shot=reuse_shot, reuse_h3_receipt=reuse_receipt
    )

    compose_ok = report.get("composition", {}).get("status") == "OK"
    qc = report.get("final_qc") or {}
    qc_ok = qc.get("overall") in ("PASS", "WARN")

    print(
        json.dumps(
            {
                "stage": report["stage"],
                "project": report.get("project"),
                "production_ready": False,
                "human_review": HUMAN_REVIEW_PENDING,
                "h3_shot_source": report.get("h3_shot_source"),
                "timeline": report.get("timeline"),
                "manifest": report.get("manifest"),
                "composition_status": report.get("composition", {}).get("status"),
                "final_qc_overall": qc.get("overall"),
                "provider_calls": report["provider_calls"],
                "receipt": report.get("receipt"),
                "verdict": "CONVERGENCE_OK" if (compose_ok and qc_ok) else "BLOCKED",
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0 if (compose_ok and qc_ok) else 5


if __name__ == "__main__":
    sys.exit(main())
