"""MiniMax M Plan video generation, with a one-task-per-attempt guarantee.

The invariant this module exists to protect
-------------------------------------------
::

    ONE GENERATION ATTEMPT = AT MOST ONE PROVIDER TASK

Video is asynchronous and billable at task creation. So a poll timeout, a
transient 5xx, a process restart or a failed download must never lead to a second
``create``. Each of those is a **recovery** problem, and the recovery is always
"ask the same task again" or "fetch the same result again".

The lifecycle
-------------
::

    validate locally        zero cost, catches every documented rule
    build the fingerprint
    check the cache          a hit needs no billing and no network
    authorize(modality="video")
    write a STARTED attempt record
    CREATE exactly one task  <- the only billable step
    persist the raw task id privately, before the first poll
    poll THAT task to a terminal state
    download THAT result, retrying the same URL on failure
    QC, canonical output, immutable receipt
    register the asset, only once the receipt exists

Restart recovery
----------------
The raw task id lives in private runtime state. On restart the provider reads it
and resumes polling **the same task**. It never re-authorises and never creates.

Transport
---------
The documented public H3 API via :mod:`contentops.media.h3_transport`. The
official ``mmx`` CLI is **not** used for generation, because it cannot reliably
express the required resolution behaviour; it remains useful for ``auth``,
``status``, ``quota``, research and diagnostics.

Billing
-------
``billing_mode=subscription``, ``allow_payg=False``, ``allow_credit_pack=False``,
``credential_class=SUBSCRIPTION``. ``modality="video"`` requires the weekly
window only; video does not draw the 5-hour window. All four paid balances must be
exactly zero, because M Plan falls through to Credit Packs once included quota is
exhausted and that is not authorised spend.

Evidence
--------
A generated shot is support-only: ``GENERATED_VIDEO``, ``generated=True``,
``evidence_capable=False``, and a receipt reference is mandatory. H3 may support a
hook, a hero visual, a concept, a metaphor, a transition or an unrecordable scene.
It may never prove a benchmark, a test result, an analytics metric, a UI state, a
customer outcome, source code or a real product demo.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from contentops.media.attempts import (  # noqa: E402
    STATUS_FAILED,
    AttemptRecordError,
    GenerationAttemptRecord,
    append_reuse_event,
    load_attempt_record,
)
from contentops.media.billing_guard import BillingGuard  # noqa: E402
from contentops.media.credentials import CredentialBinding, ResolvedCredential  # noqa: E402
from contentops.media.fingerprint import sha256_file, sha256_text  # noqa: E402
from contentops.media.h3_prompt import (  # noqa: E402
    PROMPT_SKILL_COMMIT,
    PROMPT_SKILL_REPO,
)
from contentops.media.h3_transport import (  # noqa: E402
    H3Transport,
    TaskPollResult,
    TransportError,
    UnknownTaskState,
    build_content_array,
)
from contentops.media.image_contract import (  # noqa: E402
    AssetKind,
    AssetRegistry,
    EvidenceUse,
    register_asset,
)
from contentops.media.mplan_identity import (  # noqa: E402
    ALLOW_CREDIT_PACK,
    ALLOW_PAYG,
    BILLING_MODE,
    MAX_ATTEMPTS,
    PLAN,
    PRODUCT,
    PROVIDER_NAME,
)
from contentops.media.transport import load_sidecar, verify_output, write_sidecar  # noqa: E402
from contentops.media.video_contract import (  # noqa: E402
    AudioPolicy,
    VideoAsset,
    VideoOutcome,
    VideoProvider,
    VideoReceipt,
    VideoRequest,
    VideoTaskState,
    build_human_review_package,
)
from contentops.media.video_qc import technical_video_qc  # noqa: E402
from contentops.media.video_validation import (  # noqa: E402
    RequestRejected,
    ValidatedH3Request,
    validate_h3_request,
)

__all__ = [
    "DEFAULT_H3_MODEL",
    "DEFAULT_RESOLUTION",
    "H3_API_SCHEMA_VERSION",
    "SIDECAR_SUFFIX",
    "VideoAttemptState",
    "MiniMaxMPlanVideoProvider",
    "hash_task_id",
    "receipt_to_dict",
    "video_fingerprint",
]

DEFAULT_H3_MODEL = "MiniMax-H3"
DEFAULT_RESOLUTION = "768P"
SIDECAR_SUFFIX = ".receipt.json"
VIDEO_SCHEMA = "contentops.video-receipt/v1"

#: Written next to the shot so the Founder's review sheet exists before it is
#: needed, rather than being reconstructed from a receipt after the fact.
REVIEW_SUFFIX = ".human-review.json"

#: The documented API generation this client speaks. Recorded on every receipt
#: because ``/v1`` and ``/v2`` differ in path, poll shape and model set, and a
#: receipt that cannot say which one produced a shot is not reproducible evidence.
H3_API_SCHEMA_VERSION = "v2"

#: Where private, non-committed task state lives. The raw provider task id is
#: operationally necessary for resuming a poll, so it is kept here and nowhere else.
PRIVATE_STATE_DIRNAME = "task-state"
PRIVATE_STATE_FILENAME = "task.json"


def hash_task_id(task_id: str, salt: Optional[str] = None) -> str:
    """Salted hash of a provider task id, safe for a public receipt.

    A plain hash of a numeric id would be trivially reversible by enumeration, so
    a per-receipt random salt is used. The salt is discarded, which makes the hash
    verifiable for equality but not reversible to the id.
    """
    if not task_id:
        raise ValueError("cannot hash an empty task id")
    used_salt = salt if salt is not None else secrets.token_hex(16)
    digest = hashlib.sha256(f"{used_salt}:{task_id}".encode("utf-8")).hexdigest()
    return f"sha256:{digest[:32]}"


def _reference_key_entries(reference_hashes: Optional[List[Any]]) -> List[Dict[str, str]]:
    """Normalise reference hashes into ordered ``{role, sha256}`` entries.

    Accepts bare hash strings as positional ``reference_image`` entries, so an
    older caller passing a flat list still gets a stable key rather than a crash.
    """
    entries: List[Dict[str, str]] = []
    for value in reference_hashes or []:
        if isinstance(value, str):
            entries.append({"role": "reference_image", "sha256": value})
        else:
            entries.append({
                "role": str(value.get("role")),
                "sha256": str(value.get("sha256")),
            })
    return entries


def video_fingerprint(
    *,
    provider: str,
    product: str,
    plan: str,
    model: str,
    mode: str,
    compiled_prompt: str,
    duration_s: int,
    resolution: str,
    ratio: str,
    reference_hashes: Optional[List[Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    """Stable digest of every input that can change the produced footage.

    The **compiled** prompt is hashed, not the operator's raw intent: two intents
    can compile to the same prompt, and the same intent can compile to different
    prompts. Hashing the intent would make the cache key lie in both directions.

    References are keyed by **role and position**, never as a sorted bag of
    hashes. For ``FL2VA`` swapping the first and last frame requests the opposite
    transition, and a sorted bag would give both the same key — so a caller could
    be handed the previous shot's video and receipt for a reversed request. Order
    and role are part of the request, so they are part of the key.

    ``reference_hashes`` accepts either bare hash strings (treated as positional
    reference images, in order) or ``{"role": ..., "sha256": ...}`` mappings.
    """
    payload: Dict[str, Any] = {
        "provider": provider,
        "product": product,
        "plan": plan,
        "model": model,
        "mode": mode,
        "compiled_prompt_sha256": sha256_text(compiled_prompt),
        "duration_s": int(duration_s),
        "resolution": resolution,
        "ratio": ratio,
        # Ordered, not sorted: role and position change what gets generated.
        "references": _reference_key_entries(reference_hashes),
    }
    if extra:
        payload["extra"] = {str(k): str(v) for k, v in sorted(extra.items())}
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def reference_fingerprint_entries(
    validated: "ValidatedH3Request",
) -> List[Dict[str, str]]:
    """Hash every reference with its role and position preserved.

    One list, one order, matching how the request is built. Keeping this beside the
    fingerprint is what stops the cache key from silently forgetting that
    ``first_frame`` and ``last_frame`` are different jobs.
    """
    entries: List[Dict[str, str]] = []
    if validated.first_frame is not None:
        entries.append({"role": "first_frame", "sha256": sha256_file(validated.first_frame)})
    if validated.last_frame is not None:
        entries.append({"role": "last_frame", "sha256": sha256_file(validated.last_frame)})
    for path in validated.reference_images:
        entries.append({"role": "reference_image", "sha256": sha256_file(path)})
    for path in validated.reference_videos:
        entries.append({"role": "reference_video", "sha256": sha256_file(path)})
    for path in validated.reference_audio:
        entries.append({"role": "reference_audio", "sha256": sha256_file(path)})
    return entries


@dataclass
class VideoAttemptState:
    """Private, non-committed task state.

    Held outside the attempt record because the raw provider task id must never
    reach a sanitised record, a receipt or a commit.
    """

    fingerprint: str
    task_id: str
    attempt_id: str
    created_at: float = field(default_factory=time.time)
    download_url: Optional[str] = None
    state: Optional[str] = None
    #: Which generation attempt paid for this task. Carried so a receipt written
    #: after a restart still says ``attempt=2`` when attempt 2 is what was billed.
    attempt: int = 1
    #: Declared before the original create. Carried so the resumed receipt records
    #: the budget the task was actually authorised against rather than nothing.
    quota_budget: Optional[str] = None
    test_objective: Optional[str] = None
    #: Quota as it stood **before** the task was created, read from the same
    #: pre-flight that authorised it.
    #:
    #: This must be carried, not re-read on resume. By the time a restart happens
    #: the task has already consumed its weekly entitlement, so re-reading would
    #: produce a "before" value that is really an "after" value — and the receipt
    #: would report a delta of zero, erasing the exact cost the receipt exists to
    #: record.
    quota_before: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "task_id": self.task_id,
            "attempt_id": self.attempt_id,
            "created_at": self.created_at,
            "download_url": self.download_url,
            "state": self.state,
            "attempt": self.attempt,
            "quota_budget": self.quota_budget,
            "test_objective": self.test_objective,
            "quota_before": self.quota_before,
            "warning": "private runtime state; never commit. The public receipt "
            "stores only a salted hash.",
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "VideoAttemptState":
        return cls(
            fingerprint=str(payload["fingerprint"]),
            task_id=str(payload["task_id"]),
            attempt_id=str(payload.get("attempt_id") or ""),
            created_at=float(payload.get("created_at") or 0.0),
            download_url=payload.get("download_url"),
            state=payload.get("state"),
            attempt=int(payload.get("attempt") or 1),
            quota_budget=payload.get("quota_budget"),
            test_objective=payload.get("test_objective"),
            quota_before=payload.get("quota_before"),
        )


class MiniMaxMPlanVideoProvider(VideoProvider):
    """Video provider for the MiniMax M Plan Explore subscription."""

    name = PROVIDER_NAME

    def __init__(
        self,
        *,
        guard: BillingGuard,
        work_dir: Path,
        transport: Optional[H3Transport] = None,
        model: str = DEFAULT_H3_MODEL,
        resolution: str = DEFAULT_RESOLUTION,
        transport_credential: Optional[ResolvedCredential] = None,
        poll_interval_s: float = 10.0,
        max_polls: int = 180,
        download_min_bytes: int = 1024,
        registry: Optional[AssetRegistry] = None,
    ) -> None:
        self._guard = guard
        self._work_dir = Path(work_dir)
        self._model = model
        self._resolution = resolution
        self._poll_interval_s = poll_interval_s
        self._max_polls = max_polls
        self._download_min_bytes = download_min_bytes
        # One resolved credential, bound once. The provider has no resolver of its
        # own, so the gate and the transport cannot disagree about the key.
        self._binding = CredentialBinding(transport_credential)
        self._transport = transport
        self._receipts: List[VideoReceipt] = []
        # The M3 registry is the canonical evidence boundary. This provider does
        # not redefine it; it registers into it as VISUAL_SUPPORT only.
        self.registry = registry if registry is not None else AssetRegistry()
        #: How many billable tasks this provider instance created. Tests assert
        #: on this to prove no hidden duplicate creation.
        self.create_count = 0

    # -- provider contract -------------------------------------------------

    def capabilities(self) -> Dict[str, Any]:
        return {
            "provider": PROVIDER_NAME,
            "transport": "documented_public_api",
            "api_base": "https://api.minimax.io",
            "endpoints": ["/v2/video_generation", "/v2/query/video_generation/{task_id}"],
            "video": {
                "supported": True,
                "models": ["MiniMax-H3", "MiniMax-H3-Max"],
                "default_model": self._model,
                "default_resolution": self._resolution,
                "modes": ["T2VA", "I2VA", "FL2VA", "L2VA", "Ref2VA"],
                "durations": {"MiniMax-H3": [4, 15], "MiniMax-H3-Max": [5, 15]},
                "evidence": "M2.0 T2VA receipt, Issue #4",
                "audio": "native stereo audio is generated even when not requested",
                "real_reference_mode_evidence": "not yet verified",
            },
            # This provider is video-only. Speech and image have their own providers,
            # both merged: speech in PR #24, image in PR #25.
            "speech": {"supported": False, "owner": "MiniMaxMPlanSpeechProvider (PR #24)"},
            "image": {"supported": False, "owner": "MiniMaxMPlanImageProvider (PR #25)"},
            "evidence_capable": False,
            "prompt_skill": {
                "repo": PROMPT_SKILL_REPO,
                "commit": PROMPT_SKILL_COMMIT,
            },
        }

    def health(self) -> Dict[str, Any]:
        verdict = self._guard.evaluate(modality="video")
        return {
            "reachable": self._transport is not None,
            "transport": "documented_public_api",
            "credential_class": verdict.credential_class,
            "billing_verdict": verdict.verdict,
            "billing_reasons": verdict.reasons,
            "quota_window": "weekly",
            "create_count": self.create_count,
        }

    def quota(self):
        snapshot = self._guard.read_quota()
        if snapshot is None:
            from contentops.media.contract import BillingBlocked

            raise BillingBlocked(
                "BLOCKED_BILLING_SOURCE_UNCERTAIN",
                ["included plan usage could not be read"],
            )
        return snapshot

    def registered_assets(self) -> List[Any]:
        """Everything registered by this provider, for inspection in tests."""
        return self.registry.all()

    def receipt(self, asset: Optional[VideoAsset] = None) -> VideoReceipt:
        """Return the receipt for a produced shot.

        Raises:
            RuntimeError: if nothing has been produced. A placeholder receipt would
                be fabricated provenance.
        """
        if asset is not None:
            for candidate in self._receipts:
                if candidate.output_sha256 == asset.sha256:
                    return candidate
        if self._receipts:
            return self._receipts[-1]
        raise RuntimeError("no receipt available; call generate_video() first")

    def credential_metadata(self) -> Dict[str, str]:
        return self._binding.safe_metadata()

    # -- video -------------------------------------------------------------

    def generate_video(
        self,
        request: VideoRequest,
        *,
        retry_reason: Optional[str] = None,
        attempt: int = 1,
        retry_from: Optional[Path] = None,
        quota_budget: Optional[str] = None,
        test_objective: Optional[str] = None,
    ) -> VideoOutcome:
        """Produce a shot, reuse a valid cached one, or raise.

        Args:
            quota_budget: an explicit statement of what weekly quota this run is
                allowed to spend, e.g. ``"7pp"``. Mandatory for any call that could
                create a task. A video task is the single most expensive operation
                in ContentOps, so the decision to spend must be written down before
                the gate is consulted, not inferred afterwards from a receipt.
            test_objective: what this generation is meant to prove. Recorded
                alongside the budget so a task can never be created without a
                stated reason to exist.

        Raises:
            RequestRejected: the request breaks a documented rule. Raised before
                any billing read or task creation, so it costs nothing.
            RuntimeError: no budget, a retry without changed inputs, or a failed
                generation.
            TransportError: the provider could not be reached. Never a reason to
                create another task.
        """
        # 1. Local validation. Free, and it catches every documented rule.
        validated = self._validate(request)

        # 2. Fingerprint over the compiled prompt, not the raw intent. References keep
        #    their role and order, so a reversed first/last frame is a different key.
        reference_entries = reference_fingerprint_entries(validated)
        reference_hashes = [entry["sha256"] for entry in reference_entries]
        fingerprint = video_fingerprint(
            provider=PROVIDER_NAME,
            product=PRODUCT,
            plan=PLAN,
            model=validated.model,
            mode=validated.mode,
            compiled_prompt=validated.prompt,
            duration_s=validated.duration_s,
            resolution=validated.resolution,
            ratio=validated.ratio,
            reference_hashes=reference_entries,
            extra=validated.extra,
        )

        # 3. Retry evidence, before any billing or provider call.
        self._validate_attempt(attempt, retry_reason, fingerprint, retry_from, quota_budget)

        self._work_dir.mkdir(parents=True, exist_ok=True)
        canonical_path = self._work_dir / f"shot-{fingerprint[:16]}.mp4"
        sidecar_path = canonical_path.with_name(canonical_path.name + SIDECAR_SUFFIX)

        # 4. Cache, before the billing gate.
        if not request.force:
            cached = self._reuse(
                canonical_path=canonical_path,
                sidecar_path=sidecar_path,
                fingerprint=fingerprint,
                validated=validated,
                # The caller's current choice wins. The audio policy is not part of
                # the fingerprint, so restoring the original one here would silently
                # hand back a KEEP asset to someone who just asked for MUTE.
                audio_policy=request.audio_policy,
            )
            if cached is not None:
                return cached

        # 5. Resume an interrupted attempt instead of paying twice.
        resumed = self._resume_if_possible(
            fingerprint,
            canonical_path,
            validated,
            reference_hashes=reference_hashes,
            audio_policy=request.audio_policy,
            sidecar_path=sidecar_path,
        )
        if resumed is not None:
            return resumed

        # 6. Only now does billing matter.
        #
        # The budget check sits immediately before the gate, not at the top of the
        # function: a cache hit and a resume both cost nothing, so a run that
        # spends no quota must not be forced to declare a budget for it.
        self._require_budget(quota_budget, test_objective)
        preflight = self._guard.authorize(modality="video")
        quota_before = preflight.quota

        # 7. Remove stale output so a fresh mtime is meaningful.
        for stale in (canonical_path, sidecar_path):
            if stale.exists():
                stale.unlink()

        attempt_record = GenerationAttemptRecord(
            provider=PROVIDER_NAME,
            modality="video",
            fingerprint=fingerprint,
            attempt_number=attempt,
        )
        attempt_record.write(self._work_dir)

        # 8. Exactly one billable call.
        transport = self._require_transport()
        content = build_content_array(
            prompt=validated.prompt,
            first_frame=validated.first_frame,
            last_frame=validated.last_frame,
            reference_images=validated.reference_images,
            reference_videos=validated.reference_videos,
            reference_audio=validated.reference_audio,
        )
        started = time.time()
        try:
            task_id = transport.create_task(
                model=validated.model,
                content=content,
                duration_s=validated.duration_s,
                resolution=validated.resolution,
                ratio=validated.ratio,
                extra=validated.extra or None,
            )
        except TransportError as exc:
            attempt_record.mark_failed("task_creation_failed", str(exc)).write(self._work_dir)
            raise
        self.create_count += 1

        task_hash = hash_task_id(task_id)
        attempt_record.task_created = True
        attempt_record.task_ref_hash = task_hash
        attempt_record.write(self._work_dir, forbid_values=[task_id])

        # 9. Persist the raw task id privately, BEFORE the first poll, so a crash
        #    here cannot lose the only handle on a task we already paid for.
        state = VideoAttemptState(
            fingerprint=fingerprint,
            task_id=task_id,
            attempt_id=attempt_record.attempt_id,
            attempt=attempt,
            quota_budget=quota_budget,
            test_objective=test_objective,
            quota_before=_snapshot_to_dict(quota_before),
        )
        self._write_private_state(state)

        # 10. Poll THAT task to a terminal state.
        try:
            poll = self._poll_to_terminal(transport, state)
        except UnknownTaskState as exc:
            attempt_record.provider_state = "unknown"
            attempt_record.mark_failed("unknown_provider_state", str(exc)).write(
                self._work_dir, forbid_values=[task_id]
            )
            raise
        except TransportError as exc:
            # A poll failure is not a generation failure. The task id is on disk,
            # so the next run resumes this same task.
            attempt_record.mark_failed("poll_failed", str(exc)).write(
                self._work_dir, forbid_values=[task_id]
            )
            raise

        attempt_record.provider_state = poll.state
        if poll.is_failure:
            reason = f"provider reported {poll.state}: {poll.error or 'no detail'}"
            attempt_record.mark_failed("provider_terminal_failure", reason).write(
                self._work_dir, forbid_values=[task_id]
            )
            state.state = poll.state
            self._write_private_state(state)
            raise RuntimeError(
                f"video generation reached terminal state {poll.state!r} on "
                f"attempt {attempt}/{MAX_ATTEMPTS}. A retry requires a named "
                f"reason and a changed prompt, mode, duration, resolution, ratio "
                f"or reference."
            )

        if not poll.download_url:
            attempt_record.mark_failed("succeeded_without_url", "no content.url").write(
                self._work_dir, forbid_values=[task_id]
            )
            raise TransportError(
                "the task succeeded but returned no content.url, so there is "
                "nothing to download. Not creating another task."
            )

        # 11. Download THAT result.
        state.download_url = poll.download_url
        state.state = poll.state
        self._write_private_state(state)
        try:
            transport.download_result(poll.download_url, canonical_path)
            verify_output(canonical_path, not_before=started, min_bytes=self._download_min_bytes)
        except Exception as exc:  # noqa: BLE001
            attempt_record.mark_failed("download_failed", str(exc)).write(
                self._work_dir, forbid_values=[task_id]
            )
            raise

        # 12. QC, receipt, then registration.
        outcome = self._finish(
            validated=validated,
            request=request,
            audio_policy=request.audio_policy,
            fingerprint=fingerprint,
            preflight=preflight,
            quota_before=quota_before,
            canonical_path=canonical_path,
            sidecar_path=sidecar_path,
            reference_hashes=reference_hashes,
            task_hash=task_hash,
            poll=poll,
            attempt=attempt,
            retry_reason=retry_reason,
            quota_budget=quota_budget,
            test_objective=test_objective,
        )
        attempt_record.mark_succeeded(outcome.asset.sha256, str(sidecar_path)).write(
            self._work_dir, forbid_values=[task_id]
        )
        self._clear_private_state(fingerprint)
        return outcome

    # -- internals ---------------------------------------------------------

    def _validate(self, request: VideoRequest) -> ValidatedH3Request:
        """Run every documented rule locally, before billing and before create."""
        try:
            return validate_h3_request(
                model=request.model,
                mode=request.mode,
                duration_s=request.duration_s,
                resolution=request.resolution,
                ratio=request.ratio,
                prompt=request.compiled_prompt,
                first_frame=request.first_frame,
                last_frame=request.last_frame,
                reference_images=tuple(request.reference_images),
                reference_videos=tuple(request.reference_videos),
                reference_audio=tuple(request.reference_audio),
                extra=dict(request.extra) if request.extra else None,
                audio_policy=request.audio_policy,
            )
        except RequestRejected:
            raise
        except Exception as exc:  # noqa: BLE001
            raise RequestRejected(f"request could not be validated: {exc}") from exc

    def _require_transport(self) -> H3Transport:
        transport = self._transport
        if transport is None:
            raise TransportError(
                "no H3 transport configured. Build one with the bound credential. "
                "The official mmx CLI is not used for generation because it "
                "cannot reliably express the required resolution."
            )
        # Fail closed before spending anything if no credential is bound.
        self._binding.require_env()
        return transport

    def _require_budget(self, quota_budget: Optional[str], test_objective: Optional[str]) -> None:
        """Refuse a billable run that has not declared what it may spend.

        Placed immediately before :meth:`BillingGuard.authorize` so that a cache
        hit and a restart-resume, which spend nothing, are never forced to declare
        a budget. Everything after this point can create exactly one paid task.
        """
        if not (quota_budget or "").strip():
            raise RuntimeError(
                "refusing to create a billable video task without an explicit "
                "quota_budget. Video counts only against the weekly window and is "
                "the most expensive call ContentOps makes; the decision to spend "
                "must be written down first, not reconstructed from the receipt "
                "afterwards. Pass quota_budget= (e.g. '7pp') and test_objective=."
            )
        if not (test_objective or "").strip():
            raise RuntimeError(
                "refusing to create a billable video task without a test_objective. "
                "State what this generation is meant to prove, so a task can never "
                "exist without a recorded reason to exist."
            )

    def _validate_attempt(
        self,
        attempt: int,
        retry_reason: Optional[str],
        fingerprint: str,
        retry_from: Optional[Path],
        quota_budget: Optional[str],
    ) -> Optional[GenerationAttemptRecord]:
        """Refuse a retry that is only a note, before any billing or provider call.

        Attempt 2 is a **new paid generation**, so it requires a durable record of
        a terminal FAILED attempt 1, a named reason, a changed fingerprint, and an
        explicit quota budget.

        A running task, a poll failure, a download failure and a local disk failure
        are **not** retryable generation reasons. Those are recovered by resuming
        the same task, which :meth:`_resume_if_possible` does.
        """
        if attempt <= 1:
            return None
        if attempt > MAX_ATTEMPTS:
            raise RuntimeError(
                f"attempt {attempt} exceeds the maximum of {MAX_ATTEMPTS}"
            )
        if not (retry_reason or "").strip():
            raise RuntimeError(
                f"attempt {attempt} requires a named failure reason; refusing to "
                f"retry blindly. A second task is a second bill."
            )
        if not (quota_budget or "").strip():
            raise RuntimeError(
                f"attempt {attempt} requires an explicit quota_budget, because a "
                f"new generation task costs real weekly entitlement."
            )
        if retry_from is None:
            raise RuntimeError(
                "attempt 2 requires --retry-from pointing at the attempt record of "
                "a terminally failed first attempt. A reason alone is not evidence."
            )
        try:
            record = load_attempt_record(Path(retry_from))
        except AttemptRecordError as exc:
            raise RuntimeError(f"retry record is not usable: {exc}") from exc

        if record.provider != PROVIDER_NAME:
            raise RuntimeError(
                f"retry record provider {record.provider!r} does not match {PROVIDER_NAME!r}"
            )
        if record.modality != "video":
            raise RuntimeError(f"retry record modality {record.modality!r} is not 'video'")
        if record.attempt_number != 1:
            raise RuntimeError(
                f"retry record must describe attempt 1, got {record.attempt_number}"
            )
        if record.status != STATUS_FAILED:
            # A RUNNING task is not a failure. Retrying it would pay twice for one
            # generation.
            raise RuntimeError(
                f"retry record status is {record.status!r} with provider state "
                f"{record.provider_state!r}; only a TERMINAL FAILED first attempt "
                f"may be retried. A running task is resumed, not regenerated."
            )
        # Status alone is NOT evidence of a terminal failure. A poll timeout, a
        # transient poll 5xx and a download failure are all recorded as FAILED too,
        # because from this record's point of view the call did not succeed. But in
        # each of those cases the provider task may still exist and still be
        # resumable from private state, so a changed fingerprint would bypass that
        # state and create a **second billable task** for one logical generation.
        #
        # Only a provider-reported terminal failure means the generation is gone for
        # good. Everything else is recovery, handled by resuming the same task.
        if not VideoTaskState.is_failure(record.provider_state):
            raise RuntimeError(
                f"retry record failed locally with failure_class "
                f"{record.failure_class!r} and provider state "
                f"{record.provider_state!r}, which is not a terminal provider "
                f"failure. The original task may still be running and resumable, so "
                f"creating another one would pay twice for one generation. Resume "
                f"the existing task instead, or retry only after the provider has "
                f"reported a terminal state."
            )
        if record.fingerprint == fingerprint:
            raise RuntimeError(
                "attempt 2 must change a generation input (compiled prompt, "
                "mode, duration, resolution, ratio or references). The "
                f"fingerprint is unchanged ({fingerprint[:16]})."
            )
        return record

    # -- private task state -------------------------------------------------

    def _private_state_path(self, fingerprint: str) -> Path:
        return self._work_dir / PRIVATE_STATE_DIRNAME / f"{fingerprint[:16]}.json"

    def _write_private_state(self, state: VideoAttemptState) -> Path:
        target = self._private_state_path(state.fingerprint)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(state.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return target

    def _read_private_state(self, fingerprint: str) -> Optional[VideoAttemptState]:
        target = self._private_state_path(fingerprint)
        if not target.is_file():
            return None
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
            return VideoAttemptState.from_dict(payload)
        except (json.JSONDecodeError, KeyError, OSError):
            return None

    def _clear_private_state(self, fingerprint: str) -> None:
        target = self._private_state_path(fingerprint)
        if target.exists():
            target.unlink()

    def _resume_if_possible(
        self,
        fingerprint: str,
        canonical_path: Path,
        validated: ValidatedH3Request,
        *,
        reference_hashes: List[str],
        audio_policy: str,
        sidecar_path: Path,
    ) -> Optional[VideoOutcome]:
        """Resume a task that already exists instead of paying for another.

        A crash between create and download is the dangerous case: the money is
        already spent, so the only correct action is to find the task we created
        and finish it.

        The receipt written on the resumed path must describe the generation that
        actually happened, so reference hashes, the audio policy and the attempt
        number are carried across the restart rather than defaulted. Defaulting
        them would produce a receipt claiming ``attempt=1`` with no references for
        a shot that was billed as attempt 2 with references.
        """
        state = self._read_private_state(fingerprint)
        if state is None:
            return None
        transport = self._transport
        if transport is None:
            return None

        poll = self._poll_to_terminal(transport, state)
        if not poll.is_success or not poll.download_url:
            # Terminal failure of an existing task: clear the private state and
            # let the caller decide. Creating another task here would be attempt 2
            # without evidence, which is exactly what must not happen silently.
            self._clear_private_state(fingerprint)
            raise RuntimeError(
                f"resuming the existing task reached terminal state "
                f"{poll.state!r}. No new task was created."
            )

        state.download_url = poll.download_url
        state.state = poll.state
        self._write_private_state(state)
        transport.download_result(poll.download_url, canonical_path)
        verify_output(canonical_path, not_before=state.created_at - 1,
                      min_bytes=self._download_min_bytes)

        # The "before" value must come from the pre-flight that authorised the original
        # create, not from a fresh read. The task has already been paid for by now,
        # so reading again would label the post-cost value as pre-cost and make the
        # receipt report a delta of zero.
        preflight_quota = _snapshot_from_dict(state.quota_before)
        outcome = self._finish(
            validated=validated,
            request=None,  # type: ignore[arg-type]
            audio_policy=audio_policy,
            fingerprint=fingerprint,
            preflight=None,  # type: ignore[arg-type]
            quota_before=preflight_quota,
            canonical_path=canonical_path,
            sidecar_path=sidecar_path,
            reference_hashes=reference_hashes,
            task_hash=hash_task_id(state.task_id),
            poll=poll,
            attempt=state.attempt,
            retry_reason=None,
            quota_budget=state.quota_budget,
            test_objective=state.test_objective,
            resumed=True,
        )
        self._clear_private_state(fingerprint)
        return outcome

    def _poll_to_terminal(
        self, transport: H3Transport, state: VideoAttemptState
    ) -> TaskPollResult:
        """Poll one task until it reaches a terminal state.

        Never creates anything. A transport error propagates so the caller can
        record it and resume later.
        """
        for _ in range(self._max_polls):
            poll = transport.poll_task(state.task_id)
            state.state = poll.state
            if poll.is_terminal:
                return poll
            time.sleep(self._poll_interval_s)
        raise TransportError(
            f"task did not reach a terminal state within {self._max_polls} "
            f"polls. The task id is preserved in private state so the next run "
            f"resumes it. No new task was created."
        )

    # -- reuse -------------------------------------------------------------

    def _reuse(
        self,
        *,
        canonical_path: Path,
        sidecar_path: Path,
        fingerprint: str,
        validated: ValidatedH3Request,
        audio_policy: str,
    ) -> Optional[VideoOutcome]:
        """Reuse a cached shot only when its provenance is verifiable."""
        if not canonical_path.is_file():
            return None
        payload = load_sidecar(sidecar_path)
        if not isinstance(payload, dict):
            return None
        for field_name in REQUIRED_VIDEO_RECEIPT_FIELDS:
            if field_name not in payload:
                return None
        for field_name in NON_BLANK_VIDEO_RECEIPT_FIELDS:
            value = payload.get(field_name)
            if not isinstance(value, str) or not value.strip():
                return None
        if payload.get("fingerprint") != fingerprint:
            return None
        if payload.get("generated") is not True or payload.get("evidence_capable") is not False:
            return None
        try:
            actual_sha = sha256_file(canonical_path)
        except OSError:
            return None
        if actual_sha != payload.get("output_sha256"):
            return None

        qc = technical_video_qc(
            canonical_path,
            expected_duration_s=validated.duration_s,
            expected_ratio=validated.ratio if validated.ratio != "adaptive" else None,
        )
        if not qc.approved or qc.width != payload.get("actual_width") or qc.height != payload.get("actual_height"):
            return None

        asset = VideoAsset(
            canonical_path=str(canonical_path),
            container=qc.container or "",
            codec=qc.codec,
            width=int(payload["actual_width"]),
            height=int(payload["actual_height"]),
            duration_s=float(payload.get("actual_duration_s") or qc.duration_s or 0.0),
            fps=qc.fps,
            has_audio=bool(payload.get("audio_stream_present", False)),
            sha256=actual_sha,
            technical_qc=qc.as_dict(),
            audio_policy=audio_policy,
            evidence_capable=False,
            generated=True,
        )
        receipt = _receipt_from_payload(
            asset=asset, payload=payload, audio_policy=audio_policy
        )
        self._remember_receipt(receipt)
        append_reuse_event(
            self._work_dir,
            {
                "event": "CACHE_REUSE",
                "modality": "video",
                "fingerprint": fingerprint,
                "asset_sha256": actual_sha,
                "provider_call": False,
                "billing_call": False,
                # Recorded because the reuse may have changed the handling decision
                # without changing the bytes. The immutable receipt on disk keeps its
                # original generation-time value; this says what the caller actually
                # got, so a later reader is not misled by either value alone.
                "audio_policy": audio_policy,
                "receipt_audio_policy_at_generation": payload.get("audio_policy"),
            },
        )
        return VideoOutcome(asset=asset, receipt=receipt, reused=True)

    # -- finishing ---------------------------------------------------------

    def _finish(
        self,
        *,
        validated: ValidatedH3Request,
        request: Optional[VideoRequest],
        audio_policy: str,
        fingerprint: str,
        preflight: Any,
        quota_before: Any,
        canonical_path: Path,
        sidecar_path: Path,
        reference_hashes: List[str],
        task_hash: str,
        poll: TaskPollResult,
        attempt: int,
        retry_reason: Optional[str],
        quota_budget: Optional[str] = None,
        test_objective: Optional[str] = None,
        resumed: bool = False,
    ) -> VideoOutcome:
        """QC, write the immutable receipt, and only then register the asset.

        The order is deliberate: an asset whose receipt does not exist must not be
        registrable, because provenance is what distinguishes a generated shot
        from an invented one.
        """
        qc = technical_video_qc(
            canonical_path,
            expected_duration_s=validated.duration_s,
            expected_ratio=validated.ratio if validated.ratio != "adaptive" else None,
            expected_resolution=validated.resolution,
            audio_policy=audio_policy,
        )
        if not qc.approved:
            raise RuntimeError(
                "the generated shot failed technical QC and will not be recorded "
                f"as usable: {'; '.join(qc.reasons)}"
            )

        asset = VideoAsset(
            canonical_path=str(canonical_path),
            container=qc.container or "",
            codec=qc.codec,
            width=int(qc.width or 0),
            height=int(qc.height or 0),
            duration_s=float(qc.duration_s or 0.0),
            fps=qc.fps,
            has_audio=bool(qc.has_audio),
            sha256=sha256_file(canonical_path),
            technical_qc=qc.as_dict(),
            audio_policy=audio_policy,
            evidence_capable=False,
            generated=True,
        )

        quota_after = None
        post_state: Dict[str, Any] = {}
        try:
            quota_after = self._guard.read_quota()
            post_state["quota_after"] = {
                "bucket": quota_after.bucket if quota_after else None,
                "weekly_remaining_percent": (
                    quota_after.weekly_remaining_percent if quota_after else None
                ),
            }
        except Exception as exc:  # noqa: BLE001
            post_state["quota_after"] = {"error": type(exc).__name__}

        verdict = preflight.verdict if preflight is not None else "RESUMED_NO_PREFLIGHT"
        reasons = list(preflight.reasons) if preflight is not None else [
            "resumed an existing task after a restart; no second authorisation"
        ]

        receipt = VideoReceipt(
            provider=PROVIDER_NAME,
            product=PRODUCT,
            plan=PLAN,
            billing_mode=BILLING_MODE,
            payg_allowed=ALLOW_PAYG,
            credit_pack_allowed=ALLOW_CREDIT_PACK,
            credential_class=self._binding.safe_metadata()["credential_class"],
            credential_source=self._binding.safe_metadata()["credential_source"],
            transport="documented_public_api",
            api_schema_version=H3_API_SCHEMA_VERSION,
            model=validated.model,
            mode=validated.mode,
            compiled_prompt_sha256=sha256_text(validated.prompt),
            prompt_skill_repo=PROMPT_SKILL_REPO,
            prompt_skill_commit=PROMPT_SKILL_COMMIT,
            reference_asset_sha256=list(reference_hashes),
            requested_duration_s=validated.duration_s,
            actual_duration_s=asset.duration_s,
            requested_resolution=validated.resolution,
            actual_width=asset.width,
            actual_height=asset.height,
            requested_ratio=validated.ratio,
            actual_ratio=asset.aspect_ratio,
            extra=dict(validated.extra),
            canonical_path=asset.canonical_path,
            output_sha256=asset.sha256,
            fingerprint=fingerprint,
            task_created=True,
            task_ref_hash=task_hash,
            billing_guard_verdict=verdict,
            billing_guard_reasons=reasons,
            quota_before=quota_before,
            quota_after=quota_after,
            technical_qc=qc.as_dict(),
            audio_policy=asset.audio_policy,
            audio_stream_present=asset.has_audio,
            attempt=attempt,
            retry_reason=retry_reason,
            quota_budget=quota_budget,
            test_objective=test_objective,
fallback={},
        production_ready=False,
        human_review="PENDING_FOUNDER_REVIEW",
            generated=True,
            evidence_capable=False,
            post_generation_billing_state=post_state,
        )

        # Receipt first, then the review sheet, then registration. A video whose
        # receipt failed to write must not enter the registry, and a registered shot
        # must have somewhere for the Founder to record a verdict.
        write_sidecar(sidecar_path, receipt_to_dict(receipt))
        if not sidecar_path.is_file():
            raise RuntimeError(
                "the immutable receipt could not be written, so the shot is not "
                "registered. A generated asset without provenance is exactly "
                "what the evidence boundary exists to prevent."
            )

        review_path = canonical_path.with_name(canonical_path.name + REVIEW_SUFFIX)
        write_sidecar(
            review_path,
            build_human_review_package(
                asset=asset, receipt=receipt, mode=validated.mode
            ),
        )

        # Register as a support visual only. GENERATED_VIDEO cannot carry a claim.
        register_asset(
            self.registry,
            asset_id=fingerprint[:16],
            kind=AssetKind.GENERATED_VIDEO,
            path=asset.canonical_path,
            evidence_use=EvidenceUse.VISUAL_SUPPORT,
            receipt_ref=sidecar_path.name,
            sha256=asset.sha256,
        )

        self._remember_receipt(receipt)
        return VideoOutcome(asset=asset, receipt=receipt, reused=resumed)

    def _remember_receipt(self, receipt: VideoReceipt) -> None:
        for existing in self._receipts:
            if existing.fingerprint == receipt.fingerprint:
                return
        self._receipts.append(receipt)


def _receipt_from_payload(
    *,
    asset: VideoAsset,
    payload: Dict[str, Any],
    audio_policy: Optional[str] = None,
) -> VideoReceipt:
    """Rebuild the ORIGINAL generation receipt from the immutable sidecar.

    ``quota_before``, ``quota_after`` and the original attempt number must survive,
    or the evidence that the shot came out of plan entitlement is lost on the
    first reuse.

    ``audio_policy`` is the one field a reuse may legitimately update. It is a
    downstream handling decision rather than a generation input — it is not in the
    fingerprint and it does not change the bytes — so the caller may legitimately
    change their mind. The on-disk receipt keeps its original value; this restores
    what the current caller actually asked for.
    """
    from contentops.media.contract import QuotaSnapshot

    def snapshot(value: Any):
        if not isinstance(value, dict):
            return None
        return QuotaSnapshot(
            bucket=value.get("bucket"),
            interval_remaining_percent=value.get("interval_remaining_percent"),
            weekly_remaining_percent=value.get("weekly_remaining_percent"),
            modality_breakdown=value.get("modality_breakdown") or {},
        )

    return VideoReceipt(
        provider=str(payload["provider"]),
        product=str(payload["product"]),
        plan=str(payload["plan"]),
        billing_mode=str(payload["billing_mode"]),
        payg_allowed=bool(payload.get("payg_allowed", False)),
        credit_pack_allowed=bool(payload.get("credit_pack_allowed", False)),
        credential_class=str(payload.get("credential_class") or "UNKNOWN"),
        credential_source=str(payload.get("credential_source") or "UNBOUND"),
        transport=str(payload.get("transport") or "documented_public_api"),
        api_schema_version=payload.get("api_schema_version"),
        model=str(payload["model"]),
        mode=str(payload["mode"]),
        compiled_prompt_sha256=str(payload["compiled_prompt_sha256"]),
        prompt_skill_repo=str(payload.get("prompt_skill_repo") or ""),
        prompt_skill_commit=str(payload.get("prompt_skill_commit") or ""),
        reference_asset_sha256=list(payload.get("reference_asset_sha256") or []),
        requested_duration_s=int(payload.get("requested_duration_s") or 0),
        actual_duration_s=float(payload.get("actual_duration_s") or 0.0),
        requested_resolution=str(payload.get("requested_resolution") or ""),
        actual_width=int(payload.get("actual_width") or asset.width),
        actual_height=int(payload.get("actual_height") or asset.height),
        requested_ratio=payload.get("requested_ratio"),
        actual_ratio=payload.get("actual_ratio"),
        extra=dict(payload.get("extra") or {}),
        canonical_path=asset.canonical_path,
        output_sha256=asset.sha256,
        fingerprint=str(payload["fingerprint"]),
        task_created=bool(payload.get("task_created", True)),
        task_ref_hash=str(payload.get("task_ref_hash") or ""),
        billing_guard_verdict=str(payload.get("billing_guard_verdict") or ""),
        billing_guard_reasons=list(payload.get("billing_guard_reasons") or []),
        quota_before=snapshot(payload.get("quota_before")),
        quota_after=snapshot(payload.get("quota_after")),
        technical_qc=dict(payload.get("technical_qc") or {}),
        audio_policy=audio_policy or str(payload.get("audio_policy") or AudioPolicy.REPLACE),
        audio_stream_present=bool(payload.get("audio_stream_present", False)),
attempt=int(payload.get("attempt") or 1),
            retry_reason=payload.get("retry_reason"),
            quota_budget=payload.get("quota_budget"),
            test_objective=payload.get("test_objective"),
            fallback=dict(payload.get("fallback") or {}),
        production_ready=bool(payload.get("production_ready", False)),
        human_review=str(payload.get("human_review") or "PENDING_FOUNDER_REVIEW"),
        generated=True,
        evidence_capable=False,
        post_generation_billing_state=dict(payload.get("post_generation_billing_state") or {}),
    )


def _snapshot_to_dict(snapshot: Any) -> Optional[Dict[str, Any]]:
    if snapshot is None:
        return None
    return {
        "bucket": snapshot.bucket,
        "interval_remaining_percent": snapshot.interval_remaining_percent,
        "weekly_remaining_percent": snapshot.weekly_remaining_percent,
        "modality_breakdown": snapshot.modality_breakdown,
    }


def _snapshot_from_dict(value: Any) -> Any:
    """Rebuild a :class:`QuotaSnapshot` from its serialised form."""
    from contentops.media.contract import QuotaSnapshot

    if not isinstance(value, dict):
        return None
    return QuotaSnapshot(
        bucket=value.get("bucket"),
        interval_remaining_percent=value.get("interval_remaining_percent"),
        weekly_remaining_percent=value.get("weekly_remaining_percent"),
        modality_breakdown=value.get("modality_breakdown") or {},
    )


def receipt_to_dict(receipt: VideoReceipt) -> Dict[str, Any]:
    """Serialise a video receipt.

    Contains the credential **class** and a **salted** task hash. Never the
    credential value, never a raw task id.
    """
    return {
        "schema": VIDEO_SCHEMA,
        "provider": receipt.provider,
        "product": receipt.product,
        "plan": receipt.plan,
        "billing_mode": receipt.billing_mode,
        "payg_allowed": receipt.payg_allowed,
        "credit_pack_allowed": receipt.credit_pack_allowed,
        "credential_class": receipt.credential_class,
        "credential_source": receipt.credential_source,
        "transport": receipt.transport,
        "api_schema_version": receipt.api_schema_version,
        "model": receipt.model,
        "mode": receipt.mode,
        "compiled_prompt_sha256": receipt.compiled_prompt_sha256,
        "prompt_skill_repo": receipt.prompt_skill_repo,
        "prompt_skill_commit": receipt.prompt_skill_commit,
        "reference_asset_sha256": list(receipt.reference_asset_sha256),
        "requested_duration_s": receipt.requested_duration_s,
        "actual_duration_s": receipt.actual_duration_s,
        "requested_resolution": receipt.requested_resolution,
        "actual_width": receipt.actual_width,
        "actual_height": receipt.actual_height,
        "requested_ratio": receipt.requested_ratio,
        "actual_ratio": receipt.actual_ratio,
        "extra": dict(receipt.extra),
        "canonical_path": receipt.canonical_path,
        "output_sha256": receipt.output_sha256,
        "fingerprint": receipt.fingerprint,
        "task_created": receipt.task_created,
        "task_ref_hash": receipt.task_ref_hash,
        "billing_guard_verdict": receipt.billing_guard_verdict,
        "billing_guard_reasons": list(receipt.billing_guard_reasons),
        "quota_before": _snapshot_to_dict(receipt.quota_before),
        "quota_after": _snapshot_to_dict(receipt.quota_after),
        "technical_qc": dict(receipt.technical_qc),
        "audio_policy": receipt.audio_policy,
        "audio_stream_present": receipt.audio_stream_present,
        "attempt": receipt.attempt,
        "retry_reason": receipt.retry_reason,
        "quota_budget": receipt.quota_budget,
        "test_objective": receipt.test_objective,
        "fallback": dict(receipt.fallback),
        "production_ready": receipt.production_ready,
        "human_review": receipt.human_review,
        "generated": receipt.generated,
        "evidence_capable": receipt.evidence_capable,
        "post_generation_billing_state": dict(receipt.post_generation_billing_state),
    }


#: Fields a cached video receipt must carry before reuse.
REQUIRED_VIDEO_RECEIPT_FIELDS: Tuple[str, ...] = (
    "provider", "product", "plan", "billing_mode", "model", "mode",
    "compiled_prompt_sha256", "fingerprint", "output_sha256",
    "requested_duration_s", "actual_duration_s", "requested_resolution",
    "actual_width", "actual_height", "canonical_path", "technical_qc",
    "billing_guard_verdict", "task_ref_hash", "audio_policy",
    "generated", "evidence_capable", "prompt_skill_repo", "prompt_skill_commit",
)

NON_BLANK_VIDEO_RECEIPT_FIELDS: Tuple[str, ...] = (
    "provider", "product", "plan", "billing_mode", "model", "mode",
    "compiled_prompt_sha256", "fingerprint", "output_sha256",
    "requested_resolution", "canonical_path", "billing_guard_verdict",
    "task_ref_hash", "audio_policy", "prompt_skill_repo", "prompt_skill_commit",
)