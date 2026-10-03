```yaml
status: superseded
superseded_by: docs/AUDIT-REPORT.md, docs/ARCHITECTURE.md, docs/PRD.md
historical_context: Historical research that led to the Easel decision. Contains valuable context on why Easel was chosen and how it fits with OPC. Long-term reference document.
notes: Contains research detail. Active rules and architecture now in canonical docs.
```
你这次纠正是对的。你要的不是“LLM + TTS + FFmpeg + 发布脚本”这种零件清单，而是：

> **一个能够被 API / CLI / Agent 直接调用，拿到 Source Artifact 后自己跑完整链路，并且最终把内容、发布回执、指标、Signal 再写回 OPC 的 Self-Media Runtime。**

我重新读了你的 `X-SuperPlay-OPC-Blueprint`、`X-SuperPlay-Strategy`，并重新筛了 GitHub。结论已经明显收敛了。

# 一、先给结论

## 你当前最值得采用的主线不是从零开发，而是：

> **以 ZJU-REAL/Easel 作为 WS-008 Self-Media Runtime 的主体原型，给它加一层 X-SuperPlay OPC Adapter。**

不是直接把 Easel 当你的“自媒体战略系统”，而是：

```text
OPC Blueprint
= Business / Evidence / Permission / Commercial Source of Truth

X-SuperPlay Strategy / WS-008
= Workflow Policy + Experiment + Runtime Ownership

Easel
= Executable ContentOps Runtime / Skill Engine

OpenClaw
= Agent Runtime

n8n
= Trigger / Schedule / Retry / Notification（可选）

外部媒体工作流
= Easel Skill 后端，可插拔，不拥有流程控制权
```

这是我这轮调研后的核心判断。

你 Blueprint 本身就规定，自动化链应当是：

```text
Sensing
→ Topic Ranking
→ Content Adaptation
→ Publishing Gate
→ Metrics Ingestion
→ Weekly Review
→ OPC Evidence / Opportunity / Experiment Gate
```

而且明确写着 Blueprint 只是业务契约，真正 Runtime 应放在 `X-SuperPlay-Strategy / WS-008`，而不是在 Blueprint 再造执行系统。

Easel 恰好已经实现了非常接近的：

```text
Discover
→ Plan
→ Produce
→ Publish
→ Attribute
```

不是 PPT 架构，而是 **114 个可执行 Skill + CLI + FastAPI Web Backend + OpenClaw Gateway + 浏览器真实发布 + 数据回收**。:chatgpt-content-reference{index="1"}

