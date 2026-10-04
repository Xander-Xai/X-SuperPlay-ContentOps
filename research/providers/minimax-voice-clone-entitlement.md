---
title: MiniMax M Plan voice cloning entitlement
canonical: false
type: research
status: current
issue: "#23"
checked_at: "2026-10-04"
translation_of: research/providers/minimax-voice-clone-entitlement.md
---

# MiniMax M Plan voice cloning entitlement (Issue #23)

> Research artefact, not canonical design. Canonical capability status lives in
> `docs/MEDIA-PROVIDER-CONTRACT.md` and `docs/CURRENT-STATE.md`.
>
> 中文： [minimax-voice-clone-entitlement.zh-CN.md](minimax-voice-clone-entitlement.zh-CN.md)

## Result

```
DOCUMENTED_BUT_NOT_TESTED
```

No clone was attempted. Two blockers stand in the way, and neither can be cleared
by an agent: the account's real-name verification state is unknown, and no
rights-cleared human voice sample exists in this repository.

## What the current official sources say

Re-checked 2026-10-04 on the account's own region.

| Question | Answer | Source |
|---|---|---|
| Is there a programmatic voice-clone API? | Yes, `POST /v1/voice_clone` | current voice-clone API reference |
| Does it need the legacy `GroupId`? | **No.** The current schema has no `GroupId` parameter | same |
| Does the official CLI expose it? | **No.** `mmx speech` offers `synthesize`, `generate`, `transcribe`, `recognize`, `voices` only | `mmx speech --help`, v1.0.27 |
| Is it named in the M Plan tier wording? | **No.** Tiers promise "image and audio generation"; cloning is voice management, not stated | current M Plan FAQ, both regions |
| Is there an entitlement error code? | Yes: **`2038` 无复刻权限，请检查账号认证状态** ("no cloning permission, check account verification status") | voice-clone API reference |
| Is a separate charge documented? | The optional **preview** is billed as T2A at normal T2A pricing. The clone call itself carries no documented separate charge | same |
| Is real-name verification required first? | **Yes.** "调用本接口前，请先完成个人或企业认证" | same |
| Does the clone expire? | Yes, deleted if not formally used within **7 days** | same |

### Speech entitlement is not clone entitlement

M2.0 established that speech synthesis is covered. The M Plan pages promise "image
and audio generation". They do not mention voice cloning anywhere, and the API
defines a distinct entitlement error for it. Assuming speech coverage implies clone
coverage is exactly the inference this repository refuses to make, so the status
stays unproven rather than assumed either way.

## Why no clone was attempted

### Blocker 1 — no rights-cleared voice sample

Cloning requires a recording of a real person's voice. The only audio tracked in
this repository is **synthetic TTS output** of the project's own script
(`projects/easel-review/assets/voice_easel/narration.mp3` and the per-shot files).
Cloning a synthetic voice would be a poor technical test and would have no
rights basis, so it was not attempted.

The prohibition is absolute in this repository: no celebrity, creator, podcaster,
public figure or unknown-dataset speaker.

**Founder action required.** A rights-cleared sample meeting the current official
specification:

| Requirement | Value |
|---|---|
| Formats | `mp3`, `m4a`, `wav` |
| Duration | **at least 10 s**, at most 5 min |
| Size | at most 20 MB |
| Speakers | one speaker only |
| Conditions | clean recording, no music, no overlapping speech |
| Optional prompt clip | under 8 s, with its exact transcript as `prompt_text` |
| Optional ASR check | `text_validation` up to 200 chars, `accuracy` default 0.7 |

`need_noise_reduction` and `need_volume_normalization` exist but default to false,
so a clean recording avoids depending on them.

### Blocker 2 — unknown verification state

The API requires personal or enterprise verification before the first call, and
returns `2038` when it is missing. Whether this account is verified cannot be
established without making the call, and making the call is exactly what is being
held back.

## If a test is later authorised

1. Confirm `MINIMAX_SUBSCRIPTION_KEY` class is `SUBSCRIPTION`.
2. Run the billing pre-flight: PAYG cash, Credit Pack, voucher and owed all zero,
   weekly plan usage readable and remaining. Any non-zero or unreadable field
   means `BLOCKED_BILLING_SOURCE_UNCERTAIN` and no request.
3. Upload the sample, then create **one** clone. No automatic retry.
4. Record: quota before and after, clone status and `base_resp.status_code`,
   model compatibility, the new `voice_id` as a **salted hash only**, and the
   output hash. Never the raw sample, the raw `voice_id`, or private identity data.
5. Optionally synthesise **one** short sentence with the cloned voice to prove the
   `voice_id` is usable, subject to the same gate.
6. A `2038` on a verified account would make this `NOT_ENTITLED`. A successful
   clone on a Subscription Key with all balances still zero would make it
   `VERIFIED`, and would additionally prove the clone path consumes included plan
   entitlement.

## Transport implication

Voice cloning would need the **documented public API**, because the official CLI
has no clone command. That is consistent with the transport priority already in
force: official CLI first, documented public API for a capability gap, never an
undocumented endpoint. The undocumented balance read would still come only from
`BillingGuard`.