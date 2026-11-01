# Video quality failure — capability audit, root cause and remediation plan

Date: 2026-11-01
Repository: `Xander-Xai/X-SuperPlay-ContentOps`
Branch: `feat/100-easel-first-platform-registry` (baseline `bc25b84`)
Subject: the Founder rejection of the `easel-review` final cut, and why the
repository's proven voice/motion capability never reached a delivered video.

Status legend: **MEASURED** (a command was run in this audit and its output is
reproduced here), **VERIFIED** (read from committed code or a committed
receipt), **UNGOVERNED** (present on this host outside `project.yaml`,
`receipts/`, QC and review), **OPEN** (requires an Owner decision).

No provider call, no paid generation, no credential action, no publication and
no deletion occurred during this audit. Nothing was merged.

---

## 1. Verdict

The rejected video is not evidence that the pipeline is incapable. It is
evidence that **two production entry points are structurally image-only**, while
a video-capable composition path and a working Motion + MiniMax prototype
already exist in this repository and on this disk.

The gap is integration and governance, not capability.

Three statements that are each true and are routinely conflated:

1. The pinned composer accepts video shots. **VERIFIED.**
2. A translator that emits video shots exists in the repo. **VERIFIED** — but
   only an integration sample calls it.
3. The rejected cut is static because its **storyboard says static**; V1 composed
   it faithfully. M5, separately, cannot express anything else. **VERIFIED** — see
   §4 for the attribution.

And a fourth that decides the plan:

4. An end-to-end motion build driver already exists, committed, on
   `fix/49-skill-route-ci` — 108 commits ahead of `main`, **with no PR**. See
   §5.1. The remediation was built and then stranded.

---

## 2. The rejected artifact, measured

The Founder's description matches one file exactly.

| Property | Value | How |
|---|---|---|
| Path | `projects/easel-review/final/easel.mp4` | — |
| Duration | 62.000 s | MEASURED (`ffprobe`) |
| Resolution / fps | 1080×1920 / 30 | MEASURED |
| Size | 1,868,184 B | MEASURED |
| Shots | 6, all `motion: static` | VERIFIED (`script/storyboard.json`) |
| Near-static time | **60.1 s of 62.0 s = 96.9 %**, in 12 freeze runs | MEASURED (`freezedetect=n=0.001:d=0.4`) |
| Longest single freeze | 10.33 s | MEASURED |
| Dark-pixel ratio | ≈ 0.89–0.91 across sampled frames | VERIFIED (`receipts/visual-qc.json`, checked 2026-10-03) |
| Automated QC | 21 checks, **0 fails, 0 warns**, `visual_qc: PASS` | VERIFIED (`receipts/human-review.json`) |
| Voice | `edge_tts_fallback` | VERIFIED |

The 96.9 % figure is the single most useful number in this report: it is
reproducible on any host with ffmpeg, needs no provider, and states the defect
in a form a gate can check.

Note on identity: `projects/easel-review/final/final.mp4` (552,315 B, 40.0 s) is
a **different, older** render and is the one tracked by the gitignore exception.
A reader who assumes the tracked file is the reviewed file will audit the wrong
artifact.

---

## 3. Capability matrix

Four states, never collapsed: **EXISTS** → **TESTED** → **LIVE-VERIFIED** →
**PRODUCTION-ACCEPTED**.

