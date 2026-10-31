---
translation_of: docs/DEVELOPMENT-STANDARD.md
language: zh-CN
translation_status: synced
---

# 开发标准

[English](DEVELOPMENT-STANDARD.md) | [简体中文](DEVELOPMENT-STANDARD.zh-CN.md)

> 如何在此仓库工作。对人类和 Claude Code 均有约束力。

## 工作流

1. Issue → 分支 → 实现 → 验证 → PR → CI → 审查 → Squash 合并 → 删除分支
2. 永不在 ```main``` 上工作
3. 所有变更通过 PR
4. ```python scripts/dev_check.py``` 必须通过

## 特性分支 CI

特性分支通过向自身分支推送运行检查，不通过把分支合入已授权的父分支来运行：

```bash
gh workflow run ci.yml --ref <branch>
```

`.github/workflows/ci.yml` 对 `feat/**`、`fix/**`、`chore/**`、`security/**`、
`docs/**` 和 `ci/**` 的 push 运行完整检查，并支持手动触发。运行记录以分支 ref
标识，不合入 `main`，也不把未授权的父分支合入 `main`，且不替代 PR 检查。
如果分支上的工作流早于这些触发器，需要先合入一次当前 `main`（或触发器提交）
才能手动运行。

## 双语文档规则

- Tier-1 文档必须同时有英文和中文版本
- 修改英文 Tier-1 文档必须在同一 PR 中更新 zh-CN 镜像
- 运行 ```python scripts/check_i18n.py``` 验证一致性

## Windows 子进程规则

- 后台子进程必须使用 ```scripts/process_utils.py``` 隐藏窗口
- 交互式子进程保持可见
- 禁止 ```shell=True``` 用于后台子进程
- 调试覆盖：```CONTENTOPS_SHOW_SUBPROCESS_WINDOWS=1```

## 扩展策略（Easel）

```text
ADAPTER > EXTENSION > CUSTOM SKILL > UPSTREAM PATCH > FORK
```

## 事实优先级

```text
真实执行凭证 > 代码 > 锁/配置 > ADR > 当前状态 > 运行手册 > 研究 > 旧计划
```
## 测试要求

- 每次 PR 前运行 `python scripts/dev_check.py`
- `python scripts/run_tests.py` —— 运行全部 `tests/test_*.py` 加 `scripts/test_basic.py`，自动发现，每个套件独立进程
- `python scripts/run_tests.py --missing-from .github/workflows/ci.yml` —— 套件存在但没有任何 CI `run:` 步骤执行它时失败（注释不算）
- `python scripts/test_basic.py` —— 脚本层套件（9 项），同时也是被发现的套件之一
- `python scripts/check_docs.py` —— 文档一致性
- `python scripts/check_repo_policy.py` —— 文件放置 + 安全
- Windows 路径处理必须有专项测试
