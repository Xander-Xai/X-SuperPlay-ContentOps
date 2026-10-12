"""``FOUNDER_VOUCHER_ACTIVATION`` regression tests. No provider call, no spend.

The failure each test exists to prevent
---------------------------------------
A. **Authorising a charge on an instrument that cannot carry it.** The Founder said
   "pay with the voucher"; that is *which* instrument, not proof the instrument covers
   音色管理. The gate must refuse on ``UNKNOWN`` regardless of how much balance shows.
B. **The ceiling being spent twice.** The limit is on the *total*, so two
   sub-ceiling components must not add up past what the Founder agreed to.
C. **An unauthorised deduction source.** Cash and Credit Pack must be zero *and shown to
   be* zero. A documented-but-absent balance is not a zero balance.
D. **A one-off permission becoming a standing one.** One voice, one clone, one
   activation, no retry, bounded PAYG — each checked against what already happened.
E. **A serialisation leak.** The receipt must carry the authorisation's *limits*, never
   a credential.

Every test is pure policy: no credential, no network, no spend. That is the only place
the "an ineligible voucher must refuse rather than be tried" invariant can be checked at
all, since the real path is blocked on a fact no API client can read.
"""

from __future__ import annotations

import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.media import voucher_activation as va  # noqa: E402

TESTS: List = []

VOICE_HASH = "98fcbad890c52c7cc274e8cc59e47d358ccc309eaf1b9cb7dfe5bfcb093dc197"


def test(fn):
    TESTS.append(fn)
    return fn


def _auth(**overrides: Any) -> va.FounderVoucherActivation:
    params: Dict[str, Any] = {"voice_id_hash": VOICE_HASH}
    params.update(overrides)
    return va.FounderVoucherActivation(**params)


def _decide(**overrides: Any) -> va.VoucherActivationVerdict:
    params: Dict[str, Any] = {
        "voucher_eligibility": va.EVIDENCE_VERIFIED_OFFICIAL,
        "voucher_eligibility_basis": "official 开放平台通用代金券 scope statement",
        "voucher_balance": 15.00,
        "cash_balance": 0.00,
        "credit_balance": 0.00,
        "projected_total_cny": "9.9154",
        "voice_id_hash": VOICE_HASH,
        "payg_tts_bounded": True,
    }
    params.update(overrides)
    return va.decide_voucher_activation(_auth(), **params)


# --- A. eligibility is a precondition, not a preference ----------------------


@test
def test_an_unknown_voucher_scope_refuses_even_with_a_full_balance():
    """A balance proves a voucher exists. It does not prove it covers this charge.

    This is the gate the round stops at. `voucher_balance = 15.00` says an instrument is
    present; the charge is on 音色管理, an API whose eligibility no reachable source
    establishes. Authorising on the balance alone would make "the account has money" the
    same claim as "this money can pay this", which is the error that spends real money on
    a real request.
    """
    verdict = _decide(voucher_eligibility=va.EVIDENCE_UNKNOWN)
    assert not verdict.authorised
    assert verdict.status == va.VOUCHER_CLONE_FEE_ELIGIBILITY_UNKNOWN
    assert va.REFUSAL_VOUCHER_ELIGIBILITY in verdict.refusals
    joined = " ".join(verdict.reasons)
    assert "which instrument to use" in joined, joined
    assert "好友邀请活动" in joined, (
        "the reason must name why the one favourable statement does not transfer"
    )
    assert "产品界面公示" in joined, (
        "the reason must name where the definitive scope actually lives"
    )
    print("[ok] 1. an unproven voucher scope refuses regardless of the balance")


@test
def test_only_official_or_account_level_evidence_clears_eligibility():
    """Two grades clear, one does not, and the boundary is explicit."""
    for grade, clears in (
        (va.EVIDENCE_VERIFIED_OFFICIAL, True),
        (va.EVIDENCE_VERIFIED_ACCOUNT_TERMS, True),
        (va.EVIDENCE_UNKNOWN, False),
    ):
        verdict = _decide(voucher_eligibility=grade)
        assert verdict.authorised is clears, (grade, verdict.refusals)
    assert va.EVIDENCE_UNKNOWN == "UNKNOWN"
    print("[ok] 2. only VERIFIED_OFFICIAL or VERIFIED_ACCOUNT_TERMS clears eligibility")


