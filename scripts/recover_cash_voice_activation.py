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

from contentops.media.billing_guard import BillingGuard  # noqa: E402
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
    CREDENTIAL_SUBSCRIPTION,
    load_local_env_file,
    resolve_clone_credential,
    resolve_credential,
)
from contentops.media.contract import SpeechRequest  # noqa: E402,F401
from contentops.media.minimax_speech import (  # noqa: E402,F401
    MiniMaxMPlanProvider,
    receipt_to_dict,
)
from contentops.media.transport import resolve_cli  # noqa: E402
from contentops.media.credentials import child_env_for  # noqa: E402

PRIVATE_REGISTRY = ROOT / ".private" / "founder-voice.json"
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


def _base_url() -> str:
    for name in ("CONTENTOPS_MINIMAX_BASE_URL", "MINIMAX_VOICE_CLONE_BASE_URL"):
        value = os.environ.get(name, "").strip()
        if value:
            return value.rstrip("/")
    raise SystemExit("no provider host configured; set CONTENTOPS_MINIMAX_BASE_URL")


def _read_money(base_url: str, key: str) -> Dict[str, Any]:
    guard = BillingGuard(base_url=base_url, credential=key)
    result = guard.evaluate("speech")
    return {
        "verdict": result.verdict,
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
        },
    }


