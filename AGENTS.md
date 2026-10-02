# AGENTS.md — Project rules for AI agents (Codex / Claude Code)

> 本文件用于约束在 `X-SuperPlay-ContentOps` 中工作的 AI 代理。

## North Star

> **稳定生成可发布的 final.mp4。**

任何工作都要问：这项工作能不能让我们更快、更稳定地从真实工作得到一条愿意公开发布的视频？

如果不能 → 现在不要做。

## 1. 核心原则（按重要性排序）

1. **Production output 优先于架构漂亮**。
   一个能跑的 `final.mp4` 比十份漂亮的方案更值。
2. **Real evidence > generated visuals**。
   真实截图、真实录屏、真实数据；AI 生图/视频只做辅助。
3. **不虚构实际运行结果**。
   没有跑通就不能写"我跑通了"。Easel 调研类内容可以用 README 原文 + GitHub commit 引用。
4. **不泄露 secrets**。
   API key / cookie / token / .env 永远不进 Git。
5. **不复制 Easel 大量源码**。
   Easel 是 pinned upstream runtime，本仓库只写胶水层。
6. **不自动升级 upstream**。
   Easel 锁在 commit `3fe2d9904c1619281ef57f81d9ee0b7854998399` (v0.2.1)。任何升级必须 Founder 明确同意。
7. **不为了扩展性提前造抽象**。
   三行重复比过早抽象好。
8. **FAIL 就 FAIL，不允许为了通过验收静默降级**。
   QC 报告必须诚实标注 `voice_quality: fallback` 等。
9. **每次修改尽量带可执行验证**。
   至少跑一次 `python scripts/doctor.py` 与 `python scripts/qc_video.py`。
10. **Human Approval 永远不被绕过**。
    需要人工确认的 Gate 必须停在那里输出 `NEEDS_HUMAN_REVIEW`。

## 2. 内容真实性边界（非常重要）

### 允许的写法

- "官方实现了 X"（引用 README / 源码）
- "v0.2.1 release 显示 Y"
- "Skill 文档说明 Z"
- "源码里可以看到 W"
- "本机 `doctor` 输出显示 A"

### 禁止的写法

- "我本地实测跑通 X"（除非本任务真的跑过）
- "经测试 Y 稳定"（没有数据支撑）
- 虚构客户案例 / 数据 / 用户数

## 3. 文件 / 目录纪律

- 不修改既有 5 个旧仓库的任何代码（除非 Founder 明确要求）。
- 不 fork / 复制 Easel 源码。
- 所有 runtime 用 helper 脚本统一封装，禁止裸 `cd .runtime/easel && python ...`。

## 4. 禁止清单（V1 阶段）

以下功能 **当前不做**：

- 自动发布抖音 / 小红书 / B站 / 视频号
- 评论抓取 / 数据归因 / ROI Agent
- n8n / OpenClaw 总调度中心 / 数据库 / 复杂 FastAPI
- 数字人 / AI 短剧 / 复杂 AI 视频 / 批量矩阵号
- Fork / 改造 Easel

## 5. 修改工作流

1. 先跑 `python scripts/doctor.py` 确认环境。
2. 修改代码。
3. 跑相关测试。
4. 跑 `python scripts/qc_video.py <project>` 验证产物。
5. 提交：消息前缀 `feat:` / `fix:` / `docs:` / `chore:` / `test:`。

## 6. 验证 Receipt 文化

每个项目完成后必须有：

```
projects/<slug>/receipts/
  qc-report.json
  qc-report.md
  publish-receipt.md  (人工发布后)
```

数据没有 ＝ 任务没有完成。

---

## 7. 能力证明原则（最高优先级）

> **X-SuperPlay 不以"自己开发了多少系统"为能力证明，而以"借助现有能力，多快完成真实业务闭环"为能力证明。**

### 四条铁律

```
Adopt before Build.       先采纳，后建造
Ship before Automate.     先发布，后自动化
Measure before Optimize.  先测量，后优化
Delete before Expand.     先删除，后扩展
```