| Capability | EXISTS | TESTED | LIVE-VERIFIED | PRODUCTION-ACCEPTED | Blocks delivery |
|---|---|---|---|---|---|
| edge-tts (V1) | yes | yes | yes | no — founder rejected the voice | pinned at `run_v1.py:297` |
| Windows SAPI (M5) | yes | yes | yes | no — the repo itself calls it "robotic" | `m5_production.py:463-467`, `:556` |
| MiniMax `speech-2.8-hd` | yes | yes | yes — real WAVs, real receipts, 2026-10-28 | **no** | no stage accepts a provider |
| Voice clone `founder_primary_v1` | yes | yes | **clone created; never activated** | no | see §6.1 — presumed expired |
| H3 T2VA / I2VA | yes | yes | yes (2026-10-05) | no | not wired to narration/subtitles |
| H3 Ref2VA / FL2VA / L2VA / Max | yes | yes (fixtures) | **no** | no | unexercised |
| Easel image shots | yes | yes | yes | yes (technically) | the defect itself |
| Easel **video** shots | yes | yes | **yes** — see §5 | no | no production entry *does* emit them; V1 would, if authored |
| `huashu-art-motion` | yes (MIT) | yes | **yes** — real 9:16 render on this host | no | not declared, not adapted, not licensed per-asset |
| `media-use` (HyperFrames) | yes | yes | yes (offline) | no | `MISSING_RUNTIME` on a clean checkout |

---

## 4. Root-cause chain

Each link is a code fact, not an inference.

**Attribution first.** The rejected artifact is the **V1** path, not M5.
`receipts/build-easel.json` records `voice_provider: "easel/tts-voiceover
(edge-tts, zh-CN-YunxiNeural)"` and its storyboard carries a `runtime` block
written by `run_v1.py:309-315`, with `motion` authored per shot and no
`duration_s`. M5's builder writes `windows-sapi/Huihui (offline)` and
`duration_s` instead. So the frozen cut is V1's output; M5's static literal is a
**separate, real defect** that would produce the same result on its own path.
Conflating the two misplaces the fix.

**Link 0 — V1 forces the engine upstream labels as synthetic-sounding.**
Upstream `tts.py` defaults to `--engine auto`, and `auto` consults the
`VOICE_PROVIDER` environment variable to pick a closed-source voice:

```
engine = getattr(args, "engine", "auto")
use_closed = engine == "closed" or (engine == "auto" and _closed_provider())
```

(`.runtime/easel/skills/shared/scripts/tts.py:316`, with `_closed_provider()`
reading `VOICE_PROVIDER` at `:207`). V1 passes `--engine edge` explicitly
(`run_v1.py:297`), which defeats that router — and `--engine edge` is documented
by upstream as `edge=强制 edge(AI 味)` (`tts.py:437`). The voice defect is
therefore, in part, a one-argument choice made *against* an upstream seam that
already exists.

**Link 1 — V1 production is storyboard-driven, and this storyboard said `static`.**
`run_easel` reads `script/storyboard.json` through `parse_script_shots`
(`run_v1.py:229-242`), sets only `narration`, `subtitle`, `engine` and `runtime`
(`:304-317`), and hands the **whole** storyboard to `assemble_easel.run`. It
never rebuilds a shot. V1 would therefore carry a `video` shot and any `motion`
value straight through to the composer.

So the rejected artifact is static because its storyboard specifies six
screenshots with `motion: static` — an **authoring decision**, not a code
constraint.

The `DEFAULT_SCRIPT_LINES` + `find_real_images` path at `:358-399`, which does
build a PNG per shot, is the **fallback** engine; the module documents that at
`:16` — "Production never reads `DEFAULT_SCRIPT_LINES`; that list only feeds the
fallback". Citing it as the production behaviour is a mistake.

**Link 2 — M5 builds its own storyboard, and it is image-only and static.**
`m5_production.py:603-612` constructs the shot dict inline:

```
"image": repo_asset,
...
"motion": "static",
```

and `:616` sets `"image_motion": "static"`. There is no `video` key and no
parameter to add one. This is a defect in M5's own outputs; the rejected
artifact came from V1 (see attribution above).

**Link 3 — M5 narration has no seam at all.**
`stage_narration(project, script)` (`m5_production.py:538`) takes no provider
argument and calls `_synthesize_windows` unconditionally (`:542`). The refusal is
explicit at `:467` — `"offline narration requires the Windows SAPI voice; no
network TTS is authorized"` — and the receipt records
`"quality_note": "local SAPI voice; robotic, not a production-grade voice track"`
(`:556`). The production candidate documents its own voice as unfit.

