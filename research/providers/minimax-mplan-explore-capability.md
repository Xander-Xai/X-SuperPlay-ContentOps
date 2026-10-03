---
title: MiniMax M Plan Explore capability verification
canonical: false
type: research
status: current
issue: "#4"
milestone: M2.0
checked_at: "2026-10-04"
translation_of: research/providers/minimax-mplan-explore-capability.md
---

# MiniMax M Plan Explore — capability verification (M2.0, Issue #4)

> Research artefact, not canonical design. Canonical truth lives in
> `docs/CURRENT-STATE.md`, `docs/adr/ADR-003-minimax-plan-provider.md` and the
> sanitized receipt in `research/providers/receipts/`.
>
> 中文： [minimax-mplan-explore-capability.zh-CN.md](minimax-mplan-explore-capability.zh-CN.md)

## Verdict summary

| Capability | Status | One-line reason |
|---|---|---|
| Authentication | `VERIFIED` | Subscription Key present and accepted; region resolved |
| Quota visibility | `VERIFIED` | Two windows readable; single `general` bucket, no modality split |
| Billing source | `VERIFIED_INCLUDED_PLAN_QUOTA` | PAYG cash, Credit Pack, voucher and owed are all `0.00` |
| Text | `VERIFIED` | Model list readable with the subscription credential |
| Image | `VERIFIED` | `image-01` delivered 768x1360 JPEG for a 9:16 request |
| Speech | `VERIFIED` | `speech-2.8-hd` delivered 32 kHz mono WAV, content ASR-checked |
| Voice design | `DOCUMENTED_BUT_NOT_TESTED` | Endpoint documented; not needed in M2.0 |
| Voice clone | `DOCUMENTED_BUT_NOT_TESTED` | Endpoint documented; not needed in M2.0 |
| H3 video | `NOT_ENTITLED` → `BLOCKED` | Official guidance requires a pay-as-you-go or credit key for H3 |
| H3 reference modes | `NOT_ENTITLED` → `BLOCKED` | Same credential rule as H3 |
| H3-Context-IR | `DOCUMENTED_BUT_NOT_TESTED` | Documented; gated behind the H3 credential block |

Two modalities are safe to build on. One is blocked by the provider's own
credential rules, not by anything we failed to try.

## What was actually verified, and how

Authority order used, highest first:

1. current M Plan overview / FAQ / usage pages, on the account's own region
2. current developer documentation (video, speech, image API references)
3. current official CLI repository, tag and skill files
4. real account output: `mmx auth status`, `mmx quota`, balance read
5. real generations, each behind a fail-closed billing pre-flight

Stale Token Plan Plus / Max / Ultra naming was discarded. M Plan replaced it:
Go, Explore, Build.

### Transport

| Property | Value |
|---|---|
| Official CLI | `mmx`, npm package `mmx-cli` |
| Version verified | `1.0.27`, tag `v1.0.27`, published 2026-09-29 |
| Repo `main` at check | `06e47c70b76f419196678367dae62acca4c94076`, 2026-09-29 |
| Install | `npm install -g mmx-cli` |
| Runtime | Node.js 18+ (host has 24.16.0) |
| Region in use | `cn` (mainland China platform) |
| Windows | supported, verified on this host |
| Structured output | `--output json` |
| Async video | documented (`--async`), blocked by entitlement |

A stale `mmx` launcher shim existed on this host with the package directory
missing; `npm ls -g` did not list the package. The CLI was reinstalled before
any verification so that every observation below comes from `1.0.27`.

### Authentication

```
subscription_credential_present: true
credential_class: SUBSCRIPTION
auth_method: api_key stored in the official CLI config
auth_status: VERIFIED
```

No key value, fragment, or account identifier appears in this document or in the
receipt. Classification is derived from the key prefix family only.

### Quota and billing semantics

Two windows, both starting at first use:

| Window | Applies to | Observed remaining |
|---|---|---|
| 5-hour | non-video models | 99% |
| Weekly | all models including video | 65% |

Only one bucket is exposed, named `general`. Absolute counts are not exposed,
and there is no per-modality breakdown, so ContentOps cannot compute "how many
images are left". It can only answer "is there remaining plan usage", which is
the question the pre-flight actually needs.

Video is documented as subject to the weekly window only.

### Billing pre-flight — the hard gate

The risk that had to be excluded is not pay-as-you-go. It is Credit Pack.

