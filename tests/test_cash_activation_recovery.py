"""Regression tests for ``CASH_ACTIVATION_RECOVERY``. Issue #34.

Every test here runs offline. Nothing in this file contacts a provider, reads a real
credential or spends anything.
"""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.media.cash_activation_recovery import (  # noqa: E402
    ACTIVATION_CHARGE_NOT_BOUNDED,
    EXPOSED_PAYG_KEY_FINGERPRINTS,
    EXPOSED_PAYG_KEY_NOT_ROTATED,
    RECOVERY_ALREADY_USED,
    REFUSAL_VOICE_EXPIRED,
    REFUSAL_VOICE_MISSING,
    CashActivationAuthorisation,
    ExposedKeyException,
    FOUNDER_AUTHORISED_EXPOSED_KEY_REUSE,
    character_cost,
    decide_cash_activation,
    key_fingerprint,
    payg_key_is_exposed,
)

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


VOICE_HASH = "7271d9c80c88821a6a09ed43328619d0ee08c3f2b2449237fe2c31f6899abeef"
ACTIVATION_TEXT = "这是一段用于首次激活的最短自然中文语音样本。"


def _authorisation(**overrides) -> CashActivationAuthorisation:
    base = {"voice_id_hash": VOICE_HASH}
    base.update(overrides)
    return CashActivationAuthorisation(**base)


def _decide(**overrides):
    """A clean, authorised baseline. Each test perturbs exactly one field."""
    params = dict(
        payg_key_fingerprint="deadbeef0000",
        payg_key_is_payg_class=True,
        voice_id_hash=VOICE_HASH,
        voice_exists=True,
        voice_window_remaining_s=167 * 3600,
        cash_balance=10.00,
        credit_balance=0.00,
        voucher_balance=15.00,
        owed_amount=0.00,
        billable_characters=44,
        previous_payg_refusal=True,
        previous_subscription_refusal=True,
    )
    params.update(overrides)
    return decide_cash_activation(_authorisation(), **params)


# --- A. the exposed-key gate --------------------------------------------------


@test
def test_an_exposed_key_is_refused_even_when_everything_else_is_perfect():
    """A compromised credential must not be spendable, whatever the balance says.

    This is the gate that exists because the key currently configured locally was pasted
    into chat. It has to refuse with CNY 10.00 of cash sitting on the account, because
    the whole point is that the money is not the problem -- the credential is.
    """
    verdict = _decide(
        payg_key_fingerprint=EXPOSED_PAYG_KEY_FINGERPRINTS[0], cash_balance=100.00
    )
    assert not verdict.authorised
    assert EXPOSED_PAYG_KEY_NOT_ROTATED in verdict.refusals, verdict.refusals
    joined = " ".join(verdict.reasons)
    assert "exposed in" in joined, joined
    assert "compromised" in joined, joined
    print("[ok] 1. an exposed pay-as-you-go key is refused however much cash is available")


@test
def test_the_gate_compares_the_fingerprint_it_is_given_and_never_re_hashes_it():
    """The bug this file exists to keep fixed.

    ``decide_cash_activation`` takes a *fingerprint*. An earlier revision tested it with
    ``payg_key_is_exposed(...)``, which hashes its argument again -- so the denylist
    lookup compared a hash of a hash against real fingerprints, never matched, and the
    gate reported AUTHORISED while holding a known-exposed key. A security gate that
    always passes is worse than no gate, because the receipt says it passed.
    """
    fingerprint = EXPOSED_PAYG_KEY_FINGERPRINTS[0]
    assert fingerprint in EXPOSED_PAYG_KEY_FINGERPRINTS
    assert key_fingerprint(fingerprint) not in EXPOSED_PAYG_KEY_FINGERPRINTS, (
        "if the fingerprint of a fingerprint were also on the denylist, this test would "
        "be passing for the wrong reason"
    )
    verdict = _decide(payg_key_fingerprint=fingerprint)
    assert not verdict.authorised, "the gate passed an exposed key"
    assert EXPOSED_PAYG_KEY_NOT_ROTATED in verdict.refusals

    # And the helper itself still works on a raw key, not on a fingerprint.
    assert payg_key_is_exposed("") is False
    print("[ok] 2. the gate matches the fingerprint directly and is not double-hashed")


