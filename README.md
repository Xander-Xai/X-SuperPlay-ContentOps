# X-SuperPlay-ContentOps

> Evidence-first video ContentOps runtime for Xander-Xai multi-repo content production.

[English](README.md) | [简体中文](README.zh-CN.md)

## What

A unified runtime that converts real business work (GitHub repos, experiments, research) into high-quality, traceable, publishable video content.

## Why

Previous approach used 5 separate platform-specific repos that never produced stable output. ContentOps consolidates production into one runtime with honest quality gates.

## Current Status

| Item | Status |
|---|---|
| Easel runtime | Pinned v0.2.1 (commit `3fe2d99`, 982 blobs verified) |
| Production engine | Easel `assemble.py` (upstream, unmodified) |
| Production voice | edge-tts via Easel `tts.py` (zh-CN-YunxiNeural) |
| Voice quality | `edge_tts_fallback` — awaiting MiniMax upgrade (M2) |
| Diagnostic engine | ffmpeg-only fallback (never production) |
| MiniMax integration | NOT_IMPLEMENTED (capability spike pending, Issue #4) |
| Auto-publishing | NOT in scope |
| Golden samples | 1 (`projects/easel-review/`) |
| Tests | 9 passing |
| Production ready | **false** — READY_FOR_HUMAN_REVIEW |

## Quick Start

### Windows PowerShell

```powershell
python scripts\doctor.py
python scripts\new_project.py --slug my-video --title "My Video"
python scripts\run_v1.py   projects\my-video
python scripts\qc_video.py projects\my-video
```

### WSL2 Ubuntu / Linux

```bash
python3 scripts/doctor.py
python3 scripts/new_project.py --slug my-video --title "My Video"
python3 scripts/run_v1.py   projects/my-video
python3 scripts/qc_video.py projects/my-video
```

## Architecture Summary

```
Source → Script → Storyboard → Voice → Compose → QC → Human Review → final.mp4
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for full system boundaries.

## Canonical Documentation

| Doc | Purpose |
|---|---|
| [docs/INDEX.md](docs/INDEX.md) | Navigation hub |
| [docs/CURRENT-STATE.md](docs/CURRENT-STATE.md) | What runs today |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System boundaries |
| [docs/PRD.md](docs/PRD.md) | Product requirements |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | Real executable commands |
| [docs/DEVELOPMENT-PLAN.md](docs/DEVELOPMENT-PLAN.md) | M0–M6 milestones |
| [docs/QUALITY-STANDARD.md](docs/QUALITY-STANDARD.md) | Quality gates |
| [docs/UPSTREAM-EASEL.md](docs/UPSTREAM-EASEL.md) | Easel pin policy |
| [AGENTS.md](AGENTS.md) | AI agent execution discipline |

## Easel Pin

| Property | Value |
|---|---|
| Repo | https://github.com/ZJU-REAL/Easel |
| Tag | v0.2.1 |
| Commit | `3fe2d9904c1619281ef57f81d9ee0b7854998399` |
| Local path | `.runtime/easel/` |
| Lock file | `runtime/easel.lock.json` |
| Upgrade | Requires Founder approval + regression suite |

See [docs/UPSTREAM-EASEL.md](docs/UPSTREAM-EASEL.md) for full policy.

## Governance

- **NO DIRECT PUSH TO MAIN** — all changes via PR
- `main` is **PROTECTED**: required status checks + PR + no force push + no deletion + linear history
- Active branch: `chore/g06-compatibility-operations`
- See [GitHub Issues](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues) for milestone tracking

## Extension Policy

```
ADAPTER > EXTENSION > CUSTOM SKILL > UPSTREAM PATCH > FORK
```

Fork is last resort. Current state: no fork, no upstream modification.

## Non-goals (current phase)

- Auto-publishing to any platform
- Comment scraping / ROI agent
- Digital human / AI short drama
- Metrics scraping / winner learning
- n8n / OpenClaw total orchestration

## Core Principles

```
Adopt before Build.       Ship before Automate.
Measure before Optimize.  Delete before Expand.
Evidence before Claim.    Contract before Integration.
Quota before Generation.  Quality before Scale.
Runtime Reality before Documentation.
```
