---
name: gzh-article-orchestrator
description: 公众号图文一条龙总控：选题、研究、Agent 本地写作、审稿、排版、Agnes 视觉增强、终审和微信草稿箱回读。
category: workflow
version: 2.0.0
visibility: public
---

# 公众号运营总控

文章工作区必须由 `scripts/matrix_init.py` 分配到仓库外的
`<GZH_ARTIFACT_ROOT>/active/THK-YYYYMMDD-NNN-slug/`；仓库根 `drafts/` 已废弃。路由放外部
`registry/routes/`，过程脚本/调试输出放本篇 `work/`，交付副本放 `exports/`，恢复快照放
`snapshots/`。详见 `docs/article-workspace-governance.md`。

本 skill 编排当前独立工作流的公众号图文流程；账号身份由根目录
`workflow-identity.yaml` 固定，不能在运行时切换。写稿由当前 Agent 本地完成；所有需要外部模型的图片生成统一使用
Agnes Image 2.1 Flash。架构图、流程图、公式图和代码图优先使用正文语义合同驱动的可编辑 Mermaid、
SVG 或 HTML，Agnes 只做 illustrative 视觉增强。

## 外部能力与凭证

- Agnes：固定端点 `https://apihub.agnes-ai.com/v1/images/generations`，模型
  `agnes-image-2.1-flash`，只读取仓库外环境的 `AGNES_API_KEY`。
- 微信：只读取所选槽位的 `WECHAT_{N}_APPID`、`WECHAT_{N}_APPSECRET`。
- 凭证不得写入 profile、文章、日志、审计 JSON 或 Git；通过 `--env` 或
  `WECHAT_ENV_PATH` 指定外部环境文件。

## 前置校验

```powershell
python scripts/validate_matrix.py
python skills/gzh-article-orchestrator/scripts/validate_env.py `
  --config .aws-article/config.yaml --env D:/path/to/external.env
```

只有退出码 0 才能继续。校验会严格检查 Agnes 固定配置与 `wechat_publish_slot` 指向
的微信槽位；`publish_method: none` 仅在用户明确不接微信时使用。

## 十道顺序门禁

每个阶段必须执行 `python scripts/workflow_gate.py --article <目录> --stage <阶段> --advance`，
失败不得手工改 `matrix-state.json`：

1. `environment_ready`：配置、路由、账号和内容媒介已确认；
2. `topic_selected`：选题卡、主题边界合同、主题簇、SEO 和 Brief 完整；必须锁定 canonical topic、scope、锚点词、子题回链和偏题阈值；
3. `research_complete`：研究记录、来源、claim 映射和哈希完整；
4. `research_reviewed`：逐来源完成摘要/短摘录提取、主题相关性、适用范围、局限与 include/conditional/exclude 决策；未审来源不能进入正文证据或 claim；
5. `draft_complete`：Agent 产出 `draft.md`，并登记 `content-revision.json`；
6. `content_reviewed`：敏感词、事实、错字、引用、AI 标识和结构化审稿通过；
7. `formatted`：生成微信 HTML、`format-report.json`，通过严格 HTML 校验；
8. `illustrated`：视觉简报、导演计划、正文语义合同、Agnes prompt 计划、素材来源、视觉语义 QA 和视觉 QA 完整；**公式图可读性检查**（旋转检测、空白检测、长宽比异常检测）和**视觉多样性警告**（同一 visual_type 占比不超过 60%，相邻 section 不允许相同 visual_type）在此阶段执行；
9. `final_reviewed`：真实 Chrome/Edge 移动端预览、人工确认和风险复核通过；
10. `draft_submitted`：草稿创建后 `draft/get` 回读，标题、正文、图片和摘要一致。

强制审计产物包括 `routing.yaml`、`content-brief.yaml`、`topic-card.md`、`topic-contract.yaml`、
`topic-cluster.md`、`content-calendar.md`、`topic-integrity.json`、`research.md`、
`sources.json`、`draft.md`、`content-revision.json`、`review-checks.json`、
`review-evidence.json`、`ai-disclosure.yaml`、`article.md`、`article.html`、
`format-report.json`、`visual-brief.yaml`、`image-generation-plan.json`、
`image-sources.json`、`visual-contract.json`、`visual-semantic-review.json`、`formula-manifest.json`（含公式时）、`final-review.md`、`preview-capture.json`、`publish-preflight.json`
和 `publish-attempt.json`。

## 标准执行顺序

```powershell
python scripts/bootstrap_article_environment.py
python scripts/route_content.py --interactive
python scripts/matrix_init.py --route <GZH_ARTIFACT_ROOT>/registry/routes/<routing>.yaml
python scripts/topic_integrity.py --article <目录> --contract-only
python scripts/visual_qa.py plan --article <目录>
python scripts/build_image_prompt_plan.py --article <目录> --provider agnes
python scripts/visual_semantic_qa.py --article <目录>
python scripts/generate_article_images.py --article <目录> --provider agnes --execute
python scripts/formula_pipeline.py prepare --article <目录>
python scripts/visual_qa.py check --article <目录>
python scripts/render_mobile_preview.py --article <目录>
python scripts/publish_preflight.py --article <目录> --env D:/path/to/external.env `
  --approve --draft-permission-confirmed --ip-whitelist-confirmed --probe
python skills/gzh-draft-publisher/scripts/publish.py --env D:/path/to/external.env full <目录>
python scripts/verify_draft_submission.py --article <目录> --env D:/path/to/external.env
```

