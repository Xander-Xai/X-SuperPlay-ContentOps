"""The commercial route for creating and using a cloned voice — decided before any call.

Why this is separate from :mod:`contentops.media.minimax_voice_clone`
---------------------------------------------------------------------
That module answers *how to talk to the provider*: upload, clone, list, classify
refusals. This one answers *whether this account is allowed to, and who pays*. Those
fail independently. A perfectly executed clone is worthless if the ¥9.9 cannot be
collected, and a correctly collected fee buys nothing if the plan does not cover the
model. Folding the commercial decision into the transport is how a run ends up having
already uploaded the Founder's voice before discovering the route was closed.

So this module performs **no I/O against generation endpoints**. It reads two
credentials, a billing verdict and a clock, and returns a decision. The transport is
only ever reached after this returns ``authorised``.

The three official facts that shape the whole design
-----------------------------------------------------
1. **The clone call is free. The fee is charged at first synthesis.**

   > 复刻音色时不立即收费,首次使用该音色进行合成时才计入。试听字符按所选试听模型的单价计费。
   > (Voice Cloning, 9.90 元/音色, under 按量计费 — *the fee is charged at the first use
   > of this cloned voice for speech synthesis; preview characters are billed
   > separately.*)

   So "clone then synthesise" is one billable event, not two. There is no state in
   which a clone exists and nothing has been spent.

2. **The plan does not cover it, and neither do credits.**

   > 可用模型覆盖 MiniMax 全系模型(M3 / M2.7 / 图像 / 语音),少量特殊模型
   > (MiniMax H3、音色设计、**快速复刻**等)暂不支持。

   > 积分与 Token Plan 覆盖相同资源。

   快速复刻 — rapid voice cloning — is named explicitly as *not supported*, and
   purchased Credits cover exactly the same resource set as the plan. This is the
   official explanation of the measured ``2061``, and it is also why a Credit Pack
   cannot be a fallback: it does not reach this resource at all.

3. **Balance is only deducted through a pay-as-you-go key.**

   > 使用开放平台 API Key 调用,按实际用量消耗账户余额。(付费服务协议 4.3)

Vendor confirmation, and what it is allowed to change
-----------------------------------------------------
An earlier revision of this module concluded that the payment route was *impossible*:
the fee is pay-as-you-go priced, it is triggered by a synthesis, only a pay-as-you-go
key can be charged for it, and the subscription plan that must perform the synthesis
does not cover voice management. That conclusion was too strong. It was inferred from
the published rules alone, and published rules do not describe commercial arrangements
made on a specific account.

The Founder has since obtained explicit confirmation from MiniMax customer service for
**this account**:

1. the one-time CNY 9.90 voice-clone fee is charged on the **first synthesis** using the
   cloned voice;
2. after that charge the voice becomes **permanently valid** rather than temporary;
3. subsequent synthesis is charged only the normal per-character amount;
4. a voice already activated for CNY 9.90 **can be used with the M Plan Subscription
   Key** for speech synthesis.

That is recorded as :data:`EVIDENCE_VENDOR_CONFIRMATION` — an **account-level commercial
fact, not proof that any API call succeeds.** The distinction is load-bearing and is the
reason the route status is :data:`ROUTE_VENDOR_CONFIRMED` and not ``VERIFIED``: nothing
here has been executed, nothing has been charged, and every one of those four claims is
still a claim until a live run shows it. Concretely, the confirmation settles *how the
fee is collected* but says nothing about whether the cross-key synthesis is permitted
without a 2042, and nothing at all about whether this account's cash balance can pay.

So the route moves from "blocked, and provably so" to
:data:`ROUTE_VENDOR_CONFIRMED` + :data:`LIVE_VERIFICATION_PENDING`. What has **not**
changed is the fail-closed behaviour: every gate still refuses, and the live run still
stops at the first one that cannot be cleared.

Three fees, never collapsed
---------------------------
The correction that matters operationally is that "the CNY 9.90" was never the whole
cost, and the difference has to be visible *before* anything is spent:

======================  =============  ==============================================
component               amount         when
======================  =============  ==============================================
``clone_creation``      **CNY 0**     never charged at clone time (official)
``first_activation``    **CNY 9.90**  on the first synthesis with the voice
``regular_tts``         per character  every later synthesis, M Plan-eligible
======================  =============  ==============================================

And a fourth, which is the one that would have been quietly swallowed:
:data:`FIRST_ACTIVATION_TTS_FEE_UNKNOWN` — the **character cost of the activation
synthesis itself**. That synthesis is a real TTS request with real characters, priced
at ``speech-2.8-hd`` = CNY 3.50 per 10,000 characters. It is small, and "small" is
exactly why writing it as zero is dangerous: the Founder's authorisation covers the
CNY 9.90 clone fee and does not automatically extend to additional character spend.
:class:`ActivationCost` therefore computes it from the official rate and the declared
text, and :data:`ROUTE_ACTIVATION_CHARACTER_FEE_UNAUTHORISED` blocks until it is
separately authorised.

The 168-hour clock
------------------
> 本接口产出的快速复刻音色为临时音色,若希望永久保留某复刻音色,请于 168 小时(7 天)内在
> 任意 T2A 语音合成接口中调用该音色。

A cloned voice is **temporary** and is deleted if it is not used within 168 hours. This
inverts the order of operations the issue describes: the clone cannot be created now
"ready for later", because later may not exist. Clone creation and the first synthesis
must be **one continuous session**. :data:`CLONE_TTL_SECONDS` and
:meth:`RouteDecision.remaining_ttl` exist so the deadline is a recorded fact rather
than something an operator is expected to remember.

Under the vendor confirmation this acquires a second meaning: the 168-hour window is no
longer only an expiry, it is also the clock on the activation charge. A clone that is
never activated inside the window is deleted, and so is the CNY 9.90 that would have
activated it.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from .credentials import CREDENTIAL_PAYG, CREDENTIAL_SUBSCRIPTION, TwoKeyPair

__all__ = [
    "ACTIVATION_TEXT",
    "CLONE_FEE_CNY",
    "CLONE_TTL_HOURS",
    "CLONE_TTL_SECONDS",
    "EVIDENCE_VENDOR_CONFIRMATION",
    "FIRST_ACTIVATION_TTS_FEE_UNKNOWN",
    "LIVE_VERIFICATION_PENDING",
    "ROUTE_ACTIVATION_CHARACTER_FEE_UNAUTHORISED",
    "ROUTE_ACTIVATION_CASH_INSUFFICIENT",
    "ROUTE_AUTHORISED",
    "ROUTE_CLONE_KEY_REQUIRED",
    "ROUTE_CROSS_KEY_UNKNOWN",
    "ROUTE_SUBSCRIPTION_BILLING_UNPROVEN",
    "ROUTE_VENDOR_CONFIRMED",
    "ActivationCost",
    "OFFICIAL_BASIS",
    "RouteDecision",
    "VENDOR_CONFIRMATION",
    "decide_route",
    "speech_2_8_hd_cny_per_10k_chars",
    "billable_characters",
]

#: Published price of one cloned voice, charged at the first synthesis that uses it.
CLONE_FEE_CNY = "9.90"

#: What the clone call itself costs. Official: "复刻音色时不立即收费". Recorded as an
#: explicit zero rather than left absent, because "the clone is free" and "we never
#: checked what the clone costs" must not look the same in a receipt.
CLONE_CREATION_CNY = "0.00"

#: ``speech-2.8-hd`` under 按量计费, per the published 定价概览.
SPEECH_2_8_HD_CNY_PER_10K = "3.50"

#: The utterance used for the single activation synthesis.
#:
#: Two constraints pull against each other and both matter. It has to be **short**,
#: because this synthesis is billed per character. It also has to be a **real
#: sentence**, because it is the first audio produced from the Founder's voice and is
#: what Founder listening later judges -- a one-character activation would be a
#: billable artefact with nothing to evaluate.
#:
#: 22 characters, all CJK, so 44 billable characters at the published counting rule.
ACTIVATION_TEXT = "这是一段用于首次激活的最短自然中文语音样本。"

#: The character cost of the *activation* synthesis is not covered by the CNY 9.90
#: authorisation and has never been observed on a live receipt. It is carried as an
#: explicit unknown rather than defaulted to zero, because zero is a number and this
#: is not known to be one.
FIRST_ACTIVATION_TTS_FEE_UNKNOWN = "FIRST_ACTIVATION_TTS_FEE_UNKNOWN"

#: Evidence classes. The distinction is the whole reason the route is not called
#: VERIFIED: one of these is a commercial statement about this account, the others are
#: things a machine actually observed.
EVIDENCE_VENDOR_CONFIRMATION = "FOUNDER_SUPPLIED_VENDOR_CONFIRMATION"
EVIDENCE_OFFICIAL_DOC = "VERIFIED_OFFICIAL"
EVIDENCE_LIVE_MEASURED = "VERIFIED_LOCAL"

#: Route status. Not ``VERIFIED``: the vendor confirmation is account-level commercial
#: evidence, and no API call has been made under it.
ROUTE_VENDOR_CONFIRMED = "VENDOR_CONFIRMED"
LIVE_VERIFICATION_PENDING = "LIVE_VERIFICATION_PENDING"

#: The four claims the Founder obtained from MiniMax customer service for this account,
#: verbatim in substance. Recorded so the receipt can cite what it is relying on
#: instead of asserting a conclusion that matches it.
VENDOR_CONFIRMATION: Dict[str, Any] = {
    "evidence_class": EVIDENCE_VENDOR_CONFIRMATION,
    "obtained_by": "Founder, from MiniMax customer service",
    "obtained_on": "2026-10-12",
    "scope": "ACCOUNT_LEVEL_COMMERCIAL",
    "is_proof_of_api_success": False,
    "claims": [
        "使用克隆音色首次合成时, 收取一次性 ¥9.9 音色克隆费。",
        "首次收费完成后, 音色从临时有效转为永久有效。",
        "后续语音合成仅收取对应字符的正常费用。",
        "已经支付 ¥9.9 激活的音色, 可以继续使用 M Plan 套餐进行语音合成。",
    ],
    "still_unverified": [
        "whether the cross-key synthesis is actually permitted (a 2042 is the documented "
        "symptom if it is not, and the vendor confirmation does not address the API-level "
        "permission)",
        "whether this account's cash balance can pay the activation charge",
        "the character cost of the activation synthesis itself, FIRST_ACTIVATION_TTS_FEE_UNKNOWN",
    ],
}

#: "168 小时(7 天)". The voice is deleted if no T2A call uses it within this window.
CLONE_TTL_HOURS = 168
CLONE_TTL_SECONDS = CLONE_TTL_HOURS * 3600

ROUTE_AUTHORISED = "AUTHORISED"
ROUTE_CLONE_KEY_REQUIRED = "CLONE_KEY_REQUIRED"
ROUTE_SUBSCRIPTION_BILLING_UNPROVEN = "SUBSCRIPTION_ONLY_BILLING_UNPROVEN"
ROUTE_CROSS_KEY_UNKNOWN = "CROSS_KEY_CLONED_VOICE_TTS_UNKNOWN"
ROUTE_ACTIVATION_CASH_INSUFFICIENT = "ACTIVATION_CASH_INSUFFICIENT"
ROUTE_ACTIVATION_CHARACTER_FEE_UNAUTHORISED = "ACTIVATION_CHARACTER_FEE_UNAUTHORISED"


def billable_characters(text: str) -> int:
    """Count characters the way the published price table counts them.

    > 计费项是字符数,以 10000 个字符(输入)为单位,1 个汉字算 2 个字符,英文字母、希腊字母、
    > 标点符号、特殊符号、空格、回车等算 1 个字符。

    So a CJK ideograph is 2 and everything else is 1. Getting this wrong by one factor
    of two would misprice the activation, and mispricing a charge the Founder has not
    authorised is exactly the failure this exists to prevent.
    """
    total = 0
    for char in text:
        code = ord(char)
        total += 2 if (
            0x4E00 <= code <= 0x9FFF      # CJK Unified Ideographs
            or 0x3400 <= code <= 0x4DBF  # Extension A
            or 0xF900 <= code <= 0xFAFF  # Compatibility Ideographs
            or 0x3000 <= code <= 0x303F  # CJK punctuation
            or 0xFF00 <= code <= 0xFF65  # Full-width forms
        ) else 1
    return total


def speech_2_8_hd_cny_per_10k_chars() -> str:
    return SPEECH_2_8_HD_CNY_PER_10K


@dataclass(frozen=True)
class ActivationCost:
    """Exactly what the first activation will cost, split by component.

    Split rather than summed because the three components have different owners. The
    CNY 9.90 is authorised. The character cost is **not** — it was never authorised,
    and it was never observed either. Presenting a single total would imply the two
    were covered by the same approval, which is precisely the conflation that would
    let an unauthorised charge look authorised.
    """

    clone_creation_cny: str = CLONE_CREATION_CNY
    first_activation_cny: str = CLONE_FEE_CNY
    activation_characters: int = 0
    rate_cny_per_10k: str = SPEECH_2_8_HD_CNY_PER_10K
    activation_character_cny: str = FIRST_ACTIVATION_TTS_FEE_UNKNOWN
    first_activation_authorised: bool = False
    activation_character_authorised: bool = False
    regular_tts: str = "per-character at speech-2.8-hd rate, M Plan-eligible after activation"

    @classmethod
    def for_text(
        cls,
        text: str,
        *,
        first_activation_authorised: bool = False,
        activation_character_authorised: bool = False,
    ) -> "ActivationCost":
        """Compute the activation character cost from the official rate.

        ``activation_character_cny`` stays :data:`FIRST_ACTIVATION_TTS_FEE_UNKNOWN`
        until it has been *observed* on a receipt or confirmed on an invoice. The
        computed figure is carried alongside as
        :attr:`activation_character_cny_estimated`, because a Founder asked to approve
        a charge needs the number, and refusing to state it would just push the
        decision into guesswork.
        """
        chars = billable_characters(text)
        estimated = f"{Decimal(SPEECH_2_8_HD_CNY_PER_10K) * chars / Decimal(10000):.6f}"
        cost = cls(
            activation_characters=chars,
            first_activation_authorised=first_activation_authorised,
            activation_character_authorised=activation_character_authorised,
        )
        object.__setattr__(cost, "_estimated", estimated)
        return cost

    @property
    def activation_character_cny_estimated(self) -> str:
        """The computed figure, for approval. Never presented as the observed charge."""
        return getattr(self, "_estimated", FIRST_ACTIVATION_TTS_FEE_UNKNOWN)

    @property
    def total_authorised_cny(self) -> str:
        """What is actually approved right now. Zero until the CNY 9.90 is declared."""
        return "9.90" if self.first_activation_authorised else "0.00"

    @property
    def total_unauthorised_cny(self) -> str:
        """What would be spent without a further decision. Never quietly folded in."""
        if self.activation_character_authorised:
            return "0.00"
        return f"first_activation={self.first_activation_cny}, " \
               f"activation_characters={self.activation_character_cny_estimated}"

    def as_dict(self) -> Dict[str, Any]:
        return {
            "clone_creation_cny": self.clone_creation_cny,
            "clone_creation_charged_at": "NEVER_AT_CLONE_TIME",
            "first_activation_cny": self.first_activation_cny,
            "first_activation_charged_at": "FIRST_SYNTHESIS_WITH_THIS_VOICE",
            "first_activation_authorised": self.first_activation_authorised,
            "activation_characters": self.activation_characters,
            "rate_cny_per_10k_chars": self.rate_cny_per_10k,
            "activation_character_cny": self.activation_character_cny,
            "activation_character_cny_estimated": self.activation_character_cny_estimated,
            "activation_character_authorised": self.activation_character_authorised,
            "regular_tts": self.regular_tts,
            "total_authorised_cny": self.total_authorised_cny,
            "total_unauthorised_cny": self.total_unauthorised_cny,
        }

#: Quoted from the CN platform so every status is traceable to a page rather than to
#: a recollection. ``2061`` is deliberately absent from MiniMax's own error table and
#: is documented only in the official CLI ERRORS.md, which is recorded here.
OFFICIAL_BASIS: Tuple[Dict[str, str], ...] = (
    {
        "id": "clone-fee-timing",
        "page": "platform.minimax.cn/docs/pricing/overview (音色管理 / 快速复刻)",
        "fact": (
            "9.90 元/音色, 按量计费. 复刻音色时不立即收费, 首次使用该音色进行合成时才计入. "
            "试听字符按所选试听模型的单价计费."
        ),
    },
    {
        "id": "plan-excludes-cloning",
        "page": "platform.minimax.cn/docs/guides/pricing-token-plan",
        "fact": (
            "可用模型覆盖 MiniMax 全系模型(M3 / M2.7 / 图像 / 语音), 少量特殊模型"
            "(MiniMax H3、音色设计、快速复刻等)暂不支持."
        ),
    },
    {
        "id": "credits-same-coverage",
        "page": "platform.minimax.cn/docs/guides/pricing-token-plan",
        "fact": "积分与 Token Plan 覆盖相同资源; 若同一用量可由套餐内额度和积分覆盖, 优先使用套餐内额度.",
    },
    {
        "id": "balance-only-via-payg-key",
        "page": "platform.minimaxi.cn/protocol/paid-agreement 4.1 / 4.3(1)",
        "fact": (
            "通过充值获得的 API Key 与 Token Plan API Key 相互独立, 且不可互换. "
            "使用开放平台 API Key 调用, 按实际用量消耗账户余额."
        ),
    },
    {
        "id": "speech-rate",
        "page": "platform.minimax.cn/docs/pricing/overview (按量计费说明)",
        "fact": (
            "同步语音合成 T2A speech-2.8-hd = 3.50 元/万字符. 计费项是字符数,以 10000 个"
            "字符(输入)为单位,1 个汉字算 2 个字符,英文字母、希腊字母、标点符号、特殊"
            "符号、空格、回车等算 1 个字符. Used to compute the activation synthesis's "
            "character cost, which is a separate billable item from the CNY 9.90 voice fee."
        ),
    },
    {
        "id": "subscription-key-deduction-chain",
        "page": "platform.minimax.cn/docs/guides/pricing-token-plan, M Plan FAQ",
        "fact": (
            "A Subscription Key only uses your M Plan usage and credit packs. When you "
            "reach your usage limit, any remaining credit pack balance is used next. "
            "Your account balance is charged only when you use a pay-as-you-go API Key. "
            "排他性表述: 套餐内额度 -> 积分包, 不含代金券, 不含账户余额. This is the basis on "
            "which a non-zero voucher_balance no longer blocks a Subscription-Key "
            "in-plan speech request, and equally the basis on which it STILL blocks "
            "the pay-as-you-go-key activation charge."
        ),
    },
    {
        "id": "temporary-voice-ttl",
        "page": "platform.minimax.cn/docs/api-reference/api-overview (音色快速复刻 / 注意事项)",
        "fact": (
            "本接口产出的快速复刻音色为临时音色, 若希望永久保留某复刻音色, 请于 168 小时"
            "(7 天)内在任意 T2A 语音合成接口中调用该音色(不包含本接口内的试听行为). "
            "若超过时限, 该音色将被删除."
        ),
    },
    {
        "id": "clone-requires-verification",
        "page": "platform.minimax.cn/docs/api-reference/api-overview, /docs/faq/about-apis",
        "fact": "使用本接口需要完成个人认证及企业认证用户后, 方可调用.",
    },
    {
        "id": "error-2042",
        "page": "platform.minimax.cn/docs/api-reference/errorcode",
        "fact": "2042 无权访问该 voice_id | 请确认是否为该 voice_id 创建者.",
    },
    {
        "id": "error-2061-not-in-table",
        "page": "official MiniMax CLI ERRORS.md (absent from the platform error table)",
        "fact": (
            "2061 This model is not available on your current Token Plan. Measured once "
            "against /v1/voice_clone on this account."
        ),
    },
)


@dataclass
class RouteDecision:
    """The verdict, and every reason that produced it.

    ``blocked_by`` is a list rather than a single value on purpose. The blockers are
    independent, and fixing one does not fix the others: provisioning a PAYG key does
    not make the account's cash balance able to pay. A single-valued verdict would let
    a partial fix look like a complete one.
    """

    route: str = ROUTE_VENDOR_CONFIRMED
    #: Commercial status of the route. ``VENDOR_CONFIRMED`` +
    #: ``LIVE_VERIFICATION_PENDING`` means an account-level confirmation exists and
    #: nothing under it has been executed. It is never ``VERIFIED``.
    commercial_status: str = ROUTE_VENDOR_CONFIRMED
    verification_status: str = LIVE_VERIFICATION_PENDING
    authorised: bool = False
    blocked_by: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    clone_credential_class: str = ""
    clone_credential_source: str = ""
    tts_credential_class: str = ""
    tts_credential_source: str = ""
    keys_distinct: Optional[bool] = None
    billing_verdict: str = ""
    billing_reasons: List[str] = field(default_factory=list)
    clone_fee_cny: str = CLONE_FEE_CNY
    clone_ttl_hours: int = CLONE_TTL_HOURS
    clone_created_at: Optional[float] = None
    now: Optional[float] = None
    #: Measured balances, used to decide whether the activation charge can be paid at
    #: all. Only a pay-as-you-go key deducts account balance, so this decides whether
    #: the route is physically payable rather than merely permitted.
    cash_balance: Optional[float] = None
    activation_cost: Optional[ActivationCost] = None
    #: Whether the Founder authorised the CNY 9.90 first-activation fee. The route is
    #: not authorised without it, even with a key and cash available.
    first_activation_authorised: bool = False

    @property
    def remaining_ttl(self) -> Optional[float]:
        """Seconds of clone life left, or ``None`` if nothing was created yet.

        Negative means the window has closed and the voice has already been deleted
        provider-side. That is a hard stop, not a warning: synthesising would bill a
        TTS request against a voice that no longer exists.
        """
        if self.clone_created_at is None:
            return None
        now = self.now if self.now is not None else time.time()
        return CLONE_TTL_SECONDS - (now - self.clone_created_at)

    def ttl_deadline_iso(self) -> Optional[str]:
        if self.clone_created_at is None:
            return None
        return datetime.fromtimestamp(
            self.clone_created_at + CLONE_TTL_SECONDS, tz=timezone.utc
        ).isoformat()

    def add(self, code: str, reason: str) -> None:
        if code not in self.blocked_by:
            self.blocked_by.append(code)
        self.reasons.append(reason)

    def as_dict(self) -> Dict[str, Any]:
        payload = {
            "schema": "contentops.voice-clone-route/v2",
            "route": self.route,
            "commercial_status": self.commercial_status,
            "verification_status": self.verification_status,
            "authorised": self.authorised,
            "blocked_by": list(self.blocked_by),
            "reasons": list(self.reasons),
            "clone_key": {
                "credential_class": self.clone_credential_class,
                "credential_source": self.clone_credential_source,
                "required_class": CREDENTIAL_PAYG,
                "env_var": "MINIMAX_CLONE_KEY",
                "configured": self.clone_credential_class not in ("", "ABSENT"),
            },
            "tts_key": {
                "credential_class": self.tts_credential_class,
                "credential_source": self.tts_credential_source,
                "required_class": CREDENTIAL_SUBSCRIPTION,
                "configured": self.tts_credential_class not in ("", "ABSENT"),
            },
            "keys_distinct": self.keys_distinct,
            "billing_verdict": self.billing_verdict,
            "billing_reasons": list(self.billing_reasons),
            "cash_balance": self.cash_balance,
            "clone_fee_cny": self.clone_fee_cny,
            "clone_fee_charged_at": "FIRST_SYNTHESIS_WITH_THIS_VOICE",
            "clone_ttl_hours": self.clone_ttl_hours,
            "clone_ttl_seconds": CLONE_TTL_SECONDS,
            "clone_created_at": self.clone_created_at,
            "clone_ttl_deadline": self.ttl_deadline_iso(),
            "remaining_ttl_s": self.remaining_ttl,
            "vendor_confirmation": dict(VENDOR_CONFIRMATION),
            "activation_cost": (
                None if self.activation_cost is None else self.activation_cost.as_dict()
            ),
            "official_basis": [dict(entry) for entry in OFFICIAL_BASIS],
            "payg_tts_allowed": False,
            "payg_activation_tts_allowed": True,
            "credit_pack_tts_allowed": False,
            "voucher_consumption_allowed": False,
            "automatic_topup_allowed": False,
            "retry_allowed": False,
            "production_ready": False,
            "human_review": "PENDING_FOUNDER_REVIEW",
        }
        blob = json.dumps(payload, ensure_ascii=False)
        for banned in ("Authorization", "Bearer ", "sk-cp-", "sk-api-"):
            if banned in blob:
                raise ValueError(
                    f"refusing to serialise a route receipt containing {banned!r}"
                )
        return payload


def decide_route(
    pair: TwoKeyPair,
    *,
    billing_verdict: str,
    billing_reasons: Optional[List[str]] = None,
    account_verified: Optional[bool] = None,
    cross_key_verified: Optional[bool] = None,
    clone_created_at: Optional[float] = None,
    now: Optional[float] = None,
    cash_balance: Optional[float] = None,
    activation_cost: Optional[ActivationCost] = None,
    first_activation_authorised: bool = False,
) -> RouteDecision:
    """Decide whether the Founder clone may proceed. No I/O, no generation.

    Every parameter is a fact the caller already measured. This function exists so
    that the *policy* is one readable block rather than a chain of ``if`` statements
    spread across a caller, which is how a partial gate ends up looking complete.

    Args:
        pair: the two resolved credentials.
        billing_verdict: ``BillingGuard``'s verdict for the TTS credential.
        billing_reasons: the guard's reasons, carried through so the receipt shows why.
        account_verified: whether 个人认证 / 企业认证 is confirmed complete.
        cross_key_verified: ``True``/``False`` once a real synthesis has answered the
            cross-key question, ``None`` while it is still unverified. The vendor
            confirmation does **not** settle this: it is a commercial statement about
            billing, and ``2042`` is an API-level permission error.
        clone_created_at: unix time of a successful clone, for TTL accounting.
        now: injectable clock, so the TTL is testable without waiting seven days.
        cash_balance: measured account cash. Decides whether the activation charge can
            be paid at all, since only a pay-as-you-go key deducts balance.
        activation_cost: the split fee model for the first activation.
        first_activation_authorised: whether the Founder approved the CNY 9.90.

    Returns:
        A :class:`RouteDecision`. ``authorised`` is True only when nothing blocked.
    """
    decision = RouteDecision(now=now, clone_created_at=clone_created_at)
    decision.clone_credential_class = pair.clone.credential_class
    decision.clone_credential_source = pair.clone.source
    decision.tts_credential_class = pair.tts.credential_class
    decision.tts_credential_source = pair.tts.source
    decision.keys_distinct = (
        pair.clone.key != pair.tts.key
        if pair.clone.usable and pair.tts.usable
        else None
    )
    decision.billing_verdict = billing_verdict
    decision.billing_reasons = list(billing_reasons or [])
    decision.cash_balance = cash_balance
    decision.activation_cost = activation_cost
    decision.first_activation_authorised = first_activation_authorised

    # 1. The clone key. Absent is the most common state and the cheapest to fix, so
    #    it is reported first and on its own terms -- it is a provisioning action,
    #    not a design problem.
    if not pair.clone_configured:
        decision.add(
            ROUTE_CLONE_KEY_REQUIRED,
            "MINIMAX_CLONE_KEY is not set. A pay-as-you-go API Key is required to create "
            "the clone and to perform the one activation synthesis that pays the CNY "
            "9.90, because the Subscription Key was refused once with 2061 and must not "
            "be retried. Create one at 账户管理 > 接口密钥 in the official console for "
            "THIS SAME account, then set it locally; do not paste it into chat, a PR "
            "or a log.",
        )
    elif pair.clone.credential_class != CREDENTIAL_PAYG:
        decision.add(
            ROUTE_CLONE_KEY_REQUIRED,
            f"MINIMAX_CLONE_KEY classifies as {pair.clone.credential_class}, not "
            f"{CREDENTIAL_PAYG}. A pay-as-you-go key carries the sk-api- prefix. Refused "
            "rather than guessed at: a Subscription Key here would repeat the refused "
            "2061, and an international-region key is a different account's surface.",
        )

    # 2. The TTS key must still be the subscription key. PAYG TTS remains forbidden --
    #    with one deliberate, bounded exception handled separately below: the single
    #    activation synthesis, which is what pays the one-time fee.
    if not pair.tts_configured:
        decision.add(
            ROUTE_SUBSCRIPTION_BILLING_UNPROVEN,
            "no TTS credential resolved, so M-Plan-only narration cannot be proved.",
        )
    elif pair.tts.credential_class != CREDENTIAL_SUBSCRIPTION:
        decision.add(
            ROUTE_SUBSCRIPTION_BILLING_UNPROVEN,
            f"the TTS credential classifies as {pair.tts.credential_class}, not "
            f"{CREDENTIAL_SUBSCRIPTION}. Regular PAYG TTS is forbidden outright, so "
            "this is a hard stop rather than a fallback.",
        )

    # 3. Billing must be provable *before* the clone, not after. This is the rule that
    #    stopped the last stage: a non-zero voucher balance means paid funds could be
    #    consumed, and the guard cannot prove they would not be.
    #
    #    It is explicitly NOT bypassed because the activation fee is authorised. The
    #    guard's question is "can this subscription key spend anything that is not
    #    included plan usage", and a CNY 9.90 authorisation answers a different one.
    #    Weakening the guard to get past a voucher balance would make every later
    #    narration unverifiable, in exchange for one voice.
    if billing_verdict != "SAFE_INCLUDED_PLAN":
        decision.add(
            ROUTE_SUBSCRIPTION_BILLING_UNPROVEN,
            "BillingGuard verdict is "
            f"{billing_verdict or 'UNKNOWN'}, not SAFE_INCLUDED_PLAN. TTS cannot be "
            "proved to draw only on included plan usage, so no synthesis -- and "
            "therefore no activation, and therefore no clone -- may proceed. This "
            "guard is not relaxed because the CNY 9.90 fee is authorised: the fee "
            "answers a different question from 'can this key spend non-plan funds'. "
            + "; ".join(decision.billing_reasons),
        )

    # 4. The activation charge has to be payable. It runs on the pay-as-you-go key, and
    #    the official rule is that the account balance -- 账户余额 -- is charged exactly
    #    when a pay-as-you-go key calls. `cash_balance` is that balance and it is 0.00.
    #
    #    The precision that matters: the same rule that let the *Subscription* key's
    #    in-plan TTS through despite voucher_balance = 15.00 does NOT apply here,
    #    because this request is made by the pay-as-you-go key. Whether a voucher can
    #    fund a pay-as-you-go charge is UNKNOWN -- no official page reached says either
    #    way, and `available_amount` equalling `voucher_balance` is suggestive rather
    #    than conclusive. Inference from another vendor's equivalent field would be
    #    exactly the wrong move here.
    if cash_balance is not None and cash_balance <= 0:
        decision.add(
            ROUTE_ACTIVATION_CASH_INSUFFICIENT,
            f"cash_balance is {cash_balance:.2f} and the activation synthesis runs on the "
            "pay-as-you-go key, which is the only key type the platform charges 账户余额 "
            "for (M Plan FAQ: 'Your account balance is charged only when you use a "
            "pay-as-you-go API Key'). An approved charge is not a payable charge. "
            "Whether voucher_balance can fund a pay-as-you-go charge is UNKNOWN -- no "
            "official page reached states it -- and automatic voucher consumption, "
            "automatic recharge and automatic Credit Pack use are all forbidden. This "
            "gate therefore does NOT move on the same evidence that cleared the "
            "Subscription-Key TTS gate.",
        )

    # 5. The CNY 9.90 itself. Recorded as its own authorisation rather than assumed
    #    from "the route is approved".
    if not first_activation_authorised:
        decision.add(
            ROUTE_ACTIVATION_CHARACTER_FEE_UNAUTHORISED,
            "the CNY 9.90 first-activation fee has not been recorded as authorised in "
            "this run. The Founder's standing authorisation covers the clone fee only; "
            "it does not extend to additional character spend.",
        )

    # 6. The activation synthesis is a real TTS request with billable characters. Its
    #    cost is deliberately NOT recorded as zero -- it was never authorised and never
    #    observed. Small numbers are exactly the ones that get waved through.
    if activation_cost is not None and not activation_cost.activation_character_authorised:
        decision.add(
            ROUTE_ACTIVATION_CHARACTER_FEE_UNAUTHORISED,
            "the activation synthesis itself is a billable TTS request: "
            f"{activation_cost.activation_characters} billable characters at "
            f"{activation_cost.rate_cny_per_10k} CNY/10k, estimated "
            f"CNY {activation_cost.activation_character_cny_estimated}. This is "
            "recorded as "
            f"{FIRST_ACTIVATION_TTS_FEE_UNKNOWN} and must not be assumed zero. It is "
            "separate from the CNY 9.90 voice fee and needs its own authorisation.",
        )

    # 7. The cross-key question stays open until a real synthesis answers it. The
    #    vendor confirmation states that an activated voice *may* be used with the M
    #    Plan; it does not say the API permits it, and 2042 is documented for exactly
    #    this. A commercial assurance is not a permission grant.
    if cross_key_verified is None:
        decision.add(
            ROUTE_CROSS_KEY_UNKNOWN,
            "the vendor confirmation states an activated voice may be synthesised with "
            "the M Plan key, but that is an account-level commercial statement and not "
            "an API-level permission grant. No official source confirms a voice_id "
            "created under a pay-as-you-go key can synthesise under the Subscription "
            "Key; get_voice listing is account-scoped and proves visibility, not "
            "usability, and error 2042 (无权访问该 voice_id) is the documented symptom "
            "if visibility does not imply usability. Must not be claimed as supported "
            "before one real synthesis answers it.",
        )
    elif cross_key_verified is False:
        decision.add(
            ROUTE_CROSS_KEY_UNKNOWN,
            "a real synthesis with a pay-as-you-go-created voice under the Subscription "
            "Key was attempted and refused. The cross-key route does not work; no other "
            "key may be substituted to force it, and the vendor confirmation does not "
            "override an API refusal.",
        )

    # 8. Verification prerequisite for the clone call itself.
    if account_verified is False:
        decision.add(
            ROUTE_CLONE_KEY_REQUIRED,
            "voice cloning requires 个人认证 or 企业认证, and the account is not "
            "confirmed verified. Refusing rather than spending an upload on a request "
            "that 2038 would reject.",
        )

    # 9. A created clone has a 168-hour life. Checking it last means a run that is
    #    otherwise ready still fails closed once the voice has been deleted.
    remaining = decision.remaining_ttl
    if remaining is not None and remaining <= 0:
        decision.add(
            ROUTE_ACTIVATION_CASH_INSUFFICIENT,
            f"the cloned voice was created {CLONE_TTL_HOURS}h ago and provider storage "
            "has deleted it. Cloned voices are temporary unless used within the window; "
            "a new clone must be created and activated in one continuous session.",
        )

    decision.authorised = not decision.blocked_by
    if decision.authorised:
        decision.route = ROUTE_AUTHORISED
    elif ROUTE_CLONE_KEY_REQUIRED in decision.blocked_by:
        # The provisioning action comes first because it is the one that must happen
        # before anything else can even be attempted.
        decision.route = ROUTE_CLONE_KEY_REQUIRED
    else:
        decision.route = decision.blocked_by[0]
    return decision