# Engine Comparison — easel-review

**Rendered**: 2026-10-02
**Purpose**: hand two renders of the same topic to a human. This file does
**not** judge which looks better — that decision is yours.

Both files:
- `projects/easel-review/final/easel.mp4`
- `projects/easel-review/final/fallback.mp4`

`final/final.mp4` is deliberately **not** regenerated. It remains the old
smoke-test artifact; promoting a winner is a manual step.

## Side by side

| 项目 | fallback | easel |
|---|---|---|
| engine | legacy ffmpeg (no upstream) | Easel v0.2.1 (`assemble.py` + `tts-voiceover`) |
| duration | 40.0s | 54.0s |
| resolution | 1080x1920 | 1080x1920 |
| codec | H.264 + AAC | H.264 + AAC |
| size | 0.57 MB | 1.51 MB |
| script source | **hardcoded `DEFAULT_SCRIPT_LINES`** | `script/master.md` + `script/storyboard.json` |
| shots | 6 (built-in) | 6 (project-authored, real assets) |
| real assets used | 4 generated placeholder PNGs | 5 real captures (doctor/ping/version/layers/dir) |
| generated assets | 4 synthetic text cards | **0** |
| real_source_ratio | not measurable (not storyboard-driven) | **1.00** (6/6 real_screenshot) |
| voice | Windows SAPI (robotic) | edge-tts `zh-CN-YunxiNeural` (natural) |
| subtitles | SRT written, **never burned** | **burned into the video** |
| QC overall | `WARN` (subtitle check fails) | **`PASS`** (20/20) |
| manual steps | none | none |
| render time | ~1 min | ~4 min (TTS + upstream compose + subtitle burn) |

## What actually differs

**Evidence.** The fallback uses 4 PNGs that were themselves ffmpeg-generated
text cards standing in for screenshots — the video was illustrating itself.
The Easel render uses five frames captured from actual terminal output and file
listings on this machine.

**Narration.** The fallback speaks hardcoded lines that never changed with the
project. The Easel render speaks the project-authored narration, and the
captions come from the same TTS pass, so they are synchronised by construction.

**Subtitles.** The fallback writes an SRT and stops. The Easel render burns
subtitles in; QC verifies this by sampling frames in the subtitle band.

**Voice.** SAPI reads flat and mechanical. edge-tts is a real TTS voice.

## Known limitations of the Easel render

Recorded honestly; none of these are hidden by the QC PASS:

1. **Script had to be corrected by hand.** The Easel `video-script` skill
   produced three factual errors (claimed doctor was all-green, gave the wrong
   gateway port, quoted a stale skill count). See
   `script/master.md` → 「与 Skill 初稿的差异」. The Skill output is a draft, not
   a source of truth.
2. **Upstream subtitle bug.** `assemble.py` cannot burn subtitles on Windows
   (unescaped path separators). Worked around by orchestrating, not forking —
   see `scripts/assemble_easel.py` and `receipts/runtime-receipt.md`.
3. **Web workbench still unverified.** `easel doctor` reports 6 Web-path FAILs
   (fastapi / uvicorn / sse_starlette / multipart / web frontend build / .env).
   Only the CLI + Skill + assemble path was proven.
4. **Gateway healthz port hardcode.** Upstream probes
   `http://127.0.0.1:18789/healthz` unconditionally (`commands/ping.py:56`,
   `commands/doctor.py:120`); the easel profile gateway is configured for
   37289, so with the default gateway down the doctor gateway row and ping
   step 1 read FAIL while the actual agent round-trip (step 2, via 37289)
   passes. The video shows this rather than claiming "ping 全通".
   See `receipts/runtime-receipt.md` → 2026-10-03 re-run.
4. **52 vs 51.** The layer count in the video (produce=52) comes from counting
   frontmatter. Upstream's own `skill-function-mapping.md` still says 51, so
   that document is stale upstream, not wrong in the video.

## Founder manual steps

1. Watch both files.
2. Pick the winner.
3. If easel wins: `cp final/easel.mp4 final/final.mp4`.
   If fallback wins: `cp final/fallback.mp4 final/final.mp4`.
4. Publishing stays manual either way.

**STATUS: NEEDS_HUMAN_REVIEW — not auto-promoted.**
