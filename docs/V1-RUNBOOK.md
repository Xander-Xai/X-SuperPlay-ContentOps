# V1 Runbook — X-SuperPlay-ContentOps

This is the operational manual for the V1 evidence-first video pipeline.

## 0. Environment sanity

Windows PowerShell:

```powershell
python scripts\doctor.py
```

WSL Ubuntu:

```bash
python3 scripts/doctor.py
```

Expected: all checks OK, including Easel checkout at commit
`3fe2d9904c1619281ef57f81d9ee0b7854998399`.

## 1. Create a new project

```powershell
python scripts\new_project.py --slug easel-review --title "Easel 实测"
```

Output: `projects/easel-review/` with `project.yaml` and standard subdirs.

## 2. Drop real source assets

Put your real evidence into:

```
projects/easel-review/
  sources/
    screenshots/        <- PNG/JPG of GitHub page, README, UI, etc.
    diagrams/           <- your own architecture / comparison diagrams
    recordings/         <- screen recordings (optional for V1)
    documents/          <- text excerpts, release notes
```

`ai_visuals_allowed: auxiliary_only` means you may add to
`assets/generated/`, but the run pipeline prefers real assets first.

## 3. Run V1

```powershell
python scripts\run_v1.py projects/easel-review
```

This will:

1. Detect real images in `sources/screenshots|digrams`.
2. Render voice via Windows SAPI (falls back to silence if unavailable).
3. Compose 6 shots (HOOK / problem / evidence / discovery / limits / next).
4. Concat to `projects/easel-review/work/rough.mp4`.
5. Copy to `projects/easel-review/final/final.mp4`.

## 4. Run QC

```powershell
python scripts\qc_video.py projects/easel-review
```

Emits `receipts/qc-report.json` + `qc-report.md`.

## 5. Manual publish

V1 does **not** auto-publish. Open `final/final.mp4`, review, and upload
through each platform's creator UI manually. Record the publish event in
`projects/<slug>/receipts/publish-receipt.md`.

## 6. Failure handling

If `run_v1` returns `BLOCKED`, do not retry blindly. Read the `reason`
field, fix the underlying cause (font missing, image unreadable, etc.), then
re-run.

If `qc_video` returns `FAIL`, the video is **not** production-ready. Common
causes:

- `duration_range` out of [30, 120] sec → adjust script length.
- `aspect_ratio_9_16` wrong → re-export from ffmpeg with the standard scale+pad.
- `audio_present` false → TTS provider missing, install espeak or fix .env.

## 7. Easel integration

Easel v0.2.1 is checked out at `.runtime/easel/`. To call an Easel Skill
from the run pipeline, use:

```powershell
python .runtime/easel\scripts\...   # see easel docs
```

Do **not** auto-pull updates. Re-run `scripts/bootstrap.*` only when the
Founder approves an upstream upgrade.