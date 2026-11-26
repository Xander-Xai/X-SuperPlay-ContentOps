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

## skills/

仓库自有 Skill 指令及其参考资料、模板放在 `skills/<name>/`。第三方 vendor 内容、
凭证、生成产物和运行时状态不得放在此处。可发现不代表权利已获核验或执行已获授权。

## scripts/

CLI 工具、运维脚本、验证、构建编排。

新增校验脚本（例如 ```check_skill_references.py```）属于此处。
宿主与双线入口也属于此处：`easel_host.py`（受门禁保护的宿主状态/回环启动）、
`bundle_handoff.py`（Bundle → VIDEO / GRAPHIC_TEXT 计划）、
`graphic_package.py`（失败即拒绝的图文包，停在审核）、
`graphic_generate.py`（需显式授权的 Codex/MiniMax 图文生图）、
`agent_drive.py`（coding agent 的步骤计划与受控执行器）。

## config/

机器可读、既不是固定版本也不是密钥的配置：

```
config/
├── accounts/<slug>.json      # 账号 DNA；商业策略不进入本公开仓库
└── registry/
    ├── platforms.json        # contentops.platform-registry/v1 —— 本地集成状态
    └── accounts.json         # contentops.account-registry/v1 —— 仅公开账号身份
```

```config/registry/``` 是唯一的平台注册表。换目录或换格式再建一套是缺陷，不是备选方案。
只允许登记本仓库已跟踪的账号配置；私有账号的 DNA 就是不出现，不使用占位身份替代。

## src/

核心业务逻辑。provider 代码、契约与门禁放在这里，不放 `scripts/`。
与平台工作直接相关的四个包：```src/contentops/platforms/```（注册表 loader）、
```src/contentops/content_kernel/```（Bundle 校验与形式 handoff）、
```src/contentops/easel/```（宿主门禁与回环生命周期，不复制上游）、
```src/contentops/graphic/```（图文包、生图方法与权利绑定图片校验）。
这些模块均不能在没有明确执行授权时渲染、发布或花费 Provider 额度。

## 产物根（Output Root）

一次运行的产物——渲染件、草稿、卡片、音频、日志、临时状态——是产物，不是源码。
它们可再生、体积大、对任何看 diff 的人都没有价值。本仓库只放代码、证据和收据；
产物一律落在 checkout 之外。

`CONTENTOPS_OUTPUT_ROOT` 决定它们落在哪里：

| 根 | 放什么 | 未设变量时 |
|---|---|---|
| `<root>/workspace` | 实验：项目目录及其渲染产物 | `projects/_local/` |
| `<root>/deliverables` | 成品：QC 通过且经人工复核 | `outputs/` |
| `<root>/_tmp` | 临时与验证状态 | `.verify-tmp/` |

在仓库被 gitignore 的 `.env` 里设一次即可，加载器会注入：

```
CONTENTOPS_OUTPUT_ROOT=D:\AI-Outputs\X-SuperPlay-ContentOps\2026-11-12
```

变量未设时，三个根与过去完全一致——CI 看到的、每一份已提交收据里写的，都是那三个。
没有任何东西会自己搬家：指向 `projects/<slug>/receipts/x.json` 的收据仍然指向那里。

`src/contentops/paths.py` 是唯一解析这三个根的模块。脚本向它要
`workspace_root()`、`deliverables_root()` 或 `tmp_root()`，不写死路径。

项目目录可以位于两个根之下：仓库的 `projects/`（跟踪的基线——别的机器要能复核的证据与收据）
和 workspace（实验）。只认前者的门禁，会在沙箱搬出去的那一刻拒绝每一个实验。

### 什么出仓库

| 出仓库 | 去哪 |
|---|---|
| 渲染件、草稿、卡片、音频 | workspace，复核通过后晋级到 `deliverables` |
| 临时与验证状态 | `<root>/_tmp` |
| 一次性报告与诊断 | 归档区的 `reports/` |

### 什么留下

| 留下 | 原因 |
|---|---|
| `projects/<slug>/` 里被跟踪的文件 | 基线、证据、收据——别的机器要能复核 |
| `.runtime/` | pin 住的 Easel v0.2.1；`runtime/easel.lock.json` 钉住了它的路径 |
| `assert/`、`.private/` | Founder 声音与 Provider 身份：不是产物，也不共享 |
| `vendor/` | 未验证的第三方素材，只留本机 |

## runtime/

仅机器可读的固定版本和来源记录。

```runtime/skill-registry.json``` 是能力声明指针表；
```runtime/content-skill-status.json``` 记录已安装 Skill 引用的、当前分支并不存在的代码。

## tests/

正式测试布局。

## 仅本地文件（gitignore）

- ```.env```（密钥）
- ```.verify-tmp/```（网关日志暴露 Provider 详情）
- ```docs/ai-provider-selection.md```（业务策略）
- ```runtime-config-backups/``
- ```diagnostics/``
- ```outputs/```（生成物）