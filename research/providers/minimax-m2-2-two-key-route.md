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
CLONE_KEY_REQUIRED
SUBSCRIPTION_ONLY_BILLING_UNPROVEN
PAYMENT_ROUTE_BLOCKED
CROSS_KEY_CLONED_VOICE_TTS_UNKNOWN
```

**No upload, no clone, no synthesis.** `upload=0, clone=0, tts=0`.

Four independent blockers. Fixing any one of them does not fix the others, which is
why they are listed rather than reduced to a single verdict: a run that provisions a
key and sees the same route code again would reasonably conclude the key was wrong.

## The three questions #23 left open, now answered

### Q2 — does a pay-as-you-go key reach voice cloning? **Yes, by exclusion and by pricing.**

音色管理 — voice management, which contains 快速复刻 — is priced **only** under 按量计费.
Token Plan does not list it, so the pay-as-you-go key is the key type whose billing
domain contains the operation at all.

> 快速复刻 Voice Cloning — 9.90 元/音色 — 按量计费
> — `platform.minimax.cn/docs/pricing/overview`, `/docs/guides/pricing-paygo`

And the platform says the pay-as-you-go key covers the modalities voice belongs to:

> 按量付费:通过 接口密钥 > 创建新的 API Key,获取 API Key 按量付费支持使用所有模态模型,
> 包括语言、视频、语音、图像等
> — `platform.minimax.cn/docs/api-reference/api-overview`

**`VERIFIED_OFFICIAL`.** Upgraded from #23's `VERIFIED_OFFICIAL (with a caveat)`: no
page says "voice_clone requires a pay-as-you-go key", but the key type whose billing
domain contains the price is now unambiguous, and it is the opposite of the key that
was refused.

### Q8 — can a Credit Pack pay the ¥9.9? **No. Officially.**

#23 recorded this as "voice management is not in the credit-pack list", which was
inferred from an absence. It is now stated positively:

> 积分与 Token Plan 覆盖相同资源。若同一用量同时可由 Token Plan 套餐内额度和积分覆盖,
> 优先使用套餐内额度,超出部分由积分抵扣。
> — `platform.minimax.cn/docs/guides/pricing-token-plan`

Credits cover *the same resources as the plan*. The plan excludes 快速复刻 by name:

> 可用模型覆盖 MiniMax 全系模型(M3 / M2.7 / 图像 / 语音),少量特殊模型
> (MiniMax H3、音色设计、**快速复刻**等)暂不支持。

So credits cannot reach it, which is a second and independent reason the
`CREDIT_PACK_FALLBACK` route is closed. **`VERIFIED_OFFICIAL`.**

### A new fact #23 did not have — **cloned voices are temporary**

> 本接口产出的快速复刻音色为临时音色,若希望永久保留某复刻音色,请于 **168 小时(7 天)**
> 内在任意 T2A 语音合成接口中调用该音色(不包含本接口内的试听行为)。若超过时限,
> 该音色将被删除。
> — `platform.minimax.cn/docs/api-reference/api-overview` (音色快速复刻 / 注意事项)

**This inverts the order of operations.** A clone cannot be created now and used
later — it is deleted if no T2A call touches it inside seven days. Clone creation and
the first synthesis have to be **one continuous session**, which means the clone can
only ever be attempted when every other gate is already open. Attempting the clone
early and "activating" it later is not a slower path, it is a path that ends with a
¥9.90 fee and a voice that no longer exists.

Encoded as `CLONE_TTL_HOURS = 168` in `src/contentops/media/clone_route.py`, with an
injectable clock so the boundary is testable in microseconds.

### Q6 — how is the ¥9.9 collected at first synthesis? **Still a contradiction, now sharper.**

Q6 was `UNKNOWN` in #23. It is no longer a documentation gap; it is a conflict
between three official statements, and no operator-side action resolves it:

| # | Official statement | Source |
|---|---|---|
| 1 | The ¥9.90 is charged **at the first synthesis** with the voice, not at clone time | 定价概览 |
| 2 | The plan does not cover 快速复刻, and Credits cover the same resources as the plan | pricing-token-plan |
| 3 | 账户余额 **只有在按量计费 API Key 调用时才会扣除** — balance is deducted only when a pay-as-you-go key calls | 付费服务协议 4.3(1) |

Chain them: the fee is a pay-as-you-go-priced item; it is *triggered by* a synthesis;
only a pay-as-you-go key can be charged for it; and the key that must perform the
synthesis is a Subscription Key whose plan excludes the resource.

> **The ¥9.90 can only be collected by a pay-as-you-go synthesis, and a pay-as-you-go
> synthesis is exactly what this issue forbids.**

This is `PAYMENT_ROUTE_BLOCKED`. It needs an account-specific answer from MiniMax, not
more searching — no page addresses the combination because the combination is not a
supported path.

### Q4 — cross-key voice usability. **Still `CROSS_KEY_CLONED_VOICE_TTS_UNKNOWN`.**

Unchanged and unchanged in its importance. `get_voice` is account-scoped, error 2042
(`无权访问该 voice_id | 请确认是否为该 voice_id 创建者`) is the documented symptom if
visibility does not imply usability, and listing is not synthesising. The
Subscription Key's `get_voice` does list the pre-existing `moss_audio_*` voice, which
proves account-scoped visibility and nothing about synthesis. Must not be claimed as
supported before one real synthesis answers it.

### `2061` is absent from MiniMax's own error table

`platform.minimax.cn/docs/api-reference/errorcode` lists 1000–2056 and includes 2042,
2038, 2039, 2056 — **but not 2061**. The only official documentation of 2061 remains
the official CLI `ERRORS.md`. Worth recording, because 2061 is the code that decides
this route's viability and it rests on a thin source.

Note the same page now renders 2056 as 超出 **M Plan** 资源限制 — the plan was renamed
from Coding Plan, and older copies of that table in circulation still say Coding Plan.

## Measured on this account, read-only, 2026-10-12

`POST /account/query_balance` and `/v1/token_plan/remains` with the **Subscription
Key**. Neither is a generation endpoint; no quota was consumed.

| Field | Value |
|---|---|
| `cash_balance` | 0.00 |
| `credit_balance` | 0.00 |
| `voucher_balance` | **15.00** |
| `owed_amount` | 0.00 |
| `available_amount` | 15.00 |
| plan quota, 5-hour window | 87 % |
| plan quota, weekly window | 65 % |

### `SUBSCRIPTION_ONLY_BILLING_UNPROVEN`

`BillingGuard.evaluate("speech")` returns **`BLOCKED_BILLING_SOURCE_UNCERTAIN`**:

```
balance field voucher_balance is 15.0, so paid funds could be consumed
```

This is the guard working as designed. The guard requires `cash_balance`,
`credit_balance`, `voucher_balance` and `owed_amount` to be each **exactly zero**,
because a Subscription Key draws on plan usage *and* on purchased credits, and no
documented switch disables that fallback. A non-zero voucher balance is therefore the
only provable risk that paid funds could be consumed.

**This blocks #34 independently of the clone key.** Even with a provisioned PAYG clone
key and even if the cross-key question resolved favourably, the narration still cannot
be proved to be plan-only today.

It also has a scheduling consequence. The first-use fee is *triggered by* a synthesis,
so the synthesis is the precise step that could spend the wrong pot. The block
therefore has to fire **on the clone, before the upload** — which is what
`decide_route()` does: an unprovable billing verdict blocks the clone, not merely the
narration.

**The Founder's only lever here is the voucher.** `voucher_balance = 15.00` is not a
Credit Pack and is not evidence of one; per #23 it is still unclassified in kind
(it appears in the M Plan invoice table only as an order payment method). It is
recorded, not consumed, and not cleared by inference. If the Founder redeems or allows
it to expire, the guard clears on its own.

## `CLONE_KEY_REQUIRED`

`MINIMAX_CLONE_KEY` is **not set**, and there is no fallback chain — deliberately.
The resolver reads that one variable and nothing else, because `resolve_credential()`'s
chain (Subscription Key → API Key → `~/.mmx/config.json`) is right for TTS and fatal
here: inheriting it would let a machine with only a Subscription Key "resolve" a clone
credential and repeat the refused 2061 request.

Searched and confirmed absent: `~/.mmx/config.json` (holds only the `sk-cp-`
Subscription Key, `region: cn`), the repository `.env` (absent), `.private/`,
`runtime/`, `runtime-config-backups/`, `runtime-diagnostics/`, `diagnostics/`. No
`sk-api-` value exists anywhere on this host outside test fixtures.

**To provision it**, in the official CN console for this same account:

> 账户管理 → 接口密钥 → 创建新的 API Key

Recharge is **not** required to create the key, and none was performed. The key is
stored locally, like every other credential here, and never pasted into chat, a PR or
a log.

Two further checks that are not credentials but still gate the clone:

- **个人认证 / 企业认证** must be complete. Missing verification returns `2038`
  (`用户语音克隆功能被禁用`), which is a refusal *after* the upload has already
  disclosed the sample. `decide_route(account_verified=False)` refuses first.
- **`voice_id` uniqueness.** `2039 语音克隆 voice_id 重复`. `XSuperPlayFounderV1` was
  never created — the single attempt was refused before completion — so it should be
  free. If it answers 2039, that means a prior attempt *did* create it, and the
  existing voice must be inspected rather than re-cloned.

## What was deliberately not done

- No upload, no clone, no synthesis, no retry of the refused 2061 request.
- No PAYG key created, no recharge, no Credit Pack purchase.
- No voucher consumption or clearing.
- No use of the pre-existing `moss_audio_*` voice, including as a substitute test.
- No other provider, no browser-based console purchase, no undocumented endpoint
  beyond the one `/account/query_balance` dependency `BillingGuard` already declares.

The `/v1/files/upload` call did succeed once, before the 2061 refusal, and its
`file_id` was never persisted. It is **not** reusable, and this run does not pretend
otherwise: a fresh clone needs a fresh upload.

---

## 中文说明

**结论：`CLONE_KEY_REQUIRED` / `SUBSCRIPTION_ONLY_BILLING_UNPROVEN` /
`PAYMENT_ROUTE_BLOCKED` / `CROSS_KEY_CLONED_VOICE_TTS_UNKNOWN`，四重阻塞。**

**本次没有上传、没有克隆、没有合成，也没有重试此前返回 2061 的请求。**

### 新增关键事实

**复刻音色是临时音色，7 天（168 小时）后会被删除。** 官方要求在 168 小时内于任意
T2A 合成接口调用该音色，否则删除。这意味着**不能"先克隆、以后再用"**——克隆与首次合成
必须在同一次连续操作中完成，所有门禁必须事先全部打开。

**积分包不能支付 ¥9.9。** 官方原文："积分与 Token Plan 覆盖相同资源"，而 Token Plan
明确排除"快速复刻"。这比 #23 中"积分包不包含音色管理"的推断更强，是正面陈述。

### 无法自洽的计费矛盾

三条官方规则连起来是矛盾的：¥9.90 是按量计费价格；它在**首次合成**时才收取；只有
按量计费 API Key 调用才会扣账户余额；而首次合成必须使用 Subscription Key，其套餐
又明确排除快速复刻。**结论：¥9.90 只能通过按量计费合成收取，而这正是本 Issue
禁止的。** 这需要 MiniMax 针对本账号给出书面确认，不是继续检索能解决的问题。

### 需要 Founder 处理的唯一事项

1. 在官方控制台 `账户管理 → 接口密钥` 创建一个普通按量 API Key，本地设置为
   `MINIMAX_CLONE_KEY`。**不需要充值，本次没有执行任何充值。**
2. 处理 `voucher_balance = 15.00`（或等待其失效）。在该余额归零之前，
   `BillingGuard` 无法证明 TTS 只消耗套餐内额度，因此整个路由 fail closed。
3. 就"按量计费创建的音色能否用 Subscription Key 合成"和"¥9.9 首用费如何收取"
   向 MiniMax 索取**账号专属书面确认**。

密钥请只在本地配置，**不要粘贴到聊天、PR 或日志中**。