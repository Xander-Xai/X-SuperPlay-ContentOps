# Upstream Easel Policy

> How X-SuperPlay-ContentOps relates to the Easel upstream.

## Current Pin

| Property | Value |
|---|---|
| Repo | https://github.com/ZJU-REAL/Easel |
| Tag | v0.2.1 |
| Commit | `3fe2d9904c1619281ef57f81d9ee0b7854998399` |
| Release date | 2026-09-24 |
| Lock file | `runtime/easel.lock.json` |
| Provenance | `runtime/easel-runtime.json` |
| Local path | `.runtime/easel/` (gitignored) |
| Acquisition | Release archive (GitHub tarball via `gh api`) |
| Verification | 982/982 blob SHA-1 matched upstream tree |

## Rules

1. **No auto-upgrade.** Upstream upgrades require Founder approval.
2. **No upstream modification.** Extension via ADAPTER pattern only.
3. **No fork.** Fork is last resort, requires ADR.
4. **Upgrade process:**
   - New release detected → CHANGELOG review
   - Diff relevant components
   - Run regression suite
   - Golden projects PASS
   - Founder approval
   - Update lock file

5. **Legacy clone** at `Easel/` (commit `4b9c03c`, NOT v0.2.1) is gitignored and never used as production engine.

## Verification Tool

```powershell
python scripts/verify_easel_runtime.py --resolve-tag
```

Checks all 982 upstream blobs against local files. Tamper test included.

## See Also

- [ADR-001](adr/ADR-001-easel-runtime.md) — Easel runtime decision
- [ADR-006](adr/ADR-006-upstream-upgrade-policy.md) — Upgrade policy
