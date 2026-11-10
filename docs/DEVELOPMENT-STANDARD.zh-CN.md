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

## 验证要求

遵循权威分级策略：[TEST-PLAN.md](TEST-PLAN.md)。根据受影响行为和风险选择检查，不按改动文件数量机械扩大测试。

- L0 文档/非行为变更：不跑业务测试；仅运行相关文档/链接检查，修改双语镜像时运行 i18n。
- L1 局部低风险代码：先静态分析，通常最多运行一个相关现有测试套件。
- L2 常规行为变更：运行相关测试，通常 1–3 条针对性命令；仅在跨模块契约受影响时增加契约检查。
- L3 高风险行为：运行覆盖风险所需的单元/契约/集成/回归检查；测试预算不能豁免安全验证。
- 仅在环境/运行时/安装/部署变化时运行 `doctor.py`；仅在实际视频产物或 QC 行为变化时运行 `qc_video.py`；仅在相关脚本入口/基础行为变化时运行 `test_basic.py`。
- `python scripts/dev_check.py` 是准备 PR 时运行一次的完整本地门禁，不是每次编辑都要运行。`--quick` 只跳过仓库策略检查，仍会运行其他门禁和 `test_basic.py`，不是针对性测试模式。
- 不重复运行未受后续修改影响且已通过的检查，不盲目重试失败，也不无证据扩大覆盖。失败先诊断，再只重跑受影响的检查。必要验证通过且无阻断缺陷或关键风险后停止。
- 如实报告未运行的检查，不得写成通过。

准备 PR 时仍保留完整本地门禁和相关业务回归测试。GitHub CI 继续在 Ubuntu、Windows 上运行全部套件及仓库策略检查。不得弱化或绕过 CI、分支保护或安全门禁。

新增 `tests/test_*.py` 必须加入 `.github/workflows/ci.yml`。修改 Windows 路径行为时仍需 Windows 专项测试。

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
