"""Provider-generic image types and the Asset Registry evidence boundary.

Generic on purpose
------------------
MiniMax is the only image provider wired up today, but nothing in these types
names it. ``ImageRequest`` describes *what image is wanted*; the receipt records
which provider produced it. A future provider with different flags, different
dimensions rules or a different billing model must be addable without editing
these definitions, exactly as :mod:`contentops.media.contract` was written for
speech.

Two fields carry governance, not description
--------------------------------------------
``generated`` and ``evidence_capable`` are the reason this module exists.

A generated image is not evidence. It is a plausible-looking artefact produced by
a model, so it can depict a benchmark, a dashboard, a terminal, a code editor or
a chart. If such an image is ever registered as ``EVIDENCE``, the video will
assert something that was never measured, and no later gate will catch it because
the file *looks* like a real screenshot.

:func:`register_asset` therefore refuses that combination in code. The refusal is
a domain error, not a warning, and it lives at the only place an asset enters the
system rather than in documentation that a prompt can ignore.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__all__ = [
    "AssetKind",
    "AssetRecord",
    "AssetRegistry",
    "EvidenceUse",
    "GeneratedAssetEvidenceError",
    "ImageAsset",
    "ImageOutcome",
    "ImageProvider",
    "ImageReceipt",
    "ImageRequest",
    "register_asset",
]


class GeneratedAssetEvidenceError(RuntimeError):
    """A generated asset was about to be registered as evidence.

    The failure this prevents: a generated image used to illustrate a claim it
    never measured. Generated assets may support a video; they may never prove
    one.
    """


class AssetKind:
    """Every kind of asset the planner can ask for.

    Plain strings rather than an ``Enum`` so that receipts and registry files
    stay readable and stable across refactors.
    """

    REAL = "REAL"
    SCREENSHOT = "SCREENSHOT"
    SCREEN_RECORDING = "SCREEN_RECORDING"
    DIAGRAM = "DIAGRAM"
    GENERATED_IMAGE = "GENERATED_IMAGE"
    GENERATED_VIDEO = "GENERATED_VIDEO"

    ALL = (
        REAL,
        SCREENSHOT,
        SCREEN_RECORDING,
        DIAGRAM,
        GENERATED_IMAGE,
        GENERATED_VIDEO,
    )

    #: Kinds that are not synthetic and may therefore support a factual claim.
    EVIDENCE_CAPABLE = (REAL, SCREENSHOT, SCREEN_RECORDING)

    #: Kinds produced by a model. Never evidence, regardless of how convincing
    #: the result looks.
    GENERATED = (GENERATED_IMAGE, GENERATED_VIDEO)


class EvidenceUse:
    """The claim-bearing roles an asset may be registered for."""

    EVIDENCE = "EVIDENCE"
    CLAIM_SOURCE = "CLAIM_SOURCE"
    BENCHMARK_PROOF = "BENCHMARK_PROOF"
    TEST_RESULT = "TEST_RESULT"
    ANALYTICS_PROOF = "ANALYTICS_PROOF"
    UI_SCREENSHOT = "UI_SCREENSHOT"
    CUSTOMER_PROOF = "CUSTOMER_PROOF"
    SOURCE_CODE_PROOF = "SOURCE_CODE_PROOF"
    VISUAL_SUPPORT = "VISUAL_SUPPORT"

    #: Every role that asserts a fact. A generated asset may only take
    #: :attr:`VISUAL_SUPPORT`.
    CLAIM_BEARING = (
        EVIDENCE,
        CLAIM_SOURCE,
        BENCHMARK_PROOF,
        TEST_RESULT,
        ANALYTICS_PROOF,
        UI_SCREENSHOT,
        CUSTOMER_PROOF,
        SOURCE_CODE_PROOF,
    )


@dataclass(frozen=True)
class ImageRequest:
    """What image is wanted.

    Only inputs that change the produced bytes are here. ``prompt`` is kept
    verbatim and hashed into the fingerprint; nothing derived from it is stored,
    because a paraphrase would make the cache key lie.
    """

    prompt: str
    model: Optional[str] = None
    width: int = 768
    height: int = 1360
    seed: Optional[int] = None
    force: bool = False


@dataclass
class ImageAsset:
    """A produced image file plus everything needed to gate and trace it."""

    canonical_path: str
    container: str
    width: int
    height: int
    sha256: str
    technical_qc: Dict[str, Any] = field(default_factory=dict)
    #: Always ``False``. Present as a field rather than implied, so that a
    #: consumer reading only the asset cannot mistake a generated image for a
    #: captured one.
    evidence_capable: bool = False
    generated: bool = True

    @property
    def extension(self) -> str:
        from contentops.media.image_container import canonical_extension_for

        return canonical_extension_for(self.container)


@dataclass
class ImageReceipt:
    """Traceable provenance for one generated image.

    Records the credential *class*, never a credential. Both the requested and
    the observed reality are kept: ``requested_extension`` versus
    ``detected_container`` is the pair that makes a provider's container
    surprise visible instead of silently normalised.
    """

    provider: str
    product: str
    plan: str
    billing_mode: str
    payg_allowed: bool
    credit_pack_allowed: bool
    transport: str
    transport_version: str
    model: str
    prompt_sha256: str
    seed: Optional[int]
    requested_width: int
    requested_height: int
    width: int
    height: int
    requested_path: str
    requested_extension: str
    detected_container: str
    canonical_path: str
    canonical_extension: str
    output_sha256: str
    fingerprint: str
    quota_before: Optional[Any]
    quota_after: Optional[Any]
    billing_guard_verdict: str
    billing_guard_reasons: List[str]
    technical_qc: Dict[str, Any]
    #: Credential class and source only. The private value is never recorded,
    #: here or anywhere else.
    credential_class: str = "UNKNOWN"
    credential_source: str = "UNBOUND"
    #: Set by :func:`register_asset` and the planner. Never ``True`` from a
    #: technical QC pass; that verdict is a human judgement.
    text_contamination_suspected: Optional[bool] = None
    attempt: int = 1
    retry_reason: Optional[str] = None
    fallback: Dict[str, Any] = field(default_factory=dict)
    production_ready: bool = False
    human_review: str = "PENDING_FOUNDER_REVIEW"
    generated: bool = True
    evidence_capable: bool = False
    post_generation_billing_state: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ImageOutcome:
    """Result of one ``generate_image`` call."""

    asset: ImageAsset
    receipt: ImageReceipt
    reused: bool = False
    fallback: Optional[Dict[str, Any]] = None


class ImageProvider(abc.ABC):
    """What every image provider must offer.

    Separate from :class:`contentops.media.contract.MediaProvider` because
    speech and image have genuinely different inputs and outputs, and forcing
    them through one signature would mean optional-everywhere types. Both are
    provider-generic: no vendor vocabulary appears in either.
    """

    name: str = "abstract"

    @abc.abstractmethod
    def capabilities(self) -> Dict[str, Any]:
        """Which image capabilities exist, with evidence status."""

    @abc.abstractmethod
    def health(self) -> Dict[str, Any]:
        """Reachability and credential class. Must never leak a credential."""

    @abc.abstractmethod
    def generate_image(self, request: ImageRequest) -> ImageAsset:
        """Produce an image, reuse a valid cached one, or raise."""

    @abc.abstractmethod
    def receipt(self, asset: Optional[ImageAsset] = None) -> ImageReceipt:
        """Full provenance for a produced image."""


@dataclass
class AssetRecord:
    """One registered asset and the role it is allowed to play."""

    asset_id: str
    kind: str
    path: str
    generated: bool
    evidence_capable: bool
    evidence_use: str
    receipt_ref: Optional[str] = None
    sha256: Optional[str] = None
    notes: Dict[str, Any] = field(default_factory=dict)


class AssetRegistry:
    """In-memory registry of assets and their permitted role.

    The point is the check in :meth:`register`, not the storage. A registry that
    merely lists files would let a generated image drift into an evidence slot
    through a later edit.
    """

    def __init__(self) -> None:
        self._records: Dict[str, AssetRecord] = {}

    def register(
        self,
        *,
        asset_id: str,
        kind: str,
        path: str,
        evidence_use: str = EvidenceUse.VISUAL_SUPPORT,
        receipt_ref: Optional[str] = None,
        sha256: Optional[str] = None,
        generated: Optional[bool] = None,
        evidence_capable: Optional[bool] = None,
        notes: Optional[Dict[str, Any]] = None,
    ) -> AssetRecord:
        """Register an asset, refusing any claim-bearing use of a generated one.

        Raises:
            GeneratedAssetEvidenceError: a generated asset was offered for any
                role in :attr:`EvidenceUse.CLAIM_BEARING`, or a generated asset
                was submitted without the receipt that proves where it came from.
            ValueError: the kind or the evidence use is not a known value.
        """
        if kind not in AssetKind.ALL:
            raise ValueError(f"unknown asset kind {kind!r}")
        if evidence_use not in EvidenceUse.CLAIM_BEARING + (EvidenceUse.VISUAL_SUPPORT,):
            raise ValueError(f"unknown evidence use {evidence_use!r}")

        is_generated = kind in AssetKind.GENERATED if generated is None else bool(generated)
        capable = (
            kind in AssetKind.EVIDENCE_CAPABLE if evidence_capable is None else bool(evidence_capable)
        )

        if is_generated and capable:
            raise GeneratedAssetEvidenceError(
                f"asset {asset_id!r} is generated ({kind}) but was declared "
                f"evidence_capable; that combination is not permitted. Generated "
                f"media can never carry a factual claim."
            )

        if is_generated and evidence_use in EvidenceUse.CLAIM_BEARING:
            raise GeneratedAssetEvidenceError(
                f"asset {asset_id!r} is generated ({kind}) and cannot be "
                f"registered as {evidence_use}. Use VISUAL_SUPPORT. A generated "
                f"image depicting a benchmark, dashboard or terminal is a "
                f"fabricated claim, not evidence."
            )

        if is_generated and not receipt_ref:
            raise GeneratedAssetEvidenceError(
                f"generated asset {asset_id!r} requires receipt_ref; provenance "
                f"is what distinguishes a generated visual from an invented one."
            )

        if not is_generated and evidence_use in EvidenceUse.CLAIM_BEARING and not capable:
            raise GeneratedAssetEvidenceError(
                f"asset {asset_id!r} of kind {kind} is not evidence capable and "
                f"cannot be registered as {evidence_use}."
            )

        record = AssetRecord(
            asset_id=asset_id,
            kind=kind,
            path=str(path),
            generated=is_generated,
            evidence_capable=capable,
            evidence_use=evidence_use,
            receipt_ref=receipt_ref,
            sha256=sha256,
            notes=dict(notes or {}),
        )
        self._records[asset_id] = record
        return record

    def get(self, asset_id: str) -> Optional[AssetRecord]:
        return self._records.get(asset_id)

    def all(self) -> List[AssetRecord]:
        return list(self._records.values())

    def assert_evidence_boundary(self) -> None:
        """Re-check every record. Cheap insurance against a bad direct write."""
        for record in self._records.values():
            if record.generated and record.evidence_use in EvidenceUse.CLAIM_BEARING:
                raise GeneratedAssetEvidenceError(
                    f"registry contains generated asset {record.asset_id!r} "
                    f"registered as {record.evidence_use}"
                )


def register_asset(
    registry: AssetRegistry,
    *,
    asset_id: str,
    kind: str,
    path: str,
    evidence_use: str = EvidenceUse.VISUAL_SUPPORT,
    receipt_ref: Optional[str] = None,
    sha256: Optional[str] = None,
    generated: Optional[bool] = None,
    evidence_capable: Optional[bool] = None,
    notes: Optional[Dict[str, Any]] = None,
) -> AssetRecord:
    """Module-level convenience wrapper around :meth:`AssetRegistry.register`."""
    return registry.register(
        asset_id=asset_id,
        kind=kind,
        path=path,
        evidence_use=evidence_use,
        receipt_ref=receipt_ref,
        sha256=sha256,
        generated=generated,
        evidence_capable=evidence_capable,
        notes=notes,
    )