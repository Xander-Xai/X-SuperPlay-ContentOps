# Governance Reconciliation — 2026-11-04

> Scope: bring the tracked documentation back in line with verified `main` and
> reconcile the issue register with what happened after the ADR-018 closeout.
> This pass does not claim any deferred work was delivered.

## 1. Verified state at the start of this pass

| Item | Value |
|---|---|
| `main` | `218c91d` (PR #130) |
| Open pull requests | 0 |
| Branches | local and remote: `main` only |
| Worktrees | the primary worktree only |
| CI on `main` | success (last 8 runs; one earlier run cancelled, then re-run green) |
| `python scripts/dev_check.py` | ALL CHECKS PASSED |

## 2. What was actually stale

The post-closeout work merged more than the documentation recorded:

- PRs #101, #105, #114, #117, #118, #119, #121, #125 and #127 all merged.
- Three real-source E2E runs are committed, each ending `PENDING_FOUNDER_REVIEW`.
- The XHS, X and GZH adapters verify but never execute; rights, not code, is the
  remaining blocker.

`docs/CURRENT-STATE.md`, `docs/ARCHITECTURE.md`, `docs/EASEL-CAPABILITY-INVENTORY.md`
and `docs/CONTENT-LIFECYCLE-STAGES.md` still described an unmerged branch,
`PR #101 OPEN`, and unmerged router/XHS/X/GZH tracks. The bilingual mirrors were
corrected in the same change.

## 3. Deferred register

`docs/DEFERRED-WORK.md` recorded #6, #51, #56 and #94 as descoped. After the
closeout, #94 was delivered (PR #118), #6 produced three engineering-accepted
runs, and #51/#56 produced component audits (PR #112) without a rights-cleared
subset. Each entry now carries a dated `Status 2026-11-04 (post-closeout)` row so
the register does not contradict the open issues.

## 4. Issue dispositions

| Issue | Disposition |
|---|---|
| #94 | closed; delivered by PR #118 |
| #100 | closed; deferred by ADR-018 D3 — reopen a decision under a new issue when X execution is proposed |
| #6 | stays open: the Founder's human review of the three rendered MP4s is the only remaining acceptance step |
| #51 | stays open: rights-cleared subset not built; AGPL skill must be excluded |
| #56 | stays open: 45 of 50 bundled skills have no license declaration or license file |
| #7 | stays open while #6 is open; it is the tracking epic, not a deliverable |

## 5. Filesystem action

One stray root file violated `docs/FILE-PLACEMENT-POLICY.md`:
`VIDEO-WORKFLOW-OPTIMIZATION-PLAN.md`. The newer copy was placed in the archive as
`D:\Archives\contentops\2026-11\untracked\VIDEO-WORKFLOW-OPTIMIZATION-PLAN-2026-11-04T1846.md`
(SHA-256 `a02932fb…b0df`), its row and hash were added to the archive `INDEX.md`,
and the repository-root copy was removed. No other file was moved or deleted.

## 6. What this pass does not claim

- No rights clearance for #51 or #56.
- No human review, no publication and no provider spend.
- `production_ready` remains `false`; publication count remains `0`.
