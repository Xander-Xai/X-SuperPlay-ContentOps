---
name: content-strategy
display_name: "内容策略与选题简报"
description: "把账号定位、用户问题、可搜索关键词和可分享角度整理成可审核的内容简报，不直接代替事实调研或发布。"
category: content-planning
version: 1.0.0
author: Matrix Ops
visibility: public
---

# 内容策略与选题简报

## 作用

开始前必须已有 `routing.yaml`，且其中按顺序记录了 `topic_route` 与 `account_route`；没有路由时先运行 `python scripts/route_content.py --interactive`，不能从默认账号或历史内容推断。

这个技能负责在 `topic_selected` 门禁之前回答三件事：

1. 读者正在解决什么问题；
2. 这篇内容为什么现在值得做；
3. 文章应该通过搜索获得入口，还是通过分享获得传播。

## 主题边界合同（所有主题通用）

每篇文章必须先填写并批准 `topic-contract.yaml`。它不是某个单一主题专属配置，而是
所有主题共用的防跑偏合同，至少锁定：

- `canonical_topic`：唯一主主题，以及 `anchor.required_terms` 锚点词；
- `scope.in_scope / out_of_scope`：明确写什么、不写什么；
- `series.subtopics`：后续子题、与主主题的关系、为什么属于主题、如何回链主主题；
- `drift_rules`：标题、导语和每个章节的主题回链覆盖率与无锚点章节上限；
- `approval`：人工确认人和时间。

正文在初稿、内容审稿和终审阶段都会重新执行
`python scripts/topic_integrity.py --article <文章目录> --content <正文>`。
如果正文只讲某个支撑概念，却没有回到 `canonical_topic`，门禁会阻断，不允许继续排版或提交草稿。

## 输出

- `content-brief.yaml`：账号、读者、关键词、传播角度、主张和 CTA；
- `topic-cluster.md`：系列主题、相邻选题和内容缺口；
- `content-calendar.md`：建议发布时间、复用渠道和复盘指标。
- `topic-integrity.json`：主题合同与正文回链检查回执。

## 账号规则

- AI哨兵优先写“新、真、能不能用”，必须有时效性和实测证据；
- X超玩•未来智能优先写“为什么、怎么做、怎样复用”，必须能沉淀为教程或资产；
- 不把热度当作事实，不把标题分数当作发布许可；
- 关键词、传播角度和商业 CTA 都必须进入人工审核记录。

## 门禁接口

生成简报后，执行：

```powershell
python scripts/topic_integrity.py --article <文章目录> --contract-only
python scripts/topic_integrity.py --article <文章目录> --content draft.md --write-report
python scripts/workflow_gate.py --article <文章目录> --stage topic_selected --advance
```

没有明确读者、核心判断或主要来源时，技能只返回缺口，不生成可发布文章。
