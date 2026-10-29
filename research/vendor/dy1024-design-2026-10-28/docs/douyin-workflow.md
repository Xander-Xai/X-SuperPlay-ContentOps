---
status: archived
canonical: false
issue: "#34"
date: 2026-10-28
source: dy_x1024@a5952a44dbf47d44c1a4bf475e3653b542c25ac1
---

# 抖音视频唯一生产工作流

<!-- CURRENT_WORKFLOW_CONTRACT
contract=canonical-copy-to-video-v2
stage_count=13
stages=brief,research,script,review,audio,visual_plan,visual_route,assets_plan,assets,media_generation,edit_render,quality,delivery
artifacts=00_brief/brief.json,01_research/claims.json,02_script/script.json,02_script/review.json,03_audio/audio-handoff.json,04_visual/visual-plan.json,04_visual/visual-route.json,04_visual/director-material-plan.json,05_assets/asset-ledger.json,05_assets/media-generation-receipt.json,06_edit/master-timeline.json,07_quality/quality-report.json,08_delivery/delivery-manifest.json
statuses=approved,blocked,pending,ready_for_review,running
-->

新生产包的当前合同是 `canonical-copy-to-video-v2`，由 `scripts/canonical_workflow.py` 定义 13 阶段、阶段顺序、状态和 hand-off 路径。Schema、producer、tests 和 strict config audit 对该合同提供机器校验。`canonical-copy-to-video-v1` 仅为显式标记的历史包提供读取与审计兼容；新包默认创建 V2，既有包不静默升级。

进入生产阶段前，必须先完成任务驱动前置层，再完成 route、人工操作可行性预判、Audience Lens v3 严格校验并 `apply`，以及平台政策预检；之后严格按 V2 阶段顺序执行：

任务驱动前置层不是选题器。它只记录真实任务、主要受众进展、任务单元、能力假设、GitHub 候选、应用回执和验收缺口。内容期数由未闭合任务单元推导，用户确认前不锁定标题、Hook 或期数。完整契约见 [`task-driven-workflow.md`](task-driven-workflow.md)。

```text
Task Intake → Task Graph → Capability Evaluation → Application → Acceptance / OPC Review
→
Brief → Research → Script → Review → Audio → Visual Plan → Visual Route → Assets Plan → Assets → Media Generation → Edit & Render → Quality → Delivery
```

阶段状态：`pending`（未开始）、`running`（执行中）、`ready_for_review`（检查通过，等待人工审阅）、`approved`（人工批准）、`blocked`（当前门禁失败）。每次执行都先 `check`，由人阅读输出后再 `approve`。校验失败写入具体错误并停在当前阶段；修复后重跑同一阶段，不能切 provider 或跳过门禁。新包由 `scripts/content_package.py init` 默认以 V2 合同创建；读取既有包必须遵守其声明合同。

## 关键门禁

0. 任务工作项必须先回答“要把哪一个真实任务从什么状态推进到什么状态”；没有真实任务时只能留在 backlog/research，不能用视频选题代替任务。
1. GitHub 项目必须绑定到任务单元并经过许可证、环境、最小复现、迁移适配和失败边界记录；Star/热度不能作为能力或需求证明。
2. 任务只有在真实应用和验收后才进入 OPC Fit Review；能力成立不等于收入、Offer、Stage 或 Productized。
3. 内容只记录已闭合的状态变化或明确的未完成边界；简单任务可不做内容，多步骤任务按任务单元形成 0..n 期。

4. Building in Public 采用选择性公开：所有文案、字幕、画面、代码、截图、日志和外链都要经过脱敏与 Founder 审核；没有 `approved_public_safe` 不得发布，P0/P1 或可反推 OPC 核心商业秘密的内容不得公开。

### V2 阶段职责

5. Brief — 记录主受众、承诺、CTA、时长档位和初步证据计划。
6. Research — 为每个核心 claim 记录 input、changed_variable、operation、visual_checkpoint、metric_or_result、boundary 和 evidence_kind；生成素材不能作为事实证据。
7. Script — 每个 beat 绑定受众任务、实用/情绪价值、claim IDs、画面意图和预计时长。
8. Review — 复核事实、合规、承诺、证据计划和自然口播；通过后锁定脚本哈希。
9. Audio — 只接受授权 IndexTTS2.5 音色克隆，并交接 WAV、FunASR、SRT、音频哈希和脚本哈希。
10. Visual Plan — 逐 beat 定义视觉意图、唯一 `primary_visual` 和证据需要；录屏由 claim 证据需求决定，不设置全局比例，也不提前执行 provider。
11. Visual Route — 根据 Visual Plan 为每个 beat/scene 选择并审阅明确的视觉实现路线，形成 route handoff；本阶段只决定 route，不执行生成。
12. Assets Plan — 根据 approved Visual Route 规划素材请求、B-roll、image prompt 和 generation/provider jobs；本阶段仅规划，不把计划写成已生成结果。
13. Assets — 获取或接收真实素材，检查技术质量，登记来源、权利、回执和哈希，更新 asset ledger，并准备人工操作 receipt 与 OpenChatCut/editor intake；不把 provider generation 记作本阶段完成。
14. Media Generation — 严格 V2 合同要求完成 Bridge image、Gemini B-roll、gflow i2v、MiniMax H3、OpenChatCut editor 与 Remotion renderer 六条路线。Editor intake 和 renderer receipt 必须先完成；`strict_media_orchestrator.py finalize-generation` 校验全部六条路线后才写入聚合 receipt。逐项核验真实 receipts、artifact hashes、lineage 与必需路线完成状态；`gflow-cli i2v` 的实际执行属于本阶段。
15. Edit & Render — OpenChatCut 负责时间线，Remotion 负责最终合成；HyperFrames 的 scene source/overlay/composition 职责按 motion contract（`hyperframes-full-frame`、`remotion-full-frame` 或 `interop-overlay`）逐场景声明，HyperFrames 不是 strict final compositor；数字人必须实际出镜，旁白是唯一节目主音轨。
16. Quality — 检查数字人、统一克隆旁白、字幕同步、移动端可读性、媒体 QC、直接证据覆盖率 1.0 和图片到视频血缘；不读取预先生成的 Delivery 清单。
17. Delivery — 只能在 Quality approved 后生成，写入 MP4、封面、标题/文案、字幕、音频、主时间线、台账、claim-to-evidence、QC、披露和文件哈希。

阶段责任与 artifact path 由 executable contract 决定；本页说明操作顺序和人工门禁。代码、Schema、Skill 或其他说明有冲突时，以 executable contract 和 strict audit 为准，并修复漂移的下游说明。

## 发布反馈

发布回执和反馈写入 `09_feedback/publish-receipt.json` 与 `feedback.json`，平台事实必须来自真实回执；留存、完播、复看、跳出点、收藏/分享和高质量评论按视频与 beat 记录。每条学习结论必须包含观察、假设/证据边界、下一条可执行改动和样本需求。反馈不回写生产阶段状态。

工作流自身的门禁、路径或渲染问题另记入 `09_feedback/workflow-improvement-log.json`，保留复现步骤和证据哈希，并通过仓库修复和回归验证闭环；它不是绕过生产门禁的通道。详见 [`workflow-improvement-loop.md`](workflow-improvement-loop.md)。

## 验收

```powershell
python -m pytest -q -p no:cacheprovider
python -m json.tool schemas/canonical-workflow.schema.json > $null
git diff --check
```
