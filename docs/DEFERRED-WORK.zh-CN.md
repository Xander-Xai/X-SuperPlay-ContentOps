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

### D-2 — Issue #51:XHS 迁移

| 字段 | 值 |
|---|---|
| 未完成内容 | 权利已清的 XHS 迁移、干净克隆验证、原远程退役门禁 |
| 已有内容 | 仅本地的 `feat/xhs-fa-migration`,从未推送;报告 30 个权利未知 Skill |
| 归档 | `branches/feat_xhs-fa-migration.bundle` |
| 重开条件 | 存在逐 Skill 权利清单,且 Owner 授权公开推送 |

### D-3 — Issue #56:GZH 权利审计

| 字段 | 值 |
|---|---|
| 未完成内容 | vendored GZH 树的组件级许可/溯源审计与 receipt 脱敏复核 |
| 已有内容 | `main` 中 **0** 个 GZH 文件,无 `vendor/gzh-thinktank/`;该树只存在于分支和本地工作目录 |
| 归档 | `branches/fix_56-gzh-provenance.bundle`、`untracked/gzh-thinktank.tar.gz` |
| 重开条件 | 再次提出 GZH 轨道时;审计必须从归档树开始,不能凭记忆 |

### D-4 — Issue #94:content-router S3–S4

| 字段 | 值 |
|---|---|
| 未完成内容 | capture plan、账号配置、brief/script/design/optimisation 阶段 |
| 已有内容 | S1(#93)与 S2(#95)已在 `main` |
| 归档 | `branches/feat_content-router.bundle` |
| 重开条件 | ADR-014 交付 hold 产生首个真实交付,且该交付确实需要某个阶段 |

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
