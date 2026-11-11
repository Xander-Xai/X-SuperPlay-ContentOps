---
translation_of: docs/DOC-SYNC.md
language: zh-CN
translation_status: synced
---

# 文档同步

[English](DOC-SYNC.md) | [简体中文](DOC-SYNC.zh-CN.md)

> 最后验证：2026-11-12，`main` 的 `c1da6dd`。

> 本仓库如何防止文档说谎。规则是机械的，不是口号：每份被跟踪的文档都写明它是在哪一天
> 对着哪个提交核验的，而一旦它描述的代码在那之后发生变更，CI 就会失败。

## 为什么需要这个机制

文档会悄悄腐烂。状态表继续描述上个月的架构，没有任何东西会崩，于是这份过期文档活过了
所有测试和所有评审。2026-11-12 的同步发现：README 仍把公众号和小红书写成"仅校验、
没有交付层"，而 `video_deliver.py` 与 `platform_delivery.py` 已经在 `main` 上好几天了。
没有检查失败。读者只会相信那份旧页面。

"保持文档最新"这句话不是机制。**一个日期 + 一个会失败的检查**才是。

## 契约

每份被跟踪的文档在开头写一行验证声明：

```markdown
> 最后验证：2026-11-12，`main` 的 `c1da6dd`。
```

检查器接受以下形式（中英皆可）：

| 形式 | 示例 |
|---|---|
| `Last verified:` / `最后验证：` | `> 最后验证：2026-11-12 …` |
| `Status verified:` / `状态验证：` | `> 状态验证：2026-11-12，main` |
| `Last updated:` / `最后更新：` | `> 最后更新：2026-11-12` |
| `Last reviewed:` / `最后复核：` | `> 最后复核：2026-11-12` |
| `Last regenerated …:` | `> 最后按注册表重生成：2026-11-12` |

这一行的含义是：**本文件中的事实，是在这一天、对着这个提交的代码核验过的。**
它不是构建戳，也不是"碰过文件"的计数。不看 diff 就改日期，是唯一能让这套机制失效的动作。

## 跟踪范围

权威定义在 [`config/docs/doc-freshness.json`](../config/docs/doc-freshness.json)；
本节只解释结构，不复制其中的路径。→ [英文版](DOC-SYNC.md)

| 文档 | 覆盖内容 |
|---|---|
| `README.md` / `README.en.md` | 仓库状态表、入口命令 |
| `docs/CURRENT-STATE.md` | 当前跑什么、带日期的 Git 快照 |
| `docs/PLATFORM-INTEGRATION-STATUS.md` | 注册表记录、各平台阻断原因 |
| `docs/DEVELOPMENT-PLAN.md` | 里程碑状态与退出标准 |
| `docs/TEST-PLAN.md` | 套件清单与 CI 接线 |
| `docs/RUNBOOK.md` | 可执行命令 |
| `docs/ARCHITECTURE.md` | 边界、组件地图、规则 |
| `docs/PRD.md` | 功能需求状态 |
| `docs/QUALITY-STANDARD.md` | 门禁定义 |
| `docs/ASR-BACKCHECK.md` | 旁白 ASR 门禁 |
| `docs/DOC-SYNC.md` | 本机制自身 |

豁免项在配置里写明理由：ADR（决策记录不可改，改动等于新 ADR）、带日期的审计快照、
术语表，以及 `docs/INDEX.md`（纯导航，索引覆盖由
`check_repo_policy.check_index_tracking` 负责）。

新增一份 Tier-1 文档，必须在同一次变更里为它分类；检查器会拒绝未分类的 Tier-1 文档。

## 触发条件

出现以下任一情况时执行同步：

1. 合入 `main` 的变更触及某份跟踪文档映射的代码路径。
2. 某能力、平台记录、门禁或回执的状态发生变化。
3. Tier-1 文档新增、改名或删除。
4. ADR 被接受、被取代，或被代码推翻。
5. 供应商事实变化（模型 id、端点、配额、固定版本）。

