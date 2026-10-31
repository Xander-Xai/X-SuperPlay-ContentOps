# ADR-008: HyperFrames `media-use` is integrated as a pinned adapter, not a fork

Status: Accepted — external execution only through a verified runtime lock
Date: 2026-10-31

> **Trust model:** an installed CLI is an unknown program until a reviewed lock
> names every byte it may execute. The adapter re-hashes that lock before each
> spawn and refuses when the tree is missing, drifted or version-mismatched.
> Committing the lock is not enough and is not what makes this safe.
Issue: #57
Related: ADR-004 (cross-repo source contract), ADR-006 (upstream upgrade policy),
`docs/MEDIA-PROVIDER-CONTRACT.md`

## Context

`media-use` is a skill shipped by the upstream HyperFrames repository
(`heygen-com/hyperframes`, Apache-2.0). It resolves background music, sound
effects, stock images, icons and logos, and keeps a per-project inventory at
`.media/manifest.jsonl`. It is useful to ContentOps because it can locate
licensed material without inventing a generator, but it is not a MediaProvider:
it has no receipt schema, no evidence boundary, no human-review state and no
license field on its records.

Three approaches were possible:

1. copy `skills/media-use` into this repository;
2. rebuild its catalog/resolution logic in Python;
3. keep it as an external, version-pinned dependency and write a thin adapter.

## Decision

Option 3. `src/contentops/media/media_use_adapter.py` wraps the locked CLI entry
and is the only place that knows the skill exists. The upstream source is **not**
copied and **not** modified. `scripts/media_use_adapter.py` is the operator CLI.

Skill source reference (reviewed, not executed):

| Field | Value |
|---|---|
| Repository | `https://github.com/heygen-com/hyperframes` |
| Upstream commit | `5e4f5aefb58a9996ea5920f008184e9789346871` |
| Last `skills/media-use` commit at audit | `f2358315e59731833334c5d881a7fb5543c22a97` |
| License | Apache-2.0 |
| Local skill directory | `~/.agents/skills/media-use` (override: `MEDIA_USE_SKILL_DIR`) |

## Two provenance lines, deliberately separate

- **Skill source reference:** the Git commit above describes the skill as it was
  read and reviewed. It is not what executes.
- **Execution baseline:** the published package `hyperframes@0.8.222`,
  integrity `sha512-kTPOStlNXvbuZIsT9eHr8FlA9PK26cT/fXXZkdAZKiUIe3RElIolum+/FS/25YHBilobyPGGb78rRy+pDT73Iw==`.
  Its `gitHead` is `e28dbe4ce48842cfbeab34a1bf0090fd9e428b6d`, 15 commits behind
  the reference; the two are **not** the same code and are never described as
  such. The package was chosen because it is the artifact that can be pinned,
  mirrored and hashed end to end.

## Runtime trust is two layers

A machine lock on its own is writer-controlled: whoever can install a tree can
also regenerate the hashes that describe it. Trust therefore needs a second,
version-controlled layer that the operator does not produce at install time.

| Layer | Committed? | Records | Who sets it |
|---|---|---|---|
| **Approved baseline** — `runtime/media-use-runtime-baseline.json` | yes | package, version, published integrity, dependency-lock digest, package-tree digest, entry, verb prefix, execution policy, approval record | a human, after reviewing evidence |
| **Runtime lock** — `contentops.media-use-runtime-lock/v2`, named by `CONTENTOPS_MEDIA_USE_RUNTIME_LOCK` | no | absolute root, node binary and its SHA-256, entry, per-file SHA-256 for the whole tree, `baseline_sha256` | `scripts/media_use_runtime.py lock` |

A lock is trusted only when it names the approved baseline by digest *and*
every byte matches. Regenerating a lock never approves a release; approving
never installs one. The baseline ships with `approval.status: "pending"` until
a person runs `scripts/media_use_runtime.py approve --approved-by <name>`, so a
fresh checkout refuses external execution by construction.

The baseline also pins `package_tree_sha256`, a digest over the package's own
678 files in sorted `path\\0sha256` form. Without it, editing a runtime file and
its hash in the lock leaves both self-consistent; with it, that pair no longer
matches what was approved.

Verification states are distinct because they prompt different actions:

| State | Meaning |
|---|---|
| `TRUSTED_RUNTIME` | both layers agree and every listed byte matches; execution allowed |
| `RUNTIME_MISSING` | lock or tree absent — install it |
| `INTEGRITY_MISMATCH` | a file changed, disappeared or was added after review — do not run, investigate |
| `VERSION_MISMATCH` | installed version differs from the approved one |
| `BASELINE_MISMATCH` | no approved baseline, or the lock was not produced from it, or the package tree differs |
| `DEPENDENCY_UNVERIFIED` | no lock, no pinned node, or an unsupported lock schema; execution refused |

Paths inside a lock are data from an untrusted source: absolute paths, `..`
segments and symlinks that resolve outside the root are refused, and any
regular file present in the tree but absent from the lock is an unlisted
executable. A node binary is part of the trust decision — falling back to
whatever `node` is on `PATH` would let the host decide what runs.

The lock is machine-specific and is **not** committed: it names absolute paths
and a node build for one host. What is committed is the baseline, the schema,
the verifier, the install/lock/approve entry point and their tests. The hash
pass (about 0.6 s for 5 407 files on a local disk) runs before every spawn, so a
stale `available=true` cannot authorise a tree that changed afterwards.

## Installing a runtime

`scripts/media_use_runtime.py` has four separate commands:

