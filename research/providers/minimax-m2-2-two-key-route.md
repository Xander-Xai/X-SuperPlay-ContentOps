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

CLONE_KEY_REQUIRED
SUBSCRIPTION_ONLY_BILLING_UNPROVEN
ACTIVATION_CASH_INSUFFICIENT
ACTIVATION_CHARACTER_FEE_UNAUTHORISED
CROSS_KEY_CLONED_VOICE_TTS_UNKNOWN
```

**No upload, no clone, no synthesis.** `upload=0, clone=0, tts=0`.

The commercial route is now vendor-confirmed rather than ruled out. Five independent
gates stand between here and a live run, and fixing any one of them does not fix the
others -- which is why they are listed rather than reduced to a single verdict: a run
that provisions a key and sees the same route code again would reasonably conclude the
key was wrong.

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

### `ACTIVATION_CASH_INSUFFICIENT`

Claim 1 says the ¥9.90 is charged. Only a pay-as-you-go key deducts account balance
(付费服务协议 4.3(1)), and the activation synthesis runs on the pay-as-you-go key — so
the fee draws on cash, and **cash is 0.00**.

An approved charge with no balance behind it is not payable. The options are all
Founder decisions and none are automatic here:

- recharge (explicitly **not** automatic),
- consume `voucher_balance = 15.00` (explicitly **not** automatic, and #23 recorded its
  *kind* as unclassified — it appears in the invoice table only as an order payment
  method),
- a Credit Pack (cannot reach this resource at all — credits cover the same resource
  set as the plan, and the plan excludes 快速复刻).

### `SUBSCRIPTION_ONLY_BILLING_UNPROVEN` — and it is **not** relaxed

`BillingGuard.evaluate("speech")` returns `BLOCKED_BILLING_SOURCE_UNCERTAIN`:

```
balance field voucher_balance is 15.0, so paid funds could be consumed
```

The obvious shortcut here would be to relax the guard because "the ¥9.90 is authorised,
so the guard no longer needs to apply". That would be wrong, and the reason is worth
stating precisely: **the guard and the fee answer different questions.**

> The guard asks: *can this Subscription Key spend anything outside included plan usage?*
> The fee authorisation answers: *is this one CNY 9.90 charge approved?*

Weakening the guard to get past a ¥15 voucher balance would make **every later
narration** unverifiable — which is the whole safety property the speech provider has —
in exchange for one voice. The guard is untouched. Test 12 asserts it.

**Do not remove the `BillingGuard` protection to work around `voucher = 15`.**

## Current stop: `CLONE_KEY_REQUIRED`

`MINIMAX_CLONE_KEY` is unset, and there is no fallback chain — deliberately. The
resolver reads that one variable and nothing else, because `resolve_credential()`'s
chain (Subscription Key → API Key → `~/.mmx/config.json`) is right for TTS and fatal
here: inheriting it would let a machine with only a Subscription Key "resolve" a clone
credential and repeat the refused 2061 request.

Searched and confirmed absent: `~/.mmx/config.json` (holds only the `sk-cp-`
Subscription Key, `region: cn`), the repository `.env` (absent), `.private/`,
`runtime/`, `runtime-config-backups/`, `runtime-diagnostics/`, `diagnostics/`. No
`sk-api-` value exists anywhere on this host outside test fixtures.

**To provision it**, in the official CN console for **this same account**:

> 账户管理 → 接口密钥 → 创建新的 API Key

Recharge is **not** required to create the key. Store it locally, like every other
credential here, and **never paste it into chat, a PR or a log.**

The key is needed for **two** calls, and no others: the single upload, and the single
activation synthesis that pays the ¥9.90. Regular narration stays on the Subscription
Key.

Two further non-credential prerequisites:

- **个人认证 / 企业认证** must be complete. Missing verification returns `2038`, a
  refusal *after* the upload has already disclosed the sample.
- **`voice_id` uniqueness.** `2039 语音克隆 voice_id 重复`. `XSuperPlayFounderV1` was
  never created — the single attempt was refused before completion — so it should be
  free. If it answers 2039, a prior attempt *did* create it and the existing voice
  must be inspected rather than re-cloned.

## The five gates, and which of them an operator can close

```
CLONE_KEY_REQUIRED                  provisioning              Founder creates a key
SUBSCRIPTION_ONLY_BILLING_UNPROVEN   account state            Founder resolves voucher
ACTIVATION_CASH_INSUFFICIENT         account state            Founder recharges
ACTIVATION_CHARACTER_FEE_UNAUTHORISED  approval               Founder approves ¥0.0154
CROSS_KEY_CLONED_VOICE_TTS_UNKNOWN  live verification        only a real synthesis
```

The first four are Founder actions. The fifth is not an action at all — it is answered
by running the route, which the first four gate. That is why the receipt reports all
five together: an operator who clears four of them and still sees a stop is being told
the truth, not left guessing which one they missed.

## What was deliberately not done

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

## 五个阻塞点

```
CLONE_KEY_REQUIRED                    配置      Founder 创建按量 API Key
SUBSCRIPTION_ONLY_BILLING_UNPROVEN    账号状态  Founder 处理 voucher 余额
ACTIVATION_CASH_INSUFFICIENT          账号状态  Founder 充值（现金余额为 0.00）
ACTIVATION_CHARACTER_FEE_UNAUTHORISED 审批      Founder 批准 ¥0.0154
CROSS_KEY_CLONED_VOICE_TTS_UNKNOWN    实测验证  只能由一次真实合成回答
```

前四项是 Founder 操作，第五项不是操作——它由执行路由来回答，而执行路由正是被前四项
挡住的。所以 receipt 会把五项一起报出来：清掉四项后仍然停住，是在说实话，而不是让人
猜自己漏了哪一步。

## `ACTIVATION_CASH_INSUFFICIENT` 的含义

`cash_balance = 0.00`，而只有按量计费 API Key 会扣账户余额（付费服务协议 4.3(1)）。
**已批准的收费，不等于可支付的收费。** 三条路都由 Founder 决定，且都不是自动的：
充值（**不自动**）、使用 `voucher_balance = 15.00`（**不自动**，且 #23 已记录其
*种类* 未分类——在官方资料中仅作为订单支付方式出现）、积分包（**无法覆盖该资源**：
积分与 Token Plan 覆盖相同资源，而套餐排除快速复刻）。

## 不要为了绕过 voucher = 15 而移除 BillingGuard

`BillingGuard` 回答的问题和 ¥9.9 授权回答的问题**不是同一个**：

> 守卫问的是：*这个 Subscription Key 会不会消耗套餐额度之外的资金？*
> 费用授权答的是：*这一笔 ¥9.9 扣费是否被批准？*

为了让 ¥15 的代金券余额通过而放宽守卫，会让**之后的每一次旁白**都失去可验证性——
那正是 speech provider 全部安全性的来源——代价却只是换一条音色。守卫保持不变，
测试 12 对此有断言。

## 需要 Founder 处理的事项

1. **创建 `MINIMAX_CLONE_KEY`**：官方控制台 `账户管理 → 接口密钥 → 创建新的 API Key`，
   必须是**同一国内开放平台账号**。创建 Key 本身不需要充值（本次也未执行任何充值）。
2. **处理充值**：现金余额需 ≥ ¥9.9 才能支付激活费。**不自动充值、不自动使用 voucher、
   不自动使用积分包。**
3. **批准首次激活的字符费用 ¥0.0154**（与 ¥9.9 分开授权）。
4. **`voucher_balance = 15.00`**：处理或等待失效，否则 M Plan 纯额度无法被证明。

密钥只在本地配置，**不要粘贴到聊天、PR 或日志中**。

## 本次未做

未上传、未克隆、未激活合成、未重试此前返回 2061 的请求；未创建按量 Key、未充值、
未消耗 voucher 或积分包；未使用 `moss_audio_*` 作为目标或替代测试样本（该排除项已
写入 receipt）；未转向其他供应商、未使用未文档化端点。

此前那次 `/v1/files/upload` 在 2061 之前成功过，但其 `file_id` 从未保存，**不可复用**。