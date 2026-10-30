# GitHub X 工作流二轮筛选（2026-10-25）

> 目的：筛出**今天就能借鉴**的轻量能力，而不是部署一套多 Agent 系统。
>
> 研究对象：GitHub 上公开的 X / Twitter 内容生产、发布、审核与排期仓库。证据：GitHub 仓库 README 和部分源码，以及 GitHub/X 官方文档。**研究日期 ≠ 候选项目过去 72 小时发生重大更新**。

## 可用结论 / 优先级

| 优先级 | 项目 | 真实用途 / 审核结果 | 我们的决策 |
|---|---|---|---|
| P0：现在 | [langchain-ai/social-media-agent](https://github.com/langchain-ai/social-media-agent) | URL → 社媒草稿 → 人类批准/编辑/拒绝；仓库明确提供 few-shot examples、business context 和 post content rules。完整快速安装仍需要 Anthropic、Firecrawl、Arcade、LangGraph 等；完整版更多依赖。 | **只借鉴编辑流和提示词思想**：已落地 [GITHUB-URL-TO-X.md](../prompts/GITHUB-URL-TO-X.md)，不部署全项目。 |
| P0：现在 | [twitter/twitter-text](https://github.com/twitter/twitter-text/tree/master/js) | 官方文本解析库提供 `parseTweet` 的 `weightedLength` 和 `valid`；能正确处理 URL/Unicode 权重。 | 先用 X Composer 二次确认；以后做自动校验才引入依赖。**普通字符串长度不等于 X 加权长度**。 |
| P1：验证排期前 | [gitroomhq/postiz-agent](https://github.com/gitroomhq/postiz-agent) | Postiz CLI/Skill 官方仓库提供 X Thread 的多 `-c` 结构、媒体上传、OAuth 登录与排期示例。 | **最优先候选发布层**；先验证平台连接、Thread+图片联动、实际定时成功、取消与费用。不安装、不接密钥。 |
| P2：备用 | [gitroomhq/postiz-app](https://github.com/gitroomhq/postiz-app) | 跨平台管理、日历和分析；AGPL-3.0，托管或自部署皆有配置和授权成本。 | 只有需要可视化日历/多平台时再评估，避免与 Postiz Agent 重复投入。 |
| P2：参考代码 | [burnworks/x-scheduled-posts](https://github.com/burnworks/x-scheduled-posts) | YAML → GitHub Actions → X API；README 含 Thread、媒体、ALT、`DRY_RUN`；代码使用状态文件和日志避免重复发送。仓库公开成熟度证据很弱。 | 以后若选 GitHub 原生排期，借鉴配置、状态与 dry-run，**先安全审计和沙箱验收，不复制后直接部署**。 |
| P3：参考策略 | [anas-aqeel/Agent-X](https://github.com/anas-aqeel/Agent-X) | RSS/HN 选题、去重、人工审批、失败重试、追踪；README 声称特定限制和指标，未独立实测。 | 只借鉴“候选排重 + 来源记录 + 批准状态”，现阶段不部署多服务全栈。 |
| P3：将来参考 | [n8n-io/n8n](https://github.com/n8n-io/n8n) | 可视化编排、X 服务集成，但需要运营环境/凭据/维护。 | 仅在内容生产稳定且人工操作确有瓶颈时重新比较。 |
| 不采纳 | [altansaid/ai-social-engagement-engine](https://github.com/altansaid/ai-social-engagement-engine) | 用关键词寻找陌生人帖子并起草/审批大量回复。即便有人点批准，平台规则仍可能禁止此类未经请求的批量触达。 | **不接入自动回复/自动互动**。人工、针对内容的真实讨论即可。 |
| 不优先 | [aditya-xq/weft](https://github.com/aditya-xq/weft) | 将个人 GitHub 活动汇总为图并发布 X。 | 适用于 build-in-public 账号，不符合当前核心主题（AI 技术提效与可验证商业价值）。 |

## 为什么当前不自动部署

1. **发布层有额外账户授权、潜在费用和失败恢复问题**；内容只有每天一篇，目前人工发布成本不高。
2. **GitHub Actions cron 不是准确的定时投递保证**：官方表示高负载可延迟甚至丢弃任务，整点尤需避免。参见 https://docs.github.com/en/actions/how-tos/troubleshoot-workflows 。若将来采用：需错峰、手动重跑、状态检查、去重保护与失败告警。
3. X 官方禁止模拟网页操作进行自动化、自动点赞以及未经请求的大规模自动回复。AI 回复机器人另有明确批准约束。参见 https://help.x.com/en/rules-and-policies/x-automation （2026-04 更新）。
4. **有代码、有 README ≠ 此账号可用/生产验收通过**。本轮没有做 X OAuth、真实发帖、集成测试，也未向主账号发送任何内容。

## 现在已落地的低成本改进

### 流程 A：有一个 GitHub 链接时（新）

**项目/Release/PR/Skill 链接 → 一手证据核验 → 选 1 个独立角度 → 英文 Post（优先单条）→ 真正生成的英文配图 → 人工审批 → X 发布 → 填日志**。

入口：[GITHUB-URL-TO-X.md](../prompts/GITHUB-URL-TO-X.md)。适用你看到高质量 GitHub 项目，想当天立刻发布的情形。

### 流程 B：没有素材时（原有）

当天运行 [DAILY-POST.md](../prompts/DAILY-POST.md) → 发现候选 → 核验过去 72h 事件或明确切换 evergreen → 审批 → 人工 X 发布。两条流程共享 [POST-CARD.md](../templates/POST-CARD.md)。

### 编辑审核闸门

1. 一条作品只能有一个主要结论；必须能指出目标受众、具体工作流变化和边界。
2. 每项重大事实都有可访问的**原始 URL**，并区分事件日期/抓取日期；旧 Skill 不说成新发布。
3. 普通账号每条不超过 **280 加权字符**，最终在 X Composer 复核；Thread 最多 3 条。
4. 图必须真的存在，16:9 英文且无伪造数据；发布前补充 ALT 文本。
5. **approved** 不是 **published**；发布状态只有拿到 X 原帖 URL 才记录 published。
6. 商业变现属于假设时标记 buyer / delivery / pricing hypothesis / one-week test / risk；不得声称已产生收益。

## V2 候选的验收清单（未执行）

- [ ] 用户明确授权平台连接；验证账户范围、最小权限、收费及凭据储存。
- [ ] 完整测试 1 条英文文字 Post + 1 张图片/ALT（含实际 X URL）。
- [ ] 完整测试 2–3 条 Thread 顺序与图片位置，发现产品是否支持一起排期。
- [ ] 失败后重试不会产生重复 Post；能检查状态和撤销待排期记录。
- [ ] 定时运行连续 14 天有发布状态、失败告警、成本记录。
- [ ] 严格遵守 https://help.x.com/en/rules-and-policies/x-automation 。

## 被验证的项目来源

- LangChain 社媒 Agent：https://github.com/langchain-ai/social-media-agent
- X 字符权重：https://github.com/twitter/twitter-text/blob/master/js/README.md
- Postiz Agent CLI：https://github.com/gitroomhq/postiz-agent
- GitHub YAML 排期脚本：https://github.com/burnworks/x-scheduled-posts
- Agent-X：https://github.com/anas-aqeel/Agent-X
- X 自动化规则：https://help.x.com/en/rules-and-policies/x-automation
- GitHub Actions cron 限制：https://docs.github.com/en/actions/how-tos/troubleshoot-workflows

**评估性质**：仓库项目介绍 + 核查部分实际源码，不代表已完成本地测试、许可证兼容性审计或生产可用性证明。价格、许可及上游接口可能变化，部署前再次核对。
