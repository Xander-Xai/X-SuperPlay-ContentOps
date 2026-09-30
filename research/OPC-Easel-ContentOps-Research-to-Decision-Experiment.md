你现在最需要的不是“继续研究更多工具”，而是把上一份报告变成一个**持续产生决策和行动的经营资产**。

结合我刚刚重新检查的你当前仓库治理结构，以及 GitHub 官方 Projects/Issue Forms、ADR 实践和 Easel 当前状态，我建议采用下面这条链：

```text
调研报告
  ↓
Decision Record
  ↓
可证伪实验
  ↓
GitHub Issues / Project
  ↓
真实运行 Evidence
  ↓
Founder Decision
  ↓
局部集成 / 全面集成 / 放弃
  ↓
持续监控上游变化
```

而不是：

```text
调研报告
→ 看起来不错
→ Fork Easel
→ 大改仓库
→ 又做几周基础设施
→ 内容还是没稳定生产
```

这一区别非常重要。

---

# 一、先给这份报告一个正确身份：它现在只是 `screened`

你自己的生命周期已经定义：

```text
idea
→ screened
→ queued
→ running
→ evidence-ready
→ validated
→ productized
```

其中 `running` 要有实验假设、变量、样本、指标和记录位置；`validated` 更需要实际价值证据。

所以：

> **《OPC × Easel ContentOps Runtime 调研》现在应该标记为 `screened`，而不是 `validated`。**

这是第一件事。

因为我之前得出的：

> Easel 非常适合你。

目前属于**高质量技术假设**。

不是：

> Easel 已经证明能让 X-SuperPlay 每周稳定生产 4 条、降低 Founder 工时、兼容你的三个 Active 平台。

这件事还没被证明。

---

# 二、而且我现在不建议你立刻重构成“Easel 中央 Runtime”

我重新看了你现在的 `Platform-Repository-Integration.md`。

你已经建立了：

```text
X-SuperPlay-Strategy
        ↓
┌───────┼──────────────┐
↓       ↓              ↓
抖音    小红书          B站
↓       ↓              ↓
douyin  xhs-FA       bilibili
repo    repo          matrix
```

目前明确的 Source of Truth 是：

```text
Strategy
= 平台组合 / Routing / Experiment / Metrics / Review

平台 Repo
= 真正 Workflow / Skill / Production / Receipt

OPC Blueprint
= Opportunity / Offer / Revenue / Business Truth
```



注册表里也已经正式登记：

- `douyin-1024`
- `xhs-FA`
- `bilibili-matrix-skills`
- `shipinhao-matrix-skills`
- `gzh-Future-Intelligence`

作为执行事实源。

所以如果现在一句：

> “以后 Easel 就是中央 Runtime。”

实际上会**破坏你刚建立好的 Source-of-Truth 边界**。

因此上一份报告最正确的用途不是“宣布迁移”。

而是：

> **提出一个架构候选，并设计实验决定它最终处于哪一层。**

---

# 三、把上一份报告压缩成一个 ADR

这是我认为你应该做的第一个正式资产。

ADR（Architecture Decision Record）的核心作用，就是记录：

> 当时面对什么问题、考虑了哪些方案、为什么做这个选择、有什么后果，以及未来怎么验证这个决定。

ADR 社区当前仍推荐这种方式保存重要架构决策，并特别强调不仅要记录结果，还应该留下证据、替代方案以及 realization/review plan。:chatgpt-content-reference{index="3"}

建议建立：

```text
X-SuperPlay-Strategy/
└── 00-Governance/
    └── decisions/
        └── ADR-WS008-ContentOps-Runtime.md
```

内容不要复制整份调研。

只回答：

| ADR 字段 | 内容 |
|---|---|
| Problem | 当前多平台生产是否存在重复实现、Founder handoff、维护成本 |
| Current architecture | Strategy + platform execution repos |
| Candidate | ZJU-REAL/Easel |
| Option A | 保持现状 |
| Option B | Easel 仅作为公共 Skill Provider |
| Option C | Easel 作为 Common Runtime，平台 repo 做 Adapter |
| Option D | Easel 仅用于借鉴，不成为依赖 |
| Current decision | **Experiment Required** |
| Evidence required | 真实内容生产数据 |
| Review date | 2 周实验结束 |
| Decision owner | Founder |
| Rollback | 保持现有平台 repo 完全可运行 |

