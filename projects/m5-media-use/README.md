# m5-media-use

End-to-end sample for automatic offline media sourcing in the M5 chain. It is
the project behind the `INTEGRATION_VERIFIED` record in
`docs/CURRENT-STATE.md` and the capability map in
`docs/adr/ADR-008-media-use-adapter.md`.

## What it proves

`scripts/m5_production.py` runs the whole chain for this project with no manual
media-use CLI step:

```
sources → media_use → assets → claims → script → narration → subtitles
        → storyboard → Easel compose → QC → review
```

The media-use stage resolves the three declared needs, imports each file with a
`contentops.media-import/v1` receipt, verifies its SHA-256, then feeds the visual
to the asset gate and the BGM/SFX to the storyboard. The pinned Easel assembler
mixes both audio tracks under the narration.

## Inputs

| Input | Origin | Licence |
|---|---|---|
| `assets/support.png` | owner-captured screenshot, copied from `projects/easel-review/sources/screenshots/01-easel-hero.png` | `OWNED-BY-OPERATOR` |
| `assets/bed.mp3` | deterministic ffmpeg sine bed generated for this sample | `OWNED-GENERATED-LOCAL` |
| bundled SFX | resolved offline by media-use from `skills/media-use/audio` | `Pixabay-Content-License` |

The two binaries are gitignored (`*.png`, `*.mp3`). Regenerate the BGM bed with:

```bash
ffmpeg -y -f lavfi -i "sine=frequency=196:duration=8" -f lavfi -i "sine=frequency=294:duration=8" \
  -filter_complex "[0:a][1:a]amix=inputs=2:normalize=0,volume=0.06,afade=t=in:st=0:d=1,afade=t=out:st=7:d=1" \
  -c:a libmp3lame -b:a 96k projects/m5-media-use/assets/bed.mp3
```

Copy the screenshot from the tracked evidence path before the first run.

## Run

```powershell
$env:CONTENTOPS_MEDIA_USE_RUNTIME_LOCK = "<verified runtime lock for this host>"
python scripts\m5_production.py projects\m5-media-use
```

The host lock is not committed. Without one the run exits `4` (`BLOCKED`) with
`DEPENDENCY_UNVERIFIED`; local project imports keep working, external calls do
not.

## Output

`final/m5-media-use.mp4` (gitignored) plus the committed receipts and
storyboard. `production_ready` is always `false` and `human_review` is
`PENDING_FOUNDER_REVIEW`; an automated QC `WARN` is not an approval.
