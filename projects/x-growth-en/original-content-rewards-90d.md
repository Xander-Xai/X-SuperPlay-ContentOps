# X Original Content Rewards｜90 天合规增长实验

> 状态：**PROPOSED / OWNER_REVIEW_REQUIRED**；建立于 2026-11-03；仅定义人工执行计划，**不是**平台授权、收益资格确认、X 发布成功或真实增长成果。
>
> 归属：`X-SuperPlay-ContentOps/projects/x-growth-en/`（X 执行权威）。跨平台战略仍归 `X-SuperPlay-Strategy`；商业 Stage、收入与付款事实仍归 `X-SuperPlay-OPC-Blueprint`。原 `X-SuperPlay-X-Growth-OS` 是待下线的历史来源，**不是**新的执行事实源。

## 0. 起点与边界

- 2026-11-03 创作者提供 X Creator Studio 的 Original Content Rewards 资格截图：Premium 与年龄显示通过；500 认证粉丝和过去 90 天 500,000 认证用户首页曝光尚未达标。**数值为当时用户截图，并非已通过官方授权读取**。此公开仓不上传原始截图、账号身份、精确账户数据；真实数值仅在授权私有台账保存。
- `projects/x-growth-en/project.yaml` 只绑定**唯一双语 X 账号**，`language: multi`、支持 `zh/en`，仍为 `MANUAL_ONLY`。`x-growth-en`路径和`x-superplay-english` slug仅兼容旧数据，不是第二账号；中文/英文内容和A/B/C回复都属于同一个账号。各语言的逐帖指标独立分析，账号级Q和粉丝不能双重计数。
- ContentOps 已有 X 线下增长 Skill、文章审核/可选图片与ALT/人工发布门禁、`scripts/x_growth_pipeline.py`、`projects/x-growth-en/templates/posts.csv`、账号与帖子数据 CSV；**目前无获授权的 X 自动发布、回复、读取账号数据或收益指标接口**。
- **2026-11-14 V1.4 单账号目标（延续 V1.3 数量）**：同一账号每天人工回复160条（A=灵感泛娱乐40、B=灵感AI科技40、C=时间线AI科技80），**原创发布目标24条（中文20、英文4）**，题材不限技术。旧英文4条/日与中文另设账号说法已撤销。不能绕过事实/原创、人审或真实URL；纯文字可用 `post_format=text`，图文 `post_format=image` 时图片/ALT必须合规，不能把待审稿算已发布。

## 1. 官方资格与计量口径（执行前必须重新核实）

首次验证：2026-11-03；最新政策以创作者后台与官方规则为准：
- 原创奖励：https://help.x.com/en/using-x/original-content-rewards
- 真实性：https://help.x.com/en/rules-and-policies/authenticity
- X 自动化：https://help.x.com/en/rules-and-policies/x-automation

| 项目 | 官方条件 / 计量 | 证据要求 |
|---|---|---|
| 认证粉丝 | 至少 500 位 **Verified followers** | Creator Studio 官方资格页同日截图或经授权官方导出 |
| 认证首页曝光 | 最近滚动 90 天至少 500,000 次来自认证用户的 **Home Timeline** 曝光；**回复不计入**申请门槛 | Creator Studio 的同名资格进度；不是普通 post impressions |
| 合格曝光 | Premium 用户的首页唯一合格曝光，帖子至少 50% 可见；同一账号对同一帖子去重；付费推广和人为刷量排除 | 不用普通浏览量估计或换算 |
| 资格 | 活跃的指定付费订阅、18+、支持地区实际居住、账号状态良好、原创活跃、适格账户类别 | 每项独立核验；**VPN/IP/自称地区 ≠ 居住地和收款资格** |
| 原创 | 自己的独立分析、原创实践和有实质增量的观点；不得复制、低改或聚合搬运 | 每帖 Source/Claim/Proof、使用权、审稿回执 |
| 审批/收益 | 达数字门槛也不保证通过；须申请审核，保持持续资格。现行官方说明双周支付、最低 30 美元，非美国收款通常需 Stripe/KYC | 收益只在获批与真实到账后记为商业事实 |

**强禁止**：互关互赞刷指标、购买或交换互动、自动批量评论/私信/点赞、用虚假身份/地区绕过资格、重复低价值同质帖、自动化生成或发布内容以追求奖励收益。尤其避免把“如何获取 X 奖励/收益技巧”作为唯一内容主题，官方将仅专注变现教学/讨论/最大化收益的内容列为不合格。可用 AI 协助分析和草稿，但账号本人需要实质原创贡献、人工审查并人工发帖。

## 2. 目标与计算（目标不是预测）

