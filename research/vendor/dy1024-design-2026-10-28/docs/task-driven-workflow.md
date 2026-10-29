---
status: archived
canonical: false
issue: "#34"
date: 2026-10-28
source: dy_x1024@a5952a44dbf47d44c1a4bf475e3653b542c25ac1
---

# 任务驱动的工作—验证—内容闭环

<!-- CURRENT_WORKFLOW_CONTRACT
contract=canonical-copy-to-video-v2
stage_count=13
stages=brief,research,script,review,audio,visual_plan,visual_route,assets_plan,assets,media_generation,edit_render,quality,delivery
artifacts=00_brief/brief.json,01_research/claims.json,02_script/script.json,02_script/review.json,03_audio/audio-handoff.json,04_visual/visual-plan.json,04_visual/visual-route.json,04_visual/director-material-plan.json,05_assets/asset-ledger.json,05_assets/media-generation-receipt.json,06_edit/master-timeline.json,07_quality/quality-report.json,08_delivery/delivery-manifest.json
statuses=approved,blocked,pending,ready_for_review,running
-->

```yaml
schema_version: 1
status: proposed_for_generalization
account: X•超玩1024
scope: 以真实任务完成为主线，视频是过程证据和复盘输出，不是先验目标
topic_selection: deferred_until_task_context_and_user_confirmation
episode_count: derived_from_unclosed_task_units
```

## 1. 核心原则

工作流的最小单位不是“一个视频选题”，而是一个要被推进到验收状态的真实任务：

```text
真实任务
→ 受众/使用者进展
→ 任务拆解
→ 能力假设
→ GitHub 项目测评
→ 在任务中应用
→ 结果与边界
→ OPC 可行性判断
→ 过程/结果内容
→ 下一任务
```

内容不能反向制造任务。没有真实输入、改变变量、运行证据和验收标准，只能记为研究假设或工作日志，不能包装成 Before/After。

这不是一次性的内容项目，而是持续更新的任务台账：任务可以新增、拆分、重开、暂停或转入下一任务；每次更新都必须保留当前状态、未闭合单元、证据和下一步。视频生产服从这份任务台账，最终目的不是积累视频数量，而是让真实任务逐步达到可交付、可复用、可报价并最终落地 OPC 的状态。

## 2. 任务工作项状态机

```text
backlog
  → shaped
  → ready
  → evaluating
  → applied
  → evidence_ready
  → accepted
       ├→ promoted_to_opc
       ├→ rework
       ├→ paused
       └→ stopped
```

### 每个状态的含义

| 状态 | 必须回答的问题 | 允许动作 |
|---|---|---|
| `backlog` | 发生了什么问题或机会？ | 记录来源，不选题、不接单 |
| `shaped` | 谁要取得什么进展？期望状态是什么？ | 拆任务、写非目标和 Stop 条件 |
| `ready` | 输入、权限、验收和容量是否齐全？ | 批准进入测评 |
| `evaluating` | 哪些 GitHub 项目/方案可能解决哪一个任务单元？ | 安装、复现、对照、记录失败 |
| `applied` | 能力是否迁移到自己的真实任务？ | 集成、运行、人工接管、回滚 |
| `evidence_ready` | 结果是否可回放、可解释、可脱敏？ | 生成证据包和内容记录 |
| `accepted` | 任务是否达到约定验收？ | 进入 OPC 判断或下一任务 |
| `promoted_to_opc` | 是否有可边界化需求、付费/验收信号和合规条件？ | 进入报价、交付或实验 |

状态不可通过改布尔字段前移；缺权限、缺结果、缺验收或缺隐私审查时保持 `blocked/rework/paused`。

## 3. 从人群到任务，不从人群直接跳到选题

当前三类受众是任务路由的工作假设：

1. **AI 能力判断者**：要判断某个能力是否值得投入；
2. **AI 任务迁移者**：要判断能力能迁移到真实任务哪一步、人工保留哪一步；
3. **AI 机会验证者**：要判断任务是否能形成有边界的服务、交付和付费。

开始一个新工作项时，先填写：

- 当前任务和触发场景；
- 当前状态与期望状态；
- 任务使用者/买方；
- 主要进展（只能选一个 primary audience）；
- 已有替代方案、阻断点和反对意见；
- 验收标准、隐私/授权/雇佣边界和容量上限。

受众分群不是内容类型，也不自动决定视频形式。没有直接受众证据时标记为 `exploratory`，不把模型推测写成已验证需求。

## 4. 任务拆解与复杂度

### 4.1 任务单元

每个任务至少拆成以下字段：

```text
task_unit_id
current_state
desired_state
input_and_access
capability_required
candidate_solution
operation_to_run
evidence_required
acceptance_criteria
failure_boundary
owner_and_dependency
```

### 4.2 内容期数由任务复杂度决定

| 复杂度 | 识别方式 | 执行方式 | 内容处理 |
|---|---|---|---|
| `simple` | 一个任务单元、一个主要未知、一次可复现验收 | 一个项目/方案即可验证时才使用 | 可能形成一条内容，也可能不做公开内容 |
| `multi_step` | 多个依赖单元，至少一个中间验收 | 逐单元测评、应用、复盘 | 每个不可合并的状态变化可形成一期；期数不预设 |
| `system` | 涉及数据、权限、可靠性、评测、运营或商业验收 | 分里程碑和多项目组合验证 | 只记录已闭合里程碑；未闭合链路不得剪成完整案例 |

