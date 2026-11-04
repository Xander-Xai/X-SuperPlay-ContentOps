---
translation_of: docs/DEFERRED-WORK.md
language: zh-CN
translation_status: synced
---

# Deferred Work Register

[English](DEFERRED-WORK.md) | [简体中文](DEFERRED-WORK.zh-CN.md)

> 记录被**明确 descope**、而非已完成的工作。关闭此处列出的 Issue 只表示
> “当前不做、证据已保留”,绝不表示“已完成”。每项都写明归档位置与重开条件。

## 归档

- 根目录:`D:\Archives\contentops\2026-11\`
- 含字节数与 SHA-256 的清单:`D:\Archives\contentops\2026-11\INDEX.md`
- 删除源引用前,所有 Git bundle 均已通过 `git bundle verify`。

## 条目

### D-1 — Issue #6:三个真实端到端视频

| 字段 | 值 |
|---|---|
| 未完成内容 | 三个来自不同真实来源的 E2E 视频,各自带提交的 receipt 链和完成的人工评审 |
| 已有内容 | `main` 上的 M5 证据链;始终以 `PENDING_FOUNDER_REVIEW`、`production_ready: false` 结束 |
| 归档 | `branches/main.bundle`(关闭时快照) |
| 重开条件 | 有明确交付窗口并选定真实来源时,开新 Issue 并引用此条 |
| 状态 2026-11-04(closeout 后) | **实际已重开。** `main` 已提交三次真实来源运行(PR #117、#119);每次均通过自动与视觉 QC,并停在 `PENDING_FOUNDER_REVIEW`。Issue #6 保持开放,等待 Founder 对三个成片 MP4 的人工评审;除此之外工程验收已完成 |

### D-2 — Issue #51:XHS 迁移

| 字段 | 值 |
|---|---|
| 未完成内容 | 权利已清的 XHS 迁移、干净克隆验证、原远程退役门禁 |
| 已有内容 | 仅本地的 `feat/xhs-fa-migration`,从未推送;报告 30 个权利未知 Skill |
| 归档 | `branches/feat_xhs-fa-migration.bundle` |
| 重开条件 | 存在逐 Skill 权利清单,且 Owner 授权公开推送 |
| 状态 2026-11-04(closeout 后) | **实际已重开。** 归档树已完成审计(报告见 PR #112):vendor 根为 Apache-2.0,覆盖 40 个 Skill;5 个声明 MIT,1 个带 MIT `LICENSE`,1 个为 AGPL-3.0。Issue #51 保持开放,等待剔除 AGPL 后的权利已清子集;`main` 不分发任何内容 |

### D-3 — Issue #56:GZH 权利审计

| 字段 | 值 |
|---|---|
| 未完成内容 | vendored GZH 树的组件级许可/溯源审计与 receipt 脱敏复核 |
| 已有内容 | `main` 中 **0** 个 GZH 文件,无 `vendor/gzh-thinktank/`;该树只存在于分支和本地工作目录 |
| 归档 | `branches/fix_56-gzh-provenance.bundle`、`untracked/gzh-thinktank.tar.gz` |
| 重开条件 | 再次提出 GZH 轨道时;审计必须从归档树开始,不能凭记忆 |
| 状态 2026-11-04(closeout 后) | **实际已重开。** 归档树已完成审计(报告见 PR #112):50 个 `SKILL.md` 中 45 个既无许可声明也无许可文件,3 个声明 MIT,1 个带 MIT `LICENSE`,1 个为 AGPL-3.0。Issue #56 保持开放,等待逐个清理、替换或永久排除;`main` 仍为 0 个 GZH 文件 |

### D-4 — Issue #94:content-router S3–S4

| 字段 | 值 |
|---|---|
| 未完成内容 | capture plan、账号配置、brief/script/design/optimisation 阶段 |
| 已有内容 | S1(#93)、S2(#95)与路由器(#114)已在 `main`;S4 阶段策略已作为 PR #118 合并 |
| 归档 | `branches/feat_content-router.bundle` |
| 重开条件 | ADR-014 交付 hold 产生首个真实交付,且该交付确实需要某个阶段 |
| 状态 2026-11-04(closeout 后) | **closeout 后已交付。** PR #118 合并了 S4 阶段策略与设计路由。Issue #94 已关闭;此条仅为归档 bundle 保留 |

### D-5 — motion-study 导入(未合并功能)

| 字段 | 值 |
|---|---|
| 未完成内容 | `src/contentops/media/motion_study.py`、`scripts/motion_study_import.py`、模板与测试曾在 Codex worktree 中暂存,但从未开 PR |
| 归档 | `worktrees/codex_motionclone.tar.gz`、`patches/codex_motionclone.patch` |
| 重开条件 | 视频工作流优化排期时;恢复 tarball、跑测试后再开 PR |

### D-6 — Tier-1 文档收敛(未提交)

| 字段 | 值 |
|---|---|
| 未完成内容 | `AGENTS.md`、`CLAUDE.md`、`README*`、`DEVELOPMENT-PLAN*`、`TEST-PLAN*` 以及双账号视频优化计划的更新仅存在于未提交工作区 |
| 归档 | `patches/main-worktree-wip.patch`、`untracked/VIDEO-WORKFLOW-OPTIMIZATION-PLAN.md`、`untracked/motion-*.md` |
| 重开条件 | 排期文档 PR 时;对当前 `main` 重新应用 patch,并重跑 `dev_check.py` |

## 规则

只有重开条件满足、在新 Issue/PR 下完成工作、并有 receipt 记录结果后,条目才能移出本登记。删除归档是独立的文件系统清理决定。
