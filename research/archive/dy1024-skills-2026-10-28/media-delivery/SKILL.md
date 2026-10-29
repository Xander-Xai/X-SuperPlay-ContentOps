---
status: superseded
superseded_by: research/archive/dy1024-skills-2026-10-28/README.md
historical_context: copied contract from the retired dy_x1024 workspace; archived, not routed to
source: dy_x1024@a5952a44dbf47d44c1a4bf475e3653b542c25ac1
date: 2026-10-28
name: media-delivery
description: Produce a review-gated, editable vertical-video delivery package from an approved content package. Use for second-by-second direction, local voice/ASR/avatar execution, Remotion timelines, optional OpenChatCut/FCPXML interchange, captions, platform variants, rights evidence, and final quality sign-off.
---

# Media Delivery

Use this as the canonical delivery skill for the Douyin Creator Flow.

## Required order

1. Read the account profile and `00_brief/execution-plan.json`.
2. Read `04_video/design-direction.json`; refuse the old default card style.
3. Refuse media generation until `brief`, `research`, `script`, `review`,
   `design`, and `assets` are approved by `scripts/workflow_gate.py`.
4. Require `04_video/director-material-plan.json` to be `ready`, with a viewer
   job, visual owner, source strategy, rights plan, asset reference and
   fallback for every scene.
5. Run `adapters/model/media_runtime_bridge.py doctor` and `preflight` before touching
   IndexTTS, FunASR, MiniMax H3 or OpenChatCut under the explicit `VIDEO_MODEL_ROOT`.
6. Keep one editable master composition. Remotion owns the final scene/text/audio
   timeline; HyperFrames is a transparent deterministic overlay. OpenChatCut/FCPXML
   is an optional interchange or offline assembly helper, never a second timeline owner.
7. Put narration, captions, avatar, BGM, SFX, source footage and overlays on
   separate tracks. Keep original files and their ledger rows.
8. Run automatic QC and human review. Do not call a draft render a delivery.
9. Build the bundle with `scripts/delivery_package.py` only after the quality
   gate is approved. Publishing remains manual or uses an explicitly approved
   official channel.

## Account defaults

- **X•超玩1024:** five duration tiers: 1 minute (45–75s), 2 minutes (90–150s), 3 minutes (150–210s), 4 minutes (210–270s), 5 minutes (270–330s). Select by content type and evidence density; hook in the first 3 seconds, evidence-first, no padding.
  Screen capture is preferred for tool/project claims, with host window only at hook/verdict/CTA; the CTA stays within this account.

## Non-negotiable checks

- Never invent a test, number, screenshot, testimonial or first-hand result.
- Never generate a cloned voice or likeness without an explicit permission
  record in the video manifest.
- Every external, stock, generated or local media row must pass
  `scripts/rights_audit.py` before asset approval.
- FunASR verification and MiniMax H3 QC are required when generated narration
  and the active digital-human route are enabled; no legacy lip-sync engine is
  accepted by this workflow.
- Final output includes MP4, SRT, cover, editable project, source package,
  distribution copy, rights report and QC report.
