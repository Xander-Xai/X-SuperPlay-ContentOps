# PRINCIPLES.md — X-SuperPlay 能力证明原则

> 本文件定义 X-SuperPlay 的核心能力证明方式。
> 当 AGENTS.md 与本文件冲突时，以本文件为准。

---

## 1. 核心命题

> **X-SuperPlay 不以"自己开发了多少系统"为能力证明，而以"借助现有能力，多快完成真实业务闭环"为能力证明。**

### 解读

- **能力证明 ≠ 代码行数** ≠ 仓库数量 ≠ 测试覆盖率
- **能力证明 = Time to First Output × Speed × Working Closures**

---

## 2. 四条铁律

```
Adopt before Build.        先采纳，后建造
Ship before Automate.      先发布，后自动化
Measure before Optimize.   先测量，后优化
Delete before Expand.      先删除，后扩展
```

### 详细含义

#### Adopt before Build

看到任何需求，第一反应：

```
现成 SaaS 能不能解决？
    ↓
现成 API 能不能解决？
    ↓
成熟开源项目能不能解决？
    ↓
两个项目组合能不能解决？
    ↓
写 200 行 Adapter 能不能解决？
    ↓
都不行
    ↓
才自己开发
```

#### Ship before Automate

```
手动 prototype 先跑通
    ↓
真实跑一次
    ↓
有用户
    ↓
才考虑自动化
```

#### Measure before Optimize

```
没有数据，不要"优化"
    ↓
优化是缩小问题，不是发明问题
```

#### Delete before Expand

```
想加功能前，先问"什么东西可以删？"
    ↓
WIP Limit = 1
```

---

## 3. ADOPT / EXTEND / BUILD

| 情况 | 动作 | 例子 |
|------|------|------|
| 别人解决 80%+ | **ADOPT** | Easel / BrowserSkill / Remotion |
| 别人解决 60-80%，你有特殊需求 | **EXTEND** | 给 Easel 加 douyin 业务策略层 |
| 没有成熟方案，且是核心差异 | **BUILD** | 选题逻辑、Evidence / Claim 体系 |

---

## 4. X-SuperPlay 的边界

### ✅ 应该 OWN 的（核心差异）

- 选题逻辑
- 账号定位
- Evidence / Claim 体系
- 内容实验
- 业务数据
- 产品化路径
- 收入归因
- 用户反馈
- 机会筛选逻辑

### ❌ 不应该自研的

- Browser automation → BrowserSkill
- Image generation → SaaS API
- Video generation → SaaS API
- TTS → MiniMax / ElevenLabs
- Digital Human → SaaS API
- Editing engine → Remotion / FFmpeg
- Rendering → FFmpeg
- Crawler → 现成工具
- Publishing adapter → Easel / BrowserSkill
- Workflow engine → Easel / LangGraph

---

## 5. 架构的本质

> **会删东西，比会加东西更像架构能力。**

真正重要的问题之一是：

> **这个系统哪些东西应该存在？哪些东西根本不应该由我做？**

这是 **Boundary**。

### 反面教材（最近几个月的根因）

```
问题
  ↓
设计系统
  ↓
系统复杂
  ↓
补规范
  ↓
补测试
  ↓
补治理
  ↓
补自动化
  ↓
发现新的边界问题
  ↓
重构
  ↓
还没有真正交付
```

---

## 6. 关键转变

### 从 Architecture First 到 Evidence First

#### 旧（错）：

```
Idea → Architecture → Repository → Schema → Workflow
     → Automation → Testing → Governance → Real Output
```

#### 新（对）：

```
Problem → Existing Solution Search → Manual Prototype
       → Real Output → Real User → Measure → Bottleneck
       → Automation → Architecture
```

---

## 7. 心理学纠偏

> **用别人项目 ≠ 能力不够。**

一个 AI 应用工程师：

```
自己写浏览器
自己写 workflow engine
自己写向量库
自己写 TTS
自己写编辑器
自己写视频模型
```

并不会因此更高级。

另一个工程师：

```
BrowserSkill + LangGraph + Qdrant + ElevenLabs / MiniMax
+ Remotion + 自己的 RAG / Agent / evaluation
```

三周交付真实业务结果 → 后者更成熟。

> **能判断什么时候不该自己开发，本身就是高级能力。**

---

## 8. 阶段判断

- **过去几个月**：从"不会工程化" → "过度工程化"
- **未来学习方向**：**产品工程**——怎么用最少的新增复杂度，产生最大的真实结果

---

## 9. 引用与执行

- AGENTS.md 第 7 节：能力证明原则
- [PRE-CODE-GATE.md](PRE-CODE-GATE.md)：coding 前必答
- [PROJECT-STATES.md](PROJECT-STATES.md)：项目四态
- [MEASUREMENT.md](MEASUREMENT.md)：衡量标准
- [douyin-1024-STRATEGY.md](douyin-1024-STRATEGY.md)：具体项目战略

---

> **停止证明系统正确，开始证明视频能发出来。**