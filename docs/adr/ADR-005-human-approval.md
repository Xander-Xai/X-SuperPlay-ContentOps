# ADR-005: Human approval gate

## Status

ACCEPTED

## Context

Automated QC PASS does not equal video quality PASS. Founder must personally approve before publishing.

## Decision

- Automated QC PASS → state becomes `READY_FOR_HUMAN_REVIEW` (not `PRODUCTION_READY`)
- Founder Review with 100-point scorecard (≥80, no hard fails → PRODUCTION_READY)
- Human Approval never bypassed
- `production_ready: false` until human approval recorded in `human-review.json`

## Consequences

- No auto-publishing
- Every video requires Founder time
- This is the correct bottleneck — quality before scale
