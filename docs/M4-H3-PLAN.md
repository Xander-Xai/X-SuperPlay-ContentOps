# M4 — MiniMax H3 generated shots: executable plan (Issue #22)

> Planning document. **Nothing here is implemented.** Prepared 2026-10-04, while
> PR #25 (M3 image) was open. H3 work starts only after #20 merges.
>
> Sources are cited with an access date. Where a fact could not be verified from
> an official source, it is marked `UNVERIFIED` and must not be used as evidence.

---

## 0. BLOCKER FOUND DURING PLANNING — read before writing any code

The official documentation states, verbatim:

> Note: To use MiniMax H3 or MiniMax H3 Max, please select the
> [Pay-as-you-go API](https://platform.minimax.io/docs/pricing/overview).

Source: <https://www.minimax.io/platform/document/guides_video_generation>,
accessed 2026-10-04.

H3 is documented as a **pay-as-you-go** API. This repository's standing policy,
set in M2 and reaffirmed in M3, is:

```
billing_mode: subscription
allow_payg: false
credit_pack_allowed: false
```

Those cannot both hold. H3 therefore **cannot** run through the existing
`BillingGuard` without a policy change, and a policy change is a Founder decision,
not an implementation detail.

Three options, none of which this plan may choose on its own:

| Option | What it means | Cost |
|---|---|---|
| A. Keep PAYG forbidden | H3 is not usable. #22 becomes a capability spike, not an integration. | no spend |
| B. Allow PAYG for `modality="video"` only | Subscription stays mandatory for speech and image; H3 draws on paid credit. | real money per second |
| C. H3 Max or another tier | May or may not be inside the subscription. **Untested.** | unknown |

**Required before implementation:** a Founder decision recorded as an ADR, with
the pricing page read and the cost per clip computed from the *current* page. No
code should be written against H3 before this is settled, because option B changes
the billing contract that M2's 85 tests and M3's 63 tests exist to protect.

Third-party sites advertise "9 credits per second at 768P / 14 at 2K" credit
packs. That is **UNVERIFIED** and comes from sites that are not MiniMax; it must
not be used for budgeting until read off the official pricing page.

---

## 1. Official prompt-writing guidance — VERIFIED

There is no official H3 "prompt-writing skill" repository. The authoritative
prompt guidance is the official documentation page above, and it contains exactly
three actionable rules:

1. **Camera motion tokens**: "add camera motion instructions (e.g. `[pan]`,
   `[zoom]`, `[static]`) directly after key descriptions to guide the camera work."
   The placement matters — immediately after the description they modify.
2. **Prompt length**: ≤ 7000 characters.
3. **H3-Context-IR**: the official prompt-enhancement path. It "deeply interprets
   multimodal context ... and produces a structured representation with richer
   semantic detail while preserving the user's original intent". It is
   asynchronous, **returns only an enhanced prompt and does not create a video**,
   and is identified by `task_type=h3_context_ir`, with the result in
   `content.prompt`.

Everything else offered as an "H3 prompt guide" on the web (minimaxh3.org,
minimax-h3.app, minimax-h3.com, minimax3.org, voor.ai, minimaxm.com) is a
third-party site. Their prompt formulas and credit prices are `UNVERIFIED` and
must not enter the repo as evidence.

**Source path / check date:** <https://www.minimax.io/platform/document/guides_video_generation>,
checked 2026-10-04. No upstream commit exists; this is a hosted doc.

## 2. Model specifications — VERIFIED

| Item | `MiniMax-H3` | `MiniMax-H3-Max` |
|---|---|---|
| Resolution | 768P / 2K | 480P / 768P |
| Duration | **4–15 s, integer only** | **5–15 s, integer only** |
| Aspect ratio | common ratios, or adaptive | common ratios, or adaptive |
| Modes | T2V, I2V, Reference | T2V, I2V, Reference |

This matches the duration policy already committed in M2
(`src/contentops/media/test_duration_policy.py`): H3 tests use 4 s, H3 Max tests
use 5 s. Production duration is **not** constrained by that testing policy.

## 3. Input limits — VERIFIED

| Input | Limit |
|---|---|
| Reference images | ≤ 9, each 256–5760 px, aspect 0.4–2.5 |
| Reference videos | ≤ 3, each 2–15 s, ≤ 15 s total, H.264/H.265 |
| Reference audio | ≤ 3, each 2–15 s, ≤ 15 s total, WAV/MP3 |
| Files per request | ≤ 12 total |
| Sizes | image ≤ 30 MB, video ≤ 50 MB, audio ≤ 15 MB, request ≤ 64 MB |

## 4. Modes, mapped to ContentOps names

The official API expresses every mode as one `content[]` array whose elements
carry a `type` and a `role`. The plan's five names map onto it exactly:

