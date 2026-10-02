# ADR-WS008-Presenter-Layer

## Status

**PROPOSED — 策略已定，未接入**

本 ADR 记录的是 **数字人在视频架构中的定位与 Provider 路由口径**，
不是 Provider 接入许可。任一 Provider 落地前须过 Pre-Code Gate。

## Date

2026-10-02

## Context

`douyin-1024` 的既有数字人调研（`docs/DIGITAL-HUMAN-PROVIDER-ANALYSIS.md`，2026-10-01）
已建立两条路线：

1. 照片数字人（LivePortrait / 百度照片数字人 / EMO）
2. 小样本克隆（百度曦灵 / HeyGen Digital Twin / D-ID）

但存在两个未解决的问题：

1. **架构定位问题**：既有设计默认"数字人 = 视频主体"，导致数字人质量成为整条视频的天花板。
2. **Provider 策略问题**：既有多份文档（`ai-provider-selection.md`、`HeyGen-Pricing-API-Guide.md`、
   `DIGITAL-HUMAN-PROVIDER-ANALYSIS.md`）各自记录了价格，但口径不一致，且没有统一的分档路由。

同时新识别出第三条技术路线（真人母版 + AI 改嘴），需要纳入分析框架。

## Decision

### D1 — 数字人定位为 Presenter Layer，不是主画面

数字人是 **Scene Asset**，不是 Video Pipeline。

| 维度 | 规定 |
|---|---|
| 画面占比 | 15 ~ 30%（主画面 70 ~ 85% 给内容） |
| 像素宽度 | 260 ~ 360 px（1080 宽的 24% ~ 33%） |
| 位置 | 左上 / 左侧中部；**避开右侧与底部** |
| 比例 | **3:4 优于 1:1** |
| 出现时长 | 仅占全片 **30% ~ 50%** |

**理由**：现有数字人方案的缺陷（唇形形变、牙齿糊、眨眼节奏、头部漂浮感、肩颈静止）
在 1080×1920 全屏后被无限放大。缩为小窗后观众注意力回到字幕与内容画面，
数字人质量可下降一个等级，整条视频的"高级感"反而上升。

### D2 — Provider 分工

| Provider | 定位 |
|---|---|
| **HeyGen API** | 自动化生产**主力** |
| **Google Vids** | 精品内容 / 人工增强，**不进自动化主链路** |
| **阿里云百炼 LivePortrait API** | 超低成本 **fallback**（草稿 / 小窗 / 降级） |
| **MuseTalk / LatentSync** | 真人母版 + AI 改嘴路线（本地 GPU） |

**排除 Google Vids 做主线的原因**：Google 未提供公开的 Vids 数字人生成 API；
仅 Drive API 可管理成片。UI 自动化（Playwright）在页面改版 / 验证码 / 风控下不可靠。

### D3 — 分档路由

```text
draft / test    → LivePortrait 或 HeyGen Avatar III
normal          → HeyGen Avatar IV
premium         → HeyGen Avatar V
manual-premium  → Google Vids（人工）
```

### D4 — 身份一致性：1 个 Digital Twin + 多个 Looks

禁止用多个免费账号轮流产生不同数字人。
同一自媒体账号应保持 **1 个 identity**，通过 Look 变化（背景 / 服装）区分场景。

**理由**：轮流换不同数字人会削弱 IP 识别、人设一致性、观众熟悉感与品牌记忆。
16 条/月 的规模下，Avatar IV 月成本约 **$25.76**，不值得为省这点钱牺牲 IP。

### D5 — 名称归属纠正

| 模型 | 作者 |
|---|---|
| LivePortrait | **快手 / KlingAI**（非阿里） |
| EMO | **阿里 Institute for Intelligent Computing** |

"阿里百炼 LivePortrait" 指 API 提供方，与模型作者不矛盾。

## Consequences

### 正面

- 数字人质量不再是整条视频的天花板，可用更便宜的 Provider
- Provider 可替换（统一 `PresenterProvider` 接口），不被单一供应商锁定
- 成本可预测：16 条/月 的实际数字人时长仅约 5.33 分钟
- 三条技术路线形成清晰升级阶梯

### 负面 / 风险

- 需要 compositor 支持叠加小窗（现有 V1 链路未验证）
- 真人母版路线需本地 GPU 与模型权重，增加环境复杂度
- LatentSync 1.6 在本机（RTX 5060 Ti 16GB）不可用，路线被限制在 1.5

## Open Questions（必须在接入前关闭）

| # | 问题 | 处理 |
|---|---|---|
| Q1 | 阿里云"数字人"停售（既有结论：不接）与阿里"百炼 LivePortrait API"是否同一产品线？ | **接入前必须确认**，疑似不同（智能媒体服务 vs Model Studio） |
| Q2 | HeyGen Avatar III/IV API 单价：$0.60 / $4 / $4.83 / $1 —— 哪个是当前口径？ | **以实际 API 账单为准** |
| Q3 | 本机 compositor 能否稳定做 1080×1920 小窗叠加？ | V1 链路验证 |
| Q4 | Google AI Pro 额度（25 次/月 AI Avatar）是否准确？ | 未核实 |

## Alternatives Considered

| 方案 | 否决原因 |
|---|---|
| 数字人全屏作为主画面 | 缺陷放大，质量成为天花板 |
| Google Vids 做自动化主线 | 无公开生成 API，UI 自动化不可靠 |
| 用 3 个免费账号轮流省额度 | 覆盖不了 16 条/月，且破坏 IP 一致性 |
| 立即接入 HeyGen API 主力 | 未过 Pre-Code Gate，且 benchmark 未做 |

## Evidence Required（才能从 PROPOSED 转为 ACCEPTED）

Provider Benchmark：用**同一个脚本 + 自己的脸 + 中文 + 自己的声音**跑：

```text
LivePortrait / HeyGen III / HeyGen IV / HeyGen V / Google Vids
```

评估 4 项：**嘴型 / 表情 / 动作 / 清晰度**，输出对比表。
表填完，D3 分档路由才算有证据支撑。

## Decision Owner

Founder

## Review Date

Provider Benchmark 完成后（无硬性日期，但应在首次接入 Provider 之前）

## Links

- Spec: `docs/PRESENTER-LAYER-SPEC.md`
- Routing: `docs/PRESENTER-PROVIDER-ROUTING.md`
- Provider Analysis: `docs/DIGITAL-HUMAN-PROVIDER-ANALYSIS.md`
- HeyGen Pricing: `docs/HeyGen-Pricing-API-Guide.md`
- Strategy: `00-Governance/douyin-1024-STRATEGY.md`
- Related ADR: `00-Governance/decisions/ADR-WS008-ContentOps-Runtime.md`
