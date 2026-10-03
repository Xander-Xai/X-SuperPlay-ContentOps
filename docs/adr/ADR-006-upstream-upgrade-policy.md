# ADR-006: Upstream upgrade policy

## Status

ACCEPTED

## Context

Easel upstream continues to iterate. Pinning prevents drift but upgrades must be controlled.

## Decision

- Check for new releases periodically (biweekly or on demand)
- Upgrade process: CHANGELOG review → diff → regression suite → golden projects → Founder approval → update lock
- No `git pull latest`
- No auto-merge of upstream changes
- `scripts/check_easel_upstream.py` (planned) generates delta report only

## Consequences

- Upgrades are deliberate, not accidental
- Regression suite must pass before lock update
- Old pin retained until new pin verified
