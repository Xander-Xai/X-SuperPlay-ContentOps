---
status: superseded
superseded_by: research/archive/dy1024-skills-2026-10-28/README.md
historical_context: copied contract from the retired dy_x1024 workspace; archived, not routed to
source: dy_x1024@a5952a44dbf47d44c1a4bf475e3653b542c25ac1
date: 2026-10-28
name: content-copy-orchestrator
description: Evidence-first content writing orchestrator for Douyin and other short-video platforms. It coordinates and validates one canonical, human-sounding script from verified claims, then optionally hands off visual planning without duplicating copy work.
metadata:
  version: 1.2.0
  scope: X•超玩1024 content workflow
  owner: local-workflow
---

# Content Copy Orchestrator

This is the single entry point for content writing. It combines evidence
ingestion, angle selection, platform adaptation, retention checks, humanization,
duration routing, voice profile, claim-to-scene mapping, and optional production
handoff.

## Audience Lens v3 and the dual spine

The workflow has one evidence spine, one viewer-progress spine, and one
platform packaging layer. They describe different responsibilities and do not
compete as alternative templates:

```text
viewer: recognition → tension → promise → discovery → proof → meaning → action
evidence: question → hypothesis → method/conditions → evidence → result → limitation → verdict → next action
packaging: Hook → Body → Close
```

The viewer spine owns relevance, felt stakes, value and progress. The evidence
spine owns truth, method and boundaries. A scene may advance both, but emotional
language can never upgrade evidence status. The seven viewer beats are required
as a progress card; they need not become seven equal-length scenes.

Taxonomy-specific `structure` values are beat presets, not additional writing
frameworks. They may reorder or omit optional beats for a tool test, tutorial,
failure review, or business experiment, but the strategy card must still carry
the same Thesis Card and evidence boundary. The angle catalog is a candidate
library: generate 3–8 candidates, select one primary angle (at most one
secondary), and record the selection rationale. Never paste all 40+/45 angles
into a script.

Audience selection is a gate before angle or hook selection, not a later tone
pass. Every topic must first complete `01_research/audience-insight.json`, show
all three registered segment candidates, and explicitly select one primary
segment (optionally one secondary). The three content pillars describe what the
account publishes; the three audience segments describe whose progress this
specific video serves. The five profile audience entries are identity facets,
not five competing segment routes.

It does not render media, download assets, synthesize audio, or approve rights.
Those remain downstream workflow stages.

## First principles

Every stage must perform one state transition and own one artifact:

1. topic card → audience research and explicit segment decision;
2. verified claims → evidence map;
3. audience lens + evidence map → angle, value promise and emotional arc;
4. angle → one canonical spoken script (written by the Agent/editor and validated here);
5. script → natural, risk-checked final copy;
6. approved copy → optional visual/material handoff.

Never ask two components to rewrite the same canonical script. Derived outputs
may add metadata or checks, but they must not silently fork the spoken text.

## Routing

Always run in this order:

- `audience-insight` first, to bind the topic to a researched viewer context,
  desired progress, objections, proof expectations, value and emotional arc;
- `copy-strategy` next, to bind account positioning, opportunity type,
  angle candidates, thesis card, hook variants and the teaching contract;
- `evidence-ingest` when a source or claims registry exists;
- `angle-strategy` exactly once per content package;
- `platform-script` exactly once;
- `duration-router` before timing the script;
- `retention-lint` for video, as a heuristic check rather than a fixed length rule;
- `voice-integrity` after the canonical draft;
- `creator-voice-profile` when a creator/account profile exists;
- `claim-to-scene-map` for video scripts with visual duties.

Do not write or promote `04_video/video-script.md` (including a planning draft)
until `01_research/audience-insight.json` and `00_brief/copy-strategy.json` are
both `ready`, and the strategy's Audience Lens hash, angle, Thesis Card, Hook
selection, and evidence-map receipts are applied. If a
package or strategy card does not exist, stop at a visible strategy-card
pending note; do not create a standalone spoken script that bypasses the
orchestrator.

Run only when required by the task:

- `visual-handoff` after script/review approval and before assets;
- `multi-shot-adapter` only when the deliverable actually contains multiple AI-generated video clips;
- `post-publish-learning` only when real performance data is available.

The optional contracts have explicit trigger states. `visual-handoff` remains
deferred until the canonical script declares `review_status: approved`, then
becomes eligible for a confirmed component record. `multi-shot-adapter` requires
`multi_shot_ai_video: true`, an approved script review, and at least two
storyboard scenes; a requested adapter with an approved script but fewer than
two scenes is blocked. A requested adapter before review remains deferred.
`post-publish-learning` only becomes eligible when publish feedback is required
and both metrics and comments artifacts are ready. `component_execution.py`
records the manual application and runs semantic checks; Markdown remains a
contract, not executable code.

## Platform and duration policy

The platform adapter owns wording, caption density, CTA and evidence-risk
language. The duration router owns length. A short-form heuristic must never
force a 60-second ceiling onto a 90- or 180-second brief.

### Caption and overlay contract

`04_video/video-script.md` owns the spoken wording. In the derived
`04_video/storyboard.csv`, `voice` and `subtitle` must carry the same spoken
transcript (punctuation and timed line breaks may change, wording may not).
Concise emphasis such as “官方声明 ≠ 本机跑通” belongs only in the separate
`overlay_text` column. It is optional visual copy, never a replacement for
captions. Caption generation downstream must derive from the final audio ASR;
the storyboard contract is checked before any audio or visual handoff.