- 基准：`target_verified_followers = 500`；`target_verified_home_timeline_impressions_rolling_90d = 500000`。
- 示例算术：从零计算，90 天平均每天约需 5,556 次合格首页曝光；**不是**普通曝光，且在滚动窗口中早期值会退出。
- 真实完成量与剩余缺口仅用官方 Creator Studio 账号级快照计算；`unknown != 0`，不从帖子浏览量推算验证资格。
- 方向性里程碑（仅内部挑战值，非平台算法规律/未来预报）：D14 完成基线与规则验证；D30 识别可重复主题；D60 有可验证的阶段趋势；D90 复核资格。可以在私有运营台账自行添加期望粉丝数/合格曝光，但不得当作已观察事实。
- 同时维护第二目标：高质量讨论、复现、代码/资料请求、真实潜客问题。它们与资格计数独立；`Views != Validated Demand`。

## 3. 内容定位和原创产品

**定位候选**：AI Builder × AI Tools × Real-World Experiments。以本人真正做过的 AI 工程/工具测试为起点；表达可辨认的结论、证据、反例和可复现过程。

| 内容柱（初始假设） | 比例 | 示例与证据边界 |
|---|---:|---|
| AI 工具亲测 | 40% | Codex / Claude Code、工具选型、测试前后对照；无实测不得称“我验证了” |
| Build in Public / 工程复盘 | 30% | RAG、Agent、开源 SaaS 改造、VPS；版本、配置、日志、限制经脱敏 |
| 技术观点与讨论 | 20% | Agent 复杂度、React/Vue/Python、模型工程取舍；有反对视角 |
| 个人过程 / 轻松内容 | 10% | 独立开发者经验、失败/突破、真实观察；不为凑数抄段子 |

这些比例、发布时间和用语是**待检验假设**，不在代码里硬编码为算法策略。

每帖最小内容合同：
`account + language + ICP + source_or_observation + original_thesis + honest_claim_scope + counterargument + copy + post_format(text|image) + image/ALT(if image) + permission_check + mode_specific_human_review + post_url(if published) + content_id`。

原创主帖优先采用：
`Finding / tested result → 1–3 observations → genuine artifact or repo link → substantive question (optional)`。
评论主要用于建立真实行业联系；不把回复量计入 500,000 申请门槛，也不靠“求关注/求转发”获得奖励。

## 4. 90 天执行分期

### D0–D14｜诊断与恢复（V1.4下的账号核验，不再自动恢复旧低频配额）
1. 人工确认账号 handle、语言、Profile/Bio、置顶、角色、当前规则地区/KYC、账号通知，核实最近 14 天旧恢复实验的状态。
2. 将旧仓已记录的帖子 ID/URL/发布状态/素材权利/原始时序与 ContentOps `posts.csv` 对账：`draft` 仍为草稿；`reported_published_url_pending` 必须见真实 URL 才升级为已发布。
3. 人工在官方 Creator Studio 核对 **Verified followers / Verified Home Timeline impressions (last 90 days)**；保存脱敏的私有证据编号；缺失留空。
4. 当前唯一账号每日原创发布目标24条（zh20/en4，满额168条/周），不要求全技术；旧4条英文/天、28条/周和更早低频都为历史。发布前按语言与来源逐条审核，回复160条/日为受合规约束的人工目标，禁止批量骚扰或自动互动。
5. 本周结束记录：来源覆盖率、T+24h / T+72h 快照、账号认证粉丝增量、滚动 90 日合格首页曝光增量、创作工时。样本不足则写 `INCONCLUSIVE`。

### D15–D30｜建立有效内容家族
1. 基于一致口径，选择 1–2 个高质量讨论与账号增量更好的主题；保持账号 ICP 稳定。
2. 每周至少 1 个真实项目的完整可复现案例，拆为不同原生角度的独立帖子，不可机械复制/搬运。
3. 中英文是**同一个账号下的两个内容语言队列**，并非两个账号。逐帖带语言，若做语言实验要控制受众、主题、时间等变量；不同语言结果不可当作因果增益。
4. 用户已经明确同一账号中文20+英文4=每日24条原创发布目标；任何帖子先人工审查、再发布、再按真实URL登记。未达数量记录风险或成本，不能为了数字违规；此旧90天方案不自动证明平台资格。

### D31–D60｜扩大经过验证的系列
1. 以自己账号的 `Topic Cluster × Packaging` 优胜系列继续新案例、反例、性能边界、真实问题；不是旧帖换词重发。
2. 合规的同行协作：共同复现实验、观点辩论、GitHub 技术交流；不用互粉互赞组织或流量交换。
3. 周度计算两个独立漏斗：①资格指标（官方认证粉丝/合格首页曝光）②商业信号（真实问题/请求/授权转交）；不凭曝光承诺获客或收入。

### D61–D90｜达标验证与申请准备
1. 判断滚动 90 日数据是否足够；日均所需按 **目标减现值再除以剩余天数** 仅作算术，不视为预测。
2. 审核原创权利、平台状态、居住与收款资格；准备 Creator Studio 资格申报；审核通过前记为 `APPLICATION_PENDING`，不得记录为收益。
3. 若差距巨大，降级为长期账号价值实验，不为短期奖励加码刷屏或违反政策。

