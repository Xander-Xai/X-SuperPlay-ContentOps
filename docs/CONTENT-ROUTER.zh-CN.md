---
translation_of: docs/CONTENT-ROUTER.md
language: zh-CN
translation_status: synced
---

# 内容路由器

[English](CONTENT-ROUTER.md) | [简体中文](CONTENT-ROUTER.zh-CN.md)

> 选题的统一入口：选账号、选路线，产出既有流水线可以直接接手的 Brief。

## 这是什么

这个仓库能做出片子，但答不上前置的两个问题：**这是为谁做的**，以及**这讲的是什么**。
答案原本散在两个互不相干的地方——一份没人要求过的热榜，和某个人的脑子——而两边都没有留下
"选题从哪来"的记录。下游因此分辨不出这两者，也就无法对其中任何一种施加约束。

内容路由器就是这两个答案与流水线之间的一层：

```
账号 ──▶ Account DNA ──▶ 路线 ──▶ 选题 ──▶ Content Brief ──▶ 既有流水线
          （账号定位）   （显式）  （人工选定）  （统一合约）      （保持不变）
```

两条路线从这里进入：

| 路线 | 选题来源 | 路由器做什么 |
|---|---|---|
| `HOTSPOT_DISCOVERY` | 由账号圈定的热榜 | 生成检索计划、采集、过滤、排序，然后**等待人工选择** |
| `USER_TOPIC` | 账号所有者本人 | 用账号定位核验主题、保留用户原话，然后**等待人工审核 Brief** |

两条路线产出同一个合约，也进入同一条流水线。视频生产引擎只有一个，不是两个。

## 路线绝不靠推断

`route_mode` 只能是 `HOTSPOT_DISCOVERY` 或 `USER_TOPIC`，由调用方明确指定。
不指定就返回 `ROUTE_SELECTION_REQUIRED`。路由器不会根据主题、平台或账号去猜——
默默去做一件和被要求的事不一样的工作，比直接拒绝更糟。

一次运行始终留在它自己的路线里。某个来源挂了，这次运行如实报告失败，
它不会绕道去找别的题。

## 由账号决定检索

Account DNA 在任何抓取**之前**就被读取，它的 `discovery` 块驱动整个采集过程：

| 字段 | 对检索的影响 |
|---|---|
| `keywords_positive` | 交给支持服务端查询的来源的检索词，也是候选必须命中的词 |
| `keywords_negative` | 在人工看到之前就淘汰候选的词 |
| `source_allowlist` | 唯一会被访问的来源。不在名单上的来源不是"抓了再丢弃"，而是**根本不访问** |
| `source_blocklist` | 账号拒绝的来源；黑名单优先于白名单 |
| `content_pillars` | 候选归属哪个内容支柱、落在哪个货架 |
| `not_doing` / `excluded` | 账号明确不做的内容 |
| `match_weights` | 排序权重，按百分比计，合计 100 |
| `approval_policy` | 谁来审核，以及"必须有人参与"这件事本身 |

### 反编造保证

每个关键词都带一个 `origin`，指明它取自 DNA 的哪个字段。
`scripts/check_account_dna.py` 会在同一份 DNA 里解析这条引用，
凡是 origin 无法解析的关键词，**DNA 检查直接失败**。
不存在任何一条路径，能让一个无出处的词进入检索。

英文关键词可以声明为某个中文词的 `translation`——翻译是把已有的词换一种语言表达，
而不是新增一个定位主张——但它的中文出处同样必须能解析。

```json
{ "term": "open source", "language": "en",
  "origin": { "kind": "translation", "origin_kind": "pillar_scope",
              "pillar": "AI 新物种", "origin_term": "新 GitHub 项目" } }
```

**没有** `discovery` 块的账号，热点检索会被 `ACCOUNT_DNA_MISSING` 拒绝。
它不会拿到默认值，也不会被猜测。指定主题路线对它仍然可用，
因为那条路线需要的是定位，而不是检索词。

