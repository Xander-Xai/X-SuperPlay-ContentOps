"""Shared machinery for the native-credential rounds of Issue #34.

Two routes, deliberately separate
---------------------------------
```
PAYG_ACTIVATION_ROUTE  one cash-paid first-activation synthesis on the
                       pay-as-you-go key. Gate: decide_payg_native_activation --
                       the cash-activation policy with this round's independent,
                       single-use authorisation.
MPLAN_NARRATION_ROUTE  cross-key verification and the Golden narration on the
                       Subscription Key. Gate: decide_mplan_native --
                       Subscription class plus BillingGuard SAFE_INCLUDED_PLAN.
```

They share one transport (:mod:`contentops.media.minimax_native_tts`), one
request runner, one diagnostics writer and one money reader -- and nothing
else. Credential, budget, receipt and billing verification stay per-route,
because the failure this round corrects was precisely a receipt that claimed one
credential while the transport used another.

Why the request runner lives here and not in a script
-----------------------------------------------------
The recovery round (``CASH_ACTIVATION_RECOVERY``) and this round
(``PAYG_FIRST_ACTIVATION_NATIVE``) must perform the identical request sequence:
assert the payload, send exactly one native HTTP request, preserve the raw
envelope privately, normalise and QC the audio. Two copies of that sequence
would drift in exactly the places the first three attempts failed. The recovery
script now imports the runner from here; this module is the single owner.

What is *not* here
------------------
No CLI, no ``~/.mmx`` reads, no implicit credential resolution, no retry. A
caller passes the credential explicitly; the runner puts it in one
``Authorization`` header and nowhere else.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional

from .billing_guard import SAFE_INCLUDED_PLAN, BillingGuard
from .cash_activation_recovery import (
    FOUNDER_AUTHORISED_EXPOSED_KEY_REUSE,
    CashActivationAuthorisation,
    ExposedKeyException,
    decide_cash_activation,
)
from .clone_route import ACTIVATION_TEXT, billable_characters
from .credentials import CREDENTIAL_SUBSCRIPTION
from .minimax_native_tts import (
    MINIMAX_CN_HOST,
    NativeTtsRefusal,
    build_t2a_payload,
    host_is_documented_cn,
    normalize_host,
    normalize_paragraph_newlines,
    send_t2a_once,
)

__all__ = [
    "FOUNDER_AUTHORISED_NATIVE_FIRST_ACTIVATION",
    "MPLAN_NARRATION_ROUTE",
    "NATIVE_FIRST_ACTIVATION_CEILING_CNY",
    "NATIVE_ROUND_ACTIVATION_TEXT",
    "NATIVE_ROUND_BILLABLE_CHARACTERS",
    "NATIVE_ROUND_MODEL",
    "NATIVE_ROUND_VOICE_ID_HASH",
    "PAYG_ACTIVATION_ROUTE",
    "append_activation_history",
    "build_spoken_request",
    "canonical_blob_sha256",
    "classify_mplan_only",
    "classify_payg_outcome",
    "delta_money",
    "decide_mplan_native",
    "decide_payg_native_activation",
    "read_money",
    "run_native_activation_once",
    "sanitise_history_entry",
    "write_private_provider_response",
]

PAYG_ACTIVATION_ROUTE = "PAYG_ACTIVATION_ROUTE"
MPLAN_NARRATION_ROUTE = "MPLAN_NARRATION_ROUTE"

#: This round's authorisation, named so a receipt can be matched against the
#: Founder's decision. It is independent of every earlier authorisation: the
#: three historical attempts and their consumed exceptions remain recorded
#: exactly as they were.
FOUNDER_AUTHORISED_NATIVE_FIRST_ACTIVATION = (
    "FOUNDER_AUTHORISED_NATIVE_FIRST_ACTIVATION_2026_10_12"
)

#: The Founder's cash ceiling for the one native activation request.
NATIVE_FIRST_ACTIVATION_CEILING_CNY = Decimal("10.00")

#: The GRANTED scope of this round's authorisation, as fixed constants.
#:
#: These are deliberately not derived from what the caller measures. They are
#: the terms of the grant -- this voice, this model, this fixed short text --
#: and every measured fact is checked against them, so an edit that quietly
#: points the request at a different voice, model or text refuses instead of
#: spending money outside the authorisation.
NATIVE_ROUND_VOICE_ID_HASH = (
    "7271d9c80c88821a6a09ed43328619d0ee08c3f2b2449237fe2c31f6899abeef"
)
NATIVE_ROUND_MODEL = "speech-2.8-hd"
NATIVE_ROUND_ACTIVATION_TEXT = ACTIVATION_TEXT
NATIVE_ROUND_BILLABLE_CHARACTERS = billable_characters(ACTIVATION_TEXT)

LOUDNORM_TARGET = "I=-16:TP=-1.5:LRA=11"


# --- money -------------------------------------------------------------------


def read_money(base_url: str, credential: str) -> Dict[str, Any]:
    """One read-only balance + quota read. Never a generation call."""
    guard = BillingGuard(base_url=base_url, credential=credential)
    result = guard.evaluate("speech")
    return {
        "verdict": result.verdict,
        "reasons": list(result.reasons),
        "balances": {
            k: v
            for k, v in (result.balances or {}).items()
            if k not in ("base_resp", "balance_alert_switch", "balance_alert_threshold")
        },
        "quota": None
        if result.quota is None
        else {
            "interval_remaining_percent": result.quota.interval_remaining_percent,
            "weekly_remaining_percent": result.quota.weekly_remaining_percent,
            "bucket": result.quota.bucket,
        },
    }


def delta_money(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    """Per-field movement, computed and never guessed from a provider claim."""
    out: Dict[str, Any] = {}
    for name in (
        "cash_balance",
        "voucher_balance",
        "credit_balance",
        "owed_amount",
        "available_amount",
    ):
        try:
            b = Decimal(str(before["balances"][name]))
            a = Decimal(str(after["balances"][name]))
        except Exception:  # noqa: BLE001 - reported, never inferred
            out[name] = {
                "before": before["balances"].get(name),
                "after": after["balances"].get(name),
                "delta": None,
                "error": "field unreadable; not inferred",
            }
            continue
        out[name] = {
            "before": str(b),
            "after": str(a),
            "delta": str(a - b),
            "decreased": a < b,
            "increased": a > b,
        }
    return out


def canonical_blob_sha256(path: Path) -> Optional[str]:
    """sha256 of the tracked file's canonical (Git blob) bytes, or None.

    The locked narration text is pinned this way by the evidence lock: a
    Windows working tree can hold different line endings than the blob, so
    hashing the working tree would pin an accident of the checkout. Untracked
    or unreadable files return ``None`` and the caller must refuse rather than
    substitute a weaker digest.
    """
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
    from process_utils import hidden_run  # noqa: E402

    try:
        rel = path.resolve().relative_to(
            Path(__file__).resolve().parents[3]
        ).as_posix()
    except ValueError:
        return None
    result = hidden_run(
        ["git", "show", f"HEAD:{rel}"], cwd=str(path.parent), timeout=60
    )
    if result.returncode != 0:
        return None
    import hashlib

    return hashlib.sha256((result.stdout or "").encode("utf-8")).hexdigest()


# --- payload -----------------------------------------------------------------


@dataclass(frozen=True)
class SpokenRequest:
    """Everything the one request needs, decided before anything is sent.

    ``spoken_text`` is the final synthesis text: lexicon applied, line endings
    normalised, paragraph newlines and ``<#x#>`` pause markers preserved. Since
    the narration-v2 round there is no second, flattened form: the native HTTP
    API documents the newline as the paragraph separator, so flattening was a
    CLI-era workaround that this path must not carry.
    """

    display_text: str
    voice_id: str
    model: str
    spoken_text: str
    payload: Dict[str, Any]
    pronunciation_rule_count: int


def build_spoken_request(
    *,
    display_text: str,
    voice_id: str,
    model: str,
    lexicon: Any = None,
    sample_rate: int = 32000,
    fmt: str = "wav",
    channel: int = 1,
) -> SpokenRequest:
    """Lexicon -> documented payload, preserving paragraph structure.

    The four substitutions a transport could previously make invisibly -- a
    different voice, model, text or stream mode -- are checked here against the
    payload object that will actually be serialised.

    Paragraph newlines survive. The official OpenAPI definition of
    ``POST /v1/t2a_v2`` documents the newline as the paragraph separator and
    ``<#x#>`` as the pause control, and both are validated before the payload is
    built; collapsing a narration into one line is exactly what made the earlier
    CLI-era narration sound mechanical, and it is not allowed here.
    """
    spoken = lexicon.spoken_text(display_text) if lexicon is not None else display_text
    synthesis_text = normalize_paragraph_newlines(spoken)
    pronunciation = lexicon.tone_entries() if lexicon is not None else []
    payload = build_t2a_payload(
        text=synthesis_text,
        voice_id=voice_id,
        model=model,
        sample_rate=sample_rate,
        fmt=fmt,
        channel=channel,
        pronunciation_entries=pronunciation,
    )
    if payload["voice_setting"]["voice_id"] != voice_id:
        raise RuntimeError("payload voice_id disagrees with the authorised voice")
    if payload["model"] != model:
        raise RuntimeError("payload model disagrees with the authorised model")
    if payload["text"] != synthesis_text:
        raise RuntimeError("payload text disagrees with the spoken text")
    if payload["stream"] is not False:
        raise RuntimeError("payload must be non-streaming")
    return SpokenRequest(
        display_text=display_text,
        voice_id=voice_id,
        model=model,
        spoken_text=synthesis_text,
        payload=payload,
        pronunciation_rule_count=len(pronunciation),
    )


# --- diagnostics -------------------------------------------------------------


def write_private_provider_response(
    diagnostics_dir: Path,
    attempt_id: str,
    *,
    host: str,
    route: str,
    result: Any = None,
    refusal: Optional[NativeTtsRefusal] = None,
) -> Path:
    """Persist the full provider envelope under ``.private/``. Public data is a summary."""
    import json

    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any] = {
        "schema": "contentops.provider-raw-response/v1",
        "attempt_id": attempt_id,
        "route": route,
        "host": normalize_host(host),
        "path": "/v1/t2a_v2",
        "transport": "native_http_cn",
    }
    import hashlib

    if result is not None:
        raw = dict(result.raw)
        data = dict(raw.get("data") or {})
        audio_hex = data.pop("audio", None)
        if audio_hex is not None:
            data["_audio_hex_omitted"] = True
            data["_audio_hex_chars"] = len(audio_hex)
            data["_audio_sha256"] = hashlib.sha256(result.audio_bytes).hexdigest()
        raw["data"] = data
        payload.update(
            {
                "outcome": "provider_success",
                "http_status": result.http_status,
                "trace_id": result.trace_id,
                "base_resp": {
                    "status_code": result.status_code,
                    "status_msg": result.status_msg,
                },
                "extra_info": result.extra_info,
                "raw_response": raw,
            }
        )
    if refusal is not None:
        payload.update(
            {
                "outcome": "provider_refusal",
                **refusal.structured(),
                "raw_response": refusal.raw,
                "response_text_preview": refusal.response_text or None,
            }
        )
    blob = json.dumps(payload, indent=2, ensure_ascii=False)
    for banned in ("Authorization", "Bearer ", "sk-cp-", "sk-api-"):
        if banned in blob:
            raise SystemExit(
                f"refusing to write a provider diagnostic containing {banned!r}"
            )
    path = diagnostics_dir / f"tts-{attempt_id}.json"
    path.write_text(blob + "\n", encoding="utf-8", newline="\n")
    return path


# --- history -----------------------------------------------------------------


def sanitise_history_entry(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Drop every key-shaped value except explicit fingerprints."""
    return {
        k: v for k, v in payload.items() if "key" not in k or k.endswith("fingerprint")
    }


