# Motion recovery inventory — what to lift from `fix/49-skill-route-ci`

Date: 2026-11-01
Branch inspected: `fix/49-skill-route-ci`, 108 commits ahead of `origin/main`,
**no pull request**
Basis: `reports/audits/video-quality-failure-audit-2026-11-01.md`

Read-only. Nothing was checked out, reverted, merged, executed or deleted. The
branch was read with `git show` / `git ls-tree` only.

---

## 1. Why this file exists

The audit's decisive finding is that the Motion remediation was built and then
stranded. Before anyone writes a Motion adapter, this inventory establishes what
already exists, whether it is correct, and what can be lifted without dragging
108 mixed-scope commits onto `main`.

---

## 2. Selection

### 2.1 Lift — scripts

| Path | Role | Evidence it works |
|---|---|---|
| `scripts/build_motion_film.py` | `speed → split → timeline → render → compose → qc`, writes `receipts/motion-build.json` | header documents both compose defects and the fixes; `PAD_S = 0.4`; probes every clip; asserts film vs timeline within 0.1 s |
| `scripts/build_code_animation_sample.py` | compose driver: timeline, audio-first narration placement, captions | called by `build_motion_film.py` `compose` stage |
| `scripts/presenter_opening.py` | declared presenter-opening step | used by the `presenter` segment branch |
| `scripts/package_code_animation_sample.py` | packaging of the sample | pair with the compose driver |

### 2.2 Lift — tests

| Path | Covers |
|---|---|
| `tests/test_motion_build_reliability.py` | cache never skips an unverified render; compose envelope must be success JSON; composer output bound to the actual file SHA |
| `tests/test_code_animation_composition.py` | composition contract |
| `tests/test_code_animation_consistency.py` | consistency across cuts |

All three must be wired into `.github/workflows/ci.yml`. An unwired suite does
not run, and `check_repo_policy.py` fails on it.

### 2.3 Lift — project

`projects/easel-fi-audio-first/` — 43 tracked files, already governed:

- `project.yaml` (`status: AUDIO_FIRST_P0`, `voice_provider: "miniMax/speech-2.8-hd"`, `duration_sec: 25.0`)
- `receipts/` — `audio-first-plan.json`, `build-easel.json`, `cover.json`, `qc-report.json`, `review-bundle.json`
- `qc-report.json`: `overall: PASS`, 18 checks, 0 FAIL/WARN
- `script/` — `assets.json`, `claim-map.json`, `cut-plan.json`, `lines.json`
- `motion/` — six compositions (`arch-flow`, `code-sweep`, `metric-count`, `narration-bar`, `result-chain`, `view-swap`), each with `hyperframes.json` / `index.html` / `package.json`
- `motion/.gitignore` — `**/.hyperframes/`, `**/renders/`, `node_modules/`

### 2.4 Do not lift

| Item | Reason |
|---|---|
| The branch itself | 108 commits, mixed scope (gzh vendoring, account routes, router work) |
| `**/.hyperframes/` | render state and cache; excluded by the branch's own `.gitignore` |
| `**/renders/`, `node_modules/` | same |
| Any `work/` MP4 or WAV | gitignored artifact policy |
| `projects/easel-enhanced-golden/v3-sample-*` | unrelated to this remediation |

### 2.5 Verify before lifting

- [ ] `build_motion_film.py` `DEFAULT_ENGINE` is an absolute host path
      (`C:\Users\Administrator\.agents\skills\huashu-art-motion\scripts\engine\render.py`).
      Confirm `--engine` overrides it; if not, the fallback must be a resolved
      path or an explicit failure, never a silent default to someone's machine.
- [ ] Confirm the four scripts import nothing else from the branch that is not in
      §2.1–2.3. `git grep` each import against the lift set.
- [ ] Confirm no tracked file in the lift set carries an absolute path. The
      motion tree is clean; run the same check over `script/` and `receipts/`.

---

## 3. The two documented defects, verified in code

| Defect | Claim | Code |
|---|---|---|
| `pad_mode=trim` millisecond shortfall | a clip milliseconds shorter than its beat hard-fails at compose | `PAD_S = 0.4` headroom; `if got < segment["duration"]: raise SystemExit(... pad ...)` |
| half-written MP4, no `moov` atom | upstream reports an *empty* ffmpeg error after minutes of work | probe-before-compose loop; `_log("render", f"{len(track)} segments probed")` |
| film/dialogue drift | assembled film must match the timeline | `if abs(film_s - expected) > 0.1: raise SystemExit(...)` |

All three are addressed in the code that would be lifted, and the first two are
asserted by `tests/test_motion_build_reliability.py`.

---

## 4. Reproduction plan for the existing 25 s sample

**Step 0 is already verified.** The local working-tree render and the stranded
branch's committed receipt describe the same bytes:

| Source | SHA-256 |
|---|---|
| `projects/easel-fi-audio-first/receipts/build-easel.json` → `output.sha256` | `d6c0795e51e4ed62400c6937d6c05e01d3b9134df1c1b2cfb54d80962b8f1bee` |
| `projects/easel-fi-audio-first/final/easel.mp4` on this host | `d6c0795e51e4ed62400c6937d6c05e01d3b9134df1c1b2cfb54d80962b8f1bee` |

They match exactly. So the sample is not folklore: the artifact on disk **is**
the one the receipt bounds, and the receipt also binds its narration
(`531e2c08…cdf1`, 25.000313 s), its captions (`62f0617f…eae`) and all six motion
inputs by digest.

What remains is the stronger claim — that the build reproduces those bytes from
source. That needs the drivers lifted and run:

1. Lift §2.1–2.3 onto the remediation branch.
2. Re-run the build with `--engine` pointed at the local `huashu-art-motion`.
3. Compare: duration (25.0 s), resolution (1080×1920), near-static ratio (0.0 %),
   audio mean/max dB, and the output SHA-256 against `d6c0795e…`.
4. Record the result in a **new** receipt. A re-run must not overwrite
   `build-easel.json` — the repo's append-only rule applies.

If step 2 needs a provider call, it stops: the narration already exists as a
receipt-bound WAV, and re-synthesis is not authorised.

---

## 5. Known limits of the sample

- `project.yaml` states `status: AUDIO_FIRST_P0` and carries a
  `design_deviation` note: this is a 20–30 s P0 loop, not a finished episode.
- Its captions are about the video-quality problem itself
  (「口播四十四秒，画面不能停四十四秒」), so it is a **technique proof**, not the
  Easel content deliverable.
- `qc-report.json` records `overall: PASS` but has no `currency` field, so the
  canonicalisation the M4.5 receipts went through has not been applied here.
- It proves motion + narration + Easy compose work. It does not prove a
  publishable episode, a rights-cleared asset set, or Founder approval.

---

## 6. Recommendation

Lift and verify; do not redesign. If §4 succeeds, the production change is
narrower than the audit first assumed: the composer already accepts video shots,
the drivers already exist, and only the entry points (M5's builder and V1's
forced `--engine edge`) need to change.
