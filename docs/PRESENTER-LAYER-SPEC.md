# Presenter Layer Spec — 数字人画面规范

> **核心定义**：数字人不是"主画面"，而是 **Presenter Layer / 品牌人物层**。
> **核心结论**：数字人是一种 **Scene Asset**，不是整个 Video Pipeline。
>
> 整理日期：2026-10-02
> 来源：Founder 提供的 2026-10-02 调研整理（含官方链接引用）
> 状态：**策略规范已落盘，标注"待验证"的条目未经本地实测**

---

## 1. 为什么要把数字人降为"主持人层"

现有几个数字人方案（EMO / LivePortrait 等）的缺陷不只是分辨率：

| 缺陷 | 说明 |
|---|---|
| 唇形形变 | 嘴部结构在大幅运动时崩坏 |
| 牙齿模糊 | 细节无法还原 |
| 眨眼 / 表情节奏 | 不自然、节奏机械 |
| 头部漂浮感 | 头部运动与身体脱节 |
| 肩颈静止 | 或动作模式重复 |
| 长时观看 AI 感 | 累积暴露 |

**这些缺陷在 1080×1920 全屏后被无限放大。**

缩到小窗后，观众视觉注意力回到 **字幕 + 主画面信息**，上述瑕疵被显著弱化。

> 结果：**数字人质量可以下降一个等级，整条视频的"高级感"反而上升。**
> 观众不再盯着 AI 的嘴看，而是把它理解成"负责串场的虚拟主持人"。

---

## 2. 版式基线（1080 × 1920 竖屏）

**数字人宽度：260 ~ 360 px，即屏幕宽度的 24% ~ 33%。**

```text
┌───────────────────────┐
│                       │
│    产品图 / B-roll     │
│    网页 / GitHub       │
│    PPT / 代码 / 图表    │
│                       │
│  ┌─────┐              │
│  │数字人│              │
│  │主持人│              │
│  └─────┘              │
│                       │
│  █████ 重点字幕 █████   │
│                       │
└───────────────────────┘
```

### 位置规则

| 位置 | 判定 | 原因 |
|---|---|---|
| 左上 / 左侧中部 | ✅ 推荐 | 避开抖音右侧点赞 / 评论 / 头像 UI |
| 右侧 | ❌ | 与平台交互 UI 冲突 |
| 底部 | ❌ | 与字幕 / CTA 冲突 |

### 画面比例

```text
3:4  >  1:1
```

- **3:4**：可保留 头 + 肩 + 上半身 + 一点手部动作 → 小窗里像"主播"
- **1:1**：容易退化成"一颗会说话的头"

这与既有调研一致：EMO 的 1:1（512×512）与 3:4（512×704）中，3:4 更适合人物画面。

---

## 3. 出现节奏：数字人不必全程显示

**视频里数字人实际只出现 30% ~ 50% 时长。**

60 秒示例：

| 时间 | 画面 |
|---|---|
| 0–3s | 强 Hook + 主画面 |
| 3–10s | 小窗数字人出现 |
| 10–20s | 数字人消失，产品 / 网页 / B-roll 全屏 |
| 20–28s | 小窗数字人重新出现 |
| 28–45s | 录屏 / 案例 / 动态图 |
| 45–53s | 小窗数字人总结 |
| 53–60s | CTA + 数字人 |

即：**数字人实际出现 20 ~ 35 秒**。

对比"一个 AI 人站在右下角连续讲 60 秒"，自然得多。

---

## 4. 最终画面配比

| 占比 | 内容 |
|---|---|
| **70 ~ 85%** | 内容画面：GitHub / 网页 / 产品 / AI 图片 / AI 视频 / 录屏 / 动效 / 数据图 / 大字幕 |
| **15 ~ 30%** | 数字人（且只占全片 30 ~ 50% 时长） |

---

## 5. 与 compositor 的关系

数字人是 **Scene Asset**，由 compositor 合成进 1080×1920 成片：

```text
                  ┌→ B-roll
                  ├→ 网页录屏
Script → 分镜 Router ├→ AI 图片
                  ├→ AI 视频
                  ├→ 图表
                  └→ Presenter
                         ↓
                   数字人小窗
                         ↓
                     compositor
                         ↓
                  1080×1920 成片
```

**Presenter 只产出一个场景素材**（小窗视频 / 透明背景视频 / 静帧），
主链路（Script → Storyboard → Visuals → Compose → QC）保持不变。

可替换实现：LivePortrait / EMO / MuseTalk / LatentSync / HeyGen / D-ID / 真人视频，
全部只是 **`PresenterProvider`**。

Provider 选型与路由见 [PRESENTER-PROVIDER-ROUTING.md](PRESENTER-PROVIDER-ROUTING.md)。

---

## 6. 名称纠正（模型归属）

| 模型 | 模型作者 | 备注 |
|---|---|---|
| **LivePortrait** | **快手 / KlingAI 团队** | 不是阿里 |
| **EMO** | **阿里 Institute for Intelligent Computing** | — |

> **注意区分**：上面的"作者"指模型研发方。
> **阿里云百炼提供的是托管 API**（模型作者为快手），两者不矛盾。

本仓库既有文档中"阿里百炼 LivePortrait"指的是 **API 提供方**，此处补充的是 **模型作者**。

---

## 7. 落地优先级（不改变 V1 边界）

| 阶段 | 方案 | 前提 |
|---|---|---|
| 阶段一 · 马上落地 | EMO / LivePortrait → 3:4 → 缩到 260–360px → 小窗 | 先让 `douyin-1024` 跑起来 |
| 阶段二 · 最推荐 | 真人动作母版 + 声音克隆 / TTS → MuseTalk 1.5 自动 lip sync | 见 [DIGITAL-HUMAN-PROVIDER-ANALYSIS.md](DIGITAL-HUMAN-PROVIDER-ANALYSIS.md) 路线三 |
| 阶段三 · 商业化后 | 商业数字人 API 全屏（HeyGen Avatar IV / D-ID Full-HD V3 Pro） | 账号开始产生收入 |

**当前 V1 状态不变**：`02-Runtime/v1/README.md` 中"暂时不要用复杂数字人"仍然生效。
本文件是**规范与策略落盘**，不是接入许可；接入任一 Provider 前须过 Pre-Code Gate。

---

## 8. 与既有文档的关系

| 文档 | 关系 |
|---|---|
| [DIGITAL-HUMAN-PROVIDER-ANALYSIS.md](DIGITAL-HUMAN-PROVIDER-ANALYSIS.md) | Provider 能力与成本矩阵（含本文件新增的路线三） |
| [PRESENTER-PROVIDER-ROUTING.md](PRESENTER-PROVIDER-ROUTING.md) | 分档路由与月度成本模型 |
| [HeyGen-Pricing-API-Guide.md](HeyGen-Pricing-API-Guide.md) | HeyGen 计费与 API 接入口径 |
| `00-Governance/decisions/ADR-WS008-Presenter-Layer.md` | 本规范的决策记录 |

---

## 9. 变更历史

| 日期 | 变更说明 |
|---|---|
| 2026-10-02 | 初始版本：Presenter 层定义、版式基线、出现节奏、画面配比、模型归属纠正 |
