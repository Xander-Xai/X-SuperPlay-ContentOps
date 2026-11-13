# X 灵感 vs 时间线：人工候选热帖筛选（本地 V1）

> Last reviewed: 2026-11-13. Local human-scored candidates only; no X network access, publication or real-result validation.

策略唯一权威：Strategy 仓 03-Execution/X-Inspiration-vs-Timeline-Growth-Experiment-20261113.md。
本文件只说明执行脚本，不另起一套配额或新阈值。当前 Strategy V1.2 设为每日人工回复目标**A25+B25+C50=100条**，原创**中文6条+英文4条**（题材不限技术）；唯一已注册X账号 `x-superplay-english` 同时负责中文6+英文4=10条原创发布及全部100条人工回复。每条声明 `language=zh|en`，不创建中文第二账号；旧4/day、28/week及低频目标均属历史。

## 初始化 / 排序（Windows PowerShell）

在 ContentOps 仓根目录：

    python scripts/x_discussion_candidates.py init

编辑被 Git 忽略的本地文件：

    .local/x-growth-en/discussion-candidates.csv

每个候选一行，全部为人工自己看到的公开 X 主帖，不抓取、不猜测。**日常轻量运营只需记录原帖来源与真实回复 URL；下面七维评分只在正式选帖实验中人工使用，并非每个日常回复的强制门槛。**

- source_url：公开主帖的 https://x.com/<handle>/status/<id>。
- account_handle：如 x-superplay-english；不是原作者的 handle。
- language：每条候选使用en或zh；同一个账号可分别按语言筛选和复盘，不是两个账号。
- discovery_source：仅 inspiration_broad、inspiration_ai、timeline_ai 三类。
- topic_cluster：真实主题簇，可用于之后实验配对。
- observed_at：有时区的真实观察时间，如 2026-11-13T11:00:00+08:00。
- source_access：确实人工看到原帖及上下文才填 operator_viewed。
- author_active：人工观察 yes / no / unknown；不可臆造。
- trend_signal：观察到有依据的热度趋势才按 0–5 主观评分；未知留空。
- source_impressions：公开可见主帖浏览数，仅供上下文记录，不参与排序分数。
- 七项人工 0–5 评分：topic_relevance 话题相关、audience_fit 受众吻合、
  incremental_value 新信息、evidence_quality 证据质量、discussion_potential 讨论空间、
  duplication_risk 重复风险、compliance_risk 规则风险。

输入示例（合成评分，非实际账号数据）：
AI 工具故障讨论可评 topic_relevance=5、audience_fit=5、incremental_value=4、
evidence_quality=4、discussion_potential=4、duplication_risk=1、compliance_risk=1。
评分只表达作者对当前候选的判断。

运行：

    python scripts/x_discussion_candidates.py rank --account x-superplay-english --language en
    python scripts/x_discussion_candidates.py rank --account x-superplay-english --language zh

本地输出：

    .local/x-growth-en/candidates-ranked.csv

REVIEW_CANDIDATE 只允许下一步人工看稿。SKIP 会附原因，包括
无来源链接、未亲自见过、缺评分、受众不匹配、重复或高风险。
评分公式以受众吻合与增量为主，热度最多加 1 分，作者活跃最多加 0.5 分；
没有算法权重解释，也不是自动评论、自动抓热搜。

仅筛选高分候选，不把排名当成必须发送配额。人工检查完整上下文后，
可用 skills/x-organic-growth-operator 讨论规划、skills/x-high-engagement-copywriter
写两种不同的自然回复方向。最终发布必须人工进行。没有合格候选就停止。

## 与真实运营数据闭环的衔接

候选池和已发布记录严格分开：

1. discussion-candidates.csv 保存原帖 URL，不等于你的回复。
2. 发布后在本地 posts.csv 用 source_url 记原帖、x_post_url 记你自己的真实回复 URL，
   experiment_variable 填 source:inspiration_ai / source:inspiration_broad / source:timeline_ai。
3. 在 x-metric-snapshots.csv 记录每条回复同龄后台指标，
   x-account-snapshots.csv 单列账号粉丝变化；严格 B/C 比较还需在 x-experiment-context.csv 记录 experiment_id/topic_cluster/language，真实工时和有效对话在可核验时填写。
4. 用以下命令做来源分组描述统计，输出本地 learning/latest.md：

    python scripts/x_learning_loop.py analyze --account x-superplay-english --window T+24H --compare --experiment-id CEXP-20261113-001 --topic-cluster ai_agent --language en --definition native_v1

5. Strategy 人工审核最新 Learning Brief 的 report_id，并选择 CONTINUE/ADJUST 后，经带 report-id/decision/evidence-url/reviewer/topic/confirm 的 x_learning_loop.py route 显式进入 Content Router 待审选题；未受控和无比较样本不能冒充增长决策。

原始数据和账号敏感信息留本地，请勿 git add -f .local/。

## 质量边界

- 本地真实 X 数据尚未提供给脚本，测试只用合成数据。
- 不从原帖浏览数推导自己的回复浏览或转化。
- 不把账号级增粉、原创首页合格曝光 Q 分摊给某条回复。
- 现行 X SOP 高强度100+10目标取代旧每日32条回复及50–65分钟预算。实际工时需人工记录，不因100条目标强行发送重复、无关或骚扰回复。
- B（灵感 AI）与 C（时间线 AI）应尽量配齐发布时间、语言、主题和热度；
  A（泛娱乐）仅作为探索性参考。
- 无自动抓取、自动发布、自动点赞、绕过风控或秘密/私信输入。
- 标准 Python 即可，不需要新数据库、API Key 或第三个 GitHub 仓库。

本地验收：

    python tests/test_x_discussion_candidates.py
    python tests/test_x_learning_loop.py
