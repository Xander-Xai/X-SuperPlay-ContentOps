---
name: ai-thinktank-workflow
display_name: "X超玩•未来智能 AI 项目实战与解决方案工作流"
display_name_en: "X超玩•未来智能 AI Project Build & Validation Workflow"
description: "X超玩•未来智能账号专用的 Build 型微信公众号项目实战工作流。围绕真实问题、AI 工程拆解、从需求到上线和 AI 能力变现，严格串联：需求信号 -> 深度调研 -> 项目型长文撰写 -> 事实/合规/错别字审稿 -> 微信 HTML 与 SVG/流程图排版 -> 可复用项目资产沉淀 -> 草稿箱回读。调性问题驱动、工程具体、实测优先、克制诚实，不做纯资讯搬运或收益保证。触发词：X超玩•未来智能工作流、X超玩•未来智能项目实战、写一篇 AI 项目教程、AI 项目部署SOP、AI 工程拆解。"
category: content-creation
version: 1.6.0
author: Matrix Ops
visibility: "public"
---

# X超玩•未来智能 AI 项目实战与解决方案工作流 SOP

> 本 Skill 的内部兼容路由名仍为 `ai-thinktank-workflow`，对外品牌统一为 **「X超玩•未来智能」**；定位是 Explore/Build 双账号体系中的 **Build：AI 项目实践者与教学者**。
> 核心使命：**从真实问题出发，把 AI 做成能运行、能上线、能解决问题的项目，并沉淀为可复用的工程能力与解决方案**。

---

## 📋 适用场景

- 📘 **AI 工程拆解**：从真实工程问题进入模型架构、RAG、LangGraph、Agent、评测和上线边界。
- 🛠️ **从需求到上线**：覆盖需求、PRD、架构、Coding、Evaluation、Testing、Deployment、Monitoring、Cost 与 Iteration。
- 💼 **AI 能力变现**：把能力沉淀为作品、项目包、Code Review、Workflow、企业实施和产品化验证，不承诺躺赚。
- 🎯 **需求信号承接**：优先处理“怎么实现 / 有源码吗 / 能不能部署 / 多少钱”等真实问题，不把点赞或自动回复冒充商机。

## ⛔ 开始前路由确认（账号固定）

作品不得写入仓库根目录。先由 `scripts/matrix_init.py` 分配外部工作区
`<GZH_ARTIFACT_ROOT>/active/THK-YYYYMMDD-NNN-slug/`（默认位于工作流外层
`production`）；路由登记位于外部 `registry/routes/`。
过程脚本、调试输出和一次性转换器只能放在本篇 `work/`，交付副本放 `exports/`，恢复快照放
`snapshots/`。仓库 `drafts/` 是废弃入口，禁止手工创建、复用或向其中写入文件。完整边界、生命周期和归档规则见
`docs/article-workspace-governance.md`。

任何内容生产开始前必须运行 `python scripts/route_content.py --interactive`：先询问选题走热点筛选 Skill 还是用户提供材料；本工作流账号固定为 X超玩•未来智能（thinktank），无需账号二选一。初始化工作区必须把 `routing.yaml` 传给 `matrix_init.py --route`；`content_medium` 固定为 `wechat_article`。随后必须批准通用的 `topic-contract.yaml`：锁定 canonical topic、in/out scope、锚点词、系列子题和偏题阈值；`topic_selected` 前未批准不得写稿。初稿、内容审稿和终审会用 `scripts/topic_integrity.py` 检查每个章节是否回链主主题，防止把支撑概念写成主线。初稿完成后还必须运行 `scripts/record_revision.py`，明确 `new` 或 `reused`；复用稿必须记录来源规范化 SHA-256（`hash_mode: canonical-text`）、改动说明和批准。`content-brief.yaml` 必须声明风险级别，高风险内容必须真人终审。演示视频只能在主稿 `final_reviewed` 后通过 `scripts/media_guard.py` 派生，不能绕过公众号正文门禁。

