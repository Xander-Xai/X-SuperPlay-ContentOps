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
| H3 video | `VERIFIED` | Real `MiniMax-H3` task created and succeeded on a Subscription Key |
| H3 reference modes | `DOCUMENTED_BUT_NOT_TESTED` | Documented and reachable by the same credential; not exercised |
| H3-Context-IR | `DOCUMENTED_BUT_NOT_TESTED` | Documented; not exercised |

All three generation modalities are now `VERIFIED` under the subscription. That
includes video, which an earlier revision of this document had recorded as
`NOT_ENTITLED` — see the H3 section for why that claim was too strong and how it
was corrected.

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
| Async video | verified in practice: create → poll → download |
| Documented public API | used for video, because the CLI cannot set resolution |

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
included plan usage. Video later confirmed this end to end: plan quota fell and
all four paid balances stayed at zero.

### The balance read is an undocumented dependency

The four balance fields come from a path this repository does carry as a literal:
the account balance endpoint under the API base. Classifying it honestly:

```
UNDOCUMENTED_FIRST_PARTY_IMPLEMENTATION_DEPENDENCY
```

| Property | Value |
|---|---|
| First-party | yes, MiniMax's own API surface |
| Used by the official CLI | yes, `mmx-cli` calls it for the same purpose |
| Listed in public API documentation | **no** |
| May change without notice | yes |
| Scope | research use only unless separately accepted for production |
| Behaviour on failure | fail closed |

It is a dependency and it is in the repository, so describing it as "no endpoint
literal exists" would be false. It is justified only by being the sole way found
to observe the Credit Pack balance, which is what makes subscription-only billing
provable at all. Every failure mode is a hard block: transport error, schema
change or missing field. An unreadable balance is never treated as zero.

Production use, if it is ever accepted, must be encapsulated behind a single
`BillingGuard` with contract tests on sanitized fixtures and a documented
migration path for the day MiniMax publishes an official equivalent. It must not
be scattered through provider code, and it must not quietly become the permanent
production contract.

Two further caveats that are load-bearing:

- The pre-flight must run **before every single generation**, and it fails
  closed. If the balance cannot be read, or any of the four fields is non-zero,
  the verdict is `BLOCKED_BILLING_SOURCE_UNCERTAIN` and no request is sent. A
  one-time check is not sufficient evidence.

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

## H3 video — VERIFIED on the real account

This section replaces an earlier claim that H3 was `NOT_ENTITLED`. That claim was
too strong, and the correction is worth recording rather than quietly editing
away.

### The documentation conflict was real

Two current official sources contradicted each other:

| Source | Region | Product named | Statement |
|---|---|---|---|
| M Plan overview | global and CN | **M Plan** | Explore and Build include H3; the model is selected in the API request or tool configuration |
| Video Generation guide | global and CN | not specified | "To use MiniMax H3 or MiniMax H3 Max, please select the Pay-as-you-go API" |
| Official CLI H3 skill, tag `v1.0.27` | n/a | **Token Plan** | "Do not use an OAuth credential or Token Plan Subscription Key for H3"; failure rule: "If error `2013` says TokenPlan or Credit does not support H3, stop" |

Re-verified 2026-10-04. The CN M Plan overview still reads
`视频模型 | 不可用 | 可用 H3 | 可用 H3`.

The decisive detail is the product name. The CLI skill's prohibition is written
against **Token Plan**, and it names the `2013` error class explicitly. M Plan
replaced Token Plan, and the M Plan pages are the newer authority for what a
current subscription includes. Treating a Token Plan-era restriction as proof
that an M Plan subscription lacks the model was an inference, not evidence.

Before the account test the honest status was therefore `BLOCKED` with reason
`OFFICIAL_DOC_CONFLICT` — not `NOT_ENTITLED`, which would have asserted a fact
nobody had checked.

### What the account actually did

One authorised create request, no automatic retry:

