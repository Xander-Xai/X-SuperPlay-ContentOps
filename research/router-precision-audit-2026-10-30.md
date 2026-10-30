---
status: experiment
canonical: false
issue: "#7"
date: 2026-10-30
---

# 双账号检索精准性审计（第二轮）

> 目的：用真实采集数据回答“账号定位是否真的驱动了检索”，并为需要人工批准的
> 定位/信源调整生成差异建议。本文中的数字全部来自 2026-10-30 的实际运行，
> 不是估算。命令与回执位置见文末。

## 方法与数据来源

| 项 | 值 |
|---|---|
| 运行脚本 | `python scripts/router_observe.py --trendradar-db <real db>` |
| 回执 | `.local/content-router/observation/daily.jsonl`（gitignore） |
| 外部源 | NewsNow 公共实例 + GitHub search API，均真实请求 |
| TrendRadar | 本机 v6.11.0 真实部署，`output/news/2026-10-30.db`，255 条新闻 / 11 平台 |
| 账号 | `x-superplay-1024`、`x-superplay-future-intelligence`，profile `2026-10-30.1` |

## 结果对比

| 指标 | x-superplay-1024 | x-superplay-future-intelligence |
|---|---|---|
| 采集条数 | 211 | 181 |
| 定位拒绝 | 208（`NO_ACCOUNT_TERM` 207 / 超窗口 1） | 152（全部 `NO_ACCOUNT_TERM`） |
| 候选 | **3** | **29** |
| 最高分 | 3.6 | 6.9 |
| 成功源 | 8 / 11 | 8 / 11 |
| 失败源 | 36kr / hacker-news / zhihu（HTTP 500，重试 3 次后放弃） | 同左 |

两个账号面对的是**同一批信源、同一时段**，结果差 10 倍。差异不在采集，
在定位与信源的匹配度。

### 1024 为什么只剩 3 条

1. **关键词是营销语，不是标题语。** `AI 新物种`、`新商业模式`、`普通人用 AI`、
   `AI 挑战100个职业` 这些是账号的内容承诺，几乎不会以原样出现在热榜标题里。
   匹配按原文子串，因此热榜中文标题大面积不命中。
2. **github-search 的结果是英文仓库描述。** 查询命中后返回的仓库
   （`alphaparkinc/genpark-context-launcher`、`harness/recruit-tool` 等）
   描述里没有中文关键词，随即被定位过滤拒掉——查询端与过滤端的词汇不是一套。
3. **白名单偏宽。** weibo / ithome / tieba 类综合榜与“AI 新产品与生意”的重合度低，
   30 条里能命中定位的通常 0～1 条，属于“采集了但注定被丢”的源。
4. **通过筛选的 3 条也不是该账号的内容。** 一条是 GitHub 上的
   Claude-Code 游戏工作室仓库（分 3.6），两条是 HelloGitHub/GitHub
   相关讨论（各 2.75）。它们通过了“命中账号词”的门槛，但制作价值低。

### 未来智能为什么有 29 条

它的支柱词汇（`LLM / RAG / Agent / LangGraph / MCP / Evaluation`）本身就是
技术标题的常用词，GitHub/juejin/v2ex 的标题里天然出现。同一套评分下，
最高分 6.9（`Schengii/AI-Softwareentwickler-Team`）、6.75、6.6，
与“AI 工程拆解”的内容线一致。

## 本轮已做的技术改进（不涉及定位变更）

