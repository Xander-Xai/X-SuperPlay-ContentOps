# Repository Audit Report

> Audited: 2026-10-03
> Auditor: Claude Code (Principal Software Architect)
> Branch: `refactor/contentops-easel-minimax-plan` (from `feat/v1-video-pipeline@8b5fce7`)
> Related Issue: #2

## Git State (verified)

| Branch | HEAD | Role |
|---|---|---|
| `main` | `4a42791` | Canonical history |
| `feat/v1-video-pipeline` | `8b5fce7` | FROZEN_BASELINE |
| `codex/photo-avatar-api-clarification` | `d25543c` | SUPERSEDED |
| `refactor/contentops-easel-minimax-plan` | `8b5fce7` | ACTIVE development |

Ancestry: `feat/v1-video-pipeline` strictly contains `codex/photo-avatar-api-clarification`.
PR #1 closed without merge (superseded by PR #8).

## Easel Runtime (verified)

| Aspect | Value |
|---|---|
| Version | v0.2.1 |
| Commit | `3fe2d9904c1619281ef57f81d9ee0b7854998399` |
| Path | `.runtime/easel/` |
| Acquisition | GitHub Release tarball via `gh api` |
| Verification | 982/982 blob SHA-1 matched upstream tree |
| Re-verified | 2026-10-03 via `scripts/verify_easel_runtime.py` |
| Legacy clone | `Easel/` at commit `4b9c03c` — gitignored, NOT production |

## Code Reality

| Component | What it does | Status |
|---|---|---|
| `run_v1.py` | Two engines: `easel` (production) + `fallback` (diagnostic) | Working |
| `assemble_easel.py` | Upstream Easel orchestration with Windows subtitle workaround | Working |
| `qc_video.py` | Technical + evidence-first QC gate | Working |
| `resolve_easel.py` | Single resolver for pinned runtime | Working |
| `verify_easel_runtime.py` | Content hash verification against upstream tree | Working |
| `doctor.py` | Environment checker | Working |
| `test_basic.py` | 9 tests | All PASS |

## Production Voice

- Production engine uses **edge-tts** via Easel's `tts.py` (zh-CN-YunxiNeural)
- Fallback uses Windows SAPI → espeak → silence
- Build receipt correctly marks `voice_quality: edge_tts_fallback`
- `production_ready: false` — awaiting human review and MiniMax voice upgrade

## Contradictions Found (15)

| # | Fact | Contradiction | Runtime Truth | Resolution |
|---|---|---|---|---|
| 1 | Easel version | 0.1.1 in experiment docs | v0.2.1 | Archive docs, mark superseded |
| 2 | Easel version | 0.1.1 in scorecard | v0.2.1 | Archive, update metadata |
| 3 | Easel version | 0.1.1 in 02-Runtime README | v0.2.1 | Archive doc |
| 4 | Easel path | `runtime/Easel/` in 02-Runtime | `.runtime/easel/` | Fix in canonical docs |
| 5 | Voice engine | "SAPI" in README | edge-tts (production) | Rewrite README |
| 6 | Voice engine | "SAPI" in Runbook | edge-tts (production) | Rewrite Runbook |
| 7 | Experiment status | "Queued" in experiment | Work completed | Archive, mark COMPLETED |
| 8 | Project output | `fallback.mp4` in project.yaml | `easel.mp4` is latest | Reconcile in M1 |
| 9 | Voice quality | `windows_sapi` in project.yaml | `edge_tts_fallback` | Reconcile in M1 |
| 10 | Fork policy | "❌ Fork / 改造 Easel" | New: Extension Policy | Update AGENTS.md |
| 11 | MiniMax billing | "PAYG" in provider doc | Subscription only | Doc stays local-only |
| 12 | Governance docs | 6 files in 00-Governance/ | Directory doesn't exist | Remove all references |
| 13 | Docs links | 4 docs files referenced | Files don't exist | Remove references |
| 14 | Easel acquisition | "git clone" in deployment doc | Release archive | Archive doc |
| 15 | Web workbench | "localhost:7860" as daily entry | 6 doctor FAILs | Mark unverified |

## Broken Links (10)

All files referenced in README.md that do not exist:

1. `00-Governance/PRINCIPLES.md`
2. `00-Governance/PRE-CODE-GATE.md`
3. `00-Governance/PROJECT-STATES.md`
4. `00-Governance/MEASUREMENT.md`
5. `00-Governance/douyin-1024-STRATEGY.md`
6. `00-Governance/decisions/ADR-WS008-Presenter-Layer.md`
7. `docs/OPEN-SOURCE-VERSION-HEURISTICS.md`
8. `docs/PRESENTER-LAYER-SPEC.md`
9. `docs/PRESENTER-PROVIDER-ROUTING.md`
10. `docs/DIGITAL-HUMAN-PROVIDER-ANALYSIS.md`

## Security State

| Item | Status |
|---|---|
| `.env` | Gitignored ✓ |
| `.verify-tmp/` | Gitignored ✓ (added in 8b5fce7) |
| `docs/ai-provider-selection.md` | Gitignored ✓ (added in 8b5fce7) |
| `runtime-config-backups/` | Gitignored ✓ |
| `Easel/` clone | Gitignored ✓ |
| Provider endpoint in receipts | Redacted ✓ (8b5fce7) |
| API keys in tracked files | None found ✓ |

## Golden Sample

`projects/easel-review/` contains:
- 15 real screenshots
- Master script (6 shots, evidence-first)
- Storyboard (6 shots, all `real_screenshot`, 0 generated)
- Build receipts (easel + fallback)
- QC reports (easel + fallback)
- Runtime receipt (acquisition + verification log)
- Final videos: easel.mp4, fallback.mp4 (gitignored)

## What Does NOT Exist

- MiniMax integration code
- `config/` directory
- `src/` directory
- `tests/` directory (tests in `scripts/test_basic.py`)
- Human Review receipt
- `00-Governance/` directory
- 4 docs files referenced in README
