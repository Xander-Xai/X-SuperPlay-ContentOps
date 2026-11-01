---
translation_of: docs/DEVELOPMENT-STANDARD.md
language: zh-CN
translation_status: synced
---

# 开发标准

[English](DEVELOPMENT-STANDARD.md) | [简体中文](DEVELOPMENT-STANDARD.zh-CN.md)

> 如何在此仓库工作。对人类和 Claude Code 均有约束力。

## 事实来源（优先级顺序）

```text
真实执行凭证 > 当前代码 > 机器可读锁/配置 > 当前 ADR > 当前状态 > 运行手册 > 研究 > 旧计划
```

文档与代码冲突时：以代码为准，并更新文档。

## Issue 驱动开发

非平凡变更在实现前必须先有 Issue。

Issue 类型：Bug、Task、Experiment（见 `.github/ISSUE_TEMPLATE/`）。

## 分支生命周期

```text
main（规范分支）
  -> 短生命周期 issue 分支
  -> PR
  -> CI（必须通过）
  -> squash 合并
  -> 分支删除
```

分支命名：`feat/<issue>-...`、`fix/<issue>-...`、`test/<issue>-...`、`chore/<issue>-...` 等。

### 特性分支 CI

特性分支通过向自身分支推送运行检查，不通过把分支合入已授权的父分支来运行：

```bash
gh workflow run ci.yml --ref <branch>
```

`.github/workflows/ci.yml` 对 `feat/**`、`fix/**`、`chore/**`、`security/**`、
`docs/**` 和 `ci/**` 的 push 运行完整检查，并支持手动触发。运行记录以分支 ref
标识，不合入 `main`，也不把未授权的父分支合入 `main`，且不替代 PR 检查。
如果分支上的工作流早于这些触发器，需要先合入一次当前 `main`（或触发器提交）
才能手动运行。

## 提交规则

前缀：`feat:`、`fix:`、`test:`、`docs:`、`refactor:`、`chore:`、`research:`

正文必须引用 issue：`Refs #N` 或 `Closes #N`。

不要巨型提交。一个提交一个逻辑变更。

## 依赖策略

新增任何依赖前先回答：

1. 为什么标准库不够用？
2. 是运行时依赖还是仅开发依赖？
3. 谁维护它？
4. 许可证是否兼容？
5. 是否支持 Windows？
6. 它是否会引入网络/进程执行风险？

如果标准库能做，就用标准库。

## 错误处理

- FAIL 就是 FAIL，绝不静默降级。
- 回退必须出现在凭证中，并带 `quality_impact`。
- 人工批准前 `production_ready: false`。

## 日志 / 凭证策略

每次项目运行产出：

```
projects/<slug>/receipts/
  build-<engine>.json
  qc-report.json
  runtime-receipt.md
  human-review.json（完成时）
```

没有凭证就等于任务没完成。

## 测试要求

- 每次 PR 前运行 `python scripts/dev_check.py`
- `python scripts/test_basic.py` —— 脚本级套件（10 项）
- `python scripts/check_docs.py` —— 文档一致性
- `python scripts/check_repo_policy.py` —— 文件放置 + 安全
- `python scripts/check_skill_references.py` —— 已安装 Skill 与本分支代码的一致性
- `python scripts/check_i18n.py` —— 双语结构一致性
- 新增 `tests/test_*.py` 必须同时加入 `.github/workflows/ci.yml`
- 路径处理需要 Windows 专项测试

## 文档更新矩阵

| 当你修改…… | 需同步更新…… |
|---|---|
| 运行时行为 | CURRENT-STATE + RUNBOOK |
| 架构 | ARCHITECTURE + ADR |
| 公共合约 | 合约文档 + 测试 |
| 质量标准 | QUALITY-STANDARD + 测试 |
| 供应商事实 | 能力证据 + ADR |

## 安全

- Git 中无 API key
- Git 中无 `.verify-tmp/`
- Git 中无 `docs/ai-provider-selection.md`（gitignored）
- 凭证必须脱敏
- 公开文档中不出现供应商端点 URL，除非是规范且已脱敏

## Windows 兼容性

这是一个 Windows 优先的项目。

- PR 前在 Windows（PowerShell）上测试
- 所有文本文件使用 UTF-8
- 校验 FFmpeg 路径
- 处理字幕路径转义（Windows 冒号问题）
- 支持中文路径 / 含空格路径

## 外部 API / 供应商集成规则

```text
能力验证 -> 合约 -> 实现 -> 真实冒烟测试 -> 凭证
```

不要假适配器。`MANUAL_ONLY` 是有效状态。