Current official documentation states that a Subscription Key draws on included
plan usage **and** Credit Packs, that plan usage is consumed first, and that once
the limit is reached overspend is deducted from Credit Packs **by default**, with
no documented switch to disable that fallback. So "I used a Subscription Key" is
not proof of subscription-only billing.

The only provable exclusion is a zero Credit Pack balance. Measured:

| Field | Value |
|---|---|
| pay-as-you-go cash balance | `0.00` |
| Credit Pack balance | `0.00` |
| voucher balance | `0.00` |
| outstanding owed | `0.00` |

Verdict: `VERIFIED_INCLUDED_PLAN_QUOTA`. Pay-as-you-go cannot be charged, and
Credit Pack cannot be drawn on, so a generation at this moment provably consumes
included plan usage.

Two caveats that are load-bearing:

- The balance read uses a first-party endpoint that the official CLI itself
  calls, but which is not listed in the public documentation index. It is not a
  reverse-engineered web endpoint. Treat it as an implementation detail that
  could change.
- Therefore the pre-flight must run **before every single generation**, and it
  fails closed. If the balance cannot be read, or any of the four fields is
  non-zero, the verdict is `BLOCKED_BILLING_SOURCE_UNCERTAIN` and no request is
  sent. A one-time check is not sufficient evidence.

## Tested results

### Speech

| Property | Chinese sample | English sample |
|---|---|---|
| Model | `speech-2.8-hd` | `speech-2.8-hd` |
| Voice | `Chinese (Mandarin)_Reliable_Executive` | `English_expressive_narrator` |
| Container / codec | WAV / `pcm_s16le` | WAV / `pcm_s16le` |
| Sample rate | 32000 Hz | 32000 Hz |
| Channels | 1 | 1 |
| Duration | 5.503 s | 6.223 s |
| Peak | -1.5 dB | -0.5 dB |
| Mean | -20.0 dB | -15.1 dB |

303 voice IDs are listed, including a large Chinese (Mandarin) set. Sync TTS
accepts under 10000 characters; async long-form TTS is documented separately.

**Peak level is the first quality finding.** -0.5 dB is valid, not clipping, but
it leaves effectively no headroom. A loudness normalisation gate is mandatory
before compose.

### Pronunciation — the second quality finding

Technical vocabulary sample, three variants, identical text, ASR backcheck after
each. ASR is used as a cheap detector, not as a quality verdict.

| Variant | Mechanism | Duration | Result |
|---|---|---|---|
| A | no rules | 17.41 s | `Claude` read as "Cloud", `Qwen` as "Quen", `H3` as "H-three", `v0.2.1` collapsed to "V0.21" |
| B | `pronunciation_dict` with IPA | 24.58 s (+41%) | compound names split apart: `Claude Code` lost a word, `GitHub` became two tokens, `LangGraph` became two tokens, `H3` read as "A Three" |
| C | `pronunciation_dict` with plain-text expansion + text normalisation | 18.39 s (+6%) | every sampled token correct, including `v0.2.1` and the date |

Conclusions, in order of confidence:

1. `pronunciation_dict.tone[]` is the current supported mechanism, format
   `source/replacement`. There is **no SSML**. Do not invent SSML.
2. For brand names and mixed-script technical tokens, **plain-text expansion
   works and IPA actively hurts**. Variant B got worse than doing nothing.
3. The failure mode without any lexicon is specific and predictable: hyphenated
   and CamelCase tokens are split into separate words.
4. ASR backcheck is necessary but not sufficient. It agreed with the obvious wins
   and losses, and it cannot judge naturalness, pace or emotion. Human listening
   review remains mandatory and is currently `PENDING_FOUNDER_REVIEW`.

The contentOps shape that follows: keep the display text and the spoken text
separate, and maintain a `PronunciationLexicon` of token → spoken form, emitted as
plain-text `pronunciation_dict` entries per language. That is a M2 design item,
deliberately not built during M2.0.

### Image

| Property | Value |
|---|---|
| Model | `image-01` (also `image-01-live` documented) |
| Requested | 768x1360, 9:16 portrait, seed 42 |
| Delivered | 768x1360, container **JPEG**, codec `mjpeg` |
| SHA-256 | `27f8f3d9…f062bf1` |
| Visual QC | valid, non-blank, no text, no logo, no UI, no artifacts, clean caption-safe space top and bottom, slight softness |