选题路由还必须记录其来源是需求信号、用户材料还是热点实验；优先承接“怎么实现 / 有源码吗 / 能不能部署 / 多少钱”等 Build 信号。每篇稿件都要回到真实问题、当前方案、验证结果、成本限制和可复用资产，不能把泛热点或自动回复当成商机。

---

## 🧰 调度的底层 Skill 矩阵

| 阶段 | 步骤 | 调用的 Skill | 职责说明 |
|---|---|---|---|
| ① 深度调研 | S01 | `deep-research`, `arxiv-search`, `read-arxiv-paper`, `source-evidence-layer` | 针对技术架构/开源项目进行全网深挖与 ArXiv 论文阅读，并建立可信信源与原始证据账本 |
| ② 项目型长文 | S02 | `content-production`, `khazix-writer`, `gzh-article-writing`, `record_revision.py` | 基于真实问题、Brief/源码输出 2500-5000 字项目教程，并登记新稿/复用稿与内容哈希 |
| ③ 校对与审核 | S03 | `content-humanizer`, `midu-proofread`, `gzh-editorial-review`（主） | 事实、错别字、AI 味和 3 层合规审核；Z5 作为可选增强 |
| ④ 架构与交互 | S04 | `beautiful-mermaid`（可选）、`excalidraw-diagram`（可选）、`wechat-svg-interactive`（可选） | 绘制系统架构图、流程图；交互只做增强，答案必须有静态降级 |
| ⑤ 精细排版 | S05 | `gzh-design-skill`, `gzh-article-format` | 主题转换后补齐 `span leaf`，运行 HTML 校验（0 Error、0 Warning）并生成手机预览 |
| ⑥ 配图与资产 | S06 | `gzh-visual-director`, `gzh-visual-assets`, `agnes-image-21-flash`, `beautiful-mermaid`, `excalidraw-style`, `excalidraw-diagram`, `art-direction-v1`, `visual-taste-review-v1`, `visual_contract_audit.py`, `gzh-article-assets`, `visual_qa.py` | 先做证据优先的视觉导演与 Art Direction 旁路计划；Agnes 负责封面/概念插画，架构/代码优先可编辑 SVG/Mermaid/Excalidraw-style；所有素材留来源/授权/提示词/请求指纹/哈希，路线与 claim receipt 必须一致 |
| ⑦ 发布与复盘 | S07 | `gzh-draft-publisher`（主） | 回读草稿箱；`wemp-operator` 作为可选数据/互动适配器，音视频为可选附件 |

---

## 🔄 6 步标准化作业流程 (SOP)

