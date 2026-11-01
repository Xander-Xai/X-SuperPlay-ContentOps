# GitHub governance execution — 2026-11-01

> Authoritative post-execution state for the PR / Issue / Branch / Worktree
> review of `Xander-Xai/X-SuperPlay-ContentOps` (PUBLIC, default branch `main`).
> Supersedes
> [`worktree-and-branch-audit-2026-11-01.md`](worktree-and-branch-audit-2026-11-01.md)
> for every fact both cover; that file remains the read-only inventory that
> preceded this pass.
> Method: `gh` + `git` only. Sizes measured on this host. Nothing outside the
> deletions in §2 was removed.

## 1. What moved since the 2026-11-01 inventory

| Fact | Then | Now |
|---|---|---|
| `main` HEAD | `3c559fb` (phase-4 unlock, PR #72) | `857a649` — the media-use / skill-authorization stack **and** PR #83 (X growth operator) |
| Integration stack on `main` | no | yes — PRs #71, #74–#81, #84 are ancestors of `main` |
| Working branch ahead of `main` | 17 commits | 9 (7 M5 + 2 convergence commits in §2) |

The earlier conclusion "the stack lives only on `fix/57-m5-media-fixtures`" is
now **false**. `main` carries it. What that branch still holds exclusively is
the **M5 sample reproducibility fix**, the **documentation convergence** and the
**skill-drift / unwired-suite CI checks**. Those are PR #89.

## 2. Actions taken in this pass

- Committed the convergence work that was uncommitted on
  `fix/57-m5-media-fixtures`:
  - `4d56f43` — `docs: converge the project documentation with the code`
  - `880bff4` — `feat: make skill-to-code drift and unwired suites CI failures`
- Pushed both to `fix/57-m5-media-fixtures` (PR #89) and rewrote its title and
  body to match its real scope.
- Deleted **4** local branches whose every commit is already patch-equivalent on
  `origin/main` and that are neither checked out in a worktree nor an open-PR
  head:
  `chore/57-protect-local-approvals`, `docs/phase5-integration-convergence-2026-10-31`,
  `fix/57-media-entry-rights-boundary`, `fix/57-media-use-status-available`.
  Recoverable from the reflog for 90 days.
- Ignored `.local/` (per-host scratch, router DB, gh device-id) — not source,
  not evidence.

Not done: no PR was merged, no issue was closed, no worktree was removed. Each
is listed as a decision below.

## 3. Pull requests (9 open)

| PR | Draft | Base | Merge state | Size | Recommendation |
|---|---|---|---|---|---|
| **#86** | no | main | BEHIND | 9f +489/−5 | **Land first.** Rights-gate fix for `ingest`; independent, small. Update branch, squash. |
| **#89** | no | main | BEHIND | 56f +3400/−367 | **Land second** (after #86 to avoid a `ci.yml` conflict). This pass's convergence + M5 + CI checks. |
| **#87** | no | main | CLEAN | 24f +4732/−0 | **Land.** X post gate decoupled from the vendor bundle; clean against main. |
| **#88** | yes | #87 | CLEAN | 25f +2670/−12 | Mark ready and land **after #87** (stacked on it). |
| **#62** | yes | main | BEHIND | 5f +521/−94 | **Land.** Security: binds receipt-secrets baseline to trusted values (Issue #61). Update branch, mark ready. |
| **#90** | yes | main | CLEAN | 4f +125/−0 | **Land after #89** or close as folded into ADR-012. Docs only. |
| **#49** | yes | main | CONFLICTING | 1508f +228642/−487 | **Do not merge wholesale.** Per ADR-012 D1, slice S1–S4 onto main one at a time. Convert to a tracking PR. |
| **#50** | yes | #49 | CLEAN | 140f +12120/−319 | Part of the #49 stack; keep draft until the slices land. |
| **#58** | yes | #49 | CLEAN | 23f +2410/−137 | GZH provenance audit for Issue #56; keep draft until the stack is sliced. |

Recommended landing order: **#86 → #89 → #87 → #88 → #62 → #90**. Each merge is
squash + auto-delete (repo setting). `main` requires strict checks, so every
BEHIND branch must be updated to current `main` before it can merge, which
re-runs CI.

## 4. Issues (16 open)

| Issue | Title (short) | State | Recommendation |
|---|---|---|---|
| **#82** | X Organic Growth Operator skill | delivered by merged PR #83 | **Close as completed.** |
| #7 | [EPIC] production runtime | umbrella, active | Keep. |
| #15 | Easel compatibility watch | tracking | Keep. |
| #47 | [X] platform track umbrella | active (#49/#50) | Keep. |
| #51 | [XHS] migration acceptance | blocked on provenance | Keep (blocked). |
| #56 | [P0/GOV] GZH rights audit | PR #58 draft | Keep until the stack is resolved. |
| #57 | [P1/ARCH] skill discovery | router + execution auth merged (#77–#81); umbrella | Keep, but update body: the core is delivered; remaining item is the skill-declaration record. |
| #61 | [SEC/P1] receipt-secrets guard | fixed by PR #62 | Keep until #62 merges. |
| #85 | X growth → editorial gate | PRs #87/#88 | Keep until they merge. |
| #6 | [M5-M6] cross-repo E2E, 3 videos | stale since 2026-10-03 | **Owner call:** M5 chain exists, but "3 real E2E videos" is not delivered. Restate scope or close. |
| #5, #19, #23, #29, #34 | MiniMax / voice-clone / Golden milestones | stale since 2026-10-12; much delivered by PRs #32–#46 | **Owner call:** close as delivered/superseded, or convert to milestone archive. These encode commercial outcomes a reviewer cannot judge from code. |
| #11 | [GOV] repository license | open decision | **Owner call:** license is a business decision. |

Only #82 is unambiguous and safe to close without further judgment.

## 5. Branches and worktrees

- **Local branches: 41** (after the 4 deletions in §2).
- **34 git worktrees** of this repository (plus the primary checkout), and one
  standalone clone, measured **1,053 MB** across both roots on this host:
  - `.claude/worktrees/` — **28** worktrees (largest: `story-studio-episode`
    90 MB, which is **dirty**; `integ-57-media-use` 39 MB; `skills-doctor`
    26 MB).
  - `D:\Temp\AI-Agents\claude\` — 6 worktrees plus a standalone
    `m5-clean-clone-20261101` (**486 MB**, disposable; a separate clone, not a
    worktree of this repo).
- Most local branches are held by a worktree checkout, so they cannot be deleted
  until that worktree is removed.

Classification for cleanup (per the filesystem policy, deletion is separate and
per-item):

| Class | Worktrees | Reason |
|---|---|---|
| **Disposable now** | `m5-clean-clone-20261101` (486 MB), `contentops-phase10-main` (detached) | A clean clone and a detached checkout; no branch, nothing to lose. |
| **Redundant** (branch content already on `main`, worktree clean) | `feature-ci`, `gov-report`, `phase2-report`, `phase3-report`, `phase4-report`, `portfolio`, `phase5`, `phase5-m71`, `phase5-rights`, `phase5-routea`, `phase2-pr62`, `phase2-pr64`, `m5-production`, `integ-57-media-use`, `win-subprocess`, `win-subprocess-cr`, `contentops-pr83`, `contentops-authz/wt`, `contentops-phase8-gate/wt` | The branch's commits are patch-equivalent on `main`; the checkout adds nothing. |
| **Keep — open PR head** | `pr49-prep` (#49), `phase2-pr49` (#49), `x-track` (#50), `gzh-provenance` (#58), `receipt-baseline` (#62), `contentops-x-decouple` (#87), `contentops-x-integration` (#88) | Deleting the worktree would strand an open PR. |
| **Keep — unmerged / dirty** | `story-studio-episode` (**dirty**), `skills-doctor`, `skills-doctor-cr`, `pr49-ci`, `win-subprocess-cr`, `phase3-gzh`, `phase4-combined`, `phase6`/`phase5` route stacks, `agent-a05…` (**dirty**, 2 files) | Carries unmerged work or uncommitted changes; content not provably on `main`. |

## 6. Decisions pending (Owner)

1. **Merge order §3** — approve landing #86 → #89 → #87 → #88 → #62 → #90.
2. **Close #82** as completed; restate or close the stale milestone issues
   (#5, #6, #19, #23, #29, #34); decide #11 (license).
3. **Worktree removal** — approve the "Disposable now" and "Redundant" classes
   in §5 by category, and name any "Keep" item you want removed. Removal is
   `git worktree remove <path>`; a clean worktree refuses to lose uncommitted
   work.

## 7. Statement of effect

- **No secret** was read, copied or committed.
- Files moved: none. Files deleted: none.
- Branches deleted: **4 local branches** (§2), all patch-equivalent on `main`,
  reflog-recoverable.
- Worktrees removed: **none** — proposed only, awaiting approval.
- PRs merged: none — proposed only. Issues closed: none — proposed only.
- Disk recovered: 0 bytes so far; the "Disposable + Redundant" classes in §5
  would recover roughly 700 MB if approved.

## 8. Commands to reproduce

```bash
gh pr list --state open --json number,isDraft,mergeable,mergeStateStatus,baseRefName
gh issue list --state open --json number,title,updatedAt
git worktree list
git branch --no-merged origin/main
git cherry origin/main <branch>      # '+' = commit not patch-equivalent on main
```
