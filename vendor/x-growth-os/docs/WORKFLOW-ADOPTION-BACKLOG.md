# X Workflow 可采纳方案清单（2026-10-25）

**性质：** 对 [GitHub 调研](GITHUB-X-WORKFLOW-REVIEW-2026-10-25.md) 的实施化整理。调研记录保留原始结论，这份清单负责跟踪**采用/延期/验收/回滚**，避免未来再次调研同一问题。

**当前阶段：V0（每日生成 → 人工审核 → X 发布或可用的原生排期 → 记录）。** 此处出现的开源工具均**没有**因此自动完成安装、OAuth 授权或真实发帖。仓库是私有的，但仍不得提交 API token、Session Cookie、授权密钥或用户隐私。

## 状态定义与维护约定

- `process_adopted`：已吸收为提示词、模板或 SOP；**不代表运行了原项目源码**。
- `ready_to_evaluate`：有证据与测试方案，但实际集成、付费/授权和验收尚未完成。
- `deferred`：当前没有足够需求，不安装；只有触发条件满足才评估。
- `rejected`：与运营目标/平台规则冲突，默认不采纳。
- `production_accepted`：必须有日期、实际运行日志/发布 URL、失败测试结果、费用与负责人，不能只靠 README 宣称。

**修改规则**：每次改变状态或技术选型，记录日期、理由、一手证据 URL、部署/成本/风险、验收证据链接，并同步 [路线图](EVOLUTION-ROADMAP.md) 与 [CHANGELOG](../CHANGELOG.md)。不要因为上游更新就自动升级。

## 最小采纳矩阵

