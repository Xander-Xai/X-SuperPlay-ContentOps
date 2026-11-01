# Architecture

[English](ARCHITECTURE.md) | [简体中文](ARCHITECTURE.zh-CN.md)

> What the system is. Where the boundaries are. How components call each other.
> Describes `main` (2026-11-01, after PR #89 merged), not a future branch.

## System Boundaries

```text
X-SuperPlay-OPC-Blueprint
= Business Source of Truth (separate repo)
    │
    │ Source / Proof / Permission / PD State
    ▼
X-SuperPlay-ContentOps  ← THIS REPO
= Executable Content Production Runtime
    │
    ├── SourceArtifact ingestion          (implemented, M5)
    ├── Evidence + Claim binding          (implemented, M5)
    ├── Script → Storyboard                (implemented, M5 / V1)
    ├── Asset planning + media-use         (implemented, M4.5 / M5)
    ├── Media generation (MiniMax)         (implemented, verified subsets)
    ├── Voice synthesis                    (edge-tts, Windows SAPI)
    ├── Video composition (Easel adapter)  (implemented)
    ├── Automated QC                       (implemented)
    ├── Human Review gate                  (implemented, never auto-approved)
    └── Receipts (full provenance)         (implemented)
    │
    ▼
Easel v0.2.1 (pinned upstream)
= Content Workflow / Skill Engine
    ├── tts.py (edge-tts wrapper)
    ├── auto-short-video/scripts/assemble.py
    └── 114 Skills
    │
    ▼
FFmpeg / deterministic tools
= Rendering / Media Utilities
```

## Production Lines

Two lines share everything upstream of the render step and split at it.

```text
               shared
    account positioning → topic → Brief
                  │
        SourceArtifact + ClaimLedger          (permission-aware evidence)
                  │
            rights check (Rights Gate)
                  │
        ┌─────────┴─────────┐
        │                   │
   VIDEO LINE          GRAPHIC LINE
   script              outline / draft
   storyboard          platform adapt
   voice / subtitles   images / cards
   compose (Easel)     layout (HTML/MD)
   video QC            graphic QC
        │                   │
        └─────────┬─────────┘
                  │
          human review gate
                  │
        delivery package + receipt
                  │
     ┌────────────┴────────────┐
  抖音 · 视频号 · B站        X · 小红书 · 公众号 · 知乎
                  │
        owner publishes by hand
                  │
        owner records the URL
```

Rules:

1. **One evidence layer.** Both lines read the same `SourceArtifact` and `ClaimLedger`.
   A corrected claim invalidates both lines' outputs, not just one.
2. **The video line is `contentops.copy-to-video/v1`.** Its stages (`script → audio →
   storyboard → assets → compose → quality`) are video-specific on purpose and are not
   renamed to look general.
3. **The graphic line does not reuse those stages.** Audio and storyboard have no meaning
   for an article. It defines its own shorter stage list and reuses the gate's existing
   checks — ordering, fingerprint invalidation, human approval — rather than forking them.
4. **Platform adapters are delivery, not production.** A platform never gets its own
   production engine. See §What ContentOps Does NOT Own.
5. **Shared engine extraction is earned, not assumed.** A common abstraction over the two
   lines is justified only when real duplicated code exists in both.

## Branch Layers

The repository is mid-convergence. A component is only "part of the system" if it
is on `main`.

| Layer | Where it lives | Status on `main` |
|---|---|---|
| M5 evidence chain, media, QC, skill router/authorization | `main` (PR #89) | implemented |
| X post gate, growth→editorial gate | `main` (PRs #87, #88) | implemented |
| Account-aware content router, workflow gates, brief/script/design stages | `feat/content-router` (PR #49) | **unmerged** |
| XHS eight-step workflow | `feat/xhs-fa-migration` | **unmerged** |
| X platform track (migrated records, prompt references, table gate) | `feat/47-x-platform-track` (PR #50) | **unmerged** |
| GZH ten-stage vendored workflow | local `vendor/` + `fix/56-gzh-provenance` (PR #58) | **unmerged / rights-blocked** |

[CONVERGENCE-REQUIREMENTS-2026-11-01.md](CONVERGENCE-REQUIREMENTS-2026-11-01.md)
defines the merge order. A skill that references an unmerged layer is declared
as such in [SKILL-REGISTRY.md](SKILL-REGISTRY.md); it is not presented as
runnable here.

## Component Map

```text
scripts/
├── run_v1.py             ← V1 orchestrator (easel + fallback engines)
├── m5_production.py      ← Evidence-first chain (sources → … → review)
├── assemble_easel.py     ← Easel orchestration adapter (Windows subtitle workaround)
├── qc_video.py           ← Automated technical + evidence QC
├── resolve_easel.py      ← Single runtime resolver
├── verify_easel_runtime.py ← Content-hash verification
├── doctor.py             ← Environment checker
├── process_utils.py      ← Hidden-window subprocess layer
├── media_use_adapter.py  ← media-use operator CLI
├── media_use_runtime.py  ← approved baseline / install / lock / verify
├── skill_route.py        ← discovery + rights-aware resolution (no execution)
├── skill_execute.py      ← managed execution through a trusted grant
├── dev_check.py          ← unified local gate
└── test_basic.py         ← script-level smoke suite

src/contentops/
├── evidence/             ← SourceArtifact, ClaimLedger
├── media/                ← contracts, billing, providers, manifest, validation,
│                           transform, QC canonicalization, rights gate, media-use
├── skills/               ← authorization, execution gate, grant source
└── golden/               ← Golden identity, evidence locks, review, A/B variants

runtime/
├── easel.lock.json               ← canonical Easel pin
├── easel-runtime.json            ← provenance record
├── media-use-runtime-baseline.json
├── media-use-package-lock.json
└── skill-registry.json           ← declared capabilities (media-use only)

projects/<slug>/
├── project.yaml          ← metadata + source_refs + media_use requests
├── sources/              ← real evidence
├── script/               ← master script, storyboard, claims
├── assets/               ← voice, captions, imported/generated assets
├── work/                 ← intermediate renders (gitignored)
├── final/                ← output MP4s (gitignored)
└── receipts/             ← build, QC, runtime, human-review receipts
```

The `src/contentops/{workflow,routing,platforms,quality,script,hotspots,optimization}`
directories exist only as empty `__pycache__` remnants on this branch. Their code
is on `feat/content-router`; do not treat the directories as implemented modules.

## Pipeline Flow

### V1 (storyboard-driven)

```
projects/<slug>/script/{master.md,storyboard.json}
  → resolve pinned Easel
  → voice (edge-tts via Easel tts.py)
  → Easel assemble.py
  → subtitle burn (assemble_easel adapter)
  → final/easel.mp4
  → qc_video
```

### M5 (evidence-first)

```
project.yaml source_refs
  → SourceArtifact (permission-gated)
  → ClaimLedger (quotes verified)
  → media_use stage (optional, local-only)
  → script → narration → subtitles → storyboard
  → MediaManifest (assets inventory + timeline)
  → pinned Easel compose
  → qc_video → human review
```

Both paths end at `PENDING_FOUNDER_REVIEW` with `production_ready: false`.

## Media Convergence

One `MediaManifest` is the sole asset list. `assets` is the inventory (it may hold
a source and its derived transform); `timeline` selects exactly one active asset
per placement. Composition reads the timeline, never the inventory.

All paths are logical (`project://`, `repo://`) and resolved at use. Absolute
host paths are refused in committed manifests and receipts. QC receipts are
canonicalized (`contentops.qc-canonical/v1`) with an explicit `currency` and
`graded_target`.

## media-use Integration (Issue #57)

`media-use` is a skill in the upstream HyperFrames repository (Apache-2.0). It is
consumed as a **pinned external dependency**, never copied into this repository
(ADR-008).

```
src/contentops/media/media_use_adapter.py  ← only module that knows the skill exists
scripts/media_use_adapter.py               ← operator CLI
   status | doctor | candidates | resolve | adopt | ingest | import | verify | demo
```

Two contract additions make the mapping honest:

- `AssetKind.LICENSED_EXTERNAL` — licensed third-party material. It is not a
  capture and not a model generation, so it is excluded from both
  `EVIDENCE_CAPABLE` and `GENERATED`.
- `MediaModality.AUDIO` — background music and sound effects. It is not
  narration, so it carries no `asset_kind` and can never be evidence.

Imports become `contentops.media-import/v1` sidecars and enter the single
`MediaManifest`. The skill's `.media/manifest.jsonl` is read only to look up a
record; it is never a second asset list.

Default posture is closed: no network, no paid provider, no cross-project reuse,
no forced provider. A trusted host lock must name the approved baseline; a clean
checkout is `BLOCKED / MISSING_RUNTIME` by design.

## Skill Routing and Execution

Three questions stay separate:

| Question | Layer | Who answers |
|---|---|---|
| What exists on this host? | discovery | `skill_route.py --list/--sources/--match` |
| May this be handed to an adapter? | resolution | `skill_route.py --resolve` + `runtime/skill-registry.json` |
| May it actually run? | execution | the adapter, runtime lock verifier, grant gate |

The router never authorizes execution. Every record carries
`execution_authorized: false`. A declaration points at code on this branch; a
skill whose code is unmerged is not declared.

## Extension Priority

```
ADAPTER     → wrap external API without modifying upstream
EXTENSION   → add new module in X-SuperPlay-owned space
CUSTOM SKILL → add Easel skill in extensions/ or skills/
UPSTREAM PATCH → modify Easel source (requires patch file + tests)
FORK        → last resort only
```

Current: no fork. No upstream modification. `assemble_easel.py` is an ADAPTER
(orchestration workaround, not a source edit).

## What ContentOps Does NOT Own

- Business judgment (stays in OPC Blueprint)
- Commercial facts (stays in OPC)
- Platform publishing (stays manual, human-gated)
- Metrics scraping (not implemented)
- Auto-publishing (explicitly out of scope)
