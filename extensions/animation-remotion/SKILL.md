---
name: contentops-remotion-clips
description: >
  ContentOps clip renderer pointer for pinned Remotion 4.0.543 templates.
  Discovery only. It does not authorize execution, publication, or counting
  a generated clip as a screen recording.
version: 0.1.0
owner: contentops
language: zh-CN
upstream: remotion-dev/remotion@4.0.543
---

# contentops-remotion-clips

This directory holds ContentOps-owned compositions. Remotion source is not
vendored. Official agent skills install into an isolated directory recorded by
`runtime/remotion-skills.lock.json` and are not copied into the shared skill store.

Render through `scripts/animation_render.py`. Easel remains the episode compositor.
