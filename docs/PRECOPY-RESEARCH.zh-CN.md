---
translation_of: docs/PRECOPY-RESEARCH.md
language: zh-CN
translation_status: synced
---

# 写文案前的预研契约

[English](PRECOPY-RESEARCH.md) | [简体中文](PRECOPY-RESEARCH.zh-CN.md)

> 契约 `contentops.precopy-research/v1`。只记录已核实事实。
>
> 最后验证：2026-11-12，`main` 的 `c1da6dd`。

## 为什么要有这一环

`AGENTS.md` 要求 **Evidence before Claim（证据先于断言）**。这份签署式预研契约用于
防止 VIDEO 文案和共享 `TOPIC` 在来源未核实时进入生产。单独的 GRAPHIC_TEXT 文章
可以先起草：保留事实来源链接，未核实的内容标记待查。图片权利和生图授权仍是独立检查。

契约覆盖 VIDEO（`script/master.md`）与共享 TOPIC 研究；单独 GRAPHIC_TEXT 草稿
（`02_draft/draft.md`）不需要先拿到预研签字。它不是第三条产线，也不新增账号或平台。

相关文档：[CONTENT-LIFECYCLE-STAGES.md](CONTENT-LIFECYCLE-STAGES.md)、
[RUNBOOK.md](RUNBOOK.md)、[TEST-PLAN.md](TEST-PLAN.md)。

## 契约产物

| 产物 | 必须包含 | 机器校验 |
|---|---|---|
| `00_preresearch/content-intent.json` | 本次预研所服务的、router 产出的 `contentops.content-intent/v1` 文档，逐字拷贝 | `schema` 匹配；`route_mode` ∈ {`USER_TOPIC`、`HOTSPOT_DISCOVERY`}；`topic`、`account_id`、`account_profile_version` 非空；`route_context.topic_origin` 与模式一致；`HOTSPOT_DISCOVERY` 还必须有 `candidate_id` 与 `search_plan_id` |
| `00_preresearch/project-reading.md` | 实际读了本仓库哪些文件、从中得到哪些事实，附路径与行号 | 有章节标题、达到最小长度、至少 3 个不同的仓库内路径 |
| `00_preresearch/outline.md` | 在写正式文案之前先产出大纲 / 手册 | 至少 3 条大纲项或标题、达到最小长度 |
| `00_preresearch/evidence-list.json` | 可追溯、可打开的权威信源，按类型分级 | 至少 3 条；每条需 `id`、`title`、`kind`（`primary` / `official` / `interpretation`）与 `http(s)://` 或 `repo://` URL；至少一条 `primary` 或 `official` |
| `00_preresearch/boundary.md` | 诚实边界：核实了什么、没核实什么、本阶段不产出什么 | 必须写明 `production_ready: false` 与 `publish_authorized: false` |
| `receipts/precopy-research.json` | 绑定指纹的人工签字 | `status: APPROVED`、具名 `reviewer`、书面 `opinion`、`approved_at`、`artifacts_sha256` |

指纹是对五份产物按标签拼接后的字节做 SHA-256。签字后改动任何一份产物都会报 `STALE`；没有强制开关，也不会自动重新批准。

## 选题从哪来

预研环节不发明选题，也不接受手写选题。它消费 router 已经产出的 `ContentIntent`，这正是两条入口在此汇合、而不是在文案处汇合的原因：

| 入口 | `route_mode` | `route_context.topic_origin` | intent 必须额外携带的来源 |
|---|---|---|---|
| 用户指定主题 | `USER_TOPIC` | `USER_INPUT` | — |
| 从热点探查中选定 | `HOTSPOT_DISCOVERY` | `HOTSPOT_SELECTION` | `candidate_id`、`search_plan_id` |

两种模式产出的都是同一个 `contentops.content-intent/v1` 形状，因此本门禁之后的下游，除了读 `route_context` 之外无法分辨走了哪条入口。`HOTSPOT_DISCOVERY` 在预研前多一道人工决策（`CANDIDATES_READY → TOPIC_SELECTED`），但两条入口都不能跳过预研：它们都抵达 `EVIDENCE_REQUIRED`，而 `BRIEF_READY` 只能经由本门禁到达。

