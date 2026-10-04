"""One gate decision vocabulary for every modality, and one manifest.

Technical PASS is not approval
------------------------------
Those are different claims about different things. A file can decode perfectly
and still be a shot the Founder would reject; it can also be beautiful and be
wrong about its own dimensions. Collapsing them is how a pipeline comes to
believe it cleared its own work.

So :class:`GateDecision` has five states, and the gate refuses to move to
``PRODUCTION_READY`` unless a recorded human decision exists. There is no path in
this module that infers approval from quality, and none that invents a reviewer.

===========================  =============================================
state                        meaning
===========================  =============================================
``BLOCKED``                  validation or technical QC failed
``DEGRADED_FALLBACK``        technically fine, but a substitute was used
``PENDING_HUMAN_REVIEW``     technically fine, awaiting a person
``PRODUCTION_READY``         technically fine **and** a person approved it
``REJECTED``                 a person looked at it and refused it
===========================  =============================================

The ordering is deliberate. ``BLOCKED`` outranks everything, because a file that
does not validate cannot be improved by a reviewer's opinion.

Manifest determinism
--------------------
The same registry state must produce the same bytes, or a manifest cannot be
diffed, cached or used as a cache key. Achieved by:

- sorting assets by ``asset_id`` rather than by insertion or filesystem order
- serialising with fixed key order and ``sort_keys`` where a mapping is involved
- keeping timestamps **out** of the manifest body; they belong in the receipts,
  which are already the record of when something happened

That last point is why the manifest has no ``generated_at``. Adding one would
make every build differ from the last for no informational gain, and the receipts
already carry the time.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from contentops.media.media_envelope import (
    HUMAN_REVIEW_APPROVED,
    HUMAN_REVIEW_PENDING,
    HUMAN_REVIEW_REJECTED,
    MediaAssetEnvelope,
    MediaModality,
)
from contentops.media.media_validation import (
    MediaValidationAdapter,
    MediaValidationResult,
    validate_media_asset,
)

__all__ = [
    "GATE_BLOCKED",
    "GATE_DEGRADED_FALLBACK",
    "GATE_PENDING_HUMAN_REVIEW",
    "GATE_PRODUCTION_READY",
    "GATE_REJECTED",
    "GATE_STATES",
    "AssetQualityGate",
    "GateDecision",
    "MANIFEST_SCHEMA",
    "MediaManifest",
    "build_manifest",
]

GATE_BLOCKED = "BLOCKED"
GATE_DEGRADED_FALLBACK = "DEGRADED_FALLBACK"
GATE_PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW"
GATE_PRODUCTION_READY = "PRODUCTION_READY"
GATE_REJECTED = "REJECTED"

GATE_STATES = (
    GATE_BLOCKED,
    GATE_DEGRADED_FALLBACK,
    GATE_PENDING_HUMAN_REVIEW,
    GATE_PRODUCTION_READY,
    GATE_REJECTED,
)


@dataclass
class GateDecision:
    """One asset's gate outcome, with the reasoning that produced it."""

    asset_id: str
    modality: str
    state: str
    reasons: List[str] = field(default_factory=list)
    #: The validation result the decision was derived from, kept so a reader can
    #: see the measurement rather than only the conclusion.
    validation: Optional[MediaValidationResult] = None

    def __post_init__(self) -> None:
        if self.state not in GATE_STATES:
            raise ValueError(
                f"unknown gate state {self.state!r}; expected one of "
                f"{', '.join(GATE_STATES)}"
            )

    @property
    def blocked(self) -> bool:
        return self.state == GATE_BLOCKED

    @property
    def usable(self) -> bool:
        """True when composition may reference this asset."""
        return self.state in (
            GATE_PENDING_HUMAN_REVIEW,
            GATE_PRODUCTION_READY,
            GATE_DEGRADED_FALLBACK,
        )

    def as_dict(self) -> Dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "modality": self.modality,
            "state": self.state,
            "reasons": list(self.reasons),
            "validation": self.validation.as_dict() if self.validation else None,
        }