### ADOPT / EXTEND / BUILD

看到任何需求，第一反应必须是：

| 情况 | 动作 |
|------|------|
| 别人已经解决 80%+ | **ADOPT** |
| 别人解决 60–80%，你有特殊需求 | **EXTEND** |
| 没有成熟方案，而且是你的核心差异 | **BUILD** |

**不要默认 BUILD。**

### 架构的本质

> **会删东西，比会加东西更像架构能力。**

真正重要的问题之一是：

> **这个系统哪些东西应该存在？哪些东西根本不应该由我做？**

这是 Boundary。

---

## 8. Pre-Code Gate（每个项目开始前必答）

每个项目 coding 前必须回答：

```
1. 谁会用？
2. 他现在怎么解决？
3. 我要改善的唯一核心问题是什么？
4. GitHub / SaaS / API 上是否已有 70% 解决方案？
5. 我真正独有的 20% 是什么？
6. 7 天之内最小可交付物是什么？
7. 什么条件出现时我停止这个项目？
```

**第 4 个回答不清楚 → 禁止 coding，先调研。**

---

## 9. 项目状态制度（强制）

每个项目只允许四种状态：

```
RUN       真正在产生外部结果
HOLD      暂停，不准开发
LIBRARY   只是资产/代码/参考
KILL      明确停止
```

**WIP Limit = 1**：同一时间只允许一个主要 Shipping Project。

**不允许** "这个项目以后可能有用，所以偶尔继续优化"——这是最吃时间的状态。

---

## 10. 7/14 天死亡规则

- **Day 0-1**：调研 existing solutions，决定 ADOPT/EXTEND/BUILD
- **Day 2-3**：必须出现 real artifact（MP4/网页/APP/API/报告）
- **Day 7**：必须真实使用一次
- **Day 14**：必须产生一个外部结果（用户/发布/收入/数据/反馈）

14 天没有外部结果 → **CUT SCOPE / PIVOT / HOLD / KILL**，而不是"再把架构完善一下"。

---

## 11. 新的成功衡量标准

不要看"代码完成度"，改看 5 个东西：

```
1. Time to First Real Output
2. Time to First User
3. Published / Delivered Outputs
4. Founder Minutes / Output
5. External Feedback Loops
```

**核心指标：**

```
Published videos = 0  →  项目还没完成第一次实验
```

哪怕 `400 tests passed`，从业务角度项目还没开始。

---

## 12. douyin-1024 战略定位（特例）

> **不要问"怎么终于把 douyin-1024 做完整？"**
> **问"douyin-1024 还剩哪些东西值得我拥有？"**

降级为薄业务控制层：

```
保留：account profile / content policy / evidence / claims /
      routing / experiment metadata / publish receipt /
      performance feedback

生产引擎：Easel / BrowserSkill / 数字人 API / Remotion / FFmpeg
```

Strict V2 不删，放到 **Premium / Audit / Portfolio Lane**。

Fast Lane 方向正确：
- Baseline 不强制数字人
- 不强制 AI Video
- 高级 Provider 失败不阻止基础发布
- 连续 2 周实际发布后才继续自动化

---

## 详细文档

- [00-Governance/PRINCIPLES.md](00-Governance/PRINCIPLES.md) — 完整能力证明原则
- [00-Governance/PRE-CODE-GATE.md](00-Governance/PRE-CODE-GATE.md) — Pre-Code Gate 详细说明
- [00-Governance/PROJECT-STATES.md](00-Governance/PROJECT-STATES.md) — 项目四态制度
- [00-Governance/MEASUREMENT.md](00-Governance/MEASUREMENT.md) — 衡量标准详细说明
- [00-Governance/douyin-1024-STRATEGY.md](00-Governance/douyin-1024-STRATEGY.md) — douyin-1024 详细战略

---

> **停止证明系统正确，开始证明视频能发出来。**