---
title: "Speech A/B review request — edge-tts vs MiniMax M Plan"
canonical: false
type: receipt
status: PENDING_FOUNDER_REVIEW
project: easel-review
created_at: "2026-10-04"
translation_of: projects/easel-review/receipts/speech-ab-review.md
---

# Speech A/B review request (Issue #19)

> 中文： [speech-ab-review.zh-CN.md](speech-ab-review.zh-CN.md)

**Status: `PENDING_FOUNDER_REVIEW`.** No score has been recorded, and none will be
inferred. Only a human who has listened can fill this in.

## What is being compared

Identical source, script, storyboard, screenshots and composition. **Only the voice
changes.** No image generation and no generated video are involved in this
experiment.

| | A — baseline | B — candidate |
|---|---|---|
| Provider | edge-tts (current fallback) | MiniMax M Plan Explore |
| Model | n/a | `speech-2.8-hd` |
| Voice | system default | `Chinese (Mandarin)_Reliable_Executive` |
| Pronunciation lexicon | none | `zh-2026.10.04.1` |
| Loudness processing | none | two-pass `loudnorm`, −16 LUFS target, −1.5 dBFS ceiling |
| Local file | `.verify-tmp/m2/ab/A-edge-tts.mp3` | `.verify-tmp/m2/ab/B-minimax-mplan.wav` |

The media files are gitignored and live only on the build host.

## Measured differences

| Property | A — edge-tts | B — MiniMax |
|---|---|---|
| Container / codec | MP3 | WAV, `pcm_s16le` |
| Sample rate | 24 000 Hz | 32 000 Hz |
| Channels | 1 | 1 |
| Duration | 61.92 s | 61.77 s |
| Integrated loudness | **−24.2 LUFS** | **−17.0 LUFS** |
| True peak | −3.3 dBFS | −1.5 dBFS |

Two things to know before listening:

1. **B is about 7 dB louder.** That is the loudness gate doing its job, not a
   quality difference. Judge voice quality, not volume; if you want a fair volume
   comparison, level-match them first.
2. **The ASR detector flagged items in B.** Coverage was 0.96, with `ping`,
   `FFmpeg`, `.env` and the lexicon expansion `伊泽尔` among the tokens it could
   not confirm. The detector is a transcription check, not a quality verdict, so
   these need ears rather than a transcript.

## Automated gate results for B

| Gate | Result |
|---|---|
| Billing pre-flight | `SAFE_INCLUDED_PLAN` |
| PAYG cash / Credit Pack / voucher / owed | `0.00` / `0.00` / `0.00` / `0.00` |
| Technical QC | **PASS**, 13 checks |
| Peak after normalisation | −1.5 dBFS, ceiling respected |
| Leading / trailing silence | 0.0 s / 0.0 s |
| Semantic (ASR) | `DETECTED_PROBLEM`, coverage 0.96 — detector only |
| `production_ready` | **false** |

## Founder scoring

Please score each column 1-5 and add a comment.

| Dimension | A — edge-tts | B — MiniMax |
|---|---|---|
| Naturalness | | |
| Pronunciation of technical terms | | |
| Pace | | |
| Emotion / expressiveness | | |
| Clarity (intelligibility) | | |
| Absence of AI artifacts | | |
| Overall preference | | |
| Willingness to publish | | |

## Known open items for the reviewer

- `ping` is read unclearly and has no plain-text lexicon fix; it would need an
  inline pronunciation override, which was deliberately not guessed.
- `Web` was fixed with a plain-text expansion to `网页` after ASR heard it as
  `外部`. Confirm that reads naturally.
- The golden script contains `Easel`, `v0.2.1`, `SaaS`, `Skill`, `doctor`,
  `Python`, `Node`, `FFmpeg`, `Agent`, `fastapi`, `uvicorn`, `.env`, `API Key`
  and `CLI`, so this sample exercises the real technical vocabulary rather than
  an easy sentence.

## Until this is filled in

`production_ready` stays `false` and no narration is promoted to a project asset.
A synthetic score would be worse than no score.