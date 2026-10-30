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
   "v2ex-hot", "36kr-hot", "hacker-news", "zhihu-hot", "trendradar-sqlite"
-  , "weibo-hot", "ithome"
 ]
```

依据：`weibo-hot` 与 `ithome` 在最近两次采集里都返回了数据（30 与 60 条），
但对 1024 的候选贡献为 **0**。它们仍在白名单里是因为任务要求先观察两周再决定；
两周后若仍为 0，再提移除。

更正：上一轮建议里写的 `baidu-hot` / `bilibili-hot` **本来就在黑名单里**
（`source_blocklist`），不在白名单，所以那条建议是错的，这里撤回。

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

---

# 第三轮追加：候选精确率抽检（2026-10-30 晚）

## 方法

对每个账号当次采集的候选池逐条人工判读（依据该账号 `positioning` 与三根支柱），
统计**精确率 = 判定相关或可用的候选 / 抽检候选数**，而不仅是候选数量。
判读依据是候选的 GitHub 仓库描述、热榜标题与来源，不额外抓取正文。

## x-superplay-1024（定位：亲自测试 AI 新能力、新玩法、新生意）

| # | 候选 | 分数 | 判读 |
|---|---|---|---|
| 1 | AGvin/ai-lab — "Practical notes, setups, benchmarks, and workflows for AI models" | 5.85 | 相关：正好是"亲自测试"的形态 |
| 2 | cedricvogel92/aicalc-web-workflow-tools — token 计数/定价小工具 | 5.10 | 边缘：可归入"AI 工具"，但非新物种 |
| 3 | halfsend-06/test-repo-02-mint-host — "behaviour test: mint probe workflow host" | 5.05 | **不相关：测试垃圾仓库** |
| 4 | halfsend-04/test-repo-10-mint-host | 5.05 | **不相关：测试垃圾仓库** |
| 5 | halfsend-06/test-repo-07-mint-host | 5.05 | **不相关：测试垃圾仓库** |
| 6 | kabir1921/kabir1921.github.io — 个人作品集站点 | 5.05 | **不相关** |
| 7 | Donchitos/Claude-Code-Game-Studios — 把 Claude Code 变成游戏工作室 | 3.60 | 边缘：属于"新玩法"演示 |
| 8 | HelloGitHub 127 期 | 2.75 | 边缘：可支撑"本周值得试的工具"选题 |

**precision@8 = 1/8 = 12.5%**（宽口径含边缘 = 4/8 = 50%）。

关键发现：4 条垃圾/无关项里有 3 条是 `halfsend-*` 的 mint 探测仓库，描述里含 "workflow"，
通过了"命中账号词"的门槛。**这不是查询问题，是匹配语义问题**——修它要改账号的否定词或
匹配规则，属于定位变更，已列为待批准建议 D（见下）。

## x-superplay-future-intelligence（定位：把 AI 做成真正能运行、上线和解决问题的项目）

| # | 候选 | 分数 | 判读 |
|---|---|---|---|
| 1 | IBM/mcp-context-forge — MCP/A2A/REST 的 AI 网关与注册中心 | 7.50 | 相关 |
| 2 | elcoosp/kod — 终端内本地优先的 AI 编码 agent（Rust） | 7.50 | 相关 |
| 3 | Emmad-Ud-Din/rag-chatbot — RAG + LLM-judge 评测 + 限流 | 6.90 | 相关（工程细节齐全） |
| 4 | dhandan/football-copilot — 本地 LLM + 工具调用 + DuckDB 端到端 | 6.75 | 相关 |
| 5 | MaxXSammy/procurement-rag-agent — 采购选型的 RAG agent | 6.75 | 相关（德文项目，工程可拆） |
| 6 | tawfeeqimtiyaz/Search-Engine-LLM — 多源检索 chat agent | 6.75 | 相关（完整但玩具级） |
| 7 | raullenchai/Rapid-MLX — Apple Silicon 上的推理服务 | 6.75 | 相关（部署/上线） |
| 8 | venkateshyadagiri468/V18.AI — ReAct 多步 agent | 6.60 | 相关 |
| 9 | egtimer/agentic-sql-assistant — LangGraph + Ollama + Qdrant | 6.60 | 相关 |
| 10 | ACGlove/scout — 从零实现 LLM Agent 框架 | 6.15 | 相关（"拆解"向） |
| 11 | Shradhhameduri/agentdesk — 工具调用客服 agent + 人工审批 | 6.00 | 相关 |
| 12 | scalekit-inc/scalekit-sdk-java — 厂商 SDK | 6.00 | 弱：偏营销 |

**precision@12 = 11/12 = 91.7%**（宽口径含 1 条弱相关 = 12/12）。

## 前后对比（查询表达式的影响）

| 账号 | 变更前 precision | 变更后 precision | 说明 |
|---|---|---|---|
| future-intelligence | 0.233（关键词推导查询） | **0.567**（表达式查询，仅 GitHub） | 保留表达式 |
| 1024 | 0.200（关键词推导查询） | 0.133（表达式）→ **未采用** | 表达式实测更差，已从 DNA 移除 |

注意：上表是**来源端（GitHub）精确率**，下表是**候选端精确率**，两者不可混为一谈：

| 账号 | 来源端 precision（GitHub） | 候选端 precision（人工抽检） | 候选数 |
|---|---|---|---|
| 1024 | 0.200 | 0.125（@8） | 3–6（波动） |
| future-intelligence | 0.567 | 0.917（@12） | 32–34 |

## 新增建议 D（需要人工批准，未应用）

```
1024 discovery.keywords_negative 追加：
  { "term": "test-repo",   "language": "en", "origin": {"kind": "not_doing", "index": 2} }
  { "term": "mint probe",  "language": "en", "origin": {"kind": "not_doing", "index": 2} }