| Field | Value |
|---|---|
| Model | `MiniMax-H3` |
| Mode | text-to-video (T2VA) |
| Requested | 4 s, `768P`, `9:16` |
| Task created | **yes**, HTTP 200, no error body |
| Task reference | salted hash prefix `082bb142725f` (raw id not recorded) |
| Poll outcome | `running` ×6 → `succeeded` |
| Downloaded | yes, 231,770 bytes |
| SHA-256 | `37749196a11a5e5d9e0e52ad5e95abdc93ea91cd691db8fa43f213839404d7ea` |

Delivered properties from `ffprobe`:

| Property | Value |
|---|---|
| Video codec | `h264`, 768x1344, 24 fps, 107 frames |
| Duration | 4.458 s for a 4 s request |
| Audio codec | `aac`, present although no audio was requested |
| Aspect ratio | 0.5714 delivered versus 0.5625 requested for 9:16 |

Three operational findings:

1. **The Subscription Key is accepted for H3.** The official CLI skill's
   prohibition does not apply to M Plan. Anyone following that skill literally
   would have wrongly concluded video was unavailable.
2. **The official CLI cannot request 768P.** `mmx video generate` exposes no
   resolution flag, and passing `--resolution 768P` is silently dropped: a
   `--dry-run` showed the outgoing payload still carrying `"resolution": "2K"`.
   Silent flag-dropping is itself a hazard for a paid API. The 768P smoke
   therefore used the **documented public API** `POST /v2/video_generation`, which
   is the sanctioned transport for a capability gap.
3. **Delivered dimensions are approximate.** 9:16 was requested and 768x1344 was
   delivered. Any composition gate must assert tolerance, not exact ratio.

### Billing proof for video

This is the strongest billing evidence in the whole audit, because the generation
actually succeeded:

| Field | Before | After |
|---|---|---|
| 5-hour window remaining | 99% | 99% |
| Weekly window remaining | **65%** | **58%** |
| PAYG cash balance | `0.00` | `0.00` |
| Credit Pack balance | `0.00` | `0.00` |
| Voucher balance | `0.00` | `0.00` |
| Outstanding owed | `0.00` | `0.00` |

Plan quota fell by 7 weekly percentage points and every paid balance stayed at
zero. Video generation under M Plan Explore consumes **included plan entitlement
only**. `allow_payg: false` and `allow_credit_pack_fallback: false` both held.

Video is subject only to the weekly window, which matches the observed movement:
the 5-hour window did not move at all.

### Video technical QC

- valid decodable file, no black frames, no freeze, no silence detected
- audio present but effectively ambient: mean −47.2 dB, peak −32.9 dB
- visual frame review: candle flame close-up exactly as prompted, no text, no
  logo, no visible artifacts, portrait with clean upper-half caption space

Documented H3 capability, retained for M4 design:

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

Only text-to-video was exercised. Reference-image, reference-video,
reference-audio, first/last-frame and H3-Context-IR remain
`DOCUMENTED_BUT_NOT_TESTED`; they are reachable by the same credential but each
costs weekly quota, so they wait for M4 with an explicit budget.

## Current official H3 prompt guidance

Read at execution time from the official MiniMax repositories, summarised here,
**not vendored**.

| Field | Value |
|---|---|
| Repository | `MiniMax-AI/MiniMax-H3` |
| Skill path | `skills/h3-prompt-writing/SKILL.md` |
| Repo `main` sha | `d21241f0a4b3acbb34c97dae47fa417b7065e438`, 2026-08-15 |
| Last commit touching the skill | `a107547fa669c509b8e6363fe18378d46ab3066c`, 2026-08-11 |
| Checked at | 2026-10-04 |
| Secondary source | `MiniMax-AI/cli` tag `v1.0.27`, `skill/h3-video/` |
| Tertiary source | official H3 feature-highlights gallery page in the platform docs |

This is the current official H3 **prompt-writing** skill, and it defines five
input modes with distinct contracts:

| Mode | Contract |
|---|---|
| `T2VA` | build the full audiovisual timeline from text |
| `I2VA` | start from the first frame and develop forward from it |
| `FL2VA` | describe the continuous path between first and last frames |
| `L2VA` | infer a plausible opening and converge to the supplied last frame |
| `Ref2VA` | full-reference rewrite in six labelled sections |

