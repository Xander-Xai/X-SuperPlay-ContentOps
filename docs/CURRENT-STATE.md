# Current State

[English](CURRENT-STATE.md) | [简体中文](CURRENT-STATE.zh-CN.md)

> What runs today. Verified facts only. No aspirations, no stale claims.
>
> Last verified: 2026-10-14

## Git

| Property | Value |
|---|---|
| Default branch | `main` (only persistent branch) |
| Main protection | **PROTECTED** — required status checks + PR + no force push + no deletion + linear history |
| Required checks | `Tests (ubuntu-latest)`, `Tests (windows-latest)`, `Repo policy checks` |
| Branch strategy | Issue-scoped short-lived branches, squash merge, auto-delete on merge |

## Easel Runtime

| Property | Value |
|---|---|
| Version | v0.2.1 |
| Commit | `3fe2d9904c1619281ef57f81d9ee0b7854998399` |
| Path | `.runtime/easel/` |
| Acquisition | Release archive (GitHub tarball via `gh api`) |
| Verified | 982/982 blob SHA-1 matched upstream tree |
| Re-verified | 2026-10-03 via `scripts/verify_easel_runtime.py --resolve-tag` |
| Lock file | `runtime/easel.lock.json` |
| Provenance | `runtime/easel-runtime.json` |

## Pipeline

| Property | Value |
|---|---|
| Production engine | `easel` (Easel `auto-short-video/assemble.py`) |
| Diagnostic engine | `fallback` (ffmpeg-only, never production) |
| Production voice | edge-tts via Easel `tts.py` (zh-CN-YunxiNeural) |
| Voice quality | `edge_tts_fallback` — not production-grade |
| Production ready | **false** — READY_FOR_HUMAN_REVIEW |
| Subtitle workaround | `scripts/assemble_easel.py` — strips subtitle, runs upstream, burns separately (no upstream modification) |

## Web Workbench

| Property | Value |
|---|---|
| Status | **NOT VERIFIED** |
| Doctor FAILs | 6 (fastapi, uvicorn, sse_starlette, multipart, web frontend build, .env API Key) |
| Impact | Does NOT block video pipeline (TTS + assemble use stdlib-only path) |

## MiniMax

