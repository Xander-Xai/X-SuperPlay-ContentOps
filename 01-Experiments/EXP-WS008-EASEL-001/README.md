# EXP-WS008-EASEL-001

## Title

Easel Runtime Fit Evaluation

## Status

Queued

## Hypothesis

ZJU-REAL/Easel 可以作为 X-SuperPlay ContentOps 的 Common Runtime，同时不破坏现有：

- Business / Evidence / Permission / Commercial Source of Truth
- 平台组合与 Routing 决策
- Human Approval 治理
- Claim / Source 追溯链

并能降低 Founder 内容工时（至少 25%）。

## Type

Runtime Fit Evaluation (技术假设验证，不验证选题)

## Period

2026-10-02 → 2026-10-16（约两周）

## Pinned Dependencies

```yaml
easel:
  repo: ZJU-REAL/Easel
  version: 0.1.1
  release_date: 2026-09-15
  commit: <待 Day 0 填入>
python: <待填>
node: <待填>
os: Windows 11
```

⚠️ 不追 main。每天开工前确认没有上游 commit 改动。

## Experimental Design

### Day 0 — 环境冻结

- [ ] 安装并锁定 Easel 0.1.1 commit SHA
- [ ] 记录 Python / Node / OS 版本
- [ ] 创建 `02-Runtime/v1/` 工作目录
- [ ] 配置 OpenClaw + Easel 启动
- [ ] 完成 smoke test：Easel Web UI 可访问

### Day 1–2 — 第 1 个 Source Artifact

**Source 选择**：从近期已完成真实工作的项目中选 1 个，例如：

- Easel 实测
- Agent Motion 实测
- Pixelle Video 实测
- 数字人 API 实测
- 某个 GitHub AI 项目实测

**准备 5 类素材**：

1. 项目 GitHub 页面截图
2. README / 架构关键截图
3. 真实运行过程屏幕录制
4. 最终生成结果
5. 你自己的优缺点结论

**执行**：使用 `02-Runtime/v1/templates/short-video-v1.md` 中定义的 Master Workflow Prompt。

**主要回答**：

- Easel 能否完成 `Source → Asset → final.mp4` 全链路？
- 哪个环节 friction 最大？

### Day 3–4 — 抖音适配

- [ ] 生成 1 条 60s 抖音视频
- [ ] 记录 Founder Minutes / Handoff / Rework
- [ ] 是否优于/等于现有 `douyin-1024` workflow

### Day 5–6 — 小红书适配

- [ ] 生成 1 条小红书卡片 + 视频
- [ ] 记录指标同上
- [ ] package / 卡片 / 发布是否成立

### Day 7 — 第一轮 Review

- [ ] 列出 Top 5 friction
- [ ] 决定 Week 2 是否继续 / 调整方向

### Week 2 — 再跑 2–3 个真实 Source

- [ ] 验证可重复性
- [ ] 累计 Founder Minutes 真实数据

### Day 14 — Founder Review

- [ ] 填写 `01-Experiments/EXP-WS008-EASEL-001/results/scorecard.md`
- [ ] 过 Hard Gate + Efficiency Gate
- [ ] 决策：Common Runtime / Production Engine Only / Platform-Specific Adapter / Reference Only

## Scorecard（不要看播放量）

| 维度 | 指标 | 当前 Workflow | Easel 实验 | 备注 |
|---|---|---|---|---|
| 效率 | Founder Minutes |  |  | 最重要 |
| 效率 | Wall-clock Time |  |  | 整体耗时 |
| 效率 | Manual Handoffs |  |  | 搬运次数 |
| 质量 | Rework Rounds |  |  | 返工 |
| 质量 | Failed Steps |  |  | 稳定性 |
| 适配 | Platform-native QC |  |  | 是否适配平台 |
| 治理 | Claim/Source Preservation |  |  | OPC 证据安全 |
| 治理 | Human Approval preserved |  |  | 治理 |
| 治理 | Publication Receipt |  |  | 可审计 |
| 闭环 | Metrics ingestion |  |  | 是否形成闭环 |
| 复利 | New reusable assets |  |  | 是否复利 |

## Stop Conditions

任一触发立即停止实验并 Reject：

- Human Approval 被绕过
- Source / Claim 追溯链断裂
- Credentials 进入 Git
- Publication Receipt 不可记录
- 三个 Active Platform 之一完全无法接入
- 严重 Governance Incident > 0

## Rollback

实验期间任何时点 → 切回 5 个旧仓库继续运行，零成本回滚。

## Possible Outcomes

| 结果 | 决策 |
|---|---|
| 全链路明显优于当前 | COMMON_RUNTIME_CANDIDATE |
| 创作强、发布弱 | PRODUCTION_ENGINE_ONLY |
| 某个平台特别强 | PLATFORM_SPECIFIC_ADAPTER |
| 没明显节约 Founder 时间 | REFERENCE_ONLY |

## Decision Owner

Founder

## Review Date

2026-10-16

## Out of Scope

本实验 **不** 验证：

- 播放量 / 涨粉 / ROI
- 选题策略
- AI 视频模型质量
- 全自动跨平台发布（仅 V1 验证生成 MP4，发布保持人工）
- Agent 自动晋级
- 其他 runtime（MPT / Postiz 等）

## Related

- ADR: `00-Governance/decisions/ADR-WS008-ContentOps-Runtime.md`
- Research: `OPC-Easel-ContentOps-Research-to-Decision-Experiment.md`
- V1 Plan: `02-Runtime/v1/README.md`
- V1 Master Workflow Prompt: `02-Runtime/v1/templates/short-video-v1.md`