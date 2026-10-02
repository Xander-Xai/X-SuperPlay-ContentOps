# douyin-1024-STRATEGY.md — douyin-1024 项目战略定位

> **不要再问"怎么把 douyin-1024 做完整？"**
> **问"douyin-1024 还剩哪些东西值得我拥有？"**

---

## 1. 现状

- ✅ 13 阶段 canonical workflow 已设计
- ✅ Schema、gate、receipt、provider responsibility 齐全
- ✅ 审计、兼容、质量控制完善
- ✅ Fast Lane 已确立（不强制数字人/AI Video/高级 Provider）
- ❌ 真正的瓶颈：**还没持续发布过视频**

---

## 2. 核心转变

```
旧思路：
douyin-1024 = 大而全生产系统
       ↓
所有功能都要做完整
       ↓
13 阶段都跑通才算完成

新思路：
douyin-1024 = 薄业务控制层
       ↓
只保留策略层
       ↓
生产引擎全部 ADOPT / EXTEND
```

---

## 3. 新的 douyin-1024 边界

### ✅ 保留（策略层）

```
douyin-1024/
├── account profile
├── content policy
├── evidence / claims
├── routing
├── experiment metadata
├── publish receipt
└── performance feedback
```

### ✅ 接入外部生产引擎

```
              ┌─ Easel
douyin-1024 ──┼─ 其他视频工作流
              ├─ BrowserSkill
              ├─ 数字人 API
              └─ Remotion / FFmpeg
```

### 📦 Strict V2 保留位置

```
Premium / Audit / Portfolio Lane
```

不删，作为高证据内容生产路径，偶尔使用。

---

## 4. Fast Lane 已正确的方向

已有 Fast Lane 文档方向是对的：

- ✅ Baseline 不强制数字人
- ✅ 不强制 AI Video
- ✅ 不强制 gflow
- ✅ 不强制 OpenChatCut
- ✅ 高级 Provider 失败不能阻止基础发布
- ✅ 连续两周实际发布后，才允许继续自动化真正的最高瓶颈

---

## 5. 接下来两周的实验

### Week 1

```
发布 4 条真实视频
        ↓
记录每条：
- 耗时（Founder 分钟）
- 人工切换次数
- 失败次数
- 成本
- 哪个步骤最痛
```

### Week 2

```
再 4 条
        ↓
找到最大瓶颈
        ↓
针对最大瓶颈做最小自动化
```

---

## 6. 瓶颈 → 自动化映射

```
素材是瓶颈 → 自动素材流水线
脚本是瓶颈 → 优化脚本 Skill（不是重写）
剪辑是瓶颈 → 接 Agent Motion / Remotion
发布是瓶颈 → 接 BrowserSkill / Easel
数字人是瓶颈 → 换 API（不是自己造）
```

**不要先造抽象，再找瓶颈。**

---

## 7. 禁止事项

### 不要做的事

```
🚫 继续完善 13 阶段 schema
🚫 补齐所有 Provider 抽象层
🚫 重写 gating 机制
🚫 重构 workflow engine
🚫 增加新的 Provider 集成（除非有真实需求）
```

### 要做的事

```
✅ 用现有 Fast Lane 跑出一条视频
✅ 把它真的发出去
✅ 记录 Founder 时间 / 失败 / 痛点
✅ 重复 4 次
✅ 找到最大瓶颈
```

---

## 8. 衡量标准（按 MEASUREMENT.md）

| 指标 | 目标 | 测量方式 |
|------|------|----------|
| Time to First Real Output | < 7 天 | 第一条 final.mp4 时间戳 |
| Time to First User | < 14 天 | 第一条视频播放/互动数 |
| Published Outputs | ≥ 4 条/周 | 视频发布日志 |
| Founder Minutes / Output | < 120 分钟 | 时间记录 |
| External Feedback Loops | ≥ 1 | 评论回流机制 |

---

## 9. 与其他项目的关系

### 其他项目的状态建议

```
AI Creator OS        →  HOLD 或 LIBRARY
旧平台 workflow      →  HOLD 或 KILL
数字人探索           →  LIBRARY（暂不重做）
AI Video 实验        →  LIBRARY
新发现 GitHub 项目    →  Candidate（不立即 BUILD）
```

**douyin-1024 是唯一 RUN（Shipping）项目。**

---

## 10. 退出条件

### 触发 KILL 的条件

```
- 14 天内 0 条真实发布
- 持续发现"系统不严谨"但已能跑通基础发布
- 投入大量时间但 published videos 仍 = 0
```

### 触发 PIVOT 的条件

```
- 4 周连续发布但 0 反馈
- 最大瓶颈无法用现有方案解决
```

---

## 11. 引用

- [PRINCIPLES.md](PRINCIPLES.md) — X-SuperPlay 能力证明原则
- [PRE-CODE-GATE.md](PRE-CODE-GATE.md) — coding 前 7 问
- [PROJECT-STATES.md](PROJECT-STATES.md) — 项目四态
- [MEASUREMENT.md](MEASUREMENT.md) — 衡量标准

---

> **停止证明系统正确，开始证明视频能发出来。**