也就是说：

```text
调研报告 = Why / Evidence Library

ADR = So What?
```

不要把两者混为一个文件。

---

# 四、然后建立一个真正的 WS-008 实验，而不是开发项目

这是整个方案最关键的一步。

命名：

```text
EXP-WS008-EASEL-001
Easel Runtime Fit Evaluation
```

不要先开发 `opc-source-ingest` 七个 Skill。

也不要先写统一 API。

先验证：

> **Easel 是否真的比你现有 Workflow 更省时间、更可靠、更容易维护。**

## 两周怎么实验

| 阶段 | 做什么 | 主要回答 |
|---|---|---|
| Day 0 | 冻结 Easel commit + 环境 | 能否稳定复现 |
| Day 1–2 | 跑 1 个已有 Source Artifact | 能不能完成你的 Source→Asset |
| Day 3–4 | 抖音适配 | 是否优于/等于现有 workflow |
| Day 5–6 | 小红书适配 | 卡片/发布/package 是否成立 |
| Day 7 | 第一轮 Review | 最大 friction 在哪里 |
| Week 2 | 再跑 2–3 个真实 Source | 是否可重复 |
| Day 14 | Founder Review | Adopt / Partial / Reject |

不要用假 Demo。

直接拿你近期真实工作，例如：

```text
GitHub 新项目实测
AI × 真实工作实验
OPC 自动化实验
```

这正好就是你 ContentOps 当前三个 Cluster。

---

# 五、这次实验不要主要看播放量

这是非常容易走偏的一点。

**Easel 实验首先是在验证生产系统，而不是内容选题。**

因此第一阶段核心 Scorecard 应该是：

| 指标 | Current Workflow | Easel | 目的 |
|---|---:|---:|---|
| Founder Minutes |  |  | 最重要 |
| Wall-clock Time |  |  | 整体耗时 |
| Manual Handoffs |  |  | 搬运次数 |
| Rework Rounds |  |  | 返工 |
| Failed Steps |  |  | 稳定性 |
| Platform-native QC |  |  | 是否真的适配平台 |
| Claim/Source Preservation |  |  | OPC 证据安全 |
| Human Approval preserved |  |  | 治理 |
| Publication Receipt |  |  | 可审计 |
| Metrics ingestion |  |  | 是否形成闭环 |
| New reusable assets |  |  | 是否复利 |

你的仓库当前已经规定，自媒体目标是提高 `Published Videos / Founder Hour`，并且现阶段 Founder 内容预算要可持续，而不是追求最高视觉上限。上一轮 Strategy 也已经明确要求 Workflow PASS、Published、Content Winner、Validated Demand 必须严格分开。

因此不要出现：

```text
Easel 视频播放量更高
→ Easel 架构更好
```

这在实验设计上不成立。

---

# 六、我建议设一个“晋级 Gate”

两周以后不要再开会凭感觉讨论。

直接过 Gate。

### Hard Gate

```text
Human Approval 没有被绕过
AND
Source / Claim 可以追溯
AND
Credentials 不进入 Git
AND
Publication Receipt 可记录
AND
Failure 可以 fail closed
AND
现有三个 Active Platform 至少可以接入
```

任何一项失败：

```text
不得成为 Common Runtime
```

### Efficiency Gate

你的当前系统已经有每周 Founder 内容时间预算。

因此我建议实验目标先设：

```text
Published throughput >= 当前 baseline

Founder Minutes
目标下降 >= 25%

Manual Handoff
目标下降 >= 30%

Required Record Completeness
= 100%

严重 Governance Incident
= 0
```

这里的 25% / 30% 不是“行业标准”，而是我建议的**实验判定阈值**。

因为如果 Easel 只能：

```text
节约 5% 工时
+
引入一个高速变化的新 runtime
+
增加 OpenClaw / Skill / browser dependency
```

这种迁移不值得。

---

# 七、最后不是只有“用 / 不用 Easel”两个结果

