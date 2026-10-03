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