# PRD — Animation skills and multi-engine clip rendering

[简体中文](PRD-ANIMATION-SKILLS-INTEGRATION.md) | [English](PRD-ANIMATION-SKILLS-INTEGRATION.en.md)

> Last verified: 2026-11-17
> Status: **Backend and template acceptance must be assessed against current source; production and publication remain unauthorized.** Local runtime checks and historical renders do not establish universal installation status; CI contract tests do not equal real-media acceptance or production readiness. Remotion, Manim, Huashu and Motion Canvas evidence/limits are described below. The Motion Canvas `mc-arch01` export only proves historical media acceptance for its then-current template; the source has changed, and `capability-matrix-after-export.json` now explicitly reports `STALE_SOURCE_TEMPLATE`. Re-acceptance of the current template requires a new editor export and verification. `mc-state01` also requires editor export. No status grants production, publication or human-review approval.
> A generated clip is not a screen recording and does not replace Founder review.

## 1. Background, goals, non-goals

ContentOps already has a frozen Easel v0.3.0 compositor, Huashu explanatory clips, evidence gates, and two account DNAs. What was missing is a clip renderer chosen by shot type, handed back to the existing timeline.

Goal: keep Easel as the only episode compositor and add an auditable short-clip renderer. P0 is pinned Remotion. Huashu stays available.

Non-goals: upgrading Easel; a second timeline; installing all 18 surveyed repositories; vendoring Remotion source; paid generation; automatic publishing; relaxing human review or the real-recording ratio.

## 2. What is reused

`stage_motion` dispatches an explicit `remotion` shot to `scripts/animation_render.py`. `motion_sample.py` remains the 2–8s silent 1080×1920 H.264 yuv420p 30fps gate. `motion_handoff.py` stays MotionClone-only. Account palettes are read from DNA. `motion_planner.py` now supports six DNA-constrained Huashu shot templates in the existing shot plan/spec contract; it does not create a second timeline. `real_source_duration.py` measures visible real-source seconds against the ≥70% floor for 1024 evidence-led production; `vector_animation` never counts. Future Intelligence has no recording-duration minimum and forbids manual desktop recordings. `assemble_easel.run` remains the only episode compose entry.

## 3. Eighteen upstream projects

Audited 2026-11-16 from `gh api`. None archived. Remotion's GitHub SPDX is `NOASSERTION` because the license is custom; `LICENSE.md` was read separately.

| # | Repository | What it is | License | Decision |
|---|---|---|---|---|
| 1 | remotion-dev/skills | Agent skill pack, not a renderer | no separate license object; content is Remotion 4.0.543 | P0 skill layer; install locally; do not commit the text |
| 2 | motion-canvas/motion-canvas | Vite editor + browser playback | MIT | 3.17.2 (2024-12-14, npm `latest`); editor websocket export, no headless CLI; P3-B templates + adapter implemented, `EDITOR_EXPORT_REQUIRED` |
| 3 | motiondivision/motion | React tween library | MIT | REJECT |
| 4 | franciscop/ola | number interpolation | MIT | REJECT |
| 5 | juliangarnier/anime | JS animation engine | MIT | REJECT |
| 6 | ManimCommunity/manim | Python math animation | MIT (v0.22.1) | P3-A; installed in isolated venv and rendered locally; IMPLEMENTED_NOT_VERIFIED |
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

Historical environment observation from 2026-11-16: Node v24.16.0, npm 11.13.0, FFmpeg 8.1.1, Chrome and Edge were detected on the user's machine at that time. Manim v0.22.1 was detected in an isolated venv (`runtime/manim.lock.json` records the path and creation command), not system Python. These observations apply only to that environment check, **not to universal installation or present availability**.

## 4. Selection and license

Remotion was selected for P0 because it emits MP4 and Node/Chrome were detected on the user's machine at the time; its license text allows an individual or a for-profit organization of up to 3 employees to create videos. Selling a Remotion derivative is not allowed. This repository commits its own templates and the lockfile, not `node_modules` and not upstream source. That environment observation does not establish current or other-machine availability.