这是这份报告真正开始为你服务的地方。

两周后应该允许得到四种结果：

| 实验结果 | 决策 |
|---|---|
| 全链路明显优于当前 | `COMMON_RUNTIME_CANDIDATE` |
| 创作强、发布弱 | `PRODUCTION_ENGINE_ONLY` |
| 某个平台特别强 | `PLATFORM_SPECIFIC_ADAPTER` |
| 没明显节约 Founder 时间 | `REFERENCE_ONLY` |

比如非常可能出现：

```text
Easel
├── Research / Topic / Adaptation    ✅
├── 小红书 Content Production       ✅
├── 抖音 Publish                     ⚠️
├── B站 Deep Video                   ⚠️
└── OPC Business Signal             ❌
```

那你的正确架构就不是：

```text
删掉原有仓库
→ 全部换 Easel
```

而可能是：

```text
Strategy
       ↓
Common Content Capability
       ↓
Easel
       ↓
──────────────
↓      ↓      ↓
douyin xhs  bilibili
repo   repo   repo
```

这是一种**渐进式收敛**。

---

# 八、GitHub Project 要真正成为你的“执行仪表盘”

我建议不要再让这份报告躺在 Markdown 目录里。

GitHub 官方现在推荐 Projects 维护单一 Source of Truth，并通过 custom fields、workflow automation、auto-add 来减少人工更新。:chatgpt-content-reference{index="5"}

建立：

```text
Project:
X-SuperPlay WS-008 ContentOps
```

字段：

```text
Status
Idea / Screened / Queued / Running / Evidence Ready / Validated / Killed

Work Type
Research / Decision / Experiment / Implementation / Bug

Runtime
Current / Easel / MPT / Postiz / Other

Platform
Common / Douyin / XHS / Bilibili / ...

Gate
Research / Technical / Production / Founder

Evidence
Missing / Partial / Ready

Decision
Pending / Adopt / Partial / Reject
```

然后 Issue 自动进入 Project。

GitHub 自带 Auto-add workflow，可以根据 repository + label 自动将 Issue 加进项目。:chatgpt-content-reference{index="6"}

例如所有：

```text
label:ws-008
```

自动进入 ContentOps Project。

这样以后不会出现：

> “我们之前研究 Easel 研究到哪里了？”

看 Project 就知道。

---

# 九、再建立一个 Experiment Issue Form

这个投入非常值。

GitHub Issue Forms 可以定义必填字段、下拉选择、默认标签等，非常适合把你的“实验规范”机械化。:chatgpt-content-reference{index="7"}

以后任何“这个 AI 项目好像不错，我想接进 OPC”，都不能直接 Coding。

必须填：

```yaml
problem:
current_workflow:
candidate:
hypothesis:

baseline:

expected_gain:

sample:
acceptance:

founder_time_cap:
cash_budget_cap:

failure_mode:
rollback:

evidence_path:

promotion_gate:
stop_condition:
```

这样以后：

```text
Easel
Agent Motion
Pixelle
aifusionvideo
Modly
新数字人
新 TTS
新发布工具
```

全部进入**同一个实验制度**。

这件事比再找到 100 个 AI 项目更有长期价值。

---

# 十、这份报告还必须设置“失效条件”

这一点非常重要。

Easel 是一个非常新的高速迭代项目。

截至目前，它官方 README 仍把：

> Windows 全链路适配、安装简易化、支持更多 Agent Harness

列在 Roadmap 中；与此同时，近期 changelog 又持续在修 Windows/OpenClaw、抖音指标、小红书登录等问题。:chatgpt-content-reference{index="8"}

也就是说：

> 今天正确的调研，三个月以后可能已经部分失效。

所以研究文件顶部必须增加：

```yaml
researched_at: 2026-10-01

upstream:
  repo: ZJU-REAL/Easel
  commit: <SHA>

valid_for_decision:
  - EXP-WS008-EASEL-001

assumptions:
  - active platforms remain douyin/xhs/bilibili
  - current platform repos remain source of truth
  - human publish approval required

invalidators:
  - major Easel architecture change
  - publishing mechanism change
  - platform policy/API change
  - active platform portfolio change
  - experiment evidence contradicts report

review_after:
  2026-10-15
```

