# X 本地运营数据回流｜使用说明

**数据只保存在你自己的电脑**。ContentOps 保存分析代码，Strategy 保存经过人工审核的策略结论。零 API、零云数据库、零自动发帖。

## Windows PowerShell（ContentOps 仓库根目录）

    python scripts/x_learning_loop.py init

会在已被 .gitignore 忽略的 .local/x-growth-en/ 创建仅有表头的三张本地 CSV；存在时不覆盖：

- posts.csv：使用现有 X posts.csv 的字段
- x-metric-snapshots.csv：使用现有 X 同龄指标字段
- x-account-snapshots.csv：使用现有 X 账号级指标字段

如需放到 D 盘，命令附加：

    --data-dir "D:\AI-Outputs\X-SuperPlay-ContentOps\analytics\x-growth-en"

不要把真实账号指标写入项目里受 Git 跟踪的 templates/，也不要强制提交 .local/。

## 录入方法

在本地 posts.csv 里，每个实际发出的回复一行：

- content_id：唯一内容 ID
- mode：reply，原创用 original
- status：published 或 reported_published（有真实已发布记录）
- account_handle：x-superplay-english（或者同一账号的确认别名）
- x_post_url：真实单条 X 回复 URL；不要填被回复的原帖 URL
- post_published_at：带时区的时间，如 2026-11-12T10:00:00+08:00
- experiment_variable：source:inspiration_ai、source:inspiration_broad、source:timeline_ai；原创为 source:original
- source_url：被回复的原帖 URL，可作为人工核对线索
- topic：真实话题

这里的 source 是**候选从哪里被发现**，并不是平台官方流量归因。

在本地 x-metric-snapshots.csv：

- content_id / x_post_url 必须与本地 posts.csv 匹配
- age_window：T+24H、T+72H 或 T+7D
- observed_at：带时区的观察时间
- metric_source：native_manual、native_export 或 official_api
- data_access：available 或 partial
- organic_paid：organic
- impressions、profile_clicks：后台真实数字；看不到时留空，不能填 0

T+24H 只接受发布后 18–36 小时，T+72H 为 60–84 小时，
T+7D 为 144–192 小时。单条同一窗口出现多个快照时跳过并报告原因。

在本地 x-account-snapshots.csv 可以录入账号级指标。账号级净增粉不会被归到任何单条回复。
你自己保存的七天截图只支持账号级基线，
不能用它凭空产生逐条回复指标；核对账号归属、时区和观察时间后才录入。

## 数据分析

    python scripts/x_learning_loop.py analyze --account x-superplay-english --window T+24H

本地生成：

    .local/x-growth-en/learning/latest.json
    .local/x-growth-en/learning/latest.md

内容包括各来源组的样本数、中位曝光、每千次曝光主页点击数、缺失/跳过原因。
至少两个回复来源组各有 5 条才标记 DESCRIPTIVE_ONLY；
否则 INSUFFICIENT_DATA。两种状态都不声称因果关系，不直接选择获胜方向。

## 人工审核后接入已有生产路由

人工阅读最新 Learning Brief，从真实材料选定有证据的新话题，然后运行：

    python scripts/x_learning_loop.py route --account x-superplay-english --topic "Why AI agents fail at real-world tool recovery" --reviewer Founder --confirm

此命令会检查本地 Learning Brief 的账号归属并调用已有
scripts/content_route.py start --account ... --mode topic --topic ...
创建**待审核选题运行**。不绕过事实/质量/权限门禁，不自动发布，也不改旧作品。

Strategy 仅登记脱敏结论、实验 ID、需要改的单一变量及人工决定；
绝不要把完整原始报表或私信传过去。

## 验收

    python -m unittest tests/test_x_learning_loop.py -v

脚本仅做本地数据处理；没有真实的官方指标来源校验，也没有跨平台推荐增益保证。

## 非 X 平台

本工具的 X 三表结构继续保留。抖音、TikTok、小红书、B站和 YouTube 的同平台实验请使用 [跨平台本地运营闭环](PLATFORM-LOCAL-LEARNING-LOOP.md)；无需新建 GitHub 仓库，不迁移已有 X 记录。

## 灵感 vs 时间线：先筛选候选，再人工回复

在现有 X 数据分析之前，新增 [本地候选筛选工具](X-DISCUSSION-CANDIDATES.md)：

    python scripts/x_discussion_candidates.py init
    python scripts/x_discussion_candidates.py rank --account x-superplay-english --language en

工具只筛选人工已查看的原帖，不自动抓取和发帖；选中后人工确认内容与来源，再把**自己真实发布的回复 URL** 录入本文件规定的 posts.csv、x-metric-snapshots.csv。实验策略权威在 X-SuperPlay-Strategy 的灵感 vs 时间线专项文件。