| Command | Network | Effect |
|---|---|---|
| `approve --approved-by NAME` | no | flips the baseline's approval record; refuses an unnamed approver or a missing tree digest |
| `install` | yes | refuses an unapproved baseline, copies the committed `runtime/media-use-package-lock.json` (127 entries, digest `2225ab6d…`) and runs `npm ci --ignore-scripts`; fails if the installed version, lockfile digest or SRI differ from the approved values |
| `lock` | no | hashes the tree into a v2 lock and verifies it against the baseline |
| `selfcheck` | no | runs `adopt`/`candidates`/`resolve` through the production adapter against the trusted lock |

Lifecycle scripts are disabled at install and audited afterwards; runtime
network and paid providers stay off (`policy` in the baseline).

## Verified by execution, 2026-10-31

**Linux** — isolated WSL, network namespace with no egress (`unshare -Urn`,
outbound probe refused), no credentials, no provider, no `npx`. A temporary
approved copy of the baseline was used so the committed one stays `pending`:

| Step | Result |
|---|---|
| `approve` → `lock` → `verify`, 5 397 files | `TRUSTED_RUNTIME`, package-tree digest reproduced |
| `selfcheck` inside the namespace | `adopt` 1 asset, candidate `image_001`, bundled SFX `sfx_001` |
| runtime file edited after review | `INTEGRITY_MISMATCH`, refused before any process start |
| file hash and lock hash edited together | `BASELINE_MISMATCH` (package-tree digest differs) |

**Windows 11** — Node v22.23.4 win-x64 from nodejs.org, zip SHA-256 equal to the
official `SHASUMS256.txt` entry:

| Step | Result |
|---|---|
| `install` (`npm ci` from the committed lock) | `INSTALLED`, lockfile digest `2225ab6d…`, SRI matched |
| `lock` | `TRUSTED_RUNTIME`; package-tree digest `be8e24df…`, identical to the Linux pass |
| real CLI through the adapter | `adopt` 1 asset, `image_001` candidate, bundled `sfx_001`, no network authorization |
| isolated demo with real Easel compose | manifest 7 assets, storyboard 2 placements, `compose` OK (300 437-byte 1080×1920 sample), QC `WARN`, `production_ready:false` |

The Windows run is local-only at the CLI; the namespace-level egress proof is
the Linux run. Neither proves a provider call or a production pipeline.

The import receipt records `upstream_provenance: UNVERIFIED` and no commit ID:
a verified runtime proves *what executed*, never *where an asset came from*.

## Why not a fork or a reimplementation

- A copy would drift silently from upstream and would put Apache-2.0 code into a
  tree whose own policy is "adapter first"; the repo already forbids copying
  upstream Easel source, and the same argument applies here.
- A Python reimplementation would have to duplicate catalog lookup, provider
  routing and the bundled SFX library, none of which ContentOps owns, and would
  still need the same provenance fields.
- A commit identifier and launcher hash alone do not establish which CLI and
  dependencies executed. That gap is closed by the runtime lock above, not by
  the commit constant.

## Contract mapping

`media-use` records have **no license field**. The adapter therefore cannot
derive a licence; `import_record` requires one explicitly, and refuses an empty
value (`LICENSE_MISSING`). This is deliberate: a missing licence is a human
decision, not a default to fill in.

| media-use type | MediaModality | AssetKind |
|---|---|---|
| image, icon, logo, brand | IMAGE | `LICENSED_EXTERNAL` |
| bgm, sfx | AUDIO | `None` (audio is not a visual kind) |
| voice, video, grade, lut, recipe | — | refused as `UNSUPPORTED_TYPE` in v1 |

`AssetKind.LICENSED_EXTERNAL` was added for this integration. It is neither a
capture nor a model generation, so it is absent from `EVIDENCE_CAPABLE` and from
`GENERATED`. Registering a stock photo as `REAL` would make it evidence; calling
it `GENERATED_IMAGE` would claim a model produced bytes it did not.

Every import is written as a `contentops.media-import/v1` sidecar and enters the
single `MediaManifest`. The adapter never writes a second asset list; it reads
media-use's own `.media/manifest.jsonl` only to look up a record by id.

## Safety defaults

- network, paid providers, cross-project reuse and forced providers are **off**
  unless the caller passes the matching authorization;
- the child process gets a project-local `HOME`/`USERPROFILE` at
  `<project>/.media/.home`, so the shared `~/.media` cache cannot leak another
  project's assets in;
- the child environment is allow-listed; provider keys, cookies and agent tokens
  are not inherited;
- arguments are passed as an array through `scripts/process_utils.hidden_run`;
  no shell string is constructed and no timeout is unbounded;
- generated resolutions are `GENERATED_NOT_IMPORTABLE`, because a generated
  asset is not licensed external material.

## Consequences

- Upgrading media-use is an explicit change: install the new version, regenerate
  the runtime lock, re-run `tests/test_media_use_adapter.py`, and repeat the
  isolated execution check. The adapter does not auto-update.
- Execution is blocked until a lock exists for the host. Without
  `CONTENTOPS_MEDIA_USE_RUNTIME_LOCK` every external call reports
  `DEPENDENCY_UNVERIFIED`; local project imports keep working.
- Network and paid paths stay blocked: the released resolver can fall back from
  retrieval to generation, and no enforceable spending ceiling has been verified.
- Images and icons currently require a network provider; the only offline
  third-party source is the bundled SFX library. The demo records the image
  refusal rather than fabricating a download.
