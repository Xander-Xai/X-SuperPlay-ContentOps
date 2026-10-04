"""Provider-generic video types, and the third member of the provider family.

Why video is its own ABC
------------------------
Speech (`MediaProvider`), image (`ImageProvider`) and video (`VideoProvider`) are
separate ABCs over one set of shared infrastructure. Video's inputs are genuinely
different: it is asynchronous, it needs references rather than only text, it
carries an audio track the caller did not ask for, and its most important
invariant is about *how many times a paid task may be created*. Forcing that
through a speech-shaped signature would produce optional arguments everywhere and
would bury the one-task rule in a boolean.

The family, and what it shares
------------------------------
======================  ==============================================
ABC                     Modality
======================  ==============================================
``MediaProvider``       narration (M2)
``ImageProvider``       stills (M3)
``VideoProvider``       generated shots (M4, this module)
======================  ==============================================

Shared infrastructure, one implementation each, never one per modality:

- ``ResolvedCredential`` / ``CredentialBinding`` \u2014 credential identity
- ``BillingGuard`` \u2014 included-plan proof
- ``GenerationAttemptRecord`` \u2014 durable retry evidence
- ``transport.py`` \u2014 CLI resolution, output verification, sidecar conventions
- ``fingerprint.py`` / ``image_fingerprint.py`` \u2014 cache key conventions
- ``mplan_identity.py`` \u2014 provider identity and billing constants
- immutable receipts and append-only reuse events

Evidence boundary
-----------------
A generated shot is a **support visual**. ``AssetKind.EVIDENCE_CAPABLE`` remains
``REAL``, ``SCREENSHOT``, ``SCREEN_RECORDING`` only, and ``GENERATED_VIDEO`` is
support-only. That boundary is enforced by the M3 registry and is not redefined
here; :class:`VideoReceipt` simply carries the same two flags truthfully.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "AUDIO_POLICY_REPLACE",
    "AUDIO_POLICIES",
    "AUDIO_POLICY_KEEP",
    "AUDIO_POLICY_MUTE",
    "AudioPolicy",
    "HUMAN_REVIEW_FIELDS",
    "HUMAN_REVIEW_PENDING",
    "REFERENCE_ONLY_REVIEW_FIELDS",
    "VideoAsset",
    "VideoOutcome",
    "VideoProvider",
    "VideoReceipt",
    "VideoRequest",
    "VideoTaskState",
    "build_human_review_package",
]


class AudioPolicy:
    """What to do with the audio H3 generated even when nobody asked for it.

    M2.0 measured a real H3 result containing an AAC track for a request that did
    not request audio. So the track's existence cannot be treated as a surprise to
    react to later; it has to be a decision.

    Three explicit choices, no default behaviour that depends on what the
    provider happened to return:

    ``KEEP``
        use the generated track.
    ``MUTE``
        keep the file, drop the track.
    ``REPLACE``
        drop the generated track and substitute deterministic narration.

    ``REPLACE`` is the ContentOps default, because narration must stay
    deterministic and reproducible; H3's native sound must never quietly compete
    with it. Silent mixing of generated audio and narration is never allowed.
    """

    KEEP = "KEEP"
    MUTE = "MUTE"
    REPLACE = "REPLACE"

    ALL = (KEEP, MUTE, REPLACE)
    DEFAULT = REPLACE


AUDIO_POLICY_KEEP = AudioPolicy.KEEP
AUDIO_POLICY_MUTE = AudioPolicy.MUTE
AUDIO_POLICY_REPLACE = AudioPolicy.REPLACE
AUDIO_POLICIES = AudioPolicy.ALL


class VideoTaskState:
    """Provider task states, from the documented Query Task schema.

    Non-terminal states mean *keep waiting*. Terminal states mean *stop polling*.
    Anything else is unknown, and an unknown state must never be treated as a
    reason to create another task.
    """

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    NON_TERMINAL = (QUEUED, RUNNING)
    TERMINAL = (SUCCEEDED, FAILED, CANCELLED)
    ALL = (QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED)

    #: A task in one of these is not a failure and must never be retried.
    @staticmethod
    def is_terminal(state: Optional[str]) -> bool:
        return state in VideoTaskState.TERMINAL

    @staticmethod
    def is_success(state: Optional[str]) -> bool:
        return state == VideoTaskState.SUCCEEDED

    @staticmethod
    def is_failure(state: Optional[str]) -> bool:
        return state in (VideoTaskState.FAILED, VideoTaskState.CANCELLED)


@dataclass(frozen=True)
class VideoRequest:
    """One requested shot.

    Business-facing and provider-neutral. Nothing here is an API payload: no
    ``content[]``, no ``role=first_frame``, no provider field names. The provider
    maps this into whatever its transport needs.

    ``compiled_prompt`` is supplied by :class:`~contentops.media.h3_prompt.H3PromptCompiler`
    rather than authored here, because the fingerprint must cover the prompt that
    is actually sent and not merely the operator's intent.
    """

    compiled_prompt: str
    mode: str
    model: str
    duration_s: int
    resolution: str
    ratio: Optional[str] = None
    #: Provider-neutral references. The provider decides how to send them.
    reference_images: tuple = ()
    reference_videos: tuple = ()
    reference_audio: tuple = ()
    first_frame: Optional[str] = None
    last_frame: Optional[str] = None
    #: Generation-affecting provider options, passed through untouched. Only
    #: ``MiniMax-H3-Max`` documents any. Unknown keys are refused locally, because
    #: the API rejects undeclared fields and the resulting error names the option
    #: rather than the request.
    extra: Optional[Dict[str, Any]] = None
    audio_policy: str = AudioPolicy.DEFAULT
    force: bool = False


@dataclass
class VideoAsset:
    """A produced shot plus everything needed to gate and trace it."""

    canonical_path: str
    container: str
    codec: Optional[str]
    width: int
    height: int
    duration_s: float
    fps: Optional[float]
    has_audio: bool
    sha256: str
    technical_qc: Dict[str, Any] = field(default_factory=dict)
    audio_policy: str = AudioPolicy.DEFAULT
    #: Always ``False``. Present as a field rather than implied, so a consumer
    #: reading only the asset cannot mistake generated footage for a capture.
    evidence_capable: bool = False
    generated: bool = True

    @property
    def aspect_ratio(self) -> float:
        return round(self.width / self.height, 6) if self.height else 0.0


@dataclass
class VideoReceipt:
    """Immutable provenance for one generated shot.

    Records the credential *class* and *source*, never a credential, and a
    **salted hash** of the provider task id rather than the raw id. The raw task
    id is operationally necessary for resuming a poll but is not public: it lives
    only in private runtime state.
    """

    provider: str
    product: str
    plan: str
    billing_mode: str
    payg_allowed: bool
    credit_pack_allowed: bool
    credential_class: str
    credential_source: str
    transport: str
    api_schema_version: Optional[str]
    model: str
    mode: str
    compiled_prompt_sha256: str
    prompt_skill_repo: str
    prompt_skill_commit: str
    reference_asset_sha256: List[str]
    #: Each reference with the media type **detected from its content**, plus
    #: whether its file name agreed. Recorded so a mismatch stays visible rather
    #: than being normalised away: a caller who sent ``.png`` and got
    #: ``image/jpeg`` can see exactly that.
    reference_media: List[Dict[str, Any]]
    requested_duration_s: int
    actual_duration_s: float
    requested_resolution: str
    actual_width: int
    actual_height: int
    requested_ratio: Optional[str]
    actual_ratio: Optional[float]
    canonical_path: str
    output_sha256: str
    fingerprint: str
    task_created: bool
    task_ref_hash: str
    billing_guard_verdict: str
    billing_guard_reasons: List[str]
    quota_before: Optional[Any]
    quota_after: Optional[Any]
    technical_qc: Dict[str, Any]
    audio_policy: str
    audio_stream_present: bool
    attempt: int = 1
    retry_reason: Optional[str] = None
    fallback: Dict[str, Any] = field(default_factory=dict)
    #: Generation-affecting provider options actually sent. Empty means the
    #: documented provider default applied, which is what the schema does when
    #: ``extra`` is omitted.
    extra: Dict[str, Any] = field(default_factory=dict)
    #: The declared weekly-quota budget for this run, verbatim. A receipt that
    #: cannot say what the run was allowed to spend cannot show whether it stayed
    #: inside that budget.
    quota_budget: Optional[str] = None
    #: What this generation was meant to prove. Absent means a production shot, not
    #: an experiment; either way it is recorded rather than inferred.
    test_objective: Optional[str] = None
    #: Technical QC passing is not production readiness. A Founder has to watch it.
    production_ready: bool = False
    human_review: str = "PENDING_FOUNDER_REVIEW"
    generated: bool = True
    evidence_capable: bool = False
    post_generation_billing_state: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VideoOutcome:
    """Result of one ``generate_video`` call."""

    asset: VideoAsset
    receipt: VideoReceipt
    reused: bool = False
    fallback: Optional[Dict[str, Any]] = None


#: The judgements only a person can make about a generated shot.
#:
#: These are deliberately absent from automated QC. Automated QC can prove a file
#: decodes, runs 4.4 s, is 768x1344 and does not freeze. It cannot tell whether the
#: subject stayed the same person, whether a referenced object drifted, or whether
#: the Founder would publish it. An automated gate that guessed at those would be
#: teaching the pipeline to trust itself, which is the failure this repository exists
#: to prevent. So the fields exist, are named, and stay ``null``.
HUMAN_REVIEW_FIELDS: Tuple[str, ...] = (
    "subject_fidelity",
    "motion_plausibility",
    "temporal_artifacts",
    "reference_fidelity",
    "first_frame_fidelity",
    "last_frame_fidelity",
    "audio_suitability",
    "caption_safe_area",
    "cross_shot_consistency",
    "overall_quality",
    "willingness_to_publish",
)

#: Fields that only mean something for the reference and frame modes. Recorded as
#: not-applicable rather than omitted, so a reviewer can tell "not assessed" from
#: "not relevant to this mode".
REFERENCE_ONLY_REVIEW_FIELDS: Tuple[str, ...] = (
    "reference_fidelity",
    "first_frame_fidelity",
    "last_frame_fidelity",
)

HUMAN_REVIEW_PENDING = "PENDING_FOUNDER_REVIEW"


def build_human_review_package(
    *,
    asset: VideoAsset,
    receipt: VideoReceipt,
    mode: str,
) -> Dict[str, Any]:
    """Build the Founder's review sheet for one generated shot.

    Every judgement is ``None``. That is the correct initial state, not an omission:
    a filled-in field would be a manufactured verdict, and a receipt whose
    ``human_review`` says PENDING while its scores are populated is a receipt lying
    about its own provenance.

    Automated observations are carried alongside, clearly separated and clearly
    labelled as measurements. They are evidence for the reviewer, not a substitute
    for the review.
    """
    uses_reference = mode in ("Ref2VA",) or mode in ("I2VA", "FL2VA", "L2VA")
    scores: Dict[str, Optional[int]] = {}
    not_applicable: List[str] = []
    for name in HUMAN_REVIEW_FIELDS:
        if name in REFERENCE_ONLY_REVIEW_FIELDS and not uses_reference:
            scores[name] = None
            not_applicable.append(name)
        else:
            scores[name] = None

    return {
        "schema": "contentops.human-review.video/v1",
        "asset": {
            "canonical_path": asset.canonical_path,
            "sha256": asset.sha256,
            "duration_s": asset.duration_s,
            "width": asset.width,
            "height": asset.height,
            "fps": asset.fps,
            "has_audio": asset.has_audio,
        },
        "mode": mode,
        "model": receipt.model,
        "fingerprint": receipt.fingerprint,
        "audio_policy": asset.audio_policy,
        "state": HUMAN_REVIEW_PENDING,
        "reviewer": None,
        "reviewed_at": None,
        "decision": HUMAN_REVIEW_PENDING,
        "notes": None,
        "scores": scores,
        "not_applicable_fields": not_applicable,
        "automated_observations": {
            "note": "measurements, not judgements; they do not approve a shot",
            "technical_qc": dict(receipt.technical_qc),
        },
        "instructions": (
            "Watch the shot, then fill each applicable score. Leave a field null if "
            "it was not assessed. Until decision changes from "
            f"{HUMAN_REVIEW_PENDING}, this asset is not production_ready and must "
            "not carry a claim."
        ),
    }


class VideoProvider(abc.ABC):
    """What every video provider must offer.

    Separate from ``MediaProvider`` on purpose, so the one-task rule and the
    audio decision are explicit parts of the contract rather than optional
    parameters on a speech interface.
    """

    name: str = "abstract"

    @abc.abstractmethod
    def capabilities(self) -> Dict[str, Any]:
        """Which video capabilities exist, with evidence status."""

    @abc.abstractmethod
    def health(self) -> Dict[str, Any]:
        """Reachability and credential class. Must never leak a credential."""

    @abc.abstractmethod
    def generate_video(self, request: VideoRequest) -> VideoOutcome:
        """Produce a shot, reuse a valid cached one, or raise.

        Must create **at most one** provider task per call. Implementations may take
        additional keyword arguments with defaults; the abstract signature states the
        minimum contract every video provider owes its caller.
        """

    @abc.abstractmethod
    def receipt(self, asset: Optional[VideoAsset] = None) -> VideoReceipt:
        """Full provenance for a produced shot."""