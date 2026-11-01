# ADR-007: Evidence layer in front of the existing pipeline

## Status

ACCEPTED (implementation merged with the M5 chain, Issue #6)

## Context

The pipeline could already compose a video, but nothing stopped a script from
asserting something no source supported. `docs/SOURCE-ARTIFACT-CONTRACT.md`
defined what a source should carry; no code enforced it, so "the video says X"
and "X is true" were the same sentence typed twice.

The requirement for M5 was a chain whose facts are traceable, whose visuals are
owned, and whose narration is real — without building a second media engine. The
composer, the storyboard contract and `qc_video.py` already exist; anything that
duplicated them would create two places for a fact to be wrong.

## Decision

Add a small evidence layer, and make the existing pipeline refuse to run without
it:

1. `SourceArtifact` records a source's path, SHA-256, permission and capture
   time. `evidence_capable` is derived from the permission, never asserted:
   `OWNED`, `CREATED_BY_OWNER` and `LICENSED` may back a claim; `NONE` may not.
2. `Claim` binds text to one or more artifacts plus quotes. `verify()` reports a
   claim when its quote no longer occurs in the artifact, when the artifact's
   bytes changed, or when the artifact is not evidence-capable. A claim with no
   verifiable quote is an assertion and fails the run.
3. Every visual is declared in `sources/assets.json` with a hash. The chain
   checks the hash before the composer sees the file.
4. `scripts/m5_production.py` sequences sources → assets → claims → script →
   narration → subtitles → storyboard → compose → QC → review. Each stage writes
   its own receipt and refuses rather than improvising.
5. The chain ends at `PENDING_FOUNDER_REVIEW` with `production_ready: false`.
   Technical QC passing is not publishing permission (ADR-005).

Reuse over rebuilding: the storyboard keeps the existing contract, composition
goes through `assemble_easel.py`, and QC stays `qc_video.py`. The only composer
change is a bug fix (below) — no upstream file is modified.

## Consequences

- A fabricated or drifted claim blocks the run at `claims`, before any render
  time is spent.
- A visual whose bytes changed is caught before it reaches a frame.
- Every run produces a per-stage receipt, so a failure names the stage and the
  reason instead of a video that looks fine.
- The chain is Windows-only for narration today, because the only offline voice
  is the SAPI voice. A network TTS provider would need its own authorisation and
  cost decision, which this ADR does not grant.
- The evidence layer models permissions more coarsely than
  `SOURCE-ARTIFACT-CONTRACT.md`; the mapping is recorded there.

## Composer bug fixed alongside

`assemble_easel._srt_to_ass` formatted ASS timestamps with three fractional
digits (`0:00:05.830`). libass reads the fraction as centiseconds, so every cue
was stretched roughly tenfold and neighbours overlapped: a seven-cue script
rendered four subtitle blocks at the wrong times. The formatter now emits
centiseconds, and `tests/test_m5_evidence.py` asserts the two-digit form and the
round-trip. This affected every earlier project whose subtitles went through this
script, not only M5.
