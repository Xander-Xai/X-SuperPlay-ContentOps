# Current State

[English](CURRENT-STATE.md) | [简体中文](CURRENT-STATE.zh-CN.md)

> What runs today. Verified facts only. No aspirations, no stale claims.
>
> Last verified: 2026-11-02 on `feat/106-easel-host-dual-line`
> (stacked on PR #101 and merged with `main`). Facts below describe this branch;
> unmerged layers are labelled as such.
> Sections below the "Layer status" table are historical milestone records;
> they describe how a capability was proven, not what is current.

## Layer status (2026-11-02)

| Layer | Status |
|---|---|
| M5 evidence chain, media contracts, QC, media-use adapter, skill router/authorization | implemented |
| Platform registry (`config/registry/platforms.json`, `src/contentops/platforms/`) | implemented on PR #101; 10 local entries for 9 Strategy platforms, one `INTEGRATED` (`x`), nine `PLANNED` |
| Content Bundle consumption + two-format handoff (`src/contentops/content_kernel/`) | implemented offline; VIDEO and GRAPHIC_TEXT plans, no publication |
| Easel host guard (`src/contentops/easel/`, `scripts/easel_host.py`) | implemented offline; `HOST_BLOCKED` on this machine (FastAPI/uvicorn absent), mutations denied |
| Graphic manual package (`src/contentops/graphic/`, `scripts/graphic_package.py`) | implemented offline; stops at `AWAITING_MANUAL_REVIEW`; no delivered package yet |
| Content router, account DNA, brief/script/design stages | **partial** (S1/S2 on `main`; S3–S4 pending) |
| XHS / X / GZH platform tracks | **unmerged / rights-blocked** |
| MiniMax speech, image, H3 video | implemented; verified subsets recorded below |
| Production ready | **false** for every track |
| Publication count | **0** — no delivery package has a real platform URL |

## Git

| Property | Value |
|---|---|
| Default branch | `main` — protected |
| This branch | `feat/106-easel-host-dual-line` — stacked on PR #101, not merged |
| Main protection | **PROTECTED** — required status checks + PR + no force push + no deletion + linear history |
| Required checks | `Tests (ubuntu-latest)`, `Tests (windows-latest)`, `Repo policy checks` |
| Branch strategy | Issue-scoped short-lived branches, squash merge, auto-delete on merge |
| Current branch reality | Only `main` is persistent. Unmerged work, including this branch and PR #101/#105, is not part of the system |
| What `main` actually contains | The M5 media-use integration, rights gate, skill router and skill-execution authorization (PR #89), plus the X post gate and growth→editorial gate (PRs #87, #88) |
| Consequence | Docs describe this branch and label `main` separately. PR #101 (platform registry/Bundle) and #105 (R4-A copy review) are open; this branch reuses #101 and does not treat either as approved |

## Easel Runtime

| Property | Value |
|---|---|
| Version | v0.2.1 |
| Commit | `3fe2d9904c1619281ef57f81d9ee0b7854998399` |
| Path | `.runtime/easel/` |
| Acquisition | Git clone of the pinned tag, checked out with `core.autocrlf=false` and `core.eol=lf` |
| Verified | 982/982 blob SHA-1 matched upstream tree (`scripts/verify_easel_runtime.py`) |
| Re-verified | 2026-11-01 on this branch: 982 files, 0 missing, 0 mismatch, 0 extra |
| Line endings | A Windows checkout with `core.autocrlf=true` yields **847 blob mismatches** while `resolve_easel.py --offline` still reports `OK`, because that command proves git HEAD, not content. Verify content before trusting the runtime |
| Executed surface | `skills/openclaw/auto-short-video/scripts/assemble.py` (composition) and `skills/shared/scripts/tts.py` (V1 narration only; M5 uses Windows SAPI) |
| Independent cross-check | 2026-10-31 against the official `v0.2.1` release archive: 982 files, 0 missing, 0 mismatch |
| Local extras | `outputs/` and `__pycache__/` only; no tracked file differs from upstream |
| Lock file | `runtime/easel.lock.json` |
| Provenance | `runtime/easel-runtime.json` |
| Upstream stable | v0.3.0 (2026-10-12) — **not adopted**: 158 commits, skills moved from `skills/openclaw/` to `skills/builtin/`, `assemble.py` changed, and the tag was force-replaced upstream |

## Easel Host (2026-11-02)

The Owner adopted the full Easel system as the production base (ADR-016). This
section records only what was actually run; the workbench/agent surface is not
a verified integration yet.

| Property | Value |
|---|---|
| Entry point | `scripts/easel_host.py status` / `serve` |
| `status` result on this machine | `HOST_BLOCKED` — `HOST_DEPENDENCY_MISSING:fastapi`, `HOST_DEPENDENCY_MISSING:uvicorn` |
| Pin reported | v0.2.1 / `3fe2d99` |
| Runtime bytes | `status --verify-bytes` → `VERIFIED`, 982/982 blobs (run 2026-11-02); `serve` always performs this comparison |
| Bind | `127.0.0.1` only |
| Methods | `GET`, `HEAD`, `OPTIONS` |
| Scopes | `lifespan` passes; websocket scopes are closed before upstream |
| Mutations | denied before upstream: publish, login, credentials, settings, env install, delete |
| Guard tests | `python tests/test_easel_host_guard.py` — 13/13 |
| Host authority | none over approval, publication, provider spend or accounts |
| What was not done | no dependency install, no credential/profile read, no account login, no host process started, no publication |

## Bundle and Dual-Line Handoff (2026-11-02)

| Property | Value |
|---|---|
| Handoff entry | `scripts/bundle_handoff.py`, `src/contentops/content_kernel/handoff.py` |
| Formats | `VIDEO` (`contentops.copy-to-video/v1`), `GRAPHIC_TEXT` (`contentops.copy-to-graphic/v1`) |
| Tests | `tests/test_bundle_two_formats.py` 14/14; `tests/test_graphic_workflow.py` 14/14; `tests/test_m5_bundle_handoff.py` 5/5 |
| Bundle binding | every handoff records `bundle_path`, `bundle_scope` and `bundle_sha256`; both builders re-read the Bundle and refuse `BUNDLE_CHANGED` / `HANDOFF_UNBOUND` |
| Review binding | video `human-review.json` records the Bundle digest; a changed Bundle revokes a written review with `review_revoked_reason: BUNDLE_CHANGED` |
| Host capability | handoffs accept only `UNVERIFIED`; a caller cannot promote itself with a string |
| Video wiring | `project.yaml` `content_bundle` → `stage_bundle` writes `receipts/bundle-handoff-video.json` before sources |
| Graphic package | `scripts/graphic_package.py` writes `receipts/graphic-package.json` + `graphic-preview.md`, status `AWAITING_MANUAL_REVIEW` |
| Real dual-line sample | `projects/bundle-dual-line/` — one Bundle, `bundle-dual-line-video` MP4 (22.47 s, 1080x1920, h264+AAC, QC `WARN`, `PENDING_FOUNDER_REVIEW`) and `bundle-dual-line-graphic` manual package (`AWAITING_MANUAL_REVIEW`) |
| Sample provider/network | none; Windows SAPI narration + pinned Easel compose; graphic package made no render or draft |
| Publication | not implemented; every handoff/package carries `publish_authorized: false` |

## Pipeline

Two entry points share the pinned Easel composer. Neither publishes.

| Property | `run_v1.py` (V1) | `m5_production.py` (M5) |
|---|---|---|
| Input | authored `storyboard.json` + `master.md` | `project.yaml` `source_refs` + claims |
| Narration | edge-tts (`zh-CN-YunxiNeural`) | Windows SAPI, offline |
| Voice quality | `edge_tts_fallback` — not production-grade | `windows_sapi_offline` — not production-grade |
| Evidence layer | none | `SourceArtifact` + `ClaimLedger` |
| Composition | pinned Easel `assemble.py` via `assemble_easel.run` | same |
| Subtitle handling | `assemble_easel` strips, runs upstream, burns separately | burned from narration timings |
| Production ready | **false** | **false** — `PENDING_FOUNDER_REVIEW` |

Diagnostic engine: `python scripts/run_v1.py <project> --engine fallback`
(ffmpeg-only, never production, never reports `production_ready: true`).

## M5 Evidence-First Production Chain (Issue #6) — IMPLEMENTED 2026-10-31

| Property | Value |
|---|---|
| Entry | `python scripts/m5_production.py projects/<slug>` |
| Evidence layer | `src/contentops/evidence/` — `SourceArtifact`, `ClaimLedger` |
| Stages | sources → assets → claims → script → narration → subtitles → storyboard → compose → QC → review |
| First run | `projects/m5-easel-pin` — 4 sources, 4 claims, 3 declared visuals, 7 lines |
| Narration | Windows SAPI, offline, 45.1 s, `voice_quality: windows_sapi_offline` |
| Subtitles | 7 cues burned from the narration timings, coverage 0.963 |
| Composition | pinned Easel, 1080×1920 H.264 + AAC |
| QC | PASS — 19 checks, real-source ratio 1.0 |
| Production ready | **false** — `PENDING_FOUNDER_REVIEW`, scores null |
| Tests | `tests/test_m5_evidence.py` — 18 offline tests |

Composer defect fixed in the same change: ASS subtitle timestamps were written
with three fractional digits, which libass reads as centiseconds, stretching
every cue roughly tenfold and overlapping neighbours. `assemble_easel._srt_to_ass`
now emits centiseconds; verified by rendering the cues on black and by diffing
the burned band against the unburned render.

## Web Workbench

| Property | Value |
|---|---|
| Status | **NOT VERIFIED / not a current doctor check** |
| Current doctor | 7 checks (python, node, ffmpeg, ffprobe, git, easel_checkout, repo_layout) — all OK on 2026-11-01 |
| Impact | Does NOT block the video pipeline (TTS + compose use the stdlib path) |

The earlier "6/7 doctor FAILs" list described a doctor version that checked Web
UI packages and a frontend build. The current `doctor.py` does not run those
checks, so that claim is retired rather than repeated. Web workbench readiness is
unverified, not failed.

## MiniMax

| Property | Value |
|---|---|
| Integration | speech **IMPLEMENTED** (Issue #19), `PENDING_FOUNDER_REVIEW` |
| Image integration | **IMPLEMENTED** (Issue #20, PR #25 merged), `PENDING_FOUNDER_REVIEW` |
| Video integration | **IMPLEMENTED** (Issue #22, PR #26 merged), `PENDING_FOUNDER_REVIEW` |
| Speech transport | official MiniMax CLI `mmx`; pinned Easel path is `EASEL_MPLAN_AUTH_INCOMPATIBLE` |
| Image transport | official MiniMax CLI `mmx` |
| Video transport | **documented public API** `POST /v2/video_generation` — the CLI cannot set resolution |
| Voice cloning | **DOCUMENTED_BUT_NOT_TESTED** (Issue #23), needs a rights-cleared sample |
| Capability spike | **COMPLETE** (Issue #4, 2026-10-04) |
| PAYG allowed | **false** |
| Billing mode | subscription, **verified** |
| Speech | **VERIFIED** — `speech-2.8-hd`, 32 kHz mono WAV |
| Image | **VERIFIED** — `image-01`, 9:16 portrait, seed supported |
| H3 video T2VA | **VERIFIED** — real `MiniMax-H3` 768P 4 s task succeeded on the Subscription Key (M2.0) |
| H3 video I2VA | **VERIFIED** — real reference-image task succeeded 2026-10-05 (M4) |
| H3 Ref2VA / FL2VA / L2VA, H3-Max | **DOCUMENTED_BUT_NOT_TESTED** — implemented and fixture-tested, not exercised live |
| Credit Pack balance | `0.00` observed, re-checked before every generation |
| Balance read dependency | `UNDOCUMENTED_FIRST_PARTY_IMPLEMENTATION_DEPENDENCY`, fail closed |
| H3 duration | integer enum 4-15 (H3), 5-15 (H3 Max); test minimum 4 s / 5 s |
| Evidence | `research/providers/minimax-mplan-explore-capability.md`, `research/providers/minimax-h3-official-reality.md`, `research/providers/minimax-voice-clone-entitlement.md`, `research/providers/receipts/minimax-h3-i2va-reference-2026-10-05.sanitized.json` |

## Golden Samples

| Sample | Source | Status |
|---|---|---|
| `projects/easel-review/` | Easel v0.2.1 runtime evaluation | 1 successful build, QC PASS, awaiting human review |
| `projects/m5-media-use/` | M5 evidence chain with the media-use sample | final MP4, QC WARN, `PENDING_FOUNDER_REVIEW` |
| `projects/m5-easel-pin/` | First M5 evidence-chain run | QC PASS (19 checks), real-source ratio 1.0 |
| `projects/m45-technical-integration/` | M4.5 media convergence | QC WARN, zero provider calls |
| `projects/bundle-dual-line/` | One Content Bundle, two independent outputs | video 22.47 s QC WARN / `PENDING_FOUNDER_REVIEW`; graphic `AWAITING_MANUAL_REVIEW`; 0 publications |

## Tests

| Suite group | Files | Count |
|---|---|---|
| Script smoke | `scripts/test_basic.py` | 10 |
| Media / provider (offline fixtures) | speech, image, H3, convergence, media-use adapter | 432 `test_*` functions |
| M5 evidence + media-use traceability | `test_m5_evidence.py`, `test_m5_*` | 18 + list-driven suites |
| Golden / reproducibility | A/B variants, voice assets, locked inputs | 47 |
| Skill / authorization | router, doctor, execution gate, grants | list-driven suites |
| Skill reference integrity | `tests/test_skill_references.py` | 6 |
| Windows | subprocess, paths | 53 |
| Policy / secrets | gitignore, local-approval, receipt secrets | 19 + list-driven suites |
| **Total** | **not asserted in this document** | Suite count is read at check time: `git ls-files 'tests/test_*.py' \| wc -l` |

`python scripts/dev_check.py` runs the local gate. CI enumerates every suite as a
named step; a suite without a CI step does not run, and one green run is not
evidence that every suite passed. `ffmpeg` and `Pillow` are installed in CI;
suites that need them report skips when absent.

See [TEST-PLAN.md](TEST-PLAN.md) for the full inventory.

## Known Blockers

1. Voice quality — edge-tts is mechanical and Windows SAPI is offline-flat.
   Neither is production-grade. MiniMax speech is implemented but unapproved.
2. Human Review — no completed `human-review.json` for any project.
   Every result stays `PENDING_FOUNDER_REVIEW`.
3. media-use runtime lock — a clean checkout (and this host today) resolves
   `BLOCKED / MISSING_RUNTIME`. The approved baseline exists; a host lock must be
   generated and trusted before the adapter can run.
4. Unmerged content layer — account routing, workflow gates, brief/script/design
   stages, XHS, X and GZH are not on this branch. They are prerequisites for the
   five `x-superplay-*` skills, not available capabilities.
5. Documentation convergence — this document was restructured on 2026-11-01;
   PRD, DEVELOPMENT-PLAN and TEST-PLAN were updated in the same pass. The
   remaining requirements are in
   [CONVERGENCE-REQUIREMENTS-2026-11-01.md](CONVERGENCE-REQUIREMENTS-2026-11-01.md).
6. Upstream pins — Easel v0.3.0 and HyperFrames 0.8.225 are available and not
   adopted. See the convergence requirements for the decision.
7. ~~Main branch unprotected~~ — **RESOLVED** (G0.6): main is protected via
   GitHub branch protection.
8. Easel host — `HOST_BLOCKED` on this machine because FastAPI/uvicorn are absent.
   Installing them, using a real account or starting a host requires a separate
   approval after a host-security review (ADR-016). A running host is not a
   publication authorization.


## M3 Image Generation (Issue #20) — VERIFIED 2026-10-04

Branch `feat/20-minimax-mplan-image`. One real provider generation was performed.

| Property | Value |
|---|---|
| Transport | official CLI `mmx 1.0.27`, `mmx image generate` |
| Model | `image-01` |
| Requested | 768x1360, seed 42 |
| **Requested extension** | `.png` |
| **Detected container** | **`JPEG`** |
| **Canonical extension** | `.jpg` (bytes preserved, no transcode) |
| Actual dimensions | 768x1360 (confirmed independently by `ffprobe`: `mjpeg`) |
| Aspect ratio | 0.564706 against 9:16 = 0.5625, within the 0.02 tolerance |
| Output SHA-256 | `fb0ee9489df856bc2cd554ab98d34fd73e0737ca733cdd0af6022342512f8e21` |
| Technical QC | PASS — luma stddev 29.97 (floor 6), span 146 (floor 24), decodable |
| `text_contamination_suspected` | `false` (edge density 0.0668, floor 0.18) |
| Billing preflight | `SAFE_INCLUDED_PLAN`, credential class `SUBSCRIPTION` |
| Quota before | 5h 99%, weekly 58% |
| Quota after | 5h 99%, weekly 58% |
| Observed delta | **0 percentage points** on both windows |
| `production_ready` | `false` |
| `human_review` | `PENDING_FOUNDER_REVIEW` |

### The container defect reproduced a second time

The provider returned **JPEG bytes from a `.png` request**, independently
reproducing what M2.0 measured. Had the pipeline trusted the extension, a JPEG
would have been stored as `.png` and handed to every downstream tool that selects
a decoder by suffix. The canonical file is `.jpg`; the receipt records the request
and the reality separately.

### Quota is reported as a delta, never as a price

The plan exposes percentages only. One image moved neither window, so the
observed delta is 0 percentage points. That is **not** a claim that an image
costs nothing, and no per-image cost is derived: MiniMax does not expose exact
units here.

### Evidence boundary

The generated asset was registered as `GENERATED_IMAGE` /
`VISUAL_SUPPORT` with `generated=true`, `evidence_capable=false`. Attempting any
claim-bearing role raises `GeneratedAssetEvidenceError` in code.

### Human review

`.verify-tmp/m3/human-review.json` carries the review fields with **every score
null**. Technical QC passing does not mean production ready.

## M4 H3 Video Generation (Issue #22) — VERIFIED 2026-10-05

Branch `feat/22-minimax-h3-video`. One real provider generation was performed, a
**reference-image** test, because M2.0 proved T2VA with no image content at all.

| Property | Value |
|---|---|
| Transport | documented public API `POST /v2/video_generation`, api schema `v2` |
| Model / mode | `MiniMax-H3`, **I2VA** (first-frame reference) |
| Requested | 4 s, `768P`, ratio `adaptive` (i2va derives the ratio from the input image) |
| Reference | `data:image/jpeg;base64`, 768x1360, 45 800 B, `role: first_frame` |
| Alignment instruction | emitted as the first line, upstream wording verbatim |
| Task created | **exactly 1**, polled to `succeeded`, downloaded once |
| Actual output | h264 / mp4, 768x1344, 24 fps, **4.458 s**, 424 543 B, decodable |
| Aspect | 0.571429 against reference 0.5647 — tolerance, not equality |
| Duration delta | 4.000 requested → 4.458 actual (0.458 s, threshold 1.0 s) |
| Audio | unrequested **AAC** present, exactly as M2.0 measured; `audio_policy=REPLACE` |
| Black / freeze | longest black run 0.0 s, longest freeze run 0.0 s, mean frame diff 0.0131 |
| Output SHA-256 | `b761ea2a69b3ad6181b8a48b93dddefb56edd897867f42a8b160610e74ac249a` |
| Billing preflight | `SAFE_INCLUDED_PLAN`, credential class `SUBSCRIPTION` |
| Quota before | weekly 58% |
| Quota after | weekly **51%** |
| Observed delta | **7 percentage points** weekly, matching the declared `7pp` budget |
| cash / Credit Pack / voucher / owed | `0.00` before **and** after |
| `production_ready` | `false` |
| `human_review` | `PENDING_FOUNDER_REVIEW` |

### The reference path was genuinely unproven

M2.0's receipt contains a single `text` item and **no image content**. So it was
silent on every part of the reference path: whether an `image_url` item is
accepted, whether `role: first_frame` is honoured, whether a `data:` URI is an
accepted URL form, whether the alignment instruction travels with a frame, and
whether I2VA renders at all on this account. The account also resolves to the
regional CN mirror rather than the host the public documentation targets, so
reference handling could plausibly differ. One 4 s call was the cheapest way to
close that gap.

### Quota is reported as a delta, never as a price

7 percentage points is an **observed** delta for one 4 s / 768P job. It is not a
price formula: no per-second, per-clip or credit rate is derived from a percentage.
It is used only to budget tests conservatively. Weekly now stands at **51%**.

### Cache reuse verified against the real artifact

A second run was served from the cache with the transport pointed at an
**unroutable host**, so any network attempt would have failed loudly:

| Property | Value |
|---|---|
| Reused | `true` |
| Provider creates | **0** |
| Provider polls | **0** |
| Billing calls | **0** |
| Original receipt overwritten | `false` |

### Evidence boundary

The shot was registered as `GENERATED_VIDEO` / `VISUAL_SUPPORT` with
`generated=true`, `evidence_capable=false`, and only **after** the immutable
receipt existed. Any claim-bearing role raises `GeneratedAssetEvidenceError`.

### Human review

`<shot>.mp4.human-review.json` carries eleven named review fields with **every
score null**. Automated measurements ride alongside, labelled as measurements.
Observed on the real clip, and recorded as observation rather than scored: the
first frame reproduces the reference faithfully; motion is present and consistent
with the requested slow push; but between the first and last frames the circular
headlamp reads as a filled disc rather than a ring, and one neon sign drifts in
position. Geometry stays coherent with no melting or warping. Whether that drift
is acceptable for a support visual is a human judgement, and it is not this
pipeline's to make.

### Still unverified

Ref2VA reference-video and reference-audio paths, FL2VA, L2VA, and MiniMax-H3-Max
(including its 5 s floor and 480P option) are implemented and fixture-tested but
have not been exercised against the live service.
## M4.5 Media convergence (Issue #27) — IMPLEMENTED 2026-10-05

Branch `feat/27-media-convergence`. **Zero provider calls.** Weekly quota untouched at 51%.

| Property | Value |
|---|---|
| Shared validator | `validate_media_asset(envelope, adapter)` — one common path, three adapters |
| Modality model | `MediaModality` (SPEECH/IMAGE/VIDEO) is **separate** from `AssetKind`; speech carries no `asset_kind` |
| Speech receipt facts | no `schema`, no `generated`/`evidence_capable`, digest in `normalized_sha256`/`raw_sha256` |
| Transform receipt | `contentops.media-transform/v1` — derived assets, source digest, original untouched |
| `AudioPolicy` | `KEEP` reuses the original (no transform); `MUTE`/`REPLACE` produce an audio-free derived asset |
| Capability registry | 10 capabilities resolved by name, no vendor word; only live-proven ones `VERIFIED` |
| Quota policy | explicit operator floors; weekly floor is a **chosen value**, not the observed 7pp delta |
| Scheduler | `ALLOW`/`REUSE_REQUIRED`/`DEFER`/`MANUAL_REQUIRED`/`BLOCKED`, priority evidence → narration → image → video |
| AssetPlanner execution | claim beats resolve only to real material, else `EVIDENCE_ASSET_REQUIRED` |
| Quality gate | `BLOCKED`/`DEGRADED_FALLBACK`/`PENDING_HUMAN_REVIEW`/`PRODUCTION_READY`/`REJECTED` |
| Manifest | `contentops.media-manifest/v1`, deterministic, no timestamp, sole asset list |
| Manifest paths | logical `project://` / `repo://`, resolved at use; absolute paths refused |
| Timeline | `assets` is the inventory, `timeline` is one active asset per placement; composition reads the timeline |
| Derived provenance | `generated` is inherited, never downgraded; `provider_generated_bytes` vs `source_generated` are separate fields |
| H3 reuse | explicit by path and validated; no filesystem discovery |
| QC receipt | `contentops.qc-canonical/v1` — sanitized at a boundary, declares `currency` and `graded_target` |
| Composition | reuses pinned Easel v0.2.1 via `assemble_easel.run`; no second compositor |
| Tests | 97 M4.5 + 85 speech + 84 image + 108 H3, all PASS |

### Two rules the implementation added beyond the plan

- a **provider generation** must declare its modality's schema; a **non-generated**
  asset must not, because nothing's API produced it
- a missing `technical_qc` **fails** a generation but is **not applicable** to an
  import or a transform — no provider ran, so there is nothing to report

### The technical integration is not a production golden

`scripts/m45_media_integration.py` produced one local artifact
(`project://final/m45.mp4`, h264 / 1080x1920 / 18.0 s, `qc_video` **WARN**) proving
`registry → manifest → compose → final QC` with **0** speech, image and video
provider calls.

| Canonical fact | Value |
|---|---|
| Output | `project://final/m45.mp4` |
| QC report | `receipts/qc-report-m45.json` — `overall: WARN`, `currency: CURRENT` |
| `production_ready` | `false` |
| `human_review` | `PENDING_FOUNDER_REVIEW` |
| Provider calls | speech 0 / image 0 / video 0 |
| Timeline | 5 placements, one active asset each |
| Inventory | 7 assets (5 active + 1 superseded + 1 narration) |

Every asset is a deterministic fixture, labelled in its receipt, in the manifest
header and in the integration report. Media binaries are gitignored; the manifest,
receipts and storyboard are committed.

**One QC report, one verdict.** `qc-report-m45.json` is the canonical M4.5 QC report
and is the only one. A second tracked report, `qc-report-final.json`, recorded
`FAIL` because it graded `final/final.mp4` — a file this stage never produces — and
sat beside the real `WARN` reading as an equally current, contradicting result. It
was stale output from an earlier invocation and has been removed.

QC receipts cross a sanitization boundary before being committed
(`contentops.qc_canonical`). `qc_video` is a runtime tool and keeps reporting local
paths, which is correct while it runs; the tracked receipt is rewritten in place as
`contentops.qc-canonical/v1` with logical references and an explicit `currency` plus
`graded_target`. So a reader can tell *what* a verdict is about and *whether it is
current* without inferring either from a filename. A regression test scans the
canonical committed artifacts for host-specific paths.

It does **not** prove real `SourceArtifact` ingestion, `Claim Ledger`
completeness, Founder approval, a production golden, or three consecutive
production builds. `production_ready=false` / `PENDING_FOUNDER_REVIEW`, and no code
path can report otherwise.

### Defects the final review caught in the committed artifacts

Four blockers found by reading the committed receipts rather than the code, all now
fixed with regression tests:

1. **One placement, two shots.** `manifest_to_storyboard` iterated
   `usable_assets()` — an *inventory*, not a timeline. `beat-05` and
   `beat-05-h3-replaced` are both gate-admissible, so both landed on placement
   `beat-05`: the pre-transform native audio played over the narration `REPLACE` was
   meant to guarantee would be the only track. The manifest now carries an explicit
   `timeline` with one `active_asset_id` per placement, and composition reads that.
2. **Generated provenance downgraded.** The derived H3 envelope said
   `asset_kind=GENERATED_VIDEO` with `generated=False`, because the transform receipt
   had overloaded one boolean for "did a provider emit these bytes" and "is this
   content generated". Now refused at construction, in both directions, derived or
   not.
3. **Machine paths in a committed manifest.** Eight `D:\Projects\...` references made
   "deterministic manifest" true on exactly one checkout root — and therefore useless
   as a cache key or review comparison. Paths are now logical.
4. **`--reuse-h3-shot` did nothing.** `main()` parsed it and passed no argument,
   while the provider separately globbed `.verify-tmp/m4`. So a clean clone produced
   fixtures and a workstation with M4 leftovers silently produced real provider
   media — both committed as "the integration". Reuse is now explicit by path and
   validated against the shot's own receipt.

And one found in the **QC receipts**, which the previous pass had not looked at
because the manifest was already clean:

5. **Two current-looking QC verdicts.** `qc-report-m45.json` (WARN, graded
   `final/m45.mp4`) and `qc-report-final.json` (FAIL, graded `final/final.mp4`, which
   nothing here creates) were tracked side by side, both carrying absolute
   `D:\Projects\...` paths. The stale report was removed and the canonical one now
   declares `currency` and `graded_target`.

### Defects the test suite caught during this milestone

Three real bugs in the new code, all found by tests rather than review:

1. `require_evidence_capable` was called unconditionally for generated image, which
   made a support visual **impossible to produce at all** — the capability is
   correctly flagged evidence-incapable, but the check belongs to the claim path
2. The asset-existence check was lost while restructuring the receipt loader, so a
   **missing asset file passed validation**
3. Duplicate `asset_id`s **silently collapsed** in the manifest, because
   `gate_states` is keyed by identifier; now refused

Plus one validation gap: a key-shaped value was only refused in a known field
list, so it could be smuggled through a new field. Now no string value anywhere in
a public receipt may match the provider-key shape.

## HyperFrames media-use integration (Issue #57) — IMPLEMENTED 2026-10-31

Re-verified after owner approval on 2026-10-31. Branch `feat/57-media-use-adapter`.
**Zero provider calls.** The verified runtime was exercised with no network
egress; installation itself is a separate, reviewed preparation step.

| Property | Value |
|---|---|
| Upstream | `heygen-com/hyperframes` @ `5e4f5aefb58a9996ea5920f008184e9789346871` (Apache-2.0) |
| Skill commit | `f2358315e59731833334c5d881a7fb5543c22a97` (`skills/media-use`) |
| Adapter | `src/contentops/media/media_use_adapter.py` — the only module that knows the skill exists |
| CLI | `scripts/media_use_adapter.py` — `status/doctor/candidates/resolve/adopt/ingest/import/verify/demo` |
| New kinds | `AssetKind.LICENSED_EXTERNAL`, `MediaModality.AUDIO` |
| Receipt | `contentops.media-import/v1` with `output_sha256`, `fingerprint`, `generated`, `evidence_capable`, `production_ready`, `human_review`, `license` |
| Evidence | every import is `evidence_capable=false`; generated resolutions are `GENERATED_NOT_IMPORTABLE` |
| Cross-project | blocked unless `allow_cross_project_reuse`; child `HOME` is project-local |
| Runtime trust | two layers: a committed, owner-approved baseline (`runtime/media-use-runtime-baseline.json`, approved 2026-10-31 for offline-only scope) and a host-specific lock (`CONTENTOPS_MEDIA_USE_RUNTIME_LOCK`). A lock is trusted only if it names the approved baseline by digest and every byte matches. A fresh checkout still refuses execution until a machine lock is generated; approving the baseline does not install or trust a host runtime |
| Verified runtime | `hyperframes@0.8.222` (published SRI matched), official Node v22.23.4 on Linux and win-x64 (SHASUMS match), 127-entry lockfile. Package-tree digest `be8e24df…` reproduced independently on both platforms |
| Acceptance | Linux: `TRUSTED_RUNTIME` inside a no-egress namespace, `adopt`/`candidates`/`resolve` through the adapter. Windows: `install` → `lock` → `TRUSTED_RUNTIME` → real CLI. Isolated demo with real Easel compose: `compose` OK, QC `WARN`, `production_ready:false` |
| Install / lock entry point | `scripts/media_use_runtime.py` — `approve`, `install`, `lock`, `verify`, `selfcheck`; approving and lock generation are separate actions |
| Tests | 53 adapter tests PASS; 97 M4.5 convergence tests PASS (re-run 2026-10-31) |
| Pull request | Draft [#64](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/64) |
| Skill Router | **Merged via [#77](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/77)** — `scripts/skill_route.py` and `runtime/skill-registry.json` register `media-use` as a declared capability. #49 remains unmerged; #59 was closed as superseded by #77. The adapter still exposes `status/doctor/candidates/resolve/adopt`; the registry is the routing pointer |

### What the approval does and does not authorize

- The approved baseline authorizes **offline local asset operations** with the
  pinned `hyperframes@0.8.222` runtime: `adopt`, `candidates` and local
  `resolve`.
- It does **not** authorize network providers, paid generation, cross-project
  reuse, automatic publication, production delivery, or any source-media
  licence. A trusted runtime proves *what executed*, never *where an asset came
  from* or *what its licence is*.
- Every imported asset still needs an explicit licence and stays
  `evidence_capable=false`, `production_ready=false`, `human_review=PENDING`.
- The isolated Easel demo ran against a separate verified runtime. It does
  **not** mean the original `.runtime/easel` checkout is healthy or restored.

### Offline end-to-end sample

`python scripts/media_use_adapter.py demo` (exit `0`) produced
`project://final/media-use-demo.mp4` — 1080x1920, h264, 30.0 s, 300,437 bytes.

| Fact | Value |
|---|---|
| Manifest | `receipts/media-manifest.json`, fingerprint `2b01c1cb716723007527a422dff4810b16db1d9b090e61a5f2a5de578a5ba75d` |
| Inventory | 7 assets: 2 real screenshots, 2 licensed images, 1 icon, 1 BGM, 1 bundled SFX |
| Timeline | 2 placements, both `SCREENSHOT`, `real_source_ratio` **1.0** |
| Imported via media-use | 5 records (4 local fixtures labelled `OWNED-FIXTURE-DEMO`, 1 bundled SFX `Pixabay-Content-License`) |
| Gate | every asset `PENDING_HUMAN_REVIEW` |
| Final QC | `overall: WARN` (no FAIL), `currency: NON_CURRENT_DIAGNOSTIC` |
| Provider calls | speech 0 / image 0 / video 0 |
| `production_ready` | `false` |

The two real screenshots come from `projects/easel-review/sources/screenshots/`.
The image/BGM fixtures are deterministic placeholders generated by the demo and
labelled as such in their receipts; they are **not** third-party licensed media.
An image resolve with no local candidate and no network authorization is recorded
as `NEEDS_HUMAN_ACTION` — nothing is downloaded or generated to make the demo look
complete.

The render is a technical integration sample. It has no audio track, no captions
and no Founder approval, and `qc_video` warns about exactly that.

## M5 media-use automation — INTEGRATION_VERIFIED 2026-10-31

Merged to `main` through [#71](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/71).
The rights-gate follow-up is [#76](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/76).
**Zero provider calls; zero network.** The real
`scripts/m5_production.py` entry ran the real `MediaUseAdapter` against the
approved `hyperframes@0.8.222` runtime on Windows.

| Property | Value |
|---|---|
| Entry point | `python scripts/m5_production.py projects/m5-media-use` |
| Runtime | host lock `contentops.media-use-runtime-lock/v2`, state `TRUSTED_RUNTIME`, baseline digest matched |
| Configuration | `projects/m5-media-use/project.yaml` → `media_use.requests` (image, bgm, sfx) |
| Stages run | sources → media_use → assets → claims → script → narration → subtitles → storyboard → Easel compose → QC → review |
| Imported visual | `project://assets/support.png`, SHA-256 `85c4ab5c5368b1ab60a98854ee292529d6b7908be58acfccc1d5f4ed06cddb53`, `evidence_capable=false` |
| Imported BGM | local deterministic tone bed, SHA-256 `1dcb9c7e3708cfc0cc68663642cc9d6b779ff7bd5812fdb6e31e4d74f5b4ee5e` |
| Imported SFX | bundled `sfx_001`, Pixabay Content License, receipt `contentops.media-import/v1` |
| Final artifact | `projects/m5-media-use/final/m5-media-use.mp4` — h264 1080x1920 + AAC 48 kHz stereo, 25.07 s, 505,448 B, SHA-256 `d4915f45f98008e4adbaa52d29beb787ffc437d383f15415780830aeaf33d731` |
| QC | `overall: WARN`, audio stream present, no FAIL |
| Human review | `PENDING_FOUNDER_REVIEW`; `production_ready: false` |
| Composition proof | frames at 1 s, 2 s, 13 s and 14 s show the imported screenshot with the expected burned captions |
| BGM proof | inter-line pause 11.70–12.20 s: −60.9 dB with BGM vs −91.0 dB without (−30.1 dB difference) |
| SFX proof | 6.15–6.28 s: −33.4 dB with SFX vs −60.8 dB without (−27.4 dB difference) |
| Narration preservation | the same voice window measures −26.8 dB in all three renders, so neither track replaced the voice |
| Audio controls | volume, placement and mix verified; per-track fade is **not expressible** in the pinned Easel contract (sample bed has fades baked into the file) |
| Negative acceptance | 11/11 blocked: missing/wrong lock, missing material, hash mismatch, path escape, missing import file, network, paid, unlicensed, duplicate id, legacy project unchanged |
| Rights gate | `src/contentops/media/rights_gate.py` refuses a bare `rights_reviewed` flag; each request needs a matching `assets/<id>.rights.json` review record. Unknown, software and non-commercial licences are refused; synthetic assets are never evidence |
| Committed example | `projects/m5-media-use/`; media binaries and `.media/` stay gitignored, receipts are committed |
| Pull request | Merged [#71](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/71); rights-gate follow-up [#76](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/76) |
| Routing | **MERGED via [#77](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/77)** — `scripts/skill_route.py` and `runtime/skill-registry.json` are on `main`; see *Skill discovery and resolution* below |

`INTEGRATION_VERIFIED` is a statement about this machine and this lock. It is
not `MERGED_TO_MAIN`, and it does not approve the imported material, the voice
track or the video for publication.

## Skill discovery and resolution (Issue #57) — MERGED 2026-10-31

Merged to `main` through [#77](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/77).
The router and registry run on `main` today; this section records what they do
and what remains blocked.

| Property | Value |
|---|---|
| Entry point | `python scripts/skill_route.py` (stdlib only; no process, no network) |
| Discovery | `--sources`, `--list`, `--match`, `--resolve` over repo-owned, Easel and shared skill roots |
| Doctor | `--doctor` — roots, duplicates, permission declarations, rights, unsafe and dangling paths |
| Declared capabilities | `runtime/skill-registry.json`, schema `contentops.skill-registry/v1` |
| Registered capability | `media-use` only, pointing at the merged adapter, runtime baseline, lock verifier and M5 `media_use` stage |
| Resolution verdicts | `RESOLVABLE`, or `BLOCKED` with `UNKNOWN_SKILL`, `DUPLICATE_AMBIGUITY`, `OUT_OF_SCOPE`, `UNVERIFIED_RIGHTS`, `UNAUTHORIZED_PROVIDER`, `SKILL_NOT_INSTALLED`, `MISSING_RUNTIME` |
| Execution authorization | **never granted** by the router; every record carries `execution_authorized: false` |
| media-use with a host runtime lock | `RESOLVABLE` (verified on this host against `runtime/media-use-runtime-baseline.json`) |
| media-use without a lock | `BLOCKED / MISSING_RUNTIME` (the default on a clean checkout) |
| Verdict on this host (2026-11-01) | `BLOCKED / MISSING_RUNTIME` — `CONTENTOPS_MEDIA_USE_RUNTIME_LOCK` is not set here, so the adapter is not executable on this machine |
| Legacy M5 | unchanged — `scripts/m5_production.py` does not import the router; a test asserts it |
| VIDEO track | discovery-only until a catalog root exists on the host |
| GZH track | `BLOCKED` — vendored third-party track, rights unverified, `vendor/` is gitignored |
| X track | `BLOCKED` — platform track unmerged (`feat/47-x-platform-track`, PR #50) |
| XHS track | `BLOCKED` — migration unmerged and under rights review; no catalog root |
| Tests | `tests/test_skill_doctor.py`, `tests/test_skill_router_capabilities.py`; both registered in CI |
| Pull request | Merged [#77](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/77) |

The router adds no second skill engine and copies no third-party skill. A
declaration is a pointer to code this repository already owns; the adapter, the
runtime lock verifier and the M5 gate keep their own authority.
