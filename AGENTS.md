# AGENTS.md — Project rules for AI agents (Codex / Claude Code)

> This file constrains AI agents working in `X-SuperPlay-ContentOps`.
> For full architecture, PRD, or quality standards, follow the canonical docs.

## North Star

> Real Business Source → Traceable Content → High-quality final.mp4 / Native Graphic Package → Founder willing to publish

Any work must answer: does this help produce a publishable video or graphic package faster and more reliably?

If not → don't do it now.

## 0. Content Production Harness Protocol (MANDATORY FIRST STEP)

When the user asks to create, revise, or evaluate any **video, graphic card set, WeChat/Zhihu/CSDN article, or X post**, do **NOT** scan 30+ docs or guess scripts/colors/skills. Run **ONE** command first:

```powershell
python scripts/make_content.py context --request "<user instruction>" [--project projects/<slug>] [--write]
```

This single progressive-disclosure entry builds `contentops.task-contract/v1` + `contentops.context-pack/v1`:
1. **Six-Tier Rule Priority & Conflict Check** (Tier 1 Immutable Boundaries > Tier 2 Account Hard Policies > Tier 3 Platform Scope > Tier 4 Owner Task Overrides > Tier 5 Account Defaults > Tier 6 Suggestions). If `status == "CONFLICT_BLOCKED"`, **STOP** and report every `HARD_BLOCK` conflict (e.g., FI desktop recording, AI image as evidence, Xiaohongshu graphic) without silently overriding or degrading.
2. **Exact Active Visual Tokens**: Body scenes and graphic templates **MUST** use the account's light palette (`FI`: `#E9EDEF` / `#F9FBFA` / `#157F8B`; `1024`: `#F4F2ED` / `#FFFFFF` / `#087FA6`). Brand dark `#0F1117` is restricted strictly to intro/outro marks — **never** black text cards on body frames.
3. **Skill-First Routing (Progressive)**: Loads only the 3–6 skills relevant to this task (avoiding host-level 250+ skill context-budget overflow). Run `python scripts/skill_route.py --audit` to inspect installed vs declared vs executable skills.
4. **Canonical Production Entry**:
   - Production gate entry: `python scripts/make_content.py context | answer | check | run | verify-instructions`
   - Video directing & formal render: `python scripts/direct_video.py` → `python scripts/render_film.py --mode formal` (continuous video via `om render --workers 1`, never passing off an animatic as final video)
   - Graphic templates & native platform packages: `python scripts/render_graphic_templates.py` → `python scripts/make_content.py check`
   - Bare `run_v1.py`, `produce_video.py`, or `m5_production.py` are **diagnostic paths only** and bypass production gates.
5. **Xiaohongshu Workflow Boundary**: Xiaohongshu is **VIDEO-only** (`xiaohongshu_video`); graphic/image-text is unsupported and must never be silently converted to video.
6. **Content & Editorial Standard**: Real findings and information gain before drafting; zero AI throat-clearing/filler; preserve verified facts; never fabricate first-person test claims. Every output stays `production_ready: false` / `publish_authorized: false` until named human review.

## 1. Core Rules (by priority)

1. **Production output > pretty architecture.** A working `final.mp4` beats ten design docs.
2. **Real evidence > generated visuals.** Screenshots, recordings, real data. AI visuals are auxiliary.
3. **Evidence before Claim.** LLM drafts, evidence verifies. Never: LLM says it → therefore true.
4. **No secrets in Git.** API keys, cookies, tokens, `.env` — never committed. `.verify-tmp/` and `docs/ai-provider-selection.md` stay gitignored.
5. **No upstream modification.** Easel is pinned at v0.3.0 / commit `bb3c8ff` and **frozen**
   (Founder decision, 2026-11-16). See `runtime/easel-pins.json`; `runtime/easel.lock.json` is
   its projection.
6. **Frozen engine, no upstream following.** New upstream releases, tags and `main`
   commits are information only. A change to the engine happens when the Founder asks for
   that specific change, and then through the process in `docs/UPSTREAM-EASEL.md`.