## 来源会说明自己能做什么

热榜服务和搜索 API 不是一回事，注册表不假装它们是一回事。

| `query_mode` | 含义 |
|---|---|
| `NATIVE_SEARCH` | 服务接受查询并返回该查询的结果。本目录中真正的例子是 GitHub 搜索 API：账号的词直接进入请求。这些词是 **OR** 而不是 AND——GitHub 对空格分隔的词取交集，若一次问遍账号所有词，等于要求一个仓库同时提到每一个词，结果只会是空。确切查询写进计划，因此读者能看到到底问了什么 |
| `LIST_ONLY` | 服务发布一个预先排好的榜单。账号的词无法收窄它，只能在抓取**之后本地过滤**。这是"过滤后的榜单"，不是"搜索" |

检索计划会为它列出的每一个来源写明是哪一种。
读一份热门榜单并留下合适的部分，是一种正当做法；把它称作搜索，不是。

### 失败会被指名

失败的来源被记录并跳过，其余来源继续。

| 代码 | 含义 |
|---|---|
| `SOURCE_UNAVAILABLE` | 无法访问该来源 |
| `SOURCE_TIMEOUT` | 未在时限内响应 |
| `SOURCE_RATE_LIMITED` | 对方要求降低频率 |
| `SOURCE_DATA_MALFORMED` | 返回了无法解析的内容 |
| `SOURCE_UNAVAILABLE_STATE` | 本地 TrendRadar 数据库不存在或已关闭 |
| `SOURCE_CREDENTIALS_REQUIRED` | 需要本采集器并不持有的凭据 |

这里的适配器都不需要凭据。失败的来源绝不会变成一份"看起来像结果"的空候选列表。

### TrendRadar

TrendRadar 部署在本仓库之外。它通过只读 SQLite URI 访问，绝不会被写入。
四种情况被分别指名处理：文件不存在、文件被锁、上游 Schema 漂移
（表里已经没有 `title` 列，于是这些行根本不被读取）、以及重复行
（被丢弃，避免同一个故事变成两个信号）。

## 排序是账号自己的

七个分量，各打 0–10 分，权重由账号自己给，每个分量都带一句解释：

| 分量 | 权重 | 度量什么 |
|---|---|---|
| `profile_relevance` | 30 | 命中了账号多少个声明词 |
| `evidence_availability` | 20 | 是否指向账号能打开并实测的东西 |
| `freshness` | 15 | 相对本次时间窗有多新 |
| `audience_value` | 15 | 是否点名了账号的核心受众 |
| `cross_source_signal` | 10 | 有多少个**不同**来源同时出现 |
| `originality_potential` | 5 | 是否点出了账号能实测、能定价、能复现的角度 |
| `non_repetition` | 5 | 这个账号是否已经见过它 |

榜单自身的名次从不作为排序依据。榜单名次说的是"在那份榜单的读者里有多热"，
这和"对这个账号的读者有多贴切"是两个问题。

**不同平台的计数器绝不相加。** 一个平台的浏览量和另一个平台的热度指数不是同一个量纲。
它们被记录在候选上，标记为 `metrics_comparable: false`，并且不进入评分。
唯一的跨源信号是"不同来源的数量"，这是关于覆盖范围的事实，而不是不可比的量纲之间的比较。

**来源没有给出时间的条目不会被丢掉。** 新鲜度时间窗只能排除它能判断时间的东西。
这样的条目会被保留，在新鲜度上得 0 分，并在记录里写明"无法确定新鲜度"——
于是它是明显更弱的，而不是被悄悄保留或悄悄消失。

## 统一合约

两条路线都产出 `contentops.content-intent/v1`：

