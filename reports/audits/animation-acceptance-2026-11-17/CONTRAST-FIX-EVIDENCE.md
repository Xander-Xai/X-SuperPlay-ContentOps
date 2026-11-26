# 视觉可读性修复：修改前后对比证据

> Archive provenance: 2026-11-17 visual-acceptance work. External media and worktree artifacts are not accessible in the current environment; recorded hashes and measurements below are historical evidence and have not been independently re-verified in this turn. No machine-specific path or credential is retained.


生成时间：2026-11-17（Asia/Shanghai）
对象：`projects/e2e-p2-fi-video` 99.744s TEST_ONLY 影片
变更类型：Huashu 模板参数（`y3_whiteboard` 的 `theme.ink`），**非**上游引擎修改、**非**无意义镜头运动、未改 QC 阈值

## 1. 根因

真实渲染运行时 `<installed-runtime>/huashu-art-motion/scripts/engine/clips/y3_whiteboard.js`：
- 第 163–164 行：`p = ctx.pal`；`INK = p.ink`，`BOARD = p.bg`；
- `B.text(...)` / 笔画用 `col: INK`；
- 未来智能权威 `brand.palette`：`ink=#202B31`（深），`base/bg=#0F1117`（深）。

WCAG 相对亮度：ink/bg 对比约 **1.30:1**，解释性节点、状态、输入清单标签在深底上几乎不可读。这不是检测指标问题，而是信息表达失败。

## 2. 修复（可复现）

历史独立渲染 worktree 中的项目参数补丁增加 `readable_draw_ink()`：
- 仅 `grammar=y3_whiteboard` + 深色 board（`bg` 相对亮度 < 0.25）+ ink/bg 对比 < 3.0 + 同调色板存在更亮 `surface` 令牌时，置 `theme.ink = theme.surface`（`#F9FBFA`，来自账号 DNA 自己的浅色令牌）；
- `accent`、`bg` 不变；`t2_keynote_ui` 代码卡（深字压浅卡）不动；不改 Easel、不改 Huashu 运行时、不新增依赖、不加镜头运动；
- 新 spec 用内容寻址文件名写入，`motion/shot-plan.json` 重新指向 → 缓存指纹变化 → 强制真实重渲；
- 决策写入 `receipts/motion-plan-preparation.json.readability_fix`（8 个镜头，从 `#202B31` → `#F9FBFA`）。

原始 patch 字节当前不可访问；本节保存其行为摘要，避免把历史项目脚本误认为已进入共享生成路径。

## 3. 修改前后：每帧对比度（同镜头中点帧，右侧标签区 x=600..1000,y=150..850）

| 镜头 | 内容 | before 亮像素(>60 / >120) | before p99 | after 亮像素(>60 / >120) | after p99 |
|---|---|---|---|---|---|
| 08 | 六模板→三语法 | 1,021 / 903 | 43.3 | 29,198 / 26,349 | 254.3 |
| 11 | 指纹五类输入 | 1,008 / 906 | 42.0 | 20,761 / 18,938 | 252.3 |
| 04 | 状态迁移 | 1,005 / 907 | 42.0 | 23,666 / 21,422 | 252.7 |
| 10 | 缓存身份 | 494 / 449 | 41.7 | 22,100 / 20,011 | 252.7 |
| 13 | 三步复现 | 735 / 677 | 42.0 | 24,721 / 22,535 | 252.7 |

亮像素数量提升约 20–45 倍；p99 亮度从约 42（近底色）升至约 253（浅字）。原始 before/after 帧及 contact sheet 在本环境不可访问；本报告仅保留当时记录的量化对比，不将这些文件路径作为当前可复现引用。

## 4. 真实重渲与技术核验

历史渲染在原 `experiment/p2-fi-video` worktree 中完成；该 worktree 的完整路径及媒体文件当前不可访问。以下命令记录用于说明当时过程，不应直接在现有 P2 项目上重跑：

```bash
python scripts/m5_production.py projects/e2e-p2-fi-video \
  --narration-provider existing \
  --narration-audio projects/e2e-p2-fi-video/assets/voice/narration.wav \
  --narration-receipt projects/e2e-p2-fi-video/receipts/narration.json \
  --rerender-shot fi01 --rerender-shot fi04 --rerender-shot fi08 --rerender-shot fi09 \
  --rerender-shot fi10 --rerender-shot fi11 --rerender-shot fi13 --rerender-shot fi14 --json
```

复用旁白（SHA/text_sha 与原片完全一致，未调用付费服务）；8 个 draw 镜头强制重渲，其余镜头走已验证缓存；Easel v0.3.0 重新合成整片。

| 项 | 修改前 | 修改后 |
|---|---|---|
| 影片 SHA-256 | `66ca2673dd915fad41bb6acde1396e5017be17b09bbde389538abc4f4cd24905` | `3aafc7290e16f8f28b08f858dab9a6df5757518ae53abd924684f434ed1f3511` |
| ffprobe | h264/1080×1920/yuv420p/30fps/2991f/99.744s/AAC 48k stereo | 同左（完全一致） |
| visual-qc status | PASS | PASS（绑定新 SHA） |
| qc-report overall | WARN | WARN |
| visual-gate state/light | WARN/yellow, exit 0 | WARN/yellow, exit 0 |
| fast_ratio | 0.0497 | **0.0505** |
| still_ratio | 0.604 | **0.573** |
| max_event_gap_s | 28.33 | 28.33（未通过加运动掩盖） |
| blue_purple_share | 0.0 | 0.0 |
| videosha 绑定 | 绑定 66ca2673 | 绑定 3aafc729 |

`fast_ratio` / `still_ratio` 的小幅改善是"标签从不可见变可见"的副作用，**不是**通过增加推镜/闪动实现；未调整任何阈值。

## 5. 回归测试

主仓库工作树（未合并本次修复，见下）执行，全部通过：
- `test_animation_backend.py` 40/40；`test_animation_cache_integrity.py` 21/21；`test_manim_integration.py` 18/18；`test_p3_motion_canvas.py` 16/16（`REAL_MEDIA_VERIFIED`）；`test_m5_motion_integration.py` 58/58；`scripts/dev_check.py` ALL CHECKS PASSED。

## 6. 状态与范围说明

- 修复在独立 worktree 的 `experiment/p2-fi-video` 分支完成并重渲验证；**没有**改动 PR #196 的 HEAD（`7b2068bc`），**没有**合并或推送 main。
- 新片、回执、关键帧、contact sheet 均保存在外置 `deliverables/visual-improvement/`（媒体不进 Git）；修复补丁与说明作为可追溯文本保存。
- 是否把该修复并入 PR #196 需创始人决定：并入会改变影片 SHA 与一批 hash-bound 回执，需要重新跑 CI；本轮仅交付证据与可复现补丁，不擅自扩大 PR 范围。
