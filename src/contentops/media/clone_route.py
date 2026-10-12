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

   Combine 1, 2 and 3 and there is a contradiction that no amount of local testing
   resolves: the ¥9.9 is a pay-as-you-go-priced item, it is *triggered by* synthesis,
   pay-as-you-go balances are the only thing that can be charged for it, and the
   subscription plan that must perform the synthesis does not cover voice management.

   That is :data:`ROUTE_PAYMENT_BLOCKED`. It is a real contradiction in the published
   rules, not a gap that more searching would close, and this module refuses on it
   rather than guessing which side MiniMax would resolve it on.

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
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .credentials import CREDENTIAL_PAYG, CREDENTIAL_SUBSCRIPTION, TwoKeyPair

__all__ = [
    "CLONE_FEE_CNY",
    "CLONE_TTL_HOURS",
    "CLONE_TTL_SECONDS",
    "ROUTE_AUTHORISED",
    "ROUTE_CLONE_KEY_REQUIRED",
    "ROUTE_CROSS_KEY_UNKNOWN",
    "ROUTE_PAYMENT_BLOCKED",
    "ROUTE_SUBSCRIPTION_BILLING_UNPROVEN",
    "ROUTE_TTS_ACCESS_UNVERIFIED",
    "OFFICIAL_BASIS",
    "RouteDecision",
    "decide_route",
]

#: Published price of one cloned voice, charged at first synthesis. Not the Founder's
#: customer-service quote -- both are 9.9 and the receipt records which one it used.
CLONE_FEE_CNY = "9.90"

#: "168 小时(7 天)". The voice is deleted if no T2A call uses it within this window.
CLONE_TTL_HOURS = 168
CLONE_TTL_SECONDS = CLONE_TTL_HOURS * 3600

