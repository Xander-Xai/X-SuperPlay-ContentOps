# Phase 4 — Delivery unlock: #62 merge prep, #68/#69/#64 combined acceptance, #49 dependency order, Owner decision package

Date: 2026-10-31
Scope: `Xander-Xai/X-SuperPlay-ContentOps` (public), default branch `main`
Baseline re-read at start: `main` = `1b2611d` (phase-3 report merged as #70); 10 open
Draft PRs (the previous nine plus **#71**, which appeared during this round from
other activity and is out of scope here); 14 open Issues; LICENSE = **NONE**;
visibility = **PUBLIC**.

Status legend: **EXECUTED** (a change or command ran here), **VERIFIED** (an
independent check reproduced the claim), **SIMULATED** (a local, unpushed
rehearsal), **BLOCKED** (requires an action that is not an agent's to take).

Nothing in this round was merged, pushed to a protected branch, or executed
against a provider. No key was revoked or rotated. No paid generation, network
request, or publish action occurred.

---

## 1. Work 1 — PR #62 final merge preparation

### 1.1 Live state

| Field | Value |
|---|---|
| Head | `e49f8c4` — `test(security): reject a token used as a URL username (#61)` |
| Base | `main` (`1b2611d`) |
| State | Draft, **MERGEABLE**, **BEHIND** |
| Commits ahead of `main` | 4 (`78c86ec`, `14aea6d`, `05bb447`, `e49f8c4`) |
| Exact-head CI | run `41190079828` — Repo policy + Tests (ubuntu) + Tests (windows) all **pass** |

### 1.2 Independent security verdict

**APPROVE (security) / merge BLOCKED (Owner HOLD + branch behind).**

| Check | Result | Evidence |
|---|---|---|
| Test suite at `e49f8c4` | **26 passed** | `python tests/test_receipt_secrets.py` |
| Committed-tree guard, trusted base | **PASS — 71 baselined paths, 0 new** | `check_receipt_secrets.py --base origin/main` |
| Probe: change a baselined value | **FAIL, exit 1** (`changed_value`) | value at `EXISTING_VOICE_STATUS.voice_id` changed |
| Probe: change value **and** rewrite the baseline to bless it | **FAIL, exit 1** (`changed_value`) | base comparison still authoritative |
| Probe: delete the baseline | **FAIL, exit 1** (`new_path` on every sensitive field) | absence cannot mean allow |
| Suppression of the value in output | confirmed | guard prints paths/reasons, never values |

The guard is diff-relative, not allow-list-relative: a baselined path is accepted
only when its value is byte-identical to the trusted base. Blessing a changed
value in the baseline does not help, which is the property that makes it safe to
keep the baseline in a public repository. It covers raw provider ids, task/trace
ids, balances, key-like strings, URL userinfo (password **or** token),
credential-bearing query parameters, non-UTF-8 files, and Windows path
normalization. The phase-3 token-as-username bypass is closed and the e-mail
false-positive case is covered by a test.

### 1.3 What the Owner needs to merge

1. Clear the HOLD on #62 (this is a decision, not a CI result).
2. Update the branch onto `1b2611d`. #62 is `BEHIND`, and branch protection
   requires the strict checks to run on the resulting HEAD, so the current green
   run is necessary but not sufficient for merge.
3. Wait for the fresh exact-HEAD run of the three required checks.
4. Squash merge, then confirm the post-merge `main` run is green and re-run
   `python scripts/check_receipt_secrets.py --base origin/main` → must remain
   `0 new`.

CI passing does not lift the HOLD, and this report does not lift it either.

---

## 2. Work 2 — Combined acceptance of #68 / #69 / #64

### 2.1 Bases, heads, dependencies

| PR | Head | Base | Relation |
|---|---|---|---|
| #68 | `63a0fef` | `main` | independent |
| #69 | `d4c965b` | `feat/6-m5-production-e2e` | child of #68 |
| #64 | `95c0023` | `main` | independent |

Combined build: branch `phase4/combined` at `5601897` (merge of #64 into #68+#69)
in an isolated worktree. Merges cleanly; no conflict markers.

### 2.2 Suites, run the way CI runs them

| Suite | Result |
|---|---|
| `tests/test_m5_evidence.py` | **18/18 pass** |
| `tests/test_m5_media_use_workflow.py` | **8/8 pass** |
| `tests/test_media_use_adapter.py` | **53/53 pass** |

Note: `tests/test_media_use_adapter.py` registers cases with a module-level
`def test(fn)` decorator, which `pytest` tries to collect and reports as
`fixture 'fn' not found`. CI executes `python tests/<file>.py`, so CI is not
affected, but `pytest tests/` fails collection. This is a real, low-severity
defect: rename the decorator (e.g. `def register(fn)`). It is not a blocker for
the production chain.

### 2.3 Real offline end-to-end run (not component tests)

Source project: the repository's own `projects/m5-easel-pin` (4 `CREATED_BY_OWNER`
source refs), copied to a scratch directory so tracked receipts stay untouched.
Command: `python scripts/m5_production.py <copy> --json`.

| Stage | Receipt evidence |
|---|---|
| sources | `source-artifacts.json` — 4 artifacts, all `CREATED_BY_OWNER`, `evidence_capable: true`, each with SHA-256 |
| claims | `claim-verification.json` — `ok: true`, 4 claims bind to verbatim quotes in the cited artifacts |
| script | `script-check.json` — 7 lines; 4 claims cited; 0 unused; 0 unknown |
| narration | `narration.json` — `windows_sapi`, `network: false`, `cost: 0`, 45.142 s, 7 timed lines |
| subtitles | `subtitles.json` — 7 cues, coverage 0.963, audio duration 45.142 s |
| assets | `asset-manifest.json` — `ok: true`, 3 assets verified against recorded hashes |
| storyboard | reached (shot plan produced from the manifest) |
| compose | `compose.json` — **`status: BLOCKED`, "Easel runtime not usable: no Easel runtime found"** |
| QC / review | not reached in this run; the chain stopped at compose, as designed |

The run exits non-zero with `state: BLOCKED`. `production_ready` stays `false`
and review stays `PENDING_FOUNDER_REVIEW` when compose succeeds. A missing Easel
runtime produces a refusal, not a silently empty video — this is the fail-closed
behaviour the chain is supposed to have, and it is the correct outcome on a
machine without the pinned runtime.

### 2.4 media-use fail-closed probes (enabled, local-only)

| Probe | Result |
|---|---|
| enabled, no trusted runtime lock | **BLOCKED** — `DEPENDENCY_UNVERIFIED: media-use runtime is not trusted: no runtime lock is configured` |
| `allow_network: true` | **BLOCKED** — network/paid/cross-project reuse cannot enter the stage |
| missing `rights_reviewed: true` | **BLOCKED** — intent, explicit license and `rights_reviewed=true` required |

The positive path (resolve → import → hash-verify → feed assets) is covered by
`successful_stage_resolves_imports_verifies_and_feeds_assets` and
`build_automatically_uses_the_stage_without_a_manual_adapter_cli`, using a fake
runtime CLI under a trusted lock. It was **not** re-executed against a real
media-use runtime here because no trusted machine lock exists on this host and
installing one is a network step.

### 2.5 Credibility of `rights_reviewed`

`rights_reviewed` is a **self-declared boolean**, and `license` is an unvalidated
string. The stage enforces that a reviewer made the declaration and that it is
present before any adapter call; it cannot verify that the declared licence is the
asset's actual licence. This is a structural gate, not rights clearance. Any real
asset imported through it still needs an Owner/legal rights decision — the same
boundary recorded for GZH in phase 3.

### 2.6 Can the stack enter `main`, and in what order?

- **#68 can enter `main` independently.** The adapter import is lazy and only
  reached when `media_use` is enabled. With `media_use` disabled, the chain is
  sources → claims → script → narration → subtitles → storyboard → compose → QC →
  review and does not touch the adapter. #68 is technically independent of #64
  and #69.
- **#69 must wait for #64 for its feature to function.** #69's code merges
  without #64, but every enabled `media_use` request would then block with
  “adapter is not installed”. Shipping #69 first ships a dead, permanently
  fail-closed gate.
- **Order:** #68 → #64 → #69. Re-run exact-HEAD CI on each after the previous
  merge, because each child is currently `BEHIND` its base.
- #68's latest push run `41189776728` is `cancelled` (superseded), not a failure;
  its pull-request run `41188929682` at the same HEAD is green. A merge requires a
  fresh, non-cancelled exact-HEAD run.

### 2.7 Observed but out of scope

**#71** (`feat/57-media-use-m5-integration`, Draft, `BEHIND`) appeared during this
round from other activity. It merges #68 + #69 + the #64 adapter and adds BGM/SFX
automation. It was not reviewed here, is not authorized, and would supersede the
individual stack if merged. Do not merge it as part of this plan without a
separate review.

---

## 3. Work 3 — PR #49 stack: conflict and dependency order

### 3.1 Refreshed simulation

Re-merged `origin/main` (`1b2611d`) into the previously resolved stack branch in
an isolated worktree. Result: merge commit **`d9cf0e6`** (local only, **not
pushed**).

| Check | Result |
|---|---|
| Conflicts | `ci.yml` (union) and `docs/INDEX.zh-CN.md` (keep both audit lines); no others |
| `ci.yml` jobs | `Tests` and `Repo policy checks` intact |
| `ci.yml` triggers | feature branches + `workflow_dispatch` + `PYTHONUTF8` + receipt-secret step present |
| Suites wired | `run_tests.py --missing-from ci.yml` → **73 suites, none missing** |
| Conflict markers | none |
| GZH gate step | **ABSENT** on #49 — it exists only on #58 |

### 3.2 Dependency order (executable)

1. **#58 first, or folded into #49.** #49 vendors the GZH skill tree but does not
   carry `scripts/check_gzh_skill_rights.py` or `config/gzh-skill-rights.json`.
   Merging #49 without that gate ships the vendored tree ungated.
2. Merge the children into their base `feat/content-router` in this order:
   **#50 → #58 → #59**, each after its own exact-HEAD CI (they are Draft and green
   today).
3. Update `feat/content-router` onto current `main`, resolving `ci.yml` as a union
   (main's triggers/concurrency/`workflow_dispatch` **and** the router's steps
   **and** main's receipt-secret step **and** #58's GZH gate step) and keeping
   both `INDEX.zh-CN.md` lines.
4. Merge #49 → `main` only after P0 (rotation + rights) is cleared and the
   combined CI is green on the exact HEAD.
5. Retarget any remaining children to `main` only after #49 lands.

Children are untouched: #50 `01ac69c`, #58 `3049f1f`, #59 `7f8f105`. No branch was
rewritten or force-pushed; nothing was lost.

`PR49_SECURITY_GATE_CLEARED = NO` — #49 stays blocking while P0 is open.

---

## 4. Work 4 — Owner decision package (6 items, item-by-item approval)

Each item is a decision only the Owner can make. Recommended option first. No
item is executed by an agent.

### Decision 1 — Rotate the exposed PAYG key (P0, highest priority)

| | |
|---|---|
| Evidence | A 12-hex `payg_key_fingerprint` is public on `main`; the key **value** is not in the tracked tree. Raw voice/task/trace ids and balances are public and must be treated as exposed. Introduced by public commits 2026-10-06 → 10-12. |
| Recommended | Revoke at the provider, issue a new key, store only in the host environment/secret store, confirm the old key is rejected, review the exposure window's spend. |
| Impact if approved | P0 credential exposure closes; #49's security gate can clear. |
| Owner actions | (1) revoke; (2) issue; (3) store out-of-repo; (4) provider test call rejects old key; (5) billing review; (6) set `ROTATED` in `reports/audits/credential-rotation-status.md` on #58 — never write the key or fingerprint. |
| Acceptance condition | Provider rejects the old key **and** the Owner records rotation status; repo-side `check_receipt_secrets.py --base origin/main` still reports `0 new`. |
| Consequence of inaction | The credential stays usable by anyone who saw it; P0 remains open and #49 cannot clear. |

**A repo-scan PASS is not rotation.** Only the provider-side revocation and the
Owner's recorded confirmation count.

### Decision 2 — GZH component rights (10 non-clear components)

| | |
|---|---|
| Evidence | 2 RESTRICTED (`deep-research` CC BY-NC 4.0, dispatch blocked; `gzh-design-skill` AGPL-3.0, `allowed_agpl`, required gate), 3 OWNER_ATTESTED (distribution hold), 5 RIGHTS_UNKNOWN (dispatch blocked). Enforcement (route + callsite + repackaging) is EXECUTED on #58. |
| Recommended | Keep `gzh-design-skill` isolated and comply with AGPL (separate directory, not linked; do not remove the gate); replace `deep-research` with a permissive skill; obtain file-level provenance or legal sign-off for the 3 attested; replace or obtain permission for the 5 unknown. |
| Impact if approved | GZH can distribute; otherwise it stays internal-only. |
| Owner actions | Choose: accept AGPL + comply, or fund replacements; supply evidence for attested; decide replace/permit for unknown. Mark contested items `LEGAL_REVIEW_REQUIRED`. |
| Acceptance condition | Every component has a class backed by licence text **and** use behaviour; `GZH_RIGHTS_CLEARED = YES`. |
| Consequence of inaction | GZH stays PARTIAL; no public GZH distribution; #49 ships the tree gate-only. |

### Decision 3 — XHS rights

| | |
|---|---|
| Evidence | xhs-FA migration is local-only; there is no remote XHS branch to audit. ~30 skills have unknown rights. Nothing is pushed. |
| Recommended | Keep local-only and unpushed until the ~30 skills are cleared; then run #51's clean-clone acceptance and remote-retirement gate. |
| Impact if approved | XHS can move toward a public push. |
| Owner actions | Provide rights evidence or replacement for the ~30 skills; approve #51 acceptance. |
| Acceptance condition | `XHS_RIGHTS_CLEARED = YES` on evidence, not on a green CI. |
| Consequence of inaction | XHS remains local-only; no push. |

### Decision 4 — Repository LICENSE

| | |
|---|---|
| Evidence | `LICENSE` = **NONE** on a public repository; the root licence would not cover third-party components in any case. |
| Recommended | Adopt a permissive licence (Apache-2.0 or MIT) for first-party code, plus a third-party notices file that does not relicense vendored components. |
| Impact if approved | Public reuse terms become explicit; reduces ambiguity for contributors and for GZH/AGPL interaction. |
| Owner actions | Pick the licence; add `LICENSE`; add `THIRD-PARTY-NOTICES`; confirm it does not relicense AGPL/CC BY-NC components. |
| Acceptance condition | `LICENSE` present and a notices file enumerating restricted components. |
| Consequence of inaction | Public repo has no granted rights; downstream use is ambiguous. |

### Decision 5 — PR #62 HOLD

| | |
|---|---|
| Evidence | Security verdict **APPROVE**; 26 tests pass; 71 baselined / 0 new; three adversarial probes fail closed; exact-HEAD CI 3/3. Branch is `BEHIND`. |
| Recommended | Lift the HOLD, update onto `1b2611d`, wait for fresh exact-HEAD CI, squash merge. |
| Impact if approved | The receipt-secrets guard lands on `main`; future receipts are policed. |
| Owner actions | Comment that the HOLD is cleared; update branch; merge after green. |
| Acceptance condition | Post-merge `main` CI green and `check_receipt_secrets.py --base origin/main` → `0 new`. |
| Consequence of inaction | #62 stays Draft; `main` keeps no enforcement against new receipt secrets. |

### Decision 6 — PR #64 scope (offline-only vs production)

| | |
|---|---|
| Evidence | Fail-closed tests PASS (53); trusted-runtime offline execution is Owner-recorded evidence, not re-executed here; production provider execution and publish are **not authorized**. |
| Recommended | Accept **offline-only** as the merge scope now; keep network/paid/publish out of the adapter and out of #64's definition of done. |
| Impact if approved | #64 can leave Draft as an offline adapter; production remains a separate, later decision. |
| Owner actions | State that offline-only is sufficient for merge; explicitly exclude network/paid/publish. |
| Acceptance condition | Merged adapter still refuses without a trusted lock and still refuses network/paid flags; `PR64_PRODUCTION_AUTHORIZED = NO` remains true. |
| Consequence of inaction | #64 stays Draft; #69 cannot function; the M5 media-use path stays disabled. |

### Priority

**Decision 1 (PAYG rotation) is the single action that unlocks P0.** Decisions 2–4
are rights/licence decisions that gate distribution. Decisions 5–6 are merge
decisions that are safe to take now and unblock the engineering stack.

---

## 5. Final status matrix

| PR | Technical state | Status | Minimal next action |
|---|---|---|---|
| **#62** | Security APPROVE; 26 tests; CI 3/3; `BEHIND` | **READY_FOR_OWNER / MERGE BLOCKED** | Owner clears HOLD → update branch → merge on green |
| **#64** | Offline VERIFIED; 53 tests; production not authorized | **READY_FOR_OWNER / MERGE BLOCKED** | Owner accepts offline-only scope |
| **#68** | Independent; 18 tests; E2E verified; CI green (latest push run cancelled) | **READY_FOR_OWNER / MERGE BLOCKED** | Owner review; re-run exact-HEAD CI; merge |
| **#69** | 8 tests; depends on #68 base and #64 for function | **BLOCKED (dependency)** | After #68 + #64 land, retarget and merge |
| **#49** | Conflict SIMULATED (`d9cf0e6`); 73 suites wired; GZH gate absent; P0 open | **BLOCKED (P0 + gate)** | Land #58 gate with #49; clear P0 first |

### Executed / verified / simulated / blocked

```text
PR62_SECURITY_VERDICT        = APPROVE            (VERIFIED)
PR62_TESTS                   = 26 passed          (EXECUTED)
PR62_ADVERSARIAL_PROBES      = 3/3 fail closed    (VERIFIED)
PR62_OWNER_HOLD              = ACTIVE             (BLOCKED: owner)
PR62_MERGEABLE               = NO (BEHIND)        (VERIFIED)

M5_COMBINED_BUILD            = 5601897            (EXECUTED)
M5_SUITES                    = 18 + 8 + 53 pass   (EXECUTED)
M5_REAL_OFFLINE_E2E          = stages to compose  (VERIFIED)
M5_COMPOSE                   = BLOCKED fail-closed (VERIFIED)
M5_MEDIA_USE_FAIL_CLOSED     = 3/3 correct         (VERIFIED)
M5_MEDIA_USE_POSITIVE_RUNTIME= SUITE-LEVEL ONLY    (NOT real runtime)
M5_RIGHTS_REVIEWED_CREDIBLE  = STRUCTURAL ONLY     (LIMITATION)

PR68_INDEPENDENT_OF_64_69    = YES                (VERIFIED)
PR69_NEEDS_64_FOR_FUNCTION   = YES                (VERIFIED)
PR71                         = OUT OF SCOPE        (NOT REVIEWED)

PR49_CONFLICT_PLAN           = d9cf0e6             (SIMULATED, not pushed)
PR49_GZH_GATE_PRESENT        = NO                 (VERIFIED)
PR49_SECURITY_GATE_CLEARED   = NO                 (BLOCKED)

P0_CREDENTIAL_ROTATED        = NO                 (BLOCKED: owner)
OWNER_DECISIONS_PENDING      = 6                  (BLOCKED: owner)
```

---

## 6. No false claims

- #62 was not merged, promoted, or un-held. A green CI is not an Owner approval.
- #68, #69, #64, #49 were not merged; they remain Draft.
- The M5 real E2E stopped at compose because no Easel runtime exists on this
  host. That is a correct refusal, not a successful compose.
- The media-use positive path was exercised at suite level with a fake runtime,
  not against a real trusted runtime.
- `rights_reviewed` is self-declared and licenses are not validated; the gate is
  structural, not rights clearance.
- The #49 resolution is a local simulation at `d9cf0e6`, not a push and not a merge.
- The PAYG key was not rotated; a repo scan is not provider-side rotation.
- #71 was observed but not reviewed and is not authorized.