The receipt is also not fully truthful on this point: it records
`"voice": "Microsoft Huihui Desktop (zh-CN)"` (`:549`), but the PowerShell it
generates never calls `SelectVoice` (`:477-483`), so the recorded voice is a
label rather than an enforced selection. A receipt field that names a choice the
code does not make is the same defect class the repo already fixed once.

**Link 4 — the video-capable translator is dead code for production.**
`manifest_to_storyboard` (`m45_media_integration.py:478`) already does the right
thing:

```
is_video = envelope.modality == MediaModality.VIDEO
...
if is_video:
    shot["video"] = reference
```

(`:523`, `:536-537`). It is called only by `m45_media_integration.py:878` and
`media_use_adapter.py:761` — integration samples, never `m5_production.py`.

**Link 5 — the composer was never the bottleneck.**
The pinned `assemble.py` reads `shot["video"]` first (`:240`) and the audience
contract is documented at `:14` — `{"video": "clip2.mp4", "caption": "..."} //
image 或 video 二选一`. Composition has always supported motion.

**Link 6 — nothing tests these choices.**
No suite asserts the `static` motion values or the Windows-SAPI restriction, and
the only narration test stubs the stage out. A change to either would pass CI
silently. That is why the choices survived unchanged from the first working
version to the rejected cut: they were never wrong in a way a test could see.

**Consequence.** The delivered artifact is a six-panel slide deck because its
storyboard describes a six-panel slide deck, composed faithfully by a pipeline
that had no objection to anything else. The rejection is therefore not a defect
in composition — it is a correct rendering of the content the system was given,
narrated with the one engine the code is willing to use. Two separate things
must change: **the authoring** (which produced `static` and screenshots) and
**the code** (which offers no voice beyond edge/SAPI and, in M5, cannot express a
video shot at all).

---

## 5. The prototype — the fix already exists on disk

Three projects on this host already run the exact technique the review proposes
to build. **On this branch (`feat/100`) all three are ungoverned** — no
`project.yaml`, no `receipts/`, zero git-tracked files. That is a property of
this branch, not of the work: `easel-fi-audio-first` exists in a **governed**
form on `fix/49-skill-route-ci`, with `project.yaml`, five receipts and
`qc-report.json` = **PASS** (18 checks, 0 FAIL/WARN). §5.1 details it.

The numbers below were measured on this host's working-tree copies.

| Project | Shots | Duration | Near-static | Narration |
|---|---|---|---|---|
| `easel-fi-audio-first/` | 5 × `video` | 25.0 s | **0.0 %** | MiniMax `speech-2.8-hd`, real receipts |
| `easel-fi-what-is-agent/` | `final/eras.mp4` | 38.9 s | **0.0 %** (its `work/huashu-eras.mp4` source: 5.2 %) | — |
| `x-superplay-1024/` | 1 × `video` (`film.mp4`) | 44.8 s | 40.9 % | MiniMax, `voice_provider: minimax-mplan` |

`easel-fi-audio-first` is the strongest evidence:

- `work/storyboard.json` uses `shots[].video` with `voice_provider:
  "minimax-mplan"` — the exact shape the review asks for.
- Six motion clips at 1080×1920, each 5.0 s and **0.00–0.43 s frozen**
  (MEASURED), i.e. genuinely animated.
- `assets/voice/tts/*.provider.json` records `model: speech-2.8-hd`,
  `billing_mode: subscription`, `payg_allowed: false`,
  `billing_guard_verdict: SAFE_INCLUDED_PLAN`, quota before = after.
- `final/easel.mp4` is 25.0 s, composed, **0.0 % frozen**, audio mean −21.8 dB /
  max −4.1 dB (MEASURED).

Its captions read 「口播四十四秒，画面不能停四十四秒」. It is a **technique
proof about this defect**, not an Easel content video. That distinction matters:
the capability is demonstrated, the deliverable is not.

