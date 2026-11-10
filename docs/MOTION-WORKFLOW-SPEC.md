# Motion workflow specification

[English](MOTION-WORKFLOW-SPEC.md) | [简体中文](MOTION-WORKFLOW-SPEC.zh-CN.md)

> Executable contract for the dual-account video workflow. It records what the
> code actually enforces on `main`, not an aspiration. The root-level
> `VIDEO-WORKFLOW-OPTIMIZATION-PLAN.md` is the Owner's draft; this file is the
> canonical version that code and CI point at.

## 1. Boundary

- **Easel v0.2.1 is the only compositor.** MotionClone is an external tool that
  supplies a short, self-owned clip through a handoff record; its code is not
  copied and its runtime is not merged with `media-use` 0.8.222.
- VIDEO and GRAPHIC_TEXT are separate lines; this spec covers VIDEO.
- No provider spend, credential use, dependency install, upgrade or
  publication is authorized by this spec.

## 2. Delivered contracts

| Contract | Code | What it enforces |
|---|---|---|
| Motion sample gate | `src/contentops/media/motion_sample.py`, `scripts/check_motion_sample.py` | 4–8 s, silent, 1080×1920, H.264/yuv420p, CFR 30 verified from frame timestamps, digest-bound; `TECHNICALLY_CHECKED` still `PENDING_FOUNDER_REVIEW` |
| Motion handoff | `src/contentops/media/motion_handoff.py` | `project://` only, digest-bound MP4, MotionClone 2.0.0 / HyperFrames 0.8.33, project hashes, ≤8 s source window, internal-only rights, all authority flags false |
| Real-source duration | `src/contentops/media/real_source_duration.py`, `scripts/qc_video.py` | Apply the account DNA evidence mode: `EVIDENCE_LED` keeps the ≥70% real-visible-seconds floor; `EXPLANATORY` does not use that global ratio as a gate. Missing source, rights, duration or account policy still blocks; evidence and claims remain independently verified. Generated and motion visuals never count as real capture. |
| Driver QC binding | `src/contentops/easel/driver.py` | `receipts/qc-report*.json` is resolved at plan time via `_step_receipts_ok`; a matching but ungraded or `FAIL` report is not completion |
| Router → brief → M5 | `src/contentops/routing/`, `src/contentops/script/`, `scripts/content_route.py`, `scripts/brief_to_m5.py`, `scripts/m5_production.py` | account DNA → candidate → approved brief → `script/script.json` + claims + source refs; `copy_review.require_if_brief_driven` blocks an unreviewed brief |
| S4 stage policies | `src/contentops/workflow/{audience,duration,copy_strategy,platform,delivery,visual_route}.py` | audience/duration/strategy/platform limits, manual delivery manifest and visual routing; no publication authority |
| Graphic workflow adapters | `src/contentops/gzh/runtime.py`, `src/contentops/xhs/runtime.py`, `scripts/graphic_workflow.py` | locate/hash-verify/describe a locally installed GZH or XHS workflow; GRAPHIC_TEXT manual package surface; no execution, draft or publication |
| Huashu Motion adapter | `src/contentops/media/huashu_motion.py`, `scripts/huashu_motion_adapter.py`, `runtime/huashu-motion.lock.json` | verifies the pinned v0.3.1 runtime, describes `om check`/`om still`/`om render`/`om qa` in the upstream's own syntax, writes blocked/not-executed receipts; it never builds an `om` command line and never starts the engine |
| Shared Huashu motion record | `src/contentops/media/huashu_motion.py` (`contentops.huashu-motion-asset/v1`) | one record for both engines: `engine/version/commit/spec_sha256/asset_hashes/clip_path/clip_sha256/duration/resolution/fps/audio_policy/rights/review_status`, always `generated=true`, `evidence_capable=false`, `production_ready=false` |
| Huashu motion → M4.5 | `src/contentops/media/motion_manifest.py`, `src/contentops/media/manifest_m5_bridge.py` | a checked clip becomes a source receipt, an audio-free derived clip and one active timeline placement; a missing clip, a digest mismatch, a changed byte or a `KEEP` policy is refused |
| Huashu managed execution | `src/contentops/skills/huashu_execution.py`, `scripts/huashu_execute.py` | runtime first, then the approval, then the decision, then a re-read, then one consumed use, then the executor; an unusable runtime is blocked without spending a use, and the upstream invocation is injected rather than constructed |

### Graphic and editorial workflows (GZH / XHS / X)

The GZH and XHS workflows are installed by the operator outside the public
repository and are never vendored. X is this repository's own manual-only
editorial gate. `scripts/graphic_workflow.py` is the single entry point
(`status`, `verify`, `plan` for `--workflow gzh|xhs|x`): it verifies the
workspace or lock, then describes the operator operations. It never executes a
workflow step, calls a platform API, starts the Easel host, drafts or publishes.
GZH/XHS use the GRAPHIC_TEXT manual package, which stops at
`AWAITING_MANUAL_REVIEW`; X uses the manual post package.

