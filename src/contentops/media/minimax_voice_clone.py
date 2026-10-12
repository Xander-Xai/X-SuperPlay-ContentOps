"""Voice-clone lifecycle against the documented MiniMax public API. No TTS.

Why this is separate from :class:`~contentops.media.minimax_speech.MiniMaxMPlanProvider`
------------------------------------------------------------------------------------
Synthesis and cloning are different commercial events with different failure modes.
Folding cloning into ``synthesize_speech()`` would mean one method whose billing
behaviour, entitlement error and retry semantics all change depending on an argument --
and the speech provider's whole safety story rests on "one narration, one authorised
call, zero spend". Cloning may legitimately cost money, once. That has to be visible,
not an argument.

So this module owns: sample validation, upload, clone creation, clone listing, refusal
classification and receipt sanitisation. It owns **no** synthesis. The first real TTS
with the cloned voice goes through the existing speech provider with a different
``voice``, which keeps the audio QC, lexicon, cache and receipt machinery in one place.

The two facts that shape the design
-----------------------------------
1. **The clone fee is a real, bounded, one-time cost.** The Founder's account was
   confirmed by MiniMax customer service to charge one one-time payment of CNY 9.9 per
   cloned voice, after which TTS consumes the existing M Plan subscription.
   :data:`CLONE_FEE_POLICY` records that as an account-specific fact, not as public
   MiniMax pricing.

   The existing :class:`~contentops.media.billing_guard.BillingGuard` demands that cash,
   credit and voucher balances are *exactly zero*. That rule is right for synthesis and
   wrong here: a spend of CNY 9.9 is authorised. So the guard is not weakened and not
   reused. Instead this module carries its own ceiling,
   :data:`CLONE_FEE_MAX_CNY`, and refuses any cloned-voice fee above it. PAYG and
   Credit Pack remain forbidden for **TTS**, unchanged.

2. **Sending the clone request is the billable act, and it must not happen by
   accident.** :meth:`MiniMaxVoiceCloneProvider.create_clone` refuses to transmit unless
   ``confirm_fee=True`` is passed explicitly. Default arguments fail closed, so a
   caller that merely wants to see what *would* be sent gets
   :data:`REFUSAL_FEE_NOT_CONFIRMED` and a printed gate instead of a charge.

Why preview text is never sent
------------------------------
``text`` is an optional preview field. Supplying it makes the provider synthesise an
extra utterance as part of cloning, which is a second generation event and, per the
current documentation, the point at which first-use charging is described. The clone
payload is therefore minimal: ``file_id`` and ``voice_id`` only.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .credentials import (
    CREDENTIAL_PAYG,
    CREDENTIAL_SUBSCRIPTION,
    CredentialBinding,
    CredentialBindingError,
    ResolvedCredential,
    classify_credential,
)

__all__ = [
    "CLONE_FEE_MAX_CNY",
    "CLONE_FEE_POLICY",
    "CLONE_TRANSPORT",
    "BASE_URL_ENV_VARS",
    "GET_VOICE_PATH",
    "CLONE_PATH",
    "UPLOAD_PATH",
    "PROVIDER_NAME",
    "PURPOSE_VOICE_CLONE",
    "REFUSAL_CLONE_ALREADY_ATTEMPTED",
    "REFUSAL_CREDENTIAL_CLASS",
    "REFUSAL_FEE_ABOVE_MAX",
    "REFUSAL_FEE_NOT_CONFIRMED",
    "REFUSAL_MODEL_NOT_ON_PLAN",
    "REFUSAL_NOT_ENTITLED",
    "REFUSAL_SCHEMA_CHANGED",
    "REFUSAL_SAMPLE_INVALID",
    "REFUSAL_SAMPLE_TRACKED",
    "REFUSAL_TRANSPORT",
    "REFUSAL_VOICE_ID_INVALID",
    "RESOURCE_TYPE",
    "SAMPLE_FORMATS",
    "SAMPLE_MAX_BYTES",
    "SAMPLE_MAX_SECONDS",
    "SAMPLE_MIN_SECONDS",
    "TTS_BILLING_POLICY",
    "VOICE_ID_MAX_LEN",
    "VOICE_ID_MIN_LEN",
    "CloneRefusal",
    "VoiceCloneOutcome",
    "VoiceCloneReceipt",
    "VoiceCloneRequest",
    "MiniMaxVoiceCloneProvider",
    "sample_facts",
    "sanitize_voice_id",
    "validate_voice_id",
    "voice_id_hash",
]

PROVIDER_NAME = "minimax"
RESOURCE_TYPE = "voice_cloning"
CLONE_TRANSPORT = "documented_public_api"

#: The account's region decides which documented host is addressed, and a credential
#: authorised against one host is not evidence about the other -- measured on this
#: account, where the regional host accepts the Subscription Key and the international
#: host rejects it with 2049.
#:
#: The literal host is deliberately **not** written here. Repository policy keeps
#: provider endpoint URLs out of tracked source (AGENTS.md section 8), and
#: ``scripts/check_docs.py`` enforces it. So the host is runtime configuration,
#: resolved in a fixed order and then recorded in every receipt as ``base_url_host``:
#:
#: 1. an explicit ``base_url`` argument
#: 2. ``MINIMAX_VOICE_CLONE_BASE_URL``
#: 3. ``CONTENTOPS_MINIMAX_BASE_URL`` -- the same variable BillingGuard already reads,
#:    so the billing proof and the billable call cannot address different services
#:
#: If none is set the provider refuses. A guessed default is worse than no default: the
#: wrong host returns ``2049 invalid api key``, which reads as a broken credential
#: rather than a misconfigured endpoint.
BASE_URL_ENV_VARS = (
    "MINIMAX_VOICE_CLONE_BASE_URL",
    "CONTENTOPS_MINIMAX_BASE_URL",
)

UPLOAD_PATH = "/v1/files/upload"
CLONE_PATH = "/v1/voice_clone"
GET_VOICE_PATH = "/v1/get_voice"
PURPOSE_VOICE_CLONE = "voice_clone"

#: Recorded as an ACCOUNT-SPECIFIC fact supplied by the Founder from direct MiniMax
#: customer service. Deliberately not phrased as public MiniMax pricing, and not used
#: to derive any other figure.
CLONE_FEE_POLICY = "FOUNDER_CONFIRMED_ONE_TIME_CNY_9_9"
CLONE_FEE_MAX_CNY = Decimal("9.9")

#: TTS after cloning stays on the subscription. Neither fallback is permitted.
TTS_BILLING_POLICY = "M_PLAN_SUBSCRIPTION"
ALLOW_PAYG_TTS = False
ALLOW_CREDIT_PACK_TTS = False

#: Current documented upload rules. Re-checked before the live call; if the provider
#: changes them, these constants move with the docs and the mismatch is a refusal
#: rather than a surprise.
SAMPLE_FORMATS: Tuple[str, ...] = ("mp3", "m4a", "wav")
SAMPLE_MIN_SECONDS = 10.0
SAMPLE_MAX_SECONDS = 300.0
SAMPLE_MAX_BYTES = 20 * 1024 * 1024

#: Documented custom voice_id rules: length [8, 256], must start with an English
#: letter, may contain letters/digits/'-'/'_', must not end with '-' or '_'.
VOICE_ID_MIN_LEN = 8
VOICE_ID_MAX_LEN = 256

REFUSAL_FEE_NOT_CONFIRMED = "READY_FOR_ONE_TIME_CLONE_FEE"
REFUSAL_FEE_ABOVE_MAX = "CLONE_FEE_ABOVE_AUTHORISED_MAX"
REFUSAL_CREDENTIAL_CLASS = "CREDENTIAL_CLASS_NOT_AUTHORISED"
REFUSAL_SAMPLE_INVALID = "SAMPLE_INVALID"
REFUSAL_SAMPLE_TRACKED = "SAMPLE_IS_TRACKED_PUBLIC_REFUSED"
REFUSAL_NOT_ENTITLED = "VOICE_CLONE_NOT_ENTITLED"
REFUSAL_SCHEMA_CHANGED = "SCHEMA_CHANGED"
#: The caller asked for a voice_id that the documented rules reject. Distinct from
#: SCHEMA_CHANGED: nothing about the provider moved, the input is simply unusable.
REFUSAL_VOICE_ID_INVALID = "VOICE_ID_INVALID"
REFUSAL_TRANSPORT = "TRANSPORT_ERROR"
REFUSAL_CLONE_ALREADY_ATTEMPTED = "DUPLICATE_CLONE_ATTEMPT_REFUSED"
REFUSAL_ACCOUNT_VERIFICATION = "NEEDS_ACCOUNT_VERIFICATION"
REFUSAL_DUPLICATE_VOICE_ID = "DUPLICATE_VOICE_ID"
#: The provider answered 2061: this model is not available on the current Token
#: Plan. Distinct from 2038, which is about the account's verification state -- 2061
#: is about what the plan covers, and no amount of verification changes it.
REFUSAL_MODEL_NOT_ON_PLAN = "MODEL_NOT_ON_PLAN"

#: Provider status codes, as documented. Named rather than inlined so the mapping from
#: code to meaning is one visible table instead of scattered magic numbers.
STATUS_OK = 0
STATUS_RATE_LIMITED = 1002
STATUS_AUTH_FAILED = 1004
STATUS_INSUFFICIENT_BALANCE = 1008
STATUS_PARAM_INVALID = 2013
STATUS_INVALID_API_KEY = 2049
#: 2038: no cloning permission -- check the account verification state. The current
#: documentation names real-name verification as the usual cause.
STATUS_NO_CLONE_PERMISSION = 2038
#: Documented in the official MiniMax CLI ERRORS.md: "This model is not available
#: on your current Token Plan." Measured on this account against /v1/voice_clone.
STATUS_MODEL_NOT_ON_PLAN = 2061

_STATUS_MEANING = {
    STATUS_OK: "success",
    STATUS_RATE_LIMITED: "rate limited",
    STATUS_AUTH_FAILED: "account authentication failed",
    STATUS_INSUFFICIENT_BALANCE: "insufficient account balance",
    STATUS_PARAM_INVALID: "invalid parameter",
    STATUS_INVALID_API_KEY: "invalid api key",
    STATUS_NO_CLONE_PERMISSION: "no voice-cloning permission; account verification state",
    STATUS_MODEL_NOT_ON_PLAN: "this model is not available on the current Token Plan",
}


class CloneRefusal(RuntimeError):
    """A clone step was refused before or instead of being transmitted.

    ``retry_allowed`` is False everywhere by default. This repository's rule is one
    attempt, no automatic retry: a clone that fails for entitlement or payment reasons
    will fail identically on a second call, and the money would be spent twice.
    """

    def __init__(self, code: str, detail: str, *, retry_allowed: bool = False) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail
        self.retry_allowed = retry_allowed


@dataclass(frozen=True)
class VoiceCloneRequest:
    """What is being cloned, and the commercial terms it is being cloned under.

    ``expected_fee_cny`` is an assertion the caller must make explicitly. It is not
    discovered at runtime, because a fee that is only learned from a response is a fee
    that was already agreed to.
    """

    voice_alias: str
    provider_voice_id: str
    objective: str
    expected_fee_cny: Decimal = CLONE_FEE_MAX_CNY
    sample_path: Optional[Path] = None
    sample_sha256: str = ""
    #: Set when the sample was uploaded by an earlier step. The file id is a handle to
    #: the Founder's voice on someone else's storage, so it is passed in memory and is
    #: never written to a receipt.
    uploaded_file_id: Optional[int] = None

    def fingerprint(self) -> str:
        """Stable digest of everything that decides whether this clone is authorised.

        Persisted before the request so that "what exactly was sent, and under what
        declared terms" is answerable afterwards without trusting memory or the
        provider's response.
        """
        payload = {
            "voice_alias": self.voice_alias,
            "provider_voice_id_hash": voice_id_hash(self.provider_voice_id),
            "objective": self.objective,
            "expected_fee_cny": str(self.expected_fee_cny),
            "sample_sha256": self.sample_sha256,
            "clone_fee_policy": CLONE_FEE_POLICY,
            "tts_billing_policy": TTS_BILLING_POLICY,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()


@dataclass
class VoiceCloneReceipt:
    """The sanitised, committed record of a clone attempt.

    Contains no raw provider voice_id, no raw sample, no credential and no absolute
    host path. It is written to be readable by anyone and checkable by them.
    """

    schema: str = "contentops.voice-clone-receipt/v1"
    provider: str = PROVIDER_NAME
    clone_transport: str = CLONE_TRANSPORT
    voice_alias: str = ""
    voice_id_hash: str = ""
    sample_sha256: str = ""
    rights_basis: str = "FOUNDER_OWN_VOICE"
    clone_fee_policy: str = CLONE_FEE_POLICY
    tts_billing_policy: str = TTS_BILLING_POLICY
    allow_payg_tts: bool = ALLOW_PAYG_TTS
    allow_credit_pack_tts: bool = ALLOW_CREDIT_PACK_TTS
    clone_status: str = "NOT_ATTEMPTED"
    provider_status_code: Optional[int] = None
    provider_status_meaning: str = ""
    base_url_host: str = ""
    credential_class: str = ""
    credential_source: str = ""
    model_for_tts: str = ""
    request_fingerprint: str = ""
    created_at: str = ""
    provider_calls: Dict[str, int] = field(default_factory=dict)
    production_ready: bool = False
    human_review: str = "PENDING_FOUNDER_REVIEW"
    notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        payload = dict(self.__dict__)
        # Belt and braces: the invariants this receipt exists to hold, asserted at the
        # point of serialisation rather than trusted to the caller.
        blob = json.dumps(payload, ensure_ascii=False)
        for banned in ("Authorization", "Bearer ", "sk-cp-", "sk-api-"):
            if banned in blob:
                raise CloneRefusal(
                    REFUSAL_TRANSPORT,
                    f"refusing to serialise a receipt containing {banned!r}",
                )
        if self.voice_alias and not self.voice_id_hash:
            raise CloneRefusal(
                REFUSAL_TRANSPORT,
                "a receipt naming a voice alias must also carry its sanitised hash",
            )
        return payload


@dataclass
class VoiceCloneOutcome:
    status: str
    receipt: VoiceCloneReceipt
    raw_voice_id: str = ""  # local only; never serialised into the receipt
    refusal_code: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "CLONED"


# --- pure helpers -----------------------------------------------------------


def validate_voice_id(voice_id: str) -> None:
    """Enforce the documented custom ``voice_id`` rules before sending anything."""
    if not voice_id:
        raise CloneRefusal(REFUSAL_VOICE_ID_INVALID, "voice_id is empty")
    if not (VOICE_ID_MIN_LEN <= len(voice_id) <= VOICE_ID_MAX_LEN):
        raise CloneRefusal(
            REFUSAL_VOICE_ID_INVALID,
            f"voice_id length {len(voice_id)} is outside the documented "
            f"[{VOICE_ID_MIN_LEN}, {VOICE_ID_MAX_LEN}]",
        )
    if not voice_id[0].isascii() or not voice_id[0].isalpha():
        raise CloneRefusal(
            REFUSAL_VOICE_ID_INVALID,
            "voice_id must start with an English letter",
        )
    if voice_id.endswith("-") or voice_id.endswith("_"):
        raise CloneRefusal(
            REFUSAL_VOICE_ID_INVALID, "voice_id must not end with '-' or '_'"
        )
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
    bad = sorted(set(voice_id) - allowed)
    if bad:
        raise CloneRefusal(
            REFUSAL_VOICE_ID_INVALID,
            f"voice_id contains characters outside the documented set: {bad}",
        )


def voice_id_hash(voice_id: str) -> str:
    """Stable, non-reversible digest of a provider voice id.

    The raw id is an account-scoped handle to a real person's voice. It is not a
    credential, but it is personal enough that the public repository carries only this.
    """
    return hashlib.sha256((voice_id or "").encode("utf-8")).hexdigest()


def sanitize_voice_id(voice_id: str) -> str:
    return voice_id_hash(voice_id)


def sample_facts(path: Path) -> Dict[str, Any]:
    """Hash and probe a candidate sample without modifying it."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return {
        "path": path,
        "sha256": digest.hexdigest(),
        "bytes": path.stat().st_size,
        "suffix": path.suffix.lower().lstrip("."),
    }


