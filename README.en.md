# X-SuperPlay-ContentOps

> Evidence-first, multi-platform content operations runtime for Xander-Xai.

[简体中文](README.md) | English

> Last verified: 2026-11-12 on `main` at `c1da6dd`. The status table describes
> `main`, never a draft branch.

## What

A unified runtime that converts real business work (GitHub repos, experiments,
research) into traceable video, 公众号 articles and graphic packs, and X posts —
each through its own production gate. It renders, validates and packages. It does
not publish: a delivery pack stops at a human who records the URL.

The convergence requirements that reconciled these documents with the code are
recorded in [docs/CONVERGENCE-REQUIREMENTS-2026-11-01.md](docs/CONVERGENCE-REQUIREMENTS-2026-11-01.md)
(accepted 2026-11-01; its remaining steps landed between 2026-11-04 and 2026-11-11).

## Why

Previous work used 5 separate platform-specific repos that never produced stable
output. ContentOps consolidates video production into one runtime with honest,
non-bypassable quality and human-review gates.

## Current Status

The table describes **`main`** at `c1da6dd` (verified 2026-11-12). A track is not
"done" because a draft branch describes it, and code that exists is not a
capability that published anything.

| Item | Layer | Status |
|---|---|---|
| Easel runtime | `main` | Pinned v0.2.1 (commit `3fe2d99`, 982 blobs verified). Upstream stable is v0.3.0 — not adopted |
| Stable production entry (`make_content.py`, `production_gates.py`) | `main` | Implemented: explicit gate decisions, eight fail-closed VIDEO gates and six GRAPHIC_TEXT gates. Running `m5_production.py` / `produce_video.py` directly stays a *diagnostic* path and is not gate-checked |
| Video pipeline (`run_v1.py`) | `main` | Implemented (`easel` + diagnostic `fallback`); `production_ready: false` |
| M5 evidence-first chain (`m5_production.py`) | `main` | Implemented and integration-verified on `projects/m5-media-use`; optional ASR backcheck gate on real narration; `production_ready: false`, `PENDING_FOUNDER_REVIEW` |
| M5 characterization baseline | `main` | `docs/m5-baseline/m5-characterization-2026-11-10.md` — 10 suites / 165 tests at `5ff621c1` as the slice-1 receipt of #140 (164 pass, 1 known fail left visible) |
| Card and article rendering (`render_cards.py`, `render_article.py`) | `main` | Implemented: HTML cards → PNG with a density audit, article HTML validated and preview-wrapped by the pinned Easel skills. Each writes a tamper-evident receipt; a PASS is not an approval |
| Media-use adapter (HyperFrames) | `main` | Implemented; local-only, zero network/paid calls. Needs a host runtime lock — default verdict is `BLOCKED / MISSING_RUNTIME` |
| MiniMax media | `main` | Speech, image and H3 video implemented; verified subsets are listed in CURRENT-STATE; `PENDING_FOUNDER_REVIEW` |
| Skill routing / execution authorization | `main` | Implemented; only `media-use` is a declared capability; the router never authorizes execution |
| Content router, account DNA, workflow gates | `main` | Implemented through PRs #114 and #118. 15 hotspot sources are registered — exactly one native search (GitHub) and fourteen list-only — and both account DNAs are open to all of them (#157). Hotspot and user-topic routes produce briefs; approval and copy review remain gated |
| Video delivery (`video_deliver.py`) | `main` | Implemented: `plan` / `pack` / `status` build per-platform packs and thumbnails; `dispatch` needs an operator grant. An uploader exit 0 is recorded as `UPLOADER_EXIT_0`, never as publication — only a URL a person actually saw is recorded as one |
| Graphic delivery (`platform_delivery.py`, `graphic_deliver.py`, `wechatsync_browser.py`) | `main` | Implemented: offline packs, then drafts only, through an external CLI across a process boundary. No `PUBLISHED` branch and no URL is ever written by code |
| 公众号 (WeChat article) | `main` render + draft path | Article HTML renders and validates; `wechat_draft.py` can stop at a real platform draft and `wechat_metrics.py` reads the data cube, both operator-gated and `DRAFT_ONLY`. The registry row stays `PLANNED`; Issue #56 rights remain unresolved |
| 小红书 image-text | `main` spec + delivery channel | Graphic specs and a delivery-channel record exist; the registry has no image row (the whole platform belongs to the VIDEO line, per the 2026-11-09 operator instruction). Rights and migration acceptance stay open in Issue #51 |
| X | `main` manual-only editorial track | Editorial gate, manual package, URL recording and offline metric analysis exist; no API publication or automatic metric collection |
| Auto-publishing | — | **Not in scope** |
| Publication | — | **0** — no delivery package holds a real platform URL |
| Tests | `main` | 98 suites under `tests/test_*.py`, each wired into CI as a named step; the complete local gate is `python scripts/dev_check.py` |
| Production ready | — | **false** — no track is `PRODUCTION_ACCEPTED` |

