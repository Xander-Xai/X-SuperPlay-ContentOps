# media-use × ContentOps integration acceptance — 2026-11-01

> Adversarial acceptance of the `media-use` skill integration: discovery,
> registry, runtime integrity, execution gate, rights gate, M5 end-to-end,
> regression, and a clean-environment reproduction.
>
> Scope: the code that merged as #71, #76–#81 and #84 on `main`, plus the
> remediation raised by this audit (PR #86).
>
> **This audit does not claim production release.** `production_ready` stays
> `false` and the human review stays `PENDING_FOUNDER_REVIEW`.

## A. GitHub status

| Item | Value |
|---|---|
| Remote | `https://github.com/Xander-Xai/X-SuperPlay-ContentOps.git` |
| Audit baseline (`origin/main`) | `459abb4815b163bc7c53c937c523f6190164b25c` |
| Baseline commit | `fix: read MediaUseStatus.available in the managed status wrapper (#84)` |
| Baseline date | 2026-10-31T17:28:25Z |
| Exact-HEAD CI | [run 41224692112](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/actions/runs/41224692112) — **success** |
| Issue #57 | **OPEN** (`[P1/ARCH] Consolidate ContentOps Skill discovery and rights-aware resolution without a second engine`) |
| Merged | #71, #76, #77, #78, #79, #80, #81, #84 — all present in `origin/main` |
| Open PRs at audit start | #83 (X organic growth), #62/#58/#50/#49 (draft) |

Branch protection on `main` (`gh api .../branches/main/protection`):

```text
required_status_checks   Tests (ubuntu-latest), Tests (windows-latest), Repo policy checks; strict = true
required_pull_request_reviews   required_approving_review_count = 0
enforce_admins           false
restrictions             none
```

`strict = true` means a PR must be rebased on current `main` before merging; a
green run on an older base is not merge evidence.

Local repository note: the working copy's branch
`fix/57-media-use-status-available` had a **deleted** upstream (the branch was
removed after the #84 squash-merge) and its HEAD `34f43df` is not an ancestor of
`origin/main`. `git diff origin/main HEAD` is empty, so the trees are identical;
all work here was done from `origin/main`. The stale local branch was left in
place, not deleted.

## B. Integration capability matrix

| Capability | Verdict | Evidence |
|---|---|---|
| Skill discovery | **PASS** | `~/.agents/skills/media-use` present; `resolve_capability` reports `installed=true` |
| Registry declaration | **PASS** | `runtime/skill-registry.json` — exact id match, `execution_authorizes: false`, `authorizes_execution: false` |
| Runtime lock | **PASS** | `verify_runtime_lock` → `TRUSTED_RUNTIME`, 5424 files, 0 mismatched, 0 missing |
| Runtime baseline integrity | **PASS** | `hyperframes@0.8.222`, lock `baseline_sha256` equals the committed baseline digest |
| Adapter | **PASS** | `MediaUseStatus.available` true only on a trusted runtime + usable node |
| Rights gate | **PASS** (after fix) | Software / non-commercial / unknown licences refused; bare `rights_reviewed` refused; review record cross-checked |
| Authorization | **PASS** | Default deny; exact context binding; subject/issuer separated |
| Grant source | **PASS** | Owner-gated issuer, provenance digest, atomic single-use markers |
| Execution gate | **PASS** | Re-read before spend, revocation mid-flight, exclusive receipts, sanitized output |
| M5 media_use stage | **PASS** (isolated re-run) | 3 requests → 1 image imported, 1 BGM, 1 SFX; see §C |
| Compose | **PASS** | Real MP4, 1080×1920, h264 + aac |
| QC | **PASS** (with WARN) | 21 checks, 3 warnings, `overall=WARN` |
| Human review | **PASS** (correctly pending) | `PENDING_FOUNDER_REVIEW`, `production_ready=false` |
| Clean-clone M5 reproducibility | **BLOCKED** | Media binaries are gitignored; see §C and D-4 |
| Managed write-path execution | **NOT_APPLICABLE** | `ALLOWED_OPERATIONS` is `("status","doctor")`; no mutating verb is exposed — by design |

## C. Real end-to-end evidence

### C.1 Claimed vs actually executed

| Item | Status |
|---|---|
| Unit / integration suites | **Actually executed** this session |
| Runtime integrity check | **Actually executed** against a real, present runtime |
| Managed gate execution (`status`, `doctor`) | **Actually executed**, real adapter, real runtime |
| M5 pipeline | **Actually executed** in an isolated copy with two substitutions (below) |
| Committed M5 artifact | **Not re-executed** — inputs are gitignored; historical receipts quoted as history only |

### C.2 Runtime integrity

```text
lock      .claude/worktrees/integ-57-media-use/.verify-tmp/host-lock.json
root      D:\Temp\AI-Agents\claude\node-win-20261031\runtime
node      D:\Temp\AI-Agents\claude\node-win-20261031\node-v22.23.4-win-x64\node.exe
state     TRUSTED_RUNTIME    version 0.8.222    file_count 5424
mismatched []  missing []  reasons []
```

The lock's `baseline_sha256` (`6cd2fdc2…`) equals the SHA-256 of the committed
`runtime/media-use-runtime-baseline.json`. With `CONTENTOPS_MEDIA_USE_RUNTIME_LOCK`
unset, `status()` reports `available=false`, `DEPENDENCY_UNVERIFIED`, and the
router refuses with `MISSING_RUNTIME`. Both directions were observed.

### C.3 Managed execution closure (real)

Temporary project `D:\Temp\AI-Agents\claude\media-use-acceptance-20261101`, one
approval, `max_uses: 1`, operations `["status"]`:

```text
decision   AUTHORIZED / AUTHORIZED
execution  EXECUTED   health=true
receipt    receipts/executions/apr-20261101-acceptance1-use-0001.json
adapter    available=true  runtime_state=TRUSTED_RUNTIME  resolve_sha256=18f7e7a4…
exit       0
```

Adversarial cases, same harness:

| Attempt | Result |
|---|---|
| Same `request_id` replayed | `DUPLICATE_REQUEST`, `NOT_EXECUTED` |
| New `request_id`, uses gone | `USES_EXHAUSTED`, `NOT_EXECUTED` |
| Wrong account (`future-ai`) | `CONTEXT_MISMATCH` |
| Approval window in the future | `GRANT_NOT_YET_VALID` (observed first, before widening) |
| Owner identity env unset | `NO_TRUSTED_GRANT` / `ISSUER_NOT_APPROVED` |
| Runtime lock env unset | `NOT_RESOLVABLE` / `MISSING_RUNTIME` |

A second temporary project with operations `["doctor"]` produced
`EXECUTED`, `health=true`, `adapter_receipt.ok=true`, and a sanitized receipt —
the health field and the run state are now carried separately.

No historical approval, ledger or receipt was read into, reused, overwritten or
deleted. `apr-20261031-m5status1` remains untouched (it lives outside this
checkout, under `D:\Temp\AI-Agents\claude\contentops-phase10-main`).

### C.4 M5 pipeline

Run: `python scripts/m5_production.py .verify-tmp/m5-e2e-20261101/m5-media-use`
with `CONTENTOPS_MEDIA_USE_RUNTIME_LOCK` pointed at the trusted lock. Exit 0.

```text
sources      {"count": 2}
media_use    {"state": "OK", "count": 3, "bgm": true, "sfx": 1}
assets       {"count": 1}
claims       {"count": 3}
script       {"lines": 4}
narration    {"duration_s": 25.058, "engine": "windows_sapi"}
subtitles    {"cues": 4}
storyboard   {"shots": 4, "bgm": true, "sfx": 1}
compose      {"state": "OK", "video": "project://final/m5-media-use.mp4"}
qc           {"overall": "WARN", "audio": true}
production_ready False (PENDING_FOUNDER_REVIEW)
```

**Two substitutions, disclosed.** The committed project ships no media binaries
(`final/`, `.media/`, and the image/audio inputs are gitignored). To exercise the
real chain offline:

1. `assets/support.png` ← the repository's own tracked
   `projects/easel-review/sources/screenshots/01-easel-hero.png`, which is exactly
   what the project's rights record describes ("screenshot of the pinned Easel
   runtime"). SHA-256 `85c4ab5c…`, 38438 bytes.
2. `assets/bed.mp3` ← a fresh deterministic ffmpeg tone (220 Hz, 20 s, fades),
   consistent with the declared `OWNED-GENERATED-LOCAL` / `synthetic: true`.
   The committed bed (96907 bytes, `1dcb9c7e…`) is **not** reproducible.

The produced artifact is therefore **not** the committed artifact and no claim is
made that it is.

MP4 checks:

```text
file      .verify-tmp/m5-e2e-20261101/m5-media-use/final/m5-media-use.mp4
sha256    c03e05efd7189e36b62a8e89d619c1aad1d7756e81e4eb16dcc5b157c59527ff
size      516163 bytes
video     h264 1080x1920 30/1fps 25.067s
audio     aac 25.058s
```

| Question | Answer | Evidence |
|---|---|---|
| Image really imported? | **Yes** | `media-use-stage.json`: `support_visual` `IMPORTED`, sha `85c4ab5c…`, `receipt_ref support.png.receipt.json`, `provider_call=false` |
| Image really in the video? | **Yes** | the frame at 1.5 s shows the same title-card content as `01-easel-hero.png` ("ZJU-REAL / Easel"), scaled to 1080×1920 with burned subtitles over it; the shot's `image`/`source` fields point at `assets/support.png` |
| BGM really mixed? | **Yes** | Goertzel magnitude at 220 Hz over 1.0–1.4 s: composed **64.75** vs narration **0.03** |
| SFX really at 6.15 s? | **Yes** | composed 50 ms RMS rises 211 → 953 → 747 → 256 across 6.15–6.30, matching the SFX file's own 360 → 1787 → 1357 → 442 envelope; narration does not show that shape |
| Narration intact? | **Yes** | 25.058 s SAPI track present in the mix; subtitles (4 cues) burned correctly |
| QC ran? | **Yes** | 21 checks; warnings on `duration_range`, `real_source_ratio`, `real_evidence_present` |
| Human review? | **Correctly pending** | `production_ready=false`, `PENDING_FOUNDER_REVIEW` |

Caveat on the SFX measurement: a raw envelope cross-correlation between the
composed track and `narration.wav` is weak (0.21), because compose re-times and
normalizes narration per shot. The cue is therefore evidenced by the local
envelope match at the declared time, not by whole-track correlation.

## D. Defects and remediation

| ID | Sev | File | Root cause | Reproduction | Expected | Actual | Fix |
|---|---|---|---|---|---|---|---|
| D-1 | **P1** | `scripts/media_use_adapter.py` `cmd_ingest` | `ingest` never called `_import_rights`; the adapter only rejects an empty licence | `media-use ingest --license CC-BY-4.0` (or `GPL-3.0`, unknown) with no review record | `EXIT_BLOCKED` / `RIGHTS_REVIEW_REQUIRED` | `EXIT_OK`; file frozen into the project | **Fixed** — `ingest` runs the same policy and accepts `--rights-review` |
| D-2 | P2 | `scripts/skill_execute.py`, `src/contentops/skills/execution_gate.py` | doctor wrapper returned `ok: True` unconditionally | `MediaUseDoctor.ok == False` | health distinguishable from run state | recorded `EXECUTED` with no separate verdict | **Fixed** — `health` carried separately; `ok` unchanged |
| D-3 | P2 | `tests/test_m5_media_use_workflow.py` | `rights_gate._inside()` had no test | review record at `../outside.rights.json` | refused | (was untested) | **Fixed** — regression test added |
| D-4 | P2 | `projects/m5-media-use/` | media binaries are gitignored | fresh clone | full re-run possible | cannot re-run; historical only | **Open** — see §D.1 |
| D-5 | P3 | `src/contentops/skills/grant_source.py:233` | `load_grant` hardcodes `uses_consumed=0` | disk-loaded exhausted grant | `USES_EXHAUSTED` in `evaluate` | unreachable; `consume()` still enforces | Documented — defense in depth, not a hole |
| D-6 | P3 | `src/contentops/skills/authorization.py:359` | `max_units` validated, never metered | request `units` > 1 | budget consumed | `units` fixed at 1 | Documented — budget is effectively "uses only" |
| D-7 | P3 | `media_use_adapter.py:1617` | note string truncated in a public receipt | read `assets/support.png.receipt.json` | readable sentence | "It supports a video evidence_capable is false by construction." | Documented — committed receipts left as history |
| D-8 | P3 | `scripts/media_use_adapter.py` (SFX receipt) | SFX import receipt lives under gitignored `.media/audio/sfx/` | review SFX provenance from the repo | receipt tracked | absent | **Open** — see §D.1 |

### D.1 Remaining blockers and the minimum move for each

1. **D-4 — committed M5 artifact is not reproducible from a clean clone.**
   Minimum move: commit the two small owned inputs (the support screenshot and
   the generated tone bed) with their receipts, or replace them with a tracked
   fixture directory and record that in `sources/assets.json`. Until then every
   M5 acceptance claim is "historically executed", not "reproducible".
2. **D-8 — SFX provenance is not reviewable from the repository.**
   Minimum move: copy `sfx_001.mp3.receipt.json` next to `assets/` like the other
   imports, or add the SFX to a tracked fixture set.
3. **Managed write path is not covered by the gate** (not a hole, a scope
   boundary). `resolve`/`adopt`/`ingest`/`import` are reachable from the CLI and
   from M5 without a grant. Opening them needs an approved design for side
   effects, scope and idempotency — explicitly out of scope for this round.
4. **`units` / budget metering** is nominal (D-5, D-6). No exploit was found,
   because `max_uses` is enforced by atomic markers.

## E. Test results

Executed on Windows 11, Python 3.13, `python -I`.

| Suite | Result |
|---|---|
| `test_skill_execute_status.py` | 4 passed |
| `test_execution_gate.py` | 24 passed |
| `test_trusted_grant_source.py` | 19 passed |
| `test_skill_execution_authorization.py` | 33 passed |
| `test_skill_router_capabilities.py` | 29 passed |
| `test_skill_doctor.py` | 8 passed, **1 skipped** (symlink, no privilege) |
| `test_media_use_adapter.py` | 56 passed |
| `test_m5_media_use_workflow.py` | 27 passed |
| `test_m5_evidence.py` | 18 passed |
| `test_media_convergence.py` | 97 passed |
| `test_local_approval_gitignore.py` | 5 passed |
| `test_media_use_ingest_rights.py` (new) | 5 passed |
| **Total** | **325 passed, 1 skipped, 0 failed** |
| `scripts/dev_check.py` | ALL CHECKS PASSED |

The one skip is a Windows privilege limitation for creating a symlink; it is not
counted as a pass. Adversarial coverage exercised: unapproved grant, expired
grant, not-yet-valid grant, replay, concurrent consumption (thread + separate
process), scope drift, tampered runtime, missing skill, wrong account, wrong
stage, missing rights record, forged third-party rights, path traversal, symlink
escape, duplicate import, network/paid escalation, secret and host-path leakage
in receipts, and Windows/Linux path differences.

Mocking caveat: `test_m5_media_use_workflow.py` drives the stage with a
`FakeMediaAdapter`. Real-adapter behaviour is covered by
`test_media_use_adapter.py` and was additionally exercised by §C.

## F. Verdict

```text
1. M5 offline media integration        PARTIALLY_ACCEPTED
2. Managed skill execution closure     FULLY_ACCEPTED
3. ContentOps production release       BLOCKED
```

- **M5 offline media integration — PARTIALLY_ACCEPTED.** The chain runs and the
  produced video demonstrably contains the imported image, the BGM and the SFX at
  the declared cue, with narration and burned subtitles intact. It is not
  *fully* accepted because the committed artifact cannot be reproduced from a
  clean clone (D-4) and one SFX provenance receipt is untracked (D-8).
- **Managed skill execution closure — FULLY_ACCEPTED** for the declared scope
  (`status`, `doctor`). Default deny, exact binding, atomic single use, replay
  refusal, revocation detection, sanitized receipts and health/state separation
  all hold against a real adapter and a real trusted runtime. The scope is
  read-only by design; no mutating verb is exposed.
- **ContentOps production release — BLOCKED.** `production_ready=false`,
  `human_review=PENDING_FOUNDER_REVIEW`, QC is `WARN` on `real_evidence_present`.
  Nothing in this audit changes that.

## G. GitHub delivery

| Item | Value |
|---|---|
| Issue | [#57](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues/57) (reused; still open) |
| PR | [#86](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/86) |
| Base SHA | `459abb4815b163bc7c53c937c523f6190164b25c` |
| Code commit | `310686025da1874738bb0a75ca5657e41474a329` |
| Report commit (substantive HEAD) | `9e2905179e1fc770c9ae45094de391a7fdfeb552` |
| Exact-HEAD CI | [run 41228296380](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/actions/runs/41228296380) on `9e29051` — **success**; `Repo policy checks`, `Tests (ubuntu-latest)`, `Tests (windows-latest)` all green |
| Exact-HEAD CI, current HEAD | [run 41228680309](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/actions/runs/41228680309) on `602f0b5` — **success**; same three checks green |

Documentation-only commits after `602f0b5` may move HEAD again; the PR's check
rollup is authoritative for the merge decision, and every commit cited here was
green on its own SHA.
| Files changed | `.github/workflows/ci.yml`, `scripts/media_use_adapter.py`, `scripts/skill_execute.py`, `src/contentops/skills/execution_gate.py`, `tests/test_execution_gate.py`, `tests/test_m5_media_use_workflow.py`, `tests/test_skill_execute_status.py`, `tests/test_media_use_ingest_rights.py` (new), and this report |
| Merge | **Not performed.** Branch protection requires 3 checks on the exact HEAD; owner decision required. |

Risks left open after the PR: D-4 and D-8 (both about repository-visible
provenance, not about enforcement), plus the documented P3 notes.

## Closing answer

**No — `media-use` is not yet fully "ContentOps calls it automatically, real
material is available, evidence and rights are controlled, execution cannot
escalate, and a clean environment reproduces it".**

What is true today, with evidence:

- ContentOps does call the skill automatically in the M5 `media_use` stage.
- Real material is imported with a recorded SHA-256 and really reaches the
  rendered frames and the audio mix.
- Execution cannot escalate: the gate is default-deny, single-use, replay-proof,
  and the router never grants execution.
- Rights are enforced at both entry points after this PR.

The last blockers, each with its minimum move:

1. **The committed M5 sample cannot be re-run from a clone** (D-4). Commit the two
   owned inputs and their receipts, or a tracked fixture set.
2. **The SFX import receipt is not in the repository** (D-8). Track it beside the
   other import receipts.
3. **The mutating verbs remain outside the managed gate.** Needs an approved
   design for side effects and idempotency before any widening. Do not widen
   `ALLOWED_OPERATIONS` without it.

Closing 1 and 2 would move M5 to `FULLY_ACCEPTED`. Item 3 is a scope decision, not
a defect, and item 3 plus the `WARN` QC keeps overall release at `BLOCKED`
regardless.