[ZJU-REAL/Easel GitHub](https://github.com/ZJU-REAL/Easel?utm_source=chatgpt.com)

---

# 二、为什么我现在把 Easel 放到第一优先级

你当前仓库的目标其实已经非常清楚。

你的 Strategy 不是追求“做一个最强 AI 视频系统”，而是：

```text
在质量底线、现金预算和 Founder 时间预算内
最大化 Published Videos / Founder Hour

同时获得：
Market Signal
+ Reusable Asset
+ Commercial Signal
```

当前基线是两个账号每周合计 4 条内容，而且强调 1–2 个真实 Source Artifact 派生内容，不允许为了日更制造工作。

你当前的平台优先级也是明确的：

| 状态 | 平台 |
|---|---|
| Active | 抖音、小红书、Bilibili |
| Derived | 视频号、公众号、知乎、CSDN |
| Experiment | YouTube、X |
| Infrastructure | GitHub |

因此我用你 OPC 的逻辑反过来筛 GitHub 项目，而不是看 Star。

| 项目 | 是完整工作流吗 | 可程序调用 | 中国平台 | 制作 | 发布 | 数据回流 | 对你当前适配 |
|---|---:|---:|---:|---:|---:|---:|---|
| **Easel** | ★★★★★ | CLI / Gateway / FastAPI | ★★★★★ | ★★★★★ | ★★★★★ | ★★★★☆ | **核心 Runtime** |
| **MoneyPrinterTurbo** | ★★★☆☆ | **REST API / CLI / Skill** | 发布偏海外 | ★★★★★ | ★★★☆☆ | ★☆☆☆☆ | Enhanced 制作 Worker |
| **Postiz** | ★★★★☆ | **REST API / MCP / CLI / SDK** | ★☆☆☆☆ | ★★☆☆☆ | ★★★★★ | ★★★★★ | 海外 Distribution |
| **social-auto-upload** | ★★☆☆☆ | CLI / Skill | ★★★★★ | ☆☆☆☆☆ | ★★★★★ | ★☆☆☆☆ | 国内发布备用执行器 |
| SocialFlow-AI-Agent | ★★★☆☆ | **FastAPI** | ★☆☆☆☆ | ★★☆☆☆ | ★★☆☆☆ | Roadmap | 架构参考 |
| OpenReels | ★★★☆☆ | API / CLI | ★☆☆☆☆ | ★★★★☆ | 较弱 | 较弱 | 不如 MPT |

这里最关键的一点是：

## Easel 已经不是“独立组件”

它已经包含一条真正连续的自媒体工作流：

```text
热点 / RSS / 新闻 / UGC
       ↓
趋势发现
       ↓
账号画像 + Topic Evaluation
       ↓
选题 / Hook / Script / Calendar
       ↓
图文 / TTS / 视频 / 卡片 / 信息图
       ↓
Persona Check
Risk Scanner
Quality Gate
Publish Checklist
       ↓
平台 Adaptation
       ↓
抖音 / 小红书 / B站 / 知乎 /
视频号 / 公众号 / 快手
       ↓
Account Analytics
Comments
Content Postmortem
ROI
       ↓
Profile Memory
```

它甚至已经有：

`skill-content-repurposing`、`skill-cross-platform-publish`、`skill-quality-gate`、`skill-risk-scanner`、`skill-publish-checklist`、`skill-publish-scheduler`、`skill-douyin-upload`、`skill-xhs-publisher`、`skill-bilibili-upload` 等。:chatgpt-content-reference{index="5"}

归因侧也已有 `skill-comment-insights`、`skill-content-postmortem`、`roi-calculator`、`skill-content-calendar-log` 等。:chatgpt-content-reference{index="6"}

所以这才是你说的：

> **“工作流 / Skill，而不是一大堆独立组件。”**

---

# 三、它和你的 OPC 又不能直接划等号

这是这次分析最重要的边界。

你的 OPC 经营内核明确规定：

```text
Problem Signal
→ Problem Evidence
→ Customer / Job / Context
→ Value-at-Stake
→ Buyer / Urgency / Reachability
→ Opportunity
→ Solution Hypothesis
→ Offer
→ Distribution
→ Transaction
→ Delivery
→ Acceptance
→ Reusable Asset
→ Better Problem Discovery
```

并且：

```text
Views ≠ Validated Demand
Comment / DM ≠ Paid Demand
Technology is not the starting object
One delivery ≠ Product
AI Agent ≠ Business Source of Truth
```

而 Easel 本质还是一个 **Creator Content Operating System**。

例如它的 `topic-evaluator` 会关注：

```text
流量潜力
账号匹配
竞争差异
时效价值
变现空间
制作成本
合规风险
```

:chatgpt-content-reference{index="8"}

这套逻辑对普通自媒体很好，但对 X-SuperPlay 还缺：

```text
Source Artifact 是否真实
Proof Level
Permission Status
Claim Boundary

对应哪个 Problem ID
对应哪个 Offer ID
PD Evidence 到哪一级

是否产生 Qualified Signal
是否 Commercial Progression
Founder Minutes
Reusable Asset
是否值得进入 Experiment / Opportunity Ledger
```

所以：

> **Easel 可以成为你的“手脚和流水线”，不能成为你的“经营大脑”。**

---

# 四、我要你真正重新制作的不是“视频工作流”，而是这个

建议把你新的 Runtime 定义成：

## `OPC Self-Media ContentOps Runtime`

统一 API：

```http
POST /v1/content-runs
```

输入不再只是：

```json
{
  "topic": "介绍 RAG"
}
```

而应该是：

```json
{
  "source": {
    "type": "research | repo | experiment | delivery | review",
    "refs": ["..."]
  },

  "account": "X-SuperPlay-1024",

  "lane": "baseline",

  "problem_ids": [],
  "offer_ids": [],

  "proof_level": "L0",
  "permission_status": "public",
  "claim_boundary": "...",

  "topic_cluster": "AI_REAL_WORK",
  "packaging": "RESULT_FIRST",

  "target_platforms": [
    "douyin",
    "xiaohongshu",
    "bilibili"
  ],

  "human_publish_approval": true
}
```

内部不再是“调用几个 API”，而是一条**完整状态机**：

```text
SOURCE_CAPTURED
     ↓
EVIDENCE_EXTRACTED
     ↓
OPC_TOPIC_RANKED
     ↓
MASTER_CONTENT_CREATED
     ↓
PLATFORM_ASSETS_PRODUCED
     ↓
CLAIM_CHECKED
     ↓
PERMISSION_CHECKED
     ↓
QUALITY_GATE
     ↓
HUMAN_APPROVAL
     ↓
PUBLISHED
     ↓
METRICS_INGESTED
     ↓
SIGNALS_CLASSIFIED
     ↓
OPC_REVIEWED
     ↓
REUSE / RETIRE / EXPERIMENT
```

这基本就是你 Blueprint 已经定义的状态机的可执行版本。

---

# 五、Easel Skill 应该怎样映射你的 WS-008

这才是我认为你最应该做的“重制”。

| 你的 OPC Contract | Easel 可直接复用 | 你必须自己增加 |
|---|---|---|
| Sensing | trending-topics / news-intelligence / rss-aggregator / content-gap | OPC Source Registry |
| Topic Ranking | topic-evaluator | **OPC Topic Ranker** |
| Source → Content | script / storyboard / repurposing / media Skills | Proof/Source binding |
| Platform Adaptation | content-repurposing | ContentRecord IDs |
| Claim Check | quality-gate / risk-scanner | **L0-L3 Claim rules** |
| Permission Gate | risk scanner | **OPC permission_status** |
| Human Approval | Publish Center | OPC Approval Receipt |
| Publishing | cross-platform-publish + platform Skills | Publish Receipt |
| Metrics | account analytics | T+2H/24H/72H/7D schema |
| Comment Signal | comment-insights | **PD0–PD7 classifier** |
| Review | content-postmortem | Commercial Progression |
| Learning | profile memory | Opportunity Ledger / Experiments |

所以你不是 Fork Easel 然后魔改 114 个 Skill。

真正应该增加的只是几层 **X-SuperPlay-specific Skills**：

```text
opc-source-ingest
opc-evidence-extractor
opc-topic-ranker
opc-claim-permission-gate
opc-content-record-writer
opc-signal-classifier
opc-weekly-business-review
```

其他制作、发布、适配、平台操作直接复用 Easel。

这就从：

> “我又自己开发一个自媒体系统”

变成：

> “我建立了一个 OPC Adapter，把成熟 Content Runtime 接入自己的经营内核。”

这个方向工程量小很多，也更符合你仓库的 Capability Emergence Doctrine。

---

# 六、你当前真正应该有的 3 条生产 Workflow

不是 100 个 Skill 平铺。

## Workflow A — Result-derived Baseline

这是你当前最重要的生产线。

```text
Repo / Research / Experiment / Real Delivery
                   ↓
             Source Artifact
                   ↓
       OPC Evidence Extraction
                   ↓
      Claim + Permission Boundary
                   ↓
             Topic Packaging
          R / C / Q 三选一
                   ↓
              Master Script
                   ↓
      ┌────────────┼────────────┐
      ↓            ↓            ↓
    抖音         小红书          B站
  Short Video    Cards/Video    Deep Video
      ↓            ↓            ↓
        Easel Quality Gate
                   ↓
             Human Approval
                   ↓
                Publish
                   ↓
     T+2 / 24 / 72 / 7D Metrics
                   ↓
          Qualified Signal
                   ↓
             OPC Review
```

这与 Strategy 当前的 `Baseline 4 条/周 + 1–2 Source Artifact` 完全一致。

这是 **P0**。

---

## Workflow B — GitHub / AI 实测 → 自媒体

这尤其适合你现在两个账号的定位。

你 42 天 Sprint 已经定义了三个 Cluster：

```text
A AI 新能力实测
B AI × 真实工作
C AI 生意 / 自动化实验
```

所以可以直接执行：

```text
GitHub Repo / New AI Tool
       ↓
自动获取 README / Release / Issues
       ↓
安装 / 测试 / Benchmark
       ↓
产生真实 Result Artifact
       ↓
结果：
PASS / PARTIAL / FAIL
       ↓
提炼：
“它到底解决什么问题？”
“我真跑了结果怎么样？”
“适合谁？”
“哪里翻车？”
       ↓
OPC Evidence Gate
       ↓
一源多资产
```

例如：

```text
GitHub Experiment
     ↓
抖音：
“这个 2.8 万 Star 项目我真跑了一遍”

小红书：
“部署踩坑 + 配置清单”

B站：
“完整原理 + 部署 + 实测”

CSDN：
“环境 / 命令 / Bug 修复”

GitHub：
Experiment Receipt / Demo / Code
```

这比“每天 AI 搜热点 → LLM 写文案 → AI 生成视频”适配你得多。

因为你的 **工作本身就是 Source**。

---

## Workflow C — Winner → Enhanced

只有 Baseline 已经证明主题值得投入才进入：

```text
Winner Source
     ↓
Enhanced Script
     ↓
AI Video / Digital Human /
Advanced Motion / Higher-end Visuals
     ↓
Multi-platform Adaptation
     ↓
Publish
     ↓
Compare:
Founder Minutes
Cash Cost
Retention
Qualified Signal
Commercial Signal
```

这正是你 Strategy 的 Lane B。

这里我才建议接 **MoneyPrinterTurbo**。

它现在已经不是以前简单的脚本项目，而是明确提供：

```text
AI Agent
WebUI
REST API
CLI
Skill
Docker

topic
→ script
→ voice
→ footage
→ subtitles
→ music
→ editing
→ final MP4
```

API 文档直接运行在 `/docs`，核心接口包括 `/api/v1/scripts`、`/api/v1/terms`、`/api/v1/videos`、`/api/v1/tasks`。:chatgpt-content-reference{index="12"}

它甚至已经有官方 `SKILL.md`，Agent 可直接从主题完成成片。:chatgpt-content-reference{index="13"}

截至 2026-10-01，GitHub API 显示其约 **12.7 万 Star、MIT、9 月 30 日仍在提交**。

[MoneyPrinterTurbo GitHub](https://github.com/harry0703/MoneyPrinterTurbo?utm_source=chatgpt.com)

但注意：

> **它不应该成为你的主 Runtime。**

因为它解决的是：

```text
topic → video
```

而你要解决的是：

```text
real work
→ evidence
→ content
→ distribution
→ market signal
→ business learning
```

所以 MPT 是 **Enhanced Worker**，不是 ContentOps Brain。

### 数字人口播：先验证免训练照片路线，再决定是否训练

数字人至少要区分两种生产路径，不能把“数字人”一概等同于先采集视频、付费训练：

| 路线 | 输入与准备 | 适合当前阶段的用途 | 需要验证的代价 |
|---|---|---|---|
| **免训练照片驱动** | 固定人物照片 + 已生成的配音音频，生成口型同步视频；部分服务支持直接传文字 | 低成本验证短 Hook、口播包装和自动化接口 | 单次生成效果、照片限制、计费、排队时间、素材留存和 API 可用性 |
| **训练型数字分身** | 录制本人素材并建立可复用 Avatar / Digital Twin，之后用音频或文案驱动 | 照片路线已被验证，且确实需要更稳定的长期人物表现时 | 训练要求、授权与素材治理、初始化和持续费用、身份与表情一致性 |

因此当前不应先把训练型分身当成准入门槛。先用一张有使用权、适合竖屏构图的固定人物照片和同一段自有 TTS 音频，跑通照片驱动路线；只有复测表明照片路线的身份稳定性、表情或动作达不到内容要求，并且这个人物已成为长期 IP，才把训练型方案列为下一阶段实验。训练型方案可能改善复用与一致性，但不能在没有同条件样片前当作质量保证。

#### 候选 Provider 与接口边界

- **腾讯云照片免训练**：官方接口明确支持照片免训练，照片配文本或音频生成口型匹配视频；接口接收音频并异步返回任务，可作为国内 API 候选。[腾讯云照片免训练接口](https://cloud.tencent.com/document/product/1240/118475)
- **HeyGen 照片驱动**：官方 V3 Create Video 文档说明可从 HeyGen avatar **或任意图片**创建视频，并支持预录音频口型同步；请求体区分 `CreateVideoFromImage` 与 `CreateVideoFromAvatar` 两种模式。已有 Photo Avatar 模式使用 `avatar_id`（Photo Avatar look ID），而任意图片模式可作为免训练候选。接入 PoC 应分别确认图片模式的准确字段、素材上传/URL 要求、当前 API Key 的可用权限和实际费用，不能未经验证就假定字段一定叫 `image_url`。[HeyGen Create Video API](https://developers.heygen.com/reference/create-video)
- **分清“图片直接驱动”和“Photo Avatar 资源”**：输入任意图片直接生成，与先创建可复用的 Photo Avatar 再通过 `avatar_id` 调用，是两种 API 入口/资产生命周期；两者都不等同于采集本人视频训练 Digital Twin。实现时按官方 `CreateVideoFromImage` schema 组装请求，不把示意 JSON 当成已验证字段，也不要因为出现 `avatar_id` 就误判必须先训练。
- **本地 H3**：保留为本地质量与成本基准，不预先判定它已经足够或必然优于云端方案。将它和 API Provider 放在相同素材、相同后期条件下比较。

声音与人物生成应保持解耦：`IndexTTS / 其他 TTS → audio.wav` 是独立产物，数字人 Provider 只消费该音频并返回口播视频。HeyGen 官方 API 接受公开可访问的 `audio_url` 或已上传的 `audio_asset_id`（二选一），可用预录音频驱动；请求应使用音频输入模式而不是同时传脚本。标准化链路为：

```text
固定人物图片 + 自有 audio.wav
        ↓ 上传/可访问 URL
HeyGen CreateVideoFromImage（或已创建 Photo Avatar 的 Avatar 模式）
        ↓ 返回 video_id
查询任务状态 / 接收回调 → 下载 MP4
        ↓
OpenChatCut → Remotion → 成片
```

这使声音和人物可以分别替换，不必同步更换 TTS。HeyGen、腾讯云或本地 H3 只负责生成口播视频，不取得选题、证据、发布审批或 OPC 经营判断的所有权。素材应有明确使用权和授权记录。

#### HeyGen API 计费基线（核价日期：2026-10-01）

HeyGen API 是独立的 Pay-As-You-Go 计费面，不要求先购买普通网页端 Creator/Business 套餐。官方 API 价格按实际生成秒数计费；截至本次核对，公开页面列出的费率如下：

| 模式 | Avatar III | Avatar IV | 备注 |
|---|---:|---:|---|
| Photo Avatar | $0.99/分钟 | $2.31/分钟 | 照片驱动档位；资源创建 API 另列 $1.32/次 |
| Digital Twin | $0.60/分钟 | $4.83/分钟 | Twin 创建 API 另列 $2.13/次，且自助 API 创建 Digital Twin 仅向 Enterprise API 用户开放 |

因此旧估算中的 Photo Avatar `$1/$3`、Digital Twin `$1/$4` 只能视为粗略量级，不能当当前报价；尤其 Avatar III 的 Twin 单分钟费率较低，不代表当前账号一定能自行创建 Twin。任意图片直驱、创建 Photo Avatar 资源和 Twin 创建可能涉及不同调用/权限/费用，正式预算前应以当前 API 账号的报价与账单复核。以上价格引用 HeyGen 官方说明，价格可能变更：[HeyGen API 定价说明](https://help.heygen.com/en/articles/10060327-heygen-api-pricing-explained)。

#### 首轮小样 A/B

先围绕当前目标做短 Hook 测试：同一张有使用权的竖屏人物图、同一段 5–8 秒自有 WAV、同一输出比例与后期设置，对比 **HeyGen 任意图片/Photo Avatar、腾讯云照片免训练、本地 H3**。若短样通过，再用同一素材扩展到约 30 秒，检查长段口型和表情稳定性。先确认服务条款、人物授权、素材留存、账号 API 权限和输入限制；不以单个样片宣称生产就绪。记录：

1. 人脸/人物一致性与照片身份保真；
2. 嘴型同步、停顿和音素错位；
3. 表情、头部运动与整体自然度；
4. 从提交到可下载 MP4 的真实耗时及失败/重试情况；
5. 以账单或实际扣费记录核算的单条成本，并注明分辨率、时长、引擎与账号方案；
6. 自动化接入复杂度，包括素材上传、是否需要创建可复用 Photo Avatar、任务轮询/回调、错误处理和结果下载；
7. **每条可接受 Hook 的真实成本**：包含生成失败重试和必要的资源创建费用，而不只比较标价/分钟。

价格与套餐会变化，方案表只用于形成候选，不把未经当前账号核验的每分钟报价写成固定预算。先用真实账单核价。通过画面质量、运行稳定性、成本和自动化门槛后，Provider 才能进入受控生产；对外发布仍遵循本工作流的人审门禁。

**当前建议**：先验证“人物图片 + 自有配音 → API → MP4”的免训练路线，HeyGen 任意图片模式和腾讯云作为云端候选，本地 H3 为质量/成本对照；暂不投入训练型 Digital Twin。照片驱动适合自动化 Hook 流程，但是否能无人值守仍取决于账号权限、输入资产要求、异步任务可靠性、授权与实际成本。若任意图片模式在当前账号不可用，再评估创建 Photo Avatar 资源的备用流程；只有短样和较长样都证明照片路线不满足长期 IP 的表现需求，才进入 Twin 训练评估。

#### 数字人分辨率与画面占比

分辨率描述输出像素尺寸，不直接代表数字人更自然。分辨率提高会让脸、牙齿、嘴唇、头发和衣物边缘更清楚，也可能让生成瑕疵更显眼；动作、口型、身份稳定性和素材质量仍比单纯增加像素更影响观感。常见 9:16 竖屏规格及像素量如下（供应商实际支持的档位可能不同）：

| 档位 | 横屏常见尺寸 | 9:16 竖屏对应尺寸 | 竖屏像素量 | 适用判断 |
|---|---:|---:|---:|---|
| 480P | 854×480 | 480×854 | 约 41 万 | 工作流测试、超小窗或后续明显缩小 |
| 540P | 960×540 | 540×960 | 约 52 万 | 小窗、低成本试跑；脸部细节仍有限 |
| 720P | 1280×720 | 720×1280 | 约 92 万 | 手机小窗、约 20%–40% 画面占比的实用档 |
| 1080P | 1920×1080 | 1080×1920 | 约 207 万 | 竖屏成片常用规格，也适合半屏或全屏数字人 |
| 2K / 1440P | 2560×1440 | 1440×2560 | 约 369 万 | 细节增加，但多数口播小窗收益有限；“2K”在消费级产品中常被用来指 1440P |
| 4K | 3840×2160 | 2160×3840 | 约 829 万 | 普通社媒口播通常不必原生生成；用于明确要求高分辨率的交付场景 |

数字人源素材分辨率不必与最终视频相同：可以把 720P 数字人放进 1080×1920、30fps 的成片，再与 1080P B-roll、PPT 或截图合成。小窗缩放可能减弱部分细节瑕疵，但不会修复嘴型、眼神、动作或身份不稳定。高分辨率也不必然增加费用或耗时，具体取决于 Provider 的档位、计费规则和是否为原生生成/升频；测试时记录实际输出尺寸、生成模式和账单，不据此假定更低分辨率一定更便宜。

| 使用场景 | 建议先测的数字人源素材 | 最终成片基准 |
|---|---:|---:|
| 流程冒烟测试、超小窗 | 480P / 540P | 720P 或 1080P |
| 右下角/左下角小窗，约 20%–35% 画面 | 540P / 720P | 1080×1920 |
| 约 1/3 屏讲解员 | 720P | 1080×1920 |
| 半屏数字人 | 720P / 1080P | 1080×1920 |
| 全屏数字人或近景 | 1080P 起 | 1080×1920；确有交付要求再评估更高分辨率 |

**本项目默认候选**：数字人先以 720P、约 20%–35% 画面占比测试，主体由 B-roll、PPT、截图或演示画面承担，最终统一输出 1080×1920 / 30fps。测试排序优先看动作自然度、唇形、人物稳定性，再看清晰度；若 720P 缩小后仍不自然，升到 1080P、2K 或 4K 不能替代模型与驱动质量改进。该默认值是实验起点，需以同内容、同画面占比的实看片和实际成本确认。

---

# 七、Postiz 怎么处理

Postiz 这次调研后，我认为也很有价值，但位置非常明确。

它目前已经提供：

```text
Public REST API
Node SDK
n8n Node
CLI
MCP
Webhooks
Temporal workflow
Analytics API
28+ social channels
```

而且官方已经提供可以直接给 Agent 使用的 `SKILL.md`。:chatgpt-content-reference{index="16"}

API 甚至直接包含：

```text
POST /public/v1/posts
GET  /public/v1/analytics/:integration
GET  /public/v1/analytics/post/:postId
POST /public/v1/upload
POST /public/v1/clipping
```

:chatgpt-content-reference{index="17"}

它现在有约 3.65 万 Star，2026-09-30 仍有提交，而且 9 月版本还加强了 MCP/Agent surface 和 Temporal publishing workflow。:chatgpt-content-reference{index="19"}

[Postiz GitHub](https://github.com/gitroomhq/postiz-app?utm_source=chatgpt.com)

但是你的 Active 平台恰好是：

```text
Douyin
Xiaohongshu
Bilibili
```

Postiz 并不是为这三个平台设计的。

所以当前：

```text
Easel
→ 中国 Active Platform Runtime

Postiz
→ YouTube / X / Reddit / LinkedIn 等
   全球 Distribution Plane
```

等你的 `YouTube + X` 从 Experiment 晋级，再正式接入 Postiz。

另外注意它是 **AGPL-3.0**；自己内部部署问题较小，但如果以后把修改版做成对外网络 SaaS，需要认真处理对应开源义务。:chatgpt-content-reference{index="21"}

---

# 八、social-auto-upload 怎么处理

这项目反而非常契合你当前三个 Active 平台。

原仓库 `dreammis/social-auto-upload` 截至现在约 **1.5 万 Star**，支持：

```text
抖音
小红书
Bilibili
快手
视频号
百家号
TikTok
YouTube
```

其中抖音、小红书、Bilibili 已有统一 CLI / Skill，支持定时发布。:chatgpt-content-reference{index="22"}

[social-auto-upload GitHub](https://github.com/dreammis/social-auto-upload?utm_source=chatgpt.com)

但是：

它核心依赖 Playwright / Patchright / Cookie / Web Creator UI，而不是稳定官方 publishing API。:chatgpt-content-reference{index="24"}

这恰好违反你 Strategy 已经写好的默认原则：

> 官方 API / OAuth 优先，浏览器自动化只作受控助手，并且首次接入和高风险渠道保留 Human Approval。

所以我的位置定义是：

```text
NOT:
social-auto-upload = ContentOps Runtime

YES:
social-auto-upload
= China Publishing Adapter / fallback
```

而且 Easel 自己也已经明确警告，小红书自动发布可能触发验证、限流或风控，应预览、preflight 并由用户确认。:chatgpt-content-reference{index="26"}

---

# 九、为什么我不建议你直接基于 SocialFlow / OpenReels 重做

### SocialFlow-AI-Agent

它的状态机非常值得借：

```text
Draft
→ Review
→ Revise
→ Human Approval
→ Schedule
→ Publish
→ Audit
```

而且是 LangGraph + FastAPI，API 设计也干净。:chatgpt-content-reference{index="27"}

但 GitHub 当前 metadata 显示：

```text
0 stars
0 forks
repo size 13 KB
2026-09-01 创建
主要真实 connector 只有 LinkedIn
Analytics 还在 roadmap
```

所以：

> **读它的架构，不要把你的生产系统压在它上面。**

### OpenReels

它确实符合：

```text
topic
→ research
→ script
→ voice
→ visuals
→ music
→ captions
→ assembly
```

Docker + API + CLI 也齐。:chatgpt-content-reference{index="29"}

但 GitHub metadata 显示目前约 204 Star，而且最近代码 push 仍停留在 2026-04-10。

与仍高速维护的 MoneyPrinterTurbo 相比，我不会把它作为你的主视频 Runtime。

---

# 十、最后真正建议你搭成这个形态

```text
                     X-SuperPlay OPC Blueprint
                  Business Source of Truth
                           │
                           │
          Source / Proof / Permission / PD State
                           │
                           ▼
             ┌─────────────────────────┐
             │   OPC ContentOps API    │
             │      WS-008 Adapter     │
             │                         │
             │ State / Gate / Receipt  │
             └────────────┬────────────┘
                          │
                          ▼
                   Easel / OpenClaw
         ┌───────────────┼────────────────┐
         │               │                │
      Discover          Produce          Publish
         │               │                │
    Topic/News       Native Skills     China Platforms
    GitHub/Source       │            Human Approval Gate
         │              │                 │
         │        Enhanced only           │
         │              ↓                 │
         │     MoneyPrinterTurbo          │
         │                                │
         └───────────────┬────────────────┘
                         │
                         ▼
                      Attribute
                Metrics / Comments
                         │
                         ▼
               OPC Signal Classifier
                         │
             ┌───────────┴───────────┐
             ▼                       ▼
         Research                   PD0+
         Backlog              Opportunity Ledger
                         │
                         ▼
                   Weekly Review
```

这才是一个 **完整、自洽、API 可驱动、不会把 Business Source of Truth 交给 Agent 的工作流**。

---

# 十一、仓库应该怎么处理

这里我反而不建议你马上再开 `X-SuperPlay-Self-Media-AI-v3-final-final` 这种新仓库。

因为 Blueprint 已经明确规定：

> WS-008 的实现事实源当前是 `X-SuperPlay-Strategy`；只有以后 Runtime 足够独立，才经过 Cross-Repository Workstream Gate 拆独立 Runtime Repo。

因此现在正确的实施顺序是：

1. **在 `X-SuperPlay-Strategy / WS-008` 立一个 `Easel Runtime Evaluation` 实验**，固定 Easel commit，不直接追 `main`。它 2026-08-28 才创建、9 月 30 日仍高速变化，目前约 2.5k Star，因此值得用，但不适合无版本锁定地当生产依赖。
2. **不要一开始修改 Easel 114 个 Skill**。先跑你真实的两个账号和 1–2 个 Source Artifact，验证 `Source → Platform Asset → Human Gate → Publish → Metrics`。
3. **新写 7 个 OPC Skill/Adapter**：Source Ingest、Evidence、OPC Topic Rank、Claim/Permission Gate、ContentRecord、Signal Classifier、Weekly Review。
4. **用一个统一 `POST /v1/content-runs` 包起来**。内部可以调用 `easel skill`，也可以经 OpenClaw Gateway；Easel 安装脚本本身已经启用了本地 OpenAI-compatible `/v1/chat/completions` Gateway。:chatgpt-content-reference{index="33"}
5. **n8n 只负责触发，不负责经营判断**：定时、Webhook、retry、notification、人工审批通知。你仓库原本对 n8n 的定位其实已经是正确的。
6. **Baseline 先全部走 Easel 原生简单制作路线**；MoneyPrinterTurbo 只接 Lane B Enhanced，不让 AI Video 再次阻塞每周 4 条基线。
7. 连续两周拿到 `Founder Minutes / Publish Success / Rework / Qualified Signal / Commercial Progression` 后，再通过 Cross-Repository Workstream Gate 决定是否将当前 `X-SuperPlay-ContentOps` 提升为 WS-008 Runtime 的独立实现事实源。

---

# 十二、Easel 上游策略：现在 Clone，验证后再决定 Fork

当前阶段是 Easel 适配与运行验证，还没有证据证明必须长期维护一套 Easel 核心分支。因此默认策略是：

> **先 Clone，不 Fork。只有实验确认需要持续修改 Easel Core 时，才建立 downstream。**

| 阶段 | 仓库策略 |
|---|---|
| 运行和评估 Easel | Clone 官方仓库，固定 commit |
| 添加配置、Profile、Skill、OPC Adapter | 作为 Easel 外部扩展维护，不改上游核心 |
| 发现可普遍修复的问题 | 优先向 Easel 上游提交 PR |
| 必须长期修改 Easel Core | 经决策 Gate 后建立 Fork 或 downstream |
| 二开包含商业逻辑且不能公开 | 使用独立私有 downstream，不创建公开 Fork |

Clone 是本地取用上游代码，不代表维护自己的 Easel 版本。Fork 则建立与上游关联的 GitHub 仓库，需要承担持续同步和冲突处理成本。GitHub 文档说明 Fork 不能独立更改可见性，公开上游转为私有后已有公开 Fork 仍保持公开；若 downstream 含商业 Workflow、客户逻辑、OPC 规则、私有平台 Adapter 或运营策略，应先确认仓库可见性和保密要求。[GitHub Forks 文档](https://docs.github.com/en/pull-requests/reference/forks)

## 12.1 锁定单一、可复现的上游版本

实验不能跟随 `main` 漂移。保存 `repository`、完整 commit SHA、版本、记录日期、运行环境和各平台兼容状态。新增材料推荐的候选 SHA [`4b9c03cf2129b6155595b66fc1e604546a3aa4ad`](https://github.com/ZJU-REAL/Easel/commit/4b9c03cf2129b6155595b66fc1e604546a3aa4ad) 已核实存在，提交时间为 2026-09-30；它与原有 `v0.2.1` tag 指向的 `3fe2d9904c1619281ef57f81d9ee0b7854998399` 是两个不同 commit。因此 `4b9...` 只能标记为该日期的 commit snapshot，不能误标成 `v0.2.1`。开始实验前由 Decision Record 选定其中一个作为**唯一实验 pin**，写入 `integrations/easel/UPSTREAMS.lock`；若来源或目标版本未确定，不运行实验。

Clone 并固定版本的基本操作：

```bash
git clone https://github.com/ZJU-REAL/Easel.git
cd Easel
git checkout --detach 4b9c03cf2129b6155595b66fc1e604546a3aa4ad
git rev-parse HEAD
```

最后一条命令必须与锁文件的 40 位 commit 完全相同。不要把 `main` 当作可复现版本。

示例：

```yaml
easel:
  repository: ZJU-REAL/Easel
  candidate:
    commit: 4b9c03cf2129b6155595b66fc1e604546a3aa4ad
    recorded_at: 2026-10-01
    decision: pending
  previous:
    commit: null
  update_policy:
    cadence: biweekly
    auto_merge: false
    human_review: true
  compatibility:
    windows: pending
    openclaw: pending
    content_generation: pending
    douyin: pending
    xiaohongshu: pending
    bilibili: pending
```

Compatibility 必须按真实执行记录填写；不能把计划测试或上游宣称改写成 `tested`。

## 12.2 优先做 Overlay，避免 Fork Tax

尽量让 Easel 保持接近官方版本。Profile、Skill、Adapter、Workflow、字段映射和 OPC 规则应放在 Easel 外部，通过受支持接口组合，而不要散落修改 `web/`、`core/`、`skills/`、Gateway 或发布实现。这样上游升级时，自有逻辑不需要逐文件重放，也便于把修改作为独立能力验证。

本报告前文仍将 `X-SuperPlay-Strategy / WS-008` 作为当前实现事实源。因此，在 Cross-Repository Workstream Gate 批准独立 Runtime 前，新增的可执行 Adapter/Skill 应按 Strategy 的治理登记；本仓库先保存决策、锁定规则和评估证据，不因目录建议而提前宣布 Runtime 所有权已经迁移。

适配层的参考目录可为：

```text
integrations/easel/
  README.md
  UPSTREAMS.lock
  config/
  mapping.yaml
skills/
  opc-source-to-content/
  xsuperplay-topic-router/
  evidence-preservation/
adapters/
  douyin/
  xhs/
  bilibili/
profiles/
  X-SuperPlay-1024/
  X-SuperPlay-Future-Intelligence/
```

该目录是方案示例，实施位置仍由 WS-008 当前仓库治理决定。

## 12.3 只有 Core 修改不可避免时才维护 downstream

若实验结果证明必须长期修改 Easel Core，再建立标准 upstream/downstream 关系。公开修改可评估 GitHub Fork：`origin` 指向自己的 fork，`upstream` 指向 `ZJU-REAL/Easel`：

```bash
git remote add upstream https://github.com/ZJU-REAL/Easel.git
git remote -v
```

若改动不能公开，则建独立私有仓库，保留 Git 历史并设置 `origin` 为私有 downstream、`upstream` 为官方仓库。不要先创建公开 Fork 再试图转私有：

```bash
git remote rename origin upstream
git remote add origin <private-downstream-url>
git remote -v
```

Easel 使用 Apache-2.0；对外分发衍生版本时，应保留许可证及适用的版权/归属通知，并对修改文件作显著修改说明。[Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0.html) 内部评估不等于可以忽略分发义务。

## 12.4 用受控升级分支同步上游

不要直接 `git pull upstream main` 后把结果送进生产分支。每两周检查一次，或在确有功能、安全修复、兼容性问题时提前检查：

```bash
git fetch upstream
git log HEAD..upstream/main --oneline
git diff HEAD..upstream/main
git checkout -b chore/upstream-sync-2026-10
git merge --no-ff upstream/main
```

先审查新功能、Bug 修复、Breaking Change 和对自有改动的影响，再创建类似 `chore/upstream-sync-2026-10` 的升级分支。运行兼容性测试，通过后经 PR 合并；失败则 Hold，不绕过 Gate。更新分三级：无关变化 `IGNORE`；有价值但不紧急 `NEXT_UPGRADE_WINDOW`；影响安全、OpenClaw/Windows 兼容或生产关键 Skill 的变化 `UPGRADE_CANDIDATE`。

最低兼容性检查应覆盖安装、`easel doctor`、Gateway、LLM、Profile、Source 到 Master Content、三个 Active 平台适配、Quality Gate 和 outputs 归档。发布仍必须保留 Human Approval、可追溯回执及失败关闭行为。

## 当前仓库策略

```text
现在：Clone + 固定 SHA + 真实 Source 实验
扩展：先 Overlay，避免修改 Easel Core
晋级：实验过 Gate 后才迁移实现所有权
Core downstream：证明确有长期必要后再建
更新：定期检查，上游升级分支验证后合并
```

---

# 最终判断

你之前的思路容易走成：

```text
找 AI 视频项目
+ 找 TTS
+ 找剪辑
+ 找发布
+ 找热点
+ 用 n8n 串起来
```

现在应该改成：

```text
先确定唯一 Runtime：

Easel
   ↓
加入 OPC Governance Adapter
   ↓
统一 API
   ↓
需要时给 Easel 增加专门 Worker
   ↓
所有结果重新回 OPC
```

**所以目前我不会建议你重新从零写一套自媒体工作流。**

最值得立项的是：

> **WS-008 — OPC × Easel ContentOps Runtime Integration**

而不是“AI 自媒体工具集合”。

这也是目前 GitHub 调研结果中，和你 Blueprint 的 **Business → Content → Signal → Opportunity → Business** 闭环最吻合的一条路线。:chatgpt-content-reference{index="36"}

上游维护策略也以此为界：**现在 Clone，不 Fork；先证明 OPC Adapter 与真实生产价值，再决定是否长期维护 Easel Core 的 downstream。**

如果按你现在的仓库治理方式继续，下一步已经可以直接进入 **立项设计**：我建议直接把 `WS-008 × Easel` 拆成 Issue/PR 级别的目录设计、API Schema、7 个 OPC Skill、状态机、验收标准和两周实验计划，而不再继续停留在工具调研阶段。