### 步骤 1：全网深度调研 (Deep Research & Mining)
- **选题边界先行**：先填写并批准 `topic-contract.yaml` 和 `topic-cluster.md`，再开始调研；所有后续子题必须写明与主主题的关系、证据边界和回链句式。
- 调用 `deep-research` 或 `arxiv-search` 收集官方文档、源码解析、论文与架构设计。
- 梳理出“环境准备 -> 核心原理 -> 代码实现 -> 踩坑记录 -> 商业拓展”的逻辑大纲。
- 首次运行先执行 `python scripts/check_runtime_dependencies.py --require-chrome`；缺少 PyYAML、Pillow 或浏览器时先按 `requirements-workflow.txt` 修复，不能让长流程在中途以 traceback 失败。
- 为每个事实、版本和实验结论登记 `sources.json` 的 `claims`，外部事实必须有可访问来源；本地复现必须记录路径、环境和哈希。文本证据使用 `hash_mode: canonical-text`，避免跨平台换行符造成误阻断。
- 运行 `python scripts/source_evidence.py init --article <文章目录>` 创建混合证据计划；按“第一方官方文档/官方仓库 → 标准/论文 → 维护者资料 → 二手资料”的层级分类，不能把搜索摘要当作信源。
- 主题合同批准后运行 `python scripts/topic_evidence_isolation.py bind --article <文章目录>`；证据计划会绑定当前主题指纹、锚点词和标题。换题必须重新绑定，不能复制上一主题的 evidence 目录。
- 每个 `used_in_article: true` 的可信来源至少保留一个真实证据单元（短原文摘录、截图、框架图、代码片段或离线快照），写入 `evidence-plan.json`，包含 `source_locator`、`claim_ids`、`captured_at`、`license_status`、`reuse_approved` 和 SHA-256；截图只作为原始证据，不能替代 claim 验证。
- `sources.json` 的每个 `evidence_locator` 必须同时包含 `source_id`、`kind` 和可复现的 `ref`（URL 锚点、快照路径或代码行范围）；缺少 `ref` 会在 `research_complete` 直接阻断。
- `research_reviewed` 是 `research_complete` 之后的强制来源审查门禁。每个 `sources.json` 来源必须在 `source-review.json` 中有摘要/短摘录、原文定位、`direct/adjacent/background/none` 主题匹配、`included/conditional/excluded` 决策、支持范围、局限、claim 映射和审查理由；未审、metadata-only 或 excluded 来源不得进入 `evidence-plan`/claims。
- 运行 `python scripts/source_evidence.py audit --article <文章目录>`；通过后再进入写作。定稿完成后运行 `python scripts/source_evidence.py append --article <文章目录>`，自动把“原始证据摘录 + 可信信源清单”写入篇尾，并再次以 `--require-appendix` 审计。
- 审计会写入 `topic-evidence-isolation.json`、`evidence-provenance.json` 与受 OpenLineage/in-toto 启发的离线 `evidence-lineage.json`；只要来源不命中当前主题、计划指纹过期、某个 claim 没有来自 `used_in_article=true` 来源的 evidence、证据包哈希漂移，或 `evidence/` 有未登记旧文件，就阻断 `research_complete`。provenance/lineage 都是本地完整性与血缘回执，不冒充真人签名或来源真伪证明；篇尾 append 后还要用 `audit --require-appendix` 校验 Markdown/HTML 全文摘要。
- 可信信源不是越多越好：默认至少 3 个可信来源、2 个一级/一手来源、2 个不同域名；若主题只能找到单一第一方来源，必须在 `research.md` 明确限制，而不是用低质量来源凑数。

### 步骤 2：3000+ 字长文撰写 (In-depth Writing)
- 调用 `khazix-writer` 撰写 3000–5000 字长文。
- 确保包含：架构逻辑图解、带注释的核心代码块、环境配置命令与详细步骤。

### 步骤 3：双重严谨校对 (Proofreading & Compliance)
- 调用 `midu-proofread` 生成勘误表，修正专业词汇、标点与事实错误。
- 调用 `gzh-editorial-review` 完成敏感词与合规性核查。
- 运行 `python scripts/content_truth_qa.py --article <文章目录>` 检查步骤数漂移、安装命令与 import 不一致、无来源硬阈值和绝对化承诺；回执未通过不得进入 `content_reviewed`。

### 步骤 4：架构绘图与公众号图文排版 (Diagram, SVG & Advanced Design)
- 调用 `beautiful-mermaid` 或 `excalidraw-diagram` 绘制清晰的系统架构/数据流程图。
- 调用 `wechat-svg-interactive` 时，按钮只作为增强；答案、步骤和风险必须在静态 HTML 中可见，不能只依赖 `<set>` 或客户端动画。
- 调用 `gzh-design-skill` / `gzh-article-format` 选主题排版；格式化后强制补齐 `span leaf`，运行 `validate_gzh_html.py`，ERROR 和 WARNING 都清零，再生成带复制按钮的手机预览页。

### 步骤 5：配图、资产化与商业引导 (Illustration, Assetization & Conversion)

