# 100 Useful AI Skills — 严格价值准入，不保证 100 个都值得发表

> **2026-10-25 严格审查结果：5 个 `eligible_for_research`，7 个 `hold_until_case`**。完整逐项理由、买方/提效机制/可测试指标及新增开源候选见 [GitHub Value Audit](GITHUB-VALUE-AUDIT-2026-10-25.md)。保留全部来源作为素材库，但**不得自动选取 hold 项目发帖**。

**策略：做“100 Useful AI Skills for Real Work”内容资产，不是连续 100 天宣传 100 个未经测试的仓库。** 首月先验证 8–12 个种子主题，内容既能作为 X 帖子，也能为未来教程/Newsletter/产品案例提供素材。

状态说明：`source_verified` = 已核对真实上游目录或 SKILL.md；`hands_on_pending` = 还没有在用户真实环境运行；`published` 只能在填入真实 X 链接后使用。下面只是选题池，不宣称已测试，也**不是最近 72 小时的更新事件**。

| ID | 官方/主要仓库与 Skill | 具体帖子切入点 | 证据状态 | 价值准入 |
|---|---|---|---|
| S001 | [Anthropic: mcp-builder](https://github.com/anthropics/skills/tree/main/skills/mcp-builder) | 用 workflow-first 思想设计 MCP 工具，而非一次性包住所有 API | source_verified; hands_on_pending | `eligible_for_research` |
| S002 | [Anthropic: skill-creator](https://github.com/anthropics/skills/tree/main/skills/skill-creator) | 把重复提示词写为可复用 Skill；何时值得这么做？ | source_verified; hands_on_pending | `hold_until_case` |
| S003 | [Anthropic: webapp-testing](https://github.com/anthropics/skills/tree/main/skills/webapp-testing) | 用 Playwright 做 UI 回归验收；相较手工检查覆盖什么？ | source_verified; hands_on_pending | `eligible_for_research` |
| S004 | [Anthropic: frontend-design](https://github.com/anthropics/skills/tree/main/skills/frontend-design) | 为什么设计约束比“做漂亮点”更容易复用？ | source_verified; hands_on_pending | `hold_until_case` |
| S005 | [Anthropic: xlsx](https://github.com/anthropics/skills/tree/main/skills/xlsx) | AI 辅助清洗和核对 Excel，如何避免公式错误？ | source_verified; hands_on_pending | `eligible_for_research` |
| S006 | [Anthropic: docx](https://github.com/anthropics/skills/tree/main/skills/docx) | 模板化业务文档生产，原始文档如何留痕？ | source_verified; hands_on_pending | `hold_until_case` |
| S007 | [Vercel: react-best-practices](https://github.com/vercel-labs/agent-skills/tree/main/skills/react-best-practices) | 用实际代码对比讲 React/Next.js 性能规则 | source_verified; hands_on_pending | `hold_until_case` |
| S008 | [Vercel: web-design-guidelines](https://github.com/vercel-labs/agent-skills/tree/main/skills/web-design-guidelines) | 用清单检查页面体验与可访问性 | source_verified; hands_on_pending | `hold_until_case` |
| S009 | [Vercel: deploy-to-vercel](https://github.com/vercel-labs/agent-skills/tree/main/skills/deploy-to-vercel) | 独立开发者从 demo 到可分享预览 | source_verified; hands_on_pending | `hold_until_case` |
| S010 | [Superpowers: systematic-debugging](https://github.com/obra/superpowers/tree/main/skills/systematic-debugging) | 根因定位流程如何避免试错式修复？ | source_verified; hands_on_pending | `eligible_for_research` |
| S011 | [Superpowers: test-driven-development](https://github.com/obra/superpowers/tree/main/skills/test-driven-development) | 先有失败测试再写修复，成本在哪？ | source_verified; hands_on_pending | `hold_until_case` |
| S012 | [Superpowers: verification-before-completion](https://github.com/obra/superpowers/tree/main/skills/verification-before-completion) | 如何让“已完成”必须附可复现验收证据？ | source_verified; hands_on_pending | `eligible_for_research` |

**注意**：某些上游目录可能标注 source-available、附特别许可或依赖专有平台；不要笼统称全部为 MIT 或可免费商用。单独检查目标 Skill 的 LICENSE、外部依赖、API 消耗。

**额外硬门槛：** 每项必须存在 AI 实际提效或可收费交付场景、明确使用者、机制、可验证 KPI、许可和运行成本；不足则保持 hold。不能把高 Star、通用设计指南或简单部署能力自动包装为商业价值。旧 S001/S012 已经写过 X 草稿，除非有新证据不得重复发同一个观点。

## 每个 Skill 上线前的六格卡片

1. Source: 仓库 URL、具体 SKILL.md URL、所看提交 SHA/版本、核验日期。
2. Problem: 明确读者、真实任务、原方法的步骤/成本。
3. Demo: 输入、操作、期望输出；实测/计划演示明确标记。
4. Value: 用省掉哪些步骤来解释价值；数值仅用可复核实测。
5. Catch: 运行环境、权限、隐私、许可证、配置和失败情形。
6. X asset: 一条有用的英文 Post + 一张可核验英文视觉卡 + 真实发布链接。

## 扩展到 100 的规则

新候选必须至少有直接源、明确用例、可操作步骤、许可说明、是否实测状态。每批验证最多 10 个；差的丢弃，不追求数字。选择内容时优先已有实测/审核条目。不要将 GitHub star 数量等同于实用性，也不把 Skill 目录当作最近发生的重大版本发布。
