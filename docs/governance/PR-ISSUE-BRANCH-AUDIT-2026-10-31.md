# ContentOps — current PR / Issue / Branch governance (2026-10-31)

This file is a remote snapshot, **not evidence of access to unpushed local Windows changes**. Always re-check head SHA, GitHub checks, and source rights before a release action.

## 1. Verified state after #55 merge

- `main` = `7bc3f53e961ef5b6a4f996aaf76af674f440a757`: [#55](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/55) merged using **squash**, initial PR head `ceb48976`, Ubuntu/Windows/Repo-policy checks **3/3 PASS at PR head**. Post-merge `main` exact-SHA jobs were in progress when this revision was authored; see [#53](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/53).
- GitHub automatically removed the remote feature branch `fix/53-windows-subprocess-stdin` after #55 merge. Do not assume any local dirty worktree was deleted.
- Source `Xander-Xai/gzh-Future-Intelligence` is currently accessible to the connected GitHub account as **private**, despite GZH `MANIFEST.md` and ADR-011 making broad remote-deleted/sole-copy claims. The manifest names an earlier `yandexuanxuan` URL, so repository identity and history must be reconciled, not guessed. **P0 [#56](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/56)**.
- ContentOps is **PUBLIC**; original `xhs-FA` is **PRIVATE**. The reported 34/45 bundled Skills lacking explicit licenses require component-level provenance and redistribution permission review before any public XHS migration push. No assumption of infringement from lack of a license, and no assumption of permission from repository ownership.
- `/rulesets` returned `[]` and branch listing reports `protected=false` for `main`. The current GitHub integration receives a 403 for `/branches/main/protection`; owner-side configuration still required. See [#52](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/52).

## 2. Open PRs

| PR | Base ← head | Current state | Gate |
|---|---|---|---|
| [#48](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/48) | main ← docs/portfolio-scope-20261030 `0169fb0` | Open, ready | **Owner must approve public portfolio/ownership text** |
| [#49](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/49) | main ← feat/content-router `f401f69` | **Draft**; mergeable; exact PR-head checks 3/3 PASS | **P0 #56** source rights/provenance/privacy; human review; no bypass |
| [#50](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/50) | feat/content-router ← feat/47-x-platform-track `5210b88` | Draft, conflicts resolved / mergeable | 0 exact-head checks; rerun and verify diff after #49 merge; manual-only X publishing |
| [#54](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/54) | main ← docs/governance-audit-20261031 | Draft; this governance document | Check exact head and review before merge |
| [#55](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/55) | main ← fix/53-windows-subprocess-stdin `ceb4897` | **MERGED** at `7bc3f53` | Verify resulting main CI, then resolve #53 |

Local-only `feat/xhs-fa-migration` is reportedly at `261fd3e`, clean clone tested at `0b58303`. It is not on GitHub, **cannot** be represented as a pushed, reviewed or merged PR. Its next safe action is a licensing/redistribution audit (#51/#11/#56), not a blind public push.

## 3. Open Issue triage

| Item | Status | Acceptance / next action |
|---|---|---|
| [#7](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/7) | ACTIVE parent epic | Project still missing real content production acceptance; keep open |
| [#53](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/53) | MERGED; awaiting main verification | Main check runs for `7bc3f53` must pass before marking completed |
| [#52](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/52) | BLOCKED governance | Exact #49/#55 checks now execute; enable and verify branch protection + run child PR checks |
| [#56](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/56) | **P0 BLOCKED** | Public GZH vendor permissions, false/ambiguous retired-copy history, sanitize new receipts across commits |
| [#51](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/51) | BLOCKED | Rights-cleared XHS migration push, Draft PR, real new work, independent restoration proof |
| [#47](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/47) | ACTIVE / BLOCKED | X PR #50 0 checks and parent dependency; manual-only release |
| [#11](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/11) | OWNER DECISION | Repository license plus third-party component redistribution permissions |
| [#6](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/6) | BACKLOG | Three genuine SourceArtifact E2E builds and human acceptance |
| [#5](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/5), [#19](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/19), [#23](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/23), [#29](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/29), [#34](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/34) | BLOCKED / ACTIVE | Founder voice and media proof / actual listening and expense approvals; no automatic paid requests |
| [#15](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/15) | ACTIVE monitor | Easel upstream watch; do not upgrade without scoped evaluation |

## 4. Branches

**Keep** `main`, `feat/content-router` (#49), `feat/47-x-platform-track` (#50), `docs/portfolio-scope-20261030` (#48), and `docs/governance-audit-20261031` (#54).

**Already deleted on remote after ancestor/worktree review**: `feat/34-payg-native-first-activation` @ `a283d4b`, `feat/34-narration-v2-spoken-script-ab` @ `a64f890`, `feat/34-narration-v3-creator-director` @ `c80d76f`.

**Auto-deleted by GitHub after merge**: `fix/53-windows-subprocess-stdin` @ `ceb4897`.

**Not yet a remote branch**: `feat/xhs-fa-migration`; do not invent or reconstruct its unpushed commits from the migration report.

## 5. Required sequence

1. After #55, verify that merged `main` checks all pass; close #53 only after validating scope.
2. Resolve #56: GZH vendor provenance, license, potential private IDs and binary/artifact exposure. Keep #49 Draft until rights and security gate pass; 3/3 CI is necessary but not sufficient.
3. Owner reviews #48 separately; nothing in platform consolidation substitutes for its human wording approval.
4. Owner enables main branch protection with the three exact check names; keep #52 open until settings can be verified.
5. Only after #49 audit, restore Ready for Review and merge it under policy; validate post-merge main tests. Rebase/retarget stacked #50 only after reviewing its entire real diff; get fresh CI before any merge.
6. Do not push private XHS code or retire the old repository until #51 license/provenance, clean-clone, independent backup and one real work artifact have all been verified and the owner approves archival/deletion separately.
7. #54 is documentation-only; merge after its own exact-head CI if it remains accurate.

## No false claims

- No platform publish, paid provider call or original repository deletion was performed by this governance audit.
- A private repository being available via a connected account is **not** itself proof that the named historical upstream is the same remote.
- GitHub checks passing is **not** confirmation of third-party rights or end-user approval.
- The local xhs migration and backups are not independently visible to this remote-only audit.