Motion Canvas and Manim are MIT-licensed. Motion Canvas is integrated with templates and an adapter, but official export must be initiated from the editor and has no unattended CLI; this constrains automation, not integration status. Its current-template media acceptance is described in section 20: the old `mc-arch01` export is stale after the source template changed, so the current template must be exported again from the editor. Manim was previously rendered locally through the official `python -m manim` from an isolated venv, recorded as v0.22.1; scenes use Pango `Text`, not MathTex/LaTeX (the historical record says LaTeX hung under Windows elevated privileges). An installed runtime or historical local render is not VERIFIED; the capability matrix accepts only receipt-backed evidence consistent with current source and status.

## 5. Order (historical phase record; not a statement of current general readiness)

| Phase | Historical record | Current interpretation |
|---|---|---|
| M0 environment | Node, FFmpeg and Chrome were once checked on the user's machine; `npx skills add` was refused by that machine's permission classifier | One-time local observation, not other environments' or current installation status; the skill-install record is historical, not universal |
| M1 Remotion | Historical record of 4.0.543 lock, templates and local render | The lock establishes a pinned version; a local render is historical/test evidence, not standalone production acceptance |
| M2 Motion Canvas / Manim | Previously recorded blocks, installs and local renders | See sections 20–22; status follows current source and verifiable receipts |
| M3 two accounts | Account contracts and block tests were recorded as passing | Tests establish contracts only; real media, full-film QC and Founder review remain separate |
| M4 workbench | No full-page UI; registry has a discovery pointer | No upstream Easel change or Web UI rewrite; discovery does not authorize execution |

## 6. Two accounts

1024: the account content target is 70% real screen recording, 25% vector animation, and 5% comparison cards; 45–60 seconds. **Keep two gates distinct:** the DNA's ≥70% recording mix is a content target; `real_source_duration.py` measures rights-usable real-source material visible in the finished cut (which may include recordings, screenshots, documents, logs, etc.), not a requirement that ≥70% be recordings, and not a shot-count ratio. Separately, `production_gate()` requires a registered real cropped recording; without one, `purpose=production` returns `MISSING_REAL_RECORDING`. Animation is supporting visual material: `source_kind=vector_animation`, `generated=true`, `evidence_capable=false`, `counts_as_real_recording=false`. Test-purpose renders are allowed but are not accepted cases.

Future Intelligence: target mix 70% vector animation, 25% code, 5% chart; choose 30–300 seconds per video based on the topic, with a hard five-minute ceiling. **Manual desktop recording is forbidden**; desktop/manual recording input returns `RECORDING_FORBIDDEN`. Do not substitute desktop capture for diagrams or code visuals. The RAG sample caption says “principle illustration, not system output” and contains no unverified performance numbers.

These percentages are account content targets; the 1024 recording floor is a formal-production gate, while Future Intelligence has no minimum recording share and forbids manual desktop recording.

A missing or unknown account is blocked. Palettes are not copied across accounts.

## 7. Architecture

Shot spec and account DNA go through `select_backend`, then `scripts/animation_render.py` renders one clip, then Easel composes the episode. Huashu keeps its own adapter. The new backends are clip renderers only.

## 8. Interface

`select_backend`, `preflight`, `plan_clip`, `build_receipt`, `resolve_skill`, and `production_gate` live in `src/contentops/media/animation_backend.py`. Process spawning stays in `scripts/animation_render.py` via `hidden_run`. Receipts accept only `project://` paths. An explicit backend is never replaced unless the caller listed a compatible fallback and that fallback is ready.

`production_gate()` checks technical gates, not production release or publication permission. Even when rendering and technical QC succeed, real-source/rights/evidence gates, full-film quality acceptance, and human Founder review are still required. Until the corresponding human sign-off and separate publication authorization, keep `production_ready=false`, `publish_authorized=false`, and `human_review=PENDING_FOUNDER_REVIEW`.

