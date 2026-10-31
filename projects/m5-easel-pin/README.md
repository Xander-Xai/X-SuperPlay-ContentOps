# m5-easel-pin — evidence-first production run

The first complete ContentOps production chain: a topic that comes from a real
fact, a claim ledger that proves the fact, an offline narration track, burned
subtitles, a composition by the pinned Easel runtime, automatic QC, and a human
approval gate that stays closed until a person fills it in.

Topic: why the Easel runtime must stay pinned to v0.2.1.

## Run it

```powershell
python scripts\m5_production.py projects\m5-easel-pin
```

Add `--skip-compose` to run the evidence stages only (no ffmpeg, no Easel).
The command exits `4` and prints `state: BLOCKED` with a reason when a stage
refuses — it never continues past a failed evidence check.

## Stages

| Stage | Reads | Writes | Refuses when |
|---|---|---|---|
| sources | `project.yaml` `source_refs` | `receipts/source-artifacts.json` | source missing, outside the repo, or an unknown permission |
| assets | `sources/assets.json` | `receipts/asset-manifest.json` | a declared visual's SHA-256 no longer matches, or its path escapes the repo |
| claims | `script/claims.json` | `receipts/claim-verification.json` | a claim has no artifact, cites a non-evidence-capable artifact, or its quote is not present verbatim |
| script | `script/script.json` | `receipts/script-check.json`, `script/master.md` | unknown claim id, undeclared asset, duplicate line id, empty narration |
| narration | script lines | `assets/voice/narration.wav`, `receipts/narration.json` | not on Windows (the only offline voice is the SAPI voice) |
| subtitles | narration timings | `assets/captions/default.srt`, `receipts/subtitles.json` | cue coverage below 0.8 of the audio duration |
| storyboard | all of the above | `script/storyboard.json` | — |
| compose | storyboard | `final/m5-easel-pin.mp4`, `receipts/compose.json` | Easel returns anything other than `OK` |
| qc | the video | `receipts/qc-report-*.json` | overall `FAIL`, or the render has no audio stream |
| review | the QC report | `receipts/human-review.json` | never — it writes `production_ready: false` and stops |

## What is real here

- **Facts** come from four tracked files, each recorded with a SHA-256 and a
  permission that allows citation. `script/claims.json` binds each claim to a
  quote that must occur verbatim in one of them.
- **Visuals** are three of the six evidence screenshots the Founder approved for
  tracking, declared in `sources/assets.json` with hash, origin and usage scope.
  No generated or stock imagery is used. A visual that fails its hash check
  blocks the run before it reaches the composer.
- **Narration** is synthesized locally by the Windows SAPI voice. It is
  intelligible and correctly timed, and it is also robotic: the receipt records
  `voice_quality: windows_sapi_offline`. A silent track is rejected by both the
  chain and `qc_video.py`.
- **Subtitles** are burned from the same timings that produced the audio, so a
  cue starts when its line starts.

## What is not real yet

- The voice is a placeholder, not a production voice track.
- Nothing is published. `human-review.json` ships with `scores: null`,
  `reviewer: null` and `production_ready: false`.
- This run validates the chain, not a finished episode. The topic itself is a
  short technical explainer, chosen because every fact in it is verifiable from
  the repository.
