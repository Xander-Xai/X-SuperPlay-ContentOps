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

## Testing Requirements

- `python scripts/dev_check.py` before every PR
- `python scripts/test_basic.py` — current test suite (9 tests)
- `python scripts/check_docs.py` — doc consistency
- `python scripts/check_repo_policy.py` — file placement + security
- Windows-specific tests for path handling

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
