---
status: superseded
superseded_by: research/archive/dy1024-skills-2026-10-28/README.md
historical_context: copied contract from the retired dy_x1024 workspace; archived, not routed to
source: dy_x1024@a5952a44dbf47d44c1a4bf475e3653b542c25ac1
date: 2026-10-28
name: design-direction
description: Choose and review a non-template visual direction for X•超玩1024 Douyin content packages. Use when planning HyperFrames, Remotion, HTML Video, diagrams, covers, motion cards, or any episode that risks repetitive HTML-card aesthetics.
---

# Design Direction

Treat the local design repositories as reference systems, not as a pile of
templates to copy. Create one explicit direction per content package and keep
it stable for that episode.

## Project-to-capability map

- **Open Design**: design-system manifests, theme selection and bento token
  ideas. Use it for deterministic theme rotation, not a cloud dependency.
- **Penpot / OpenPencil**: token extraction, naming and accessibility lint.
  Use them as optional brand-system sources and review references.
- **cs-board / Manim**: continuous whiteboard narratives and exact mechanism
  animations; prefer them for technical diagrams and approachable X•超玩1024 analogies.
- **Open Canvas / AFFiNE**: persistent style memory and episode structure;
  use as planning references, not video editors.
- **HTML Video / Slidev**: content graph, theme boundaries and chapter scene
  composition. Use them to vary scene grammar while keeping one master editor.
- **Remotion**: data-driven or kinetic scene renderer only. HyperFrames remains
  a scene renderer, never the episode-wide visual owner.
- **shadcn/ui / Magic UI / Fragments / OpenUI**: component and motion
  references only; do not ship their default gallery look unchanged.

## Anti-fatigue rules

1. Choose a family through `scripts/design_router.py`; do not default to the
   old Swiss/amber card style.
2. Keep HTML/card scenes below the direction's `html_scene_ratio_max` and no
   more than `max_consecutive_html` scenes. Replace the next scene with
   evidence, screen capture, diagram, or original footage.
3. Rotate family and palette using `06_metrics/design-history.json`.
4. Do not mix design systems in one episode. Token source, typography, radius,
   accent and motion easing must agree.
5. Run `scripts/workflow_gate.py check --step design` and obtain human approval
   before acquiring or generating visual assets.

## Required output

Produce `04_video/design-direction.json`, its human-readable review copy, and a
design-lint report. The direction must name its source projects, palette,
typography, layout, motion renderer, evidence/media mix and fallback strategy.
