# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Every time Claude Code enters this repository, it must follow this protocol before making changes.

## Startup Protocol

Before any task, always run:

```bash
git status
git branch --show-current
git fetch --all --prune
```

Then read, in order:
1. `AGENTS.md` — core rules
2. `docs/INDEX.md` — what canonical docs exist
3. `docs/CURRENT-STATE.md` — what actually runs today
4. `docs/DEVELOPMENT-STANDARD.md` — how to work here
5. `docs/FILE-PLACEMENT-POLICY.md` — where files belong

Then read the relevant GitHub Issue and PR.

## Commands

Windows-first repo; all commands run from the repository root with the system Python (no virtualenv required).

```bash
# Environment
python scripts/doctor.py [--json]
python scripts/verify_easel_runtime.py --resolve-tag
python scripts/resolve_easel.py --bootstrap   # or --offline

# Unified developer gate (run before every commit)
python scripts/dev_check.py
python scripts/dev_check.py --quick           # skip repo policy check

# Production pipeline
python scripts/new_project.py --slug my-video --title "My Video"
python scripts/run_v1.py projects/my-video                       # Easel (production candidate)
python scripts/run_v1.py projects/my-video --engine fallback     # diagnostic only
python scripts/m5_production.py projects/m5-media-use            # evidence-first M5 chain
python scripts/qc_video.py projects/my-video

# Discovery / media-use (read-only unless a subcommand says otherwise)
python scripts/skill_route.py --doctor
python scripts/skill_route.py --resolve media-use
python scripts/media_use_adapter.py status
python scripts/media_use_runtime.py verify --lock <path>
python scripts/check_skill_references.py   # installed skills vs code on this branch

# Tests
python scripts/test_basic.py
python tests/test_m5_evidence.py              # one suite
```

`python scripts/dev_check.py` runs: repo policy → subprocess policy → skill references → docs check → i18n check → `test_basic.py` → `git diff --check`. CI additionally runs `check_receipt_secrets.py` and every `tests/test_*.py` suite.

### Testing

There is **no pytest**. Each suite is a standalone script that builds a `TESTS` list and runs it from `main()`; run it directly with `python tests/test_<name>.py`. There is no per-function selector — run the whole suite, or temporarily narrow its `TESTS` list.

Every suite is enumerated explicitly in `.github/workflows/ci.yml`. **Adding `tests/test_x.py` without adding a CI step means it never runs**, and a green CI run is then not evidence. `check_repo_policy.py` now fails when a suite is not named in the workflow, so the omission is caught locally instead of in review.

CI installs `Pillow` and ffmpeg; everything else is stdlib. Some suites SKIP when ffmpeg, Pillow, the media-use runtime, or gitignored artifacts are absent — a green run can hide skipped coverage, so check the reported availability line rather than assuming it passed.

## Architecture

### Two-layer code split

- `scripts/` — CLI entry points and ops only (pipelines, QC, gates, verifiers).
- `src/contentops/` — business logic, imported as a package by adding `<repo>/src` to `sys.path`. Put provider code, billing/quality gates, contracts, and evidence logic here, never in `scripts/`.

Key package boundaries:

| Package | Owns |
|---|---|
| `src/contentops/evidence/` | `SourceArtifact`, `ClaimLedger` — permission-aware evidence and quote-verified claims |
| `src/contentops/media/` | provider contracts, billing guards, capability registry, media envelope/validation/transform, asset planner, quality gate, QC canonicalization, rights gate, `media_use_adapter` |
| `src/contentops/skills/` | skill authorization, execution grants and the execution gate |
| `src/contentops/golden/` | Golden identity, evidence locks, review and A/B variants |
| `src/contentops/platforms/`, `routing/`, `workflow/`, `quality/`, `script/`, `hotspots/`, `optimization/` | platform adapters and pipeline policy |

### Production chain

```
project.yaml source_refs
  → SourceArtifact (permission: NONE cannot back a claim)
  → ClaimLedger (quotes verified against the source)
  → master script → storyboard
  → MediaManifest (assets inventory + timeline)
  → narration / subtitles → pinned Easel compose → qc_video → human review
```

`scripts/m5_production.py` is the evidence-first entry (`sources → media_use → assets → claims → script → narration → subtitles → storyboard → compose → QC → review`). It always ends `PENDING_FOUNDER_REVIEW` with `production_ready: false`.

Composition must reuse the pinned Easel through `scripts/assemble_easel.py` (`assemble_easel.run`). Do not add a second compositor.

### Pinned upstream

- `.runtime/easel/` is Easel v0.2.1 (commit `3fe2d99`), gitignored and **read-only**. `Easel/` is a local working clone and is also gitignored.
- `runtime/easel.lock.json` is the canonical pin; `scripts/resolve_easel.py` resolves it and `scripts/verify_easel_runtime.py` verifies blob hashes.
- `assemble_easel.py` is an **adapter** (orchestration plus the Windows subtitle-burn workaround), not an upstream patch.

### media-use and skill routing

- `src/contentops/media/media_use_adapter.py` is the only module that knows the HyperFrames `media-use` skill exists. Never copy the skill into this repo.
- Execution requires a trusted host lock that names the approved baseline (`runtime/media-use-runtime-baseline.json`) by digest and matches every byte. A clean checkout is `BLOCKED / MISSING_RUNTIME` by design.
- `scripts/skill_route.py` + `runtime/skill-registry.json` are discovery/routing only. Every resolution carries `execution_authorized: false`. Legacy M5 must not import the router.
- The five `x-superplay-*` content skills are installed in the shared store but are **not declared**: their code lives on the unmerged `feat/content-router` branch. `runtime/content-skill-status.json` records every path they name that this branch lacks; `scripts/check_skill_references.py` fails when that record stops matching reality.

