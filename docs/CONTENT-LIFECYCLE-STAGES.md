# Content Lifecycle Stages

> Canonical stage model for the content lifecycle. It maps each stage to its
> input, output, owner, current implementation state and receipt.
>
> A stage may have no executable code. It then stays a **placeholder** and must
> not emit a success receipt, a publication record or a metric.

Status: reference — 2026-11-04
Related: [ARCHITECTURE.md](ARCHITECTURE.md), [PRD.md](PRD.md),
[ADR-015](adr/ADR-015-platform-placeholders-and-content-bundle.md),
[ADR-016](adr/ADR-016-easel-host-adoption.md),
[PLATFORM-ADAPTER-CONTRACT.md](PLATFORM-ADAPTER-CONTRACT.md),
[EASEL-CAPABILITY-INVENTORY.md](EASEL-CAPABILITY-INVENTORY.md)

## Branch status (read this first)

Every `implemented` in the table below means **on `main`** (`218c91d`), not on a
parallel branch. The router, platform registry, Bundle kernel and graphic package
landed through PRs #101, #114 and #118. Rights, not code, is what blocks the
platform tracks: every XHS/X/GZH adapter on `main` verifies and never executes.

## Position

`ARCHITECTURE.md` owns the system boundaries and the two production lines. This
file owns the **ordered lifecycle** and the **status of each stage**. It does not
redefine a contract; it maps the existing ones.

```text
DISCOVERY → RESEARCH → BRIEF → CONTENT_BUNDLE → PRODUCTION
    → QUALITY_REVIEW → PLATFORM_PACKAGING → PUBLISH_HANDOFF
    → METRICS_COLLECTION → ANALYSIS → LEARNING_FEEDBACK
    → back to Strategy
```

`PRODUCTION` splits into two lines, which diverge before the render step:

- **VIDEO**: `script → audio → storyboard → assets → compose → quality`
  (`contentops.copy-to-video/v1`)
- **GRAPHIC_TEXT**: `brief → outline → draft → images → layout → quality → delivery`
  (`contentops.copy-to-graphic/v1`)

## Stage status

Status vocabulary: `implemented` (code runs on this branch), `partial` (some
pieces exist), `unmerged` (code on another branch), `planned` (placeholder). A
fact about another branch is stated in the Branch column, never folded into this
one's status.

