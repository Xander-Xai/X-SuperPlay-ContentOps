# Quality Standard

[English](QUALITY-STANDARD.md) | [简体中文](QUALITY-STANDARD.zh-CN.md)

> Video, content, fact, visual, and audio quality gates.

## Technical (automated)

| Check | Requirement |
|---|---|
| File exists | final.mp4 present, > 100KB |
| ffprobe parses | valid container |
| Resolution | 1080×1920 |
| Aspect ratio | 9:16 |
| Duration | 30–120 seconds |
| Video codec | H.264 |
| Audio codec | AAC |
| Audio present | non-silent (volumedetect) |
| Subtitles | burned in or subtitle stream |

## Content (automated + human)

- 3-second hook with result/conclusion
- Result-first structure
- No long empty introductions
- Visual change every 3–8 seconds
- Key claims have visual evidence
- Clear conclusion at end

## Factual (automated + human)

- Claims traceable to evidence
- Version numbers correct
- No fabricated test results
- No private info leaked
- No unauthorized material

## Visual (human)

- Subtitles in safe zone
- Font large enough
- Text not overflowing
- Screenshots readable
- No severe blur or stretch
- AI visuals not deformed
- Transitions not excessive
- Visual style consistent

## Audio (human)

- No clipping/popping
- No abnormal silence
- Loudness reasonable
- Narration understandable
- Sentence breaks natural
- Technical terms acceptable
- Background doesn't drown narration

## Evidence-First Policy

- Real source ratio ≥ 70% (automated check in qc_video.py)
- AI-generated visuals must not be the majority
- Each shot carries `source_type` and `source` provenance

## Human Review (100-point scorecard)

| Dimension | Points |
|---|---|
| Hook | 15 |
| Information density | 15 |
| Evidence quality | 15 |
| Voice naturalness | 15 |
| Visual quality | 15 |
| Pacing | 10 |
| Platform fit | 10 |
| Trustworthiness | 5 |

≥ 80 and no hard fails → PRODUCTION_READY

### Hard Fails

- Obvious factual error
- Voice severely mechanical/unintelligible
- AI video severely deformed
- Screenshots completely unreadable
- Subtitles misaligned
- Sensitive data leaked
- Unauthorized material
- Key claim without evidence