ROUTE_AUTHORISED = "AUTHORISED"
ROUTE_CLONE_KEY_REQUIRED = "CLONE_KEY_REQUIRED"
ROUTE_PAYMENT_BLOCKED = "PAYMENT_ROUTE_BLOCKED"
ROUTE_CROSS_KEY_UNKNOWN = "CROSS_KEY_CLONED_VOICE_TTS_UNKNOWN"
ROUTE_SUBSCRIPTION_BILLING_UNPROVEN = "SUBSCRIPTION_ONLY_BILLING_UNPROVEN"

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
    independent, and fixing one does not fix the others: an operator who provisions a
    PAYG key still faces the payment contradiction. A single-valued verdict would let
    a partial fix look like a complete one.
    """

    route: str = ROUTE_PAYMENT_BLOCKED
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
            "schema": "contentops.voice-clone-route/v1",
            "route": self.route,
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
            "clone_fee_cny": self.clone_fee_cny,
            "clone_fee_charged_at": "FIRST_SYNTHESIS_WITH_THIS_VOICE",
            "clone_ttl_hours": self.clone_ttl_hours,
            "clone_ttl_seconds": CLONE_TTL_SECONDS,
            "clone_created_at": self.clone_created_at,
            "clone_ttl_deadline": self.ttl_deadline_iso(),
            "remaining_ttl_s": self.remaining_ttl,
            "official_basis": [dict(entry) for entry in OFFICIAL_BASIS],
            "payg_tts_allowed": False,
            "credit_pack_tts_allowed": False,
            "voucher_consumption_allowed": False,
            "automatic_topup_allowed": False,
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
            cross-key question, ``None`` while it is still unverified.
        clone_created_at: unix time of a successful clone, for TTL accounting.
        now: injectable clock, so the TTL is testable without waiting seven days.

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

    # 1. The clone key. Absent is the most common state and the cheapest to fix, so
    #    it is reported first and on its own terms -- it is a provisioning action,
    #    not a design problem.
    if not pair.clone_configured:
        decision.add(
            ROUTE_CLONE_KEY_REQUIRED,
            "MINIMAX_CLONE_KEY is not set. A pay-as-you-go API Key is required to create "
            "the clone, because the Subscription Key was refused once with 2061 and "
            "must not be retried. Create one at 账户管理 > 接口密钥 in the official "
            "console and set it locally; do not paste it into chat, a PR or a log.",
        )
    elif pair.clone.credential_class != CREDENTIAL_PAYG:
        decision.add(
            ROUTE_PAYMENT_BLOCKED,
            f"MINIMAX_CLONE_KEY classifies as {pair.clone.credential_class}, not "
            f"{CREDENTIAL_PAYG}. A pay-as-you-go key carries the sk-api- prefix; a "
            "value with any other prefix is refused rather than guessed at.",
        )

    # 2. The TTS key must still be the subscription key. A missing one is reported
    #    here rather than silently skipped, because the alternative is cloning a voice
    #    that nothing in this repository is then allowed to speak with.
    if not pair.tts_configured:
        decision.add(
            ROUTE_SUBSCRIPTION_BILLING_UNPROVEN,
            "no TTS credential resolved, so M-Plan-only narration cannot be proved.",
        )
    elif pair.tts.credential_class != CREDENTIAL_SUBSCRIPTION:
        decision.add(
            ROUTE_SUBSCRIPTION_BILLING_UNPROVEN,
            f"the TTS credential classifies as {pair.tts.credential_class}, not "
            f"{CREDENTIAL_SUBSCRIPTION}. PAYG TTS is forbidden outright, so this is "
            "a hard stop rather than a fallback.",
        )

    # 3. Billing must be provable *before* the clone, not after. This is the rule that
    #    stopped the last stage: a non-zero voucher balance means paid funds could be
    #    consumed, and the guard cannot prove they would not be.
    if billing_verdict != "SAFE_INCLUDED_PLAN":
        decision.add(
            ROUTE_SUBSCRIPTION_BILLING_UNPROVEN,
            "BillingGuard verdict is "
            f"{billing_verdict or 'UNKNOWN'}, not SAFE_INCLUDED_PLAN. TTS cannot be "
            "proved to draw only on included plan usage, so no synthesis -- and "
            "therefore no first-use fee, and therefore no clone -- may proceed. "
            + "; ".join(decision.billing_reasons),
        )

    # 4. The payment contradiction. Stated as its own blocker because provisioning a
    #    key does not resolve it, and an operator who fixes (1) must not be led to
    #    believe the route then works.
    decision.add(
        ROUTE_PAYMENT_BLOCKED,
        "official rules do not connect: the CNY 9.90 is a pay-as-you-go priced item "
        "(定价概览: 9.90 元/音色, 按量计费) charged at the FIRST SYNTHESIS with the "
        "voice; the plan explicitly excludes 快速复刻 and Credits cover the same "
        "resource set as the plan (定价概览 / pricing-token-plan); and account balance "
        "is only deducted when a pay-as-you-go API Key is called (付费服务协议 4.3(1)). "
        "So the fee can only be collected by a pay-as-you-go synthesis, which this "
        "issue forbids. Needs account-specific confirmation from MiniMax.",
    )

    # 5. The cross-key question stays open until a real synthesis answers it.
    if cross_key_verified is None:
        decision.add(
            ROUTE_CROSS_KEY_UNKNOWN,
            "no official source confirms a voice_id created under a pay-as-you-go key "
            "can synthesise under the Subscription Key. get_voice listing is "
            "account-scoped and proves visibility, not usability; error 2042 (无权访问"
            "该 voice_id) is the documented symptom if visibility does not imply "
            "usability. Must not be claimed as supported before one real synthesis "
            "answers it.",
        )
    elif cross_key_verified is False:
        decision.add(
            ROUTE_CROSS_KEY_UNKNOWN,
            "a real synthesis with a pay-as-you-go-created voice under the Subscription "
            "Key was attempted and refused. The cross-key route does not work; no other "
            "key may be substituted to force it.",
        )

    # 6. Verification prerequisite for the clone call itself.
    if account_verified is False:
        decision.add(
            ROUTE_PAYMENT_BLOCKED,
            "voice cloning requires 个人认证 or 企业认证, and the account is not "
            "confirmed verified. Refusing rather than spending an upload on a request "
            "that 2038 would reject.",
        )

    # 7. A created clone has a 168-hour life. Checking it last means a run that is
    #    otherwise ready still fails closed once the voice has been deleted.
    remaining = decision.remaining_ttl
    if remaining is not None and remaining <= 0:
        decision.add(
            ROUTE_PAYMENT_BLOCKED,
            f"the cloned voice was created {CLONE_TTL_HOURS}h ago and provider storage "
            "has deleted it. Cloned voices are temporary unless used within the window; "
            "a new clone must be created and first-used in one continuous session.",
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