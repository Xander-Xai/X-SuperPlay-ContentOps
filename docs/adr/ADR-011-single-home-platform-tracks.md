# ADR-011: This repository becomes the single home for every platform track

## Status

ACCEPTED 2026-10-30 — staged by importing the workflow (see "Reversibility").
Supersedes the "keep it external" part of [ADR-010](ADR-010-gzh-integration.md).

## Context

ADR-010 proposed keeping the WeChat Official Account workflow external and
integrating through an adapter. Two facts invalidated that:

1. The Founder intends to delete the local checkout **and possibly the GitHub
   remote**, leaving this repository as the only surviving project.
2. The checkout's history **diverged** from its remote (`origin/main` is `e9303d1`,
   the checkout is `93645f1`), so its four commits exist on no remote. Cloning
   upstream does not reproduce it.

An external dependency that is scheduled to disappear is not a dependency; it is a
gap. The product goal is also now explicit: this project should carry the workflow
for **every** platform it publishes to — Douyin, Bilibili, Xiaohongshu, 公众号, and
later X.

## Decision

**Import the 公众号 workflow into `vendor/gzh-thinktank/` and treat it as owned
surface, while keeping it unmodified.**

- The engine (scripts, profiles, contracts, skills source) is vendored verbatim:
  684 files, 8 MB.
- Regenerable dependency trees (`node_modules` 32 MB, `.venv` inside the excalidraw
  pack) and anything credential-bearing (`.aws-article/config.yaml`) are excluded.
  The full original remains in a git bundle outside both trees.
- The tree is **never edited**. A change is a new import with a new digest.
- `scripts/gzh_pin.py` recomputes the tree digest and the bundle digest; a mismatch
  is a failure.
- The workflow keeps its workspace outside its own root: `GZH_ARTIFACT_ROOT` points
  at `projects/gzh-thinktank/`, which satisfies its "artifact root outside the
  workflow root" rule while keeping articles inside this repository.

### Why vendoring rather than re-implementing

The engine is 2.6 MB of Python implementing ten ordered stages, each with structural
and semantic contracts, and an evidence layer that mints and re-derives its own
receipts. Re-implementing that is weeks of work and would produce a second, weaker
gate. The repository's own rule rejects a sixth production system; a vendored engine
under a pinned digest is not a new system, it is an owned copy of an existing one.

### Why not the whole upstream tree

The two large skill packs are 162 MB almost entirely of `node_modules` and a Python
`.venv`. Neither is content: both are rebuilt by the skills' own install steps. The
source of those packs is 4 MB and is what was imported.

## Consequences

- **The archive is retired.** The bundle, the original checkout and its GitHub remote
  were deleted on 2026-10-30 (both paths absent, the URL returns 404), so
  `vendor/gzh-thinktank/` is the only copy. Lost with them:
  the original's four commits, the twelve files this repository cannot track, and
  `production/`'s image assets (its text and JSON were copied to
  `projects/gzh-thinktank/` first). `scripts/gzh_pin.py` sets
  `BUNDLE_RETIRED = True`, so a missing bundle is expected; a present one must still
  match its digest.
- **The capability was measured, not assumed.** A clean clone of the original bundle
  and the vendored copy fail the *same* five of twenty-eight workflow-gate tests —
  the ones needing the never-versioned `.aws-article/config.yaml`. The import is
  faithful to what the original actually contained.

- This repository now contains two Python codebases. `dev_check` runs this one's
  suites; the vendored workflow keeps its own per-script tests and its
  `validate_matrix.py`, which reports three expected findings (documented in
  `vendor/gzh-thinktank/MANIFEST.md`): the deliberately excluded credential config,
  and two pre-existing hash drifts that also appear in the original checkout.
- The account has two names — `thinktank` (公众号) and
  `x-superplay-future-intelligence` (this repository). `scripts/gzh_pin.py` records
  the mapping; neither side may rename silently.
- Publishing stays inside the vendored workflow: preflight → create draft →
  read-back. It never publishes publicly, and credentials stay outside both trees.
- Video remains a downstream derivative in the 公众号 workflow
  (`media_guard.py`); this repository's video producers are not its upstream.

## Reversibility

Deleting `vendor/gzh-thinktank/`, its `MANIFEST.md`, the pin block in
`scripts/gzh_pin.py` and `tests/test_gzh_pin.py` restores the previous state. The
bundle at `D:\Archives\repos\gzh-thinktank\2026-10-30\` is unaffected either way.

## Open questions

1. Should the two large packs' `node_modules` / `.venv` be rebuilt on demand (an
   install step) or left out until the `illustrated` stage needs them?
2. Does the 公众号 track run on the same cadence as the video tracks, or only when
   an episode has enough written depth?
3. Who authors the 2500–5000 character article body?
