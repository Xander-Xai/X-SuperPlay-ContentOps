# 2026-10-25 GitHub 工作流调研与资料索引

## 2026-10-25 扩展：X + GitHub 双信息源

- [X 研究准入/候选与数据出处](X-SIGNAL-RESEARCH.md)：X 原帖仅作为热议、用户痛点和内容机会信号，**高曝光不能证明 AI 提效或存在客户预算**。
- [严格 GitHub/Skill 审核](GITHUB-VALUE-AUDIT-2026-10-25.md)：仅具体 AI 生产力/商业交付项目有资格进入候选；旧 12 项 5 可研究、7 待补案例。
- 官方 API 来源：[X Search](https://github.com/xdevplatform/docs/blob/main/x-api/posts/search/introduction.mdx) / [Post Lookup](https://github.com/xdevplatform/docs/blob/main/x-api/posts/lookup/introduction.mdx)，未来如预算与授权允许可采用只读检索；当前手工 X 搜索。
- 借鉴但未运行：[trailofbits/skills-curated X Research](https://github.com/trailofbits/skills-curated/blob/main/plugins/x-research/skills/x-research/SKILL.md)（排序/去重/线索核查），[Desearch-ai/x-monitor](https://github.com/Desearch-ai/x-monitor)（Seen-ID、防重和候选归档）。
- 排除 Cookie/Session 代理式自动化、未经请求的互动机器人、不加核验的排名分值。详细见双源研究文件。

## 结论（面向当下 V0）

最简单、最稳健：**ChatGPT 联网研究与写作 + 真实配图 + 人工审核 + X 官方发布/可用时的原生排期 + CSV 记账**。GitHub 是 SOP 与数据来源，不是自动发帖器。此方案不需要安装 Docker/n8n，不需要 X API 密钥。

| 方案/来源 | 已核实的能力/内容 | 当前决策 | 一手链接 |
|---|---|---|---|
| X 官方 Scheduling | X Ads 文档有 Organic / Scheduled 帖子的排期路径；不同账号/入口可用性需实测 | **V0 可尝试**；不可默认 Thread 排期完整可用 | https://help.x.com/en/business-and-advertising/scheduled-tweets |
| X 官方自动化政策 | 授权信息类自动发布在规则内有条件允许；禁止非 API 网页脚本、自动点赞、批量无请求回复 | **必遵守** | https://help.x.com/en/rules-and-policies/x-automation |
| Postiz | 社媒排期、分析、官方平台 OAuth，支持自托管/API；AGPL-3.0，配置和成本非零 | **V2 候选**，目前不部署 | https://github.com/gitroomhq/postiz-app |
| n8n | 开源可自托管/云端编排；X 节点可创建或回复推文，须开发者凭据；自动化合规仍需单独考虑 | **V2–V4 候选** | https://github.com/n8n-io/n8n ; https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.twitter/ |
| Anthropic Skills | 官方技能样例，含 skill-creator、mcp-builder、webapp-testing、xlsx 等；不同文件许可不一 | **首批内容来源** | https://github.com/anthropics/skills |
| Vercel Agent Skills | React / Web Design / Deploy 类官方技能 | **首批内容来源** | https://github.com/vercel-labs/agent-skills |
| Superpowers | 系统调试、TDD、完成前验收等开发工作流 Skill | **首批内容来源** | https://github.com/obra/superpowers |
| Skills CLI | 技能安装/查找/列表工具；不是 X 发帖工具 | **Skill 发现工具，暂不安装** | https://github.com/vercel-labs/skills |
| Community skills directory | 覆盖面广、质量和许可混合；项目介绍“production ready”仅属其自述，需逐条审查 | **发现线索，不作事实背书** | https://github.com/ComposioHQ/awesome-claude-skills |

### 证据边界

- 本调研为 **X 工作流和可持续选题来源** 研究，不等于验证任何候选最近 72 小时有重大更新。
- 仓库可访问 / README 声称的功能 ≠ 已在此账号完成 OAuth / 稳定发布验证。
- Skills 是否可跨模型、商业使用、可执行、对某种环境生效，需看该 Skill 的说明与 license 并实测。
- **不要购买/部署平台**仅为了今天发一条内容。升级以真实劳动成本、发布失败率和粉丝质量数据触发。

调研时间：2026-10-25；重要外部服务能力及政策应在使用前复核。