Base modes (`T2VA`, `I2VA`, `FL2VA`, `L2VA`) use the ordered fields
`integrated_multimodal_description`, `overall_soundscape`, `non_diegetic_music`.
`Ref2VA` uses `subject_definitions`, `summary`, `retention_analysis`,
`detailed_description`, `overall_soundscape`, `non_diegetic_music`.

Output rules that a future `H3PromptCompiler` must honour:

1. Rewrite sections are written in English; dialogue, lyrics and visible scene
   text keep their original language.
2. Each shot is described by composition, subjects, environment, actions, camera,
   sound, and the exact point where referenced content appears.
3. No plot summaries, no unresolved reference labels, and no timing that does not
   match the requested duration.
4. Reference labels stay consistent across every section, for example
   `<Picture 1>`, `<Video 1>`, `<Audio 1>`.
5. Concrete visual and audio detail beats abstract words such as "cinematic".
6. Keyframe modes must state how the first or last frame connects to the timeline.
7. Total described duration always matches the requested length, 4-15 s.

The CLI's own H3 skill adds timeline mechanics that the prompt-writing skill does
not cover: a two-level timeline, contiguous non-overlapping ranges whose final end
equals the requested duration, a state ledger at every boundary where shot N's
locked end state equals shot N+1's initial state, and hard continuity constraints
kept separate from aesthetic preferences.

Failure-handling rules from the CLI skill, adopted because they are about money:
once a task id exists, all recovery must act on that task id; a replacement paid
task is never created because polling, terminal handling or download failed;
download failure retries the same URL rather than regenerating.

No `H3PromptCompiler` is implemented in M2.0.

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
| M4 H3 video | Proceed, scheduled **after** M2 and M3. Video is verified, but it is the most expensive modality in the plan and consumes weekly quota |
| Legacy Hailuo video | Not investigated, not required |

Quality gates that follow directly from the findings above:

- speech technical: valid container, duration, sample rate, clipping, silence,
  **loudness normalisation** because the provider peaks near 0 dB
- speech semantic: full script coverage, numbers, proper nouns, terminology,
  ASR backcheck as a detector
- speech human: naturalness, pace, emotion, pronunciation — mandatory, not optional
- image technical: **sniffed** container, decoded dimensions, aspect ratio
- image semantic: requested subject present, no fabricated facts, no stray text
- video technical: decodability, duration, codec, resolution, fps, black and
  freeze detection, and **aspect ratio within tolerance** because 9:16 was
  requested and 768x1344 delivered
- video content: no fabricated evidence, and never used to imitate a real UI,
  screenshot, test result or customer proof

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
| Per-call weekly cost of H3 | Video retry budget | One 4 s 768P job cost 7 weekly percentage points |
| Reference-image / reference-video / reference-audio H3 modes | M4 mode coverage | Each costs weekly quota; test inside M4 with a budget |
| Naturalness / pace / emotion of the voice | Cannot be automated | Founder listening review |
| Whether image output is byte-stable for a fixed seed | Affects idempotency strength | Regenerate once and compare hashes |

## H3 role in the final video

H3 is a **high-value short generated insert**, never the backbone of the video
and never a source of evidence.

Good uses: hook visual, hero shot, concept visualisation, visual metaphor,
transition, a scene that cannot be recorded.

Forbidden uses: any imitation of a real interface, dashboard, screenshot, test
result, analytics view, product demo, customer proof or source code output. Real
evidence stays real, and a generated asset must never be registered as evidence.

## What was deliberately not done

- Exactly **one** H3 task was created. No second task, no blind retry, no
  alternate-credential attempt, no alternate-region retry.
- No pay-as-you-go key was requested, created or used, and no Credit Pack was
  bought.
- Only text-to-video was exercised. Reference and keyframe modes wait for M4 with
  an explicit weekly-quota budget.
- No key value, fragment, account id or raw task id was written to this
  repository; the task reference is a salted hash prefix.
- No provider integration code was written. M2.0 produced evidence and a
  decision, not a provider.