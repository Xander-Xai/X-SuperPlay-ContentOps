"""``FOUNDER_VOUCHER_ACTIVATION`` — a bounded, single-use payment authorisation.

Why this is its own module
--------------------------
:mod:`contentops.media.clone_route` decides *whether the commercial route is open*.
:mod:`contentops.media.billing_guard` *reads the money*. Neither of them can authorise a
charge, and an authorisation is the one thing that must never be inferred from the shape
of the other two. So this holds exactly one authorisation, with hard ceilings, and
refuses rather than clamps.

The authorisation, as the Founder granted it
--------------------------------------------
======================  =========  ===================================================
field                   value      meaning
======================  =========  ===================================================
allowed_voucher_spend   10.00      a ceiling on the **total**, not per component
allowed_cash_spend      0.00       zero, and structurally so: cash_balance is 0.00
allowed_credit_spend    0.00       zero, and structurally so: credit_balance is 0.00
allow_auto_recharge     False      forbidden, not merely unused
max_clone_count         1          one clone, ever, for this authorisation
max_activation_count    1          one activation TTS, ever, for this authorisation
allow_unbounded_payg    False      this is not a general PAYG licence
======================  =========  ===================================================

The ceiling is on the **total**. A ¥9.90 voice fee plus a ¥0.0154 character fee is
¥9.9154 and passes; ¥9.90 plus a longer activation text could cross ¥10 and must refuse.
Authorising each component separately would let two sub-ceiling charges add up past the
number the Founder actually agreed to.

Voucher eligibility is a *precondition*, not a preference
----------------------------------------------------------
The authorisation says the Founder will pay with the voucher. It does not say the voucher
**can** pay. Those are different claims, and conflating them is how a ¥9.90 charge gets
attempted against an instrument that cannot carry it.

:data:`VOUCHER_ELIGIBILITY_UNPROVEN` is the required input, and it defaults to refusing.
An operator who believes the voucher applies must prove it and pass it in; the module
never derives eligibility from a balance, because ``voucher_balance = 15.00`` is a
statement that a voucher exists, not that it covers 音色管理.

What the official sources actually say, and what they do not
------------------------------------------------------------
``VERIFIED_OFFICIAL``
    - 代金券 is an **order payment method**: 使用代金券 | 扣除代金券后实际支付的金额,
      代金券抵扣部分不可开票 (M Plan FAQ, 开票金额怎么计算).
    - 账户余额只有在使用按量计费 API Key 时才会扣除, so a pay-as-you-go request draws on
      the account balance -- which is the only place a voucher could be applied.
    - 扣费顺序为 M Plan 额度优先、积分包其次, and 积分包仅用于其支持的模型与能力.
      积分包支持...图像与音频生成 -- 快速复刻 is not named, so it cannot pay this fee.

``UNKNOWN``
    - Whether a voucher offsets **API 调用费用** as opposed to **orders**. The one
      official statement that says 使用范围:仅可用于抵扣 MiniMax 开放平台内的 API 调用费用
      sits inside the **好友邀请活动** (referral reward) section and governs that
      programme's voucher. This account's voucher provenance is unknown, so that scope
      cannot be transferred to it.
    - 付费服务协议 4.4 defers the question: 代金券只可用于消费,不可用于抵扣欠费金额。
      具体权益应以产品界面公示及服务权益实际展示为准 — the definitive scope lives in the
      product console, which no API endpoint exposes.
    - Deduction priority **between voucher and cash** within 账户余额 is undocumented.
    - This voucher's issuance date and remaining validity are not exposed by any endpoint
      available here.

The honest consequence is :data:`VOUCHER_CLONE_FEE_ELIGIBILITY_UNKNOWN`, and this module
refuses on it. It is not a documentation gap that more searching closes: the answer is on
a page an API client cannot read.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

__all__ = [
    "ACTIVATION_ALREADY_USED",
    "ACTIVATION_COST_ABOVE_AUTHORISED_TOTAL",
    "ACTIVATION_VOICE_ID_MISMATCH",
    "EVIDENCE_UNKNOWN",
    "EVIDENCE_LIVE_REFUTED",
    "EVIDENCE_VERIFIED_ACCOUNT_TERMS",
    "EVIDENCE_VERIFIED_OFFICIAL",
    "FOUNDER_VOUCHER_ACTIVATION",
    "REFUSAL_PAYG_TTS_UNBOUNDED",
    "REFUSAL_RETRY",
    "REFUSAL_VOUCHER_ELIGIBILITY_REFUTED",
    "VOUCHER_CLONE_FEE_ELIGIBILITY_UNKNOWN",
    "VOUCHER_BALANCE_INSUFFICIENT",
    "VOUCHER_CASH_FALLBACK_RISK",
    "VOUCHER_CREDIT_FALLBACK_RISK",
    "VOUCHER_ACTIVATION_AUTHORISED",
    "VoucherActivation",
    "VoucherActivationVerdict",
    "decide_voucher_activation",
]

#: Evidence grades, weakest last. Only the first two may clear eligibility.
EVIDENCE_VERIFIED_OFFICIAL = "VERIFIED_OFFICIAL"
EVIDENCE_VERIFIED_ACCOUNT_TERMS = "VERIFIED_ACCOUNT_VOUCHER_TERMS"
EVIDENCE_UNKNOWN = "UNKNOWN"

#: A live call on this account that **refuted** the eligibility claim. Ranked above both
#: grades above rather than folded into :data:`EVIDENCE_UNKNOWN`, because "we do not
#: know" and "we tested it and it does not work" call for different next actions, and a
#: receipt that conflates them sends the next reader back out to re-run the experiment
#: that has already been paid for.
#:
#: On 2026-10-12 the activation was attempted with the pay-as-you-go key that customer
#: service had said the voucher would cover. The platform answered ``insufficient
#: balance`` with ``voucher_balance`` 15.00, ``available_amount`` 15.00 and
#: ``cash_balance`` 0.00, and every balance was unchanged afterwards. Nothing was
#: charged. See :data:`contentops.media.clone_route.EVIDENCE_LIVE_REFUTED`.
EVIDENCE_LIVE_REFUTED = "VERIFIED_LOCAL_REFUTED"

REFUSAL_VOUCHER_ELIGIBILITY = "VOUCHER_CLONE_FEE_ELIGIBILITY_UNKNOWN"
REFUSAL_VOUCHER_ELIGIBILITY_REFUTED = "VOUCHER_CLONE_FEE_ELIGIBILITY_REFUTED"
VOUCHER_CLONE_FEE_ELIGIBILITY_UNKNOWN = REFUSAL_VOUCHER_ELIGIBILITY
VOUCHER_BALANCE_INSUFFICIENT = "VOUCHER_BALANCE_INSUFFICIENT"
VOUCHER_CASH_FALLBACK_RISK = "VOUCHER_CASH_FALLBACK_RISK"
VOUCHER_CREDIT_FALLBACK_RISK = "VOUCHER_CREDIT_FALLBACK_RISK"
ACTIVATION_COST_ABOVE_AUTHORISED_TOTAL = "ACTIVATION_COST_ABOVE_AUTHORISED_TOTAL"
ACTIVATION_ALREADY_USED = "ACTIVATION_ALREADY_USED"
ACTIVATION_VOICE_ID_MISMATCH = "ACTIVATION_VOICE_ID_MISMATCH"
REFUSAL_RETRY = "AUTOMATIC_RETRY_FORBIDDEN"
REFUSAL_PAYG_TTS_UNBOUNDED = "UNBOUNDED_PAYG_TTS_FORBIDDEN"

VOUCHER_ACTIVATION_AUTHORISED = "FOUNDER_VOUCHER_ACTIVATION"


@dataclass(frozen=True)
class FounderVoucherActivation:
    """The authorisation exactly as granted. Immutable, and total-bounded.

    ``allowed_voucher_spend_cny`` is the ceiling on the **combined** charge, so the
    component ceilings cannot be used to authorise a total the Founder never agreed to.
    """

    allowed_voucher_spend_cny: Decimal = Decimal("10.00")
    allowed_cash_spend_cny: Decimal = Decimal("0.00")
    allowed_credit_pack_spend_cny: Decimal = Decimal("0.00")
    allow_auto_recharge: bool = False
    max_clone_count: int = 1
    max_activation_tts_count: int = 1
    allow_unbounded_payg_tts: bool = False
    #: Scoped to one voice. An authorisation for one clone must not be reusable for a
    #: different voice, which is what turns a one-off permission into a standing one.
    voice_alias: str = "founder_primary_v1"
    voice_id_hash: str = ""
    authorised_by: str = "FOUNDER"
    note: str = (
        "one-time activation of one Founder clone, paid from the existing CNY 15.00 "
        "voucher; no recharge, no cash, no Credit Pack"
    )


@dataclass
class VoucherActivationVerdict:
    status: str = REFUSAL_VOUCHER_ELIGIBILITY
    authorised: bool = False
    refusals: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    evidence: Dict[str, Any] = field(default_factory=dict)

    def add(self, code: str, reason: str) -> None:
        if code not in self.refusals:
            self.refusals.append(code)
        self.reasons.append(reason)

    def as_dict(self) -> Dict[str, Any]:
        payload = {
            "schema": "contentops.voucher-activation/v1",
            "authorisation": VOUCHER_ACTIVATION_AUTHORISED,
            "status": self.status,
            "authorised": self.authorised,
            "refusals": list(self.refusals),
            "reasons": list(self.reasons),
            "evidence": dict(self.evidence),
            "limits": {
                "allowed_voucher_spend_cny": "10.00",
                "allowed_cash_spend_cny": "0.00",
                "allowed_credit_pack_spend_cny": "0.00",
                "allow_auto_recharge": False,
                "max_clone_count": 1,
                "max_activation_tts_count": 1,
                "allow_unbounded_payg_tts": False,
                "scope": "one voice_alias, one voice_id_hash",
            },
            "payg_tts_allowed": False,
            "automatic_recharge_allowed": False,
            "production_ready": False,
            "human_review": "PENDING_FOUNDER_REVIEW",
        }
        blob = json.dumps(payload, ensure_ascii=False)
        for banned in ("Authorization", "Bearer ", "sk-cp-", "sk-api-"):
            if banned in blob:
                raise ValueError(
                    f"refusing to serialise an activation receipt containing {banned!r}"
                )
        return payload


def decide_voucher_activation(
    authorisation: FounderVoucherActivation,
    *,
    voucher_eligibility: str,
    voucher_eligibility_basis: str,
    voucher_balance: Optional[float],
    cash_balance: Optional[float],
    credit_balance: Optional[float],
    projected_total_cny: str,
    voice_id_hash: str,
    clone_count: int = 0,
    activation_tts_count: int = 0,
    retry: bool = False,
    payg_tts_bounded: bool = False,
) -> VoucherActivationVerdict:
    """Decide whether the one authorised activation may be charged. No I/O.

    Every argument is a fact the caller measured or established. The function is the
    policy, kept in one readable block, because a payment gate scattered across a
    caller's ``if`` statements is a payment gate that will eventually be skipped.

    Args:
        voucher_eligibility: one of :data:`EVIDENCE_*`. Only the first two clear the
            eligibility gate; :data:`EVIDENCE_UNKNOWN` refuses.
        voucher_eligibility_basis: what that grade rests on, quoted into the receipt.
        projected_total_cny: the combined expected charge -- clone fee plus activation
            characters. Compared against the ceiling as one number.
        voice_id_hash: the voice this authorisation covers. A mismatch refuses, so a
            permission granted for one clone cannot be spent on another.
        payg_tts_bounded: whether the caller has a hard cap on PAYG synthesis. An
            unbounded PAYG path is refused regardless of how small this run's charge is.

    Returns:
        A :class:`VoucherActivationVerdict`. ``authorised`` is True only when nothing
        refused.
    """
    verdict = VoucherActivationVerdict()
    verdict.evidence = {
        "voucher_eligibility": voucher_eligibility,
        "voucher_eligibility_basis": voucher_eligibility_basis,
        "voucher_balance": voucher_balance,
        "cash_balance": cash_balance,
        "credit_balance": credit_balance,
        "projected_total_cny": projected_total_cny,
        "allowed_voucher_spend_cny": str(authorisation.allowed_voucher_spend_cny),
        "allowed_cash_spend_cny": str(authorisation.allowed_cash_spend_cny),
        "allowed_credit_pack_spend_cny": str(authorisation.allowed_credit_pack_spend_cny),
        "authorised_for_voice_id_hash": authorisation.voice_id_hash,
        "presented_voice_id_hash": voice_id_hash,
    }

    # 1. Eligibility. First, because everything after it is arithmetic on an
    #    instrument that may not exist. This is the gate this round stops at.
    if voucher_eligibility == EVIDENCE_LIVE_REFUTED:
        # Checked before the UNKNOWN branch so a measurement is never reported as
        # ignorance. The two refuse identically; only the reason and the next action
        # differ, and collapsing them would discard the most expensive fact this
        # module has ever been given.
        verdict.add(
            REFUSAL_VOUCHER_ELIGIBILITY_REFUTED,
            "voucher eligibility was refuted by a live call on this account, not left "
            "unknown. The activation was sent with the pay-as-you-go API Key that "
            "customer service had said the voucher would cover, and the platform "
            "answered 'insufficient balance' while voucher_balance was 15.00, "
            "available_amount was 15.00 and cash_balance was 0.00. Every balance was "
            "unchanged afterwards, so nothing was charged and no 欠费 was created. The "
            "voucher is real, it is on the account, and it does not fund a pay-as-you-go "
            "API call. Do not re-attempt on the same assurance; the next step is a "
            "payment-instrument decision by the Founder, not another trial.",
        )
    elif voucher_eligibility not in (
        EVIDENCE_VERIFIED_OFFICIAL,
        EVIDENCE_VERIFIED_ACCOUNT_TERMS,
    ):
        # The basis is carried in `evidence` rather than appended here: repeating it in
        # the prose made the printed refusal twice as long as the claim it supports,
        # which is its own kind of noise in a gate an operator has to read under time
        # pressure.
        verdict.add(
            REFUSAL_VOUCHER_ELIGIBILITY,
            "voucher eligibility is not established. The Founder authorised payment "
            "FROM the voucher; that is an instruction about which instrument to use, "
            "not proof that this instrument covers 音色管理. The one official statement "
            "that a voucher offsets API 调用费用 is scoped to the 好友邀请活动 referral "
            "programme and cannot be transferred to a voucher of unknown provenance, "
            "and 付费服务协议 4.4 defers the definitive scope to 产品界面公示, which no "
            "API endpoint exposes. See evidence.voucher_eligibility_basis.",
        )

    # 2. The balance must exist and cover the ceiling. A balance read is not optional:
    #    approving a ¥9.9154 charge against an unreadable balance is approving a charge
    #    whose size nobody can state.
    if voucher_balance is None:
        verdict.add(
            VOUCHER_BALANCE_INSUFFICIENT,
            "voucher balance could not be read. An unreadable balance is never treated "
            "as sufficient, and it is never treated as zero either.",
        )
    elif Decimal(str(voucher_balance)) < Decimal("0.01"):
        verdict.add(
            VOUCHER_BALANCE_INSUFFICIENT,
            f"voucher_balance is {voucher_balance}, so there is no voucher to pay with.",
        )

    # 3. The total, compared as one number against the Founder's ceiling.
    try:
        projected = Decimal(str(projected_total_cny))
    except (InvalidOperation, TypeError):
        projected = Decimal("-1")
        verdict.add(
            ACTIVATION_COST_ABOVE_AUTHORISED_TOTAL,
            f"projected_total_cny is not a number: {projected_total_cny!r}",
        )
    if projected > authorisation.allowed_voucher_spend_cny:
        verdict.add(
            ACTIVATION_COST_ABOVE_AUTHORISED_TOTAL,
            f"projected total CNY {projected} exceeds the authorised CNY "
            f"{authorisation.allowed_voucher_spend_cny}. The ceiling is on the combined "
            "charge, so per-component limits cannot authorise a total above it.",
        )

    # 4. The other two pots must be zero, and here they are structurally zero rather
    #    than merely configured to be. That distinction is what makes "no unauthorised
    #    deduction source" a structural fact rather than a promise.
    if cash_balance is None:
        verdict.add(
            VOUCHER_CASH_FALLBACK_RISK,
            "cash balance could not be read, so it cannot be shown that a cash fallback "
            "is impossible.",
        )
    elif Decimal(str(cash_balance)) > Decimal(str(authorisation.allowed_cash_spend_cny)):
        verdict.add(
            VOUCHER_CASH_FALLBACK_RISK,
            f"cash_balance is {cash_balance}, above the authorised cash spend of "
            f"{authorisation.allowed_cash_spend_cny}. A non-zero cash balance means a "
            "wrong priority could debit an unauthorised source, and deduction priority "
            "between voucher and cash is undocumented.",
        )
    if credit_balance is None:
        verdict.add(
            VOUCHER_CREDIT_FALLBACK_RISK,
            "credit balance could not be read, so it cannot be shown that a Credit Pack "
            "fallback is impossible.",
        )
    elif Decimal(str(credit_balance)) > Decimal(
        str(authorisation.allowed_credit_pack_spend_cny)
    ):
        verdict.add(
            VOUCHER_CREDIT_FALLBACK_RISK,
            f"credit_balance is {credit_balance}, above the authorised Credit Pack spend "
            f"of {authorisation.allowed_credit_pack_spend_cny}.",
        )

    # 5. Scope. A permission granted for one clone must not be spendable on another.
    if authorisation.voice_id_hash and voice_id_hash != authorisation.voice_id_hash:
        verdict.add(
            ACTIVATION_VOICE_ID_MISMATCH,
            "this authorisation covers a different voice than the one presented. It was "
            "granted for one voice_id and cannot be transferred to another.",
        )

    # 6. Counts and shape. Each is a single-use limit, checked against what already
    #    happened rather than against intent.
    if clone_count >= authorisation.max_clone_count:
        verdict.add(
            ACTIVATION_ALREADY_USED,
            f"{clone_count} clone(s) already made against a limit of "
            f"{authorisation.max_clone_count}.",
        )
    if activation_tts_count >= authorisation.max_activation_tts_count:
        verdict.add(
            ACTIVATION_ALREADY_USED,
            f"{activation_tts_count} activation TTS call(s) already made against a limit "
            f"of {authorisation.max_activation_tts_count}.",
        )
    if retry:
        verdict.add(
            REFUSAL_RETRY,
            "a retry was requested. A billable activation is attempted once; a second "
            "attempt is a second charge, and an entitlement or payment failure fails "
            "identically the second time.",
        )
    if not payg_tts_bounded:
        verdict.add(
            REFUSAL_PAYG_TTS_UNBOUNDED,
            "the PAYG synthesis path is not bounded. A permission for one ¥9.9154 charge "
            "must not sit behind an endpoint that could bill any number of requests.",
        )
    if authorisation.allow_auto_recharge:
        verdict.add(
            REFUSAL_PAYG_TTS_UNBOUNDED,
            "automatic recharge is enabled in the authorisation. It is forbidden.",
        )

    verdict.authorised = not verdict.refusals
    verdict.status = (
        VOUCHER_ACTIVATION_AUTHORISED if verdict.authorised else verdict.refusals[0]
    )
    return verdict