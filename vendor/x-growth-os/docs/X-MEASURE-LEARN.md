> **2026-10-26 DATA-INTEGRITY ADDENDUM:** Apply [14-day Recovery V2](X-GROWTH-RECOVERY-2026-10-26.md), including its diagnostic decision tree and follower-attribution safeguards. User reported three posts published on 2026-10-26; without exact X URLs their interim status is `reported_published_url_pending`, not verified `published`. Never impute 0 for missing metrics, never allocate account-level net follower changes to one post, and never compare arbitrary age windows. Add append-only **account-level** observations in [x-account-snapshots.csv](../templates/x-account-snapshots.csv) and complete [recovery weekly review](../templates/X-RECOVERY-WEEKLY-REVIEW.md). Keep original per-post snapshot rules below.

---

# X 内容运营与数据闭环：V0 操作手册（2026-10-25）

> **范围**：面向现有英文 X 账号，用最少步骤把“准备内容 → 人工发布 → 真人讨论 → 原生数据 → 周复盘 → 下一次实验”跑通。**不宣称已登录 X Analytics、接入 X API 或自动获取指标。** 本库只维护 X 执行证据；平台组合/内容战略在 [X-SuperPlay-Strategy](https://github.com/Xander-Xai/X-SuperPlay-Strategy)，商业 Opportunity/付款在 [OPC-Blueprint](https://github.com/Xander-Xai/X-SuperPlay-OPC-Blueprint)。

## 1. 每天最低可执行流程（不为了配额制造作品）

| 时点 | 行动 | 原始证据 |
|---|---|---|
| 发布前 | 选择一个有可信来源的 AI 工程问题/项目实验，提出一个具体而可操作的英文结论 | `source_url` + `content_id` |
| 发布前 | 检查事实、图像、授权、链接，人工批准一条 Post（复杂时最多3条 Thread） | 对应 `posts/*.md` |
| 发布后 | 只有真实 X URL 可访问，才将 `templates/posts.csv` 该条状态从 `draft` 改为 `published` | `x_post_url` |
| 当日/次日 | 人工回复本帖的专业问题，在相关同行讨论中提供真实帮助，不做自动点赞、刷评、批量回复或私信 | 仅存匿名问题分类/链接（如公开） |
| 到期 | 打开该账号实际可见的 X 原生分析入口，将相关作品数字录入 `templates/x-metric-snapshots.csv` 的新行 | `observed_at / metric_source` |
| 周日 | 按 `templates/WEEKLY-REVIEW.md` 比较相同时间窗口和内容形式，选择下周一个主要测试变量 | 完整 Weekly Review |

官方参考：[X Post Analytics](https://business.x.com/en/help/campaign-measurement-and-analytics/tweet-activity-dashboard)；[X 自动化政策](https://help.x.com/en/rules-and-policies/x-automation)。功能因账号/产品权益而异；以实际后台可用为准。

## 2. 怎样正确收数

1. 在 `templates/posts.csv` 找到已发布且具真实 URL 的作品；`draft`/`scheduled` 不得补 0 冒充发帖。
2. 读取真实发布时间（日期 + 时区 + 时间）；若找不到精确时刻，不要事后编造 T+24H，记录窗口 `unknown` 并说明原因。
3. 在条件允许时分别于 T+24H、T+72H、T+7D 查看对应帖子的真实数据；T+2H 可选。不保证 X 提供历史时点回溯，所以必须真的在近似到期时采集，并保留采集时间与窗口偏差。
4. 记录 `metric_source=native_manual/native_export/official_api`（以实际来源填写；不要复制示例当事实）；`data_access=available/partial/unavailable`；缺失字段留空并填写 `missing_reason`。
5. 同一 snapshot ID 不可覆盖旧数据。若后续平台修正数据，写新 snapshot ID 并说明，不偷偷改旧行。
6. `account_net_follower_change` 应当记在周报账号级，不映射到某条帖；单帖 `attributed_follows` 只有平台确实报告对应归因时才填写。
7. 不将推广曝光、自然曝光、不同数据口径混在一起计算；不使用爬虫/网页点击模拟 X 自动化。

注意：如果当时无真实指标、账户无权限或页面无法打开，明确记录 `unavailable`，**不认为该帖互动为 0**。所有指标均属于观察数据，不能单凭相关性说明算法因果。

## 3. 一周只做一个主要内容实验

优先从现有项目实际运行结果提取内容，按既有 Strategy 约定：
- A：AI 新能力实测；B：AI × 真实工作；C：AI 生意 / 自动化实验。
- R：Result-first；C：Conflict-first；Q：Question-first。
- 单次只主要改变 Topic、Hook、图像、CTA、时段中的一个；其他尽量维持一致。小样本只能做初步假设。

X 典型诊断：

| 观察 | 不能直接下的结论 | 建议下一步 |
|---|---|---|
| 曝光不高 | “算法限流了” | 检查内容定位、话题关联、受众是否具体 |
| 曝光有了，相关回复很少 | “用户不需要 AI” | 把工具介绍改成读者能复现的机制或具体测试 |
| 技术讨论多，净关注少 | “这类技术没价值” | 重写个人简介/置顶内容，继续验证同系列 |
| 高浏览、请求源码的人多 | “已有付费需求” | 给出可复现 GitHub 资源，询问真实用途；需要 OPC 再做商业验证 |
| 时间投入增加、有效信号不增 | “要上更多 Agent” | 降复杂度、停止低效制作/发布路径 |

同平台、同格式、同年龄窗口对比，样本不足20条先记录学习结果，不打“爆款公式”标签。

## 4. X 专属周报要交付什么？

填写 [每周复盘](../templates/WEEKLY-REVIEW.md)，至少包含：
- 发布量、失败/草稿数、账号粉丝基期/期末与净增长（账号级）。
- 每个被比较作品的 `content_id + 真实 URL + 相同年龄窗口`；原生曝光、互动、主页点击与链接点击仅在可得时填写。
- 有多少去重有效提问、请求代码、想部署、想讨论真实工作问题；匿名概括，不公开 DM。
- 研究、写作、发布、互动、收数的工时，哪种内容更高效。
- 下一周选择**一个**改动变量、明确对比指标和观察截止时间。
- 若 Signal 涉及潜在商业需求，只将脱敏候选提交 Strategy → OPC，不能在本库宣布成交。

## 5. 数据记录分工

```text
templates/posts.csv             → 每条内容的唯一索引，状态和真实 URL
templates/x-metric-snapshots.csv → 同一作品每个真实采集时点的一行（append-only）
templates/WEEKLY-REVIEW.md      → 每周人审决策 + 账号级涨粉
Strategy/90-Templates           → 跨平台模板与字段口径
OPC-Blueprint                   → 唯一商业事实源
```

推荐成熟度：
- **V0**：人工整理真实指标与有效评论、每周复盘一次。
- **V1**：可靠 CSV 读入、自动计算同窗口指标和草拟周报（只读，人工审批）。
- **V2**：账号授权条件满足后尝试只读官方 API 采集；验证权限/速率限制/成本/撤销机制。
- 不将没有授权的网页抓取、自动互动和“数据缺失补0”视为自动化进展。

## 6. 验收与回滚

**14天验收**：至少形成两次真实周复盘（或明确记录未完成原因）；每个 published 有 URL；有实际获取的帖子快照且指标来源可追溯；能说出一个内容决策及下一次实验；记录创作+运营总工时。

触发回滚：发现发布记录无 URL、指标定义混乱、疑似隐私泄露、自动化权限不明、连续两周只有量没有有效讨论时，优先恢复人工小规模验证，不再增加发布渠道。当前 `posts.csv` 的历史记录是 draft 时必须保留，不允许伪造已发布状态。
