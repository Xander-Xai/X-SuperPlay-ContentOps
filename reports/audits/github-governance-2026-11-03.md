# GitHub Governance Pass — 2026-11-03

> Scope: PRs, Issues and Branches in `Xander-Xai/X-SuperPlay-ContentOps`.
> Read-only audit plus the actions recorded in §7. Destructive branch actions
> were **not** performed: the permission layer required the Owner to name the
> specific remote branches. See §8 for the exact list awaiting approval.
>
> Method limits: branch "merged" status is taken from **GitHub PR state**, not
> from Git ancestry. This repository squash-merges, so a branch whose PR merged
> is never an ancestor of `main` and `git branch --merged` under-reports.

## 1. Scope and exclusions

| Item | Included | Excluded |
|---|---|---|
| Pull requests | all 4 open, all recently merged/closed (40) | none |
| Issues | all 9 open, all recently closed (60) | none |
| Branches | 32 local refs, 14 remote refs | files, worktree contents |
| Worktrees | inventory and dirty count | no worktree removed |
| Disk | `D:` free/used | per-file accounting |
| Hosts | Claude Code | Codex / OpenCode hooks not exercised |

## 2. Snapshot — before this pass

| PR | Head | State | Checks |
|---|---|---|---|
| #105 | `docs/r4a-script-and-evidence` | Open | 3/3 green, `BEHIND` main |
| #107 | `feat/106-easel-host-dual-line` | Draft | 3/3 green, `CLEAN` |
| #108 | `feat/106-easel-host` | Draft | 3/3 green, `CLEAN` |
| #109 | `docs/x-rewards-90d-20261103` | Draft | 3/3 green, `CLEAN` |

Open Issues: #6, #7, #11, #15, #47, #51, #56, #57, #94, #100, #106.

`main` was one commit behind `origin/main`; local and remote `main` differed
(`357a84e` → `92c41f4`).

## 3. PR governance

| PR | Action | Reason |
|---|---|---|
| #105 | `gh pr update-branch` executed; branch now current with `main` | it was `BEHIND`; content is unchanged and no approval was implied |
| #108 | left **Draft**; governance comment added | merge requires the Owner's explicit `SECURITY_APPROVED / APPROVE_FOR_MERGE` verdict; CI green is not a security review |
| #107 | left **Draft**, stacked on #108 | its base is #108; merging it first would detach the docs layer |
| #109 | left **Draft** | its own body says "Do not merge until reviewed and acceptance conditions pass" |

No PR was merged, closed, retargeted or marked ready.

### 3.1 Contract gap found in #108 (not fixed here)

`src/contentops/easel/driver.py` declares the `qc-video` step receipt as
`receipts/qc-report.json`. `scripts/qc_video.py` computes
`target_name = final.stem` and writes `receipts/qc-report-<target_name>.json`
(for example `qc-report-easel.json` or `qc-report-final.json`). The declared
literal is therefore never produced and the step cannot reach completion from
a real run.

A local, uncommitted edit changes the declaration to
`receipts/qc-report*.json`. It was **not** committed to #108 during this pass
because #108 is under final review and the change alters a completion contract.
It is recorded on the PR and must be reviewed and committed before a merge
verdict.

## 4. Issue governance

| Issue | Action | Reason |
|---|---|---|
| #47 X platform track | **closed** | its implementation branch (PR #50) was closed as superseded by #94's slice process; the X track landed via #83/#87/#88 and future strategy work is #109 |
| #57 Skill discovery | **closed** | router, doctor and tests are on `main` via #77; PR #59 was closed as superseded. Rights follow-ups remain #51/#56/#11 |
| #100 Platform placeholders | comment only, kept open | PR #101 merged, but ADR-015 D-3/D-4 and X execution authority are still Owner decisions |
| #94 Content-router slices | comment only, kept open | ADR-014 hold runs to 2026-11-07; S3/S4 not started |
| #106 Easel host adoption | comment only, kept open | blocked on #108's Owner verdict; the qc-report gap was recorded |
| #6, #7, #11, #15, #51, #56 | unchanged | real unfinished work, rights decisions or the automated upstream watch |

