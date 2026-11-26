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
| Graphic workflow adapter | `scripts/graphic_workflow.py`, `src/contentops/gzh/runtime.py`, `src/contentops/x/runtime.py` | GZH and X only; locate/hash-verify/describe, manual package surface; no workflow execution, platform API call, draft or publication. Xiaohongshu graphic/image-text is excluded; only the `xiaohongshu_video` VIDEO target is configured. |

### Graphic and editorial workflows (GZH / X)

The GZH workflow is installed by the operator outside the public repository and
is never vendored. X is this repository's own manual-only editorial gate.
`scripts/graphic_workflow.py` accepts `gzh`, `x`, and `video`; the graphic/editorial
routes are only `gzh` and `x` (`status`, `verify`, `plan`). It verifies the
workspace or lock, then describes operator operations. The `video` route lists
supported video destinations without executing a platform workflow. With
`--handoff --project <path>`, it invokes `scripts/video_deliver.py pack` and
`dispatch` for supported video IDs (specifically `xiaohongshu_video` for Xiaohongshu),
building a multi-platform delivery package and dispatch argv. A video target accepts
video material only; this handoff does not convert image-text content into video. The
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
- A routine VIDEO stage advances on a passing machine check. It is recorded as
  `checked`, never as `approved`, and a changed artifact or upstream digest
  retires it. A stage that names a human decision still waits for one. Graphic
  stages are unchanged.
- Rights are reviewed once per source and licence, not once per file. The batch
  names every asset and hash it covers; a request to review is not the review,
  and a changed hash is a new batch.
- Keep `production_ready: false`, `publish_authorized: false`, and
  `human_review: PENDING_FOUNDER_REVIEW` until required human review is recorded.
  A technical PASS or rendered film is not Founder acceptance or publication authorization.
- For account `x-superplay-1024`, the DNA's 70% real-recording mix is a
  content target. The separate real-source-duration gate measures rights-usable
  real-source material visible in the finished cut (recordings, screenshots,
  documents, logs, etc.); it does not require all qualifying seconds to be
  recordings. Formal production separately requires a registered real cropped
  recording. Neither gate is satisfied by shot count.
- For `x-superplay-future-intelligence`, each video chooses a 30–300 s duration based on its topic; 300 s is a hard maximum. Manual desktop recording is forbidden; there is no minimum recording duration. Do not substitute a desktop capture for diagrams or code-focus visuals.
- **Creator-edited copy is authoritative.** When the creator revises an AI-authored draft and says their version is final, preserve their wording verbatim—including spoken fillers, colloquialisms, repetitions and punctuation. Do not unsolicitedly polish, shorten, remove filler words or apply an AI-style rewrite. Change only the exact parts the creator asks to change. Keep storyboard directions, URLs and evidence notes outside spoken lines. If a phrase raises a factual/evidence concern, flag it separately; do not silently rewrite the creator's copy.
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

## 7. B-roll-first production (standard video path)

A narrated VIDEO project must not degrade into a deck of static text cards.
The default path is **registered real media as the main picture**, with the
narration driving shot choice, camera motion and shot duration.

### 7.1 Defaults that must hold

| Setting | Required default | Enforced by |
|---|---|---|
| Narration | MiniMax M Plan cloned voice from the account DNA. SAPI is an explicit diagnostic opt-in only; a missing DNA must never silently degrade to the offline voice. | `m5_production.build` fallthrough (`or "minimax"`); `stage_narration(provider="minimax")` |
| Canvas | The account's reviewed `visual.motion.motion_profile.render_variant`, not the dark-blue `brand.palette`. Accounts declare this once; changing the look needs no code edit. | `motion_planner.build_auto_plan`, `scripts/animation_render.py` `style_variant` |
| Picture | A rights-checked still (real screenshot or generated illustration) is the main picture; information graphics are used only where no truthful still exists. | `scripts/plan_broll.py` |
| Duration | Each shot spans the measured narration slot (this line's start to the next line's start), clamped to the clip 2–8 s contract. Never a fixed guess. | `plan_broll._line_slot` |
| Callout | A 2–6 char semantic keyword anchored to the spoken line. Never a truncated copy of the subtitle (that prints the same sentence twice). | `plan_broll._callout` |
| Evidence labels | Only a licensed/owned real capture may be labelled "证据画面". A generated illustration is "概念示意 · 不是证据"; a locally authored card is never a B-roll picture at all. | `plan_broll._usable_stills` grade filter |

### 7.2 Standard command sequence

```bash
# 1. Build/produce the M5 project up to narration, with the account bound.
python scripts/m5_production.py <project> --skip-compose

# 2. Materialize the B-roll shot plan from registered stills + measured narration.
python scripts/plan_broll.py <project> --json

# 3. Render and compose with the materialized plan.
python scripts/m5_production.py <project>
```

`plan_broll.py` writes `motion/broll/<line>.json`, `motion/broll-plan.json`
(schema `contentops.m5-motion-shots/v1`) and sets `motion.backend: remotion` /
`motion.shot_plan` in `project.yaml`. It fails closed if the project has no
registered stills, no measured narration, no account binding, or no reviewed
render variant. It never renders, approves copy or grants publication.

### 7.3 Rights registration for a generated illustration

Register once, with all five fields, or `verify_assets` will reject it one gate
at a time:

- `repo_path` is **repo-root relative** (`projects/<slug>/...`), not project-relative.
- `permission: CREATED_BY_OWNER`; `license` and `rights.license_id: OWNED-GENERATED-LOCAL`.
- `rights.review_evidence: assets/<id>.rights.json` pointing at a
  `contentops.media-rights-review/v1` record.
- `rights.source_url: local://minimax-m-plan/image-01/<id>` (a non-third-party
  provenance token; an http URL is not required for `OWNED-GENERATED-LOCAL`).
- `rights.synthetic: true`, `reviewed_by`, `reviewed_at` set consistently in both.

### 7.4 Mechanism regression tests

```bash
python tests/test_broll_workflow_mechanism.py
python tests/test_default_narration.py
python tests/test_animation_orchestrator.py
```

These lock in the no-silent-SAPI, reviewed-canvas, evidence-grade, keyword-callout
and measured-duration rules so a future change cannot reintroduce static text
cards or a mechanical voice.