7. **FAIL is FAIL.** Never silently degrade to pass QC. Fallback marks `production_ready: false`.
8. **Keep review and execution separate.** Local, non-paid Huashu draft rendering may run in `AUTO` and `REVIEW` without per-project execution grants or copy approval. It must stay project-local, use the pinned installed runtime and authorized assets, and keep `production_ready: false` / `publish_authorized: false` until required human review. Paid/network actions, unclear asset rights, and external publication retain their own gates; never bypass them.
9. **No direct push to main.** All changes via PR. `main` is **PROTECTED** (enabled 2026-10-31): required checks `Tests (ubuntu-latest)`, `Tests (windows-latest)`, `Repo policy checks`; PR required; no force push; no deletion; linear history. Required approval count is 0 while the owner works solo; raise it to 1 when a second reviewer exists.
10. **Documentation freshness is gate-checked, not aspirational.** Every tracked
    doc in `config/docs/doc-freshness.json` carries the date it was verified
    against (`> Last verified: YYYY-MM-DD`). If a commit touches that doc's mapped
    code after that date, `scripts/check_doc_freshness.py` fails locally and in CI.
    Read the diff, correct the facts, then bump the date — in the primary and the
    mirror in the same change. Never bump the date to silence the check. Adding a
    Tier-1 doc means classifying it in the config in the same PR. Procedure:
    [docs/DOC-SYNC.md](docs/DOC-SYNC.md).
11. **Each change carries risk-appropriate verification.** Use the L0–L3 policy in `docs/TEST-PLAN.md`; do not run unrelated checks. `doctor.py` is for environment/runtime/install/deployment changes, and `qc_video.py` is for actual video artifacts or video-QC behavior. Run `python scripts/dev_check.py` once as the complete local gate when preparing a PR, not after every small edit. `--quick` only skips the repository policy check; it is not a targeted test mode.
12. **Research before factual VIDEO copy.** VIDEO production and shared `TOPIC` packages must pass the signed pre-copy research gate (`contentops.precopy-research/v1`) before `script/master.md` or copy approval: bind the router's `ContentIntent`, read the relevant project files, verify authoritative sources, write an outline, an evidence list and a boundary statement, then have a named human sign with `--confirm`. A standalone `GRAPHIC_TEXT` draft does not block on VIDEO's signed pre-copy research receipt: draft with concrete findings, cite sources as they become available, and mark uncertain claims rather than blocking writing. Keep image rights, provider spend and external delivery as separate real gates. Procedure: [docs/PRECOPY-RESEARCH.md](docs/PRECOPY-RESEARCH.md).

## 2. Extension Policy

Priority when extending Easel:

```
ADAPTER     → wrap external API without modifying upstream
EXTENSION   → add new module in X-SuperPlay-owned space
CUSTOM SKILL → add Easel skill in extensions/ or skills/
UPSTREAM PATCH → modify Easel source (requires patch file + tests + upgrade note)
FORK        → last resort only
```

Current state: no fork. `assemble_easel.py` is an ADAPTER (orchestration workaround).

## 3. Content Truth Boundary

### Allowed

- "Official implements X" (cite README / source)
- "v0.2.1 release shows Y"
- "Doctor output shows A" (with receipt)

### Forbidden

- "I tested X" (unless actually tested this session)
- "Y is stable" (without data)
- Fabricated cases / data / metrics

## 4. Fallback Honesty

| Engine | Role | May report production_ready? |
|---|---|---|
| `easel` | Production candidate | Only with human approval + QC PASS |
| `fallback` | Diagnostic only | **Never** — always `production_ready: false` |
| future MiniMax | Production (when verified) | Only with receipt + quota tracking |

Any degradation must appear in the receipt:

```yaml
requested_provider: ...
actual_provider: ...
fallback_reason: ...
quality_impact: ...
requires_human_review: true
```

## 5. Receipt Culture

Every project run produces receipts:

```
projects/<slug>/receipts/
  build-<engine>.json
  qc-report.json
  qc-report.md
  runtime-receipt.md
  human-review.json (when completed)
```

No receipt = task not done.

## 6. File Discipline

- Don't modify Easel source (`.runtime/easel/`).
- Don't commit `.runtime/`, `Easel/`, `.env`, `.verify-tmp/`, `docs/ai-provider-selection.md`.
- Use helper scripts, not bare `cd .runtime/easel && python ...`.
- Don't copy Easel source code into the repo.

