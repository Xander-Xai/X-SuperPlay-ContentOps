# Current State

> What runs today. Verified facts only. No aspirations, no stale claims.
>
> Last verified: 2026-10-03

## Git

| Property | Value |
|---|---|
| Active branch | `refactor/contentops-easel-minimax-plan` |
| Baseline commit | `8b5fce7` (from `feat/v1-video-pipeline`) |
| Frozen baseline | `feat/v1-video-pipeline` |
| Superseded | `codex/photo-avatar-api-clarification` |
| Main protection | **Unprotected** — NO DIRECT PUSH TO MAIN |

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
| Capability spike | **PENDING** (Issue #4) |
| PAYG allowed | **false** |
| Billing mode | subscription (planned, not yet verified) |

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
5. Main branch unprotected — governance policy enforced by convention, not by GitHub settings.
