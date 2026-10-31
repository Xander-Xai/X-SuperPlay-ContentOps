# ContentOps — PR / Issue / Branch governance register (2026-10-31)

> This is an observed **GitHub remote** snapshot, not a claim about local Windows worktrees. Do not promote a status without fresh verification. This register tracks #7, #47, #51, #52 and #53.

## Latest verified update — 2026-10-31 (supersedes older snapshot below)

**These are the latest remote checks, not statements about unpushed local assets.**

| PR | Current head | Status | Exact-head CI |
|---|---|---|---|
| [#49](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/49) | `f401f69` | Open, Ready for Review, MERGEABLE | **3/3 SUCCESS**: Ubuntu / Windows / Repo policy |
| [#50](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/50) | `5210b88` | Open, Draft, MERGEABLE; conflicts resolved | **0 check runs**; base remains `feat/content-router` |
| [#55](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/55) | `ceb4897` | Open, Ready for Review, MERGEABLE | **3/3 SUCCESS**: Ubuntu / Windows / Repo policy |
| [#48](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/48) | `0169fb0` | Open, independent owner review | prior green run |
| [#54](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/54) | this branch | Draft governance register | new-head check pending |

- The three closed-PR legacy remote branches (`feat/34-payg-native-first-activation`, `feat/34-narration-v2-spoken-script-ab`, `feat/34-narration-v3-creator-director`) have **now been deleted remotely** after preserving their head SHAs. Do not try to prune their local worktrees without a separate local state audit.
- `feat/xhs-fa-migration` is still **local-only** at owner-reported `261fd3e` (clean-clone tested at `0b58303`); remote push was blocked by the local session's permission classifier, not a network or GitHub error.
- **Public/private rights gate:** the destination ContentOps is PUBLIC; source `xhs-FA` is PRIVATE. Owner reports 34/45 bundled Skills lacking explicit license; the source core's Apache-2.0 declaration does not automatically license third-party assets. Per-component provenance and redistribution authorization must be audited **before any public push**. See [#11](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/11) and [#51](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/51).
- The GitHub `/rulesets` endpoint returned `[]` and branch listing returned `protected=false`. The connected GitHub integration was **denied** access to the branch-protection endpoint (403), so an owner-side branch-protection check remains necessary. Owner's local report says there are no main protection rules. See [#52](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/52).
- No PR merged, no platform published, no original `xhs-FA` repo archived/deleted in this update.
- #49 and #55 have green CI but **zero submitted PR reviews** as last checked; release still requires applicable human/safety review. #50 remains Draft with no checks.

### Safe next operations

1. Owner: verify rights for all bundled XHS Skills and any media before public push; never treat a permission-classifier denial as proof of GitHub connectivity failure.
2. Owner: enable main branch protection/ruleset in Settings requiring PR reviews and the three exact check names, after confirming visibility and available plan permissions.
3. Review small #55 first, then recheck #49 against updated main; review large #49 before merge. Do not bypass the owner approval decision.
4. Preserve #50 until the parent is merged and the child diff / checks are independently verified.
5. XHS PR should remain Draft and blocked pending permissions, licensing, real-work approval and clean-clone evidence.

---

## Operating rules
- One maintained ContentOps repository is the goal. Platform-specific workflows remain distinct, behind adapters and source pins.
- A PR with failed or unexecuted checks is not merge-ready. A local green run does not replace required remote checks.
- Do not force-push, reset worktrees, delete unverified branches or bypass human content/publish approval.
- Source-repository retirement is a **separate owner decision**, after a verified remote merged copy, independent restore test and real-work acceptance.
- Retain explicit release state `PLANNED / INTEGRATED / TESTED / PILOT_READY / PRODUCTION_ACCEPTED`; code presence is not public publishing.

## Live PR register

| PR | Base → Head | Verified status | Required next action |
|---|---|---|---|
| [#48](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/48) | `main` ← `docs/portfolio-scope-20261030` | Open; independent README-only portfolio copy; prior CI success | Owner review of public ownership/privacy wording before merge |
| [#49](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/49) | `main` ← `feat/content-router` | Open Draft; head `87d7701`; 101 commits / ~1,508 changed files; CI jobs failed before running steps | Independent scope/security/content review; restore exact-head CI (#52); then review and merge |
| [#50](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/50) | `feat/content-router` ← `feat/47-x-platform-track` | Open Draft; head `8196324`; conflicting, 7 ahead / 10 behind parent | Safe non-forced reconciliation; preserve GZH/video/X, test schema and routes; do not merge until #49 and exact-head checks |
| XHS migration (not yet a PR) | `feat/content-router` ← `feat/xhs-fa-migration` | **Owner-reported local-only branch; not present on remote** | Verify the local commits, scan for secrets, push branch and create **Draft stacked PR**; follow #51 |

PR #49's `mergeable=true` does **not** overrule the failing CI. PR #50's conflict concerns `docs/CURRENT-STATE.md`, the zh-CN mirror and `tests/test_account_route.py`. Recheck diff after any parent merge, especially if squash merge rewrites the parent history. The X PR and the XHS PR should not be conflated.

## Open Issue triage

| Issue | Decision / owner gate |
|---|---|
| [#7](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/7) | Parent production-runtime epic: keep open; review milestones after actual platform acceptance |
| [#47](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/47) | X integration; keep open until #50 reconciled, verified and merged |
| [#51](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/51) | XHS migration cutover, clean clone, real work, restore/retirement gate |
| [#52](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/52) | GitHub Actions billing/runner access and required check re-verification |
| [#53](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/53) | Windows non-interactive subprocess handle regression; independent of #52 |
| [#34](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/34), [#23](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/23), [#29](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/29), [#19](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/19), [#5](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/5) | MiniMax / cloned Founder voice / listening approval remain open; no unapproved paid API calls |
| [#6](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/6) | SourceArtifact and real production E2E milestone remains open |
| [#11](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/11) | Founder must decide public repository license; do not select one automatically |
| [#15](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/15) | Easel upstream watch; retain as recurring technical watch |

Do not close Issue #47 merely because X code exists on an unmerged branch. Issue #19 is still open for listening approval despite the code PR being merged. Historical closed issues and PRs stay closed.

## Branch retention / cleanup inventory

| Remote branch | Verified relation / PR | Recommendation |
|---|---|---|
| `main` | Default, head `5d1fcf2` | **PROTECT / KEEP** |
| `feat/content-router` | #49, head `87d7701` | **KEEP** until all stacked PRs are settled |
| `feat/47-x-platform-track` | #50, head `8196324` | **KEEP**; branch is conflicting |
| `docs/portfolio-scope-20261030` | #48, head `0169fb0` | **KEEP** pending owner review |
| `feat/34-payg-native-first-activation` | Closed PR #44; remote head is ancestor of `feat/content-router` | Cleanup **candidate only**, after source/worktree/backup review |
| `feat/34-narration-v2-spoken-script-ab` | Closed PR #45; remote head is ancestor of `feat/content-router` | Cleanup **candidate only**, after source/worktree/backup review |
| `feat/34-narration-v3-creator-director` | Closed PR #46; remote head is ancestor of `feat/content-router` | Cleanup **candidate only**, after source/worktree/backup review |
| `docs/governance-audit-20261031` | This document's review branch | Delete normally only after merged and independently verified |

The three old #44–#46 branch tips were separately compared against `feat/content-router` and found to be ancestors (no unique commits at their tips). This **does not authorize deletion of local dirty worktrees or unique untracked assets**. Do not use `git branch -D`, `git clean -fd` or a ref reset as deletion.

## CI evidence / required checks

Latest observed #49 Actions run `41084595479` returned failed `Tests (ubuntu-latest)`, `Tests (windows-latest)`, and `Repo policy checks`, each with **zero executed steps**. Owner reports GitHub billing/spending-limit message; billing is the leading hypothesis, but do not assert code checks passed remotely. Fix #52 and run checks on the exact PR head SHA.

Windows `test_windows_subprocess.py` headless-console failures are separate (#53). Do not skip the suite to hide them.

## Suggested integration sequence

1. **Now:** keep #49/#50 Draft; push owner-controlled XHS branch only after local safety review; open Draft stacked PR against `feat/content-router` and reference #51.
2. **CI & scope:** unblock #52, run exact SHA checks and audit #49 (including vendor provenance, credentials and repo visibility).
3. **Parent:** review/merge #49 only when all required checks and human reviews pass.
4. **Children:** re-evaluate XHS and X diffs against the resulting parent; merge XHS after real-work/clean-clone acceptance, then reconcile and merge X (order may change if dependency evidence supports it).
5. **Cleanup:** after child PRs merge, confirm no refs/worktrees depend on stale branch tips; only then prune candidate branches using normal GitHub branch deletion controls.
6. **Retirement:** independently verify backed-up XHS source assets and successful restored use, then archive original `xhs-FA` if explicitly requested. Permanent deletion requires **a separate explicit decision**.

## What cannot be verified from this remote snapshot
- Local `feat/xhs-fa-migration` commit contents, local dirty state, or claimed clean-room validation.
- Local cold bundle, 37 MB work-assets archive and whether a second independent backup exists.
- True acceptance of a new XHS post from real evidence, since local E2E relied on fixtures.
- An actual recovered Github Actions runner and required status checks.
