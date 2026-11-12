# Content Lifecycle Stages

> Canonical stage model for the content lifecycle. It maps each stage to its
> input, output, owner, current implementation state and receipt.
>
> A stage may have no executable code. It then stays a **placeholder** and must
> not emit a success receipt, a publication record or a metric.

> Status: reference — 2026-11-12.
> Last verified: 2026-11-12 on `main` at `c1da6dd`.
Related: [ARCHITECTURE.md](ARCHITECTURE.md), [PRD.md](PRD.md),
[ADR-015](adr/ADR-015-platform-placeholders-and-content-bundle.md),
[ADR-016](adr/ADR-016-easel-host-adoption.md),
[PLATFORM-ADAPTER-CONTRACT.md](PLATFORM-ADAPTER-CONTRACT.md),
[EASEL-CAPABILITY-INVENTORY.md](EASEL-CAPABILITY-INVENTORY.md)

## Branch status (read this first)

Every `implemented` in the table below means **on `main`** (`c1da6dd`), not on a
parallel branch. The router, platform registry, Bundle kernel and graphic package
landed through PRs #101, #114 and #118; rendering, gates and both delivery runners
landed through #141–#157. Rights and the absence of a bound public account, not
code, are what block the platform tracks. Two corrections worth carrying:

- The **XHS runtime adapter was removed on 2026-11-09** with the graphic workflow.
  `src/contentops/xhs/` is empty and `scripts/graphic_workflow.py` names only
  `gzh`, `x` and `video`; the `xiaohongshu_video` registry row and its delivery
  channel remain, and both stay `PLANNED`.
- The **X and GZH adapters verify and never execute**. GZH additionally has a
  renderer, an SDK adapter, a workflow runner and a `DRAFT_ONLY` draft path.

## Position

`ARCHITECTURE.md` owns the system boundaries and the two production lines. This
file owns the **ordered lifecycle** and the **status of each stage**. It does not
redefine a contract; it maps the existing ones.

```text
DISCOVERY → RESEARCH → PRECOPY_RESEARCH → BRIEF → CONTENT_BUNDLE → PRODUCTION
    → QUALITY_REVIEW → PLATFORM_PACKAGING → PUBLISH_HANDOFF
    → METRICS_COLLECTION → ANALYSIS → LEARNING_FEEDBACK
    → back to Strategy
```

`PRODUCTION` splits into two lines, which diverge before the render step:

- **VIDEO**: `script → audio → storyboard → assets → compose → quality`
  (`contentops.copy-to-video/v1`)
- **GRAPHIC_TEXT**: `brief → outline → draft → images → layout → quality → delivery`
  (`contentops.copy-to-graphic/v1`)

Both lines share one upstream gate: `PRECOPY_RESEARCH` must be signed before
`script/master.md` or `02_draft/draft.md` exists
(`contentops.precopy-research/v1`, see
[PRECOPY-RESEARCH.md](PRECOPY-RESEARCH.md)). The research package is bound to
the `ContentIntent` that `DISCOVERY` produced, so the gate proves *which*
topic's evidence was verified — not merely that some research happened.

## Stage status

Status vocabulary: `implemented` (code runs on this branch), `partial` (some
pieces exist), `unmerged` (code on another branch), `planned` (placeholder). A
fact about another branch is stated in the Branch column, never folded into this
one's status.

