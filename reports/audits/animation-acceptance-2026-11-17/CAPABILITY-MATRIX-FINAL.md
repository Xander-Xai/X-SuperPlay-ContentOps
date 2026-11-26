# 最终能力矩阵（任务口径状态词汇）

> Archive provenance: originally generated 2026-11-17 in the external output area; verified for local machine paths/secrets before archiving. Media evidence stays external and hash-bound; SHA values are not machine paths.


生成时间：2026-11-17（Asia/Shanghai）
基线 HEAD：`7b2068bce25837e68b5eef75e068834a884bf164`（PR #196，OPEN，CI 三项 PASS）
核验方式：本轮独立重跑全部测试、逐文件 SHA-256、逐媒体 ffprobe，结果见 `ENGINEERING-ACCEPTANCE.md` 与下方证据索引。

## 状态定义（严格区分，禁止混用）

| 状态 | 含义 |
|---|---|
| `IMPLEMENTED` | 代码已实现（有源码与接线）。不等于通过测试或真实渲染。 |
| `CONTRACT_PASS` | 合同/静态测试通过（类型、路由、账号权限、缓存、拒绝条件）。不等于真实视频。 |
| `RENDER_VERIFIED` | 真实视频经过 SHA-256 + ffprobe + 首中末帧/contact sheet + 来源回执核验。 |
| `BLOCKED` | 缺少环境、素材或授权；有明确 BLOCKED 码与证据。**FAIL 不降级为 PASS**。 |
| `PENDING_FOUNDER_REVIEW` | 等待人工验收；技术项可能已 VERIFIED，但不得声明生产可用。 |
| `NOT_RUN` | 真实媒体在本环境未执行（如 CI 缺 gitignored 外置 MP4）。 |

> 安装成功、锁文件存在、TypeScript 编译通过、CI 全绿、stub 测试通过都**不等于** `RENDER_VERIFIED`。所有行 `production_ready=false`、`publish_authorized=false`。

## 能力矩阵