## 9. Skills

The shared skill store and `~\.claude\skills` were not modified. The official installer was refused, so skill installation is **NOT_INSTALLED**, not PASS. The registry id `contentops-remotion-clips` points at this repository's templates and does not authorize execution. Pin: `runtime/remotion.lock.json`, Remotion 4.0.543.

```text
npm install --ignore-scripts --no-audit --no-fund --prefix extensions/animation-remotion
```

Do not pull `latest` at render time.

## 10. Easel and Huashu

The Easel pin remains v0.3.0 / `bb3c8ff`. Huashu aliases still resolve to Huashu. A `remotion` configuration without `motion.shot_plan` does not fall through to the Huashu auto-plan.

## 11. M5

`stage_motion` calls `animation_render.py` for `remotion` and `motion-canvas`. A `manim` shot uses its declared render entry `scripts/manim_render.py`, rendered from the isolated venv; it reuses the same backend selector, receipt, trusted cache, M45 manifest, and asset-registration contracts — no second system. Failure is `M5Blocked`, not a Huashu substitution. The dispatch test asserts the command contains the clip adapter and not `huashu_motion`.

## 12. Asset class

Generated animation is visual support, not evidence, not a real recording, and not commercially cleared. The rights field is `GENERATED_LOCAL_NO_COMMERCIAL_CLEARANCE`.

## 13. Platforms

No new platform table. `config/platforms/video-platforms.yaml` and `scripts/platform_adapt.py` stay the source. This change does not activate undeclared platforms and does not treat a packed file as a published post. `x-superplay-english` is not a third video brand.

## 14. Safety and review

Local non-paid rendering and a project-level npm install were in scope. Easel was not upgraded. No credentials, MiniMax calls, or publishing. Technical QC leaves `human_review` at `PENDING_FOUNDER_REVIEW`.

## 15. Tests

These are historical test records: `tests/test_animation_backend.py` was registered in `.github/workflows/ci.yml` and does not render video. The historical PR #188 baseline was 56/56; Huashu integration 58/58 and real-source duration 19/19 were also recorded. These results apply to their respective time/commit and do not prove current code, current real media, or production readiness.

## 16. Acceptance

| Item | Status | Evidence |
|---|---|---|
| 18-project audit | Historical record | Section 3 |
| PRD | Document record | This file and Chinese mirror |
| Remotion skills install | Historical check: refused | `npx skills add` was refused; current or other-machine install state cannot be inferred |
| Remotion render | Historical local TEST_ONLY evidence | Local samples are not production acceptance |
| Motion Canvas | `STALE_SOURCE_TEMPLATE` | Old `mc-arch01` export/matrix is historical; current template needs a new editor export and acceptance; `mc-state01` also requires editor export |
| Manim | Historical TEST_ONLY / `IMPLEMENTED_NOT_VERIFIED` | Previously rendered in isolated environment; not universal installation or production readiness |
| 1024 rules | Contract record | Formal production without real recording remains `MISSING_REAL_RECORDING`; test clips do not count as recording |
| Future Intelligence rules | Contract record | Manual desktop recording is `RECORDING_FORBIDDEN` |
| M5 wiring | Code/test record | Dispatch tests do not mean media acceptance |
| Easel | Current pin `v0.3.0` / `bb3c8ff` | Pin is frozen; runtime installation is not universal |
| Human review and safety | Mandatory boundary | `production_ready=false`, `publish_authorized=false`, Founder review pending |

**Remotion, Manim and Huashu output records below are historical local/TEST_ONLY artifacts.** They show what was generated and recorded at the time, not current machine availability, verified real-source evidence, full production QC, or publication readiness.
|---|---|---|
| 1024 annotation test | `4c31e531dbed90070b5d61159acf56f07a70d56a009167cbd1d483ac11327b62` | h264, 1080x1920, yuv420p, 30/1, 4.000s, no audio |
| Future-intelligence RAG | `417019d985f440b4f910f91ed37192118353e01c1b0a5f66b78ca67568c067c0` | h264, 1080x1920, yuv420p, 30/1, 6.000s, no audio |