```json
{
  "schema": "contentops.content-intent/v1",
  "account_id": "x-superplay-1024",
  "account_profile_version": "2026-10-30.1",
  "route_mode": "USER_TOPIC",
  "topic": "…",
  "content_angle": null,
  "source_artifact_refs": [],
  "evidence_status": "verification_required",
  "approval_status": "pending",
  "target_pipeline": "VIDEO",
  "brief_status": "draft",
  "route_context": { "…": "两条路线键完全相同" }
}
```

所有与路线相关的内容都放在 `route_context` 下，两种模式下键完全相同。
下游读取 `route_context.candidate_id` 时，不需要关心它是 `None`
是因为用户自己写了主题，还是因为有人从候选里选了一条。
这正是下游代码里不会出现 `if route == HOTSPOT` 的原因。

磁盘上的 Brief 包是 `00_brief/brief.json`，其中带两份**仓库既有**合约的文档：

- `candidate` — `contentops.content-candidate/v1`，按既有选题合约的形状给出打分；
- `forecast` — `contentops.evidence-feasibility/v1`，写明需要哪些采集证据、
  谁来产出、现在是否可得、拿不到时怎么办。

两者都用仓库既有的校验器在校验通过后才写盘。
过不了这些合约的 Brief 不会被写出来。

## 状态机

一台状态机，位于 `contentops.routing.models`，没有强制路径。

```
ACCOUNT_REQUIRED ─┬─▶ ACCOUNT_DNA_MISSING ─▶ BLOCKED
                  └─▶ ROUTE_SELECTION_REQUIRED
                         ├─▶ SEARCH_PLAN_READY ─▶ CANDIDATES_READY ─▶ TOPIC_SELECTED
                         └─▶ INPUT_REQUIRED ─┬─▶ OUT_OF_PROFILE_REVIEW_REQUIRED
                                            └─▶ EVIDENCE_REQUIRED ─▶ BRIEF_READY
                                                                        │
        APPROVED_FOR_PRODUCTION ◀── AWAITING_HUMAN_APPROVAL ◀──────────┘
```

其中四个状态是整套设计的重点：

- **`CANDIDATES_READY` 无法变成 Brief。** 它到 `BRIEF_READY` 没有边。
  选题由人决定，否则不做。
- **`OUT_OF_PROFILE_REVIEW_REQUIRED`** 会拦下账号自身声明覆盖不到的用户主题。
  所有者可以改主题，也可以明确批准例外；例外会被记录是谁、为什么。
- **`AWAITING_HUMAN_APPROVAL`** 是每份 Brief 的等待点。
- **`BLOCKED` 是终态。** 被拦下的运行就是"是什么拦住了它"的记录。

### 状态不代表什么

Brief 里写着 `evidence_status: verified`，指的是证据**路径**已被记录。
它不代表其中的事实为真，也不代表视频好看。下游那道复制评审关卡保持原样，
仍然是脚本与渲染之间唯一的门。这里是**另一道处于不同位置的关卡**——
生产之前，而不是渲染之前——它本身不授予任何发布或付费媒体权限。

## 命令

```bash
python scripts/content_route.py accounts
python scripts/content_route.py sources
python scripts/content_route.py start --account x-superplay-1024 --mode hotspot
python scripts/content_route.py start --account x-superplay-1024 --mode topic \
    --topic "如何使用 LangGraph 开发可靠的 Agent？"
python scripts/content_route.py candidates --account x-superplay-1024
python scripts/content_route.py select --candidate CAND-XXXX --by "Founder"
python scripts/content_route.py status --run RUN-XXXX
python scripts/content_route.py resume --run RUN-XXXX
python scripts/content_route.py approve --run RUN-XXXX --reviewer "Founder" --confirm \
    --project my-episode
```

`accounts` 列出各账号以及是否可路由；`sources` 列出来源目录，以及每个来源实际能做什么——
账号的白名单正是从这里挑的。

任何命令加 `--json` 都会输出同样的 JSON 结果。
`approve --project` 用仓库自己的脚手架（`scripts/new_project.py`）创建项目，
并把 Brief 包放进去，于是这一集从和其他每一集相同的地方开始。

