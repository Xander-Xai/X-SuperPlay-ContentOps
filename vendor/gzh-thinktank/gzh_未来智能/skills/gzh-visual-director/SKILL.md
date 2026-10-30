---
name: gzh-visual-director
display_name: "公众号视觉导演与生图编排"
description: "把文章的认知任务转成证据优先、可复核、可降级的封面与插图计划，再路由到确定性图表或 Agnes illustrative 生图。"
category: visual-assets
version: 1.2.0
visibility: public
---

# 公众号视觉导演与生图编排

这是当前独立工作流的视觉规划层。账号身份由根目录 `workflow-identity.yaml` 固定。它借鉴本地短视频项目的
`director-material-planner`、`design-direction` 和 Excalidraw 评审原则，
但把时间轴镜头改成了“文章章节 → 读者任务 → 认知锚点”。它不是另一个
发布流程，也不会在没有审核的情况下偷偷下载或生成素材。

## 视觉决策顺序

1. **先写读者任务**：这张图要让读者看懂什么，而不是“给这一节装饰”。任务必须绑定正文片段哈希、claim、expected_elements 和 forbidden_elements。
2. **先证据，后装饰**：用户/官方素材 → 可编辑 Mermaid/SVG/HTML/Excalidraw
   图 → Agnes illustrative 概念图。生成图不能冒充截图、实验结果、代码或政策页面。
3. **确定视觉负责人**：`evidence`、`diagram`、`illustration`、
   `screen-recording` 只能选一个；每条记录必须有一个明确 fallback。
4. **锁定一套视觉系统**：颜色、字体、留白、移动端安全区和连续生图上限
   在 `visual-director-plan.json` 中固定，防止一篇文章变成模板拼盘。
5. **先生成 Art Direction 旁路合同**：运行 `python scripts/build_art_direction.py --article <文章目录>`，写出
   `art-direction.yaml`。它必须明确本篇 visual thesis、材质语言、layout families、anti-patterns、
   data_egress 和 fallback；这是审美规划证据，不是事实图合同。
6. **生成前停下来审核**：视觉简报批准、导演计划 `status: ready` 后才允许
   调用 Agnes；失败时必须留下错误和降级记录。
7. **生成后看结果**：真实 PNG 先通过 `visual_semantic_qa.py` 的语义合同检查，再通过 `visual_contract_audit.py`、`visual_qa.py`、
   `visual_taste_review.py`、390px 预览和人工/多模态视觉复核，
   任何裁切、主体漂移、文字乱码或对事实造成误导都要退回重生成。
   对任何有连线的确定性图，还必须通过 `geometry-contract-v1`：端点、节点边界、交叉、
   穿越和箭头方向都要可计算验证；没有几何合同的关系图不能进入 `illustrated`。

### 语义路由（visual-semantic-routing-v1）

正文配图不再按章节编号或固定卡片模板轮换。先运行
visual_semantic_router.py --article <文章目录>，对每个章节计算公式、矩阵/数值、关系、
时序、概念、清单和代码信号，再按以下优先级选主后端：

checklist → kv-cache/timeline → multi-head/branch → numeric/matrix →
shape → attention pipeline → qkv metaphor → relationship → concept → default

每条路由必须记录 route_rule、route_reason、route_confidence、layout_archetype、
recommended_skill 和可选的 secondary_backend。导演还必须遍历
`profiles/visual-capability-registry.yaml` 中登记的每个能力，输出
`skill-evaluation.json`：逐项记录 task overlap、集成状态、精确文本能力、移动端评分、
primary/secondary/advisory/rejected 决策及 fallback 原因。主后端承载可核验事实（KaTeX、
Mermaid、SVG、HTML 信息图）；次后端只用于同一认知任务的隐喻、白板或热力图增强，
不得把精确公式交给生图模型。路由审计写入文章目录的 visual-routing.json。

## 解释深度合同（visual-depth-contract-v1）

技术正文图在资产合同之外必须声明 reader_question、answer_sentence、entities、typed relations、claim_ids、evidence_ids、source_locator、must_explain 和 machine-readable fallback。每条 relation 必须带 type/source/target/verification_status=verified；没有证据定位的抽象边只能标 proposed，不能进入 passed。执行 scripts/visual_depth_qa.py check；结构合同通过不等于真人 reader test 或审美批准。

## 客观美学卫生合同（visual-aesthetic-contract-v1）

几何不穿节点只是底线，不代表图面可发布。确定性 SVG 还必须运行
`python scripts/visual_aesthetic_qa.py --article <article>`，并在
`visual-aesthetic-review.json` 中记录箭头方向、路由终点箭头唯一性、标签与节点/其他连线的碰撞、safe frame 边界和 footer 裁切。该回执失败时，视觉阶段必须阻断，不能用“字段齐全”覆盖图面错误。

## 读者理解测试包（visual-reader-test-v1）

使用 `python scripts/visual_reader_test.py --article <article>` 生成固定问题、答案锚点和阈值。没有真人回答时必须保持 `pending-human`；回答记录必须带 reviewer_id、correct、score 和原始答案，不能由 agent 自报理解通过。

## 资产合同

每张图都必须记录：

