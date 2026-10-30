# 渐进式升级路线（按痛点触发，不按日期堆功能）

> 对应项目及可验证采纳标准见 [WORKFLOW-ADOPTION-BACKLOG.md](WORKFLOW-ADOPTION-BACKLOG.md)。项目调研与代码资料见 [GITHUB-X-WORKFLOW-REVIEW-2026-10-25.md](GITHUB-X-WORKFLOW-REVIEW-2026-10-25.md)。后续按编号 XGW-001～011 更新，不以列入候选视为已经部署。

## 双源价值准入更新（2026-10-25）

V0 先采用 [X Signal SOP](X-SIGNAL-RESEARCH.md) 的高互动原帖发现（需要 URL、原作者、互动证据等级及观察时刻），再用 [GitHub Value Audit](GITHUB-VALUE-AUDIT-2026-10-25.md) 严格核验 AI 工作提效或变现交付机制。原 12 个 Skill 中 7 个当前不能直接自动入选，缺具体案例时必须维持 hold。所有 X 作品必须有真正匹配的 PNG/JPG 配图，不为热度或日更数量编造论据。X 搜索 API 候选 XGW-009～011 当前只采纳规则，不执行授权部署。

## V0 即刻执行的编辑标准（2026-10-25）

用户反馈前两篇观点不足够 impressive。无须引入新自动化系统，先将 V0 工作流改为 **证据 → 至少 3 个原创判断角度 → 因果机制与最强反例 → 六维质量审核 → 英文帖与对应配图**，详见 [EDITORIAL-QUALITY-GATE.md](EDITORIAL-QUALITY-GATE.md) 和 [旧稿对照](EDITORIAL-BEFORE-AFTER.md)。

**下次验收**：输出至少 3 个不同候选观点和一个有证据支撑的非泛泛判断；主观 30 分评分、红队反对意见、事实/推断边界、真实配图和字符核查。**不能**以评分替代实际用户互动与粉丝增长结果。

## V1.0 fourth pillar: reproducible Build & Learn (2026-10-25)

- Extend [CONTENT-PLAN](CONTENT-PLAN.md) to a **30% Skills / 30% AI improvements / 20% monetization / 20% tutorials** starting hypothesis, not an enforced daily quota.
- Add [Tutorial SOP](TUTORIAL-CONTENT-WORKFLOW.md) and [Tutorial-to-X prompt](../prompts/TUTORIAL-TO-X.md). One canonical reproducible GitHub runbook can feed X with **paired English copy+image**, and later Xiaohongshu/YouTube/Bilibili with adapted formats.
- **Immediate:** manually curate 12 candidate lessons; run one small scoped example, capture results and common errors. No auto scraping, hosting stack, or new external posting integration needed.
- **Next:** after four published tutorial packages, review demand, successful reproductions, maintenance burden and business relevance. Only then consider a Quarto/Docusaurus/Zensical online knowledge site. Avoid treating MkDocs Material as a permanent default given its announced 2027 EOL.
- **Release gate:** no "complete runnable tutorial" if only a source summary; no X publication if English text or actual PNG/JPG image is missing. Reader feedback/errata is part of tutorial lifecycle.

## V0.9 mandatory image delivery (2026-10-25)

**Every post MUST be delivered as one package: final English text + actual X-uploadable PNG/JPG matching that exact argument + English ALT + references and QA record.** See [POST-IMAGE-DELIVERY-GATE.md](POST-IMAGE-DELIVERY-GATE.md). All legacy `text-only` exemptions are revoked: if an image fails, publication is blocked, not downgraded to text-only.

## V0：可执行的半手动运营（NOW）

**功能**：每日双源选题 prompt、原始证据核验、按需真实配图/纯文字、人工发布/可用的原生排期、发布日志、一周一次复盘。

**验收**：可连续执行 14 天；至少 12 篇合格作品；没有未验证的新闻数字；每篇都有 source 和 published/draft 状态；至少一次周复盘。此阶段不是“自动发布”。

**下一步仅需**：使用 prompt 生成当天作品并发到 X，填 logs；别先建设复杂技术栈。

## V1：内容库标准化（ONLY WHEN V0 STABLE）

按主题整理 Skill 选题卡与常青备稿；编写复用 Hook、配图样式；对照来源清理低质量内容。Skill 内容池从 12 → 30 → 100 **经过检查的候选**，而不是一次性灌水。

**触发**：已稳定完成两周，发现研究/写稿重复劳动明显。**验收**：可提前准备 7 篇合格常青内容；减少漏发；复盘可找到有效主题。

## V2：排期/发布辅助（OPTIONAL）

先验证 X 账号支持的官方原生排期；仍有痛点时优先评估 **XGW-003 Postiz Agent**，需要 GitHub 原生 YAML 执行时才评估 **XGW-004 x-scheduled-posts**；不要同时部署两套。仅在有可视化跨平台管理需求时评估 **XGW-006 Postiz App**，编排层 **XGW-007 n8n** 留到 V3/V4。所有接入前必须先过采纳清单验收。首轮仅 **人工批准后的定时发布**，先跑沙箱 / 不重要测试帖子，再启用主账号。

**触发**：每周发布执行占用时间持续过高，或频繁因日程漏发。**验收**：核实权限/费用/规则；重复发布保护；失败告警；撤回机制；人工审批记录；连续 2 周无严重事故。

## V3：分析辅助

在数据可获取且合规前提下对比主题、格式、时间、点击/关注转化。原始指标可能来自不同口径；不要混算，没有统计显著性不声称“最优发布时间”。

**触发**：累计 >=30 篇，且部分帖子有可比较的可见数据。**验收**：以周为单位执行单变量小实验，形成可复用分析结论。

## V4：选择性自动化

自动采集 Releases / PR / 官方动态，去重评分、起草、生成配图、审核队列、排期、异常回滚；可参考 **XGW-005 Agent-X** 的审核/去重思想，不能视为已有完整系统。发布权限最小化，绝不自动刷评论/点赞/关注。

**触发**：V2/3 指标显示人工耗时是明显瓶颈，且质量、合规、账号安全可保障。**验收**：原始链接与事件时区可追溯；每次发布保留人工授权；可重放与撤销；定期审计成本/风险。

## 决策记录

| 日期 | Decision | Why | Next review |
|---|---|---|---|
| 2026-10-25 | 先做 V0；暂不部署 n8n/Postiz 或 X API | 目前缺乏运营基线，配置成本高于预期收益 | 14 天后 |
| 2026-10-25 | 100 Skills 作为选题池，不搞 100 篇堆量 | 目标是高质量目标受众，不是输出数量 | 第一轮周复盘 |
| 2026-10-25 | 最近 72 小时新闻与常青 Skill 分开标注 | 避免新旧事件混淆 | 每天审核 |
| 2026-10-25 | 建立 XGW-001～008 候选采纳清单 | 把已调研工具转为有触发条件、验收与回滚的决策，避免重复调研和盲目部署 | 达到 V0 验收门槛后 |
| 2026-10-25 | 升级原创观点 V1 编辑流程 | 前两篇事实核验尚可，但只是一般性建议，没有足够洞察增量 | 下一次产稿及每周复盘 |

如出现方向冲突，优先级：**证据真实 > 帖子质量 > 每日稳定 > 自动化程度 > 追逐数量**。
