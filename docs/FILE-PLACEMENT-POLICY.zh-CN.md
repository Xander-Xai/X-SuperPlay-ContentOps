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

## config/

流水线读取的机器可读配置。只放声明式内容——不放可执行代码，不放生成物。

```
config/
├── accounts/
│   ├── x-superplay-1024.json                 # 账号 DNA
│   ├── x-superplay-future-intelligence.json  # 账号 DNA
│   └── prompts/
│       └── *.prompt.md                       # 一键粘贴的账号提示词
└── optimization/
    ├── policy.json
    ├── signals.json
    └── *.json
```

- 一个账号在 `config/accounts/` 下只有一个文件。DNA 是配色、画面配比、字幕样式、
  封面规则、叙事模板和提示词路径的唯一来源。
- 提示词文件是纯文本：它会被粘贴进对话，因此不带 front matter，也不带说明性注释。
- `scripts/check_account_dna.py` 会在 DNA 偏离品牌基座、或偏离它自己的提示词时报错。

## vendor/

来自另一个仓库、且必须在上游消失后仍能存活的代码。

```
vendor/
└── gzh-thinktank/          # 公众号工作流，逐字节导入
    ├── MANIFEST.md         # 来源、排除项、预期的校验器输出
    └── gzh_未来智能/        # 永不修改
```

- `vendor/` 用于上游正在退役的代码，因此**入库提交**——与 `.runtime/` 相反，后者
  可以重新获取，所以被 gitignore。
- 该目录树永不修改。要变更就重新导入并更新摘要。
- 每个 vendored 目录都带 `MANIFEST.md`：来源仓库与提交、树摘要、排除了什么以及
  为什么、它自己的校验器预期输出是什么。
- 可重建依赖（`node_modules`、`.venv`）和任何带凭据的内容一律不入库。
- `scripts/gzh_pin.py` 会重算摘要。不符即是失败，不是警告。

## tests/

正式测试布局。

## 仅本地文件（gitignore）

- ```.env```（密钥）
- ```.verify-tmp/```（网关日志暴露 Provider 详情）
- ```docs/ai-provider-selection.md```（业务策略）
- ```runtime-config-backups/``
- ```diagnostics/``
- ```outputs/```（生成物）