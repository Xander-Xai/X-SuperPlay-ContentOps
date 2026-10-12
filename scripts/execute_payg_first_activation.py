"""``PAYG_FIRST_ACTIVATION_NATIVE`` -- one new, independent first-activation. Issue #34.

The Founder's authorisation for THIS round (2026-10-12)
-------------------------------------------------------
- one real first-activation synthesis of the existing ``founder_primary_v1``
- through the currently configured pay-as-you-go key -- the known exposed one.
  The Founder accepted that risk for this round and did not require rotation
  first.
- existing cash only; total actual cash debit <= CNY 10.00 (the CNY 9.90
  one-time voice fee plus the activation synthesis's character cost)
- no recharge, no Credit Pack consumption, no voucher consumption, no debt
- no re-upload of the WAV, no re-creation of the clone
- exactly ONE provider request; no automatic retry

This is a **new independent authorisation**. The three earlier attempts and
their consumed authorisations remain recorded exactly as they were: this script
never clears ``cash_recovery_used``, never rewinds the consumed exception, and
appends to the same append-only history. Its own single-use flags live under
separate registry names (``native_first_activation_used``,
``native_first_activation_exception_consumed``).

The one engineering correction this round carries
-------------------------------------------------
The first three attempts were sent by the official CLI, which resolves request
auth from ``--api-key``/OAuth/``~/.mmx/config.json`` and never from the
environment variable the earlier rounds injected. All three therefore
authenticated with the config-file Subscription Key. This script sends through
:mod:`contentops.media.minimax_native_tts` -- native HTTP, the documented CN
host pinned, the authorised PAYG credential passed explicitly into the one
``Authorization`` header. The CLI is not in this request path at all.

Dry run by default. ``--execute`` sends the one authorised request.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.media.cash_activation_recovery import (  # noqa: E402
    EXPOSED_PAYG_KEY_NOT_ROTATED,
    FOUNDER_AUTHORISED_EXPOSED_KEY_REUSE,
    key_fingerprint,
    payg_key_is_exposed,
)
from contentops.media.clone_route import (  # noqa: E402
    ACTIVATION_TEXT,
    CLONE_TTL_SECONDS,
    SPEECH_2_8_HD_CNY_PER_10K,
    billable_characters,
)
from contentops.media.credentials import (  # noqa: E402
    CREDENTIAL_PAYG,
    load_local_env_file,
    resolve_clone_credential,
    resolve_credential,
)
from contentops.media.minimax_native_tts import (  # noqa: E402
    MINIMAX_CN_HOST,
    NativeTtsRefusal,
    host_is_documented_cn,
    normalize_host,
)
from contentops.media.native_rounds import (  # noqa: E402
    FOUNDER_AUTHORISED_NATIVE_FIRST_ACTIVATION,
    NATIVE_FIRST_ACTIVATION_CEILING_CNY,
    NATIVE_ROUND_VOICE_ID_HASH,
    PAYG_ACTIVATION_ROUTE,
    append_activation_history,
    build_spoken_request,
    classify_payg_outcome,
    decide_payg_native_activation,
    delta_money,
    read_money,
    run_native_activation_once,
)

ROUND_NAME = "PAYG_FIRST_ACTIVATION_NATIVE"

VOICE_ID = "founder_primary_v1"
#: The granted scope's voice digest, imported so the script and the gate cannot
#: drift apart about which voice the authorisation covers.
VOICE_ID_HASH = NATIVE_ROUND_VOICE_ID_HASH
MODEL = "speech-2.8-hd"
SAMPLE_SHA256 = (
    "bb56d052cd637bd8a369f6e37a745c7609de9988ada0fa0827d4d5c59035df8d"
)
CEILING_CNY = NATIVE_FIRST_ACTIVATION_CEILING_CNY

PRIVATE_REGISTRY = ROOT / ".private" / "founder-voice.json"
PRIVATE_DIAGNOSTICS = ROOT / ".private" / "diagnostics"
WORK = ROOT / ".verify-tmp" / "m34-payg-native-activation"
RECEIPT = (
    ROOT
    / "projects/easel-enhanced-golden/receipts"
    / "founder-voice-payg-first-activation-receipt.json"
)
HISTORY_RECEIPT = (
    ROOT
    / "projects/easel-enhanced-golden/receipts"
    / "founder-voice-activation-history.json"
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _activate_once(*, payg, receipt: Dict[str, Any]) -> Dict[str, Any]:
    """One native HTTP T2A call, via the shared runner. One request; no retry."""
    from contentops.media.lexicon import default_zh_lexicon

    lexicon = default_zh_lexicon()
    spec = build_spoken_request(
        display_text=ACTIVATION_TEXT,
        voice_id=VOICE_ID,
        model=MODEL,
        lexicon=lexicon,
    )
    return run_native_activation_once(
        spec=spec,
        credential=payg.key,
        credential_class=payg.credential_class,
        credential_source=payg.source,
        base_url=MINIMAX_CN_HOST,
        attempt_id=str(receipt["attempt_id"]),
        work_dir=WORK,
        diagnostics_dir=PRIVATE_DIAGNOSTICS,
        receipt=receipt,
        route=PAYG_ACTIVATION_ROUTE,
    )


def _f(value: Any) -> Optional[float]:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _write(receipt: Dict[str, Any]) -> None:
    receipt["finished_at"] = _now()
    blob = json.dumps(receipt, ensure_ascii=False)
    for banned in ("Authorization", "Bearer ", "sk-cp-", "sk-api-"):
        if banned in blob:
            raise SystemExit(f"refusing to write a receipt containing {banned!r}")
    RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    RECEIPT.write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {RECEIPT.relative_to(ROOT).as_posix()}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="send the one authorised request. Without this, "
                             "nothing is transmitted.")
    parser.add_argument(
        "--authorised-exposed-key-reuse",
        action="store_true",
        help=(
            "The Founder granted a NEW independent authorisation on 2026-10-12 "
            "for one native first-activation request through the known exposed "
            "pay-as-you-go key, accepting the risk for this round. Grants a "
            "single-use, scope-limited exception so the exposed-key gate permits "
            "one spend. It does not rotate the key, does not change "
            "payg_key_is_exposed(), and exposed_key stays true in the receipt."
        ),
    )
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    load_local_env_file(ROOT / ".env")
    base_url = MINIMAX_CN_HOST
    attempt_id = f"paygact-{uuid.uuid4().hex[:12]}"

    payg = resolve_clone_credential()
    sub = resolve_credential()
    payg_fp = key_fingerprint(payg.key)
    exposed = payg_key_is_exposed(payg.key)

    registry: Dict[str, Any] = {}
    if PRIVATE_REGISTRY.is_file():
        registry = json.loads(PRIVATE_REGISTRY.read_text(encoding="utf-8"))
    voice_ok = registry.get("provider_voice_id") == VOICE_ID
    created_unix = float(registry.get("created_at_unix") or 0)
    remaining_s = (
        (CLONE_TTL_SECONDS - (time.time() - created_unix)) if created_unix else None
    )
    prior_recovery_used = bool(registry.get("cash_recovery_used"))
    native_round_used = bool(registry.get("native_first_activation_used"))
    exception_consumed = bool(
        registry.get("native_first_activation_exception_consumed")
    )

    configured_env = ""
    for name in ("CONTENTOPS_MINIMAX_BASE_URL", "MINIMAX_VOICE_CLONE_BASE_URL"):
        value = os.environ.get(name, "").strip()
        if value:
            configured_env = value
            break
    configured_norm = normalize_host(configured_env) if configured_env else ""

    before = read_money(base_url, payg.key)
    chars = billable_characters(ACTIVATION_TEXT)

    decision = decide_payg_native_activation(
        payg_key_fingerprint=payg_fp,
        payg_key_is_payg_class=payg.credential_class == CREDENTIAL_PAYG,
        voice_id_hash=VOICE_ID_HASH,
        voice_exists=voice_ok,
        voice_window_remaining_s=remaining_s,
        cash_balance=_f(before["balances"].get("cash_balance")),
        credit_balance=_f(before["balances"].get("credit_balance")),
        voucher_balance=_f(before["balances"].get("voucher_balance")),
        owed_amount=_f(before["balances"].get("owed_amount")),
        billable_character_count=chars,
        previous_payg_refusal=bool(registry.get("activation_refused")),
        previous_subscription_refusal=bool(
            registry.get("subscription_activation_probes")
        ),
        native_round_used=native_round_used,
        prior_recovery_used=prior_recovery_used,
        exception_granted=bool(args.authorised_exposed_key_reuse),
        exception_consumed=exception_consumed,
        model=MODEL,
        upload_count=0,
        clone_count=0,
    )

    receipt: Dict[str, Any] = {
        "schema": "contentops.payg-first-activation/v1",
        "round": ROUND_NAME,
        "attempt_id": attempt_id,
        "issue": "#34",
        "started_at": _now(),
        "executed": bool(args.execute),
        "route": PAYG_ACTIVATION_ROUTE,
        "authorisation": {
            "name": FOUNDER_AUTHORISED_NATIVE_FIRST_ACTIVATION,
            "granted_on": "2026-10-12",
            "granted_by": "FOUNDER",
            "scope": {
                "voice_id_hash": VOICE_ID_HASH,
                "model": MODEL,
                "credential": "the configured MINIMAX_CLONE_KEY (exposed; risk accepted)",
                "billable_characters": chars,
                "max_cash_debit_cny": str(CEILING_CNY),
                "provider_requests": 1,
                "upload": 0,
                "clone": 0,
                "automatic_retry": False,
            },
            "note": (
                "new independent authorisation; it does not restore, replace or "
                "clear any earlier attempt or consumed authorisation"
            ),
        },
        "voice_id": VOICE_ID,
        "voice_id_hash": VOICE_ID_HASH,
        "voice_sample_sha256": SAMPLE_SHA256,
        "clone_reused": True,
        "reupload_count": 0,
        "reclone_count": 0,
        "model": MODEL,
        "text": ACTIVATION_TEXT,
        "billable_characters": chars,
        "rate_cny_per_10k_chars": str(SPEECH_2_8_HD_CNY_PER_10K),
        "character_cost_cny": f"{Decimal(SPEECH_2_8_HD_CNY_PER_10K) * chars / 10000:.6f}",
        "one_time_activation_cny": "9.90",
        "max_cash_debit_cny": str(CEILING_CNY),
        "payg_key_fingerprint": payg_fp,
        "payg_key_exposed": exposed,
        "exposed_key_exception": FOUNDER_AUTHORISED_EXPOSED_KEY_REUSE,
        "exposed_key_exception_granted": bool(args.authorised_exposed_key_reuse),
        "exposed_key_exception_applied": bool(
            decision.get("verdict", {})
            .get("evidence", {})
            .get("exposed_key_exception_applied")
        ),
        "key_rotation_note": (
            "The key is NOT rotated. exposed_key stays true. This exception is the "
            "Founder's acceptance of the risk for THIS one request only; rotation "
            "remains the standing recommendation."
        ),
        "subscription_key_class": sub.credential_class,
        "keys_distinct": bool(payg.key) and bool(sub.key) and payg.key != sub.key,
        "hosts": {
            "activation_host": MINIMAX_CN_HOST,
            "balance_query_host": MINIMAX_CN_HOST,
            "configured_env_host": configured_norm or None,
            "configured_env_matches": (
                None
                if not configured_norm
                else host_is_documented_cn(configured_norm)
            ),
            "why": (
                "the activation request and its balance evidence address the same "
                "documented CN host; the native adapter refuses any other origin "
                "before the transport is touched"
            ),
        },
        "prior_records": {
            "prior_records_note": (
                "historical facts, recorded and preserved; none of them is cleared"
            ),
            "first_activation_refusal": {
                "at": registry.get("activation_refused_at"),
                "provider_message": registry.get("activation_refusal_provider_message"),
            },
            "subscription_probe_count": len(
                registry.get("subscription_activation_probes") or []
            ),
            "cash_recovery_used": prior_recovery_used,
            "exposed_key_exception_consumed": bool(
                registry.get("exposed_key_exception_consumed")
            ),
        },
        "money_before": before,
        "window_remaining_h": None
        if remaining_s is None
        else round(remaining_s / 3600, 2),
        "provider_call_budget": {
            "activation_tts": 1,
            "upload": 0,
            "clone": 0,
            "automatic_retry": 0,
        },
        "activation_attempts": 0,
        "upload_count": 0,
        "clone_count": 0,
        "retries_performed": 0,
        "decision": decision,
        "notes": [],
    }

    print(f"=== {ROUND_NAME} ===")
    print(f"  attempt_id        : {attempt_id}")
    print(f"  authorisation     : {FOUNDER_AUTHORISED_NATIVE_FIRST_ACTIVATION}")
    print(f"  voice_id          : {VOICE_ID} (sha256 {VOICE_ID_HASH[:16]}...)")
    print(f"  clone reused      : TRUE -- reupload_count=0, reclone_count=0")
    print(f"  window remaining  : {receipt['window_remaining_h']} h of 168 h")
    print(f"  activation key    : {payg.credential_class} ({payg.source}) "
          f"fingerprint={payg_fp} exposed={exposed}")
    print(f"  transport         : native_http_cn -> {MINIMAX_CN_HOST}/v1/t2a_v2")
    print(f"  configured env host: {configured_norm or '(unset)'} "
          f"(matches adapter host: {receipt['hosts']['configured_env_matches']})")
    print(f"  model / text      : {MODEL} / {ACTIVATION_TEXT}")
    print(f"  billable chars    : {chars} -> CNY {receipt['character_cost_cny']}")
    print(f"  projected total   : CNY {decision['projected_total_cny']} "
          f"(ceiling CNY {CEILING_CNY})")
    print()
    print("=== BALANCES BEFORE (read-only, CN host, PAYG key) ===")
    print(f"  {json.dumps(before['balances'], ensure_ascii=False)}")
    print()
    print(f"=== GATE: {decision['status']} ===")
    print(f"  authorised : {decision['authorised']}")
    print(f"  refusals   : {', '.join(decision['refusals']) or '(none)'}")
    for reason in decision["reasons"]:
        print(f"  - {reason}")
    print()

    if not decision["authorised"]:
        append_activation_history(HISTORY_RECEIPT, attempt_id, {
            "at": _now(), "outcome": "REFUSED_PRECHECK",
            "round": ROUND_NAME, "route": PAYG_ACTIVATION_ROUTE,
            "refusals": decision["refusals"], "charged_cny": "0.00",
            "money_before": before["balances"],
        })
        _write(receipt)
        print("NOTHING WAS SENT. No charge was attempted.")
        if EXPOSED_PAYG_KEY_NOT_ROTATED in decision["refusals"]:
            print()
            print("STOP: the exposed-key gate is closed.")
            print("The Founder's new authorisation accepts the exposure for this")
            print("one request; pass --authorised-exposed-key-reuse only when that")
            print("authorisation is actually in force.")
        return 1

    if not args.execute:
        _write(receipt)
        print("=== DRY RUN. NOTHING WAS SENT. ===")
        print(f"  one speech-2.8-hd synthesis, voice={VOICE_ID}, PAYG key,")
        print(f"  projected CNY {decision['projected_total_cny']}, no upload, "
              f"no clone, no retry.")
        return 0

    # --- the one authorised request ------------------------------------------
    receipt["activation_attempts"] = 1
    receipt["request_started_at"] = _now()
    receipt["request_transmitted"] = False
    print("=== ONE REAL ACTIVATION SYNTHESIS (PAYG key, speech-2.8-hd) ===")
    audio_ok = False
    status: Dict[str, Any] = {"status_code": None, "message": ""}
    provider_receipt: Dict[str, Any] = {}
    try:
        outcome = _activate_once(payg=payg, receipt=receipt)
        audio_ok = True
        summary = receipt.get("provider_response") or {}
        status = {
            "status_code": summary.get("base_resp", {}).get("status_code", 0),
            "status_meaning": "success",
            "http_status": summary.get("http_status"),
            "trace_id": summary.get("trace_id"),
            "usage_characters": summary.get("usage_characters"),
            "usage_voice_count": summary.get("usage_voice_count"),
        }
        provider_receipt = outcome["provider_receipt"]
        print(f"  audio: {receipt['audio']['path']}")
        print(f"  sha256: {receipt['audio']['sha256']}")
        print(f"  trace_id: {status['trace_id']}")
        print(f"  usage_characters: {status['usage_characters']}  "
              f"usage_voice_count: {status['usage_voice_count']}")
    except NativeTtsRefusal as refusal:
        status = {
            **refusal.structured(),
            "status_meaning": (
                "provider refused" if refusal.provider_status_code is not None
                else refusal.code
            ),
        }
        receipt["failure_tail"] = " ".join(str(refusal).split())[:400]
        print(f"  REFUSED ({status['refusal_code']}): "
              f"HTTP {status['http_status']} / provider status "
              f"{status['provider_status_code']}: {status['provider_status_msg']}")
        if status.get("trace_id"):
            print(f"  trace_id: {status['trace_id']}")
    except Exception as exc:  # noqa: BLE001 - reported, never retried
        text = str(exc)
        transmitted = bool(receipt.get("request_transmitted"))
        status = {
            "status_code": None,
            "message": " ".join(text.split())[:300],
            "transmitted": transmitted,
        }
        receipt["failure_tail"] = text[-400:]
        where = "after transmission" if transmitted else "local, before transmission"
        print(f"  FAILED ({where}): {status['message']}")
    receipt["request_finished_at"] = _now()
    receipt["provider_status"] = status
    receipt["error_taxonomy"] = {
        "http_status": status.get("http_status"),
        "provider_status_code": status.get("provider_status_code"),
        "provider_status_msg": status.get("provider_status_msg"),
        "trace_id": status.get("trace_id"),
        "cli_exit_code": None,
        "cli_exit_code_note": (
            "not applicable: this round uses the native HTTP transport; the CLI "
            "is not in the request path"
        ),
        "local_precheck": "decide_payg_native_activation",
        "transport": "native_http_cn",
    }

    after = read_money(base_url, payg.key)
    deltas = delta_money(before, after)
    receipt["money_after"] = after
    receipt["deltas"] = deltas

    cash_row = deltas.get("cash_balance") or {}
    actual: Optional[str] = None
    if cash_row.get("decreased"):
        actual = str(-Decimal(str(cash_row["delta"])))
    receipt["actual_cash_debit_cny"] = actual

    anomalies = [
        name
        for name in ("voucher_balance", "credit_balance", "owed_amount")
        if (deltas.get(name) or {}).get("decreased")
        or (deltas.get(name) or {}).get("increased")
    ]
    if actual is not None and Decimal(str(actual)) > CEILING_CNY:
        anomalies.append("cash_debit_over_ceiling")
    receipt["unexpected_balance_movements"] = anomalies

    outcome_kind = classify_payg_outcome(
        audio_ok=audio_ok,
        cash_debit=None if actual is None else Decimal(str(actual)),
        anomalies=anomalies,
        ceiling_cny=CEILING_CNY,
    )
    receipt["outcome"] = outcome_kind
    receipt["voice_activated"] = outcome_kind == "SUCCESS_ACTIVATED_CASH"
    if anomalies:
        receipt["notes"].append(
            "SEVERE_ANOMALY: " + ", ".join(anomalies)
            + ". A charged request must move cash and only cash, within the ceiling."
        )
    if outcome_kind == "TTS_SUCCESS_BILLING_UNVERIFIED":
        receipt["notes"].append(
            "Audio returned but no cash movement proves the one-time fee was "
            "charged. Activation is NOT claimed: audio output is not proof of "
            "payment. No further provider request may be sent until this is "
            "checked against the provider's billing record."
        )

    print()
    print("=== MEASURED ===")
    print(f"  {json.dumps(deltas, ensure_ascii=False)}")
    print()
    print(f"=== OUTCOME: {outcome_kind} ===")
    print(f"  actual cash debit : {actual}")
    print(f"  anomalies         : {anomalies or '(none)'}")
    print(f"  voice_activated   : {receipt['voice_activated']}")
    if outcome_kind == "TTS_SUCCESS_BILLING_UNVERIFIED":
        print("  activation NOT claimed -- audio is not proof of payment.")

    append_activation_history(HISTORY_RECEIPT, attempt_id, {
        "at": _now(), "outcome": outcome_kind,
        "round": ROUND_NAME, "route": PAYG_ACTIVATION_ROUTE,
        "transport": "native_http_cn",
        "credential_class": payg.credential_class,
        "credential_source": payg.source,
        "request_host": MINIMAX_CN_HOST,
        "request_transmitted": bool(receipt.get("request_transmitted")),
        "provider_status": status,
        "cash_debit_cny": actual,
        "usage_voice_count": status.get("usage_voice_count"),
        "money_before": before["balances"],
        "money_after": after["balances"],
        "anomalies": anomalies,
    })

    if receipt.get("request_transmitted"):
        registry["native_first_activation_used"] = True
        registry["native_first_activation_attempt_id"] = attempt_id
        registry["native_first_activation_outcome"] = outcome_kind
        registry["native_first_activation_at"] = _now()
        registry["native_first_activation_exception_consumed"] = True
        registry["native_first_activation_exception_consumed_at"] = _now()
        if receipt["voice_activated"]:
            registry["activated"] = True
            registry["activated_at"] = _now()
            registry["activation_attempt_id"] = attempt_id
            registry["activation_fee_cny"] = actual
            registry["activation_payment_source"] = "CASH"
    else:
        registry.setdefault("locally_blocked_attempts", []).append({
            "attempt_id": attempt_id,
            "at": _now(),
            "reason": "blocked by a local gate before any provider request",
            "charged_cny": "0.00",
        })
        receipt["note_on_consumption"] = (
            "no provider request was transmitted, so this round's single-use "
            "authorisation and exception remain unconsumed."
        )
        print("  no provider request was transmitted; authorisation NOT consumed")
    PRIVATE_REGISTRY.write_text(
        json.dumps(registry, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8", newline="\n",
    )

    receipt["provider_receipt"] = provider_receipt
    _write(receipt)
    return 0 if receipt["voice_activated"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
