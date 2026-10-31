# ContentOps phase-2 — security, rights and PR unblock (2026-10-31)

> Read-only audits plus one shipped security fix and one simulated merge, all
> measured against the live remote. No secret value is reproduced; no provider,
> paid, publish, network or history action was taken. This file consolidates the
> four requested artifacts and cross-references the detailed files already on the
> `fix/56-gzh-provenance` branch (#58) instead of duplicating them.

Baseline at start: `main` = `681ef5d`; 6 open Draft PRs; 14 open Issues; 7 remote
branches. Re-read from GitHub at execution time, not assumed.

## 1. P0 credential and public-exposure status

| Question | Finding | Evidence |
|---|---|---|
| Which credential class was exposed | A PAYG (pay-as-you-go) provider key | Two receipts record an exposure flag and a "not rotated" note |
| Is the key value itself in the repo | **No** | Full-tree scan of tracked files found no key/shape; only an identifier fingerprint |
| What *is* public | A 12-hex `payg_key_fingerprint` (identifies the credential, not the key), raw `voice_id` (18-char), provider `task_id`/`trace_id`/`file_id`, and account balances | 10 receipt JSON/MD files on `main`; 1 carries the fingerprint there |
| Still valid / abnormal spend | **UNVERIFIED** — no provider access was used and no request was made (forbidden this round) | n/a |
| Rotation done | **NO** — `NOT_ROTATED` | `reports/audits/credential-rotation-status.md` on #58 |
| History | The exposed files entered `main` across public commits 2026-10-06 → 10-12 (#30/#31/#32/#35–#43) | `sensitive-receipts-2026-10-31.md` on #58 |

**Order of remediation: rotate first, history second.** A history rewrite cannot
recall forks, clones or caches and needs explicit owner authorisation; neither was
performed.

### Redacted public-exposure risk matrix

| Location | Risk type | Sev | Exposure | Verification | Remediation | Owner gate |
|---|---|---|---|---|---|---|
| `projects/easel-enhanced-golden/receipts/` (8 files) | Raw provider IDs + balances | P1 | `main` (public) | Confirmed by scan | Move to hashes/summaries; keep raw in ignored dir | No (engineering) |
| `…/founder-voice-cash-activation-receipt.json` | PAYG key fingerprint (credential identifier) | P1 | `main` | Confirmed | Remove/rotate-linked; never re-add | Yes (rotation) |
| `research/providers/receipts/*.sanitized.json` | Provider task/trace ids (sanitized) | P2 | `main` | Confirmed | Already sanitized; keep policy | No |
| #49 branch `founder-voice-*.json` (5 files) | Raw voice/balance ids | P1 | public **branch** | Confirmed | Same policy before any merge | Yes (with #49) |
| Exposed PAYG key itself | Live credential misuse | P0 | outside repo, assumed leaked | Unverified | **Rotate at provider** | Yes |
| Public history (commits above) | Historical exposure | P2 | `main` history | Confirmed | Owner decides rewrite vs accept | Yes |

## 2. Security fix shipped this round — PR #62

The diff-relative guard was correct (compares value at each baselined path to a
trusted base, stores no values or hashes). One real detection gap was found and
fixed on the PR branch:

- **Gap:** the text scanner matched only key prefixes (`sk-`/`ghp_`/`AKIA`/private-key
  blocks). A receipt carrying a credential in a URL — `scheme://user:pass@host` or a
  signed query param (`X-Amz-*`, `GoogleAccessId`, `token`, `secret`, `password`, …)
  — passed silently.
- **Fix:** added `URL_CREDENTIAL` detection to the text-token scan, plus 8 adversarial
  tests (credential-URL userinfo, signed-query URL, plain URL must NOT flag, changed
  array element, multiple files, benign new field, non-UTF-8 receipt, Windows path
  normalisation). **Fail-first:** the two URL tests failed before the change.

| Check | Result |
|---|---|
| `python tests/test_receipt_secrets.py` | **24 passed** (was 16) |
| `python scripts/check_receipt_secrets.py --base origin/main` | PASS — 71 baselined paths, **0 new** (URL rule does not false-positive on existing receipts) |
| `python scripts/dev_check.py` | **ALL CHECKS PASSED** |
| Exact-head CI on `05bb447` | **3/3** — run 41187654423 (ubuntu, windows, repo policy) |

PR #62 remains **Draft** and the owner **HOLD stays ACTIVE**. This round does not
release it or merge it.

## 3. GZH / XHS third-party rights matrix

Full per-skill matrix (41 rows + archived) is at
`reports/audits/gzh-skill-license-matrix.md` on #58; machine-readable rights at
`config/gzh-skill-rights.json`. Summary of the audit already performed and spot-
checked here:

| Class | Count | Meaning | Action |
|---|---:|---|---|
| OWNED_AND_CLEARED | 22 active + 9 archived | Git authorship in the owner's private repo, no third-party marker | keep |
| THIRD_PARTY_LICENSE_VERIFIED | 9 | MIT/ISC verified with source + notice | keep with notice |
| RESTRICTED | 2 | Copyleft/non-commercial obligation | owner decision |
| OWNER_ATTESTED | 3 | Owner notice only, no file-level provenance | hold public release until evidence |
| RIGHTS_UNKNOWN | 5 | No licence/author/source | block dispatch; obtain permission or replace |

**RESTRICTED components**

- `gzh-design-skill` — **AGPL-3.0** (copyright 甲木 × 摸鱼小李). A *required* HTML
  validator invoked by `workflow_gate.py`/`verify_draft_submission.py`. Verbatim,
  separate directory, not linked into ContentOps Python. Distribution is allowed
  under AGPL with source+licence, but it is **not permissive** and cannot be
  relicensed here. Network-service operation would trigger AGPL §13. Removing it
  breaks the HTML gate with no equal replacement → **owner must accept AGPL or fund
  a replacement.** Not a legal opinion; mark `LEGAL_REVIEW_REQUIRED` if contested.
- `deep-research` — **CC BY-NC 4.0** (non-commercial). Blocked for this commercial
  context; obtain permission or replace.

**RIGHTS_UNKNOWN / OWNER_ATTESTED on hold:** `content-repurposer`,
`exa-web-search-free`, `midu-proofread`, `vision`, `wechat-viral-topic` (unknown);
`content-humanizer`, `content-production`, `content-strategy` (attested only).

**XHS:** the xhs-FA migration is local-only and not on the remote; there is no remote
XHS branch to audit component-by-component. Rights for the ~30 XHS skills remain
unknown and must be cleared before any public push (#51). **XHS_RIGHTS_CLEARED = NO.**

Only the owner's own statement (not a licence) backs the attested set; absence of a
licence is recorded as unknown, not as infringement, and ownership of a private repo
is not proof of third-party permission.

## 4. PR #64 — media-use offline verification

Verified by code reading + the branch's own 53 tests (all pass) + direct fail-closed
runs. No provider, network or paid call.

- **Trust chain:** a runtime is trusted only if a machine lock names the approved
  baseline by SHA-256, the baseline is `approved`, package/version/integrity match,
  the installed dependency-lock digest matches, the entry stays inside the root, the
  **package-tree digest pinned in the baseline** matches (so re-hashing a tampered
  tree still mismatches), and the pinned **node binary sha256** matches. Editing a
  file plus its per-file hash does not help — the baseline tree digest catches it.
- **Fail-closed default:** with no lock, `verify` → `trusted:false`,
  `DEPENDENCY_UNVERIFIED`; `selfcheck` → `RUNTIME_NOT_TRUSTED`. Lock without node
  hash → not trusted; unapproved baseline → blocks a valid lock; lock from a different
  baseline → refused.
- **Evidence boundary:** `LICENSED_EXTERNAL` is never evidence-capable and never
  `generated`; generated resolution is not importable; import requires a licence;
  URL userinfo/query/fragment stripped from source URIs; the child process is
  argv-only and never receives a credential; every import gates to
  `PENDING_HUMAN_REVIEW`, not ready; cross-project reuse refused unless asked.

Acceptance: **OFFLINE = PASS.** The committed approval text is explicitly limited to
offline local asset operations — network, paid providers, cross-project reuse,
publication and production readiness are **not** authorised.

```text
MEDIA_USE_OFFLINE_RUNTIME  = PASS
MEDIA_USE_SECURITY_GATE    = PASS (offline scope only)
MEDIA_USE_PRODUCTION_READY = NO
MEDIA_USE_MERGE_AUTHORIZED = NO
```

## 5. PR #49 stack — unblock analysis

Dependency graph re-checked live: `main → #49 (feat/content-router)` with children
#50, #58, #59 all based on `feat/content-router`; #58/#59 merge-base = `f401f69`
(parent tip). #49 is still `CONFLICTING/DIRTY` against `main`.

**Conflict simulated in an isolated worktree** (branch `phase2/pr49`, merge commit
`1d43b35`, **not pushed**). Conflicts were exactly two files:

- `.github/workflows/ci.yml` — `main` (after #63) rewrote `on:` to add feature-branch
  triggers + concurrency + `workflow_dispatch`; `feat/content-router` instead added
  `PYTHONUTF8: "1"` and ~314 lines of content-router test steps but kept the old
  `on:` and lacked the receipt-secret step from #60. **Resolution = union:** keep
  `main`'s trigger/concurrency block and content-router's added steps **plus** main's
  receipt-secret step. Verified: YAML parses; `Tests`/`Repo policy` jobs intact;
  feature triggers, `workflow_dispatch`, concurrency, `PYTHONUTF8`, and the
  receipt-secret step all present; **`run_tests.py --missing-from ci.yml` → "every
  suite is run (73 suites checked)"**. No check was weakened or removed.
- `docs/INDEX.zh-CN.md` — keep content-router's richer audit description + the
  governance-report line from #66. Resolved; English `INDEX.md` auto-merged with both
  lines present.

**No duplicate engine:** one `scripts/skill_route.py` (the vendored
`skill_resolver.py` lives inside the third-party GZH tree under audit, not a
ContentOps engine). One media-manifest receipt. #59 modifies the existing router; it
does not add a second. The bulk of #49's additions are `research/vendor/dy1024-design-*`
— i.e. more third-party provenance to clear, not new duplication.

**This does not clear P0.** #49 still carries the vendored GZH (AGPL + unknown) tree
and the 5 extra raw-id receipts. Conflict is now a solved engineering step; the
content gate is not.

### PR unblock matrix

| PR | What it still lacks | Blocking class | Ready when |
|---|---|---|---|
| #49 | P0 #56 rights + PAYG rotation; merge conflict (resolution proven, `1d43b35`, unpushed); owner review | Security + Rights | Rights cleared + key rotated + owner review |
| #50 | Parent #49 merge; retarget to new `main`, then fresh exact-head CI | Dependency | #49 merged first |
| #58 | Parent #49; and a checker that blocks *actual* vendored runner callsites (not just path scans) | Dependency + Rights | #49 merged + callsite test |
| #59 | Parent #49; exact-head CI on retarget | Dependency | #49 merged first |
| #62 | Owner review to lift HOLD (tests now PASS) | Owner | Owner approval comment |
| #64 | Owner scope decision to leave Draft | Owner | Explicit offline-vs-prod decision |

## 6. Latest GitHub state (re-read)

| Item | Value |
|---|---|
| `main` | `681ef5d` (unchanged this round) |
| Open PRs | 6, all Draft (#49, #50, #58, #59, #62, #64) |
| PR #62 head | `05bb447` (this round's fix), 3/3 CI |
| Open Issues | 14 |
| Remote branches | 7 (`main` + 6 PR heads) |

## 7. Exact-head CI

| Ref | SHA | Runs |
|---|---|---|
| main | `681ef5d` | run 41186500179 success |
| PR #62 | `05bb447` | run 41187654423 3/3 (ubuntu, windows, repo policy) |

## 8. Final acceptance

```text
P0_CREDENTIAL_ROTATED        = NO
P0_PUBLIC_EXPOSURE_AUDITED   = PASS
GZH_RIGHTS_CLEARED           = PARTIAL   (matrix built; restricted/unknown remain)
XHS_RIGHTS_CLEARED           = NO
PR62_SECURITY_TESTS          = PASS
PR62_OWNER_HOLD              = ACTIVE
PR64_OFFLINE_VERIFIED        = PASS
PR64_PRODUCTION_AUTHORIZED   = NO
PR49_CONFLICT_PLAN_READY     = YES
PR49_SECURITY_GATE_CLEARED   = NO
CI_EXACT_HEAD_VERIFIED       = YES
OWNER_DECISIONS_PENDING      = 6
```

## A. Executed fixes

- PR #62 (`05bb447`): credential-bearing-URL detection in the receipt guard + 8
  adversarial tests. 24 tests pass; real-repo check 71 baselined / 0 new; full gate
  passes; CI 3/3.
- Simulated #49 merge (`1d43b35`, local only): resolved `ci.yml` and `INDEX.zh-CN`
  by union; 73 suites still wired; no CI check weakened. Not pushed to the
  P0-blocked PR.

## B. GitHub operations

- Updated PR #62 branch head to `05bb447` (push to `fix/61-receipt-baseline`).
- No PR merged, no Issue closed, no branch deleted this round.
- Evidence comments posted to the relevant Issues/PRs (see the issue threads).

## C. Owner minimal decisions

1. **Rotate the PAYG key** at the provider; then set `Rotation status: ROTATED` in
   `credential-rotation-status.md` (no key/fingerprint). Unlocks P0.
2. **GZH rights:** accept AGPL for `gzh-design-skill` (or fund a replacement) and
   resolve `deep-research` (CC BY-NC) + the 5 unknown / 3 attested skills.
3. **XHS rights:** clear the ~30 XHS skills before any public push (#51).
4. **LICENSE:** choose Apache-2.0 / MIT / proprietary (root licence does not cover
   third-party components) (#11).
5. **#62 merge:** review and clear the HOLD.
6. **#64 scope:** decide whether offline-only is enough to leave Draft.

## D. Remaining blockers and phase-3 plan

P0 is **not** cleared: rotation is owner-only and rights are unresolved. Phase 3
should, in order: (1) rotate the key; (2) push the proven #49 `ci.yml`/`INDEX`
resolution and retarget the stack once rights clear; (3) replace or isolate the
AGPL/unknown vendored skills behind a tested callsite gate; (4) clear XHS rights
before any migration push; (5) decide LICENSE. Engineering work that does not touch
those gates can proceed in parallel.

## No false claims

- The key value is not in the repo; a fingerprint and raw provider IDs/balances are
  public on `main` and must be treated as exposed.
- Rotation was **not** performed; validity and abnormal spend are **unverified**.
- CI passing is not a licence, not a rotation, and not owner approval.
- The #49 conflict resolution is a local, tested simulation — **not** a merge.
