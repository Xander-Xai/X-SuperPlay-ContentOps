---
translation_of: docs/CONTENT-LIFECYCLE-STAGES.md
language: zh-CN
translation_status: synced
---

# 内容生命周期阶段

> 生命周期阶段的规范模型：为每个阶段记录输入、输出、责任方、实现状态与回执。
> 没有可执行代码的阶段必须保持为占位符，不得写成功回执、发布记录或指标。
>
> 状态：参考文档——2026-11-12 历史基线。
> 最后验证：2026-11-26，#210 候选分支与最新 main 合并；样片仍为 TEST_ONLY、完整 QC WARN，真实交付与人工审核未完成。
> 最后验证：2026-11-21，对照 PR #210 head `d2220078080b83ef0740b594dbedb06791ce9cec` 与实时 Issue #199。PR #210 增加 B 站原生源几何 QC 与 TEST_ONLY 样片回执；这不代表 Issue 已关闭，也不授权生产或发布。
> 2026-11-21 复核：#210 仍是 TEST_ONLY 工程验收，`a5ce83f` 已恢复旧 Motion Canvas 历史阻塞回执；#199 正式交付与发布权限均未获批准。
> 回执记录原生检查及全片解码 PASS、完整 QC WARN、生成式非证据画面与待完成的 Founder 审片。本次未核验全仓已批准人工审核或已创建平台草稿的数量，标记为 NOT_VERIFIED。

相关文档：[架构](ARCHITECTURE.md)、[PRD](PRD.md)、[ADR-015](adr/ADR-015-platform-placeholders-and-content-bundle.md)、[ADR-016](adr/ADR-016-easel-host-adoption.md)、[平台适配器契约](PLATFORM-ADAPTER-CONTRACT.md)、[Easel 能力清单](EASEL-CAPABILITY-INVENTORY.md)。

## 分支状态（先读）

下方阶段表是有日期的 `main` 基线，不是 PR #210 的实时完整清单。PR #210 修改账号 schema 分派、Easel YAML 派生校验与 B 站原生 QC；没有增加发布阶段，也没有满足仍 OPEN 的 Issue #199 真实交付门槛。原生 16:9 回执属于 TEST_ONLY，完整 QC 为 WARN，人工审核仍待完成。

本 PR 已确认：

- 原生横屏 QC 必须显式声明 B 站目标与 native relayout，storyboard 画布为 1920×1080，并逐镜头验证源素材几何。不能把竖屏主画面加边或改标签伪装成原生横屏。
- 已提交样片使用生成式解释图（`generated=true`、`evidence_capable=false`），不能满足真实来源证据或账号生产要求。
- Issue #199 仍开放，待办包括经授权的录屏生产、双账号正式成片、Motion Canvas 编辑器真实导出、人工审片与干净检出复现。
- 2026-11-09 移除 XHS 运行时适配器及 X/GZH 仅人工操作边界是历史事实；本次未核验当前平台草稿/发布数量，标记为 NOT_VERIFIED。

## 定位

`ARCHITECTURE.md` 负责系统边界与两条产线；本文负责**生命周期顺序**及**各阶段状态**。本文映射已有契约，不重新定义契约。

```text
DISCOVERY → RESEARCH → PRECOPY_RESEARCH → BRIEF → CONTENT_BUNDLE → PRODUCTION
    → QUALITY_REVIEW → PLATFORM_PACKAGING → PUBLISH_HANDOFF
    → METRICS_COLLECTION → ANALYSIS → LEARNING_FEEDBACK
    → 返回 Strategy
```

`PRODUCTION` 分为两条产线，并在渲染前分流：

- **VIDEO**：`script → audio → storyboard → assets → compose → quality`（`contentops.copy-to-video/v1`）
- **GRAPHIC_TEXT**：`brief → outline → draft → images → layout → quality → delivery`（`contentops.copy-to-graphic/v1`）

两条产线共用一个前置门禁：创建 `script/master.md` 或 `02_draft/draft.md` 前，必须签署 `PRECOPY_RESEARCH`（`contentops.precopy-research/v1`）。研究包绑定 `DISCOVERY` 产生的 `ContentIntent`，所以门禁证明核验的是哪个主题的证据，而不只是“做过研究”。

## 阶段状态

