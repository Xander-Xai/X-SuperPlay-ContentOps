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

### Skill-First Routing (mandatory before any deliverable)

The Easel checkout is a skill library, not just `assemble.py`. Before writing
code, a storyboard, or any ffmpeg/HTML composition for a video, image, card,
audio or copy deliverable:

1. Run `python scripts/skill_route.py --match "<the deliverable>"` and read the
   `SKILL.md` of every matching candidate.
2. State the chosen skill, its input/output contract, and why it owns the task.
3. Use that skill's scripts; do not hand-roll `zoompan`/`xfade`, card HTML or a
   subtitle burn when a skill owns the step.
4. If no skill matches, say so before coding.
5. If the result looks poor, fix the skill's input or design layer first, not
   the compositor.
6. Build receipts carry `skill_route: {name, script, why}`.

A bare `assemble.py` call with raw screenshots is a compositor step, not a
production decision, and is the failure this rule prevents.

### Account-First Routing (mandatory before any build)

Skills do not choose the pipeline; the account does. Before running any producer:

```bash
python scripts/account_route.py projects/<project>
```

It resolves `project.yaml → account_slug → account DNA` and prints the ordered
chain that the account declares, with the creative skill owners from the same DNA.
A declared `pipeline` wins: `X_EDITORIAL` is a text chain with no capture step and
no film. Otherwise the account's `evidence.mode` decides — `EVIDENCE_LED` starts
from capture contracts, `EXPLANATORY` starts from audio-first planning and has no
capture step at all. A mode, or a declared pipeline, with no known chain is refused
(`EVIDENCE_MODE_UNMAPPED` / `PIPELINE_UNMAPPED`) — never substitute one pipeline for
another, and never hand-assemble a chain from the runbook.

The router says which chain to run. It does not certify the result: `cut_qc`
(`account_composition`, `manual_recording_forbidden`, `account_duration`) and a
person still decide whether the film belongs to the account.

### Vendored 公众号 workflow (never edit)

The WeChat Official Account track is vendored at `vendor/gzh-thinktank/`, imported
from a checkout whose history diverged from its own remote and which is being
retired. It is **not** a sixth production system: it is an owned copy of an existing
one, pinned by digest.

- Never edit anything under `vendor/`. A change is a new import with a new digest.
- Its workspace lives at `projects/gzh-thinktank/` via `GZH_ARTIFACT_ROOT`; the
  workflow refuses a hand-made article directory.
- `python scripts/gzh_pin.py` must pass before any 公众号 work.
- Publishing stays inside the vendored workflow (preflight → create draft →
  read-back). It never publishes publicly, and credentials never enter this tree.

### Vendored X workflow (never edit)

The X track is vendored at `vendor/x-growth-os/`, imported verbatim from
`Xander-Xai/X-SuperPlay-X-Growth-OS` (64 files, commit `3154db49`) behind a digest
pin. Same rule as the 公众号 tree: it is an owned copy, not a sixth production system.

- Never edit anything under `vendor/`. A change is a new import with a new digest.
- `python scripts/x_growth_pin.py` must pass before any X work; `--suite` also runs
  the vendored analytics tests.
- The gate is this repository's, not the vendor's: `python scripts/x_post.py --check
  projects/x-growth-en/posts/<id>.json`. A verdict of `DRAFT`, `IMAGE_MISSING`,
  `READY`, `PUBLISHED` or `BLOCKED` is derived from the named issues, never guessed.
- Publication is `MANUAL_ONLY`: `--package` stops at `AWAITING_MANUAL_PUBLISH`, and a
  person posts it and records the real `x.com/<handle>/status/<id>` URL with
  `--mark-published`. `PublishMode.API` raises. There is no X API call here and there
  must be none without a capability spike, an ADR and credentials outside the tree.
- A post that says `published` without a real status URL is a lie the gate refuses.

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
