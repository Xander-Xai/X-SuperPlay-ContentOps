# Next phase — Enhanced Golden A/B/C/D

> Prepared 2026-10-05. **Not started.** Requires PR #28 merged, then a dedicated
> issue. Do **not** jump into #6: the point of this phase is to prove quality
> progression under controlled conditions, and going straight to SourceArtifact E2E
> would confound "did the media help?" with "did the pipeline work at all?".

## What this phase is for

M4.5 proved the media layer executes. It did not prove any of it is *worth using*.
The single technical `final.mp4` had one of each asset type and no Founder
judgement, so it cannot answer the only question that matters for production:

> Does a MiniMax narration, a generated support visual, or an H3 insert make the
> video better — and does any of them make it worse?

Four controlled variants, one variable at a time, is how that gets answered without
guessing.

## The experimental rule that matters

**Factual evidence must be byte-identical across A, B, C and D.**

Every claim-bearing asset — every screenshot, every captured recording, every cited
document — is the same file in all four variants. Only the *media enhancement*
variables change. If the factual material differs between variants, the comparison
measures the evidence, not the enhancement, and the result is worthless.

This is enforced, not merely stated: the variant builder takes the manifest once
and may only alter assets whose `generated` flag is true or whose modality is
speech/video-support. A variant that would substitute a generated asset for a real
one must fail to build.

## The variants

| | Narration | Support image | H3 insert | What it isolates |
|---|---|---|---|---|
| **A** | existing voice | none | none | the pinned Easel baseline |
| **B** | MiniMax narration | none | none | narration quality alone |
| **C** | MiniMax narration | 1 generated image | none | + support visual |
| **D** | MiniMax narration | 1 generated image | **max 1–2** H3 inserts | + generated video |

Deliberately nested: B→C adds one variable, C→D adds one. A→B is the largest single
jump and is measured on its own so a regression there is not attributed to the
visuals.

### Why H3 goes last and is capped at 1–2

One 4 s / 768P H3 job cost ~7 weekly percentage points. Weekly sits at **51%**, so a
four-variant sweep using H3 in all of them would be a material and pointless spend.
One insert in variant D only tests whether an H3 shot helps *at all*; more would
test nothing extra and cost real quota. `C` deliberately has no H3 insert so that
D's addition is measurable.

## What each variant must record

Per variant, in a receipt:

- the exact asset set from the manifest, with every fingerprint
- which assets differ from variant A, and why
- `qc_video` and `qc_visual` results
- the real weekly quota delta, declared as a budget **before** the run
- `production_ready=false` and `human_review=PENDING_FOUNDER_REVIEW` — every
  variant, without exception

## Founder review criteria

Applied to all four, in the same order:

1. **voice** — naturalness, and whether it sounds like a person
2. **image usefulness** — does the support visual help comprehension, or is it
   decoration
3. **H3 usefulness** — does the insert carry meaning, and does it look like the
   rest of the video
4. **visual consistency** — does generated material clash with real captures
5. **artifact severity** — warping, melting, drifting subjects, garbled text
6. **pace** — does anything sit badly against the narration
7. **publishability** — the only criterion that can select a production baseline

The winner becomes the production golden baseline. A tie, or a preference for A,
is a legitimate outcome and is recorded as one — it would mean the paid providers
did not earn their quota, which is a result worth having.

## Quota discipline

| Variant | Speech | Image | Video |
|---|---|---|---|
| A | 0 | 0 | 0 |
| B | declared budget | 0 | 0 |
| C | reuse B's narration | declared budget | 0 |
| D | reuse B's narration | reuse C's image | declared budget, ~7pp |

Narration and image are **reused across variants** wherever the variant does not
change them. Rebuilding identical speech four times would spend quota to prove
nothing, and the fingerprint already tells us when an asset can be reused.

Any real provider call in this phase requires a written `TEST_OBJECTIVE`,
`MODEL`, `MODE`, `DURATION`, `RESOLUTION`, `WHY EXISTING EVIDENCE IS INSUFFICIENT`
and `EXPECTED_WEEKLY_QUOTA_BUDGET` before the call. Absent any of those, no task is
created.

## Then, and only then, #6

```
Enhanced Golden A/B/C/D
  → Founder review selects a baseline
  → #6 M5-M6: SourceArtifact → Claim Ledger → ContentRun → 3 real E2E builds
```

Three consecutive successful builds with a Founder-approved golden is the
definition of a production baseline in this repository. A technical integration
that nobody has watched is not one, which is why this phase cannot be skipped even
though everything in it already passes.

## Preconditions

| Condition | State |
|---|---|
| PR #28 merged | **required** — not merged by this author |
| weekly quota | 51% |
| all modalities | `PENDING_FOUNDER_REVIEW` |
| variant builder refuses a factual substitution | to be implemented in this phase |

## Acceptance

- [ ] A, B, C, D all build from one manifest with identical factual evidence
- [ ] a variant that would substitute generated media for a real asset fails to build
- [ ] the only differing assets are speech and generated media, enumerated per variant
- [ ] every variant records its QC results, its quota delta and a pre-declared budget
- [ ] every variant is `production_ready=false` / `PENDING_FOUNDER_REVIEW`
- [ ] Founder review recorded for voice, image usefulness, H3 usefulness, visual
      consistency, artifact severity, pace and publishability
- [ ] a baseline is selected, or A is recorded as the winner
- [ ] Reuse verified: B's narration reused in C and D, C's image reused in D

## Explicitly out of scope

- SourceArtifact ingestion · Claim Ledger · ContentRun (#6)
- PAYG or Credit Pack fallback
- Live verification of Ref2VA / FL2VA / L2VA / H3-Max
- Changing the pinned Easel version
