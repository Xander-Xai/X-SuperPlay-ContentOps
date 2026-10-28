# Code-animation specs (huashu-art-motion)

Each `p0N.json` is a `t2_keynote_ui` clip: 4.0 s, 1080×1920, 30 fps, theme
`ink`, brand accent `#38BDF8`. The engine is the external skill
`huashu-art-motion` (MIT), installed at
`C:\Users\Administrator\.agents\skills\huashu-art-motion`, upstream commit
`8a0d7d72ca65fcce6f8ba82c4a6c8dfe35b8422c`, with a local Windows adapter
(`LOCAL-PATCH.md`: Chrome/Edge channel fallback; run with `PYTHONUTF8=1`).

## Render one clip

```powershell
$env:PYTHONUTF8 = "1"
python C:\Users\Administrator\.agents\skills\huashu-art-motion\scripts\engine\render.py `
  --spec "D:\Projects\X-SuperPlay-ContentOps\projects\easel-fi-what-is-agent\motion\specs\p01.json" `
  --out  "D:\Projects\X-SuperPlay-ContentOps\projects\easel-fi-what-is-agent\work\clips\p01.mp4"
```

The host Python is used on purpose: it resolves Playwright's Chromium at
`D:\DevCaches\ms-playwright\chromium-1223`. `uv run --with playwright` would
fetch a newer Playwright build and ask for a browser revision that is not on
this machine.

## Compose the sample

```powershell
python scripts\build_code_animation_sample.py projects\easel-fi-what-is-agent
python scripts\qc_video.py projects\easel-fi-what-is-agent --video easel.mp4
```

The driver places each synthesized line at its 4 s placement start, writes the
SRT from the measured durations, burns it with the Future Intelligence DNA
style, and writes `receipts/sample.json`. `receipts/qc-summary.json` binds that
verdict to the output SHA.

## Why `t2_keynote_ui`

It is the “发布会界面” grammar: one thing per screen, cards and steps, no
real footage. The grammar card recommends `t1_3b1b` for mechanisms and `y1`
for scale; this sample proves the pipeline on the simplest grammar first.
