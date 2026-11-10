# Development Standard

[English](DEVELOPMENT-STANDARD.md) | [简体中文](DEVELOPMENT-STANDARD.zh-CN.md)

> How to work in this repository. Binding for humans and Claude Code.

## Sources of Truth (Priority Order)

```
REAL EXECUTION RECEIPT
> CURRENT CODE
> MACHINE-READABLE LOCK / CONFIG
> CURRENT ADR
> CURRENT-STATE
> RUNBOOK
> RESEARCH
> OLD PLAN
```

When docs conflict with code: code wins. Update docs to match code.

## Issue-driven Development

Non-trivial change requires an Issue before implementation.

Issue types: Bug, Task, Experiment (see `.github/ISSUE_TEMPLATE/`).

## Branch Lifecycle

```
main (canonical)
  -> short-lived issue branch
  -> PR
  -> CI (must pass)
  -> squash merge
  -> branch deleted
```

Branch naming: `feat/<issue>-...`, `fix/<issue>-...`, `test/<issue>-...`, `chore/<issue>-...`, etc.

### Feature-branch CI

A feature branch is checked by a `push` to its own branch, not by merging it
into an authorised parent. `.github/workflows/ci.yml` runs on `feat/**`,
`fix/**`, `chore/**`, `security/**`, `docs/**` and `ci/**`, and can be started
manually with:

```bash
gh workflow run ci.yml --ref <branch>
```

The run is identified by the branch ref in the Actions log. It does not merge
the branch into `main`, does not merge an unauthorised parent into `main`, and
does not replace the PR check. A branch whose workflow predates these triggers
needs one merge of current `main` (or the trigger commit) before it can be
dispatched.

## Commit Rules

Prefix: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`, `research:`

Body must reference issue: `Refs #N` or `Closes #N`.

No mega-commits. One logical change per commit.

## Dependency Policy

Before adding any dependency, answer:
1. Why is stdlib insufficient?
2. Is it runtime or dev-only?
3. Who maintains it?
4. License compatible?
5. Windows support?
6. Can it introduce network/process execution risk?

If stdlib can do it: use stdlib.

## Error Handling

- FAIL is FAIL. Never silently degrade.
- Fallback must appear in receipt with `quality_impact`.
- `production_ready: false` until human approval.

## Logging / Receipt Policy

Every project run produces:
```
projects/<slug>/receipts/
  build-<engine>.json
  qc-report.json
  runtime-receipt.md
  human-review.json (when completed)
```

No receipt = task not done.

## Verification

Use the authoritative risk-based local policy in [TEST-PLAN.md](TEST-PLAN.md). Select checks by affected behavior and risk, not by changed-file count.

- L0 documentation/non-behavioral changes: no business tests; run only relevant docs/link checks and i18n when bilingual mirrors change.
- L1 local low-risk code: static analysis first and ordinarily at most one relevant existing test suite.
- L2 ordinary behavior changes: relevant tests, ordinarily 1–3 targeted commands; add a cross-module contract check only when affected.
- L3 high-risk behavior: all unit/contract/integration/regression checks needed for the risk. Budget does not waive safety verification.
- Run `doctor.py` only for environment/runtime/install/deployment changes; `qc_video.py` only for actual video artifacts or QC behavior; `test_basic.py` only for a relevant script entry/basic behavior.
- `python scripts/dev_check.py` is the full local gate when preparing a PR, not a per-edit requirement. `--quick` only skips repo policy and still runs other gates plus `test_basic.py`; it is not targeted testing.
- Do not rerun unchanged passing checks, blindly retry failures, or expand coverage without evidence. Diagnose failures and rerun only affected checks. Stop when required verification passes and no blocking defect or critical risk remains.
- Report checks not run as not run, never as passed.

PR preparation retains the complete local gate and relevant business regression tests. GitHub CI retains all suites on Ubuntu and Windows and repo-policy checks. Never weaken or bypass CI, branch protection or security gates.

A new `tests/test_*.py` must also be added to `.github/workflows/ci.yml`. Windows-specific tests remain required when Windows path behavior is changed.

## Documentation Update Matrix

| If you change... | Update... |
|---|---|
| runtime behavior | CURRENT-STATE + RUNBOOK |
| architecture | ARCHITECTURE + ADR |
| public contract | contract doc + tests |
| quality criteria | QUALITY-STANDARD + tests |
| provider facts | capability evidence + ADR |

## Security

- No API keys in Git
- No `.verify-tmp/` in Git
- No `docs/ai-provider-selection.md` in Git (gitignored)
- Receipts must redact secrets
- No provider endpoint URLs in public docs unless canonical and sanitized

## Windows Compatibility

This is a Windows-first project.
- Test on Windows (PowerShell) before PR
- UTF-8 encoding for all text files
- FFmpeg paths validated
- Subtitle path escaping handled (Windows colon bug)
- Chinese paths / spaces in paths supported

## External API / Provider Integration Rules

```
CAPABILITY SPIKE -> CONTRACT -> IMPLEMENTATION -> REAL SMOKE TEST -> RECEIPT
```

No fake adapters. `MANUAL_ONLY` is a valid status.
