# Phase 5 — Integration convergence, independent security acceptance and delivery unlock

Date: 2026-10-31
Repository: `Xander-Xai/X-SuperPlay-ContentOps` (public), default branch `main`
Baseline re-read at start: `main` = `3c559fb` (phase-4 report merged as #72).
Open Draft PRs reviewed: #62, #64, #68, #69, #71 (plus the router stack
#49/#50/#58/#59, unchanged this round).

Status legend: **EXECUTED** (a change or command ran here), **VERIFIED** (an
independent check reproduced it), **SIMULATED** (local rehearsal, not pushed),
**BLOCKED** (needs an action that is not an agent's to take).

No Draft PR was merged, closed or deleted. No provider call, paid generation,
credential action or publication occurred. The Owner HOLD on #62 remains active.

---

## 1. #71 versus #64 / #68 / #69 — overlap matrix

### 1.1 Commit and ancestry facts

| Fact | Value |
|---|---|
| #71 head | `4dbad69` (28 commits from `main`: 24 non-merge + 4 integration merges) |
| #64 head | `95c0023` — **ancestor of #71** |
| #68 head | `63a0fef` — **ancestor of #71** |
| #69 head | `d4c965b` — **ancestor of #71** |
| #71 integration merges | `f118284` (#64), `5f7c67f` (#68), `16338cf` (#69) |
| #71-only commits | `ce037b4` (BGM/SFX automation), `282fde8` (tests/docs), `4dbad69` (docs) |
| #71 files vs `main` | 87 files, +11111/−577 |

#71 contains the full history and tree of all three upstream PRs. There is no
lost commit and no rewritten upstream branch.

### 1.2 File ownership

| PR | Files | Insertions | Scope |
|---|---:|---:|---|
| #64 | 28 | +7324 | pinned media-use adapter (`src/contentops/media/`), runtime script/locks, adapter tests |
| #68 | 41 | +2140 | SourceArtifact, ClaimLedger, M5 production chain, evidence tests |
| #69 | 5 | +450 | automatic media-use stage in `m5_production.py`, workflow tests, RUNBOOK, CI |
| #71-only | 30 | +1244 | BGM/SFX stage, example project `projects/m5-media-use/`, ADR/current-state/runbook docs, 7 new audio tests |

### 1.3 Duplicate implementations

- `scripts/media_use_adapter.py` is **not** a duplicate of
  `src/contentops/media/media_use_adapter.py`. The first is a thin operator CLI;
  the header states all policy lives in the `src` module.
- No second asset registry exists. The example project's committed receipts are
  outputs of a real run, not a parallel catalogue.
- The only overlap is intentional: #71 re-contains the three upstream PRs by
  merge ancestry, so a route that merges them separately must not then merge
  #71 wholesale (that would replay already-merged commits).

### 1.4 Missing on `main`

Everything in #64/#68/#69/#71 is absent from `main`: the media-use adapter,
the evidence-first chain, automatic media-use sourcing and the BGM/SFX stage.

---

## 2. Two delivery routes compared

### Route A — merge #68, then #64, then #69, then the audio increment

**Simulation (EXECUTED):** from `main` `3c559fb`, merged `63a0fef` → `95c0023`
→ `d4c965b`. **All three merges clean, zero conflicts, zero conflict markers.**
Suites: 18/8/53 pass.

The audio increment (`ce037b4`, `282fde8`, `4dbad69`) was then cherry-picked onto
that result: **all three apply cleanly**. The resulting tree differs from #71
only in `docs/INDEX.md` / `docs/INDEX.zh-CN.md` (because #71 predates the
phase-3/4 report links). Suites: **18/15/53 pass — identical to #71**.

| Property | Assessment |
|---|---|
| Maintainability | One feature per PR; the audio increment is separately reviewable |
| Risk | Lowest per merge; #68 is independent and can land first |
| Testability | Each PR carries its own suite; #71's 7 audio tests move intact |
| Dependencies | #68 → #64 → #69 → audio |
| Merge cost | 4 merges, each small |
| Rollback | Reverting the audio increment leaves the chain and adapter intact |

### Route B — merge #71 as one integrated delivery

| Property | Assessment |
|---|---|
| Maintainability | 87 files, 28 commits, four features and a docs/example bundle in one review |
| Risk | Highest single-review surface; a problem in any layer blocks all |
| Testability | 18/15/53 pass, but the review must separate four concerns |
| Dependencies | None after merge, but it must be rebased onto `3c559fb` |
| Merge cost | 1 merge, large |
| Rollback | Reverting #71 rolls back the chain, adapter, media-use and audio together |

### Recommendation: **Route A**

Route A wins on rollback granularity, review surface and dependency safety, and
the simulation proves it loses nothing: the audio increment cherry-picks cleanly
and reproduces #71's test results. Route B is only preferable if the Owner wants
a single review checkpoint; it costs rollback separation and makes the licence
correction below harder to see.

**#71 should be treated as superseded by Route A, not merged.** Closing it is an
Owner action; this report does not close it.

One finding from #71 must be preserved in Route A's audio increment:
`scripts/media_use_adapter.py` tagged the bundled SFX as **Apache-2.0**, which is
the skill *code* licence. The skill's own `audio/assets/sfx/CREDITS.md` states
they are **Pixabay Content License**. #71 corrects the constant; the audio
increment must carry that correction.

---

## 3. M5 combined E2E re-verification

### 3.1 Result classes (kept separate)

| Dimension | Result |
|---|---|
| Unit suites | **PASS** — 18 evidence, 15 media-use workflow, 53 adapter, 20 rights-gate workflow, 97 media convergence, 85 image |
| CI fixtures | **PASS** — fake runtime/fake narration; no provider request |
| Real runtime — media-use | **BLOCKED** — no trusted host runtime lock; refusal is `DEPENDENCY_UNVERIFIED` |
| Real runtime — Easel compose | **BLOCKED** — no Easel runtime in the isolated worktree; refusal is "Easel runtime not usable" |
| Video/audio artefacts | **NOT RE-EXECUTED here** — the committed `projects/m5-media-use/` receipts are the author's real run (compose OK, QC WARN, review PENDING); treated as recorded evidence, not as this round's execution |
| Publish authorization | **NOT AUTHORIZED** |

### 3.2 Chain results, executed here

Isolated copy of `projects/m5-easel-pin` (no media-use), rebound #71 on `3c559fb`:

| Stage | Receipt evidence |
|---|---|
| sources | 4 artifacts, all `CREATED_BY_OWNER`, `evidence_capable: true`, SHA-256 recorded |
| claims | 4 claims, all bound to verbatim quotes, `ok: true` |
| script | 7 lines, 4 claims cited, 0 unused, 0 unknown |
| narration | Windows SAPI, `network: false`, `cost: 0`, 45.142 s |
| subtitles | 7 cues, coverage 0.963 |
| assets | 3 assets verified against recorded hashes |
| compose | **BLOCKED** — "Easel runtime not usable: no Easel runtime found" |
| review | not reached; `production_ready` stays false by construction |

Isolated copy of `projects/m5-media-use` (media-use enabled):

1. The new rights gate accepts all three example requests (valid review records).
2. The chain then refuses at runtime: `DEPENDENCY_UNVERIFIED: media-use runtime
   is not trusted: no runtime lock is configured`.
3. Exit code 4, no provider call, no partial success.

This is the required fail-closed behaviour. A simulated success is **not**
substituted for the missing runtime.

### 3.3 Checks the task asked for

| Check | Evidence |
|---|---|
| Claim ↔ quote consistency | 4/4 claims verified; unsupported claim refuses first |
| Asset SHA-256 integrity | asset manifest verifies each hash; tampered fixture blocks |
| Licensed external is not evidence | `evidence_capable: false` on every imported visual and on audio |
| BGM/SFX timeline accuracy | fixture tests: SFX `at` within narration, duplicate refused, volume bounds enforced |
| Volume/mix/narration integrity | volume bounds and narration duration drive storyboard; no silent narration accepted |
| Receipt consistency after failure | blocked runs write only completed-stage receipts, never a success marker |
| No machine paths | `committed_example_receipts_carry_no_machine_paths` passes; imported paths are `project://` |
| Missing Easel runtime refuses | verified above |
| Human review not approved ⇒ not production-ready | `production_ready: false`, `PENDING_FOUNDER_REVIEW` |
| No network/paid/publish | mode local-only; network/paid/cross-project flags refused |

### 3.4 pytest collection fix

`tests/test_media_use_adapter.py` registered cases with a module-level
`def test(fn)`, which pytest collected as a test (`fixture 'fn' not found`).
Renamed to `register` and made `SkipTest` subclass `unittest.SkipTest`.
Both entries now pass: `python tests/test_media_use_adapter.py` → 53, and
`python -m pytest tests/test_media_use_adapter.py` → 53 passed. The script entry
is unchanged, so CI is unaffected.

---

## 4. Third-party rights gate (implemented)

`src/contentops/media/rights_gate.py` is a policy gate, not a second asset
registry and not a licence verifier. Every media request must now carry:

```yaml
rights:
  license_id: Pixabay-Content-License
  source_url: "https://pixabay.com/sound-effects/"
  reviewed_by: <reviewer>
  reviewed_at: "2026-10-31"
  review_evidence: assets/click_accent.rights.json
  attribution: "..."
  synthetic: false
```

plus a matching review sidecar (`contentops.media-rights-review/v1`). The gate
checks and fails closed on:

| Rule | Result |
|---|---|
| A bare `rights_reviewed: true` | **refused** — self-declaration is not evidence |
| Software licence used for media (`Apache-2.0`, `MIT`, `AGPL-3.0`, …) | **refused** |
| Non-commercial licence (`CC-BY-NC*`) | **refused** |
| Unknown licence | **refused** |
| Missing / unreadable / schema-mismatched sidecar | **refused** |
| Request fields disagreeing with the sidecar | **refused** |
| Third-party asset without `http(s)` source | **refused** |
| Attribution-required licence with empty attribution | **refused** |
| Future review date | **refused** |
| Synthetic material | imported but `evidence_capable: false`, flagged `synthetic` |
| Receipt | records licence, source, reviewer, date, evidence path and its SHA-256 |

**Pixabay:** the bundled media-use SFX are Pixabay Content License (per the
skill's `audio/assets/sfx/CREDITS.md`), **not** the Apache-2.0 licence of the
skill code. Free commercial use, no attribution required but appreciated, no
standalone redistribution. #71's correction is preserved in the recommended
audio increment.

**Limitation, stated plainly:** the gate proves the record is complete,
internally consistent and policy-compliant. It cannot prove the declared licence
is the asset's actual licence. That remains a human/legal decision, and the gate
is described that way in code and docs.

Delivered as stacked PR **#73** on `feat/57-media-use-m5-integration` (CI green,
not merged). 20 workflow tests pass, including five new gate tests.

---

## 5. PR #62 final review

| Field | Value |
|---|---|
| Head | `276ce42` (merge of `main` `3c559fb` into the branch) |
| State | Draft, **MERGEABLE / CLEAN**, no longer behind |
| Exact-HEAD CI | runs `41195736962` and `41195738684` — Repo policy + Tests (ubuntu) + Tests (windows) all **pass** |
| Tests | 26 passed |
| Guard | `check_receipt_secrets.py --base origin/main` → 71 baselined, **0 new** |
| Adversarial probes (phase 4, still valid) | changed value, bless-baseline, delete-baseline → all exit 1 |

**Independent verdict: APPROVE (security).** The HOLD is **ACTIVE** and was not
lifted; the branch update is a merge, not a force-push and not a promotion.

Minimum Owner decision to lift the HOLD: state that #62 may merge. Then squash
merge and re-run the guard on the post-merge `main` (must stay `0 new`).

---

## 6. P0 credentials, GZH and XHS (incremental status)

| Item | Status | Evidence |
|---|---|---|
| PAYG rotation | **NOT_ROTATED** | `credential-rotation-status.md` on #58; Owner action required |
| Repo-side guard | PASS — 71 baselined, 0 new | `check_receipt_secrets.py` |
| Repo scan = rotation? | **No** | scan prevents new exposure; it cannot revoke a provider key |
| #56 | OPEN, P0 | unchanged |
| GZH gate | EXECUTED on #58 (`3049f1f`), not on `main` | callsite + repackaging checks, 12 tests |
| GZH rights | **PARTIAL** — 2 restricted, 3 attested, 5 unknown | decisions 2 in the phase-4 package |
| XHS | **NOT CLEARED**, nothing pushed | no remote XHS branch exists |
| #49 | **CONFLICTING / DIRTY**, Draft | blocked by P0 and the missing GZH gate |

No new licence matrix was produced; the phase-3 matrix and #58 config remain the
source of truth.

---

## 7. Delivered references

| Item | Ref | Kind |
|---|---|---|
| Rights gate + pytest fix (stacked on #71) | PR **#73**, head `2c5bedc`, CI run `41195483154` | EXECUTED |
| #62 rebased onto `main` without lifting HOLD | `fix/61-receipt-baseline` `276ce42`, CI `41195736962` | EXECUTED |
| Route A merge simulation | local `phase5/route-a` | SIMULATED |
| Route A + audio increment | local `phase5/route-a-audio` | SIMULATED |
| #71 rebased on `main` | local `phase5/m71-main` | SIMULATED |
| Real offline chain | receipts under `.verify-tmp/phase5/` | EXECUTED |
| Phase-5 report | this file, PR #74 | EXECUTED |

No PR merged this round; no Issue closed; no branch deleted.

---

## 8. Final status

```text
PR71_CONTAINS_UPSTREAM_3      = YES (ancestry verified)   VERIFIED
ROUTE_A_MERGES_CLEAN          = YES (3/3, no conflicts)   SIMULATED
ROUTE_A_AUDIO_EXTRACTION      = CLEAN (tree == #71)       SIMULATED
RECOMMENDED_ROUTE             = A (separate + audio)      VERIFIED

M5_UNIT_SUITES                = 18/15/53/20/97/85 pass    EXECUTED
M5_CI_FIXTURES                = PASS (offline fakes)      EXECUTED
M5_REAL_MEDIA_USE_RUNTIME     = BLOCKED (no host lock)    BLOCKED
M5_REAL_EASEL_COMPOSE         = BLOCKED (no runtime)      BLOCKED
M5_PRODUCTION_READY           = NO                        VERIFIED
M5_PUBLISH_AUTHORIZED         = NO                        BLOCKED

RIGHTS_GATE                   = EXECUTED (PR #73)          VERIFIED
BARE_RIGHTS_REVIEWED          = REFUSED                   VERIFIED
SOFTWARE_LICENCE_AS_MEDIA     = REFUSED                   VERIFIED
PIXABAY_SFX_LICENCE           = CORRECTED (Pixabay)       VERIFIED

PR62_SECURITY_VERDICT         = APPROVE                   VERIFIED
PR62_STATE                    = CLEAN, 3/3 exact HEAD     VERIFIED
PR62_OWNER_HOLD               = ACTIVE                    BLOCKED

P0_CREDENTIAL_ROTATED         = NO                        BLOCKED
GZH_RIGHTS_CLEARED            = PARTIAL                   BLOCKED
XHS_RIGHTS_CLEARED            = NO                        BLOCKED
PR49_MERGEABLE                = NO (CONFLICTING)          BLOCKED
```

---

## 9. Next minimal Owner decisions

1. **Rotate the PAYG key at the provider** (unchanged P0; unlocks #49).
2. **Approve Route A** and authorize merging #68 → #64 → #69, then the audio
   increment. Decide whether to close #71 as superseded.
3. **Merge PR #73** (rights gate + pytest fix) into #71's branch, or apply the
   same changes to the Route A audio increment.
4. **Lift the #62 HOLD** and merge the now-clean branch.
5. **Decide GZH/XHS rights** per the phase-4 package; #49 stays blocked until
   then.

---

## 10. No false claims

- No real media-use runtime or Easel runtime executed here; both stages are
  reported BLOCKED, not simulated-success.
- The committed example video receipts are recorded evidence from the #71
  author's machine, not a re-execution this round.
- The rights gate is a completeness/consistency policy check, not a licence
  verification and not legal advice.
- Route A and the audio extraction are local simulations, not pushes or merges.
- #62 was updated and CI-verified, but not promoted and its HOLD was not lifted.
- The PAYG key was not rotated; a green guard is not rotation.

---

## 11. State change during this round (post-analysis snapshot)

At 2026-10-31T11:22Z, while this report was being delivered, another actor
**promoted #71 out of Draft** and advanced its head from `4dbad69` to `8f23149`.
This round did not touch #71. Recorded here so the audit stays accurate:

| Fact | Value |
|---|---|
| #71 state | **Ready for review** (no longer Draft), `CONFLICTING / DIRTY` |
| New head | `8f23149` — "merge: bring current main into the media-use integration (#71)" |
| Added commits | `0ac3346` receipt sanitization + audit gaps, `3fb9983` worktree-path redaction, `f49e5f7` Windows `dev_check` readability, `a819f3c` final audited SHA, plus a PR-71 audit report |
| Conflict with `main` `07ea5c1` | only `docs/INDEX.md` and `docs/INDEX.zh-CN.md` |

The overlap matrix and both route simulations above were computed at `4dbad69`;
their conclusions hold. If the Owner keeps Route A, the new audit fixes
(`0ac3346`, `3fb9983`, `f49e5f7`, `a819f3c`) must be carried into the audio
increment. If the Owner prefers a single delivery, #71 at `8f23149` is now the
closer candidate; its only merge conflict is the two index files. In both cases
the Owner decision and merge remain unauthorized actions for this agent.
