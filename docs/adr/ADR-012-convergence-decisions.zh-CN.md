---
translation_of: docs/adr/ADR-012-convergence-decisions.md
language: zh-CN
translation_status: synced
---

# ADR-012：收敛决策 —— 内容层、Skill 与上游固定版本

[English](ADR-012-convergence-decisions.md) | [简体中文](ADR-012-convergence-decisions.zh-CN.md)

> 状态：**已接受** —— Owner 授权，2026-11-01
> 未取代任何记录。填补未合并的 `feat/content-router` 分支预留的 ADR-011 空位
> （`ADR-011-single-home-platform-tracks`），因此本记录取 012，避免编号冲突。
> 证据：[../CONVERGENCE-REQUIREMENTS-2026-11-01.md](../CONVERGENCE-REQUIREMENTS-2026-11-01.md)

## 背景

2026-11-01 的审计发现，仓库同时描述了三套不同的系统：`main`、工作分支
（`fix/57-m5-media-fixtures`，领先 17 个提交），以及承载账号感知内容层的一批未合并
分支。五个已安装的 `x-superplay-*` Skill 描述的命令与模块只存在于那些未合并分支上。
上游固定版本落后于当前稳定版。

D1–D6 由 Owner 于 2026-11-01 记录。本 ADR 固化这些决策，使后续工作有一个引用，
而不是一次对话。

## 决策

### D1 —— 内容路由是正式的账号/Brief 前端

`feat/content-router`（PR #49）成为把选题变成 Brief 的前端。M5 证据链保留为生产
引擎。一个引擎、一份 Brief 合约、一套门禁词汇。

它**不做整体合并**，而是分片合并，每片自带测试，每片先落地再进下一片。顺序：

1. **S1 —— workflow 核心。** `src/contentops/workflow/{contract,gate,validators}.py`
   与 `scripts/workflow_gate.py`。这是 Skill 调用的确定性阶段门禁，且不依赖账号配置。
2. **S2 —— 证据侧校验器。** `src/contentops/workflow/{sources,capture_plan}.py`、
   `scripts/workflow_docs.py`、`scripts/recording_plan.py`。这两片解锁
   `x-superplay-source-research` 与 `x-superplay-capture-plan`。
3. **S3 —— 账号配置。** `config/accounts/*` 与路由脚本。
4. **S4 —— 其余阶段。** Brief、脚本、设计、优化层。

每片合并时必须同步更新 `runtime/content-skill-status.json`：落地 Skill 所命名的代码，
会让旧记录变成假话。

### D2 —— 五个内容 Skill 在代码落地前保持未声明

只有当条目指向的代码存在于集成分支上时，`runtime/skill-registry.json` 才能新增条目。
声明是指向已验证代码的指针；指向未合并分支会让 `RESOLVABLE` 变成假话。

`scripts/check_skill_references.py` 强制这一点：未登记的悬空引用失败；已落地的引用
在记录更新前失败；标记为已合并却缺代码的 Skill 失败。

### D3 —— Easel 保持 v0.2.1

现在不采用 Easel v0.3.0。差异为 158 个提交、300 个文件，全部 Skill 从
`skills/openclaw/` 迁到 `skills/builtin/`，`auto-short-video/scripts/assemble.py`
变更，且上游在保持版本号不变的前提下**强制替换过 tag**。可被替换的 tag 不是固定版本。

将来采用时，按**内容摘要**而不是 tag 采用，并走完整升级门禁：来源校验、上游差异分析、
单元测试、Windows 测试、3 次黄金渲染、凭证比对、人工审核、Founder 批准、更新锁文件。

### D4 —— HyperFrames 以补丁版本升到 0.8.225，并重新钉住

差异为 34 个提交，含导出与 CLI 修复。其间 `skills/media-use/SKILL.md` 及其引用文件
发生了变化，因此已固定的 Skill commit
（`f2358315e59731833334c5d881a7fb5543c22a97`）必须重新固定，并在使用新版本前重新
生成已批准基线与主机锁。

升级与运行时安装一起执行，不提前：没有可信主机锁的固定版本，是一个谁也跑不起来的
固定版本。

### D5 —— 未跟踪的内容项目按需收编

`projects/x-superplay-1024`、`projects/easel-fi-audio-first`、`projects/gzh-thinktank`
既没有 `project.yaml` 也没有凭证。它们保持本地、未跟踪，直到再次被处理。收编意味着
补 `project.yaml`、来源清单与凭证，而不是 `git add` 那些二进制文件。

### D6 —— worktree 与分支先审计、再报告、逐项批准删除

`.claude/worktrees` 与 `D:\Temp\AI-Agents` 下存在 30+ 个 worktree。文件系统策略禁止
把它们当作例行清理直接删除。审计报告逐项列出归属、分支、年龄与是否被引用；删除是
另一件事，需要逐项批准。

## 后果

- 文档可以直接陈述某个分支上有什么，而不必附带免责声明，因为分支层现在已被命名。
- 五个内容 Skill 保持诚实：可见、被阻断，缺失的依赖从"阅读题"变成 CI 失败。
- 没有门禁、没有摘要、没有 Owner 批准，任何上游固定版本都不移动。
- 下一处实质性的代码变更是 S1 分片，而不是新能力。

## 重新审视的触发条件

- PR #49 被重写或取代 → 重新推导分片顺序。
- Easel 发布 v0.4.0 或 v0.3.0 的 tag 再次变化 → 重开 D3。
- media-use 生成了主机运行时锁 → D4 变为可执行。
- Owner 想要另一个账号/Brief 前端 → 重开 D1。
