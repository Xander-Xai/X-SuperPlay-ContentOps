# AGENTS.md — Project rules for AI agents (Codex / Claude Code)

> This file constrains AI agents working in `X-SuperPlay-ContentOps`.
> For full architecture, PRD, or quality standards, follow the canonical docs.

## North Star

> Real Business Source → Traceable Content → High-quality final.mp4 → Founder willing to publish

Any work must answer: does this help produce a publishable video faster and more reliably?

If not → don't do it now.

## 1. Core Rules (by priority)

1. **Production output > pretty architecture.** A working `final.mp4` beats ten design docs.
2. **Real evidence > generated visuals.** Screenshots, recordings, real data. AI visuals are auxiliary.
3. **Evidence before Claim.** LLM drafts, evidence verifies. Never: LLM says it → therefore true.
4. **No secrets in Git.** API keys, cookies, tokens, `.env` — never committed. `.verify-tmp/` and `docs/ai-provider-selection.md` stay gitignored.
5. **No upstream modification.** Easel is pinned at v0.2.1 / commit `3fe2d99`. See `runtime/easel.lock.json`.
6. **No auto-upgrade.** Upstream upgrades require Founder approval + regression suite.
7. **FAIL is FAIL.** Never silently degrade to pass QC. Fallback marks `production_ready: false`.
8. **Human Approval never bypassed.** Gates stop and emit `NEEDS_HUMAN_REVIEW`.
9. **No direct push to main.** All changes via PR. `main` is unprotected but governance is by convention.
10. **Each change carries verification.** Run `doctor.py` and `qc_video.py` at minimum.

## 2. Extension Policy

Priority when extending Easel:

```
ADAPTER     → wrap external API without modifying upstream
EXTENSION   → add new module in X-SuperPlay-owned space
CUSTOM SKILL → add Easel skill in extensions/ or skills/
UPSTREAM PATCH → modify Easel source (requires patch file + tests + upgrade note)
FORK        → last resort only
```

Current state: no fork. `assemble_easel.py` is an ADAPTER (orchestration workaround).

## 3. Content Truth Boundary

### Allowed

- "Official implements X" (cite README / source)
- "v0.2.1 release shows Y"
- "Doctor output shows A" (with receipt)

### Forbidden

- "I tested X" (unless actually tested this session)
- "Y is stable" (without data)
- Fabricated cases / data / metrics

## 4. Fallback Honesty

| Engine | Role | May report production_ready? |
|---|---|---|
| `easel` | Production candidate | Only with human approval + QC PASS |
| `fallback` | Diagnostic only | **Never** — always `production_ready: false` |
| future MiniMax | Production (when verified) | Only with receipt + quota tracking |

Any degradation must appear in the receipt:

```yaml
requested_provider: ...
actual_provider: ...
fallback_reason: ...
quality_impact: ...
requires_human_review: true
```

## 5. Receipt Culture

Every project run produces receipts:

```
projects/<slug>/receipts/
  build-<engine>.json
  qc-report.json
  qc-report.md
  runtime-receipt.md
  human-review.json (when completed)
```

No receipt = task not done.

## 6. File Discipline

- Don't modify Easel source (`.runtime/easel/`).
- Don't commit `.runtime/`, `Easel/`, `.env`, `.verify-tmp/`, `docs/ai-provider-selection.md`.
- Use helper scripts, not bare `cd .runtime/easel && python ...`.
- Don't copy Easel source code into the repo.

## 7. Canonical Docs Map

| Need | Read |
|---|---|
| What runs today | [docs/CURRENT-STATE.md](docs/CURRENT-STATE.md) |
| System boundaries | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| How to run | [docs/RUNBOOK.md](docs/RUNBOOK.md) |
| What we're building | [docs/PRD.md](docs/PRD.md) |
| Quality gates | [docs/QUALITY-STANDARD.md](docs/QUALITY-STANDARD.md) |
| Easel pin policy | [docs/UPSTREAM-EASEL.md](docs/UPSTREAM-EASEL.md) |
| Decisions | [docs/adr/](docs/adr/) |
| Research | [research/README.md](research/README.md) |
| Audit | [docs/AUDIT-REPORT.md](docs/AUDIT-REPORT.md) |

## 8. MiniMax Boundary

- `billing_mode: subscription`
- `allow_payg: false`
- Capability spike (Issue #4) must complete before any implementation.
- No fake adapters. `MANUAL_ONLY` is a valid status.
- Provider endpoint URLs, pricing, and business strategy stay local-only.

## 9. Commit Discipline

- Message prefix: `feat:` / `fix:` / `docs:` / `chore:` / `test:` / `refactor:`
- Reference Issue numbers: `Refs #N`
- No mega-commits. One logical change per commit.
- Run tests before committing: `python scripts/test_basic.py`
