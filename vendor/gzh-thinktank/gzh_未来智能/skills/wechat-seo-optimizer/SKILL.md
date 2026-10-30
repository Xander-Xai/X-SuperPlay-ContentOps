---
name: wechat-seo-optimizer
display_name: "微信搜一搜 SEO 算法优化与打分器"
display_name_en: "WeChat Search (SouYiSou) SEO Optimizer & Scorer"
description: "分析公众号文章的标题、Headings 结构、关键词密度、摘要描述与搜索排名潜力，提供 0-100 评分及优化建议。触发词：微信SEO、搜一搜优化、搜索排名提升、关键词密度、SEO打分。"
category: optimization
version: 1.0.0
author: WeChat Matrix Team
visibility: "public"
---

# 微信搜一搜 SEO 算法优化与打分器 (wechat-seo-optimizer)

近 40% 的公众号流量来自“微信搜一搜”。本 Skill 对文章的搜索引擎友好度进行确定性分析。

---

## 🛠️ 使用方法

```bash
python skills/wechat-seo-optimizer/scripts/optimize_seo.py article.md --keywords "AI Agent,公众号排版,自动化"
```

脚本会在文章目录生成 `seo-report.json`，包含综合分、标题分、关键词密度和修改建议。
`topic_selected` 门禁读取该回执；AI哨兵标题分低于 85 或综合分低于 70 时不能推进。
