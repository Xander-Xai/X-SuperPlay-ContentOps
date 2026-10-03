---
translation_of: CONTRIBUTING.md
language: zh-CN
translation_status: synced
---

# 贡献指南 — X-SuperPlay-ContentOps

[English](CONTRIBUTING.md) | [简体中文](CONTRIBUTING.zh-CN.md)

## 开发流程

```text
Issue
  -> 分支（Issue 作用域）
  -> 实现
  -> 本地验证 (python scripts/dev_check.py)
  -> PR
  -> CI
  -> 审查
  -> Squash 合并
  -> 分支删除
```

## 分支命名

允许：```feat/<issue>-<desc>```, ```fix/<issue>-<desc>``, ```test/<issue>-<desc>``, ```docs/<issue>-<desc>``, ```chore/<issue>-<desc>``, ```refactor/<issue>-<desc>``, ```research/<issue>-<desc>```

禁止：```tmp``, ```new``, ```test2``, ```final``, ```final2``, ```claude-work``` 等。

## 提交格式

```text
feat:     新功能
fix:      修复
test:     测试
docs:     文档
refactor: 重构（无行为变化）
chore:    构建/工具/依赖
research: 调查或实验
```

始终关联 Issue：```Refs #N``` 或 ```Closes #N```。

## PR 前必做

运行开发门控：

```bash
python scripts/dev_check.py
```

所有检查必须通过。无例外。

## 文件放置

见 ```docs/FILE-PLACEMENT-POLICY.md```。

## 运行时现实规则

> 不要修改文档去匹配你希望为真的事实。修改代码去匹配真实情况，然后更新文档。

规范来源优先级：
```text
真实执行凭证 > 代码 > 锁/配置 > ADR > 当前状态 > 运行手册 > 研究 > 旧计划
```

## 扩展策略（Easel）

```text
ADAPTER > EXTENSION > CUSTOM SKILL > UPSTREAM PATCH > FORK
```

无 ADR + 补丁文件 + 测试，不得修改上游。

## 安全规则

- 永不提交 API Key、Token、Cookie 或凭据
- ```docs/ai-provider-selection.md``` 和 ```.verify-tmp/``` 已 gitignore — 不得强制添加
- Provider 端点 URL 和定价策略保持仅本地
- 所有凭证必须脱敏

## 贡献政策

这是一个 owner 主导的项目 (Xander-Xai)。欢迎外部贡献，但：
- 所有变更需要先有 Issue
- 所有 PR 需要 CI 通过
- 禁止直接推送到 main
- 仅 Squash 合并