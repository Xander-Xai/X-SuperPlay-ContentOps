# Code-animation specs (huashu-art-motion)

The twelve `p0N.json` files are 1080×1920, 30 fps motion beats with measured
2.4–3.4 s placement windows. They use the external `huashu-art-motion` skill
(MIT; upstream `8a0d7d72ca65fcce6f8ba82c4a6c8dfe35b8422c`) and the account palette
from Future Intelligence. P02 is a full-frame, independently redrawn
workflow-versus-agent concept diagram attributed on-screen to Anthropic's
*Building effective agents*.

The external skill owns all animation and transition primitives. ContentOps owns
measured narration placement, subtitles, BGM, receipts and review gating.

## Render one beat

```powershell
$env:PYTHONUTF8 = "1"
python C:\Users\Administrator\.agents\skills\huashu-art-motion\scripts\engine\render.py `
  --spec "D:\Projects\X-SuperPlay-ContentOps\projects\easel-fi-what-is-agent\motion\specs\p01.json" `
  --out "D:\Projects\X-SuperPlay-ContentOps\projects\easel-fi-what-is-agent\work\clips\p01.mp4"
```

The host Python is used deliberately: it resolves the locally installed
Playwright Chromium. `uv run --with playwright` would request a browser revision
that is not present on this machine.

## Render the transition film

`motion/film/eras.js` declares the measured beat sequence and only uses
huashu-native transitions. It renders every clip into an owned frame sequence,
then lets the engine compose the complete 9:16 visual track in one pass—no
ffmpeg `xfade` chain.

```powershell
$env:PYTHONUTF8 = "1"
python projects\easel-fi-what-is-agent\motion\film\render.py `
  projects\easel-fi-what-is-agent `
  --engine "C:\Users\Administrator\.agents\skills\huashu-art-motion\scripts\engine" `
  --out work\huashu-eras.mp4
```

## Compose and review

`--variant eras` keeps the baseline `final/easel.mp4`, `assets/captions/default.srt`
and `receipts/*.json` untouched; the variant writes `final/eras.mp4`,
`assets/captions/eras.srt`, `work/eras/` and `receipts/eras/`.

The eras film opens on the digital human. `motion/presenter/contract.json`
declares that opening, and the composer refuses the eras build when the
declaration is unmet — the segment dropped from `timeline.json`, a hash that no
longer matches the files, a missing asset, or a spoken line nobody verified. The
same check runs on its own:

```powershell
python scripts\presenter_opening.py projects\easel-fi-what-is-agent --check
python scripts\presenter_opening.py projects\easel-fi-what-is-agent --verify-speech
```

`--verify-speech` transcribes the opening with MiniMax `asr-1.0` and compares it
to the intended sentence. It is a detector: it can prove the words are right or
wrong, never that the delivery is usable.

```powershell
python scripts\build_code_animation_sample.py projects\easel-fi-what-is-agent `
  --variant eras --out-name eras `
  --motion-video projects\easel-fi-what-is-agent\work\huashu-eras.mp4
python scripts\qc_video.py projects\easel-fi-what-is-agent --video eras.mp4
python scripts\package_code_animation_sample.py projects\easel-fi-what-is-agent --variant eras
```

`build_code_animation_sample.py` treats the full eras render as the sole visual
shot while keeping the per-beat timeline for voice, captions, generated-media
limits and receipts. In eras mode it also writes
`receipts/eras/timing-reconciliation.json`, which proves
`voice + tails + silent bridge = film length` and that no caption falls inside
the bridge. The review bundle remains `PENDING_HUMAN_REVIEW`; no QC result
publishes or approves the film.

A beat can be re-rendered for this variant alone by writing
`work/eras/clips/<beat>.mp4`; the adapter prefers it over `work/clips/<beat>.mp4`.
That is how p02 uses the redrawn diagram without changing the baseline clip.