Rights: XHS root is Apache-2.0 with one AGPL-3.0 skill that must stay excluded;
GZH has 45 of 50 skills unlicensed, so it remains local internal use only until
cleared. A verified runtime is not a redistribution licence.

## 3. Commands

```bash
python scripts/check_motion_sample.py <sample.mp4> [--sha256 <hex>]
python scripts/graphic_workflow.py status --workflow gzh|xhs|x
python scripts/graphic_workflow.py plan   --workflow x --json
python tests/test_motion_sample.py
python tests/test_motion_handoff.py
python tests/test_real_source_duration.py
python tests/test_s4_stages.py

python scripts/content_route.py accounts
python scripts/brief_to_m5.py --check projects/<slug>
python scripts/m5_production.py projects/<slug>
python scripts/qc_video.py projects/<slug> --video <slug>.mp4
python scripts/qc_visual.py projects/<slug> --video <slug>.mp4

python scripts/huashu_motion_adapter.py status
python scripts/huashu_motion_adapter.py plan render
python scripts/huashu_motion_adapter.py request render --project projects/huashu-motion-sample
python scripts/huashu_execute.py check projects/huashu-motion-sample --operation render --account x-superplay-1024
python tests/test_huashu_motion_sample.py
python tests/test_huashu_motion_manifest.py
python tests/test_huashu_execution_gate.py
```

A motion handoff has no CLI by design: it is a contract that a caller validates
before placing the asset on the one active timeline. A validated record does not
enter M5 by itself.

## 3.1 The two Huashu engines

`huashu-motion` (upstream `alchaincyf/huashu-motion`) and `huashu-art-motion`
(upstream `alchaincyf/huashu-art-motion`) are separate programs with separate
runtimes. ContentOps integrates them as **clip producers**, not as a second
compositor: Easel remains the only compositor.

What the integration guarantees:

- One runtime pin per engine, in `runtime/`, checked for version, commit, Git
  remote, clean tree, entrypoint and licence. A missing file, an escaped path,
  a version drift and a dirty tree are separate verdicts.
- One asset record for both engines (`contentops.huashu-motion-asset/v1`), so a
  consumer never branches on the engine to read a duration or a digest.
- One technical gate for both (`check_motion_clip`): silent, 1080×1920,
  H.264/yuv420p, constant 30 fps verified from frame timestamps, digest-bound.
  A technically checked clip is still `PENDING_FOUNDER_REVIEW`.
- One path into M4.5: the checked clip becomes a source receipt and an
  audio-free derived clip, and only the derived clip may be activated on the
  timeline.
- Generated motion stays `generated=true`, `evidence_capable=false`. It may be a supplementary visual on a factual line only when the separate `ClaimLedger` independently verifies that claim. The generated asset itself must have no `claim_refs`, `evidence_use: EVIDENCE`, or evidence-capable flag; the M5 stage rejects those contradictions.
- A real manifest-driven M5 composition refuses generated motion whose source receipt has unresolved or incomplete rights. Fixture assets may pass only in a project explicitly marked `fixture: true`; the resulting receipt remains fixture-only and never grants publication or production readiness.

What it does not do: it does not start `om`, it does not build an upstream
command line, it does not install a runtime, and it does not compose. A real
render needs the Owner's approval record; the request is
`docs/governance/HUASHU-EXECUTION-AUTHORIZATION-REQUEST.md`.

The pinned `skills/huashu-motion/references/contract.md` requires a composition
root with `data-composition-id`, `data-width`, and `data-height`; a paused GSAP
timeline registered at `window.__timelines[composition-id]`; and `scene:<id>`
labels. `data-om-id` marks pointable regions only. The current CSS-keyframe
`index.html` lacks those native structures and is explicitly
`NOT_HUASHU_MOTION_COMPATIBLE`; no `om` command may be run against it. The
contract/runtime documents deterministic time-driven rendering, but the draft
has no registered paused timeline to provide that behavior. `om render --silent`
suppresses the no-soundtrack warning; it does **not** prove the output has no
audio stream. Verify actual audio-stream absence with ffprobe after rendering or
after the existing `AudioPolicy` transform.

### The prepared sample

`projects/huashu-motion-sample` is a 21 s **design**, not a film: storyboard
and shot rhythm, one unified visual spec, six Art Motion clip specs, the
Huashu Motion HTML concept draft, and the M4.5 asset mapping. The first Art
Motion shot is 4.0 s; the remaining five are 3.4 s each. This prepares a first
4–8 s motion-sample candidate without changing `motion_sample.py`; the other
beats use the ordinary per-clip gate, not the sample gate. The Huashu Motion
HTML remains non-compatible until rewritten to its native contract. Nothing has
been rendered, so the sample is `RENDER_NOT_VERIFIED`. Its topic is an original
abstract AI Agent workflow; it uses no real screenshot or third-party material.

## 4. Always / Ask / Never

**Always**

- Keep one manifest and one active asset per placement.
- Bind approval to the artifact and upstream digests; a changed Bundle revokes it.
- Record `production_ready: false` and `human_review: PENDING_FOUNDER_REVIEW`
  until a person signs.
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
| Two real A/B samples | real task recording / reproducible RAG project and rights-cleared source windows |
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
