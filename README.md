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
| Content router, account DNA, workflow gates | `main` | Implemented through PRs #114 and #118; hotspot and user-topic routes produce briefs, while approval and downstream copy review remain gated |
| 公众号 (WeChat article) | `main` verify-only adapter | `status` / `verify` / `plan` only; third-party rights remain unresolved in Issue #56; no production or publication |
| 小红书 image-text | `main` verify-only adapter | `status` / `verify` / `plan` only; rights and migration acceptance remain open in Issue #51; no production or publication |
| X | `main` manual-only editorial track | Editorial gate, manual package, URL recording and offline metric analysis exist; no API publication or automatic metric collection |
| Auto-publishing | — | **Not in scope** |
| Tests | `main` | Every suite under `tests/test_*.py` is wired into CI; count is not asserted here — see [docs/TEST-PLAN.md](docs/TEST-PLAN.md); unified gate `python scripts/dev_check.py` |
| Production ready | — | **false** — no track is `PRODUCTION_ACCEPTED` |

### X Original Content Rewards — proposed growth experiment

The [X project](projects/x-growth-en/README.md) now includes a [90-day evidence-first growth plan](projects/x-growth-en/original-content-rewards-90d.md) and blank eligibility/weekly-review templates. This is **documentation and manual measurement only**. The existing X post/editorial gates remain the executable authority; no automated X metric access, posting, payout eligibility, or publication is claimed. The older private `X-SuperPlay-X-Growth-OS` is a retirement/migration source, not a second execution owner.

### Branch reality

This README describes the repository's current `main` capabilities, not the status
of an earlier feature branch. The content router and brief bridge are on `main`
(PRs #114 and #118); X, XHS and GZH adapters are also on `main` but have different
execution boundaries, as listed above. GZH and XHS remain verify-only while rights
and acceptance are unresolved. See [docs/CURRENT-STATE.md](docs/CURRENT-STATE.md)
for dated evidence and [docs/DEFERRED-WORK.md](docs/DEFERRED-WORK.md) for open work.

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
DNA → Brief) is implemented on `main` (PR #114). The separate `router_e2e.py`
command is an acceptance harness, not the production operator entry. Copy review
remains a required gate before a brief-driven project can render. See
[docs/CURRENT-STATE.md](docs/CURRENT-STATE.md) and
[docs/CONTENT-LIFECYCLE-STAGES.md](docs/CONTENT-LIFECYCLE-STAGES.md) for current
scope and limits.

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
