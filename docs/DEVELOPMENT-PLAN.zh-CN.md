---
translation_of: docs/DEVELOPMENT-PLAN.md
language: zh-CN
translation_status: synced
---

# 开发计划

[English](DEVELOPMENT-PLAN.md) | [简体中文](DEVELOPMENT-PLAN.zh-CN.md)

> 基于里程碑执行。每个里程碑都有退出标准。
>
> 最后验证：2026-11-13；已实施 X / 跨平台本地分析和人工选题回流，不代表真实平台效果或发布。
> X 业务规则以 Strategy 唯一 SOP 及 ContentOps 注册账号 DNA 为准，指标与发布须真人核验。


## 状态标记

| 标记 | 含义 |
|---|---|
| **DONE** | 退出标准已满足且有证据 |
| **PARTIAL** | 机制存在；某个具名退出标准未满足 |
| **ACTIVE** | 当前工作 |
| **NOT STARTED** | 无实现 |

## 里程碑

| 里程碑 | 描述 | 状态 | 证据 / 阻碍 |
|---|---|---|---|
| M0 | 仓库规范化：文档、运行时事实、治理 | **DONE** | `dev_check.py` 通过；锁与文档检查 |
| G0.5 | GitHub 与 Claude Code 开发治理 | **DONE** | 分支保护、PR 模板、Agent 规则 |
| G0.6 | 上游监控、双语文档、Windows 子进程策略 | **DONE** | `check_easel_upstream.py`、`check_i18n.py`、`process_utils.py` |
| M1 | 稳定 Easel V1 流水线与黄金回归 | **PARTIAL** | 构建与 QC 存在；没有任何项目持有 APPROVED 的 `human-review.json` |
| M2.0 | MiniMax 能力验证 | **DONE** | `research/providers/*`（Issue #4） |
| M2-M4 | MiniMax 语音 / 图片 / H3 集成 | **DONE（已实现）** | 已验证子集见 CURRENT-STATE；`PENDING_FOUNDER_REVIEW` |
| M4.5 | 媒体收敛：唯一清单、唯一门禁词汇 | **DONE** | 97 项测试；`projects/m45-technical-integration` |
| M5 | 证据优先生产链 | **DONE** | `scripts/m5_production.py`、`projects/m5-media-use`；ASR 回检门禁（#150）；特征基线（#153） |
| 稳定生产入口 | 所有生产者之前的唯一受门禁 CLI | **DONE** | `scripts/make_content.py` + `scripts/production_gates.py`（#157）；7 个 VIDEO / 5 个 GRAPHIC_TEXT 失败即拒绝门禁 |
| 渲染：卡片与公众号文章 | HTML 卡片转 PNG 并做密度审计；文章 HTML 校验 | **DONE（离线）** | `render_cards.py`（#149）、`render_article.py`（#152）；回执恒为 `production_ready: false` |
| M5-M6 | 跨仓库 `SourceArtifact` 工作流与生产 E2E | **DONE（证据在 issue）** | `main` 上三次真实来源运行（#117、#119）通过自动与视觉 QC；Founder 审核 PASS 记录在 #6，已于 2026-11-10 关闭。注意：批准记录在 issue 里，而不是 APPROVED 的 `human-review.json` |
| 内容路由 | 账号 DNA → 路线 → Brief → 现有流水线 | **DONE** | PR #114 / #118；15 个热点源对两个账号开放（#157） |
| 交付层 | 各平台交付包、缩略图与仅草稿交接 | **DONE（打包）** | `video_deliver.py`、`platform_delivery.py`、`graphic_deliver.py`、`wechatsync_browser.py`；仓库内 0 条交付回执 |
| 发布 | 作品真的发到平台并记录 URL | **NOT STARTED** | 未绑定公开账号；除 `x` 外每条注册表记录仍为 `PLANNED`；发布计数 0 |
| M5 阶段拆分（#140） | 把编排器拆成阶段模块 | **ACTIVE** | slice 1 已作为特征基线落地（#153） |
| 收敛 | 文档、Skill、分支与固定版本收敛 | **DONE（2026-11-01 计划；步骤 3–5 后落地）** | [CONVERGENCE-REQUIREMENTS-2026-11-01.md](CONVERGENCE-REQUIREMENTS-2026-11-01.md)；步骤 3–5 由 #114/#118 与 #132–#159 关闭 |

## 编号说明

本仓库中的 “M5” 指两件不同的事：

- **M5 证据优先生产链** —— 已实现，入口 `scripts/m5_production.py`。
- **M5-M6 跨仓库 SourceArtifact / 生产 E2E** —— Issue #6 中的原始里程碑计划，现已随
  Founder 审核记录一起关闭。

文档说 “M5” 时，以上表为准，不要只看 Issue 编号。

## 退出标准

### M1 —— 流水线稳定

- 连续 3 次 Easel 构建通过，QC 通过，运行时校验通过。
- 至少一个项目存在人工审核凭证。
- 当前阻碍：第三个标准从未满足。#6 的审核是一条 issue 评论，不是项目回执，因此
  不能关闭这一条。

### M2-M4 —— 供应商集成

- 每种模态的真实订阅冒烟测试通过。
- 凭证以观测差值记录生成前后的配额。
- 回退在凭证中具名，且永不报告生产就绪。
- 当前阻碍：Founder 批准，而非实现。

### M5-M6 —— 生产 E2E

- 3 个不同来源 → 同一 ContentRun 工作流 → 3 个 final MP4。
- 无仓库专用代码。
- 每个都经过 Founder 审核。
- 当前状态：已满足，但审核记录在 Issue #6，而不是每项目回执中。发布仍未获授权。

### 发布 —— 下一个开放里程碑

- 至少一条平台记录绑定公开账号。
- 一条交付回执写下人真正看到的 URL。
- 因该证据（而不是因为运行器存在）有一条注册表记录升到 `PLANNED` 之上。

## 严格顺序

```text
M0 → G0.5 → G0.6 → M1 → M2.0 → M2-M4 → M4.5 → M5 → M5-M6 → 发布
```

不得跳步。实现存在但退出标准未满足的里程碑仍保持开放。

## 当前重点

1. 发布证据：交付运行器已经建好，但没有任何作品持有真实平台 URL，也没有绑定公开账号。
2. 权利清理（Issue #51、#56），它们把公众号与小红书记录压在 `PLANNED`。
3. M5 阶段拆分（#140），由已记录的特征基线守住。