| Plan name | Official expression | Notes |
|---|---|---|
| T2VA | `text` only | **`ratio` is required and may not be `adaptive`** |
| I2VA | `text` + `image_url` `role=first_frame` | `ratio` always `adaptive`, set by the image |
| FL2VA | `text` + `first_frame` + `last_frame` | still Image-to-Video |
| L2VA | `text` + `last_frame` only | `mmx` documents a last frame alone as supported |
| Ref2VA | `text` + `reference_image` / `reference_video` / `reference_audio` | any combination, ≤ 12 files |

## 5. `H3PromptCompiler` (new module)

`src/contentops/media/h3_prompt.py`. Provider-generic, no vendor types in its
output.

Input: a `ShotPlan` entry — beat id, role, narration text, intended shot
description, aspect ratio, duration, and whether it is a support or evidence beat.

Output: a compiled prompt plus a `dict` of the parts, so the fingerprint can
cover the compiled form and not just the raw intent. Rules:

- emit camera motion tokens from a closed vocabulary (`[pan]`, `[zoom]`,
  `[static]`, `[tracking]`, `[orbit]`, `[push-in]`) immediately after the
  description they modify;
- describe **change over time**, since a 4 s clip is a transition, not a scene;
- state what must stay fixed as firmly as what changes, since the model
  invents detail otherwise;
- **never** request on-screen text, numbers, logos or UI. Critical text is a
  deterministic overlay, exactly as in M3;
- enforce the 7000-character limit locally, before billing;
- record `compiled_sha256` so the cache key covers what was actually sent.

## 6. ShotPlan → H3 prompt mapping

`AssetPlanner` already emits `MINIMAX_IMAGE` for support beats. For video:

- support beats → H3 is allowed;
- beats requiring evidence → H3 refused, same as generated images, raising
  `GeneratedAssetEvidenceError`;
- narration timing drives duration: the compiled duration is the shot's slot
  rounded into the model's legal integer range, **not** a fixed 4 s.

## 7. `ResolvedCredential` binding — invariant unchanged

The M3 rule applies verbatim:

```
THE CREDENTIAL AUTHORISED BY BILLINGGUARD
MUST BE
THE CREDENTIAL THE mmx CHILD ACTUALLY USES
```

One `resolve_credential()`, one `CredentialBinding`, `MINIMAX_API_KEY` in the
child environment, never `--api-key` on argv, unbound means refuse.

## 8. `BillingGuard` modality="video"

**Weekly quota only.** Video does not draw the 5-hour bucket the way speech and
image do, so `modality="video"` must require `weekly_remaining_percent > 0` and
must not require the interval window. Credential class check unchanged.

This is a change to `billing_guard.py`'s modality table and will need its own
tests; the existing speech and image cases must keep passing unchanged.

Plus an explicit weekly budget for the whole milestone, agreed before the first
generation, because each clip is billed per second and a retry is another clip.

## 9. Transport — the public documented API via the official CLI

Verified present on this host, `mmx 1.0.27`:

```
mmx video generate --model MiniMax-H3 --prompt <text>
                   [--image <path>] [--last-frame <path>]
                   [--reference-image <path>]... [--reference-video <path>]...
                   [--reference-audio <path>]...
                   --duration <4-15> --ratio <adaptive|21:9|16:9|4:3|1:1|3:4|9:16>
                   [--async|--no-wait] [--poll-interval <s>] [--download <path>]

mmx video task get --task-id <id> [--model MiniMax-H3] --output json
mmx video download --file-id <id> --out <path>
```

Underlying public API, for reference only — never called directly:
`POST /v2/video_generation`, `GET /v2/query/video_generation/{task_id}`.
The CLI is the transport; ContentOps does not hand-roll HTTP for video.

## 10. One task, one poll, one download

The rule that makes retries expensive if broken:

1. **create exactly one task**; record its `task_id` in the attempt record
   immediately, before polling;
2. **poll that same `task_id`** until a terminal state. Recommended interval 10 s.
   Terminal: `succeeded`, `failed`, `cancelled`;
3. **download that same result** from the URL the same task returned;
4. **never create a replacement because polling or downloading failed.**

Point 4 is the whole point. A failed poll is a transport problem, not a generation
problem; answering it by creating another task silently doubles the bill and
destroys the ability to explain what was paid for. A retry requires a named
reason and a changed fingerprint, exactly like M2 and M3.

## 11. `GenerationAttemptRecord` — extended, not replaced

Add `task_id` and `task_type` fields. Same rules: at most 2 attempts, attempt 2
needs a durable FAILED record from attempt 1, a named reason, and a changed
fingerprint (prompt, duration, ratio, model, first frame).

A task that is still running is **not** a failure and must never be retried.

## 12. Immutable video receipt

`<asset>.mp4.receipt.json`, same rules as M3: written once on success, never
rewritten on reuse, reuse appended to `reuse-events.jsonl`.