`huashu-art-motion` is likewise not merely installed:

| Fact | Value |
|---|---|
| Licence | MIT (`LICENSE`) |
| Upstream commit | `8a0d7d72ca65fcce6f8ba82c4a6c8dfe35b8422c` (2026-10-17) |
| Local patch | Playwright Chromium→Chrome→Edge fallback; `PYTHONUTF8=1` (`LOCAL-PATCH.md`) |
| Anti-slideshow machinery | `film_gate.py`, `qa.py`, `storyboard_lint.py`, `clip_lint.py`, `subzone_gate.py` |
| Real render on this host | `easel-fi-what-is-agent/work/huashu-eras.mp4`, 1080×1920, 38.9 s, 5.2 % frozen |

`huashu-motion` — the second skill the review names — **is not on this host**.
Only `huashu-art-motion` and `jacky-motion` are. `jacky-motion` is 16:9 and does
not synthesise voice, so it cannot supply 9:16 clips directly.

### 5.1 The remediation is already committed — on a branch with no PR

The adapter the review proposes to build exists, committed, on
`fix/49-skill-route-ci`:

| Artifact | What it does |
|---|---|
| `scripts/build_motion_film.py` | end-to-end: `speed → split → timeline → render → compose → qc`, writing `receipts/motion-build.json` |
| `scripts/build_code_animation_sample.py` | compose driver: timeline, audio-first narration placement, captions |
| `projects/easel-fi-audio-first/motion/*` | the six compositions tracked as real projects (`hyperframes.json`, `index.html`, `package.json`) |

`build_motion_film.py` is not a sketch. Its header documents two compose-time
defects found on the 2026-10-28 hand-built cut and fixed there:

- `pad_mode=trim` hard-fails when a clip is even milliseconds shorter than its
  beat, which is exactly what exact-duration renders produce;
- a clip still being written has no `moov` atom, which the upstream assembler
  reports as an *empty* ffmpeg error after several minutes of work.

It resolves both by rendering with `PAD_S = 0.4` headroom, probing every clip
before compose, and asserting the assembled film matches the timeline within
0.1 s. That is precisely the institutional knowledge the review asks for, and it
is already written down — with tests:

| Test | Covers |
|---|---|
| `tests/test_motion_build_reliability.py` | unverified cache never skips a render; compose envelope must be success JSON; the composer's output is bound to the actual file SHA |
| `tests/test_code_animation_composition.py` | composition contract |
| `tests/test_code_animation_consistency.py` | consistency across cuts |

The project is **governed on that branch**, not only the drivers:

| Artifact | Present on `fix/49-skill-route-ci` |
|---|---|
| `project.yaml` | yes — `status: AUDIO_FIRST_P0`, `voice_provider: "miniMax/speech-2.8-hd"`, `duration_sec: 25.0`, and a `design_deviation` note recording that this is a 20–30 s P0 loop rather than a finished episode |
| `receipts/` | yes — `audio-first-plan.json`, `build-easel.json`, `cover.json`, `qc-report.json`, `review-bundle.json` |
| `qc-report.json` | `overall: PASS`, 18 checks, 0 FAIL/WARN |
| `script/` | `assets.json`, `claim-map.json`, `cut-plan.json`, `lines.json` |
| `motion/.gitignore` | excludes `**/.hyperframes/`, `**/renders/`, `node_modules/` — render state does not travel |
| absolute host paths in tracked motion files | **none** |
| tracked files under the project | 43 |

Its state is the problem:

| Fact | Value |
|---|---|
| Commits ahead of `main` | **108** |
| Open PR | **none** — `gh pr list --head fix/49-skill-route-ci` returns `[]` |
| Relationship to `#49` | `#49` (`feat/content-router`) was **CLOSED unmerged** on 2026-11-01 |
| `#45` / `#46` (narration v2 / v3) | **CLOSED unmerged** 2026-10-30 |
| On the current branch | absent — the working-tree `projects/easel-fi-audio-first/` is an untracked copy |