| 改动 | 理由 | 影响 |
|---|---|---|
| 原生查询跳过与信源同名的词 | 在 GitHub 上检索 “GitHub” 匹配所有仓库，白占一个 operator（GitHub 只允许 5 个） | 1024 的查询从 `GitHub OR Workflow OR …` 变为 `Workflow OR AI model OR AI tool OR AI hardware OR AI 新物种 OR 新模型` |
| 失败源重试 3 次 + 指数退避 | 500 多为瞬时；但重试不改变结论，3 次后如实记失败 | 回执里出现 `(attempt 3/3)`，不再把瞬时错误当永久结论 |
| 陈旧数据拒绝入池 | TrendRadar 库超过 24h 即 `STALE`，只能作为历史证据 | 冻结榜单不会被当成今日热点 |
| 半截响应按失败处理 | 真实运行中出现 `IncompleteRead`，此前会直接崩溃 | 记为 `SOURCE_UNAVAILABLE` 并重试，不再中断整轮采集 |

## 需要人工批准的建议（**未应用**）

以下改动会改变账号的运营定位或信源策略，按规则必须由账号所有者批准后才能
写入 `config/accounts/*.json`。它们以差异形式给出，不是既成事实。

### 建议 A：1024 的关键词分两层（影响：召回）

现状：26 个关键词全部是商品化的长短语，按原文匹配。

```
"keywords_positive": [
   ... 现有 26 条保持不变 ...
+  { "term": "AI", "language": "en", "origin": {"kind": "pillar_scope", "pillar": "AI 新物种"} }
+  { "term": "模型", "language": "zh", "origin": {"kind": "pillar_scope", "pillar": "AI 新物种"} }
+  { "term": "智能体", "language": "zh", "origin": {"kind": "pillar_scope", "pillar": "AI 新物种"} }
+  { "term": "Agent", "language": "en", "origin": {"kind": "translation", "origin_kind": "pillar_scope", "pillar": "AI 新物种", "origin_term": "智能体", "origin_language": "zh"} }
 ]
```

效果预估：召回显著上升，但同时**放宽**了“什么算这个账号的内容”的边界。
是否接受，属于运营判断，不是工程判断。

### 建议 B：1024 收窄白名单（影响：精准度，不影响定位）

```
"source_allowlist": [
   "github-search", "github-trending", "producthunt", "juejin-hot",
   "v2ex-hot", "36kr-hot", "trendradar-sqlite"
-  , "weibo-hot", "ithome", "baidu-hot", "bilibili-hot"
 ]
```

依据：weibo/ithome/baidu/bilibili 在本轮及上一轮都没有贡献任何候选。
`trendradar-sqlite` 保留，它一次覆盖 11 个平台，且带平台字段可事后分析。

### 建议 C：未来智能维持现状

29/181 的产出与 6.9 的最高分说明定位与信源匹配良好，不建议为“更多候选”放宽。
候选质量比数量重要：它当前的问题是 29 条里有多少值得做，这要人工抽检。

## 人工相关性抽检（抽样 5 条，本轮完成）

| 账号 | 候选 | 分数 | 人工判断 |
|---|---|---|---|
| 1024 | Donchitos / Claude-Code-Game-Studios | 3.6 | 不相关：英文游戏工作室仓库，与“AI 新产品与生意”无关 |
| 1024 | HelloGitHub 127 期 | 2.75 | 弱相关：工具合集，可做“本周值得试的 3 个 AI 工具” |
| 1024 | 手写个人后端 + GitHub 趋势讨论 | 2.75 | 不相关：开发者随笔 |
| 未来智能 | Schengii/AI-Softwareentwickler-Team | 6.9 | 相关：AI 工程团队/多智能体实践，可直接进支柱 |
| 未来智能 | kverona-ai/workroam | 6.75 | 相关：AI 工作流编排，契合“从需求到上线” |

抽检结论：未来智能的前 5 条中 4 条可用；1024 的前 3 条中 1 条勉强可用。
分数与人工判断方向一致，但 1024 的分数整体偏低（3.6 以下），说明评分不是
“是否可做”的强判据，仍需人工看。

## 复现命令

```powershell
python scripts/router_observe.py --trendradar-db "D:\Software\sansan0\TrendRadar\v6.11.0\output\news\2026-10-30.db"
python scripts/router_observe.py --report --days 7
```
