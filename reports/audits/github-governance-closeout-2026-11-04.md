# Governance Closeout — 2026-11-04

> Scope: bring the repository to **zero open PRs, zero open issues, only
> `main` as a branch and only the primary worktree**, without claiming that
> descoped work was delivered. Owner decisions were taken on 2026-11-04:
> Apache-2.0 license; descope and archive #6/#51/#56/#94; archive unmerged
> work; stop the upstream watch from creating issues.

## 1. Decisions recorded

Recorded in [ADR-018](../../docs/adr/ADR-018-governance-closeout-scope.md):

1. Repository license is **Apache-2.0** (`LICENSE`, standard text).
2. #6, #51, #56 and #94 are **descoped**, not completed; they move to
   [DEFERRED-WORK.md](../../docs/DEFERRED-WORK.md).
3. X execution authority stays **manual**; #100 D-3/D-4 are deferred.
4. The upstream watch writes a workflow summary and artifact; it no longer
   creates or updates an issue.
5. Target state: zero open PRs, zero open issues, `main` only.

## 2. Archive

Root: `D:\Archives\contentops\2026-11\`
Manifest (bytes + SHA-256): `D:\Archives\contentops\2026-11\INDEX.md`

| Kind | Contents |
|---|---|
| Branch bundles | `main`, `feat/content-router`, `fix/56-gzh-provenance`, `feat/xhs-fa-migration`, `feat/106-easel-host-dual-line`, `codex/motionclone-contentops-20261102`, `feat/47-story-studio-episode`, `feat/47-x-platform-track`, `worktree-agent-a05b8f460dac8dc34` |
| Worktree patches | `codex_motionclone`, `agent_a05b8f46`, `story_studio`, `x_track` |
| Worktree tarballs | the same four trees (tracked + untracked, excluding `.git`) |
| Main working tree | `patches/main-worktree-wip.patch`; the three untracked planning/research files; `projects/gzh-thinktank/` (packed) |

All nine bundles passed `git bundle verify` **before** any source ref was
deleted. The archive is the only copy of the removed branches; it is not
deleted by this change.

## 3. Per-item disposition

| Item | Disposition | Evidence |
|---|---|---|
| #6 three E2E videos | descoped | DEFERRED-WORK D-1; M5 chain remains on `main`, `production_ready: false` |
| #51 XHS migration | descoped | DEFERRED-WORK D-2; branch archived |
| #56 GZH rights | descoped | DEFERRED-WORK D-3; `main` has 0 GZH files; branch and working tree archived |
| #94 S3–S4 | descoped | DEFERRED-WORK D-4; S1/S2 remain on `main` |
| #100 D-3/D-4, X authority | deferred | ADR-018 D3; no authority granted |
| #15 upstream watch | converted | ADR-018 D4; report is a summary + artifact, no issue |
| #11 license | delivered | `LICENSE` Apache-2.0 + ADR-018 D1 |
| Motion-study feature | archived | DEFERRED-WORK D-5 |
| Tier-1 doc convergence WIP | archived | DEFERRED-WORK D-6 |
| `gzh-thinktank` working data | archived | `untracked/gzh-thinktank.tar.gz` |

## 4. What this report does **not** claim

- No rights audit was performed for #51 or #56. They are excluded from the
  active scope; the archived material still needs the audits if reopened.
- No E2E video was produced for #6, and no S3/S4 slice was built for #94.
- No X execution authority was granted. Publication remains manual.
- No host dependency was installed and no host was started.
- `production_ready` remains `false`; publication count remains `0`.

## 5. Verification performed in this change

| Check | Result |
|---|---|
| `python scripts/dev_check.py` | run on the closeout branch |
| Working tree document links | `check_docs.py` |
| Bilingual structure | `check_i18n.py` |
| Bundle integrity | 9/9 `git bundle verify` OK |
| Archive manifest | SHA-256 recorded for every file |

The branch/worktree/issue counts reach zero only **after** this PR merges and
the archived refs are deleted; the final verification is recorded in the PR
conversation and in the closing comment on #7.

## 6. Statement of effect at report time

| Item | Value |
|---|---|
| Open PRs | 1 (this closeout PR) |
| Open issues | 8, all scheduled to close with a named disposition |
| Non-main remote branches | 2 (`feat/content-router`, `fix/56-gzh-provenance`) |
| Local branches | 9 |
| Worktrees | 5 |
| Files moved to archive | 22 files (bundles, patches, tarballs, planning docs) |
| Files deleted before verification | none |