Fields: provider, product, plan, billing mode, credential class, transport and
version, model, `task_id`, `task_type`, compiled prompt hash, duration requested
and actual, ratio requested and actual, resolution, fingerprint, quota before and
after, technical QC, output SHA-256, attempt, retry reason, `generated=true`,
`evidence_capable=false`, `production_ready=false`,
`human_review=PENDING_FOUNDER_REVIEW`.

`generated=true` / `evidence_capable=false` are non-negotiable, same as M3.

## 13. Test durations — do not waste quota

- `MiniMax-H3` tests: **4 s**
- `MiniMax-H3-Max` tests: **5 s**
- No unnecessary long test clips. One 4 s clip proves the transport; a 15 s clip
  proves nothing extra and costs roughly four times as much.

## 14. Video technical QC

Measured facts only, in the M3 spirit — never "watchable", never "cinematic":

- container and codec (`ffprobe`), decodable end to end;
- actual duration within tolerance of the requested integer;
- actual width and height, and **aspect ratio within tolerance** — never exact
  equality, exactly as M3 learned;
- **unexpected audio-track detection**: H3 emits native stereo audio, so the
  pipeline must decide explicitly whether a silent clip or a narrated one is
  wanted, and must not silently mux narration over generated audio;
- **black-frame detection**: any frame that is essentially black;
- **freeze detection**: runs of near-identical frames, which indicate a stalled
  or failed render;
- **temporal consistency**: frame-to-frame difference distribution, so a clip that
  is one still image with a frozen time is caught.

## 15. Human review — visual *and* temporal

Fields, all null until a human fills them in:

- subject fidelity to the shot intent
- motion plausibility over time (not just frame quality)
- temporal artefacts: warping, melting faces, object drift
- reference fidelity, when Ref2VA was used
- audio: acceptable, or must be replaced
- caption-safe area across the whole clip
- consistency with the other shots in the video
- overall quality
- willingness to publish

An AI or automated observation may be recorded separately and clearly labelled as
not a review verdict, as in M3.

## 16. GENERATED_VIDEO cannot become evidence

`AssetKind.GENERATED_VIDEO` already exists and is already refused for every
claim-bearing role by `AssetRegistry`. #22 adds tests proving it for video, and
must not weaken the registry.

## 17. Zero Windows background popups

Every child process, including polling loops and downloads, goes through
`process_utils`. The policy gate scans tracked files; M3 was caught by its own
suite and fixed, so expect the same for a polling loop and fix it the same way.

## 18. Test plan for #22

`tests/test_minimax_h3.py`, no provider request in CI, fake CLI extended with
`video generate` / `video task get` / `video download`, including deliberate
failure modes:

- prompt compilation, camera tokens placed after the description they modify
- 7000-character limit enforced locally, before billing
- mode mapping: T2VA / I2VA / FL2VA / L2VA / Ref2VA, and `ratio` required and
  non-adaptive for T2VA
- input limits: ≤ 9 images, ≤ 3 videos, ≤ 3 audio, ≤ 12 files, per-clip and total
  durations, 256–5760 px, aspect 0.4–2.5
- duration validation: H3 4–15, H3 Max 5–15, integers only
- weekly-only quota rule; weekly = 0 blocks before any provider call
- credential binding with a conflicting ambient key
- one task created; polling reuses the same `task_id`
- a poll timeout does **not** create a second task
- a download failure does **not** create a second task
- `failed` / `cancelled` are terminal and recorded
- durable retry across a process boundary; identical fingerprint refused
- immutable receipt; reuse restores it
- cache validation, and a hit costs no billing and no provider call
- black frame, freeze, unexpected audio track, aspect tolerance
- secret sentinel absent from every receipt, sidecar, attempt and event
- GENERATED_VIDEO refused as evidence
- popup-free process layer

## 19. Real smoke — one clip, after everything above passes

- `MiniMax-H3`, 4 s, `9:16`, T2VA, one shot
- record 5-hour and weekly remaining and all four paid balances before and after
- report only the observed percentage delta, never a per-second price
- `production_ready=false`, `human_review=PENDING_FOUNDER_REVIEW`

## 20. Definition of done

- [ ] Founder decision on the PAYG question, recorded as an ADR
- [ ] pricing read from the official page, cost per clip computed
- [ ] `H3PromptCompiler` with tests
- [ ] `modality="video"` weekly-only rule with tests
- [ ] one-task-one-poll-one-download, proven by test
- [ ] video receipt immutable, reuse-safe
- [ ] video technical QC: black, freeze, audio track, aspect tolerance
- [ ] GENERATED_VIDEO cannot be evidence
- [ ] one real 4 s clip, receipt written, human review pending
- [ ] M2 (85) and M3 (63) suites still green
- [ ] all local gates and exact-head CI green
