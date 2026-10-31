---
translation_of: docs/SKILL-REGISTRY.md
language: zh-CN
translation_status: synced
---

# Skill 注册表与体检

[English](SKILL-REGISTRY.md) | [简体中文](SKILL-REGISTRY.zh-CN.md)

> 一个解析器，回答三个问题：有什么、哪一份优先、它能访问到哪里。体检不执行 skill。

## 入口

`scripts/skill_route.py` 是唯一解析器。本次增加检查能力，不新建第二套目录或第二套
skill 生产引擎。

| 命令 | 回答 |
|---|---|
| `python scripts/skill_route.py --sources` | 每个声明的目录根，存在或缺失 |
| `python scripts/skill_route.py --list` | 去重后的全部 skill |
| `python scripts/skill_route.py --match "<交付物>"` | 排序后的候选 |
| `python scripts/skill_route.py --resolve <name>` | 该名称的每一份副本，包括被遮蔽的 |
| `python scripts/skill_route.py --doctor` | 目录根、重名、权限声明、越界路径 |

任何命令加 `--json` 输出机器可读记录。

## 目录根

| 优先级 | 根 | 轨道 |
|---:|---|---|
| 1 | `.runtime/easel/skills/openclaw` | 固定的 Easel 运行时 |
| 2 | `Easel/skills/openclaw` | 工作中的 Easel checkout |
| 3 | `vendor/gzh-thinktank/gzh_未来智能/skills` | vendored 公众号 |
| — | `~/.agents/skills` | 共享库，单独解析 |

同名 skill 只在最早出现的根里索引一次，后面的记为 `shadowed`；`--doctor` 会统计所有
冲突。

小红书 skill 库在当前分支**不是**目录根。它属于未合并的迁移，正在 #56/#51 做权限审查。

## 体检字段

| 字段 | 含义 |
|---|---|
| `roots[].exists` / `skills` | 每个声明根是否存在、有多少 `SKILL.md` |
| `shared.exists` / `skills` | 共享库是否存在 |
| `duplicates` | 有多份副本的名称及所在轨道 |
| `missing_description` / `missing_name` | front matter 缺失 |
| `permission_declarations` | 多少 skill 声明了 `allowed-tools`、`permissions`、`tools` 或 `requires` |
| `unsafe_paths` | 目录 skill 解析后离开 checkout 与声明根 |
| `dangling_links` | 共享库链接的目标不存在 |

只有“完全没有 skill”或“目录路径越界”才使 `ok=false`。重名是警告：优先级已经选定一份，
冲突被报告出来即可。

## 当前快照

审计主机（2026-10-31），缺少固定 Easel 运行时、共享库存在：

```text
gzh              ok       40 skills
shared           ok      225 skills
total                    265
duplicates                16
permissions               15/265 声明权限字段
unsafe paths               0
dangling links             0
OK
```

这些是主机相关证据，不是永久计数。没有 `.runtime` 或共享库的干净 checkout 会把对应根
报告为 `absent`；只要 vendored 公众号目录存在，仍然通过。

## 边界

- 体检不安装、升级、执行或沙箱化 skill。
- 声明权限字段是审查信号，不是授权系统。
- 平台专有 skill 不会因为解析器看得见就适用于另一个平台。
- 权限不明或已归档的 skill 不得被默认调度。