状态词汇：`implemented`（当前分支有可运行代码）、`partial`（部分组件存在）、`unmerged`（代码在其他分支）、`planned`（占位）。其他分支的事实放在分支说明中，不混入当前分支状态。

| 阶段 | 输入 | 输出 | 责任方 | 状态 | 适配器 / 代码 | 回执 | 阻碍 |
|---|---|---|---|---|---|---|---|
| `DISCOVERY` | Strategy 方向、趋势 | 主题候选 | Strategy + ContentOps | `implemented` | `src/contentops/routing/`、`src/contentops/hotspots/` | 路由结果 | 热点采集需要联网与凭据；离线时为 `BLOCKED` |
| `RESEARCH` | 主题、来源 | `SourceArtifact` 集合 | ContentOps | `partial` | M5 `src/contentops/evidence/` | 来源记录 | 来源研究仍从人工提供的 `SourceArtifact` 开始 |
| `PRECOPY_RESEARCH` | `ContentIntent`、已核验来源 | 研究包 + 签署回执 | ContentOps + 人 | `implemented` | `src/contentops/workflow/preresearch.py`、`scripts/preresearch.py` | `receipts/precopy-research.json` | VIDEO 第 8 门 / GRAPHIC_TEXT 第 6 门；无 `--force`；签署后修改会变为 `STALE` |
| `BRIEF` | 主题、受众 | Brief | ContentOps | `implemented` | `src/contentops/routing/brief.py`；图文契约的 `brief` 阶段 | `BRIEF_READY` | Brief→M5 桥拒绝自动化审批，必须由人批准 |
| `CONTENT_BUNDLE` | Strategy Bundle | 已校验 Bundle + digest | Strategy 所有；ContentOps 消费 | `implemented`（`main`） | `src/contentops/content_kernel/bundle.py`、`scripts/content_bundle.py` | 校验结果 / handoff | Bundle 是计划，不是发布 |
| `PRODUCTION`（VIDEO） | Bundle、claims | 视频主稿 | ContentOps | `implemented` | `make_content.py` + `production_gates.py`；`produce_video.py` / `m5_production.py`、`run_v1.py`、`assemble_easel.py`、ASR 回检 | `build-*.json`、`asr-backcheck.json`、`runtime-receipt.md` | 直接运行 producer 属诊断路径，不经过稳定入口门禁；人工审核待定 |
| `PRODUCTION`（GRAPHIC_TEXT） | Bundle、图片 | 人工包、渲染卡片、已校验文章 | ContentOps | `implemented` | `src/contentops/graphic/`、`graphic_package.py`、`render_cards.py`、`render_article.py` | `graphic-package.json`、`card-render.json`、`gzh-article.json` | 终态为 `AWAITING_MANUAL_REVIEW` 或 `BLOCKED`；PASS 不等于批准 |
| `QUALITY_REVIEW` | 生产产物 | QC + 人工结论 | ContentOps + 人 | `implemented` | `production_gates.py`、`scripts/qc_video.py`、`qc_visual.py`、ASR 回检、`quality_gate.py`、`workflow/gate.py`；B 站原生 profile 另检查逐镜头源几何 | `qc-report.json`、`human-review.json`、原生样片回执 | TEST_ONLY 样片几何/解码 PASS，但完整 QC WARN 且人工审核待定；全仓已批准审核数量 NOT_VERIFIED |
| `PLATFORM_PACKAGING` | 已审核包 | 各平台包 + 草稿 | ContentOps | `partial` | `video_deliver.py`、`platform_delivery.py`、`graphic_deliver.py`、`wechatsync_browser.py`、X 人工门禁 | `06_delivery/` 包回执、`graphic-package.json` | PR #210 未增加打包或发布行为；全仓草稿数量及当前注册表统计 NOT_VERIFIED |
| `PUBLISH_HANDOFF` | 草稿 | 真实 URL + 交付回执 | 人 | `partial` | 人工操作：`video_deliver.py record`、`x_post.py --mark-published`、桥接工具 URL 回显 | `AWAITING_MANUAL_PUBLISH` / `REPORTED_PUBLISHED` / `UPLOADER_EXIT_0` | 无自动发布；上传器退出不等于已发布 |
| `METRICS_COLLECTION` | 交付回执 | 指标快照 | ContentOps | `partial` | `wechat_metrics.py`、`bilibili_metrics.py`、离线 X 分析；均需运营操作 | 指标回执 | 无自动采集；缺失指标为 `NONE`，不是零 |
| `ANALYSIS` | 指标快照 | 发现 | ContentOps | `partial` | X organic-growth advisory（离线） | advisory JSON | 通用分析未实现 |
| `LEARNING_FEEDBACK` | 发现 | 下一轮指导 | Strategy + 人 | `partial` | `x_learning_loop.py`、`platform_learning_loop.py`（本地） | 本地 learning 文件 / handoff | 需操作人员复核主题路由；无自动 Strategy 写作或跨平台因果效果证明 |

