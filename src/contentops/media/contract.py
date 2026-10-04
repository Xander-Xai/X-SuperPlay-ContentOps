"""Provider-generic media contract.

Deliberately **not** provider-shaped. The North Star needs speech first, image
next and generated video last, and none of those may leak MiniMax vocabulary
into the architecture. A future provider with a different billing model must be
addable without editing the interface.

Only what #19 needs exists. ``generate_image`` and ``generate_video`` are
declared as unimplemented on purpose: a method that raises
:class:`CapabilityNotSupported` is honest, a method that silently falls back to
edge-tts or to a manual import is not.
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
        raise CapabilityNotSupported(
            f"{self.name} does not implement image generation in this milestone"
        )

    def generate_video(self, request: Any) -> Any:
        raise CapabilityNotSupported(
            f"{self.name} does not implement video generation in this milestone"
        )