def append_activation_history(
    history_path: Path, attempt_id: str, payload: Dict[str, Any]
) -> None:
    """Append-only. Existing entries are never rewritten or removed.

    Both activation rounds append to the same file through this one function,
    so "what was tried" cannot look different depending on which script wrote
    last. A failed or refused attempt is an entry like any other; deleting one
    would make the record of what was tried differ from what was tried.
    """
    import json

    entries: list = []
    if history_path.is_file():
        try:
            entries = json.loads(history_path.read_text(encoding="utf-8")).get(
                "attempts", []
            )
        except (OSError, json.JSONDecodeError):
            entries = []
    entries.append({"attempt_id": attempt_id, **sanitise_history_entry(payload)})
    blob = json.dumps(
        {
            "schema": "contentops.voice-activation-history/v1",
            "note": (
                "Append-only. Every first-activation attempt on founder_primary_v1 is "
                "listed, including the ones that failed and charged nothing. Removing a "
                "failed entry would make the record of what was tried look different "
                "from what was tried."
            ),
            "attempts": entries,
        },
        indent=2,
        ensure_ascii=False,
    )
    for banned in ("Authorization", "Bearer ", "sk-cp-", "sk-api-"):
        if banned in blob:
            raise SystemExit(f"refusing to write history containing {banned!r}")
    history_path.write_text(blob + "\n", encoding="utf-8", newline="\n")


