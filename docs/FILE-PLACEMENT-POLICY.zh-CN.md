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
├── gzh-thinktank/          # 公众号工作流，逐字节导入
│   ├── MANIFEST.md         # 来源、排除项、预期的校验器输出
│   └── gzh_未来智能/        # 永不修改
└── x-growth-os/            # X 增长工作流，逐字节导入（64 个文件）
    └── MANIFEST.md         # 来源、什么都没排除、永不修改
```

- `vendor/` 用于上游正在退役的代码，因此**入库提交**——与 `.runtime/` 相反，后者
  可以重新获取，所以被 gitignore。
- 该目录树永不修改。要变更就重新导入并更新摘要。
- 每个 vendored 目录都带 `MANIFEST.md`：来源仓库与提交、树摘要、排除了什么以及
  为什么、它自己的校验器预期输出是什么。
- 可重建依赖（`node_modules`、`.venv`）和任何带凭据的内容一律不入库。
- `scripts/gzh_pin.py` 会重算摘要。不符即是失败，不是警告。
- `scripts/x_growth_pin.py` 对 X 树做同样的事；`--suite` 还会跑 vendored 分析脚本的测试。

## projects/

内容运行项目与金样本：

```
projects/
└── <slug>/
    ├── project.yaml
    ├── sources/
    ├── script/
    ├── assets/
    ├── work/           # 中间渲染（gitignored）
    ├── final/          # 输出 MP4（gitignored）
    └── receipts/
```

大体积生成文件（MP4、WAV、PNG）按 `.gitignore` 的产物策略处理。

### 文本轨项目（`projects/x-growth-en/`）

X 项目没有 `sources/`、`script/`、`work/`、`final/`：没有成片。它仍按项目放置，
只是布局是文本形状：

```
projects/x-growth-en/
├── project.yaml          # account_slug、platforms: [x]、language: en、gate: scripts/x_post.py
├── posts/                # <content_id>.json —— 每条帖子一个 contentops.x-post/v1 记录
├── templates/            # posts.csv、x-metric-snapshots.csv、x-account-snapshots.csv
├── assets/
│   └── cards/            # <id>.html 入库；渲染出的 <id>.png 被 gitignore
└── receipts/             # x-check-*.json、x-package-*.json、x-publish-*.json
```

- 一条帖子就是一个文件，放在 `posts/`。JSON 是记录本体；`templates/posts.csv` 是它的
  行式镜像，由 `--mark-published` upsert、由 `--verify-log` 对照。
- 卡片以 HTML 为产物，PNG 是渲染结果，因此被 gitignore——重新渲染，不要提交。
- `project.yaml` 不得出现 `quality_gate: enforced`：那个键会让项目进入视频脚本门禁
  （SQ01–SQ07），而它并不描述一条 X 帖子。X 的门禁是 `scripts/x_post.py`，写在 `gate:` 里。
- 工作流本体在 `vendor/x-growth-os/`，永不修改。

## tests/

正式测试布局。

## 仅本地文件（gitignore）

- ```.env```（密钥）
- ```.verify-tmp/```（网关日志暴露 Provider 详情）
- ```docs/ai-provider-selection.md```（业务策略）
- ```runtime-config-backups/``
- ```diagnostics/``
- ```outputs/```（生成物）