## 7. Canonical Docs Map

| Need | Read |
|---|---|
| What runs today | [docs/CURRENT-STATE.md](docs/CURRENT-STATE.md) |
| System boundaries | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| How to run | [docs/RUNBOOK.md](docs/RUNBOOK.md) |
| What we're building | [docs/PRD.md](docs/PRD.md) |
| Quality gates | [docs/QUALITY-STANDARD.md](docs/QUALITY-STANDARD.md) |
| Local verification policy (L0–L3) | [docs/TEST-PLAN.md](docs/TEST-PLAN.md) |
| Documentation freshness procedure | [docs/DOC-SYNC.md](docs/DOC-SYNC.md) |
| Per-platform status | [docs/PLATFORM-INTEGRATION-STATUS.md](docs/PLATFORM-INTEGRATION-STATUS.md) |
| Narration ASR gate | [docs/ASR-BACKCHECK.md](docs/ASR-BACKCHECK.md) |
| Current convergence plan | [docs/CONVERGENCE-REQUIREMENTS-2026-11-01.md](docs/CONVERGENCE-REQUIREMENTS-2026-11-01.md) |
| Easel pin policy | [docs/UPSTREAM-EASEL.md](docs/UPSTREAM-EASEL.md) |
| Decisions | [docs/adr/](docs/adr/) |
| Research | [research/README.md](research/README.md) |
| Audit | [docs/AUDIT-REPORT.md](docs/AUDIT-REPORT.md) |

## 8. MiniMax Boundary

- `billing_mode: subscription`
- `allow_payg: false`
- Capability spike (Issue #4) must complete before any implementation.
- No fake adapters. `MANUAL_ONLY` is a valid status.
- Provider endpoint URLs, pricing, and business strategy stay local-only.

## 9. Commit Discipline

- Message prefix: `feat:` / `fix:` / `docs:` / `chore:` / `test:` / `refactor:`
- Reference Issue numbers: `Refs #N`
- No mega-commits. One logical change per commit.
- Run the checks required by the change's risk level in `docs/TEST-PLAN.md`; do not turn this into a repeated full suite after each small edit.
- New `tests/test_*.py` suites must be wired into `.github/workflows/ci.yml`.

## 10. Session Hygiene

A session ends with zero invisible work. Anything that exists only on this
machine — uncommitted modifications, unpushed branches or tags, worktree-only
files — is invisible to GitHub, has no receipt, and dies with the disk. The
2026-11-10 drift (784 uncommitted lines, two unpushed island branches) and the
surviving pr2 worktree are the standing examples.

- Before ending a session, run `git status --porcelain` and `git stash list`.
  Every uncommitted change must be either committed to a registered branch,
  deliberately discarded, or recorded in an issue / receipt as deliberately
  parked. Untracked non-gitignored files count as uncommitted work.
- A local branch or tag holding unique work must be pushed in the same session
  (archive tags included). "Archived locally" is not a backup. An archive
  action is complete only when the push has succeeded.
- A worktree is temporary. Before removing one, diff it; unique content is
  salvaged into a branch/tag or explicitly retired in writing first.
- Registering a branch in `config/governance/branch-registry.json`? Run
  `python scripts/check_branch_registry.py --today <date>` locally BEFORE
  committing: non-persistent entries require a non-null `expires` (the
  #148 first-attempt CI failure came exactly from skipping this). `expires`
  is a **review date, not a deletion deadline**. `status=merged` past that
  date is reported as `RETIRE DUE` (report-only, never a CI failure) and
  `status=archived` is a deliberate permanent snapshot exempt from
  `max_age_days`; active statuses past their review date still fail as
  `EXPIRED`. Once a month, remove merged entries whose remote branch no
  longer exists in a governance PR — Git history keeps the audit trail.
  Also validate a future `--today` date, not just today's, so a calendar
  time-bomb cannot reach CI unnoticed.
- New test suites: besides the ci.yml wiring rule above, verify the suite
  actually runs (`python tests/<suite>.py` exits 0 locally) — CI green on a
  suite that was never executed locally is not evidence of anything.