# --- the one request ---------------------------------------------------------


def run_native_activation_once(
    *,
    spec: SpokenRequest,
    credential: str,
    credential_class: str,
    credential_source: str,
    base_url: str,
    attempt_id: str,
    work_dir: Path,
    diagnostics_dir: Path,
    receipt: Dict[str, Any],
    route: str = PAYG_ACTIVATION_ROUTE,
    timeout_s: float = 600.0,
    transport: Optional[Any] = None,
) -> Dict[str, Any]:
    """One native HTTP T2A request for a short utterance. One request; no retry.

    ``receipt["request_transmitted"]`` is set the moment the request leaves this
    process -- before local audio processing -- so a later ffmpeg or QC failure
    can never make a transmitted request look untransmitted. A refusal always
    raises :class:`NativeTtsRefusal` with HTTP status, provider status code,
    provider message and trace id kept as separate fields.
    """
    import hashlib

    from process_utils import hidden_run  # noqa: E402

    from .audio import measure_audio, technical_qc

    if not host_is_documented_cn(base_url):
        raise SystemExit(
            f"refusing to send: {base_url!r} is not the documented CN host "
            f"({MINIMAX_CN_HOST}). This run does not guess an endpoint."
        )

    receipt["route"] = route
    receipt["request_target"] = {
        "host": normalize_host(base_url),
        "path": "/v1/t2a_v2",
        "transport": "native_http_cn",
        "route": route,
        "credential_class": credential_class,
        "credential_source": credential_source,
    }
    from .clone_route import billable_characters

    receipt["request_payload"] = {
        "fields": sorted(spec.payload.keys()),
        "model": spec.payload["model"],
        "text_sha256": hashlib.sha256(spec.payload["text"].encode()).hexdigest(),
        "text_billable_characters": billable_characters(spec.display_text),
        "voice_setting": dict(spec.payload["voice_setting"]),
        "voice_setting_voice_id_hash": hashlib.sha256(
            spec.voice_id.encode()
        ).hexdigest(),
        "audio_setting": dict(spec.payload["audio_setting"]),
        "output_format": spec.payload["output_format"],
        "stream": spec.payload["stream"],
        "pronunciation_rule_count": spec.pronunciation_rule_count,
    }

    work_dir.mkdir(parents=True, exist_ok=True)
    raw = work_dir / f"{attempt_id}-raw.wav"
    normalised = work_dir / f"{attempt_id}-normalised.wav"
    for stale in (raw, normalised):
        if stale.exists():
            stale.unlink()

    try:
        result = send_t2a_once(
            payload=spec.payload,
            credential=credential,
            base_url=base_url,
            timeout_s=timeout_s,
            transport=transport,
        )
    except NativeTtsRefusal as refusal:
        receipt["request_transmitted"] = True
        write_private_provider_response(
            diagnostics_dir,
            attempt_id,
            host=base_url,
            route=route,
            refusal=refusal,
        )
        raise

    receipt["request_transmitted"] = True
    write_private_provider_response(
        diagnostics_dir, attempt_id, host=base_url, route=route, result=result
    )

    raw.write_bytes(result.audio_bytes)
    hidden_run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw),
         "-af", f"loudnorm={LOUDNORM_TARGET}",
         "-ar", "44100", "-ac", "1", str(normalised)],
        timeout=600,
    )
    asset = (
        normalised
        if normalised.is_file() and normalised.stat().st_size > 1024
        else raw
    )

    h = hashlib.sha256()
    with asset.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    measured = measure_audio(asset)
    technical = technical_qc(asset, expected_sample_rate_hz=44100)
    receipt["audio"] = {
        "path": str(asset),
        "sha256": h.hexdigest(),
        "duration_s": measured.duration_s,
        "sample_rate_hz": measured.sample_rate_hz,
        "channels": measured.channels,
        "codec": measured.codec,
        "loudness_lufs": getattr(measured, "integrated_lufs", None),
        "technical_qc_approved": technical.get("approved"),
        "technical_qc": technical,
        "lexicon_applied": True,
        "spoken_text_sha256": hashlib.sha256(spec.spoken_text.encode()).hexdigest(),
    }
    receipt["provider_response"] = result.public_summary()
    return {
        "provider_receipt": {
            "provider": "minimax",
            "transport": "native_http_cn",
            "request_host": normalize_host(base_url),
            "route": route,
            "credential_class": credential_class,
            "credential_source": credential_source,
            "model": spec.model,
            "voice_id_hash": hashlib.sha256(spec.voice_id.encode()).hexdigest(),
            "trace_id": result.trace_id,
            "http_status": result.http_status,
            "provider_status_code": result.status_code,
            "usage_characters": result.usage_characters,
            "usage_voice_count": result.usage_voice_count,
            "loudnorm_target": LOUDNORM_TARGET,
            "technical_qc": technical,
            "human_review": "PENDING_FOUNDER_REVIEW",
            "production_ready": False,
        },
        "result": result,
    }


