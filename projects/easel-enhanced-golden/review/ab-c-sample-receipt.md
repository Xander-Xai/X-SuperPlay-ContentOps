# A/B/C narration sample receipt (Issue #34)

- attempt: `absample-425cc266cbd7`
- executed: `True`
- outcome: `AB_C_READY_FOR_FOUNDER_LISTENING`
- route: `MPLAN_NARRATION_ROUTE` / model `speech-2.8-hd`
- credential class: `SUBSCRIPTION` (source `MMX_CONFIG`)

## Listen (gitignored real audio)

- **A**: `D:\Projects\X-SuperPlay-ContentOps\outputs\founder-ab-sample\A-original-excerpt.wav` (27.555 s, sha256 `0546580a663fcd63...`)
- **B**: `D:\Projects\X-SuperPlay-ContentOps\outputs\founder-ab-sample\B-spoken-auto.wav` (30.244 s, sha256 `a23abb9e4df936a8...`)
- **C**: `D:\Projects\X-SuperPlay-ContentOps\outputs\founder-ab-sample\C-segmented-joined.wav` (28.698 s, sha256 `9c7544d1355b6063...`)
  - C S01: `D:\Projects\X-SuperPlay-ContentOps\outputs\founder-ab-sample\C-S01.wav` (5.478 s)
  - C S02: `D:\Projects\X-SuperPlay-ContentOps\outputs\founder-ab-sample\C-S02.wav` (8.833 s)
  - C S03: `D:\Projects\X-SuperPlay-ContentOps\outputs\founder-ab-sample\C-S03.wav` (13.436 s)

A is a local excerpt of the existing Golden narration, cut at a
detected silence. Its alignment with the sample text is approximate
and is described in `alignment_note` plus the A ASR record.

## Not decided by this receipt

- Emotion naturalness, pace, pause naturalness, voice similarity, term
  pronunciation and join artifacts are **listening** judgements.
  Machine measurements (durations, ASR coverage, loudness, trace ids,
  usage) are recorded in the JSON; they cannot replace the Founder's ears.
- `production_ready` stays `false`; `human_review` stays
  `PENDING_FOUNDER_REVIEW`.

