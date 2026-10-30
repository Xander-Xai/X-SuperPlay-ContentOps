> **2026-10-26 RECOVERY MODE — ACTIVE 14-DAY OVERRIDE.** Read [X Growth Recovery V2](X-GROWTH-RECOVERY-2026-10-26.md) first. The older daily frequency and 15–30 minute production loop below are **historical defaults and suspended as quotas**. During recovery, recommend 3–4 qualified original posts/week/account, normally ≤1/day, with one consistent ICP/account, real evidence and human distribution. No automatic posting or scraping. Owner-reported posts without real URLs receive `reported_published_url_pending` (not `published`). Maintain original mandatory PNG/JPG + ALT gate. Measure profile visits, qualified feedback and account-level net followers using real source data. All metrics absent stay blank. Do not self-award quality scores as growth evidence.

---

# V0: 每日 X 发帖操作手册

## 最高优先级发布闸门

**每条产出必须有最终英文文案 + 一张主题匹配、真实存在、能上传 X 的 PNG/JPG + 英文 ALT**。参见 [文案配图成套交付规范](POST-IMAGE-DELIVERY-GATE.md)。没有图片是未完成草稿，不能标为可发布。与旧版“可无图”建议冲突时，以本规则为准。

## 目标与真实边界

目标：**每天形成并发布一份高质量英文作品，积累对 AI 实用工具、开发者和独立创业内容感兴趣的粉丝。** 默认 **1 条原创英文 Post**，**必须同时交付经过验收的英文配图（可上传的 PNG/JPG）**；确有必要时最多 3 条 Thread（不为了凑数拆分）。

**V0 是半手动流程**：ChatGPT 做研究、写作、配图；发布前由人核实、审核并通过 X 发布或排期。此仓库尚未接入 X API，不能宣称自动发帖成功。若暂时没有时间，提前储备已核验的常青内容，排入支持的 X 官方排期入口。

## 新增 X × GitHub 双来源准入（强制）

开始日更前按 [X Signal Research SOP](X-SIGNAL-RESEARCH.md) 发现高互动 AI 生产力/商业讨论：保存原帖、作者、互动数据与快照/来源等级，绝不把高曝光直接当作正确性证据。交叉使用 [GitHub Value Audit](GITHUB-VALUE-AUDIT-2026-10-25.md) 核实具体 AI 提效机制、买方/交付物/实验和运行成本，`hold_until_case` 不得直接自动选题。没有可核实的 X 讨论可退回严格 GitHub 内容，但注明缺失 X 信号。不能照搬他人 X 文案/图片。

## V1.3 教程价值与合规硬性审核

所有 X 实战教程先执行 [教程两分钟路由](TUTORIAL-QUICK-VALUE-ROUTER.md) 和 [AI 提效/变现价值门禁](TUTORIAL-VALUE-AND-MONETIZATION-GATE.md)：明确职业角色、重复工作、具体技术/AI 的输入输出、**A 可测试净提效/成本/质量**或**B 合法付费客户/交付物/定价假设/运营成本与试点**。泛平台运营秘籍、高互动但与 AI 无关的赚钱操作，不自动进入教程内容柱。可以作为题材结构参照。

参考四篇 X 长文的完整审查见 [对照案例](TUTORIAL-FOUR-X-REFERENCE-AUDIT-2026-10-25.md)。禁止刷单、虚构低价 SKU、误导买家/平台、冒用身份地区、误填银行税务和忽视许可证。X 旧创作者 Revenue Sharing 2026 年 9 月结束，所有收益教程必须以现行官方 Original Content Rewards 为准；自报收益≠可靠商业收入证据。通过门禁再制作完整实操、对应英文 X 正文及真正的 PNG/JPG+ALT。

## 实战教程独立工作流（第四类内容）

遇到“如何运营小红书、GitHub 自学 LLM、自媒体工作流、自建节点”等话题时，先按 [教程内容 SOP](TUTORIAL-CONTENT-WORKFLOW.md) 执行需求 → 官方/GitHub课程聚合 → 环境/权限/成本 → 编号实操/预期结果 → 实测/失败分支 → GitHub 完整教程 → X 英文精华稿 + 实际16:9 PNG/JPG + ALT。完整教程优先在 [tutorials/](../tutorials/README.md) 留下可运行、可追溯的知识资产，候选在 [tutorial-candidates.csv](../templates/tutorial-candidates.csv) 管理。若未真正执行，必须标记 `REPRO_PENDING` 而非“已实测”。具体入口：[TUTORIAL-TO-X.md](../prompts/TUTORIAL-TO-X.md)。

教程不要求最近72h，但**引用的平台政策和命令版本必须核实**；即使教程长文正确，也不能省略 X 配图闸门。初期每周一篇完整教程是试验目标，不要牺牲日更稳定性。

## 写稿前先通过原创洞察审核

必须使用 [Editorial Quality Gate](EDITORIAL-QUALITY-GATE.md)，针对选题提出至少 3 个不同判断，逐个核验因果机制与反例，并进行六维 0–5 主观质量评分（推荐 ≥24/30，且新颖性、证据、机制均 ≥4）。可以从 [原稿对照](EDITORIAL-BEFORE-AFTER.md) 看出：清单式正确建议不等于高价值技术评论。**评分是编辑辅助，不是 X 推荐算法，不保证涨粉。**

