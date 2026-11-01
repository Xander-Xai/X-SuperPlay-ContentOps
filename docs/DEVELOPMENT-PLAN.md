# Development Plan

[English](DEVELOPMENT-PLAN.md) | [简体中文](DEVELOPMENT-PLAN.zh-CN.md)

> Milestone-based execution. Every milestone has an exit criterion.
>
> Status verified: 2026-11-01 on `fix/57-m5-media-fixtures`.

## Status legend

| Mark | Meaning |
|---|---|
| **DONE** | exit criterion met and evidence exists |
| **PARTIAL** | the mechanism exists; a named exit criterion is not met |
| **ACTIVE** | current work |
| **UNMERGED** | implemented on a branch that is not integrated |
| **NOT STARTED** | no implementation |

## Milestones

| Milestone | Description | Status | Evidence / blocker |
|---|---|---|---|
| M0 | Repository canonicalization: docs, runtime facts, governance | **DONE** | `dev_check.py` green; lock and docs checks |
| G0.5 | GitHub and Claude Code development governance | **DONE** | branch protection, PR template, agent rules |
| G0.6 | Upstream watch, bilingual docs, Windows subprocess policy | **DONE** | `check_easel_upstream.py`, `check_i18n.py`, `process_utils.py` |
| M1 | Stabilize the Easel V1 pipeline and golden regression | **PARTIAL** | builds and QC exist; no completed human review |
| M2.0 | MiniMax capability spike | **DONE** | `research/providers/*` (Issue #4) |
| M2-M4 | MiniMax speech / image / H3 integration | **DONE (implemented)** | verified subsets in CURRENT-STATE; `PENDING_FOUNDER_REVIEW` |
| M4.5 | Media convergence: one manifest, one gate vocabulary | **DONE** | 97 tests; `projects/m45-technical-integration` |
| M5 | Evidence-first production chain | **DONE on this branch** | `scripts/m5_production.py`, `projects/m5-media-use` |
| M5-M6 | Cross-repo `SourceArtifact` workflow and production E2E | **NOT STARTED** | Issue #6; needs the content-router layer |
| Content router | Account DNA → route → brief → existing pipeline | **UNMERGED** | `feat/content-router` (PR #49, draft) |
| Convergence | Documentation, skill, branch and pin convergence | **ACTIVE** | [CONVERGENCE-REQUIREMENTS-2026-11-01.md](CONVERGENCE-REQUIREMENTS-2026-11-01.md) |

## Numbering note

"M5" names two different things in this repository:

- **M5 evidence-first production chain** — implemented, entry
  `scripts/m5_production.py`.
- **M5-M6 cross-repo SourceArtifact / production E2E** — the original milestone
  plan (Issue #6), not started.

Read the milestone table above, not the issue number alone, when a document says
"M5".

## Exit criteria

### M1 — pipeline stabilization

- 3 consecutive Easel builds pass, QC passes, runtime verification passes.
- A human-review receipt exists for at least one project.
- Current blocker: the third criterion has never been met.

### M2-M4 — provider integration

- Real subscription smoke test passes per modality.
- Receipt records quota before/after as an observed delta.
- Fallback is named in the receipt and never reports production-ready.
- Current blocker: Founder approval, not implementation.

### M5-M6 — production E2E

- 3 different sources → the same ContentRun workflow → 3 final MP4s.
- No repo-specific code.
- Founder review for each.
- Current blocker: the cross-repo adapter and content-router layer are unmerged.

## Strict order

```
M0 → G0.5 → G0.6 → M1 → M2.0 → M2-M4 → M4.5 → M5 → M5-M6
```

No skipping. A milestone whose exit criterion is not met stays open even when
its implementation exists.

## Current focus

Documentation and skill convergence (P0 of the convergence requirements)
followed by the Owner decisions D1–D6. No new capability is added until those
decisions are recorded.
