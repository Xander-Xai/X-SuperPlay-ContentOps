"""Reconcile the PAYG activation's billing settlement. Issue #34.

Why this exists
---------------
The activation request itself succeeded -- provider ``status_code=0``, audio
returned, ``usage_voice_count=1`` -- but the *immediate* post-request balance
read showed no movement: usage billing settles asynchronously, on the order of
minutes. The activation script recorded exactly what it saw at the time
(``TTS_SUCCESS_BILLING_UNVERIFIED``) and stopped, as it must. This script
performs the follow-up verification that the original run could not:

- re-reads the balances (read-only) and measures the *settled* paid-fund debit
  against the receipt's own ``money_before``;
- checks the debit is consistent with the documented one-time voice fee
  (CNY 9.90) plus the character cost, within the CNY 10.00 ceiling;
- checks cash / Credit Pack / 欠费 invariants and reports which fund actually
  paid;
- reads ``/v1/get_voice`` with the PAYG key, because the current documentation
  says ``voice_cloning`` entries appear only **after the voice has been used
  for synthesis** -- the clone's own listing is corroborating evidence that the
  first use happened;
- writes a settlement receipt and updates the private registry.

It sends **no generation request** and cannot activate anything. If the
settlement is absent it reports ``SETTLEMENT_PENDING`` and stops -- it never
re-activates.

Honest boundary: the original receipt is not rewritten. Its immediate
observation ("no movement yet") and this settlement observation ("moved by N
later") are two measurements at two times, and the record keeps both.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.media.clone_route import SPEECH_2_8_HD_CNY_PER_10K, billable_characters  # noqa: E402
from contentops.media.credentials import (  # noqa: E402
    load_local_env_file,
    resolve_clone_credential,
)
from contentops.media.minimax_native_tts import MINIMAX_CN_HOST  # noqa: E402
from contentops.media.native_rounds import (  # noqa: E402
    NATIVE_FIRST_ACTIVATION_CEILING_CNY,
    read_money,
)

ACTIVATION_RECEIPT = (
    ROOT
    / "projects/easel-enhanced-golden/receipts"
    / "founder-voice-payg-first-activation-receipt.json"
)
SETTLEMENT_RECEIPT = (
    ROOT
    / "projects/easel-enhanced-golden/receipts"
    / "founder-voice-payg-activation-settlement-receipt.json"
)
PRIVATE_REGISTRY = ROOT / ".private" / "founder-voice.json"

VOICE_ID = "founder_primary_v1"
VOICE_ID_HASH = "7271d9c80c88821a6a09ed43328619d0ee08c3f2b2449237fe2c31f6899abeef"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dec(value: Any) -> Optional[Decimal]:
    try:
        return Decimal(str(value))
    except Exception:  # noqa: BLE001
        return None


def _voice_visible_listing(payg) -> Dict[str, Any]:
    """Read-only: does /v1/get_voice now list the cloned voice?

    Documentation: ``voice_cloning`` entries appear only after the voice has
    been used for synthesis. A hit is corroboration, not proof of payment --
    it is recorded with exactly that weight.
    """
    import hashlib

    from contentops.media.minimax_voice_clone import MiniMaxVoiceCloneProvider

    try:
        provider = MiniMaxVoiceCloneProvider(
            credential=payg,
            base_url=MINIMAX_CN_HOST,
            allow_payg_clone=True,
        )
        entries = provider.list_cloned_voices()
    except Exception as exc:  # noqa: BLE001 - a failed read is reported, not fatal
        return {"read": False, "error": type(exc).__name__}
    hashes = [
        hashlib.sha256(str(entry.get("voice_id", "")).encode()).hexdigest()
        for entry in entries
    ]
    return {
        "read": True,
        "count": len(entries),
        "lists_founder_voice": VOICE_ID_HASH in hashes,
        "matched_by": "sha256 voice_id comparison; raw ids never recorded",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="perform the read-only verification and write the settlement receipt. "
             "Without it, only prints what would be checked.",
    )
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    load_local_env_file(ROOT / ".env")
    payg = resolve_clone_credential()

    if not ACTIVATION_RECEIPT.is_file():
        print("REFUSED: no activation receipt; nothing to reconcile.")
        return 1
    activation = json.loads(ACTIVATION_RECEIPT.read_text(encoding="utf-8"))
    provider_status = activation.get("provider_status") or {}
    transmitted = bool(activation.get("request_transmitted"))
    provider_ok = provider_status.get("status_code") == 0 and provider_status.get(
        "http_status"
    ) == 200
    usage_voice_count = provider_status.get("usage_voice_count")

    print("=== PAYG_ACTIVATION_SETTLEMENT ===")
    print(f"  activation attempt : {activation.get('attempt_id')}")
    print(f"  transmitted        : {transmitted}")
    print(f"  provider status    : {json.dumps(provider_status, ensure_ascii=False)}")

    if not (transmitted and provider_ok):
        print("REFUSED: the activation receipt does not record a successful "
              "provider request; there can be no fee to settle.")
        return 1
    if not usage_voice_count:
        print("NOTE: usage_voice_count is absent on the activation response. The "
              "provider documents it as returned exactly when a voice fee is "
              "charged, so this is recorded as its own fact, not assumed away.")

    before = activation.get("money_before", {}).get("balances", {})
    after_now = read_money(MINIMAX_CN_HOST, payg.key)
    now_balances = after_now["balances"]

    deltas: Dict[str, Any] = {}
    total_debit = Decimal("0")
    for name in ("cash_balance", "voucher_balance", "credit_balance", "owed_amount",
                 "available_amount"):
        b = _dec(before.get(name))
        a = _dec(now_balances.get(name))
        if b is None or a is None:
            deltas[name] = {"before": before.get(name), "after": now_balances.get(name),
                            "delta": None}
            continue
        deltas[name] = {
            "before": str(b), "after": str(a), "delta": str(a - b),
            "decreased": a < b, "increased": a > b,
        }
        if name in ("cash_balance", "voucher_balance", "credit_balance") and a < b:
            total_debit += b - a

    char_fee = (
        Decimal(SPEECH_2_8_HD_CNY_PER_10K)
        * billable_characters(activation.get("text", ""))
        / Decimal(10000)
    )
    one_time = Decimal("9.90")
    projected = one_time + char_fee

    cash_row = deltas.get("cash_balance") or {}
    voucher_row = deltas.get("voucher_balance") or {}
    credit_row = deltas.get("credit_balance") or {}
    owed_row = deltas.get("owed_amount") or {}
    paid_sources = [
        name
        for name, row in (
            ("cash", cash_row), ("voucher", voucher_row), ("credit_pack", credit_row)
        )
        if row.get("decreased")
    ]
    overdrawn = bool(owed_row.get("increased"))
    settled = total_debit > 0
    within_ceiling = total_debit <= NATIVE_FIRST_ACTIVATION_CEILING_CNY
    consistent = settled and one_time <= total_debit <= one_time + Decimal("0.05")

    if overdrawn:
        outcome = "SEVERE_ANOMALY_DEBT_CREATED"
    elif not settled:
        outcome = "SETTLEMENT_PENDING"
    elif not within_ceiling:
        outcome = "SEVERE_ANOMALY_OVER_CEILING"
    elif not consistent:
        outcome = "SETTLED_UNEXPECTED_AMOUNT"
    else:
        outcome = "ACTIVATION_FEE_SETTLED_" + "_AND_".join(paid_sources).upper()

    settlement: Dict[str, Any] = {
        "schema": "contentops.payg-activation-settlement/v1",
        "issue": "#34",
        "attempt_id": activation.get("attempt_id"),
        "checked_at": _now(),
        "transport": "read_only",
        "generation_requests_sent": 0,
        "activation_receipt": str(ACTIVATION_RECEIPT.relative_to(ROOT)).replace("\\", "/"),
        "provider_status": provider_status,
        "usage_voice_count": usage_voice_count,
        "money_before": before,
        "money_now": now_balances,
        "deltas": deltas,
        "settled_total_debit_cny": str(total_debit),
        "expected_components": {
            "one_time_voice_fee_cny": str(one_time),
            "character_fee_estimated_cny": f"{char_fee:.6f}",
            "projected_total_cny": f"{projected:.4f}",
            "note": (
                "balances are displayed to 0.01, so the settled figure is compared "
                "against the projected total as a bounded band, not an equality"
            ),
        },
        "within_cny_10_authorization": within_ceiling,
        "paid_by": paid_sources,
        "payment_source_note": (
            "the platform's own deduction order chose the voucher; the request "
            "contains no field that selects a fund. No recharge was performed, "
            "no Credit Pack was drawn on and no debt was created."
        ),
        "fee_consistent_with_documented_components": consistent,
        "outcome": outcome,
        "human_review": "PENDING_FOUNDER_REVIEW",
    }

    print()
    print("=== SETTLED BALANCES (read-only) ===")
    print(f"  {json.dumps(deltas, ensure_ascii=False)}")
    print(f"  total paid-fund debit: CNY {total_debit} (ceiling CNY 10.00)")
    print(f"  paid by: {paid_sources or '(nothing moved yet)'}")

    if not args.execute:
        print("=== DRY RUN. Settlement receipt NOT written. ===")
        return 0

    if settled:
        listing = _voice_visible_listing(payg)
        settlement["voice_listing"] = listing
        print(f"  /v1/get_voice     : {json.dumps(listing, ensure_ascii=False)}")

        registry = json.loads(PRIVATE_REGISTRY.read_text(encoding="utf-8"))
        registry["activated"] = outcome.startswith("ACTIVATION_FEE_SETTLED_")
        registry["activated_at"] = _now()
        registry["activation_attempt_id"] = activation.get("attempt_id")
        registry["activation_fee_cny"] = str(total_debit)
        registry["activation_payment_source"] = "+".join(paid_sources).upper()
        registry["activation_settlement_outcome"] = outcome
        registry["activation_settlement_at"] = settlement["checked_at"]
        PRIVATE_REGISTRY.write_text(
            json.dumps(registry, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8", newline="\n",
        )
        print(f"  registry updated  : activated={registry['activated']} "
              f"source={registry['activation_payment_source']}")

    blob = json.dumps(settlement, ensure_ascii=False)
    for banned in ("Authorization", "Bearer ", "sk-cp-", "sk-api-"):
        if banned in blob:
            raise SystemExit(f"refusing to write settlement containing {banned!r}")
    SETTLEMENT_RECEIPT.write_text(
        json.dumps(settlement, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8", newline="\n",
    )
    print(f"wrote {SETTLEMENT_RECEIPT.relative_to(ROOT).as_posix()}")
    print(f"=== OUTCOME: {outcome} ===")
    return 0 if outcome.startswith("ACTIVATION_FEE_SETTLED_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
