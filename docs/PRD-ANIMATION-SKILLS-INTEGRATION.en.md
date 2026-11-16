# PRD — Animation skills and multi-engine clip rendering

[简体中文](PRD-ANIMATION-SKILLS-INTEGRATION.md) | [English](PRD-ANIMATION-SKILLS-INTEGRATION.en.md)

> Last verified: 2026-11-17
> Status: **P0 clip render implemented.** Remotion short clips rendered locally and dispatched from M5. Motion Canvas and Manim are BLOCKED, not VERIFIED. A DNA-driven 3s conflict `title_card` and a trusted render cache were added and verified locally on 2026-11-17.
> A generated clip is not a screen recording and does not replace Founder review.

## 1. Background, goals, non-goals

ContentOps already has a frozen Easel v0.3.0 compositor, Huashu explanatory clips, evidence gates, and two account DNAs. What was missing is a clip renderer chosen by shot type, handed back to the existing timeline.

Goal: keep Easel as the only episode compositor and add an auditable short-clip renderer. P0 is pinned Remotion. Huashu stays available.

Non-goals: upgrading Easel; a second timeline; installing all 18 surveyed repositories; vendoring Remotion source; paid generation; automatic publishing; relaxing human review or the real-recording ratio.

## 2. What is reused

`stage_motion` dispatches an explicit `remotion` shot to `scripts/animation_render.py`. `motion_sample.py` remains the 2–8s silent 1080×1920 H.264 yuv420p 30fps gate. `motion_handoff.py` stays MotionClone-only. Account palettes are read from DNA. Generated clips use `source_kind=vector_animation` and do not count toward the 70% real-recording share. `assemble_easel.run` remains the only episode compose entry.

## 3. Eighteen upstream projects

Audited 2026-11-16 from `gh api`. None archived. Remotion's GitHub SPDX is `NOASSERTION` because the license is custom; `LICENSE.md` was read separately.

| # | Repository | What it is | License | Decision |
|---|---|---|---|---|
| 1 | remotion-dev/skills | Agent skill pack, not a renderer | no separate license object; content is Remotion 4.0.543 | P0 skill layer; install locally; do not commit the text |
| 2 | motion-canvas/motion-canvas | Vite editor | MIT | P1; BLOCKED this round (no headless CLI) |
| 3 | motiondivision/motion | React tween library | MIT | REJECT |
| 4 | franciscop/ola | number interpolation | MIT | REJECT |
| 5 | juliangarnier/anime | JS animation engine | MIT | REJECT |
| 6 | ManimCommunity/manim | Python math animation | MIT | P1; BLOCKED (not installed; cairo/pango) |
| 7 | jeremyckahn/shifty | tween engine | MIT | REJECT |
| 8 | jonobr1/two.js | 2D drawing API | MIT | REJECT |
| 9 | airbnb/lottie-web | animation player | MIT | P2 |
| 10 | CreateJS/TweenJS | tween library | MIT | REJECT |
| 11 | lume/lume | 3D HTML elements | MIT | REJECT |
| 12 | mattdesl/gifenc | GIF encoder | MIT | P2 |
| 13 | konvajs/konva | canvas scene graph | NOASSERTION | REJECT |
| 14 | blender/blender | full DCC | API NOASSERTION; do not guess GPL | REJECT |
| 15 | mrdoob/three.js | 3D library | MIT | REJECT; later consider `@remotion/three` |
| 16 | godotengine/godot | game engine | MIT | REJECT. The releases API's first object was `3.6.3-stable`; that is not proof of the newest tag |
| 17 | BabylonJS/Babylon.js | game/render engine | Apache-2.0 | REJECT |
| 18 | drawcall/Proton | particle library | MIT | REJECT |

Side fact: `remotion-dev/remotion` latest release is **v4.0.543** (2026-11-11). This machine has Node v24.16.0, npm 11.13.0, FFmpeg 8.1.1, Chrome, and Edge. Manim is not installed.

## 4. Selection and license

Remotion is P0 because it emits MP4, Node and Chrome are present, and the license text allows an individual or a for-profit organization of up to 3 employees to create videos. Selling a Remotion derivative is not allowed. This repository commits its own templates and the lockfile, not `node_modules` and not upstream source.

Motion Canvas and Manim are MIT. They are blocked this round by runtime shape, not by license: no headless exporter, and no local cairo/pango environment. A missing runtime is not marked VERIFIED.

