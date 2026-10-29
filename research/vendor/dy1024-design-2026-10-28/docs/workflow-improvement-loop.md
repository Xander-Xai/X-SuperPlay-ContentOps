---
status: archived
canonical: false
issue: "#34"
date: 2026-10-28
source: dy_x1024@a5952a44dbf47d44c1a4bf475e3653b542c25ac1
---

# 工作流优化闭环

真实生产中的问题，不直接改状态字段或临时绕过门禁，而是进入每个内容包的：

```text
09_feedback/workflow-improvement-log.json
```

它和发布后的 `09_feedback/feedback.json` 分工不同：

- `feedback.json` 记录平台发布回执、指标、评论和内容学习；
- `workflow-improvement-log.json` 记录工作流、脚本、路径、门禁、渲染器、提供商、环境或文档的问题。

## 记录一条问题

问题必须能回答四件事：看到了什么、应该是什么、如何复现、用什么证据证明。示例：

```powershell
python scripts/workflow_improvement.py record `
  --project "$project" `
  --content-id $contentId `
  --stage quality `
  --category gate `
  --severity high `
  --summary 'Quality 读取了旧的渲染回执路径' `
  --observed '检查时访问了 05_publish/...' `
  --expected 'canonical 包应只读取 07_quality/...' `
  --reproduction 'python scripts/workflow_gate.py check --project ... --step quality' `
  --evidence '07_quality/quality-report.json|<该文件的SHA-256>|当前质量报告' `
  --proposed-change '改为从 content.json 的 canonical 路径读取' `
  --verification-plan '运行 canonical 测试、硬化验证和一次真实质量检查'
```

证据路径必须在内容包内；如果文件存在，脚本会重新计算 SHA-256，哈希不一致会拒绝记录。密码、Cookie、Token、私人聊天和未授权素材不能写入证据或备注。

查看当前记录：

```powershell
python scripts/workflow_improvement.py show --project "$project"
```

## 从记录到修复

每条记录按以下状态推进：

```text
reported → triaged → reproduced → planned → fixed → verified
```

`wont_fix` 也必须写明理由。修复时按问题类型选择范围：

- 路径/契约问题：同步 canonical 路径、schema、初始化器和门禁；
- 逻辑问题：增加最小回归测试，禁止只改布尔状态；
- 渲染/提供商问题：区分代码缺陷和外部不可用，外部不可用时保持 `blocked`；
- 文档问题：同步 README、SKILL 和运行手册；
- 生产内容问题：修正内容包，不把一次内容失败扩大成全局规则。

完成修复后必须：

1. 重现原问题已不再出现；
2. 运行相关测试、完整 `pytest`、`workflow_config_audit.py --strict` 和 `verify_hardening.py`；
3. 如涉及媒体链，再执行一次真实渲染或明确记录外部阻塞；
4. 将记录状态改为 `verified`，再通过独立分支、PR 和合并进入 `main`。

这个日志是优化方向盘，不是生产完成门禁；它不能替代审批、证据、哈希或真实人工审核，也不能阻止已完成的 Delivery。
