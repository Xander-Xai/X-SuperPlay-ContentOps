"""One cross-modality vocabulary, and the envelope that indexes a media asset.

Modality is not asset kind
--------------------------
This module introduces a dimension the repository did not have: **what form the
media takes**, as distinct from **what kind of visual evidence it is**.

The existing :class:`~contentops.media.image_contract.AssetKind` answers the second
question and only the second. Its members are all *visuals*:

```
REAL  SCREENSHOT  SCREEN_RECORDING  DIAGRAM  GENERATED_IMAGE  GENERATED_VIDEO
```

Narration is none of those. Forcing it in would have meant inventing
``GENERATED_SPEECH``, and that is exactly the wrong move twice over: it would put a
non-visual into a visual evidence enum, and it would imply speech has an evidence
boundary it does not have. Speech is deterministic narration, not proof.

So :class:`MediaModality` is separate and orthogonal:

- :attr:`MediaModality.modality` — SPEECH / IMAGE / VIDEO, always present
- :attr:`MediaAssetEnvelope.asset_kind` — optional, and ``None`` for speech

The evidence truth table is **not** restated or duplicated here.
:class:`~contentops.media.image_contract.AssetRegistry` remains its single owner,
and this module never decides what may carry a claim.

The envelope is an index, not a source of truth
------------------------------------------------
:class:`MediaAssetEnvelope` deliberately carries **fewer** fields than a receipt.
It exists so composition, the quality gate and final QC can ask one question
("is this asset usable, and what is its provenance?") without parsing three
different receipt schemas, and so a manifest can be emitted without flattening
the modality-specific detail away.

The full receipt is always reachable through :attr:`MediaAssetEnvelope.receipt_ref`,
and the facts that only make sense for one modality stay in that receipt. Copying
loudness metrics or frame-difference statistics into a shared struct would make it
the place where modality detail is lost.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from contentops.media.image_contract import AssetKind

__all__ = [
    "HUMAN_REVIEW_PENDING",
    "MediaAssetEnvelope",
    "MediaModality",
    "TECHNICAL_BLOCKED",
    "TECHNICAL_NOT_RUN",
    "TECHNICAL_PASS",
    "TECHNICAL_STATUSES",
    "human_review_states",
]


class MediaModality:
    """The form the media takes. Independent of :class:`AssetKind`.

    Kept as a plain string namespace rather than an ``Enum``, matching the
    repository's existing convention for ``AssetKind`` and ``EvidenceUse``, so
    these values serialise into a manifest without a conversion step.
    """

    SPEECH = "SPEECH"
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"

    ALL: Tuple[str, ...] = (SPEECH, IMAGE, VIDEO)

    #: Modalities whose assets are visual and therefore participate in the
    #: ``AssetKind`` evidence boundary. Speech is excluded, and that exclusion is
    #: the whole point of the split.
    VISUAL: Tuple[str, ...] = (IMAGE, VIDEO)

    #: Human-readable, for a refusal message.
    LABELS = {
        SPEECH: "narration",
        IMAGE: "still image",
        VIDEO: "video",
    }

    @staticmethod
    def canonical(modality: str) -> str:
        """Return the canonical spelling, or raise for an unknown modality."""
        candidate = (modality or "").strip().upper()
        if candidate not in MediaModality.ALL:
            raise ValueError(
                f"unknown media modality {modality!r}; expected one of "
                f"{', '.join(MediaModality.ALL)}"
            )
        return candidate

    @staticmethod
    def is_visual(modality: str) -> bool:
        return MediaModality.canonical(modality) in MediaModality.VISUAL


#: Technical QC outcome vocabulary. Deliberately separate from the human-review
#: vocabulary, because conflating them is how a pipeline ends up believing it
#: approved its own work.
TECHNICAL_PASS = "PASS_TECHNICAL"
TECHNICAL_BLOCKED = "BLOCKED"
TECHNICAL_NOT_RUN = "NOT_RUN"

TECHNICAL_STATUSES: Tuple[str, ...] = (
    TECHNICAL_PASS,
    TECHNICAL_BLOCKED,
    TECHNICAL_NOT_RUN,
)

#: The one human-review state every provider currently writes. A reviewed state
#: would be recorded here once a Founder actually scores something; until then it
#: is the only valid value, which makes an invented approval impossible.
HUMAN_REVIEW_PENDING = "PENDING_FOUNDER_REVIEW"

#: Accepted ``human_review`` values. Narrow on purpose: widening it to whatever a
#: string happens to contain would let ``"approved"`` in without a decision record.
HUMAN_REVIEW_APPROVED = "APPROVED_FOUNDER"
HUMAN_REVIEW_REJECTED = "REJECTED_FOUNDER"

HUMAN_REVIEW_STATES: Tuple[str, ...] = (
    HUMAN_REVIEW_PENDING,
    HUMAN_REVIEW_APPROVED,
    HUMAN_REVIEW_REJECTED,
)


def human_review_states() -> Tuple[str, ...]:
    """The accepted ``human_review`` values.

    Exposed as a function so the validator and the manifest agree on one list
    without either owning a private copy that can drift.
    """
    return HUMAN_REVIEW_STATES


@dataclass
class MediaAssetEnvelope:
    """A cross-modality index pointing at one asset and its full receipt.

    Not a receipt and not a substitute for one. It carries the facts a consumer
    needs in order to decide whether to use the asset, and nothing more.
    """

    asset_id: str
    modality: str
    path: str
    #: Digest of the asset bytes. Not computed during serialisation, because that
    #: would make a manifest depend on I/O and on when it was written. Producers
    #: set it from a validation decision, so the value always traces back to one.
    sha256: Optional[str] = None
    receipt_ref: Optional[str] = None
    fingerprint: Optional[str] = None
    #: Visual kind from :class:`AssetKind`, or ``None``. ``None`` for speech and
    #: for any asset that is not visual evidence.
    asset_kind: Optional[str] = None
    generated: bool = False
    evidence_capable: bool = False
    evidence_use: Optional[str] = None
    claim_refs: List[str] = field(default_factory=list)
    technical_status: str = TECHNICAL_NOT_RUN
    human_review: str = HUMAN_REVIEW_PENDING
    production_ready: bool = False
    #: What to do with a provider-generated audio track. ``None`` where the
    #: modality has no audio track to decide about.
    audio_policy: Optional[str] = None
    #: Explicit, never silent. An empty dict means no fallback occurred; a
    #: populated one must say what was requested, what was used and why.
    fallback: Dict[str, Any] = field(default_factory=dict)
    #: Set on a derived asset, so provenance stays traversable in both
    #: directions. ``None`` on a provider generation.
    derived_from: Optional[str] = None
    transform_receipt_ref: Optional[str] = None
    #: Timeline / beat / shot this asset serves. Composition needs it; the
    #: providers have no opinion about it.
    placement_id: Optional[str] = None

    def __post_init__(self) -> None:
        """Refuse an envelope whose kind and ``generated`` flag contradict.

        Enforced at construction, not only at validation. ``generated`` is intrinsic
        provenance derived from the asset kind, so a contradictory pair is not an
        unvalidated input to be caught later — it is an impossible value, and
        letting one exist would mean a caller could build an envelope asserting
        that generated footage is real material and simply not validate it yet.

        Derived-ness is irrelevant here: stripping audio off a generated shot does
        not turn it into captured material.
        """
        MediaModality.canonical(self.modality)
        if self.asset_kind is None:
            return
        if self.asset_kind in AssetKind.GENERATED and not self.generated:
            raise ValueError(
                f"asset {self.asset_id!r} has kind {self.asset_kind}, which is "
                f"generated by definition, but generated=False. Provenance is not "
                f"downgradable, and a deterministic local transform does not change "
                f"what the content is."
            )
        if self.asset_kind not in AssetKind.GENERATED and self.generated:
            raise ValueError(
                f"asset {self.asset_id!r} has kind {self.asset_kind}, which is "
                f"never generated, but generated=True. Only "
                f"{', '.join(AssetKind.GENERATED)} are generated media."
            )

    @property
    def is_derived(self) -> bool:
        """True when these bytes came from a deterministic transform."""
        return self.derived_from is not None

    @property
    def is_provider_generation(self) -> bool:
        """True when these bytes came straight from a provider call."""
        return not self.is_derived and self.generated

    def as_dict(self) -> Dict[str, Any]:
        """Serialise deterministically, key order fixed by the dataclass."""
        return {
            "asset_id": self.asset_id,
            "modality": self.modality,
            "placement_id": self.placement_id,
            "path": self.path,
            "sha256": self.sha256,
            "receipt_ref": self.receipt_ref,
            "fingerprint": self.fingerprint,
            "asset_kind": self.asset_kind,
            "generated": self.generated,
            "evidence_capable": self.evidence_capable,
            "evidence_use": self.evidence_use,
            "claim_refs": list(self.claim_refs),
            "technical_status": self.technical_status,
            "human_review": self.human_review,
            "production_ready": self.production_ready,
            "audio_policy": self.audio_policy,
            "fallback": dict(self.fallback),
            "derived_from": self.derived_from,
            "transform_receipt_ref": self.transform_receipt_ref,
        }

    def validate_shape(self) -> None:
        """Check the envelope is internally coherent before it is trusted.

        Cheap, self-contained checks that catch a caller building an envelope by
        hand and getting the relationships wrong. This does **not** verify the
        asset or receipt on disk; that is :func:`validate_media_asset`'s job.

        Raises:
            ValueError: the envelope contradicts itself.
        """
        modality = MediaModality.canonical(self.modality)

        # Generated-ness is intrinsic provenance, derived from the kind and enforced
        # by AssetRegistry. Re-asserting it here means an envelope cannot even be
        # *constructed* into a lie, rather than relying on a later check to notice.
        # Derived-ness deliberately does not excuse it: stripping the audio off a
        # generated shot does not turn it into real material.
        if self.asset_kind is not None:
            if self.asset_kind in AssetKind.GENERATED and not self.generated:
                raise ValueError(
                    f"asset {self.asset_id!r} has kind {self.asset_kind}, which is "
                    f"generated by definition, but generated=False. Provenance is "
                    f"not downgradable, and a deterministic local transform does not "
                    f"change what the content is."
                )
            if self.asset_kind not in AssetKind.GENERATED and self.generated:
                raise ValueError(
                    f"asset {self.asset_id!r} has kind {self.asset_kind}, which is "
                    f"never generated, but generated=True. Only "
                    f"{', '.join(AssetKind.GENERATED)} are generated media."
                )

        if self.asset_kind is not None and modality not in MediaModality.VISUAL:
            raise ValueError(
                f"asset {self.asset_id!r} is {modality} but declares asset_kind "
                f"{self.asset_kind!r}. Speech is not a visual kind and has no "
                f"place in the evidence enum; leave asset_kind as None."
            )
        if self.evidence_capable and modality not in MediaModality.VISUAL:
            raise ValueError(
                f"asset {self.asset_id!r} is {modality} and cannot be evidence "
                f"capable; that concept belongs to visual kinds only"
            )
        if self.generated and self.evidence_capable:
            raise ValueError(
                f"asset {self.asset_id!r} is both generated and evidence_capable. "
                f"Generated media can never carry a factual claim."
            )
        if self.technical_status not in TECHNICAL_STATUSES:
            raise ValueError(
                f"asset {self.asset_id!r} has unknown technical_status "
                f"{self.technical_status!r}; expected one of "
                f"{', '.join(TECHNICAL_STATUSES)}"
            )
        if self.human_review not in HUMAN_REVIEW_STATES:
            raise ValueError(
                f"asset {self.asset_id!r} has unknown human_review "
                f"{self.human_review!r}; expected one of "
                f"{', '.join(HUMAN_REVIEW_STATES)}"
            )
        if self.is_derived and not self.transform_receipt_ref:
            raise ValueError(
                f"asset {self.asset_id!r} is derived but carries no "
                f"transform_receipt_ref, so its bytes have no provenance record"
            )
        if not self.path.strip():
            raise ValueError(f"asset {self.asset_id!r} has no path")
