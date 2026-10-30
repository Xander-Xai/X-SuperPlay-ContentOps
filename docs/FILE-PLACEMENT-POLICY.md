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

## `src/`

Core business logic. This is where provider code, billing gates and
quality gates live, as opposed to `scripts/` which stays ops-only.

```
src/
└── contentops/
    └── media/
        ├── contract.py         # provider-generic MediaProvider contract
        ├── billing_guard.py    # fail-closed billing gate
        ├── lexicon.py          # PronunciationLexicon
        ├── audio.py            # loudness normalisation + technical QC
        ├── asr_backcheck.py    # ASR as a detector, never an approver
        ├── fingerprint.py      # idempotency fingerprint
        ├── minimax_speech.py   # MiniMax M Plan speech provider
        └── test_duration_policy.py  # test-only video duration rule
```

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

## config/

Machine-readable configuration the pipeline reads. Declarative only — no
executable code, no generated output.

```
config/
├── accounts/
│   ├── x-superplay-1024.json                 # account DNA
│   ├── x-superplay-future-intelligence.json  # account DNA
│   └── prompts/
│       └── *.prompt.md                       # one-click account prompt
└── optimization/
    ├── policy.json
    ├── signals.json
    └── *.json
```

- One account owns one file under `config/accounts/`. The DNA is the single
  source for palette, composition, caption style, cover rules, narrative
  template and the one-click prompt path.
- A prompt file is pure text: it is pasted into a chat, so it carries no
  front matter and no commentary.
- `scripts/check_account_dna.py` fails the DNA when it drifts from the brand
  base or from its own prompt.

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

### Text-track projects (`projects/x-growth-en/`)

An X project has no `sources/`, `script/`, `work/` or `final/`: there is no film.
It is placed like any other project, with a text-shaped layout:

```
projects/x-growth-en/
├── project.yaml          # account_slug, platforms: [x], language: en, gate: scripts/x_post.py
├── posts/                # <content_id>.json — one contentops.x-post/v1 record per post
├── templates/            # posts.csv, x-metric-snapshots.csv, x-account-snapshots.csv
├── assets/
│   ├── cards/            # <id>.html is tracked; the rendered <id>.png is gitignored
│   └── imported/         # text that came from the retired source repository (see below)
└── receipts/             # x-check-*.json, x-package-*.json, x-publish-*.json, x-tables-*.json
```

- One post is one file in `posts/`. The file is the record; `templates/posts.csv` is the
  row-shaped mirror that `--mark-published` upserts and `--verify-log` cross-checks.
- The card's HTML is the artifact. The PNG is a render, so it is generated and
  gitignored — re-render it rather than committing it.
- `project.yaml` must not carry `quality_gate: enforced`: that key opts a project into
  the video script gate (SQ01–SQ07), which does not describe an X post. The X gate is
  `scripts/x_post.py`, named in `gate:`.
- The workflow itself lives at `vendor/x-growth-os/` and is never edited.
- `assets/imported/` holds the text that came from the retired source repository: the
  two drafts that existed only on its unmerged branches, their SVG and their experiment
  script. It is tracked, because the remote they came from no longer exists and the
  record's `provenance` points into it. Nothing else may go there: it is an archive of
  one dead repository, not a general import drawer.

The cold copy of that repository is not in this tree at all. It is a verified git
bundle under `D:\Archives\repos\x-growth-os\2026-10-30\`, with the refs, the commits
and the digest recorded in the `INDEX.md` beside it.

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

## vendor/

Committed code from another repository that must survive its own upstream.

```
vendor/
└── gzh-thinktank/          # 公众号 workflow, imported verbatim
    ├── MANIFEST.md         # provenance, exclusions, expected validator output
    └── gzh_未来智能/        # never edited
```

- `vendor/` is for code whose upstream is being retired, so it is **committed** —
  unlike `.runtime/`, which is gitignored because it can be re-acquired.
- The tree is never edited. A change means a new import with a new digest.
- Every vendored tree carries a `MANIFEST.md`: source repository and commit, tree
  digest, what was excluded and why, and the expected output of its own validator.
- Regenerable dependencies (`node_modules`, `.venv`) and anything credential-bearing
  are never vendored.
- `scripts/gzh_pin.py` recomputes the digest. A mismatch is a failure, not a
  warning.

## Local-only Files (gitignored)

These must never be committed:
- `.env` (secrets)
- `.verify-tmp/` (gateway logs exposing provider details)
- `docs/ai-provider-selection.md` (business strategy)
- `runtime-config-backups/`
- `diagnostics/`
- `outputs/` (generated)
- Any `*.mp4`, `*.wav`, `*.png` in non-source dirs
