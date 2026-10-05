# Enhanced Golden A/B — engineering preflight

**Status: `PENDING_FOUNDER_REVIEW`.** This is a preflight for engineering review. It does not request a selection and implies none.

The two arms share the Evidence Lock, the six factual screenshots, the master script, the narration text, the canonical caption and the entire visual timeline. Only the narration stack differs.

## Arms

| Arm | Narration stack | Provenance | Narration SHA256 | Duration | QC |
|---|---|---|---|---|---|
| **A** | baseline narration stack | `CONSISTENT_HISTORICAL_BASELINE` | `bc6b721656a5aab3…` | 61.86 s | `WARN` |
| **B** | MiniMax production narration stack | `VERIFIED_CURRENT_BASELINE` | `e2e014a916eb7a63…` | 61.86 s | `WARN` |

## Gates

- factual identity: **EXPERIMENT_VALID** (6 placements, 0 mismatches)
- evidence lock: `119b3825eb6334d8…` (`fixture=false`)
- provider calls: speech 0, image 0, video 0
- quota delta: 0 — both voices reused, nothing generated

## What differs, and what does not

| Field | A | B | Same? |
|---|---|---|---|
| narration SHA256 | `bc6b721656a5aab3491d` | `e2e014a916eb7a637b68` | NO — declared variable |
| voice provider | `easel/tts-voiceover ` | `minimax_m_plan/minim` | NO — declared variable |
| caption SHA256 | `ea3a8a52439af1d3b75b` | `ea3a8a52439af1d3b75b` | yes |
| script SHA256 | `997679154e64a0b6b8df` | `997679154e64a0b6b8df` | yes |
| narration text SHA256 | `f2de808c9e723f8430ac` | `f2de808c9e723f8430ac` | yes |
| storyboard structure | `b77b4295a49c9c2ec6c2` | `b77b4295a49c9c2ec6c2` | yes |
| evidence digest | `a50ea21300d689eb996b` | `a50ea21300d689eb996b` | yes |

## Not started

- no generated support image
- no H3 insert
- no Founder selection of any kind

Provider spend before A and B are reviewed would confound the first real comparison with the cost of the experiment.
