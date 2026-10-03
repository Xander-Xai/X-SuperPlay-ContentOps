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
| MiniMax capability audit | VERIFIED (speech + image), H3 BLOCKED | `providers/minimax-mplan-explore-capability.md` |
| MiniMax sanitized receipt | CURRENT | `providers/receipts/minimax-mplan-explore-capability-2026-10-04.sanitized.json` |

## Archived

| Doc | Archived Location | Reason |
|---|---|---|
| EXP-WS008-EASEL-001 README | `archive/01-experiments-canonicalization/exp-ws008-easel-001-readme.md` | Contains 0.1.1, "Queued" — superseded by actual runtime (v0.2.1) |
| EXP-WS008-EASEL-001 scorecard | `archive/01-experiments-canonicalization/exp-ws008-easel-001-scorecard.md` | Blank scorecard for superseded experiment |
| V1 runtime README | `archive/02-runtime-v1/v1-runtime-readme.md` | Contains 0.1.1, wrong path (runtime/Easel/) — superseded by canonical docs |
| V1 short-video template | `archive/02-runtime-v1/short-video-v1-template.md` | Duplicate of `templates/short-video-v1.md` |
| Easel deployment decision | `archive/easel-deployment-decision/easel-deployment-decision-20261002.md` | Says "git clone" — actual was release archive; web workbench unverified |
| V1 execution methodology | `archive/v1-execution-methodology/v1-execution-methodology.md` | Philosophy absorbed into PRD + AGENTS.md |
| V1 runbook | `archive/v1-execution-methodology/v1-runbook-replaced.md` | Replaced by `docs/RUNBOOK.md` (derived from actual code) |
| OPC-Easel research | `archive/opc-easel-research/opc-easel-contentops-research.md` | Historical research, not current architecture |

All archived files carry a `status: superseded` YAML header.
