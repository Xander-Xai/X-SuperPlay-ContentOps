# Runbook

[English](RUNBOOK.md) | [简体中文](RUNBOOK.zh-CN.md)

> Real executable commands. Derived from actual script behavior, not assumptions.
> Last updated: 2026-10-03

## 0. Environment check

```powershell
python scripts/doctor.py
```

Checks: Python ≥3.10, Node ≥22, FFmpeg, ffprobe, git, Easel checkout (v0.2.1), repo layout.

Expected: all OK. If Easel checkout fails, run bootstrap (§1).

## 1. Bootstrap (first time or after cleanup)

```powershell
python scripts/bootstrap.ps1    # Windows
bash scripts/bootstrap.sh       # WSL/Linux
```

If Easel runtime is missing/broken:

```powershell
python scripts/resolve_easel.py --bootstrap
```

Acquisition ladder: git clone (Strategy A) → release archive (Strategy B) → BLOCKED.

## 2. Verify Easel runtime

```powershell
python scripts/verify_easel_runtime.py --resolve-tag
```

Expected: `VERIFIED · 982/982 blobs matched · 0 mismatch / 0 missing / 0 extra`

Offline mode (no network):

```powershell
python scripts/resolve_easel.py --offline
```

Uses recorded provenance in `runtime/easel-runtime.json`.

## 3. Create a new project

```powershell
python scripts\new_project.py --slug my-video --title "My Video Title"
```

Creates: `projects/my-video/` with `project.yaml` and standard subdirs.
Refuses to overwrite existing project.

## 4. Prepare source assets

Place real evidence in:

```
projects/my-video/
  sources/
    screenshots/    ← PNG/JPG of GitHub, UI, results
    diagrams/       ← architecture/comparison diagrams
    recordings/     ← screen recordings (optional for V1)
    documents/      ← text excerpts, release notes
```

Author the script:

```
projects/my-video/
  script/
    master.md        ← master script (human-authored or LLM-drafted + corrected)
    storyboard.json  ← per-shot structure with provenance
```

## 5. Run V1 pipeline

### Production engine (Easel)

```powershell
python scripts\run_v1.py projects\my-video
```

What it does:
1. Reads `script/storyboard.json` (requires authored storyboard, not built-in lines)
2. Reads `script/master.md` (requires authored script)
3. Resolves pinned Easel runtime via `resolve_easel.py`
4. Generates narration via Easel `tts.py` (edge-tts, zh-CN-YunxiNeural)
5. Runs Easel `auto-short-video/assemble.py` (upstream, unmodified)
6. Burns subtitles via `assemble_easel.py` (Windows path workaround)
7. Outputs `final/easel.mp4`
8. Writes `receipts/build-easel.json`

Voice: **edge-tts** (free, no-key, no emotion engine). Marked `edge_tts_fallback`.

### Diagnostic engine (fallback)

```powershell
python scripts\run_v1.py projects\my-video --engine fallback
```

What it does:
1. Uses built-in `DEFAULT_SCRIPT_LINES` (test fixture only)
2. Renders voice via Windows SAPI → espeak → silence
3. Composes 6 shots with ffmpeg
4. Outputs `final/fallback.mp4` (NOT `final.mp4`)
5. Writes `receipts/build-fallback.json`

Voice: Windows SAPI (or silence). Marked `voice_quality: fallback`.
This engine is **diagnostic only** — never reports `production_ready: true`.

## 6. Run QC

```powershell
python scripts\qc_video.py projects\my-video
```

Checks: file existence, size, ffprobe parse, resolution (1080×1920), aspect ratio (9:16),
duration (30–120s), video codec (H.264), audio codec (AAC), audio presence,
script/storyboard existence, real-source ratio (≥70%), source provenance,
voice audibility (volumedetect), subtitle burn detection (multi-frame pixel scan).

Emits: `receipts/qc-report.json` + `qc-report.md`. Status: PASS / WARN / FAIL.

Grade a specific render:

```powershell
python scripts\qc_video.py projects\my-video --video easel
python scripts\qc_video.py projects\my-video --video fallback
```

## 7. Manual publish

V1 does **not** auto-publish. Open `final/easel.mp4`, review, and upload
through each platform's creator UI manually. Record in
`receipts/publish-receipt.md`.

## 8. Failure handling

If `run_v1.py` returns `BLOCKED`:
- Read the `reason` field
- Fix the underlying cause (missing script, missing storyboard, Easel unresolvable)
- Re-run

If `qc_video.py` returns `FAIL`:
- Video is not production-ready
- Common causes: duration out of range, aspect ratio wrong, audio missing,
  script/storyboard missing, real-source ratio < 70%

## 9. Test suite

```powershell
python scripts\test_basic.py
```

9 tests covering: doctor execution, project creation idempotency, QC FAIL on
missing video, blob SHA-1 verification, path exclusion symmetry, foreign
remote rejection, archive provenance acceptance/rejection.
