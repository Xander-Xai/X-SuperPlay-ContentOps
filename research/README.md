# Research

Research materials for X-SuperPlay-ContentOps. Research is detailed exploration; active rules live in canonical docs.

## Structure

```
research/
├── README.md          ← this file
├── archive/           ← superseded planning docs (historical, not current truth)
└── providers/         ← provider capability audits (when completed)
```

## Archive Convention

Files moved to `research/archive/` carry this header:

```yaml
status: superseded
superseded_by: <path or doc name>
historical_context: <brief note>
```

Archived docs are historical evidence, not current design. Never treat them as active truth.

## Canonical Fact Priority

When documents conflict:

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

## Current Research

| Area | Status | Location |
|---|---|---|
| MiniMax capability audit | NOT_YET_VERIFIED | (stub to be created in M2.0, Issue #4) |

## Archived

| Doc | Archived From | Reason |
|---|---|---|
| Easel experiment proposal | `01-Experiments/EXP-WS008-EASEL-001/` | Contains 0.1.1, "Queued" — superseded by actual runtime |
| V1 runtime README | `02-Runtime/v1/README.md` | Contains 0.1.1, wrong path — superseded by canonical docs |
| Easel deployment decision | `docs/EASEL-DEPLOYMENT-DECISION.md` | Says "git clone" — actual was release archive |
| V1 execution methodology | `docs/V1-EXECUTION-METHODOLOGY.md` | Absorbed into PRD + AGENTS.md |
| V1 runbook | `docs/V1-RUNBOOK.md` | Replaced by `docs/RUNBOOK.md` |
| OPC-Easel research | `research/OPC-Easel-ContentOps-...md` | Historical research, not current architecture |
