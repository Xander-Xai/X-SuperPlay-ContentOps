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
- evidence lock: `af8128b958906e8e…` (`fixture=false`)
- provider calls: speech 0, image 0, video 0
- quota delta: 0 — both voices reused, nothing generated

## What differs, and what does not

| Field | A | B | Same? |
|---|---|---|---|
| narration SHA256 | `bc6b721656a5aab3491d` | `e2e014a916eb7a637b68` | NO — declared variable |
| voice provider | `easel/tts-voiceover ` | `minimax_m_plan/minim` | NO — declared variable |
| caption SHA256 | `ea3a8a52439af1d3b75b` | `ea3a8a52439af1d3b75b` | yes |
| script SHA256 | `7df3adbd34f3e2fc5157` | `7df3adbd34f3e2fc5157` | yes |
| narration text SHA256 | `2f7122228c53de128d04` | `2f7122228c53de128d04` | yes |
| storyboard structure | `edf33923b17c4dc3565a` | `edf33923b17c4dc3565a` | yes |
| evidence digest | `a50ea21300d689eb996b` | `a50ea21300d689eb996b` | yes |

## Not started

- no generated support image
- no H3 insert
- no Founder selection of any kind

Provider spend before A and B are reviewed would confound the first real comparison with the cost of the experiment.
