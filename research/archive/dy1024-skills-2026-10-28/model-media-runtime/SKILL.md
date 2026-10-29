---
status: superseded
superseded_by: research/archive/dy1024-skills-2026-10-28/README.md
historical_context: copied contract from the retired dy_x1024 workspace; archived, not routed to
source: dy_x1024@a5952a44dbf47d44c1a4bf475e3653b542c25ac1
date: 2026-10-28
name: model-media-runtime
description: Use the local IndexTTS2.5, FunASR, MiniMax H3 Ref2VA, and OpenChatCut installations as execution workers for a review-gated video content package. Trigger when a project needs local reference-conditioned TTS, ASR transcript verification, digital-human lip sync, avatar QC, or an editable OpenChatCut/FCPXML bridge.
---

# Local model media runtime

> **Legacy V1 package adapter.** This adapter still targets the `video_production` gate and V1 artifact defaults. Use it only for an explicitly declared historical V1 package. It is not the canonical V2 Media Generation executor; V2 production follows `docs/strict-media-workflow.md` and `scripts/canonical_workflow.py`.

Use `adapters/model/model_adapter.py` as the only entry point for the local
model folder. Do not copy model repositories, checkpoints, virtual environments,
cookies, voice references, face videos, or generated media into this Git repo.

The adapter is an execution layer, not a second workflow. The repository's
`scripts/workflow_gate.py` remains the only serial approval state machine.

## Runtime map

| Capability | Local project | Expected environment |
|---|---|---|
| IndexTTS2.5 narration | `$env:VIDEO_MODEL_ROOT\index-tts-2.5` | `index-tts-2.5\\.venv\\Scripts\\python.exe` |
| ASR and script verification | `$env:VIDEO_MODEL_ROOT\FunASR` | `FunASR\\venv\\Scripts\\python.exe` |
| Digital-human lip sync | `$env:VIDEO_MODEL_ROOT\Minimax_H3` | `ComfyUI\\.venv\\Scripts\\python.exe` with ComfyUI port 8190 and SageAttention |
| Editable timeline | `$env:VIDEO_MODEL_ROOT\OpenChatCut` | local editor plus FCPXML bridge |

Override the model root with `VIDEO_MODEL_ROOT` or `--model-root` when the
machine uses a different layout.

## Required order

1. Finish script/review approval. Immediately run the audio-only runtime mode:
   `python adapters/model/model_adapter.py run --project <content-package>
   --mode audio --confirm-model-use`. This runs IndexTTS2.5, FunASR and writes
   the hash-bound `04_video/audio-handoff.json` before visual/assets work.
2. Approve the new `audio` gate, then run the `content-copy-orchestrator`
   `visual-handoff` component and get its `04_video/director-material-plan.json`
   approved by the `assets` gate.
3. Finish the content package gates through `assets`.
4. Put the nested video project path in `04_video/video.json`.
5. Confirm `permissions.voice_clone` (authorization for the local reference
   audio) and `permissions.avatar` in the nested
   video manifest before using those media operations.
6. Run the runtime doctor and preflight:

   ```powershell
   python adapters/model/model_adapter.py doctor --strict
    python adapters/model/model_adapter.py preflight --project <content-package> --mode all
   ```

7. Review `04_video/model-runtime.json`. Only after it reports `status: ready`
   may the model stage run:

   ```powershell
   python adapters/model/model_adapter.py run `
      --project <content-package> `
     --mode all `
     --confirm-model-use
   ```

8. After the runner writes avatar output, preview, QC and the
   editable bridge, run the repository gate:

   ```powershell
    python scripts/workflow_gate.py check --project <content-package> --step video_production
    python scripts/workflow_gate.py approve --project <content-package> --step video_production --reviewer "姓名" --confirm
   ```

9. After the repository `quality` record is approved, finalize the platform
   package through the adapter:

   ```powershell
    python adapters/model/model_adapter.py finalize --project <content-package>
   ```

## Safety and quality rules

- Never synthesize a voice or animate a face unless the content package records
  the corresponding permission as `true`.
- Treat `person_video.mp4`, voice references, and generated takes as user-owned
  local assets. Record them in the asset ledger; do not commit them.
- FunASR must compare the generated narration with the approved script. Missing
  names, numbers, percentages, or project identifiers fail the stage.
- MiniMax H3 output must include `h3-manifest.json`, `h3-prompt.txt`,
  `h3-workflow.json` and passing `h3-qc.json` before quality approval.
- Remotion is the editable master composition owner and HyperFrames is its
  transparent overlay. The runner's FCPXML/OpenChatCut project is an optional
  interchange artifact, not a second timeline authority.
- A draft render is not a deliverable. It remains blocked until the model report,
  captions, QC, rights, audio, visual and editable-project checks pass.

## Failure handling

- If `doctor --strict` fails, fix the local runtime or point `--model-root` to the
  correct installation. Do not bypass the check.
- If preflight fails, fix the content package, permission, reference asset, or
  runtime path and run it again.
- If FunASR or MiniMax H3 fails, keep the raw take and report; do not replace it
  with an unverified flattened video. Historical LatentSync wrappers are not an
  active route.
