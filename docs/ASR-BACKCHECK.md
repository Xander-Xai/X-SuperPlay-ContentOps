# ASR Backcheck

> A detector, never a judge. It can report a problem; it can never approve a video.

## What it does

`scripts/m5_production.py::stage_asr_backcheck` transcribes the narration track and
compares the transcript against the **spoken** script with a multiset coverage
measure (`src/contentops/media/asr_backcheck.py`). It exists to catch failures that
are objectively wrong — dropped words, repeated words, mangled numbers, flattened
proper nouns, split technical vocabulary.

It deliberately does not judge naturalness, emotion, pacing or publishability. A
transcript that reads perfectly can accompany audio nobody wants to publish; that
stays human review.

The comparison target is the narration text, never the on-screen subtitle text.
The pronunciation lexicon rewrites how a token is spoken, so a subtitle-shaped
expectation would report a false problem on a correct reading.

## Configuration

| Variable | Purpose | Default |
|---|---|---|
| `SILICONFLOW_API_KEY` | credential. Read from the environment only | none — absent means `SKIPPED` |
| `SILICONFLOW_ASR_MODEL` | model id | `XingChenAGI/XingChenASR-V3.2` |
| `SILICONFLOW_ASR_ENDPOINT` | overrides the published endpoint for a staging smoke | `https://api.siliconflow.cn/v1/audio/transcriptions` |

There is no configuration file for these. The key is never written to a receipt, a
log line, a CLI argument or an exception message; `asr_siliconflow.redact()` exists
so a caller that must echo an error can do so without leaking it.

## Model choice

`XingChenAGI/XingChenASR-V3.2`, on the free tier. The reasoning, and what is still
unproven:

| Candidate | Verdict | Why |
|---|---|---|
| `XingChenAGI/XingChenASR-V3.2` | **selected** | free; no speaker labels; best mixed-language technical-term recall of the free set |
| `XingChenAGI/XingChenASR-V3.2-Ultra` | rejected | same accuracy on short mixed-language audio at roughly 6x the latency; its dialect/long-meeting strengths do not apply to single-speaker TTS narration |
| `XingChenAGI/XingChenASR-Diarize-V3.0` | rejected | speaker labels enter the transcript and manufacture phantom coverage gaps |
| `XingChenAGI/XingChenGSR-V1.0` | rejected | thinnest published documentation and community evidence of the set |
| `FunAudioLLM/CosyVoice2-0.5B` | rejected | text-to-speech, not recognition |
| `FunAudioLLM/SenseVoiceSmall` | rejected as primary | fuses English terms (`GitHub` → `gitthub`), which is the exact failure mode this detector reports |
| `Qwen/Qwen3-ASR-1.7B` | comparison baseline only | most accurate in third-party short-audio testing, but metered (~CNY 0.79/hour) and would add a billing gate to a detector |

Evidence level: the ranking above rests on one third-party short-utterance
comparison, not on this repository's own measurements. The following are therefore
**unproven** and must not be described as verified until a real run says so:

1. whether `/v1/audio/transcriptions` accepts the `XingChen*` model ids — the
   vendor's endpoint documentation enumerates only `SenseVoiceSmall` and
   `TeleSpeechASR`, while the free-tier pricing page lists the `XingChen*` family;
2. behaviour on a full two-to-three minute narration rather than a 7-second clip;
3. rate limiting on the free tier.

## Contract of the provider call

`POST /v1/audio/transcriptions`, `multipart/form-data`, fields `file` and `model`,
`Authorization: Bearer <key>`. Upload ceiling 50 MB and 1 hour, enforced locally
before the request so an oversized input fails loudly instead of as a server 413.

The 200 body guarantees only `text`. Timestamps, segments and language are treated
as optional: present and well-formed they are recorded as capabilities; absent the
request still succeeds and the receipt says `timestamps: false`. A missing optional
field is never a failure and never a pass.

## Outcomes and what each one gates

| Status | Meaning | Account-bound project |
|---|---|---|
| `NO_PROBLEM_DETECTED` | transcript covers the script | proceeds to review; nothing approved |
| `DETECTED_PROBLEM` | the audio may say something else | proceeds to review **with the finding recorded** — interpreting a misread word is a human judgement |
| `SKIPPED` | no evidence was obtained | **blocked before compose** |

`SKIPPED` blocks because "no evidence" and "no problem found" must never look the
same in a receipt. A project with no `account_slug` records the skip and continues;
that path exists for historical samples, not as a way around the gate.

## Receipt

`projects/<slug>/receipts/asr-backcheck.json`, logical paths only:

```json
{
  "schema": "contentops.asr-backcheck/v1",
  "provider": "siliconflow",
  "model": "XingChenAGI/XingChenASR-V3.2",
  "capabilities": {"text": true, "timestamps": false, "language": false},
  "role": "DETECTOR_ONLY",
  "can_approve_quality": false,
  "audio": "project://assets/voice/narration.wav",
  "audio_sha256": "...",
  "status": "NO_PROBLEM_DETECTED",
  "coverage": 0.97,
  "issues": [],
  "missing": [],
  "excess": [],
  "account_bound": true,
  "blocks_human_review": false,
  "production_ready": false,
  "publish_authorized": false
}
```

## Boundaries

ASR is not wired into the rights gate, the publisher or the evidence layer. It
consumes no `SourceArtifact` and produces no claim. Removing it entirely would
reduce the amount of evidence available for review; it would not change what may
be published.