“一期”不是任务边界。任务没有闭合，就继续工作；任务闭合但没有受众价值或权限，也可以不发布。

## 5. GitHub 项目如何进入任务

GitHub 项目不是内容素材库，而是能力候选。每个候选必须绑定一个任务单元，按以下顺序处理：

```text
候选发现
→ 许可证/权限核验
→ 环境与成本核验
→ 最小复现
→ 失败定位
→ 能力评分与适用边界
→ 迁移到真实任务
→ 结果/回滚/验收
```

候选评估至少记录：

- 解决的具体任务单元；
- README、源码、Issue、Discussion、Release 或 commit 的来源；
- License、数据/模型/API 权利和隐私要求；
- 安装、硬件、成本、运行时间和维护负担；
- 最小复现结果与首个失败；
- 相比现有方案改变了什么；
- 能否迁移到当前任务；
- 是否产生可交付、可复用或可报价的结果。

Star、Fork、热榜只作为发现信号，不作为能力成立、市场需求或 OPC 变现证据。

## 6. OPC 判断必须在应用和验收之后

完成一个能力测评不等于有生意。只有在真实任务中产生以下证据，才进入 OPC 判断：

```text
真实问题
→ 目标买方/使用者
→ 有界 Scope
→ 可核验 Payment/Interest/Acceptance 信号
→ Founder/IP/隐私/容量 Gate
→ 交付与复盘
```

允许的结果包括：

- `not_ready`：只有技术能力，没有真实需求或验收；
- `research_candidate`：能力和任务匹配，但还需要真实场景；
- `bounded_offer_candidate`：可写 Scope、价格/成本、验收和支持边界；
- `active_experiment`：已获批准进入当前 Stage 实验；
- `promoted`：达到对应 Stage/Offer 的证据门槛。

“能力很好”不能直接升级为收入、Offer、Stage 或 Productized。

## 7. 内容是任务证据的派生层

本项目采用以 OPC 落地为目标的选择性 Building in Public：公开可复用的任务切片、实现过程、失败边界和学习结果，但不公开可反推出 OPC 核心商业策略的完整信息。详细披露分级和审核契约见 [`building-in-public-and-disclosure.md`](building-in-public-and-disclosure.md)。

### 7.1 内容触发条件

只有以下事件之一发生，才考虑生成内容记录：

- 一个任务单元从失败到可运行；
- 一个能力在真实任务中被验证或被否定；
- 一个中间验收揭示了新的问题；
- 一个失败边界可复用于下一任务；
- 一个任务形成了经授权的 public-safe Proof；
- 一个真实买方/使用者反馈改变了下一步。

### 7.2 内容记录最小结构

```text
任务背景
→ 当前状态
→ 本轮要验证的能力
→ GitHub/方案候选与条件
→ 实际操作与失败
→ 应用后的结果
→ 验收与局限
→ 对当前受众的意义
→ 下一任务
```

标题、Hook、时长和平台适配放在任务证据之后，由人工确认；不提前规定“这一定要做成几期”。

文案、字幕、画面、代码片段、截图、日志、评论回复和外链都必须经过 Founder 的公开披露审核；没有 `approved_public_safe`，不得进入发布路线。

## 8. 与现有 V2 视频主链的关系

任务工作项是 13 阶段 canonical V2 视频主链的上游输入，不替代它：

```text
Task Intake / Task Graph / Capability Evaluation / Application Receipt
→ Brief
→ Research
→ Script
→ Review
→ Audio
→ Visual Plan
→ Visual Route
→ Assets Plan
→ Assets
→ Media Generation
→ Edit & Render
→ Quality
→ Delivery
```

如果任务仍在 `evaluating` 或 `applied`，可以保留研究/工作记录，但不能进入“结果型成片”口径。只有 `evidence_ready` 或明确声明“过程记录/未完成边界”时，才进入内容生产。

## 9. 人工确认点

每个新任务至少在以下节点与 Founder 交互确认：

1. 任务是否真实、是否值得进入 `shaped`；
2. 主要受众和期望进展是否正确；
3. 任务拆分是否足以验收；
4. GitHub 候选是否允许安装/运行；
5. 是否允许把结果迁移到真实工作；
6. 是否满足隐私、雇佣、许可证和容量边界；
7. 哪些已经闭合、哪些仍应继续，不由系统替 Founder 决定是否做视频。

## 10. 失败和停止规则

- 项目能安装但不能证明任务价值：停在 `evaluating`；
- 能力成立但无法迁移到真实任务：记录为 `not_fit`，不要剪成成功案例；
- 任务可迁移但没有权限/验收/容量：`paused`；
- 任务反复失败且成本超出 appetite：`stopped` 或重新塑形；
- 只剩观点、热度或 Star：回到 `backlog`，不进入生产；
- 内容制作开始吞噬任务完成时间：暂停内容，不改变任务边界。
