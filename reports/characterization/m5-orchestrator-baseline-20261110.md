# M5 Orchestrator Characterization Baseline — 2026-11-10

Slice 1 of the M5 orchestrator split (Issue #140). Goal: lock the currently
observable behaviour of the M5 chain on `main` before any structural change, so
every later slice can prove "zero behaviour change" against this baseline.

Everything below was executed for real on this host, offline, with zero provider
calls. Raw run artifacts stay in the gitignored `projects/_local/`
characterization directory; this document records only facts and hashes.

## Environment (this host)

| Component | Value |
|---|---|
| Repo state | `main` @ `dbc72bc` (post #139), clean worktree |
| Python | 3.13.14 in a dedicated venv (Pillow 13.0.0, PyYAML 6.0.3, opencv-python added during characterization) |
| ffmpeg / ffprobe | 8.1.1 essentials build |
| Node | v22.22.2 |
| Easel runtime | pinned v0.2.1 @ `3fe2d990`, verified by blob-SHA-1 tree compare: 982 files, 0 mismatch, 0 extra |
| Huashu skill | host user-skill installation under the home directory (`.agents/skills/huashu-art-motion`), resolved by `find_runtime` |
| Local gate | `dev_check.py` — ALL CHECKS PASSED before the characterization run |

## The run (single end-to-end M5 execution)

Entry: `scripts/m5_production.py projects/_local/characterize-m5-20261110`
(copy of the tracked `projects/m5-easel-pin` sample; the tracked original was
not touched).

| Stage | Observed |
|---|---|
| sources | 4 |
| media_use | DISABLED (no requests configured — legacy sample) |
| assets / claims | 3 / 4 |
| script | 7 lines |
| narration | Windows SAPI, offline, 45.142 s |
| subtitles | 7 cues |
| storyboard | 7 shots |
| compose | OK — `project://final/m5-easel-pin.mp4`, 1,061,877 bytes, SHA-256 `07ff16dd43a1ea97e666fdcfcda695785fe9cf2e3d3a89a4aaca70289ae4f8d0`; the visual-gate receipt records the identical digest (hash chain intact) |
| qc | PASS (audio present) |
| visual motion gate | **FAIL — gate light red** |
| final state | **BLOCKED**, `production_ready: false`, `publish_authorized: false`, `PENDING_FOUNDER_REVIEW` |

## Characterized gate behaviours (two distinct, both fail-closed)

1. **Incomplete environment → unrecognized result → BLOCKED.** With a fresh venv
   missing OpenCV, the Huashu `film_gate.py` subprocess crashed (`import cv2`),
   produced no JSON and exited 1. `evaluate_film_gate` mapped the empty payload
   to an unrecognized result and the orchestrator refused to proceed. The
   fail-closed path is real: an under-specified host cannot wave a video
   through the gate.
2. **Complete environment → explicit red verdict.** After installing
   `opencv-python`, the gate returned real measurements for the static legacy
   sample: 1 shot, `still_ratio` 0.994, longest still 17.4 s, `dead_bg` 0.906,
   0 fast actions overall — verdict **red** ("整片没有一次镜头内的快速动作，
   读起来像翻页"), with an actionable Chinese remediation brief (in-shot motion
   per the shot-language reference). A static slide-show sample is supposed to
   fail this gate; the orchestrator surfaced the full reason verbatim.

## What this locks for the split

- The ten-stage sequence and its receipt set (`m5-run.json`, `motion-stage.json`,
  `visual-gate.json`, `visual-qc.json`, `qc-report-*.json`, contact sheets) is
  the observable contract the orchestrator split must preserve stage for stage.
- The film gate sits **after** compose/QC and can BLOCK the run; the split must
  keep that ordering and the fail-closed mapping (empty payload → BLOCKED, never
  PASS).
- `production_ready` stayed `false` through every path — including a successful
  compose and a PASS QC. No code path promoted the sample.
- Known host-dependency to document in the split: the visual motion gate needs
  `opencv-python` in the executing interpreter; without it the run is BLOCKED,
  not skipped.

## Not done here (explicitly)

- No orchestrator code was changed; no stage was extracted.
- No second/third characterization run yet (B/C-style samples, media-use-enabled
  run) — the roadmap schedules them before the first extraction PR.
- No publication, no provider call, no rights change.