| 能力名称 | 源码位置 | 运行时版本 | 账号适用范围 | 测试状态 | 真实 MP4 证据 | 技术 QC | 人工审核 | 阻断原因 | 待修复事项 | 最终状态 |
|---|---|---|---|---|---|---|---|---|---|---|
| Easel 总合成器（唯一） | `.runtime/easel`（pin `runtime/easel-pins.json`，commit `bb3c8ff`，tree `c26fc96a`） | v0.3.0 | 两账号；唯一总合成器 | 门禁/合同通过 | P2 TEST_ONLY 整片经其合成 | 合成回执 PASS | PENDING | 无（合成已验证） | 人审；横版分支另立 | `RENDER_VERIFIED` + `PENDING_FOUNDER_REVIEW` |
| Huashu architecture_flow | `motion_planner.py` + `huashu_motion_adapter.py`；spec `projects/e2e-huashu-six-templates/motion/auto/specs/arch01-*.json` | 1.2.0（frozen） | 未来智能（解释）/ 1024（矢量解释） | 后端 40/40，M5 58/58 | `huashu-arch01.mp4` `10cff6da…`；P2 fi02/fi08/fi11/fi13 | 1080×1920/30/h264/yuv420p/静音 | PENDING | 无 | 人审 | `RENDER_VERIFIED` + `PENDING_FOUNDER_REVIEW` |
| Huashu state_transition | 同上；`state01-*.json` | 1.2.0 | 两账号 | 同上 | `huashu-state01.mp4` `046da855…`；P2 fi04/fi10 | 同上 | PENDING | 无 | 人审 | `RENDER_VERIFIED` + `PENDING_FOUNDER_REVIEW` |
| Huashu code_focus | 同上；`code01-*.json` + P2 代码截图锚点 | 1.2.0 | 未来智能（代码局部聚焦）、1024 | 同上 | `huashu-code01.mp4` `02080661…`；P2 fi03/fi05/fi06/fi07/fi12（注册截图 + 关键行 highlight） | 同上 | PENDING | 无 | 人审 | `RENDER_VERIFIED` + `PENDING_FOUNDER_REVIEW` |
| Huashu evidence_zoom | 同上；`evid01-*.json` | 1.2.0 | 1024（真录屏放大）/ FI | 同上 | `huashu-evid01.mp4` `e29056f8…` | 同上 | PENDING | 1024 无真实录屏，正式片不生成 | 提供真实录屏 | `RENDER_VERIFIED`（TEST_ONLY）+ `BLOCKED`（1024 正式） |
| Huashu metric_transition | 同上；`metric01-*.json` | 1.2.0 | 两账号 | 同上 | `huashu-metric01.mp4` `f410a206…` | 同上 | PENDING | 无 | 人审 | `RENDER_VERIFIED` + `PENDING_FOUNDER_REVIEW` |
| Huashu comparison_reveal | 同上；`cmp01-*.json` | 1.2.0 | 两账号 | 同上 | `huashu-cmp01.mp4` `64c867b4…`；P2 fi01/fi09/fi14 | 同上 | PENDING | 无 | 人审 | `RENDER_VERIFIED` + `PENDING_FOUNDER_REVIEW` |
| Remotion title_card | `extensions/animation-remotion/src/TitleCard.tsx`；`animation_backend.py` DNA 版式 | 4.0.543 | 1024（3s 冲突钩子） | 后端 40/40（DNA 版式、拒证据字段、去 test banner） | 长钩子 `18556d08…`、刷新钩子 `62d2f2b2…`（gitignored `_local`） | 3s/1080×1920/30/h264/静音 | PENDING | 正式片缺录屏 | 人审 | `RENDER_VERIFIED`（TEST_ONLY）+ `BLOCKED`（1024 正式） |
| Remotion rag_flow | `src/RagFlow.tsx` | 4.0.543 | 未来智能 | 合同通过 | `clip-rag-fi.mp4` `c9582e23…`（`_local`） | 6s/1080×1920/30/静音 | PENDING | 无 | 人审 | `RENDER_VERIFIED`（TEST_ONLY） |
| Remotion annotation / comparison | `src/AnnotationCard.tsx` | 4.0.543 | 两账号 | 合同通过 | `clip-annotation.mp4` `4c31e531…`（`_local`） | 1080×1920/30/静音 | PENDING | 无 | 人审 | `RENDER_VERIFIED`（TEST_ONLY） |
| Remotion recording_mark | `src/RecordingMark.tsx` | 4.0.543 | 1024（录屏标注，仅 remotion 后端） | 合同通过（props 校验） | 路由已接线；无独立正式样片 | n/a | PENDING | 依赖真实录屏，未生产 | 提供录屏后测试 | `CONTRACT_PASS` + `BLOCKED`（1024 正式） |
| Remotion 3D technical_3d_explainer | `src/Technical3DExplainer.tsx` + `@remotion/three` | 4.0.543 + three 0.180.0 | 两账号（必要 3D 解释） | 合同通过 | `remotion-three-3d-explainer.mp4` `6a5bf56b…` | 4s/1080×1920/30/h264/静音 | PENDING | WebGL 字节非确定（同 fingerprint SHA 变） | 人审；确定性记录 | `RENDER_VERIFIED` + `PENDING_FOUNDER_REVIEW` |
| Manim math_formula_reveal | `scripts/manim_scenes.py` + `manim_render.py`；隔离 venv | 0.22.1 | 未来智能（数学/公式） | 18/18 | `manim-math01-formula-reveal.mp4` `6d657406…` | 4.533s/1080×1920/30/h264/静音 | PENDING | LaTeX 在 Windows 管理员权限卡死，已换 Pango Text | 人审 | `RENDER_VERIFIED` + `PENDING_FOUNDER_REVIEW` |
| Manim attention_matrix_flow | 同上 | 0.22.1 | 未来智能（Attention/矩阵） | 18/18 | `manim-attention-matrix-flow.mp4` `5552c03f…` | 5s/1080×1920/30/静音 | PENDING | 无 | 人审 | `RENDER_VERIFIED` + `PENDING_FOUNDER_REVIEW` |
| Motion Canvas mc-arch01（系统图） | `extensions/motion-canvas/src/scenes/animated_system_graph.tsx` + `scripts/motion_canvas_adapter.py` | 3.17.2（MIT） | 未来智能（复杂系统图） | 16/16（本地 `REAL_MEDIA_VERIFIED`，CI `REAL_MEDIA_NOT_RUN`） | `motion-canvas-mc-arch01-editor-export.mp4` `8741f5c5…` | 7.233s/1080×1920/30/h264/静音 | PENDING | 无（真实编辑器导出成功） | 人审 | `RENDER_VERIFIED` + `PENDING_FOUNDER_REVIEW` |
| Motion Canvas mc-state01（Agent 状态机） | `src/scenes/agent_state_machine.tsx` + 适配器 | 3.17.2 | 未来智能（Agent 状态机） | 16/16（合同） | 无（未导出） | n/a | PENDING | `EDITOR_EXPORT_REQUIRED`：官方无 headless CLI，帧经编辑器 websocket | 在编辑器打开 prepared spec → Video Settings FFmpeg → Render → `--import-editor-export --asset-id mc-state01` | `BLOCKED` |
| 1024 正式视频线 | `production_gate` + `recording_intake.py` | n/a | 1024 | 门禁测试通过 | 无（正式片） | n/a | PENDING | `MISSING_REAL_RECORDING`，70% 真实录屏缺失 | 按 `RECORDING-CAPTURE-PLAN-1024.md` 采集 + intake | `BLOCKED` |
| B站原生 1920×1080 | `adaptation.py` + `video_deliver.py`（仅 blur-pad 载体） | n/a | 未来智能 | 阻断测试通过 | 无（原生横版） | n/a | PENDING | `NATIVE_16_9_RENDER_UNAVAILABLE`，渲染/QC 只认 1080×1920 | 按 `PRD-NATIVE-16-9-DESIGN.md` 独立 Issue/PR | `BLOCKED` |
| 18 个上游候选取舍 | `docs/PRD-ANIMATION-SKILLS-INTEGRATION.md` §3 | 各候选锁定版本 | n/a | 18/18 调研 PASS（PRD §17） | n/a | n/a | n/a | 15 个 REJECT（无新增依赖）；采纳 Remotion/Motion Canvas/Three.js + 既有 Huashu/Manim | 无 | `CONTRACT_PASS`（调研完成） |