## Invariants

These require reading multiple files to learn and are enforced in code or tests:

1. **One verdict per artifact.** `production_ready` stays `false` and `human_review` stays pending until a human writes the review receipt. The fallback engine can never report production-ready.
2. **Receipts are the unit of done.** Every run writes `projects/<slug>/receipts/`. Committed QC receipts go through `contentops.qc_canonical` (logical `project://`/`repo://` paths, explicit `currency` and `graded_target`). Never commit absolute host paths in manifests or receipts.
3. **One manifest, one timeline.** `assets` is the inventory; `timeline` selects exactly one `active_asset_id` per placement. Composition reads the timeline — iterating the inventory is the historical duplicate-shot defect.
4. **Generated media is never evidence.** Provider output is `generated=true`, `evidence_capable=false`; any claim-bearing role raises `GeneratedAssetEvidenceError`.
5. **Fail closed on providers.** Subscription billing only, `allow_payg: false`, `billing_guard` before every call, one attempt with no retry, fingerprint-based cache reuse. Quota is reported as an observed delta, never converted into a price.
6. **media-use defaults closed.** No network, no paid provider, no cross-project reuse, no automatic publication, and no licence approval. The runtime lock proves *what executed*, not where an asset came from.
7. **Gitignore exceptions are exact paths.** The media/evidence exceptions (six screenshots, two voice fixtures, two M5 sample files) are asserted by tests. Do not broaden an exception, negate a directory, or unignore a new binary.
8. **Committed media stays out of Git** unless an exact-path exception and a tracked receipt already exist.

## Never

- Do not work directly on `main`
- Do not create random root files
- Do not invent provider capabilities without a capability spike
- Do not modify `.runtime/easel/` (or the local `Easel/` clone)
- Do not commit local/private provider research (`docs/ai-provider-selection.md`, `.verify-tmp/`, `.private/`, `assert/`, `vendor/`, etc.)
- Do not add a dependency without answering: why is stdlib insufficient?
- Do not skip tests, and do not add a test suite without wiring it into `.github/workflows/ci.yml`
- Do not mark human review as approved automatically
- Do not create files outside of their canonical directory (see `docs/FILE-PLACEMENT-POLICY.md`)

## Before Creating a File

Answer these first:
1. What owns this information?
2. What directory does policy assign it to?
3. Is it canonical / research / generated / runtime / test?
4. Does an existing file already own this fact?

If you do not know: **do not create the file**. Read `docs/FILE-PLACEMENT-POLICY.md` first.

Also record: `docs/CURRENT-STATE.md` claims only verified facts; `research/` and `research/archive/` require their YAML front matter.

## Branch Strategy

- `main` — canonical default branch, never pushed to directly
- Protected: required checks `Tests (ubuntu-latest)`, `Tests (windows-latest)`, `Repo policy checks`; PR required; no force push; linear history
- Short-lived issue-scoped branches: `feat/<issue>-...`, `fix/<issue>-...`, `test/<issue>-...`, `docs/<issue>-...`, `chore/<issue>-...`, `refactor/<issue>-...`
- All changes go through PR → squash merge → branch deleted
- Feature branches run CI on push (`feat/**`, `fix/**`, `chore/**`, `security/**`, `docs/**`, `ci/**`) or via `gh workflow run ci.yml --ref <branch>`

## Extension Priority (Easel)

```
ADAPTER > EXTENSION > CUSTOM SKILL > UPSTREAM PATCH > FORK
```

Fork is last resort. No upstream modification without patch + tests + ADR.

## MiniMax Boundary

- `billing_mode: subscription`
- `allow_payg: false`
- Capability spike required before any implementation
- `MANUAL_ONLY`, `DOCUMENTED_BUT_NOT_TESTED` are valid, honest statuses
- Provider endpoint URLs, pricing, and business strategy stay local-only

## Bilingual Documentation Policy

Tier-1 docs require both English and Chinese versions:

- Modifying a Tier-1 English doc requires updating the zh-CN mirror in the same PR.
- Modifying a zh-CN mirror to change facts (not pure translation) requires updating the English canonical too.
- zh-CN mirrors must include YAML front matter: `translation_of`, `language: zh-CN`, `translation_status: synced`.
- Run `python scripts/check_i18n.py` before every commit.
- Machine checks structural synchronization, not translation quality.

## Windows Subprocess Policy

- Background subprocesses (ffmpeg, ffprobe, helper Python) MUST use `scripts/process_utils.py` with hidden window.
- Interactive subprocesses (gh auth login, OAuth, manual debug) MUST stay visible.
- Never use `shell=True` for background subprocesses.
- Debug override: set `CONTENTOPS_SHOW_SUBPROCESS_WINDOWS=1` to force visible windows.
- Hidden windows do NOT hide errors: stdout/stderr/returncode must always be captured.
- `python scripts/check_subprocess_policy.py` enforces this and runs in both the local gate and CI.

## Receipt Culture

Every run produces receipts under `projects/<slug>/receipts/` (`build-<engine>.json`, `qc-report.json`, `runtime-receipt.md`, `human-review.json` when completed). No receipt = task not done.

## Commit Format

```
feat:
fix:
test:
docs:
refactor:
chore:
research:
```

Always include `Refs #N` or `Closes #N`.
