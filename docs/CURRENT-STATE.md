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
| Integration | **NOT_IMPLEMENTED** |
| Capability spike | **COMPLETE** (Issue #4, 2026-10-04) |
| PAYG allowed | **false** |
| Billing mode | subscription, **verified** |
| Transport | official MiniMax CLI `mmx` (`mmx-cli` v1.0.27) |
| Speech | **VERIFIED** — `speech-2.8-hd`, 32 kHz mono WAV |
| Image | **VERIFIED** — `image-01`, 9:16 portrait, seed supported |
| H3 video | **NOT_ENTITLED / BLOCKED** — H3 requires a pay-as-you-go or credit key |
| Credit Pack balance | `0.00` observed, re-checked before every generation |
| Evidence | `research/providers/minimax-mplan-explore-capability.md` |

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
