# ADR-WS008-ContentOps-Runtime

## Status

EXPERIMENT_REQUIRED

This is **not** an Adopt decision. The candidate has been screened but not validated.

## Date

2026-10-02

## Context

X-SuperPlay 当前在抖音、小红书、Bilibili 等平台拥有实际账号，当前平台职责为基线 4 条/周 + 1–2 个真实 Source Artifact。

现有执行仓库包括：

- `douyin-1024`
- `xhs-FA`
- `bilibili-matrix-skills`
- `shipinhao-matrix-skills`
- `gzh-Future-Intelligence`

经对 GitHub 上开源 Self-Media / ContentOps 项目调研，**ZJU-REAL/Easel** 是一个接近完整的"发现 → 策划 → 创作 → 发布 → 归因"工作流，已包含：

- CLI / Gateway / FastAPI Web Backend
- OpenClaw Agent Harness
- 抖音 / 小红书 / B站 / 视频号 / 公众号 / 知乎 / 快手 发布 Skill
- 视频生产、字幕、TTS、剪辑 Skill
- 质量门、风险扫描、人机协同
- 账号画像、评论洞察、内容复盘
- 指标回收

且 Easel 当前仍处于高速迭代期（2026-08-28 创建、2026-10-01 仍活跃，version 为 0.1.1，2026-09-15 发布）。

## Problem Statement

当前多平台生产是否存在：

1. 重复实现（多个仓库维护类似的 TTS / 字幕 / 视频 / 发布逻辑）
2. Founder handoff 摩擦（脚本分散在不同仓库）
3. 维护成本（每个平台一个仓库需要独立更新）
4. 治理风险（自动化 / 发布 / Claim 是否可追溯）

## Current Architecture

```
X-SuperPlay-Strategy
        ↓
┌───────┼──────────────┐
↓       ↓              ↓
douyin  xhs-FA        bilibili
repo    repo          repo
+ shipinhao + gzh
```

**Source of Truth 边界**：
- Strategy：平台组合 / Routing / Experiment / Metrics / Review
- Platform Repo：实际 Workflow / Skill / Production / Receipt
- OPC Blueprint：Opportunity / Offer / Revenue / Business Truth

## Candidate

