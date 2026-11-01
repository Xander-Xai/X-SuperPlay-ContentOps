# media-use pre-merge convergence and authorization boundary — 2026-11-01

Status: **PRE-MERGE / INCOMPLETE**. This is the current-state addendum to the acceptance reports in PR [#86](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/86) and PR [#89](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/89). The old reports preserve their run-specific historical evidence. This addendum does **not** retroactively rewrite those receipts.

## Verified remote snapshot

| Subject | Fact observed |
|---|---|
| Repo | `Xander-Xai/X-SuperPlay-ContentOps` |
| Current `main` | `857a6497b57fa4df2c4c88dbdcdeac70b04bbac4` — #83 organic-growth operator squash commit |
| Earlier common base | `459abb4815b163bc7c53c937c523f6190164b25c` |
| PR #86 | OPEN, not merged; HEAD `44337ff472106db99f49ba4bfd1dcd5c7f958ba7`; mergeable against GitHub's reported current snapshot |
| PR #89 | OPEN, not merged; HEAD `dd8802c5381542d5c68ec667ff2a5cdfe888acff`; mergeable against GitHub's reported current snapshot |
| Issue #57 | OPEN |
| Required checks | `Tests (ubuntu-latest)`, `Tests (windows-latest)`, `Repo policy checks` |

Both PRs had all three required checks **SUCCESS on their respective exact HEADs**. The current main also had these three checks successful. However, comparison against the new main returned **diverged, behind 1** for each PR. Those green results are therefore **not** proof of a post-convergence integration result. The #86 historical report records branch protection `strict=true`; the present branch API verified the three required check names, not a new independent strict-value read.

## P1 security review: #86 goes first

PR #86 changes `cmd_ingest` to invoke the existing `_import_rights` policy **before** `MediaUseAdapter.ingest`. The proposed `--rights-review` argument and `tests/test_media_use_ingest_rights.py` cover the direct-ingest bypass; companion changes distinguish doctor execution success from health status. The PR does not expand `ALLOWED_OPERATIONS` or change the runtime baseline.

This security fix has higher priority than sample fixture provenance. **Recommended order: #86, then #89.** This is a recommendation, not an authorization to merge.

## Three-way overlap and conflict risks

| Path | New main (#83) | #86 | #89 | Required convergence |
|---|---|---|---|---|
| `.github/workflows/ci.yml` | Added X organic-growth test steps | Added direct-ingest rights regression step | Added M5 traceability step | Preserve **all three** families of checks without duplication or deletion |
| `tests/test_m5_media_use_workflow.py` | No observed change in #83 | Adds project escape negative test | No direct file modification in #89's changed-file list | Retain #86's test and all fixture/M5 tests |
| Other files | May include router and other X changes | Ingest, execution, report | Fixture, receipts, M5 mirror | Preserve all scopes, avoid unreviewed refactors |

**Correction to earlier summaries:** PR #86 and PR #89 actually overlap at `.github/workflows/ci.yml`, but **not** at `tests/test_m5_media_use_workflow.py`: GitHub's actual PR #89 file list does not contain that test file. The latter is modified by #86 only. Do not claim a second direct file overlap. This source-of-truth table supersedes earlier conversational claims.

The shared CI patch fragments add steps at the same insertion point. This is a **possible merge conflict**, not a confirmed conflict: actual conflict resolution must occur on a branch with the new main applied. `mergeable=true` for each independent PR does not establish successful sequential integration.

## Conditional sequence and hard stops

1. **Before #86:** re-read latest `main`, #86 HEAD and branch protection. Bring new main into #86 using ordinary non-force merge when permitted; preserve #83's X checks and #86's rights-gate checks. Run full regression and all exact-head required CI. Do not merge #86 unless the Owner explicitly authorizes that specific merge.
2. **After the actual #86 squash merge:** verify real merge commit, main HEAD, and main exact-head CI SUCCESS. This event has **not happened** at the time of this report.
3. **Only then:** merge the latest `origin/main` normally into #89's branch (no force push/history rewrite), inspect any CI conflict and preserve X tests, rights-gate tests and traceability tests. Re-run all required suites on its **new** exact HEAD. Do not merge #89 without separate Owner authorization.
4. Re-verify any receipt/source digest affected by changes in canonical documentation. Keep original receipt history and explicitly record superseded generated BGM bytes.
5. If any dependency, mergeability, permission, security gate, required check or SHA changes unexpectedly, **stop and report**, rather than bypass protection.

No branch merges, PR merges or issue closures are claimed in this report.

## Acceptance and release are different verdicts

| Scope | Evidence basis | Current disposition |
|---|---|---|
| Managed `status`/`doctor` grant loop | #86 acceptance and real-adapter evidence | `FULLY_ACCEPTED` **for read-only scope on its reviewed branch** |
| M5 offline media integration | #89 clean clone, approved `hyperframes@0.8.222` host lock, verified external Easel v0.2.1 checkout, hash-bound fixtures and MP4 | `FULLY_ACCEPTED` **for the tested offline integration scope on its reviewed branch** |
| Combined #86 + #89 + current main | No combined exact-head build or CI yet | **NOT_RUN / NOT YET MERGED** |
| Full ContentOps production publication | QC `WARN` including `real_evidence_present`; `production_ready=false`, `PENDING_FOUNDER_REVIEW` | **BLOCKED** |

The phrase "clean clone reproducible" is conditional on supplying the separately verified, gitignored Easel checkout and machine-specific approved HyperFrames runtime lock; `git clone` alone is not a complete runtime installation.

## Next design-only item

Write access for `resolve`, `adopt`, `ingest`, `import` is **outside** the managed read-only gate. The design-only [ADR-011](../../docs/adr/ADR-011-media-use-mutating-authorization-proposal.md) is `Proposed`, not approved. No verbs are added, M5 is not migrated, and neither paid/network usage nor publication is authorized.

**Issue #57 remains OPEN.** Its cross-platform Skill registry/governance criteria exceed the media-use acceptance scope.