| Stage | Input | Output | Owner | Status | Adapter / code | Receipt | Blocker |
|---|---|---|---|---|---|---|---|
| `DISCOVERY` | Strategy direction, trends | topic candidates | Strategy + ContentOps | `implemented` | `src/contentops/routing/` (`user_topic_route`, `hotspot_route`), `src/contentops/hotspots/` | route result | hot-list collection needs network and credentials; offline runs are `BLOCKED` |
| `RESEARCH` | topic, sources | `SourceArtifact` set | ContentOps | `partial` | M5 `src/contentops/evidence/`; `x-superplay-source-research` is not declared on `main` | source records | source research still starts from manual `SourceArtifact` input |
| `BRIEF` | topic, audience | brief | ContentOps | `implemented` | router `src/contentops/routing/brief.py`; graphic contract `brief` stage | `BRIEF_READY` result | an automation approval is refused by the brief→M5 bridge; a human must approve |
| `CONTENT_BUNDLE` | Strategy Bundle | validated Bundle + digest | Strategy owns; ContentOps consumes | `implemented` (on `main`; PR #101) | `src/contentops/content_kernel/bundle.py`, `scripts/content_bundle.py` | validation result / handoff | Bundle is a plan, never a publication |
| `PRODUCTION` (VIDEO) | Bundle, claims | video master | ContentOps | `implemented` | M5 `scripts/m5_production.py`, `run_v1.py`, `assemble_easel.py` | `build-*.json`, `runtime-receipt.md` | voice quality; human review pending |
| `PRODUCTION` (GRAPHIC_TEXT) | Bundle, images | manual package | ContentOps | `implemented` | `src/contentops/graphic/package.py`, `scripts/graphic_package.py` | `graphic-package.json` | terminal `AWAITING_MANUAL_REVIEW` |
| `QUALITY_REVIEW` | produced artifacts | QC + human verdict | ContentOps + human | `implemented` | `scripts/qc_video.py`, `qc_visual.py`, `src/contentops/media/quality_gate.py`, `workflow/gate.py` | `qc-report.json`, `human-review.json` | human review never auto-approved |
| `PLATFORM_PACKAGING` | reviewed package | platform draft | ContentOps | `partial` | X manual gate only (`src/contentops/publish/`) | X package receipt | 9 of 10 registry rows remain `PLANNED`; X is the sole `INTEGRATED` row |
| `PUBLISH_HANDOFF` | draft | real URL + delivery receipt | human | `partial` | manual only; `x_post.py --mark-published` records a URL a person already has (as `REPORTED_PUBLISHED`) | `AWAITING_MANUAL_PUBLISH` / `REPORTED_PUBLISHED` | no automatic publication; no external verification path yet |
| `METRICS_COLLECTION` | delivery receipt | metric snapshot | ContentOps | `planned` | none | none | `metrics: NONE`; not implemented |
| `ANALYSIS` | metric snapshots | findings | ContentOps | `partial` | X organic-growth advisory (`x_organic_growth.py`), offline | advisory JSON | general analysis not implemented |
| `LEARNING_FEEDBACK` | findings | next-cycle guidance | Strategy | `planned` | none | none | no loop back to Strategy yet |

## Production profile vs medium

Two independent axes must not be conflated:

| Axis | Values | Owner |
|---|---|---|
| **Medium** (production line) | `VIDEO`, `GRAPHIC_TEXT` | ContentOps |
| **Production profile** (cost / complexity lane) | `baseline`, `enhanced`, `experimental` | Strategy |

A profile is not a medium, and a medium is not a profile. `XHS_EDITORIAL` and
`GZH_EDITORIAL` are local content-type labels that map onto the shared
`GRAPHIC_TEXT` line; they do not create a third production line.

## Contract mapping

| Contract | Owner file |
|---|---|
| `contentops.copy-to-video/v1` | `src/contentops/workflow/contract.py` |
| `contentops.copy-to-graphic/v1` | `src/contentops/workflow/contract.py` |
| `contentops.bundle-handoff/v1` | `src/contentops/content_kernel/handoff.py` |
| `contentops.graphic-package/v1` | `src/contentops/graphic/package.py` |
| `contentops.qc-canonical/v1` | `src/contentops/media/qc_canonical.py` |
| `contentops.platform-registry/v1` | `config/registry/platforms.json` |

## Rules

1. **One stage, one status.** A stage with no code is a placeholder and returns
   no success receipt.
2. **No stage claims a later stage.** A production receipt is not a publication;
   a draft is not a publish; a publish is not a metric.
3. **Human review is never auto-approved.** `production_ready` stays `false`
   until a person writes `human-review.json`.
4. **Metrics are evidence.** Absent metrics are `NONE`, never zero and never a
   price derived from a quota percentage.
5. **The feedback loop belongs to Strategy.** ContentOps reports findings; it
   does not re-derive the thesis or re-choose the platform.
6. **A gate has no `--force`.** `workflow/gate.py` `approve` requires a fresh
   successful `check`, a named reviewer and explicit confirmation.
7. **A hand-entered URL is `REPORTED_PUBLISHED`, not verified evidence** (see
   [PLATFORM-ADAPTER-CONTRACT.md](PLATFORM-ADAPTER-CONTRACT.md)). Only external
   verification produces `VERIFIED_PUBLISHED`.
8. **`PRODUCTION_ACCEPTED` is never automatic.** It requires external
   verification (`VERIFIED_PUBLISHED`), a written human approval, and a complete
   delivery receipt — all three together. `REPORTED_PUBLISHED` alone upgrades
   nothing.
9. **X editorial content production lives in `src/contentops/publish/`** —
   `x_text.py`, `x_image.py` and `x_editorial.py` are the authoring components;
   the X gate is their packaging stage. There is no `copy-to-x` contract and no
   third production engine.

## Remaining placeholders and non-implemented capabilities

This section describes gaps on `main` as of 2026-11-04. The router, brief,
script, hotspot and optimization code is present; it is not an unmerged layer.

- Cross-stage metric collection and a real metric snapshot are not implemented.
  X has an offline analyzer for manually supplied snapshots, not a platform
  collector or a Strategy feedback loop.
- A general analysis stage and written learning-feedback loop are not
  implemented.
- The X adapter is manual-only. GZH and XHS adapters on `main` verify and
  describe external workspaces; they do not execute production or publishing.
  Other platform rows remain placeholders in the single platform registry.
- The five `x-superplay-*` skills are not declared as executable capabilities.
  `runtime/content-skill-status.json` records missing referenced paths; this is
  separate from the merged router and stage code.

## Next actions

1. The main-branch Brief-to-M5 path still needs a human copy-review command. A
   fingerprint-bound CLI implementation and regression tests are present in the
   current convergence branch, but are not yet part of `main`.
2. Complete the first real manual delivery, including a verifiable URL and
   manually sourced metric snapshot, before expanding platform automation.
3. Resolve GZH/XHS rights and acceptance independently; a successful workspace
   verification does not grant execution or publication authority.
