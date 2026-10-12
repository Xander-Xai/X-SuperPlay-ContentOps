"""``CASH_ACTIVATION_RECOVERY`` -- one authorised cash-paid activation. Issue #34.

Why this is a separate module and not a flag on the existing script
-----------------------------------------------------------------
:mod:`contentops.media.minimax_voice_clone` refuses a second activation, and that refusal
is correct and must survive: the pay-as-you-go first-synthesis attempt on 2026-10-12 was
refused with ``insufficient balance``, and the Subscription-Key probe was refused
identically. Re-running either is not a retry, it is a fresh payment under a fresh
authorisation -- so it needs its own authorisation record, its own attempt id and its own
budget rather than a way to talk the old guard down.

Deleting the protection to get past it would also destroy the only thing that protects the
next operator from spending twice. So the guard stays; this sits beside it.

What it authorises
------------------
The Founder authorised, for this account, a single pay-as-you-go synthesis of an
**already-existing** cloned voice, paid in cash, with a hard ceiling of CNY 10.00.

===================================  ==========  ==============
component                             amount      paid from
===================================  ==========  ==============
one-time clone activation fee        CNY 9.90    cash
activation synthesis characters      CNY 0.0154  cash
upload / clone creation              CNY 0.00    not performed
===================================  ==========  ==============

And forbids: voucher deduction, Credit Pack deduction, automatic recharge, re-uploading
the sample, re-cloning, and automatic retry.

On "bounded", precisely
----------------------
This module refuses to claim the provider enforces a ceiling. It does not: no documented
source states one, and the previous round's whole lesson is that a commercial assurance
and an API behaviour are different things.

What is bounded is the **request**, by construction: exactly one call, a fixed
44-billable-character text, a published per-character rate, and a published one-time fee.
That makes the *expected* total 9.9154 against an authorised 10.00. What the provider
actually deducts is then **measured** against the same ceiling, and an overrun is a stop
condition, not a rounding remark. Request-side control and outcome-side verification are
kept separate here because conflating them is how a projected number becomes a reported
guarantee.

The key-rotation gate
---------------------
The pay-as-you-go key currently configured locally was pasted into chat and is therefore
exposed. Paying through a compromised credential is not acceptable at any price, so
:data:`EXPOSED_PAYG_KEY_FINGERPRINTS` refuses it by digest before anything else happens.
A digest identifies a key without storing it -- the same pattern the receipts already use
for provider voice ids -- and it persists across processes, so the gate cannot be walked
past by re-running the tool.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "ACTIVATION_ATTEMPT_REFUSED",
    "ACTIVATION_CHARGE_NOT_BOUNDED",
    "CASH_ACTIVATION_RECOVERY",
    "CashActivationAuthorisation",
    "CashActivationVerdict",
    "EXPOSED_PAYG_KEY_NOT_ROTATED",
    "EXPOSED_PAYG_KEY_FINGERPRINTS",
    "FINGERPRINT_PREFIX_LEN",
    "REFUSAL_VOICE_EXPIRED",
    "REFUSAL_VOICE_MISSING",
    "RECOVERY_ALREADY_USED",
    "decide_cash_activation",
    "key_fingerprint",
    "payg_key_is_exposed",
]

RECOVERY_NAME = CASH_ACTIVATION_RECOVERY = "CASH_ACTIVATION_RECOVERY"

#: How much of the SHA256 digest is kept. Twelve hex characters is 48 bits, which is far
#: more than enough to distinguish two 126-character random keys and far too little to be
#: useful to anyone who does not already hold the key.
FINGERPRINT_PREFIX_LEN = 12

#: SHA256 prefixes of pay-as-you-go keys that were exposed in chat and must never carry a
#: real charge.
#:
#: Storing the digest rather than the key is the whole point: the check has to outlive the
#: process that discovered the exposure, and it has to be committable, so it is a one-way
#: fingerprint of a high-entropy random string. Nothing here narrows a keyspace.
EXPOSED_PAYG_KEY_FINGERPRINTS: Tuple[str, ...] = ("2ac10c6e9029",)

EXPOSED_PAYG_KEY_NOT_ROTATED = "EXPOSED_PAYG_KEY_NOT_ROTATED"
ACTIVATION_CHARGE_NOT_BOUNDED = "ACTIVATION_CHARGE_NOT_BOUNDED"
ACTIVATION_ATTEMPT_REFUSED = "ACTIVATION_ATTEMPT_REFUSED"
RECOVERY_ALREADY_USED = "RECOVERY_ALREADY_USED"
REFUSAL_VOICE_MISSING = "CLONED_VOICE_MISSING"
REFUSAL_VOICE_EXPIRED = "CLONED_VOICE_EXPIRED"

#: Documented components. ``clone_creation`` is zero because the published rule is
#: 复刻音色时不立即收费 -- the clone call is already done and was not charged; this
#: recovery does not call it again.
CLONE_CREATION_CNY = Decimal("0.00")
ONE_TIME_ACTIVATION_CNY = Decimal("9.90")
SPEECH_2_8_HD_CNY_PER_10K = Decimal("3.50")


def key_fingerprint(key: str) -> str:
    """A stable, non-reversible fingerprint of a credential."""
    return hashlib.sha256((key or "").encode("utf-8")).hexdigest()[:FINGERPRINT_PREFIX_LEN]


def payg_key_is_exposed(key: str) -> bool:
    """Is this exact credential one that was exposed in chat?"""
    return bool(key) and key_fingerprint(key) in EXPOSED_PAYG_KEY_FINGERPRINTS


@dataclass(frozen=True)
class CashActivationAuthorisation:
    """The Founder's cash authorisation, exactly as granted.

    Split from the payment rather than merged into one number, because the two components
    have different owners: CNY 9.90 is the vendor's price for the voice, and the character
    cost is this module's own synthesis. Presenting one total would imply a single
    approval covered both.
    """

    max_cash_debit_cny: Decimal = Decimal("10.00")
    one_time_activation_cny: Decimal = ONE_TIME_ACTIVATION_CNY
    allow_voucher_deduction: bool = False
    allow_credit_pack_deduction: bool = False
    allow_auto_recharge: bool = False
    allow_reupload: bool = False
    allow_reclone: bool = False
    allow_automatic_retry: bool = False
    max_activation_tts_count: int = 1
    max_upload_count: int = 0
    max_clone_count: int = 0
    voice_id_hash: str = ""
    authorised_by: str = "FOUNDER"
    authorised_on: str = "2026-10-12"
    note: str = (
        "one cash-paid first activation of an existing clone; no voucher, no Credit "
        "Pack, no recharge, no re-upload, no re-clone, no retry"
    )


@dataclass
class CashActivationVerdict:
    status: str = ACTIVATION_CHARGE_NOT_BOUNDED
    authorised: bool = False
    refusals: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)
    projected_total_cny: str = "0.00"
    ceiling_cny: str = "0.00"

    def add(self, code: str, reason: str) -> None:
        if code not in self.refusals:
            self.refusals.append(code)
        self.reasons.append(reason)

    def as_dict(self) -> Dict[str, Any]:
        payload = {
            "schema": "contentops.cash-activation-recovery/v1",
            "recovery": RECOVERY_NAME,
            "status": self.status,
            "authorised": self.authorised,
            "refusals": list(self.refusals),
            "reasons": list(self.reasons),
            "evidence": dict(self.evidence),
            "projected_total_cny": self.projected_total_cny,
            "ceiling_cny": self.ceiling_cny,
            "limits": {
                "max_cash_debit_cny": "10.00",
                "allow_voucher_deduction": False,
                "allow_credit_pack_deduction": False,
                "allow_auto_recharge": False,
                "allow_reupload": False,
                "allow_reclone": False,
                "allow_automatic_retry": False,
                "max_activation_tts_count": 1,
                "max_upload_count": 0,
                "max_clone_count": 0,
                "scope": "one voice_id_hash, one cash activation",
            },
            "bounderiness_note": (
                "The REQUEST is bounded by construction: one call, a fixed "
                "44-billable-character text, a published per-character rate and a "
                "published one-time fee. No source states that the PROVIDER enforces a "
                "ceiling, and none is claimed here. The actual debit is measured against "
                "the ceiling after the call, and an overrun is a stop condition."
            ),
            "production_ready": False,
            "human_review": "PENDING_FOUNDER_REVIEW",
        }
        blob = json.dumps(payload, ensure_ascii=False)
        for banned in ("Authorization", "Bearer ", "sk-cp-", "sk-api-"):
            if banned in blob:
                raise ValueError(
                    f"refusing to serialise a cash activation receipt containing {banned!r}"
                )
        return payload


def _dec(value: Any) -> Optional[Decimal]:
    """Parse a balance, or return None.

    None is the answer for anything unreadable, and the caller must treat it as a refusal.
    ``Decimal(str(""))`` raises :class:`decimal.InvalidOperation` -- which is neither a
    ``TypeError`` nor a ``ValueError``, so a bare ``except`` clause misses it and an
    empty balance field crashes the decision instead of stopping it. That is the worst
    possible failure for a payment gate: it turns "I cannot tell what this costs" into a
    traceback rather than a refusal.
    """
    if value is None:
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError, ArithmeticError):
        return None


def character_cost(billable_characters: int) -> Decimal:
    """The published character cost, from the rate and the counted characters."""
    return SPEECH_2_8_HD_CNY_PER_10K * Decimal(int(billable_characters)) / Decimal(10000)


def decide_cash_activation(
    authorisation: CashActivationAuthorisation,
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
    billable_characters: int,
    previous_payg_refusal: bool,
    previous_subscription_refusal: bool,
    cash_recovery_used: bool = False,
    upload_count: int = 0,
    clone_count: int = 0,
) -> CashActivationVerdict:
    """Decide whether the one cash activation may be sent. No I/O, no generation.

    Every argument is a fact the caller measured. This is the policy, kept in one readable
    block, because a payment gate scattered across a caller's ``if`` statements is a
    payment gate that will eventually be skipped.
    """
    verdict = CashActivationVerdict()
    verdict.ceiling_cny = str(authorisation.max_cash_debit_cny)

    # 1. Credential. A compromised key is not an acceptable way to spend money, and the
    #    check is a digest comparison so it survives process restarts.
    #
    #    Membership is tested directly. Calling :func:`payg_key_is_exposed` here would
    #    hash the fingerprint a second time and never match anything -- a security gate
    #    that always passes is worse than no gate, because it is reported as passing.
    if payg_key_fingerprint in EXPOSED_PAYG_KEY_FINGERPRINTS:
        verdict.add(
            EXPOSED_PAYG_KEY_NOT_ROTATED,
            f"the configured pay-as-you-go key matches a credential that was exposed in "
            f"chat (fingerprint {payg_key_fingerprint}). It must be revoked at "
            "账户管理 > 接口密钥 and replaced in the local .env before any charged call. "
            "Paying through a compromised credential is not acceptable at any price.",
        )
    if not payg_key_is_payg_class:
        verdict.add(
            ACTIVATION_ATTEMPT_REFUSED,
            "the activation credential does not classify as PAYG. The one-time fee is "
            "charged only to a pay-as-you-go key; a Subscription Key was already "
            "measured returning 'insufficient balance' for this same voice.",
        )

    # 2. The voice must already exist and still be activatable. Absence here is NOT
    #    evidence of absence provider-side: get_voice lists voice_cloning entries only
    #    after a voice has been used in T2A, so an unactivated clone is legitimately
    #    invisible. The local registry plus the clone response are the authority.
    if not voice_exists:
        verdict.add(
            REFUSAL_VOICE_MISSING,
            "the local registry does not record this voice. This recovery reuses an "
            "existing clone and never creates one, so there is nothing to activate.",
        )
    elif voice_window_remaining_s is not None and voice_window_remaining_s <= 0:
        verdict.add(
            REFUSAL_VOICE_EXPIRED,
            f"the cloned voice was created {(-voice_window_remaining_s) / 3600:.1f}h ago "
            "and provider storage will have deleted it. Re-cloning is forbidden here and "
            "requires a separate authorisation.",
        )

    # 3. The charge must be bounded by construction before it is attempted.
    try:
        chars = int(billable_characters)
    except (TypeError, ValueError):
        chars = -1
    if chars <= 0:
        verdict.add(
            ACTIVATION_CHARGE_NOT_BOUNDED,
            f"billable_characters is {billable_characters!r}; the character cost cannot "
            "be computed, so the charge is not bounded.",
        )
        chars = 0
    character_cny = character_cost(chars) if chars else Decimal("0")
    projected = CLONE_CREATION_CNY + authorisation.one_time_activation_cny + character_cny
    verdict.projected_total_cny = f"{projected:.4f}"
    if projected > authorisation.max_cash_debit_cny:
        verdict.add(
            ACTIVATION_CHARGE_NOT_BOUNDED,
            f"projected cash debit CNY {projected:.4f} exceeds the authorised ceiling "
            f"CNY {authorisation.max_cash_debit_cny}. "
            f"({chars} billable characters at CNY {SPEECH_2_8_HD_CNY_PER_10K}/10k = "
            f"CNY {character_cny:.6f}, plus the CNY "
            f"{authorisation.one_time_activation_cny} one-time fee.)",
        )

    # 4. Cash must cover it, and the other two pots must be exactly what was authorised.
    if _dec(cash_balance) is None:
        verdict.add(
            ACTIVATION_CHARGE_NOT_BOUNDED,
            f"cash balance could not be read ({cash_balance!r}). An unreadable balance "
            "is never treated as sufficient and never treated as zero.",
        )
    elif _dec(cash_balance) < projected:
        verdict.add(
            ACTIVATION_CHARGE_NOT_BOUNDED,
            f"cash_balance CNY {cash_balance} is below the projected CNY {projected:.4f}. "
            "The authorised payment source cannot pay the authorised amount.",
        )
    # Voucher and Credit Pack are forbidden as payment sources. A non-zero voucher is not
    # itself a failure -- the account has had CNY 15.00 sitting on it throughout -- but
    # deduction priority against cash is undocumented, so the receipt must record that a
    # voucher movement would be an anomaly rather than a pass.
    if _dec(credit_balance) is None:
        verdict.add(
            ACTIVATION_CHARGE_NOT_BOUNDED,
            f"credit balance could not be read ({credit_balance!r}), so a Credit Pack "
            "deduction cannot be ruled out.",
        )
    elif _dec(credit_balance) != 0:
        verdict.add(
            ACTIVATION_CHARGE_NOT_BOUNDED,
            f"credit_balance is {credit_balance}. Credit Pack use is not authorised and "
            "cannot be ruled out as a fallback deduction source.",
        )
    if _dec(owed_amount) is None:
        verdict.add(
            ACTIVATION_CHARGE_NOT_BOUNDED,
            f"owed amount could not be read ({owed_amount!r}), so no 欠费 can be ruled out.",
        )
    elif _dec(owed_amount) != 0:
        verdict.add(
            ACTIVATION_CHARGE_NOT_BOUNDED,
            f"owed_amount is {owed_amount}. Activating on an account already carrying debt "
            "is not authorised.",
        )

    # 5. Scope and shape.
    if authorisation.voice_id_hash and voice_id_hash != authorisation.voice_id_hash:
        verdict.add(
            ACTIVATION_ATTEMPT_REFUSED,
            "this authorisation covers a different voice than the one presented; it "
            "cannot be transferred to another voice.",
        )
    if upload_count > authorisation.max_upload_count:
        verdict.add(
            ACTIVATION_ATTEMPT_REFUSED,
            f"{upload_count} upload(s) recorded against a limit of "
            f"{authorisation.max_upload_count}. Re-uploading the Founder's voice is "
            "forbidden.",
        )
    if clone_count > authorisation.max_clone_count:
        verdict.add(
            ACTIVATION_ATTEMPT_REFUSED,
            f"{clone_count} clone(s) recorded against a limit of "
            f"{authorisation.max_clone_count}. Re-cloning is forbidden.",
        )
    if cash_recovery_used:
        verdict.add(
            RECOVERY_ALREADY_USED,
            "this cash recovery has already been used. The authorisation is for one "
            "activation; a second would be a second charge.",
        )
    for label, value in (
        ("voucher_deduction", authorisation.allow_voucher_deduction),
        ("credit_pack_deduction", authorisation.allow_credit_pack_deduction),
        ("auto_recharge", authorisation.allow_auto_recharge),
        ("reupload", authorisation.allow_reupload),
        ("reclone", authorisation.allow_reclone),
        ("automatic_retry", authorisation.allow_automatic_retry),
    ):
        if value:
            verdict.add(
                ACTIVATION_ATTEMPT_REFUSED,
                f"{label} is enabled in the authorisation. It is forbidden.",
            )

    verdict.evidence = {
        "payg_key_fingerprint": payg_key_fingerprint,
        "payg_key_is_payg_class": payg_key_is_payg_class,
        "voice_id_hash": voice_id_hash,
        "voice_window_remaining_h": (
            None if voice_window_remaining_s is None
            else round(voice_window_remaining_s / 3600.0, 2)
        ),
        "cash_balance": cash_balance,
        "credit_balance": credit_balance,
        "voucher_balance": voucher_balance,
        "owed_amount": owed_amount,
        "billable_characters": chars,
        "character_cost_cny": f"{character_cny:.6f}",
        "one_time_activation_cny": str(authorisation.one_time_activation_cny),
        "clone_creation_cny": str(CLONE_CREATION_CNY),
        "projected_total_cny": verdict.projected_total_cny,
        "previous_payg_refusal": previous_payg_refusal,
        "previous_subscription_refusal": previous_subscription_refusal,
        "note_on_history": (
            "the two earlier refusals are preserved and are NOT cleared by this "
            "authorisation. They are recorded because they are why the payment source "
            "changed from voucher to cash, not because they may be undone."
        ),
    }
    verdict.authorised = not verdict.refusals
    verdict.status = "AUTHORISED" if verdict.authorised else verdict.refusals[0]
    return verdict