写稿阶段可先运行 `skills/gzh-article-writing/scripts/write.py prompt draft ...` 获取公开
约束提示词，再由 Agent 直接写入 `draft.md`；该脚本不会联网。草稿模式是默认模式，
不会群发；只有用户明确要求对外发布才允许切换发布模式。

## 视觉路由规则

- 封面、概念隐喻和机制插画：Agnes，比例和安全区由视觉计划确定；中文标题后置排版。
- Transformer、Q/K/V、Agent 架构、调用链：Mermaid/SVG/HTML 优先，Agnes 仅增强背景或
  视觉隐喻，不能生成事实图、代码或精确公式。
- 公式推导、Shape 检查和对比表：先执行 `scripts/formula_pipeline.py prepare`，再使用 HTML/SVG/KaTeX 的确定性渲染，禁止依赖模型文字。
  - **公式文字颜色必须为深色**（#17324D），白色文字在透明背景上不可见。
  - **Chrome 截图视口高度不低于 2000px**，防止复杂公式被裁切或旋转。
  - **`visual_semantic_qa.py` 包含公式图可读性检查**：检测旋转（inline 公式 height > width）、空白（文件大小/像素比过低）和长宽比异常。
- 事实截图、产品界面和数据：使用官方或用户授权素材，记录来源、许可和 SHA-256。
- Agnes/API 不可达：按语义合同中的 fallback 生成可编辑本地资产，并在 provenance 中同时标明
  `requested_provider` 与 `execution_provider=local-*`，不得伪称为模型生成；技术正文禁止退化为无关文字海报。
- **视觉多样性约束**：`build_image_prompt_plan.py` 在编译 prompt 计划时检查 visual_type 重复率（上限 60%）和相邻 section 雷同，违规时输出警告。
- **模板高度溢出断言**：`render_visual_anchor.py` 在 `semantic_svg()` 返回前检测内容最大 y 坐标，超出 canvas 高度时立即报错，避免"画完才发现裁切"。
- **source_excerpt 单源化**：`scripts/excerpt_utils.py` 是 `source_excerpt_sha256` 的唯一计算入口，`visual_semantic_qa.py` 和 `formula_pipeline.py` 均从该模块导入，消除双写不一致。

## 发布安全

图文是唯一主交付物；视频、音频和跨平台切片只能在 `final_reviewed` 后经过
`media_guard.py` 派生。发布器只能在终审通过且预检批准后运行，草稿回读通过后才推进
最后一道门禁；群发仍需人工确认。