配图先经过 scripts/visual_semantic_router.py 的内容语义路由：清单走 HTML 信息图，
KV Cache 走 SVG/白板时序，Multi-Head 走 Mermaid 分支图，Shape/公式走 KaTeX，
概念隐喻可走 Excalidraw/Agnes；每条记录必须留下 visual-routing.json 的规则、原因、
次后端和版式原型，禁止按章节机械套同一张卡片。导演计划阶段还要遍历
`profiles/visual-capability-registry.yaml` 的全部候选能力，写出 `skill-evaluation.json`；
集成能力可进入 primary/secondary 执行，未集成能力只保留 advisory 评估和明确 fallback。
- 在执行 renderer 之前运行 `python scripts/build_art_direction.py --article <文章目录>`，生成 `art-direction.yaml`。该旁路合同必须记录 `visual_thesis`、读者任务、palette、材质语言、layout families、anti-patterns、data_egress、fallback 和 `source_visual_brief_sha256`；它是规划层，不替代 `visual-contract.json`。
- `visual-routing.json` 是路由唯一事实源；`visual-brief.yaml`、`visual-contract.json` 和 `image-sources.json` 只能引用相同的 `route_rule`、`claim_ids`、requested/execution backend。`scripts/visual_contract_audit.py` 发现 route、claim 或实际尺寸 drift 时，`illustrated` 必须阻断。
- 运行 `python scripts/visual_taste_review.py --article <文章目录>` 生成 `visual-taste-review.json`。初期是 warning-first：检查 layout/backend/cognitive-role 多样性、390px 尺寸、素材 hash 与 Art Direction source hash；它不能替代多模态或真人审美复核。`profiles/visual-taste-policy.yaml` 校准通过后才能把 taste 评分升级为阻断门。
- 运行 `python scripts/visual_content_qa.py --article <文章目录>` 做可见语义审查：architecture/flow/relationship 必须有真实节点和箭头，comparison 必须有两组或表格，code 必须有代码结构，checklist 必须有可勾选结构；geometry metadata 不能代替画面拓扑。该回执是 illustrated 的硬门禁。
- 调用 `gzh-visual-director` + `gzh-visual-assets` 按“读者任务 → 证据优先 → Art Direction → 架构/流程图/概念插画”确定配图方案；先生成 `visual-brief.yaml`、`art-direction.yaml`、`image-plan.md` 和 `visual-director-plan.json/.md`。正文图数量按 `max(min_body_visuals, round(汉字数 / words_per_visual))` 再夹到账号/全局上限，不把 4～8 误写成所有文章的硬下限。
- 调用 `scripts/build_image_prompt_plan.py --provider agnes` 把每张图写成可审的高信息密度提示词：主体、环境、风格、光线、构图、读者任务、claim、fallback 和移动端安全区齐全。
- Agnes 只优先用于封面、概念场景和抽象机制插画；架构、流程、代码、数据和真实产品界面优先使用 `beautiful-mermaid`、`excalidraw-diagram`、SVG/HTML 或用户授权截图，避免模型在图片中生成错误文字。
- 通过视觉简报后，才运行 `scripts/generate_article_images.py --provider agnes --execute`；生成结果必须写入 `image-generation-plan.json` 与 `image-sources.json`，再运行 `visual_qa.py check`。
- 运行时默认按当前文章的 `topic_domain` 与视觉合同路由；只有显式声明 Transformer 领域时才启用 Q/K/V、Shape、Attention 等专用渲染器。新主题默认使用通用 Mermaid/SVG/HTML/Excalidraw 语义后端，清单走当前主题信息图，封面和概念插画才调用 Agnes。技术图的本地后端失败时必须阻断，禁止回退到历史主题图或无关文字海报。
- 视觉后端不是“登记即可”：`workflow_gate.py --stage illustrated --advance` 会重新执行 `visual_semantic_qa.py`。每个正文图必须证明 requested backend 已落到 editable source、实际 backend 已写入 provenance、输出路径被 `article.html` 引用；同一篇包含关系/时序/清单任务时，实际后端数量必须至少为 2。
- 视觉后端必须通过 `visual-contract-audit-v1`：评估层的 primary、requested backend 和 execution backend 必须可解释；registry 中的 skill path、adapter、版本和许可证必须真实存在。`excalidraw-style` 是当前可执行 SVG 后端，原生 `.excalidraw.json` 仍是 advisory，不能混写。
- 关系/流程/架构图还必须通过 `geometry-contract-v1`：连线端点、节点边界、交叉、穿越和箭头方向由 `scripts/visual_geometry_qa.py` 计算验证；正文画布背景由 `background-contract-v1` 锁定，卡片 surface 可分层，封面单独处理。
- 模型路由固定为：文本大模型负责调研、写作、合同和图规格；图片理解多模态大模型或真人负责最终像素/构图/移动端审查；技术图由确定性 SVG/HTML/Mermaid/KaTeX 生成，不能让文本模型或生图模型代替几何事实。
- 正文图不得带左下角账号署名或“语义绑定视觉”内部标识；品牌只出现在文章署名、CTA 或关注组件。数学图和技术图不得退化为通用四节点卡片；后端适配失败必须阻断 illustrated。
- 公式统一走 `canonical LaTeX → KaTeX HTML/SVG → Chrome 2× PNG`，采用透明背景、纯白前景、深蓝细描边和 `Times New Roman`；行内公式以 manifest 的 CSS 宽度和负基线对齐，避免比正文高一截。HTML、代码块、Mermaid/SVG、公式资产的英文字符统一遵循 Times New Roman，中文回退 CJK 字体。
- 公式门禁会扫描反引号中的数学表达；`B×n_q×d_v`、`W_O`、`d_model`、`O(t·d)`、矩阵 Shape 等必须写成 `$...$` LaTeX，只有 `dim=-1` 等真正代码允许保留。公式数量、源/HTML/SVG/PNG 哈希、2× DPR、CSS 尺寸和 HTML 引用任一不一致，`formatted` 直接失败。
- 多后端不再只要求“至少两种”：数学任务必须实际出现 `katex-html-composite`，Multi-Head 必须实际出现 `beautiful-mermaid`，KV Cache 必须实际出现 `deterministic-svg`，清单必须实际出现 `deterministic-infographic`；语义 QA 缺少任一对应后端时阻断 `illustrated`。
- 封面候选需人工确认，再运行 `python scripts/visual_qa.py approve ...` 和 `python scripts/visual_qa.py check ...`。
- 外部生图不可用时，仅封面允许使用当前品牌主题的确定性封面生成器；正文技术图必须使用语义正确的 SVG/HTML/Mermaid/Excalidraw 本地后端，后端失败就阻断，禁止使用历史主题素材或 `text_poster.py` 充当正文图。
- 新 renderer 的 POC 必须输出真实 PNG/JPG/WebP，经过 Chrome/CJK 字体、微信 HTML、390px、文件大小与草稿回读；技术图遇到字体、Chrome、SVG sanitize、上传或回读失败必须阻断。外部 provider 还必须记录 `data_egress`，禁止把标题/章节摘要未经批准外发。
- 调用 `gzh-article-assets` 将本教程的 SOP、配置参数沉淀为素材包。
- 调用 `obsidian` 将稿件同步归档入本地知识库网络。
- 调用 `opc-conversion-loop` 在文末配置与项目结论相关的承接区块（如“获取可复现清单 / 项目包 / 部署支持 / Code Review”）；不使用泛化诱饵或收益承诺。
- 需要公众号关注卡片时，显式调用 `python scripts/render_footer_card.py --output <文章目录>/work/follow-card.png --snippet-output <文章目录>/work/follow-card.html`；这是可选 CTA 资产，不会被视觉阶段自动生成，加入 HTML 后必须重新通过 `formatted` 门禁。
- 每篇新稿必须有 `public_brand`、`primary_cta`、`lead_magnet` 和 `reply_keyword`；正文至少出现一次品牌署名和可执行的关注/留言引导，技术解释必须回到真实问题、验证结果和可复用资产。
- 内容简报还要记录 `commercial_offer`；`metrics.json` 预留需求信号、用户访谈、项目试用、预约、付费和有效线索字段。
- 若用户明确要求朗读或演示，再调用 `wechat-tts-audio` 或视频适配器；这些附件必须在图文终审之后生成，失败时只记录降级，不阻断公众号图文草稿。
- 完成 AI 文字/图片标识和元数据保留确认后，写入 `ai-disclosure.yaml`；未通过不得进入排版。