- `viewer_job`：读者要理解的结论；
- `visual_owner`：diagram / evidence / illustration / screen-recording；
- `claim_ids`：与事实主张的映射，纯概念图写 `[]`；
- `source_strategy`、`rights_status`、`license`；
- `generation_mode`：`deterministic` 或 `agnes`；
- `prompt_file`、`prompt_sha256`、`provider`、`model`、`size`、`ratio`；
- `continuity_group`、`safe_area`、`reference_images`；
- `fallback`、`output_sha256`、`request_sha256`。
- `source_excerpt_sha256`、`expected_elements`、`forbidden_elements`、`render_backend`。
- `content_signal`、`public_brand`、`requested_provider` 与实际 `execution_provider`；技术图必须能解释为何选择该后端。
- `requested_backend`、`execution_backend`、`fallback_reason` 和 `semantic_features`；后端降级必须有明确原因。
- `route_rule`、`route_source_sha256` 和 `claim_source_sha256`；`visual-routing.json` 是唯一路由事实源，brief/contract/source receipt 不得各自重写路由。
- `geometry_required`、`canvas_background`、`surface_background`；正文画布背景来自文章级
  `background-contract-v1`，封面可使用独立品牌背景。

## 正文任务路由（v1.1）

- Q/K/V、Shape、Attention、矩阵手算：`katex-html-composite`，保留 `formula-src` 与可编辑 HTML 源，禁止通用文字卡片。
- Multi-Head 的分支关系：优先使用 `beautiful-mermaid`；KV Cache 的 Prefill→Cache→Decode 时序：优先使用可编辑 SVG（可替换为 Excalidraw），公式仍由 KaTeX 资产单独负责。
- 架构、调用链和状态关系：`beautiful-mermaid` 或确定性 SVG；时序可用 Excalidraw/SVG。
- 封面、抽象机制和概念隐喻：Agnes Image 2.1 Flash；精确公式、代码、Shape 和事实数字不得交给生图模型。

能力注册表位于 `profiles/visual-capability-registry.yaml`，全盘扫描得到的技能清单见
`docs/visual-skills-inventory.md`。所有后端都必须接受视觉合同并返回可编辑源、输出哈希和实际执行后端；
没有合同的临时图片不能进入 `illustrated`。注册表中的 advisory 能力会被导演评估但不会被误调用，
只有 integrated 能力能成为实际 primary renderer。

`excalidraw-style` 是当前 integrated 的手绘 SVG 后端；原生 `.excalidraw.json`、
外部 Excalidraw clone 只有在完成 adapter、依赖、许可证、CJK/390px/微信 PNG
验收后才能从 advisory/POC 变为 integrated。`visual-contract-audit-v1` 会验证 path、adapter、
requested/evaluated/execution backend 和实际尺寸，避免把 registry 声明当成真实能力。

## Agnes 使用边界

- **适合**：X超玩•未来智能的封面、抽象机制、概念场景、高信息密度但不承载精确文字的
  视觉隐喻；AI哨兵的工具氛围图和机会雷达背景。
- **不适合**：架构节点、代码、数字、接口字段、产品截图、新闻现场和任何需要
  逐字核验的事实。此类素材走 Mermaid/SVG/HTML/用户授权截图。
- **提示词结构**：`Subject → Scene → Style → Lighting → Composition →
  Quality → Constraints`，并显式写读者任务、claim、移动端安全区、连续性组和 fallback。
- **图生图/多图合成**：只在计划里登记参考图角色；本地参考图由适配器转成 Data URI，
  不把本机绝对路径或私有 URL发送给模型。

## 执行入口

```powershell
python scripts/visual_qa.py plan --article <文章目录>
python scripts/build_image_prompt_plan.py --article <文章目录> --provider agnes
python scripts/visual_qa.py approve --article <文章目录> --reason "已确认视觉导演计划"
python scripts/generate_article_images.py --article <文章目录> --provider agnes --execute
python scripts/visual_qa.py check --article <文章目录>
```

架构、流程、代码、公式和 Shape 图即使与同一篇文章共存，也要保留可编辑的确定性版本；Agnes
只负责 illustrative 层。没有 API Key 或端点不可达时使用显式的
`--fallback-on-error`，技术正文必须降级到语义正确的 SVG/HTML/Excalidraw 图，不能降级为无关文字卡片，且必须标记真实的 `execution_provider`。

### 几何与背景门禁

- `scripts/visual_semantic_qa.py` 会调用 `scripts/visual_geometry_qa.py`；SVG 可使用
  `metadata#visual-geometry-contract`，简单图也可使用 `data-role=node/edge`。
- `geometry_required: true` 的图必须证明每条边的 source/target、路径点和节点边界；
  非端点穿越、无意交叉、路径重叠或箭头未到达目标都会阻断。
- 正文所有确定性图的画布底色必须等于 `visual-brief.yaml.background_contract.canvas_hex`；
  `surface` 仅用于卡片内部层次，封面不参与正文背景强一致比较。

### 模型职责路由

遵守根目录 `profiles/visual-model-policy.yaml`：文本模型负责读者任务、语义合同、提示词
和图规格；多模态模型或人工负责真实 PNG/截图的构图、线段视觉效果、文字可读性和移动端裁切；
架构/公式/代码/流程图由本地 SVG/HTML/Mermaid/KaTeX 确定性渲染。没有图片输入能力的文本模型
不得把 `final_pixel_review` 写成 passed。
