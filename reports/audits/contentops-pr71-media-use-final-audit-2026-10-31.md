# PR #71 final audit — media-use in the M5 chain (2026-10-31)

Status: audit complete, merge gate reached except Owner authorization.
Audited code head before this report: `50fe15ab8c391f9e63c0b1c76aa447760c7bb371`
(`feat/57-media-use-m5-integration`, after merging `main` at `1b2611d`).
This report is added in a follow-up commit on the same PR.

## 1. Scope and method

- PR: [#71](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/71) → `main`
- Contained PRs: #64 (`f118284` merge), #68 (`5f7c67f` merge), #69 (`16338cf` merge)
- Ancestry was checked from the branch, not from the earlier report:
  `git merge-base --is-ancestor` returned `0` for all three branches.
- Repo is **public**. Security and media-rights review were treated as merge gates.
- Branch protection on `main`: strict up-to-date required; required checks
  `Tests (ubuntu-latest)`, `Tests (windows-latest)`, `Repo policy checks`;
  linear history; force push and deletion disabled; conversation resolution required.
  PR #71 was `BEHIND` at audit start, so current `main` was merged in before testing.

## 2. Integration review

| Check | Result | Evidence |
|---|---|---|
| Real `MediaUseAdapter` called by M5 | PASS | `scripts/m5_production.py` imports the production class; no fake in `scripts/` or `src/` |
| `adopt → resolve → import_record → verify` order | PASS | stage receipt and real E2E |
| image/icon/logo enter asset gate and storyboard | PASS | `projects/m5-media-use` run |
| BGM/SFX written to timeline and mixed | PASS | storyboard fields + audio control renders |
| Duplicate import of identical bytes | PASS after fix | deterministic `asset_id` now refused under a second request id |
| SHA-256 verified | PASS | `verify()` before asset/storyboard use |
| Unlicensed material fails closed | PASS | `rights_reviewed` + non-empty licence required |
| Second manifest / second router | PASS | no second asset list; no router added |
| Legacy project unchanged | PASS | `projects/m5-easel-pin` full run, media_use `DISABLED` |
| `production_ready=false`, human review gate | PASS | always emitted; no code path reports otherwise |

## 3. Defects found and fixed

1. **P1 — host-specific absolute paths in receipts introduced by #68.**
   `projects/m5-easel-pin/receipts/{compose.json,m5-run.json,qc-report-m5-easel-pin.json,.md}`
   contained `D:\Projects\...\.claude\worktrees\m5-production\...`.
   Fixed by re-running the legacy project through the sanitized pipeline:
   compose and `m5-run` now use `project://`, QC is `contentops.qc-canonical/v1`,
   and the upstream reference is `easel@v0.2.1:...`.
   The regenerated video is `1,098,055` bytes, matching the previous receipt value.
2. **P1 — identical bytes could be imported under two request ids.**
   Added a deterministic `asset_id` check; the second request now blocks with a
   message telling the author to reuse one id. Regression test added.
3. **P2 — a blocked compose receipt lost its reason.**
   `compose.json` now keeps `reason` when `status != OK`.
4. **P2 — machine-path regression covered only one project.**
   The test now scans `projects/m5-media-use` and `projects/m5-easel-pin`.
5. **P2 — screenshot attribution overclaimed.**
   Wording now says “repository-classified `CREATED_BY_OWNER`; no separate capture
   receipt”, which is what the repository actually holds.

Out of scope, not changed: `projects/easel-review/receipts/*.md` already on `main`
carry the canonical repo root path. They predate this PR and are historical
records; rewriting them is a separate decision.

## 4. Real end-to-end evidence (this host, this HEAD)

Command:

```powershell
$env:CONTENTOPS_MEDIA_USE_RUNTIME_LOCK = "<verified host lock>"
python scripts/m5_production.py projects/m5-media-use
```

A fresh isolated copy under `.verify-tmp/audit-e2e/` was used so committed
receipts were not replaced during the audit. Exit code `0`.

| Fact | Value |
|---|---|
| Runtime | `TRUSTED_RUNTIME`, `hyperframes@0.8.222`, 5424 files, baseline digest matched |
| Stage chain | sources → media_use → assets → claims → script → narration → subtitles → storyboard → compose → QC → review |
| Imported visual | `project://assets/support.png`, SHA-256 `85c4ab5c…` |
| Imported BGM | `project://assets/bed.mp3`, SHA-256 `1dcb9c7e…` |
| Imported SFX | `project://.media/audio/sfx/sfx_001.mp3`, SHA-256 `075e17bd…`, Pixabay Content License |
| Provider calls | speech 0 / image 0 / video 0; network 0 |
| Video | h264 1080x1920 + AAC 48 kHz stereo, 25.067 s, 505,448 B |
| Video SHA-256 | `d4915f45f98008e4adbaa52d29beb787ffc437d383f15415780830aeaf33d731` |
| Reproducibility | byte-identical to the committed example's recorded SHA |
| QC | `WARN`, `CURRENT`, audio stream present |
| Human review | `PENDING_FOUNDER_REVIEW`, `production_ready=false` |
| Composition proof | frames at 1/2/13/14 s show the imported screenshot and captions |
| BGM proof | pause 11.70–12.20 s: −60.9 dB vs −91.0 dB without BGM |
| SFX proof | 6.15–6.28 s: −33.4 dB vs −60.8 dB without SFX |
| Narration preserved | voice window −26.8 dB in all three renders |

Legacy path: `python scripts/m5_production.py projects/m5-easel-pin` also ran
with full compose (no `--skip-compose`): exit `0`, 45.142 s, QC `PASS`,
`media_use.state=DISABLED`.

## 5. Negative controls

`11/11` blocked: missing lock, wrong lock, missing material, SHA-256 mismatch,
path escape, missing import file, network, paid, unlicensed, duplicate id,
legacy project unchanged. The same controls were re-run after the audit fixes.

## 6. Security audit (public repo)

| Check | Result |
|---|---|
| `scripts/check_receipt_secrets.py` | PASS — 71 baselined paths, 0 new |
| `scripts/check_repo_policy.py` | PASS |
| High-confidence key patterns in reachable history (`ghp_`, `github_pat_`, `AKIA`, `sk-`, private key, Slack, JWT) | 0 commits |
| Added lines in PR diff matching those patterns | 0 |
| Sensitive filenames tracked (`.env`, `auth.json`, keys, cookies) | 0 |
| `.verify-tmp/`, `.local/`, `diagnostics/`, `outputs/` tracked | 0 |
| Private host/user paths in PR files | 0 (only the test's own detection regex) |
| `Bearer` history hits | 4 commits; non-credential test/header fixtures, remediated by `f426c47` (“assemble the bearer fixture at runtime”) |

No live credential was found. No history rewrite was performed.

## 7. Licence and media-rights audit

| Item | Evidence | Status |
|---|---|---|
| HyperFrames code | `package.json` declares `Apache-2.0`; upstream repository is Apache-2.0 | PASS |
| Executed package | `hyperframes@0.8.222`, SRI recorded, dependency lock and package-tree digest approved | PASS |
| Bundled SFX | skill `audio/assets/sfx/CREDITS.md`: Pixabay Content License | PASS |
| BGM | deterministic local ffmpeg tone bed, `OWNED-GENERATED-LOCAL`, not catalog music | PASS |
| Example screenshot | repository-classified `CREATED_BY_OWNER`; no separate capture receipt | WEAK EVIDENCE, not a licence conflict |
| Third-party media committed by the PR | none (`git diff --name-only` has no media extension) | PASS |

`rights_reviewed: true` is recorded as an operator assertion, not as commercial
clearance. Every import is `evidence_capable=false`, `production_ready=false`,
`PENDING_FOUNDER_REVIEW`. Nothing here authorises publication.

## 8. QC `WARN` analysis

The report is `WARN` for exactly three checks; none is a calculation crash or a
reason to change thresholds.

| Check | Reading | Classification |
|---|---|---|
| `duration_range` | 25.07 s vs floor 30 s | **Expected technical-sample limitation.** Production blocker; not an integration blocker. |
| `real_source_ratio` | 0.0 | **Expected policy outcome.** Every shot is `LICENSED_EXTERNAL` / `evidence_capable=false`; no `REAL_*` shots. The WARN is correct for evidence-first production. The ratio display counts only real/generated shots, so 0/0 reads as 0.0; this is a reporting-clarity gap, not a verdict bug. |
| `real_evidence_present` | 0 | **Expected policy outcome.** `sources/assets.json` is empty and media-use visuals are not evidence. |
| Voice | `voice_not_silence` PASS, `voice_quality_declared` INFO | Windows SAPI is a declared fallback; production voice quality is still a known blocker, not an integration failure. |

No threshold, fixture or statistic was changed to turn these green.

## 9. Merge gate

| Gate | Status |
|---|---|
| SECURITY_AUDIT | PASS |
| LICENSE_AUDIT | PASS (rights-evidence weakness recorded, non-blocking for a technical sample) |
| CODE_REVIEW | PASS |
| INTEGRATION_TESTS | PASS — 53 adapter, 18 evidence, 17 workflow, 97 convergence; `dev_check.py` PASS |
| CI_WINDOWS | PASS on audited code head; final report commit re-checked by PR CI |
| CI_UBUNTU | PASS on audited code head; final report commit re-checked by PR CI |
| CI_POLICY | PASS on audited code head; final report commit re-checked by PR CI |
| BRANCH_PROTECTION | PASS — strict, required checks, linear history |
| MAIN_DIFF_REVIEW | PASS — merge of current `main` is documentation only; no unrelated feature merged |
| OWNER_MERGE_AUTHORIZATION | **PENDING** |

`PR71_READY_FOR_MERGE = YES` once the CI run on the report commit is green.
`PR71_MERGED = NO` — this audit does not authorise merging `main`.

## 10. Governance recommendations (after Owner authorisation)

1. Squash-merge #71 into `main`; do not merge #64/#68/#69 separately.
2. After verifying `main` contains the adapter, M5 entry, tests and baseline,
   close #64/#68/#69 as **Superseded** with the #71 merge commit link.
3. Keep Issue #57 **OPEN**: the global Skill Router is still unmerged
   (`feat/content-router`; no `scripts/skill_route.py` on `main`).
4. Delete remote branches only after confirming no independent commits remain and
   with explicit deletion authorisation.
5. Follow-ups, not mixed into #71: router registration (#57), per-track fades,
   rights-evidence receipts, real-evidence content quality, human commercial
   review, host-lock deployment guidance.

## 11. Evidence boundary

`INTEGRATION_VERIFIED` means this host, this lock and this HEAD. It is not
`MERGED_TO_MAIN`, not a production approval, and not a licence grant. The hosted
CI runs offline/fixture suites only; the runtime-lock and compose evidence above
is machine acceptance and is labelled as such.
