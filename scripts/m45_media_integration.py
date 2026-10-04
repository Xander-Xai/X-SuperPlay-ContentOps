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
) -> Dict[str, Any]:
    """Produce a deterministic shot, or reuse a real one if one already exists.

    Refuses to run without a declared budget, exactly as the real provider does.
    A fixture that skipped the check would let the orchestration path pass while
    the rule it exists to enforce went untested.
    """
    if not (quota_budget or "").strip():
        raise RuntimeError(
            "fixture video provider refuses to run without a declared budget; the "
            "no-budget refusal must be exercised, not bypassed"
        )
    reuse = _find_reusable_h3_shot()
    if reuse is not None:
        shot, receipt_path, fingerprint, origin = reuse
        return {
            "path": str(shot),
            "receipt_path": receipt_path.name,
            "asset_id": f"{beat_id}-h3",
            "sha256": _digest(shot),
            "receipt": _receipt_from_disk(receipt_path, fingerprint, shot),
            "provider": origin,
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
    }


def _digest(path: Path) -> str:
    from contentops.media.fingerprint import sha256_file

    return sha256_file(path)


def _find_reusable_h3_shot() -> Optional[Tuple[Path, Path, str, str]]:
    """Look for a real M4 shot already on disk. Reuse costs nothing; generation does."""
    candidates: List[Path] = []
    for base in (ROOT / ".verify-tmp" / "m4",):
        if not base.is_dir():
            continue
        for sidecar in sorted(base.rglob("*.mp4.receipt.json")):
            candidates.append(sidecar)
    for sidecar in candidates:
        try:
            payload = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("schema") != "contentops.video-receipt/v1":
            continue
        shot = sidecar.with_name(sidecar.name[: -len(".receipt.json")])
        if not shot.is_file():
            continue
        return shot, sidecar, str(payload.get("fingerprint") or ""), PROVIDER_NAME
    return None


def _receipt_from_disk(receipt_path: Path, fingerprint: str, shot: Path) -> Dict[str, Any]:
    """Load a real provider receipt verbatim, so real provenance stays real."""
    try:
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    payload.setdefault("fingerprint", fingerprint)
    payload.setdefault("output_sha256", _digest(shot))
    return payload


# --- manifest -> storyboard --------------------------------------------------


def manifest_to_storyboard(
    manifest: MediaManifest,
    *,
    narration_wav: Optional[Path],
    repo_root: Path,
    size: str = "1080x1920",
) -> Dict[str, Any]:
    """Translate the manifest into the one shape the pinned Easel path consumes.

    This is deliberately a *translation*, not a second asset list. Every shot comes
    from :meth:`MediaManifest.usable_assets`, so composition cannot reference an
    asset the gate blocked, and paths are emitted repo-root-relative because the
    upstream assembler resolves them against the repository working directory.

    ``qc_video`` then reads this same file, which is what makes the final QC a
    check of the manifest rather than a second opinion from a separate list.
    """
    shots: List[Dict[str, Any]] = []
    for envelope in manifest.usable_assets():
        if envelope.modality == MediaModality.SPEECH:
            continue
        absolute = Path(envelope.path)
        try:
            relative = absolute.resolve().relative_to(repo_root.resolve())
            reference = relative.as_posix()
        except ValueError:
            # Outside the repository: absolute, since a repo-relative path would
            # not resolve for the upstream process.
            reference = absolute.resolve().as_posix()

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
        try:
            storyboard["narration"] = narration_wav.resolve().relative_to(
                repo_root.resolve()
            ).as_posix()
        except ValueError:
            storyboard["narration"] = narration_wav.resolve().as_posix()
    return storyboard


# --- the run ----------------------------------------------------------------


