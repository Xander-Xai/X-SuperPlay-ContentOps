---
translation_of: docs/PLATFORM-INTEGRATION-STATUS.md
language: zh-CN
translation_status: synced
---

# 平台集成状态

[English](PLATFORM-INTEGRATION-STATUS.md) | 简体中文

> 本仓库在每个平台上实际能做什么。数据在
> [`config/registry/platforms.json`](../config/registry/platforms.json)；决策记录在
> [ADR-015](adr/ADR-015-platform-placeholders-and-content-bundle.md)。
> 一行说的是**本分支**的事实，永远不是组合策略。

## 如何读状态

| 状态 | 含义 | 前提 |
|---|---|---|
| `PLANNED` | 本分支没有该平台代码，已写明阻断原因 | 无（占位） |
| `INTEGRATED` | 本分支有平台专属代码，离线测试通过 | 代码 + 测试 |
| `TESTED` | 有一次真实本地运行并留下回执 | 代码 + 测试 + 运行 |
| `PILOT_READY` | 真的创建过平台草稿 | 上一条 + 草稿 |
| `PRODUCTION_ACCEPTED` | 真的发布过，并有回执记录 | 上一条 + URL + 人工审核 |

占位不是进展。`PLANNED` 不等于"已配置"，`INTEGRATED` 不等于"已发布"，
任何一行都不意味着账号访问、指标回收或发布授权。

## 九个平台

| 平台 | 本地条目 | 流水线 | 本地状态 | Easel 能力 | 阻断原因 |
|---|---|---|---|---|---|
| 抖音 | `douyin` | `VIDEO` | `PLANNED` | `UPSTREAM_DECLARED` | `PLATFORM_CODE_ABSENT`、`ACCOUNT_NOT_PUBLIC` |
| 小红书（视频） | `xiaohongshu_video` | `VIDEO` | `PLANNED` | `UPSTREAM_DECLARED` | `PLATFORM_CODE_ABSENT`、`ACCOUNT_NOT_PUBLIC`、`RIGHTS_UNRESOLVED` |
| 小红书（图文） | `xiaohongshu_image` | `XHS_EDITORIAL` | `PLANNED` | `UPSTREAM_DECLARED` | `PLATFORM_CODE_ABSENT`、`ACCOUNT_NOT_PUBLIC`、`RIGHTS_UNRESOLVED` |
| B站 | `bilibili` | `VIDEO` | `PLANNED` | `UPSTREAM_DECLARED` | `PLATFORM_CODE_ABSENT`、`ACCOUNT_NOT_PUBLIC` |
| 视频号 | `shipinhao` | `VIDEO` | `PLANNED` | `UPSTREAM_DECLARED` | `PLATFORM_CODE_ABSENT`、`ACCOUNT_NOT_PUBLIC` |
| 公众号 | `wechat_article` | `GZH_EDITORIAL` | `PLANNED` | `UPSTREAM_DECLARED` | `PLATFORM_CODE_ABSENT`、`ACCOUNT_NOT_PUBLIC`、`RIGHTS_UNRESOLVED` |
| 知乎 | `zhihu` | `ARTICLE_EDITORIAL` | `PLANNED` | `UPSTREAM_DECLARED` | `PLATFORM_CODE_ABSENT`、`ACCOUNT_NOT_PUBLIC` |
| CSDN | `csdn` | `ARTICLE_EDITORIAL` | `PLANNED` | `ABSENT` | `PLATFORM_CODE_ABSENT`、`ACCOUNT_NOT_PUBLIC`、`EASEL_CAPABILITY_ABSENT` |
| YouTube | `youtube` | `VIDEO` | `PLANNED` | `ABSENT` | `PLATFORM_CODE_ABSENT`、`ACCOUNT_NOT_PUBLIC`、`EASEL_CAPABILITY_ABSENT` |
| X | `x` | `X_EDITORIAL` | `INTEGRATED` | `ABSENT` | — |

`x` 是唯一非 `PLANNED` 的行，而且范围很窄：X 发帖闸门只打包并停在
`AWAITING_MANUAL_PUBLISH`。没有任何分支返回 `PUBLISHED`，`PublishMode.API` 直接抛出，
也不回收任何指标。这个闸门属于本仓库，不构成对其他任何 X 执行仓库的授权主张。

## GitHub —— 证据基础设施，不是平台

GitHub **不**是 `platforms.json` 中的一行。它没有流水线、没有账号、也没有发布目标；
loader 要求三者都有值，写一行就等于强行填假值。GitHub 的角色改记在这里。

| 字段 | 取值 |
|---|---|
| 行类型 | `INFRASTRUCTURE` |
| 集成状态 | `NOT_APPLICABLE` —— 没有可集成的东西 |
| 发布目标 | `NOT_A_PUBLISH_TARGET` |
| 指标 | `NONE` |
| 本地代码 | 无；唯一关联是本仓库自身的 Git 历史与 CI |

## Easel 上游覆盖

Easel v0.2.1（已锁定，`3fe2d99`）声明支持七个平台的登录、适配与发布。
那是上游的陈述，不是本仓库已验证的能力。每条注册表记录现在携带
`easel_capability`：`UPSTREAM_DECLARED` 并给出上游 Skill 路径，或 `ABSENT`。
没有任何一行为 `verified_here: true`；宿主本身受门禁保护，当前为 `HOST_BLOCKED`。

| 覆盖情况 | 平台 |
|---|---|
| 上游已声明 | 抖音、小红书、B站、视频号、公众号、知乎 |
| 上游未覆盖 | CSDN、YouTube、X |
| 仅上游、组合之外 | 快手 —— 按设计不建本地行 |

九个平台中有六个被上游声明。这是关于 Easel 的事实，永远不是对九平台范围的限制：
CSDN、YouTube、X 是 ContentOps 自己的原生工作，不是需要被解释掉的缺口。

## 重新生成与检查

```bash
python scripts/platforms.py check
python scripts/platforms.py list --json
python tests/test_platform_registry.py
```

新增一个平台 = 新增一行加它的证据，永远不是新增第二套生产系统。
