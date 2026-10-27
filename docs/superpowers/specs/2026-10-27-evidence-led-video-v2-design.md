# Evidence-Led Video V2 Design

**Status:** Founder-approved design baseline  
**Issue:** #34 for the video rebuild; #6 remains a separate milestone  
**Date:** 2026-10-27

## Goal

Replace the existing static screenshot-card treatment with two genuinely different, evidence-led videos built from verified real captures. The short cut answers whether Easel is ready to use out of the box. The engineering cut distinguishes what has been verified from what remains unverified.

The design must improve watchability without turning evidence into decoration, generated imagery into proof, or an automated QC result into human approval.

## Non-goals

- Do not claim to close Issue #6 through video metadata alone.
- Do not create a second production system or modify the pinned Easel runtime.
- Do not publish automatically, manufacture platform metrics, or move `MEASURE`/`LEARN` out of `BLOCKED` without a real URL and metrics snapshot.
- Do not add BGM while `DASHSCOPE_API_KEY` is unavailable or fall back to `video_ops` BGM.
- Do not treat MiniMax generation as a substitute for a real capture.

## Delivery Topology

Three independent projects prevent shared-input contamination:

| Project | Owns | Must not share mutable inputs with |
|---|---|---|
| `easel-evidence-capture` | approved raw and redacted recordings, Capture Proof receipts, source hashes | either cut |
| `easel-1024-proof` | 9:16 script, timeline, captions, cover, receipt, review bundle | engineering cut |
| `easel-engineering-proof` | 16:9 script, timeline, captions, cover, receipt, review bundle | 1024 cut |

Each cut has its own project metadata, narration, subtitle asset, storyboard, target dimensions, cover, QC result, and human-review receipt. Both cuts may point to immutable source hashes and source time ranges held by `easel-evidence-capture`; no cut may depend on a mutable `default.srt`, shared storyboard, or shared project configuration.

## Evidence Capture Contract

A captured segment is not automatically proof of a narrated claim. Each reusable segment has a `Capture Proof` receipt with:

```json
{
  "capture_id": "CAP-...",
  "evidence_class": "EXECUTED | HISTORICAL | DOCUMENTED",
  "repository_revision": "commit SHA",
  "working_tree_state": "clean | declared diff hash",
  "target_environment": "named verification environment",
  "command": "approved redacted command",
  "read_only": true,
  "fixture_or_cache": "none | declared fixture/cache",
  "started_at": "UTC timestamp",
  "finished_at": "UTC timestamp",
  "exit_code": 0,
  "recording_sha256": "...",
  "raw_time_range": "00:07.200-00:13.840",
  "permission_scope": "internal-review | publishable"
}
```

Evidence class controls permitted language:

- `EXECUTED` proves the declared command and environment outcome from this run.
- `HISTORICAL` proves only what a previous receipt or capture recorded then.
- `DOCUMENTED` proves configuration or source text, not a runtime outcome.

UI claims require visible UI evidence. A terminal success line does not prove a browser or app state.

### Capture Safety

Capture takes place only in a dedicated, sanitized, visible terminal session. Commands are allowlisted and read-only. The process must not read `.env`, credential stores, browser profiles, historical scrollback, or customer data; must not include secret-bearing parameters; and must not start paid provider jobs, mutate remote state, overwrite evidence, or consume quota.

Notifications, microphones, and system audio are disabled before capture. Background helpers follow `process_utils.py`; the intentionally visible terminal is separate from those hidden helpers.

Raw recordings stay restricted in the project work area and are never committed or used directly for distribution. The distributable derivative requires a redaction-transform receipt linking source SHA, output SHA, masked regions, time ranges, and review outcome. Contact sheets, covers, stills, and review assets derive only from the redacted master.

### Context-Preserving Edits

Every crop records its source time range and crop rectangle. A key result first appears once with adequate context, then may be enlarged. A crop cannot remove warnings, mock/cache status, skipped work, failure summaries, units, environment markers, or other information that changes the conclusion. Command and result must come from the same captured session.

## Interim Claim Map

Issue #6 is still required for a production-wide Claim Ledger. Until it exists, every claim-bearing beat uses a compatible minimal `Claim Map` with:

| Field | Purpose |
|---|---|
| `claim_id` | stable identifier |
| `claim_text` | exact narration, on-screen, cover, or CTA text |
| `claim_kind` | runtime, source, historical receipt, or judgement |
| `evidence_ids` and `evidence_sha256` | immutable support |
| `time_range` | final-cut appearance |
| `support_status` | `SUPPORTED`, `PARTIAL`, or `BLOCKED` |
| `permission_scope` | publishable, internal, or pending |

Only `SUPPORTED` claims may appear as asserted facts. `PARTIAL` claims must state the limitation; `BLOCKED` claims cannot enter narration, captions, covers, labels, or CTAs. This map becomes input to, rather than a false substitute for, Issue #6.

## Editorial Products

### 1024 Conflict-Proof Cut

- **Format:** 1080×1920, 42–50 seconds.
- **Audience question:** Is Easel ready to use out of the box?
- **Opening conclusion, within 3 seconds:** “It is not out-of-the-box ready; this red line is the boundary.”
- **Argument:** show the specific anomaly, establish that core CLI/Skill work does function, show that the Web path remains unverified, then state the use boundary.
- **Intentionally omitted:** full skill taxonomy and detailed hash mechanics.
- **CTA:** an evidence-oriented invitation, not an unverified product promise.

### Engineering Evidence-Proof Cut

- **Format:** 1920×1080, 78–90 seconds.
- **Audience question:** What is verified, and what is not?
- **Opening conclusion, within 3 seconds:** “CLI and Skill are verified; the Web path is not.”
- **Argument:** revision/lock evidence, runtime verification scope, port mismatch, Web verification boundary, skill route, and an explicit verified/unverified matrix.
- **Intentionally omitted:** repeated conflict-hook material and generalized marketing language.
- **CTA:** a source/evidence review action, not a claim of production readiness.

The cuts have distinct audience question, opening assertion, argument order, proof depth, deliberate omissions, and CTA. Runtime and aspect ratio alone do not establish distinction.

## Motion, Captions, and Generated Media

### Motion Rules

A visual change must produce new evidence, new context, or a new explanatory relationship. Cursor blinking, filler scroll, red-box movement, or a filename change is not meaningful progress.

| Constraint | 1024 cut | Engineering cut |
|---|---:|---:|
| Non-reading beat | 1.2–2.5 s | 2–4 s |
| Key-evidence minimum reading hold | 2.0 s | 2.5 s |
| No-semantic-progress hold | ≤2.0 s | ≤3.0 s |
| Decorative transitions | ≤2 | ≤1 |

Evidence readability takes precedence over narration cadence, which takes precedence over a cutting-rate target. Captures are high-DPI before crop and must be checked at final display dimensions.

### Captions

Phrase captions are burned into each final cut, use the cut’s target safe zone, and are independently bound to the final narration timing. A subtitle-pixel detector is insufficient. Verification combines source caption timing, final audio, and full playback. Every key caption needs a measurable timing tolerance and a human review for overlap, legibility, and semantic break quality.

### MiniMax Experiment

First complete a zero-generated-visual evidence master. Only after it passes the evidence, redaction, readability, and playback gates may a single controlled MiniMax H3 experiment run:

- at most one generated clip;
- exactly one supported minimum-duration clip, currently 4 seconds for H3;
- generated duration is measured in seconds against final duration and must remain below 10%;
- asset metadata is `GENERATED_VIDEO`, `VISUAL_SUPPORT`, and `evidence_capable=false`;
- it runs only during a claim-free interval: no factual narration, subtitle, title, cover claim, or CTA assertion may rely on it;
- usage, quota delta, technical QC, and human taste review are recorded;
- delete it if it does not improve comprehension or pacing.

`DIAGRAM` and generated assets never contribute to real-source duration. Real-source ratio is duration-weighted rather than asset-count-weighted.

## Covers and Packaging

The 1024 package includes an 1080×1440 Xiaohongshu cover; the engineering package includes a 1600×900 Bilibili cover. Both use a real, permission-cleared evidence crop plus title treatment. They follow `card-design` under an editorial engineering/archive direction: warm neutral surface, ink/charcoal, one signal-red emphasis, restrained typography, and no blue-purple gradient, glass treatment, oversized empty card, or generic AI-tech imagery.

