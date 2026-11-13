# 跨平台本地运营反馈闭环（V1）

> Status: 2026-11-13 — local-only pilot; no real cross-platform metrics imported or automatic publishing authorized.
> Strategy 管策略，ContentOps 管离线数据；原始数据只保存在你的电脑。

这个工具补充 X 专用 scripts/x_learning_loop.py，不替换已有 X 四张（含本地实验上下文）CSV；平台间不混算指标。X 账号的工时、原创频次和评判标准始终服从 Strategy 唯一 X SOP 与 ContentOps 对应账号 DNA。
服务其他自媒体平台：YouTube、抖音、TikTok、小红书、B站等的同平台增长实验。
不爬虫，不登录社媒，不自动发帖，不自动批准 Content Bundle。

## 第一次使用：Windows PowerShell

进入 X-SuperPlay-ContentOps 仓库根目录：

    git pull
    python scripts/platform_learning_loop.py init

本地创建两个 CSV（不会覆盖已有文件）：

    .local/platform-learning/content-index.csv
    .local/platform-learning/metric-snapshots.csv

也可放在 D 盘：

    python scripts/platform_learning_loop.py init --data-dir "D:\AI-Outputs\X-SuperPlay-ContentOps\analytics\platform-learning"

该目录由原有 .gitignore 忽略。不要用 git add -f 上传真实报表。

## 数据录入规则

content-index.csv：每条真实已发布作品一行：

- content_id：唯一内容编号
- platform：youtube / douyin / tiktok / xiaohongshu / bilibili / x
- account_alias：非敏感账号别名
- content_format：video / shorts / graphic / reply_text / article
- discovery_source：作者从哪里发现话题，例如 trending、search、recommendation、following、community、inspiration
- topic_cluster：主题簇，例如 ai_agent
- experiment_id：实验编号，与指标表一致
- post_url：实际 https 发布 URL
- published_at：带时区的时间，比如 2026-11-12T10:00:00+08:00
- publish_status：reported_published / verified_published（draft 被跳过）

metric-snapshots.csv 使用 Strategy/90-Templates/metric-snapshot.yaml 的原有指标名称，不是新指标标准。
至少填 content_id、experiment_id、platform、account_alias、content_format、post_url、
published_at、observed_at、window、metric_source、metric_definition_version、data_access、organic_paid；
再填该平台可获得的主要指标，如 views_or_reads 和 saves。

- window：T+24H（18–36小时）/ T+72H（60–84小时）/ T+7D（144–192小时）
- metric_source：native_manual / native_export / official_api
- metric_definition_version：自己确认的指标口径版本，必须同名同定义
- data_access：available / partial
- organic_paid：organic；付费或混合不参与本分析
- 指标看不到留空，不能填 0；不推算平台算法权重
- account_net_follower_change 是账号级数据，不能归因到一条内容

## 跑一次同平台来源对比

以 B站技术视频为例（使用已注册的账号 Profile）：

    python scripts/platform_learning_loop.py analyze --platform bilibili --account x-superplay-future-intelligence --format video --topic-cluster ai_agent --window T+24H --metric views_or_reads --interest saves --definition native_v1

只有平台、账号、格式、话题簇、时间窗和指标版本一致才比较。
两个来源组各有至少 5 条、且各自至少 5 条具有完整主指标与兴趣指标时，标 DESCRIPTIVE_ONLY；否则 INSUFFICIENT_DATA。
这仍然只是描述统计，不证明平台算法的因果推荐效果。

本地输出：

    .local/platform-learning/learning/latest.json
    .local/platform-learning/learning/latest.md
    .local/platform-learning/learning/history/PL-<report-id>.json

同一组同时展示单帖兴趣比率中位数（主）、汇总曝光加权比率（辅助），有真实有效信号与 Founder 工时时另算单位小时有效交流；没有信息留空，不补 0。分析结论为观察性相关，不是算法因果推荐。

特别注意：discovery_source 记录你在哪里发现选题，不是官方给你的实际流量来源。
真实流量来自搜索/推荐/关注等，需要平台专属官方报表另行核实。

## 将复盘结果送回内容生产

人工查看 Learning Brief、选定有实际来源的新主题后，可明确授权启动已有 Router：

    python scripts/platform_learning_loop.py route --account-profile x-superplay-future-intelligence --report-id PL-REPLACE --decision ADJUST --topic "Why AI agents fail at tool recovery" --reviewer Founder --evidence-url "https://example.org/public-primary-source" --confirm

程序读取本地 latest.json，通过现有 scripts/content_route.py start --account ... --mode topic --topic ...
生成待审核主题运行。仅当最新分析报告 ID 一致、报告具备可比较样本、Strategy 人工给出 CONTINUE 或 ADJUST，且账号 Profile.slug 与报表 account_alias 精确匹配且允许该平台，才允许路由。证据 URL 会作为 --url 传给内容 Router，审核人作为 --by 传入。回执写入本地 learning/handoff.json；无发布权限，不能绕过证据、QC、版权和人工批准。

必须使用 config/accounts 下已经登记且 platforms 列表包含目标平台的账号 Profile。YouTube 当前没有匹配的已注册 Profile 时只支持离线分析，不允许把 YouTube 结果路由到 X 账号。缺少相应账号或平台适配时，不表示该平台已能生产/发布。
本工具不会读取图像截图计算曝光，不能无证据推算 11 月 6 日至 12 日的跨渠道转化。

## 归属与方法

普适的增长假设：借势曝光、受众匹配、原创价值承接、持续复访、数据反馈。
平台执行入口不同：X 对话回复；TikTok/抖音短视频推荐及搜索；
小红书话题/搜索；YouTube/B站搜索、推荐和长内容。没有“热点必定获得推荐”的通用公式。

本地保存数据，ContentOps 保存代码，Strategy 审查并写下周实验策略，OPC-Blueprint 单独负责商业证据。
不新增 GitHub 仓库、不新建云数据库、不自动发布。

官方可核查资料：
- X 对话推荐：https://help.x.com/en/resources/recommender-systems/conversations-recommendations
- TikTok 推荐与评论：https://support.tiktok.com/en/using-tiktok/exploring-videos/how-tiktok-recommends-content
- YouTube 推荐：https://blog.youtube/inside-youtube/on-youtubes-recommendation-system/

验收：

    python tests/test_platform_learning_loop.py

只运行合成数据测试，不读取真实社媒账户。
