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

### TrendRadar：真实部署，只读访问

TrendRadar 部署在本仓库之外，固定为 **v6.11.0**
（`D:\Software\sansan0\TrendRadar\v6.11.0`，克隆标签 `ceabb02`），并且关闭了
AI 分析、AI 翻译、通知和 HTML 报告，因此一次采集不花钱、不调用任何付费 API。
它写出 `output/news/YYYY-MM-DD.db` 与 `output/rss/YYYY-MM-DD.db`。

适配器是按一次真实采集产出的数据库重写的。上一版假设了并不存在的表名，
对每一个真实文件都会返回 `SOURCE_DATA_MALFORMED`——这正是 fixture 最容易长期掩盖的失败。
v6 文件的真实内容：

| 表 | 读取内容 |
|---|---|
| `news_items` | `title`、`platform_id`、`rank`、`url`、`created_at`、`first_crawl_time` |
| `platforms` | 平台显示名 |

两件对下游重要的事实：

- **TrendRadar 记录的是它第一次看到标题的时间，不是发布时间。** 适配器把它作为
  `published_at` 返回，并标注 `extra.published_at_source = "trendradar_crawl_time"`，
  任何下游都无法把它误当成文章自身的日期。
- **时间戳是本地时间（UTC+8）。** 官方 compose 使用 `TZ=Asia/Shanghai`；
  按 UTC 读取会把每一条都推到八小时之后。

最新一条记录超过 24 小时的数据库会被标记 `stale`，其条目以 `STALE_SOURCE` 被拒，
而不会当作新热点提供。文件通过 URI 以 `mode=ro` 打开，绝不会被写入。

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

```powershell
python scripts/content_route.py accounts
python scripts/content_route.py sources
python scripts/content_route.py start --account x-superplay-1024 --mode hotspot
python scripts/content_route.py start --account x-superplay-1024 --mode topic `
    --topic "如何使用 LangGraph 开发可靠的 Agent？"
python scripts/content_route.py candidates --account x-superplay-1024
python scripts/content_route.py select --candidate CAND-XXXX --by "Founder"
python scripts/content_route.py status --run RUN-XXXX
python scripts/content_route.py resume --run RUN-XXXX
python scripts/content_route.py approve --run RUN-XXXX --reviewer "Founder" --confirm `
    --project my-episode
python scripts/content_route.py verify --run RUN-XXXX
python scripts/brief_handoff.py projects/my-episode --dry-run
python scripts/router_observe.py --trendradar-db "D:\Software\sansan0\TrendRadar\v6.11.0\output\news\2026-10-30.db"
python scripts/router_observe.py --report --days 7
```

对真实 TrendRadar 库只需要给一次路径，之后也可以直接用环境变量：