No issue was closed without a comment naming what is and is not resolved.

## 5. Branch governance

### 5.1 Remote branches (14)

| Branch | Verdict | Reason |
|---|---|---|
| `main` | keep | default branch |
| `feat/106-easel-host` | keep | PR #108 head |
| `feat/106-easel-host-dual-line` | keep | PR #107 head |
| `docs/r4a-script-and-evidence` | keep | PR #105 head |
| `docs/x-rewards-90d-20261103` | keep | PR #109 head |
| `feat/content-router` | keep | retained source for #94 by decision |
| `fix/56-gzh-provenance` | keep | evidence/source for open #56 |
| `chore/skills-doctor-cr` | **delete candidate** | PR #59 closed as superseded; doctor is on `main` |
| `feat/47-x-platform-track` | **delete candidate** | PR #50 closed as superseded; issue #47 closed in this pass |
| `feat/57-media-use-adapter` | **delete candidate** | PR #64 closed; media-use merged via #71/#77 |
| `feat/6-m5-production-e2e` | **delete candidate** | PR #68 closed; M5 merged via #71 |
| `feat/m5-media-use-auto-assets` | **delete candidate** | PR #69 closed; merged via #71 |
| `fix/media-use-rights-gate-2026-10-31` | **delete candidate** | PR #73 closed; rights gate merged via #76 |
| `phase6/route-a-stack` | **delete candidate** | PR #76 merged; squash merge left the branch behind |

The seven delete candidates were **not deleted**. The permission layer requires
the Owner to name them (see §8).

### 5.2 Local branches (32)

Verified merged/superseded and proposed for deletion (not executed):