## 5. 每周人工运营 SOP（遵守 ContentOps 现有门禁）

1. **周一**：从本人真实开发记录选 2–4 个可论证话题，记录内容母资产与账号角色、ICP、语言。
2. **周二至周六**：实测/截图/观点证据 → 内容/图片/ALT 审核 → 本人自行在 X 发布 → 回填真实 URL；不足以完成审核的稿件保留 `DRAFT`。
3. **每日**：只在有真实补充的讨论中自然互动，人工回复问题，不设置强制评论次数，不机械蹭热点。
4. **固定数据窗口**：T+2h（可选）、T+24h、T+72h、T+7d 记录帖子实际可见数据；认证首页曝光为官方**账户滚动窗口**快照，不拆到单帖。
5. **周日**：人工做一份决策：`CONTINUE / REPACKAGE / PAUSE / INCONCLUSIVE`，明确本周变化的唯一主要测试变量及下次采集日期。

### 首周选题池（候选，不代表已经实际发过）
- 我为什么放弃从零重写已有成熟 GitHub 工具（开源选择案例）。
- Claude Code 和 Codex 在同一个任务里的真实边界（须有实验输出）。
- 为什么增加 Agent 数量可能降低工程可靠性（须有具体错误机制）。
- 本地单卡做 LLM 开发最容易忽略的资源约束（须展示真实机器/版本）。
- RAG Evidence Gate 的价值与失效边界（区分设计与已测指标）。
- 独立开发 SaaS 的首个可验证交付流程（避免虚构上线/收入）。

## 6. 数据合同：不要重复建立影子事实源

**已存在**（保持权威，不覆盖/伪造）：
- `projects/x-growth-en/templates/posts.csv`：post 索引、状态、真实链接。
- `projects/x-growth-en/templates/x-account-snapshots.csv`：账户总体粉丝/曝光、账号通知。
- `projects/x-growth-en/templates/x-metric-snapshots.csv`：每帖、同发布时间龄快照；`impressions` 与认证主页曝光不是同一字段。

**新增**：
- `projects/x-growth-en/templates/x-rewards-eligibility-snapshots.csv`：仅用于 Creator Studio 的资格/地区/KYC/滚动 90 日官方账号级观测；先只提交表头，无私人数值。
- `projects/x-growth-en/templates/x-rewards-weekly-review.md`：人工复盘资格趋势、运营实验、政策与下线风险。

统一规则：`source + observed_at + timezone + metric_definition + account_alias + data_access` 必须完整；未知不是 0；不得以公开账户 follower 数代替 verified followers；不计算帖级的“合格曝光归因”；不得承诺收入。

## 7. 与旧 X-Growth-OS 下线的关系

- 内容生产与 X 增长执行权威：`X-SuperPlay-ContentOps`。旧仓 `X-SuperPlay-X-Growth-OS` 仅作只读迁移核验来源，**不要继续向旧仓提交日常内容**。
- 完成旧仓文件清单、迁移映射、帖子逐行对账、媒体/权限核验、脚本/SOP 等价检查、旧 PR/Draft 和跨仓引用替换后，再由 Owner 单独审核归档/删除；**本计划不授权删除旧仓**。
- ContentOps 是公开仓：私有旧仓资料、私信、Cookie、Key、原始账号截图、客户数据、未许可素材不应直接迁移到公开仓。
- 迁移完毕仍保留 PR/commit/审查证据，不得把仅在历史仓存在的功能写成 ContentOps `main` 已实现。
- `X-SuperPlay-Strategy` 仅持有跨平台定位、Playbook 和新的执行仓库导航；不创建第二套 X 数据表。

## 8. 验收清单

- [ ] 本计划可从 ContentOps 项目入口找到，包含官方政策链接/核验日期。
- [ ] 新版V1.4数量目标与账号语言/ICP、证据、版权、人工发布治理均一致；旧恢复频率仅用于历史参照。
- [ ] 已有 post/account/post metric CSV 未被清空或重建；新增资格 CSV 只有 header。
- [ ] 数字门槛、普通曝光/合格曝光、账号/帖级指标、滚动窗口互不混淆。
- [ ] 人工内容/配图/ALT 审核与发布 URL 回执仍是硬要求。
- [ ] 不出现批量自动化 X 互动、付款或伪造身份的路径。
- [ ] Strategy 指向 ContentOps 的 repo 字段与执行 Playbook 链接同步修改。
- [ ] 真实数据/账号验证仍待 Owner，人审/平台收益不能被 GitHub CI 冒充。
- [ ] 旧仓的历史完整迁移与归档另列阻断项，不以本次 PR 合并冒充下线完成。

## 9. 最小真实成功定义

此 PR 成功 = **规范文档 + 空白原生资格快照模板 + 周复盘模板 + 正确跨仓索引**，不包含账号授权、实际发帖、资格达标、收益入账、全量旧仓迁移或自动发布功能。真实经营效果需随后按官方数据和可验证回执持续确认。
