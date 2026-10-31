# ContentOps phase-3 — P0 convergence and stack unlock (2026-10-31)

> Scope: the residual blockers confirmed in phase 2 only — PAYG exposure, GZH/XHS
> rights, PR #62, the #49 stack, and PR #64. No general re-governance.
> No secret value is reproduced; no provider, paid, publish, network or history
> action was taken; no blocked PR was merged or closed.

Status legend: **EXECUTED** (code/action done), **VERIFIED** (re-checked against
live state), **SIMULATED** (done in an isolated worktree, not pushed), **BLOCKED**
(needs owner or external authorization).

Baseline re-read at start: `main` = `dac1f7c`; 7 open Draft PRs (the six from
phase 2 plus a new **#68** M5 chain, base `main`, head `63a0fef`, out of this
round's scope); 14 open Issues. #68's receipts were spot-checked and contain **no**
raw provider ids, fingerprints or balances, so it adds no exposure.

## 1. PAYG event status and owner actions

| Field | Value | Status |
|---|---|---|
| Credential class | PAYG provider key | VERIFIED |
| Key value inside repo | Not present (full tracked-tree scan) | VERIFIED |
| Public on `main` | 12-hex `payg_key_fingerprint` (1 file), `voice_id` (9 files), `task_id`/`trace_id` (2 files), balances (10 files) | VERIFIED |
| Rotation | `NOT_ROTATED` | BLOCKED (owner) |
| Validity / abnormal spend | Not tested (no provider request made) | BLOCKED (owner) |
| History | Introduced by public commits 2026-10-06 → 10-12 | VERIFIED |

**Owner rotation checklist (minimal, provider side).** Nothing here is executed by
an agent; each step is a human action at the provider console.

1. Revoke the exposed PAYG key.
2. Issue a new key; store it only in the host environment or a secret store.
3. Confirm the old key is rejected by the provider (their own test call).
4. Check the billing/usage view for the exposure window for unexpected spend.
5. Set `Rotation status: ROTATED`, `Rotated at`, `Method`, `Verified by` in
   `reports/audits/credential-rotation-status.md` (on #58). Never add the key or
   fingerprint.

**Post-rotation verification (repo side, no secret exposure).** After step 1–5 the
owner runs `python scripts/check_receipt_secrets.py --base origin/main`, which
must still report `0 new`; the fingerprint receipt and raw-id receipts remain
baselined by field path only. A history rewrite is a separate owner decision and
is **not** performed here.

## 2. New security engineering this round (EXECUTED)

### PR #62 — token-as-username URL bypass closed (`e49f8c4`)

Phase 2's URL rule caught `scheme://user:pass@host` and signed query params but
**not** a token used as the username (`scheme://<token>@host`, no colon). Added a
gated alternative — ≥20 characters, mixed letter+digit run — so a normal host, a
short user, or an e-mail user/query does not false-positive.

| Check | Result |
|---|---|
| `tests/test_receipt_secrets.py` | **26 passed** (was 24) |
| `check_receipt_secrets.py --base origin/main` | PASS — 71 baselined, **0 new** |
| Exact-head CI `e49f8c4` | **3/3** — run 41190079828 |

### PR #58 — GZH rights gate strengthened (`3049f1f`)

The rights gate only inspected `routing.yaml` `selected_skill:` lines. A
ContentOps-owned runner could still reach a blocked skill by path, and a
held/blocked skill could be copied into a distributable location. Added two
fail-closed checks to `scripts/check_gzh_skill_rights.py`:

- **Callsites:** scan `scripts/` and `src/` for `skills/<path>` references to any
  skill whose `dispatch` is not `allowed`/`allowed_agpl`.
- **Repackaging:** flag a byte-identical copy of a held/blocked skill's `SKILL.md`
  outside the vendored tree and outside `research/`. Identity is the exact bytes,
  so a same-named archival copy (e.g. the `research/archive/dy1024-*` tree) is not
  a false positive.

5 tests added (blocked callsite, allowed callsite, repackaged copy, research copy
ignored, committed gate passes on the real tree). **12 tests pass; real-tree gate
PASS — 50 skills, 0 blocked.** Exact-head CI: run 41190970269.

## 3. GZH / XHS rights — before/after

Nothing was re-classified this round (that needs owner/legal evidence); the change
is that the *enforcement* now covers callsites and repackaging, not only routes.
Full matrix remains `reports/audits/gzh-skill-license-matrix.md` on #58; config is
`config/gzh-skill-rights.json`.

| Class | Count | Enforcement before | Enforcement after |
|---|---:|---|---|
| OWNED_AND_CLEARED | 22 + 9 archived | route check | route + callsite + repackaging |
| THIRD_PARTY_LICENSE_VERIFIED | 9 | route check | same |
| RESTRICTED | 2 | route check (blocked / allowed_agpl) | + callsite + repackaging |
| OWNER_ATTESTED | 3 | route check (dispatch allowed, distribution hold) | + repackaging (hold) |
| RIGHTS_UNKNOWN | 5 | route check (blocked) | + callsite + repackaging |

**The 10 non-clear components**

| Skill | Class / licence | Obligation | Callsite | Replacement / action |
|---|---|---|---|---|
| `deep-research` | RESTRICTED, CC BY-NC 4.0 | non-commercial only | dispatch **blocked**, no callsite | replace with a permissive research skill, or obtain permission |
| `gzh-design-skill` | RESTRICTED, AGPL-3.0 | source+licence on distribution; §13 if run as a network service | required HTML gate (`workflow_gate.py`, `verify_draft_submission.py`), `allowed_agpl` | keep+comply (separate dir, not linked); owner accepts AGPL or funds a permissive replacement — **do not remove the gate** |
| `content-humanizer` / `content-production` / `content-strategy` | OWNER_ATTESTED | owner notice only, no file-level provenance | internal use allowed, distribution **hold** | obtain file-level evidence or legal sign-off before public release |
| `content-repurposer` / `exa-web-search-free` / `midu-proofread` / `vision` / `wechat-viral-topic` | RIGHTS_UNKNOWN | none found | dispatch **blocked** | obtain permission or replace; route gate + callsite gate reject them |

AGPL and CC BY-NC are judged by licence text **and** use behaviour; owner risk
acceptance is recorded as a decision, not as licence compliance. Legal uncertainty
is marked `LEGAL_REVIEW_REQUIRED`, not resolved here.

**XHS:** the xhs-FA migration is local-only and not on the remote; there is no
remote XHS branch to audit. Its ~30 skills stay unknown and **nothing is pushed**
to the public repo. XHS_RIGHTS_CLEARED = NO.

## 4. PR #62 conclusion

`READY_FOR_OWNER` — the guard is diff-relative against a trusted base, stores no
values or low-entropy hashes, refuses a legacy v1 baseline, fails with a non-zero
exit, and now covers URLs with userinfo (password or token), signed query params,
plus the phase-2 adversarial cases. No new bypass for the covered shapes and no
false positive on the real receipts (71 baselined, 0 new). **The owner HOLD stays
ACTIVE; it is not merged and passing tests do not lift the hold.**

## 5. PR #64 — four separate acceptance dimensions

Kept Draft. No network, paid, cross-project or publish action.

| Dimension | Result | Basis |
|---|---|---|
| Fail-closed tests | **PASS** | 53 tests re-run at `95c0023`; no lock → `trusted:false`/`DEPENDENCY_UNVERIFIED`; selfcheck → `RUNTIME_NOT_TRUSTED` |
| Trusted-runtime real offline execution | **VERIFIED (owner evidence)** | baseline approval records the isolated Linux no-egress + Windows local acceptance; not re-executed this round because no machine lock exists here and installing is a network step |
| Production provider execution | **NOT AUTHORIZED / NOT VERIFIED** | approval text excludes network/paid |
| Publish / commercialization | **NOT AUTHORIZED** | same |

These four are not interchangeable: passing fail-closed tests does not prove a
trusted runtime executed, and neither authorises production or publication.

## 6. PR #49 stack — conflict and dependency status

- **Conflict: SIMULATED.** Refreshed the isolated resolution against the newer
  `main` (`dac1f7c`): merge commit `88a65f4` (local only, **not pushed**) on top of
  the earlier `1d43b35`. Conflicts are `ci.yml` (union: main's feature triggers +
  concurrency + `workflow_dispatch`, content-router's steps **and** main's
  receipt-secret step) and `docs/INDEX.zh-CN.md` (keep both audit lines). Verified:
  YAML valid; `Tests`/`Repo policy` jobs intact; feature triggers, `PYTHONUTF8`,
  receipt step present; **`run_tests.py --missing-from ci.yml` → 73 suites wired**;
  no conflict markers.
- **New dependency finding:** `scripts/check_gzh_skill_rights.py` and the rights
  config live only on #58, not on #49. #49 vendors the GZH tree without that gate.
  Therefore **#49 must not merge before the #58 gate lands with it** (fold #58 into
  #49, or land #58 first); otherwise the vendored tree ships ungated.
- **Children:** #50/#58/#59 remain based on `feat/content-router`; retarget only
  after #49 clears P0. No forced push, no parent rewrite.
- #49_SECURITY_GATE_CLEARED = NO (P0 rights + rotation still open).

## 7. Actual deliveries

| Item | Ref | Kind |
|---|---|---|
| Receipt guard URL bypass fix + tests | PR #62 head `e49f8c4` | EXECUTED, CI 3/3 run 41190079828 |
| GZH callsite + repackaging gate + tests | PR #58 head `3049f1f` | EXECUTED, CI run 41190970269 |
| #49 conflict resolution (refreshed) | local `88a65f4` | SIMULATED, not pushed |
| #64 offline re-check | `95c0023` | VERIFIED |
| Exposure re-audit | `main` `dac1f7c` | VERIFIED |

No PR merged, no Issue closed, no branch deleted this round.

## 8. Final acceptance

```text
P0_CREDENTIAL_ROTATED        = NO        (BLOCKED: owner)
P0_PUBLIC_EXPOSURE_AUDITED   = PASS      (VERIFIED)
GZH_RIGHTS_CLEARED           = PARTIAL   (gate EXECUTED; rights decisions owner)
GZH_CALLSITE_GATE            = EXECUTED + VERIFIED (3049f1f)
XHS_RIGHTS_CLEARED           = NO        (local-only, not pushed)
PR62_SECURITY_TESTS          = PASS      (26 tests, CI 3/3)
PR62_OWNER_HOLD              = ACTIVE
PR64_OFFLINE_VERIFIED        = PASS
PR64_PRODUCTION_AUTHORIZED   = NO
PR49_CONFLICT_PLAN_READY     = YES       (SIMULATED 88a65f4)
PR49_SECURITY_GATE_CLEARED   = NO
CI_EXACT_HEAD_VERIFIED       = YES
OWNER_DECISIONS_PENDING      = 6
```

## 9. Remaining owner gates and minimal unlock

1. **Rotate the PAYG key** (provider) → unblocks P0. Steps in §1.
2. **GZH rights:** accept AGPL for `gzh-design-skill` (or fund a replacement);
   resolve `deep-research` (CC BY-NC) and the 5 unknown / 3 attested skills.
3. **XHS rights:** clear ~30 skills before any public push (#51).
4. **LICENSE:** Apache-2.0 / MIT / proprietary (#11; root licence does not cover
   third-party components).
5. **#62:** review and clear the HOLD.
6. **#64:** decide whether offline-only is enough to leave Draft.

Phase 4 (only after 1–2): push the proven #49 `ci.yml`/`INDEX` resolution with the
#58 gate folded in, retarget the stack, then a full exact-head CI run rectified to
the resulting `main`.

## No false claims

- The key value is not in the repo; a fingerprint and raw ids/balances are public
  and must be treated as exposed. Rotation is not performed; validity is unverified.
- A passing CI is not a licence, a rotation, or owner approval.
- The #49 resolution is a local simulation, not a merge; #49 and its children stay
  Draft and blocking.
