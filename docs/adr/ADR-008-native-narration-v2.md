# ADR-008: Native narration v2 — paragraph structure, pauses, emotion, segments

## Status

ACCEPTED (2026-10-13, Issue #34)

## Context

The Founder voice `founder_primary_v1` was cloned and the first Golden narration
was synthesised through the native CN HTTP adapter (receipt:
`projects/easel-enhanced-golden/receipts/founder-voice-golden-narration-receipt.json`).
That run exposed two separate problems:

1. **The narration sounds mechanical.** The pre-v2 pipeline inherited a
   CLI-era workaround: because the pinned `mmx` CLI silently mishandles text
   containing a newline (measured 2026-10-04: exit 0, ignores `--out`, writes an
   MP3, synthesises only the first line), `build_spoken_request` flattened every
   narration to a single line. The native HTTP path inherited that flattening
   even though the API documents the newline as the *paragraph separator*. The
   Golden audio therefore contains only sentence-level pauses (six silences of
   0.4-0.6 s over 80 s) and no paragraph structure, and it carries no pause
   emphasis and no emotion direction.
2. **The billing path needed pinning.** The narration route's credential
   resolution could fall back through `MINIMAX_API_KEY` (a pay-as-you-go
   variable) and the stored config, and the first activation rounds had already
   shown how a claim ("sent on key A") can disagree with the transport (used key
   B). Regular narration must be provably plan-only.

## Evidence (official, quoted)

From the official OpenAPI definition of `POST /v1/t2a_v2`
(`platform.minimax.cn/docs/api-reference/speech-t2a-http`), fetched 2026-10-13:

- `text`: "段落切换用换行符标记" (paragraph switching is marked with newline
  characters).
- `text`: pause control is the inline marker `<#x#>`, `x` in `[0.01, 99.99]`,
  at most two decimals, placed between two speakable texts, and consecutive
  markers are forbidden.
- `voice_setting.emotion`: documented enum
  `happy, sad, angry, fearful, disgusted, surprised, calm, fluent, whisper`;
  the model "会根据输入文本自动匹配合适的情绪，一般无需手动指定" (auto-detects);
  `fluent`/`whisper` only take effect on `speech-2.6` models and `speech-2.8`
  does not support `whisper`.

From the executed A/B/C sample
(`projects/easel-enhanced-golden/review/ab-c-sample-receipt.json`,
`ab-c-sample-receipt-term-check.json`, 2026-10-13):

| Fact | Value |
|---|---|
| Provider calls | 5 (B + C×3 + S04 term check); A reused existing audio, 0 cost |
| ASR backchecks | 4 (A/B/C/S04) |
| Billable characters | 584 used of 1500 capped; 0 otherwise |
| Plan-only proof | 5-hour window 99% -> 98%, all paid balances flat, `M_PLAN_ONLY_VERIFIED` |
| A vs B vs C duration | 27.55 s / 30.24 s / 28.70 s |
| C join exactness | segments 5.478 + 8.833 + 13.436 + gaps 0.95 = 28.697 s vs joined 28.698 s |
| B paragraph pauses | 6 silences up to 0.65 s vs A's sentence-only silences |
| ASR term check | "doctor" transcribed correctly (the historical "Docker" mishearing did not reproduce); "伊泽尔" consistent; version strings read correctly, detector false mismatch remains (see below) |

## Decision

1. **The native path preserves paragraph newlines.** `build_spoken_request`
   no longer flattens; `flatten_for_cli` remains only for the CLI transport
   (`contentops.media.minimax_speech`) with its measured tests untouched.
2. **Pause markers are validated locally** (`validate_pause_markers`) against
   the four documented constraints before any request. A malformed marker is a
   local refusal (`INVALID_PAUSE_MARKER`), never a provider 2013.
3. **Emotion is optional and validated.** `build_t2a_payload(emotion=None)`
   omits the key (model auto-detects); a supplied value must be documented and
   applicable to the requested model. No default emotion is ever invented.
4. **Segmentation is the delivery unit** (`contentops.media.t2a_segments`):
   per-segment emotion/speed, a content-addressed segment cache, partial
   regeneration by segment id (unknown ids refuse), and deterministic
   concatenation with declared gaps. Gaps live in the join, not the segment
   fingerprint, so changing a gap never invalidates cached audio.
5. **The spoken script is a derivative artefact, not a rewrite of the
   original.** The locked `narration.txt` is untouched; the spoken script is
   validated mechanically (evidence-lock digest, digit tokens, protected
   phrases, pause syntax, role coverage) and the three-way SHA256 mapping
   (original / spoken / synthesis, plus per-segment) is tracked in
   `narration-version-map.json`. The validator's own docstring states what it
   cannot prove (tone, semantic equivalence).
6. **Billing is fixed before the first real call.** Narration resolves through
   `resolve_subscription_credential` (`MINIMAX_SUBSCRIPTION_KEY` or the stored
   subscription config; never the pay-as-you-go variable), passes the M Plan
   gate (`SAFE_INCLUDED_PLAN` + live quota), and every real request is wrapped
   in before/after plan-quota and balance reads. `--execute` is the explicit
   switch; `--budget-chars`/`--budget-asr-calls` are hard caps. No voice
   creation, no file transfer, no automatic top-up exists in the code path.

## Consequences

- The A/B/C sample and the S04 term check are produced and ready for Founder
  listening; `production_ready` stays `false`, `human_review` stays
  `PENDING_FOUNDER_REVIEW`. Nothing is auto-published and no digital-human
  video is produced.
- A full-narration regeneration (all seven segments at ~2x the sample length)
  is **not** executed by this ADR; the pipeline supports it
  (`--variants`/segment plans), and it should be a deliberate, separately
  budgeted action after the Founder's listening verdict.
- The ASR backcheck still reports a version-string false mismatch: the
  synthesis text carries the lexicon expansion `v零点二点一`, whose numeral
  reconciliation normalises to `v0.21`, while the transcript writes `v0.2.1`.
  The transcripts themselves show the version is read correctly. This is a
  detector artifact, recorded rather than "fixed" by weakening the detector.
- The A arm of the sample is a local excerpt cut at a detected silence; the
  flat source has no paragraph-level silence to align to, so its text alignment
  is approximate (ASR coverage 0.9639; the final "52 个" falls after the cut).
  `--a-mode fresh` exists for an exact-text control at character cost.

## References

- `src/contentops/media/minimax_native_tts.py`, `native_rounds.py`,
  `t2a_segments.py`, `spoken_script.py`, `credentials.py`
- `scripts/run_ab_sample.py`, `scripts/verify_spoken_script.py`
- `projects/easel-enhanced-golden/script/narration-spoken.json`,
  `narration-version-map.json`
- `projects/easel-enhanced-golden/review/ab-c-sample-receipt*.json`
- ADR-007 (CLI vs native transport), ADR-003 (M Plan provider)
