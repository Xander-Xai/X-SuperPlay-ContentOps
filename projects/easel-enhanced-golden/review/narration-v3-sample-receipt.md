# Narration v3 D/E/F sample receipt (Issue #34)

- attempt: `v3sample-d586a1abac13`
- executed: `True`
- outcome: `NARRATION_V3_CANDIDATES_READY_FOR_FOUNDER_LISTENING`
- model: `speech-2.8-hd` / route `MPLAN_NARRATION_ROUTE`
- credential class: `SUBSCRIPTION` (source `MMX_CONFIG`)
- budget used: `676` of `1200` billable characters

## Listen first (gitignored real audio)

```
outputs/founder-v3-sample/candidate-1.wav
outputs/founder-v3-sample/candidate-2.wav
outputs/founder-v3-sample/candidate-3.wav
```

Score the three candidates in `listening-review-v3.md` BEFORE reading
the key below.

## Listening key (reveal after scoring)

- `candidate-1` = **F** -- same script and parameters as D, official preset voice (auto emotion) (22.558 s)
- `candidate-2` = **D** -- new script + clone voice + auto emotion (no director controls) (28.735 s)
- `candidate-3` = **E** -- same text + clone voice + selective director controls (26.585 s)

## Machine facts (not quality verdicts)

- ASR and technical QC passing is not a naturalness verdict; the six
  listening criteria in the review template are the acceptance gate.
- Durations, loudness, silence maps, trace ids and usage are in the JSON.
- `production_ready` stays `false`; `human_review` stays
  `PENDING_FOUNDER_REVIEW`.