如果缺少能支撑观点的证据，则收窄结论、更换 evergreen 选题或推迟发布；不能编造最新事件或所谓独到观点来凑日更。

## 每篇配图都要经过视觉编辑质量门槛

使用 [Visual Editorial Standard](VISUAL-EDITORIAL-STANDARD.md) 和 [Visual Brief](../prompts/VISUAL-BRIEF.md)。默认先考虑**真实一手图/截图**或**只突出一条判断的可编辑 SVG**，必要时才调用生图。上一版科技海报因通用霓虹渐变、机器人与密集卡片而被用户明确否决。优先清晰的编辑式设计，不能通过不断加“高质量、科技感、炫酷”等形容词补救。

所有配图都须核对项目、英文、技术关系、来源、手机版可读性；评分 0–10，仅用于编辑质检。若无法匹配，不可发布，保留草稿并修复配图，不可用无关图片补位。

## 每天 15–30 分钟

1. **输入**（约 2 分钟）：在 ChatGPT 使用 [prompts/DAILY-POST.md](../prompts/DAILY-POST.md) 并指明当天日期、需要的主题优先级。要求必须联网与事实核验，**每篇都必须交付实际图片与文案**。
2. **核验**（约 5–10 分钟）：先打开候选 X 原帖及上下文、记录高互动证据等级；再逐条打开原始 GitHub Release / PR / commit / SKILL.md 或官方公告。事件时间在执行时点往前 72 小时内；**热榜出现时间不等于更新发生时间**。Skill 教程不作为“新事件”处理。
3. **选择及红队**（约 3–8 分钟）：先提出至少 3 个不同且有证据的角度，再挑原创性、证据和因果机制最强的一条；说明最强反例。只保留核实的数字，区分发布者宣传、独立测量、推断、验证中的商机。
4. **审稿**（约 3 分钟）：默认单 Post；如果不够清楚，改成最多 3 条，核对 X 字符计数；宁可写短（建议预留长度缓冲）也不要卡极限。链接、emoji、不同 Unicode 字符可能受 X 加权计数影响，最终以 X 撰写器的实际计数为准。
5. **配图**（约 2–5 分钟）：先选源图或编辑式 SVG；优先一条论点、清晰字体与留白。对照 [visual standard](VISUAL-EDITORIAL-STANDARD.md) 检查来源、设计和手机可读性；错配其他项目时弃用，每天都必须有通过审核的实际 PNG/JPG 配图。16:9，手机上三秒读懂，不能让示意图伪装为真实 Benchmark / 产品截图。
6. **发布**（约 2–5 分钟）：在 X 新建 Post，贴第一条文字并附图；如果是 Thread，发布第一条后用“回复”接第二、第三条，确保连续且顺序正确。也可以按实际可用的 X 排期入口排期**单条**；Thread 排期能力需在当前界面验证，不能默认支持。
7. **记录**（约 1 分钟）：向 [posts.csv](../templates/posts.csv) 新增一行，填 URL / 状态 / 主题 / 证据链接，不需要暴露敏感账号数据。先生成但没有发布的记录标记 `draft`，已排期为 `scheduled`，仅当有真实链接才是 `published`。

## 失败时怎么办

- **72 小时无高价值事件**：改发已核验的 Skill 教程或真实工作流，标签 `evergreen`；严禁编造时间。
- **图片生成失败**：重试一次；若仍失败，使用可核实的原始图片，或准确排版的 SVG 转 PNG；最终仍失败则保持 `draft/image_missing`，不得宣布帖子完成或建议纯文字发布。
- **API / Web / 来源不可访问**：不引用无法核实的关键断言；改选另一题。
- **当天来不及研究**：优先从有原始证据的内容库中挑选，重新核验操作步骤；必要时降低产量，不用垃圾内容补量。
- **X 发布 / 排期失败**：状态保留为 `draft` / `scheduled`（依据实际情况）并人工重试；发布前先搜索现有帖子防重复。
- **连续三天无法稳定发布**：先减少选题范围和文案长度，暂停新增自动化。

另见 [X 发布后的运营与数据闭环](X-MEASURE-LEARN.md)：发布后按真实时间窗口将可得指标**追加**写入 [`x-metric-snapshots.csv`](../templates/x-metric-snapshots.csv)，不可覆盖历史数据或将账号净涨粉归因到单帖。原 `posts.csv` 仍是作品索引与实际 URL 的唯一执行记录。

## 每周复盘（周日）

填 [WEEKLY-REVIEW.md](../templates/WEEKLY-REVIEW.md)。记录发帖数、原创观点数、曝光、主页访问（可得时）、粉丝净增长、关注转化（若数据支持），观察哪个主题带来**相关受众**。互动率不是粉丝转化率；样本量小不做因果判断。每周仅调整一个因素（选题、Hook、配图形式或发布时间），避免归因混乱。

## X 合规

官方自动化规则：https://help.x.com/en/rules-and-policies/x-automation

- 自动发布有条件允许，但必须遵守反垃圾、授权与 API 规则；**不用模拟网页点击来自动化 X**。
- **禁止自动点赞**；不做自动追踪/取关或对陌生人的关键词批量回复、私信。
- 不冒充用户体验，不复制同质内容刷屏。以事实、原创试验和有用讨论获得真实关注。
- 可能可用的 X 官方排期说明：https://help.x.com/en/business-and-advertising/scheduled-tweets （该文档涉及 ads.x.com；普通用户界面可用情况需自行验证）。
