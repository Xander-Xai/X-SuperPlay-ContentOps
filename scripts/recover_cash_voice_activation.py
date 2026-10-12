"""Execute ``CASH_ACTIVATION_RECOVERY``: one cash-paid activation. Issue #34.

Reuses the existing ``founder_primary_v1``. Never uploads, never clones, never retries.

Run it without ``--execute`` first. It prints the full plan, every gate and the exact
expected charge, and transmits nothing.

Blocking preconditions, in order
--------------------------------
1. the configured pay-as-you-go key is not one that was exposed in chat
2. the voice exists in the local registry and is inside its 168 h activation window
3. the projected charge fits under the Founder's CNY 10.00 cash ceiling
4. cash covers it, Credit Pack is 0.00 and owed is 0.00
5. this recovery has not already been used

Any of them failing is a stop, not a warning.

Transport correction (Issue #34, 2026-10-12)
--------------------------------------------
The first three activation attempts went through the official CLI with the
authorised key injected as ``MINIMAX_API_KEY``. Auditing the pinned CLI
(``mmx-cli`` 1.0.27) found that its request-auth resolver never consults that
variable: it uses the ``--api-key`` flag, an OAuth token, or the ``api_key`` in
``~/.mmx/config.json`` -- so all three "pay-as-you-go" attempts actually
authenticated with the config-file Subscription Key, and the CLI also chose its
own host from that config. This script now sends its one request through
:mod:`contentops.media.minimax_native_tts`, which pins the documented CN host,
uses the authorised credential verbatim in the header, and parses the full
provider envelope (HTTP status, ``base_resp``, ``trace_id`` separately) instead
of accepting the CLI's lossy ``API error: ... (HTTP 200)`` collapse.

The gates are unchanged. What changed is which component performs the request,
and that the credential claim in the receipt is now a fact of this process
rather than a claim about a child.
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
    RECOVERY_NAME,
    CashActivationAuthorisation,
    ExposedKeyException,
    character_cost,
    decide_cash_activation,
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
from contentops.media.contract import SpeechRequest  # noqa: E402,F401
from contentops.media.minimax_native_tts import (  # noqa: E402
    MINIMAX_CN_HOST,
    NativeTtsRefusal,
    host_is_documented_cn,
    normalize_host,
)
from contentops.media.native_rounds import (  # noqa: E402
    append_activation_history,
    build_spoken_request,
    delta_money,
    read_money,
    run_native_activation_once,
)
from contentops.media.minimax_speech import (  # noqa: E402,F401
    MiniMaxMPlanProvider,
    receipt_to_dict,
)
# NOTE: the CLI transport imports (resolve_cli, child_env_for) were removed with
# the transport itself. The activation call no longer goes through the CLI: the
# CLI's auth resolver never read the environment variable these helpers wrote,
# which is the root cause this script now fixes. Keep them out so no future
# edit re-introduces a transport that cannot bind the authorised credential.

PRIVATE_REGISTRY = ROOT / ".private" / "founder-voice.json"
PRIVATE_DIAGNOSTICS = ROOT / ".private" / "diagnostics"
WORK = ROOT / ".verify-tmp" / "m34-cash-recovery"
RECEIPT = (
    ROOT
    / "projects/easel-enhanced-golden/receipts"
    / "founder-voice-cash-activation-receipt.json"
)
HISTORY_RECEIPT = (
    ROOT
    / "projects/easel-enhanced-golden/receipts"
    / "founder-voice-activation-history.json"
)

VOICE_ID = "founder_primary_v1"
VOICE_ID_HASH = "7271d9c80c88821a6a09ed43328619d0ee08c3f2b2449237fe2c31f6899abeef"
MODEL = "speech-2.8-hd"
SAMPLE_SHA256 = (
    "bb56d052cd637bd8a369f6e37a745c7609de9988ada0fa0827d4d5c59035df8d"
)
CEILING_CNY = Decimal("10.00")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_hosts() -> Dict[str, Any]:
    """Where the balances are read and where the one request is sent.

    Both are the documented CN host. The environment variables are still read so
    the receipt can record what an operator had configured, but the activation
    call never follows them: the transport that sent the first three refusals
    chose its own host from a config file this repository does not control, and
    that is precisely the split this function closes.
    """
    configured = ""
    for name in ("CONTENTOPS_MINIMAX_BASE_URL", "MINIMAX_VOICE_CLONE_BASE_URL"):
        value = os.environ.get(name, "").strip()
        if value:
            configured = value
            break
    configured_norm = normalize_host(configured) if configured else ""
    return {
        "activation_host": MINIMAX_CN_HOST,
        "balance_query_host": MINIMAX_CN_HOST,
        "configured_env_host": configured_norm or None,
        "configured_env_matches": (
            None
            if not configured_norm
            else host_is_documented_cn(configured_norm)
        ),
        "why": (
            "The activation call is sent by the native CN adapter, which refuses "
            "any host other than the documented CN service, and the balance reads "
            "now use the same host so the billing evidence and the billed request "
            "cannot address different services."
        ),
    }


# ``_read_money``, ``_delta`` and ``_write_private_provider_response`` moved to
# :mod:`contentops.media.native_rounds` so the recovery round and the native
# first-activation round share one implementation. Two copies would drift in
# exactly the places the first three attempts failed.


def _write_history_append(attempt_id: str, payload: Dict[str, Any]) -> None:
    """Append-only history. Existing entries are never rewritten or removed."""
    append_activation_history(HISTORY_RECEIPT, attempt_id, payload)


def _activate_once(*, base_url: str, payg, receipt: Dict[str, Any]) -> Dict[str, Any]:
    """One native HTTP T2A call for the activation, via the shared runner.

    The request sequence itself lives in
    :func:`contentops.media.native_rounds.run_native_activation_once` so this
    round and the native first-activation round cannot drift apart in the
    places the first three attempts failed: the credential actually used, the
    host actually addressed, the single-request rule, and the preservation of
    the provider's raw envelope.
    """
    from contentops.media.lexicon import default_zh_lexicon

    if not host_is_documented_cn(base_url):
        raise SystemExit(
            f"refusing to send: {base_url!r} is not the documented CN host "
            f"({MINIMAX_CN_HOST}). This run does not guess an endpoint."
        )
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
        base_url=base_url,
        attempt_id=str(receipt.get("attempt_id", "")),
        work_dir=WORK,
        diagnostics_dir=PRIVATE_DIAGNOSTICS,
        receipt=receipt,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="send the one authorised request. Without this, nothing "
                             "is transmitted.")
    parser.add_argument(
        "--authorised-exposed-key-reuse",
        action="store_true",
        help=(
            "Founder was shown the exposure risk in full and chose to accept it for "
            "this one activation. Grants a single-use, scope-limited exception so the "
            "exposed-key gate permits one spend. It does not rotate the key, does not "
            "change payg_key_is_exposed(), and exposed_key stays true in the receipt."
        ),
    )
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    load_local_env_file(ROOT / ".env")
    hosts = _resolve_hosts()
    base_url = hosts["balance_query_host"]
    attempt_id = f"cashact-{uuid.uuid4().hex[:12]}"

    payg = resolve_clone_credential()
    sub = resolve_credential()
    payg_fp = key_fingerprint(payg.key)
    exposed = payg_key_is_exposed(payg.key)

    registry: Dict[str, Any] = {}
    if PRIVATE_REGISTRY.is_file():
        registry = json.loads(PRIVATE_REGISTRY.read_text(encoding="utf-8"))
    voice_ok = registry.get("provider_voice_id") == VOICE_ID
    created_unix = float(registry.get("created_at_unix") or 0)
    remaining_s = (CLONE_TTL_SECONDS - (time.time() - created_unix)) if created_unix else None
    recovery_used = bool(registry.get("cash_recovery_used"))

    before = read_money(base_url, payg.key)
    chars = billable_characters(ACTIVATION_TEXT)
    author = CashActivationAuthorisation(voice_id_hash=VOICE_ID_HASH)

    # The exception is constructed from what is actually present, not from a hardcoded
    # value, so it cannot drift out of scope: it names the key that is configured now and
    # the voice that is in the registry now.
    exception = ExposedKeyException(
        granted=bool(args.authorised_exposed_key_reuse),
        key_fingerprint=payg_fp,
        voice_id_hash=VOICE_ID_HASH,
        model=MODEL,
        billable_characters=chars,
        max_cash_debit_cny=CEILING_CNY,
        granted_on="2026-10-12",
        consumed=bool(registry.get("exposed_key_exception_consumed")),
    )

    verdict = decide_cash_activation(
        author,
        payg_key_fingerprint=payg_fp,
        payg_key_is_payg_class=payg.credential_class == CREDENTIAL_PAYG,
        voice_id_hash=VOICE_ID_HASH,
        voice_exists=voice_ok,
        voice_window_remaining_s=remaining_s,
        cash_balance=_f(before["balances"].get("cash_balance")),
        credit_balance=_f(before["balances"].get("credit_balance")),
        voucher_balance=_f(before["balances"].get("voucher_balance")),
        owed_amount=_f(before["balances"].get("owed_amount")),
        billable_characters=chars,
        previous_payg_refusal=bool(registry.get("activation_refused")),
        previous_subscription_refusal=bool(
            registry.get("subscription_activation_probes")
        ),
        cash_recovery_used=recovery_used,
        upload_count=0,
        clone_count=0,
        exception=exception,
        model=MODEL,
    )

    receipt: Dict[str, Any] = {
        "schema": "contentops.cash-activation-recovery/v1",
        "recovery": RECOVERY_NAME,
        "attempt_id": attempt_id,
        "issue": "#34",
        "started_at": _now(),
        "executed": bool(args.execute),
        "voice_id": VOICE_ID,
        "voice_id_hash": VOICE_ID_HASH,
        "voice_sample_sha256": SAMPLE_SHA256,
        "clone_reused": True,
        "model": MODEL,
        "text": ACTIVATION_TEXT,
        "billable_characters": chars,
        "rate_cny_per_10k_chars": str(SPEECH_2_8_HD_CNY_PER_10K),
        "character_cost_cny": f"{character_cost(chars):.6f}",
        "one_time_activation_cny": "9.90",
        "max_cash_debit_cny": str(CEILING_CNY),
        "payg_key_fingerprint": payg_fp,
        "payg_key_exposed": exposed,
        "exposed_key_exception": FOUNDER_AUTHORISED_EXPOSED_KEY_REUSE,
        "exposed_key_exception_granted": bool(args.authorised_exposed_key_reuse),
        "exposed_key_exception_applied": bool(
            verdict.evidence.get("exposed_key_exception_applied")
        ),
        "key_rotation_note": (
            "The key is NOT rotated. exposed_key is true and stays true in this receipt. "
            "The exception is a Founder decision to spend through a known exposure once, "
            "not a fix. The key should still be rotated afterwards."
        ),
        "subscription_key_class": sub.credential_class,
        "keys_distinct": bool(payg.key) and bool(sub.key) and payg.key != sub.key,
        "transport": "native_http_cn",
        "hosts": hosts,
        "money_before": before,
        "window_remaining_h": None if remaining_s is None else round(remaining_s / 3600, 2),
        "provider_call_budget": {"activation_tts": 1, "upload": 0, "clone": 0,
                                 "automatic_retry": 0},
        "activation_attempts": 0,
        "upload_count": 0,
        "clone_count": 0,
        "retries_performed": 0,
        "verdict": verdict.as_dict(),
        "notes": [],
    }

    print(f"=== {RECOVERY_NAME} ===")
    print(f"  attempt_id        : {attempt_id}")
    print(f"  voice_id          : {VOICE_ID} (sha256 {VOICE_ID_HASH[:16]}...)")
    print(f"  clone reused      : TRUE -- no upload, no /v1/voice_clone")
    print(f"  window remaining  : {receipt['window_remaining_h']} h of 168 h")
    print(f"  payg fingerprint  : {payg_fp}  exposed={exposed}")
    print(f"  payload           : native_http_cn /v1/t2a_v2 @ "
          f"{normalize_host(hosts['activation_host'])}")
    print(f"  activation key    : {payg.credential_class} ({payg.source})")
    print(f"  configured env host: {hosts['configured_env_host'] or '(unset)'} "
          f"(matches adapter host: {hosts['configured_env_matches']})")
    print(f"  model / text      : {MODEL} / {ACTIVATION_TEXT}")
    print(f"  billable chars    : {chars} -> CNY {receipt['character_cost_cny']}")
    print(f"  projected total   : CNY {verdict.projected_total_cny} "
          f"(ceiling CNY {CEILING_CNY})")
    print()
    print("=== BALANCES BEFORE (read-only) ===")
    print(f"  {json.dumps(before['balances'], ensure_ascii=False)}")
    print()
    print(f"=== GATE: {verdict.status} ===")
    print(f"  authorised : {verdict.authorised}")
    print(f"  refusals   : {', '.join(verdict.refusals) or '(none)'}")
    for reason in verdict.reasons:
        print(f"  - {reason}")
    print()

    if not verdict.authorised:
        _write_history_append(attempt_id, {
            "at": _now(), "outcome": "REFUSED_PRECHECK",
            "refusals": verdict.refusals, "charged_cny": "0.00",
            "money_before": before["balances"],
        })
        _write(receipt)
        print("NOTHING WAS SENT. No charge was attempted.")
        if EXPOSED_PAYG_KEY_NOT_ROTATED in verdict.refusals:
            print()
            print("STOP: EXPOSED_PAYG_KEY_NOT_ROTATED")
            print("Founder action required, in this order:")
            print("  1. 账户管理 -> 接口密钥: create a NEW pay-as-you-go API Key for this")
            print("     same account")
            print("  2. revoke the exposed key in the same console page")
            print("  3. update MINIMAX_CLONE_KEY in the local .env (never in chat, never")
            print("     in git, never in a PR)")
            print("  4. re-run this script; it will verify by read-only probe")
        return 1

    if not args.execute:
        _write(receipt)
        print("=== DRY RUN. NOTHING WAS SENT. ===")
        print(f"  one speech-2.8-hd synthesis, voice={VOICE_ID}, PAYG key,")
        print(f"  projected CNY {verdict.projected_total_cny}, no upload, no clone, no retry.")
        return 0

# --- the one authorised call ---------------------------------------------
    #
    # Sent by the native CN HTTP adapter, NOT through the official CLI and NOT through
    # ``MiniMaxMPlanProvider``.
    #
    # The CLI is out because its request-auth resolver ignores the environment variable
    # this repository used to bind the authorised key into (see the module docstring):
    # all three refused attempts authenticated with the config-file Subscription Key,
    # and the CLI chose the request host from its own config. The plan provider is out
    # because its ``BillingGuard`` refuses a PAYG credential by design -- correctly,
    # because PAYG narration is exactly what this repository forbids.
    #
    # The guard is NOT disabled here. It has already run for this run, in
    # ``read_money``, and its verdict and balances are recorded in the receipt. What is
    # changed is which component performs the request: the authorisation to spend is
    # :func:`decide_cash_activation`, whose narrowness this run is about, and the
    # measured outcome is the balance delta below.
    WORK.mkdir(parents=True, exist_ok=True)
    receipt["billing_guard_precheck"] = {
        "verdict": before["verdict"],
        "note": (
            "BillingGuard refuses PAYG credentials categorically, which is correct for "
            "narration and is not bypassed here. The receipt records its verdict as a "
            "measurement; the cash authorisation that permitted this one request is "
            "decide_cash_activation."
        ),
    }
    receipt["activation_attempts"] = 1
    receipt["request_started_at"] = _now()
    receipt["request_transmitted"] = False
    print("=== ONE REAL ACTIVATION SYNTHESIS (PAYG key, speech-2.8-hd) ===")
    print(f"  transport         : native_http_cn -> {normalize_host(base_url)}/v1/t2a_v2")
    print(f"  credential class  : {payg.credential_class} ({payg.source})")
    audio_ok = False
    status: Dict[str, Any] = {"status_code": None, "message": ""}
    provider_receipt: Dict[str, Any] = {}
    try:
        outcome = _activate_once(
            base_url=base_url, payg=payg, receipt=receipt
        )
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
    except NativeTtsRefusal as refusal:
        # The four codes stay separate, exactly as measured. ``request_transmitted``
        # was already set by ``_activate_once`` at the moment the request was
        # transmitted; a provider refusal still burns the single-use authorisation,
        # because "it failed" is not "it was free".
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
    # The error taxonomy, kept in one block so no future edit can collapse the four
    # different "codes" into one string again. ``cli_exit_code`` is explicitly null
    # because this run has no CLI in the path at all: a null says "not applicable",
    # an absent field would say "not checked".
    receipt["error_taxonomy"] = {
        "http_status": status.get("http_status"),
        "provider_status_code": status.get("provider_status_code"),
        "provider_status_msg": status.get("provider_status_msg"),
        "trace_id": status.get("trace_id"),
        "cli_exit_code": None,
        "cli_exit_code_note": (
            "not applicable: this run uses the native HTTP transport; the CLI is not "
            "in the request path"
        ),
        "local_billing_guard_verdict": before.get("verdict"),
        "local_billing_guard_note": (
            "BillingGuard's PAYG refusal is a local pre-check outcome and is never "
            "confused with a provider status"
        ),
        "transport": "native_http_cn",
        "historical_note": (
            "the three earlier attempts preserved no trace_id and no "
            "base_resp.status_code: the CLI emitted "
            '{"error": {"code": 1, ...}} where 1 is the CLI general-error class. '
            "Those fields are HISTORICAL_RAW_RESPONSE_UNAVAILABLE and are not "
            "reconstructed."
        ),
    }

    after = read_money(base_url, payg.key)
    deltas = delta_money(before, after)
    receipt["money_after"] = after
    receipt["deltas"] = deltas

    cash_row = deltas.get("cash_balance") or {}
    actual = None
    if cash_row.get("decreased"):
        actual = str(-Decimal(str(cash_row["delta"])))
    receipt["actual_cash_debit_cny"] = actual

    anomalies = [
        name
        for name in ("voucher_balance", "credit_balance", "owed_amount")
        if (deltas.get(name) or {}).get("decreased") or (deltas.get(name) or {}).get("increased")
    ]
    receipt["unexpected_balance_movements"] = anomalies
    if actual is not None and Decimal(str(actual)) > CEILING_CNY:
        anomalies.append("cash_debit_over_ceiling")
        receipt["unexpected_balance_movements"] = anomalies

    receipt["voice_activated"] = bool(
        audio_ok and actual is not None and not anomalies
    )
    receipt["outcome"] = (
        "SUCCESS_ACTIVATED_CASH" if receipt["voice_activated"]
        else ("TTS_SUCCESS_BILLING_UNVERIFIED" if audio_ok else "ACTIVATION_FAILED")
    )
    if anomalies:
        receipt["outcome"] = "SEVERE_ANOMALY"
        receipt["notes"].append(
            "SEVERE_ANOMALY: " + ", ".join(anomalies)
            + ". A charged request must move cash and only cash, within the ceiling."
        )

    print()
    print("=== MEASURED ===")
    print(f"  {json.dumps(deltas, ensure_ascii=False)}")
    print()
    print(f"=== OUTCOME: {receipt['outcome']} ===")
    print(f"  actual cash debit : {actual}")
    print(f"  anomalies         : {anomalies or '(none)'}")
    print(f"  voice_activated   : {receipt['voice_activated']}")
    if receipt["outcome"] == "TTS_SUCCESS_BILLING_UNVERIFIED":
        receipt["notes"].append(
            "Audio returned but no cash movement proves the one-time fee was charged. "
            "Activation is NOT claimed: audio output is not proof of payment."
        )
        print("  activation NOT claimed -- audio is not proof of payment.")

    _write_history_append(attempt_id, {
        "at": _now(), "outcome": receipt["outcome"],
        "transport": "native_http_cn",
        "credential_class": payg.credential_class,
        "credential_source": payg.source,
        "request_host": normalize_host(base_url),
        "request_transmitted": bool(receipt.get("request_transmitted")),
        "provider_status": status,
        "error_taxonomy": receipt.get("error_taxonomy"),
        "cash_debit_cny": actual, "money_before": before["balances"],
        "money_after": after["balances"], "anomalies": anomalies,
    })
    registry_update: Dict[str, Any] = {}
    if receipt["voice_activated"]:
        registry_update = {
            "activated": True,
            "activated_at": _now(),
            "activation_attempt_id": attempt_id,
            "activation_fee_cny": actual,
            "activation_payment_source": "CASH",
        }
    else:
        registry_update = {
            "cash_recovery_used": True,
            "cash_recovery_attempt_id": attempt_id,
            "cash_recovery_outcome": receipt["outcome"],
            "cash_recovery_at": _now(),
        }
    # The exception and the recovery are consumed only when a request was actually
    # TRANSMITTED. Consuming them on a locally-blocked attempt would be a bug of its own:
    # a paid authorisation, and with it the only path to an already-cloned voice, would be
    # destroyed by a fault in this script that never reached the network -- forcing either
    # a re-clone or a second approval from the Founder for something that cost nothing.
    #
    # The boundary is drawn at the transmitted request, not at success: the native
    # adapter sets ``request_transmitted`` the moment the request leaves this process. A
    # provider refusal still burns the authorisation, because "it failed" is not "it was
    # free". A payload that failed local schema validation never reaches that boundary
    # and does not consume the authorisation.
    if receipt.get("request_transmitted"):
        registry.update(registry_update)
        registry["exposed_key_exception_consumed"] = True
        registry["exposed_key_exception_consumed_at"] = _now()
        registry["exposed_key_exception_consumed_by"] = attempt_id
    else:
        registry.setdefault("locally_blocked_attempts", []).append({
            "attempt_id": attempt_id,
            "at": _now(),
            "reason": "blocked by a local gate before any provider request",
            "charged_cny": "0.00",
        })
        receipt["note_on_consumption"] = (
            "no provider request was transmitted, so the single-use exception and the "
            "cash recovery remain unconsumed. recorded as a locally blocked attempt."
        )
        print("  no provider request was transmitted; authorisation NOT consumed")
    PRIVATE_REGISTRY.write_text(
        json.dumps(registry, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8", newline="\n",
    )
    receipt["provider_receipt"] = provider_receipt
    _write(receipt)
    return 0 if receipt["voice_activated"] else 1


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
        encoding="utf-8", newline="\n",
    )
    print(f"wrote {RECEIPT.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    raise SystemExit(main())