## 5. Order

M0 environment is partial: Node, FFmpeg, and Chrome were checked. `npx skills add` was refused by the local permission classifier, so the skill pack is not installed. M1 Remotion is done at 4.0.543. M2 is BLOCKED. M3 account rules are enforced in the selector. M4 does not rewrite the workbench UI; the skill registry gains a discovery pointer only.

## 6. Two accounts

1024 stays 70/25/5 recording, vector, comparison card, 45–60 seconds. A generated clip cannot satisfy production without a cropped recording (`MISSING_REAL_RECORDING`). A test-purpose render is allowed and labeled as not an accepted case.

Future-intelligence stays 70/25/5 vector, code, chart, 90–120 seconds. A desktop or manual recording input is `RECORDING_FORBIDDEN`. The RAG sample caption says it is a principle diagram, not system output, and contains no performance numbers.

A missing or unknown account is blocked. Palettes are not copied across accounts.

## 7. Architecture

Shot spec and account DNA go through `select_backend`, then `scripts/animation_render.py` renders one clip, then Easel composes the episode. Huashu keeps its own adapter. The new backends are clip renderers only.

## 8. Interface

`select_backend`, `preflight`, `plan_clip`, `build_receipt`, `resolve_skill`, and `production_gate` live in `src/contentops/media/animation_backend.py`. Process spawning stays in `scripts/animation_render.py` via `hidden_run`. Receipts accept only `project://` paths. An explicit backend is never replaced unless the caller listed a compatible fallback and that fallback is ready.

## 9. Skills

The shared skill store and `~\.claude\skills` were not modified. The official installer was refused, so skill installation is **NOT_INSTALLED**, not PASS. The registry id `contentops-remotion-clips` points at this repository's templates and does not authorize execution. Pin: `runtime/remotion.lock.json`, Remotion 4.0.543.

```text
npm install --ignore-scripts --no-audit --no-fund --prefix extensions/animation-remotion
```

Do not pull `latest` at render time.

## 10. Easel and Huashu

The Easel pin remains v0.3.0 / `bb3c8ff`. Huashu aliases still resolve to Huashu. A `remotion` configuration without `motion.shot_plan` does not fall through to the Huashu auto-plan.

## 11. M5

`stage_motion` calls `animation_render.py` for `remotion`, `motion-canvas`, and `manim`. Failure is `M5Blocked`, not a Huashu substitution. The dispatch test asserts the command contains the clip adapter and not `huashu_motion`.

## 12. Asset class

Generated animation is visual support, not evidence, not a real recording, and not commercially cleared. The rights field is `GENERATED_LOCAL_NO_COMMERCIAL_CLEARANCE`.

## 13. Platforms

No new platform table. `config/platforms/video-platforms.yaml` and `scripts/platform_adapt.py` stay the source. This change does not activate undeclared platforms and does not treat a packed file as a published post. `x-superplay-english` is not a third video brand.

## 14. Safety and review

Local non-paid rendering and a project-level npm install were in scope. Easel was not upgraded. No credentials, MiniMax calls, or publishing. Technical QC leaves `human_review` at `PENDING_FOUNDER_REVIEW`.

## 15. Tests

`tests/test_animation_backend.py` is registered in `.github/workflows/ci.yml`. It does not render video. Existing `tests/test_m5_motion_integration.py` passed 56/56 locally.

## 16. Acceptance

| Item | Status | Evidence |
|---|---|---|
| 18-project audit | PASS | section 3 |
| PRD | PASS | this file and the Chinese original |
| Remotion skills install | FAIL | `npx skills add` refused; shared store untouched |
| Remotion render | PASS | table below |
| Motion Canvas | BLOCKED | `NO_HEADLESS_EXPORT` |
| Manim | BLOCKED | `missing manim`; system Python was not modified |
| 1024 rules | PASS | production without a recording is `MISSING_REAL_RECORDING` |
| Future-intelligence rules | PASS | desktop recording is `RECORDING_FORBIDDEN` |
| M5 wiring | PASS | dispatch test and selector |
| Easel regression | PASS | pin unchanged; Huashu suite 56/56 |
| Platforms | PASS | registry not rewritten into a publish claim |
| Review and safety | PASS | `production_ready=false`, `publish_authorized=false` |