So the accurate statement is not "we need to build a Motion adapter". It is:
**a Motion adapter was built, proven, and then stranded.** Any plan that starts
by writing one repeats 2026-10-28.

---

## 6. Corrections to the circulating review

An audit that repeats unsupported claims is worthless. Four items in the
review brief do not survive checking.

### 6.1 The voice clone: what is proven, what is not

The review says the clone was "created successfully, then blocked by balance".
The repo holds two receipts that disagree, and **neither may simply overwrite the
other**, because the later diagnosis records that the raw provider responses were
never preserved:

- `RAW_ERROR_PRESERVATION.status`: `"HISTORICAL_RAW_RESPONSE_UNAVAILABLE"`
- missing: "trace_id for all three attempts", "base_resp.status_code for all three
  attempts", and "the actual request host per attempt"
- its own instruction: "do not reconstruct a trace_id or a provider status code
  for the historical attempts"

So the defensible record is a ladder, not a verdict swap:

| Question | Answer | Basis |
|---|---|---|
| Did the historical activation attempts fail? | **Yes** | `founder-voice-activation-history.json`: every attempt `REFUSED_PRECHECK` or `ACTIVATION_FAILED`, `charged_cny: "0.00"` |
| Was the clone object created? | **Yes**, but never first-use activated | `activation_state: "NOT_ACTIVATED -- no successful first synthesis, no fee paid"` |
| Was CLI credential binding / host mismatch real? | **Yes** | `ROOT_CAUSE: "CLI_REGION_MISMATCH_VERIFIED + CLI_CREDENTIAL_BINDING_VOID (composite)"` |
| Did "insufficient balance" reflect a real pay-as-you-go execution path? | **Not independently confirmable** | `founder-voice-route-receipt.json` says `ACTIVATION_CASH_INSUFFICIENT`; the diagnosis says the PAYG route "has never actually been transmitted". The raw status code that would settle it was destroyed by the CLI before any receipt saw it |
| Does the voice still exist on 2026-11-01? | **Unknown** | requires one read-only list call; the retention rule is a documented expectation, not an observed deletion |

The 2026-10-19 date is real but is not an "activation deadline":

- `ttl_seconds: 604800` (7 days)
- `first_use_deadline_utc: "2026-10-19T11:59:16Z"`
- `NEXT_HUMAN_ACTIONS`: "if no T2A call uses `founder_primary_v1` by then, the
  provider deletes it and a re-clone (with a fresh authorisation) becomes the
  only route"

Today is 2026-11-01 — 13 days past that deadline. The date is a documented
expectation, **not a receipt of deletion**. Claiming the voice is gone without a
provider response would repeat exactly the error this section is about.
**OPEN:** one read-only list check, then record what the server actually says.

Separately, `founder-voice-clone-receipt.json` records a *later* re-clone attempt
refused with `2061 MODEL_NOT_ON_PLAN` — a third, distinct fact.

Disposition: `founder-voice-route-receipt.json` should carry
`SUPERSEDED_BY_DIAGNOSIS`, and the diagnosis should carry its own
`RAW_ERROR_PRESERVATION` limitation. Neither file may be overwritten, deleted or
rewritten. The append-only rule stated in
`founder-voice-activation-history.json` is the principle at stake — "Removing a
failed entry would make the record of what was tried look different from what was
tried."

**Consequence for the plan:** the first audio candidate must be the open-model
voice already proven live (`Chinese (Mandarin)_Reliable_Executive`, used in
`easel-fi-audio-first`), not the founder clone.

### 6.2 The proposed storyboard rests on a retired claim

The review's beat 「左侧 Gateway 通信成功、右侧 Web 依赖失败」 is not
supportable. `docs/CURRENT-STATE.md:103-107` retires it:

> "The earlier '6/7 doctor FAILs' list described a doctor version that checked
> Web UI packages… The current `doctor.py` does not run those checks, so that
> claim is retired rather than repeated. Web workbench readiness is unverified,
> not failed."

