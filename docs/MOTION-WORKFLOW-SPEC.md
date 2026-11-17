# Motion workflow specification

[English](MOTION-WORKFLOW-SPEC.md) | [简体中文](MOTION-WORKFLOW-SPEC.zh-CN.md)

> Executable contract for the dual-account video workflow. This branch was
> established from `origin/main`; the statements below describe the code and
> receipts actually verified for this closeout, not an aspiration. The root-level
> `VIDEO-WORKFLOW-OPTIMIZATION-PLAN.md` is the Owner's draft; this file is the
> canonical version that code and CI point at.

## 1. Boundary

- **Easel v0.3.0 (`bb3c8ff`) is the only episode compositor.** MotionClone is an external tool that
  supplies a short, self-owned clip through a handoff record; its code is not
  copied and its runtime is not merged with `media-use` 0.8.222. The pinned
  engine is frozen; this workflow does not authorize an upstream change.
- VIDEO and GRAPHIC_TEXT are separate lines; this spec covers VIDEO.
- No provider spend, credential use, dependency install, upgrade or
  publication is authorized by this spec. A rendered clip or passing technical
  QC does not authorize production release: `production_ready: false`,
  `publish_authorized: false`, and `human_review: PENDING_FOUNDER_REVIEW` remain
  until the required human review and separate publication authorization.

## 2. Delivered contracts

| Contract | Code | What it enforces |
|---|---|---|
| Motion sample gate | `src/contentops/media/motion_sample.py`, `scripts/check_motion_sample.py` | 2–8 s, silent, 1080×1920, H.264/yuv420p, CFR 30 verified from frame timestamps, digest-bound; `TECHNICALLY_CHECKED` still `PENDING_FOUNDER_REVIEW` |
| Motion handoff | `src/contentops/media/motion_handoff.py` | `project://` only, digest-bound MP4, MotionClone 2.0.0 / HyperFrames 0.8.33, project hashes, ≤8 s source window, internal-only rights, all authority flags false |
| Real-source duration | `src/contentops/media/real_source_duration.py`, `scripts/qc_video.py` | For 1024 evidence-led content, ≥70% of visible output seconds must be rights-usable real-source material (e.g. recordings, screenshots, documents or logs), not necessarily recordings; count visible duration, not shot count, and exclude diagrams, cards, generated and motion renders. Separately, the 1024 production gate requires a registered real cropped recording. Future Intelligence has no recording-duration requirement and forbids manual desktop recording. Overlaps count once. |
| Driver QC binding | `src/contentops/easel/driver.py` | `receipts/qc-report*.json` is resolved at plan time via `_step_receipts_ok`; a matching but ungraded or `FAIL` report is not completion |
| Router → brief → M5 | `src/contentops/routing/`, `src/contentops/script/`, `scripts/content_route.py`, `scripts/brief_to_m5.py`, `scripts/m5_production.py` | account DNA → candidate → approved brief → `script/script.json` + claims + source refs; `copy_review.require_if_brief_driven` blocks an unreviewed brief |
| S4 stage policies | `src/contentops/workflow/{audience,duration,copy_strategy,platform,delivery,visual_route}.py` | audience/duration/strategy/platform limits, manual delivery manifest and visual routing; no publication authority |
| Graphic workflow adapter | `scripts/graphic_workflow.py`, `src/contentops/gzh/runtime.py`, `src/contentops/x/runtime.py` | GZH and X only; locate/hash-verify/describe, manual package surface; no workflow execution, platform API call, draft or publication. The XHS graphic adapter was removed; Xiaohongshu belongs to the VIDEO delivery line. |

### Graphic and editorial workflows (GZH / X)

