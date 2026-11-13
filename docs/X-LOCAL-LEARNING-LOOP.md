# X 本地运营数据闭环｜唯一执行手册（2026-11-13）

**权威优先级**：X 官方与安全规范 → ContentOps 真实账号 DNA → Strategy 的
[唯一 X 增长 SOP V1.2](https://github.com/Xander-Xai/X-SuperPlay-Strategy/blob/main/01-Strategy/X-Original-Content-Rewards-Growth-V1.md)
→ [灵感/时间线专项](https://github.com/Xander-Xai/X-SuperPlay-Strategy/blob/main/03-Execution/X-Inspiration-vs-Timeline-Growth-Experiment-20261113.md)
→ 本工具的指标结果与人工批准。
本手册不创设额外回复配额、发布权限或评分标准。

**当前唯一 X 账号**使用旧兼容slug `x-superplay-english`，实际DNA是 `language:multi`（允许zh/en）、`MANUAL_ONLY`。**同一账号**每日目标：A25+B25+C50=100条合规人工回复；中文原创6+英文原创4=10条真实发布。逐条记录语言、原帖和自己帖子URL、实际工时。旧英文4条/日、28条/周和跨账号说法全部作废。
未登记为 X 平台的账号不能进入 X 路由。真人复核、发布、取数。

## 1. 初始化（Windows PowerShell，在 ContentOps 仓库根目录）

    git pull
    python scripts/x_learning_loop.py init
    python scripts/x_discussion_candidates.py init

在已忽略 Git 的本地 .local/x-growth-en/ 生成**四张指标/上下文表和一张可选候选表**：

- posts.csv：唯一 content_id，已发布的自己回复 URL；与项目模板相同
- x-metric-snapshots.csv：同龄 T+24H / T+72H / T+7D 官方可得指标；与项目模板相同
- x-account-snapshots.csv：账号层的粉丝和 Q 观察，不归因给回复
- x-experiment-context.csv：一条发布内容一行，记录对照必须的语言/主题/实验 ID/工时/有效交流
- discussion-candidates.csv：可选的**人工收集**原帖候选；评分后得到 candidates-ranked.csv

已有文件**永不覆盖**。要放在 D 盘可在上述脚本后分别添加
--data-dir "D:\ContentOps-private\x-growth-en"，注意所有 X 命令使用**同一路径**。
真实报表不要写入项目 templates/ 或 git add -f .local/。

## 2. 记录和字段判定

### 人工候选（可选，不必给每天所有回复都打七项分）

详见 [X-DISCUSSION-CANDIDATES.md](X-DISCUSSION-CANDIDATES.md)。
候选的 source_url 是**被回复的主帖**；来源只能是：
inspiration_broad (A，泛娱乐探索)、inspiration_ai (B)、timeline_ai (C)。
B/C 为同类 AI 主题的正式比较；A 不被当成 B/C 的严格对照。新目标 A25/B25/C50 不代表必须发送100条不合适或重复评论；草稿、人工实际发送、跳过原因必须分别保留，缺失指标不能写0。

### 已发布回复

posts.csv 每行：content_id、mode=reply、status=published 或 reported_published、
account_handle=x-superplay-english、x_post_url=**自己真正发布的回复链接**、
source_url=候选主帖、experiment_variable=source:inspiration_ai（或另外两组）、
post_published_at=2026-11-12T10:00:00+08:00。
没有自己的真实回复 URL 一律不能计入对照。原创的 source:original
用于观察原创承接，不与回复的 B/C 混算；普通曝光不能代替 Q。

x-experiment-context.csv 与 posts.csv 通过 content_id 和 x_post_url 精确关联：

- experiment_id：例 CEXP-20261113-001；**使用 Strategy 实验的真实编号**
- topic_cluster：如 ai_agent，与当前专项明确的同类主题保持一致
- language：en 或 zh，均属于同一个账号DNA；单次B/C实验严格同语言，不能把两语言混算
- founder_minutes：人工实测的分钟（非人工实测留空）
- qualified_conversations：已人工核验的有效往返对话数（非核验留空）
- content_id、x_post_url：与 posts.csv 完全一致

x-metric-snapshots.csv 用相同 content_id + x_post_url 保存
metric_definition_version=native_v1（以真实平台口径定义为准）、
age_window=T+24H 等、observed_at 真实时间、organic_paid=organic、
data_access=available 或 partial、metric_source=native_manual 等；
impressions、profile_clicks 看不到就留空。T+24H 接受 18–36h、
T+72H 接受 60–84h、T+7D 接受 144–192h；重复同窗快照需要人工消歧。

**强制区别**：discovery_source 只表示你如何发现这个话题，
不表示 X 官方认为你的回复曝光来自灵感/时间线渠道。
账号净增粉和 Creator Studio 合格首页曝光 Q 是账号级单独口径，
不能从逐帖普通曝光反推。

## 3. 先探索，再严格 B/C 比较

探索性查看，不会宣布哪组更好：

    python scripts/x_learning_loop.py analyze --account x-superplay-english --window T+24H

正式两组对照，**必须指定四个范围**：

    python scripts/x_learning_loop.py analyze --account x-superplay-english --window T+24H --compare --experiment-id CEXP-20261113-001 --topic-cluster ai_agent --language en --definition native_v1

工具只对同账号、实验 ID、语言、主题簇、同龄观察窗、原生指标定义、
organic 的**已发布回复**进行 B/C 描述性对照。
B/C 分别有至少 5 条完整曝光与单帖主页点击样本才返回 DESCRIPTIVE_ONLY；
不足时返回 INSUFFICIENT_DATA，未严格选择四个维度则为 EXPLORATORY_ONLY。
**5 条只是软件最低观察门槛，不是统计显著性证明。**

输出在本地：
- learning/latest.json 和 latest.md（最新分析）
- learning/history/XL-xxxx.json（按报告 ID 归档，避免覆盖历史）
- 每组同时显示**单帖主页点击/千次曝光的中位数（主要）**
  与**组内曝光加权合并比率（辅助）**。高曝光的单条帖子可能显著影响后者。
- 单位 Founder 小时的有效对话数仅在两项都真实填写时计算；
  留空永远不等于 0。
- 报告可描述哪组**观察上**较好，但不声称平台算法因果加成、不直接决定配额。

## 4. 人审后把建议送进已有 Content Router

人工确认最新 Learning Brief 的 report_id 和证据 URL，
由 Strategy 决定 CONTINUE 或 ADJUST、下一轮一个变量和新主题。
只有 DESCRIPTIVE_ONLY 的严格报告才能由数据回流路由创建新选题：
（把下面的报告 ID、证据 URL 和主题替换成真实值）

    python scripts/x_learning_loop.py route --account x-superplay-english --report-id XL-REPLACE --decision ADJUST --reviewer Founder --topic "Evidence-backed Agent recovery" --evidence-url "https://docs.example.org/primary-source" --confirm

路由验证报告 ID、账号 DNA、决策与 HTTPS 证据链接，
在本地 learning/handoffs/XL-xxxx-CONTINUE.json（或 ADJUST）记录人工决定与路由回执；同一报告/决策不会重复创建运行。
将证据 URL 传给现有 content_route.py 的 --url，
并生成待审内容 Brief。**不自动批准、生产或发布。**
报告不足或明确 PAUSE/INCONCLUSIVE 时，不允许以“数据驱动增长”名义新建任务；
普通人工主题生产可以继续走原有 Router 的独立流程。

## 5. 当前可验收、仍待现实验证

CI 使用合成 CSV 覆盖对照条件、来源 URL、缺失/异常/重复快照、
中位与加权结果差异、历史报告和审核路由。尚未接收你的本地真实
X Analytics，不能从 11 月 6–12 日总览截图伪造来源转化和实验因果结论。
真实指标的可用性、人工打分成本、实际原创建议仍需要你在自己电脑上验证。

    python tests/test_x_learning_loop.py
    python tests/test_x_discussion_candidates.py

跨平台复用另见 [PLATFORM-LOCAL-LEARNING-LOOP.md](PLATFORM-LOCAL-LEARNING-LOOP.md)。
