# Architecture

[English](ARCHITECTURE.md) | [简体中文](ARCHITECTURE.zh-CN.md)

> What the system is. Where the boundaries are. How components call each other.
> Describes the target architecture after the 2026-11-02 host decision, and
> marks what is verified today. A target section is not a running capability.

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
Easel v0.2.1 (pinned upstream, guarded)
= Content Production Host (target base, ADR-016)
    ├── EXECUTED HERE TODAY
    │   ├── auto-short-video/scripts/assemble.py   ← composition
    │   └── tts.py                                 ← V1 narration only; M5 uses Windows SAPI
    └── TARGET HOST SURFACE, NOT YET RUNNING
        └── agent, web workbench, 114 skills, profiles/, outputs/ and publishing
    │
    ▼
src/contentops/easel/
= Deny-by-default host boundary
    ├── loopback-only bind (127.0.0.1)
    ├── read-only allowlist
    └── HOST_BLOCKED until runtime and dependencies are reviewed
    │
    ▼
FFmpeg / deterministic tools
= Rendering / Media Utilities
```

## Host Adoption (ADR-016)

The Owner decided on 2026-11-02 to adopt the full Easel system as the
production base, superseding ADR-015 D1. The verified runtime today is still
the pinned v0.2.1 checkout; the workbench/agent surface is **target**, not a
running integration.

| Fact | State |
|---|---|
| Pinned upstream | v0.2.1, commit `3fe2d99`, read-only |
| Host entry point | `scripts/easel_host.py` only |
| Bind | `127.0.0.1`; upstream `0.0.0.0` is not used |
| Methods | `GET`, `HEAD`, `OPTIONS` only |
| Mutations | denied before upstream (publish, login, credentials, settings, env install, delete) |
| Current host status | `HOST_BLOCKED` on this machine until FastAPI/uvicorn are present and a host-security review is recorded |
| What the host does not carry | approval, publication authority, provider spend, account access |

The guard is a policy boundary, not an OS sandbox. A host that is merely
running is not evidence that a content package is approved. See
[ADR-016](adr/ADR-016-easel-host-adoption.md).

## Production Lines

Two lines share the evidence and review machinery, then diverge into their own
production flow. They diverge before the render step: a video script and a graphic
outline are already different objects.

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
   for an article. It runs `contentops.copy-to-graphic/v1`
   (`brief → outline → draft → images → layout → quality → delivery`) and reuses the
   gate's ordering, fingerprint invalidation and human approval rather than forking them.
   Its current product is a **manual package** (`scripts/graphic_package.py`) that stops
   at `AWAITING_MANUAL_REVIEW`; it is not an HTML renderer or a WeChat publisher.
4. **Platform adapters are delivery, not production.** A platform never gets its own
   production engine. See §What ContentOps Does NOT Own.
5. **Shared engine extraction is earned, not assumed.** A common abstraction over the two
   lines is justified only when real duplicated code exists in both.
6. **One Bundle, two handoffs, no shared approval.** `src/contentops/content_kernel/handoff.py`
   validates a Strategy Bundle and writes a form-specific handoff. Both handoffs carry the
   same `bundle_sha256` and source mapping; neither carries `publish_authorized: true`, and
   the graphic package never inherits the video's review.
7. **A coding agent drives through a plan, not a shell.** `src/contentops/easel/driver.py`
   exposes an ordered step list with fixed argv, `READ` / `PRODUCE` / `HUMAN_ONLY`
   authorities, and a receipt per execution. There is no publish, credential or install
   step, and `human-review` is refused when a driver asks for it (ADR-017).

## Branch Layers

The repository is mid-convergence. A component is only "part of the system" if it
is on `main`.

| Layer | Where it lives | Status on `main` |
|---|---|---|
| M5 evidence chain, media, QC, skill router/authorization | `main` (PR #89) | implemented |
| X post gate, growth→editorial gate | `main` (PRs #87, #88) | implemented |
| Account-aware content router, workflow gates, brief/script/design stages | `main` (S1 #93, S2 #95) + Issue #94 for S3–S4 | **partial** — the account/brief front-end and stage gate are on `main`; remaining stages are sliced |
| Platform registry + Content Bundle intake | PR #101 / Issue #100 | **pending review**; reused, not duplicated |
| Easel host guard, Bundle handoff, graphic package | Issue #106 (this branch) | **implemented offline**; host `HOST_BLOCKED` until dependencies and security review |
| XHS eight-step workflow | `feat/xhs-fa-migration` | **unmerged** |
| X platform track (migrated records, prompt references, table gate) | Issue #47 (PR #50 closed as superseded) | **unmerged** |
| GZH ten-stage vendored workflow | local `vendor/` + Issue #56 | **unmerged / rights-blocked** |

[CONVERGENCE-REQUIREMENTS-2026-11-01.md](CONVERGENCE-REQUIREMENTS-2026-11-01.md)
defines the merge order. A skill that references an unmerged layer is declared
as such in [SKILL-REGISTRY.md](SKILL-REGISTRY.md); it is not presented as
runnable here.

## Component Map

```text
scripts/
├── run_v1.py             ← V1 orchestrator (easel + fallback engines)
├── m5_production.py      ← Evidence-first chain (sources → … → review)
├── bundle_handoff.py     ← Bundle → VIDEO / GRAPHIC_TEXT plan
├── graphic_package.py    ← Manual graphic package (stops at review)
├── easel_host.py         ← Guarded host status / loopback serve
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
├── content_kernel/       ← Bundle validation + form-specific handoff
├── easel/                ← Host guard, loopback lifecycle, coding-agent driver
├── graphic/              ← Manual graphic package + rights-bound images
├── platforms/            ← The one machine-readable platform registry
├── workflow/             ← Video + graphic ordered stages and human gate
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