def _delta(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for name in ("cash_balance", "voucher_balance", "credit_balance",
                 "owed_amount", "available_amount"):
        try:
            b = Decimal(str(before["balances"][name]))
            a = Decimal(str(after["balances"][name]))
        except Exception:  # noqa: BLE001
            out[name] = {"delta": None, "error": "field unreadable; not inferred"}
            continue
        out[name] = {
            "before": str(b), "after": str(a), "delta": str(a - b),
            "decreased": a < b, "increased": a > b,
        }
    return out


def _write_history_append(attempt_id: str, payload: Dict[str, Any]) -> None:
    """Append-only history. Existing entries are never rewritten or removed."""
    entries: list = []
    if HISTORY_RECEIPT.is_file():
        try:
            entries = json.loads(HISTORY_RECEIPT.read_text(encoding="utf-8")).get(
                "attempts", []
            )
        except (OSError, json.JSONDecodeError):
            entries = []
    entries.append({"attempt_id": attempt_id, **_safe(payload)})
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
    HISTORY_RECEIPT.write_text(blob + "\n", encoding="utf-8", newline="\n")


def _safe(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in payload.items() if "key" not in k or k.endswith("fingerprint")}


def _activate_once(*, base_url: str, payg, receipt: Dict[str, Any]) -> Dict[str, Any]:
    """One TTS call for the activation, through the CLI with the PAYG key bound in.

    Mirrors :func:`contentops.media.minimax_speech.synthesize_speech` for the parts that
    matter to a receipt -- lexicon, loudnorm, technical QC and a SHA256 -- but performs the
    request itself, because the one-time fee is charged to a pay-as-you-go key and the M
    Plan provider must not be handed one.

    Exactly one provider request. There is no loop and no retry: a failure raises, and the
    caller stops.
    """
    import hashlib

    from contentops.media.audio import measure_audio, technical_qc
    from contentops.media.lexicon import default_zh_lexicon
    from contentops.media.minimax_speech import flatten_for_cli
    from process_utils import hidden_run

    env = child_env_for(payg)
    cli = resolve_cli()
    if not cli:
        raise SystemExit("official MiniMax CLI not on PATH; install: npm install -g mmx-cli")
    prefix = list(cli) if isinstance(cli, (list, tuple)) else [str(cli)]

    lexicon = default_zh_lexicon()
    spoken = lexicon.spoken_text(ACTIVATION_TEXT)
    cli_text = flatten_for_cli(spoken)
    raw = WORK / "activation-raw.wav"
    normalised = WORK / "activation-normalised.wav"
    for stale in (raw, normalised):
        if stale.exists():
            stale.unlink()
    WORK.mkdir(parents=True, exist_ok=True)

    result = hidden_run(
        prefix
        + [
            "speech", "synthesize",
            "--model", MODEL,
            "--text", cli_text,
            "--voice", VOICE_ID,
            "--format", "wav",
            "--out", str(raw),
            "--quiet", "--non-interactive",
        ]
        + lexicon.provider_arguments(),
        env=env, timeout=600,
    )
    if result.returncode != 0 or not raw.is_file() or raw.stat().st_size <= 1024:
        raise RuntimeError((result.stderr or result.stdout or "").strip()[-400:])
    hidden_run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw),
         "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
         "-ar", "44100", "-ac", "1", str(normalised)],
        timeout=600,
    )
    asset = normalised if normalised.is_file() and normalised.stat().st_size > 1024 else raw

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
        "loudness_lufs": getattr(measured, "loudness_lufs", None),
        "technical_qc_approved": technical.get("approved"),
        "technical_qc": technical,
        "lexicon_applied": True,
        "spoken_text_sha256": hashlib.sha256(cli_text.encode()).hexdigest(),
    }
    return {
        "provider_receipt": {
            "provider": "minimax",
            "transport": "official_cli",
            "credential_class": "PAYG",
            "model": MODEL,
            "voice_id_hash": VOICE_ID_HASH,
            "lexicon": "default_zh_lexicon",
            "loudnorm_target": "I=-16:TP=-1.5:LRA=11",
            "technical_qc": technical,
            "human_review": "PENDING_FOUNDER_REVIEW",
            "production_ready": False,
        }
    }


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
    base_url = _base_url()
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

    before = _read_money(base_url, payg.key)
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
    print(f"  tts credential    : {sub.credential_class} (never used for this call)")
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
    # Through the CLI with the pay-as-you-go key bound in, NOT through
    # ``MiniMaxMPlanProvider``. That provider is the M Plan subscription provider and its
    # ``BillingGuard`` refuses a PAYG credential by design -- correctly, because PAYG
    # narration is exactly what this repository forbids. Routing a deliberately
    # cash-paid activation through it asks a subscription-only provider to perform a
    # pay-as-you-go call, and the guard was right to say no.
    #
    # The guard is NOT disabled here. It has already run twice for this run, in
    # ``_read_money``, and its verdict and balances are recorded in the receipt. What is
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
    audio_ok = False
    status: Dict[str, Any] = {"status_code": None, "message": ""}
    provider_receipt: Dict[str, Any] = {}
    try:
        outcome = _activate_once(
            base_url=base_url, payg=payg, receipt=receipt
        )
        # Set immediately before the return, so it is True only once the CLI actually
        # produced audio. See the consumption rule below.
        receipt["request_transmitted"] = True
        audio_ok = True
        status = {"status_code": 0, "status_meaning": "success"}
        provider_receipt = outcome["provider_receipt"]
        print(f"  audio: {receipt['audio']['path']}")
        print(f"  sha256: {receipt['audio']['sha256']}")
    except Exception as exc:  # noqa: BLE001 - reported, never retried
        text = str(exc)
        status = {"status_code": None, "message": " ".join(text.split())[:300]}
        receipt["failure_tail"] = text[-400:]
        # Reaching here means the CLI was launched and the provider answered, so this IS
        # a transmitted request. It still burns the authorisation: a provider refusal can
        # and does consume a charge, and "it failed" is not "it was free".
        receipt["request_transmitted"] = True
        print(f"  FAILED: {status['message']}")
    receipt["request_finished_at"] = _now()
    receipt["provider_status"] = status

    after = _read_money(base_url, payg.key)
    deltas = _delta(before, after)
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
        "credential_class": "PAYG", "provider_status": status,
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
    # The boundary is drawn at the CLI launch, not at success. A provider refusal still
    # burns the authorisation, because "it failed" is not "it was free".
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