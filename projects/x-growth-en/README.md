# X English creator track / Original Content Rewards

- [90 天原创奖励资格增长实验](original-content-rewards-90d.md)：当前计划草案，须人工确认账号、规则及实验恢复状态。
- [资格截图的账号级快照模板](templates/x-rewards-eligibility-snapshots.csv)：只记录 Creator Studio 官方合格门槛；**没有自动采集**，公开库默认不保存真实个人账号指标。
- [每周人工复盘模板](templates/x-rewards-weekly-review.md)。
- [现有帖子索引](templates/posts.csv)、[账号观察](templates/x-account-snapshots.csv)和[帖子同龄快照](templates/x-metric-snapshots.csv)：既有数据事实源，新增计划不得覆盖旧记录。
- [项目账户契约](project.yaml)：当前 `language: en` 和 `publication_mode: MANUAL_ONLY`，双语方案须经过账户角色和实验审批。
- Growth Operator: `../../skills/x-organic-growth-operator/`；X post gate: `../../scripts/x_post.py`；bridge: `../../scripts/x_growth_pipeline.py`。

**状态边界**：ContentOps 对 X 已集成离线内容审核和人工发布门禁；X 平台真实发布、官方认证粉丝/合格首页曝光导入、最终收益资格均未在此仓自动实现。原 `X-SuperPlay-X-Growth-OS` 属待下线迁移来源，不是未来执行仓。严格禁止把 GitHub 文件写入视为 X 发帖成功。

- High-engagement **original post writing**: [x-high-engagement-copywriter](../../skills/x-high-engagement-copywriter/SKILL.md) — conversation-derived hypotheses, editorial drafts and A/B design, **not** verified virality or an auto-publish tool. This project's English account remains English; Chinese variants need separate account/language approval.

### Copywriter offline validation and learning

- Skill: [X high-engagement copywriter](../../skills/x-high-engagement-copywriter/SKILL.md). Verified source IDs S01–S10 + summary-only S11 are in [sample ledger](../../skills/x-high-engagement-copywriter/references/sample-ledger.json); the pasted examples' X performance remains **user-reported, not authenticated here**.
- Runnable draft example: [synthetic JSON fixture](../../tests/fixtures/x-copywriter-draft.json). Draft checker (no platform access): \`python skills/x-high-engagement-copywriter/tools/check.py --corpus\` and \`python skills/x-high-engagement-copywriter/tools/check.py --check tests/fixtures/x-copywriter-draft.json\`.
- After **real manual publication**, retain account-specific real X URL and metrics in the existing \`templates/posts.csv\` and \`templates/x-metric-snapshots.csv\`. Label \`posts.csv.experiment_variable\` with \`cw:Pxx:hook_variant\` then use \`python skills/x-high-engagement-copywriter/tools/check.py --review projects/x-growth-en --age-window T+24h\` for descriptive review. No auto-publish and no new analytics table.