@test
def test_the_fingerprint_helper_identifies_the_key_without_revealing_it():
    """A digest can be committed and compared; the key cannot."""
    key = "sk-api-" + "a" * 120
    fp = key_fingerprint(key)
    assert len(fp) == 12
    assert fp != key and key[-12:] not in fp
    assert key_fingerprint(key) == fp, "must be stable across calls"
    assert key_fingerprint("sk-api-" + "b" * 120) != fp
    print("[ok] 3. the fingerprint is stable, short, and does not carry the key")


@test
def test_a_payg_class_credential_is_required_because_only_payg_is_charged():
    """The Subscription Key was already measured returning 'insufficient balance'."""
    verdict = _decide(payg_key_is_payg_class=False)
    assert not verdict.authorised
    assert any("PAYG" in r for r in verdict.reasons), verdict.reasons
    print("[ok] 4. a non-PAYG credential cannot carry the one-time activation fee")


# --- B. the charge is bounded, and bounded honestly ----------------------------


@test
def test_the_projected_charge_is_nine_point_nine_one_five_four_against_ten():
    """The arithmetic is pinned, because being wrong in the Founder's favour is worse."""
    assert character_cost(44) == Decimal("3.50") * 44 / 10000
    verdict = _decide()
    assert verdict.authorised, verdict.refusals
    assert verdict.projected_total_cny == "9.9154", verdict.projected_total_cny
    assert verdict.ceiling_cny == "10.00"
    assert Decimal(verdict.projected_total_cny) <= Decimal(verdict.ceiling_cny)
    print("[ok] 5. the activation projects CNY 9.9154 against a CNY 10.00 ceiling")


@test
def test_boundedness_is_a_property_of_the_request_and_not_a_claimed_vendor_cap():
    """No source says the provider enforces a ceiling, and none may be implied."""
    payload = _decide().as_dict()
    note = payload["bounderiness_note"]
    assert "REQUEST is bounded by construction" in note, note
    assert "no source states" in note.lower(), note
    # The clone component is zero because it is already done, not because it is free.
    assert _decide().evidence["clone_creation_cny"] == "0.00"
    assert _decide().evidence["one_time_activation_cny"] == "9.90"
    print("[ok] 6. boundedness is attributed to the request, never to the provider")


@test
def test_a_longer_text_that_would_cross_the_ceiling_is_refused():
    """The ceiling is on the total, so a longer utterance cannot quietly exceed it.

    44 characters cost CNY 0.0154, leaving CNY 0.0846 of headroom. That is roughly 240
    further billable characters, so the refusal has to come from the arithmetic rather
    than from a hardcoded length check -- otherwise a future text edit would slip past.
    """
    verdict = _decide(billable_characters=10000)
    assert not verdict.authorised
    assert ACTIVATION_CHARGE_NOT_BOUNDED in verdict.refusals, verdict.refusals
    assert "exceeds the authorised ceiling" in " ".join(verdict.reasons)
    assert _decide(billable_characters=0).authorised is False, (
        "an uncountable text must refuse rather than be treated as free"
    )
    print("[ok] 7. a text whose charge crosses CNY 10.00 is refused by arithmetic")


@test
def test_insufficient_cash_refuses_rather_than_partially_paying():
    verdict = _decide(cash_balance=9.50)
    assert not verdict.authorised
    assert ACTIVATION_CHARGE_NOT_BOUNDED in verdict.refusals
    assert "below the projected" in " ".join(verdict.reasons)
    for unreadable in (None, "not-a-number", ""):
        assert _decide(cash_balance=unreadable).authorised is False, repr(unreadable)
    print("[ok] 8. insufficient or unreadable cash refuses; it never partially pays")


# --- C. only cash may move ----------------------------------------------------


@test
def test_credit_pack_and_outstanding_debt_refuse_the_activation():
    """Both are structurally-zero properties; non-zero means an unmodelled deduction."""
    for field, value in (("credit_balance", 10.00), ("owed_amount", 0.01)):
        verdict = _decide(**{field: value})
        assert not verdict.authorised, field
        assert ACTIVATION_CHARGE_NOT_BOUNDED in verdict.refusals
    assert "Credit Pack" in " ".join(_decide(credit_balance=5.0).reasons)
    assert "欠费" in " ".join(_decide(owed_amount=1.0).reasons) or "debt" in " ".join(
        _decide(owed_amount=1.0).reasons
    )
    print("[ok] 9. a Credit Pack balance or an existing 欠费 refuses the activation")