`15-easel-doctor-fails.png` is a 2026-10-03 artifact. Using it as present-tense
evidence would fabricate a current claim.

### 6.3 The skill-layer split does not sum

The count of 114 is real — MEASURED: 114 subdirectories under
`.runtime/easel/skills/openclaw/`, 114 with `SKILL.md`. The distribution in the
review (9 / 16 / 51 / 20 / 11) omits the six-work base layer and sums to 107.
The repository's own table (`docs/skill-function-mapping.md`) totals **113**
(6 + 9 + 16 + 51 + 20 + 11), so the repo is off by one against its own directory
count, and `script/master.md` says 52 creative-layer skills where the mapping
says 51. Any on-screen number must be re-derived, not copied.

### 6.4 `huashu-motion` is not installed

As above. A plan that assumes it is available is a plan with a missing
dependency.

---

## 7. Why the automated gate passed a video nobody would publish

The automated QC that passed it performs only technical checks: file exists,
size, ffprobe parse, resolution, 9:16 aspect, duration range, codec, audio
presence, silence, subtitle burn, and similar. None of them measure:

- inter-frame motion, or the absence of it;
- time a single composition is held;
- on-screen text height relative to frame height;
- black or empty area as a proportion of the frame;
- slide-likeness, information density, or safe areas.

A counting caveat: the `21` in `human-review.json` (`auto_qc_checks: 21`) is a
receipt field, not the length of `qc_video.py`'s own list — that file has 22
`checks.append` sites, several of them conditional. The two numbers must not be
quoted as if they were the same measurement.

The rejected file is 96.9 % static and passed every one of them. The gate is not
broken — it simply measures a different property than the one the Founder
judged. That is the whole defect, stated in one line.

---

## 8. Remediation plan

Sequenced by what the governance rules actually permit. ADR-014 holds P2
expansion from 2026-11-01 to 2026-11-07 and authorises, inside that window, only
the platform registry, ADR-015 and the Content Bundle contract. **A new Motion
adapter module is not authorised before 2026-11-08** absent an Owner exception
recorded inside ADR-014.

### Stage 0 — authorised now (this audit)

| Item | State |
|---|---|
| Record `REJECTED_FOUNDER` on `projects/easel-review/receipts/human-review.json` | DONE in this change |
| This audit report | DONE in this change |
| Measured baseline for the rejected artifact | DONE (§2) |

### Stage 1 — measurement before construction (no new module)

1. Add a `motion` block to `qc_video.py` computing freeze runs with the exact
   filter used in §2, and fail a verdict below a calibrated floor.
2. Re-run it against the four known artifacts to calibrate thresholds:
   62.0 s @ 96.9 %, 25.0 s @ 0.0 %, 44.8 s @ 40.9 %, 38.9 s @ 5.2 %.
3. This is a change to an existing ops script, not a new module.

### Stage 1b — recover, do not rebuild

4. Triage `fix/49-skill-route-ci` commit by commit and lift only what the motion
   path needs onto a fresh issue-scoped branch: `scripts/build_motion_film.py`,
   `scripts/build_code_animation_sample.py`, `projects/easel-fi-audio-first/motion/*`,
   and their tests. **Do not merge the branch wholesale** — 108 commits, mixed
   scope, and its parent PR `#49` was already closed as superseded.
5. Record in `docs/CURRENT-STATE.md` that this work exists, so the next agent
   does not start again. A stranded branch that nobody records is how the same
   capability gets rebuilt three times.

### Stage 2 — one seam, not a second orchestrator

6. Make M5 use `manifest_to_storyboard` instead of its inline builder
   (`m5_production.py:603-612`), so the repo has one translator. `video` support
   already exists there — **but this is not a drop-in swap.** The two builders
   do not share a contract: M5 emits `duration_s` per line, `caption`,
   `narration`, `claim` and `source_type` derived from its own evidence chain,
   while `manifest_to_storyboard` emits `duration`, `shot_id`, `source`, and its
   own `source_type` mapping. Field-by-field mapping, duration semantics and the
   audio/evidence fields must be reconciled and regression-tested before the swap
   is claimed complete.
