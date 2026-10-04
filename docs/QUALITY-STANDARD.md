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

## Test-Only Video Duration Policy

**This governs development, research, smoke and regression video requests only.
It has no authority over production shot duration.** Production shots are
constrained by narrative and the North Star, not by this rule.

Video is the most expensive modality in the MiniMax M Plan Explore subscription:
one 4 s 768P H3 job consumed **7 percentage points of the weekly window**, and
video counts only against that weekly window. A careless 10 s "quick check"
therefore costs more than the shortest legal check.

```yaml
TEST_VIDEO_DURATION_POLICY:
  preferred_seconds: [1, 3]
  effective_duration:
    if provider_min <= 3: shortest supported duration in 1-3s
    else:                 provider_min
  never: send an unsupported 1s / 2s / 3s request just because it is cheaper
  longer_than_minimum_requires:
    - test_objective
    - why_minimum_is_insufficient
    - quota_budget
  production_duration: NOT_CONSTRAINED_BY_THIS_POLICY
```

Verified provider output-duration ranges, re-checked 2026-10-04 against the
current public API schema, the official CLI help and the real M2.0 receipt:

| Model | Range | Kind | Effective test duration |
|---|---|---|---|
| `MiniMax-H3` | 4-15 | integer enum | **4 s** |
| `MiniMax-H3-Max` | 5-15 | integer enum | **5 s** |

Resolution does not change the range (`768P` and `2K` both accept 4-15 for H3).
Reference *input* clips are a separate constraint: 2-15 s each, 15 s total.

Implementation and tests: `src/contentops/media/test_duration_policy.py`, covered
by `tests/test_minimax_speech.py`. No provider request is made in CI.

> "Tests use 4 s" means the **shortest legal test** for this provider. It does
> **not** mean a production video may only be 4 s long.

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
