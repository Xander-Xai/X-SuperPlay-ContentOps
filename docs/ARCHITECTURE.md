# Architecture

[English](ARCHITECTURE.md) | [简体中文](ARCHITECTURE.zh-CN.md)

> What the system is. Where the boundaries are. How components call each other.

## System Boundaries

```
X-SuperPlay-OPC-Blueprint
= Business Source of Truth (separate repo)
    │
    │ Source / Proof / Permission / PD State
    ▼
X-SuperPlay-ContentOps  ← THIS REPO
= Executable Content Production Runtime
    │
    ├── SourceArtifact ingestion
    ├── Evidence + Claim binding
    ├── Content Brief → Master Script → Storyboard
    ├── Asset planning (real first, generated second)
    ├── Media generation (MiniMax subscription, when implemented)
    ├── Voice synthesis
    ├── Video composition (Easel assemble.py)
    ├── Automated QC
    ├── Human Review gate
    └── Receipts (full provenance)
    │
    ▼
Easel v0.2.1 (pinned upstream)
= Content Workflow / Skill Engine
    ├── tts.py (edge-tts wrapper)
    ├── auto-short-video/scripts/assemble.py
    └── 114 Skills (discover/plan/produce/publish/attribute)
    │
    ▼
FFmpeg / deterministic tools
= Rendering / Media Utilities
```

## Component Map

```
scripts/
├── run_v1.py            ← Pipeline orchestrator (easel + fallback engines)
├── assemble_easel.py    ← Easel orchestration adapter (Windows subtitle workaround)
├── qc_video.py          ← Automated QC gate (technical + evidence-first)
├── resolve_easel.py    ← Single runtime resolver (rejects unpinned/foreign)
├── verify_easel_runtime.py ← Content hash verification
├── doctor.py            ← Environment checker
├── bootstrap.ps1/.sh    ← Environment setup
├── new_project.py       ← Project scaffolding
└── test_basic.py        ← Current test suite (9 tests)

runtime/
├── easel.lock.json      ← Canonical Easel pin (machine-readable)
└── easel-runtime.json   ← Provenance record

projects/<slug>/
├── project.yaml         ← Project metadata
├── sources/             ← Real evidence (screenshots, diagrams, docs)
├── script/              ← Master script + storyboard
├── assets/              ← Voice, captions, generated assets
├── work/                ← Intermediate renders (gitignored)
├── final/               ← Output MP4s (gitignored)
└── receipts/            ← Build, QC, runtime, human review receipts

templates/               ← Project and video templates
```

## Pipeline Flow

```
Business Repo / Experiment / Research
         ↓
   SourceArtifact (planned: RepoSourceAdapter)
         ↓
   Evidence + Claim Ledger (planned)
         ↓
   Content Brief → Master Script
         ↓
   Storyboard (per-shot: purpose, narration, source, provenance)
         ↓
   Asset Plan (real first, generated second)
         ↓
   Voice synthesis (current: edge-tts → planned: MiniMax subscription)
         ↓
   Easel auto-short-video/assemble.py (upstream, unmodified)
         ↓
   FFmpeg subtitle burn (Windows path workaround)
         ↓
   final.mp4
         ↓
   Automated QC (scripts/qc_video.py)
         ↓
   Human Review gate (100-point scorecard)
         ↓
   PRODUCTION_READY (only with Founder approval)
```

## Extension Priority

```
ADAPTER     → wrap external API without modifying upstream
EXTENSION   → add new module in X-SuperPlay-owned space
CUSTOM SKILL → add Easel skill in extensions/ or skills/
UPSTREAM PATCH → modify Easel source (requires patch file + tests)
FORK        → last resort only
```

Current: No fork. No upstream modification. `assemble_easel.py` is an ADAPTER (orchestration workaround, not source edit).

## What ContentOps Does NOT Own

- Business judgment (stays in OPC Blueprint)
- Commercial facts (stays in OPC)
- Platform publishing (stays manual, human-gated)
- Metrics scraping (not yet implemented)
- Auto-publishing (explicitly out of scope)