Local renders (gitignored, `projects/_local/`):

| Clip | sha256 | ffprobe |
|---|---|---|
| 1024 annotation test | `4c31e531dbed90070b5d61159acf56f07a70d56a009167cbd1d483ac11327b62` | h264, 1080x1920, yuv420p, 30/1, 4.000s, no audio |
| Future-intelligence RAG | `417019d985f440b4f910f91ed37192118353e01c1b0a5f66b78ca67568c067c0` | h264, 1080x1920, yuv420p, 30/1, 6.000s, no audio |

Receipts use `project://` paths only.

## 17. Risk and rollback

If the organization grows past 3 employees, stop rendering until a Remotion company license exists. Windows Chrome launch uses `--gl angle`. Transcode forces `yuv420p` and `color_range tv` because `yuvj420p` fails the sample gate.

Rollback is deleting the clip-dispatch branch in `stage_motion` plus `extensions/animation-remotion` and the lockfile. Huashu and the Easel pin do not depend on them. Do not touch `.runtime/easel-v030`.

## 19. DNA conflict hook and trusted clip cache (2026-11-17)

This section is independent of the Huashu six-template work tracked in Issue #192 / PR #193. It adds no second timeline and no new brand config.

**Conflict title card.** `title_card` was declared in `SHOT_COMPATIBILITY` but had no composition or render route. `extensions/animation-remotion/src/TitleCard.tsx` fills that gap: a 3s hook card for the 1024 account. Every colour resolves from the account DNA palette (`animation_backend.palette_from_dna`), including the `problem` token copied from `brand.palette.problem`. A shot spec cannot inject a colour or an evidence claim — `plan_clip` drops `claim`, `source_refs`, `recording_asset_id` and any recording path before planning, and the card is always `generated=true`, `evidence_capable=false`, `counts_as_real_recording=false`. Motion is fade/slide only, matching both accounts' `forbidden_effects`. Frame inspection found body text on the dark DNA base was unreadable with the `ink` token; body copy now uses the DNA `surface` token. No colour is hardcoded in the component.

**Trusted clip cache.** `animation_render.py` previously computed a fingerprint but never used it to skip a render (`reused` was always False). `animation_backend.clip_fingerprint` now binds backend version, template, account, placement, asset, purpose, duration, props, the full DNA digest, referenced source digests and a digest of the composition sources (`src/*.tsx` + `package.json`). A cached clip is replayed only when the fresh fingerprint matches the sidecar, the file's actual SHA-256 still equals the recorded hash, and the sample still passes `check_motion_sample`. A filename match alone is never a hit. A DNA, parameter, source, template or version change invalidates the cache.

**Local verification (2026-11-17, Remotion 4.0.543, Chrome, FFmpeg 8.1.1):**

| Sample | Template | Path (logical) | SHA-256 | ffprobe |
|---|---|---|---|---|
| 1024 conflict hook | `title_card` | `project://assets/generated/remotion/clip-title-hook.mp4` | `9c1b5d54f7e5d55bd4251a8eb740cf032f48734da52e7ace18f1cda098a8657c` | h264, 1080x1920, yuv420p, 30/1, 3.000s, no audio |
| Future-intelligence RAG | `rag_flow` | `project://assets/generated/remotion/clip-rag-fi.mp4` | `c9582e235e103d948cef0c62e5ea961eb577a7a62afba3dc750c97e121ce9730` | h264, 1080x1920, yuv420p, 30/1, 6.000s, no audio |

`python tests/test_animation_backend.py` passed 34/34. `tsc --noEmit` passed. Re-running the identical render returned `state=REUSED, reused=true` with the same SHA; changing `duration_s` from 3 to 4 returned `EXECUTED` with a new fingerprint and SHA; editing the template source invalidated the title-card cache and forced a fresh render. A frame was extracted and visually inspected before and after the contrast fix.

**Acceptance limits.** Both samples are `purpose=test`, `TEST_PURPOSE` gate, `production_ready=false`, `publish_authorized=false`, `human_review=PENDING_FOUNDER_REVIEW`. No user-provided 1024 recording exists, so 1024 production remains `MISSING_REAL_RECORDING`. The future-intelligence RAG nodes are a principle illustration (`原理示意，非真实系统输出`), not a real system trace. No full episode was composed and no video was published.
