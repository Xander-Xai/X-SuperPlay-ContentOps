# Current State

[English](CURRENT-STATE.md) | [简体中文](CURRENT-STATE.zh-CN.md)

> What runs today. Verified facts only. No aspirations, no stale claims.
>
> Last verified: 2026-10-04

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
| Image integration | **IMPLEMENTED** (Issue #20, PR #25), `PENDING_FOUNDER_REVIEW` |
| Video integration | **IMPLEMENTED** (Issue #22, PR open), `PENDING_FOUNDER_REVIEW` |
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