| ID | GitHub 项目 / 一手来源 | 可复用能力 | 当前状态 | 触发条件及下一步 |
|---|---|---|---|---|
| **XGW-001** | [langchain-ai/social-media-agent](https://github.com/langchain-ai/social-media-agent) | 一手链接 → 提炼信息 → 拟稿 → 人工编辑/批准 | **process_adopted** | 已映射到 [URL→X Prompt](../prompts/GITHUB-URL-TO-X.md)；后续按真实发帖体验优化，不部署其完整技术栈。 |
| **XGW-002** | [twitter/twitter-text](https://github.com/twitter/twitter-text/tree/master/js) | URL/Unicode 加权字符数解析 | **deferred** | 先用 X Composer 人工核对；当每周字符超限返工多次时，基于官方库实现本地校验器并写单元测试。 |
| **XGW-003** | [gitroomhq/postiz-agent](https://github.com/gitroomhq/postiz-agent) | 发布、排期、图片/Thread CLI/Agent 工作流 | **ready_to_evaluate**（V2 候选，未接入） | 每周有明显排期负担或连续漏发；先核对账号权限/费用，再手动授权，用测试帖子完整验收。 |
| **XGW-004** | [burnworks/x-scheduled-posts](https://github.com/burnworks/x-scheduled-posts) | YAML 排期、Thread/图片、ALT、dry-run、已发历史状态 | **deferred**（V2 备用） | 若优先 GitHub 原生排期，再审计源码、密钥权限、持久状态、重试去重；定时 Actions 并不保证准点运行。 |
| **XGW-005** | [anas-aqeel/Agent-X](https://github.com/anas-aqeel/Agent-X) | 选题来源、排重、审批状态、失败重试 | **process_adopted（仅思想）** | 审核卡中已记录来源/状态；当内容库存量变大、有实质重复时才引入自动去重。 |
| **XGW-006** | [gitroomhq/postiz-app](https://github.com/gitroomhq/postiz-app) | 跨平台内容日历、发布与效果分析 | **deferred** | 仅在确需可视化统一日历或多平台时与 XGW-003 进行**替代性**比较；避免两套都部署。须复核 AGPL-3.0 义务。 |
| **XGW-007** | [n8n-io/n8n](https://github.com/n8n-io/n8n) | 定时触发、API 集成、内容流水线编排 | **deferred**（V3/V4） | 先证明手动研究/记录是最大瓶颈，再评估运行成本、X 访问权限、失败告警；不为了技术堆栈而引入。 |
| **XGW-009** | [trailofbits/skills-curated X Research](https://github.com/trailofbits/skills-curated/blob/main/plugins/x-research/skills/x-research/SKILL.md) | 只读 X 检索、高互动排序、线程读取和缓存成本管理 | **process_adopted（仅研究规则）** | 当前手动实施；按 30 分钟/天瓶颈、X 官方 API 授权、费用上限决定是否安装。 |
| **XGW-010** | [Desearch-ai/x-monitor](https://github.com/Desearch-ai/x-monitor) | 只读关注列表、已见帖去重、定期窗口和候选日志 | **process_adopted（只借鉴机制）** | 不部署其外部 API/Discord，先用 CSV 留痕；以后审核数据许可。 |
| **XGW-011** | [xdevplatform/docs](https://github.com/xdevplatform/docs/tree/main/x-api/posts/search) | X 官方 Posts Search / Lookup 规范 | **ready_to_evaluate（API 未授权）** | V2 仅在明确同意 OAuth/Bearer/API 消费预算与账号风险时评估。 |
| **XGW-008** | [altansaid/ai-social-engagement-engine](https://github.com/altansaid/ai-social-engagement-engine) | 基于关键词的社媒互动引擎 | **rejected** | 当前不引入任何自动点赞/自动关注/对陌生人的批量回复或私信。坚持真实、人工互动与 [X 自动化规则](https://help.x.com/en/rules-and-policies/x-automation)。 |

原始项目如何工作、源码检查范围、局限与来源保留在 [调研报告](GITHUB-X-WORKFLOW-REVIEW-2026-10-25.md)，此处不重复维护功能清单。

**新的研究准入：** [X-SIGNAL-RESEARCH.md](X-SIGNAL-RESEARCH.md) 与 [GITHUB-VALUE-AUDIT-2026-10-25.md](GITHUB-VALUE-AUDIT-2026-10-25.md) 是 XGW-009～011 的强制筛选依据。以上均无实际 API/OAuth 测试记录。

## 接下来怎么执行（只保留 3 个动作）

1. **今天开始用 XGW-001 的轻量产稿流程**：有项目链接用 [GITHUB-URL-TO-X.md](../prompts/GITHUB-URL-TO-X.md)，没有链接用 [DAILY-POST.md](../prompts/DAILY-POST.md)；最后必须有人检查来源、事实、英文图和 X 字数。
2. **发布后填 [posts.csv](../templates/posts.csv)**：发布状态要有真实 X URL；没有 URL 就不能标 `published`。每周从真实表现选择改进方向。
3. **满足稳定性门槛时再进入 V2**：先完成 14 天观察（至少 12 篇有效作品、一份周复盘）；若人工排期/漏发问题明显，选择 Postiz Agent 或 GitHub Actions 二选一验证，**不是一口气全部安装**。

## 未来升级验收卡（执行时复制并填写）

**候选 ID：** XGW-___  
**触发问题及证据：** 哪项耗时/发布失败、每周几次、有哪条操作日志？  
**版本/上游 commit：**  
**核验日期、license、费用、账号权限：**  
**最小实施范围：** 第一阶段仅人工批准后的计划发布；不做自动互动。  
**沙箱测试：**
- [ ] 无有效凭据时安全失败，不打印密钥
- [ ] 一条英文短帖可以成功创建，有真实 X URL
- [ ] 图片与 ALT 正确；2–3 条 Thread 顺序准确（如果确需）
- [ ] 同一草稿重复触发不会重复发帖
- [ ] 可查看计划任务、取消未发任务、手动重新执行失败任务
- [ ] 运行有可追溯日志、异常通知、费用上限与人工紧急停止办法
- [ ] 平台条款、许可证和数据安全已复核
- [ ] 观察 14 天，无严重漏发、重复或错误内容事故

**结论：** `evaluate / postpone / reject / production_accepted`  
**验收证据 URL：**  
**回滚方法：** 停用定时器 → 撤销授权/密钥（如适用）→ 转回 V0 手动发帖 → 确认没有排期任务残留。  
**下一次检查：**  

> 备注：GitHub Actions 的定时任务可延迟或丢失；需要可靠发送时，应有外部状态核对和人工补救，而不是将 workflow `success` 等同于 X 已实际发布。官方参考：https://docs.github.com/en/actions/how-tos/troubleshoot-workflows

## 历史决策

| 日期 | ID | 决定 | 依据 | 执行状态 |
|---|---|---|---|---|
| 2026-10-25 | XGW-001 | 复用 URL→草稿→人工审查的工作流思想 | 项目 README；V0 已有提示词 | process_adopted |
| 2026-10-25 | XGW-005 | 只借鉴去重/审核状态，不部署 Agent-X | 成本和复杂度不匹配当前日更任务 | process_adopted |
| 2026-10-25 | XGW-003/004 | 保留两种候选发布层，但现在不授权、不上线 | 尚未有运营负担基线、测试/费用/权限未确认 | pending |
| 2026-10-25 | XGW-008 | 不做机器人式增长 | 平台政策与长期账号质量风险 | rejected |

**最后更新：2026-10-25。** 以上状态描述的是**仓库运营方案**，不是任何第三方系统的在线状态。