## 执行步骤

1. **读 diff，不读结论。** `git log --oneline <文档日期>..HEAD -- <映射路径>`，
   再对有意义的提交执行 `git show --stat`。
2. **远端事实必须查远端。** 分支、PR、issue、tag 与保护规则用 `gh` 查，不能用本地锁
   或上一份快照。本地检查只能证明内部一致。
3. **改事实。** 不适用的行直接删掉，不要绕着解释；一张短的、真实的表胜过一张长的、
   到处打补丁的表。
4. **主文档和镜像在同一次变更里改日期。** 检查器会在两份日期不一致时失败，
   半更新的一对发不出去。
5. **跑门禁：**
   ```bash
   python scripts/check_doc_freshness.py
   python scripts/check_i18n.py
   python scripts/check_docs.py
   python scripts/check_governance_ledger.py
   ```
6. **写明证据来源**（PR 号、回执路径、提交、URL）。没有指针的断言，就是下一行过期内容。
7. **走 PR 合入。** `main` 受保护，不存在直接推送。

## 诚实规则

- **运行时现实高于文档。** 回执 > 当前代码 > 机器可读锁/配置 > 当前 ADR >
  CURRENT-STATE > RUNBOOK > 旧计划。
- **只有回执才能提升状态。** 代码存在不抬升任何东西：注册表记录不动、
  `production_ready` 不翻转、不暗示任何发布。
- **宁可写"未验证"，也不要猜。** 没跑过的路径就写没跑过，哪怕代码看起来已经完成。
- **降级要记录，不要抹平。** 回退与跳过（`SKIPPED`、`HOST_BLOCKED`、`NOT_RUN`）
  在文档里和在回执里必须一致。
- **日期本身也是断言。** 比它描述的代码更旧的验证日期，就是一条失败的断言，
  不管有没有人读到。

## 机器校验

| 命令 | 捕获什么 |
|---|---|
| `python scripts/check_doc_freshness.py` | 映射代码在文档日期之后有提交；中英成对日期不一致；日期在未来；Tier-1 文档未分类 |
| `python scripts/check_i18n.py` | 缺镜像、缺 front matter、语言切换单向或断链、重复的中文 README |
| `python scripts/check_docs.py` | 内部链接断裂、必备文档缺失、固定版本引用过时、密钥 |
| `python scripts/check_governance_ledger.py` | CURRENT-STATE 中英与注册表的日期/SHA 漂移（离线） |

`check_doc_freshness.py` 接入 `dev_check.py` 与 CI 的 `Repo policy checks` 任务。
它需要 git 历史，因此 CI 使用 `fetch-depth: 0` 检出。

本地排查可用只报告模式：

```bash
python scripts/check_doc_freshness.py --report-only
python scripts/check_doc_freshness.py --json
```

只报告模式永远不能替代 CI 门禁。没人修的过期文档，否则就是默认结果。

## 检查失败时

`STALE` 不是噪音，改日期也不是修复。必须显式选择其一：

- **更新文档。** 常规情况：读 diff，改正事实。
- **退役该断言。** 如果这一节已经不再描述系统，删掉它。
- **调整跟踪范围。** 如果该文档确实不依赖那条路径，改
  `config/docs/doc-freshness.json` 并在 PR 里写明理由。

绝不要为了让检查变绿而改日期。一条绿了但没人读过的 diff，比一条红的更糟 ——
它把谎言挪进了"机器已校验"的那一栏。

## 节奏

- **每次变更：** 上述门禁，作为 PR 的一部分。
- **每月：** 对着 GitHub 实时状态完整重读一遍 Tier-1 文档集 —— 2026-11-12 那一轮
  （issue、PR、分支、tag、保护规则、CI、套件数量）就是模板。
- **每季度：** 删除不再值得保留的文档。删除优先于扩展。