7. Give `stage_narration` a provider parameter with the current SAPI path as the
   default, so the existing offline behaviour is preserved and a verified
   provider is selectable rather than unrepresentable.
8. In V1, stop forcing `--engine edge` (`run_v1.py:297`) so the upstream `auto`
   router and `VOICE_PROVIDER` can be used, and make `--voice-provider` reach
   `run_easel` instead of being dropped at `:345-346`. This is the cheapest
   voice change in the repo because the seam already exists upstream.
9. Add the missing tests — one asserting the motion value actually used per
   shot, one asserting the narration engine actually invoked. Without them the
   next change to either is unobservable.

### Stage 3 — authoring, not just code

10. The rejected storyboard cannot be edited in place: `projects/easel-review/
    script/storyboard.json` is a **locked input**, pinned by
    `tests/test_locked_input_reproducibility.py`. A new cut needs a new
    storyboard and an updated lock, in the same change, plus a new receipt —
    not an edit to the pinned file.

### Stage 4 — sanction the prototype (after 2026-11-08, or by Owner exception)

11. Promote `easel-fi-audio-first` into a governed project: `project.yaml`,
    `receipts/`, QC receipt, logical `project://` paths (the prototype embeds
    absolute `D:\` paths in its storyboard and audio concat lists).
12. Register `huashu-art-motion` as a declared capability in
    `runtime/skill-registry.json` with per-asset licence enforcement, mirroring
    the `media-use` entry. Its MIT licence covers the code, never the demo assets.
13. Mark `founder-voice-route-receipt.json` superseded by
    `founder-voice-activation-diagnosis.json` so the two verdicts stop competing.
14. Only then attempt a reviewed deliverable and route it to Founder review.

**Not in scope**, and why: no second compositor (ADR-002, pinned Easel); no
digital-human path (unverified and outside the current hold); no new platform
module; no automatic publication.

---

## 9. Replacement storyboard (proposal — not yet produced)

50–60 s, 9:16 1080×1920, same topic. Every beat carries its real evidence and
its date; nothing is presented as current unless it was re-measured today.

| Time | On screen | On-screen text (≤8 字) | Evidence | Motion | Source |
|---|---|---|---|---|---|
| 0–4 s | Six frozen frame thumbnails from the rejected cut, laid side by side, then a counter | 62 秒，59 秒没动 | MEASURED §2 | kinetic type, counter | local recording |
| 4–12 s | `skills/openclaw/` directory filling to 114, splitting into 6 layers | 114 个 Skill | MEASURED 2026-11-01 | diagram animation | `13/14-easel-*.png` |
| 12–22 s | Two code paths drawn as rails: V1 → PNG (`run_v1.py:387`), M5 → `"motion":"static"` | 两条生产路径，都只出图 | VERIFIED | code-sweep | source excerpt |
| 22–34 s | The composer's `shot["video"]` contract opening while the rails stay still | 合成器早就支持视频 | VERIFIED `assemble.py:240` | view-swap | source excerpt |
| 34–46 s | The 25 s prototype playing, freeze metric ticking 96.9 % → 0.0 % | 实测 0% 静止 | MEASURED §5 | real clip playback | `easel-fi-audio-first/final` |
| 46–56 s | Three ungoverned projects vs. one `project.yaml`; gap highlighted | 能力有，流程没有 | VERIFIED §5 | diagram animation | directory tree |

Voice: MiniMax `speech-2.8-hd` (`Chinese (Mandarin)_Reliable_Executive`), the
variant with live receipts. Founder clone only after §6.1 is resolved.

Every historical screenshot must be labelled with its date. If `doctor.py` is
not re-run on the day of production, the result must not appear at all.

---

## 10. Visual quality gate — proposed checks

Thresholds are **calibrated guesses** derived from the four measured artifacts,
not borrowed constants. Each must be re-measured before it is enforced.

| Check | Proposed rule | Measurement |
|---|---|---|
| `no_long_freeze` | no single freeze run > 2.0 s | `freezedetect=n=0.001:d=2.0` |
| `static_ratio` | near-static total < 25 % of duration | sum of `freeze_duration` |
| `motion_present` | mean frame-difference above a floor | `signalstats` / `tblend` |
| `shot_cadence` | no shot holds longer than 8 s | storyboard `duration` |
| `text_legibility` | largest text block ≥ 4 % of frame height | Pillow bbox on extracted frames |
| `safe_area` | all text inside 10 % margin | Pillow bbox |
| `frame_utilisation` | non-background area ≥ 30 % | luma histogram |
| `slide_likeness` | warn when ≥ 3 consecutive checks above fail | aggregate |

Calibration evidence: 96.9 % / 40.9 % fail all of these; 0.0 % / 5.2 % pass
`static_ratio` and `no_long_freeze`. The 2.0 s and 25 % values are chosen to sit
between the two clusters, not derived from a standard.

---

## 11. Open Owner decisions

1. **Motion adapter before 2026-11-08?** ADR-014 currently says no. Either grant
   a limited exception inside ADR-014 or wait.
2. **Voice clone.** Authorise a read-only voice-list check, and decide whether a
   re-clone (CNY 9.9) is worth it versus the proven open-model voice.
3. **Promote `easel-fi-audio-first`** into a governed project — it is the fastest
   route to a reviewable dynamic sample.
4. **Adopt `huashu-art-motion`** as a declared capability, with per-asset licence
   handling.

---

## 12. Method and verification

Six read-only surface audits were each re-checked by a separate adversarial agent
instructed to refute them. All six came back `PARTLY_SOUND` — every surface
contained at least one claim that did not survive. Corrections applied to this
report as a result:

- the rejected artifact is attributed to **V1**, not M5 (§4);
- a first draft cited `run_v1.py:387` as the production shot builder; that line
  belongs to the **fallback** engine, and the production path is storyboard-driven
  (§4 Link 1). This is the correction with the largest effect on the plan;
- the upstream `VOICE_PROVIDER` / `auto` seam V1 defeats was added (§4 Link 0);
- the unenforced `Huihui` receipt label was added (§4 Link 3);
- the check-count caveat replaces an earlier "21 checks" assertion (§7);
- §6.1 was rewritten after review: the later diagnosis does **not** settle the
  "insufficient balance" question, because it records that the raw provider
  status and trace id were never preserved (§6.1).

The numbers in §2 and §5 were produced by commands run here (`ffprobe`,
`freezedetect`, `ffmpeg signalstats`), not quoted from an agent.

## 13. Delivery state

These are eight different facts and none implies another.

| Fact | State on 2026-11-01 |
|---|---|
| Exists only in the local working tree | **yes** — this report and the receipt edit |
| Committed to a branch | see the commit that carries this file; the branch and SHA are named in the hand-off message, not here |
| Pushed to GitHub | **not at the time of writing** unless the hand-off says otherwise |
| Pull request opened | **no** |
| CI green | **no run** |
| A real replacement video produced | **no** — §9 is a design |
| Founder approved | **no** — the only Founder decision recorded is the rejection |
| Manually published with a URL | **no** |

The rejection receipt in `projects/easel-review/receipts/human-review.json` binds
the verdict to `graded_artifact` plus `sha256`, so future readers can tell which
file was judged without trusting a filename. The tracked `final/final.mp4` is a
**different, older** render and is not the rejected object.

## 14. What this audit did not do

- No provider call, no paid generation, no credential action.
- No file was deleted, moved or renamed.
- No project was promoted, no receipt fabricated, no score invented.
- No merge, no direct push to `main`.
- The replacement storyboard was **not produced**. It is a design, and §8 gates
  its production behind ADR-014.