| Stage | Input | Output | Owner | Status | Adapter / code | Receipt | Blocker |
|---|---|---|---|---|---|---|---|
| `DISCOVERY` | Strategy direction, trends | topic candidates | Strategy + ContentOps | `implemented` | `src/contentops/routing/` (`user_topic_route`, `hotspot_route`), `src/contentops/hotspots/` | route result | hot-list collection needs network and credentials; offline runs are `BLOCKED` |
| `RESEARCH` | topic, sources | `SourceArtifact` set | ContentOps | `partial` | M5 `src/contentops/evidence/`; `x-superplay-source-research` is not declared on `main` | source records | source research still starts from manual `SourceArtifact` input |
| `PRECOPY_RESEARCH` | `ContentIntent`, verified sources | research package + signed receipt | ContentOps + human | `implemented` | `src/contentops/workflow/preresearch.py`, `scripts/preresearch.py` | `receipts/precopy-research.json` | 8th VIDEO / 6th GRAPHIC_TEXT gate; no `--force`; edits after signing report `STALE` |
| `BRIEF` | topic, audience | brief | ContentOps | `implemented` | router `src/contentops/routing/brief.py`; graphic contract `brief` stage | `BRIEF_READY` result | an automation approval is refused by the brief→M5 bridge; a human must approve |
| `CONTENT_BUNDLE` | Strategy Bundle | validated Bundle + digest | Strategy owns; ContentOps consumes | `implemented` (on `main`; PR #101) | `src/contentops/content_kernel/bundle.py`, `scripts/content_bundle.py` | validation result / handoff | Bundle is a plan, never a publication |
| `PRODUCTION` (VIDEO) | Bundle, claims | video master | ContentOps | `implemented` | gated entry `scripts/make_content.py` + `scripts/production_gates.py` (8 VIDEO gates); `produce_video.py` / `m5_production.py`, `run_v1.py`, `assemble_easel.py`; ASR backcheck stage | `build-*.json`, `asr-backcheck.json`, `runtime-receipt.md` | voice quality; human review pending. A direct producer run is diagnostic and not gate-checked |
| `PRODUCTION` (GRAPHIC_TEXT) | Bundle, images | manual package, rendered cards, validated article | ContentOps | `implemented` | `src/contentops/graphic/` (package, cards, articles), `scripts/graphic_package.py`, `render_cards.py`, `render_article.py`; 6 GRAPHIC_TEXT gates | `graphic-package.json`, `card-render.json`, `gzh-article.json` | every terminal state is `AWAITING_MANUAL_REVIEW` or `BLOCKED`; a PASS is not an approval |
| `QUALITY_REVIEW` | produced artifacts | QC + human verdict | ContentOps + human | `implemented` | `production_gates.py` preflight, `scripts/qc_video.py`, `qc_visual.py`, ASR backcheck, `src/contentops/media/quality_gate.py`, `workflow/gate.py` | `qc-report.json`, `human-review.json` | human review never auto-approved; no project holds an APPROVED `human-review.json` |
| `PLATFORM_PACKAGING` | reviewed package | per-platform pack + draft | ContentOps | `partial` | `scripts/video_deliver.py` (`plan`/`pack`/`status`), `scripts/platform_delivery.py`, `graphic_deliver.py`, `wechatsync_browser.py`; X manual gate (`src/contentops/publish/`) | `06_delivery/` pack receipts, `graphic-package.json` | packs are implemented, but **no platform draft has ever been created**: 0 delivery receipts, 8 of 9 registry rows `PLANNED` |
| `PUBLISH_HANDOFF` | draft | real URL + delivery receipt | human | `partial` | human-only: `video_deliver.py record`, `x_post.py --mark-published`, and the bridge's own URL echo | `AWAITING_MANUAL_PUBLISH` / `REPORTED_PUBLISHED` / `UPLOADER_EXIT_0` | no automatic publication, 0 recorded URLs; an uploader exit is not a published claim |
| `METRICS_COLLECTION` | delivery receipt | metric snapshot | ContentOps | `partial` | `scripts/wechat_metrics.py` (data cube), `scripts/bilibili_metrics.py` (public counters), offline X metric analysis; all operator-gated | metric receipts | no automatic collection; a missing metric is `NONE`, never zero |
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
| `contentops.precopy-research/v1` | `src/contentops/workflow/preresearch.py` |
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
10. **Copy never precedes research.** Before `script/master.md`,
    `02_draft/draft.md` or any copy decision, `PRECOPY_RESEARCH` must be
    `APPROVED`: bind the router's `ContentIntent`, read the relevant project
    files, verify authoritative sources, write an outline, an evidence list and
    a boundary statement, and obtain a named human signature.
    `production_gates.py` and `copy_review.py --approve` both fail closed.
    Changing a research artifact — or re-routing the topic — makes the approval
    `STALE` or `INCOMPLETE`; there is no `--force` and no silent grandfathering.
    See [PRECOPY-RESEARCH.md](PRECOPY-RESEARCH.md).

## Remaining placeholders and non-implemented capabilities

This section describes gaps on `main` as of 2026-11-12. The router, brief,
script, hotspot and platform code is present; it is not an unmerged layer.

- Cross-stage metric collection and a real metric snapshot are not implemented.
  X has an offline analyzer for manually supplied snapshots, not a platform
  collector or a Strategy feedback loop.
- A general analysis stage and written learning-feedback loop are not
  implemented.
- The X adapter is manual-only. The GZH adapter verifies and describes an
  external workspace; it does not execute production or publishing. The XHS
  runtime adapter was removed on 2026-11-09 and has no replacement — only its
  registry row and video delivery channel remain. Other platform rows remain
  placeholders in the single platform registry.
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
