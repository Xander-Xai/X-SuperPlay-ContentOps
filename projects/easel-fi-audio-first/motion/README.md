# Motion b-roll (Build account)

Six HyperFrames compositions, one per beat plus a result card. Each renders a
5 s, 1080×1920, 30 fps clip that `build_evidence_cut` uses as a `kind: motion`
asset. They are **support visuals**: they explain the architecture and the
measurement, and they are not evidence for any claim.

| Project | What moves |
|---|---|
| `narration-bar` | a 44 s narration bar draws, 22 view cells pop in, count to 22 |
| `view-swap` | V1 → V2 → V3 activate inside one placement by meaning |
| `arch-flow` | placement, views and gate assemble; a packet travels the chain |
| `code-sweep` | code lines reveal, a highlight sweep lands on the measured check |
| `metric-count` | 0 → 1.80 s counts up against a 2.20 s limit; QC PASS stamps |
| `result-chain` | 8 → 22 → 1.80 s → PASS, re-countable |

Shared treatment: 5 % grain, a 1.0 → 1.035 camera push, focus dimming, and only
transform/opacity animation.

## Render

```powershell
cd projects\easel-fi-audio-first\motion\arch-flow
npx --yes hyperframes@0.8.208 check
npx --yes hyperframes@0.8.208 render . -o ../../work/motion/arch-flow.mp4 -q delivery
```

Repeat per project. `work/motion/` is gitignored; the HTML is the source, the mp4
is reproducible.

After re-rendering, refresh the asset hashes and rebuild the cut (the builder
refuses an asset whose SHA changed):

```powershell
python scripts\build_evidence_package.py projects\easel-fi-audio-first
```

`assets.json` records each clip's SHA-256; the build receipt records it again, so
a changed motion clip cannot pass as the reviewed one.

## Why not the registry blocks

`flowchart-vertical` (1440×2560, white) and `code-snippet-dark-2026`
(1920×1080, editor) were installed and inspected. Both need a full coordinate
re-layout for this 1080×1920 dark brand frame, so they were used as composition
references only.
