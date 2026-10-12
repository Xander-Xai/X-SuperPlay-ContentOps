---
title: MiniMax two-key clone route — official-rule verification
canonical: false
type: research
status: current
issue: "#23"
checked_at: "2026-10-12"
---

# Two-key clone route: what the official rules actually say

> Research artefact, not canonical design. Canonical capability status lives in
> `docs/MEDIA-PROVIDER-CONTRACT.md` and `docs/CURRENT-STATE.md`.
>
> Supersedes nothing. Complements
> [minimax-voice-clone-entitlement.md](minimax-voice-clone-entitlement.md), which records
> the measured 2061 refusal.

## Why this exists

The proposed route was: create the clone with a **pay-as-you-go key**, then synthesise
with the **Subscription Key** so TTS stays on M Plan quota. That route depends on two
things being true — that the ¥9.9 can actually be paid, and that a voice created under
one key is usable under another. Both were checked against current official sources
before anything was sent. **Neither is confirmed. The route is stopped.**

## Verdict summary

| # | Question | Verdict |
|---|---|---|
| 1 | Meaning of 2061 for this Subscription Key | `VERIFIED_OFFICIAL` |
| 2 | Does a pay-as-you-go API Key allow `voice_clone` | `VERIFIED_OFFICIAL` (with a caveat) |
| 3 | Same account resource domain for both key types | `VERIFIED_OFFICIAL` for keys; `UNKNOWN` for resources |
| 4 | **Can a voice_id created under one key be used by the other** | **`UNKNOWN`** |
| 5 | When the ¥9.9 is actually billed | `VERIFIED_OFFICIAL` |
| 6 | Does first use require payment via a pay-as-you-go Key | `UNKNOWN` |
| 7 | Balance / recharge-threshold limits | `VERIFIED_OFFICIAL` + `VERIFIED_LOCAL` |
| 8 | Does M Plan quota take priority over credit packs | `VERIFIED_OFFICIAL` |
| 9 | What kind of balance `voucher_balance = 15` is | `UNKNOWN` |
| 10 | A permission check that does not trigger synthesis fees | `VERIFIED_LOCAL` for listing; `UNKNOWN` for a dry-run |

---

## 1. 2061 for this Subscription Key — `VERIFIED_OFFICIAL`

The official MiniMax CLI `ERRORS.md` documents:

> `status_code 2061 (model not on plan)` — This model is not available on your current
> Token Plan.

Corroborated by the official M Plan model list, which covers text, **image and audio
models**, video (Explore/Build) and multimodal understanding. **音色管理 — voice
management — is not in that list.** Voice Design and Voice Cloning are priced separately
under 按量计费 (pay-as-you-go).

So 2061 here means: *the plan does not include voice management*. It is not a
verification failure and not a permission failure — the account already holds a cloned
voice, so verification has been satisfied at some point.