这样它才是一个**活的 Research Asset**。

而不是历史文章。

---

# 十一、外部依赖一定要 Pin

如果进入实验，不要：

```bash
git clone ...
git pull main
```

然后每天的环境都不一样。

先记录：

```text
repo
commit SHA
Easel version
OpenClaw version
Python version
Node version
OS/runtime
```

GitHub 在它自己的供应链安全指南里也强调了“不可变引用”的重要性，例如 Actions 推荐使用完整 commit SHA 固定依赖，避免上游引用漂移。:chatgpt-content-reference{index="9"}

对你的实验同样适用：

```text
EXP-001
必须对应
Easel@abcdef123...
```

否则两周以后：

> 为什么 Week 1 可以、Week 2 不行？

你都不知道是不是 Easel main 变了。

---

# 十二、你的“调研 → 行动”以后统一变成这个制度

这是我认为这次最值得沉淀的东西。

```text
Internet / GitHub / X / ChatGPT
             ↓
          Research
             ↓
        Research Note
             ↓
       Architecture /
        Decision Record
             ↓
      Hypothesis / Gate
             ↓
           Issue
             ↓
         Experiment
             ↓
      Evidence Receipt
             ↓
          Review
       ↙     ↓      ↘
    Reject Partial  Adopt
             ↓
      Implementation
             ↓
       Runtime Metrics
             ↓
        Periodic Review
```

**这才是“让 ChatGPT 的调研真正为你服务”。**

否则你现在最大的问题很容易变成：

```text
今天发现 Easel
明天发现 Pixelle
后天发现 Agent Motion
大后天发现另一个 5 万 Star 项目

↓
一直感觉在进步

实际：
没有形成 Decision
没有形成 Experiment
没有形成 Production
没有形成 Evidence
```

你的 OPC 已经足够成熟，现在应该明确堵住这个漏洞。

---

# 十三、所以你现在不要继续“调研 Easel”

## 现在应该进入这个状态

```text
Research: DONE

Architecture hypothesis: READY

Decision:
EXPERIMENT_REQUIRED

Next:
EXP-WS008-EASEL-001
```

然后只允许两周实验回答三个问题：

```text
1. Easel 能否真的减少 Founder Minutes？

2. Easel 能否保持你已有
   Evidence / Claim / Human Approval / Receipt
   治理？

3. 它应该替代什么，而不是“它还能做什么”？
```

第三个问题尤其重要。

不要再问：

> Easel 有 114 个 Skill，我能不能全部用？

要问：

> **我现在已有的 5 套重复能力中，哪 2 套可以安全地被 Easel 消掉？**

这才是你的 OPC 思维。

---

## 我给你的最终行动排序

| 优先级 | 现在做什么 | 不做什么 |
|---|---|---|
| **P0** | 把上一份报告落成 Research Asset | 不再扩展工具清单 |
| **P0** | 建 `ADR-WS008-ContentOps-Runtime` | 不宣布 Easel 为正式架构 |
| **P0** | 建 `EXP-WS008-EASEL-001` | 不直接重构 5 个执行仓库 |
| **P0** | 锁 Easel commit | 不跟着 `main` 跑 |
| **P1** | 跑 2 周真实 Source | 不做假 Demo |
| **P1** | 记录 Founder Minutes / Handoff / Rework | 不以播放量判断 Runtime |
| **P1** | Founder Review | 不让 Agent 自动晋级 |
| **P2** | 根据证据 Partial / Adopt / Reject | 不预设必须迁移 |
| **P2** | 只实现被证明需要的 OPC Adapter | 不预写七八十个 Skill |
| **P3** | 若确实形成 Common Runtime，再讨论独立 Repo | 现在不新建 Runtime 仓库 |

如果这套机制跑通，上一份报告最大的价值甚至不是“找到了 Easel”，而是帮你建立了一个以后处理**所有 AI 工具、开源项目、自动化机会的统一 Research → Decision → Experiment → Evidence → Adoption 机制**。

这才是最值得进入 `X-SuperPlay` 的可复利资产。



::chatgpt-content-reference{index="11"}