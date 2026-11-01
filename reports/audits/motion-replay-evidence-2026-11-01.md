# Motion replay evidence — 2026-11-01

Date: 2026-11-01
Subject: whether the 2026-10-28 `easel-fi-audio-first` motion output can be
regenerated from its source, as opposed to re-developed.
Method: isolated Git worktree from `fix/49-skill-route-ci`, read-only against the
original working tree.

Status legend: **MEASURED** (a command ran here), **VERIFIED** (read from a
committed receipt), **BLOCKED** (a gate or a missing input stopped it),
**DEVIATION** (a recorded departure from the pinned configuration).

---

## 1. Result in one line

**L1 holds completely; L2 holds for the render layer and is BLOCKED for the
compose layer.** The six motion clips regenerate from their HTML source with
visual equivalence, but the film cannot be re-composed without a human copy
review that was never recorded.

Byte-level reproduction was **not** achieved and is not claimed.

---

## 2. Asset protection first

Before any work, every file under `projects/easel-fi-audio-first/` was hashed
into `D:\Temp\AI-Agents\claude\motion-recovery-2026-11-01\original-assets-manifest.json`
(88 files). The original directory was not moved, deleted, or overwritten. All
replay work happened in separate worktrees.

---

## 3. L1 — hash binding

| Object | SHA-256 | Matches |
|---|---|---|
| `final/easel.mp4` | `d6c0795e51e4ed62400c6937d6c05e01d3b9134df1c1b2cfb54d80962b8f1bee` | `receipts/build-easel.json` ✓ |
| `work/narration.wav` | `531e2c081dc0342524fd705e456ae521e66071296272003600808e89a5bcdfd1` | ✓ (25.000313 s) |
| `assets/captions/cut.srt` | `62f0617f02f615adadb4912e0150c76d2c8243efe776a755b8657eff33d31eae` | ✓ |
| six motion clips | 6 / 6 | `script/assets.json` ✓ |

MEASURED. The artifact on disk **is** the one the committed receipt bounds.

---

## 4. L2-render — regenerated from source

The six compositions are HyperFrames projects (`hyperframes.json` /
`index.html` / `package.json`). Rendered in place in a worktree:

```
npx --no-install hyperframes render . -o ../../work/motion/<name>.replay.mp4 -q delivery
```

### DEVIATION — runtime version

The project pins `hyperframes@0.8.208`. The host resolves **0.8.226**, and
`0.8.208` is not in the npx cache; installing it would have required a network
download, which this task does not authorise. The CLI itself reports the drift:
"This project pins hyperframes@0.8.208 (latest 0.8.226)."

Every number below is therefore "same source, different renderer".

### Comparison

| Clip | Spec | Frames | Duration | SSIM | PSNR (dB) | Bytes (orig / replay) |
|---|---|---|---|---|---|---|
| arch-flow | 1080×1920 30fps | 150 | 5.000 s | 0.9954 | 52.34 | 1,894,776 / 1,956,731 |
| code-sweep | 1080×1920 30fps | 150 | 5.000 s | 0.9945 | 51.20 | 2,471,464 / 2,568,995 |
| metric-count | 1080×1920 30fps | 150 | 5.000 s | 0.9946 | 52.07 | 1,605,413 / 1,682,343 |
| narration-bar | 1080×1920 30fps | 150 | 5.000 s | 0.9948 | 51.70 | 1,620,177 / 1,670,303 |
| result-chain | 1080×1920 30fps | 150 | 5.000 s | 0.9951 | 52.14 | 1,719,070 / 1,777,765 |
| view-swap | 1080×1920 30fps | 150 | 5.000 s | 0.9952 | 52.27 | 1,700,716 / 1,773,428 |

MEASURED (`ssim`, `psnr` lavfi filters).

All six replay clips: **0.00 s frozen of 5.0 s** (MEASURED, `freezedetect`), so
the regenerated clips are still genuinely animated.

Byte-identical: **no**, for all six. The difference is consistent with an encoder
or renderer version change, not with a content change: identical geometry, frame
count, duration, and SSIM ≥ 0.9945.

This is **functional and visual equivalence**, not byte reproduction. The two
are distinct claims and only the first is supported.