**Third finding, and the one most likely to cause a silent production bug:** the
provider chose the output container itself. A `.png` path received JPEG bytes.
Any consumer that picks a decoder from the filename will fail on a perfectly
valid asset. ContentOps must sniff the container from the bytes, and its image
quality gate must assert the container rather than trust the extension.

`--seed` is supported, which gives idempotency a real anchor.

## H3 video — blocked by the provider's own credential rule

Two current official sources state that H3 requires a pay-as-you-go or credit key:

- the Video Generation guide, on both regions: "To use MiniMax H3 or MiniMax H3
  Max, please select the Pay-as-you-go API"
- the official CLI's own H3 skill at tag `v1.0.27`: "Use a standard
  Pay-as-you-go/Credit API Key for H3. Do not use an OAuth credential or Token
  Plan Subscription Key for H3", with the failure handling rule: "If error `2013`
  says TokenPlan or Credit does not support H3, stop"

One current official page disagrees: the M Plan FAQ states that Explore and Build
include the H3 video model.

The coherent reading is that plan entitlement to H3 is delivered through
in-app MiniMax Code sign-in, while the **programmatic CLI and API path for H3
requires a pay-as-you-go or credit key**. Under `allow_payg: false` and
`allow_credit_pack_fallback: false`, H3 is therefore not available to this
repository.

Status: `NOT_ENTITLED`, verdict `BLOCKED`, **no generation was sent and no quota
was spent**.

This was resolved by reading current official sources, not by spending quota to
find out. The remaining risk is asymmetric and was accepted deliberately: if the
restrictive reading were wrong, a single 4-second 768P job would have been spent
to learn it. That is not worth it next to a documented rule that says stop.

Documented H3 capability, recorded so that M4 is ready the moment entitlement is
resolved by a human:

| Property | Value |
|---|---|
| Models | `MiniMax-H3`, `MiniMax-H3-Max` |
| Modes | text-to-video; image-to-video with first and/or last frame; multimodal reference generation |
| Reference inputs | up to 9 images, 3 videos, 3 audio clips, 12 files mixed total |
| Resolution | 768P / 2K (H3); 480P / 768P (H3 Max) |
| Duration | 4-15 s integer (H3); 5-15 s integer (H3 Max) |
| Ratios | adaptive, 21:9, 16:9, 4:3, 1:1, 3:4, 9:16 |
| Prompt limit | 7000 characters |
| Body limit | 64 MB |
| Workflow | create task → poll → download, fully asynchronous |
| Also documented | H3-Context-IR prompt enhancement, 768P → 2K regeneration |

## Current official H3 prompt guidance

Read at execution time from the official CLI repository, summarised here, **not
vendored**.

| Field | Value |
|---|---|
| Repository | `MiniMax-AI/cli` |
| Skill path | `skill/h3-video/SKILL.md` |
| Reference | `skill/h3-video/references/h3-video.md` |
| Tag / date | `v1.0.27`, 2026-09-29 |
| `main` sha | `06e47c70b76f419196678367dae62acca4c94076` |
| Secondary source | official H3 feature-highlights gallery page in the platform docs |

Substantive guidance that a prompt compiler must honour:

1. Expand an underspecified request in a fixed order: output goal, subjects and
   assets, timeline, scene, camera, look, sound, constraints.
2. Use a **two-level timeline**: a master range per reference, then micro-ranges
   inside each shot — establish, preparation, core action, settle, hold.
3. Ranges must be contiguous, never overlapping, and the final end time must
   equal the requested duration.
4. Maintain a **state ledger** at every boundary and make shot N's locked end
   state exactly equal shot N+1's initial state.
5. Keep actions physically achievable inside 4-15 s; one clear action beat per
   shot; reallocate time by action complexity rather than splitting evenly.
6. Use explicit camera language, and explicit "preserve / may change" statements.
7. State hard continuity constraints separately from aesthetic preferences, and
   repeat a critical invariant inside the timeline block where it matters.
8. Never silently add brands, dialogue, text overlays or unsafe content.
9. Default 0.5 s precision; use finer timing only for a short precise transition.
10. A complete structured storyboard supplied by the user must be kept intact,
    not condensed or replaced by a generic prompt.

Failure-handling rules worth adopting now, because they are about money: once a
task id exists, all recovery must act on that task id; a replacement paid task is
never created because polling, terminal handling or download failed; download
failure retries the same URL rather than regenerating.

