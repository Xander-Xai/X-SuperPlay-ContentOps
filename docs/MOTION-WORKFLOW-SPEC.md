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
| Real-source duration | `src/contentops/media/real_source_duration.py`, `scripts/qc_video.py` | ≥70% of the rendered file's visible seconds are real capture; diagrams, cards, generated and motion renders are excluded and overlaps count once |
| Driver QC binding | `src/contentops/easel/driver.py` | `receipts/qc-report*.json` is resolved at plan time via `_step_receipts_ok`; a matching but ungraded or `FAIL` report is not completion |
| Router → brief → M5 | `src/contentops/routing/`, `src/contentops/script/`, `scripts/content_route.py`, `scripts/brief_to_m5.py`, `scripts/m5_production.py` | account DNA → candidate → approved brief → `script/script.json` + claims + source refs; `copy_review.require_if_brief_driven` blocks an unreviewed brief |
| S4 stage policies | `src/contentops/workflow/{audience,duration,copy_strategy,platform,delivery,visual_route}.py` | audience/duration/strategy/platform limits, manual delivery manifest and visual routing; no publication authority |

## 3. Commands

```bash
python scripts/check_motion_sample.py <sample.mp4> [--sha256 <hex>]
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