# --- B. the ceiling is on the total ------------------------------------------


@test
def test_the_ceiling_applies_to_the_combined_charge():
    """Two components under ¥10 can still add up past ¥10.

    The Founder authorised ¥10 of *total* voucher spend. A per-component ceiling would
    let a ¥9.90 voice fee and a ¥0.50 activation text each pass individually while the
    combined ¥10.40 exceeds what was agreed to.
    """
    assert _decide(projected_total_cny="9.9154").authorised

    over = _decide(projected_total_cny="10.0001")
    assert not over.authorised
    assert va.ACTIVATION_COST_ABOVE_AUTHORISED_TOTAL in over.refusals
    assert "combined" in " ".join(over.reasons)

    exactly = _decide(projected_total_cny="10.00")
    assert exactly.authorised, "the ceiling is inclusive; it is a limit, not a threshold"
    print("[ok] 3. the CNY 10 ceiling is applied to the combined charge, inclusively")


@test
def test_an_unreadable_or_absent_voucher_balance_refuses():
    """"I could not check" and "it is empty" are different facts, and only one is safe."""
    for balance in (None, 0.0):
        verdict = _decide(voucher_balance=balance)
        assert not verdict.authorised, balance
        assert va.VOUCHER_BALANCE_INSUFFICIENT in verdict.refusals, balance
    joined = " ".join(_decide(voucher_balance=None).reasons)
    assert "never treated as sufficient" in joined, joined
    print("[ok] 4. an unreadable or empty voucher balance refuses")


# --- C. no unauthorised deduction source -------------------------------------


@test
def test_nonzero_cash_or_credit_pack_refuses_as_a_fallback_risk():
    """The authorisation is zero cash and zero Credit Pack, so anything above zero fails.

    Deduction priority *between* voucher and cash inside 账户余额 is undocumented, so a
    non-zero cash balance means a wrong priority could debit a source the Founder did not
    authorise. At 0.00 the risk is structural rather than merely configured away -- and
    that is the whole point of checking the measured number, not the policy.
    """
    cash = _decide(cash_balance=0.01)
    assert not cash.authorised
    assert va.VOUCHER_CASH_FALLBACK_RISK in cash.refusals

    credit = _decide(credit_balance=0.01)
    assert not credit.authorised
    assert va.VOUCHER_CREDIT_FALLBACK_RISK in credit.refusals

    # And unreadable is not zero.
    assert va.VOUCHER_CASH_FALLBACK_RISK in _decide(cash_balance=None).refusals
    assert va.VOUCHER_CREDIT_FALLBACK_RISK in _decide(credit_balance=None).refusals

    # The measured account state is exactly what clears it.
    clean = _decide(cash_balance=0.00, credit_balance=0.00)
    assert clean.authorised, clean.refusals
    print("[ok] 5. cash and Credit Pack must be zero *and readable*, not assumed")


# --- D. one-off, not standing ------------------------------------------------


@test
def test_the_authorisation_is_single_use_and_scoped_to_one_voice():
    """One voice, one clone, one activation. A permission that survives its use is a licence."""
    assert va.ACTIVATION_ALREADY_USED in _decide(clone_count=1).refusals
    assert va.ACTIVATION_ALREADY_USED in _decide(activation_tts_count=1).refusals
    assert not _decide(clone_count=0, activation_tts_count=0).authorised is False

    other = _decide(voice_id_hash="0" * 64)
    assert va.ACTIVATION_VOICE_ID_MISMATCH in other.refusals
    assert "cannot be transferred" in " ".join(other.reasons)
    print("[ok] 6. the authorisation is spent once and cannot move to another voice")


