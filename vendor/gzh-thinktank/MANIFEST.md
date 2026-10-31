# gzh-thinktank — vendored 公众号 workflow

This directory holds a **verbatim copy of the Future Intelligence WeChat Official
Account workflow**, imported from a checkout whose history diverged from its
private remote.

## Provenance

| | |
|---|---|
| Upstream repository | `https://github.com/Xander-Xai/gzh-Future-Intelligence` (**private, alive**) |
| Remote main | `e9303d18066a4232838b9dafff6827f6b4e8adf1` — `fix: allow verified draft resubmission` |
| Remote tree | `7b75e4e840b29a18f5262c0e81e64c080c274c6a` |
| Imported from | `D:\Projects\gzh_x未来智能` (local checkout now absent) |
| Imported commit | `93645f178418c1e0a03cbb3fc06a7f87ee11f631` (not present on the remote) |
| Imported tree | `7b75e4e840b29a18f5262c0e81e64c080c274c6a` — same full tree object as remote main; the vendored copy is a filtered subset |
| Imported | 2026-10-30 |
| Files / size | 667 / 8 MB |
| Tree digest | `0b96d179a224f0b9668843fd78fcdcefb8f9a83d7918b7d8127fce5d6687919a` |

The digest is SHA-256 over the sorted list of `relative/path\0file-sha256\n` for
every file under the workflow root (`gzh_未来智能/`), with the path relative to that
root and sorted by the relative POSIX path string. Each file\'s SHA-256 is taken
over its content with CRLF folded to LF, so the pin is the same on a platform that
rewrites line endings on checkout and one that does not. `scripts/gzh_pin.py`
recomputes it.

### Provenance correction — 2026-10-31

An earlier version of this file said the GitHub remote had been deleted and that
its URL returned 404. **That was wrong.** Verified against the live API:

- `Xander-Xai/gzh-Future-Intelligence` exists, is **private**, and is **not archived**.
- Its `main` is `e9303d1`, tree `7b75e4e8`, with five commits
  (`bb52de1`, `5860343`, `96bfe41`, `901aeee`, `e9303d1`).
- The imported commit `93645f1` is **not** on that remote, but its **full tree object**
  is byte-identical to remote `main` (`7b75e4e8`). The commit identity was lost; the
  content was not. The vendored root is a filtered copy: its Git subtree hash in
  ContentOps is `4b284a4c…`, not `7b75e4e8`, because this repository excludes files
  and normalizes line endings. The SHA-256 content pin, not a Git tree hash,
  identifies the vendored subset.
- The local checkout `D:\Projects\gzh_x未来智能` and the local bundle
  `D:\Archives\repos\gzh-thinktank\2026-10-30\gzh-thinktank.bundle` are both
  absent. The private remote is the recoverable source; this tree is the public copy.

Do not delete the remote to make this document's old claim true. The remote is the
only recoverable Git history for the workflow.

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
rest remain in the private remote (and in any surviving local bundle).

**One deliberate deviation:** the workflow's own `.gitignore` is not vendored. It
ignores `.aws-article/`, `outputs/`, `reports/`, `skills/_archive/` and similar —
correct for the original repository, where those were runtime output, but here it
would silently exclude **103 files** from this repository's history. The
import has to be complete or it is not a copy.

One file still cannot be tracked: `skills/beautiful-mermaid/package-lock.json` is
excluded by a rule outside this repository's `.gitignore`. It is regenerable
(`npm install` in that skill) and remains recoverable from the private remote.

**Not carried at all:** that lockfile and ten golden-fixture PNGs under
`skills/excalidraw-skill-pack/packages/shared/fixtures/golden/` plus
`skills/obsidian/_icon.png`. This repository's `.gitignore` ignores `*.png`
globally and its policy test refuses a new image negation without a Founder
decision, so those files cannot be committed here. They remain in the private
remote; the local bundle is absent. The tree digest covers exactly what this
repository can carry, so a fresh clone reproduces it.

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

Measured, not assumed: a clean clone of the original tree (from the bundle, before
it was removed) was run through the same suite and produced **the same five
failures**. The vendored copy therefore behaves exactly like a fresh checkout of
the original, and the failures are a property of the original, not of this import.

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
