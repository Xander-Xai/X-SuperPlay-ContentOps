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


## Generated Image Quality (M3, Issue #20)

A generated image may support a video. It may never evidence one.

| Requirement | Rule | Enforced in |
|---|---|---|
| Container known | PNG, JPEG or WEBP, decided from magic bytes | `image_container.py` |
| Requested vs actual both recorded | `requested_extension` and `detected_container` | `minimax_image.py` |
| Provider bytes preserved | rename only, never transcode | `minimax_image.py` |
| Dimensions valid | `[512, 2048]`, multiples of 8, checked locally | `image_fingerprint.py` |
| Billing proven | subscription, all four paid balances zero, 5h and weekly above zero | `billing_guard.py` |
| Credential bound | gate and child use one key | `credentials.py` |
| Decodable and non-uniform | luminance stddev and span floors | `image_qc.py` |
| Aspect ratio | within tolerance, not exact equality | `image_qc.py` |
| Not evidence | generated assets refused every claim-bearing role | `image_contract.py` |

**Technical QC never approves on taste.** `approved` means technically sound. It
does not mean beautiful, on-brand or publishable. Those are human judgements, and
an automated gate that reports "publishable" teaches the pipeline to trust itself.

**A blank or near-uniform image fails.** A solid fill decodes cleanly and looks
real to every naive check, so it is caught by pixel statistics rather than by the
file being unreadable.

**Critical text is not asked of the model.** A model asked for "a benchmark
chart" invents one, and invented glyphs read as data. Critical text is a
deterministic overlay applied later. `text_contamination_suspected` is an honest
suspicion signal from edge-density measurements, never a verdict.

### Hard Fail: support-only asset used as evidence

Evidence-capable kinds, and only these:

| Kind | |
|---|---|
| `REAL` | a real recording, photograph or capture |
| `SCREENSHOT` | a real screen capture |
| `SCREEN_RECORDING` | a real screen recording |

Support-only kinds:

| Kind | May | May never |
|---|---|---|
| `DIAGRAM` | explain architecture, flow, relationship, concept, sequence | witness a benchmark, test result, analytics metric, customer outcome, UI state, source-code fact or production behaviour |
| `GENERATED_IMAGE` | hook, cover, concept, metaphor, background, transition | carry any claim |
| `GENERATED_VIDEO` | hook, hero, concept, transition, impossible-to-record shot | carry any claim |

A diagram is a legitimate asset. It **explains**; it does not **prove**. When one
illustrates a claim, the real source behind it stays traceable separately through
`claim_refs`.

Registering any of them as `EVIDENCE`, `CLAIM_SOURCE`, `BENCHMARK_PROOF`,
`TEST_RESULT`, `ANALYTICS_PROOF`, `UI_SCREENSHOT`, `CUSTOMER_PROOF` or
`SOURCE_CODE_PROOF` raises `GeneratedAssetEvidenceError`, **even when the caller
passes `evidence_capable=True`**. Generated assets also require
`evidence_capable=False` and a `receipt_ref`.

Generated-ness is **intrinsic provenance**, derived from kind and never
overridable:

| Intrinsic (from `kind`) | | Usage (caller, within limits) | |
|---|---|---|---|
| `generated` | **never overridable** | `evidence_use` | overridable |
| | | `evidence_capable` | **down only** |

```
GENERATEDNESS IS DERIVED FROM KIND AND CANNOT BE OVERRIDDEN
CALLER MAY REDUCE CAPABILITY
CALLER MAY NEVER ESCALATE CAPABILITY
```

`GENERATED_IMAGE` and `GENERATED_VIDEO` are always generated. `REAL`,
`SCREENSHOT`, `SCREEN_RECORDING` and `DIAGRAM` never are. A conflicting
caller-supplied value is **refused, not normalised**, because the conflict means
bad caller logic, a bad migration, or an attempt to bypass provenance.

Capability and provenance are independent. A real capture used decoratively is
legal. Promoting a diagram into proof is not. Labelling a real capture as
model-generated is not either.

This is a domain error at the single point an asset enters the system, not a note
in a document that a prompt can ignore.
## Converged Asset Gate (M4.5, Issue #27)

One vocabulary for every modality, so composition and final QC can ask one
question and get one answer.

| State | Meaning |
|---|---|
| `BLOCKED` | validation or technical QC failed |
| `DEGRADED_FALLBACK` | technically fine; a declared substitute was used |
| `PENDING_HUMAN_REVIEW` | technically fine; awaiting a person |
| `PRODUCTION_READY` | technically fine **and** a person approved it |
| `REJECTED` | a person looked at it and refused it |

### Technical PASS is not approval

These are claims about different things. A file can decode perfectly and still be
a shot nobody would publish; it can also be beautiful and be wrong about its own
dimensions. Collapsing them is how a pipeline comes to believe it cleared its own
work.

Two rules enforce the separation, and both are tested:

- the gate cannot reach `PRODUCTION_READY` without a **recorded** human decision
- the **validator** refuses a receipt claiming `production_ready: true` while
  `human_review` is still `PENDING_FOUNDER_REVIEW`

No automated check synthesises a Founder score, and none infers approval from
quality. Generated image, generated video and diagrams are additionally
`never_evidence_capable`, so they cannot carry a claim even if a reviewer were
asked to.

### Usable is not the same as placed

`usable_assets()` is an **inventory**: it answers "may this asset appear". It may hold
several assets for one placement, because an AudioPolicy transform keeps its source
alongside the derived asset — that is correct, and both stay in the manifest as
provenance.

`active_visual_assets()` is the **timeline**: exactly one asset per placement, each
with a recorded `selection_reason` and the `superseded_asset_ids` it displaced.

Composition reads the timeline. Iterating the inventory is how a single placement
ended up on the timeline twice, playing the pre-transform native audio underneath the
narration REPLACE was meant to guarantee would be the only track. Each active shot's
audio outcome is stated as an `audio_postcondition`, so it is checkable rather than
inferred.

### Generated provenance is not downgradable

A transform changes bytes; it does not change what the content is. A `GENERATED_*`
asset stays `generated: true` whether or not it was derived, and
`MediaAssetEnvelope` refuses to be **constructed** with a generated kind and
`generated=False` — in both directions. `derived_from` is how derivation is recorded.

### A committed artifact contains no machine path

Manifest and receipt paths are logical (`project://`, `repo://`) and resolved at the
point of use. An absolute path is refused, not written: one committed manifest
carried eight `D:\Projects\...` paths, which made its fingerprint specific to one
checkout root.

### Fallback is visible and never self-approving

A declared fallback names what was **requested**, what was **used** and **why**, and
sets `degraded: true`. An unnamed substitute is refused at validation. A fallback
reaches `DEGRADED_FALLBACK`, which is usable in composition but never becomes
production-ready on its own.

### Gate state does not equal registry state

The gate admits or excludes an asset from **composition**. The registry records
**what the asset is**. They must agree — `BUILDING` and `PENDING_HUMAN_REVIEW` in
the registry, but `BLOCKED` at the gate, would mean composition and provenance
disagree about the same file.