class AssetQualityGate:
    """Validate, then decide. One vocabulary for all three modalities."""

    def __init__(self, adapters: Optional[Dict[str, MediaValidationAdapter]] = None) -> None:
        self._adapters = dict(adapters) if adapters else {}

    def _adapter_for(self, modality: str) -> Optional[MediaValidationAdapter]:
        canonical = MediaModality.canonical(modality)
        return self._adapters.get(canonical)

    def evaluate(
        self,
        envelope: MediaAssetEnvelope,
        adapter: Optional[MediaValidationAdapter] = None,
    ) -> GateDecision:
        """Decide one asset's gate state.

        The order below is the policy:

        1. validation failure blocks, whatever else is true
        2. a technical block blocks
        3. a recorded human rejection rejects
        4. a substitute downgrades, and says so
        5. technical success with no review stays pending
        6. only a recorded approval becomes production-ready
        """
        resolved = adapter if adapter is not None else self._adapter_for(envelope.modality)
        result = validate_media_asset(envelope, resolved)

        if not result.approved:
            return GateDecision(
                asset_id=envelope.asset_id,
                modality=str(envelope.modality),
                state=GATE_BLOCKED,
                reasons=result.failures,
                validation=result,
            )

        # A derived asset is fine on its own terms, but it is not a provider
        # generation, so it is never reported as if it were one.
        if envelope.is_derived:
            return GateDecision(
                asset_id=envelope.asset_id,
                modality=str(envelope.modality),
                state=GATE_PENDING_HUMAN_REVIEW,
                reasons=[
                    "derived asset: validated against its transform receipt, and "
                    "awaiting review like any other unapproved asset"
                ]
                + result.notes,
                validation=result,
            )

        if envelope.human_review == HUMAN_REVIEW_REJECTED:
            return GateDecision(
                asset_id=envelope.asset_id,
                modality=str(envelope.modality),
                state=GATE_REJECTED,
                reasons=["a human review recorded a rejection"],
                validation=result,
            )

        if envelope.human_review == HUMAN_REVIEW_APPROVED:
            return GateDecision(
                asset_id=envelope.asset_id,
                modality=str(envelope.modality),
                state=GATE_PRODUCTION_READY,
                reasons=["a human review recorded an approval"],
                validation=result,
            )

        reasons = ["technically valid; awaiting Founder review"] + result.notes
        if envelope.fallback:
            return GateDecision(
                asset_id=envelope.asset_id,
                modality=str(envelope.modality),
                state=GATE_DEGRADED_FALLBACK,
                reasons=[
                    "a declared substitute was used instead of the requested "
                    "capability: "
                    + json.dumps(dict(envelope.fallback), sort_keys=True)
                ]
                + reasons
                + ["a fallback never becomes production-ready on its own"],
                validation=result,
            )

        return GateDecision(
            asset_id=envelope.asset_id,
            modality=str(envelope.modality),
            state=GATE_PENDING_HUMAN_REVIEW,
            reasons=reasons,
            validation=result,
        )

    def evaluate_all(
        self, envelopes: Sequence[MediaAssetEnvelope]
    ) -> List[GateDecision]:
        return [self.evaluate(envelope) for envelope in envelopes]


#: The manifest schema. Versioned, so a later shape change is detectable rather
#: than silently mis-parsed.
MANIFEST_SCHEMA = "contentops.media-manifest/v1"