**Gap worth recording:** 2061 does **not** appear in the platform's own
[error-code reference](https://platform.minimaxi.com/docs/api-reference/errorcode.md).
That table lists 2038, 2039, 2042, 2048, 2056 — but not 2061. The only official
documentation of 2061 is the CLI repository. That is a thin source for a code that
decides a route.

## 2. Does a pay-as-you-go API Key allow `voice_clone` — `VERIFIED_OFFICIAL` (caveat)

The official voice-clone guide's own examples authenticate with a generic
`MINIMAX_API_KEY`, and the pricing table lists 快速复刻 Voice Cloning at **9.90 元/音色**
under 按量计费. The API FAQ says voice cloning requires **个人实名认证 or 企业认证**.

**Caveat, stated plainly:** no official page says "voice_clone requires a pay-as-you-go
Key". What is official is that the fee is pay-as-you-go priced and that the plan does not
cover the model. The pay-as-you-go route is therefore *implied* by the plan refusal, not
explicitly documented as the alternative.

## 3. Same account resource domain — split verdict

`VERIFIED_OFFICIAL` for the keys:

> 订阅 Key 与普通按量计费 API Key 相互独立，不能混用。
> (The Subscription Key and the regular pay-as-you-go API Key are mutually independent
> and cannot be mixed.)

Both are created under the same account — 账户管理 > 接口密钥 for pay-as-you-go,
订阅管理 > M Plan for the subscription Key.

`UNKNOWN` for **resources**. "Keys cannot be mixed" is a statement about keys and
billing. It says nothing about whether account-level *resources* such as a cloned voice
are shared between them. That is a different question and it is not answered anywhere.

## 4. Cross-key voice_id usability — **`UNKNOWN`** ← the decisive gap

**No official source confirms that a voice_id created under one key can be used for
synthesis under another.**

Two official facts pull in opposite directions:

- `POST /v1/get_voice` queries voices **"under the current account"**, which reads as
  account-scoped.
- Error **2042** exists precisely for this: `无权访问该 voice_id | 请确认是否为该
  voice_id 创建者` — *no permission to access this voice_id; confirm you are the creator
  of this voice_id.* A permission error scoped to the **creator** means access is
  mediated by something, and the official table does not say whether "creator" means the
  account or the key.

`VERIFIED_LOCAL`, and it is the strongest evidence available without spending: the
Subscription Key's `get_voice` listing **did** return the `moss_audio_*` voice, which was
created through the web UI and not by any API key of ours. So **listing** is
account-scoped and a voice not created by that key is visible to it.

But visibility is not usability. Listing a voice and synthesising with it are different
operations, and only the second one is what the route needs. `2042` is exactly the error
that would appear if visibility did not imply usability.

**Gate: `CROSS_KEY_VOICE_SCOPE_UNVERIFIED`.**

## 5. When the ¥9.9 is billed — `VERIFIED_OFFICIAL`

From the official 音色管理 pricing table:

> **快速复刻 Voice Cloning** — 9.90 元/音色 — **复刻音色时不立即收费，首次使用该音色进行
> 合成时才计入。试听字符按所选试听模型的单价计费。**

So: **the clone call is free. The ¥9.9 is charged at the first synthesis with that
voice.** And preview characters are billed separately at the preview model's rate — which
is why omitting `text` from the clone payload was the right call, and why the previous
attempt's zero charge is consistent with a refusal that happened before any synthesis.

This also means the earlier framing of a "one-time clone fee at clone time" was wrong in
its timing, and it is corrected here.

## 6. Does first use require payment via a pay-as-you-go Key — `UNKNOWN`

The fee is pay-as-you-go priced, and the official rule is unambiguous that
**account balance is only deducted when a pay-as-you-go API Key is used**
(账户余额只有在使用按量计费 API Key 时才会扣除). The Subscription Key uses only M Plan
quota and credit packs.

So the ¥9.9 can only be collected through a pay-as-you-go Key — **but the fee is
triggered by synthesis, and synthesis is required to be M Plan-only.** Those two official
facts do not obviously fit together:

- If the first synthesis runs on the Subscription Key, it is unclear whether the ¥9.9
  can be collected at all, or whether the synthesis is refused.
- If the first synthesis runs on a pay-as-you-go Key to trigger the fee, that is
  pay-as-you-go TTS, which this task forbids.

No official page addresses this combination. `UNKNOWN`, and it is a real contradiction
rather than a documentation gap that more searching would close.

## 7. Balance and recharge limits

`VERIFIED_OFFICIAL`: error 1008 is 余额不足 (insufficient balance). Recharge is via
WeChat online payment at 账户管理 > 余额, or corporate transfer for enterprise accounts.
A balance-alert threshold can be configured. **No minimum recharge amount is documented**
— so whether a recharge of exactly ¥9.9 is possible is `UNKNOWN`.

`VERIFIED_LOCAL`, measured on this account:

| Field | Value |
|---|---|
| `cash_balance` | **0.00** |
| `credit_balance` | 0.00 |
| `voucher_balance` | 15.00 |
| `owed_amount` | 0.00 |

`cash_balance` is zero, so a pay-as-you-go-priced ¥9.9 charge cannot currently be paid
from cash. Recharging is a payment action, which is the Founder's to take, not an
agent's.

## 8. M Plan quota versus credit packs — `VERIFIED_OFFICIAL`

> 扣费顺序为 M Plan 额度优先、积分包其次。
> (Deduction order is M Plan quota first, credit packs second.)

And credit packs cover "M3.1 Flash Preview 文本模型、H3 视频模型，以及图像与音频生成、
网络搜索和多模态理解能力" — image and audio **generation**. Voice management is not in
that list, so **a credit pack cannot pay the ¥9.9 either.**

## 9. `voucher_balance = 15` — `UNKNOWN`

The only official mention of 代金券 found is in the M Plan invoice table, where it appears
as an **order payment method**:

> 使用代金券 | 扣除代金券后实际支付的金额，代金券抵扣部分不可开票

That is, a voucher pays for purchases (recharge or subscription), and the part it covers
is not invoiceable. Nothing found says whether `voucher_balance` can be consumed by
metered API usage, and the `query_balance` field is not documented in the pages reached.

**`UNKNOWN`. Not tested, not consumed, and deliberately not zeroed.** It is recorded as an
open classification question rather than resolved by spending it.

## 10. A permission check that does not trigger synthesis fees — `VERIFIED_LOCAL`

`POST /v1/get_voice` is a metadata listing. It was called repeatedly during this work
with **zero charge and zero quota movement** (measured: interval 99 % and weekly 66 %
identical before and after). File-management list/retrieve/delete are likewise metadata.

Whether the provider offers an official *dry-run* that answers "can this voice synthesise
under this key" — `UNKNOWN`, and none is documented.

The practical free test is therefore: **synthesise with the voice that already exists**.
It carries no new ¥9.9 (its fee was settled when it was first used — it is listed under
`voice_cloning`, which only happens after a successful synthesis), and it consumes M Plan
quota that is already paid for. That is exactly what #33 proposes, and it answers
question 4 for free.

---

## Gates

```
STOP: CROSS_KEY_VOICE_SCOPE_UNVERIFIED      <- decisive
STOP: PAYMENT_ROUTE_NEEDS_FOUNDER_DECISION  <- also standing
```

The decisive one is the cross-key scope, for one reason: **it is free to answer.** #33's
test — synthesise with the existing voice via the Subscription Key — resolves it without
spending the ¥9.9, without a recharge, and without touching the voucher. If that test
fails with 2042, the two-key route is dead and the ¥9.9 question becomes moot. If it
succeeds, the route is viable and only the payment question remains.

No new voice was created to answer any of this. The task's instruction not to create a
voice merely to test was followed, and the 2061 attempt was not repeated.
