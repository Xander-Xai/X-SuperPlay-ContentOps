# X-SuperPlay-ContentOps

> Evidence-first, multi-platform content operations runtime for Xander-Xai.

[English](README.md) | [简体中文](README.zh-CN.md)

## What

A unified runtime that converts real business work (GitHub repos, experiments, research) into traceable video, 公众号 articles, 小红书 image-text notes and X posts, each through its own production gate.

## Why

Previous approach used 5 separate platform-specific repos that never produced stable output. ContentOps consolidates production into one runtime with honest quality gates.

## Current Status

| Item | Status |
|---|---|
| Easel runtime | Pinned v0.2.1 (commit `3fe2d99`, 982 blobs verified) |
| Video pipeline | Implemented; producers and QC exist; `production_ready: false`; human review pending |
| 公众号 (WeChat article) | Vendored ten-stage workflow; stops at a WeChat draft; rights audit open (#56) |
| 小红书 image-text | Eight-step workflow on `feat/xhs-fa-migration`; not merged; manual upload only |
| X | PR #50; manual-only editorial package; not merged |
| MiniMax media | Speech, image and H3 video implemented and live-tested; `PENDING_FOUNDER_REVIEW` |
| Auto-publishing | **NOT** in scope |
| Tests | See [docs/CURRENT-STATE.md](docs/CURRENT-STATE.md); run the unified gate with `python scripts/dev_check.py` |
| Production ready | **false** — no platform is `PRODUCTION_ACCEPTED` |

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
Route (HOTSPOT_DISCOVERY / USER_TOPIC)
  -> Account DNA -> Content format -> Brief -> platform gate -> human review
     ├ Video        -> cut plan -> capture -> compose -> QC -> final.mp4
     ├ 公众号        -> ten vendored stages -> WeChat draft
     ├ 小红书图文    -> eight gates -> manual upload package
     └ X            -> editorial package -> manual publish
```

No route publishes by itself. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and
[docs/CURRENT-STATE.md](docs/CURRENT-STATE.md) for the current boundaries.

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
- `main` is **PROTECTED** (enabled 2026-10-31): required checks `Tests (ubuntu-latest)`, `Tests (windows-latest)`, `Repo policy checks`; PR required; no force push; no deletion; linear history
- A solo owner cannot self-approve, so the required approval count is 0; raise it to 1 when a second reviewer is available
- See [GitHub Issues](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues) for milestone tracking

## Extension Policy

```
ADAPTER > EXTENSION > CUSTOM SKILL > UPSTREAM PATCH > FORK
```

Fork is last resort. Current state: no fork, no upstream modification.

## Non-goals (current phase)

- Autonomous platform publishing
- Comment scraping / ROI agent
- Autonomous digital-human product / AI short drama
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


## Portfolio responsibility boundary (2026-10-30)

This public note defines technical responsibilities only. Any private portfolio registry or business operation remains outside this repository; there is no claim that other privately managed systems are accessible, commercialized, or operational.

- **Owns:** production and human review of source-grounded video, 公众号 articles, 小红书 image-text and X editorial artifacts.
- **Outputs:** media assets, articles, upload packages, QC results and reproducible generation workflows; actual platform publication tracked by its authorized operators.
- **Does not own:** not a social-platform account, paid-customer CRM, revenue source of truth or automatic publisher.
- **Public interfaces and handoff:** Technical public-source examples may originate from [Beauty RAG](https://github.com/Xander-Xai/Beauty-Industry-RAG-QA-System) and [Customer-Service AI Agent](https://github.com/Xander-Xai/Customer-Service-AI-Agent), with licenses and publicity permission checked separately.
- Technical implementation, testing and release evidence stay in this repository. An upstream portfolio document cannot promote draft, local tests or CI into real production usage, payment or user traction.
