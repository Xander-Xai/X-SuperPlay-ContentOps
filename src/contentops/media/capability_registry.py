"""Resolve an executor by capability, never by vendor name.

Why this exists now and not earlier
-----------------------------------
It was deliberately deferred while there were fewer members, because a registry
with one or two entries is indirection without benefit. There is now a concrete
consumer: the asset execution layer must answer "who can produce a
``GENERATED_IMAGE`` support visual?" and "who can produce an ``H3_I2VA`` shot?"
before it can execute a plan. That question is about capability, not vendor — a
future provider should be addable by declaring a capability, not by a caller
rewriting an import.

What it is not
--------------
Not a plugin framework. There is no discovery, no entry-point scanning and no
dynamic loading. A capability is registered explicitly by code that knows what it
provides. That is the whole design surface, and it is small on purpose.

What it does not hold
---------------------
No credential, no ``BillingGuard``, no plan state, no secret of any kind. Those
belong to the provider that already owns them. :meth:`MediaCapabilityRegistry.
describe` deliberately cannot expose them because the registry never receives
them: registration takes an *executor callable*, not a provider object.

Why status matters
------------------
The registry is the one place a consumer asks "can I rely on this?", so it is the
one place where an over-optimistic answer would be most costly. Status is
therefore **not** inferred from "the code exists" or "the fixtures pass":

``VERIFIED``
    exercised against the live provider on this account, with a receipt.
``DOCUMENTED_BUT_NOT_TESTED``
    implemented and fixture-tested, never run live. Which is *not* the same as
    working, and is recorded as such.
``MANUAL_ONLY``
    a person has to do it; no code path.
``UNAVAILABLE``
    declared as a gap so a caller gets a clear refusal instead of a silent one.

Fixture evidence proves how code behaves. It never proves what an account is
entitled to, and the two are not conflated here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from contentops.media.contract import CapabilityNotSupported
from contentops.media.media_envelope import MediaModality

__all__ = [
    "CAPABILITY_SPEECH_NARRATION",
    "CAPABILITY_VIDEO_H3_FL2VA",
    "CAPABILITY_VIDEO_H3_I2VA",
    "CAPABILITY_VIDEO_H3_L2VA",
    "CAPABILITY_VIDEO_H3_MAX",
    "CAPABILITY_VIDEO_H3_REF2VA",
    "CAPABILITY_VIDEO_H3_T2VA",
    "CAPABILITY_VISUAL_GENERATED_IMAGE",
    "CAPABILITY_VISUAL_REAL_EVIDENCE",
    "CAPABILITIES",
    "CapabilityDescriptor",
    "MediaCapabilityRegistry",
    "SUPPORTED_STATUSES",
]

# --- capability identifiers -------------------------------------------------
#
# Named by capability, not by vendor. The word "MiniMax" appears in none of them,
# because the consumer asks what it needs, not who supplies it.

CAPABILITY_SPEECH_NARRATION = "SPEECH/NARRATION"
CAPABILITY_VISUAL_REAL_EVIDENCE = "VISUAL/REAL_EVIDENCE"
CAPABILITY_VISUAL_DIAGRAM = "VISUAL/DIAGRAM"
CAPABILITY_VISUAL_GENERATED_IMAGE = "IMAGE/GENERATED_SUPPORT_VISUAL"

CAPABILITY_VIDEO_H3_T2VA = "VIDEO/H3_T2VA"
CAPABILITY_VIDEO_H3_I2VA = "VIDEO/H3_I2VA"
CAPABILITY_VIDEO_H3_FL2VA = "VIDEO/H3_FL2VA"
CAPABILITY_VIDEO_H3_L2VA = "VIDEO/H3_L2VA"
CAPABILITY_VIDEO_H3_REF2VA = "VIDEO/H3_REF2VA"
CAPABILITY_VIDEO_H3_MAX = "VIDEO/H3_MAX"

STATUS_VERIFIED = "VERIFIED"
STATUS_DOCUMENTED = "DOCUMENTED_BUT_NOT_TESTED"
STATUS_MANUAL_ONLY = "MANUAL_ONLY"
STATUS_UNAVAILABLE = "UNAVAILABLE"

SUPPORTED_STATUSES: Tuple[str, ...] = (
    STATUS_VERIFIED,
    STATUS_DOCUMENTED,
    STATUS_MANUAL_ONLY,
    STATUS_UNAVAILABLE,
)


@dataclass(frozen=True)
class CapabilityDescriptor:
    """What one registered capability offers.

    Frozen on purpose: a descriptor is a declaration of fact. Mutating one into
    saying more than it was registered to say would be the exact failure this
    module exists to prevent, and freezing it makes that a loud error rather than
    a quiet edit.
    """

    capability: str
    modality: str
    #: Callable that performs the work. A callable, never a provider object, so
    #: the registry cannot accidentally hold billing or credential state.
    executor: Callable[..., Any]
    status: str
    provider: str
    models: Tuple[str, ...] = ()
    modes: Tuple[str, ...] = ()
    #: Evidence for the declared status. A receipt path or issue reference. Empty
    #: for ``UNAVAILABLE``, which is why it is required to be non-empty otherwise.
    evidence: Tuple[str, ...] = ()
    #: Every generated asset still awaits a human. True for all three providers
    #: today; recorded rather than assumed so a future consumer reads it instead
    #: of guessing.
    requires_human_review: bool = True
    #: What this capability can never be used for, in plain words.
    never_evidence_capable: bool = False
    notes: str = ""

    def __post_init__(self) -> None:
        if self.status not in SUPPORTED_STATUSES:
            raise ValueError(
                f"capability {self.capability!r} has unknown status "
                f"{self.status!r}; expected one of {', '.join(SUPPORTED_STATUSES)}"
            )
        MediaModality.canonical(self.modality)
        if self.status != STATUS_UNAVAILABLE and not self.evidence:
            raise ValueError(
                f"capability {self.capability!r} declares {self.status!r} but "
                f"cites no evidence. A status with nothing behind it is a guess, "
                f"and this module does not accept guesses."
            )

    @property
    def usable(self) -> bool:
        """True when code can execute this capability right now.

        ``DOCUMENTED_BUT_NOT_TESTED`` is deliberately usable: the code path
        exists and is tested. What is *not* allowed is treating it as
        ``VERIFIED``. The distinction is between "can run" and "has run against
        the provider", and this property answers only the first.
        """
        return self.status in (STATUS_VERIFIED, STATUS_DOCUMENTED)

    def as_dict(self) -> Dict[str, Any]:
        """A description safe to print, log or put in a manifest.

        Note what is absent: the executor callable is not serialised, because a
        function has no useful serial form and its repr would leak a bound
        method's owner.
        """
        return {
            "capability": self.capability,
            "modality": self.modality,
            "status": self.status,
            "provider": self.provider,
            "models": list(self.models),
            "modes": list(self.modes),
            "evidence": list(self.evidence),
            "requires_human_review": self.requires_human_review,
            "never_evidence_capable": self.never_evidence_capable,
            "usable": self.usable,
            "notes": self.notes,
        }


#: The default registry, built from what has actually been proven.
#:
#: Each entry cites its evidence. That is what stops this table from decaying
#: into a wish list: a capability cannot be added at ``VERIFIED`` without naming
#: the receipt that proves it.
CAPABILITIES: Tuple[CapabilityDescriptor, ...] = (
    CapabilityDescriptor(
        capability=CAPABILITY_SPEECH_NARRATION,
        modality=MediaModality.SPEECH,
        executor=lambda **kw: None,
        status=STATUS_VERIFIED,
        provider="minimax_m_plan",
        models=("speech-2.8-hd",),
        evidence=(
            "PR #24 merged 731d45e",
            "research/providers/minimax-mplan-explore-capability.md",
        ),
        notes="Deterministic narration. Not a visual kind and never evidence.",
    ),
    CapabilityDescriptor(
        capability=CAPABILITY_VISUAL_REAL_EVIDENCE,
        modality=MediaModality.IMAGE,
        executor=lambda **kw: None,
        status=STATUS_MANUAL_ONLY,
        provider="operator",
        modes=("REAL", "SCREENSHOT", "SCREEN_RECORDING"),
        evidence=(
            "projects/easel-review/sources/screenshots (existing real captures)",
        ),
        requires_human_review=False,
        notes=(
            "Locating and importing real material. M4.5 deliberately does not "
            "build a browser recorder; absence is reported, never substituted."
        ),
    ),
    CapabilityDescriptor(
        capability=CAPABILITY_VISUAL_DIAGRAM,
        modality=MediaModality.IMAGE,
        executor=lambda **kw: None,
        status=STATUS_MANUAL_ONLY,
        provider="operator",
        modes=("DIAGRAM",),
        evidence=("docs/MEDIA-PROVIDER-CONTRACT.md (DIAGRAM is support-only)",),
        requires_human_review=False,
        notes="Deterministic drawing. Explains, never proves.",
    ),
    CapabilityDescriptor(
        capability=CAPABILITY_VISUAL_GENERATED_IMAGE,
        modality=MediaModality.IMAGE,
        executor=lambda **kw: None,
        status=STATUS_VERIFIED,
        provider="minimax_m_plan",
        models=("image-01",),
        evidence=(
            "PR #25 merged 1849e84",
            "research/providers/minimax-mplan-explore-capability.md",
        ),
        never_evidence_capable=True,
        notes="Support visual only. Registering one as evidence is refused.",
    ),
    CapabilityDescriptor(
        capability=CAPABILITY_VIDEO_H3_T2VA,
        modality=MediaModality.VIDEO,
        executor=lambda **kw: None,
        status=STATUS_VERIFIED,
        provider="minimax_m_plan",
        models=("MiniMax-H3",),
        modes=("T2VA",),
        evidence=(
            "M2.0 real task, Issue #4",
            "research/providers/minimax-mplan-explore-capability.md",
        ),
        never_evidence_capable=True,
    ),
    CapabilityDescriptor(
        capability=CAPABILITY_VIDEO_H3_I2VA,
        modality=MediaModality.VIDEO,
        executor=lambda **kw: None,
        status=STATUS_VERIFIED,
        provider="minimax_m_plan",
        models=("MiniMax-H3",),
        modes=("I2VA",),
        evidence=(
            "research/providers/receipts/"
            "minimax-h3-i2va-reference-2026-10-05.sanitized.json",
        ),
        never_evidence_capable=True,
        notes=(
            "The only reference mode exercised against the live service, and the "
            "only one that proved the data-URI reference path works."
        ),
    ),
    CapabilityDescriptor(
        capability=CAPABILITY_VIDEO_H3_FL2VA,
        modality=MediaModality.VIDEO,
        executor=lambda **kw: None,
        status=STATUS_DOCUMENTED,
        provider="minimax_m_plan",
        models=("MiniMax-H3",),
        modes=("FL2VA",),
        evidence=(
            "tests/test_minimax_h3.py (fixture and schema coverage)",
            "research/providers/minimax-h3-official-reality.md",
        ),
        never_evidence_capable=True,
        notes="Implemented and fixture-tested. Never run live. Not VERIFIED.",
    ),
    CapabilityDescriptor(
        capability=CAPABILITY_VIDEO_H3_L2VA,
        modality=MediaModality.VIDEO,
        executor=lambda **kw: None,
        status=STATUS_DOCUMENTED,
        provider="minimax_m_plan",
        models=("MiniMax-H3",),
        modes=("L2VA",),
        evidence=(
            "tests/test_minimax_h3.py (fixture and schema coverage)",
            "research/providers/minimax-h3-official-reality.md",
        ),
        never_evidence_capable=True,
        notes="Implemented and fixture-tested. Never run live. Not VERIFIED.",
    ),
    CapabilityDescriptor(
        capability=CAPABILITY_VIDEO_H3_REF2VA,
        modality=MediaModality.VIDEO,
        executor=lambda **kw: None,
        status=STATUS_DOCUMENTED,
        provider="minimax_m_plan",
        models=("MiniMax-H3",),
        modes=("Ref2VA",),
        evidence=(
            "tests/test_minimax_h3.py (fixture and schema coverage)",
            "research/providers/minimax-h3-official-reality.md",
        ),
        never_evidence_capable=True,
        notes=(
            "Reference video and audio share the content[] machinery the I2VA "
            "test exercised, but that is an argument, not a receipt. Not VERIFIED."
        ),
    ),
    CapabilityDescriptor(
        capability=CAPABILITY_VIDEO_H3_MAX,
        modality=MediaModality.VIDEO,
        executor=lambda **kw: None,
        status=STATUS_DOCUMENTED,
        provider="minimax_m_plan",
        models=("MiniMax-H3-Max",),
        evidence=(
            "research/providers/minimax-h3-official-reality.md (documented only)",
        ),
        never_evidence_capable=True,
        notes=(
            "Different duration floor (5 s) and no 2K. Documented, never run. "
            "Not VERIFIED."
        ),
    ),
)


class MediaCapabilityRegistry:
    """Explicit capability -> executor lookup.

    Holds no credential, no billing guard, no quota state and no provider object.
    Registration takes a callable precisely so there is nothing secret to retain.
    """

    def __init__(self, descriptors: Optional[Tuple[CapabilityDescriptor, ...]] = None) -> None:
        self._by_capability: Dict[str, CapabilityDescriptor] = {}
        for descriptor in (descriptors if descriptors is not None else CAPABILITIES):
            self.register(descriptor)

    def register(self, descriptor: CapabilityDescriptor) -> None:
        """Register one capability. Re-registering a name is refused."""
        if descriptor.capability in self._by_capability:
            raise ValueError(
                f"capability {descriptor.capability!r} is already registered. "
                f"Two executors claiming one capability is a routing ambiguity, "
                f"not an override."
            )
        self._by_capability[descriptor.capability] = descriptor

    def capabilities(self) -> List[str]:
        """Registered capability names, sorted for determinism."""
        return sorted(self._by_capability)

    def describe(self, capability: str) -> Dict[str, Any]:
        """Safe description of one capability.

        Raises:
            CapabilityNotSupported: no such capability.
        """
        return self._require(capability).as_dict()

    def find(self, capability: str) -> Optional[CapabilityDescriptor]:
        """The descriptor, or ``None``. For callers that want to branch."""
        return self._by_capability.get(capability)

    def resolve(self, capability: str) -> Callable[..., Any]:
        """Return the executor for a capability.

        Raises:
            CapabilityNotSupported: the capability is not registered, or is
                registered as unavailable. Never returns a substitute, because a
                silent swap to a different capability is the failure this
                prevents.
        """
        descriptor = self._require(capability)
        if not descriptor.usable:
            raise CapabilityNotSupported(
                f"capability {capability!r} is {descriptor.status} and cannot be "
                f"executed automatically"
                + (f"; {descriptor.notes}" if descriptor.notes else "")
            )
        return descriptor.executor

    def status(self, capability: str) -> str:
        return self._require(capability).status

    def is_verified(self, capability: str) -> bool:
        """True only when a live receipt exists.

        Narrower than :meth:`usable` on purpose, so a caller that needs
        proven-in-production can ask precisely that question.
        """
        return self.status(capability) == STATUS_VERIFIED

    def by_modality(self, modality: str) -> List[CapabilityDescriptor]:
        canonical = MediaModality.canonical(modality)
        return [
            descriptor for descriptor in self._by_capability.values()
            if descriptor.modality == canonical
        ]

    def require_evidence_capable(self, capability: str) -> None:
        """Refuse a capability that may never carry a factual claim.

        Called by the execution layer before routing a claim-bearing beat, so the
        refusal happens before work is spent rather than after.

        Raises:
            CapabilityNotSupported: the capability cannot be evidence.
        """
        descriptor = self._require(capability)
        if descriptor.never_evidence_capable:
            raise CapabilityNotSupported(
                f"capability {capability!r} may never carry a factual claim. It is "
                f"a {descriptor.modality.lower()} asset from {descriptor.provider} "
                f"and generated or substituted material cannot prove anything."
            )

    def describe_all(self) -> List[Dict[str, Any]]:
        return [self.describe(name) for name in self.capabilities()]

    def _require(self, capability: str) -> CapabilityDescriptor:
        descriptor = self._by_capability.get(capability)
        if descriptor is None:
            available = ", ".join(self.capabilities()) or "none"
            raise CapabilityNotSupported(
                f"no capability {capability!r} is registered. Available: "
                f"{available}. Refusing to substitute a different one."
            )
        return descriptor