---

## 5. L2-compose — BLOCKED

`scripts/build_evidence_cut.py:354` calls
`contentops.workflow.copy_review.require_approved(project)`. The project has no
`receipts/script-review.json`, because the gate was introduced **after** the
2026-10-28 build (commit `b54802b`, "stop every producer until a person has
reviewed the copy").

No review record was fabricated, and the gate was not bypassed. Recomposing the
film therefore requires a real human copy review first — an Owner decision, not
an agent one.

**State: `BLOCKED_COPY_REVIEW`.**

Since 2026-11-01 the fingerprint also covers `video`, `caption`, `claim` and
`source` plus the declared asset digests, so an approval of this sample would
bind the clips as well as the words. A review request — the full copy, the beats
and the `copy_sha256` — is at
`reports/audits/copy-review-request-easel-fi-audio-first-2026-11-01.md`. It is a
request, not a decision.

Consequence: the film's byte reproduction is **unproven**, and will remain
unproven until a copy review exists. The render layer is proven.

---

## 6. Scope decisions and exclusions

| Item | Decision | Why |
|---|---|---|
| `tests/test_code_animation_composition.py` | **excluded** | asserts `qc_video._graded_inputs`, which does not exist on `main`; the branch's `qc_video.py` is **406 insertions** ahead. Lifting it would turn R2 into a QC-behaviour change |
| `projects/easel-fi-what-is-agent/` | **excluded** | only needed by the excluded test; 62 files of unrelated scope |
| `tests/test_motion_build_reliability.py` | included | 3 / 3 pass |
| `tests/test_code_animation_consistency.py` | included | 6 / 6 pass |

Two suites (9 tests) are green on a `main`-based branch with this lift.

---

## 7. Files in this change

### Code (9)

```
scripts/build_motion_film.py
scripts/build_code_animation_sample.py
scripts/package_code_animation_sample.py
scripts/presenter_opening.py
scripts/split_narration_lines.py
src/contentops/workflow/copy_review.py
tests/test_motion_build_reliability.py
tests/test_code_animation_consistency.py
.github/workflows/ci.yml            (two steps added)
```

`src/contentops/workflow/copy_review.py` is stdlib-only and was the only missing
module in the import closure.

### Project

`projects/easel-fi-audio-first/` — 43 tracked text files: `project.yaml`, five
receipts, `script/` (assets, claim-map, cut-plan, lines), six HyperFrames
compositions, card/cover HTML, source READMEs. No media binaries; the `.gitignore`
under `motion/` excludes `.hyperframes/` and `renders/`.

---

## 8. Commands run

```
git worktree add <tmp>/wt fix/49-skill-route-ci
npx --no-install hyperframes --version              # 0.8.226
cd <project>/motion/<name> && npx --no-install hyperframes render . -o ../../work/motion/<name>.replay.mp4 -q delivery
ffmpeg -i <orig> -i <replay> -lavfi "[0:v][1:v]ssim" -f null -
ffmpeg -i <orig> -i <replay> -lavfi "[0:v][1:v]psnr" -f null -
ffmpeg -i <replay> -vf "freezedetect=n=0.001:d=0.4" -map 0:v -f null -
python tests/test_motion_build_reliability.py
python tests/test_code_animation_consistency.py
```

No provider call, no paid generation, no dependency download, no runtime
replacement, no publication.

---

## 9. Watchable sample

The original 25 s cut is at `projects/easel-fi-audio-first/final/easel.mp4`
(local, gitignored, SHA-256 `d6c0795e…`). It is a **technique proof about this
very defect**, not an Easel episode, and it has not been reviewed by the Founder.

---

## 10. What this does and does not establish

| Question | Answer |
|---|---|
| Is the existing sample bound to its receipts? | **Yes** — L1, all four objects |
| Can the motion clips be regenerated from their source? | **Yes**, with visual equivalence (SSIM ≥ 0.9945) |
| Byte-identical reproduction? | **No**, and not claimed |
| Can the film be re-composed? | **Not yet** — blocked by a missing human copy review |
| Is a new Motion Adapter needed? | **No** — the drivers exist and run |
| Is the sample publishable? | **No** — technical sample only |
