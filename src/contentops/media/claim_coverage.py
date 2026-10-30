"""Per-claim evidence coverage: the gate that replaces a global ratio.

Why a global ratio is the wrong gate
------------------------------------
"At least 70% of the cut is real source" is a *whole-film* statistic. It can be
satisfied while one claim is entirely unsupported, and it can fail a film whose
every claim is properly evidenced but which uses more animation because the
account is explanatory. The number measures the mix, not the truth.

So this module asks the per-claim question instead:

- is every claim-bearing beat bound to a claim that exists?
- is that claim SUPPORTED (not BLOCKED, not PARTIAL)?
- does at least one beat showing a *factual* claim use a real capture, rather
  than a card, motion clip or generated visual?

What is not claimed
-------------------
Passing this does not prove the claim is true; the ClaimMap's evidence binding
does that. This proves the cut does not assert a fact on a surface that cannot
support it. Both are needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set

from contentops.evidence.claim_map import BLOCKED, PARTIAL, SUPPORTED, ClaimMap
from contentops.media.cut_plan import CutPlan

#: Claims that assert something about the world. A judgement, a transition or
#: a CTA is not a fact and may appear without real capture.
FACTUAL_KINDS = ("runtime", "source", "historical")

#: Every spelling this repository has used for "a capture of something real".
#: One list, because four gates used to carry their own: a storyboard that said
#: ``screen_recording`` counted as evidence in one check, as nothing in another,
#: and an honest author could lose the ratio gate for choosing a synonym.
CAPTURE_SPELLINGS = frozenset({
    "recording",
    "real_source",
    "real_document",
    "real_screenshot",
    "real_recording",
    "real_capture",
    "screen_recording",
    "screen_capture",
    "terminal_recording",
    "terminal_capture",
    "recorded",
})

#: Asset kinds that can carry real evidence. A card, a motion clip and a
#: generated visual are support, not proof.
REAL_EVIDENCE_KINDS = tuple(sorted(CAPTURE_SPELLINGS))

#: Evidence modes the QC understands, in one place so the check and the report
#: cannot disagree about what a mode means.
EVIDENCE_MODES = ("EVIDENCE_LED", "CLAIM_LED", "EXPLANATORY")


def evidence_mode_policy(mode: str) -> Dict[str, Any]:
    """What one evidence mode does to the ratio and the coverage requirements."""
    if mode not in EVIDENCE_MODES:
        raise ValueError(f"evidence_mode must be one of {EVIDENCE_MODES}, got {mode!r}")
    if mode == "EVIDENCE_LED":
        return {"ratio_severity": "FAIL", "require_claim_coverage": False,
                "detail": "whole-film real-source floor applies"}
    if mode == "CLAIM_LED":
        return {"ratio_severity": "WARN", "require_claim_coverage": True,
                "detail": "real-source share is advisory; per-claim coverage is the gate"}
    return {"ratio_severity": "INFO", "require_claim_coverage": False,
            "detail": "not applicable: explanatory account, no recording asset by policy"}


#: Composition roles that can carry real evidence. ``vector_animation`` is the
#: explanatory surface and is deliberately absent: a cut built mostly from it
#: can never satisfy a whole-film real-source floor.
REAL_COMPOSITION_ROLES = frozenset({
    "screen_recording_evidence",
    "real_screenshot",
    "real_recording",
    "real_document",
    "diagram",
    "code_snapshot",
    "metric_chart",
})

#: The real-source floor a proven account's declared mix must be able to reach.
MIN_REAL_COMPOSITION_PCT = 70


def composition_policy_errors(
    mode: str,
    segments: Iterable[Dict[str, Any]],
    floor_pct: int = MIN_REAL_COMPOSITION_PCT,
) -> List[str]:
    """Whether a declared composition can satisfy the mode that governs it.

    The case this exists for: one account declaring 70% ``vector_animation``
    *and* a 70% real-source floor. Neither declaration is wrong alone, and
    nothing compared them, so the pair shipped and the floor was unreachable by
    construction. The mode decides which surface may dominate, so the mode and
    the mix have to be checked together.
    """
    evidence_mode_policy(mode)  # raises on an unknown mode
    rows = [segment for segment in segments or [] if isinstance(segment, dict)]
    if not rows:
        return ["composition declares no segment"]

    errors: List[str] = []
    roles = [str(segment.get("role")) for segment in rows]
    if len(roles) != len(set(roles)):
        errors.append("composition repeats a role")
    total = 0
    real_pct = 0
    for segment in rows:
        pct = segment.get("pct")
        if not isinstance(pct, int) or isinstance(pct, bool) or pct <= 0:
            errors.append(f"composition segment {segment.get('role')!r} has pct {pct!r}")
            continue
        total += pct
        if segment.get("role") in REAL_COMPOSITION_ROLES:
            real_pct += pct
    if total != 100:
        errors.append(f"composition sums to {total}, expected 100")

    if mode == "EVIDENCE_LED" and real_pct < floor_pct:
        errors.append(
            f"EVIDENCE_LED requires a real-source share of at least {floor_pct}%, "
            f"but this composition tops out at {real_pct}% (real roles: "
            f"{sorted(REAL_COMPOSITION_ROLES)}; vector_animation is not one)"
        )
    if mode == "EXPLANATORY" and "screen_recording_evidence" in roles:
        errors.append(
            "EXPLANATORY plans no recording asset by policy, but the composition "
            "declares a screen_recording_evidence segment"
        )
    return errors


@dataclass
class CoverageResult:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    covered: List[str] = field(default_factory=list)
    uncovered: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _active_assets(placement) -> Set[str]:
    ids = {placement.asset_id}
    for shot in getattr(placement, "shots", []) or []:
        if getattr(shot, "asset_id", None):
            ids.add(shot.asset_id)
    return {item for item in ids if item}


def _is_real(asset: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(asset, dict):
        return False
    if asset.get("kind") in REAL_EVIDENCE_KINDS:
        return True
    if asset.get("evidence_capable") is True:
        return True
    return asset.get("source_type") in REAL_EVIDENCE_KINDS


def validate_claim_coverage(cut_plan: CutPlan,
                            claim_map: ClaimMap,
                            assets: Optional[Dict[str, Dict[str, Any]]] = None) -> CoverageResult:
    """Check every claim-bearing beat against the claim it asserts.

    ``assets`` is optional. Without it the structural rules still run; the
    "real capture, not a card" rule needs the asset map and is skipped.
    """
    result = CoverageResult()
    known = {claim.claim_id: claim for claim in claim_map.claims}
    cited_by: Dict[str, List[Any]] = {claim_id: [] for claim_id in known}

    for placement in cut_plan.placements:
        cited = list(getattr(placement, "claim_ids", []) or [])
        if len(cited) != len(set(cited)):
            result.warnings.append(f"{placement.placement_id} cites a duplicate claim id")
        if getattr(placement, "claim_bearing", False) and not cited:
            result.errors.append(f"{placement.placement_id} is claim-bearing but cites no claim")
        for claim_id in cited:
            claim = known.get(claim_id)
            if claim is None:
                result.errors.append(f"{placement.placement_id} cites unknown claim {claim_id!r}")
                continue
            cited_by[claim_id].append(placement)
            if claim.support_status == BLOCKED:
                result.errors.append(f"{placement.placement_id} cites BLOCKED claim {claim_id}")
            elif claim.kind in FACTUAL_KINDS and claim.support_status != SUPPORTED:
                result.errors.append(
                    f"{placement.placement_id} asserts {claim.kind} claim {claim_id} "
                    f"whose support_status is {claim.support_status}; a video beat is an "
                    f"asserted surface and requires SUPPORTED")

    for claim_id, claim in known.items():
        if claim.kind in FACTUAL_KINDS and claim.support_status == SUPPORTED:
            placements = cited_by.get(claim_id, [])
            if not placements:
                result.uncovered.append(claim_id)
                result.warnings.append(f"supported claim {claim_id} never appears in the cut")
                continue
            result.covered.append(claim_id)
            if assets is not None:
                backed = any(
                    _is_real(assets.get(asset_id))
                    for placement in placements
                    for asset_id in _active_assets(placement)
                )
                if not backed:
                    result.errors.append(
                        f"claim {claim_id} is supported only by non-evidence assets; "
                        f"a card, motion clip or generated visual cannot assert a fact")
    return result
