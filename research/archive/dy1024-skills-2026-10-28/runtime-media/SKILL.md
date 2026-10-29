---
status: superseded
superseded_by: research/archive/dy1024-skills-2026-10-28/README.md
historical_context: copied contract from the retired dy_x1024 workspace; archived, not routed to
source: dy_x1024@a5952a44dbf47d44c1a4bf475e3653b542c25ac1
date: 2026-10-28
name: runtime-media
description: Run the local speech, ASR, avatar and editable-timeline workers under the explicit VIDEO_MODEL_ROOT only after the content matrix gates and permission checks pass.
---

# Runtime Media

> **Legacy V1 package adapter.** This adapter still targets the `video_production` state machine and its V1 artifact defaults. Use it only for an explicitly declared historical V1 package. It is not the canonical V2 Media Generation executor; V2 production follows `docs/strict-media-workflow.md` and `scripts/canonical_workflow.py`.

Use the `VIDEO_MODEL_ROOT` environment variable as the external execution root. Keep model code,
weights, environments, voice references and face videos outside this
repository. This workflow is local-only: voice cloning is IndexTTS2.5 and
digital-human generation is MiniMax H3 Ref2VA; no hosted avatar/TTS provider is
allowed as a fallback.

## Required sequence

1. Run `python adapters/model/model_adapter.py doctor --strict`.
2. Finish `script` + `review`, then run
   `python adapters/model/model_adapter.py run --project ... --mode audio --confirm-model-use`.
   This creates the final IndexTTS2.5 narration, FunASR captions and the
   hash-bound `04_video/audio-handoff.json` before visual/assets work.
3. Approve the `audio` gate, then continue through `assets` before any avatar
   render. Confirm the local reference-audio authorization (`permissions.voice_clone`)
   and avatar permission in the nested video manifest. For H3, validate the
   selected `avatar.source_image` and `avatar.reference_audio`; the reference
   image must come from the controlled `assert/Fig*.png` manifest.
4. Run `preflight` for the requested post-assets mode (`avatar` or `all`).
5. Run the worker only with an explicit `--confirm-model-use`.
6. Review FunASR transcript verification, the audio handoff hash and H3 sync metrics before
   approving quality.

The bridge never downloads models or copies them into the content package. It
feeds local narration/ASR/avatar outputs into the Remotion master composition;
OpenChatCut and FCPXML remain optional interchange helpers, not a competing
timeline owner.