For Douyin, lead with a recognisable viewer trigger and a concrete value
promise, show proof early, explain what the evidence means for this viewer, and
close with one action. The value contract may be practical, epistemic,
emotional, social or identity-based; it must still name a primary dimension and
an observable promise. Connection serves understanding and agency, not fear,
hype or invented intimacy.
Do not promise viral reach, platform preference, speed, quality, or conversion
outcomes.

## Human voice contract

The final copy must contain specific observations, a clear creator judgment,
and at least one honest boundary or uncertainty when evidence is limited.
Remove generic AI throat-clearing, stacked adjectives, empty “赋能” language,
and unsupported first-person claims. Preserve technical terms, numbers,
claim IDs, licenses, and source boundaries exactly.

### Audience research and emotional value

The audience is the protagonist; the creator is the guide. Before the hook is
finalized, the Audience Lens must declare:

- primary and optional secondary segment, with a recorded rationale;
- `viewer_context`: the trigger, situation, awareness level and current workaround;
- desired functional, emotional and identity progress;
- objections and proof expectations;
- a value contract with one primary value dimension;
- `viewer_emotional_job`: one job such as lowering anxiety, being understood,
  regaining control, finding courage to act, or co-creating the next test;
- `empathy_line`: one plain sentence that names the tension without pretending
  to know a viewer's private life;
- `emotional_turn`: the change the video should enable, such as “担心踩坑 →
  知道先检查哪三个条件”.

The source artifact is marked `validated`, `mixed`, or `exploratory`.
`validated` requires at least two independent sources and one direct audience
source. `exploratory` is allowed only when the research source or proxy is named
and the script carries a falsifiable learning CTA. Audience Lens is the only
source of audience, value, and emotional-progression truth in the active workflow.

## Evidence and AI-content contract

Each factual statement maps to a claim or source. Official statements,
first-hand tests, editorial inference, examples, and illustrative fiction are
separate labels. Generated visuals never become documentary evidence. If AI
generation is used in the final deliverable, the downstream publish stage must
apply the platform's current AI-content disclosure policy.

## Canonical outputs

The orchestrator writes or updates only these writing artifacts:

- `01_research/audience-insight.json` — the per-topic audience decision and
  evidence record; it must be ready before the strategy or script can be ready;
- `00_brief/copy-strategy.json` — the ready-gated strategy card produced by
  `scripts/copy_strategy.py`; it connects positioning, hotspot/newsjacking
  eligibility, angle selection and script packaging;
- `04_video/video-script.md` — canonical spoken script and timing, authored by the Agent/editor and validated here;
- `04_video/storyboard.csv` — derived scene/timing map;
- `05_publish/copy-orchestrator-plan.json` — component routing and checks;
- `04_video/render-project-clean/01_script/script-qc.md` — derived retention and
  voice-integrity QC receipt.

`04_video/video-script.md` is the only canonical copy source. Narration,
captions, visual plans and production files must derive from it.

The copy brief lifecycle is a hard gate, not descriptive metadata. A scaffold
may remain `pending` during package initialization, but component execution,
the orchestrator plan, and `workflow_gate` all require `status: ready` or
`status: approved` before they can report applied copy. A blocked component
must retain its concrete check error so the operator can repair the correct
artifact.

The humanization receipt at the Script gate is explicitly a machine preflight,
not human editorial approval. The canonical script must declare
`humanizer_review_type: machine-preflight`, and the nested humanized script
must declare `Review Type: machine-preflight`; the separate Review gate still
requires a human approval before audio or visual work.

Derived compiler and variant commands follow the same rule by default. Their
explicit `--planning-draft` mode is non-delivery only and writes
`planning_draft: true` plus `production_eligible: false`; quality and variant
approval gates reject that state.

## Component contracts

The replaceable component contracts live in `components/`. They are ordinary
Markdown modules, not standalone registered Skills. A replacement component
must preserve the same input/output contract before it can be promoted.

`copy-strategy` is a code-backed contract rather than a replaceable Markdown
component: its JSON artifact is validated by the orchestrator, component
execution ledger and workflow gate before script work can proceed.

- `evidence-ingest.md` — records source, operation and evidence inputs;
- `angle-strategy.md` — selects one registered angle for the strategy card;
- `platform-script.md` — applies the Douyin packaging contract;
- `retention-lint.md` — checks evidence rhythm and duration fit;
- `voice-integrity.md` — checks controlled-colloquial delivery and claim integrity;
- `duration-router.md` — removes the fixed 60-second assumption;
- `creator-voice-profile.md` — makes “活人感” reproducible;
- `claim-to-scene-map.md` — binds spoken claims to visual duty;
- `visual-handoff.md` — hands approved evidence scenes to visual production;
- `multi-shot-adapter.md` — conditionally handles multi-clip AI video;
- `post-publish-learning.md` — closes the retention-feedback loop.

## Gate order

`topic → audience research → evidence research → copy strategy → script → review → visual-handoff → assets`

The visual handoff must not execute before review. The multi-shot adapter is
not part of the writing gate unless the task explicitly requests AI video clips.

## Failure behavior

Return `blocked` with the missing artifact, owner component, and next action
when audience evidence, value promise, evidence, duration, voice, rights, or
platform constraints are missing.
Never fill a missing source with a fabricated test result or a generic prompt.
