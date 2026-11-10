---
name: x-superplay-huashu-motion
description: "Route short explanatory animation through the locally installed Huashu Art Motion runtime while preserving account evidence, rights, review and M5 gates."
metadata:
  author: "X-SuperPlay ContentOps"
  upstream: "https://github.com/alchaincyf/huashu-art-motion"
  version: "0.1.0"
---

# X-SuperPlay Huashu motion adapter

Use `python scripts/huashu_motion_adapter.py <project> --preflight` to check the
project and account before rendering. Use `--render --spec <project-relative
spec> --placement-id <id> --asset-id <id>` only after the adapter reports
`READY` and the ContentOps execution grant authorizes this exact account,
pipeline, stage and `render` operation.

The adapter calls the shared `huashu-art-motion` Skill through
`scripts/huashu_render.py`; it does not copy or modify that Skill's engine.
Generated clips are visual support only. They are never source evidence and
cannot replace a claim's real source material.

Account rules:

- `x-superplay-1024`: animation is explanatory B-roll only. Owner-provided
  Recordly footage remains the evidence; Huashu frames do not count as visible
  source time.
- `x-superplay-future-intelligence`: no manual screen recording. Prefer Native
  Motion for already validated mechanism clips. Huashu can fill only a visual
  placement explicitly mapped by the reviewed script.

The render receipt is followed by AssetRegistry registration and an M4.5
`MediaManifest` entry. M5/Easel still run through their existing entry points.
Updating an asset hash changes the copy/asset map and leaves review pending;
the adapter never signs review or marks an output production-ready.
