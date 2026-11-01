# Convergence Requirements — 2026-11-01

> Status: **ACCEPTED** — Owner authorization 2026-11-01.
> P0 and P1 are delivered in this change; P2–P4 are scheduled.
> Decisions D1–D6 are frozen in
> [adr/ADR-012-convergence-decisions.md](adr/ADR-012-convergence-decisions.md).
> Scope: documentation truth, skill alignment, branch convergence, upstream pins.
> Owner: Xander-Xai. Author: Claude Code (audit run, 2026-11-01).
> This document does not change production behaviour by itself.

> **Execution status (2026-11-01, after the merge).** Steps 1, 1b and 2 of the
> §7 runbook are done. PR #89 merged the integration stack into `main`;
> `fix/57-m5-media-fixtures` and its remote branch are gone. The five content
> skills carry a status banner, and `scripts/check_skill_references.py` — with
> the capture-group defect fixed — is wired into `dev_check.py` and CI. The
> analysis below is the state at decision time and is not rewritten. Steps 3–5
> remain open.

## 1. Executive summary

The repository can produce video, but it cannot currently describe itself
honestly. Three layers disagree:

1. **`main`** — the protected branch, 17 commits behind the working branch.
2. **`fix/57-m5-media-fixtures` (HEAD, PR #89)** — the newest M5/media-use work.
3. **Unmerged branches and worktrees** — the account-aware content router,
   workflow gates, X/XHS/GZH tracks, and the five `x-superplay-*` skills that
   depend on them.

Every document written before the last convergence pass still describes a
mixture of those layers. The five installed content skills reference files
that are absent from this branch. The upstream pins are behind the current
stable releases. The result is not a missing feature — it is an unreadable
system.

This document defines what must become true, in what order, and what needs an
Owner decision before code moves.

## 2. Evidence collected (2026-11-01)

All commands were run against `d:\Projects\X-SuperPlay-ContentOps` on
`fix/57-m5-media-fixtures`.

| # | Finding | Evidence |
|---|---|---|
| E1 | HEAD is 17 commits ahead of `main`; `main` has no M5/media-use work | `git rev-list --left-right --count main...HEAD` → `0 17` |
| E2 | `main` has ADR-001…007; HEAD has a duplicated ADR-007 and ADR-008…010 | `git ls-tree -r --name-only main -- docs/adr` vs `HEAD` |
| E3 | The content router and workflow gate are not on HEAD | `git cat-file -e HEAD:scripts/workflow_gate.py` fails; present on `feat/content-router` |
| E4 | The five `x-superplay-*` skills reference `scripts/workflow_gate.py`, `scripts/recording_plan.py`, `scripts/design_router.py`, `src/contentops/workflow/*` — none exist on HEAD | skill `SKILL.md` bodies vs `ls` |
| E5 | `src/contentops/{workflow,routing,quality,script,hotspots,optimization}` and `platforms/xhs` are empty on HEAD (only stale `__pycache__`) | `find` / `git ls-tree -r HEAD -- src/contentops` |
| E6 | README claims a vendored 公众号 track, but no GZH code is on HEAD | README status table vs `git ls-tree HEAD -- scripts` |
| E7 | CURRENT-STATE is append-only: it claims 9 tests, edge-tts as the pipeline voice, 6 web-workbench FAILs, and "main is the only persistent branch" | `docs/CURRENT-STATE.md` §Pipeline/§Web Workbench/§Tests/§Git |
| E8 | Actual test inventory is 30 suites, 704 `test_*` functions plus list-driven suites; `scripts/test_basic.py` has 10 | `grep -c '^def test_'` |
| E9 | `doctor.py` reports all 7 checks OK on this host | `python scripts/doctor.py --json` |
| E10 | `skill_route.py --capabilities` reports `media-use` as `BLOCKED / MISSING_RUNTIME` on this host | router output |
| E11 | Easel pin is v0.2.1; upstream stable is v0.3.0 (2026-10-12), 158 commits / 300 files | `gh api repos/ZJU-REAL/Easel/releases/latest` |
| E12 | Easel v0.3.0 moved all skills from `skills/openclaw/` to `skills/builtin/` and changed `auto-short-video/scripts/assemble.py` | upstream compare |
| E13 | The v0.3.0 tag was force-replaced upstream while keeping the version number | release notes: "本次发布替换此前的 v0.3.0" |
| E14 | HyperFrames pin is 0.8.222; upstream stable is 0.8.225 (2026-10-31), 34 commits | `gh api repos/heygen-com/hyperframes/releases/latest` |
| E15 | `skills/media-use/SKILL.md` and its references changed between 0.8.222 and 0.8.225 | upstream compare |
| E16 | Untracked content projects (`projects/x-superplay-1024`, `easel-fi-audio-first`, `gzh-thinktank`) have no `project.yaml` or `receipts/` | directory inspection |
| E17 | 30+ git worktrees exist under `.claude/worktrees` and `D:\Temp\AI-Agents` | `git worktree list` |
| E18 | `docs/INDEX.md` is accurate about which docs exist, but `TEST-PLAN`/`PRD`/`DEVELOPMENT-PLAN` are stale | doc read |

## 3. Root causes

- **Branch-defined architecture.** Work was done in issue branches and
  worktrees, then documented as if it were on the integration branch. No
  single document states which layer a fact belongs to.
- **Skills shipped ahead of code.** The `x-superplay-*` skills were copied from
  a retired workspace and adapted to this repo's paths before the target code
  was merged. They are now accurate against `feat/content-router`, not HEAD.
- **Append-only status doc.** `CURRENT-STATE.md` accumulated milestone records
  and never shed the superseded ones, so old and new facts sit side by side.
- **Pin policy without a review cadence.** The Easel/HyperFrames pins are
  deliberately frozen, but no document records the deltas or the decision to
  stay frozen.

## 4. Required outcomes

### R1 — One truthful status layer (P0)

Every Tier-1 doc states what is true on the branch it ships from, and labels
unmerged layers explicitly.

Acceptance:
- README status table distinguishes **on this branch**, **unmerged branch**,
  and **not started**.
- ARCHITECTURE component map lists only modules present on the branch, plus a
  clearly separated "unmerged / planned" section.
- CURRENT-STATE opens with a verified summary and marks historical sections as
  historical.
- TEST-PLAN lists the real suites and their CI wiring.
- PRD and DEVELOPMENT-PLAN carry per-milestone status, not future tense.
- `python scripts/check_docs.py`, `check_i18n.py`, `dev_check.py` pass.

### R2 — Skills tell the truth (P0)

No installed skill may present a command or module that does not exist on the
branch it claims to serve.

Acceptance:
- Each `x-superplay-*` skill declares its dependency on the unmerged
  `feat/content-router` layer at the top of the file.
- `docs/SKILL-REGISTRY.md` lists the five content skills as **not declared**
  and explains why: a registry entry must point at code on this branch.
- The router continues to report them as unknown / blocked, not runnable.

### R3 — Canonical content architecture (P1, Owner decision)

Decide how the account/brief front-end (content router) and the evidence-first
production chain (M5) become one system.

Acceptance:
- One ADR records the chosen layering and merge order.
- The content router is merged in slices, each with tests, not as one draft.
- `scripts/workflow_gate.py` and its validators exist on the integration
  branch before any skill is declared against them.

### R4 — Upstream pin policy (P1, Owner decision)

Record the Easel v0.3.0 and HyperFrames 0.8.225 deltas and decide.

Acceptance:
- An Upgrade Issue states the delta, the breaking changes, the regression
  suite, and the rollback.
- Easel v0.3.0 is treated as **high risk**: skill paths moved, the assembly
  script changed, and the tag was force-replaced. Pinning it requires a
  content digest, not just a tag.
- HyperFrames 0.8.225 is treated as **patch-level** only after the `media-use`
  skill commit is re-pinned and the runtime lock is regenerated.
- No auto-upgrade.

### R5 — Repository hygiene (P2)

Content projects and worktrees stop being invisible state.

Acceptance:
- Every tracked `projects/<slug>` has `project.yaml` and receipts, or is
  explicitly marked `draft` in a manifest.
- Untracked content outputs are either adopted with receipts or left local and
  documented as local-only.
- Worktree cleanup follows the filesystem policy: audit, report, ask, then act.
  No worktree is deleted by this plan.

### R6 — CI reflects the real suite (P1, delivered)

Acceptance:
- Every `tests/test_*.py` that is meant to run in CI has a named CI step.
- TEST-PLAN and CURRENT-STATE counts match the suite inventory.
- A new suite without a CI step fails a repository check, or the omission is
  documented in the PR.

Delivered by `check_repo_policy.check_test_suites_registered_in_ci`: every
`tests/test_*.py` must appear in `.github/workflows/ci.yml`, and a suite that
does not is a policy failure.

### R7 — Skill drift is caught by a check, not by a reader (P0, delivered)

The five installed content skills name code this branch does not have. A prose
note decays; a check does not.

Acceptance:
- `runtime/content-skill-status.json` records every repository path an
  installed skill names that is absent on this branch, with the branch that
  carries it and a note.
- `python scripts/check_skill_references.py` fails on an undocumented dangling
  reference, on a recorded reference that has since appeared (the layer merged
  and the record is stale), and on a skill marked `MERGED`/`DECLARED` whose code
  is missing.
- The check runs in `dev_check.py` and in CI, and its suite
  (`tests/test_skill_references.py`) is wired into the CI matrix.
- With no shared store on the host (CI), the reference scan is skipped and only
  the record-versus-branch checks run. A skip is reported as a skip.

## 5. Phased plan

| Phase | Outcome | Depends on |
|---|---|---|
| **P0** | R1 + R2 + R7: docs converged, skill status declared and enforced by a check | done |
| **P1** | R6 + the decision record | done — ADR-012 |
| **P2** | R3 merge slices S1–S4 from `feat/content-router` | Owner-authorized; slice by slice |
| **P3** | R4 upgrade gate for Easel / HyperFrames | Easel deferred (D3); HyperFrames with the runtime install (D4) |
| **P4** | R5 project and worktree hygiene | audit first; per-item approval for deletion |

P0 and P1 are documentation plus read-only checks, and do not change runtime
behaviour. P2–P4 each start from a clean branch cut from the then-current
integration branch.

Merging a content-router slice lands code the five content skills name. The
skill reference check will then fail with `RECORD_STALE` until
`runtime/content-skill-status.json` is updated in the same PR — which is the
point: the record and the branch must change together.

### What P0 and P1 changed

- README, ARCHITECTURE, CURRENT-STATE, PRD, DEVELOPMENT-PLAN, TEST-PLAN,
  RUNBOOK, SKILL-REGISTRY, DEVELOPMENT-STANDARD and FILE-PLACEMENT-POLICY (with
  their zh-CN mirrors) now state what is on this branch, what is on an unmerged
  branch, and what is not started.
- `docs/INDEX.md` lists the convergence requirements, both ADR-007 records and
  ADR-012.
- `runtime/content-skill-status.json` + `scripts/check_skill_references.py` +
  `tests/test_skill_references.py` make the skill/code drift a CI failure.
- `check_repo_policy.check_test_suites_registered_in_ci` makes an unwired test
  suite a policy failure.
- `docs/adr/ADR-012-convergence-decisions.md` records D1–D6; UPSTREAM-EASEL
  records the measured Easel v0.3.0 delta and why it is not adopted.

## 6. Decisions

Recorded by the Owner on 2026-11-01 and frozen in
[adr/ADR-012-convergence-decisions.md](adr/ADR-012-convergence-decisions.md).

| ID | Decision | Outcome |
|---|---|---|
| D1 | Canonical account/brief front-end | `feat/content-router` (PR #49), merged in slices S1–S4; M5 stays the production engine |
| D2 | Status of the five `x-superplay-*` skills | Undeclared until their code lands; `check_skill_references.py` enforces it |
| D3 | Easel v0.3.0 | **Not adopted.** Tag was force-replaced upstream, skill paths moved, `assemble.py` changed. Future adoption pins a content digest |
| D4 | HyperFrames 0.8.225 | Adopt as a patch release, together with the runtime install: re-pin `skills/media-use`, regenerate baseline and host lock |
| D5 | Untracked content projects | Stay local until worked on again; adoption means `project.yaml` + sources + receipts |
| D6 | Stale worktrees | Audit and report per item; deletion needs a separate, explicit approval |

## 7. Execution runbook

Ordered, mechanical steps. Nothing here needs a new decision; each step has a
verification command that must pass before the next.

### Step 1 — verify this change locally

```bash
python scripts/check_skill_references.py
python scripts/check_repo_policy.py
python scripts/check_docs.py
python scripts/check_i18n.py
python tests/test_skill_references.py
python scripts/dev_check.py
```

### Step 1b — mark the installed skills at the point of use

The repository-side record is not enough: the skill is read before the
repository is. Insert this block after the front matter of each of the five
skills in the shared store (`~/.agents/skills/<skill>/SKILL.md`), listing that
skill's own missing paths:

```markdown
> **Status in X-SuperPlay-ContentOps (2026-11-01): the commands below do not run here yet.**
> They depend on the account-aware content-router layer, which lives on the
> unmerged `feat/content-router` branch (PR #49). The authoritative list of
> missing paths is `runtime/content-skill-status.json` in the repository, and
> `python scripts/check_skill_references.py` fails when that record stops
> matching the branch. Read every command below as the target behaviour once
> that layer lands, not as something that works today.
```

Per-skill paths (from `runtime/content-skill-status.json`):

| Skill | Missing paths |
|---|---|
| `x-superplay-broll-production` | `scripts/workflow_gate.py`, `scripts/workflow_docs.py`, `scripts/check_account_dna.py`, `src/contentops/workflow/sources.py`, `src/contentops/media/claim_coverage.py`, `scripts/material_candidates.py`, `scripts/broll_plan.py`, `scripts/broll_execute.py` |
| `x-superplay-capture-plan` | `src/contentops/workflow/capture_plan.py`, `scripts/recording_plan.py` |
| `x-superplay-source-research` | `scripts/workflow_gate.py`, `src/contentops/workflow/sources.py`, `scripts/material_candidates.py` |
| `x-superplay-design-direction` | `scripts/workflow_gate.py`, `scripts/design_router.py` |
| `x-superplay-copy-orchestrator` | `src/contentops/workflow/audience.py`, `src/contentops/workflow/duration.py`, `src/contentops/quality/script_rhythm.py`, `scripts/copy_strategy.py` |

### Step 2 — land the integration stack on `main`

`main` currently stops at PR #72; the whole media-use and skill-authorization
stack lives on `fix/57-m5-media-fixtures`.

```bash
git switch fix/57-m5-media-fixtures
git add -A -- AGENTS.md CLAUDE.md README.md README.zh-CN.md docs/ runtime/ scripts/ tests/ .github/
git commit -m "docs: converge the project documentation with the code" -m "Refs #7"
git commit -m "feat: make skill-to-code drift and unwired suites CI failures" -m "Refs #7"
git push origin fix/57-m5-media-fixtures
gh pr view 89 --json baseRefName,mergeable,statusCheckRollup
```

If PR #89 targets `main`, it now carries this work as well; update its title
and body so the scope matches what it contains, then merge it with squash after
CI is green.

### Step 3 — cut the S1 slice from the content router

```bash
git fetch origin
git switch -c feat/57-content-router-s1 origin/main
# Branch from main; take only the self-contained S1 files from the router branch.
git checkout origin/feat/content-router -- \
    scripts/workflow_gate.py \
    src/contentops/workflow/__init__.py src/contentops/workflow/contract.py \
    src/contentops/workflow/gate.py \
    tests/test_workflow_contract.py tests/test_workflow_gate.py
# Do NOT copy src/contentops/workflow/ wholesale: validators.py imports the
# evidence/media/quality trees (S2+) and scripts/workflow_docs.py / sources.py /
# capture_plan.py are S2. Landing them here would make content-skill-status.json
# stale for paths that are not ready.
# Write a placeholder validators.py (validators_for -> []) for S1; S2 replaces it.
# Then update runtime/content-skill-status.json (drop the workflow_gate.py refs)
# and wire both suites into .github/workflows/ci.yml, in the same PR.
python scripts/check_skill_references.py
python scripts/dev_check.py
git commit -m "feat: land the workflow stage gate (S1)" -m "Refs #57"
git push origin feat/57-content-router-s1
gh pr create --base main --title "feat: land the workflow stage gate (S1)" --body "..."
```

> Executed 2026-11-01. The literal S1 file list in ADR-012 D1 could not land
> as-is: `validators.py` imports 16 modules that are whole new trees (S2–S4).
> S1 therefore lands the contract/gate core, the CLI, and an **empty
> `validators.py` seam** whose `validators_for` returns `[]` until S2; `check`
> reports no editorial validators are wired for unwired stages. S2 replaces
> `validators.py` wholesale.
>
> **S2 deviation (executed 2026-11-01).** S2 lands only
> `src/contentops/workflow/sources.py` and wires the source-candidate validators
> into `validators.py` for the `assets` stage. `capture_plan.py`,
> `recording_plan.py` and `test_capture_plan.py` are **deferred to S3**:
> `recording_plan.py` reads `config/accounts/<slug>.json` (business strategy that
> stays off the public repository until that exposure is reviewed), and
> `test_capture_plan.py` drives that CLI, so it cannot pass without the config.
> `scripts/workflow_docs.py` is also deferred — it imports
> `contentops.quality.naturalness` and `contentops.workflow.human_forecast`
> (S3/S4 trees).

S1 lands the deterministic stage gate only. Each slice updates
`runtime/content-skill-status.json` in the same PR, because the skill reference
check fails with `RECORD_STALE` the moment the code the skills name appears.

### Step 4 — upstream pins

Easel stays on v0.2.1 (D3). Open an Upgrade Issue for v0.3.0 that requires a
digest-pinned release archive; do not move the lock.

HyperFrames moves with the runtime install (D4):

```bash
python scripts/media_use_runtime.py install --runtime-dir <dir> --node <node> --baseline runtime/media-use-runtime-baseline.json
python scripts/media_use_runtime.py lock --runtime-dir <dir> --node <node> --out <lock.json>
python scripts/media_use_runtime.py verify --lock <lock.json>
python scripts/skill_route.py --capabilities
```

### Step 5 — hygiene audit (no deletion without per-item approval)

Report each worktree, its branch, age, size and whether anything references it.
Deletion is a separate decision per item, per the filesystem policy.

## 8. Non-goals

- No automatic publishing.
- No new provider capability.
- No merge of an unmerged branch without Owner approval.
- No deletion of worktrees, local projects, or gitignored media in this plan.
- No claim that documentation changes make the pipeline production-ready.

## 8. Appendix — upstream research commands

```bash
gh api repos/ZJU-REAL/Easel/releases/latest --jq '{tag_name,published_at,target_commitish}'
gh api repos/ZJU-REAL/Easel/compare/v0.2.1...v0.3.0 --jq '{ahead_by,files:(.files|length)}'
gh api repos/heygen-com/hyperframes/releases/latest --jq '{tag_name,published_at}'
gh api repos/heygen-com/hyperframes/compare/v0.8.222...v0.8.225 --jq '{ahead_by,files:(.files|length)}'
```

Local audit commands:

```bash
git rev-list --left-right --count main...HEAD
git worktree list
python scripts/doctor.py --json
python scripts/skill_route.py --capabilities
grep -c '^def test_' tests/test_*.py scripts/test_basic.py
```