```

依据：本轮 4 条垃圾候选中 3 条来自这两个描述片段。但这仍属"什么算这个账号的内容"，
需要账号所有者批准；未批准前宁可有这 3 条噪音，也不擅自扩大排除范围。

## 四个零产出源的处理

任务要求"暂不永久移除，观察后再形成建议"。按本轮实测把两类原因分开：

| 来源 | 状态 | 原因 | 处理 |
|---|---|---|---|
| 36kr-hot / hacker-news / zhihu-hot | 连续 2 次 `SOURCE_UNAVAILABLE`（HTTP 500，重试 3 次） | **上游故障**，不是账号不匹配 | 保留；上游恢复即恢复 |
| weibo-hot / ithome | 有数据（30 / 60 条），候选贡献 **0** | 与账号定位不匹配 | 保留观察两周，再决定 |
| producthunt | 有数据（20–40 条），候选贡献偶发 | 边界 | 保留 |

本轮**不动白名单**。

---

# 第四轮：Source Quality Gate 与人工标注验证（2026-10-30）

## 机制

`contentops.hotspots.quality` 只回答一个问题：链接背后有没有真实项目。
单一弱信号（stars / 新旧 / 描述里的一个词）永远不足以拒绝，拒绝需要**两个相互独立的
信号**；检视失败（限流、超时）一律 `UNVERIFIED` 通过，绝不因此删候选。
名字与描述都能从榜单直接读到，因此"自称夹具两次"的仓库不花 API 就能被拒。

## 同一快照的前后对比（x-superplay-1024，7 个候选）

为了避免"两次采集结果不同"造成的假对比，下面是对**同一次采集结果**逐条跑门禁：

| # | 候选 | 分数 | 门禁 | 人工判读 |
|---|---|---|---|---|
| 1 | qpmsapps-dot/qpms-crm — CRM / 外勤平台 | 5.10 | ACCEPT | 不相关（ISV 业务系统，非 AI） |
| 2 | aien-dev/aienos.com — 网站源码，Rust 生成 | 5.05 | ACCEPT | 边缘（不是可测试的产品） |
| 3 | fabcode-it-solutions/hr-portal — HR 后端 API | 5.05 | ACCEPT | 不相关 |
| 4 | halfsend-10/test-repo-12-mint-host — "behaviour test" | 5.05 | **REJECT** | 不相关（测试夹具）✓ |
| 5 | dipakarmakar11363-arch/Oralguard — 口腔癌筛查 AI 模型 | 5.05 | REVIEW | 边缘（可作"AI 新物种"实测） |
| 6 | fastbrowse — 开源浏览器 agent | 2.80 | — | 边缘（可实测的 AI 工具） |
| 7 | HelloGitHub 127 期 | 2.75 | — | 边缘（可做工具合集） |

| 指标 | 门禁前 | 门禁后 |
|---|---|---|
| 候选数 | 7 | 6 |
| 明确相关 | 0 | 0 |
| 边缘可用 | 4 | 4 |
| 不相关 | 3 | 2（其中 1 条是夹具） |
| **宽口径精确率（可用 / 全部）** | 4/7 = 57% | **4/6 = 67%** |
| **自动门禁通过率** | — | 6/7 = 86% |
| **误杀率**（门禁拒掉但人工认为可用） | — | **0/1 = 0%** |

## 结论（必须分开说）

1. **门禁做对了它该做的事**：唯一被拒的是真夹具，误杀 0。
2. **门禁不解决 1024 的精度问题**：剩下的 6 条里仍有 2 条是"真实但与账号无关"的项目
   （CRM、HR 后端）。这不是夹具，质量门禁**不应该**也不可以删掉它们——删掉就变成
   用工程手段隐性地改定位。它们只能由定位（关键词/否定词）或人工判断处理。
3. **自动通过率 ≠ 精确率**：86% 的候选通过了门禁，但人工精确率只有 67%（宽口径）、
   0%（严格口径）。把两者混为一谈会得出"门禁很有效"的错误结论。

## 未来智能：回归检查

同一次运行下，40 个候选，门禁**拒绝 0 条**，1 条 `REVIEW`（保留）。池子与上一轮
一致（40 vs 38–41 波动来自 GitHub `sort=updated`）。**未发生跨账号回归。**

## 环境限制（真实）

GitHub 未认证 API 限额 60 次/小时，本轮实验后剩 **0**。因此绝大多数条目落在
`UNVERIFIED`——这正是设计行为（宁可放行也不错杀），但它同时意味着
**"空壳仓库"这类信号在本机当前配额下无法可靠触发**。已加磁盘缓存
（`.local/content-router/quality-cache.json`，TTL 7 天），使每日运行不会重复消耗配额；
要完整启用 substance 信号，需要等配额恢复，或由用户批准使用带 token 的访问。