@dataclass
class MediaManifest:
    """The single asset list composition and final QC both read.

    Deliberately **not** a receipt, and deliberately not complete. It indexes; the
    modality-specific receipts remain the record of detail. A manifest that copied
    every receipt field would be a second source of truth that could disagree with
    the first.
    """

    assets: List[MediaAssetEnvelope] = field(default_factory=list)
    #: Gate decisions keyed by asset_id, so a consumer sees why an asset was
    #: admitted without re-running validation.
    gate_states: Dict[str, str] = field(default_factory=dict)
    #: Scheduling decisions, recorded so the plan that produced this manifest is
    #: inspectable afterwards.
    scheduling: Dict[str, Any] = field(default_factory=dict)
    #: Narration the composition must mux, with the reason. Kept at manifest
    #: level because it is a timeline fact, not a per-asset one.
    narration: Dict[str, Any] = field(default_factory=dict)
    #: Free-form provenance notes about the run that produced this manifest.
    #: Used by an integration run to state plainly that its assets are
    #: deterministic placeholders rather than real business evidence, so the
    #: manifest cannot be mistaken for a production one.
    notes: Dict[str, Any] = field(default_factory=dict)

    def envelope_for(self, asset_id: str) -> Optional[MediaAssetEnvelope]:
        for envelope in self.assets:
            if envelope.asset_id == asset_id:
                return envelope
        return None

    def usable_assets(self) -> List[MediaAssetEnvelope]:
        """Assets the gate admitted, in manifest order."""
        return [
            envelope for envelope in self.assets
            if self.gate_states.get(envelope.asset_id) in (
                GATE_PENDING_HUMAN_REVIEW,
                GATE_PRODUCTION_READY,
                GATE_DEGRADED_FALLBACK,
            )
        ]

    def blocked_assets(self) -> List[MediaAssetEnvelope]:
        return [
            envelope for envelope in self.assets
            if self.gate_states.get(envelope.asset_id) in (GATE_BLOCKED, GATE_REJECTED)
        ]

    def requires_narration(self) -> bool:
        """True when some asset demands a deterministic narration track.

        Set by ``REPLACE``: the H3 native track was stripped, so composition must
        supply narration. Following it is how the two tracks can never end up
        mixed without an explicit decision.
        """
        if self.narration.get("required"):
            return True
        return any(
            envelope.audio_policy == "REPLACE" and envelope.is_derived
            for envelope in self.assets
        )

    def as_dict(self) -> Dict[str, Any]:
        """Deterministic serialisation.

        Assets sorted by ``asset_id``; no timestamp in the body. Byte-stability
        is what makes this usable as a cache key and diffable in review.
        """
        ordered = sorted(self.assets, key=lambda e: e.asset_id)
        return {
            "schema": MANIFEST_SCHEMA,
            "notes": dict(self.notes),
            "narration": dict(self.narration),
            "scheduling": self.scheduling,
            "counts": {
                "assets": len(ordered),
                "by_modality": _count_by(ordered, lambda e: e.modality),
                "by_gate_state": dict(sorted(self.gate_states.items())),
            },
            "assets": [envelope.as_dict() for envelope in ordered],
        }

    def fingerprint(self) -> str:
        """Digest of the manifest body.

        Stable across runs for identical registry state, which is what lets a
        caller reuse a cached composition without re-deriving whether anything
        changed.
        """
        canonical = json.dumps(
            self.as_dict(), sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def write(self, path: Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.as_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return target

    @classmethod
    def load(cls, path: Path) -> "MediaManifest":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"{path} is not a media manifest")
        schema = payload.get("schema")
        if schema != MANIFEST_SCHEMA:
            raise ValueError(
                f"{path} declares manifest schema {schema!r}; this client "
                f"understands {MANIFEST_SCHEMA!r}"
            )
        assets: List[MediaAssetEnvelope] = []
        gate_states: Dict[str, str] = {}
        for item in payload.get("assets") or []:
            envelope = MediaAssetEnvelope(
                asset_id=item["asset_id"],
                modality=item["modality"],
                placement_id=item.get("placement_id"),
                path=item["path"],
                sha256=item.get("sha256"),
                receipt_ref=item.get("receipt_ref"),
                fingerprint=item.get("fingerprint"),
                asset_kind=item.get("asset_kind"),
                generated=bool(item.get("generated", False)),
                evidence_capable=bool(item.get("evidence_capable", False)),
                evidence_use=item.get("evidence_use"),
                claim_refs=list(item.get("claim_refs") or []),
                technical_status=item.get("technical_status", "NOT_RUN"),
                human_review=item.get("human_review", HUMAN_REVIEW_PENDING),
                production_ready=bool(item.get("production_ready", False)),
                audio_policy=item.get("audio_policy"),
                fallback=dict(item.get("fallback") or {}),
                derived_from=item.get("derived_from"),
                transform_receipt_ref=item.get("transform_receipt_ref"),
            )
            assets.append(envelope)
            state = (payload.get("counts", {}).get("by_gate_state") or {}).get(
                envelope.asset_id
            )
            if state:
                gate_states[envelope.asset_id] = state
        return cls(
            assets=assets,
            gate_states=gate_states,
            scheduling=dict(payload.get("scheduling") or {}),
            narration=dict(payload.get("narration") or {}),
            notes=dict(payload.get("notes") or {}),
        )


def _count_by(items: Sequence[Any], key) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in items:
        value = key(item)
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def build_manifest(
    envelopes: Sequence[MediaAssetEnvelope],
    decisions: Sequence[GateDecision],
    *,
    scheduling: Optional[Dict[str, Any]] = None,
    narration: Optional[Dict[str, Any]] = None,
    notes: Optional[Dict[str, Any]] = None,
) -> MediaManifest:
    """Assemble a manifest from validated assets and their gate decisions.

    An envelope with no decision is refused rather than admitted. Defaulting it
    to "pending" would let an unvalidated asset into the one list composition
    reads, which is the failure the manifest exists to prevent.
    """
    by_id = {decision.asset_id: decision for decision in decisions}
    missing = [
        envelope.asset_id for envelope in envelopes
        if envelope.asset_id not in by_id
    ]
    if missing:
        raise ValueError(
            f"no gate decision for asset(s) {', '.join(sorted(missing))}. Refusing "
            f"to admit an asset the gate never judged."
        )

    # Duplicate identifiers would collapse here rather than loudly, because
    # ``gate_states`` is keyed by asset_id: two assets would share one decision and
    # ``envelope_for`` would return whichever came first. A manifest whose entries
    # cannot be told apart is not a manifest.
    seen: Dict[str, int] = {}
    for envelope in envelopes:
        seen[envelope.asset_id] = seen.get(envelope.asset_id, 0) + 1
    duplicates = sorted(
        asset_id for asset_id, count in seen.items() if count > 1
    )
    if duplicates:
        raise ValueError(
            f"duplicate asset_id(s) {', '.join(duplicates)} in one manifest. Two "
            f"entries sharing an identifier cannot be distinguished by a consumer."
        )

    return MediaManifest(
        assets=list(envelopes),
        gate_states={
            envelope.asset_id: by_id[envelope.asset_id].state
            for envelope in envelopes
        },
        scheduling=dict(scheduling or {}),
        narration=dict(narration or {}),
        notes=dict(notes or {}),
    )