### 步骤 6：草稿箱同步与后期互动 (Publishing & Analytics)
- 调用 `gzh-draft-publisher` 上传微信图床并发布至草稿箱。
- 文章发布后，调用 `wemp-operator` 跟踪数据复盘与读者评论互动。

---

## 🎯 质量标准

### 视觉解释深度（v1）

原理、架构、流程、状态、checkpoint、API 边界和后端选型图，不能只提交 expected_elements 标签清单。每个正文视觉单元还必须声明 reader_question、answer_sentence、entities、typed relations、claim/evidence/source_locator、must_explain 以及 machine-readable fallback。现在所有正文技术图都强制运行 `scripts/visual_depth_qa.py check` 生成 visual-depth-review.json；该回执只证明结构合同通过，reader_test_status=pending-human 时仍需真人或多模态读者测试，不能冒充审美/读者批准。

### 视觉美学卫生（v1）

技术图在语义和几何通过后，必须继续运行 `scripts/visual_aesthetic_qa.py`。该检查器验证箭头朝向、路由终点箭头唯一性、标签/节点/连线碰撞、safe frame 和底部裁切；`visual-aesthetic-review.json` 是 illustrated/final_reviewed 的阻断证据。

读者理解层使用 `scripts/visual_reader_test.py` 生成 `visual-reader-test.json`。该文件只在提供真实回答和 reviewer_id 后才能变成 passed；默认 pending-human 不是审美或读者验收。
- 文章字数 ≥ 2500 字，逻辑严密，可操作性强；公众号图文是唯一必交付主产物。
- 必须包含至少 1 张架构/流程图；SVG 交互必须有静态降级，不把关键信息藏在动画里。
- 需要 4～8 张有明确认知作用的正文图，另有 1 张封面；所有图片是真实 PNG/JPG/WebP，不能残留 `placeholder` 图片源。
- 必须通过 `gzh-editorial-review`；若 `midu-proofread` 缺少 Key，要记录降级原因，不得假装调用成功。初稿和定稿必须分别绑定 `content-revision.json` 的 `draft_digest` / `final_digest`。
- `content-brief.yaml` 必须记录 `risk_level` 和 `human_review_required`；high/critical 内容必须由 `reviewer_type: human` 的真人终审，不能由 Agent 自审冒充。
- 必须通过 `gzh-design-skill` 0 ERROR、0 WARNING 校验，并完成手机尺寸预览抽检。
- 必须通过 `scripts/visual_qa.py check`；视觉简报、封面确认、图片尺寸、重复度、替代文本以及每个素材的 `origin/source/license/sha256` 均要有记录；复用图还要有 `reuse_approved/source_ref/reuse_reason`。每个有图章节的 Markdown 图片锚点必须与 `visual-brief.yaml`/`visual-contract.json` 的 `asset` 完全一致，禁止章节之间交叉引用图片。
- 必须留下 `art-direction.yaml`、`visual-taste-review.json` 和 `visual-contract-audit.json`；`visual-taste-review` 初期为 warning-first，不能把“字段存在”冒充“高级感已通过”。
- 必须通过 `gzh-visual-director` 的导演合同；`visual-director-plan.json` 和 `image-generation-plan.json` 要绑定读者任务、视觉负责人、生成模式、连续性、安全区、fallback、请求指纹和可编辑 SVG 来源。
- 使用 Agnes 或其它外部模型时，生成素材还必须记录 provider、model、method、prompt_file、prompt_sha256、visual_owner、viewer_job、claim_ids 和 fallback；未执行 API 时不得把计划写成 `generated`。
- `render_mobile_preview.py` 必须生成真实浏览器截图和 DOM 运行时检查；如传入已登录公众号编辑器 URL，只记录脱敏地址，不读取登录凭证。
- 草稿提交后必须回读标题、作者、摘要、正文、图片数量和字面量 `\\uXXXX`，再写 `publish-receipt.json`。
- 必须同时留下 `content-brief.yaml`、`sources.json`、`source-verification.json`、`source-review.json`、`evidence-plan.json`、`source-evidence.json`、`evidence-provenance.json`、`evidence-lineage.json`、`topic-evidence-isolation.json`、`content-revision.json`、`review-evidence.json`、`format-report.json`、`image-sources.json` 和 `final-review.md`。
- `review-evidence.json`、`format-report.json`、`image-sources.json`、`final-review.md` 和 `publish-receipt.json` 必须绑定当前文件 SHA-256；微信草稿提交前还必须有 `publish-preflight.json`。