| Property | Value |
|---|---|
| Integration | speech **IMPLEMENTED** (Issue #19), `PENDING_FOUNDER_REVIEW` |
| Image integration | **IMPLEMENTED** (Issue #20, PR #25 merged), `PENDING_FOUNDER_REVIEW` |
| Video integration | **IMPLEMENTED** (Issue #22, PR #26 merged), `PENDING_FOUNDER_REVIEW` |
| Speech transport | official MiniMax CLI `mmx`; pinned Easel path is `EASEL_MPLAN_AUTH_INCOMPATIBLE` |
| Image transport | official MiniMax CLI `mmx` |
| Video transport | **documented public API** `POST /v2/video_generation` — the CLI cannot set resolution |
| Voice cloning | **DOCUMENTED_BUT_NOT_TESTED** (Issue #23), needs a rights-cleared sample |
| Capability spike | **COMPLETE** (Issue #4, 2026-10-04) |
| PAYG allowed | **false** |
| Billing mode | subscription, **verified** |
| Speech | **VERIFIED** — `speech-2.8-hd`, 32 kHz mono WAV |
| Image | **VERIFIED** — `image-01`, 9:16 portrait, seed supported |
| H3 video T2VA | **VERIFIED** — real `MiniMax-H3` 768P 4 s task succeeded on the Subscription Key (M2.0) |
| H3 video I2VA | **VERIFIED** — real reference-image task succeeded 2026-10-05 (M4) |
| H3 Ref2VA / FL2VA / L2VA, H3-Max | **DOCUMENTED_BUT_NOT_TESTED** — implemented and fixture-tested, not exercised live |
| Credit Pack balance | `0.00` observed, re-checked before every generation |
| Balance read dependency | `UNDOCUMENTED_FIRST_PARTY_IMPLEMENTATION_DEPENDENCY`, fail closed |
| H3 duration | integer enum 4-15 (H3), 5-15 (H3 Max); test minimum 4 s / 5 s |
| Evidence | `research/providers/minimax-mplan-explore-capability.md`, `research/providers/minimax-h3-official-reality.md`, `research/providers/minimax-voice-clone-entitlement.md`, `research/providers/receipts/minimax-h3-i2va-reference-2026-10-05.sanitized.json` |

## Golden Samples

| Sample | Source | Status |
|---|---|---|
| `projects/easel-review/` | Easel v0.2.1 runtime evaluation | 1 successful build, QC PASS, awaiting human review |

## Tests

| Suite | Status |
|---|---|
| `scripts/test_basic.py` (9 tests) | All PASS |

## Known Blockers

1. Voice quality — edge-tts is mechanical, not production-grade. Primary motivation for MiniMax voice integration (M2).
2. Web workbench — 6 doctor FAILs. Does not block video pipeline.
3. Gateway healthz — upstream hardcodes port 18789; easel profile uses 37289. Does not block video pipeline.
4. Human Review — no `human-review.json` receipt for easel-review project.
5. ~~Main branch unprotected~~ — **RESOLVED** (G0.6): main is now protected via GitHub branch protection.


## M3 Image Generation (Issue #20) — VERIFIED 2026-10-04

Branch `feat/20-minimax-mplan-image`. One real provider generation was performed.

| Property | Value |
|---|---|
| Transport | official CLI `mmx 1.0.27`, `mmx image generate` |
| Model | `image-01` |
| Requested | 768x1360, seed 42 |
| **Requested extension** | `.png` |
| **Detected container** | **`JPEG`** |
| **Canonical extension** | `.jpg` (bytes preserved, no transcode) |
| Actual dimensions | 768x1360 (confirmed independently by `ffprobe`: `mjpeg`) |
| Aspect ratio | 0.564706 against 9:16 = 0.5625, within the 0.02 tolerance |
| Output SHA-256 | `fb0ee9489df856bc2cd554ab98d34fd73e0737ca733cdd0af6022342512f8e21` |
| Technical QC | PASS — luma stddev 29.97 (floor 6), span 146 (floor 24), decodable |
| `text_contamination_suspected` | `false` (edge density 0.0668, floor 0.18) |
| Billing preflight | `SAFE_INCLUDED_PLAN`, credential class `SUBSCRIPTION` |
| Quota before | 5h 99%, weekly 58% |
| Quota after | 5h 99%, weekly 58% |
| Observed delta | **0 percentage points** on both windows |
| `production_ready` | `false` |
| `human_review` | `PENDING_FOUNDER_REVIEW` |

### The container defect reproduced a second time

The provider returned **JPEG bytes from a `.png` request**, independently
reproducing what M2.0 measured. Had the pipeline trusted the extension, a JPEG
would have been stored as `.png` and handed to every downstream tool that selects
a decoder by suffix. The canonical file is `.jpg`; the receipt records the request
and the reality separately.

### Quota is reported as a delta, never as a price

The plan exposes percentages only. One image moved neither window, so the
observed delta is 0 percentage points. That is **not** a claim that an image
costs nothing, and no per-image cost is derived: MiniMax does not expose exact
units here.

### Evidence boundary

The generated asset was registered as `GENERATED_IMAGE` /
`VISUAL_SUPPORT` with `generated=true`, `evidence_capable=false`. Attempting any
claim-bearing role raises `GeneratedAssetEvidenceError` in code.

### Human review

`.verify-tmp/m3/human-review.json` carries the review fields with **every score
null**. Technical QC passing does not mean production ready.

## M4 H3 Video Generation (Issue #22) — VERIFIED 2026-10-05

Branch `feat/22-minimax-h3-video`. One real provider generation was performed, a
**reference-image** test, because M2.0 proved T2VA with no image content at all.

| Property | Value |
|---|---|
| Transport | documented public API `POST /v2/video_generation`, api schema `v2` |
| Model / mode | `MiniMax-H3`, **I2VA** (first-frame reference) |
| Requested | 4 s, `768P`, ratio `adaptive` (i2va derives the ratio from the input image) |
| Reference | `data:image/jpeg;base64`, 768x1360, 45 800 B, `role: first_frame` |
| Alignment instruction | emitted as the first line, upstream wording verbatim |
| Task created | **exactly 1**, polled to `succeeded`, downloaded once |
| Actual output | h264 / mp4, 768x1344, 24 fps, **4.458 s**, 424 543 B, decodable |
| Aspect | 0.571429 against reference 0.5647 — tolerance, not equality |
| Duration delta | 4.000 requested → 4.458 actual (0.458 s, threshold 1.0 s) |
| Audio | unrequested **AAC** present, exactly as M2.0 measured; `audio_policy=REPLACE` |
| Black / freeze | longest black run 0.0 s, longest freeze run 0.0 s, mean frame diff 0.0131 |
| Output SHA-256 | `b761ea2a69b3ad6181b8a48b93dddefb56edd897867f42a8b160610e74ac249a` |
| Billing preflight | `SAFE_INCLUDED_PLAN`, credential class `SUBSCRIPTION` |
| Quota before | weekly 58% |
| Quota after | weekly **51%** |
| Observed delta | **7 percentage points** weekly, matching the declared `7pp` budget |
| cash / Credit Pack / voucher / owed | `0.00` before **and** after |
| `production_ready` | `false` |
| `human_review` | `PENDING_FOUNDER_REVIEW` |

### The reference path was genuinely unproven

M2.0's receipt contains a single `text` item and **no image content**. So it was
silent on every part of the reference path: whether an `image_url` item is
accepted, whether `role: first_frame` is honoured, whether a `data:` URI is an
accepted URL form, whether the alignment instruction travels with a frame, and
whether I2VA renders at all on this account. The account also resolves to the
regional CN mirror rather than the host the public documentation targets, so
reference handling could plausibly differ. One 4 s call was the cheapest way to
close that gap.

### Quota is reported as a delta, never as a price

7 percentage points is an **observed** delta for one 4 s / 768P job. It is not a
price formula: no per-second, per-clip or credit rate is derived from a percentage.
It is used only to budget tests conservatively. Weekly now stands at **51%**.

### Cache reuse verified against the real artifact

A second run was served from the cache with the transport pointed at an
**unroutable host**, so any network attempt would have failed loudly:

| Property | Value |
|---|---|
| Reused | `true` |
| Provider creates | **0** |
| Provider polls | **0** |
| Billing calls | **0** |
| Original receipt overwritten | `false` |

### Evidence boundary

The shot was registered as `GENERATED_VIDEO` / `VISUAL_SUPPORT` with
`generated=true`, `evidence_capable=false`, and only **after** the immutable
receipt existed. Any claim-bearing role raises `GeneratedAssetEvidenceError`.

### Human review

`<shot>.mp4.human-review.json` carries eleven named review fields with **every
score null**. Automated measurements ride alongside, labelled as measurements.
Observed on the real clip, and recorded as observation rather than scored: the
first frame reproduces the reference faithfully; motion is present and consistent
with the requested slow push; but between the first and last frames the circular
headlamp reads as a filled disc rather than a ring, and one neon sign drifts in
position. Geometry stays coherent with no melting or warping. Whether that drift
is acceptable for a support visual is a human judgement, and it is not this
pipeline's to make.

### Still unverified

Ref2VA reference-video and reference-audio paths, FL2VA, L2VA, and MiniMax-H3-Max
(including its 5 s floor and 480P option) are implemented and fixture-tested but
have not been exercised against the live service.
## M4.5 Media convergence (Issue #27) — IMPLEMENTED 2026-10-05

Branch `feat/27-media-convergence`. **Zero provider calls.** Weekly quota untouched at 51%.

| Property | Value |
|---|---|
| Shared validator | `validate_media_asset(envelope, adapter)` — one common path, three adapters |
| Modality model | `MediaModality` (SPEECH/IMAGE/VIDEO) is **separate** from `AssetKind`; speech carries no `asset_kind` |
| Speech receipt facts | no `schema`, no `generated`/`evidence_capable`, digest in `normalized_sha256`/`raw_sha256` |
| Transform receipt | `contentops.media-transform/v1` — derived assets, source digest, original untouched |
| `AudioPolicy` | `KEEP` reuses the original (no transform); `MUTE`/`REPLACE` produce an audio-free derived asset |
| Capability registry | 10 capabilities resolved by name, no vendor word; only live-proven ones `VERIFIED` |
| Quota policy | explicit operator floors; weekly floor is a **chosen value**, not the observed 7pp delta |
| Scheduler | `ALLOW`/`REUSE_REQUIRED`/`DEFER`/`MANUAL_REQUIRED`/`BLOCKED`, priority evidence → narration → image → video |
| AssetPlanner execution | claim beats resolve only to real material, else `EVIDENCE_ASSET_REQUIRED` |
| Quality gate | `BLOCKED`/`DEGRADED_FALLBACK`/`PENDING_HUMAN_REVIEW`/`PRODUCTION_READY`/`REJECTED` |
| Manifest | `contentops.media-manifest/v1`, deterministic, no timestamp, sole asset list |
| Manifest paths | logical `project://` / `repo://`, resolved at use; absolute paths refused |
| Timeline | `assets` is the inventory, `timeline` is one active asset per placement; composition reads the timeline |
| Derived provenance | `generated` is inherited, never downgraded; `provider_generated_bytes` vs `source_generated` are separate fields |
| H3 reuse | explicit by path and validated; no filesystem discovery |
| QC receipt | `contentops.qc-canonical/v1` — sanitized at a boundary, declares `currency` and `graded_target` |
| Composition | reuses pinned Easel v0.2.1 via `assemble_easel.run`; no second compositor |
| Tests | 97 M4.5 + 85 speech + 84 image + 108 H3, all PASS |

### Two rules the implementation added beyond the plan

- a **provider generation** must declare its modality's schema; a **non-generated**
  asset must not, because nothing's API produced it
- a missing `technical_qc` **fails** a generation but is **not applicable** to an
  import or a transform — no provider ran, so there is nothing to report

### The technical integration is not a production golden

`scripts/m45_media_integration.py` produced one local artifact
(`project://final/m45.mp4`, h264 / 1080x1920 / 18.0 s, `qc_video` **WARN**) proving
`registry → manifest → compose → final QC` with **0** speech, image and video
provider calls.

| Canonical fact | Value |
|---|---|
| Output | `project://final/m45.mp4` |
| QC report | `receipts/qc-report-m45.json` — `overall: WARN`, `currency: CURRENT` |
| `production_ready` | `false` |
| `human_review` | `PENDING_FOUNDER_REVIEW` |
| Provider calls | speech 0 / image 0 / video 0 |
| Timeline | 5 placements, one active asset each |
| Inventory | 7 assets (5 active + 1 superseded + 1 narration) |

Every asset is a deterministic fixture, labelled in its receipt, in the manifest
header and in the integration report. Media binaries are gitignored; the manifest,
receipts and storyboard are committed.

**One QC report, one verdict.** `qc-report-m45.json` is the canonical M4.5 QC report
and is the only one. A second tracked report, `qc-report-final.json`, recorded
`FAIL` because it graded `final/final.mp4` — a file this stage never produces — and
sat beside the real `WARN` reading as an equally current, contradicting result. It
was stale output from an earlier invocation and has been removed.

QC receipts cross a sanitization boundary before being committed
(`contentops.qc_canonical`). `qc_video` is a runtime tool and keeps reporting local
paths, which is correct while it runs; the tracked receipt is rewritten in place as
`contentops.qc-canonical/v1` with logical references and an explicit `currency` plus
`graded_target`. So a reader can tell *what* a verdict is about and *whether it is
current* without inferring either from a filename. A regression test scans the
canonical committed artifacts for host-specific paths.

It does **not** prove real `SourceArtifact` ingestion, `Claim Ledger`
completeness, Founder approval, a production golden, or three consecutive
production builds. `production_ready=false` / `PENDING_FOUNDER_REVIEW`, and no code
path can report otherwise.

### Defects the final review caught in the committed artifacts

Four blockers found by reading the committed receipts rather than the code, all now
fixed with regression tests:

1. **One placement, two shots.** `manifest_to_storyboard` iterated
   `usable_assets()` — an *inventory*, not a timeline. `beat-05` and
   `beat-05-h3-replaced` are both gate-admissible, so both landed on placement
   `beat-05`: the pre-transform native audio played over the narration `REPLACE` was
   meant to guarantee would be the only track. The manifest now carries an explicit
   `timeline` with one `active_asset_id` per placement, and composition reads that.
2. **Generated provenance downgraded.** The derived H3 envelope said
   `asset_kind=GENERATED_VIDEO` with `generated=False`, because the transform receipt
   had overloaded one boolean for "did a provider emit these bytes" and "is this
   content generated". Now refused at construction, in both directions, derived or
   not.
3. **Machine paths in a committed manifest.** Eight `D:\Projects\...` references made
   "deterministic manifest" true on exactly one checkout root — and therefore useless
   as a cache key or review comparison. Paths are now logical.
4. **`--reuse-h3-shot` did nothing.** `main()` parsed it and passed no argument,
   while the provider separately globbed `.verify-tmp/m4`. So a clean clone produced
   fixtures and a workstation with M4 leftovers silently produced real provider
   media — both committed as "the integration". Reuse is now explicit by path and
   validated against the shot's own receipt.

And one found in the **QC receipts**, which the previous pass had not looked at
because the manifest was already clean:

5. **Two current-looking QC verdicts.** `qc-report-m45.json` (WARN, graded
   `final/m45.mp4`) and `qc-report-final.json` (FAIL, graded `final/final.mp4`, which
   nothing here creates) were tracked side by side, both carrying absolute
   `D:\Projects\...` paths. The stale report was removed and the canonical one now
   declares `currency` and `graded_target`.

### Defects the test suite caught during this milestone

Three real bugs in the new code, all found by tests rather than review:

1. `require_evidence_capable` was called unconditionally for generated image, which
   made a support visual **impossible to produce at all** — the capability is
   correctly flagged evidence-incapable, but the check belongs to the claim path
2. The asset-existence check was lost while restructuring the receipt loader, so a
   **missing asset file passed validation**
3. Duplicate `asset_id`s **silently collapsed** in the manifest, because
   `gate_states` is keyed by identifier; now refused

Plus one validation gap: a key-shaped value was only refused in a known field
list, so it could be smuggled through a new field. Now no string value anywhere in
a public receipt may match the provider-key shape.

## MiniMax Narration v2 (Issue #34) — A/B/C SAMPLE READY FOR FOUNDER LISTENING

Branch `feat/34-narration-v2-spoken-script-ab` (stacked on PR #44). Design
decision: `adr/ADR-008-native-narration-v2.md`. Receipts:
`projects/easel-enhanced-golden/review/ab-c-sample-receipt.json` and
`ab-c-sample-receipt-term-check.json`.

| Property | Value |
|---|---|
| Native text controls | paragraph newlines preserved; `<#x#>` pauses validated locally; `emotion` optional (auto-detect when absent) |
| Spoken script | `projects/easel-enhanced-golden/script/narration-spoken.json` — derivative of the locked original; original and evidence lock untouched |
| Version map | `narration-version-map.json` — SHA256 of original / spoken / synthesis (full, sample and per segment) |
| Delivery | segment-level emotion/speed, content-addressed segment cache, partial regeneration, deterministic joins |
| Billing | subscription-only resolver; M Plan gate plus before/after plan-quota and balance reads on every request; `--execute` switch; hard caps 1500 chars / 6 ASR calls |
| Sample A / B / C | 27.55 s reused excerpt (0 cost) / 30.24 s single request (newlines + pauses, auto emotion) / 28.70 s three segments (calm 0.98, auto 1.05, calm 1.00) joined with declared gaps |
| Provider usage | 5 calls, 584 billable characters; every request `M_PLAN_ONLY_VERIFIED`; 5h window 99% → 98%, all paid balances flat |
| C join exactness | 5.478 + 8.833 + 13.436 + 0.95 s gaps = 28.697 s vs 28.698 s joined |
| ASR findings | "doctor" reads correctly (term check S04); "伊泽尔" consistent; version strings read correctly — the detector's `v0.21`/`v0.2.1` mismatch remains a normalisation false positive |
| Review state | `production_ready: false`, `human_review: PENDING_FOUNDER_REVIEW`; no publish, no digital-human video |

## MiniMax Narration v3 (Issue #34) — D/E/F SAMPLE READY FOR BLIND LISTENING

Branch `feat/34-narration-v3-creator-director` (stacked on PRs #44/#45). The v2
round **failed Founder listening** (mechanical emotion/rhythm). The read-only
diagnosis is `projects/easel-enhanced-golden/review/narration-v3-diagnosis.md`;
the design decision is `adr/ADR-009-narration-v3-creator-director.md`.

| Property | Value |
|---|---|
| Creator script | `script/creator-script.json` — hook-first re-order, one declared omission, value unit, natural ending; refusals for invented numbers/facts, template language and undeclared first person |
| Director plan | `script/narration-plan.json` — per-unit intent metadata (never sent); auto emotion default; `calm` at most once; bounded homogeneous speeds; intent-paced pauses; 8 units → 4 synthesis groups |
| Version map | `script/creator-version-map.json` — fact script / creator / plan / synthesis texts |
| Candidates (blind) | `candidate-1/2/3.wav`: D clone+auto, E director controls, F preset voice; key in the receipt |
| Provider usage | 4 calls, 676 billable of the 1200 cap; all `M_PLAN_ONLY_VERIFIED`; no paid-fund movement; no re-clone/top-up/upload |
| Machine facts | same text: clone 28.74 s vs preset 22.56 s; E six intentional pauses vs D nine; technical QC approved for all three |
| Review state | `production_ready: false`, `human_review: PENDING_FOUNDER_REVIEW`; blind listening with `listening-review-v3.md` is the gate |

## Narration v3 sample video (Issue #34) — BUILT 2026-10-27, PENDING FOUNDER REVIEW

The D/E/F stage previously stopped at audio. `scripts/build_v3_sample_video.py`
now closes the narration → video gap for the existing candidates, with **zero
provider calls**.

| Property | Value |
|---|---|
| Arm rendered | E (`candidate-3.wav`, 26.585 s) |
| Unit → evidence | U01 → `shot_00` (doctor) · U03 → `shot_01` (version) · U05 → `shot_03` (ping/gateway) |
| Durations | 6.584 + 9.679 + 10.323 = 26.585 s; U01/U03 boundary from the detected silence |
| Output | `project://final/v3-sample.mp4` — h264 / 1080x1920 / aac, 26.6 s |
| Receipts | `receipts/v3-sample-video.json`, `receipts/qc-report-v3-sample.{json,md}` |
| QC | **WARN** — duration below 30 s; `real_evidence_present` is directory-local and reads 0 |
| Provider calls | speech 0 / image 0 / video 0; quota untouched |
| Review state | `production_ready: false`, `human_review: PENDING_FOUNDER_REVIEW` |

It is a three-unit excerpt, not the full eight-unit script, and the candidate
audio is gitignored, so the build is host-local by design. The full v3 narration
(4 synthesis groups, ~466 characters) is still not generated.

A second build, `projects/easel-enhanced-golden/v3-sample-motion/`, uses the same
E audio with the pinned upstream `ken-burns` zoom and clause-level captions
(9 cues instead of 3). Same QC WARN and zero provider calls. The zoom is a slow
1.0→1.08 push; at 1080x1920 nothing is cropped because the evidence screenshots
already fill the frame. Both builds remain `production_ready=false`.

## Subtitle burn timing defect — FIXED 2026-10-27

`assemble_easel._srt_to_ass` emitted ASS timestamps as `H:MM:SS.mmm`, but ASS is
`H:MM:SS.cc` (centiseconds). libass read `.584` as 584 centiseconds, so every cue
was stretched by roughly ten times: a cue ending at 6.584 s stayed on screen
until 11.84 s. `qc_video` only checks that a subtitle is *present*, so the
desynchronisation survived green runs and was found by extracting frames from a
real render.

Fixed to centiseconds, with `tests/test_subtitle_timing.py` as the regression.
**Renders produced before this commit still carry the old desync**, including the
A/B variants; they need a re-burn before any subtitle-sync claim is made about
them.

## Account DNA v2 — 2026-10-27

`config/accounts/*.json` now carries the brand base, the composition ratios, the
caption style, the cover rules and the narrative template, next to the one-click
account prompt.

| Property | Value |
|---|---|
| Schema | `contentops.account-dna/v2` — both accounts |
| Brand base | `#0F1117` charcoal, `#38BDF8` accent; `visual.accent` mirrors `brand.palette.accent`, so the accent has one owner |
| 1024 composition | 65% cropped screen-recording evidence / 30% vector animation / 5% comparison card |
| Future Intelligence composition | 70% vector animation / 25% code snapshot / 5% metric chart |
| Recording policy | 1024 `ALLOWED_CROPPED` (a recorded segment and a still crop of a real capture are the same evidence); Future Intelligence `FORBIDDEN` |
| Caption style | borderless, shadowless, `#F5F7FA` base with `#38BDF8` highlight; `burn_style` is read from the DNA by `build_account_variants.py` instead of a hardcoded constant |
| Cover | one title line, whitespace ≥ 30% |
| One-click prompts | `config/accounts/prompts/*.prompt.md` — global base merged with the account prompt, pure text, no commentary |
| Render parameters | `render` — `easel` engine on the pinned v0.2.1 runtime, 1080×1920 vertical canvas (16:9 blur derivative for Future Intelligence), Noto Sans/Serif CJK and Cascadia Mono, `speech-2.8-hd` voice, nine QC checks |
| Validator | `scripts/check_account_dna.py` — schema, palette, ratio sum, motion allow/deny lists, caption style, cover floor, recording policy, and prompt/DNA agreement |
| Tests | `tests/test_account_dna.py` |

Two things are deliberately not claimed:

- **Per-cue caption highlight is declared, not rendered.** The DNA declares
  `#38BDF8` for key terms and a `<hl>…</hl>` markup, and records
  `highlight_rendering: DECLARED_NOT_RENDERED`. The burn path applies one
  uniform style per cue, so a marked cue still renders in the base colour.
- **The rendered cards, motion segments and covers still carry the previous
  palette.** They were rendered before the dark brand base was adopted — paper
  surface `#f2f4f5`, ink `#0a1f3d`, accent `#b03a2e` (1024) and `#315d93`
  (Future Intelligence). The DNA records that as
  `brand.refresh.rendered_artifacts: PREVIOUS_PALETTE` and names the stale
  locations. The next render has to regenerate them under `brand.palette`
  before a new cut is published.

The account videos themselves were not rebuilt for this change; they keep the
captions burned from the previous style until the next build.

## Account positioning layer — 2026-10-27

The DNA now carries the strategy that `X-SuperPlay-Strategy` owns, so the
pipeline and the prompt read one set of positioning facts instead of two.

| Field | Meaning |
|---|---|
| `mission` | Brand mission shared by both accounts |
| `promise` | The internal positioning statement, verbatim from `X-SuperPlay-Strategy/02-Accounts` |
| `tagline` | The public hook; a separate field, because a positioning statement is not a slogan |
| `decision_question` | The one question a cut answers: 1024 "值不值得用", Future Intelligence "怎么才能跑起来" |
| `audience` vs `core_audience` | Reach list (who may watch) is wider than the core list (who the script is written for) |
| `audience_layers` | Names which layer the writing targets |
| `content_pillars` | Three pillars; 1024 is weighted 40 / 35 / 25, Future Intelligence is unweighted |
| `platform_roles` | Per-platform role, observed signals and CTA, taken from `Platform-Operating-Matrix` |
| `non_negotiable` | Nine rules; `forbidden` keeps the three machine-checked baselines |
| `evidence_ladder` | view < like < question < consult < paid, with a rule that a lower rung never proves a higher one |
| `business` | Source of truth is `X-SuperPlay-OPC-Blueprint`, Stage 0; content may not move the stage |
| `cadence` | 4 baseline videos/week from 1–2 source artifacts, 6–10 founder hours |
| `acceptance_metrics` | Ten measures; publish rate, founder minutes, rework and qualified signal come first |

Two reconciliations are deliberate:

- **Promise and tagline are different objects.** A positioning statement is an
  internal strategic claim; a tagline is the external hook. The Strategy text
  is the `promise`; the narrower line ("一个人，一个真实业务，一次跑给你看的实测")
  is the `tagline`, used in copy, not as the positioning.
- **Reach audience is not target audience.** The five-ish reach groups stay in
  `audience` so the topic space is honest; the three (1024) or four (Future
  Intelligence) decision groups move to `core_audience`, and only those decide
  wording and conclusions.

Content pillars, platform roles, cadence and the evidence ladder are
configuration only. They do not change the render path, and no video was
rebuilt for them.

## Evidence cut: views, hold limit and DNA captions — 2026-10-27

A placement may run as long as its narration; its picture may not. `CutPlan`
placements can now carry `shots`, and `target.max_visual_hold_ms` (2000 ms for
the 1024 cut) caps every view. An enlarged view must be contained by an earlier
context view of the same placement, so "context first, then detail" is checked
rather than described.

| Property | Value |
|---|---|
| New plan fields | `shots[]` (per view: crop, source range, semantic progress, `context_shot_id`), `max_visual_hold_ms`, `min_visual_hold_ms` |
| QC gate | `views_declared` (a static placement over the limit must declare views) and `static_hold_within_limit` (measured frozen run ≤ limit + 0.2 s); the old `freeze_is_declared` pass is removed |
| Caption style | `build_evidence_cut` reads `visual.caption_style` from the account DNA and passes it to `assemble_easel`; `_wrap` applies Chinese kinsoku so a closing mark never opens a line |
| Panel layout | recordings sit on a `brand.palette.surface` panel at their own aspect; cards map 1:1 to the frame |
| Skill-route repair | `CAP-20261028-SKILLROUTE-AUTO` re-captures the subtitle route; the 2026-10-27 capture asked `final cut subtitles burn` and did not return `auto-subtitle` |

Rebuilt `projects/easel-1024-proof`: 44.0 s, 1080×1920, h264/aac, `qc_cut`
**PASS**, longest frozen run **1.80 s**, real source **72.7 %**, generated
**0 %**, 22 views across 8 placements. `production_ready: false` and
`PENDING_HUMAN_REVIEW`; distribution stays blocked because all four captures are
`internal_review` and no redaction receipt exists yet.

Two facts are deliberately not claimed:

- **The engineering cut predates the gate.** `projects/easel-engineering-proof`
  is 62.0 s with 7–8 s single-view placements, so the tightened QC will FAIL it
  on re-run; its committed PASS receipt is stale until it is rebuilt.
- **The account DNA ratio and the V2 gate conflict.** The 1024 DNA asks for
  65 % recording / 30 % vector / 5 % card, while V2 requires real source ≥ 70 %.
  The rebuilt cut satisfies V2 (72.7 % real, 0 % vector) and therefore does not
  meet the DNA's 30 % vector share. That is a Founder decision, recorded in
  `research/video-replication/capability-reconciliation-2026-10-27.md`.

## Audio-first B-account sample (Issue #34) — 2026-10-28

`scripts/audio_first_plan.py` makes the voice the first artefact: it synthesises
each line, measures it, and only then writes the CutPlan windows.
`scripts/build_evidence_package.py` builds, grades and bundles the cut in one
command.

| Property | Value |
|---|---|
| Project | `projects/easel-fi-audio-first` — Build account, 1080×1920 |
| Length | 25.0 s (5 beats, 10 views); the account template targets 90–120 s, so this is the blueprint's 20–30 s P0 loop |
| Voice | MiniMax `speech-2.8-hd`, 5 calls, cached per line |
| Visuals | three vector cards, one static code snapshot and one metric card; zero generated media |
| QC | PASS — longest frozen run 2.40 s (limit 3.20 s), composition 70/20/10 against 70/25/5 |
| Status | `production_ready: false`, `PENDING_FOUNDER_REVIEW` |

Three gates were added for this account: `manual_recording_forbidden` (no
recording asset may appear), `composition_ratio` (declared vector/code/metric
shares within ±8 pp), and `evidence_mode: EXPLANATORY` (the ≥70 % real-source
floor does not apply; the composition gate replaces it). A shot may now name its
own asset, so one placement can move from a metric card to a vector summary;
`burns_caption` lets a diagram card keep subtitles while a citation card still
replaces them.

Not claimed: the vector cards are static, not animated; BGM is omitted by
policy; the sample is not a finished episode.

## Motion b-roll for the Build sample (Issue #34) — 2026-10-28

The Build sample no longer uses still cards. Six HyperFrames compositions render
5 s / 1080×1920 / 30 fps clips under
`projects/easel-fi-audio-first/motion/`, and `build_evidence_cut` accepts them as
`kind: motion` assets.

| Property | Value |
|---|---|
| Renderer | HyperFrames CLI `0.8.208` (Apache-2.0), `check` 0 errors, `render -q delivery` |
| Clips | `narration-bar`, `view-swap`, `arch-flow`, `code-sweep`, `metric-count`, `result-chain` |
| Treatment | 5 % grain, 1.0→1.035 camera push, focus dimming, transform/opacity only |
| Evidence role | support visual only; `evidence_capable: false`, not counted as real source or generated media |
| Sample | 25.0 s, QC PASS, longest freeze 1.60 s, composition 70/20/10 against 70/25/5 |

A motion clip's SHA is recorded in `assets.json` and again in the build receipt,
so a re-rendered clip cannot pass as the reviewed one.

## Code-animation layer: huashu-art-motion (Issue #34) — 2026-10-28

The Build account's animation layer is an external skill, not a self-built
engine. `huashu-art-motion` (MIT, commit `8a0d7d7`, SKILL 1.2.0) is installed in
the shared skill store and used through its `scripts/engine/render.py`.

| Property | Value |
|---|---|
| Engine path | `C:\Users\Administrator\.agents\skills\huashu-art-motion` |
| Windows adapter | Chrome/Edge channel fallback; run with `PYTHONUTF8=1` (the spec reader uses the default codec) |
| Interpreter | host Python, so Playwright resolves `D:\DevCaches\ms-playwright\chromium-1223` |
| Grammar used | `y1_kurzgesagt` for the two mechanism beats (three satellites in portrait) and `t2_keynote_ui` for the three supporting beats; clip duration is exact |
| Sample | `projects/easel-fi-what-is-agent/` — 45.0 s, 1080×1920, h264/aac, 12 variable beats (2.6–4.1 s) + one 4.0 s generated insert |
| Voice | MiniMax `speech-2.8-hd` with the cloned voice `founder_primary_v1`, 12 lines, 36.758 s measured; each window is speech + 0.35 s |
| Captions | SRT from measured durations, burned with the Future Intelligence DNA style |
| BGM | code-synthesised ambient bed, peak −24.4 dBFS against a −1.5 dBFS voice (22.9 dB headroom); no sample library, no provider |
| QC | `qc_video` **WARN** (pure animation: real-source ratio and real-evidence checks do not apply; no `source_refs`), duration/decode/audio/subtitle/loudness pass |
| Status | `production_ready: false`, `PENDING_FOUNDER_REVIEW`, no publishing URL |

The sample is definitional, not claim-bearing (`claim_bearing: false`). No
recording and no mouse appears. One MiniMax H3 clip is used as a silent,
claim-free bridge (4.0 s = 8.9 % of the film, below the 10 % cap); a generated
still was produced, judged to read as a near-black frame, and removed from the
cut. Both decisions and the quota delta are in `receipts/generated-media.json`.
Receipts bind the spec, clip and output SHAs; `receipts/qc-summary.json` also
binds the QC verdict to the output SHA.

## ERAS whole-film variant (Issue #34) — 2026-10-28

The explainer has a sibling cut in which **one Huashu ERAS timeline owns every
transition**, instead of concatenating twelve separately rendered clips. The
baseline `final/easel.mp4` and its receipts were not touched; the four baseline
artifacts were re-hashed after the variant build and were byte-identical.

| Property | Value |
|---|---|
| Project | `projects/easel-fi-what-is-agent` — Build account, 1080×1920 |
| Visual track | one ERAS render, `project://work/huashu-eras.mp4` — 36.300 s, 30 fps, 1089 frames, h264 |
| Timing | 29.593 s voice + 12 × 0.35 s tails + 2.5 s silent bridge = **36.293 s** |
| Transitions | `push` / `matchCut` / `blurPush` / `fadeShift` on the incoming era only, no `xfade`, no clip concat |
| Adapter | `motion/film/render.py` — read-only mount of the external engine at `/engine/` and the project at `/project/`; no upstream modification |
| Film config | `motion/film/eras.js` (clip-frame eras with explicit no-op drawers), `motion/film/index.html` |
| Voice | cloned `founder_primary_v1`, 1.20×, 12 lines, all `SAFE_INCLUDED_PLAN`, technical QC approved |
| Diagram | p02 uses the redrawn `motion/specs/diagram-workflow-vs-agent.png` (Anthropic one-source), card audit PASS |
| Output | `project://final/eras.mp4` — 36.3 s, 1080×1920, h264/aac |
| Receipts | `receipts/eras/{sample.json,timing-reconciliation.json,review-bundle.json,human-review.json,cover.json,runtime-receipt.md}` and `receipts/qc-report-eras.{json,md}` |
| Generated share | 2.5 / 36.293 = **6.89 %**, below the 10 % cap; the bridge is silent and claim-free |
| QC | `qc_video` **WARN** — same class as the baseline (pure animation, no real source); resolution, aspect, duration, codecs, audio, subtitle burn and loudness pass |
| Status | `production_ready: false`, `PENDING_FOUNDER_REVIEW` |

Three defects surfaced during this build and are recorded rather than smoothed
over:

- the ERAS table first carried the previous 43.5 s pacing; a regression test now
  binds every era duration to `motion/timeline.json`;
- the p03 source clip is 2.900 s while its window is 3.009 s, so the adapter
  pads a **contiguous tail** with the final frame and still fails on any interior
  gap;
- the engine binds `#scrub`/`#tt`/`#play` and declares fonts as relative
  `lib/fonts/*.woff`, so the project page needs those controls plus
  `<base href="/engine/">`; both are covered by tests.

`freeze_s` for the variant is 2.4 s against 0.6 s for the baseline. A PSNR
check across the bridge (t=23.0 vs t=24.2, y = 21.8 dB) shows the bridge is not
a static frame, so the number is reported as measured rather than explained away.