绑定靠两处强制：

- `scripts/preresearch.py intent` 把 `00_brief/brief.json` 里的 `intent` 对象拷进 `00_preresearch/content-intent.json`。这是产生该产物的唯一受支持方式：没有 brief 时拒绝（`NO_ROUTED_INTENT`），已经批准时也拒绝（`ALREADY_APPROVED`）。
- `00_brief/brief.json` 存在时，`check` 要求预研里的这份 intent 与之逐字一致。因此把同一个项目改路由到另一个主题，门禁会自己变红，而不必动那份已签字的回执。

## 操作流程

```powershell
# 1. 生成四份文字产物骨架（不覆盖已有文件）
python scripts\preresearch.py init --project projects\my-video

# 2. 绑定 router 为这个项目产出的 intent
python scripts\preresearch.py intent --project projects\my-video

# 3. 通读项目、核实信源，填好大纲、证据清单与边界声明

# 4. 检查整套产物。返回 4 表示 BLOCKED
python scripts\preresearch.py check --project projects\my-video

# 5. 由具名人签字。--confirm 必填，没有 --force
python scripts\preresearch.py approve --project projects\my-video `
  --reviewer "你的名字" --opinion "已看过 diff 并核对来源" --confirm
```

此后才允许写文案并做文案审核：

```powershell
python scripts\copy_review.py projects\my-video --approve `
  --reviewer "你的名字" --opinion "已核对旁白" --confirm
python scripts\make_content.py check --project projects\my-video
```

## 门禁生效点

| 生效点 | 行为 |
|---|---|
| `scripts/production_gates.py` — VIDEO 第 8 门 | VIDEO 的 `make_content.py check` / `run` 和生产调用会在预研未完成时阻断；单独 GRAPHIC_TEXT 没有写前预研门禁 |
| `scripts/copy_review.py --approve` | VIDEO 需当前预研；共享 TOPIC 消费者校验已绑定的主题包；单独 GRAPHIC_TEXT 可直接记录文案审核，不再要求第二份预研签字 |
| `scripts/preresearch.py` | `init` / `intent` / `check` / `status` / `approve`；被挡时退出码 4 |

直接调用 `m5_production.py` / `produce_video.py` 仍属**诊断路径**，原本就不经过门禁，本契约不改变这一边界，也不新增发布步骤。

## 状态

| 状态 | 含义 |
|---|---|
| `NOT_STARTED` | 所有产物都缺，等于还没开始 |
| `INCOMPLETE` | 缺少部分产物，或内容不合格（未绑定 intent、证据清单为空、缺边界声明、仓库路径不足等） |
| `AWAITING_APPROVAL` | 产物合格，还没有具名人工签字 |
| `INVALID_RECEIPT` | 回执不是 `APPROVED`，或缺具名审核人 / 书面理由 |
| `STALE` | 批准后改动了产物；需重新 check 并 approve |
| `APPROVED` | 仅对文案工作放行 |

## 诚实边界

- 预研批准**不等于**文案批准、生产批准或发布许可；两份回执都保持
  `production_ready: false` 与 `publish_authorized: false`。
- `init` 生成的骨架本身无法通过：此时还没有 intent，证据清单为空，通读记录带 `TODO`；占位 URL 会被拒绝。
- AI 生成的图 / 视频只是视觉辅助，永不承担事实举证。
- VIDEO 和共享 TOPIC 项目没有预研包时，预检仍会报告 `NOT_STARTED` / `INCOMPLETE`。
  单独 GRAPHIC_TEXT 的起草和文案审核不需要这份签字；来源链接和逐图权利仍须核验。

## 验证

`tests/test_precopy_research.py`（26 个用例）覆盖产物缺失、骨架拒绝、`init`
幂等、两条入口的 intent 绑定、改路由失效、证据与边界校验、具名审核人要求、
VIDEO 缺预研时拒绝文案审核，以及单独 GRAPHIC_TEXT 可审核文案。该套件已在
`.github/workflows/ci.yml` 具名注册。