The GZH workflow is installed by the operator outside the public repository and
is never vendored. X is this repository's own manual-only editorial gate.
`scripts/graphic_workflow.py` accepts `gzh`, `x`, and `video`; the graphic/editorial
routes are only `gzh` and `x` (`status`, `verify`, `plan`). It verifies the
workspace or lock, then describes operator operations. The `video` route lists
supported video destinations without executing a platform workflow. With
`--handoff --project <path>`, it invokes `scripts/video_deliver.py pack` and
`dispatch` for supported video platform IDs derived from the routes (including
Xiaohongshu), building a multi-platform delivery package and dispatch argv. The
handoff still sets `execute=false` and `publish_authorized=false`: it does not run
an uploader and does not authorize publication.
GZH uses the GRAPHIC_TEXT manual package, which stops at
`AWAITING_MANUAL_REVIEW`; X uses the manual post package. XHS has no graphic
adapter or CLI route; Xiaohongshu is handled only as a VIDEO destination.

Rights: GZH has 45 of 50 skills unlicensed, so it remains local internal use only
until cleared. A verified runtime is not a redistribution licence.

## 3. Commands

```bash
python scripts/check_motion_sample.py <sample.mp4> [--sha256 <hex>]
python scripts/graphic_workflow.py status --workflow gzh
python scripts/graphic_workflow.py plan   --workflow x --json
python scripts/graphic_workflow.py status --workflow video --json
python tests/test_motion_sample.py
python tests/test_motion_handoff.py
python tests/test_real_source_duration.py
python tests/test_s4_stages.py

python scripts/content_route.py accounts
python scripts/brief_to_m5.py --check projects/<slug>
python scripts/m5_production.py projects/<slug>
python scripts/qc_video.py projects/<slug> --video <slug>.mp4
python scripts/qc_visual.py projects/<slug> --video <slug>.mp4
```

A motion handoff has no CLI by design: it is a contract that a caller validates
before placing the asset on the one active timeline. A validated record does not
enter M5 by itself.

## 4. Always / Ask / Never

**Always**

- Keep one manifest and one active asset per placement.
- Bind approval to the artifact and upstream digests; a changed Bundle revokes it.
- Keep `production_ready: false`, `publish_authorized: false`, and
  `human_review: PENDING_FOUNDER_REVIEW` until required human review is recorded.
  A technical PASS or rendered film is not Founder acceptance or publication authorization.
- For account `x-superplay-1024`, the DNA's 70% real-recording mix is a
  content target. The separate real-source-duration gate measures rights-usable
  real-source material visible in the finished cut (recordings, screenshots,
  documents, logs, etc.); it does not require all qualifying seconds to be
  recordings. Formal production separately requires a registered real cropped
  recording. Neither gate is satisfied by shot count.
- For `x-superplay-future-intelligence`, manual desktop recording is forbidden;
  there is no minimum recording duration. Do not substitute a desktop capture
  for diagrams or code-focus visuals.
- Keep receipts logical (`project://`, `repo://`), never absolute host paths.
- Register every new `tests/test_*.py` in `.github/workflows/ci.yml`.

**Ask the Owner**

- Any real A/B source clip or third-party derivative.
- Any provider call, spend or credential use.
- Any change to the MotionClone / Easel / media-use pins.
- Any publication or external delivery.

**Never**

- Treat a handoff record as a public-reuse licence.
- Count generated, diagram, card or motion material as real-source seconds.
- Let a technical PASS become a G6 or publication approval.
- Rewrite public history, close an unresolved issue, or delete an archive
  without an explicit decision.

## 5. Blocked work

| Item | Blocker |
|---|---|
| Two real A/B samples | 1024: rights-usable real capture; Future Intelligence: reproducible RAG project and rights-cleared source windows without desktop recording |
| Module expansion and full cut | per-account G6 decisions after the samples |
| Publication | separate manual authorization and a real platform URL |
| GZH/XHS integration | rights, not architecture: XHS excludes one AGPL skill; GZH has 45 unlicensed skills |

## 6. Verification

The offline gate is:

```bash
python tests/test_motion_sample.py
python tests/test_motion_handoff.py
python tests/test_real_source_duration.py
python tests/test_s4_stages.py
python scripts/dev_check.py
```

A green run proves the contracts, not that a real sample exists or is usable.
