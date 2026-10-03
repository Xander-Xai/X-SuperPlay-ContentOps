# CLAUDE.md — Claude Code Project Instructions

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

## Never

- Do not work directly on `main`
- Do not create random root files
- Do not invent provider capabilities without a capability spike
- Do not modify `.runtime/easel/`
- Do not commit local/private provider research (`docs/ai-provider-selection.md`, `.verify-tmp/`, etc.)
- Do not add a dependency without answering: why is stdlib insufficient?
- Do not skip tests
- Do not mark human review as approved automatically
- Do not create files outside of their canonical directory (see `docs/FILE-PLACEMENT-POLICY.md`)

## Before Creating a File

Answer these first:
1. What owns this information?
2. What directory does policy assign it to?
3. Is it canonical / research / generated / runtime / test?
4. Does an existing file already own this fact?

If you do not know: **do not create the file**. Read `docs/FILE-PLACEMENT-POLICY.md` first.

## Before Any Commit

Run the unified developer gate:

```bash
python scripts/dev_check.py
```

This runs: repo policy check + docs check + basic tests + whitespace check.

## Branch Strategy

- `main` — canonical default branch, never pushed to directly
- Short-lived issue-scoped branches: `feat/<issue>-...`, `fix/<issue>-...`, `test/<issue>-...`, `docs/<issue>-...`, `chore/<issue>-...`, `refactor/<issue>-...`
- All changes go through PR → squash merge → branch deleted

## Extension Priority (Easel)

```
ADAPTER > EXTENSION > CUSTOM SKILL > UPSTREAM PATCH > FORK
```

Fork is last resort. No upstream modification without patch + tests + ADR.

## MiniMax Boundary

- `billing_mode: subscription`
- `allow_payg: false`
- Capability spike required before any implementation
- `MANUAL_ONLY` is a valid, honest status

## Receipt Culture

Every run produces receipts. No receipt = task not done.

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
