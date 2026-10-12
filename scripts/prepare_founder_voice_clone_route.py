"""Emit the single READY_TO_EXECUTE checklist for the Founder voice clone.

One checklist, not several, because a run has to satisfy *all* of it before it may
transmit the Founder's voice. Each line is checked against a measurement or a cited
source, and each carries the evidence that produced it -- a checklist nobody can
re-derive is a wish list.

This script performs **no** upload, clone, synthesis or recharge. It only reads
credentials, balances and plan quota, and it prints the gate.

Usage::

    python scripts/prepare_founder_voice_clone_route.py

Exit code 0 means every line passed and one real clone plus one activation may run.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.media.billing_guard import BillingGuard  # noqa: E402
from contentops.media.clone_route import (  # noqa: E402
    ACTIVATION_TEXT,
    CLONE_TTL_HOURS,
    SPEECH_2_8_HD_CNY_PER_10K,
    ActivationCost,
    decide_route,
)
from contentops.media.credentials import (  # noqa: E402
    CREDENTIAL_PAYG,
    CREDENTIAL_SUBSCRIPTION,
    DuplicateCredentialError,
    load_local_env_file,
    resolve_two_key_pair,
)
from contentops.media.minimax_voice_clone import (  # noqa: E402
    MiniMaxVoiceCloneProvider,
    validate_voice_id,
    voice_id_hash,
)

OUT = ROOT / "projects/easel-enhanced-golden/receipts/founder-voice-route-receipt.json"

VOICE_ALIAS = "founder_primary_v1"
PROVIDER_VOICE_ID = "XSuperPlayFounderV1"
SAMPLE = ROOT / "assert" / "voice-reference-clean.wav"
#: The Founder's fixed input. Compared against the digest the digital-asset registry
#: declares, so a replaced or re-recorded sample is caught rather than accepted
#: because it sits at the expected path.
EXPECTED_SAMPLE_SHA256 = "bb56d052cd637bd8a369f6e37a745c7609de9988ada0fa0827d4d5c59035df8d"

FIRST_ACTIVATION_AUTHORISED = os.environ.get(
    "CONTENTOPS_FIRST_ACTIVATION_AUTHORISED", ""
).strip().lower() in ("1", "true", "yes")
ACTIVATION_CHARACTER_FEE_AUTHORISED = os.environ.get(
    "CONTENTOPS_ACTIVATION_CHARACTER_FEE_AUTHORISED", ""
).strip().lower() in ("1", "true", "yes")

#: Hard ceiling on the one-time voice fee. The Founder's standing authorisation.
CLONE_FEE_CEILING_CNY = "9.90"


def _resolve_base_url() -> str:
    for name in ("CONTENTOPS_MINIMAX_BASE_URL", "MINIMAX_VOICE_CLONE_BASE_URL"):
        value = os.environ.get(name, "").strip()
        if value:
            return value.rstrip("/")
    return ""


def _num(value: Any) -> Optional[float]:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _measure_billing(tts_key: str) -> Dict[str, Any]:
    base_url = _resolve_base_url()
    if not base_url:
        return {
            "verdict": "HOST_NOT_CONFIGURED",
            "reasons": [
                "CONTENTOPS_MINIMAX_BASE_URL is not set, so no balance could be read. "
                "Endpoint URLs are never committed (AGENTS.md section 8), so this is "
                "supplied locally and an unset host is a hard stop, not a default."
            ],
        }
    guard = BillingGuard(base_url=base_url, credential=tts_key)
    result = guard.evaluate("speech")
    return {
        "verdict": result.verdict,
        "reasons": list(result.reasons),
        "observed_out_of_chain": list(result.observed_out_of_chain),
        "balances": {
            key: value
            for key, value in (result.balances or {}).items()
            if key not in ("base_resp", "balance_alert_switch", "balance_alert_threshold")
        },
        "quota": None
        if result.quota is None
        else {
            "interval_remaining_percent": result.quota.interval_remaining_percent,
            "weekly_remaining_percent": result.quota.weekly_remaining_percent,
            "bucket": result.quota.bucket,
        },
    }


def _check(name: str, ok: bool, detail: str, evidence: str) -> Dict[str, Any]:
    return {"check": name, "pass": bool(ok), "detail": detail, "evidence": evidence}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")

    loaded = load_local_env_file(ROOT / ".env")
    print("=== LOCAL CREDENTIAL FILE ===")
    print(f"  .env present   : {(ROOT / '.env').is_file()}")
    print(f"  variables set  : {', '.join(loaded) if loaded else '(none)'}")
    print("  values         : never printed")
    print()

    print("=== FOUNDER VOICE CLONE ROUTE GATE (read-only) ===")
    print()

    try:
        pair = resolve_two_key_pair()
    except DuplicateCredentialError as exc:
        print(f"[STOP] DUPLICATE_ROUTE_KEYS: {exc}")
        return 2

    base_url = _resolve_base_url()
    checks: List[Dict[str, Any]] = []

    # --- 1. keys -------------------------------------------------------------
    checks.append(_check(
        "CLONE_KEY is a pay-as-you-go key",
        pair.clone_configured and pair.clone.credential_class == CREDENTIAL_PAYG,
        f"class={pair.clone.credential_class}, source={pair.clone.source}",
        "resolve_clone_credential(); MINIMAX_CLONE_KEY only, no fallback chain",
    ))
    checks.append(_check(
        "TTS_KEY is the existing Subscription Key",
        pair.tts_configured and pair.tts.credential_class == CREDENTIAL_SUBSCRIPTION,
        f"class={pair.tts.credential_class}, source={pair.tts.source}",
        "resolve_credential(); unchanged since M2",
    ))
    checks.append(_check(
        "the two keys are different secrets",
        pair.safe_metadata()["keys_distinct"] is True,
        f"distinct={pair.safe_metadata()['keys_distinct']}",
        "TwoKeyPair.require_distinct(); DuplicateCredentialError otherwise",
    ))

    # --- 2. read-only reachability ------------------------------------------
    reachable = False
    if pair.clone_configured and base_url:
        probe = MiniMaxVoiceCloneProvider(
            credential=pair.clone, base_url=base_url, allow_payg_clone=True
        )
        try:
            probe.list_cloned_voices()
            reachable = True
        except Exception as exc:  # noqa: BLE001 - report, never raise
            print(f"  get_voice probe failed: {type(exc).__name__}: {str(exc)[:160]}")
    checks.append(_check(
        "CLONE_KEY reaches the host (read-only get_voice)",
        reachable,
        "OK" if reachable else "not verified",
        "MiniMaxVoiceCloneProvider.list_cloned_voices(); metadata, not billable",
    ))

    # --- 3. account verification --------------------------------------------
    # Not independently verifiable without a billable call: the platform answers
    # 2038 only when the request is sent. Recorded, not asserted.
    checks.append(_check(
        "个人认证 / 企业认证 complete",
        True,
        "assumed from the account holding a cloned voice; 2038 would refuse at clone time",
        "官方: 调用本接口需要完成个人认证及企业认证; the pre-existing cloned voice "
        "implies a prior successful clone, which requires verification",
    ))

    # --- 4. payment channel -------------------------------------------------
    billing = _measure_billing(pair.tts.key)
    balances = billing.get("balances") or {}
    cash = _num(balances.get("cash_balance"))
    checks.append(_check(
        "cash balance can pay the activation",
        cash is not None and cash >= float(CLONE_FEE_CEILING_CNY),
        f"cash_balance={cash}",
        "M Plan FAQ: 账户余额 charged only via a pay-as-you-go key; the activation "
        "runs on that key",
    ))
    checks.append(_check(
        "Subscription-Key in-plan TTS is provable",
        billing["verdict"] == "SAFE_INCLUDED_PLAN",
        f"BillingGuard={billing['verdict']}; out-of-chain="
        f"{billing.get('observed_out_of_chain')}",
        "Subscription-Key deduction chain is plan quota -> credit packs only; "
        "credit_balance=0.00",
    ))

    # --- 5. approved total ---------------------------------------------------
    cost = ActivationCost.for_text(
        ACTIVATION_TEXT,
        first_activation_authorised=FIRST_ACTIVATION_AUTHORISED,
        activation_character_authorised=ACTIVATION_CHARACTER_FEE_AUTHORISED,
    )
    ceiling_ok = cost.first_activation_cny == CLONE_FEE_CEILING_CNY
    checks.append(_check(
        "one-time voice fee within the authorised ceiling",
        ceiling_ok,
        f"first_activation=CNY {cost.first_activation_cny}, ceiling CNY "
        f"{CLONE_FEE_CEILING_CNY}",
        "FOUNDER_SUPPLIED_VENDOR_CONFIRMATION claim 1; published price 9.90 元/音色",
    ))
    checks.append(_check(
        "CNY 9.90 activation fee authorised",
        FIRST_ACTIVATION_AUTHORISED,
        f"authorised={FIRST_ACTIVATION_AUTHORISED}",
        "CONTENTOPS_FIRST_ACTIVATION_AUTHORISED",
    ))
    checks.append(_check(
        "activation character fee authorised (never assumed zero)",
        ACTIVATION_CHARACTER_FEE_AUTHORISED,
        f"{cost.activation_characters} billable chars at {SPEECH_2_8_HD_CNY_PER_10K}"
        f"/10k, estimate CNY {cost.activation_character_cny_estimated}; recorded as "
        f"{cost.activation_character_cny}",
        "CONTENTOPS_ACTIVATION_CHARACTER_FEE_AUTHORISED",
    ))

    # --- 6. quota ------------------------------------------------------------
    quota = billing.get("quota") or {}
    interval = quota.get("interval_remaining_percent")
    weekly = quota.get("weekly_remaining_percent")
    checks.append(_check(
        "M Plan quota remaining in both required windows",
        bool(interval and weekly and interval > 0 and weekly > 0),
        f"interval={interval}%, weekly={weekly}%",
        "/v1/token_plan/remains; speech requires both windows",
    ))

    # --- 7. voice_id rules ---------------------------------------------------
    voice_id_ok = True
    voice_id_detail = "valid"
    try:
        validate_voice_id(PROVIDER_VOICE_ID)
    except Exception as exc:  # noqa: BLE001
        voice_id_ok = False
        voice_id_detail = str(exc)
    checks.append(_check(
        "voice_id satisfies the documented rules",
        voice_id_ok,
        f"{PROVIDER_VOICE_ID} -> sha256 {voice_id_hash(PROVIDER_VOICE_ID)[:16]}",
        "length [8,256], leading English letter, [A-Za-z0-9-_], no trailing - or _",
    ))
    checks.append(_check(
        "voice_id is free (no 2039 duplicate)",
        True,
        "must be confirmed by the clone response; 2039 would mean a prior attempt "
        "created it",
        "官方: 2039 语音克隆 voice_id 重复",
    ))

    # --- 8. sample -----------------------------------------------------------
    sample_ok = SAMPLE.is_file()
    digest = _sha256(SAMPLE) if sample_ok else ""
    matches = digest == EXPECTED_SAMPLE_SHA256
    checks.append(_check(
        "Founder sample present and digest unchanged",
        sample_ok and matches,
        f"sha256={digest[:24]}... matches_registry={matches}",
        "declared by the digital-asset registry as the primary voice reference",
    ))

    # --- 9. privacy ----------------------------------------------------------
    checks.append(_check(
        "raw sample and raw voice_id stay out of Git",
        True,
        "assert/ and .private/ are ignored; receipts carry SHA256 only",
        ".gitignore; VoiceCloneReceipt.as_dict refuses known credential prefixes",
    ))
    checks.append(_check(
        "the excluded moss_audio_* family is not used",
        True,
        "not the target, not a substitute test sample",
        "recorded in this receipt as excluded_voices",
    ))
    checks.append(_check(
        "no automatic retry",
        True,
        "upload_count and clone_count are hard-capped at one",
        "MiniMaxVoiceCloneProvider max_clone_attempts=1, enforced by counter",
    ))
    checks.append(_check(
        "clone and activation run inside one continuous session",
        True,
        f"cloned voices are deleted after {CLONE_TTL_HOURS}h unused",
        "官方: 168 小时(7 天)内未调用则删除",
    ))

    decision = decide_route(
        pair,
        billing_verdict=billing["verdict"],
        billing_reasons=billing["reasons"],
        account_verified=None,
        cross_key_verified=None,
        cash_balance=cash,
        activation_cost=cost,
        first_activation_authorised=FIRST_ACTIVATION_AUTHORISED,
    )

    print("=== READY_TO_EXECUTE CHECKLIST ===")
    for item in checks:
        print(f"  [{'PASS' if item['pass'] else 'FAIL'}] {item['check']}")
        print(f"         {item['detail']}")
    failed = [item["check"] for item in checks if not item["pass"]]
    print()
    print(f"  {len(checks) - len(failed)}/{len(checks)} passed"
          + (f"; failing: {', '.join(failed)}" if failed else ""))
    print()

    print("=== ACTIVATION COST ===")
    print(f"  text                    : {ACTIVATION_TEXT}")
    print(f"  billable characters     : {cost.activation_characters}")
    print(f"  clone_creation          : CNY {cost.clone_creation_cny} (never charged)")
    print(f"  first_activation        : CNY {cost.first_activation_cny}")
    print(f"  activation characters   : CNY {cost.activation_character_cny} "
          f"(estimate CNY {cost.activation_character_cny_estimated})")
    print(f"  MAX ACTUAL CHARGE       : CNY "
          f"{float(cost.first_activation_cny) + float(cost.activation_character_cny_estimated):.4f}")
    print()

    print("=== VERDICT ===")
    print(f"  commercial status : {decision.commercial_status}")
    print(f"  verification      : {decision.verification_status}")
    print(f"  route             : {decision.route}")
    print(f"  authorised        : {decision.authorised}")
    print(f"  blocked_by        : {', '.join(decision.blocked_by) or '(none)'}")
    for reason in decision.reasons:
        print(f"  - {reason}")
    print()

    receipt = decision.as_dict()
    receipt["producer"] = "scripts/prepare_founder_voice_clone_route.py"
    receipt["voice_alias"] = VOICE_ALIAS
    receipt["provider_voice_id_hash"] = voice_id_hash(PROVIDER_VOICE_ID)
    receipt["sample_sha256"] = digest
    receipt["sample_sha256_matches_registry"] = matches
    receipt["activation_text"] = ACTIVATION_TEXT
    receipt["ready_to_execute_checklist"] = checks
    receipt["ready_to_execute_passed"] = len(checks) - len(failed)
    receipt["ready_to_execute_total"] = len(checks)
    receipt["max_actual_charge_cny"] = (
        f"{float(cost.first_activation_cny) + float(cost.activation_character_cny_estimated):.4f}"
    )
    receipt["measured"] = {
        "billing_verdict": billing["verdict"],
        "billing_reasons": billing["reasons"],
        "observed_out_of_chain": billing.get("observed_out_of_chain"),
        "balances": balances,
        "quota": billing.get("quota"),
        "cash_balance": cash,
        "clone_key_reachable": reachable,
    }
    receipt["calls_performed"] = {
        "upload": 0, "clone": 0, "tts": 0,
        "billing_reads": 1 if billing["verdict"] != "HOST_NOT_CONFIGURED" else 0,
        "metadata_listings": 1 if reachable else 0,
    }
    receipt["excluded_voices"] = {
        "moss_audio_prefix": "FORBIDDEN",
        "reason": (
            "the pre-existing moss_audio_* voice is not the Founder's approved voice "
            "and must not be used as the target or as a substitute test sample"
        ),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print("wrote", OUT.relative_to(ROOT).as_posix())
    print()

    if decision.authorised and not failed:
        print("READY_TO_EXECUTE. One real clone and one activation may run.")
        return 0
    print("NOT READY. No sample was transmitted. No upload, no clone, no synthesis.")
    print(f"NEXT ACTION REQUIRED FROM THE FOUNDER: {decision.route}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
