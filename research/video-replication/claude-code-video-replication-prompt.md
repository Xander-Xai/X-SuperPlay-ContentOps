---
status: experiment
canonical: false
issue: "#34"
date: 2026-10-27
---

# X-SuperPlay ContentOps · 视频制作能力复刻主提示词（Claude Code）

> 本文件是给 Claude Code 的完整任务提示词（综合 2026-10-27 竞品对标全程成果，对齐本仓库 CLAUDE.md / AGENTS.md / docs/* 治理）。
> 使用方法见文末「如何使用」。

## 0. 任务一句话

把对标博主（A组 X超玩·1024：小天fotos > Simon林 > 浙大猫学长；B组 X超玩·未来智能：Ai林爻 > 陈与小金 > 李白｜AI创造力实验室）视频的**制作能力**，以「扩展既有 ContentOps 运行时」的方式落地为可运行、可验收、可复现的视频工作流，并按 `docs/superpowers/specs/2026-10-27-evidence-led-video-v2-design.md`（创始人今日批准的 V2 设计基线）产出 P0 证据型样片。

**三条硬约束**：禁止另起第二套生产系统；禁止修改 Easel 上游（`.runtime/easel/`、`Easel/`）；禁止自动发布。

## 1. 开工前必读（仓库启动协议，按序执行）

1. `git status` / `git branch --show-current` / `git fetch --all --prune`
2. 依次读：`AGENTS.md`、`docs/INDEX.md`、`docs/CURRENT-STATE.md`、`docs/DEVELOPMENT-STANDARD.md`、`docs/FILE-PLACEMENT-POLICY.md`
3. 再读：`docs/ARCHITECTURE.md`、`docs/PRD.md`、`docs/RUNBOOK.md`、`docs/QUALITY-STANDARD.md`、`docs/superpowers/specs/2026-10-27-evidence-led-video-v2-design.md`
4. 读两个账号 DNA 与一键提示词：`config/accounts/x-superplay-1024.json`、`config/accounts/x-superplay-future-intelligence.json`、`config/accounts/prompts/x-superplay-1024.prompt.md`、`config/accounts/prompts/x-superplay-future-intelligence.prompt.md`
5. 读既有相关研究：`research/x-media-workflow-skills-2026-10-27.md`（X 平台媒体工作流 skill 扫描，71 posts / 9 repos）
6. **先输出「现状理解」再动手**：管线哪些环节已存在、哪些缺失、哪些是缺口；以仓库当前代码与 CURRENT-STATE 为准（事实优先级：REAL EXECUTION RECEIPT > CURRENT CODE > CONFIG > ADR > CURRENT-STATE > RUNBOOK > RESEARCH > OLD PLAN）。

## 2. 竞品对标输入文档（绝对路径，同一台机器可直接读）

- `D:\Projects\Model\douyin-downloader\X-SuperPlay_TOP3对标博主视频拆解_2026-10-27.md` — 18 条视频内容结构拆解（受众/钩子/叙事/可借鉴/规避）
- `D:\Projects\Model\douyin-downloader\X-SuperPlay_制作手法拆解与ClaudeCode实现蓝图_2026-10-27.md` — 【主规格】制作手法拆解 + M1-M9 模块蓝图 + 红线模块级设计
- `D:\Projects\Model\douyin-downloader\X-SuperPlay_18条对标视频制作证据分级表_2026-10-27.md` — 证据分级（画面事实 / 工具链推断 / 待验证）

读完后做**能力对账**：把 M1-M9 蓝图逐模块对照本仓库现有管线（Source → Script → Storyboard → Voice → Compose → QC → Human Review → final.mp4），输出四类清单：

```
已覆盖 / 需扩展 / 需新增 / 明确不建（含理由）
```

对账依据必须是当前代码、DNA、V2 规格中的实际内容，不得凭蓝图文档推测仓库能力。

## 3. 不可违反的红线（仓库 DNA 是唯一真源，此处为执行摘要）

| 领域 | 红线 |
|---|---|
| A组 X超玩·1024 | 录屏允许但必须裁切干净（`manual_recording=ALLOWED_CROPPED`，只保留日志/报错/运行结果/模型输出区，命令与结果同一次录制）；画面配比 65% 录屏证据 + 30% 矢量动画 + 5% 对比卡片；翻车与成本必须讲 |
| B组 X超玩·未来智能 | 零手动录屏、零鼠标操作画面、零整屏 IDE、指标必须来自真实运行（`manual_recording=FORBIDDEN`）；画面配比 70% 矢量链路动画 + 25% 代码截图（只高亮关键行）+ 5% 指标图表；架构图必须可复现且与 X-SuperPlay 系列仓库工程设计对齐 |
| 证据阶梯 | view < like_or_collect < comment_or_question < dm_or_consult < paid；低阶不证明高阶；只有真实 URL + 指标快照才能上移；无真实 URL 不得声明发布成功 |
| 商业归属 | `business.source_of_truth` = Xander-Xai/X-SuperPlay-OPC-Blueprint，`stage` = Stage 0；内容可引流，不得移动 OPC 阶段 |
| 证据类目 | EXECUTED / HISTORICAL / DOCUMENTED；Claim Map：SUPPORTED 才能作断言事实，PARTIAL 必须陈述限制，BLOCKED 不得进入口播/字幕/封面/CTA |
| 生成画面 | 矢量图/动画/生成视频只是解释工具，不得冒充实测、客户案例、运行日志；MiniMax 实验必须遵守 V2 规格（单条生成片段、时长 <10%、claim-free 区间、receipt、无改善即删除） |
| 配音 | 28-35 岁中低音、略带沙哑磁性、冷静理性（A组不带情绪煽动 / B组偏严谨工程师口吻）；`speech_rate_cpm=220`；220-260 字/分钟断句；只做口语化断句，禁止扩展/润色/改写原文 |
| 治理 | 不修改 `.runtime/easel/`；不建第二套系统；不自动发布；人工审核必经；不在 main 直接提交；不创建政策外文件；无许可证不引入外部资产；不提交 `.env`/`docs/ai-provider-selection.md`/`.verify-tmp/` |

## 4. 落地范围与实现顺序

**扩展策略（强制优先级）**：`ADAPTER > EXTENSION > CUSTOM SKILL > UPSTREAM PATCH > FORK`。优先在 X-SuperPlay 自有空间（`scripts/`、`src/contentops/`、自有 skill 扩展、`config/`）内扩展。

**P0（本次必须完成）**

1. 能力对账清单落盘：`research/video-replication/capability-reconciliation-2026-10-27.md`（四类清单 + 每条依据 + 外部资产采用记录：许可证/版本/适配点/为什么）。
2. 按 V2 设计规格跑通一条 **1024 证据冲突版**（1080×1920，42–50s）全链路：真实捕获源 → 脚本（`video-script` skill）→ 分镜 → 配音 → 字幕（`auto-subtitle`）→ 合成（`auto-short-video` / `assemble_easel.py`，不手搓 ffmpeg）→ QC（`qc_video.py`）→ 人工审核材料；receipts 齐全。
3. 素材源：优先复用 `projects/easel-evidence-capture/` 既有捕获；不具备时按 V2 的 Capture Proof 契约采集一次最小证据源（read-only、白名单命令、redaction 变换、许可范围标注）。

**P1（有余量再做，否则明确列为下一步）**

- B组 engineering cut（1920×1080，78–90s）同源派生
- 配音语速实测闭环（ffprobe 实测 + 必要时 atempo 校正，目标 220–260 字/分，输出实测数值）
- 封面（`card-design`；1024 配 1080×1440 小红书封面）

**明确不建（除非另有指令）**：n8n 编排、发布自动化、独立选题库系统、第二套渲染引擎。

## 5. 可参考的 GitHub 工作流资产（先读许可证与 README，记录后再采用，不整体照搬）

| 资产 | 用途 | 注意 |
|---|---|---|
| harry0703/MoneyPrinterTurbo | 一键短视频流水线参考（文案→素材→配音→字幕→合成） | 参考模块划分与字幕/合成实现思路；检查许可证与依赖；其素材为免费图库视频，与本项目证据型画面不同，不得照搬素材逻辑 |
| anthropics/skills | Claude Code 官方 Skills 规范与模板 | 可参照把本工作流关键步骤封装为仓库自有 Skill（配合 `scripts/skill_route.py`）；注意仓库 skill 放置规范 |
| n8n-io/workflows + n8n.io 官方模板 | 可选自动化参考（CSV→成片、Shotstack 信息图视频等） | 本阶段不引入；仅在能力对账发现明确缺口且符合 ADAPTER 策略时才评估 |
| remotion-dev/remotion、ManimCommunity/manim | 程序化视频/讲解动画（对标证据中出现 Manim/edge-tts 链路） | 仅当现有 `infographic` / `slideshow-video` skill 覆盖不了时才评估，且必须走 ADAPTER/EXTENSION |

任何外部资产采用前：记录许可证、版本、适配点、为什么采用（写入对账清单或 ADR 候选）。

## 6. 验收标准（全部满足才算完成）

1. 能力对账清单存在，四类分明，每条有代码/文档依据。
2. P0 样片按 V2 规格产出：ffprobe 校验时长/分辨率/音轨；`qc_video.py` 通过；receipts（build / qc / runtime / human-review 材料）齐全。
3. 每条口播/字幕/封面断言在 Claim Map 中可定位支持状态；无 BLOCKED 断言进入成品。
4. B组红线在产物中可验证：无手动录屏 / 鼠标 / 整屏 IDE / 伪造指标。
5. 未修改 `.runtime/easel/`、未建第二套系统、未自动发布、未在 main 直接提交。
6. 文档按 `docs/FILE-PLACEMENT-POLICY.md` 落位；涉及 Tier-1 文档时按 i18n 政策同步 EN/zh-CN。
7. 无编造数据/链接；外部引用有出处。
8. 完成报告包含：改动文件清单、对账表、验证实测数据、已知缺口、下一步建议。

## 7. 工作纪律

- 每次交付前先做 skill 路由：`python scripts/skill_route.py --match "<产物>"`，读命中 SKILL.md，声明所选 skill、输入输出契约与原因；不手搓 ffmpeg 滤镜链 / 字幕烧录 / 卡片 HTML 替代 skill 属主步骤。
- 特性分支工作（如 `feat/34-...` 或新建 `feat/<issue>-video-replication`）；提交前 `python scripts/dev_check.py` + 相关测试；commit 带 `Refs #N` / `Closes #N`。
- 收据文化：每次运行产 receipts；FAIL 就是 FAIL，不静默降级；降级必须 `production_ready: false` + 原因，人工审核标记不自动通过。
- 卡住时如实报告缺口与补装步骤；工具不可用就换备选或标注 `MANUAL_ONLY`，不虚构成功。
- 先读后写；不确定文件放哪先查 `docs/FILE-PLACEMENT-POLICY.md`；一个事实只有一个属主，链接优于复制。

## 8. 如何使用本提示词

1. 终端进入仓库：`cd D:\Projects\X-SuperPlay-ContentOps`
2. **分支注意**：当前工作区在 `feat/34-narration-v3-creator-director` 且存在未提交改动（config/docs/scripts 多处）——先与创始人确认 WIP 归属，再新建独立特性分支（如 `feat/<issue>-video-replication`），不要污染既有分支。
3. 启动 `claude`，把本文件全文作为第一条消息粘贴；或：
   ```powershell
   claude -p "$(Get-Content -Raw 'research\video-replication\claude-code-video-replication-prompt.md')"
   ```
4. Claude Code 会先执行启动协议并报告「现状理解」，再开始能力对账与 P0 实现。

## 附：本轮对话成果脉络（供追溯，均已在 2026-10-27 完成）

1. **竞品对标筛选**：6 位博主 × 3 条视频 = 18 条，含抖音链接/赞评数据/受众/钩子/叙事拆解/可借鉴与规避点（数据缺口如实标注：收藏转发全量未检索到，藏赞比未量化）。
2. **制作手法拆解 + 证据分级**：三制作谱系（真实可运行录屏 / 低成本静态起步 / 讲解图+口播）；12 种手法 T1-T12；口播级工具链证据 3/18，其余为推断；字幕/BGM/精确时长/配音方式等待验证项列入附录。
3. **Claude Code 实现蓝图**：One Source 双资产（9:16 抖音 + 16:9 B站派生）、M1-M9 模块规格、红线模块级内嵌（四道闸）、P0-P2 实现顺序。
4. **本仓库现状**：两账号 DNA 已内嵌对标优先级与多数红线（证据阶梯、Stage 0、配音参数、画面配比、skill 路由）；V2 设计规格为 P0 样片基线。**结论：复刻 = 把蓝图缺口补进既有运行时，而非从零搭建。**
