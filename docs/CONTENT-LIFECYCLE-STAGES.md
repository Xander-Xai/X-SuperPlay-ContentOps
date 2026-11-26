# Content Lifecycle Stages

> Canonical stage model for the content lifecycle. It maps each stage to its
> input, output, owner, current implementation state and receipt.
>
> A stage may have no executable code. It then stays a **placeholder** and must
> not emit a success receipt, a publication record or a metric.

> Status: reference — 2026-11-12.
> Last verified: 2026-11-18 against current platform routes and constraints.
> Last verified: 2026-11-14. The X ORIGINAL_POST path now validates explicit text or image format, content-mode review profiles and human-only package handoff; image records require raster+ALT and text records carry neither. No live account growth or platform publication is verified.
> Last verified: 2026-11-23 on `feat/208-shared-graphic-workflow`; standalone GRAPHIC_TEXT no longer requires signed pre-copy or copy-review steps before preparation. Focused production-gate tests 39/39 and pre-copy tests 26/26 passed.
> Local feedback remains PARTIAL: manually supplied metrics -> learning brief -> human-approved Topic route; not automated publishing.
Related: [ARCHITECTURE.md](ARCHITECTURE.md), [PRD.md](PRD.md),
[ADR-015](adr/ADR-015-platform-placeholders-and-content-bundle.md),
[ADR-016](adr/ADR-016-easel-host-adoption.md),
[PLATFORM-ADAPTER-CONTRACT.md](PLATFORM-ADAPTER-CONTRACT.md),
[EASEL-CAPABILITY-INVENTORY.md](EASEL-CAPABILITY-INVENTORY.md)

## Branch status and historical baseline

The older main snapshot in the table below is historical, not a statement of the
current branch. The router, platform registry, Bundle kernel and graphic package
landed through PRs #101, #114 and #118; rendering, gates and both delivery runners
landed through #141–#157. The signed pre-copy research gate (`contentops.precopy-research/v1`)
is also merged and is enforced before copy in both VIDEO and GRAPHIC_TEXT lines;
it is the eighth VIDEO gate and the sixth GRAPHIC_TEXT gate. It establishes
research approval only—not copy approval, production readiness or publication.
Current execution evidence and blockers remain governed by the stage table below;
no runtime or publication capability is inferred from this historical snapshot.

Two corrections worth carrying:

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
DISCOVERY → RESEARCH → PRECOPY_RESEARCH → BRIEF → CONTENT_BUNDLE
    → CANONICAL_COPY (shared when a topic targets both formats) → PRODUCTION
    → QUALITY_REVIEW → PLATFORM_PACKAGING → PUBLISH_HANDOFF
    → METRICS_COLLECTION → ANALYSIS → LEARNING_FEEDBACK
    → back to Strategy
