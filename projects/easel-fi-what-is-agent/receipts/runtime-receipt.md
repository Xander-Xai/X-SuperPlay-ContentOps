# Runtime receipt — easel-fi-what-is-agent

- engine: huashu-art-motion (MIT), `scripts/engine/render.py`, upstream `8a0d7d7`
- interpreter: host Python; Playwright Chromium `D:\DevCaches\ms-playwright\chromium-1223`
- env: `PYTHONUTF8=1`; browser launch falls back bundled → Chrome → Edge
- render: `render.py --spec motion/specs/p0N.json --out work/clips/p0N.mp4`
- visual track: measured beat clips assembled by ContentOps
- compose: `python scripts/build_code_animation_sample.py easel-fi-what-is-agent`
- grade: `python scripts/qc_video.py easel-fi-what-is-agent --video easel.mp4`

Measured duration: `37.9 s`.
Verdict: technical QC is recorded separately; it never creates production approval.
`production_ready: false`, `PENDING_FOUNDER_REVIEW`.
