# Contributing to X-SuperPlay-ContentOps

[English](CONTRIBUTING.md) | [简体中文](CONTRIBUTING.zh-CN.md)

## Development Workflow

```
Issue
  -> Branch (issue-scoped)
  -> Implementation
  -> Local Validation (python scripts/dev_check.py)
  -> PR
  -> CI
  -> Review
  -> Squash Merge
  -> Branch Delete
```

## Branch Naming

Allowed:

```
feat/<issue>-<short-description>
fix/<issue>-<short-description>
test/<issue>-<description>
docs/<issue>-<description>
chore/<issue>-<description>
refactor/<issue>-<description>
research/<issue>-<description>
```

Forbidden: `tmp`, `new`, `test2`, `final`, `final2`, `claude-work`, etc.

## Commit Format

```
feat:     new feature
fix:      bug fix
test:     test addition or update
docs:     documentation change
refactor: code restructure without behavior change
chore:    build/tooling/dependency change
research: investigation or experiment
```

Always reference the issue: `Refs #N` or `Closes #N`.

## Before Opening a PR

Run the developer gate:

```bash
python scripts/dev_check.py
```

All checks must pass. No exceptions.

## File Placement

See `docs/FILE-PLACEMENT-POLICY.md` for the authoritative directory layout.

Key rules:
- `docs/` — canonical product docs, architecture, operations, contracts, quality, ADRs
- `research/` — non-canonical investigation, spikes, experiments (marked `canonical: false`)
- `research/archive/` — superseded historical material (marked `status: superseded`)
- `scripts/` — CLI, ops, verification, build orchestration
- `runtime/` — machine-readable pins and provenance only
- Root — only long-lived entry points (README, AGENTS.md, CLAUDE.md, etc.)

## Runtime Reality Rule

> Do not change documentation to match what you wish was true. Change code to match what is true, then update documentation.

Canonical sources:
```
REAL EXECUTION RECEIPT > CODE > LOCK/CONFIG > ADR > CURRENT-STATE > RUNBOOK > RESEARCH > OLD PLAN
```

## Extension Priority (Easel)

```
ADAPTER > EXTENSION > CUSTOM SKILL > UPSTREAM PATCH > FORK
```

No upstream modification without an ADR + patch file + tests.

## Security Rules

- Never commit API keys, tokens, cookies, or credentials
- `docs/ai-provider-selection.md` and `.verify-tmp/` are gitignored — do not force-add them
- Provider endpoint URLs and pricing strategy stay local-only
- All receipts must redact secrets

## Contribution Policy

This is an owner-led project (Xander-Xai). External contributions are welcome but:
- All changes require an Issue before a PR
- All PRs require CI to pass
- No direct pushes to main
- Squash merge only

For security issues, see `SECURITY.md`.