### X Original Content Rewards — proposed growth experiment

The [X project](projects/x-growth-en/README.md) now includes a [90-day evidence-first growth plan](projects/x-growth-en/original-content-rewards-90d.md) and blank eligibility/weekly-review templates. This is **documentation and manual measurement only**. The existing X post/editorial gates remain the executable authority; no automated X metric access, posting, payout eligibility, or publication is claimed. The older private `X-SuperPlay-X-Growth-OS` is a retirement/migration source, not a second execution owner.

### Branch reality

This README describes the repository's current `main` capabilities, not the status
of an earlier feature branch. As verified on 2026-11-12: `main` is the only
persistent branch; one non-runtime catalog branch is open as PR #158; four issues
are open (#7 EPIC, #51 and #56 rights gates, #140 M5 stage split). The X, XHS and
GZH adapters are all on `main`, with different execution boundaries, as listed
above. Delivery code exists for every content line, yet no platform row is above
`PLANNED` except `x`, because no public account is bound and nothing has a real
platform URL. One correction worth stating: the Xiaohongshu runtime adapter was
removed on 2026-11-09 with the graphic workflow (`src/contentops/xhs/` is empty),
so `main` carries only its registry row and video delivery-channel config — there
is no Xiaohongshu adapter code to run. See [docs/CURRENT-STATE.md](docs/CURRENT-STATE.md) for dated
evidence and [docs/DEFERRED-WORK.md](docs/DEFERRED-WORK.md) for open work.

### Overseas channel candidate coverage (not operational)

The separate, **non-runtime** `config/registry/channel-candidates.json` catalog documents **Threads, Instagram and Facebook** as pre-canonical research candidates. They are absent from the canonical platform runtime registry and have no account, executable pipeline, publishing or metrics. WhatsApp and LINE are private-conversion research touchpoints, not publishing destinations. See [candidate status and acceptance boundaries](docs/OVERSEAS-CHANNEL-CANDIDATES-20261111.md). This does not change the Strategy canonical 14-platform portfolio or production readiness.

## Architecture

One sentence: **source → evidence → decision → two production lines → gates →
delivery pack → human**. Each layer does one thing. Every shortcut across layers
has a price (skip evidence and the video has no provenance; skip the gates and the
render is irreproducible; skip delivery and a human retypes the same metadata).

### Layers

```text
real sources                              Strategy
GitHub repos / experiments  →  direction · Bundle template
                    │
                    ▼
┌─ EVIDENCE ───────────────────────────────────────────────┐
│ SourceArtifact (permission) · ClaimLedger (quotes)       │
│ Content Bundle (a plan, never a publication)             │
└──────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─ DECISION ───────────────────────────────────────────────┐
│ Router: hotspot (15 sources) / user topic                │
│ → Account DNA → Brief → script / storyboard / design     │
└──────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─ PRODUCTION (two lines, split before render) ────────────┐
│ VIDEO   narration · subtitles · shots → Easel → QC       │
│ GRAPHIC outline · draft → cards / HTML → validate        │
└──────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─ GATES ──────────────────────────────────────────────────┐
│ make_content.py: 8 VIDEO / 6 GRAPHIC_TEXT gates          │
│ copy review (fingerprint) · QC · ASR (detect only)       │
└──────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─ DELIVERY (packs only, never publishes) ─────────────────┐
│ video_deliver: per-platform pack + thumbnails            │
│ platform_delivery / graphic_deliver: drafts only         │
└──────────────────────────────────────────────────────────┘
                    │
                    ▼
        human review → a person records the URL (count: 0)
```

### Entry points: which one to run

| Goal | Command | Publishes? |
|---|---|---|
| Environment check | `python scripts/doctor.py` | — |
| Complete local gate | `python scripts/dev_check.py` | — |
| Production (gated, recommended) | `python scripts/make_content.py run --project <p> --mode STRICT` | No |
| Diagnostic M5 run | `python scripts/m5_production.py <p>` | No |
| Card / article render | `render_cards.py` / `render_article.py` | No |
| Video delivery pack | `video_deliver.py plan` / `pack` / `status` | No |
| Graphic delivery | `platform_delivery.py pack`, `graphic_deliver.py --all` | Drafts only |
| GZH draft | `wechat_draft.py` (operator grant) | Draft only |
| Record a real URL | `video_deliver.py record --url <url>` | Records, never publishes |
| Platform status | `python scripts/platforms.py check` / `list` | No |

### Module map

| Location | Responsibility |
|---|---|
| `src/contentops/evidence/` | `SourceArtifact`, `ClaimLedger`: where every claim comes from |
| `src/contentops/content_kernel/` | Bundle validation + the two handoffs (VIDEO / GRAPHIC_TEXT) |
| `src/contentops/routing/` | Routes (hotspot / user topic), Account DNA, Brief, script and design stages |
| `src/contentops/hotspots/` | Capability registry for 15 sources, fetch, dedup, quality, ranking |
| `src/contentops/script/` | Copy drafting and its refusal paths |
| `src/contentops/media/` | Media contracts, billing gate, providers, manifest, QC canonicalization, ASR backcheck, read-only scene analysis |
| `src/contentops/workflow/` | Ordered stage contract and the human gate |
| `src/contentops/easel/` | Host guard and step driver for the pinned Easel (upstream untouched) |
| `src/contentops/platforms/` | The single platform registry + delivery-channel specs (video / graphic) |
| `src/contentops/publish/` | X manual-only gate (no `PUBLISHED` branch) |
| `src/contentops/graphic/` | Manual graphic package, cards, GZH article (rendering is not approval) |
| `src/contentops/gzh/` | GZH runtime adapter (`VERIFY_ONLY`) |
| `src/contentops/skills/` | Skill resolution, execution gate and authorization source |
| `src/contentops/golden/` | Golden identity, evidence locks, review, A/B variants |
| `scripts/` | Every CLI entry point (table above) + gate scripts (`check_*`, `dev_check`) |

### Three hard boundaries

1. **Production does not publish.** Delivery produces packs and platform drafts;
   `PUBLISHED` does not exist in code and a URL can only be recorded by a person.
   An uploader exit 0 is stored as `UPLOADER_EXIT_0`, not as publication.
2. **Evidence before claim.** An LLM drafts, evidence verifies. QC PASS is not
   approval; `production_ready` stays `false` until a human-review receipt exists.
3. **Docs follow code.** Every tracked doc carries a verification date; a commit
   touching its code after that date fails the check
   ([docs/DOC-SYNC.md](docs/DOC-SYNC.md)). A stale status table is not a small
   problem — it is a wrong one.

## Quick Start

### Windows PowerShell

```powershell
python scripts\doctor.py
python scripts\dev_check.py
python scripts\new_project.py --slug my-video --title "My Video"
python scripts\make_content.py check --project projects\my-video
python scripts\run_v1.py   projects\my-video
python scripts\m5_production.py projects\m5-media-use
python scripts\qc_video.py projects\my-video
```

### WSL2 Ubuntu / Linux

```bash
python3 scripts/doctor.py
python3 scripts/dev_check.py
python3 scripts/new_project.py --slug my-video --title "My Video"
python3 scripts/make_content.py check --project projects/my-video
python3 scripts/run_v1.py   projects/my-video
python3 scripts/m5_production.py projects/m5-media-use
python3 scripts/qc_video.py projects/my-video
```

`make_content.py` is the production entry: it refuses to invoke a producer until
every gate passes, and `m5_production.py` / `produce_video.py` run directly are
diagnostic paths. Delivery commands (`video_deliver.py`, `platform_delivery.py`,
`graphic_deliver.py`) are listed in [docs/RUNBOOK.md](docs/RUNBOOK.md); none of
them publishes without an operator grant.

## Runtime detail

### Two video entry points, one gated production entry

`run_v1.py` (storyboard-driven, edge-tts) and `m5_production.py` (evidence-first,
local narration) share one compose-and-QC engine. In front of both is
`make_content.py`: it runs the gates first and refuses to invoke a producer when
one fails. Calling either script directly is a diagnostic path — ungated, and it
never reports production-ready. None of the three publishes.

### Routing and copy review

The account-aware router (hotspot / user topic → Account DNA → Brief) is on
`main` (PR #114); `router_e2e.py` is an acceptance harness, not a production
entry. A brief-driven project must pass copy review (fingerprint-bound) before it
can render. Stage ownership and current state live in
[docs/CONTENT-LIFECYCLE-STAGES.md](docs/CONTENT-LIFECYCLE-STAGES.md).

### Boundaries and evidence

System boundaries, component calls and rules: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
What actually runs today and which sections are historical:
[docs/CURRENT-STATE.md](docs/CURRENT-STATE.md). Platform status is derived from the
registry in [docs/PLATFORM-INTEGRATION-STATUS.md](docs/PLATFORM-INTEGRATION-STATUS.md).

## Canonical Documentation

| Doc | Purpose |
|---|---|
| [docs/INDEX.md](docs/INDEX.md) | Navigation hub |
| [docs/CURRENT-STATE.md](docs/CURRENT-STATE.md) | What runs today |
| [docs/DOC-SYNC.md](docs/DOC-SYNC.md) | Documentation freshness: triggers, procedure and the machine check |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System boundaries |
| [docs/PRD.md](docs/PRD.md) | Product requirements |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | Real executable commands |
| [docs/DEVELOPMENT-PLAN.md](docs/DEVELOPMENT-PLAN.md) | Milestones and status |
| [docs/QUALITY-STANDARD.md](docs/QUALITY-STANDARD.md) | Quality gates |
| [docs/TEST-PLAN.md](docs/TEST-PLAN.md) | Test inventory and CI wiring |
| [docs/PLATFORM-INTEGRATION-STATUS.md](docs/PLATFORM-INTEGRATION-STATUS.md) | Per-platform status, from the registry |
| [docs/ASR-BACKCHECK.md](docs/ASR-BACKCHECK.md) | The narration ASR gate: a detector, never a judge |
| [docs/CONVERGENCE-REQUIREMENTS-2026-11-01.md](docs/CONVERGENCE-REQUIREMENTS-2026-11-01.md) | 2026-11-01 convergence plan and its outcome |
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
- `main` is **PROTECTED** (enabled 2026-10-31, admin-enforced since 2026-11-10): required checks `Tests (ubuntu-latest)`, `Tests (windows-latest)`, `Repo policy checks`; PR required; no force push; no deletion; linear history
- A solo owner cannot self-approve, so the required approval count is 0; raise it to 1 when a second reviewer is available
- Branch registry: `config/governance/branch-registry.json`, checked offline by `python scripts/check_branch_registry.py --today <date>`
- Documentation freshness: every tracked doc carries a verification date and must be re-synced when its code changes; `python scripts/check_doc_freshness.py` enforces it locally and in CI (rules in [docs/DOC-SYNC.md](docs/DOC-SYNC.md))
- Open work: [GitHub Issues](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues)

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