## Easel reuse assessment

Checked before recommending any implementation, at execution time.

| Question | Answer |
|---|---|
| Pinned version | `v0.2.1`, commit `3fe2d99` |
| Latest stable release | still `v0.2.1`, published 2026-09-24 — no newer release |
| Upstream `main` | `d80b26c`, 2026-10-03, 78 commits ahead |
| Upstream modified | no, and none planned |

| Capability | Classification |
|---|---|
| MiniMax TTS / speech | `UPSTREAM_AVAILABLE_IN_PIN` |
| MiniMax voice cloning | `UPSTREAM_AVAILABLE_IN_PIN` |
| MiniMax image | `UPSTREAM_AVAILABLE_IN_PIN`, provider list to confirm in M3 |
| MiniMax H3 video | `NOT_AVAILABLE` |

The pinned Easel already ships a MiniMax voice path:
`skills/shared/scripts/multivoice.py` accepts `--provider minimax`,
`skills/shared/scripts/voice_clone.py` accepts `--provider minimax`, and
`skills/shared/scripts/model_registry.py` already registers a `minimax` voice
provider with `MINIMAX_API_KEY`, `MINIMAX_GROUP_ID`, `MINIMAX_MODEL` and
`MINIMAX_BASE_URL`. Easel's `ai_video.py` contains no MiniMax reference at all.

**Decision: reuse pinned upstream for speech.** Do not build a second MiniMax
TTS client. ContentOps owns the layers upstream does not have: subscription-only
credential handling, the billing pre-flight, the sanitized receipt, the
pronunciation lexicon, loudness and ASR QC, idempotency, and the no-popup
subprocess contract.

One concrete compatibility risk for M2: Easel's MiniMax path is written against
`MINIMAX_API_KEY` plus `MINIMAX_GROUP_ID`, which is the older credential shape.
Whether it accepts an `sk-cp-` Subscription Key is **unverified** and is the
first thing M2 must test. If it does not, the fallback is a thin ContentOps
adapter over the official `mmx` CLI, not a fork.

## Implementation recommendation

| Milestone | Decision |
|---|---|
| M2 speech | Proceed. Adapt pinned Easel MiniMax TTS; add pre-flight, lexicon, QC, receipt, idempotency |
| M3 image | Proceed. ContentOps provider adapter over the official CLI; Easel has no MiniMax image provider |
| M4 H3 video | Do not start. `BLOCKED` on entitlement; prepare the design, write no code |
| Legacy Hailuo video | Not investigated, not required |

Quality gates that follow directly from the findings above:

- speech technical: valid container, duration, sample rate, clipping, silence,
  **loudness normalisation** because the provider peaks near 0 dB
- speech semantic: full script coverage, numbers, proper nouns, terminology,
  ASR backcheck as a detector
- speech human: naturalness, pace, emotion, pronunciation — mandatory, not optional
- image technical: **sniffed** container, decoded dimensions, aspect ratio
- image semantic: requested subject present, no fabricated facts, no stray text
- video: not applicable while blocked

Idempotency anchors that are real rather than aspirational: speech from
model + voice + text + lexicon version; image from model + prompt + seed +
dimensions; video from model + mode + prompt + reference hashes.

Retry budget: at most 2 attempts per asset, and a second attempt only with a
named failure reason and a changed input.

## Unknowns

| Unknown | Why it matters | How to close it |
|---|---|---|
| Does Easel's MiniMax TTS accept an `sk-cp-` Subscription Key? | Decides adapt-vs-adapter for M2 | One test in M2 against pinned Easel |
| Exact per-modality quota cost of speech and image | Retry budget needs a real number | Observe quota delta across controlled generations |
| Is H3 reachable from a Subscription Key at all? | Only route to M4 | Founder decision, or MiniMax confirmation |
| Naturalness / pace / emotion of the voice | Cannot be automated | Founder listening review |
| Whether image output is byte-stable for a fixed seed | Affects idempotency strength | Regenerate once and compare hashes |

## What was deliberately not done

- No H3 generation was sent, so no quota was spent on an unresolved question.
- No pay-as-you-go key was requested, created or used.
- No key value, fragment, account id, task id or private endpoint was written to
  this repository.
- No provider integration code was written. M2.0 produced evidence and a
  decision, not a provider.