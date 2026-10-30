# From Generic to Insightful — 编辑训练对照（均未新发到 X）

旧帖保留为 `draft`，以下是写作改进示例，不声称这些改写已经发布或效果更好。

## 001 — obra/superpowers verification-before-completion

- [一手 Skill](https://github.com/obra/superpowers/tree/main/skills/verification-before-completion)
- **旧逻辑**：AI coding agent says “Fixed”; 记住 3 项测试清单。
- **升级判断（作者分析）**：“Fixed”只是字符串，PR 的完成状态应该依赖可复现的真实执行证据。这里改变的是评审决策，不是用更猛的形容词。
- **主要反例**：一次通过也不能证明所有行为正确，仍需适当覆盖、环境复现和人工评审。
- **示例（不是已发布文字）**：

```text
"Fixed" is an output string, not a test result.

If an AI agent can't show the command, fresh exit code and original failure now passing, the PR is still unverified.

The bottleneck isn't writing code. It's proving the fix.
https://github.com/obra/superpowers/tree/main/skills/verification-before-completion
```

X URL 固定权重估算 **247**，Composer 最终复核。

## 002 — anthropics/skills mcp-builder

- [一手 Skill](https://github.com/anthropics/skills/tree/main/skills/mcp-builder)
- **旧逻辑**：MCP 不是 API wrapper，要测任务。
- **升级判断（作者分析）**：API 200 OK 和 Agent 成功解决真实用户任务不是同一个验收指标。工具的可发现性、错误恢复和任务完成需要单独检验。源文建议 10 道可验证评测题。
- **主要反例**：完整 endpoint 覆盖对一些客户端仍有价值，不应据此推断“一律只留高阶操作”。
- **示例（不是已发布文字）**：

```text
Your MCP server can return 200 OK and still fail the user.

API coverage isn't enough: can an agent find a tool, recover from errors and finish a job?

Anthropic's mcp-builder suggests 10 verifiable eval questions.
https://github.com/anthropics/skills/tree/main/skills/mcp-builder
```

X URL 固定权重估算 **238**，Composer 最终复核。

## 复用原则

**具体失败方式 > 一般正确建议；真实决策变化 > 产品特性罗列；可证伪判断 > 热点修辞。**

下次不要重新推送 001/002 的主题来证明本次调整；应选择新主题，按 [EDITORIAL-QUALITY-GATE.md](EDITORIAL-QUALITY-GATE.md) 产出全新的可检验观点。