ZJU-REAL/Easel (https://github.com/ZJU-REAL/Easel)

## Options Considered

### Option A — 保持现状
继续在 5 个独立执行仓库中维护各自的工作流。

**优点**：不引入新依赖，治理边界清晰，平台间隔离。
**缺点**：重复实现、Founder 工时高、维护成本高、Skill 难以跨平台复用。

### Option B — Easel 仅作为公共 Skill Provider
Easel 安装为外部 Skill 来源，但 Strategy 仍是中央决策层，平台 repo 仍为执行源。

**优点**：保留现有 SoT 边界，复用 Easel Skill。
**缺点**：当前 OpenClaw 跨项目复用方式 — 与现有仓库结构兼容性未验证。

### Option C — Easel 作为 Common Runtime，平台 repo 做 Adapter
新建 `X-SuperPlay-ContentOps` 作为唯一 V1 Runtime，Easel 作为 Core，5 个旧仓库停止开发。

**优点**：统一 Runtime、Skill 复用高、Founder 时间预算降低。
**缺点**：破坏现有 SoT 边界、引入 OpenClaw 依赖、Easel 高速变化存在稳定性风险。

### Option D — Easel 仅用于借鉴，不成为依赖
读 Easel 架构与 Skill 设计，自己写 ContentOps。

**优点**：完全自主控制。
**缺点**：高开发成本、错过上游社区维护红利。

## Current Decision

**EXPERIMENT_REQUIRED**

采用 Option C 作为假设，但在两周实验（EXP-WS008-EASEL-001）前 **不宣布** Easel 为正式架构。

## Evidence Required

两周实验结束前需要的真实数据：

| 指标 | Baseline | Easel 实验 | 目的 |
|---|---:|---:|---|
| Founder Minutes | 待测 | 待测 | 最重要 |
| Wall-clock Time | 待测 | 待测 | 整体耗时 |
| Manual Handoffs | 待测 | 待测 | 搬运次数 |
| Rework Rounds | 待测 | 待测 | 返工 |
| Failed Steps | 待测 | 待测 | 稳定性 |
| Platform-native QC | 待测 | 待测 | 是否适配平台 |
| Claim/Source Preservation | 待测 | 待测 | OPC 证据安全 |
| Human Approval preserved | 待测 | 待测 | 治理 |
| Publication Receipt | 待测 | 待测 | 可审计 |
| Metrics ingestion | 待测 | 待测 | 是否形成闭环 |
| New reusable assets | 待测 | 待测 | 是否复利 |

## Acceptance Criteria

### Hard Gate（任一失败 → 不得成为 Common Runtime）

- Human Approval 没有被绕过
- Source / Claim 可以追溯
- Credentials 不进入 Git
- Publication Receipt 可记录
- Failure 可以 fail closed
- 现有三个 Active Platform 至少可以接入

### Efficiency Gate

| 指标 | 目标 |
|---|---|
| Published throughput | >= 当前 baseline |
| Founder Minutes | 下降 >= 25% |
| Manual Handoff | 下降 >= 30% |
| Required Record Completeness | = 100% |
| 严重 Governance Incident | = 0 |

## Possible Outcomes

| 实验结果 | 决策 |
|---|---|
| 全链路明显优于当前 | COMMON_RUNTIME_CANDIDATE |
| 创作强、发布弱 | PRODUCTION_ENGINE_ONLY |
| 某个平台特别强 | PLATFORM_SPECIFIC_ADAPTER |
| 没明显节约 Founder 时间 | REFERENCE_ONLY |

## Rollback Plan

两周实验期间 / 之后任何时点：

- 5 个旧执行仓库（`douyin-1024` / `xhs-FA` / `bilibili-matrix-skills` / `shipinhao-matrix-skills` / `gzh-Future-Intelligence`）保持完全可运行
- Easel 实验环境与方案在 `01-Experiments/EXP-WS008-EASEL-001/` 隔离
- 不修改 Strategy 中已登记的注册表
- 实验失败 → 旧仓库继续作为执行事实源

## V1 Runtime 状态机

OPC ContentOps API（`POST /v1/content-runs`）内部流转：

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

13 个状态，每个状态都对应可记录的 Receipt。

## 候选 OPC Skill 清单（仅在实验证据证明需要后才实现）

```text
opc-source-ingest            # 真实 Source Artifact 接入
opc-evidence-extractor       # 从 Source 抽取 Evidence
opc-topic-ranker             # 按 OPC 标准对选题排序
opc-claim-permission-gate    # Claim Boundary + Permission 检查
opc-content-record-writer    # 写 ContentRecord 关联 Source/Claim
opc-signal-classifier        # 评论/DM 分类为 PD0–PD7 信号
opc-weekly-business-review   # 每周商业复盘
```

**P0 不预写**。只有在 EXP-WS008-EASEL-001 证明确实需要时，按必要性逐个落地。

## n8n 定位

n8n **只** 负责：

- 定时触发（cron）
- Webhook 接收
- 重试 / 失败通知
- 人工审批通知

n8n **不** 负责：

- 经营判断
- 选题排序
- Claim / Permission 决策
- 内容生产调度

经营逻辑在 OPC ContentOps API 与 Easel / OpenClaw Runtime 中实现，n8n 不进入 SoT 链路。

## Decision Owner

Founder

## Review Date

实验结束后两周（约 2026-10-16）

## Links

- Research: `OPC-Easel-ContentOps-Research-to-Decision-Experiment.md`
- Experiment: `01-Experiments/EXP-WS008-EASEL-001/`
- V1 Runtime Plan: `02-Runtime/v1/README.md`