Receipts use `project://` paths only.

## 17. Risk and rollback

If the organization grows past 3 employees, stop rendering until a Remotion company license exists. Windows Chrome launch uses `--gl angle`. Transcode forces `yuv420p` and `color_range tv` because `yuvj420p` fails the sample gate.

Rollback is deleting the clip-dispatch branch in `stage_motion` plus `extensions/animation-remotion` and the lockfile. Huashu and the Easel pin do not depend on them. Do not touch `.runtime/easel-v030`.

## 18. DNA-driven Huashu shot templates (Issue #192)

This round extends Huashu Art Motion inside the existing M5 shot-plan/spec chain. It adds no second timeline, asset registry, or compositor. `motion_planner.py` resolves the effective DNA palette from `brand.palette`; the palette, refresh declaration, and visual inputs participate in plan identity. Legacy `motion_profile.style_variants` cannot override a declared brand palette, and an unsupported refresh target fails closed.

| Explicit `animation_type` | Huashu grammar | Inputs and rejection boundary |
|---|---|---|
| `architecture_flow` | `y3_whiteboard` | 2–6 nodes drawn as a one-way flow |
| `state_transition` | `y3_whiteboard` | 2–5 states plus required transition, success, and failure labels |
| `code_focus` | `t2_keynote_ui` | A `CODE_SNAPSHOT` image bound to `source_document_sha256`, with an in-frame focus rectangle |
| `evidence_zoom` | `t2_keynote_ui` | A registered real still and source-bound region; Future Intelligence rejects recording inputs |
| `metric_transition` | `t3_finance_chart` | A JSON source record whose title, unit, citation, and every label/value exactly match; only bar/line |
| `comparison_reveal` | `y3_whiteboard` | Explicit before/after labels, using cross/check icons |

Every template requires a registered asset, repository-contained path, byte SHA-256, permission, and either claim/source references or `editorial_only=true`. Specs record `animation_type`, `source_asset_id`, claim/editorial relationship, and source hash; changes to brand colors or source bytes invalidate the affected spec cache. Generated motion is explanatory, never a proof shot; it remains `generated=true`, `evidence_capable=false`, and `evidence_use=VISUAL_SUPPORT`. Claim/source gates remain independent. The 1024 `EVIDENCE_LED` 70% visible-real-material floor applies only to that account's formal evidence-led production and is not relaxed for `tech_review` or similar types. Future Intelligence explanatory clips do not require recording duration and must not include manual desktop recording; factual claims still need sources.

**Acceptance boundary for this update:** the six template contract and rejection tests pass. The shared planner now changes drawing ink only for `y3_whiteboard` on a dark canvas (relative luminance < 0.25) when ink/background contrast is below 3:1, and only to an explicitly declared account-DNA `surface` token that itself reaches at least 3:1. Other colors remain unchanged. Light `t2_keynote_ui` code cards and already-readable whiteboards are unaffected; a missing or insufficient token fails closed. The planner source hash participates in plan identity, adjusted spec bytes participate in the existing per-shot Huashu cache fingerprint, and each applied change is recorded in `contentops_scene.readability_adjustment` with old/new ink, background, and before/after contrast. Fresh-project planner tests cover both 1024 and Future Intelligence. A real five-second Future Intelligence Huashu short clip was also rendered under `projects/_local/animation-readability-20261117/`: source SHA-256 `fc3863e64a7947ea7484f7f2b9298532d0a15392dfee1d7ef3b7d119676d7bb8`, spec SHA-256 `7d3096ad2471d8e6f80a14c09f0d5a6626cc3d0c428934708ca318e872c40554`, H.264 / 1080×1920 / yuv420p / 30fps / 150 frames / silent, clip SHA-256 `dc1e4c5240e5330985fcd35df36b3143764160978f798645ef8affc057e8057c`; short-sample technical QC was `TECHNICALLY_CHECKED`. Easel v0.3.0 composed the clip; final composite SHA-256 `e4a91c30ddfcdcf0e7902ffee64de7f4bc655d273fd27bb6cae9cbb6d12ac5fb`, with short-sample technical QC passed. The experiment's `receipts/readability-lineage.json` links the old 99-second records (original SHA `66ca2673dd915fad41bb6acde1396e5017be17b09bbde389538abc4f4cd24905`; historical parameter-rerender SHA `3aafc7290e16f8f28b08f858dab9a6df5757518ae53abd924684f434ed1f3511`) to this new five-second spec/clip/composite. No old media or receipt was overwritten, but those files are currently inaccessible; the old SHAs remain historical records and were not reverified in this turn. Human visual readability review of the frame remains pending; this is not full-film production QC or release acceptance. The M5 motion integration suite is 61/61 and source-anchor regressions are 6/6. Formal 1024 production still requires a real recording. All outputs remain `production_ready=false`, `publish_authorized=false`, and `human_review=PENDING_FOUNDER_REVIEW`.
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

