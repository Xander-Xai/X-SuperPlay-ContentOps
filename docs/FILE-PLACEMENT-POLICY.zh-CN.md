---
translation_of: docs/FILE-PLACEMENT-POLICY.md
language: zh-CN
translation_status: synced
---

# 文件放置策略

[English](FILE-PLACEMENT-POLICY.md) | [简体中文](FILE-PLACEMENT-POLICY.zh-CN.md)

> 每种文件归属何处。对人类和 Claude Code 均有约束力。

## ROOT 目录

仅允许长期入口点：
- README.md, AGENTS.md, CLAUDE.md, CONTRIBUTING.md, SECURITY.md
- .env.example, .gitignore, .gitattributes, .editorconfig

## docs/

仅规范产品文档。每个文件必须出现在 ```docs/INDEX.md```。

## research/

非规范调查、spike、实验。每个文件必须有 ```canonical: false``` 头。

## research/archive/

仅已废弃的历史资料。每个文件必须有 ```status: superseded``` 头。

## scripts/

CLI 工具、运维脚本、验证、构建编排。

## runtime/

仅机器可读的固定版本和来源记录。

## tests/

正式测试布局。

## 仅本地文件（gitignore）

- ```.env```（密钥）
- ```.verify-tmp/```（网关日志暴露 Provider 详情）
- ```docs/ai-provider-selection.md```（业务策略）
- ```runtime-config-backups/``
- ```diagnostics/``
- ```outputs/```（生成物）