@test
def test_a_non_zero_voucher_is_not_a_refusal_but_is_recorded_as_a_watch_item():
    """The account has carried CNY 15.00 throughout, and it is not the blocker.

    The published deduction order inside 账户余额 is undocumented, so the honest position
    is: a voucher sitting there does not block a cash-authorised charge, and any movement
    in it afterwards is an anomaly rather than an acceptable outcome. Refusing on its
    presence would make this route unrunnable for a reason that was already measured and
    found not to be the cause.
    """
    verdict = _decide(voucher_balance=15.00)
    assert verdict.authorised, verdict.refusals
    assert verdict.evidence["voucher_balance"] == 15.00
    print("[ok] 10. a standing voucher does not block a cash-authorised activation")


# --- D. the voice is reused, never re-created ---------------------------------


@test
def test_a_missing_or_expired_voice_refuses_and_does_not_suggest_recloning():
    """Re-cloning is forbidden by the authorisation, so the refusal must not offer it."""
    missing = _decide(voice_exists=False)
    assert REFUSAL_VOICE_MISSING in missing.refusals

    expired = _decide(voice_window_remaining_s=-1.0)
    assert REFUSAL_VOICE_EXPIRED in expired.refusals, expired.refusals
    joined = " ".join(expired.reasons)
    assert "Re-cloning is forbidden" in joined, joined
    print("[ok] 11. a missing or expired voice refuses without offering to re-clone")


@test
def test_the_voice_hash_is_scoped_so_an_authorisation_cannot_move_to_another_voice():
    verdict = _decide(voice_id_hash="0" * 64)
    assert not verdict.authorised
    assert "different voice" in " ".join(verdict.reasons)
    print("[ok] 12. a cash authorisation cannot be spent on a different voice")


# --- E. single use, and the history that stays ---------------------------------


@test
def test_the_recovery_is_single_use_and_the_forbidden_shapes_all_refuse():
    assert RECOVERY_ALREADY_USED in _decide(cash_recovery_used=True).refusals
    for forbidden in (
        "allow_voucher_deduction",
        "allow_credit_pack_deduction",
        "allow_auto_recharge",
        "allow_reupload",
        "allow_reclone",
        "allow_automatic_retry",
    ):
        verdict = decide_cash_activation(
            _authorisation(**{forbidden: True}),
            payg_key_fingerprint="deadbeef0000",
            payg_key_is_payg_class=True,
            voice_id_hash=VOICE_HASH,
            voice_exists=True,
            voice_window_remaining_s=167 * 3600,
            cash_balance=10.00,
            credit_balance=0.00,
            voucher_balance=15.00,
            owed_amount=0.00,
            billable_characters=44,
            previous_payg_refusal=True,
            previous_subscription_refusal=True,
        )
        assert not verdict.authorised, forbidden
        assert "forbidden" in " ".join(verdict.reasons), forbidden
    print("[ok] 13. single use, and every forbidden shape is refused by name")


@test
def test_the_two_prior_refusals_are_recorded_as_context_and_never_cleared():
    """They are the reason the payment source changed; they are not undoable.

    Nothing in this module writes to the registry or clears a flag. What it must do is
    refuse to *treat them as absent* -- so the verdict carries them as evidence, and a
    run that has never seen them is distinguishable from one that has.
    """
    fresh = _decide(previous_payg_refusal=False, previous_subscription_refusal=False)
    assert fresh.evidence["previous_payg_refusal"] is False
    assert fresh.authorised, "the absence of prior refusals must not itself block"

    seen = _decide()
    assert seen.evidence["previous_payg_refusal"] is True
    assert seen.evidence["previous_subscription_refusal"] is True
    assert "NOT cleared" in seen.evidence["note_on_history"]
    print("[ok] 14. prior refusals are carried as evidence and never presented as undone")


@test
def test_the_receipt_carries_no_secret_and_no_host_literal():
    verdict = _decide().as_dict()
    blob = str(verdict)
    for banned in ("sk-api-", "sk-cp-", "Bearer ", "Authorization", "minimaxi"):
        assert banned not in blob, banned
    assert verdict["production_ready"] is False
    assert verdict["human_review"] == "PENDING_FOUNDER_REVIEW"
    assert verdict["limits"]["max_activation_tts_count"] == 1
    assert verdict["limits"]["max_upload_count"] == 0
    assert verdict["limits"]["max_clone_count"] == 0
    assert verdict["limits"]["allow_automatic_retry"] is False
    print("[ok] 15. the receipt is public-safe and records a single-use, no-retry budget")


# --- F. the Founder's scoped exception to the exposed-key gate -----------------