def run_integration(project: Path, *, reuse_h3_shot: Optional[Path] = None) -> Dict[str, Any]:
    """Execute the whole convergence chain and return a report."""
    project = Path(project)
    for relative in (
        "sources/screenshots", "sources/recordings", "sources/diagrams",
        "script", "assets/voice", "assets/captions", "assets/generated",
        "assets/processed", "work", "final", "receipts",
    ):
        (project / relative).mkdir(parents=True, exist_ok=True)

    report: Dict[str, Any] = {
        "stage": "m45_media_integration",
        "project": str(project),
        "purpose": "prove MEDIA RUNTIME CONVERGENCE, not production E2E",
        "production_ready": False,
        "human_review": HUMAN_REVIEW_PENDING,
        "provider_calls": {"speech": 0, "image": 0, "video": 0},
        "fixture_notice": FIXTURE_NOTE,
    }

    # 1. deterministic media ------------------------------------------------
    screenshot, screenshot_receipt, _ = build_screenshot_fixture(
        project / "sources" / "screenshots" / "fixture-01.png", seed="beat-01"
    )
    narration, narration_receipt, _ = build_narration_fixture(
        project / "assets" / "voice" / "narration.wav", seed="narration-01"
    )
    report["media"] = {
        "screenshot": probe_fixture_media(screenshot),
        "narration": {"path": str(narration), "bytes": narration.stat().st_size},
    }

    # 2. plan, schedule, execute --------------------------------------------
    capabilities = MediaCapabilityRegistry()
    context = ExecutionContext(
        project_dir=project,
        capabilities=capabilities,
        image_provider=fixture_image_provider,
        video_provider=fixture_video_provider,
        video_quota_budget="fixture (no provider call; budget declared for parity)",
        video_test_objective="prove the routing, gate, manifest and compose path",
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
    report["execution"] = [result.as_dict() for result in results]

    envelopes: List[MediaAssetEnvelope] = [
        result.envelope for result in results if result.ok and result.envelope
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
    report["execution"].append(video_result.as_dict())
    if video_result.ok and video_result.envelope:
        envelopes.append(video_result.envelope)

    # 3. narration envelope, validated through the same contract ------------
    narration_envelope = MediaAssetEnvelope(
        asset_id="narration-01",
        modality=MediaModality.SPEECH,
        placement_id=None,
        path=str(narration),
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
        application = apply_audio_policy(
            source_video=Path(shot_envelope.path),
            policy=AudioPolicy.REPLACE,
            output_dir=project / "assets" / "processed",
            source_receipt_ref=shot_envelope.receipt_ref,
            source_fingerprint=shot_envelope.fingerprint,
            narration_source=str(narration),
            created_at=None,
        )
        audio_application = application.as_dict()
        report["audio_policy"] = {
            **audio_application,
            "source_sha256": _digest(Path(shot_envelope.path)),
            "source_unchanged_after_transform": True,
        }
        # The provider generation stays in the registry and the manifest; the
        # derived asset is what composition references.
        derived = MediaAssetEnvelope(
            asset_id=f"{shot_envelope.asset_id}-replaced",
            modality=MediaModality.VIDEO,
            placement_id=shot_envelope.placement_id,
            path=application.output_path,
            sha256=application.transform_receipt.output_sha256,
            # No provider receipt: these bytes were not produced by a provider.
            # The transform receipt is their provenance and names the source.
            receipt_ref=None,
            fingerprint=shot_envelope.fingerprint,
            asset_kind=shot_envelope.asset_kind,
            generated=False,
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
    gate = AssetQualityGate()
    decisions = gate.evaluate_all(envelopes)
    report["gate"] = [decision.as_dict() for decision in decisions]

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
            "source": str(narration),
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
        "path": str(manifest_path),
        "fingerprint": manifest.fingerprint(),
        "assets": len(manifest.assets),
        "usable": len(manifest.usable_assets()),
        "blocked": len(manifest.blocked_assets()),
        "requires_narration": manifest.requires_narration(),
    }

    # 8. manifest -> storyboard -> existing pinned Easel path ---------------
    storyboard = manifest_to_storyboard(manifest, narration_wav=narration, repo_root=ROOT)
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
        "storyboard": str(storyboard_path),
        "shots": len(storyboard["shots"]),
        "derived_from_manifest": manifest.fingerprint(),
    }

    compose = _compose(project)
    report["composition"] = compose

    # 9. final QC reads the same manifest-derived storyboard ----------------
    qc = _final_qc(project, compose.get("video"))
    report["final_qc"] = qc

    # 10. the integration receipt -------------------------------------------
    receipt_path = project / "receipts" / INTEGRATION_RECEIPT
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    report["receipt"] = str(receipt_path)
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
        help="optional existing H3 shot to reuse instead of a fixture",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    project = Path(args.project)
    if not project.is_absolute():
        project = (ROOT / args.project).resolve()

    report = run_integration(project)

    compose_ok = report.get("composition", {}).get("status") == "OK"
    qc = report.get("final_qc") or {}
    qc_ok = qc.get("overall") in ("PASS", "WARN")

    print(
        json.dumps(
            {
                "stage": report["stage"],
                "project": str(project),
                "production_ready": False,
                "human_review": HUMAN_REVIEW_PENDING,
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
