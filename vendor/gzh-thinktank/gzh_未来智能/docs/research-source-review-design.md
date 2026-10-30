# 研究来源审查门禁设计

## 问题定义

`verify_sources.py` 只能证明 URL/快照被抓取并完成哈希指纹；`source_evidence.py` 只能证明证据单元、来源层级和 claim 映射完整。两者都不能回答：

> 这篇资料是否真的与当前选题相关？我们到底读到了什么？它能支撑哪一句话？哪些范围不能外推？

因此，来源“可访问”不再等于来源“可采用”。

## 外部方法调研

### NIST：有效性必须绑定预期用途

NIST AI RMF 的 Valid and Reliable 指南把 validation 定义为：用客观证据确认某个预期用途的要求已满足，并强调结果必须放在预期条件和范围内解释。

来源：[NIST AI RMF AIRC — Valid and Reliable](https://airc.nist.gov/airmf-resources/airmf/3-sec-characteristics/)

落地：来源审查必须记录 `support_scope`，不能只记录“这篇文章讲过这个主题”。

### Cochrane：结构化风险域 + 书面理由

Cochrane 的风险偏倚方法使用固定问题/域，并要求每个判断有书面 justification；它还区分 risk of bias、间接性、不精确性等不同限制，避免把“质量”压成一个没有解释的分数。

来源：[Cochrane Handbook Chapter 8 — Risk of Bias](https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-08)，[Chapter 14 — Certainty of Evidence](https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-14)

落地：来源审查记录 `limitations`、`review_rationale`，不设置一个虚假的总分代替理由。

### PRISMA：显式纳入/排除标准与筛选过程

PRISMA 2020 要求报告研究问题、eligibility criteria 和 selection process，并建议说明自动化工具如何参与筛选；被排除但看似相关的记录也应保留排除理由。

来源：[PRISMA 2020 Statement](https://www.prisma-statement.org/prisma-2020-statement)，[PRISMA 2020 selection-process guidance](https://www.bmj.com/content/bmj/372/bmj.n71.full.pdf)

落地：每个来源都必须有 `review_verdict`（included/conditional/excluded）、`topic_match`、`exclusion_reason` 或 `support_scope`。

## 本工作流采用的最小审查闭环

```text
来源抓取/哈希
  -> 摘要或短摘录提取 + 原文定位
  -> 与 canonical topic / scope / claim 对照
  -> 记录 direct / adjacent / background / none
  -> included / conditional / excluded
  -> 限制与不可外推范围
  -> 只有 included/conditional 才能进入 evidence-plan 和 claims
```

## 为什么不把 LLM 总结当作事实证明

摘要提取只是“我审查了哪一段”的回执，不是语义真值证明。新门禁只负责来源相关性、摘要/短摘录可追溯性、适用范围和采用决策；论文、benchmark、医疗、法律、金融及高风险主张继续由独立事实审查门禁处理。

## 契约文件

- `source-review.json`
- contract：`source-review-v1`
- 每个来源必填：`source_id`、`review_verdict`、`topic_match`、`extraction`、`extracted_summary`、`support_scope`、`claim_ids`、`limitations`、`review_rationale`
- `sources_digest` 绑定当前 `sources.json`
- `topic_fingerprint` 绑定当前 `evidence-plan.json` 的主题指纹
- `metadata` 只能用于排除/待定，不能作为正文采用依据

## 新门禁位置

`research_complete -> research_reviewed -> draft_complete`

原有 `research_complete` 继续负责抓取、哈希、证据和 claim provenance；新增 `research_reviewed` 专门负责“资料是否真的可用”。两者职责不重叠，也不允许用来源数量替代相关性审查。
