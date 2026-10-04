# ADR-007: MiniMax M Plan speech transport

## Status

ACCEPTED (2026-10-04, Issue #19)

## Context

M2.0 (Issue #4) verified MiniMax speech on the M Plan Explore subscription using
the official `mmx` CLI. The implementation question for M2 was which transport to
build on.

Pinned Easel `v0.2.1` already ships a MiniMax voice path:
`skills/shared/scripts/multivoice.py --provider minimax`, which delegates to
`voice_clone.py`. Reusing it would have avoided writing a second TTS client, so
it was tested first rather than dismissed.

## Evidence

The compatibility test was executed against the pinned runtime with a real
Subscription Key in the environment and no invented values:

| Command | Exit | Result |
|---|---|---|
| `voice_clone.py check --provider minimax` | 3 | reports `MINIMAX_GROUP_ID` missing although `MINIMAX_API_KEY` was present |
| `voice_clone.py clone --provider minimax --voice-id test ...` | 1 | blocked by `require_env("MINIMAX_GROUP_ID")` before any HTTP request |

Three independent incompatibilities, all read from the pinned source:

1. `MINIMAX_GROUP_ID` is **mandatory** and is appended as `?GroupId=` to every
   call. The current M Plan credential model has no GroupId.
2. Easel's MiniMax path is **clone-only**: `clone_minimax` requires a
   `voice_id` produced by `enroll_minimax`. There is no system-voice TTS path, so
   the capability M2.0 actually verified is unreachable through it.
3. Legacy defaults: base URL `https://api.minimax.chat` and model `speech-01`.

Classification: `EASEL_MPLAN_AUTH_INCOMPATIBLE`.

## Decision

- ContentOps speaks to the **current official CLI** (`mmx`, `mmx-cli` v1.0.27)
  through a thin adapter: `src/contentops/media/minimax_speech.py`.
- Easel is **not patched, not forked, not modified**, and `.runtime/easel` stays
  read-only. A test asserts the pinned source still requires `MINIMAX_GROUP_ID`,
  so an upstream change forces this decision to be revisited rather than
  silently inherited.
- The undocumented balance read is isolated in a single module,
  `src/contentops/media/billing_guard.py`, classified
  `UNDOCUMENTED_FIRST_PARTY_IMPLEMENTATION_DEPENDENCY`. A test asserts it exists
  in exactly one implementation location.
- The architecture stays provider-generic: `MediaProvider` in
  `src/contentops/media/contract.py` knows nothing about MiniMax.

## Consequences

- Two MiniMax speech paths now exist in the repository: Easel's upstream one and
  ContentOps's adapter. ContentOps's is the only one that can produce
  production narration, because it adds the billing gate, the pronunciation
  lexicon, loudness normalisation, QC, idempotency and the receipt.
- When Easel gains current-M-Plan support, the adapter can be replaced by an
  upstream call without changing anything above the transport.

## Transport defects absorbed

Found by running against the real CLI, not by reading docs. Each has a regression
test.

| Defect | Behaviour | Handling |
|---|---|---|
| Newline in `--text` | exits **0**, ignores `--out` and `--format`, writes MP3 into the working directory, synthesises only the first line | text is flattened to one line before sending |
| Unknown flag | silently ignored rather than rejected | output is verified to exist, be fresh and be non-trivial, so a future regression fails loudly |
| `<#seconds#>` pause marker | rejected with exit 1 | not used; plain space join instead |

## Consequences for quality

- Provider output peaked at **-0.2 dBFS**, so raw success is not production
  audio. Normalisation to **-17.0 LUFS / -1.5 dBFS true peak** is now part of the
  pipeline, measured with `ebur128`.
- Integrated loudness must be metered, not predicted: `loudnorm` reports the
  loudness it *would* produce, and recording that as a measurement produced a
  wrong conclusion that the target was unreachable.
- The ASR backcheck had to become script-aware. A whitespace tokeniser scored a
  correct Chinese reading at 0.31 coverage; per-character CJK comparison plus
  Latin word tokens and numeral reconciliation brought it to 0.96.

## Reopen when

- Easel's MiniMax path supports the current M Plan credential shape, or
- MiniMax changes the balance endpoint, or
- a documented official credit-balance endpoint replaces the undocumented one.