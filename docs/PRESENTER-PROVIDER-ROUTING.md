# Presenter Provider Routing — 数字人 Provider 路由与成本模型

> **一句话结论**：
> **HeyGen API = 自动化生产主力 · Google Vids = 精品内容/人工增强 · 阿里云百炼 LivePortrait API = 超低成本 fallback**
>
> 整理日期：2026-10-02
> 来源：Founder 提供的 2026-10-02 调研整理（含官方链接引用）
> 状态：**部分价格条目存在冲突，见 §7，未经本地实测**

---

## 1. 分工定位

| 项目 | HeyGen | Google Vids |
|---|---|---|
| 数字人质量 | 高（Avatar IV / V） | 高（2026 版已升级） |
| 自定义本人数字人 | 强 | 已支持部分个人化能力 |
| 中文 | 支持 | 支持 |
| **API** | **有正式 API** | **无公开 Vids 数字人生成 API** |
| 自动化 | **非常适合** | 不适合无人值守 |
| 按量计费 | 可以 | 主要跟 Google AI 方案额度 |
| 每周稳定批产 | **适合** | 一般 |
| 精品人工制作 | 强 | **很适合** |
| 本项目定位 | **主力** | **补充 / 实验室** |

**判断依据**：本项目核心要求是 `API + 自动化 + 每周稳定更新`。

### Google Vids 为什么不做自动化主链路

Google Workspace 开发者平台目前提供 Drive / Gmail / Calendar / Meet 等 API，
**没有 Vids 的数字人生成 API**。Vids 成片可通过 Drive API 管理下载，
但"调用 API → 输入脚本 → 生成数字人"这一步没有公开接口。

理论上可用 Playwright / BrowserSkill / Computer Use 做 UI 自动化：

```text
Playwright → 自动登录 Google Vids → 点击生成
```

**不建议**，因为下面任一项都会让无人值守流水线挂掉：

```text
页面改版 / 按钮变化 / 验证码 / 账号风控 / 生成失败 / 额度提示
```

---

## 2. Presenter Router 分档策略

```text
Presenter Router

draft / test      → LivePortrait (阿里百炼) 或 HeyGen Avatar III
normal            → HeyGen Avatar IV
premium           → HeyGen Avatar V
manual-premium    → Google Vids（人工）
```

对应质量/成本档位（HeyGen API，截至 2026-09 官方口径）：

| 模型 | Digital Twin API | 用途建议 |
|---|---:|---|
| Avatar III | $0.60 / min | 低成本测试 / 内部预览 |
| Avatar IV | $4.83 / min | **日常正式发布（主力）** |
| Avatar V | $7.20 / min | 精品 / 品牌视频 |
| Avatar IV Photo | $2.31 / min | 照片数字人路径 |

> ⚠️ 上述单价与仓库既有 HeyGen 文档口径不一致，见 §7「冲突与待验证项」。

---

## 3. 阿里云百炼 LivePortrait API（超低成本 fallback）

现有官方托管 API 能力：

```text
人物图片 + 人声音频 → LivePortrait API → 异步生成数字人口播视频
```

| 项 | 值 |
|---|---|
| 价格 | ≈ $0.002868 / 秒 ≈ $0.17 / 分钟 |
| 换算 | ≈ ¥0.019 / 秒 ≈ ¥1.15 / 分钟 |
| 最长音频 | 3 分钟 |
| 并发 | **同时只能 1 个运行任务**，其余排队 |
| 地域 | 文档标注中国北京地域 |

**关键判断：API 化不解决画质。**

把同样的模型搬到云端 API，只会解决：

- 不用本地 GPU
- 自动提交任务 / 自动下载成片
- 超低成本

**不会解决嘴型、动作、表情、清晰度本身。**

因此定位为 **廉价 fallback / 草稿 / 小窗 / API 失败降级**，不承担品牌主数字人。

> 交叉印证：本仓库 `ai-provider-selection.md` 与 `docs/DIGITAL-HUMAN-PROVIDER-ANALYSIS.md`
> 记录的 LivePortrait 成本为 **¥0.02/秒 = ¥1.20/分钟**，与本节 $0.002868/秒换算结果一致 ✅

---

## 4. 身份一致性规则（重要）

### ❌ 不要做

```text
Google 账号 A → HeyGen Free → 数字人 A
Google 账号 B → HeyGen Free → 数字人 B
Google 账号 C → HeyGen Free → 数字人 C
随机轮流用
```

### ✅ 要做

```text
轩轩 AI 数字分身（1 个 identity）
        ├── Look A：科技办公室
        ├── Look B：深色背景
        ├── Look C：浅色背景
        ├── Look D：休闲装
        └── Look E：正式装
```

**身份保持一个，Look 可以变化。** 对自媒体 IP 识别、人设一致性、观众熟悉感、品牌记忆至关重要。

同一账号轮流出现 3 个不同数字人，会削弱以上全部。

### 为什么不靠免费账号省额度

| 项 | 数字 |
|---|---:|
| 3 个免费账号产出 | 约 3 × 3 = 9 条/月 |
| 实际需求（4 条/周） | 约 16 ~ 18 条/月 |
| 结论 | **覆盖不了** |

**HeyGen 网页免费额度 ≠ HeyGen API 免费额度。**
HeyGen 自 2026-02 起不再提供免费 API credits；API 为独立 Pay-As-You-Go。

---

## 5. 月度成本模型（真实口径）

假设：

```text
每周 4 条 × 4 周 = 16 条/月
每条 60 秒，数字人只出现 20 秒
→ 数字人总时长 ≈ 5.33 分钟/月
```

