"""Turn an ``AssetPlanner`` decision into a concrete asset.

The gap this closes
-------------------
M3 made the planner decide. Nothing consumed the decision: ``PlannedAsset`` was
returned to a caller and stopped there. This module is the consumer.

One rule outranks everything here
---------------------------------
**A claim-bearing beat may only resolve to real or captured material.** When the
required evidence is absent, the beat **fails**. It does not fall back to a
diagram, a generated image or a generated shot, because a fabricated support
visual standing in for proof is precisely the failure the whole evidence boundary
exists to prevent.

That is why :meth:`AssetExecutionRouter.execute` can return
``EVIDENCE_ASSET_REQUIRED`` — a structured, machine-readable refusal — rather
than an exception and rather than a substitute. The caller can act on it: go
capture the evidence, or drop the claim. Both are honest. Silently replacing a
benchmark with a pretty picture is not.

What each executor does
-----------------------
``REAL`` / ``SCREENSHOT`` / ``SCREEN_RECORDING``
    Locate an existing real file, verify it, and register it with provenance.
    M4.5 deliberately does **not** build a browser recorder. Absence is reported
    as ``MISSING_REAL_ASSET`` or ``NEEDS_CAPTURE``; nothing is invented.
``DIAGRAM``
    A deterministic local draw. Remains ``generated=false``,
    ``evidence_capable=false``, ``VISUAL_SUPPORT`` — a diagram explains, it never
    proves.
``MINIMAX_IMAGE``
    The existing image provider. Callers inject a fake in tests, so no real
    provider call happens in CI.
``H3``
    The existing video provider, including its one-task lifecycle and its
    mandatory declared budget. This module does not wrap task creation in a retry
    loop of its own; doing so would hide a second bill inside a convenience.

Fallback
--------
Fallback is a recorded field, never a behaviour. An executor that cannot do the
requested work returns a refusal or a ``manual_only`` outcome; it never quietly
returns something else. :class:`ExecutionResult` carries ``fallback`` so a
deliberate, declared substitution stays visible all the way into the manifest.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from contentops.media.asset_planner import (
    MINIMAX_IMAGE,
    AssetPlanner,
    PlanRequest,
    PlannedAsset,
)
from contentops.media.capability_registry import (
    CAPABILITY_SPEECH_NARRATION,
    CAPABILITY_VISUAL_DIAGRAM,
    CAPABILITY_VISUAL_GENERATED_IMAGE,
    CAPABILITY_VISUAL_REAL_EVIDENCE,
    CAPABILITY_VIDEO_H3_I2VA,
    CAPABILITY_VIDEO_H3_T2VA,
    MediaCapabilityRegistry,
)
from contentops.media.fingerprint import sha256_file
from contentops.media.image_contract import (
    AssetKind,
    AssetRegistry,
    EvidenceUse,
    register_asset,
)
from contentops.media.media_envelope import (
    HUMAN_REVIEW_PENDING,
    TECHNICAL_BLOCKED,
    TECHNICAL_NOT_RUN,
    TECHNICAL_PASS,
    MediaAssetEnvelope,
    MediaModality,
)
from contentops.media.media_validation import IMPORT_SCHEMA
from contentops.media.mplan_identity import PROVIDER_NAME
from contentops.media.transport import write_sidecar

__all__ = [
    "OUTCOME_EVIDENCE_ASSET_REQUIRED",
    "OUTCOME_MISSING_REAL_ASSET",
    "OUTCOME_NEEDS_CAPTURE",
    "OUTCOME_OK",
    "OUTCOME_UNSUPPORTED",
    "AssetExecutionRouter",
    "ExecutionContext",
    "ExecutionResult",
    "RealAssetLocator",
]

OUTCOME_OK = "OK"
#: A beat asserted a fact and no real material was available. The beat fails.
OUTCOME_EVIDENCE_ASSET_REQUIRED = "EVIDENCE_ASSET_REQUIRED"
OUTCOME_MISSING_REAL_ASSET = "MISSING_REAL_ASSET"
OUTCOME_NEEDS_CAPTURE = "NEEDS_CAPTURE"
OUTCOME_UNSUPPORTED = "UNSUPPORTED_CAPABILITY"

#: Where real material is looked for, by kind. Absolute, or project-relative.
_REAL_SEARCH_DIRS: Dict[str, Sequence[str]] = {
    AssetKind.REAL: ("sources/screenshots", "sources/recordings", "sources/documents"),
    AssetKind.SCREENSHOT: ("sources/screenshots",),
    AssetKind.SCREEN_RECORDING: ("sources/recordings",),
}

_REAL_SUFFIXES: Dict[str, Sequence[str]] = {
    AssetKind.REAL: (".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov", ".pdf"),
    AssetKind.SCREENSHOT: (".png", ".jpg", ".jpeg", ".webp"),
    AssetKind.SCREEN_RECORDING: (".mp4", ".mov", ".webm"),
}

REAL_MEDIA_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".mp4", ".mov")

#: Provenance record for material ContentOps adopted rather than generated.
#: Declared here and imported by the validator so the two agree on the spelling.
IMPORT_SCHEMA = "contentops.media-import/v1"
IMPORT_RECEIPT_SUFFIX = ".receipt.json"


def _import_fingerprint(kind: str, digest: str) -> str:
    """Stable identity for an adopted file: its kind and its content.

    Keyed on the digest, so re-importing the same bytes is the same import while a
    changed file is visibly a different one.
    """
    return hashlib.sha256(f"import:{kind}:{digest}".encode("utf-8")).hexdigest()


def record_capability(kind: str) -> bool:
    """Whether ``kind`` may carry a factual claim. Asked of the registry's table.

    Delegates to :class:`AssetKind` rather than restating it, so the converged
    layer cannot drift from the truth table that owns the boundary.
    """
    return kind in AssetKind.EVIDENCE_CAPABLE


class RealAssetLocator:
    """Finds an existing real file, or reports honestly that there is none.

    Deliberately not a recorder. Building a browser capture pipeline is real work
    and doing it here would produce something untested; a locator that reports
    absence forces the caller to decide, which is the correct behaviour while
    capture is still manual.
    """

    def __init__(self, *, project_dir: Path, repo_root: Optional[Path] = None) -> None:
        self._project = Path(project_dir)
        self._repo = Path(repo_root) if repo_root is not None else self._project

    def locate(self, kind: str, *, hint: Optional[str] = None) -> Optional[Path]:
        """Return a real file for ``kind``, or ``None``.

        A ``hint`` is checked first and must actually exist: a caller naming a
        file that is not there gets ``None`` rather than a silent fallback to
        some other file that happens to be lying around.
        """
        if hint:
            candidate = Path(hint)
            if not candidate.is_absolute():
                candidate = (self._repo / candidate) if not candidate.exists() else candidate
            if candidate.is_file():
                return candidate
            return None
        suffixes = _REAL_SUFFIXES.get(kind, ())
        for directory in _REAL_SEARCH_DIRS.get(kind, ()):
            base = self._project / directory
            if not base.is_dir():
                continue
            # Sorted so two runs on the same tree pick the same file. Filesystem
            # order would make the chosen asset, and therefore the manifest,
            # non-reproducible.
            for suffix in suffixes:
                for candidate in sorted(base.glob(f"*{suffix}")):
                    if candidate.is_file():
                        return candidate
        return None


@dataclass
class ExecutionContext:
    """What an executor is allowed to reach.

    Providers are injected rather than constructed here, so the router holds no
    credential, no billing guard and no transport. A caller that supplies a fake
    gets a fully exercised routing layer with no provider call at all, which is
    what keeps CI free of network and quota.
    """

    project_dir: Path
    registry: Optional[AssetRegistry] = None
    capabilities: Optional[MediaCapabilityRegistry] = None
    #: Real-material finder.
    locator: Optional[RealAssetLocator] = None
    #: Provider callables keyed by capability. ``None`` means the caller supplied
    #: no provider, so that capability reports ``MANUAL_REQUIRED`` instead of
    #: silently doing nothing.
    image_provider: Optional[Callable[..., Any]] = None
    video_provider: Optional[Callable[..., Any]] = None
    speech_provider: Optional[Callable[..., Any]] = None
    #: Where deterministic renders go. Defaults to ``<project>/assets/generated``.
    output_dir: Optional[Path] = None
    #: Declared budget a video action may schedule against. Required for video.
    video_quota_budget: Optional[str] = None
    video_test_objective: Optional[str] = None
    repo_root: Optional[Path] = None

    def __post_init__(self) -> None:
        self.project_dir = Path(self.project_dir)
        if self.registry is None:
            self.registry = AssetRegistry()
        if self.capabilities is None:
            self.capabilities = MediaCapabilityRegistry()
        if self.locator is None:
            self.locator = RealAssetLocator(
                project_dir=self.project_dir, repo_root=self.repo_root
            )
        if self.output_dir is None:
            self.output_dir = self.project_dir / "assets" / "generated"

    def generated_dir(self) -> Path:
        target = Path(self.output_dir)
        target.mkdir(parents=True, exist_ok=True)
        return target


@dataclass
class ExecutionResult:
    """What executing one plan item produced, or why it could not."""

    beat_id: str
    outcome: str
    envelope: Optional[MediaAssetEnvelope] = None
    reasons: List[str] = field(default_factory=list)
    #: Explicit and empty when nothing was substituted.
    fallback: Dict[str, Any] = field(default_factory=dict)
    capability: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.outcome == OUTCOME_OK

    def as_dict(self) -> Dict[str, Any]:
        return {
            "beat_id": self.beat_id,
            "outcome": self.outcome,
            "capability": self.capability,
            "reasons": list(self.reasons),
            "fallback": dict(self.fallback),
            "envelope": self.envelope.as_dict() if self.envelope else None,
        }


class AssetExecutionRouter:
    """Routes a :class:`PlannedAsset` to a concrete executor.

    The routing table is the documented policy, expressed once. Adding a
    capability means adding a row, not editing branches scattered through the
    method.
    """

    def __init__(self, planner: Optional[AssetPlanner] = None) -> None:
        self._planner = planner if planner is not None else AssetPlanner()

    def plan_for(self, request: PlanRequest) -> PlannedAsset:
        """Plan one beat. Exposed so a caller can inspect the decision first."""
        return self._planner.plan(request)

    def execute(self, planned: PlannedAsset, context: ExecutionContext) -> ExecutionResult:
        """Execute one already-decided plan item."""
        kind = planned.kind

        # Evidence first, before anything else. A claim-bearing beat has exactly
        # one legal destination, and checking it here means no later branch can
        # route a claim into generated media.
        if planned.requires_evidence:
            if kind not in AssetKind.EVIDENCE_CAPABLE:
                return ExecutionResult(
                    beat_id=planned.beat_id,
                    outcome=OUTCOME_EVIDENCE_ASSET_REQUIRED,
                    reasons=[
                        f"beat {planned.beat_id!r} asserts a fact, so it may only "
                        f"use {', '.join(AssetKind.EVIDENCE_CAPABLE)}, but the plan "
                        f"chose {kind}. Failing the beat rather than substituting "
                        f"generated or diagram material for evidence."
                    ],
                    capability=None,
                )
            return self._execute_real(planned, context)

        if kind in AssetKind.EVIDENCE_CAPABLE:
            return self._execute_real(planned, context)
        if kind == AssetKind.DIAGRAM:
            return self._execute_diagram(planned, context)
        if kind == MINIMAX_IMAGE:
            return self._execute_generated_image(planned, context)
        return ExecutionResult(
            beat_id=planned.beat_id,
            outcome=OUTCOME_UNSUPPORTED,
            reasons=[
                f"no executor for planned kind {kind!r}; refusing to substitute a "
                f"different one"
            ],
        )

    def execute_request(
        self, request: PlanRequest, context: ExecutionContext
    ) -> ExecutionResult:
        """Plan and execute in one step, for callers that do not need the split."""
        try:
            planned = self.plan_for(request)
        except Exception as exc:  # noqa: BLE001
            # A planner refusal (a claim with no capable option) is a structured
            # outcome here, not an exception escaping into orchestration.
            return ExecutionResult(
                beat_id=request.beat_id,
                outcome=OUTCOME_EVIDENCE_ASSET_REQUIRED
                if request.requires_evidence or request.role
                in ("evidence", "proof", "benchmark", "comparison", "demo", "screenshot")
                else OUTCOME_UNSUPPORTED,
                reasons=[f"planning refused this beat: {exc}"],
            )
        return self.execute(planned, context)

    def execute_all(
        self,
        requests: Sequence[PlanRequest],
        context: ExecutionContext,
    ) -> List[ExecutionResult]:
        """Execute beats in the given order; the caller supplies that order.

        Ordering is not decided here. The quota scheduler decides which actions
        may proceed, and this router is told the resulting order — because the
        scheduler knows about quota and this router knows about evidence, and
        neither should own the other's concern.
        """
        return [self.execute_request(request, context) for request in requests]

    # -- executors ---------------------------------------------------------

    def _execute_real(
        self, planned: PlannedAsset, context: ExecutionContext
    ) -> ExecutionResult:
        """Import an existing real file, or report that there is none."""
        locator = context.locator
        assert locator is not None
        found = locator.locate(planned.kind)
        if found is None:
            directories = ", ".join(_REAL_SEARCH_DIRS.get(planned.kind, ()))
            return ExecutionResult(
                beat_id=planned.beat_id,
                outcome=OUTCOME_MISSING_REAL_ASSET
                if planned.kind != AssetKind.SCREEN_RECORDING
                else OUTCOME_NEEDS_CAPTURE,
                reasons=[
                    f"no real {planned.kind} material found under {directories}. "
                    f"Reported rather than substituted: a factual beat must not "
                    f"be satisfied by generated or diagram media."
                ],
                capability=CAPABILITY_VISUAL_REAL_EVIDENCE,
            )

        digest = sha256_file(found)
        asset_id = f"{planned.beat_id}-{digest[:12]}"

        # Adopting real material is a provenance event, so it gets a receipt. An
        # import with only a digest would be the weakest link in the chain, and
        # "no receipt, no record" is the repository's standing rule. The schema is
        # the import one: no provider produced this file, and the record says so.
        receipt_path = found.with_name(
            found.name + IMPORT_RECEIPT_SUFFIX
        )
        write_sidecar(receipt_path, {
            "schema": IMPORT_SCHEMA,
            "record_type": "media_import",
            "provider": "contentops_local_import",
            "product": "contentops",
            "plan": "real_material",
            "transport": "local_import",
            "transport_version": "1",
            "imported_kind": planned.kind,
            "fingerprint": _import_fingerprint(planned.kind, digest),
            "canonical_path": str(found),
            "output_sha256": digest,
            "bytes": found.stat().st_size,
            "beat_id": planned.beat_id,
            "role": planned.role,
            "provider_call": False,
            "generated": False,
            "evidence_capable": record_capability(planned.kind),
            "production_ready": False,
            "human_review": HUMAN_REVIEW_PENDING,
            "note": (
                "ContentOps located and adopted existing material. No provider was "
                "involved and no quota was consumed."
            ),
        })

        record = register_asset(
            context.registry,
            asset_id=asset_id,
            kind=planned.kind,
            path=str(found),
            # Real material is the only thing that may carry a claim, so the role
            # follows the plan's own decision rather than being re-derived.
            evidence_use=planned.evidence_use or EvidenceUse.EVIDENCE,
            sha256=digest,
            receipt_ref=receipt_path.name,
            notes={"beat_id": planned.beat_id, "role": planned.role},
        )
        envelope = MediaAssetEnvelope(
            asset_id=asset_id,
            modality=MediaModality.IMAGE,
            placement_id=planned.beat_id,
            path=str(found),
            sha256=digest,
            receipt_ref=receipt_path.name,
            fingerprint=_import_fingerprint(planned.kind, digest),
            asset_kind=planned.kind,
            generated=record.generated,
            evidence_capable=record.evidence_capable,
            evidence_use=record.evidence_use,
            # ``PlannedAsset`` carries no claim identifiers, so an imported real
            # asset starts with none. Claim linkage is established by the claim
            # ledger in M5, not inferred here.
            claim_refs=[],
            technical_status=TECHNICAL_NOT_RUN,
            human_review=HUMAN_REVIEW_PENDING,
            production_ready=False,
        )
        return ExecutionResult(
            beat_id=planned.beat_id,
            outcome=OUTCOME_OK,
            envelope=envelope,
            reasons=[
                f"real {planned.kind} material located at {found.name} and "
                f"registered with its digest as provenance"
            ],
            capability=CAPABILITY_VISUAL_REAL_EVIDENCE,
        )

    def _execute_diagram(
        self, planned: PlannedAsset, context: ExecutionContext
    ) -> ExecutionResult:
        """Deterministic local draw. Never a claim-bearing role."""
        if context.capabilities is not None:
            context.capabilities.require_evidence_capable(CAPABILITY_VISUAL_DIAGRAM)

        destination = context.generated_dir() / f"{planned.beat_id}-diagram.png"
        renderer = _render_placeholder_diagram
        rendered = renderer(destination, planned)
        if not rendered:
            return ExecutionResult(
                beat_id=planned.beat_id,
                outcome=OUTCOME_UNSUPPORTED,
                reasons=["the deterministic diagram renderer produced no file"],
                capability=CAPABILITY_VISUAL_DIAGRAM,
            )
        digest = sha256_file(rendered)
        receipt_path = rendered.with_name(rendered.name + IMPORT_RECEIPT_SUFFIX)
        write_sidecar(receipt_path, {
            "schema": IMPORT_SCHEMA,
            "record_type": "media_import",
            "provider": "contentops_local_render",
            "product": "contentops",
            "plan": "deterministic_diagram",
            "transport": "local_deterministic",
            "transport_version": "1",
            "imported_kind": AssetKind.DIAGRAM,
            "fingerprint": _import_fingerprint(AssetKind.DIAGRAM, digest),
            "canonical_path": str(rendered),
            "output_sha256": digest,
            "bytes": rendered.stat().st_size,
            "beat_id": planned.beat_id,
            "role": planned.role,
            "provider_call": False,
            "generated": False,
            "evidence_capable": False,
            "production_ready": False,
            "human_review": HUMAN_REVIEW_PENDING,
            "note": (
                "Drawn deterministically by ContentOps. No provider was involved. "
                "A diagram explains a structure and never proves one, so "
                "evidence_capable is false by construction."
            ),
        })

        record = register_asset(
            context.registry,
            asset_id=f"{planned.beat_id}-diagram",
            kind=AssetKind.DIAGRAM,
            path=str(rendered),
            evidence_use=EvidenceUse.VISUAL_SUPPORT,
            sha256=digest,
            receipt_ref=receipt_path.name,
            notes={"beat_id": planned.beat_id, "role": planned.role},
        )
        return ExecutionResult(
            beat_id=planned.beat_id,
            outcome=OUTCOME_OK,
            envelope=MediaAssetEnvelope(
                asset_id=record.asset_id,
                modality=MediaModality.IMAGE,
                placement_id=planned.beat_id,
                path=str(rendered),
                sha256=digest,
                receipt_ref=receipt_path.name,
                fingerprint=_import_fingerprint(AssetKind.DIAGRAM, digest),
                asset_kind=AssetKind.DIAGRAM,
                generated=record.generated,
                evidence_capable=record.evidence_capable,
                evidence_use=record.evidence_use,
                technical_status=TECHNICAL_NOT_RUN,
                human_review=HUMAN_REVIEW_PENDING,
                production_ready=False,
            ),
            reasons=[
                "diagram rendered deterministically. It explains and never "
                "proves, so it is registered as VISUAL_SUPPORT with "
                "evidence_capable=false."
            ],
            capability=CAPABILITY_VISUAL_DIAGRAM,
        )

    def _execute_generated_image(
        self, planned: PlannedAsset, context: ExecutionContext
    ) -> ExecutionResult:
        """Route to the image provider, which a test may replace with a fake."""
        if context.image_provider is None:
            return ExecutionResult(
                beat_id=planned.beat_id,
                outcome=OUTCOME_UNSUPPORTED,
                reasons=[
                    "no image provider was supplied to the execution context, so "
                    "a generated support visual cannot be produced. Reported "
                    "rather than substituted with a diagram."
                ],
                capability=CAPABILITY_VISUAL_GENERATED_IMAGE,
            )
        if planned.requires_evidence and context.capabilities is not None:
            # Asked only when the beat actually asserts a fact. Calling this
            # unconditionally would make a support visual impossible to produce at
            # all, because the capability is *correctly* flagged as
            # evidence-incapable -- the check belongs to the claim path, not the
            # support path.
            context.capabilities.require_evidence_capable(
                CAPABILITY_VISUAL_GENERATED_IMAGE
            )
        produced = context.image_provider(
            beat_id=planned.beat_id,
            prompt=planned.prompt or "",
            output_dir=context.generated_dir(),
        )
        return _envelope_from_provider_output(
            planned=planned,
            produced=produced,
            modality=MediaModality.IMAGE,
            context=context,
            capability=CAPABILITY_VISUAL_GENERATED_IMAGE,
            registry_kind=AssetKind.GENERATED_IMAGE,
        )

    def execute_video(
        self,
        *,
        beat_id: str,
        capability: str,
        context: ExecutionContext,
        request: Any,
        prompt: str = "",
    ) -> ExecutionResult:
        """Route to the video provider, preserving its one-task discipline.

        Split out from :meth:`execute` because a video request is a provider-
        specific object, not something the planner produces. The declared budget
        and objective are forwarded rather than defaulted here: this module must
        not invent permission to spend.
        """
        if context.video_provider is None:
            return ExecutionResult(
                beat_id=beat_id,
                outcome=OUTCOME_UNSUPPORTED,
                reasons=["no video provider was supplied to the execution context"],
                capability=capability,
            )
        if not (context.video_quota_budget or "").strip():
            return ExecutionResult(
                beat_id=beat_id,
                outcome=OUTCOME_UNSUPPORTED,
                reasons=[
                    "no declared video quota budget in the execution context. A "
                    "video task is the most expensive call ContentOps makes, and "
                    "this module will not authorise one without a budget."
                ],
                capability=capability,
            )
        produced = context.video_provider(
            beat_id=beat_id,
            capability=capability,
            request=request,
            prompt=prompt,
            output_dir=context.generated_dir(),
            quota_budget=context.video_quota_budget,
            test_objective=context.video_test_objective,
        )
        return _envelope_from_provider_output(
            planned=None,
            produced=produced,
            modality=MediaModality.VIDEO,
            context=context,
            capability=capability,
            registry_kind=AssetKind.GENERATED_VIDEO,
            beat_id=beat_id,
        )


def _envelope_from_provider_output(
    *,
    produced: Any,
    modality: str,
    context: ExecutionContext,
    capability: str,
    registry_kind: str,
    planned: Optional[PlannedAsset] = None,
    beat_id: Optional[str] = None,
) -> ExecutionResult:
    """Turn a provider outcome into a validated-shaped envelope.

    Accepts either a real provider outcome or the plain dict a fake returns, so
    the routing layer is testable without a provider. The envelope's flags are
    taken from the **provider's own receipt**, not from the request, so a
    provider that disagreed with us cannot be laundered through here.
    """
    if not isinstance(produced, dict):
        return ExecutionResult(
            beat_id=beat_id or (planned.beat_id if planned else "?"),
            outcome=OUTCOME_UNSUPPORTED,
            reasons=[
                f"provider for {capability} returned "
                f"{type(produced).__name__}, not an outcome mapping"
            ],
            capability=capability,
        )
    receipt = produced.get("receipt") or {}
    if not isinstance(receipt, dict):
        receipt = {}
    path = produced.get("path") or receipt.get("canonical_path")
    if not path:
        return ExecutionResult(
            beat_id=beat_id or (planned.beat_id if planned else "?"),
            outcome=OUTCOME_UNSUPPORTED,
            reasons=[f"provider for {capability} reported no canonical path"],
            capability=capability,
        )

    generated = bool(receipt.get("generated", True))
    capable = bool(receipt.get("evidence_capable", False))
    technical = receipt.get("technical_qc") or {}
    technical_status = (
        TECHNICAL_PASS
        if isinstance(technical, dict) and technical.get("approved")
        else TECHNICAL_BLOCKED
        if isinstance(technical, dict) and technical
        else TECHNICAL_NOT_RUN
    )

    receipt_path = produced.get("receipt_path")
    digest = produced.get("sha256") or receipt.get("output_sha256")
    if not digest and Path(path).is_file():
        digest = sha256_file(Path(path))

    envelope = MediaAssetEnvelope(
        asset_id=produced.get("asset_id")
        or (receipt.get("fingerprint") or "")[:16]
        or Path(path).stem,
        modality=modality,
        placement_id=beat_id or (planned.beat_id if planned else None),
        path=str(path),
        sha256=digest,
        receipt_ref=str(receipt_path) if receipt_path else None,
        fingerprint=receipt.get("fingerprint"),
        asset_kind=registry_kind,
        generated=generated,
        evidence_capable=capable,
        evidence_use=EvidenceUse.VISUAL_SUPPORT,
        technical_status=technical_status,
        human_review=str(receipt.get("human_review") or HUMAN_REVIEW_PENDING),
        production_ready=bool(receipt.get("production_ready", False)),
        audio_policy=receipt.get("audio_policy"),
        fallback=dict(receipt.get("fallback") or {}),
    )
    return ExecutionResult(
        beat_id=beat_id or (planned.beat_id if planned else "?"),
        outcome=OUTCOME_OK,
        envelope=envelope,
        reasons=[
            f"produced by {capability}; registered support-only with the "
            f"provider's own receipt"
        ],
        fallback=dict(receipt.get("fallback") or {}),
        capability=capability,
    )


def _render_placeholder_diagram(destination: Path, planned: PlannedAsset) -> Optional[Path]:
    """Draw the minimum deterministic diagram needed for an integration proof.

    Intentionally plain. A diagram explains a structure; it never proves
    anything, and its whole value here is that it is deterministic and obviously
    synthetic, so nobody mistakes a test fixture for evidence.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:  # pragma: no cover - Pillow is a project dependency
        return None
    width, height = 768, 1360
    image = Image.new("RGB", (width, height), (250, 250, 252))
    draw = ImageDraw.Draw(image)
    draw.rectangle([0, 0, width, 120], fill=(28, 34, 48))
    draw.text((28, 46), f"DIAGRAM (support only, never evidence)",
              fill=(240, 240, 245))
    boxes = ["Source", "Transform", "Output"]
    top = 260
    for index, label in enumerate(boxes):
        y = top + index * 300
        draw.rectangle([120, y, width - 120, y + 180], outline=(60, 70, 96), width=4)
        draw.text((160, y + 80), f"{index + 1}. {label}", fill=(30, 34, 48))
        if index < len(boxes) - 1:
            draw.line(
                [(width // 2, y + 180), (width // 2, y + 300)],
                fill=(60, 70, 96), width=4,
            )
            draw.polygon(
                [
                    (width // 2 - 14, y + 286),
                    (width // 2 + 14, y + 286),
                    (width // 2, y + 300),
                ],
                fill=(60, 70, 96),
            )
    draw.text(
        (28, height - 90),
        f"beat: {planned.beat_id} | role: {planned.role}",
        fill=(90, 96, 110),
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG")
    return destination
