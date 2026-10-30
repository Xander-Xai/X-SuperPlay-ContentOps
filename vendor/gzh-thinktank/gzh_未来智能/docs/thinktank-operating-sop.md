# X超玩•未来智能（X超玩•未来智能）单账号运营 SOP

> 本手册只描述 `gzh-thinktank` 单账号工作流。它不恢复 AI哨兵运行时，也不读取任何外部工作流目录。作品工作区遵守 [`article-workspace-governance.md`](article-workspace-governance.md)，默认位于工作流外层 `production`，由 `GZH_ARTIFACT_ROOT` 指定。

账号定位：**X超玩•未来智能 = Build**。目标不是追逐所有 AI 热点，而是把经过需求信号验证的问题做成可运行、可部署、可复用的项目、教程、Workflow 和解决方案。内容必须问题驱动、工程具体、实测优先、克制诚实；禁止把 Demo 展示写成上线证明，也不做 AI 暴富、躺赚或收益保证。

内容支柱固定为：**AI 工程拆解**、**从需求到上线**、**AI 能力变现**。商业化表达遵循“能力 → 作品 → 用户 → 服务 → 产品”，以真实用户行为、项目试用、预约或付费信号为依据。

## 1. 业务阶段与技术门禁

| 业务阶段 | 关键输入 | 主要产物 | 技术门禁 |
|---|---|---|---|
| 选题与主题合同 | 用户选题或 `inbox/handoff/` 已批准卡片 | `routing.yaml`、`topic-contract.yaml`、`topic-cluster.md`、`content-brief.yaml` | `environment_ready`、`topic_selected` |
| 研究与复现 | 官方文档、源码、论文、版本和实验记录 | `research.md`、`sources.json`、`source-verification.json`、`source-review.json`、`evidence-plan.json`、`source-evidence.json`、`evidence-provenance.json` | `research_complete`、`research_reviewed` |
| 初稿与三层审核 | 主题回链、claim 台账、风险级别 | `draft.md`、`content-revision.json`、`review-report.md`、`review-checks.json`、`review-evidence.json`、`ai-disclosure.yaml` | `draft_complete`、`content_reviewed` |
| 微信排版 | 当前定稿、公式源、技术图可编辑源 | `article.html`、`format-report.json`、公式 PNG/manifest | `formatted` |
| 视觉与资产化 | 视觉合同、读者任务、来源授权、当前主题 | `visual-contract.json`、`visual-semantic-review.json`、`vision-review.json`、`asset-index.json` | `illustrated` |
| 移动端终审 | Chrome/Edge 390px、全页和滚动切片 | `final-review.md`、`preview-capture.json`、`preview-fullpage.png`、`preview-slices/` | `final_reviewed` |
| 草稿回读与复盘 | 外部 token probe、自动 media_id、真实导出指标 | `publish-preflight.json`、`publish-attempt.json`、`publish-receipt.json`、`metrics.json` | `draft_submitted` |

每次只推进一个阶段：

```powershell
python scripts/workflow_gate.py --article <外部active/THK-YYYYMMDD-NNN-slug> --stage <阶段> --advance
```

`GATE CHECKED` 不是 `GATE ADVANCED`。失败时回到第一个未通过阶段，不得手工修改 `matrix-state.json`。

## 2. CTA 与 handoff 输入

- 每篇文章必须有非空、唯一、主题绑定的 `primary_cta`、`reply_keyword` 和 `lead_magnet`。
- 新工作区会生成 `cta-contract.json`；修改主题或 CTA 后运行 `python scripts/cta_contract.py --article <文章目录> --write`，再运行 `--check`。
- `reply_keyword` 可以使用主题模板示例（例如 Transformer 主题的“架构”），但不能跨主题复用 QKV、公式或旧项目承诺。
- handoff 只作为人工复制进来的 `user_material` 输入。若路由引用 `handoff-card.md`，卡片必须符合 `handoff-contract-v1`，包括来源文章 SHA-256、至少 3 个升级信号、目标主题和人工确认。
- 优先记录需求信号：`怎么实现？`、`有源码吗？`、`能不能出完整教程？`、`能不能部署？`、`可以帮我做吗？`、`多少钱？`。信号只能作为选题和访谈线索，不能直接当作有效商机。

```powershell
python scripts/validate_handoff.py --card inbox/handoff/<handoff_id>/handoff-card.md
```

## 3. 研究、视觉和发布原则

- 软件/API/benchmark 主张必须绑定官方来源、版本范围、检索时间和 freshness。
- 每个正文采用的可信来源至少保留一个真实证据单元；证据审计只证明本地完整性，不冒充事实真伪或真人身份。
- 架构、流程、公式、代码和数据优先使用可编辑的确定性后端；生成模型只用于封面和概念插画。
- 技术图不能以历史主题素材或无关文字海报降级；关系图必须通过几何合同，图片必须有逐图视觉回执。
- 视频、音频、跨平台复用和回退发布器只能在 `final_reviewed` 后，通过 `media_guard`，并且以 opt-in 方式执行。
- 真实微信提交必须自动传递 `media_id` 并执行 `draft/get` 回读；IP 白名单或权限失败时保持阻断，不填人工回执。
- 每篇稿件应回答一个真实工程问题，并明确当前方案、复现步骤、验证结果、成本、限制、失败处理和下一步可复用资产。

## 4. 复盘与适配器

T+1/T+7 只接收带 `captured_at`、`source` 和原始 `source_sha256` 的真实 JSON/CSV 导出；没有真实导出时保持空对象。后置适配器统一记录版本、执行模式、输入文章 SHA-256、输出结果和失败原因。

当前可选适配器：

- `z5-wechat-sop`：外部审核；
- `wechat-publisher`：本地 CLI 回退；
- `content-repurposer`：终审后的派生内容；
- `wemp-operator`：真实发布后的指标/互动导入。

它们均不是公众号主稿的替代品，也不改变九阶段门禁顺序。