`feat/100-easel-first-platform-registry` (#101 merged),
`fix/53-windows-subprocess-stdin-cr` (#55 merged),
`phase6/route-a-stack` (#76 merged),
`chore/skills-doctor`, `chore/skills-doctor-cr` (#59 closed/superseded),
`feat/57-media-use-adapter`, `feat/6-m5-production-e2e`,
`fix/media-use-rights-gate-2026-10-31` (closed/superseded).

Retained deliberately:

| Branch | Reason |
|---|---|
| `feat/content-router` | only source for #94 |
| `feat/xhs-fa-migration` | local-only work for #51; must not be pushed before the rights gate |
| `fix/56-gzh-provenance`, `phase3/gzh` | evidence for open #56 |
| `backup-dual-line-20261102` | deliberate backup of the dual-line layer |
| `phase2/pr49`, `phase2/pr62`, `phase2/pr64` | historical stack snapshots; review-required, not proven redundant |
| `phase4/combined`, `phase5/*`, `rehearsal-108` | old slice/rehearsal stacks; review-required |
| Branches checked out in worktrees | cannot be deleted while the worktree exists |

## 6. Worktrees (9) — protected, none removed

| Path | Branch | Size | Dirty |
|---|---|---|---|
| `D:/Projects/X-SuperPlay-ContentOps` | `feat/106-easel-host-dual-line` | — | 16 |
| `D:/Projects/codex/worktrees/motionclone-contentops-20261102` | `codex/motionclone-contentops-20261102` | 17 MB | 20 |
| `.claude/worktrees/agent-a05b8f460dac8dc34` | `worktree-agent-a05b8f460dac8dc34` | 11 MB | 2 |
| `.claude/worktrees/story-studio-episode` | `feat/47-story-studio-episode` | 95 MB | 3 |
| `.claude/worktrees/x-track` | `feat/47-x-platform-track` | 28 MB | 3 |
| `D:/Temp/.../motion-recovery-2026-11-01/r2` | `feat/motion-recovery` | 13 MB | 0 |
| `D:/Temp/.../motion-recovery-2026-11-01/r3` | `feat/r3-motion-integration` | 14 MB | 0 |
| `D:/Temp/.../motion-recovery-2026-11-01/wt` | `fix/49-skill-route-ci` | 35 MB | 0 |
| `D:/Temp/.../pr99-merge-2026-11-02` | `fix/98-ignore-agent-state` | 13 MB | 0 |

Worktrees are protected by the filesystem policy. The three clean ones under
`D:/Temp` belong to **merged** PRs (#103, #104, #99) and are the safest future
removal candidates, but removal is a separate per-item approval.

## 7. Actions actually performed

| Action | Result |
|---|---|
| `git fetch origin main:main` | local `main` fast-forwarded `357a84e` → `92c41f4` |
| `gh pr update-branch 105` | branch updated; CI re-ran |
| Issue #47 closed with evidence comment | done |
| Issue #57 closed with evidence comment | done |
| Comments on #100, #94, #106 | done |
| Comment on PR #108 (qc-report gap) | done |
| Files moved | **none** |
| Files deleted | **none** |
| Branches deleted (local or remote) | **none** — blocked pending named approval |
| Worktrees removed | **none** |
| PRs merged | **none** |

## 8. Awaiting explicit Owner approval

Remote branches (seven, exact names):

```
chore/skills-doctor-cr
feat/47-x-platform-track
feat/57-media-use-adapter
feat/6-m5-production-e2e
feat/m5-media-use-auto-assets
fix/media-use-rights-gate-2026-10-31
phase6/route-a-stack
```

Local branches (eight, exact names):

```
feat/100-easel-first-platform-registry
fix/53-windows-subprocess-stdin-cr
phase6/route-a-stack
chore/skills-doctor
chore/skills-doctor-cr
feat/57-media-use-adapter
feat/6-m5-production-e2e
fix/media-use-rights-gate-2026-10-31
```

No deletion is reversible on GitHub without restoring the ref. Approve by
naming the list; do not treat this report as approval.

## 9. Uncommitted local work found (left untouched)

The main checkout is dirty (16 entries). It was **not** stashed, committed or
discarded.

| Group | Files | Note |
|---|---|---|
| Tier-1 doc convergence | `AGENTS.md`, `CLAUDE.md`, `README.md`, `README.zh-CN.md`, `docs/DEVELOPMENT-PLAN.md`, `docs/DEVELOPMENT-PLAN.zh-CN.md`, `docs/INDEX.md`, `docs/INDEX.zh-CN.md`, `docs/TEST-PLAN.md`, `docs/TEST-PLAN.zh-CN.md` | describes the #106 stack; belongs in a docs PR, not in #107's 5-file diff |
| Driver fix | `src/contentops/easel/driver.py` | the `qc-report*.json` gap in §3.1 |
| New plan | `docs/VIDEO-WORKFLOW-OPTIMIZATION-PLAN.md` | indexed by the dirty `docs/INDEX.md`; implementation pending |
| Research/draft | `docs/motion-asset-handoff-draft.md`, `docs/motion-source-rights-ledger-20261102.md`, `MotionClone-ContentOps-双账号复刻最终方案.md` | content/research work, separate from #106 |
| Untracked project tree | `projects/gzh-thinktank/` (≈14 MB) | not a Git repository; contains GZH working data and binary images. Protected by #56/#51 rights work. It should **not** be committed; placement decision pending |

## 10. Disk

| Value | Measurement |
|---|---|
| `D:` size | 782 GB |
| Used | 605 GB |
| Free | 177 GB (78% used) |
| Recoverable by approved branch deletion | 0 bytes |
| Recoverable by worktree removal | ≈226 MB (8 worktrees, all protected) |

## 11. Host integration status

| Host | Status |
|---|---|
| Claude Code | active for this session; performed every action above |
| Codex | hook and `AGENTS.md` not exercised in this pass; status unverified |
| OpenCode | plugin not exercised in this pass; status unverified |
| Easel host | **not started**; `HOST_BLOCKED` remains the honest state |

## 12. Open Owner decisions

1. Name the remote and local branches to delete (§8).
2. Decide whether the uncommitted doc convergence becomes its own PR stacked
   on #107, and whether the `driver.py` qc-report fix goes into #108 before its
   verdict.
3. Supply the `SECURITY_APPROVED / APPROVE_FOR_MERGE` verdict for #108 (or a
   scoped rejection), which unblocks #107 and #106.
4. Decide the placement of `projects/gzh-thinktank/` and whether the untracked
   motion documents are ready for a PR.
5. #105 remains open for the four content decisions listed in its body; it is
   now current with `main`.
