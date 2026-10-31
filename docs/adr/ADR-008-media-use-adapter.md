# ADR-008: HyperFrames `media-use` is integrated as a pinned adapter, not a fork

Status: Under review — trusted execution is blocked
Date: 2026-10-31

> **Security correction:** the commit IDs below are target provenance, not
> verified runtime identity. The launcher delegates to an external CLI and its
> dependencies. Hashing the launcher alone does not verify that execution chain.
> The adapter currently blocks external execution pending a complete, reviewed
> runtime lock and real offline test. The historical decision below is not proof
> that this verification exists.
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

Option 3. `src/contentops/media/media_use_adapter.py` wraps the pinned
`resolve.mjs` and is the only place that knows the skill exists. The upstream
source is **not** copied and **not** modified. `scripts/media_use_adapter.py`
is the operator CLI.

Target provenance, not verified execution provenance:

| Field | Value |
|---|---|
| Repository | `https://github.com/heygen-com/hyperframes` |
| Upstream commit | `5e4f5aefb58a9996ea5920f008184e9789346871` |
| Last `skills/media-use` commit at audit | `f2358315e59731833334c5d881a7fb5543c22a97` |
| License | Apache-2.0 |
| Local skill directory | `~/.agents/skills/media-use` (override: `MEDIA_USE_SKILL_DIR`) |

## Candidate runtimes — not yet approved

- **npm `hyperframes@0.8.222`:** the registry advertises
  `sha512-kTPOStlNXvbuZIsT9eHr8FlA9PK26cT/fXXZkdAZKiUIe3RElIolum+/FS/25YHBilobyPGGb78rRy+pDT73Iw==`;
  the downloaded tarball was checked against that integrity value. Its
  `gitHead` is `e28dbe4ce48842cfbeab34a1bf0090fd9e428b6d`, not the target
  commit. The target is 15 commits ahead and includes media-use changes. The
  tarball does not bundle the entire npm dependency tree or its lockfile.
- **Build the target source:** the pinned checkout uses a Bun workspace and CLI
  build steps that require other workspace packages and generated assets. A
  verified full dependency cache and reproducible clean build have not been
  established.

Neither candidate has passed an isolated real-CLI execution or complete
transitive integrity verification. Selection remains open; do not execute one
as a trusted ContentOps runtime based on these observations.

## Why not a fork or a reimplementation

- A copy would drift silently from upstream and would put Apache-2.0 code into a
  tree whose own policy is "adapter first"; the repo already forbids copying
  upstream Easel source, and the same argument applies here.
- A Python reimplementation would have to duplicate catalog lookup, provider
  routing and the bundled SFX library, none of which ContentOps owns, and would
  still need the same provenance fields.
- A commit identifier and launcher hash alone do not establish which CLI and
  dependencies executed. The full execution chain remains to be independently
  locked and verified before this option can be declared operational.

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

- Upgrading media-use is an explicit change: bump the three constants, re-run
  `tests/test_media_use_adapter.py`, and record the new hashes. The adapter does
  not auto-update.
- The integration requires Node ≥ 22 but remains blocked even when Node and the
  skill are present: the complete runtime has not been verified.
- Images and icons currently require a network provider; the only offline
  third-party source is the bundled SFX library. The demo records the image
  refusal rather than fabricating a download.