def _is_tracked(path: Path) -> bool:
    """Is this file tracked by Git?

    A raw human voice must never be committed. Uploading a *tracked* sample would mean
    the privacy breach already happened, so this is checked as a precondition rather
    than assumed from the fact that the path is currently ignored.

    Every git invocation goes through ``process_utils.hidden_run``. Calling
    ``subprocess.run`` directly here would spawn a visible console window on Windows,
    which is the specific regression ``scripts/check_subprocess_policy.py`` exists to
    catch -- and it did catch it, in CI, after this file became tracked.
    """
    from process_utils import hidden_run

    try:
        root = hidden_run(
            ["git", "rev-parse", "--show-toplevel"], cwd=str(path.parent), timeout=60
        )
        if root.returncode != 0:
            return False
        cwd = (root.stdout or "").strip()
        rel = path.resolve().relative_to(Path(cwd).resolve()).as_posix()
    except Exception:  # noqa: BLE001 - not in a repository at all
        return False
    proc = hidden_run(
        ["git", "ls-files", "--error-unmatch", "--", rel], cwd=cwd, timeout=60
    )
    return proc.returncode == 0


class MiniMaxVoiceCloneProvider:
    """Upload, clone, verify. No synthesis, no retry, no silent spend."""

    name = PROVIDER_NAME

    def __init__(
        self,
        binding: Optional[CredentialBinding] = None,
        *,
        credential: Optional[ResolvedCredential] = None,
        base_url: Optional[str] = None,
        transport: Optional[Any] = None,
        clock: Optional[Callable[[], str]] = None,
        max_clone_attempts: int = 1,
        allow_payg_clone: bool = False,
    ) -> None:
        if binding is None:
            binding = CredentialBinding(credential)
        self._binding = binding
        #: Which credential class this run is allowed to clone with.
        #:
        #: ``False`` -- the default, and the behaviour every existing test covers --
        #: requires ``SUBSCRIPTION``. ``True`` requires ``PAYG`` instead, which is the
        #: two-key route: the plan refuses 快速复刻 with 2061, so the clone must go
        #: through the pay-as-you-go key while the narration stays on the plan.
        #:
        #: It is an argument and not an inference from the key's prefix because the
        #: *intent* is what should be declared. A provider handed a PAYG key and not
        #: told to use it for cloning refuses, rather than quietly reinterpreting the
        #: commercial intent of a secret it was merely given.
        self._required_credential_class = (
            CREDENTIAL_PAYG if allow_payg_clone else CREDENTIAL_SUBSCRIPTION
        )
        self._allow_payg_clone = allow_payg_clone
        resolved_host = (base_url or "").strip()
        if not resolved_host:
            for name in BASE_URL_ENV_VARS:
                candidate = os.environ.get(name, "").strip()
                if candidate:
                    resolved_host = candidate
                    break
        if not resolved_host:
            raise CloneRefusal(
                REFUSAL_TRANSPORT,
                "no provider host is configured. Set "
                + " or ".join(BASE_URL_ENV_VARS)
                + ". There is deliberately no built-in default: the wrong regional host "
                "answers with an invalid-api-key status, which looks like a broken "
                "credential instead of a misconfigured endpoint.",
            )
        self._base_url = resolved_host.rstrip("/")
        #: Injectable so tests never touch the network.
        self._transport = transport
        self._clock = clock or (lambda: __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ).isoformat())
        self._max_clone_attempts = max(1, max_clone_attempts)

        #: Observable counters. A test can assert exactly one upload and exactly one
        #: clone request, which is the only mechanical way to prove "no retry".
        self.upload_count = 0
        self.clone_count = 0
        self.list_count = 0
        self.created_voice_ids: List[str] = []

    # -- capability / health -------------------------------------------------

    def capabilities(self) -> Dict[str, Any]:
        return {
            "provider": PROVIDER_NAME,
            "resource_type": RESOURCE_TYPE,
            "clone_transport": CLONE_TRANSPORT,
            "endpoints": {
                "upload": UPLOAD_PATH,
                "clone": CLONE_PATH,
                "list": GET_VOICE_PATH,
            },
            "base_url_host": self._base_url,
            "fee_policy": CLONE_FEE_POLICY,
            "fee_max_cny": str(CLONE_FEE_MAX_CNY),
            "tts_billing_policy": TTS_BILLING_POLICY,
            "allow_payg_tts": ALLOW_PAYG_TTS,
            "allow_credit_pack_tts": ALLOW_CREDIT_PACK_TTS,
            "synthesizes": False,
            "evidence_status": (
                "DOCUMENTED_BUT_NOT_TESTED on this account until a real clone and a "
                "real cloned-voice synthesis both succeed"
            ),
        }

    def health(self) -> Dict[str, Any]:
        resolved = self._binding.resolved
        return {
            "provider": PROVIDER_NAME,
            "base_url_host": self._base_url,
            "credential": self._binding.safe_metadata(),
            "credential_usable": bool(resolved and resolved.usable),
            "base_url_resolved": bool(self._base_url),
        }

    @property
    def safe_metadata(self) -> Dict[str, str]:
        return self._binding.safe_metadata()

    # -- preconditions -------------------------------------------------------

    def _require_clone_credential(self) -> None:
        """Only the declared credential class is authorised for cloning.

        One attempt used a Subscription Key and was refused with ``2061``, because
        the plan does not cover 快速复刻. The pay-as-you-go key is therefore the only
        credential that can create this voice -- but it is also the credential that
        can spend cash, so it is admitted **only** when the caller declared
        ``allow_payg_clone=True``. Nothing about the key's own prefix can grant that,
        or every machine that happened to have a PAYG key would have a billable clone
        path available by accident.

        Note what is *not* permitted here: the pay-as-you-go key may create the
        voice and may do nothing else. Synthesis stays on the subscription key and is
        gated separately, because a PAYG synthesis is a different charge with no
        ceiling in this module at all.
        """
        resolved = self._binding.resolved
        if resolved is None or not resolved.usable:
            raise CloneRefusal(
                REFUSAL_CREDENTIAL_CLASS,
                "no credential is bound. Resolve it once and pass it, so the "
                "authorised credential and the transmitted credential are the same one.",
            )
        if resolved.credential_class != self._required_credential_class:
            wanted = (
                "PAYG (the pay-as-you-go key, which the plan does not cover) -- pass "
                "allow_payg_clone=True to declare that intent"
                if self._required_credential_class == CREDENTIAL_PAYG
                else "SUBSCRIPTION only. A PAYG key would bill cash for the clone and "
                "for every later TTS, and neither is permitted on this route."
            )
            raise CloneRefusal(
                REFUSAL_CREDENTIAL_CLASS,
                f"credential_class={resolved.credential_class} is not authorised for "
                f"cloning. This run requires {wanted}",
            )

    def _require_fee_authorisation(self, request: VoiceCloneRequest) -> None:
        try:
            declared = Decimal(str(request.expected_fee_cny))
        except (InvalidOperation, TypeError) as exc:
            raise CloneRefusal(
                REFUSAL_FEE_ABOVE_MAX, f"expected_fee_cny is not a number: {exc}"
            ) from exc
        if declared > CLONE_FEE_MAX_CNY:
            raise CloneRefusal(
                REFUSAL_FEE_ABOVE_MAX,
                f"declared fee CNY {declared} exceeds the authorised maximum "
                f"CNY {CLONE_FEE_MAX_CNY}. This is not a rounding argument; a fee "
                "above the authorised ceiling is unauthorised spending.",
            )

    def validate_sample(self, path: Path, *, duration_s: Optional[float] = None) -> Dict[str, Any]:
        """Check the sample against the current documented rules. Does not upload.

        ``duration_s`` is passed in rather than measured here so that the caller's
        probe (which already ran for the audit receipt) is the single measurement. If
        it is omitted the duration check is skipped and that fact is recorded, because
        "not measured" and "measured and fine" are different claims.
        """
        if not path.is_file():
            raise CloneRefusal(REFUSAL_SAMPLE_INVALID, f"sample not found: {path}")
        facts = sample_facts(path)
        if _is_tracked(path):
            raise CloneRefusal(
                REFUSAL_SAMPLE_TRACKED,
                f"the sample at {path} is tracked by Git. A raw human voice must never "
                "be committed, and uploading a committed sample would mean the privacy "
                "breach already happened. Remove it from the index before cloning.",
            )
        if facts["suffix"] not in SAMPLE_FORMATS:
            raise CloneRefusal(
                REFUSAL_SAMPLE_INVALID,
                f"format {facts['suffix']!r} is not one of the documented "
                f"{list(SAMPLE_FORMATS)}",
            )
        if facts["bytes"] > SAMPLE_MAX_BYTES:
            raise CloneRefusal(
                REFUSAL_SAMPLE_INVALID,
                f"sample is {facts['bytes']} bytes, above the documented "
                f"{SAMPLE_MAX_BYTES} byte limit",
            )
        if duration_s is not None and not (
            SAMPLE_MIN_SECONDS <= float(duration_s) <= SAMPLE_MAX_SECONDS
        ):
            raise CloneRefusal(
                REFUSAL_SAMPLE_INVALID,
                f"sample duration {duration_s}s is outside the documented "
                f"[{SAMPLE_MIN_SECONDS}, {SAMPLE_MAX_SECONDS}]s range",
            )
        facts["duration_s"] = duration_s
        facts["duration_checked"] = duration_s is not None
        return facts

    # -- preflight -----------------------------------------------------------

    def preflight(
        self, request: VoiceCloneRequest, *, duration_s: Optional[float] = None
    ) -> Dict[str, Any]:
        """Everything that decides the request, computed before it is sent.

        Deliberately performs no network I/O. It exists so the exact payload, the
        declared fee and the fingerprint can be persisted and reported *before* the
        one billable call, which is what makes "one attempt, on these terms"
        verifiable rather than asserted.
        """
        validate_voice_id(request.provider_voice_id)
        self._require_clone_credential()
        self._require_fee_authorisation(request)

        sample: Dict[str, Any] = {}
        if request.sample_path is not None:
            sample = self.validate_sample(request.sample_path, duration_s=duration_s)

        declared_sha = request.sample_sha256
        if sample and declared_sha and sample["sha256"] != declared_sha:
            raise CloneRefusal(
                REFUSAL_SAMPLE_INVALID,
                "the request declares one sample digest and the file on disk hashes to "
                "another. Refusing to clone one sample while recording a different one.",
            )

        return {
            "voice_alias": request.voice_alias,
            "provider_voice_id": request.provider_voice_id,
            "voice_id_hash": voice_id_hash(request.provider_voice_id),
            "objective": request.objective,
            "expected_fee_cny": str(request.expected_fee_cny),
            "fee_max_cny": str(CLONE_FEE_MAX_CNY),
            "clone_fee_policy": CLONE_FEE_POLICY,
            "tts_billing_policy": TTS_BILLING_POLICY,
            "allow_payg_tts": ALLOW_PAYG_TTS,
            "allow_credit_pack_tts": ALLOW_CREDIT_PACK_TTS,
            "base_url_host": self._base_url,
            "sample": {k: v for k, v in sample.items() if k != "path"},
            "request_payload_fields": ["file_id", "voice_id"],
            "preview_text_sent": False,
            "request_fingerprint": request.fingerprint(),
            "credential": self._binding.safe_metadata(),
        }

    def fee_gate(self, request: VoiceCloneRequest) -> str:
        """The text to print when the billable request has not been confirmed.

        Returned rather than merely logged so that a caller cannot "handle" the gate by
        ignoring a log line.
        """
        return (
            "READY_FOR_ONE_TIME_CLONE_FEE\n"
            f"expected_max_fee_cny={CLONE_FEE_MAX_CNY}\n"
            "additional_payg_allowed=false\n"
            "credit_pack_fallback_allowed=false\n"
            f"voice_alias={request.voice_alias}\n"
            f"voice_id_hash={voice_id_hash(request.provider_voice_id)}\n"
            f"sample_sha256={request.sample_sha256}\n"
            f"request_fingerprint={request.fingerprint()}"
        )

    # -- transport -----------------------------------------------------------

    def _headers(self, *, content_type: Optional[str] = "application/json") -> Dict[str, str]:
        try:
            env = self._binding.require_env()
        except CredentialBindingError as exc:
            raise CloneRefusal(REFUSAL_CREDENTIAL_CLASS, str(exc)) from exc
        key = env.get("MINIMAX_API_KEY", "")
        headers = {"Authorization": f"Bearer {key}"}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _post_json(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self._base_url}{path}"
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url, data=data, headers=self._headers(), method="POST"
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise CloneRefusal(
                REFUSAL_TRANSPORT,
                f"POST {path} failed with HTTP {exc.code}. The response body is not "
                "echoed because it can contain account detail; inspect it manually.",
            ) from exc
        except urllib.error.URLError as exc:
            raise CloneRefusal(
                REFUSAL_TRANSPORT, f"POST {path} could not reach {self._base_url}: {exc}"
            ) from exc

    @staticmethod
    def _multipart_body(
        field_name: str,
        filename: str,
        content: bytes,
        extra: Dict[str, str],
    ) -> Tuple[bytes, str]:
        boundary = "----ContentOpsBoundary" + uuid.uuid4().hex
        parts: List[bytes] = []
        for key, value in extra.items():
            parts.append(
                f"--{boundary}\r\n".encode()
                + f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode()
                + f"{value}\r\n".encode()
            )
        parts.append(
            f"--{boundary}\r\n".encode()
            + f'Content-Disposition: form-data; name="{field_name}"; '
            f'filename="{filename}"\r\n'.encode()
            + b"Content-Type: application/octet-stream\r\n\r\n"
            + content
            + b"\r\n"
        )
        parts.append(f"--{boundary}--\r\n".encode())
        return b"".join(parts), f"multipart/form-data; boundary={boundary}"

    def _check_base_resp(self, payload: Dict[str, Any], *, stage: str) -> int:
        """Map a documented status code onto an explicit refusal. Never retries."""
        base = payload.get("base_resp") or {}
        code = base.get("status_code")
        if code is None:
            raise CloneRefusal(
                REFUSAL_SCHEMA_CHANGED,
                f"{stage}: response carried no base_resp.status_code. The schema this "
                "module was written against is gone; re-read the current documentation "
                "before sending anything else.",
            )
        try:
            code_int = int(code)
        except (TypeError, ValueError) as exc:
            raise CloneRefusal(
                REFUSAL_SCHEMA_CHANGED,
                f"{stage}: base_resp.status_code={code!r} is not an integer",
            ) from exc
        if code_int == STATUS_OK:
            return code_int
        meaning = _STATUS_MEANING.get(code_int, "unrecognised status code")
        # The provider's own message is carried through, bounded, because "2061" alone
        # is not actionable and the message is what tells an operator which plan or
        # model is at issue. It is a status string, never a credential or an id.
        message = str(base.get("status_msg") or "").strip()[:200]
        detail = f"{stage}: provider status_code={code_int} ({meaning})"
        if message:
            detail += f": {message}"
        if code_int == STATUS_MODEL_NOT_ON_PLAN:
            raise CloneRefusal(
                REFUSAL_MODEL_NOT_ON_PLAN,
                detail + ". The plan does not include this model, so this is not a "
                "verification problem and not a retry problem: the same request will be "
                "refused again until the plan or the route changes.",
            )
        if code_int == STATUS_NO_CLONE_PERMISSION:
            raise CloneRefusal(REFUSAL_ACCOUNT_VERIFICATION, detail)
        if code_int in (STATUS_AUTH_FAILED, STATUS_INVALID_API_KEY):
            raise CloneRefusal(REFUSAL_CREDENTIAL_CLASS, detail)
        if code_int == STATUS_INSUFFICIENT_BALANCE:
            raise CloneRefusal(
                REFUSAL_FEE_ABOVE_MAX,
                detail + ". An insufficient-balance reply means the request would have "
                "been paid for outside the subscription; refusing.",
            )
        if code_int == STATUS_PARAM_INVALID:
            raise CloneRefusal(REFUSAL_SCHEMA_CHANGED, detail)
        raise CloneRefusal(REFUSAL_NOT_ENTITLED, detail)

    # -- steps ---------------------------------------------------------------

    def upload_sample(self, path: Path) -> int:
        """Upload the sample with ``purpose=voice_clone`` and return the file id.

        The file id is returned to the caller and never persisted by this method: it is
        a handle to the Founder's voice on someone else's storage.
        """
        self._require_clone_credential()
        facts = self.validate_sample(path)
        if self._transport is not None:
            payload = self._transport.upload(path, facts)
            self.upload_count += 1
            self._check_base_resp(payload, stage="upload")
            return int((payload.get("file") or {}).get("file_id"))

        body, content_type = self._multipart_body(
            "file", path.name, path.read_bytes(), {"purpose": PURPOSE_VOICE_CLONE}
        )
        request = urllib.request.Request(
            f"{self._base_url}{UPLOAD_PATH}",
            data=body,
            headers=self._headers(content_type=content_type),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise CloneRefusal(
                REFUSAL_TRANSPORT,
                f"POST {UPLOAD_PATH} failed with HTTP {exc.code}",
            ) from exc
        except urllib.error.URLError as exc:
            raise CloneRefusal(
                REFUSAL_TRANSPORT, f"POST {UPLOAD_PATH} could not reach the host: {exc}"
            ) from exc
        self.upload_count += 1
        self._check_base_resp(payload, stage="upload")
        file_obj = payload.get("file") or {}
        if "file_id" not in file_obj:
            raise CloneRefusal(
                REFUSAL_SCHEMA_CHANGED,
                "upload succeeded but the response carried no file.file_id",
            )
        return int(file_obj["file_id"])

    def create_clone(
        self,
        file_id: int,
        voice_id: str,
        *,
        confirm_fee: bool = False,
    ) -> Dict[str, Any]:
        """Create the clone. Refuses unless the fee has been explicitly confirmed.

        ``confirm_fee`` defaults to False, and that default is the whole gate: a caller
        that has not been told to spend CNY 9.9 cannot spend CNY 9.9 by forgetting an
        argument.
        """
        validate_voice_id(voice_id)
        self._require_clone_credential()

        if not confirm_fee:
            raise CloneRefusal(
                REFUSAL_FEE_NOT_CONFIRMED,
                "the clone request is billable and has not been confirmed. Refusing to "
                "transmit. Re-run with explicit Founder confirmation to proceed.",
            )
        if self.clone_count >= self._max_clone_attempts:
            raise CloneRefusal(
                REFUSAL_CLONE_ALREADY_ATTEMPTED,
                f"a clone attempt has already been made ({self.clone_count}); the "
                "configured maximum is one. This repository does not retry a billable "
                "call automatically.",
            )

        payload = {"file_id": int(file_id), "voice_id": voice_id}
        if self._transport is not None:
            response = self._transport.clone(payload)
        else:
            response = self._post_json(CLONE_PATH, payload)
        self.clone_count += 1
        self._check_base_resp(response, stage="clone")
        self.created_voice_ids.append(voice_id)
        return response

    def list_cloned_voices(self) -> List[Dict[str, Any]]:
        """Read-only listing. Not billable, and safe to call before any clone exists.

        Current documentation is explicit that ``voice_cloning`` entries appear only
        **after the voice has been used for synthesis**, so an empty list immediately
        after clone creation is expected and is not evidence that the clone failed.
        """
        payload = (
            self._transport.list_voices()
            if self._transport is not None
            else self._post_json(GET_VOICE_PATH, {"voice_type": "voice_cloning"})
        )
        self.list_count += 1
        self._check_base_resp(payload, stage="get_voice")
        entries = payload.get("voice_cloning")
        if entries is None:
            raise CloneRefusal(
                REFUSAL_SCHEMA_CHANGED,
                "get_voice response carried no voice_cloning array; the schema this "
                "module was written against may have changed",
            )
        return list(entries)

    # -- orchestration -------------------------------------------------------

    def clone(
        self,
        request: VoiceCloneRequest,
        *,
        confirm_fee: bool = False,
        duration_s: Optional[float] = None,
    ) -> VoiceCloneOutcome:
        """Preflight, then clone only if authorised. Never retries.

        Refusals are returned as an outcome with ``status='REFUSED'`` and a code, rather
        than raised, so the caller can persist a receipt for a refusal too. A refusal
        that leaves no record is how the same refusal gets attempted twice.

        Ordering matters and is deliberate. The fee gate is checked **before** the
        upload, not after: uploading the Founder's voice is itself an irreversible
        disclosure to a third party, so a run that is going to refuse the fee must not
        first hand over the sample and then decline. Gate, then upload, then clone.
        """
        receipt = VoiceCloneReceipt(
            voice_alias=request.voice_alias,
            voice_id_hash=voice_id_hash(request.provider_voice_id),
            sample_sha256=request.sample_sha256,
            base_url_host=self._base_url,
            credential_class=self._binding.safe_metadata().get("credential_class", ""),
            credential_source=self._binding.safe_metadata().get("credential_source", ""),
            model_for_tts=request.objective,
        )

        # 1. Preflight: no network. Establishes the payload, the declared fee and the
        #    fingerprint, and refuses on credential class, fee ceiling or bad sample.
        try:
            preflight = self.preflight(request, duration_s=duration_s)
            receipt.request_fingerprint = preflight["request_fingerprint"]
            if request.sample_path is not None:
                receipt.sample_sha256 = preflight["sample"]["sha256"]
        except CloneRefusal as refusal:
            receipt.clone_status = "REFUSED"
            receipt.notes.append(f"[{refusal.code}] {refusal.detail}")
            return VoiceCloneOutcome(
                status="REFUSED", receipt=receipt, refusal_code=refusal.code
            )

        # 2. The billable gate, before anything leaves the machine.
        if not confirm_fee:
            receipt.clone_status = "REFUSED"
            receipt.notes.append(
                f"[{REFUSAL_FEE_NOT_CONFIRMED}] the clone request is billable and was "
                f"not confirmed. Nothing was uploaded and nothing was cloned. Gate:\n"
                f"{self.fee_gate(request)}"
            )
            return VoiceCloneOutcome(
                status="REFUSED", receipt=receipt, refusal_code=REFUSAL_FEE_NOT_CONFIRMED
            )

        # 3. Upload (only now).
        file_id = request.uploaded_file_id
        if request.sample_path is not None:
            try:
                file_id = self.upload_sample(request.sample_path)
            except CloneRefusal as refusal:
                receipt.clone_status = "REFUSED"
                receipt.notes.append(f"[{refusal.code}] upload: {refusal.detail}")
                return VoiceCloneOutcome(
                    status="REFUSED", receipt=receipt, refusal_code=refusal.code
                )
        if file_id is None:
            receipt.clone_status = "REFUSED"
            receipt.notes.append(
                f"[{REFUSAL_SAMPLE_INVALID}] no sample_path and no uploaded_file_id: "
                "there is nothing to clone"
            )
            return VoiceCloneOutcome(
                status="REFUSED", receipt=receipt, refusal_code=REFUSAL_SAMPLE_INVALID
            )

        # 4. Clone.
        try:
            response = self.create_clone(
                int(file_id), request.provider_voice_id, confirm_fee=True
            )
        except CloneRefusal as refusal:
            receipt.clone_status = "REFUSED"
            receipt.notes.append(f"[{refusal.code}] clone: {refusal.detail}")
            return VoiceCloneOutcome(
                status="REFUSED", receipt=receipt, refusal_code=refusal.code
            )

        base = response.get("base_resp") or {}
        receipt.provider_status_code = int(base.get("status_code", STATUS_OK))
        receipt.provider_status_meaning = _STATUS_MEANING.get(
            receipt.provider_status_code, ""
        )
        receipt.clone_status = "CLONED"
        receipt.created_at = self._clock()
        receipt.provider_calls = {
            "upload": self.upload_count,
            "clone": self.clone_count,
            "list": self.list_count,
        }
        return VoiceCloneOutcome(
            status="CLONED", receipt=receipt, raw_voice_id=request.provider_voice_id
        )
