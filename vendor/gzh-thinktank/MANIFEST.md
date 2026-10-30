# gzh-thinktank — vendored 公众号 workflow

This directory holds a **verbatim copy of the Future Intelligence WeChat Official
Account workflow**, imported because its own repository is being retired.

## Provenance

| | |
|---|---|
| Upstream repository | `https://github.com/yandexuanxuan/gzh-Future-Intelligence.git` |
| Imported from | `D:\Projects\gzh_x未来智能` |
| Commit | `93645f178418c1e0a03cbb3fc06a7f87ee11f631` (`fix: allow verified draft resubmission`) |
| Git tree object | `7b75e4e840b29a18f5262c0e81e64c080c274c6a` |
| Imported | 2026-10-30 |
| Files / size | 667 / 8 MB |
| Tree digest | `0b96d179a224f0b9668843fd78fcdcefb8f9a83d7918b7d8127fce5d6687919a` |

The digest is SHA-256 over the sorted list of `relative/path\0file-sha256\n` for
every file under the workflow root (`gzh_未来智能/`), with the path relative to that
root. Each file's SHA-256 is taken over its content with CRLF folded to LF, so the
pin is the same on a platform that rewrites line endings on checkout and one that
does not; only content edits change it. `scripts/gzh_pin.py` recomputes it.

The full original repository — including every commit the divergence left off
GitHub — was preserved as a git bundle:

```
D:\Archives\repos\gzh-thinktank\2026-10-30\gzh-thinktank.bundle
sha256 fc6965c076af07d1e6842b06bb11afae760d4315d950545604a041a97e4fb4e7
```

The upstream history **diverged** from GitHub origin (`origin/main` was
`e9303d1`), so cloning upstream does not reproduce this copy.

### The archive is retired

The bundle, the original checkout and its GitHub remote were **deleted on
2026-10-30** (verified: both paths absent, the repository URL returns 404). This
directory is now the only copy, and the following are gone:

- the original's Git history (four commits `bb52de1`, `5860343`, `00f8c98`,
  `93645f1`) — the tree survives, the commits do not;
- the twelve files this repository cannot track (ten golden fixtures, an icon, and
  the npm lockfile);
- `production/`, the account's article artifacts. The in-progress article
  `THK-20260825-002-mcp-tool-governance-v2` was copied to
  `projects/gzh-thinktank/` before retirement: its text and JSON are tracked there,
  its 17 image assets are not (this repository ignores `*.png`).

Nothing needed to *run* the workflow is in that list. `scripts/gzh_pin.py` records
`BUNDLE_RETIRED = True`, so a missing bundle is expected rather than a failure; a
bundle that is present still has to match its digest.

## Rule: do not edit

This tree is vendored, not owned. Fixes belong in the workflow itself; here they
would be lost on the next import. If the workflow changes, import a new pinned
copy and update the digest — the same discipline as the Easel runtime, whose
981/982 state is the cautionary example.

## What was excluded, and why

| Excluded | Size | Why |
|---|---:|---|
| `skills/beautiful-mermaid/node_modules` | 32 MB | regenerable dependency tree (`npm install` inside the skill) |
| `skills/excalidraw-skill-pack/packages/*/.venv` | part of 130 MB | regenerable Python environment |
| `.aws-article/config.yaml` | — | account/publish configuration and credentials; never vendored |
| `production/` | 15 MB | the account's article artifacts, not the workflow |

`node_modules` and `.venv` are restored with the skills' own install steps; the
rest are in the bundle.

**One deliberate deviation:** the workflow's own `.gitignore` is not vendored. It
ignores `.aws-article/`, `outputs/`, `reports/`, `skills/_archive/` and similar —
correct for the original repository, where those were runtime output, but here it
would silently exclude **103 files** from this repository's history. The
import has to be complete or it is not a copy.

One file still cannot be tracked: `skills/beautiful-mermaid/package-lock.json` is
excluded by a rule outside this repository's `.gitignore`. It is regenerable
(`npm install` in that skill) and is present in the bundle.

**Not carried at all:** that lockfile and ten golden-fixture PNGs under
`skills/excalidraw-skill-pack/packages/shared/fixtures/golden/` plus
`skills/obsidian/_icon.png`. This repository's `.gitignore` ignores `*.png`
globally and its policy test refuses a new image negation without a Founder
decision, so those files cannot be committed here. They are all in the bundle. The
tree digest covers exactly what this repository can carry, so a fresh clone
reproduces it.

## Expected validator output

`python scripts/validate_matrix.py` inside `gzh_未来智能/` reports three findings,
and all three are expected here:

| Finding | Cause |
|---|---|
| `manifest allowlist 文件不存在：.aws-article/config.yaml` | deliberately not vendored (credentials) |
| `manifest hash drift：skills/gzh-draft-publisher/SKILL.md` | **pre-existing**: the same drift appears in the original checkout |
| `manifest hash drift：skills/gzh-draft-publisher/scripts/publish.py` | **pre-existing**, same |

The two hash drifts are not caused by this import. They mean the upstream's
`split-manifest.json` was not regenerated after the publisher changed.

## Proven faithful by experiment

`python scripts/test_workflow_gate.py` passes 23 of 28 tests here. The five failures
are the environment-stage tests, which need `.aws-article/config.yaml` — the
account's local publish configuration. That file was **never in the original git
either** (`git ls-files | grep aws-article` → 0; it is gitignored there).

Measured, not assumed: a clean clone of the original bundle was run through the same
suite and produced **the same five failures**. The vendored copy therefore behaves
exactly like a fresh checkout of the original, and the failures are a property of the
original, not of this import.

To use the workflow, supply `.aws-article/config.yaml` locally (slot 1, credentials
outside both trees). It is gitignored here and must stay that way.

## Where articles live

The workflow keeps its workspace **outside** its own root and refuses a hand-made
article directory. Point it at this repository's projects:

```powershell
$env:GZH_ARTIFACT_ROOT = "D:\Projects\X-SuperPlay-ContentOps\projects\gzh-thinktank"
python vendor\gzh-thinktank\gzh_未来智能\scripts\workspace_audit.py --check
```

Then `route_content.py` → `matrix_init.py` create and register the workspace under
that root, exactly as the upstream contract requires.