## 🔒 强制顺序门禁（不可跳步）

本 Skill 的业务步骤由 10 个可审计门禁放行：
`environment_ready` → `topic_selected` → `research_complete` → `research_reviewed` → `draft_complete` →
`content_reviewed` → `formatted` → `illustrated` → `final_reviewed` → `draft_submitted`。
每个阶段通过后才允许推进到下一个阶段：

```powershell
python scripts/workflow_gate.py --article <文章目录> --stage <当前门禁> --advance
```

`--advance` 会同时复核当前阶段之前的全部输入，失败则不写状态。不得手工把状态改成
`formatted`、`final_reviewed` 或 `draft_submitted`，不得绕过门禁直接调用发布器；蜜度
缺 Key 时必须把降级原因留在 `review-report.md`，不能以“已校对”代替证据。

## 🧾 矩阵执行契约

本流程使用仓库根目录的 `profiles/shared.yaml` 与 `profiles/thinktank.yaml`。
输入必须来自已确认的哨兵 handoff 卡片，或用户明确指定的独立深度选题。

### 必须落盘的产物

1. `content-brief.yaml`、`seo-report.json`：问题、读者、关键词、传播角度、CTA 和搜一搜诊断。
2. `topic-card.md`：问题定义、适用人群、与哨兵内容的关联。
3. `research.md`：官方文档、源码、论文、版本号和证据等级。
4. `draft.md`：含环境、原理、代码、踩坑和边界的初稿。
5. `review-report.md`：校对、事实核验、三层合规和 AI 味诊断。
6. `review-evidence.json`：内容、事实、敏感词、错别字和去 AI 味的结构化通过回执。
7. `article.md`：审核通过后的定稿，才允许进入排版。
8. `article.html`、`format-report.json`：微信兼容 HTML 和严格校验回执。
9. `article_预览.html`、`final-review.md`：390px 手机预览和人工终审记录。
10. `visual-brief.yaml`、`image-plan.md`、`img_analysis.md`、`image-sources.json`：视觉决策、图片质量、来源授权和复用回执。
11. `content-revision.json`：新稿/复用稿、来源哈希、改动说明和最终稿哈希。
12. `imgs/cover.*` 与 `imgs/section-*.{png,jpg,webp}`：真实配图。
13. `knowledge-note.md`：可复用的 SOP、模板、参数和后续选题。
14. `publish-receipt.json`：草稿箱结果与使用的账号槽位。

### 阻断规则

- 没有官方来源、可复现实验或明确限制说明时，不进入排版和发布。
- 没有可信信源证据单元或篇尾参考资料区块时，不进入排版和发布；`source_evidence.py` 的哈希、授权和篇尾回执必须与当前文件一致。
- 三层审核出现阻断级问题时，退回写作，不用“去 AI 味”掩盖事实问题。
- `wemp-operator` 只负责发布后的数据和互动；未安装时只能输出手工复盘模板。
- 项目承接区块必须与文章结论和真实需求信号相关，且允许用户在发布前删除或替换；不得写成 AI 暴富、躺赚或收益保证。
- 环境凭证可以由用户放在仓库外；发布脚本支持 `WECHAT_ENV_PATH` 指向该文件，不复制或打印密钥。
- 发布器也支持 `python skills/gzh-draft-publisher/scripts/publish.py --env <仓库外凭证> full <文章目录>`，显式参数优先于环境变量。
- 微信草稿发布前必须通过 `workflow_gate.py --stage draft_submitted`；群发动作仍需人工确认。
