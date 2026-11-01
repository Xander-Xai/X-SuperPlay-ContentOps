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
`graphic_package.py`（人工图文包，停在审核）。

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
```src/contentops/graphic/```（人工图文包与权利绑定图片校验）。
它们都不渲染、不发布、不花钱。

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