### 19.1 Pre-merge hardening (2026-11-17, same branch)

Three issues found during PR #195 review were fixed without new features:

1. **Cache reuse no longer skips M5 registration.** A cache hit now audits the canonical receipt plus `sources/assets.json`, `script/assets.json` and the m45 media manifest against the trusted MP4's fingerprint and on-disk SHA-256. Missing or stale rows are repaired by re-running the existing idempotent `register_generated_clip` and re-audited; a present row that contradicts the bytes or escalates `generated`/`evidence_capable`/`production_ready`/`publish_authorized`/human review is **BLOCKED**, never overwritten. `REUSED` now carries `registration_repaired` and the repaired row names. The canonical receipt carries a `fingerprint`; the sidecar carries `source_spec` so repair can rebuild faithfully.
2. **Cache identity covers all real inputs.** `_template_digest` now hashes `package.json`, `package-lock.json`, `tsconfig.json` and every `src/**/*.tsx|ts`; `_source_digests` collects SHA-256 references recursively from nested props. A lockfile change, a nested component, or a source hash hidden in a list now invalidates the cache.
3. **TitleCard obeys DNA layout.** `hook_visual_contract` derives font, caption size, 18-char line limit, 120px vertical margin and 0.07 side ratio from the account DNA; a shot spec's font/margin/effect overrides are stripped and hook text longer than 3× the line limit is refused (`DNA_VISUAL`). Body copy uses the DNA `surface` token for contrast on the dark base. A production spec cannot inject a test banner.

Verification: `test_animation_backend.py` 37/37, new `tests/test_animation_cache_integrity.py` 11/11 (deletion/tampering of every registration artifact), `tsc --noEmit` pass. Real TEST_ONLY renders: long-hook 3s clip SHA-256 `18556d0894c2f8798c4c106978fa651e00807109467f9b4cb4571abf40f48c6a` and refreshed hook clip `62d2f2b20ea7f7b5d762ffc4b760bdad2bf734a7e1636e2183b374495cc10e6e`, both h264/1080x1920/yuv420p/30fps/no audio; frame extraction confirmed wrapping, safe margins and readable contrast. Acceptance limits unchanged: TEST_PURPOSE, production_ready=false, publish_authorized=false, human review pending.

### 19.2 Multi-shot shared-manifest merge (2026-11-17, same branch)

PR #195 review found that `register_generated_clip` rewrote the whole `work/m45/remotion-media-manifest.json` with a single `[envelope]` each time, while the 19.1 registration audit requires the current clip to exist in that manifest. When one project generates clips A and B back to back, the latter overwrites the former, cache hits repeatedly trigger REPAIRABLE, and the repairs destroy each other (ping-pong). Reproduced first with the existing logic for real (two asset_ids, two placements, real renders A→B→A→B): after B registered, A's envelope vanished; after A's cache-hit repair, B's vanished in turn. The MP4s, source rows and canonical receipts all survived (they already merge); only the shared manifest lost data.

