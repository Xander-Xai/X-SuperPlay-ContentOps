# Worktree and Branch Audit — 2026-11-01

> Scope: local repository state only. Read-only inspection.
> **Nothing was deleted, moved, trimmed, or reset.** This document is the
> evidence step of the cleanup contract; the action step is a separate,
> per-item decision.
> Method limits are stated in §2 — read them before using this report to
> delete anything.

## 1. Why this audit exists

The repository carries 39 worktrees and 41 local branches, most of them from
milestone passes between 2026-10-30 and 2026-11-01. They are not harmless: a
worktree holds a checkout, and `git worktree list` shows them as live
attachments to the repository's administrative data. Under the filesystem
policy these are **protected** until ownership, activity and regeneration cost
are established.

## 2. Method and its limits

| Question | Method used | Limit |
|---|---|---|
| Which worktrees exist | `git worktree list` | complete |
| Which branches exist | `git branch` | complete |
| Is a branch's work already integrated | `git branch --merged <branch>` | **ancestry only** |
| Is a PR open, merged, or closed | `gh pr list` (2026-11-01, before the shell outage) | snapshot at 2026-11-01T00:00Z |
| Disk size per worktree | not measured | `du`/`Get-ChildItem` needed |
| Age per branch | commit dates available from git | — |

**Ancestry is not enough here.** The repository squash-merges, so a branch
merged as PR #77 has a *different* SHA on the integration branch than its own
tip. `git branch --merged` therefore reports work as unmerged when it is in
fact already integrated. Only the PR state from GitHub is authoritative. The
`gh` snapshot below must be re-checked before any deletion.

## 3. The finding that changes the cleanup order

`main` stops at phase-4 delivery unlock (PR #72). The media-use integration,
rights gate, skill router and skill-execution authorization stack — PRs #71,
#74, #75, #76, #77, #78, #79, #80, #81, #84 — was squash-merged into
`fix/57-m5-media-fixtures`, **not into `main`**.

So the integration branch is 17 commits ahead of the protected branch, and
several "finished" milestone branches are still the only copy of that work's
history. Cleaning them up *before* the stack lands on `main` risks deleting the
only place a merge can be traced from.

**Order is therefore: land the stack first, clean up second.**

## 4. Inventory

### 4.1 Worktrees (39)

Under the repository (`.claude/worktrees/`): `agent-a05b8f460dac8dc34`,
`feature-ci`, `gov-report`, `gzh-provenance`, `integ-57-media-use`,
`m5-production`, `phase2-pr49`, `phase2-pr62`, `phase2-pr64`, `phase2-report`,
`phase3-gzh`, `phase3-report`, `phase4-combined`, `phase4-report`, `phase5`,
`phase5-m71`, `phase5-rights`, `phase5-routea`, `portfolio`, `pr49-ci`,
`pr49-prep`, `receipt-baseline`, `skills-doctor`, `skills-doctor-cr`,
`story-studio-episode`, `win-subprocess`, `win-subprocess-cr`, `x-track`.

Under `D:\Temp\AI-Agents\claude\`: `contentops-authz/wt`,
`contentops-phase10-main`, `contentops-phase8-gate/wt`, `contentops-pr83`,
`contentops-x-decouple`, `contentops-x-integration`.

### 4.2 Branches (41)

Local branches span `chore/`, `docs/`, `feat/`, `fix/`, `phase2/`–`phase6/`.
Ancestry against the integration branch:

- **contained** (3): `main`, `fix/57-m5-media-fixtures`,
  `worktree-agent-a05b8f460dac8dc34`
- **not contained** (38): everything else — including branches whose PRs were
  merged by squash (§2)

### 4.3 PR state snapshot (2026-11-01)

| PR | Branch | State |
|---|---|---|
| #49 | `feat/content-router` | draft, open |
| #50 | `feat/47-x-platform-track` | draft, open |
| #58 | `fix/56-gzh-provenance` | draft, open |
| #62 | `fix/61-receipt-baseline` | draft, open |
| #86 | `fix/57-media-use-ingest-rights-gate` | open |
| #87 | `feat/85-x-editorial-decoupled` | open |
| #88 | `feat/85-x-growth-integration` | draft, open |
| #89 | `fix/57-m5-media-fixtures` | open, mergeable |
| #90 | `docs/57-media-use-premerge-and-mutation-adr` | draft, open |
| #71, #74–#81, #84 | — | merged **into `fix/57-m5-media-fixtures`**, not `main` |

## 5. Classification (cleanup contract)

| Class | Items | Reason |
|---|---|---|
| **Protected** | `main`, `fix/57-m5-media-fixtures`, all worktrees of open PRs (#49, #50, #58, #62, #86, #87, #88, #90) | active work or the only copy of merged history |
| **Review required** | worktrees of merged PRs whose history is not on `main` yet (#71, #74–#81, #84), plus `phase2-*`–`phase6-*` branches | squash-merged content, stale ancestry; verify with `gh` before any removal |
| **Regenerable candidate** | none confirmed | every remaining branch maps to a PR or a worktree; no branch is provably empty of value |
| **Protected by policy** | `.claude/`, `D:\Temp\AI-Agents\*`, `.verify-tmp/`, `assert/`, `vendor/`, `projects/*/work`, `projects/*/final` | agent state, media and downloads are not routine cleanup |

## 6. Recommended sequence

1. Land PR #89 (with the convergence work) on `main`.
2. Re-run `gh pr list --state merged` and mark every branch whose PR is
   merged into `main`.
3. Measure worktree sizes:
   `Get-ChildItem .claude/worktrees -Directory | ForEach-Object { "{0}`t{1:N0} MB" -f $_.Name, ((Get-ChildItem $_.FullName -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum / 1MB) }`
4. Present the measured list for per-item approval, then remove approved
   worktrees with `git worktree remove <path>` and delete the approved branches
   with `git branch -d <name>`.

`-d` (not `-D`) is deliberate: it refuses to delete a branch that is not
merged, which is the behaviour a cleanup wants.

## 7. Statement of effect

- Files moved: **none**.
- Files deleted: **none**.
- Branches deleted: **none**.
- Worktrees removed: **none**.
- Disk space recovered: **0 bytes** — no cleanup was performed, only measured
  in part and classified.

## 8. Commands to reproduce

```bash
git worktree list
git branch --merged fix/57-m5-media-fixtures
git branch --no-merged fix/57-m5-media-fixtures
gh pr list --state open --limit 30
gh pr list --state merged --limit 30
```
