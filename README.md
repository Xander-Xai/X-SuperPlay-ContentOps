# X-SuperPlay-ContentOps

> Evidence-first, multi-platform content operations runtime for Xander-Xai.

[English](README.md) | [简体中文](README.zh-CN.md)

## What

A unified runtime that converts real business work (GitHub repos, experiments,
research) into traceable video and, eventually, 公众号 articles, 小红书
image-text notes and X posts — each through its own production gate.

This branch also carries the convergence requirements that reconcile the
documents with the code: [docs/CONVERGENCE-REQUIREMENTS-2026-11-01.md](docs/CONVERGENCE-REQUIREMENTS-2026-11-01.md).

## Why

Previous work used 5 separate platform-specific repos that never produced stable
output. ContentOps consolidates video production into one runtime with honest,
non-bypassable quality and human-review gates.

## Current Status

The table separates what is on **`main`** from what exists only on an
**unmerged branch**. A track is not "done" because a draft branch describes it.

| Item | Layer | Status |
|---|---|---|
| Easel runtime | `main` | Pinned v0.2.1 (commit `3fe2d99`, 982 blobs verified). Upstream stable is v0.3.0 — not adopted |
| Video pipeline (`run_v1.py`) | `main` | Implemented (`easel` + diagnostic `fallback`); `production_ready: false` |
| M5 evidence-first chain (`m5_production.py`) | `main` | Implemented and integration-verified on `projects/m5-media-use`; `production_ready: false`, `PENDING_FOUNDER_REVIEW` |
| Media-use adapter (HyperFrames) | `main` | Implemented; local-only, zero network/paid calls. Needs a host runtime lock — default verdict is `BLOCKED / MISSING_RUNTIME` |
| MiniMax media | `main` | Speech, image and H3 video implemented; verified subsets are listed in CURRENT-STATE; `PENDING_FOUNDER_REVIEW` |
| Skill routing / execution authorization | `main` | Implemented; only `media-use` is a declared capability; the router never authorizes execution |
| Content router, account DNA, workflow gates | **unmerged** | `feat/content-router` (PR #49, draft) — not on `main` |
| 公众号 (WeChat article) | **unmerged / local vendor** | Ten-stage vendored workflow; provenance/rights fix is PR #58 (#56) |
| 小红书 image-text | **unmerged** | `feat/xhs-fa-migration`; manual upload only |
| X | **partial** | Post gate and growth→editorial gate are on `main` (PRs #87, #88); the migrated platform track is still PR #50 |
| Auto-publishing | — | **Not in scope** |
| Tests | `main` | 31 suites; see [docs/TEST-PLAN.md](docs/TEST-PLAN.md); unified gate `python scripts/dev_check.py` |
| Production ready | — | **false** — no track is `PRODUCTION_ACCEPTED` |

### Branch reality

`main` now carries the integration stack: the media-use adapter, rights gate,
skill router and skill-execution authorization landed as PR #89, followed by
PRs #87 and #88. The former integration branch `fix/57-m5-media-fixtures` was
merged and its remote branch deleted.

What is still **not** on `main` is named in the table above and tracked by open
PRs: the content router (#49), the X platform track (#50), the GZH provenance
fix (#58), the receipt-baseline fix (#62) and the media-use pre-merge ADR (#90).

The docs describe `main`. An unmerged layer is named as unmerged rather than
described as a working feature; see
[docs/CONVERGENCE-REQUIREMENTS-2026-11-01.md](docs/CONVERGENCE-REQUIREMENTS-2026-11-01.md).

## Quick Start

### Windows PowerShell

```powershell
python scripts\doctor.py
python scripts\dev_check.py
python scripts\new_project.py --slug my-video --title "My Video"
python scripts\run_v1.py   projects\my-video
python scripts\m5_production.py projects\m5-media-use
python scripts\qc_video.py projects\my-video
```

### WSL2 Ubuntu / Linux

```bash
python3 scripts/doctor.py
python3 scripts/dev_check.py
python3 scripts/new_project.py --slug my-video --title "My Video"
python3 scripts/run_v1.py   projects/my-video
python3 scripts/m5_production.py projects/m5-media-use
python3 scripts/qc_video.py projects/my-video
```

## Architecture Summary

What runs on this branch:

```text
project.yaml source_refs
  -> SourceArtifact (permission-aware)
  -> ClaimLedger (quote-verified claims)
  -> script + storyboard
  -> MediaManifest (assets inventory + timeline)
  -> narration / subtitles
  -> pinned Easel compose (assemble_easel adapter)
  -> qc_video
  -> human review gate
```

Two entry points share that engine: `run_v1.py` (storyboard-driven, edge-tts)
and `m5_production.py` (evidence-first, local narration). Neither publishes and
neither reports production-ready.

The account-aware content router (`HOTSPOT_DISCOVERY` / `USER_TOPIC` → Account
DNA → Brief) is **not on this branch**. It is the subject of
[docs/CONVERGENCE-REQUIREMENTS-2026-11-01.md](docs/CONVERGENCE-REQUIREMENTS-2026-11-01.md)
and PR #49.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and
[docs/CURRENT-STATE.md](docs/CURRENT-STATE.md) for the current boundaries.

## Canonical Documentation

| Doc | Purpose |
|---|---|
| [docs/INDEX.md](docs/INDEX.md) | Navigation hub |
| [docs/CURRENT-STATE.md](docs/CURRENT-STATE.md) | What runs today |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System boundaries |
| [docs/PRD.md](docs/PRD.md) | Product requirements |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | Real executable commands |
| [docs/DEVELOPMENT-PLAN.md](docs/DEVELOPMENT-PLAN.md) | Milestones and status |
| [docs/QUALITY-STANDARD.md](docs/QUALITY-STANDARD.md) | Quality gates |
| [docs/TEST-PLAN.md](docs/TEST-PLAN.md) | Test inventory and CI wiring |
| [docs/CONVERGENCE-REQUIREMENTS-2026-11-01.md](docs/CONVERGENCE-REQUIREMENTS-2026-11-01.md) | Current convergence plan |
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
| Upstream stable | v0.3.0 (not adopted; skill paths moved to `skills/builtin/`) |
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