| 模型 | 月成本约 |
|---|---:|
| Avatar III | ≈ $3.20 |
| Avatar IV | ≈ $25.76 |
| Avatar V | ≈ $38.40 |

且这是 **16 条全部使用数字人** 的上限估算。

> **为了每月省二三十美元去维护 3 个账号、3 套身份和网页自动化，不划算。**
> 时间成本远高于 API 成本。

---

## 6. 双层内容系统

### A 层：稳定更新（每周 2 ~ 4 条）

```text
热点 / 项目 / AI 工具
        ↓ LLM 调研 → 选题评分 → 脚本 → TTS
        ↓ HeyGen Avatar IV API
        ↓ B-roll / GitHub / 网页 / 图片
        ↓ 字幕 → FFmpeg / Remotion
        ↓ 成片
```

目标不是影视级，而是 **稳定、有信息量、画面不廉价**。
数字人采用 15~30% 画面占比的小窗主持人（见 [PRESENTER-LAYER-SPEC.md](PRESENTER-LAYER-SPEC.md)）。

### B 层：精品内容（每周 0 ~ 2 条）

适用：深度项目调研 / AI 工具实测 / 架构讲解 / 热门事件分析 / 教程 / 观点型内容。

```text
Google Vids / Veo
    + HeyGen Avatar V
    + 高质量 B-roll
    + 动态图表
    + 人工检查
    + 剪映 / Remotion 精修
```

数字人只需在 **开头 5s + 中间 10s + 结尾 5s** 出现即可，其余交给内容画面。

---

## 7. 冲突与待验证项（必须实测后才能定稿）

| # | 项 | 冲突内容 | 处理 |
|---|---|---|---|
| 1 | HeyGen Avatar IV API 单价 | `$4/min`（Avatar IV guide 引用） vs `$4.83/min`（API pricing 引用） vs 本仓库 `HeyGen-Pricing-API-Guide.md` 记录的 `$4/min`（Digital Twin/Studio 1080p） | **待实测**，以实际 API 账单为准 |
| 2 | HeyGen Avatar III API 单价 | `$0.60/min`（新） vs `$1/min`（本仓库既有文档） | **待实测** |
| 3 | 阿里云数字人可用性 | 本仓库既有结论为"阿里云数字人**不接**"（2026-10-11 停止新购 / 2027 全面停止）；本次内容推荐阿里**百炼** LivePortrait API | **疑似不同产品线**（智能媒体服务数字人 vs 百炼 Model Studio 模型 API），**接入前必须先确认** |
| 4 | Google AI Pro 额度 | AI Avatar 最高 25 次/月、AI 视频片段最高 50 次/月、单条 ≤60 秒 | 未本地核实 |
| 5 | HeyGen 免费 API credits 终止 | 自 2026-02 起不再提供 | 未本地核实 |

> 遵循既有教训（`ai-provider-selection.md`）：
> **官方文档冲突时，以实际 API 测试为准。**

---

## 8. Provider Benchmark 计划

不采信"网上别人说哪个好"。用 **自己的脸 + 中文 + 自己的声音 + 自己的脚本** 跑同一条脚本。

```text
同一个脚本
        ├── LivePortrait
        ├── HeyGen Avatar III
        ├── HeyGen Avatar IV
        ├── HeyGen Avatar V
        └── Google Vids Avatar
```

只看 4 件事：

```text
嘴型 / 表情 / 动作 / 清晰度
```

输出表格：

| Provider | 唇形 | 表情 | 动作 | 清晰度 | 稳定性 |
|---|---:|---:|---:|---:|---:|
| LivePortrait | | | | | |
| HeyGen III | | | | | |
| HeyGen IV | | | | | |
| HeyGen V | | | | | |
| Google Vids | | | | | |

**只有这张表填完，§2 的路由档位才算有证据支撑。**

---

## 9. 目标架构

```text
                    选题 Agent
                        ↓
                    调研 Agent
                        ↓
                    Script Agent
                        ↓
                     分镜 Agent
                        ↓
              ┌─────────┴─────────┐
              ↓                   ↓
         Presenter             Main Visual
              ↓                   ↓
       Presenter Router       Visual Router
              ↓                   ↓
     ┌────────┼────────┐    ┌─────┼──────┐
     ↓        ↓        ↓    ↓     ↓      ↓
 Alibaba   HeyGen   Manual  Web   B-roll AI Video
LivePortrait API      ↓    Screenshot
              ↓    Google Vids
              │
              └──────────┬─────────┘
                         ↓
                    Compositor
                         ↓
               Subtitle / Music
                         ↓
                  Quality Gate
                         ↓
                    成片审核
                         ↓
                     发布
```

> 这样做的产物不是"数字人口播工具"，而是 **AI 自媒体视频工厂**，
> 数字人只是其中一个 `PresenterProvider`。

---

## 10. 边界声明

本文件是 **策略与路由口径落盘**，不是实现的开始。

- 不新增 Provider 集成代码（`00-Governance/douyin-1024-STRATEGY.md` §7）
- 不提前造抽象（`AGENTS.md` §1.7）
- 接入任一 Provider 前须过 **Pre-Code Gate**（`00-Governance/PRE-CODE-GATE.md`）
- 产出的 5 类资产（选题 / 脚本 / 分镜 / 素材 / 成片）仍受 `AGENTS.md` 内容真实性边界约束

---

## 11. 变更历史

| 日期 | 变更说明 |
|---|---|
| 2026-10-02 | 初始版本：Provider 分工、Presenter Router、成本模型、身份一致性、冲突清单、Benchmark 计划 |