```

`PRODUCTION` splits into two lines, which diverge before the render step:

- **VIDEO**: `script → audio → storyboard → assets → compose → quality`
  (`contentops.copy-to-video/v1`)
- **GRAPHIC_TEXT**: `brief → outline → draft → images → layout → quality → delivery`
  (`contentops.copy-to-graphic/v1`)

The signed `PRECOPY_RESEARCH` gate applies before VIDEO copy and shared,
medium-neutral `TOPIC` approval (`contentops.precopy-research/v1`, see
[PRECOPY-RESEARCH.md](PRECOPY-RESEARCH.md)). A standalone GRAPHIC_TEXT draft may
start without that signature; it still needs traceable source links and image
rights before package delivery. The shared research package remains bound to the
`ContentIntent` that `DISCOVERY` produced, so it proves *which* topic's evidence
was reviewed—not merely that some research happened.

When one selected topic is intended for both VIDEO and GRAPHIC_TEXT, route it as
one medium-neutral `TOPIC` intent. The topic project owns the signed research,
`00_brief/canonical-copy.json`, and its human review; `topic-package.json` binds
them into one authority package. Separate sibling production projects carry a
root-scoped package reference and digest, then create their own
`00_brief/copy-derivative.json` and format copy (`script/master.md` or `draft.md`).
Each format adaptation is separately human-reviewed, and the shared package is
re-read at production gates. Structural checks establish lineage, not semantic
equivalence; reviewers remain responsible for stronger wording, omissions and
new claims. Explicit legacy single-format projects keep their existing path.

## Stage status

Status vocabulary: `implemented` (code runs on this branch), `partial` (some
pieces exist), `unmerged` (code on another branch), `planned` (placeholder). A
fact about another branch is stated in the Branch column, never folded into this
one's status.

| Stage | Input | Output | Owner | Status | Adapter / code | Receipt | Blocker |
|---|---|---|---|---|---|---|---|
| `DISCOVERY` | Strategy direction, trends | topic candidates | Strategy + ContentOps | `implemented` | `src/contentops/routing/` (`user_topic_route`, `hotspot_route`), `src/contentops/hotspots/` | route result | hot-list collection needs network and credentials; offline runs are `BLOCKED` |
| `RESEARCH` | topic, sources | `SourceArtifact` set | ContentOps | `partial` | M5 `src/contentops/evidence/`; `x-superplay-source-research` is not declared on `main` | source records | source research still starts from manual `SourceArtifact` input |
| `PRECOPY_RESEARCH` | `ContentIntent`, verified sources | research package + signed receipt | ContentOps + human | `implemented` | `src/contentops/workflow/preresearch.py`, `scripts/preresearch.py` | `receipts/precopy-research.json` | VIDEO/shared TOPIC only; no `--force`; edits after signing report `STALE`; standalone GRAPHIC_TEXT is draft-first |
| `BRIEF` | topic, audience | brief | ContentOps | `implemented` | router `src/contentops/routing/brief.py`; graphic contract `brief` stage | `BRIEF_READY` result | an automation approval is refused by the brief→M5 bridge; a human must approve |
| `CONTENT_BUNDLE` | Strategy Bundle | validated Bundle + digest | Strategy owns; ContentOps consumes | `implemented` (on `main`; PR #101) | `src/contentops/content_kernel/bundle.py`, `scripts/content_bundle.py` | validation result / handoff | Bundle is a plan, never a publication |
| `CANONICAL_COPY` (shared topic) | medium-neutral `TOPIC` intent, signed research, one canonical source | one reviewed topic package plus independently reviewed format derivatives | shared copy Skill + human reviewers | `partial` (Issue #211) | `src/contentops/workflow/topic_package.py`, `canonical_copy.py`, `copy_review.py`; `scripts/topic_package.py` | `topic-package.json`, child `receipts/topic-package-ref.json`, `receipts/script-review.json` | package initialization and binding are operator-driven; current code validates lineage but cannot establish semantic equivalence |
| `PRODUCTION` (VIDEO) | Bundle, claims | video master | ContentOps | `implemented` | gated entry `scripts/make_content.py` + `scripts/production_gates.py` (8 VIDEO gates); `produce_video.py` / `m5_production.py`, `run_v1.py`, `assemble_easel.py`; ASR backcheck stage | `build-*.json`, `asr-backcheck.json`, `runtime-receipt.md` | voice quality; human review pending. A direct producer run is diagnostic and not gate-checked |
| `PRODUCTION` (GRAPHIC_TEXT) | Bundle, images | generated support visuals + manual package, rendered cards, validated article | ContentOps | `implemented` (three generation routes on `feat/208-shared-graphic-workflow`; not merged) | `src/contentops/graphic/` (methods, generation receipts, package and rights checks), `scripts/graphic_generate.py`, `scripts/graphic_package.py`, `render_cards.py`, `render_article.py`; focused account/evidence/rights/runtime checks | `graphic-image-generation-*.json`, `graphic-package.json`, `card-render.json`, `gzh-article.json` | one live Codex smoke run passed the repaired adapter and wrote an image plus project-local generation receipt in a temporary workflow test project. This was not an approved article; article package, rights/AIGC review, layout/quality review and delivery remain unverified. Draft work can proceed before human research/copy sign-off; external delivery remains rights-gated. Terminal state remains `AWAITING_MANUAL_REVIEW` or `BLOCKED` |
| `QUALITY_REVIEW` | produced artifacts | QC + human verdict | ContentOps + human | `implemented` | `production_gates.py` preflight, `scripts/qc_video.py`, `qc_visual.py`, ASR backcheck, `src/contentops/media/quality_gate.py`, `workflow/gate.py` | `qc-report.json`, `human-review.json` | human review never auto-approved; no project holds an APPROVED `human-review.json` |
| `PLATFORM_PACKAGING` | reviewed package | per-platform pack + draft | ContentOps | `partial` | `scripts/video_deliver.py` (`plan`/`pack`/`status`), `scripts/platform_delivery.py`, `graphic_deliver.py`, `wechatsync_browser.py`; X manual gate (`src/contentops/publish/`) | `06_delivery/` pack receipts, `graphic-package.json` | packs are implemented, but **no platform draft has ever been created**: 0 delivery receipts, 8 of 9 registry rows `PLANNED` |
| `PUBLISH_HANDOFF` | draft | real URL + delivery receipt | human | `partial` | human-only: `video_deliver.py record`, `x_post.py --mark-published`, and the bridge's own URL echo | `AWAITING_MANUAL_PUBLISH` / `REPORTED_PUBLISHED` / `UPLOADER_EXIT_0` | no automatic publication, 0 recorded URLs; an uploader exit is not a published claim |
| `METRICS_COLLECTION` | delivery receipt | metric snapshot | ContentOps | `partial` | `scripts/wechat_metrics.py` (data cube), `scripts/bilibili_metrics.py` (public counters), offline X metric analysis; all operator-gated | metric receipts | no automatic collection; a missing metric is `NONE`, never zero |
| `ANALYSIS` | metric snapshots | findings | ContentOps | `partial` | X organic-growth advisory (`x_organic_growth.py`), offline | advisory JSON | general analysis not implemented |
| `LEARNING_FEEDBACK` | findings | next-cycle guidance | Strategy + human | `partial` | `scripts/x_learning_loop.py` (X) and `scripts/platform_learning_loop.py` (cross-platform, local-only); Strategy handoff document | local `learning/latest.json` / `learning/handoff.json` | operator-reviewed Topic routing exists; Strategy has no automatic writer, and no real cross-platform attribution proof |

## Production profile vs medium

Two independent axes must not be conflated:

| Axis | Values | Owner |
|---|---|---|
| **Medium** (production line) | `VIDEO`, `GRAPHIC_TEXT` | ContentOps |
| **Production profile** (cost / complexity lane) | `baseline`, `enhanced`, `experimental` | Strategy |

A profile is not a medium, and a medium is not a profile. `GZH_EDITORIAL`
is the local content-type label that maps onto the shared `GRAPHIC_TEXT` line;
it does not create a third production line. Xiaohongshu is VIDEO-only in this
repository; its image-text/graphic target is excluded and has no registry row.

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
10. **Evidence precedes factual claims; signatures are scoped.** VIDEO and shared
    `TOPIC` copy must have current `PRECOPY_RESEARCH` approval before production or
    copy approval. A standalone GRAPHIC_TEXT draft can start first; it must retain
    source links and mark unverified claims. `production_gates.py` keeps evidence
    and per-image rights checks, while external delivery remains separately gated.
    Changing shared research or re-routing its topic makes its approval `STALE` or
    `INCOMPLETE`; there is no `--force`. See
    [PRECOPY-RESEARCH.md](PRECOPY-RESEARCH.md).

## Remaining placeholders and non-implemented capabilities

This section describes gaps on `main` as of 2026-11-12. The router, brief,
script, hotspot and platform code is present; it is not an unmerged layer.

- Automatic cross-platform metric collection is not implemented. X and the generic local-only CSV analyzers operate on human-supplied snapshots; human-reviewed topic handoff can start the existing Router but cannot publish.
- The X offline source analysis and cross-platform local-only descriptive Learning Brief are implemented; no automatic cross-platform strategy writer, official acquisition source attribution, or verified performance causal analysis exists.
- The X adapter is manual-only. The GZH adapter verifies and describes an
  external workspace; it does not execute production or publishing. The XHS
  runtime adapter was removed on 2026-11-09 and has no replacement — only its
  registry row and video delivery channel remain. Other platform rows remain
  placeholders in the single platform registry.
- The five `x-superplay-*` skills are not declared as executable capabilities.
  `runtime/content-skill-status.json` records missing referenced paths; this is
  separate from the merged router and stage code.

## Next actions

1. Complete one real content run through signed pre-copy research, fingerprint-bound
   copy review, the relevant production gates, QC and human review. The review CLI
   is already implemented; a signed research receipt is not a copy approval.
2. Complete the first real manual delivery, including a verifiable URL and
   manually sourced metric snapshot, before expanding platform automation.
3. Resolve GZH/XHS rights and acceptance independently; a successful workspace
   verification does not grant execution or publication authority.
