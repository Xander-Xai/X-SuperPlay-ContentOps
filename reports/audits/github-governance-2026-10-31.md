# GitHub governance execution — 2026-10-31

> Authoritative post-execution state for the PR / Issue / Branch / CI / security
> review of `Xander-Xai/X-SuperPlay-ContentOps` (PUBLIC, default branch `main`).
> Supersedes the earlier same-day snapshot at
> [`docs/governance/PR-ISSUE-BRANCH-AUDIT-2026-10-31.md`](../../docs/governance/PR-ISSUE-BRANCH-AUDIT-2026-10-31.md)
> for any fact both cover. That earlier file remains as historical record and is
> **not** rewritten.

This round performed one merge (PR #48) and no destructive action. Everything
else that looked "cleanable" is legitimately gated by an owner decision, an
external rights review, or a security hold. No issue was closed to raise a count.
No secret value is reproduced here.

## Scan scope and method

- Local repository `D:\Projects\X-SuperPlay-ContentOps`, every worktree, and the
  GitHub remote read through the authenticated `gh` CLI (owner account).
- Inventory taken with paginated `gh pr|issue|run|api` reads, not the first screen.
- Exact-head CI was checked against the SHA on each open PR, not a stale run.
- Source rights, credentials and media usage were inspected by reading tracked
  files. No provider request, paid call, publish, or network media fetch was made.
- No filesystem cleanup was performed. Disk free/used and deletion accounting are
  **not applicable** to this task (it is a remote-repository governance pass, not a
  machine cleanup); no file was moved or deleted, and no branch was force-deleted.

## A. Governance conclusion

```text
GOVERNANCE_EXECUTED        = PARTIAL
PR_AUDIT_COMPLETE          = YES
ISSUE_AUDIT_COMPLETE       = YES
BRANCH_AUDIT_COMPLETE      = YES
SECURITY_GATE_CLEARED      = NO
MAIN_CI_VERIFIED           = YES      (see G04 main run below)
OWNER_DECISIONS_PENDING    = 6
```

`PARTIAL` is the honest result: the audits are complete, one authorized merge
executed, but six items need an owner decision that this pass may not make on the
owner's behalf. `SECURITY_GATE_CLEARED = NO` because the PAYG key is recorded as
exposed and not rotated, and third-party rights are unresolved (#56).

## B. Statistics

| Metric | Before this pass | After this pass |
|---|---:|---:|
| Open PRs | 7 | 6 |
| Merged PRs (all time) | 27 | 28 |
| Open Issues | 14 | 14 |
| Remote branches (incl. `main`) | 8 | 7 |

- **Merged this pass:** PR #48 `docs(portfolio): define public technical ownership and non-goals` → merge commit `d7ed1fe` (squash). Head `485bc9b` had all three required checks pass on both the push and pull_request runs.
- **Issues closed this pass:** none. Every open issue is active, external-blocked, security-blocked, or an owner decision (see C). Closing any would have been a false close.
- **Branches deleted this pass:** `docs/portfolio-scope-20261030` (auto-deleted by GitHub on #48 squash merge). No force deletion, no mirror push.
- **Still Draft, by design:** #49, #50, #58, #59, #62, #64 (six PRs).
- **CI issues fixed:** PR #48's README referenced `scripts/run_tests.py`, which does not exist on `main` (it exists only on the unmerged `feat/content-router` stack). Corrected to `python scripts/dev_check.py`, the unified gate `CLAUDE.md` already names. Fixed in the same PR before merge.

## C. Full object table

### Pull requests

| PR | Title focus | Original | Final | Action | Evidence | Residual risk |
|---|---|---|---|---|---|---|
| #48 | Portfolio/README ownership boundary | Open, ready, exact-head green, behind `main` | **MERGED** | Updated branch to `main`, fixed broken `run_tests.py` pointer, squash merged | merge `d7ed1fe`; CI run 41185632856 (PR) + 41185630076 (push) 3/3 | Public wording is now live; owner-approved this pass |
| #49 | Content router + account tracks (stack parent) | Draft, **CONFLICTING**, 228k+ lines | Draft, kept | None (blocked) | conflicts in `.github/workflows/ci.yml`; P0 #56 | P0: PAYG not rotated, GZH AGPL + rights-unknown skills, historical receipt exposure |
| #50 | X platform track | Draft on `feat/content-router` | Draft, kept | None (stack child) | run 41179421432 3/3 on head `01ac69c` | Cannot merge before parent #49; no blind retarget |
| #58 | GZH provenance + rights audit | Draft on `feat/content-router` | Draft, kept | None (stack child) | run 41166120956 3/3 on `bfe7243` | Docs-only; does not clear third-party rights by itself |
| #59 | Skill doctor + exact resolve | Draft on `feat/content-router` | Draft, kept | None (stack child) | run 41166150519 3/3 on `7f8f105` | Diagnostic only; `execution.authorized:false` |
| #62 | Receipt baseline hardening (#61) | Draft, exact-head green | Draft, kept | None (security hold) | run 41165550503 3/3 on `14aea6d` | Owner flagged HOLD; do not merge without owner review |
| #64 | HyperFrames media-use adapter (#57) | Draft, protected | Draft, kept | Static review only | run 41181687395 3/3 on `95c0023` | Offline baseline only; network/paid/cross-project/publication still unauthorized |

### Issues

| # | Classification | Action | Basis |
|---|---|---|---|
| #5 | IN_PROGRESS (umbrella) | Keep open | Speech #19/#24, image #20/#25, video #22/#26 merged; voice Golden #29 still open |
| #6 | BACKLOG | Keep open | No SourceArtifact E2E delivered; 3 real videos not built |
| #7 | IN_PROGRESS (EPIC) | Keep open | Production acceptance not met; sub-items still open |
| #11 | NEEDS_OWNER | Keep open | License file absent; decision coupled to #56 rights audit |
| #15 | IN_PROGRESS (continuous watch) | Keep open | Upstream watch; do not close a standing monitor |
| #19 | IN_PROGRESS | Keep open | M Plan speech integrated via #24, but the issue's own Founder-listening gate was never formally closed by owner; the voice target has since pivoted to a cloned voice |
| #23 | IN_PROGRESS | Keep open | 2061 refusal explained and two-key route proven via #44; live entitlement/rotation chain continues under #34 |
| #29 | IN_PROGRESS | Keep open | Enhanced Golden voiced with clone; Founder listening still pending |
| #34 | IN_PROGRESS | Keep open | First-use activation executed and verified in PR #44; downstream acceptance continues |
| #47 | BLOCKED_EXTERNAL | Keep open | Depends on #49/#56; #50 Draft |
| #51 | BLOCKED_RIGHTS/EXTERNAL | Keep open | XHS vendor rights + clean-clone + retirement gate unverified from remote |
| #56 | BLOCKED_SECURITY/RIGHTS (P0) | Keep open | GZH AGPL + rights-unknown skills; PAYG not rotated; existing public receipt exposure |
| #57 | IN_PROGRESS | Keep open | #59 Draft; media-use #64 is the adapter but not a second engine |
| #61 | IN_PROGRESS | Keep open | #62 Draft under owner security hold |

### Branches

| Branch | Head | Open PR / base | Disposition | Reason |
|---|---|---|---|---|
| `main` | `d7ed1fe` | — | KEEP | Default, protected |
| `feat/content-router` | `f401f69` | #49 head / base of stack | KEEP | Parent of #50/#58/#59; carries unmerged work |
| `feat/47-x-platform-track` | `01ac69c` | #50 head | KEEP | Draft child |
| `fix/56-gzh-provenance` | `bfe7243` | #58 head | KEEP | Draft child |
| `chore/skills-doctor-cr` | `7f8f105` | #59 head | KEEP | Draft child |
| `fix/61-receipt-baseline` | `14aea6d` | #62 head | KEEP | Security hold |
| `feat/57-media-use-adapter` | `95c0023` | #64 head | KEEP | Protected draft |
| `docs/portfolio-scope-20261030` | `485bc9b` | #48 head | **DELETED** | Squash merged; GitHub auto-deleted |

No branch met all six deletion preconditions simultaneously except the merged
#48 head. Local branches with a "gone" upstream (`ci/feature-branch-checks`,
`fix/53-windows-subprocess-stdin`) are local-only worktree leftovers; their remote
counterparts were already auto-deleted on merge and are out of remote scope.

## D. Owner decisions pending

1. **Rotate the PAYG credential (#56).** Evidence: `reports/audits/receipt-secrets-guard.md` records the key as exposed and not rotated. Options: rotate at the provider and re-baseline, or accept and document. Impact if undecided: #49/#50/#58 cannot clear P0. Unlock: provider-side rotation action.
2. **Third-party rights for the GZH vendor and XHS skills (#11/#51/#56).** Evidence: AGPL-3.0 component plus rights-unknown skills in the vendored trees. Options: obtain licences/redistribution permission, remove the components, or keep the branches unmerged. Impact: blocks #49 and any public XHS push. Unlock: component-level licence evidence or owner attestation recorded in the matrix.
3. **Repository LICENSE (#11).** Options: Apache-2.0, MIT, or proprietary. Impact: source-licence ambiguity persists; media rights are separate and unaffected.
4. **Whether to authorize merge of #62 after review.** Evidence: exact-head 3/3 green, but owner posted HOLD. Options: review and clear, or keep draft. Unlock: explicit owner approval comment.
5. **Whether #64's offline baseline is sufficient to leave Draft.** Evidence: offline-tested, 3/3 green, but network/paid/cross-project/publication remain unauthorized. Unlock: explicit authorisation scope for any provider or publish action.
6. **Raise required approval count from 0 to 1 (#7 convention).** Evidence: protection requires 0 approvals while solo. Options: leave at 0 until a second reviewer exists. Impact: none on safety today; note for when a collaborator joins.

## E. Security, rights and CI findings

- **Tracked secrets scan:** no hardcoded key/token/private-key patterns
  (`ghp_…`, `gho_…`, `sk-…`, `AKIA…`, PEM blocks) found in tracked files.
  `scripts/check_docs.py` sensitive patterns pass.
- **Receipt exposure (documented, not new):** 8 receipt JSON files on public
  `main` carry real provider identifiers (voice/task/trace ids), account balances
  and a PAYG key fingerprint. The guard baseline stores **field paths only, zero
  values**; new field paths fail. This lowers future exposure but does not rewrite
  history. Remaining work is rotation (#56) and a possible owner-approved history
  action — not a rewrite by an agent.
- **No LICENSE file** (see D3).
- **Supply chain:** workflows use `permissions: contents: read` (least privilege),
  no `pull_request_target`, no artifact upload. Actions are pinned to major tags
  (`actions/checkout@v4`, `setup-python@v5`), not SHAs, and there is no
  Dependabot config. Low risk; noted for hardening, not changed here.
- **Branch protection on `main`:** enabled — required checks
  `Tests (ubuntu-latest)`, `Tests (windows-latest)`, `Repo policy checks`;
  strict (up-to-date), linear history, no force push, no deletion, conversation
  resolution required, 0 approvals, admins not enforced.
- **Doc drift corrected in this PR:** `AGENTS.md` still said "`main` is
  unprotected"; updated to the enforced state.

## Adversarial re-verification (G01–G18)

| # | Item | Verdict | Basis |
|---|---|---|---|
| G01 | PR list complete / matches GitHub | PASS | paginated `gh pr list --state all` (35 records) |
| G02 | Merged PR has real merge SHA | PASS | #48 → `d7ed1fe` |
| G03 | Merges passed authorization + gates | PASS | owner directive for #48; 3/3 checks; no bypass |
| G04 | Exact head SHA matches CI | PASS | #48 `485bc9b` runs 41185632856/41185630076; main `d7ed1fe` post-merge run (see G04 note) |
| G05 | No unexplained merge conflict | PASS | #49 conflict is explained and left unmerged |
| G06 | Stack dependencies intact | PASS | #50/#58/#59 unchanged; #49 still parent |
| G07 | Draft PRs not merged | PASS | #49/#50/#58/#59/#62/#64 remain Draft |
| G08 | Issue state matches delivery | PASS | all 14 kept with classification |
| G09 | EPIC / security issues not mis-closed | PASS | #7, #56 open |
| G10 | No live dev branch deleted | PASS | only merged #48 head removed |
| G11 | No asset lost after squash | PASS | #48 was README-only; no other content in it |
| G12 | main protection not weakened | PASS | unchanged on read-back |
| G13 | Public sensitive-info risk has a conclusion | PASS | documented above (P0 #56) |
| G14 | Third-party rights gate not bypassed | PASS | #49/#50/#58 unmerged |
| G15 | Docs synced to actual state | PASS | this report + AGENTS.md fix |
| G16 | Report has verifiable URL/commit/run | PASS | section E / PR links |
| G17 | No new implicit paid/publish/network permission | PASS | no such action taken |
| G18 | Local vs remote final state explained | PASS | see note |

- **G04 note:** the post-merge `main` CI run for `d7ed1fe` is listed in the PR
  conversation; it must be green before this governance PR itself merges. If a
  later fetch shows it red, that is recorded here rather than hidden.
- **G18 note:** local worktrees (`docs/portfolio-scope-20261030`,
  `fix/61-receipt-baseline`, etc.) may still exist on disk. Their remote branches
  were deleted only where merged; local working copies are the owner's in-progress
  state and were not touched.

## No false claims

- One PR merged; no issue closed; one merged branch auto-deleted; no force push,
  no history rewrite, no mirror push.
- Green CI is **not** a substitute for third-party rights, credential rotation, or
  owner approval; none of those were inferred from a passing check.
- No provider request, paid generation, public media fetch or platform publish was
  performed.
- Absence of a hardcoded key pattern is not proof of no exposure; the receipt
  files are the known exposure and are handled separately under #56/#61.