@test
def test_a_retry_is_refused_and_unbounded_payg_is_refused():
    """Both are refused regardless of how small this particular run's charge is.

    A retry of a billable activation is a second charge. An unbounded PAYG path behind a
    ¥9.9154 permission is a much larger permission wearing that number's clothes.
    """
    retry = _decide(retry=True)
    assert not retry.authorised
    assert va.REFUSAL_RETRY in retry.refusals
    assert "second charge" in " ".join(retry.reasons)

    unbounded = _decide(payg_tts_bounded=False)
    assert not unbounded.authorised
    assert va.REFUSAL_PAYG_TTS_UNBOUNDED in unbounded.refusals

    recharge = va.decide_voucher_activation(
        _auth(allow_auto_recharge=True),
        voucher_eligibility=va.EVIDENCE_VERIFIED_OFFICIAL,
        voucher_eligibility_basis="x", voucher_balance=15.0, cash_balance=0.0,
        credit_balance=0.0, projected_total_cny="9.9154", voice_id_hash=VOICE_HASH,
        payg_tts_bounded=True,
    )
    assert not recharge.authorised
    assert "automatic recharge is enabled" in " ".join(recharge.reasons)
    print("[ok] 7. retry, unbounded PAYG and auto-recharge are each refused")


# --- E. the receipt -----------------------------------------------------------


@test
def test_the_receipt_carries_the_limits_and_no_credential():
    """Serialisation is where a receipt leaks, so it is checked rather than trusted."""
    payload = _decide(voucher_eligibility=va.EVIDENCE_UNKNOWN).as_dict()
    blob = repr(payload)
    assert "sk-api-" not in blob and "sk-cp-" not in blob and "Bearer " not in blob
    assert payload["authorisation"] == va.VOUCHER_ACTIVATION_AUTHORISED
    assert payload["limits"]["allowed_voucher_spend_cny"] == "10.00"
    assert payload["limits"]["allowed_cash_spend_cny"] == "0.00"
    assert payload["limits"]["allowed_credit_pack_spend_cny"] == "0.00"
    assert payload["limits"]["allow_auto_recharge"] is False
    assert payload["limits"]["max_clone_count"] == 1
    assert payload["limits"]["max_activation_tts_count"] == 1
    assert payload["limits"]["allow_unbounded_payg_tts"] is False
    assert payload["payg_tts_allowed"] is False
    assert payload["automatic_recharge_allowed"] is False
    assert payload["production_ready"] is False
    assert json.loads(json.dumps(payload)) == payload
    print("[ok] 8. the activation receipt states every limit and carries no credential")


@test
def test_every_refusal_is_reported_not_just_the_first():
    """An operator fixing the visible blocker must still see what remains."""
    verdict = _decide(
        voucher_eligibility=va.EVIDENCE_UNKNOWN,
        voucher_balance=None,
        cash_balance=5.0,
        credit_balance=1.0,
        projected_total_cny="12.00",
        voice_id_hash="0" * 64,
        retry=True,
        payg_tts_bounded=False,
    )
    assert not verdict.authorised
    assert len(verdict.refusals) >= 7, verdict.refusals
    assert len(verdict.reasons) >= len(verdict.refusals)
    assert verdict.refusals[0] == va.REFUSAL_VOUCHER_ELIGIBILITY, (
        "eligibility is reported first because everything after it is arithmetic on an "
        "instrument that may not exist"
    )
    print("[ok] 9. all applicable refusals are listed, eligibility first")


def main() -> int:
    failures = 0
    for fn in TESTS:
        try:
            fn()
        except AssertionError as exc:
            print(f"[FAIL] {fn.__name__}: {exc}")
            failures += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[ERR ] {fn.__name__}: {type(exc).__name__}({exc})")
            failures += 1
    total = len(TESTS)
    if failures:
        print(f"\n{failures} of {total} test(s) failed")
        return 1
    print(f"\nAll {total} voucher-activation regression tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())