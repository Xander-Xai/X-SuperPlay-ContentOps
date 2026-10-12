---
title: MiniMax M2.2 two-key Founder clone route — official verification and live blockers
canonical: false
type: research
status: current
issue: "#34"
checked_at: "2026-10-12"
---

# M2.2: create the Founder clone, and speak with it on M Plan

> Research artefact, not canonical design. Canonical capability status lives in
> `docs/MEDIA-PROVIDER-CONTRACT.md` and `docs/CURRENT-STATE.md`.
>
> Continues [minimax-two-key-clone-route.md](minimax-two-key-clone-route.md) (Issue #23),
> which verified the route's preconditions and left three questions open. This run
> closes the ones the official sources can answer, measures the account, and stops at
> the blockers that remain.
>
> 中文说明见本文件末尾。

## Result

```
VENDOR_CONFIRMED  +  LIVE_VERIFICATION_PENDING

STOP: VOUCHER_CLONE_FEE_ELIGIBILITY_UNKNOWN    <- decisive, needs an account-specific answer
     ACTIVATION_CHARACTER_FEE_UNAUTHORISED
     CROSS_KEY_CLONED_VOICE_TTS_UNKNOWN          <- resolved by running, not by deciding
```

**No upload, no clone, no synthesis.** `upload=0, clone=0, tts=0`. No charge.

Two earlier gates are **closed**: `CLONE_KEY_REQUIRED` (the pay-as-you-go key is
provisioned and verified live) and `SUBSCRIPTION_ONLY_BILLING_UNPROVEN` (the official
deduction-chain rule, below). What remains is one fact nobody can look up from here, one
approval, and one verification that only a real run produces.

## Vendor confirmation, and what it is allowed to change

An earlier revision of this document concluded the payment route was **impossible**.
That conclusion was too strong, and it is corrected here rather than quietly dropped.

It was inferred from the published rules alone: the fee is pay-as-you-go priced, it is
triggered by a synthesis, only a pay-as-you-go key can be charged for it, and the
subscription plan that must perform the synthesis does not cover voice management. Each
step is sourced. The error was assuming that the published rules fully describe a
commercial arrangement made on a specific account — which they do not.

The Founder has obtained explicit confirmation from **MiniMax customer service** for
this account:

```
FOUNDER_SUPPLIED_VENDOR_CONFIRMATION
```

| # | Confirmed |
|---|---|
| 1 | 使用克隆音色首次合成时, 收取一次性 ¥9.9 音色克隆费 |
| 2 | 首次收费完成后, 音色从临时有效转为永久有效 |
| 3 | 后续语音合成仅收取对应字符的正常费用 |
| 4 | 已经支付 ¥9.9 激活的音色, 可以继续使用 M Plan 套餐进行语音合成 |

**This is account-level commercial evidence. It is not proof that any API call
succeeds.** Nothing has been executed under it, nothing has been charged, and the
route's status is therefore:

```
commercial_status  VENDOR_CONFIRMED
verification_status LIVE_VERIFICATION_PENDING
```

— deliberately **not** `VERIFIED`.

### What the confirmation does *not* settle

1. **Whether the cross-key synthesis is permitted by the API.** Claim 4 is a billing
   statement. `2042 无权访问该 voice_id | 请确认是否为该 voice_id 创建者` is an API
   permission error. A commercial assurance is not a permission grant, so
   `CROSS_KEY_CLONED_VOICE_TTS_UNKNOWN` stands until one real synthesis answers it.
2. **Whether this account can pay.** Claim 1 says the fee is charged; it says nothing
   about the balance it will be charged to, and `cash_balance` is `0.00`.
3. **What the activation synthesis itself costs in characters.** See below.

### The 168-hour clock gains a second meaning

> 本接口产出的快速复刻音色为临时音色,若希望永久保留某复刻音色,请于 168 小时(7 天)
> 内在任意 T2A 语音合成接口中调用该音色。若超过时限,该音色将被删除。

Claim 2 says the voice becomes permanent **after the first charge**. So the 168-hour
window is no longer only an expiry — it is also the deadline on the activation charge.
A clone never activated inside the window is deleted, and so is the ¥9.90 that would
have activated it. Clone and activation remain one continuous session.

## Three fees, and a fourth that was nearly invisible

The earlier framing of "the CNY 9.90" was always incomplete. It is three components
with different owners:

| Component | Amount | When | Status |
|---|---|---|---|
| `clone_creation` | **¥0.00** | never at clone time (官方: 复刻音色时不立即收费) | `VERIFIED_OFFICIAL` |
| `first_activation` | **¥9.90** | on the first synthesis using the voice | `FOUNDER_SUPPLIED_VENDOR_CONFIRMATION` |
| `regular_tts` | per character | every later synthesis, M Plan-eligible per claim 4 | `LIVE_VERIFICATION_PENDING` |

And a fourth that the earlier framing collapsed:

```
FIRST_ACTIVATION_TTS_FEE_UNKNOWN
```

The **activation synthesis is itself an ordinary billable TTS request**. It is not free
just because it is short. At the published rate:

> 同步语音合成 T2A speech-2.8-hd = 3.50 元/万字符。计费项是字符数,以 10000 个字符
> (输入)为单位,**1 个汉字算 2 个字符**,英文字母、希腊字母、标点符号、特殊符号、空格、
> 回车等算 1 个字符。

The activation text is `这是一段用于首次激活的最短自然中文语音样本。` — a real
sentence, not a meaningless single character, because the same recording is what
Founder listening later judges.

| | |
|---|---|
| billable characters | **44** |
| rate | 3.50 / 10k |
| **computed estimate** | **¥0.015400** |
| **recorded value** | `FIRST_ACTIVATION_TTS_FEE_UNKNOWN` |
| separately authorised | **NO** |

**It is not written as zero.** It is small, and small is exactly why that would be
dangerous: the Founder's authorisation covers the ¥9.90 clone fee and does not extend
to additional character spend. Writing `0.00` would both overstate what was approved
and understate what the call costs. It stays an unknown until a receipt observes it or
an invoice confirms it, and it needs its own decision.

Both numbers are carried: `activation_character_cny_estimated` so a Founder has
something to approve, and `activation_character_cny` as the honest unknown. A Founder
asked to approve a charge needs the figure; refusing to state it would push the
decision into guesswork.

## Measured on this account, read-only, 2026-12

`POST /account/query_balance` and `/v1/token_plan/remains` with the **Subscription
Key**. Neither is a generation endpoint; no quota was consumed.

| Field | Value |
|---|---|
| `cash_balance` | **0.00** |
| `credit_balance` | 0.00 |
| `voucher_balance` | 15.00 |
| `owed_amount` | 0.00 |
| `available_amount` | 15.00 |
| plan quota, 5-hour window | 59 % |
| plan quota, weekly window | 62 % |

### `ACTIVATION_CASH_INSUFFICIENT` — still standing

Claim 1 says the ¥9.90 is charged, and the M Plan FAQ names exactly one key that gets
charged: the pay-as-you-go key. The activation synthesis runs on that key, so the fee
draws on the account balance — and **cash is 0.00**.

An approved charge with no balance behind it is not payable. The options are all Founder
decisions and none are automatic here:

- recharge (explicitly **not** automatic),
- use `voucher_balance = 15.00` (explicitly **not** automatic, and see below — its ability
  to fund a pay-as-you-go charge is `UNKNOWN`),
- a Credit Pack (cannot reach this resource at all — credits cover the same resource set
  as the plan, and the plan excludes 快速复刻).

Note the deliberate asymmetry. The same official rule that let the Subscription-Key
in-plan TTS through **does not** clear this gate, because this request is made by the
pay-as-you-go key and that is the one key the account balance is charged for. Same
evidence, opposite verdict, because the key differs.

### Superseded: the old "do not relax the guard" note

> **Earlier text, now superseded.** This section previously read *"SUBSCRIPTION_ONLY_
> BILLING_UNPROVEN — and it is not relaxed"*, with `BillingGuard.evaluate("speech")`
> returning `BLOCKED_BILLING_SOURCE_UNCERTAIN` on `voucher_balance is 15.0`.
>
> That block was **correct under the rule as written and wrong under the official
> facts**: the flat "every balance must be exactly zero" rule could not distinguish
> "the balance exists" from "this request will be deducted from it", and for a
> Subscription-Key in-plan speech request those are different claims.
>
> The principle it protected was right, though, and the reasoning behind it still
> matters for a different reason — see **What was *not* concluded** below. Removing a
> gate because it is inconvenient is not the same as correcting a gate because it was
> measuring the wrong thing. This was the second.

## `voucher_balance = 15.00` — classified

**`VOUCHER_CLASSIFICATION`: NOT_IN_SUBSCRIPTION_KEY_DEDUCTION_CHAIN. Not a Credit Pack.
Not required to be cleared.**

This was `UNKNOWN` in every earlier round. It is now resolved, and it resolves in the
direction that matters: the voucher is **not** something a Subscription-Key in-plan
speech request can spend, so it never had to block this stage at all.

The official M Plan FAQ states the Subscription Key's deduction chain exhaustively:

> A Subscription Key only uses your M Plan usage and credit packs. When you reach your
> usage limit, any remaining credit pack balance is used next. **Your account balance is
> charged only when you use a pay-as-you-go API Key.**
> — `platform.minimax.cn/docs/guides/pricing-token-plan`, M Plan FAQ

Three funds, three chains:

| Fund | Chain | Reachable by a Subscription-Key in-plan TTS? |
|---|---|---|
| M Plan 套餐内额度 | Subscription Key | **yes** — this is the point |
| `credit_balance` 积分包 | Subscription Key, after plan quota | yes (measured **0.00**) |
| `voucher_balance` 代金券 | **neither** | **no** |
| `cash_balance` 账户余额 | pay-as-you-go key only | **no** |

> 代金券只可用于消费,不可用于抵扣欠费金额。 — 付费服务协议 4.4. In the invoice table a
> voucher appears as an **order payment method** (使用代金券), i.e. it pays for
> purchases, not for metered API calls.

### The distinction this fixes

The guard previously required **every** balance to be exactly zero. That treats
"the balance exists" and "this request will be deducted from it" as the same claim.
For `voucher_balance = 15.00` they are not: the balance exists, and a Subscription-Key
speech request cannot reach it.

Blocking a provably unreachable balance is not caution. It is a gate that has taught
its readers to bypass it — and this repository nearly did exactly that, by contemplating
removing the `BillingGuard` to get past a voucher.

### What was **not** concluded

**Whether a voucher can fund a pay-as-you-go charge is still `UNKNOWN`.** No official
page reached states it either way. `available_amount` happens to equal
`voucher_balance` (15.00) while `cash_balance` is 0.00, which is suggestive — and
suggestive is not evidence. A comparable field on a *different* vendor's platform
includes vouchers in its spendable balance, but importing another vendor's semantics is
exactly the wrong move, so it was not used.

That is why `ACTIVATION_CASH_INSUFFICIENT` **did not move**. The activation runs on the
pay-as-you-go key, which is the one key the FAQ says *does* charge the account balance.
Same evidence, opposite verdict, because the key is different.

And per the Founder's instruction, the voucher **is not required to be cleared, spent,
or expiring.** It is recorded, classified, and left alone.

## `BillingGuard` — scoped change, and what it deliberately leaves shut

```
SUBSCRIPTION_KEY_DEDUCTION_CHAIN = ("credit_balance",)
PAYG_DEDUCTION_CHAIN             = ("cash_balance", "credit_balance", "voucher_balance")
ALWAYS_ZERO_BALANCE_FIELDS       = ("owed_amount",)
```

Three properties, each asserted by a test:

1. **Presence is never relaxed.** Every one of the four fields must still be present and
   numeric, whichever chain applies. A field the platform stopped sending blocks, or a
   schema change would read as "that fund is fine".
2. **Zero-ness is chain-scoped.** A Subscription-Key request needs `credit_balance` at
   zero (measured 0.00) and `owed_amount` at zero. `cash_balance` and `voucher_balance`
   are reported in `observed_out_of_chain` — visible, not dropped.
3. **A pay-as-you-go credential still needs everything at zero.** Same fixture, opposite
   verdict. If the two ever agree, the split is broken.

Measured on this account, both keys, after the change:

```
SUBSCRIPTION  SAFE_INCLUDED_PLAN     out-of-chain: cash_balance=0.0, voucher_balance=15.0
PAYG          BLOCKED                credential class is PAYG, not a Subscription Key
```

`SUBSCRIPTION_ONLY_BILLING_UNPROVEN` has cleared, on official evidence rather than on a
Founder request.

## Keys: verified live, read-only

`MINIMAX_CLONE_KEY` is configured locally in `.env` (gitignored, untracked, never
printed, never committed). It classifies `PAYG`, and it is a **different secret** from
the Subscription Key.

| Probe | PAYG clone key | Subscription key |
|---|---|---|
| `POST /v1/get_voice` | `status_code=0` | `status_code=0` |
| `GET` balance endpoint | `status_code=0` | `status_code=0` |
| `cash_balance` | 0.00 | 0.00 |
| `credit_balance` | 0.00 | 0.00 |
| `voucher_balance` | 15.00 | 15.00 |
| `owed_amount` | 0.00 | 0.00 |

**Identical balances from two different keys is account-level evidence that they are
one account** — which is the requirement the route has, and it is now measured rather
than assumed. It is also evidence about account *scope*, not about resource *scope*:
both keys can list `voice_cloning`, and both list the same one. Listing is visibility.
Only a synthesis is usability, and that remains `CROSS_KEY_CLONED_VOICE_TTS_UNKNOWN`.

Cost of this verification: `upload=0, clone=0, tts=0`. Both probes are metadata reads
that previous measurement showed consume no quota and cost nothing.

### The key is in the chat transcript

The Founder supplied the key in conversation. It is now also on local disk in `.env`,
which is the correct home for it — but a secret pasted into a chat is a secret that has
been disclosed. **Rotate it after this round** and set the replacement in `.env` the
same way. No repository commit ever contained it.

## `VOUCHER_CLONE_FEE_ELIGIBILITY_UNKNOWN` — the stop, and why it is not closable here

The Founder authorised paying from the existing ¥15.00 voucher, up to ¥10. That is an
instruction about **which instrument to use**. It is not proof that the instrument covers
音色管理, and treating the two as the same claim is how a ¥9.90 charge gets attempted
against something that cannot carry it.

### What the official sources establish

`VERIFIED_OFFICIAL`

- 代金券 is an **order payment method**: 使用代金券 | 扣除代金券后实际支付的金额,
  代金券抵扣部分不可开票 — M Plan FAQ, 开票金额怎么计算.
- 账户余额只有在使用按量计费 API Key 时才会扣除. So a pay-as-you-go request draws on the
  account balance, which is the only place a voucher could apply.
- 扣费顺序为 **M Plan 额度优先、积分包其次**; 积分包支持…图像与音频生成 — **快速复刻 is not
  named**, so a Credit Pack cannot pay this fee either.

### What they do not

`UNKNOWN`

1. **Whether a voucher offsets API 调用费用 as opposed to orders.** There is exactly one
   official statement that says 使用范围:仅可用于抵扣 MiniMax 开放平台内的 API 调用费用,
   and it sits inside the **Token Plan 好友邀请活动** (referral reward) section — so it
   governs *that programme's* voucher. This account's ¥15.00 voucher has unknown
   provenance, so that scope cannot be transferred to it. A search-index snippet showed
   the sentence; fetching the live CN FAQ page shows it is **not** in the current
   rendered page at all, which is exactly why a cached snippet is not evidence.
2. **The definitive scope.** 付费服务协议 4.4: 代金券只可用于消费,不可用于抵扣欠费金额。
   **具体权益应以产品界面公示及服务权益实际展示为准** — the answer lives in the product
   console, which no API endpoint exposes.
3. **Deduction priority between voucher and cash** within 账户余额.
4. **This voucher's issuance date and remaining validity.** No reachable endpoint returns
   them. Balance reads 15.00, and expired vouchers auto-invalidate, so that is *consistent*
   with valid — it is not proof.

This is not a documentation gap that more searching closes. The answer is on a page an API
client cannot read, and the one favourable statement belongs to a different programme.

### One thing that *is* structurally safe

`cash_balance = 0.00` and `credit_balance = 0.00`. There is no cash and no Credit Pack on
the account to be debited, so an ineligible voucher would most plausibly produce a refusal
(`1008 余额不足`) rather than an unauthorised charge. That is reassuring, and it is still
not a substitute for the eligibility proof — "the failure mode is probably clean" is not
"the payment path is proven", and the Founder's instruction was to prove the path. It is
also not the Founder's authorisation to upload their voice on the expectation that it will
probably work.

**Therefore: no upload, no clone, no synthesis.** The sample was not transmitted.

## `FOUNDER_VOUCHER_ACTIVATION` — the authorisation, encoded

Implemented and refusing. The ceiling is on the **combined** charge, because per-component
ceilings let two sub-ceiling charges add past what was agreed:

```python
allowed_voucher_spend_cny      = Decimal("10.00")   # total, inclusive
allowed_cash_spend_cny         = Decimal("0.00")
allowed_credit_pack_spend_cny  = Decimal("0.00")
allow_auto_recharge            = False
max_clone_count                = 1
max_activation_tts_count       = 1
allow_unbounded_payg_tts       = False
```

Scoped to one `voice_alias` and one `voice_id_hash`, so a permission granted for one clone
cannot be spent on another. Refuses on: eligibility `UNKNOWN`, unreadable or empty voucher
balance, projected total above ¥10, a non-zero or unreadable cash or Credit Pack balance,
a reused count, a retry, an unbounded PAYG path, or an enabled auto-recharge.

Nine tests, pure policy, no credential and no network. The decisive one asserts that an
`UNKNOWN` grade refuses **even with a ¥15.00 balance showing** — a balance proves an
instrument exists, not that it covers this charge.

---

## `READY_TO_EXECUTE` — 15 of 18

Plus the voucher gate above, which is the decisive one.

| # | Check | State |
|---|---|---|
| 1 | CLONE_KEY is a pay-as-you-go key | **PASS** |
| 2 | TTS_KEY is the existing Subscription Key | **PASS** |
| 3 | the two keys are different secrets | **PASS** |
| 4 | CLONE_KEY reaches the host (read-only) | **PASS** |
| 5 | 个人认证 / 企业认证 complete | PASS (assumed; `2038` would refuse at clone time) |
| 6 | **cash balance can pay the activation** | **FAIL** — 0.00 |
| 7 | Subscription-Key in-plan TTS is provable | **PASS** — `SAFE_INCLUDED_PLAN` |
| 8 | one-time fee within the ¥9.90 ceiling | **PASS** |
| 9 | **¥9.90 activation fee authorised** | **FAIL** — not set for this run |
| 10 | **activation character fee authorised** | **FAIL** — not set, never assumed zero |
| 11 | M Plan quota in both required windows | **PASS** — interval / weekly remaining |
| 12 | `voice_id` satisfies the documented rules | **PASS** |
| 13 | `voice_id` is free (no `2039`) | PASS (confirmed by the clone response) |
| 14 | Founder sample present, digest unchanged | **PASS** — matches the registry |
| 15 | raw sample and raw voice_id stay out of Git | **PASS** |
| 16 | the excluded `moss_audio_*` family is not used | **PASS** |
| 17 | no automatic retry | **PASS** |
| 18 | clone and activation run in one continuous session | **PASS** |

### `MAX_ACTUAL_CHARGE` = **¥9.9154**

| Component | Amount |
|---|---|
| `clone_creation` | ¥0.00 — never charged (官方: 复刻音色时不立即收费) |
| `first_activation` | ¥9.90 |
| activation characters (44 billable @ 3.50/10k) | **¥0.0154** — `FIRST_ACTIVATION_TTS_FEE_UNKNOWN` |
| **`MAX_ACTUAL_CHARGE`** | **¥9.9154** |

Ceiling ¥9.90 for the voice fee; the ¥0.0154 is a separate approval and is **not**
folded into it. Neither is assumed zero.

---

- No upload, no clone, no activation synthesis, no retry of the refused 2061 request.
- No PAYG key created, no recharge, no Credit Pack, no voucher consumption.
- No use of the pre-existing `moss_audio_*` voice — not as the target and not as a
  substitute test sample. The exclusion is recorded in the receipt so it travels with
  the evidence rather than living only in prose.
- No other provider, no browser-based console purchase, no undocumented endpoint beyond
  the `/account/query_balance` dependency `BillingGuard` already declares.

The prior `/v1/files/upload` succeeded before the 2061 refusal and its `file_id` was
never persisted. It is **not** reusable, and nothing here pretends otherwise: a fresh
clone needs a fresh upload.

---## 结论

```
VENDOR_CONFIRMED  +  LIVE_VERIFICATION_PENDING
```

Founder 已从 MiniMax 客服获得**本账号专属**确认：

1. 使用克隆音色首次合成时，收取一次性 ¥9.9 音色克隆费；
2. 首次收费完成后，音色从临时有效转为永久有效；
3. 后续语音合成仅收取对应字符的正常费用；
4. 已经支付 ¥9.9 激活的音色，可以继续使用 M Plan 套餐进行语音合成。

记录为 `FOUNDER_SUPPLIED_VENDOR_CONFIRMATION`。

> **这是账号级商务证据，不是实际 API 执行成功的证明。**
> 状态因此是 `VENDOR_CONFIRMED` + `LIVE_VERIFICATION_PENDING`，**不是 `VERIFIED`**。
> 此前版本据公开规则判定"商业路线不可能成立（PROVEN_IMPOSSIBLE）"，**该结论过强，
> 现予更正**：公开规则不足以描述一个具体账号上的商业安排。

### 确认没有解决的三件事

1. **跨 Key 合成是否被 API 允许。** 第 4 条是计费说明，而 `2042 无权访问该 voice_id`
   是 API 权限错误。商务承诺不等于 API 授权，故
   `CROSS_KEY_CLONED_VOICE_TTS_UNKNOWN` 仍然成立，必须由一次真实合成回答。
2. **本账号是否付得起。** 第 1 条说会收费，但没说从哪个余额扣，而 `cash_balance = 0.00`。
3. **首次激活合成本身的字符费用。** 见下。

## 三种费用，外加一个差点被吞掉的第四种

| 项目 | 金额 | 发生时机 | 证据等级 |
|---|---|---|---|
| `clone_creation` | **¥0.00** | 创建时永不收取 | `VERIFIED_OFFICIAL` |
| `first_activation` | **¥9.90** | 首次使用该音色的合成时 | `FOUNDER_SUPPLIED_VENDOR_CONFIRMATION` |
| `regular_tts` | 按字符 | 之后每次合成，激活后可用 M Plan | `LIVE_VERIFICATION_PENDING` |
| 首次激活的**字符费** | **未知** | 与 ¥9.9 同一次合成中 | `FIRST_ACTIVATION_TTS_FEE_UNKNOWN` |

第四项是本次更正的核心。**首次激活合成本身是一次正常计费的 TTS 请求**，不是"因为
很短所以免费"。按官方 `speech-2.8-hd = 3.50 元/万字符`（1 个汉字算 2 个字符）：

| | |
|---|---|
| 激活文本 | `这是一段用于首次激活的最短自然中文语音样本。` |
| 计费字符 | **44** |
| **计算估值** | **¥0.015400** |
| **记录值** | `FIRST_ACTIVATION_TTS_FEE_UNKNOWN` |
| 是否单独授权 | **否** |

**不得写成零。** 金额很小，而"金额很小"正是它容易被顺手放行的原因。Founder 的 ¥9.9
授权只对应音色克隆费，**不自动涵盖额外的字符消费**。写成 `0.00` 会同时高估已获授权
范围、低估实际调用成本。它只有在 receipt 实际观测到、或账单确认之后才能定值，且
需要单独决策。

两个数字都会记录：`activation_character_cny_estimated` 供 Founder 审批，
`activation_character_cny` 保留为诚实的未知值。

## 168 小时时钟获得了第二重含义

> 复刻音色为临时音色，请在 168 小时（7 天）内在任意 T2A 合成接口中调用，否则删除。

客服第 2 条说"首次收费完成后转为永久有效"。因此 168 小时窗口不仅是过期时间，
**也是激活扣费的截止时间**。窗口内未激活的音色会被删除，¥9.9 也就无从扣起。
克隆与激活仍然是同一次连续操作。

## 当前状态：三个阻塞点

```
ACTIVATION_CASH_INSUFFICIENT            账号状态  Founder 充值（现金余额 0.00）
ACTIVATION_CHARACTER_FEE_UNAUTHORISED   审批      Founder 批准 ¥0.0154
CROSS_KEY_CLONED_VOICE_TTS_UNKNOWN      实测验证  只能由一次真实合成回答
```

**已解除的三项**（本轮取得证据）：

| 原阻塞 | 现状态 | 依据 |
|---|---|---|
| `CLONE_KEY_REQUIRED` | **已解除** | Founder 已提供按量 Key，本地 `.env` 配置，实测 `status_code=0` |
| `SUBSCRIPTION_ONLY_BILLING_UNPROVEN` | **已解除** | 官方 M Plan FAQ：Subscription Key 只用套餐额度与积分包；`voucher_balance` 不在该扣费链中 |
| `ACTIVATION_CHARACTER_FEE_UNAUTHORISED` 之外的计费链路 | 已厘清 | 见下方"代金券分类" |

前两项是 Founder 操作，第三项不是操作——它由执行路由来回答，而执行路由正是被前两项
挡住的。receipt 会把三项一起报出来：清掉两项后仍然停住，是在说实话。

## 代金券的真实计费类别（本轮解决）

**`VOUCHER_CLASSIFICATION`：不在 Subscription Key 扣费链中。不是 Credit Pack。
不需要清空。**

官方 M Plan FAQ：

> A Subscription Key only uses your M Plan usage and credit packs. When you reach your
> usage limit, any remaining credit pack balance is used next. **Your account balance is
> charged only when you use a pay-as-you-go API Key.**

四种资金，三条链：

| 资金 | 扣费链 | Subscription Key 套餐内 TTS 能扣到吗 |
|---|---|---|
| M Plan 套餐内额度 | Subscription Key | **能**——这正是目的 |
| `credit_balance` 积分包 | Subscription Key，套餐额度之后 | 能（实测 **0.00**） |
| `voucher_balance` 代金券 | **两者都不在** | **不能** |
| `cash_balance` 账户余额 | 仅按量计费 Key | **不能** |

> 代金券只可用于消费，不可用于抵扣欠费金额。——付费服务协议 4.4。在发票表中，代金券是
> **订单支付方式**（使用代金券），支付的是购买行为，不是有量化的 API 调用。

**因此不需要清空、不需要消耗、不需要等待失效。** 它只需被记录和分类。此前把它当作阻塞点，
是因为守卫规则是"所有余额必须为零"，无法区分"余额存在"与"本次请求会不会扣它"。

### 没有得出的结论

**代金券能否支付按量计费扣费：仍然 `UNKNOWN`。** 没有任何官方页面说明。`available_amount`
恰好等于 `voucher_balance`（均为 15.00）而 `cash_balance` 为 0.00，这只是暗示，不是证据。
某**其他**厂商平台的同类字段确实把代金券计入可用余额，但把别家语义搬过来是错误的做法，
因此没有采用。

这也正是 `ACTIVATION_CASH_INSUFFICIENT` **没有**解除的原因：激活走的是按量计费 Key，
而官方明确只有该 Key 会扣账户余额。**同一条依据，两个相反结论，因为 Key 不同。**

## BillingGuard 的改动范围

```
SUBSCRIPTION_KEY_DEDUCTION_CHAIN = ("credit_balance",)
PAYG_DEDUCTION_CHAIN             = ("cash_balance", "credit_balance", "voucher_balance")
ALWAYS_ZERO_BALANCE_FIELDS       = ("owed_amount",)
```

- **字段存在性从不放宽**：四项仍必须存在且可读，否则按 schema 变更阻断。
- **"必须为零"按扣费链划分**：链外余额进入 `observed_out_of_chain`，可见但不丢弃。
- **PAYG 凭证仍要求全部为零**：同一份 fixture，相反结论。

## 本轮实测（两把 Key，只读）

| 探测 | 按量 Key | 订阅 Key |
|---|---|---|
| `POST /v1/get_voice` | `status_code=0` | `status_code=0` |
| 余额接口 | `status_code=0` | `status_code=0` |
| `cash_balance` | 0.00 | 0.00 |
| `credit_balance` | 0.00 | 0.00 |
| `voucher_balance` | 15.00 | 15.00 |
| `owed_amount` | 0.00 | 0.00 |

**两把不同的 Key 返回完全相同的余额，这是账号级证据，证明它们属于同一个账号。**
这也证明了账号 *scope*，但不是资源 *scope*：两把 Key 都能列出 `voice_cloning`，且列出
的是同一条。列出是可见性，只有合成才是可用性。

`upload=0, clone=0, tts=0`。两个探测都是元数据读取，不消耗额度、不产生费用。

### 关于 Key 出现在聊天记录中

Founder 在对话中提供了该 Key。它现在也存在于本地 `.env`（正确的存放位置），但**粘贴进
聊天的密钥就是已经泄露的密钥**。**本轮结束后请轮换**，并在 `.env` 中以同样方式设置新值。
仓库的任何一次提交都没有包含过它。

## `MAX_ACTUAL_CHARGE` = **¥9.9154**

| 项目 | 金额 |
|---|---|
| `clone_creation` | ¥0.00 —— 创建时不收取（官方：复刻音色时不立即收费） |
| `first_activation` | ¥9.90 |
| 激活字符费（44 计费字符 @ 3.50/万字符） | **¥0.0154** —— `FIRST_ACTIVATION_TTS_FEE_UNKNOWN` |
| **`MAX_ACTUAL_CHARGE`** | **¥9.9154** |

音色费上限 ¥9.90；¥0.0154 是**单独授权**，不并入其中。两者都没有被假设为零。

## 需要 Founder 处理的事项

1. **充值**：现金余额需 ≥ ¥9.9 才能支付激活费。**不自动充值、不自动使用 voucher、
   不自动使用积分包。**
2. **批准首次激活的字符费用 ¥0.0154**（与 ¥9.9 分开授权）。
3. **轮换 `MINIMAX_CLONE_KEY`**：它已出现在聊天记录中。

`voucher_balance = 15.00` **不需要处理**。

密钥只在本地配置，**不要粘贴到 PR 或日志中**。

## 本次未做

未上传、未克隆、未激活合成、未重试此前返回 2061 的请求；未充值、未消耗 voucher 或
积分包；未使用 `moss_audio_*` 作为目标或替代测试样本（该排除项已写入 receipt）；
未转向其他供应商、未使用未文档化端点。

此前那次 `/v1/files/upload` 在 2061 之前成功过，但其 `file_id` 从未保存，**不可复用**。
