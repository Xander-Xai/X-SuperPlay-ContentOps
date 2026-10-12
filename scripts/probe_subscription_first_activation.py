"""``SUBSCRIPTION_FIRST_ACTIVATION_PROBE`` -- one authorised experiment. Issue #34.

What this is
------------
Issue #34 already created ``founder_primary_v1`` with a pay-as-you-go key. The first
synthesis -- the call that triggers the one-time CNY 9.90 -- was refused with
``insufficient balance`` while the CNY 15.00 voucher sat on the account.

The Founder has now authorised exactly one more request, with a different payment
question: **can the Subscription Key perform the first synthesis of this voice, and if so
does the one-time fee come off the ¥15 voucher while the character cost comes off M Plan
quota?**

No published rule guarantees that combination. The published deduction chain for a
Subscription Key is 套餐内额度 -> 积分包, which excludes 代金券 and excludes 账户余额. So this
is an empirical question and it is answered by one real call, not by reasoning.

What it will not do
-------------------
- use ``MINIMAX_CLONE_KEY`` or any pay-as-you-go credential, even as a fallback
- upload a sample, create a clone, or touch ``/v1/voice_clone``
- retry. One request, then stop.
- clear the previous ``activation_refused`` record or reset a call counter
- assert that the voice is activated, paid, or permanent without measured evidence

The refusal from the pay-as-you-go attempt is a historical fact and stays on disk. This
probe writes its own attempt id and its own record; it does not edit that one.

Three outcomes, and only three
------------------------------
``SUCCESS_ACTIVATED_MPLAN``
    Audio returned AND the voucher moved by the one-time fee AND plan quota moved.
``TTS_SUCCESS_ACTIVATION_UNVERIFIED``
    Audio returned, but no measured fee movement. The audio is kept. **Activation is not
    claimed**, because producing audio does not prove the voice was paid for, and a
    voice that was never activated is a temporary voice with an expiry clock.
``SUBSCRIPTION_ACTIVATION_REFUSED``
    The provider refused. The clone is preserved, no pay-as-you-go fallback is attempted,
    and the raw status is reported.

Any cash movement, Credit Pack movement, or 欠费 is a SEVERE_ANOMALY and stops the run
regardless of which outcome would otherwise have applied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.media.billing_guard import BillingGuard  # noqa: E402
from contentops.media.clone_route import (  # noqa: E402
    ACTIVATION_TEXT,
    CLONE_TTL_SECONDS,
    SPEECH_2_8_HD_CNY_PER_10K,
    billable_characters,
)
from contentops.media.credentials import (  # noqa: E402
    CREDENTIAL_PAYG,
    CREDENTIAL_SUBSCRIPTION,
    resolve_clone_credential,
    resolve_credential,
)
from contentops.media.contract import SpeechRequest  # noqa: E402
from contentops.media.minimax_speech import (  # noqa: E402
    MiniMaxMPlanProvider,
    receipt_to_dict,
    resolve_cli,
)
from contentops.media.transport import resolve_cli as _resolve_cli  # noqa: E402

PROBE_NAME = "SUBSCRIPTION_FIRST_ACTIVATION_PROBE"

VOICE_ID = "founder_primary_v1"
VOICE_ID_HASH = "7271d9c80c88821a6a09ed43328619d0ee08c3f2b2449237fe2c31f6899abeef"
MODEL = "speech-2.8-hd"
EXPECTED_SAMPLE_SHA256 = (
    "bb56d052cd637bd8a369f6e37a745c7609de9988ada0fa0827d4d5c59035df8d"
)

PRIVATE_REGISTRY = ROOT / ".private" / "founder-voice.json"
WORK = ROOT / ".verify-tmp" / "m34-sub-activation"
RECEIPT = (
    ROOT
    / "projects/easel-enhanced-golden/receipts"
    / "founder-voice-subscription-activation-receipt.json"
)

VOUCHER_CEILING_CNY = Decimal("10.00")
ONE_TIME_FEE_CNY = Decimal("9.90")

OUTCOME_SUCCESS = "SUCCESS_ACTIVATED_MPLAN"
OUTCOME_UNVERIFIED = "TTS_SUCCESS_ACTIVATION_UNVERIFIED"
OUTCOME_REFUSED = "SUBSCRIPTION_ACTIVATION_REFUSED"
OUTCOME_ANOMALY = "SEVERE_ANOMALY"

#: Documented provider status codes that are meaningful here. Recorded by name so the
#: receipt says what the code means rather than leaving a bare number.
STATUS_MEANINGS = {
    0: "success",
    1002: "rate limited",
    1004: "account authentication failed",
    1008: "insufficient account balance",
    2013: "invalid parameter",
    2042: "no permission to access this voice_id",
    2049: "invalid api key",
    2061: "this model is not available on the current Token Plan",
}


class StopRun(RuntimeError):
    """A refusal. Nothing is retried and nothing after this point runs."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base_url() -> str:
    for name in ("CONTENTOPS_MINIMAX_BASE_URL", "MINIMAX_VOICE_CLONE_BASE_URL"):
        value = os.environ.get(name, "").strip()
        if value:
            return value.rstrip("/")
    raise StopRun(
        "no provider host configured; set CONTENTOPS_MINIMAX_BASE_URL. Endpoint URLs "
        "are never committed (AGENTS.md section 8)."
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_money(base_url: str, credential: str) -> Dict[str, Any]:
    """Read-only balance and quota snapshot. Never a generation call."""
    guard = BillingGuard(base_url=base_url, credential=credential)
    result = guard.evaluate("speech")
    return {
        "verdict": result.verdict,
        "credential_class": result.credential_class,
        "balances": {
            k: v
            for k, v in (result.balances or {}).items()
            if k
            not in (
                "base_resp",
                "balance_alert_switch",
                "balance_alert_threshold",
            )
        },
        "observed_out_of_chain": list(result.observed_out_of_chain),
        "quota": None
        if result.quota is None
        else {
            "interval_remaining_percent": result.quota.interval_remaining_percent,
            "weekly_remaining_percent": result.quota.weekly_remaining_percent,
            "bucket": result.quota.bucket,
        },
    }


def delta(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for name in (
        "voucher_balance",
        "cash_balance",
        "credit_balance",
        "owed_amount",
        "available_amount",
    ):
        try:
            b = Decimal(str(before["balances"][name]))
            a = Decimal(str(after["balances"][name]))
        except Exception:  # noqa: BLE001 - reported, never inferred
            out[name] = {"before": before["balances"].get(name),
                         "after": after["balances"].get(name),
                         "delta": None,
                         "error": "field unreadable; not inferred"}
            continue
        out[name] = {
            "before": str(b),
            "after": str(a),
            "delta": str(a - b),
            "decreased": a < b,
            "increased": a > b,
        }
    qb, qa = before.get("quota") or {}, after.get("quota") or {}
    out["m_plan_quota"] = {
        "interval_before_pct": qb.get("interval_remaining_percent"),
        "interval_after_pct": qa.get("interval_remaining_percent"),
        "weekly_before_pct": qb.get("weekly_remaining_percent"),
        "weekly_after_pct": qa.get("weekly_remaining_percent"),
        "consumed": bool(
            qb.get("interval_remaining_percent") is not None
            and qa.get("interval_remaining_percent") is not None
            and float(qa["interval_remaining_percent"])
            < float(qb["interval_remaining_percent"])
        )
        or bool(
            qb.get("weekly_remaining_percent") is not None
            and qa.get("weekly_remaining_percent") is not None
            and float(qa["weekly_remaining_percent"])
            < float(qb["weekly_remaining_percent"])
        ),
    }
    return out


def parse_provider_error(text: str) -> Dict[str, Any]:
    """Pull a status code and message out of the CLI's error output.

    The CLI reports ``{"error": {"code": N, "message": "..."}}``. The code is the
    documented platform status, and it is the only part that is comparable across runs,
    so it is extracted rather than left inside a stderr tail for a reader to spot.
    """
    code = None
    message = ""
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            payload = json.loads(text[start : end + 1])
            err = payload.get("error") or {}
            raw = err.get("code")
            if isinstance(raw, int):
                code = raw
            elif isinstance(raw, str) and raw.isdigit():
                code = int(raw)
            message = str(err.get("message") or "")
        except json.JSONDecodeError:
            pass
    if not message:
        message = " ".join(text.split())[:300]
    return {
        "status_code": code,
        "status_meaning": STATUS_MEANINGS.get(code, "unrecognised status code"),
        "message": message[:300],
    }


def classify(deltas: Dict[str, Any], audio_ok: bool) -> str:
    """Exactly one of the three declared outcomes, or the anomaly stop.

    The fee test is ``decreased``, not ``== -9.90``: the character cost rides along on
    the same call, so the voucher movement is expected to be the fee plus a little, and
    demanding an exact match would reject the correct result as a failure.
    """
    cash = deltas.get("cash_balance") or {}
    credit = deltas.get("credit_balance") or {}
    owed = deltas.get("owed_amount") or {}
    voucher = deltas.get("voucher_balance") or {}
    if cash.get("increased") or credit.get("increased") or owed.get("increased"):
        return OUTCOME_ANOMALY
    fee_moved = bool(voucher.get("decreased"))
    if not audio_ok:
        return OUTCOME_REFUSED
    if fee_moved and (deltas.get("m_plan_quota") or {}).get("consumed"):
        return OUTCOME_SUCCESS
    return OUTCOME_UNVERIFIED


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="send the one authorised request. Without this, nothing is transmitted.",
    )
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    attempt_id = f"subact-{uuid.uuid4().hex[:12]}"
    base_url = _base_url()

    # --- credential isolation, before anything else ---------------------------
    resolved = resolve_credential()
    clone_key = resolve_clone_credential()
    if resolved.credential_class != CREDENTIAL_SUBSCRIPTION:
        raise SystemExit(
            f"REFUSING: the resolved TTS credential is "
            f"{resolved.credential_class}, not {CREDENTIAL_SUBSCRIPTION}. This probe "
            "is defined as the Subscription-Key experiment. There is no pay-as-you-go "
            "fallback, and none is attempted on failure."
        )
    if clone_key.usable and clone_key.key == resolved.key:
        raise SystemExit(
            "REFUSING: the pay-as-you-go clone key and the TTS credential resolved to "
            "the same secret. The two-key separation this route depends on is broken."
        )

    # --- the voice must already exist, and must still be activatable ----------
    registry: Dict[str, Any] = {}
    if PRIVATE_REGISTRY.is_file():
        registry = json.loads(PRIVATE_REGISTRY.read_text(encoding="utf-8"))
    if registry.get("provider_voice_id") != VOICE_ID:
        raise SystemExit(
            f"REFUSING: {PRIVATE_REGISTRY.relative_to(ROOT).as_posix()} does not record "
            f"provider_voice_id={VOICE_ID}. This probe does not create a voice."
        )
    created_unix = float(registry["created_at_unix"])
    elapsed = time.time() - created_unix
    remaining_h = (CLONE_TTL_SECONDS - elapsed) / 3600.0
    if elapsed >= CLONE_TTL_SECONDS:
        raise SystemExit(
            f"REFUSING: the voice was created {elapsed / 3600:.1f}h ago, past the "
            f"{CLONE_TTL_SECONDS // 3600}h temporary-voice window. Provider storage will "
            "have deleted it. Activation is no longer possible with this voice."
        )
    sample = ROOT / "assert" / "voice-reference-clean.wav"
    if not sample.is_file() or _sha256(sample) != EXPECTED_SAMPLE_SHA256:
        raise SystemExit("REFUSING: the approved sample is absent or has changed.")

    receipt: Dict[str, Any] = {
        "schema": "contentops.subscription-activation-probe/v1",
        "probe": PROBE_NAME,
        "attempt_id": attempt_id,
        "issue": "#34",
        "started_at": _now(),
        "executed": bool(args.execute),
        "voice_id": VOICE_ID,
        "voice_id_hash": VOICE_ID_HASH,
        "voice_already_created": True,
        "voice_source_sample_sha256": EXPECTED_SAMPLE_SHA256,
        "clone_created_at": registry.get("created_at"),
        "temporary_window_remaining_h": round(remaining_h, 2),
        "model": MODEL,
        "text": ACTIVATION_TEXT,
        "billable_characters": billable_characters(ACTIVATION_TEXT),
        "rate_cny_per_10k_chars": SPEECH_2_8_HD_CNY_PER_10K,
        "one_time_fee_expected_cny": str(ONE_TIME_FEE_CNY),
        "voucher_spend_ceiling_cny": str(VOUCHER_CEILING_CNY),
        "credential_class": resolved.credential_class,
        "credential_source": resolved.source,
        "payg_key_used": False,
        "provider_call_budget": {"subscription_tts": 1, "upload": 0, "clone": 0},
        "new_upload_count": 0,
        "new_clone_count": 0,
        "subscription_tts_attempts": 0,
        "retries_performed": 0,
        "prior_payg_refusal": {
            "preserved": True,
            "refused_at": registry.get("activation_refused_at"),
            "provider_message": registry.get("activation_refusal_provider_message"),
            "note": (
                "historical fact from the pay-as-you-go first-synthesis attempt. It is "
                "not cleared, not overwritten and not counted against this probe's "
                "budget: this is a separate authorised experiment against a different "
                "credential, not a retry of that one."
            ),
        },
        "notes": [],
    }

    print(f"=== {PROBE_NAME} ===")
    print(f"  attempt_id        : {attempt_id}")
    print(f"  voice_id          : {VOICE_ID} (sha256 {VOICE_ID_HASH[:16]}...)")
    print(f"  already created   : TRUE, at {registry.get('created_at')}")
    print(f"  window remaining  : {remaining_h:.1f}h of {CLONE_TTL_SECONDS // 3600}h")
    print(f"  credential class  : {resolved.credential_class} ({resolved.source})")
    print(f"  pay-as-you-go key : NOT USED, and not reachable from this path")
    print(f"  model / text      : {MODEL} / {ACTIVATION_TEXT}")
    print(f"  billable chars    : {receipt['billable_characters']}")
    print()

    before = read_money(base_url, resolved.key)
    receipt["before"] = before
    print("=== READ-ONLY PRE-FLIGHT ===")
    print(f"  BillingGuard      : {before['verdict']}")
    print(f"  balances          : {json.dumps(before['balances'], ensure_ascii=False)}")
    print(f"  out_of_chain      : {before['observed_out_of_chain']}")
    print(f"  M Plan quota      : {before['quota']}")
    print()

    # Section 五 of the authorisation, checked rather than assumed.
    b = before["balances"]
    problems = []
    if before["verdict"] != "SAFE_INCLUDED_PLAN":
        problems.append(f"BillingGuard verdict is {before['verdict']}")
    if Decimal(str(b.get("cash_balance", "0"))) != 0:
        problems.append(f"cash_balance is {b.get('cash_balance')}, must be 0.00")
    if Decimal(str(b.get("credit_balance", "0"))) != 0:
        problems.append(f"credit_balance is {b.get('credit_balance')}, must be 0.00")
    if Decimal(str(b.get("owed_amount", "0"))) != 0:
        problems.append(f"owed_amount is {b.get('owed_amount')}, must be 0.00")
    if Decimal(str(b.get("voucher_balance", "0"))) < Decimal("10"):
        problems.append(f"voucher_balance is {b.get('voucher_balance')}, below 10.00")
    quota = before.get("quota") or {}
    for window in ("interval_remaining_percent", "weekly_remaining_percent"):
        value = quota.get(window)
        if not value or float(value) <= 0:
            problems.append(f"M Plan {window} is {value}")
    if problems:
        receipt["preflight_problems"] = problems
        receipt["outcome"] = "REFUSED_PRECHECK"
        _write(receipt)
        print("=== PRE-FLIGHT FAILED. NOTHING WAS SENT. ===")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("  all pre-flight conditions met")
    print()

    if not args.execute:
        print("=== DRY RUN. NOTHING WAS SENT. ===")
        print(f"  one speech-2.8-hd synthesis, voice={VOICE_ID},")
        print(f"  credential={resolved.credential_class}, no upload, no clone, no retry.")
        print("Re-run with --execute.")
        return 0

    WORK.mkdir(parents=True, exist_ok=True)
    guard = BillingGuard(base_url=base_url, credential=resolved.key)
    provider = MiniMaxMPlanProvider(
        guard=guard,
        work_dir=WORK,
        cli=_resolve_cli(),
        transport_credential=resolved,
    )
    request = SpeechRequest(
        display_text=ACTIVATION_TEXT,
        language="zh",
        voice=VOICE_ID,
        model=MODEL,
        force=True,   # a cache hit would be a provider call that never happened
    )

    receipt["subscription_tts_attempts"] = 1
    receipt["request_started_at"] = _now()
    print("=== ONE REAL SYNTHESIS (Subscription Key, speech-2.8-hd) ===")
    audio_ok = False
    provider_receipt: Dict[str, Any] = {}
    failure: Dict[str, Any] = {}
    try:
        outcome = provider.synthesize_speech(request, attempt=1)
        audio_ok = True
        provider_receipt = receipt_to_dict(outcome.receipt)
        receipt["provider_status"] = {"status_code": 0, "status_meaning": "success"}
        receipt["audio"] = {
            "path": str(outcome.asset.normalized_path),
            "duration_s": outcome.asset.duration_s,
            "sample_rate_hz": outcome.asset.sample_rate_hz,
            "channels": outcome.asset.channels,
            "codec": outcome.asset.codec,
            "loudness_before": outcome.asset.loudness_before,
            "loudness_after": outcome.asset.loudness_after,
            "technical_qc_approved": outcome.asset.approved,
            "sha256": _sha256(Path(outcome.asset.normalized_path))
            if Path(outcome.asset.normalized_path).is_file()
            else None,
        }
        print(f"  audio returned: {receipt['audio']['path']}")
        print(f"  duration      : {outcome.asset.duration_s}s")
        print(f"  sha256        : {receipt['audio']['sha256']}")
    except Exception as exc:  # noqa: BLE001 - reported, never retried
        text = str(exc)
        failure = parse_provider_error(text)
        receipt["provider_status"] = failure
        receipt["failure_raw_tail"] = text[-400:]
        print(f"  REFUSED: {failure['status_meaning']}")
        print(f"  provider message: {failure['message']}")
    receipt["request_finished_at"] = _now()

    after = read_money(base_url, resolved.key)
    receipt["after"] = after
    deltas = delta(before, after)
    receipt["deltas"] = deltas
    outcome_kind = classify(deltas, audio_ok)
    receipt["outcome"] = outcome_kind

    print()
    print("=== MEASURED AFTER THE REQUEST ===")
    print(f"  {json.dumps(deltas, ensure_ascii=False)}")
    spent = None
    row = deltas.get("voucher_balance") or {}
    if row.get("decreased"):
        spent = str(-Decimal(str(row["delta"])))
    receipt["one_time_fee_observed_cny"] = spent
    receipt["voice_activated"] = outcome_kind == OUTCOME_SUCCESS
    receipt["m_plan_only_verified"] = outcome_kind == OUTCOME_SUCCESS
    print()
    print(f"=== OUTCOME: {outcome_kind} ===")
    print(f"  voice_activated          : {receipt['voice_activated']}")
    print(f"  one_time_fee_observed    : {spent}")
    print(f"  voucher delta            : {(deltas.get('voucher_balance') or {}).get('delta')}")
    print(f"  m_plan quota consumed    : {(deltas.get('m_plan_quota') or {}).get('consumed')}")
    if outcome_kind == OUTCOME_UNVERIFIED:
        receipt["notes"].append(
            "Audio was produced but no measured movement on the voucher. Activation is "
            "NOT claimed: producing audio does not prove the one-time fee was charged, "
            "and an unpaid cloned voice remains a temporary voice subject to the "
            f"{CLONE_TTL_SECONDS // 3600}h deletion window."
        )
        print("  activation NOT claimed; the audio is kept for listening.")
    if outcome_kind == OUTCOME_REFUSED:
        receipt["notes"].append(
            "The Subscription Key was refused. The existing clone is preserved, no "
            "pay-as-you-go fallback is attempted, and no further attempt follows."
        )
    if outcome_kind == OUTCOME_ANOMALY:
        receipt["notes"].append(
            "SEVERE_ANOMALY: cash, Credit Pack or 欠费 moved. Stopping immediately."
        )

    receipt["provider_receipt"] = provider_receipt
    _write(receipt)
    return 0 if audio_ok else 1


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


if __name__ == "__main__":
    raise SystemExit(main())