# --- PAYG activation policy --------------------------------------------------


def decide_payg_native_activation(
    *,
    payg_key_fingerprint: str,
    payg_key_is_payg_class: bool,
    voice_id_hash: str,
    voice_exists: bool,
    voice_window_remaining_s: Optional[float],
    cash_balance: Optional[float],
    credit_balance: Optional[float],
    voucher_balance: Optional[float],
    owed_amount: Optional[float],
    billable_character_count: int,
    previous_payg_refusal: bool,
    previous_subscription_refusal: bool,
    native_round_used: bool,
    prior_recovery_used: bool,
    exception_granted: bool,
    exception_consumed: bool,
    model: str = NATIVE_ROUND_MODEL,
    upload_count: int = 0,
    clone_count: int = 0,
) -> Dict[str, Any]:
    """This round's PAYG gate: the cash policy with a *new* single-use record.

    ``prior_recovery_used`` is carried as evidence, never as a blocker: the
    earlier recovery was consumed by an earlier attempt, and the Founder's new
    authorisation is an independent one. What blocks here is only this round's
    own single-use flag, its own scoped exception, and the unchanged structural
    gates (cash, ceiling, voice window, no upload/clone, no forbidden
    allowances). Nothing about the historical record is cleared or rewound.

    The authorisation and the exception are both built from the **granted**
    constants above, not from the caller's measurements, so the scope checks
    are real: a request for another voice, model or text length fails the
    authorisation's own scope instead of silently inheriting it.
    """
    authorisation = CashActivationAuthorisation(
        voice_id_hash=NATIVE_ROUND_VOICE_ID_HASH,
        max_cash_debit_cny=NATIVE_FIRST_ACTIVATION_CEILING_CNY,
    )
    exception = ExposedKeyException(
        granted=exception_granted,
        key_fingerprint=payg_key_fingerprint,
        voice_id_hash=NATIVE_ROUND_VOICE_ID_HASH,
        model=NATIVE_ROUND_MODEL,
        billable_characters=NATIVE_ROUND_BILLABLE_CHARACTERS,
        max_cash_debit_cny=NATIVE_FIRST_ACTIVATION_CEILING_CNY,
        granted_on="2026-10-12",
        consumed=exception_consumed,
        reason=(
            "The Founder granted a NEW independent authorisation on 2026-10-12 "
            "for one native-Host first-activation request through the known "
            "exposed pay-as-you-go key, accepting the exposure risk for this "
            "round, with a CNY 10.00 total cash ceiling. This is not the earlier "
            "consumed exception and does not restore it."
        ),
    )
    verdict = decide_cash_activation(
        authorisation,
        payg_key_fingerprint=payg_key_fingerprint,
        payg_key_is_payg_class=payg_key_is_payg_class,
        voice_id_hash=voice_id_hash,
        voice_exists=voice_exists,
        voice_window_remaining_s=voice_window_remaining_s,
        cash_balance=cash_balance,
        credit_balance=credit_balance,
        voucher_balance=voucher_balance,
        owed_amount=owed_amount,
        billable_characters=billable_character_count,
        previous_payg_refusal=previous_payg_refusal,
        previous_subscription_refusal=previous_subscription_refusal,
        cash_recovery_used=native_round_used,
        exception=exception,
        model=model,
        upload_count=upload_count,
        clone_count=clone_count,
    )
    return {
        "route": PAYG_ACTIVATION_ROUTE,
        "authorisation": FOUNDER_AUTHORISED_NATIVE_FIRST_ACTIVATION,
        "exposed_key_exception_name": FOUNDER_AUTHORISED_EXPOSED_KEY_REUSE,
        "authorised": verdict.authorised,
        "status": verdict.status,
        "refusals": list(verdict.refusals),
        "reasons": list(verdict.reasons),
        "projected_total_cny": verdict.projected_total_cny,
        "ceiling_cny": str(NATIVE_FIRST_ACTIVATION_CEILING_CNY),
        "prior_recovery_used": prior_recovery_used,
        "prior_attempts_note": (
            "the three earlier attempts and their consumed authorisations are "
            "historical facts; prior_recovery_used is recorded and does NOT "
            "block this independent authorisation"
        ),
        "verdict": verdict.as_dict(),
    }


