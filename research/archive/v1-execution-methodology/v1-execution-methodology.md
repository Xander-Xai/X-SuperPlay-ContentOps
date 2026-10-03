```yaml
status: superseded
superseded_by: docs/PRD.md, docs/ARCHITECTURE.md, AGENTS.md
historical_context: Philosophy absorbed into PRD + AGENTS.md. Content remains valid principles.
notes: "先跑通，再改造" (adopt before build) is absorbed into AGENTS.md and core principles.
```
# V1 执行方法论 — 先跑通，再改造

> 来自 Founder 反复踩坑后的执行规则。
> 相关 memory：[[approach-iterative]]

## 规则

**V1 第一阶段不动 Easel 源码。先用原版跑通一次完整链路。**

## 为什么

反复出现的反模式：

```
clone main
  ↓
大改
  ↓
加十几个功能
  ↓
重构
  ↓
又发现新项目
  ↓
Easel 没真正用起来
```

正确路径：

```
v0.2.1
  ↓
原版安装
  ↓
doctor
  ↓
ping
  ↓
web
  ↓
跑通一个真实内容
  ↓
再开始改
```

## 决策树（每个新功能 ask 必走）

```
这个改动今天能帮我产出真实 final.mp4 吗？
  → 是：现在做
  → 否：等第一次真实产出后再排
```

## 第一阶段必须跑通的完整链路

```
热点 → 选题 → 脚本 → 内容生成 → 发布前检查 → 发布 / 人工确认 → 数据回收
```

跑不通就不算 V1 ready。

## 禁止动作清单

- 不 fork Easel 源码
- 不在 vanilla 没跑通之前加 Skill
- 不在看到真实 final.mp4 之前重新设计架构
- 不重建 Easel 已经做得不错的能力
- 不为假设未来需求造抽象

## 数据没有 = 任务没有完成

每个项目完成后必须有 `receipts/`：

```
projects/<slug>/receipts/
  qc-report.json
  qc-report.md
  publish-receipt.md  (人工发布后)
```
