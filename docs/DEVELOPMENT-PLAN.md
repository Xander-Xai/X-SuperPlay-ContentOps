# Development Plan

[English](DEVELOPMENT-PLAN.md) | [简体中文](DEVELOPMENT-PLAN.zh-CN.md)

> Milestone-based execution. Every milestone has an exit criterion.
>
> Last verified: 2026-11-14: X original-post contract now offers explicit text-only and raster+ALT modes plus strict technical versus general-interest human review. No live platform outcome claimed; CI of this change is tracked in its PR.
> X policy: Strategy canonical SOP and registered account DNA; source metrics and publishing still require human verification.


## Status legend

| Mark | Meaning |
|---|---|
| **DONE** | exit criterion met and evidence exists |
| **PARTIAL** | the mechanism exists; a named exit criterion is not met |
| **ACTIVE** | current work |
| **NOT STARTED** | no implementation |

## Milestones

| Milestone | Description | Status | Evidence / blocker |
|---|---|---|---|
| M0 | Repository canonicalization: docs, runtime facts, governance | **DONE** | `dev_check.py` green; lock and docs checks |
| G0.5 | GitHub and Claude Code development governance | **DONE** | branch protection, PR template, agent rules |
| G0.6 | Upstream watch, bilingual docs, Windows subprocess policy | **DONE** | `check_easel_upstream.py`, `check_i18n.py`, `process_utils.py` |
| M1 | Stabilize the Easel V1 pipeline and golden regression | **PARTIAL** | builds and QC exist; no project carries an APPROVED `human-review.json` |
| M2.0 | MiniMax capability spike | **DONE** | `research/providers/*` (Issue #4) |
| M2-M4 | MiniMax speech / image / H3 integration | **DONE (implemented)** | verified subsets in CURRENT-STATE; `PENDING_FOUNDER_REVIEW` |
| M4.5 | Media convergence: one manifest, one gate vocabulary | **DONE** | 97 tests; `projects/m45-technical-integration` |
| M5 | Evidence-first production chain | **DONE** | `scripts/m5_production.py`, `projects/m5-media-use`; ASR backcheck gate (#150); characterization baseline (#153) |
| Stable production entry | One gated CLI in front of every producer | **DONE** | `scripts/make_content.py` + `scripts/production_gates.py` (#157); 7 VIDEO / 5 GRAPHIC_TEXT fail-closed gates |
| Rendering: cards and GZH article | HTML cards → PNG with a density audit; article HTML validation | **DONE (offline)** | `render_cards.py` (#149), `render_article.py` (#152); receipts keep `production_ready: false` |
| M5-M6 | Cross-repo `SourceArtifact` workflow and production E2E | **DONE (evidence in issue)** | three real-source runs on `main` (#117, #119) pass automated and visual QC; Founder review PASS recorded in #6, closed 2026-11-10. Caveat: the approval lives in the issue, not in an APPROVED `human-review.json` |
| Content router | Account DNA → route → brief → existing pipeline | **DONE** | PRs #114 / #118; 15 hotspot sources opened to both accounts (#157) |
| Delivery layer | Per-platform packs, thumbnails and draft-only handoff | **DONE (packaging)** | `video_deliver.py`, `platform_delivery.py`, `graphic_deliver.py`, `wechatsync_browser.py`; 0 delivery receipts exist |
| Publication | A work published on a platform with a recorded URL | **NOT STARTED** | no public account is bound; every registry row except `x` stays `PLANNED`; publication count 0 |
| M5 stage split (#140) | Split the orchestrator into stage modules | **ACTIVE** | slice 1 landed as the characterization baseline (#153) |
| Convergence | Documentation, skill, branch and pin convergence | **DONE (2026-11-01 plan; steps 3–5 landed later)** | [CONVERGENCE-REQUIREMENTS-2026-11-01.md](CONVERGENCE-REQUIREMENTS-2026-11-01.md); steps 3–5 closed by #114/#118 and #132–#159 |

## Numbering note

"M5" names two different things in this repository:

- **M5 evidence-first production chain** — implemented, entry
  `scripts/m5_production.py`.
- **M5-M6 cross-repo SourceArtifact / production E2E** — the original milestone
  plan in Issue #6, now closed with the Founder review recorded.

Read the milestone table above, not the issue number alone, when a document says
"M5".

## Exit criteria

### M1 — pipeline stabilization

- 3 consecutive Easel builds pass, QC passes, runtime verification passes.
- A human-review receipt exists for at least one project.
- Current blocker: the third criterion has never been met. The #6 review is an
  issue comment, not a project receipt, so it does not close this one.

### M2-M4 — provider integration

- Real subscription smoke test passes per modality.
- Receipt records quota before/after as an observed delta.
- Fallback is named in the receipt and never reports production-ready.
- Current blocker: Founder approval, not implementation.

### M5-M6 — production E2E

- 3 different sources → the same ContentRun workflow → 3 final MP4s.
- No repo-specific code.
- Founder review for each.
- Current state: met, with the review recorded in Issue #6 rather than in a
  per-project receipt. Publication remains unauthorized.

### Publication — the next open milestone

- A bound public account for at least one platform row.
- One delivery receipt naming a URL a person actually saw.
- A registry row that moves above `PLANNED` because of that evidence, not
  because a runner exists.

## Strict order

```
M0 → G0.5 → G0.6 → M1 → M2.0 → M2-M4 → M4.5 → M5 → M5-M6 → publication
```

No skipping. A milestone whose exit criterion is not met stays open even when
its implementation exists.

## Current focus

1. Publication evidence: the delivery runners are built, but nothing has a real
   platform URL, and no public account is bound.
2. Rights clearance (Issues #51, #56) that keeps the GZH and XHS rows at
   `PLANNED`.
3. M5 stage split (#140), guarded by the recorded characterization baseline.
