"""AssetPlanner: decide *what kind* of asset each video beat needs.

The decision this module encodes
--------------------------------
Evidence first, decoration last. When a beat needs to prove something, only
something real can prove it; when it needs to set a mood, a generated image is
cheap, fast and perfectly adequate. Getting that order wrong produces videos
that *look* well-sourced and are not, so it is written down here rather than left
to each caller's judgement.

::

    real factual evidence
        > screenshot / screen recording
        > deterministic diagram
        > generated support visual

Why generated imagery is confined to support roles
--------------------------------------------------
A text-to-image model asked for "a benchmark chart" or "a terminal showing a
build" will produce a convincing, entirely invented one. Those pixels then sit
under a caption asserting a fact, and no downstream gate can tell them from a
real capture. So :data:`SUPPORT_ROLES` is where generated assets are allowed to
appear, and it contains only :attr:`EvidenceUse.VISUAL_SUPPORT`.

Generated media is for hooks, covers, concepts, metaphors, backgrounds,
transitions and decorative scenes. It is never for evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from contentops.media.image_contract import (
    AssetKind,
    EvidenceUse,
    GeneratedAssetEvidenceError,
)

__all__ = [
    "GENERATED_ROLES",
    "MINIMAX_IMAGE",
    "SUPPORT_ROLES",
    "AssetOption",
    "AssetPlanner",
    "PlanRequest",
    "PlannedAsset",
]

#: The planner-facing name for the generated-image option.
MINIMAX_IMAGE = "MINIMAX_IMAGE"

#: Evidence role, strictly ordered. Index is the priority.
EVIDENCE_PRIORITY = (
    AssetKind.REAL,
    AssetKind.SCREENSHOT,
    AssetKind.SCREEN_RECORDING,
    AssetKind.DIAGRAM,
    MINIMAX_IMAGE,
)

#: What each planner option may be used for.
GENERATED_ROLES = (EvidenceUse.VISUAL_SUPPORT,)
SUPPORT_ROLES = GENERATED_ROLES

#: Beat roles that a generated image is a sensible answer for.
GENERATED_SUITABLE_ROLES = (
    "hook",
    "cover",
    "concept",
    "metaphor",
    "background",
    "transition",
    "decorative_scene",
)

#: Beat roles that require real evidence. A generated asset offered for one of
#: these is refused.
EVIDENCE_REQUIRED_ROLES = (
    "evidence",
    "proof",
    "benchmark",
    "comparison",
    "demo",
    "screenshot",
)


@dataclass(frozen=True)
class AssetOption:
    """One way a beat could be satisfied, and what it would cost in integrity."""

    kind: str
    evidence_capable: bool
    description: str

    @property
    def priority(self) -> int:
        return EVIDENCE_PRIORITY.index(self.kind)


OPTIONS: Dict[str, AssetOption] = {
    AssetKind.REAL: AssetOption(
        AssetKind.REAL, True, "a real recording, photograph or capture"
    ),
    AssetKind.SCREENSHOT: AssetOption(
        AssetKind.SCREENSHOT, True, "a real screen capture"
    ),
    AssetKind.SCREEN_RECORDING: AssetOption(
        AssetKind.SCREEN_RECORDING, True, "a real screen recording"
    ),
    AssetKind.DIAGRAM: AssetOption(
        AssetKind.DIAGRAM, True, "a deterministically drawn diagram"
    ),
    MINIMAX_IMAGE: AssetOption(
        MINIMAX_IMAGE, False, "a generated support visual; never evidence"
    ),
}


@dataclass
class PlanRequest:
    """One beat that needs an asset."""

    beat_id: str
    role: str
    #: ``True`` when the beat asserts a fact that must be demonstrated.
    requires_evidence: bool = False
    prompt: Optional[str] = None
    notes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PlannedAsset:
    """The planner's answer for one beat."""

    beat_id: str
    role: str
    kind: str
    evidence_capable: bool
    evidence_use: str
    rationale: str
    requires_evidence: bool
    prompt: Optional[str] = None
    alternatives: List[str] = field(default_factory=list)


class AssetPlanner:
    """Choose the cheapest asset kind that can honestly satisfy a beat.

    Deliberately not a generator: it returns a decision, and the caller invokes
    the provider. Keeping the decision separate from the provider call is what
    lets the "generated images are never evidence" rule be enforced in one place
    rather than at each call site.
    """

    def __init__(self, options: Optional[Sequence[str]] = None) -> None:
        allowed = list(options) if options else list(EVIDENCE_PRIORITY)
        unknown = [name for name in allowed if name not in OPTIONS]
        if unknown:
            raise ValueError(f"unknown asset option(s): {', '.join(unknown)}")
        self._options: List[str] = [
            name for name in EVIDENCE_PRIORITY if name in allowed
        ]

    @property
    def options(self) -> List[str]:
        return list(self._options)

    def plan(self, request: PlanRequest) -> PlannedAsset:
        """Decide how one beat should be satisfied.

        Raises:
            GeneratedAssetEvidenceError: only ``MINIMAX_IMAGE`` is available for
                a beat that requires evidence, or the beat's role demands
                evidence. Returning a generated image for such a beat would put
                invented pixels under a factual caption, so the planner refuses
                instead of degrading.
            ValueError: no options remain.
        """
        if not self._options:
            raise ValueError("no asset options are available to the planner")

        needs_evidence = request.requires_evidence or request.role in EVIDENCE_REQUIRED_ROLES

        if needs_evidence:
            capable = [name for name in self._options if OPTIONS[name].evidence_capable]
            if not capable:
                raise GeneratedAssetEvidenceError(
                    f"beat {request.beat_id!r} requires evidence, but the only "
                    f"available option is {', '.join(self._options)}, which cannot "
                    f"evidence a claim. Capture the real thing, or drop the claim."
                )
            # The best available evidence: earliest in the priority order.
            chosen = capable[0]
            return PlannedAsset(
                beat_id=request.beat_id,
                role=request.role,
                kind=chosen,
                evidence_capable=True,
                evidence_use=EvidenceUse.EVIDENCE,
                rationale=(
                    f"beat {request.beat_id!r} asserts a fact, so it takes the "
                    f"highest-integrity available option ({chosen}). A generated "
                    f"visual cannot demonstrate something that was not measured."
                ),
                requires_evidence=True,
                prompt=None,
                alternatives=[name for name in self._options if name != chosen],
            )

        # Support beat: the earliest available option, which is the cheapest
        # thing that satisfies a mood rather than a claim.
        chosen = self._options[0]
        if request.role not in GENERATED_SUITABLE_ROLES and chosen == MINIMAX_IMAGE:
            chosen = self._options[min(1, len(self._options) - 1)]
        is_generated = chosen == MINIMAX_IMAGE
        return PlannedAsset(
            beat_id=request.beat_id,
            role=request.role,
            kind=chosen,
            evidence_capable=OPTIONS[chosen].evidence_capable,
            evidence_use=(
                SUPPORT_ROLES[0] if is_generated else EvidenceUse.EVIDENCE
            ),
            rationale=(
                f"beat {request.beat_id!r} is a support beat, so {chosen} is "
                f"sufficient and cheaper than capturing something real."
                if is_generated
                else f"beat {request.beat_id!r} takes {chosen}."
            ),
            requires_evidence=False,
            prompt=request.prompt,
            alternatives=[name for name in self._options if name != chosen],
        )

    def plan_all(self, requests: Sequence[PlanRequest]) -> List[PlannedAsset]:
        return [self.plan(request) for request in requests]