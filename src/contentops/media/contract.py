"""Provider-generic speech contract, and the shape of the provider family.

Deliberately **not** provider-shaped. The North Star needs speech, image and
generated video, and none of those may leak MiniMax vocabulary into the
architecture. A future provider with a different billing model must be addable
without editing the interface.

The provider family
-------------------
Speech and image are **separate provider ABCs** over one set of shared
infrastructure, not one monolithic class with optional-everywhere signatures:

===========================  ==========================================
ABC                          Modality
===========================  ==========================================
:class:`SpeechProvider`      narration  (``contract.py``)
:class:`ImageProvider`       stills    (``image_contract.py``)
:class:`VideoProvider`       shots     (``video_contract.py``, Issue #22)
===========================  ==========================================

Shared by all of them: :class:`~contentops.media.credentials.ResolvedCredential`,
``CredentialBinding``, ``BillingGuard``, ``GenerationAttemptRecord``, the
transport helpers, the fingerprint conventions, immutable receipts and the
reuse-event conventions. Provider identity lives in ``mplan_identity``.

Splitting them is what keeps a receipt honest. Speech and image have genuinely
different inputs, outputs and failure modes, and forcing them through one
signature produces optional arguments rather than types. Future orchestration
may aggregate the family through a ``MediaProviderRegistry``; that is deliberately
not built yet, because with two members a registry is indirection without benefit.

:class:`MediaProvider` remains the common ancestor so that existing speech code
and its tests keep working. Its ``generate_image`` / ``generate_video`` hooks are
**deprecated cross-modality shortcuts**: :class:`~contentops.media.contract.MediaProvider.generate_image`
raises :class:`CapabilityNotSupported` and says so, rather than pretending. An
unimplemented capability that raises is honest; one that silently falls back to
edge-tts or a manual import is not.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__all__ = [
    "CapabilityNotSupported",
    "BillingBlocked",
    "MediaProvider",
    "SpeechRequest",
    "SpeechAsset",
    "SpeechReceipt",
    "QuotaSnapshot",
]


class CapabilityNotSupported(NotImplementedError):
    """The provider does not offer this modality.

    Raised instead of returning a fake asset or falling back silently.
    """


class BillingBlocked(RuntimeError):
    """Generation refused because the billing source could not be proven.

    Carries the machine-readable verdict so a caller can put it in a receipt
    rather than only in a log line.
    """

    def __init__(self, verdict: str, reasons: List[str]) -> None:
        self.verdict = verdict
        self.reasons = list(reasons)
        super().__init__(f"{verdict}: " + "; ".join(reasons))


@dataclass(frozen=True)
class QuotaSnapshot:
    """Included-plan usage as far as the provider exposes it.

    ``modality_breakdown`` is usually empty: M Plan exposes a single ``general``
    bucket, so ContentOps can answer "is there plan usage left" but not "how many
    images are left". Callers must not assume per-modality numbers exist.
    """

    bucket: Optional[str]
    interval_remaining_percent: Optional[float]
    weekly_remaining_percent: Optional[float]
    modality_breakdown: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SpeechRequest:
    """A narration request.

    ``display_text`` is what the reader sees. ``spoken_text`` is what the voice
    says, and they are kept apart on purpose: a pronunciation lexicon changes
    only the spoken form. See :mod:`contentops.media.lexicon`.
    """

    display_text: str
    spoken_text: Optional[str] = None
    voice: Optional[str] = None
    language: str = "zh"
    speed: Optional[float] = None
    model: Optional[str] = None
    pronunciation: tuple = ()
    text_normalization: bool = True
    force: bool = False


@dataclass
class SpeechAsset:
    """A produced narration file plus the measurements needed to gate it."""

    raw_path: str
    normalized_path: Optional[str]
    model: str
    voice: str
    display_text_sha256: str
    spoken_text_sha256: str
    raw_sha256: str
    normalized_sha256: Optional[str]
    duration_s: Optional[float]
    sample_rate_hz: Optional[int]
    channels: Optional[int]
    codec: Optional[str]
    peak_before_db: Optional[float]
    peak_after_db: Optional[float]
    loudness_before: Optional[float]
    loudness_after: Optional[float]
    technical_qc: Dict[str, Any] = field(default_factory=dict)
    semantic_qc: Dict[str, Any] = field(default_factory=dict)
    approved: bool = False


@dataclass
class SpeechReceipt:
    """Traceable provenance for one narration.

    Carries the billing verdict, both hashes and the QC outcomes. It records the
    credential *class*, never a credential.
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
    voice: str
    display_text_sha256: str
    spoken_text_sha256: str
    lexicon_version: str
    fingerprint: str
    quota_before: Optional[QuotaSnapshot]
    quota_after: Optional[QuotaSnapshot]
    billing_guard_verdict: str
    billing_guard_reasons: List[str]
    technical_qc: Dict[str, Any]
    semantic_qc: Dict[str, Any]
    raw_sha256: str
    normalized_sha256: Optional[str]
    attempt: int
    retry_reason: Optional[str]
    fallback: Dict[str, Any]
    production_ready: bool
    human_review: str
    #: Observed state *after* generation. Recorded separately so a later
    #: exhaustion can never overwrite the authorisation that permitted the call.
    post_generation_billing_state: Dict[str, Any] = field(default_factory=dict)


class MediaProvider(abc.ABC):
    """What every media provider must offer.

    Implementations speak their own vendor's vocabulary; callers do not.
    """

    name: str = "abstract"

    @abc.abstractmethod
    def capabilities(self) -> Dict[str, Any]:
        """Which modalities are actually available, with evidence status."""

    @abc.abstractmethod
    def health(self) -> Dict[str, Any]:
        """Reachability and credential class. Must never leak a credential."""

    @abc.abstractmethod
    def quota(self) -> QuotaSnapshot:
        """Remaining included-plan usage."""

    @abc.abstractmethod
    def synthesize_speech(self, request: SpeechRequest) -> SpeechAsset:
        """Produce narration. Only supported where ``capabilities()`` says so."""

    @abc.abstractmethod
    def receipt(self, asset: SpeechAsset) -> SpeechReceipt:
        """Full provenance for a produced asset."""

    def generate_image(self, request: Any) -> Any:
        """Deprecated shortcut. Use an ``ImageProvider``.

        Speech and image are separate provider ABCs sharing infrastructure; a
        speech provider does not implement image generation.
        """
        raise CapabilityNotSupported(
            f"{self.name} is a speech provider and does not implement image "
            f"generation. Build an ImageProvider (see image_contract.py); this "
            f"cross-modality shortcut is deprecated."
        )

    def generate_video(self, request: Any) -> Any:
        """Deprecated shortcut. Use a ``VideoProvider`` (Issue #22).

        Raises rather than falling back: a video request that silently became
        a still image, or a manual import, would be a fabricated capability.
        """
        raise CapabilityNotSupported(
            f"{self.name} is a speech provider and does not implement video "
            f"generation. Build a VideoProvider when Issue #22 introduces it; "
            f"this cross-modality shortcut is deprecated."
        )