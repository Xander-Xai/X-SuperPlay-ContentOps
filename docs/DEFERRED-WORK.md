# Deferred Work Register

[English](DEFERRED-WORK.md) | [简体中文](DEFERRED-WORK.zh-CN.md)

> One register for work that was **explicitly descoped**, not completed.
> Closing an issue listed here means "not doing this now, evidence preserved",
> never "done". Each entry names its archive and the condition that reopens it.

## Archive

- Root: `D:\Archives\contentops\2026-11\`
- Manifest with byte counts and SHA-256: `D:\Archives\contentops\2026-11\INDEX.md`
- All Git bundles were verified with `git bundle verify` before the source
  refs were deleted.

## Entries

### D-1 — Issue #6: three real end-to-end videos

| Field | Value |
|---|---|
| What was not done | Three E2E videos from three different real sources, each with a committed receipt chain and a completed human review |
| What exists | The M5 evidence chain on `main`; it always ends `PENDING_FOUNDER_REVIEW` with `production_ready: false` |
| Archive | `branches/main.bundle` (snapshot at closeout) |
| Reopen when | A concrete delivery slot exists and a real source is selected; open a new issue referencing this entry |
| Status 2026-11-04 (post-closeout) | **Reopened in effect.** Three real-source runs are committed on `main` (PRs #117, #119); every one passes automated and visual QC and stops at `PENDING_FOUNDER_REVIEW`. Issue #6 stays open for the Founder's human review of the three rendered MP4s; engineering acceptance is otherwise complete |

### D-2 — Issue #51: XHS migration

| Field | Value |
|---|---|
| What was not done | Rights-cleared XHS migration, clean-clone validation, remote retirement gate |
| What exists | Local-only `feat/xhs-fa-migration`, never pushed; 30 rights-unknown skills reported |
| Archive | `branches/feat_xhs-fa-migration.bundle` |
| Reopen when | A per-skill rights manifest exists and the Owner authorizes a public push |
| Status 2026-11-04 (post-closeout) | **Reopened in effect.** The archived tree was audited (report in PR #112): the vendor root is Apache-2.0 covering 40 skills, 5 declare MIT, 1 carries an MIT `LICENSE`, and 1 is AGPL-3.0. Issue #51 stays open for a rights-cleared subset with the AGPL skill excluded; nothing is redistributed from `main` |

### D-3 — Issue #56: GZH rights audit

| Field | Value |
|---|---|
| What was not done | Component-level license/provenance audit of the vendored GZH tree and receipt redaction review |
| What exists | `main` contains **0** GZH files and no `vendor/gzh-thinktank/`; the tree lived only on the branch and in a local working directory |
| Archive | `branches/fix_56-gzh-provenance.bundle`, `untracked/gzh-thinktank.tar.gz` |
| Reopen when | The GZH track is proposed again; the audit must start from the archived tree, not from memory |
| Status 2026-11-04 (post-closeout) | **Reopened in effect.** The archived tree was audited (report in PR #112): 45 of 50 `SKILL.md` entries have neither a license declaration nor a license file, 3 declare MIT, 1 carries an MIT `LICENSE`, and 1 is AGPL-3.0. Issue #56 stays open for individual clearance, replacement or permanent exclusion; `main` still carries 0 GZH files |

### D-4 — Issue #94: content-router S3–S4

| Field | Value |
|---|---|
| What was not done | Capture plan, account configuration, brief/script/design/optimisation stages |
| What exists | S1 (#93), S2 (#95) and the router (#114) on `main`; S4 stage policies merged as PR #118 |
| Archive | `branches/feat_content-router.bundle` |
| Reopen when | The ADR-014 delivery hold has produced a first real delivery and a stage is needed by that delivery |
| Status 2026-11-04 (post-closeout) | **Delivered after closeout.** PR #118 merged the S4 stage policies and design router. Issue #94 is closed; this entry is retained for the archived bundle only |

### D-5 — Motion-study import (unmerged feature)

| Field | Value |
|---|---|
| What was not done | `src/contentops/media/motion_study.py`, `scripts/motion_study_import.py`, templates and tests were staged in a Codex worktree but never opened as a PR |
| Archive | `worktrees/codex_motionclone.tar.gz`, `patches/codex_motionclone.patch` |
| Reopen when | The video workflow optimisation plan is scheduled; restore the tarball, run its tests, then open a PR |

### D-6 — Tier-1 documentation convergence (uncommitted)

| Field | Value |
|---|---|
| What was not done | Updates to `AGENTS.md`, `CLAUDE.md`, `README*`, `DEVELOPMENT-PLAN*`, `TEST-PLAN*` and the dual-account video optimisation plan were present only as uncommitted work |
| Archive | `patches/main-worktree-wip.patch`, `untracked/VIDEO-WORKFLOW-OPTIMIZATION-PLAN.md`, `untracked/motion-*.md` |
| Reopen when | A documentation PR is scheduled; re-apply the patch against current `main` and re-run `dev_check.py` |

## Rule

An entry leaves this register only when its reopening condition is met, the work
is done under a new issue/PR, and a receipt records the result. Deleting an
archive is a separate cleanup decision under the filesystem policy.