The fix keeps the M5 single asset list and timeline contract — no second system: `register_generated_clip` now merges the current envelope into the existing manifest by `asset_id` — same id replaces in place (keeping declaration order and the timeline's stable choice), every other envelope and its gate state are carried as-is, the timeline is rebuilt by `build_manifest`/`build_timeline` (exactly one active asset per placement), and `scheduling`/`narration` are preserved. Three anomalies fail loudly and surface as `REGISTRATION_REPAIR_FAILED` BLOCKED in the render repair path: an unparseable manifest (`MEDIA_MANIFEST_UNREADABLE`, the corrupt file is left untouched for a human), a carried asset with no recorded gate state (`MEDIA_MANIFEST_GATE_MISSING`), and two different asset_ids claiming the same output path (`MEDIA_MANIFEST_PATH_COLLISION`).

Regression (`tests/test_animation_cache_integrity.py`, 10 new tests, 21/21): A,B,A,B consecutive registrations stay CONSISTENT throughout; A,B,C each get their own timeline slot; re-registering B with a new fingerprint does not stale A's cache; repairing A after its rows are deleted leaves every one of B's record rows byte-identical; evidence escalation still BLOCKED after merges; one placement always yields exactly one active asset; re-registering the same clip is byte-idempotent; a pre-fix single-asset manifest upgrades in place and keeps scheduling/narration. Real-pipeline before/after: before the fix `repeated_repairable=true`, `repair_mutual_harm=true`; after, the manifest holds both clips throughout, both cache replays return `registration_repaired=false`, and both audits are CONSISTENT.

## 20. Unified backend capability matrix (2026-11-17)

`animation_backend.capability_matrix()` extends the existing backend selector contract with one executable capability table (schema `contentops.animation-capability-matrix/v1`); no second capability list is maintained in parallel. Six backends — `remotion`, `remotion-three`, `huashu-art-motion`, `huashu-motion`, `manim`, `motion-canvas` — each record runtime version and source, lock file, install environment, supported shot types, templates, render entry, input/output contracts, output spec, license fields, applicable accounts, blocking status, and whether it is a full-film compositor. Every row has `is_compositor=false`; `remotion-three` reuses the `scripts/animation_render.py` entry and is a 3D composition inside Remotion, not a new compositor. P3-B extension: `motion-canvas` uses `scripts/motion_canvas_adapter.py` as its render entry, a new `export_mode` field is `EDITOR_EXPORT_REQUIRED` for Motion Canvas and `HEADLESS` for the others, and its templates are `animated_system_graph` and `agent_state_machine`.

**Current status:** `current_status` in `projects/e2e-p3-motion-canvas/receipts/capability-matrix-after-export.json` is `STALE_SOURCE_TEMPLATE`. The old `mc-arch01` export supports historical acceptance of that old template only; the current template requires a new editor export and re-verification. `mc-state01` still requires editor export. The backend's historical `VERIFIED` status does not mean the current template is accepted and does not grant execution, production or publication authority.

**Trust boundary.** Reading a lock file yields only version/install facts and never promotes a backend to VERIFIED. Only a caller-supplied `render_evidence` entry carrying `verified_at`, `sha256` and `receipt` marks a backend VERIFIED; an active `block_state` code outranks a historical receipt. All rows keep `execution_authorized=false`, `publish_authorized=false`, `production_ready=false`. `tests/test_animation_backend.py` 40/40 is a historical result, not current-media acceptance.

## 21. P3-B Motion Canvas integration (historical implementation and acceptance record; current status is stale)

> This section preserves implementation context and historical evidence. Current-template status is governed by section 20 and the receipt: `STALE_SOURCE_TEMPLATE`. The old `mc-arch01` export/matrix state does not mean the current template is accepted; re-acceptance requires editor export from the current template. `mc-state01` also requires editor export.

- Detailed template/local-render/cache/stage/matrix statements below are historical and do not override this section's heading, receipt `current_status=STALE_SOURCE_TEMPLATE`, or the production boundaries. In particular, old `mc-arch01` `REAL_MEDIA_VERIFIED`, old matrix `VERIFIED`, CI contract tests and local runtime observations do not establish acceptance of the current template or availability in all environments.



- `extensions/motion-canvas/` is a minimal runnable project: all Motion Canvas packages pinned to 3.17.2 (npm registry `latest`, published 2024-12-14), npm lockfile committed, `node_modules` gitignored. The official `@motion-canvas/ffmpeg` exporter is registered in `vite.config.ts`; 1080x1920 / 30fps / sRGB live in `src/project.meta`.
- Two templates: `animated_system_graph` (components appear step by step, one-direction arrows, then explain) and `agent_state_machine` (states, conditional branches, failure fallback). Every colour comes from the account `brand.palette`; the problem colour exists only during the failure step and the next step restores the brand colour. No bounce, flash, sticker or flashy transition. `tsc --noEmit` and `vite build` pass, but that is compile evidence, not a render.
- `scripts/motion_canvas_adapter.py` reuses the existing receipt, fingerprint/cache, M45 manifest, asset registry and QC; it adds no second system. `--preflight`/`--prepare` write an `EDITOR_EXPORT_REQUIRED` receipt with raw evidence and remediation; `--import-editor-export` accepts only a real editor-exported MP4 inside the project and registers it after the technical gate.
- E2E: `projects/e2e-p3-motion-canvas/` (TEST_ONLY). `tests/test_p3_motion_canvas.py` is 16/16 and wired into CI. `mc-arch01` has a real editor export imported: SHA-256 `8741f5c56612f712a296e9a4cb347366b63b310badf07fc1a191af6610d238e1`, h264 / 1080x1920 / yuv420p / 30/1 / 7.233s / 217 frames / no audio, with first/mid/last frames and QC registered. `mc-state01` remains `EDITOR_EXPORT_REQUIRED`. When CI lacks the gitignored external MP4 it reports `REAL_MEDIA_NOT_RUN`; a green contract suite is not a real-media acceptance claim.
- Official sources: <https://github.com/motion-canvas/motion-canvas>, <https://motion-canvas.io/docs/rendering/video/>, <https://github.com/motion-canvas/exporters>. The official exporter has no CLI entry; a render starts from the editor Video Settings tab.

## 22. Pre/post-export snapshots and final integration governance (2026-11-17)

**Snapshot status.** `projects/e2e-p3-motion-canvas/receipts/capability-matrix.json` is preserved as PRE_EXPORT historical evidence; `capability-matrix-after-export.json` is a POST_EXPORT_ACCEPTANCE snapshot, but its current status field is `STALE_SOURCE_TEMPLATE` because the source template changed. It preserves the old export and then-current matrix provenance, not a current acceptance result. To re-accept the current template, export `mc-arch01` again from the Motion Canvas editor, then import and verify it; `mc-state01` independently still requires an editor export. CI without the external MP4 checks contracts/provenance/governance only and prints `REAL_MEDIA_NOT_RUN`; it is not real-media acceptance.

- `capability-matrix.json` remains PRE_EXPORT historical evidence, generated before the earlier export; its earlier `BLOCKED` status is not current.
- `capability-matrix-after-export.json` recorded POST_EXPORT_ACCEPTANCE evidence for the old source template, including generator/input hashes, the historical export MP4 hash and receipt. Current `current_status=STALE_SOURCE_TEMPLATE` supersedes the historical stage label.
- The old `mc-arch01` export SHA-256 `8741f5c56612f712a296e9a4cb347366b63b310badf07fc1a191af6610d238e1` and `mc-state01` `EDITOR_EXPORT_REQUIRED` receipt are historical. They cannot inherit status from each other and do not establish current-template readiness.
- `production_ready`, `publish_authorized` and human-review authorization remain closed; re-acceptance does not grant them automatically.