## 生产 profile 与内容形式

两条独立轴不可混淆：

| 轴 | 取值 | 归属 |
|---|---|---|
| **内容形式**（生产线） | `VIDEO`、`GRAPHIC_TEXT` | ContentOps |
| **生产 profile**（成本 / 复杂度） | `baseline`、`enhanced`、`experimental` | Strategy |

profile 不等于内容形式。`XHS_EDITORIAL` 与 `GZH_EDITORIAL` 是映射到 `GRAPHIC_TEXT` 的本地类型标签，不会创建第三条产线。

## 契约映射

| 契约 | 所属文件 |
|---|---|
| `contentops.copy-to-video/v1`、`contentops.copy-to-graphic/v1` | `src/contentops/workflow/contract.py` |
| `contentops.precopy-research/v1` | `src/contentops/workflow/preresearch.py` |
| `contentops.bundle-handoff/v1` | `src/contentops/content_kernel/handoff.py` |
| `contentops.graphic-package/v1` | `src/contentops/graphic/package.py` |
| `contentops.qc-canonical/v1` | `src/contentops/media/qc_canonical.py` |
| `contentops.platform-registry/v1` | `config/registry/platforms.json` |

## 规则

1. **一个阶段，一个状态。** 没有代码的阶段是占位，不产出成功回执。
2. **阶段不能冒领后续阶段。** 生产回执不是发布；草稿不是发布；发布不是指标。
3. **人工审核不自动批准。** 人工回执前 `production_ready` 保持 `false`。
4. **指标是证据。** 缺失指标为 `NONE`，不是零，也不能把配额百分比换算为价格。
5. **反馈环属于 Strategy。** ContentOps 提供发现，不替 Strategy 重新选择论点或平台。
6. **门禁没有 `--force`。** `workflow/gate.py approve` 要求新鲜且成功的 check、具名审核人和明确确认。
7. **手工填写 URL 只表示 `REPORTED_PUBLISHED`，不是已验证证据。** 只有外部验证才会产生 `VERIFIED_PUBLISHED`。
8. **`PRODUCTION_ACCEPTED` 绝不自动产生。** 必须同时具备外部验证、书面人工批准与完整交付回执。
9. **X 编辑内容由 `src/contentops/publish/` 负责。** 无 `copy-to-x` 契约，也没有第三套生产引擎。
10. **文案必须晚于预研。** 写主稿、草稿或作出文案决策前，`PRECOPY_RESEARCH` 必须批准并绑定当前 `ContentIntent`；修改研究产物或重新路由会令批准变成 `STALE` / `INCOMPLETE`。

## 剩余占位与未实现能力

以下列项是截至 2026-11-12 的 `main` 缺口快照，不代表已核验当前平台状态：跨平台指标自动采集、自动 Strategy 写作、平台来源归因与因果效果分析仍未在本 PR 中验证；X 发布仍为人工路径；GZH 验证外部工作区但不执行生产/发布；XHS 运行时适配器已于 2026-11-09 移除；五个 `x-superplay-*` 技能未声明为可执行能力。

## 后续行动（历史主线缺口）

1. 验证 Brief→M5 人工文案审核的主线实现状态；本次未重新审查，标记 NOT_VERIFIED。
2. 在扩展平台自动化前完成首个可外部验证的人工交付，并记录人工采集的指标快照。
3. 独立解决 GZH/XHS 权利与验收；工作区验证成功不授予执行或发布权。


2026-11-26 同步说明：保留 main 已合并的 M5 ASR、字幕、分镜、QC 等阶段抽取与兼容入口；#210 的 native Bilibili 检查是附加候选能力，不改变证据门禁或发布边界。
