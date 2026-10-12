"""``MPLAN_NARRATION_ROUTE`` stage 1: one cross-key verification synthesis. Issue #34.

The question this answers, with one request
-------------------------------------------
The vendor confirmation says an activated voice *may* be used with the M Plan.
That is a commercial statement; ``2042 无权访问该 voice_id`` is the documented
API-level refusal if visibility does not imply usability. Only a real synthesis
answers it. So this stage sends **one** short synthesis of ``founder_primary_v1``
with the **Subscription Key** through the native HTTP adapter, and measures:

- the cross-key access itself (success, or the provider's own refusal code)
- plan quota before and after
- cash / voucher / Credit Pack / 欠费 before and after -- with the pay-as-you-go
  key, so "no extra PAYG charge" is a measurement, not an assumption
- ``usage_voice_count``, which the provider returns only when a voice fee is
  charged: a second clone fee would show up here

Route separation, explicitly
----------------------------
This script owns ``MPLAN_NARRATION_ROUTE`` only: its credential is the
Subscription Key, its gate is :func:`decide_mplan_native` (Subscription class +
``SAFE_INCLUDED_PLAN``), its budget is one request, and its receipt is its own
file. The PAYG activation's cash authorisation is not visible here and is not
transferable to it.

Dry run by default. ``--execute`` sends the one request.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.media.clone_route import ACTIVATION_TEXT, billable_characters  # noqa: E402
from contentops.media.credentials import (  # noqa: E402
    CREDENTIAL_SUBSCRIPTION,
    load_local_env_file,
    resolve_clone_credential,
    resolve_credential,
)
from contentops.media.minimax_native_tts import (  # noqa: E402
    MINIMAX_CN_HOST,
    NativeTtsRefusal,
)
from contentops.media.native_rounds import (  # noqa: E402
    MPLAN_NARRATION_ROUTE,
    build_spoken_request,
    classify_mplan_only,
    decide_mplan_native,
    delta_money,
    read_money,
    run_native_activation_once,
)

VOICE_ID = "founder_primary_v1"
VOICE_ID_HASH = "7271d9c80c88821a6a09ed43328619d0ee08c3f2b2449237fe2c31f6899abeef"
MODEL = "speech-2.8-hd"

WORK = ROOT / ".verify-tmp" / "m34-mplan-crosskey"
RECEIPT = (
    ROOT
    / "projects/easel-enhanced-golden/receipts"
    / "founder-voice-mplan-crosskey-receipt.json"
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _activation_verified() -> Optional[Dict[str, Any]]:
    """The PAYG activation must be recorded as successful before this stage.

    Two admissible records: the activation receipt itself when the immediate
    read caught the debit (``voice_activated`` true), or -- because usage
    billing settles asynchronously -- the settlement receipt that reconciled
    the same attempt later. Stage ordering is not a formality here: the
    cross-key question is only meaningful for a voice whose one-time fee has
    actually been collected.
    """
    if not ACTIVATION_RECEIPT.is_file():
        return None
    try:
        payload = json.loads(ACTIVATION_RECEIPT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if payload.get("voice_activated"):
        return {
            "source": "activation_receipt",
            "outcome": payload.get("outcome"),
            "attempt_id": payload.get("attempt_id"),
            "actual_cash_debit_cny": payload.get("actual_cash_debit_cny"),
            "trace_id": (payload.get("provider_status") or {}).get("trace_id"),
        }
    if not SETTLEMENT_RECEIPT.is_file():
        return None
    try:
        settlement = json.loads(SETTLEMENT_RECEIPT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if (
        settlement.get("attempt_id") == payload.get("attempt_id")
        and str(settlement.get("outcome", "")).startswith("ACTIVATION_FEE_SETTLED_")
    ):
        return {
            "source": "settlement_receipt",
            "outcome": settlement.get("outcome"),
            "attempt_id": settlement.get("attempt_id"),
            "settled_total_debit_cny": settlement.get("settled_total_debit_cny"),
            "paid_by": settlement.get("paid_by"),
            "trace_id": (payload.get("provider_status") or {}).get("trace_id"),
        }
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="send the one verification request. Without this, "
                             "nothing is transmitted.")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    load_local_env_file(ROOT / ".env")
    attempt_id = f"mplanverify-{uuid.uuid4().hex[:12]}"

    sub = resolve_credential()
    payg = resolve_clone_credential()

    activation = _activation_verified()
    receipt: Dict[str, Any] = {
        "schema": "contentops.mplan-crosskey-verification/v1",
        "stage": "CROSS_KEY_VERIFICATION",
        "route": MPLAN_NARRATION_ROUTE,
        "attempt_id": attempt_id,
        "issue": "#34",
        "started_at": _now(),
        "executed": bool(args.execute),
        "voice_id": VOICE_ID,
        "voice_id_hash": VOICE_ID_HASH,
        "model": MODEL,
        "text": ACTIVATION_TEXT,
        "billable_characters": billable_characters(ACTIVATION_TEXT),
        "credential_class": sub.credential_class,
        "credential_source": sub.source,
        "payg_key_used_for_this_request": False,
        "host": MINIMAX_CN_HOST,
        "transport": "native_http_cn",
        "provider_call_budget": {
            "subscription_tts": 1,
            "upload": 0,
            "clone": 0,
            "automatic_retry": 0,
        },
        "activation_precondition": activation,
        "notes": [],
    }

    print("=== MPLAN_CROSSKEY_VERIFICATION ===")
    print(f"  attempt_id        : {attempt_id}")
    print(f"  route             : {MPLAN_NARRATION_ROUTE}")
    print(f"  voice             : {VOICE_ID}")
    print(f"  subscription key  : {sub.credential_class} ({sub.source})")
    print(f"  payg key          : present={bool(payg.key)} -- NOT used for the request")

    if activation is None:
        receipt["outcome"] = "REFUSED_ACTIVATION_NOT_VERIFIED"
        receipt["notes"].append(
            "the PAYG activation receipt is absent or does not record "
            "voice_activated=true; the cross-key question is not yet due"
        )
        _write(receipt)
        print("REFUSED: activation is not recorded as verified. Nothing was sent.")
        return 1

    if sub.credential_class != CREDENTIAL_SUBSCRIPTION:
        receipt["outcome"] = "REFUSED_CREDENTIAL_CLASS"
        _write(receipt)
        print(f"REFUSED: the resolved credential is {sub.credential_class}, not a "
              f"Subscription Key. Nothing was sent.")
        return 1

    guard_money = read_money(MINIMAX_CN_HOST, sub.key)
    paid_before = read_money(MINIMAX_CN_HOST, payg.key) if payg.usable else guard_money
    decision = decide_mplan_native(
        credential_class=sub.credential_class,
        credential_source=sub.source,
        guard_verdict=guard_money["verdict"],
        guard_reasons=guard_money.get("reasons"),
        quota=guard_money["quota"],
    )
    receipt["preflight"] = {
        "billing_verdict": guard_money["verdict"],
        "quota": guard_money["quota"],
        "balances": paid_before["balances"],
        "decision": decision,
    }

    print(f"  BillingGuard      : {guard_money['verdict']}")
    print(f"  balances          : {json.dumps(paid_before['balances'], ensure_ascii=False)}")
    print(f"  M Plan quota      : {guard_money['quota']}")
    print(f"=== GATE: {'AUTHORISED' if decision['authorised'] else decision['refusals']} ===")
    for reason in decision["reasons"]:
        print(f"  - {reason}")

    if not decision["authorised"]:
        receipt["outcome"] = "REFUSED_PRECHECK"
        _write(receipt)
        print("NOTHING WAS SENT.")
        return 1

    if not args.execute:
        _write(receipt)
        print("=== DRY RUN. NOTHING WAS SENT. ===")
        return 0

    # --- the one request ------------------------------------------------------
    WORK.mkdir(parents=True, exist_ok=True)
    from contentops.media.lexicon import default_zh_lexicon

    spec = build_spoken_request(
        display_text=ACTIVATION_TEXT,
        voice_id=VOICE_ID,
        model=MODEL,
        lexicon=default_zh_lexicon(),
    )
    receipt["request_started_at"] = _now()
    receipt["request_transmitted"] = False
    audio_ok = False
    status: Dict[str, Any] = {}
    try:
        outcome = run_native_activation_once(
            spec=spec,
            credential=sub.key,
            credential_class=sub.credential_class,
            credential_source=sub.source,
            base_url=MINIMAX_CN_HOST,
            attempt_id=attempt_id,
            work_dir=WORK,
            diagnostics_dir=ROOT / ".private" / "diagnostics",
            receipt=receipt,
            route=MPLAN_NARRATION_ROUTE,
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
        receipt["provider_receipt"] = outcome["provider_receipt"]
        print(f"  audio: {receipt['audio']['path']}")
        print(f"  trace_id: {status['trace_id']}")
    except NativeTtsRefusal as refusal:
        status = {
            **refusal.structured(),
            "status_meaning": (
                "provider refused" if refusal.provider_status_code is not None
                else refusal.code
            ),
        }
        receipt["failure_tail"] = " ".join(str(refusal).split())[:400]
        print(f"  REFUSED: HTTP {status['http_status']} / provider status "
              f"{status['provider_status_code']}: {status['provider_status_msg']}")
    receipt["request_finished_at"] = _now()
    receipt["provider_status"] = status

    guard_after = read_money(MINIMAX_CN_HOST, sub.key)
    paid_after = read_money(MINIMAX_CN_HOST, payg.key) if payg.usable else guard_after
    deltas = delta_money(paid_before, paid_after)
    receipt["quota_after"] = guard_after["quota"]
    receipt["balances_after"] = paid_after["balances"]
    receipt["deltas"] = deltas

    classification = classify_mplan_only(
        quota_before=guard_money["quota"],
        quota_after=guard_after["quota"],
        deltas=deltas,
    )
    receipt["verification"] = classification

    second_clone_fee = status.get("usage_voice_count")
    receipt["second_clone_fee_check"] = {
        "usage_voice_count": second_clone_fee,
        "meaning": (
            "documented: returned only when a voice fee is charged on this request"
        ),
        "second_clone_fee_charged": bool(second_clone_fee),
    }

    cross_key = (
        "GRANTED" if audio_ok else f"REFUSED status_code={status.get('provider_status_code')}"
    )
    receipt["cross_key_voice_access"] = cross_key
    receipt["outcome"] = (
        "CROSS_KEY_VERIFIED" if (audio_ok and classification["verified"])
        else ("CROSS_KEY_REFUSED" if not audio_ok else classification["status"])
    )
    receipt["m_plan_only_verified"] = bool(audio_ok and classification["verified"])

    print()
    print("=== MEASURED ===")
    print(f"  quota before/after: {guard_money['quota']} -> {guard_after['quota']}")
    print(f"  deltas            : {json.dumps(deltas, ensure_ascii=False)}")
    print(f"  cross-key access  : {cross_key}")
    print(f"  M_PLAN_ONLY       : {classification['status']} "
          f"(basis {classification['basis']})")
    print(f"  second clone fee  : {receipt['second_clone_fee_check']['second_clone_fee_charged']}")
    print(f"=== OUTCOME: {receipt['outcome']} ===")

    _write(receipt)
    return 0 if receipt["m_plan_only_verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
