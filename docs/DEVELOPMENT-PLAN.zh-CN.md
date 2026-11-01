---
translation_of: docs/DEVELOPMENT-PLAN.md
language: zh-CN
translation_status: synced
---

# 开发计划

[English](DEVELOPMENT-PLAN.md) | [简体中文](DEVELOPMENT-PLAN.zh-CN.md)

> 基于里程碑执行。每个里程碑都有退出标准。
>
> 状态验证：2026-11-01，分支 `fix/57-m5-media-fixtures`。

## 状态标记

| 标记 | 含义 |
|---|---|
| **DONE** | 退出标准已满足且有证据 |
| **PARTIAL** | 机制存在；某个具名退出标准未满足 |
| **ACTIVE** | 当前工作 |
| **UNMERGED** | 已在分支实现但未集成 |
| **NOT STARTED** | 无实现 |

## 里程碑

| 里程碑 | 描述 | 状态 | 证据 / 阻碍 |
|---|---|---|---|
| M0 | 仓库规范化：文档、运行时事实、治理 | **DONE** | `dev_check.py` 通过；锁与文档检查 |
| G0.5 | GitHub 与 Claude Code 开发治理 | **DONE** | 分支保护、PR 模板、Agent 规则 |
| G0.6 | 上游监控、双语文档、Windows 子进程策略 | **DONE** | `check_easel_upstream.py`、`check_i18n.py`、`process_utils.py` |
| M1 | 稳定 Easel V1 流水线与黄金回归 | **PARTIAL** | 构建与 QC 存在；没有完成的人工审核 |
| M2.0 | MiniMax 能力验证 | **DONE** | `research/providers/*`（Issue #4） |
| M2-M4 | MiniMax 语音 / 图片 / H3 集成 | **DONE（已实现）** | 已验证子集见 CURRENT-STATE；`PENDING_FOUNDER_REVIEW` |
| M4.5 | 媒体收敛：唯一清单、唯一门禁词汇 | **DONE** | 97 项测试；`projects/m45-technical-integration` |
| M5 | 证据优先生产链 | **本分支 DONE** | `scripts/m5_production.py`、`projects/m5-media-use` |
| M5-M6 | 跨仓库 `SourceArtifact` 工作流与生产 E2E | **NOT STARTED** | Issue #6；依赖 content-router 层 |
| 内容路由 | 账号 DNA → 路线 → Brief → 现有流水线 | **UNMERGED** | `feat/content-router`（PR #49，草稿） |
| 收敛 | 文档、Skill、分支与固定版本收敛 | **ACTIVE** | [CONVERGENCE-REQUIREMENTS-2026-11-01.md](CONVERGENCE-REQUIREMENTS-2026-11-01.md) |

## 编号说明

本仓库中的 “M5” 指两件不同的事：

- **M5 证据优先生产链** —— 已实现，入口 `scripts/m5_production.py`。
- **M5-M6 跨仓库 SourceArtifact / 生产 E2E** —— 原始里程碑计划（Issue #6），未开始。

文档说 “M5” 时，以上表为准，不要只看 Issue 编号。

## 退出标准

### M1 —— 流水线稳定

- 连续 3 次 Easel 构建通过，QC 通过，运行时校验通过。
- 至少一个项目存在人工审核凭证。
- 当前阻碍：第三个标准从未满足。

### M2-M4 —— 供应商集成

- 每种模态的真实订阅冒烟测试通过。
- 凭证以观测差值记录生成前后的配额。
- 回退在凭证中具名，且永不报告生产就绪。
- 当前阻碍：Founder 批准，而非实现。

### M5-M6 —— 生产 E2E

- 3 个不同来源 → 同一 ContentRun 工作流 → 3 个 final MP4。
- 无仓库专用代码。
- 每个都经过 Founder 审核。
- 当前阻碍：跨仓库适配器与 content-router 层未合并。

## 严格顺序

```text
M0 → G0.5 → G0.6 → M1 → M2.0 → M2-M4 → M4.5 → M5 → M5-M6
```

不得跳步。实现存在但退出标准未满足的里程碑仍保持开放。

## 当前重点

文档与 Skill 收敛（收敛需求 P0），随后是 Owner 决策 D1–D6。在这些决策记录之前，
不新增能力。
