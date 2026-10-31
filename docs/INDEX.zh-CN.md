---
translation_of: docs/INDEX.md
language: zh-CN
translation_status: synced
---

# 文档索引

[English](INDEX.md) | [简体中文](INDEX.zh-CN.md)

> 单一导航中心。一个事实，一个归属。其他文档链接，不复制。

## 快速入门

1. [README.md](../README.md) — 仓库入口
2. [CURRENT-STATE.md](CURRENT-STATE.md) — 当前运行状态
3. [ARCHITECTURE.md](ARCHITECTURE.md) — 系统边界
4. [PRD.md](PRD.md) — 产品需求
5. [RUNBOOK.md](RUNBOOK.md) — 可执行命令
6. [DEVELOPMENT-PLAN.md](DEVELOPMENT-PLAN.md) — M0–M6 里程碑
7. [QUALITY-STANDARD.md](QUALITY-STANDARD.md) — 质量门控
8. [TEST-PLAN.md](TEST-PLAN.md) — 测试策略

## 合约

- [SOURCE-ARTIFACT-CONTRACT.md](SOURCE-ARTIFACT-CONTRACT.md)
- [MEDIA-PROVIDER-CONTRACT.md](MEDIA-PROVIDER-CONTRACT.md)
- [adr/ADR-008-media-use-adapter.md](adr/ADR-008-media-use-adapter.md) — HyperFrames `media-use` 集成：固定版本适配器，不复制上游
- [CROSS-REPO-INTEGRATION.md](CROSS-REPO-INTEGRATION.md)

## 上游

- [UPSTREAM-EASEL.md](UPSTREAM-EASEL.md) — Easel 固定版本策略

## 里程碑计划

- [M4-H3-PLAN.md](M4-H3-PLAN.md) — M4 MiniMax H3 视频（Issue #22）—— **已实现**
- [M4.5-MEDIA-CONVERGENCE-PLAN.md](M4.5-MEDIA-CONVERGENCE-PLAN.md) — M4.5 媒体收敛（Issue #27）—— **已实现**

## 治理

- [DEVELOPMENT-STANDARD.md](DEVELOPMENT-STANDARD.md) — 开发规则
- [FILE-PLACEMENT-POLICY.md](FILE-PLACEMENT-POLICY.md) — 文件归属规则
- [GLOSSARY.md](GLOSSARY.md) — 高频术语表

## 决策

- [adr/ADR-001-easel-runtime.md](adr/ADR-001-easel-runtime.md)
- [adr/ADR-002-contentops-boundaries.md](adr/ADR-002-contentops-boundaries.md)
- [adr/ADR-003-minimax-plan-provider.md](adr/ADR-003-minimax-plan-provider.md)
- [adr/ADR-004-cross-repo-source-contract.md](adr/ADR-004-cross-repo-source-contract.md)
- [adr/ADR-005-human-approval.md](adr/ADR-005-human-approval.md)
- [adr/ADR-006-upstream-upgrade-policy.md](adr/ADR-006-upstream-upgrade-policy.md)
- [adr/ADR-008-media-use-adapter.md](adr/ADR-008-media-use-adapter.md)

## 事实优先级

```text
真实执行凭证 > 当前代码 > 机器可读锁/配置 > 当前 ADR > 当前状态 > 运行手册 > 研究 > 旧计划
```

## Agent 规则

- [../AGENTS.md](../AGENTS.md) — AI Agent 执行纪律

## 研究

- [../research/README.md](../research/README.md) — 研究索引和归档

## 审计

- [AUDIT-REPORT.md](AUDIT-REPORT.md) — 仓库审计（2026-10-03）
- [audits/windows-subprocess-audit.zh-CN.md](audits/windows-subprocess-audit.zh-CN.md) — Windows 控制台弹窗审计、每个子进程调用点的分类，以及统一进程层（Issue #16）
- [../reports/audits/github-governance-2026-10-31.md](../reports/audits/github-governance-2026-10-31.md) — GitHub 治理执行：PR/Issue/Branch/CI/安全复核与 PR #48 合并（2026-10-31）
- [../reports/audits/contentops-phase2-security-and-unblock-2026-10-31.md](../reports/audits/contentops-phase2-security-and-unblock-2026-10-31.md) — 第二阶段安全、第三方版权与 PR 解锁审计（2026-10-31）
- [../reports/audits/contentops-phase3-p0-convergence-2026-10-31.md](../reports/audits/contentops-phase3-p0-convergence-2026-10-31.md) — 第三阶段 P0 收敛与堆栈解锁（2026-10-31）
- [../reports/audits/contentops-pr71-media-use-final-audit-2026-10-31.md](../reports/audits/contentops-pr71-media-use-final-audit-2026-10-31.md) — PR #71 media-use 集成：安全、版权、代码、端到端与合并门禁审计（2026-10-31）