# --- M Plan narration policy -------------------------------------------------


def decide_mplan_native(
    *,
    credential_class: str,
    credential_source: str,
    guard_verdict: str,
    guard_reasons: Optional[list] = None,
    quota: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """This round's Subscription-route gate. No PAYG credential can pass it.

    The two refusals that matter: a credential that is not a Subscription Key
    (so a PAYG key can never be substituted for narration), and a billing
    verdict that is not ``SAFE_INCLUDED_PLAN``. A non-zero Credit Pack balance
    is part of that verdict because it is the only paid fund a Subscription Key
    can touch, and this project requires plan-quota-only usage.
    """
    refusals: list = []
    reasons: list = []
    if credential_class != CREDENTIAL_SUBSCRIPTION:
        refusals.append("MPLAN_REQUIRES_SUBSCRIPTION_KEY")
        reasons.append(
            f"credential class is {credential_class}, not a Subscription Key; a "
            "pay-as-you-go key would bill cash and can never carry narration"
        )
    if guard_verdict != SAFE_INCLUDED_PLAN:
        refusals.append("MPLAN_BILLING_NOT_PROVEN")
        reasons.append(
            f"BillingGuard verdict is {guard_verdict or 'UNKNOWN'}, not "
            f"{SAFE_INCLUDED_PLAN}: " + "; ".join(guard_reasons or [])
        )
    if quota is None:
        refusals.append("MPLAN_QUOTA_UNREADABLE")
        reasons.append("plan quota could not be read")
    else:
        for window in ("interval_remaining_percent", "weekly_remaining_percent"):
            value = quota.get(window)
            if value is None:
                refusals.append("MPLAN_QUOTA_UNREADABLE")
                reasons.append(f"{window} is unknown")
            elif float(value) <= 0:
                refusals.append("MPLAN_QUOTA_EXHAUSTED")
                reasons.append(f"{window} is exhausted ({value})")
    return {
        "route": MPLAN_NARRATION_ROUTE,
        "authorised": not refusals,
        "refusals": refusals,
        "reasons": reasons,
        "credential_class": credential_class,
        "credential_source": credential_source,
        "billing_verdict": guard_verdict,
    }


def classify_mplan_only(
    *,
    quota_before: Optional[Dict[str, Any]],
    quota_after: Optional[Dict[str, Any]],
    deltas: Dict[str, Any],
) -> Dict[str, Any]:
    """Was this request's usage carried by plan quota alone?

    Two admissible proofs and one honest unknown:

    ``QUOTA_DELTA``
        a plan window measured lower after the request than before it.
    ``EXCLUSION_CHAIN``
        no paid fund moved (cash, voucher, credit, owed all unchanged), the
        Credit Pack balance was zero before and after, and the request
        succeeded on a Subscription Key -- which per the official FAQ can draw
        on plan quota and Credit Packs only. With the Credit Pack at zero, the
        only chain left that the provider documents is plan quota.
    ``INCONCLUSIVE``
        neither of the above. Quota percentages are integers and a short
        utterance can move them by less than a point, which is exactly why a
        flat percentage is *not* treated as failure either: it falls to the
        exclusion chain, and only if that also fails does this become
        ``M_PLAN_ONLY_VERIFICATION_PENDING``.
    """
    paid_moved = []
    for name in ("cash_balance", "voucher_balance", "credit_balance", "owed_amount"):
        row = deltas.get(name) or {}
        if row.get("decreased") or row.get("increased"):
            paid_moved.append(name)

    quota_moved = False
    windows = ("interval_remaining_percent", "weekly_remaining_percent")
    if quota_before and quota_after:
        quota_moved = any(
            quota_before.get(w) is not None
            and quota_after.get(w) is not None
            and float(quota_after[w]) < float(quota_before[w])
            for w in windows
        )

    credit_after = (deltas.get("credit_balance") or {}).get("after")
    owed_after = (deltas.get("owed_amount") or {}).get("after")

    if paid_moved:
        return {
            "verified": False,
            "status": "MPLAN_CHARGED_PAID_FUNDS",
            "basis": "PAID_FUND_MOVEMENT",
            "paid_funds_moved": paid_moved,
            "quota_moved": quota_moved,
        }
    if quota_moved:
        return {
            "verified": True,
            "status": "M_PLAN_ONLY_VERIFIED",
            "basis": "QUOTA_DELTA",
            "quota_before": quota_before,
            "quota_after": quota_after,
        }
    credit_zero = credit_after is not None and Decimal(str(credit_after)) == 0
    owed_zero = owed_after is not None and Decimal(str(owed_after)) == 0
    if credit_zero and owed_zero:
        return {
            "verified": True,
            "status": "M_PLAN_ONLY_VERIFIED",
            "basis": "EXCLUSION_CHAIN",
            "note": (
                "no paid fund moved; Credit Pack was zero before and after; the "
                "request succeeded on a Subscription Key, whose documented "
                "deduction chain is plan quota -> credit packs only, so plan "
                "quota is the only chain left. Quota percentages are integers "
                "and a short utterance can round below one point, which is why "
                "a flat percentage is not treated as failure."
            ),
            "quota_before": quota_before,
            "quota_after": quota_after,
        }
    return {
        "verified": False,
        "status": "M_PLAN_ONLY_VERIFICATION_PENDING",
        "basis": "INCONCLUSIVE",
        "quota_before": quota_before,
        "quota_after": quota_after,
        "note": "neither a quota delta nor a clean exclusion chain is available",
    }


def classify_payg_outcome(
    *,
    audio_ok: bool,
    cash_debit: Optional[Decimal],
    anomalies: list,
    ceiling_cny: Decimal = NATIVE_FIRST_ACTIVATION_CEILING_CNY,
) -> str:
    """The activation outcome, with the recovery round's exact semantics.

    Audio without a measured cash movement is **not** activation: producing
    sound does not prove the one-time fee was collected.
    """
    if anomalies:
        return "SEVERE_ANOMALY"
    if audio_ok and cash_debit is not None and cash_debit <= ceiling_cny:
        return "SUCCESS_ACTIVATED_CASH"
    if audio_ok:
        return "TTS_SUCCESS_BILLING_UNVERIFIED"
    return "ACTIVATION_FAILED"
