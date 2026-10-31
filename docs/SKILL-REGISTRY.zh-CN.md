---
translation_of: docs/SKILL-REGISTRY.md
language: zh-CN
translation_status: synced
---

# Skill 注册表与 Doctor

[English](SKILL-REGISTRY.md) | [简体中文](SKILL-REGISTRY.zh-CN.md)

> 一个解析器回答三个问题：存在什么、哪个副本优先、可以交给谁。路由器从不执行 Skill。

## 入口

`scripts/skill_route.py` 是唯一的解析器。它只依赖标准库，只读取 front matter 与已声明数据，不启动子进程，不发起网络请求。

| 命令 | 回答 |
|---|---|
| `python scripts/skill_route.py --sources` | 每个已声明的目录根、其权利姿态、是否存在 |
| `python scripts/skill_route.py --list` | 去重后的全部 Skill |
| `python scripts/skill_route.py --match "<交付物>"` | 排序后的候选 |
| `python scripts/skill_route.py --resolve <名称>` | 全部精确副本，或能力判定结果 |
| `python scripts/skill_route.py --capabilities` | 每个已声明能力及其判定 |
| `python scripts/skill_route.py --doctor` | 目录根、重名、权限声明、权利与越界路径 |

加 `--json` 可获得机器可读记录。`--resolve` 接受 `--account`、`--pipeline`、`--stage` 以限定能力解析范围。

## 三个不可混同的问题

| 问题 | 层次 | 由谁回答 |
|---|---|---|
| 本机存在什么？ | 发现 | `skill_route.py --list/--sources/--match` |
| 可以交给适配器吗？ | 解析 | `skill_route.py --resolve`，对照 `runtime/skill-registry.json` |
| 真的可以执行吗？ | 执行 | 适配器、运行时锁校验器与 M5 门禁 |

仅被发现绝不等于可执行。注册表里的声明同样不授予执行权：路由器的判定是 `RESOLVABLE`，返回记录永远带 `execution_authorized: false`。

有两个字段容易被误读，因此按语义命名：

- `provider.path_permitted` 表示该能力的 provider 路径被声明的策略允许。刻意不叫 `authorized`，因为那个词会被读成调用方已获执行授权。
- `accounts: ["*"]` 是路由通配符：匹配任意请求的账号，不是在该账号上、也不是跨账号执行的许可。

## 目录根

| 优先级 | 目录根 | 轨道 | 权利姿态 |
|---:|---|---|---|
| 1 | `.runtime/easel/skills/openclaw` | 固定版本 Easel 运行时 | external-pinned |
| 2 | `Easel/skills/openclaw` | 工作用 Easel 检出 | external-checkout |
| 3 | `vendor/gzh-thinktank/gzh_未来智能/skills` | 本地 vendor 的公众号轨 | unverified-vendor |
| — | `~/.agents/skills` | 共享库，单独解析 | 由操作者掌控 |

同名出现在多个根时只索引一次，取最早的根；后出现的副本作为 `shadowed` 报告，`--doctor` 统计每一处冲突。

`vendor/` 已被 gitignore。第三方 vendor 材料是本地操作资源，不是再分发授权，不得进入公开仓库。

## 已声明能力

`runtime/skill-registry.json`（schema `contentops.skill-registry/v1`）是一张指针表。每个条目记录：

| 字段 | 含义 |
|---|---|
| `id`、`name` | `--resolve` 精确匹配的标识 |
| `discovery` | Skill 目录应在何处（`shared` 或 `catalog`） |
| `source` | 发布方、上游包、版本、来源 commit |
| `canonical_path` | 拥有该集成的仓库代码 |
| `license` | 已声明的许可证状态与 SPDX id；从不是权利清零 |
| `rights` | 验证状态、范围与证据 |
| `accounts`、`pipelines`、`stages` | 该能力的服务范围；`accounts: ["*"]` 仅表示路由匹配任意账号 |
| `contract` | 输入、输出与回执 schema |
| `provider` | `path_permitted` 以及联网、付费、跨项目复用开关；其中任何一个都不是执行授权 |
| `runtime` | 依赖、已批准基线、锁环境变量、校验器 |
| `verification` | 状态、范围与证据 |
| `execution` | 适配器与 M5 阶段；`authorizes_execution: false` |

未声明的轨道被刻意排除。解析它们返回 `UNKNOWN_SKILL` —— 这是诚实答案，不是需要掩盖的缺口。

## 解析规则

| 条件 | 原因码 | 判定 |
|---|---|---|
| 没有任何声明精确匹配该名称 | `UNKNOWN_SKILL` | BLOCKED |
| 多个声明匹配 | `DUPLICATE_AMBIGUITY` | BLOCKED |
| 请求的 account/pipeline/stage 未声明 | `OUT_OF_SCOPE` | BLOCKED |
| 权利未验证，或许可证受限 | `UNVERIFIED_RIGHTS` | BLOCKED |
| provider 路径未被允许，或声明了联网/付费/复用 | `UNAUTHORIZED_PROVIDER` | BLOCKED |
| Skill 目录未安装 | `SKILL_NOT_INSTALLED` | BLOCKED |
| 已批准基线或运行时锁缺失 | `MISSING_RUNTIME` | BLOCKED |
| 唯一匹配、权利已验证、provider 路径已允许、运行时就绪 | `RESOLVABLE` | RESOLVABLE |

顺序是刻意的：歧义、范围、权利与 provider 先于运行时判定，因此一个被阻断的能力不会仅仅因为运行时恰好装着就显得可运行。Skill front matter 中的权限字段只被记录，从不被当作授权。

## media-use

| 字段 | 值 |
|---|---|
| id | `media-use` |
| 来源 | `hyperframes@0.8.222`，commit `f2358315e59731833334c5d881a7fb5543c22a97` |
| 规范路径 | `src/contentops/media/media_use_adapter.py` |
| 范围 | accounts `*`，pipeline `M5`，stage `media_use` |
| 运行时 | 已批准基线 `runtime/media-use-runtime-baseline.json`，锁环境变量 `CONTENTOPS_MEDIA_USE_RUNTIME_LOCK` |
| 验证 | `VERIFIED`，离线 local-only，集成验收 |
| 证据 | `reports/audits/contentops-pr71-media-use-final-audit-2026-10-31.md` |

该注册复用已合并的适配器、运行时基线、锁校验器与 M5 `media_use` 阶段。不新增第二套 Manifest，也不改变已验收的 media-use 行为。交接仅作声明：

```
Skill Discovery -> Skill Resolution -> Permission Gate -> Existing Adapter -> M5
```

`scripts/m5_production.py` 不导入路由器。旧版 M5 在没有路由器时可独立运行，并由测试断言这一独立性。

## 轨道状态

| 轨道 | 状态 | 原因 |
|---|---|---|
| VIDEO（Easel） | 仅发现，直到本机存在目录根 | 公开仓库不含 vendor 内容 |
| GZH | BLOCKED | vendor 的第三方轨，权利未验证，不再分发 |
| X | BLOCKED | 平台轨未合并（`feat/47-x-platform-track`，PR #50） |
| XHS | BLOCKED | 迁移未合并且处于权利审查中；无目录根 |

## 边界

`--doctor` 报告结构、许可证、权限声明与越界路径。它不清理权利，不授予权限，也不授权执行。Issue #57 保持开启，直到执行授权成为一个独立的、经审查的决定。
