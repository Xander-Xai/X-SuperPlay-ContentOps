# File Placement Policy

[English](FILE-PLACEMENT-POLICY.md) | [简体中文](FILE-PLACEMENT-POLICY.zh-CN.md)

> Where each type of file belongs. Binding for humans and Claude Code.

## ROOT Directory

Allowed long-lived entry points only:

```
README.md           # required entry point
AGENTS.md          # AI agent rules
CLAUDE.md          # Claude Code instructions
CONTRIBUTING.md    # contribution guide
SECURITY.md        # security policy
CODE_OF_CONDUCT.md # (if applicable)
LICENSE             # only after Founder decision
.env.example        # template for local config
.gitignore          # Git ignore rules
.gitattributes      # line ending rules
.editorconfig       # editor rules
```

Forbidden in ROOT:
```
analysis.md notes.md report-final.md final-v2.md
claude-output.md tmp.md TODO.md CHANGELOG-old.md
*.tmp *.log *.bak credentials.txt secrets.md
```

## docs/

Canonical product documentation only:

```
docs/
├── INDEX.md              # navigation hub
├── CURRENT-STATE.md     # what runs today (verified facts)
├── ARCHITECTURE.md       # system boundaries
├── PRD.md               # product requirements
├── RUNBOOK.md          # executable commands
├── DEVELOPMENT-STANDARD.md # development rules
├── QUALITY-STANDARD.md  # quality gates
├── TEST-PLAN.md         # test strategy
├── UPSTREAM-EASEL.md   # Easel pin policy
├── SOURCE-ARTIFACT-CONTRACT.md
├── MEDIA-PROVIDER-CONTRACT.md
├── CROSS-REPO-INTEGRATION.md
├── adr/                # architecture decision records
│   └── ADR-*.md
└── AUDIT-REPORT.md     # repository audit (historical)
```

Every file in `docs/` must appear in `docs/INDEX.md`.

## research/

Non-canonical investigation, spikes, experiments. Each file must have:

```yaml
status: experiment
canonical: false
issue: "#N"
date: YYYY-MM-DD
```

## research/archive/

Superseded historical material only. Each file must have:

```yaml
status: superseded
superseded_by: <path>
historical_context: <brief note>
```

## scripts/

CLI tools, ops scripts, verification, build orchestration.

```
scripts/
├── run_v1.py           # production pipeline
├── qc_video.py         # automated QC
├── doctor.py            # environment checker
├── resolve_easel.py    # runtime resolver
├── verify_easel_runtime.py
├── assemble_easel.py   # upstream orchestration
├── process_utils.py    # Windows no-popup subprocess helper
├── check_easel_upstream.py # Easel upstream watch
├── check_i18n.py       # bilingual consistency checker
├── check_docs.py       # doc consistency
├── check_repo_policy.py # file placement + security
├── dev_check.py        # unified developer gate
├── new_project.py
├── bootstrap.ps1 / bootstrap.sh
└── test_basic.py       # current test suite
```

Core business logic should migrate to `src/` over time. Keep `scripts/` for ops.

## runtime/

Machine-readable pins and provenance only:

```
runtime/
├── easel.lock.json       # canonical Easel pin
└── easel-runtime.json    # provenance record
```

Forbidden in `runtime/`:
- secrets, credentials, tokens
- local config backups
- generated logs

## projects/

Content run projects and golden samples:

```
projects/
├── .gitkeep
└── <slug>/
    ├── project.yaml
    ├── sources/
    ├── script/
    ├── assets/
    ├── work/           # intermediate renders (gitignored)
    ├── final/          # output MP4s (gitignored)
    └── receipts/
```

Large generated files (MP4, WAV, PNG) follow `.gitignore` artifact policy.

## tests/

Formal test layout (established from M1):

```
tests/
├── unit/
├── regression/
├── integration/
├── contract/
├── e2e/
└── fixtures/
```

## .github/

GitHub governance only:

```
.github/
├── CODEOWNERS
├── PULL_REQUEST_TEMPLATE.md
├── workflows/
│   └── ci.yml
├── ISSUE_TEMPLATE/
│   ├── bug.yml
│   ├── task.yml
│   ├── experiment.yml
│   └── config.yml
└── dependabot.yml     # (if needed)
```

## .runtime/ and /Easel/

Vendored upstream runtime. Gitignored. Never modified.

## Local-only Files (gitignored)

These must never be committed:
- `.env` (secrets)
- `.verify-tmp/` (gateway logs exposing provider details)
- `docs/ai-provider-selection.md` (business strategy)
- `runtime-config-backups/`
- `diagnostics/`
- `outputs/` (generated)
- Any `*.mp4`, `*.wav`, `*.png` in non-source dirs