`workflow/` contains the merged S1/S2 contract and gate, plus this branch's
graphic contract. `platforms/` and `content_kernel/` exist through PR #101 and
are reused here, not duplicated. `routing/`, `quality/`, `script/`,
`hotspots/` and `optimization/` remain incomplete slices from Issue #94; a
directory existing is not proof that its stages are wired.

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

## Platform Registry and Content Bundle

Two contracts sit between production and delivery. Neither renders, publishes or
spends (ADR-015).

```
config/registry/platforms.json              ← contentops.platform-registry/v1 (data)
src/contentops/platforms/registry.py        ← the only loader and validator
scripts/platforms.py                        ← list | accounts | resolve | check
docs/PLATFORM-INTEGRATION-STATUS.md         ← human-readable mirror, same PR

Strategy Content Bundle (YAML, Strategy-owned)
src/contentops/content_kernel/bundle.py     ← consumption-side validation only
scripts/content_bundle.py                   ← check | summary
```

**The platform registry describes this branch, not the portfolio.** A row says
what code exists here, what it can produce, and what blocks it. `PLANNED` means
no platform code; `INTEGRATED` means code plus offline tests; a non-`PLANNED`
row must carry evidence. Status is a claim about evidence and is never upgraded
because an account exists, a render passed, or a configuration was written.
GitHub is proof infrastructure and is documented instead of registered, because
it has no pipeline, account or publish target to declare.

**The Content Bundle is a plan.** Strategy owns the template, the thesis, the
account treatments, the production lane (`baseline | enhanced | experimental`)
and the execution-profile hint (`default | strict_evidence`). ContentOps checks
that a Bundle is intact before consuming it: identity shape, claim binding for
`direct_evidence`, the four fail-closed invariants, and credential-shaped
fields. It never re-derives a thesis or turns a Bundle into published content.

Ownership across repositories is unchanged: Strategy decides what, ContentOps
owns execution evidence and receipts, platform execution repositories keep their
production authority until a separate approved migration, and commercial truth
stays in OPC.

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
