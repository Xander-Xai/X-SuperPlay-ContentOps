# X超玩•未来智能（X超玩•未来智能）公众号内容工作流（独立版）

> 本目录是 **X超玩•未来智能**（`account_id: thinktank`，对外品牌 **X超玩•未来智能**，发布槽位 1）的单账号独立工作流，
> 拆分自原 gzh 双账号矩阵。核心使命：**从真实问题出发，把 AI 做成能运行、能上线、能解决问题的项目**。

## 快速开始

```powershell
python scripts/validate_matrix.py          # 静态校验（身份/产物契约/registry）
python scripts/workspace_hygiene.py --check # clean-room 文件与 manifest 漂移检查
python scripts/bootstrap_article_environment.py   # 预设目录与公开种子
python scripts/route_content.py --interactive     # 选题路由（账号固定 thinktank，写入外部 registry/routes）
python scripts/matrix_init.py --route <外部artifact-root>/registry/routes/<路由>.yaml --title "你的深度选题"
python scripts/workspace_audit.py                  # 外部作品仓边界与编号审计
python scripts/topic_integrity.py --article <外部active/THK-...> --contract-only  # 主题边界合同
python scripts/cta_contract.py --article <外部active/THK-...> --check
```

初始化后，`matrix_init.py` 会输出一个外部 `active/THK-YYYYMMDD-NNN-slug/` 工作区；在该目录中依次填写：
`topic-contract.yaml` + `topic-cluster.md` + `content-brief.yaml` + `cta-contract.json` → `topic-card.md` + `seo-report.json` → `research.md` + `sources.json` + `source-verification.json` + `evidence-plan.json` + `source-evidence.json` + `evidence-provenance.json` + `evidence-lineage.json` →
`draft.md` + `content-revision.json` → `review-report.md` + `review-evidence.json` + `ai-disclosure.yaml` →
`article.md` → `article.html` + `format-report.json` → `visual-brief.yaml` + `image-plan.md` + `image-sources.json` →
`final-review.md` + `preview-capture.json` → `publish-preflight.json` → 草稿回读。

视觉阶段不可省略：先运行 `visual_qa.py plan`，再运行 `build_image_prompt_plan.py`；确定性关系图/代码图必须有可编辑 SVG/HTML 源，生成后依次运行 `visual_artifact_qa.py`、`visual_geometry_qa.py`、`visual_semantic_qa.py`、`check_orphan_assets.py` 和 `build_asset_index.py`。`visual_semantic_qa.py` 必须生成 vision-skill-v1 与逐图 `vision-review.json` 回执；没有实际 native 多模态/外部 vision/真人审阅证据不得推进。

移动端终审必须用真实 Chrome/Edge：生成 390px 首屏、full-page 与滚动切片截图，并通过 DOM、图片可见比例、横向溢出和 WCAG AA 对比度检查。研究来源还必须记录官方来源、版本、检索时间和 freshness 状态；混合证据层还要求每个正文采用的可信来源有短摘录、截图、代码或离线快照等真实证据单元，而且每个 claim 至少绑定一个带 `claim_ids` 的有效 evidence 单元，并在篇尾自动生成参考资料清单；CTA 必须是主题绑定且唯一的最后收尾 CTA。

每完成一个阶段都必须通过顺序门禁，不能跳步：

```powershell
python scripts/workflow_gate.py --article <外部active/THK-...> --stage environment_ready `
  --env D:/path/to/external.env --advance
