# Upstream Easel Policy

[English](UPSTREAM-EASEL.md) | [简体中文](UPSTREAM-EASEL.zh-CN.md)

> How X-SuperPlay-ContentOps relates to the Easel upstream.

## Core Principle

```text
Production tracks stable releases only.
Upstream main is monitored for early-warning signals,
not consumed as production runtime.
```

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
| Upstream stable | v0.3.0 (2026-10-12) — **not adopted** (see *v0.3.0 delta* below) |

## Rules

1. **No auto-upgrade.** Upstream upgrades require Founder approval.
2. **No upstream modification.** Extension via ADAPTER pattern only.
3. **No fork.** Fork is last resort, requires ADR.
4. **No main as production.** Upstream main is a compatibility radar, not a deployment source.
5. **Upgrade process:**
   - New release detected → CHANGELOG review
   - Diff relevant components
   - Run regression suite
   - Golden projects PASS
   - Founder approval
   - Update lock file

6. **Legacy clone** at `Easel/` (commit `4b9c03c`, NOT v0.2.1) is gitignored and never used as production engine.

## Easel Upgrade Gate

Only an explicit Upgrade Issue allows:

```text
Acquire new release
    ↓
Verify provenance
    ↓
Run upstream diff analysis
    ↓
Run unit tests
    ↓
Run Windows tests
    ↓
Run 3 golden renders
    ↓
Compare receipts
    ↓
Human Review
    ↓
Founder approval
    ↓
Update lock
```

Any step FAIL → keep old pin.

## Easel Compatibility Matrix

| Easel Area | ContentOps Dependency | Regression Required |
|---|---|---|
| TTS | High | voice smoke |
| assemble/video | Critical | 3 golden renders |
| Windows subprocess | High | Windows CI/local |
| model registry | Medium | provider contract |
| doctor | Medium | doctor regression |
| gateway | Low/Medium currently | gateway tests |
| publishing | Low currently | later M5/M6 |
| Web Workbench | Low currently | no upgrade blocker |

## Upstream Delta Ledger

| Upstream | ContentOps | Decision |
|---|---|---|
| Easel v0.2.1 | pinned | production |
| Easel v0.3.0 | available, not adopted | **HIGH** risk delta — see below (ADR-012 D3) |
| Easel main | monitored | no production consumption |
| next release | pending | compatibility gate |

Dynamic SHAs are not duplicated here. Real-time values come from `runtime/easel.lock.json` and the watch script output.

## v0.3.0 delta (measured 2026-11-01)

| Property | Value |
|---|---|
| Released | 2026-10-12 |
| Distance from the pin | 158 commits, 300 changed files |
| Breaking for this repository | **yes** |
| Decision | not adopted (ADR-012 D3) |

Three facts decide it:

1. **Skill paths moved.** Every skill moved from `skills/openclaw/` to
   `skills/builtin/`, and `auto-short-video/scripts/assemble.py` changed. The
   skill router's first catalog root is `.runtime/easel/skills/openclaw`, so the
   catalog root changes with the version.
2. **The tag was force-replaced.** Upstream published v0.3.0, then replaced it
   while keeping the version number. A tag that can be replaced is not a pin.
   Any future adoption must record a **content digest**, not only a tag.
3. **The scope is large.** The release adds a multi-agent execution engine
   (OpenClaw / Codex / OpenCode / ACP / chat-only) and changes install,
   login and artifact handling — a wider blast radius than a patch release.

Adoption, when it happens, runs the full upgrade gate above plus a digest
pinned release archive.

## Upstream Watch

```bash
python scripts/check_easel_upstream.py
```

Checks pinned release vs latest release vs main. Classifies impact areas. Never modifies the lock file.

### Impact Levels

| Level | Description |
|---|---|
| NONE | docs-only, unrelated platform skill |
| LOW | minor internal refactor, no watched interface change |
| MEDIUM | Windows behavior, TTS, assemble, doctor, gateway, provider registry, video pipeline |
| HIGH | new stable release, security fix, breaking runtime interface, video assembly behavior change, provider contract change |

### Noise Control

Daily watch runs, but only NEW STABLE RELEASE or MEDIUM/HIGH watched-path changes produce issue updates. No per-commit issue spam.

### Watcher Prohibitions

The watcher never:
- edits `runtime/easel.lock.json`
- downloads or replaces production Easel
- opens automatic upgrade PRs
- merges anything
- modifies ContentOps code

The watcher only: DETECT → CLASSIFY → REPORT.

## Verification Tool

```powershell
python scripts/verify_easel_runtime.py --resolve-tag
```

Checks all 982 upstream blobs against local files. Tamper test included.

## See Also

- [ADR-001](adr/ADR-001-easel-runtime.md) — Easel runtime decision
- [ADR-006](adr/ADR-006-upstream-upgrade-policy.md) — Upgrade policy
