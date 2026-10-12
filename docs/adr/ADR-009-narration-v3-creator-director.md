# ADR-009: Narration v3 — CreatorScriptEditor, NarrationDirector, minimal D/E/F

## Status

ACCEPTED (2026-10-14, Issue #34)

## Context

The v2 round (ADR-008) passed every test and failed human acceptance: the
Founder judged the narration still mechanical, with emotion and rhythm that did
not follow the content. The read-only diagnosis
(`projects/easel-enhanced-golden/review/narration-v3-diagnosis.md`) measured the
committed artifacts rather than guessing:

| Finding | Measurement |
|---|---|
| Spoken script was the written original | 96.9% character-level similarity; S01/S07 byte-identical; no re-order, no hook, no value framing |
| `calm` was the mechanical majority | 5 of 7 segments (71%); the only auto units were the two carrying numbers |
| Pauses were fixed values | 12 markers, durations only 0.3 s (x8) and 0.4 s (x4), one per clause mechanically |
| Paragraph slicing | C generated every paragraph as its own request; join silences 0.84/0.75 s vs internal 0.41–0.65 s |
| Why tests could not see it | invariant tests, detector-only ASR, level-based QC; none measures prosody |

Three independent variables were entangled: the copy, the delivery plan and
the voice timbre. The v2 evidence could not say which dominated.

## Decision

Three changes, one variable each:

1. **CreatorScriptEditor** (`contentops.media.creator_script`). The spoken
   derivative stops being a re-punctuated transcript: it may re-order the
   narrative, drop declared details and ask questions that introduce no fact,
   and must carry a hook, a setup, evidence, a turn, a problem, a value unit
   and a natural ending. Hard refusals: invented numbers; preserved facts that
   do not exist in the locked original; reintroduced declared omissions;
   template marketing phrases; first-person markers without a declared basis;
   missing beats; question overload; newlines or markers inside a unit.
   The locked fact script and the evidence lock remain the untouched owners of
   the truth.
2. **NarrationDirector** (`contentops.media.narration_director`). Full-narrative
   planning before any parameter: per-unit `communicative_intent`,
   `delivery_style`, `emphasis_terms`, `pause_intent`, `pace_intent`,
   `emotional_transition` and `context_before`/`context_after` are **internal
   labels and never request fields**. The conservative mapping allows only:
   auto emotion as the default (explicit values need a justification, must be
   documented for the model, and `calm` may appear at most once and never as a
   majority); bounded speed (0.95–1.08, homogeneous across every unit of a
   group, justified); pause markers 0.2–0.5 s with unique anchors and provider
   validation. Synthesis boundaries follow narrative groups (8 units → 4
   groups), with at least one multi-unit group and single-unit groups legal
   only with a declared reason and a differing control.
3. **Minimal D/E/F experiment** (`scripts/run_creator_sample.py`, hidden labels
   `candidate-1/2/3.wav`): D = new script + clone + auto; E = same text +
   clone + director controls; F = same text + subscription-confirmed preset
   voice (`Chinese (Mandarin)_Reliable_Executive`, evidence pinned to the M2.0
   in-plan receipt). B and C from v2 are referenced, never regenerated.

## Evidence (executed 2026-10-14)

Receipts: `projects/easel-enhanced-golden/review/narration-v3-sample-receipt.json`
and the blind-listening template `listening-review-v3.md`.

| Fact | Value |
|---|---|
| Provider calls | 4 (D, E x2, F); 676 billable characters of the 1200 cap |
| Billing | every request `M_PLAN_ONLY_VERIFIED`; no paid-fund movement; no re-clone/top-up/upload |
| Durations (same text) | D 28.74 s · E 26.59 s · F 22.56 s |
| Pace evidence | the clone speaks ~27% slower than the preset voice at the same nominal speed 1.0 — the first hard signal that voice timbre/pace is a real variable |
| Pauses | D 9 silences · E 6 intentional pauses (director) · F 11 |
| Technical QC | all three candidates approved (−16.0/−16.0/−16.8 LUFS, TP ≤ −1.4 dB) |
| ASR | 0.978–0.989 coverage; only the known version-normalisation false mismatch plus one preset-voice token difference |
| Review state | `production_ready: false`, `human_review: PENDING_FOUNDER_REVIEW`; nothing published |

## Consequences

- The acceptance gate is the Founder's blind listening: six criteria (real
  person, emotion fit, pace comfort, emphasis, voice similarity, join/pause
  naturalness) scored in `listening-review-v3.md` **before** the key is read.
  ASR and CI passing are explicitly not naturalness verdicts.
- The experiment's design supports a lean verdict: if F (preset) sounds natural
  and D/E do not, the voice is implicated; if all three still feel mechanical,
  the copy or the mapped delivery is; if E beats D, the director strategy
  works. The decision options are pre-declared in the review template.
- A full-narration v3 run, further lexicon work or any voice change remain
  deliberate follow-ups, not part of this ADR.

## References

- `projects/easel-enhanced-golden/review/narration-v3-diagnosis.md`
- `projects/easel-enhanced-golden/script/creator-script.json`, `narration-plan.json`, `creator-version-map.json`
- `projects/easel-enhanced-golden/review/narration-v3-sample-receipt.{json,md}`, `listening-review-v3.md`
- `src/contentops/media/creator_script.py`, `narration_director.py`; `scripts/verify_creator_script.py`, `run_creator_sample.py`
- ADR-008 (v2 payload/segments/billing), ADR-007 (transport)
