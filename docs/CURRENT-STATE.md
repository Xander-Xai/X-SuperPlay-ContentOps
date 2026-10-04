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
| Image / video integration | **NOT_IMPLEMENTED** (Issues #20, #22) |
| Speech transport | official MiniMax CLI `mmx`; pinned Easel path is `EASEL_MPLAN_AUTH_INCOMPATIBLE` |
| Voice cloning | **DOCUMENTED_BUT_NOT_TESTED** (Issue #23), needs a rights-cleared sample |
| Capability spike | **COMPLETE** (Issue #4, 2026-10-04) |
| PAYG allowed | **false** |
| Billing mode | subscription, **verified** |
| Transport | official MiniMax CLI `mmx` (`mmx-cli` v1.0.27) |
| Speech | **VERIFIED** — `speech-2.8-hd`, 32 kHz mono WAV |
| Image | **VERIFIED** — `image-01`, 9:16 portrait, seed supported |
| H3 video | **VERIFIED** — real `MiniMax-H3` 768P 4 s task succeeded on the Subscription Key |
| H3 reference / keyframe modes | **DOCUMENTED_BUT_NOT_TESTED** — same credential, not exercised |
| Credit Pack balance | `0.00` observed, re-checked before every generation |
| Balance read dependency | `UNDOCUMENTED_FIRST_PARTY_IMPLEMENTATION_DEPENDENCY`, fail closed |
| H3 duration | integer enum 4-15 (H3), 5-15 (H3 Max); test minimum 4 s / 5 s |
| Evidence | `research/providers/minimax-mplan-explore-capability.md`, `research/providers/minimax-voice-clone-entitlement.md` |

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