## 证据索引（本轮独立复核）

- 测试：`test_animation_backend.py` 40/40；`test_animation_cache_integrity.py` 21/21；`test_manim_integration.py` 18/18；`test_p3_motion_canvas.py` 16/16（`REAL_MEDIA_VERIFIED`）；`test_m5_motion_integration.py` 58/58；`scripts/dev_check.py` 全绿。M5 与 dev_check 在去掉 WorkBuddy safe-delete shim 后运行（该 shim 使 `TemporaryDirectory` 清理失败，是环境伪影，非测试失败；CI 直接运行同套件全绿）。
- 媒体：11 个 MP4 逐一 `sha256sum` 与报告一致；`ffprobe` 全部 h264/1080×1920/yuv420p/30fps，短镜头无音轨，P2 整片 99.744s/2991 帧含 AAC。
- 视觉门：`visual-gate.json` / `visual-qc.json` / `qc-report` 均绑定当前视频 SHA `66ca2673…`；黄灯 `fast_ratio=0.0497` 稳定，`verdict=pass`，0 个代码可修缺陷（见 `p2-warn-analysis.json`）。
- 远端：PR #196 OPEN / MERGEABLE / 三项 CI SUCCESS，head = 本地 HEAD；main HEAD `10017c2b` 一致；工作树干净。

## 明确声明

- 没有任何一行达到「正式生产可用」；全部 `production_ready=false` / `publish_authorized=false`。
- `IMPLEMENTED` 不冒充 `CONTRACT_PASS`，`CONTRACT_PASS` 不冒充 `RENDER_VERIFIED`，CI 全绿不冒充真实媒体通过。
- `RENDER_VERIFIED` 项均为 TEST_ONLY 诊断样本，不构成本账号正式成片；1024 与 B站横版的正式路径仍 BLOCKED，且有独立证据与修复条件。