python scripts/workflow_gate.py --article <外部active/THK-...> --stage topic_selected --advance
```

完整顺序为 10 道门禁：`environment_ready` → `topic_selected` → `research_complete` → `research_reviewed` → `draft_complete` → `content_reviewed` → `formatted` → `illustrated` → `final_reviewed` → `draft_submitted`。每一步都区分 `GATE CHECKED`（只检查）和 `GATE ADVANCED`（写入状态）；真实微信发布还必须通过 token probe、自动 media_id、`draft/get` 回读，禁止人工填写回执。

完整门禁顺序见 [`profiles/workflow-gates.yaml`](profiles/workflow-gates.yaml)。
主题合同会在 `topic_selected`、`draft_complete`、`content_reviewed` 和 `final_reviewed` 重复检查，
防止正文从主主题漂移成只讲某个支撑概念。

## X超玩•未来智能主流程

接收用户选题或真实需求信号（也可使用人工放入 `inbox/handoff/` 且通过 handoff-contract-v1 的已批准卡片）→ 深度调研 → 需求定义与可信信源分级 → 2500–5000 字项目型图文教程 →
三层审核 → 正文语义视觉合同 → SVG/HTML 技术图与 Agnes 概念增强 → LaTeX 公式 PNG → 微信 HTML 校验 →
语义视觉 QA → 项目/Workflow 资产沉淀 → 草稿回读 → 需求信号和转化复盘。

## 战略接入：Explore → Build

参考项目 [`X-SuperPlay-Strategy`](integrations/x-superplay-strategy.yaml) 已通过授权读取接入为文档型战略参考：
`X•超玩1024` 负责 Explore，`X超玩•未来智能`（`thinktank`）负责 Build。当前账号消费
[`x-superplay-strategy-contract.yaml`](integrations/x-superplay-strategy-contract.yaml) 中的内容支柱、需求信号和
30/60/90 天验证框架，把“怎么实现 / 有源码吗 / 能不能部署 / 多少钱”等信号升级为深度选题、用户访谈和 Demo/MVP 验证；该参考项目不进入渲染、发布或运行时依赖。

账号调性以问题驱动、工程具体、实测优先、克制诚实为准：先说明用户问题和当前解决方式，再讲技术；必须交代成本、限制、失败和人工介入；不做纯资讯搬运、未实测项目清单或收益保证。

## 身份合同（不可修改）

见 [`workflow-identity.yaml`](workflow-identity.yaml) —— 本工作流唯一账号 `thinktank`，主题 `thinktank-atlas`，发布槽位 1。

## 目录

```text
workflow-identity.yaml        # 单账号身份合同
profiles/thinktank.yaml       # X超玩•未来智能账号配置
profiles/visual-styles.yaml   # 视觉系统（X超玩•未来智能主题）
profiles/third-stage-expansion.yaml # 第三阶段本地扩容状态（策略/转化/资产）
scripts/topic_integrity.py       # 通用主题边界与防跑偏门禁
scripts/cta_contract.py          # 主题绑定 CTA 与回复关键词合同
scripts/validate_handoff.py      # 人工 handoff 卡片来源/信号/审批验证
scripts/audit_skill_inventory.py # 参数化、无密钥的 SKILL.md 能力盘点
scripts/source_evidence.py       # 可信信源、逐主张证据、授权、内容寻址回放和篇尾参考资料门禁
skills/ai-thinktank-workflow/ # X超玩•未来智能编排入口（内部兼容路由名）
skills/skill-registry.yaml    # 技能映射（X超玩•未来智能版）
scripts/                      # 门禁/路由/视觉/公式/发布脚本
.aws-article/                 # 本地预设与单槽位配置
<GZH_ARTIFACT_ROOT>/active/ # 制作中的 THK 编号作品工作区（默认位于工作流外层 production）
inbox/handoff/                # 已批准 handoff 卡片副本收件处
docs/thinktank-operating-sop.md # X超玩•未来智能单账号业务阶段与执行手册
opc-doc/                      # 转化闭环阶段的渠道、内容承接与成交路径资产
split-manifest.json           # 拆分来源/哈希清单
```

## 验证

```powershell
python scripts/validate_matrix.py
python scripts/test_adversarial_controls_v2.py # 对抗控制与边界回归测试（网络无关）
python scripts/test_workflow_hardening.py   # clean-room、视觉回执、CTA、长页与主题回归
python scripts/test_cta_contract.py
python scripts/test_handoff_contract.py
python scripts/test_post_publish_registry.py
python scripts/test_skill_inventory.py
```

发布需仓库外凭证（`--env`），不写入本目录；默认只生成草稿，不群发。

## 混合证据层的最小闭环

```powershell
python scripts/source_evidence.py init --article <外部active/THK-...>
python scripts/topic_evidence_isolation.py bind --article <外部active/THK-...>
python scripts/source_evidence.py capture --article <外部active/THK-...> --source-id <source_id>
python scripts/source_evidence.py audit --article <外部active/THK-...> # 同时生成 evidence-provenance.json
python scripts/source_evidence.py append --article <外部active/THK-...>
python scripts/source_evidence.py audit --article <外部active/THK-...> --require-appendix
```

默认策略是至少 3 个**实际用于正文**的可信来源、2 个一级/一手来源、2 个不同域名；隐藏的 `used_in_article=false` 来源不能为 claim 伪造覆盖。每个进入正文的来源至少有一个证据单元，每个 claim 至少有一个有效证据单元。审计会生成 `evidence-provenance.json`，把来源快照和证据文件的字节哈希组成 `pack_sha256`，并生成受 OpenLineage/in-toto 启发的离线 `evidence-lineage.json`（run/job/material/product；无签名、非身份认证），供重放与发现拼接回执；它不等同于真人签名或来源真伪证明。`append` 记录篇尾 Markdown/HTML 全文 SHA-256，`audit --require-appendix` 会复核这两个摘要，防止只保留标记却篡改引用块。截图或代码的复用必须填写 `license_status`、`reuse_approved` 和 `reuse_reason`，授权不明确时只保存到工作区，不自动发布。
换主题时，`topic-evidence-isolation.json` 会校验当前 `topic-contract.yaml` 指纹、来源是否命中主题锚点，以及 `evidence/` 是否残留未登记文件；因此 vLLM 不会自动套用 LangGraph 的来源和截图。
