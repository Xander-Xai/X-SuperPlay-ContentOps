---
name: contentops-native-motion
description: Produce original, deterministic, local-only explanatory motion clips for the two X-SuperPlay video accounts. No external assets, no GSAP, no arbitrary commands, no publication.
license: LicenseRef-Owner-Directed-Internal-Only
---

# ContentOps Native Motion

This repository-owned skill produces **original explanatory support clips** with the fixed local Pillow + FFmpeg toolchain. It is a clip producer, never a compositor. Easel remains the only final compositor.

## Account routing

- `x-superplay-future-intelligence-motion-20261107`: 8-second mechanism animation. The three continuous visual beats show (1) tool found but authorization not granted, (2) Request → Grant → Gate → Runner, and (3) BLOCKED versus explicitly theoretical AUTHORIZED / EXECUTED states. Nothing depicts a successful operation for this project.
- `x-superplay-1024-motion-20261107`: 6-second auxiliary diagram of local pin/HEAD → offline resolver boundary → upstream byte comparison marked not run. It is not real product capture, does not state a resolver result, and does not count toward the real-source duration gate.

The clip uses the account slug in `project.yaml`; the CLI allowlists these exact project ids and refuses a mismatched account. Every output is `generated=true`, `evidence_capable=false`, `production_ready=false`, and `publish_authorized=false`.

## Runtime and rights

- Renderer: `scripts/native_motion_preview.py` version 0.1.0.
- Required existing local tools: Python 3.13.15, Pillow 12.3.0 (MIT-CMU), FFmpeg 8.1.1 (this host's binary reports GPL-3.0-or-later). The binary is not redistributed. The command refuses a version mismatch; it does not install or update tools.
- Source uses original Pillow-drawn shapes and system text only. No GSAP, Huashu runtime, network request, third-party image, video, music, or paid API is used.
- Use only for the two P6 internal previews. This is not a repo-wide software license, public reuse clearance, production approval, execution Grant, or publishing authorization.

## Fixed commands

```powershell
python scripts/native_motion_preview.py route --project x-superplay-future-intelligence-motion-20261107
python scripts/native_motion_preview.py render --project x-superplay-future-intelligence-motion-20261107
python scripts/native_motion_preview.py route --project x-superplay-1024-motion-20261107
python scripts/native_motion_preview.py render --project x-superplay-1024-motion-20261107
```

The script refuses output overwrites and writes a per-project route record and digest-bound render receipt. The existing 4–8 second motion-sample gate verifies the silent H.264/yuv420p output at 1080×1920, constant 30 fps. That technical pass is not a rights decision, a human review, an M4.5 registration, an M5 composition, or an Easel render.

## Limits

- Generated diagrams are never documentary evidence, operation logs, screenshots, or current command output.
- Huashu Motion's separate route remains `LICENSE_REVIEW_REQUIRED` for GSAP 3.14.2 offline video rendering; this native skill does not inherit that dependency or that block.
- The native clip is not automatically inserted into a production manifest. The M4.5 Huashu registration API currently accepts only its Huashu asset record schema; a native route requires an explicit compatible handoff before M5/Easel can consume it.
- Owner-provided 1024 Recordly capture remains mandatory for real-source scenes and the ≥35-second measured source gate.