The cover title is claim-mapped. Each cover passes density and actual-size visual inspection; a cover is never reused across ratios without a layout designed for that ratio.

## Optimization-Loop Decisions

| Candidate | Decision | Why |
|---|---|---|
| Capture Proof + redaction chain | BUILD | makes real capture trustworthy and publishable only after boundary checks |
| Interim Claim Map | BUILD | blocks unsupported video facts while #6 is pending |
| Per-cut project/QC configuration | BUILD | prevents portrait/landscape and shared-input contamination |
| Semantic-progress and readability gates | EXTEND | replaces the false-positive static-hold-only pass |
| Covers and title variants | EXTEND | supports distinct platform packaging |
| Single MiniMax bridge | EXPERIMENT | only after the zero-generated evidence master passes |
| BGM via audio-mix | DEFER | missing key; forbidden loudness-regression fallback |
| Platform metrics and viewer feedback | DEFER | requires a real published URL and metrics |
| Complete cross-repo Claim Ledger | BUILD | remains Issue #6, independently scoped |

The rebuild is not an isolated retention experiment. It is a quality and trust correction. After publication, single-variable tests can compare such items as hook order, cover wording, or caption segmentation using real platform metrics and a declared observation window.

## Quality Gates

### Automated and Structural

- Target dimensions, codec, audio presence, and cut-specific QC config match the project declaration.
- Every claim-bearing time range has a `SUPPORTED` Claim Map binding.
- Every evidence time range has an immutable source SHA, source time range, evidence class, and permission scope.
- Generated duration is below the declared cap; no generated asset appears in a claim-bearing interval.
- Real-source duration is at least 70% and excludes diagrams/generated assets.
- Caption timing and safe-zone checks pass for the final cut.
- Cover, CTA, storyboard, receipt, and review-bundle inputs exist for each project.
- Any unresolved redaction or source-permission issue blocks distribution.

### Human Playback and Visual Inspection

Frame samples and contact sheets inspect layout, crop, safe area, overlays, black borders, text overflow, and still-image readability. They are supplementary. Full playback checks hook clarity, temporal evidence integrity, pacing, transition restraint, audio/caption alignment, brief secret flashes, and generated-media quality.

### Approval Binding

Each cut receives a `review_bundle_fingerprint` derived from its MP4, narration, captions, cover, Claim Map, evidence manifest, redaction receipt, and target-platform specification. Any change to a fingerprinted input invalidates review. `PRODUCTION_READY` requires a recorded Founder score of at least 80 with no hard fail. Publishing, URL receipt, metric capture, `MEASURE`, and `LEARN` remain separate state transitions.

## Skill Route

- `card-design`: visual system and density rules for covers.
- `card-xiaohongshu`: 3:4 Xiaohongshu cover rendering.
- `card-quote`: 16:9 Bilibili cover rendering.
- `auto-subtitle`: caption generation and burn workflow.
- `video-reframe`: only for an approved fallback transform of an existing video, never as the mechanism that makes the two editorial cuts distinct.

No matching Easel skill owns the Windows real-terminal recording plus evidence-capture contract. ContentOps must build this as an owned, receipt-bearing capability without hand-rolling generic transition chains.

## Deferred BGM

The master video must record BGM as optional and intentionally omitted:

```json
{
  "role": "optional_bgm",
  "status": "OMITTED_BY_POLICY",
  "reason": "DASHSCOPE_API_KEY unavailable; video_ops loudness regression prohibited"
}
```

A future key enables capability and rights testing, not automatic music generation. Any future BGM uses `audio-mix` and passes loudness plus human listening review.

## Completion Criteria

The rebuild is ready for Founder review when both cuts have independent, verified evidence manifests; the Claim Map contains no asserted unsupported claim; the capture/redaction chain is complete; subtitles are synchronized and readable; covers pass visual review; generated-media rules are honored; final playback is reviewed; and each immutable review bundle has been assembled. Neither cut becomes production-ready or published without a recorded human decision.