```powershell
$env:TRENDRADAR_DB_PATH = "D:\Software\sansan0\TrendRadar\v6.11.0\output\news\2026-10-30.db"
python scripts/content_route.py start --account x-superplay-1024 --mode hotspot
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

## 失败有分类，也有预算

| 代码 | 含义 | 是否重试 |
|---|---|---|
| `SOURCE_RATE_LIMITED` | HTTP 429，服务要求等待 | 是，按 `Retry-After` |
| `SOURCE_UNAVAILABLE` | 5xx、连接中断、响应被截断 | 是，3 次 |
| `SOURCE_TIMEOUT` | 超时无响应 | 是，3 次 |
| `SOURCE_CREDENTIALS_REQUIRED` | 401/403，我们没有凭据，也不会伪造 | 否 |
| `SOURCE_DATA_MALFORMED` | 返回的结构与声明不符 | 否 |
| `SOURCE_CIRCUIT_OPEN` | 本进程内该源反复失败，熔断中 | 否，冷却后恢复 |
| `SOURCE_UNAVAILABLE_STATE` | 未部署或未配置 | 否 |

退避是指数加抖动、上限 8 秒。422 属于请求本身错误，绝不重试——上一轮 GitHub
查询就是因为它带的 `OR` 超过服务允许的数量而返回 422，现在按源在注册表里
声明 `max_query_terms` 截断。

采集器不会伪装浏览器身份去绕过限制：它发送
`Mozilla/5.0 (compatible; ContentOps/1.0)`，这是非浏览器代理表明身份的标准写法，
并且不持有、不复用、不伪造任何凭据。

## 审批与被审批的内容绑定

审批不是运行记录上的一个状态位。它记录谁批的、什么时候、是人还是验收脚本，
以及**被批 Brief 的摘要**——主题、候选、证据预测与 profile 版本。

摘要就是重点：

- 审批后被改过的 Brief 不再匹配，`content route verify --run <id>` 会给出
  `APPROVAL_STALE`，`materialize_project` 以 `APPROVAL_NOT_VALID` 拒绝；
- 把旧的已批包复制进另一个运行，不会把审批带过去；
- `approve` 没有 `--confirm` 就拒绝；`automation` 身份除非显式
  `--allow-automation`（只有验收脚本会传）否则拒绝。回执里写明是哪一种，
  自动审批不可能被人误当成人工审批。

审核人填的名字是声明，不是身份认证。仓库没有为它准备身份提供方，假装有会更糟：
记录能保证的是**这份内容**在**这个时间**由**声称叫这个名字的人**批准，并且这个声明
就写在它对应的摘要旁边。

## 交接给生产流水线

`scripts/brief_handoff.py` 是已批准工程与现有生产脚本之间的适配器。它在本机重新
校验审批摘要，遇到 `DEGRADED` 证据预测以 `EVIDENCE_REQUIRED` 拒绝，通过
`scripts/account_route.py` 解析账号流水线，并写出 `00_brief/handoff.json`。

它不写脚本，也不写分镜。对这样的工程运行真正的入口脚本会停在 copy review——
这正是正确答案：`scripts/audio_first_plan.py` 在合成任何旁白之前就以
`{"status":"BLOCKED","stage":"copy_review"}` 退出码 4 结束，因此交接证明了链路，
且一分钱不花。

## 连续一周的观察

`scripts/router_observe.py` 在 `.local/content-router/observation/daily.jsonl`
里每次每账号记录一行：每个来源是否应答、给了多少行、数据是否陈旧、账号过滤做了什么。
`--report --days 7` 打印每个来源的成功率与候选产出。

每天跑一次、连续七天；机制已经存在，也已记录一次运行。七天的数据并不存在，
本文档也不声称存在。

## 查询表达式不是定位

账号可以按适配器声明：自己已声明的词里，哪些值得拿去问这个来源，按什么顺序问。

```json
"query_expressions": {
  "github_search": {
    "why": "…",
    "terms": [{"term": "LangGraph", "language": "en", "from_keyword": "LangGraph"}]
  }
}
```

每个词都写着它渲染的是哪个关键词（`from_keyword`），而每个关键词本身在 DNA 里已有出处，
所以回到账号主写下的文本的链条没有断。表达式增加的是**查询**决策——把来源有限的
operator 预算花在哪些已声明词上——不是新的定位主张。`check_account_dna.py` 会让引用了
未声明关键词的词失败，所以臆造的检索词从这里也进不来。

2026-10-30 用 `scripts/router_query_experiment.py` 实测（同一时刻、各跑一次、仅 GitHub）：

| 账号 | 查询 | 返回 | 通过门禁 | 精确率 |
|---|---|---|---|---|
| future-intelligence | 表达式 | 30 | 17 | **0.567** |
| future-intelligence | 关键词推导 | 30 | 7 | 0.233 |
| 1024 | 表达式 | 30 | 4 | 0.133 |
| 1024 | 关键词推导 | 30 | 6 | 0.200 |

结论：future-intelligence 保留表达式，**1024 的表达式已移除**——它实测降低了那个账号的
精确率，保留只是为了对称而不是为了证据。1024 的问题不在查询：通用英文词会命中通过了
门禁的垃圾仓库；要修它就得改"什么算这个账号的内容"，那是账号所有者的决定。

## 按时间自动运行

`scripts/router_schedule.py` 一次跑一个采集周期：经 TrendRadar 自己的入口抓取、发现最新的
数据库、为两个账号采集、追加当天的观察记录、写回执。它是唯一无人值守运行的组件，能做什么由结构和测试共同约束
——它不能选题、不能批准 Brief、不能渲染或发布。

```powershell
python scripts\router_schedule.py run                 # 一个周期，含抓取
python scripts\router_schedule.py run --skip-crawl    # 只读已有数据
python scripts\router_schedule.py status              # 锁、最近的运行、漏跑
python scripts\router_schedule.py register            # 打印 schtasks 命令
```

它必须成立的四件事：

- **同一时间只跑一个。** 状态目录里的锁文件让第二个运行以 `ALREADY_RUNNING`（退出码 3）结束，
  而不是抓两次；超过三小时的锁视为已废弃。
- **用最新数据库，不用固定日期。** 它按文件名从新到旧读 `output/news/*.db`，当天文件被仍在写入的
  抓取锁住时回退到前一天。最新的 RSS 文件也会被记录，尽管路由器不读它。
- **过期是判断，不是意外。** 被选数据库的年龄写在回执里，超过 24h 标记 `stale`——这与适配器
  自己的 `STALE_SOURCE` 拒绝是两道独立的关。
- **漏跑可见。** `status` 用最后一次成功回执与预期间隔比较并说明；失败的运行也照样写回执，
  写明哪一步失败。

注册是单独的、刻意的步骤（`register --apply`），它会创建 Windows 计划任务、改变这台机器，
本仓库的任何东西都不会自动执行它。

## 一次审批证明了什么、没证明什么

三种东西很容易被混为一谈，这里分开写：

| 层级 | 是什么 | 我们有没有 |
|---|---|---|
| 操作者声明 | `--reviewer` 里打进去的名字 | 有；它是声明，不是身份 |
| 交互式确认 | 终端前的人传 `--confirm` | 有；它标记意图，不标记身份 |
| 经过身份认证的审批 | 与审批绑定的已验证身份 | **没有**——本仓库没有身份提供方 |

因此这套系统实际提供的保证是狭窄且写明的：

- **内容绑定**：审批记录的是被批那份 Brief 的摘要（主题、候选、证据预测、profile 版本）。
  其中任何一项变了，审批就失效（`APPROVAL_STALE`），也无法据此创建工程；
- **审计留痕**：谁声称、何时、是人还是验收运行，与你对应的摘要并列；
- **没有人能自动把内容送进生产**：`approve` 需要 `--confirm`，而 `automation` 身份除非在代码里
  显式允许**且**进程带 `CONTENTOPS_TEST_SANDBOX=1`，否则一律拒绝。这个环境标记刻意不是命令行
  开关：开关是工作流参数，而工作流参数会被任何编辑任务的人复制进生产。

它**不**提供：证明名字就是那个人、防住明知内容不好的操作者、防住能写状态目录的人。
那些需要身份提供方与可信主机，这里两者都没有。

## 命中关键词不等于有项目

对 GitHub 来说，账号主题之后还有第二个问题：链接背后有没有一个真实项目？
描述写着 `behaviour test: mint probe workflow host` 的仓库命中了账号的词，
却对观众毫无价值。

`contentops.hotspots.quality` 只回答这一个问题。它不是相关性评分——主题由
DNA 决定，它只决定"有没有项目"。

**任何单一弱信号都不足以定论。** Stars、新旧、描述里的一个词，各算一个信号，
拒绝需要**两个相互独立的**信号：

| 信号 | 它证明了什么 |
|---|---|
| `placeholder_name` | 仓库名字本身就是测试夹具（`test-repo`、`mint-probe`） |
| `placeholder_description` | 描述自己承认是测试 |
| `no_readme` | 没有任何文档说明它做什么 |
| `tiny_repository` | 低于体积下限，里面几乎没有代码 |
| `archived` | 已归档，不会再变 |
| `young_and_unproven` | 几天前创建且无 star——只是**一个**信号，不是判决 |

前两个信号能从榜单数据直接读出，因此"名字和描述都自称夹具"的仓库**不花任何 API
调用**就会被拒。其余信号需要实际检视，而**检视失败不等于拒绝**：条目以
`UNVERIFIED` 通过并附带原因。限流绝不能变成删候选。

阈值是数字不是偏见（`QualityPolicy`，可按次调整），每个判决都带走它依据的证据与
信号，审阅者可以在**证据层面**反驳，而不是靠信任。

这道门移除的是夹具。它**不会**移除"真实但不适合该账号"的项目——那是 DNA 的职责，
而且两种失败在候选池里长得很不一样：一个是垃圾，一个是诚实的不匹配。

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