def _exception(**overrides) -> ExposedKeyException:
    base = {
        "granted": True,
        "key_fingerprint": EXPOSED_PAYG_KEY_FINGERPRINTS[0],
        "voice_id_hash": VOICE_HASH,
        "model": "speech-2.8-hd",
        "billable_characters": 44,
        "max_cash_debit_cny": Decimal("10.00"),
        "granted_on": "2026-10-12",
    }
    base.update(overrides)
    return ExposedKeyException(**base)


@test
def test_the_default_is_still_refusal_so_the_exception_can_only_be_granted():
    """Adding an escape hatch must not quietly turn it into the default."""
    verdict = _decide(payg_key_fingerprint=EXPOSED_PAYG_KEY_FINGERPRINTS[0])
    assert not verdict.authorised
    assert EXPOSED_PAYG_KEY_NOT_ROTATED in verdict.refusals
    assert _decide(payg_key_fingerprint="deadbeef0000").authorised, (
        "the exception must not affect a key that is not exposed"
    )
    print("[ok] 16. without a granted exception an exposed key is still refused")


@test
def test_a_matching_exception_permits_the_spend_but_never_hides_the_exposure():
    """The exception permits one spend. It cannot rewrite the security record."""
    verdict = _decide(
        payg_key_fingerprint=EXPOSED_PAYG_KEY_FINGERPRINTS[0],
        exception=_exception(),
    )
    assert verdict.authorised, verdict.refusals
    # The exposure is still recorded as true. This is the whole contract.
    assert verdict.evidence["exposed_key"] is True
    assert verdict.evidence["exposed_key_exception_applied"] is True
    applied = verdict.evidence["exposed_key_exception"]
    assert applied["name"] == FOUNDER_AUTHORISED_EXPOSED_KEY_REUSE
    assert "not a rotation and not a fix" in applied["note"]
    assert FOUNDER_AUTHORISED_EXPOSED_KEY_REUSE in " ".join(verdict.reasons)
    assert "should still be rotated" in " ".join(verdict.reasons)
    print("[ok] 17. a matching exception permits the spend and keeps exposed_key=true")


@test
def test_the_exception_is_scoped_to_one_key_one_voice_one_model_one_length():
    """Every way a stale exception becomes a wrong one is a mismatch to check."""
    fp = EXPOSED_PAYG_KEY_FINGERPRINTS[0]
    cases = {
        "different key": dict(key_fingerprint="ffffffffffff"),
        "different voice": dict(voice_id_hash="1" * 64),
        "different model": dict(model="speech-2.6"),
        "different length": dict(billable_characters=88),
        "lower ceiling": dict(max_cash_debit_cny=Decimal("5.00")),
    }
    for label, over in cases.items():
        verdict = _decide(
            payg_key_fingerprint=fp, exception=_exception(**over)
        )
        assert not verdict.authorised, f"{label} must not be covered by the exception"
        assert EXPOSED_PAYG_KEY_NOT_ROTATED in verdict.refusals, label
        assert verdict.evidence["exposed_key"] is True, label
    print("[ok] 18. the exception covers one key, one voice, one model and one length")


@test
def test_the_exception_is_single_use_across_processes():
    """``consumed`` is the flag; without it a one-time grant becomes a standing hole."""
    verdict = _decide(
        payg_key_fingerprint=EXPOSED_PAYG_KEY_FINGERPRINTS[0],
        exception=_exception(consumed=True),
    )
    assert not verdict.authorised
    assert "already been consumed" in " ".join(verdict.reasons)
    print("[ok] 19. a consumed exception is refused; single use survives a restart")


@test
def test_an_exception_never_overrides_the_other_gates():
    """It narrows one gate only. Cash, ceiling, voice window and single-use still bind."""
    fp = EXPOSED_PAYG_KEY_FINGERPRINTS[0]
    for label, over in (
        ("cash too low", dict(cash_balance=1.00)),
        ("voice expired", dict(voice_window_remaining_s=-1.0)),
        ("voice missing", dict(voice_exists=False)),
        ("already recovered", dict(cash_recovery_used=True)),
        ("credit pack present", dict(credit_balance=5.0)),
        ("outstanding debt", dict(owed_amount=1.0)),
        ("text over ceiling", dict(billable_characters=100000)),
    ):
        verdict = _decide(
            payg_key_fingerprint=fp, exception=_exception(), **over
        )
        assert not verdict.authorised, f"{label} must still block under the exception"
    print("[ok] 20. the exception relaxes the key gate and nothing else")


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
    print(f"\nAll {total} cash-activation-recovery regression tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())