### 一次热点运行的实际过程

```
选择账号：AI 技术视频账号 (x-superplay-1024)
选择模式：热点发现

已加载账号定位版本 2026-10-30.1
已生成精准检索计划：9 个来源，0 个来源被拒绝，1 个来源接受服务端查询
采集与筛选完成：抓取 18 条，拒绝 9 条，候选 7 条

候选选题：
1. 用 LangGraph 做多步骤工作流，失败重试怎么设计
2. langchain-ai/langgraph
…

请选择一个候选：content route select --candidate CAND-XXXX --by "Founder"
```

### 一次指定主题运行的实际过程

```
选择账号：AI 技术视频账号 (x-superplay-future-intelligence)
选择模式：指定主题

输入主题：如何使用 LangGraph 开发可靠的 Agent？
进行账号定位检查…ALIGNED（匹配账号声明词 3 个）
生成 Content Brief…等待人工审核。

content route approve --run RUN-XXXX --reviewer "Founder" --confirm
```

## 状态存在哪里

候选池和运行轨迹按账号存进 SQLite，位于 `.local/content-router/`——
仓库本来就已经忽略这个目录，因为另一个账号的候选标题属于运行时状态，不是源码。
`CONTENTOPS_ROUTER_HOME` 可以把整个目录搬走。

候选的每一次读写都带上账号 id。两个账号共用一个数据库文件，别的什么都不共用：
候选 id 由账号和标题共同派生，所以同一个故事在两个账号下会得到两个候选，
谁也选不了对方的。

运行记录保留本次运行所依据的定位版本。账号定位变更后，
新运行使用新版本，旧运行保留它当时实际使用的版本。

## 这个模块不做什么

- 它不替你选选题。它只提出，由人决定。
- 它不发布，也不触及媒体生成器。路由器产出 Brief 就停下。
- 它不在只提供榜单的服务上宣称原生全文检索。每个来源都写明自己是哪一种。
- 它不把不同平台的热度数字相加。
- 它不编造账号定位。没有 discovery 块的账号拿到的是 `ACCOUNT_DNA_MISSING`，不是默认值。
- 它不切换一次运行的路线。来源挂了是报告失败的理由，不是绕道做别的事的理由。

## 代码在哪里

| 路径 | 负责什么 |
|---|---|
| `src/contentops/routing/models.py` | 统一合约与状态机 |
| `src/contentops/routing/account_profile.py` | 解析 DNA，以及出处校验 |
| `src/contentops/routing/hotspot_route.py` | 路线 A：计划、采集、过滤、排序 |
| `src/contentops/routing/user_topic_route.py` | 路线 B：用户主题及其定位契合度 |
| `src/contentops/routing/brief.py` | Brief 包及其引用的两份既有合约 |
| `src/contentops/routing/router.py` | 两条路线共同经过的入口 |
| `src/contentops/hotspots/source_registry.py` | 来源目录及其能力声明 |
| `src/contentops/hotspots/query_planner.py` | 写下来的检索计划 |
| `src/contentops/hotspots/adapters.py` | 读取各个来源，并按名失败 |
| `src/contentops/hotspots/ranking.py` | 按账号权重计算的评分 |
| `src/contentops/hotspots/dedup.py` | 同一个故事出现在两处时合并 |
| `src/contentops/hotspots/storage.py` | 按账号隔离的候选池与轨迹 |
| `scripts/content_route.py` | 命令行 |

测试：`tests/test_content_router.py`、`tests/test_hotspot_sources.py`、
`tests/test_account_discovery.py`。三者全部离线运行。

验证了什么、何时验证，见 [CURRENT-STATE.md](CURRENT-STATE.zh-CN.md)；
命令在整体语境下的用法见 [RUNBOOK.md](RUNBOOK.zh-CN.md)。
