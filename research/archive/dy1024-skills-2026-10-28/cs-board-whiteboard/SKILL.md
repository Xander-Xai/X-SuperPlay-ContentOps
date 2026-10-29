---
status: superseded
superseded_by: research/archive/dy1024-skills-2026-10-28/README.md
historical_context: copied contract from the retired dy_x1024 workspace; archived, not routed to
source: dy_x1024@a5952a44dbf47d44c1a4bf475e3653b542c25ac1
date: 2026-10-28
name: cs-board-whiteboard
description: 使用本地 cs-board 将人工编排的源图、annotation JSON 与字幕/音频渲染为连续白板动画；输出必须经过资产回执、比例检查和 Remotion 最终合成。
---

# CS Board 白板动画路由

> **Legacy V1 package route.** The bundled bridge default is V1. Use this route only for an explicitly declared historical V1 package. For V2, consume the package-declared `03_audio/audio-handoff.json` through a V2-aware route and keep execution under canonical `Visual Route` / `Media Generation` ownership.

这是 `skills/cs-board` 的工作流路由绑定。完整的字幕解析、语义标注、遮罩时序、预览台和渲染规范以同目录 `cs-board/SKILL.md` 为准。

本路由只接受已批准的源图、同名 annotation JSON 以及中央 `04_video/audio-handoff.json`；不自行生成脚本、不绕过 `assets_plan`/`assets` 门禁，也不替代真实 UI 或事实证据。CS Board 只绑定最终口播的场景时长和 ASR 字幕（`timing-and-caption-only`），不得读取音色参考、不得生成第二条音轨。渲染必须通过 `scripts/cs_board_whiteboard_bridge.py`，并记录源码版本、Python 环境、输入尺寸、输出媒体参数、音频 handoff SHA-256 和 SHA-256。桥接输出必须是无音轨视频；Remotion 负责最终 9:16 重构、字幕、唯一 narration 音轨和交付。
