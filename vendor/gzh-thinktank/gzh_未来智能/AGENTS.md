# Agent Skills Mount Configuration — X超玩•未来智能（X超玩•未来智能）独立工作流

> 本文件用于定义 Codex, Claw, Cursor, Claude Code 等 Agent 识别与加载本工作流技能的通用规范。
> 本目录是 **X超玩•未来智能 单账号独立工作流**（拆分自 gzh 双账号矩阵），对外品牌 **X超玩•未来智能**。
> 本工作流只负责 X超玩•未来智能 账号（`account_id: thinktank`，发布槽位 1），不存在账号二选一。

## 作品工作区隔离（强制）

- 工作流源代码留在本目录；作品、证据、图片、预览、过程脚本和发布回执必须写入仓库外层的 `GZH_ARTIFACT_ROOT`（默认 `production`）。
- 新稿只能通过 `scripts/matrix_init.py` 创建 `active/THK-YYYYMMDD-NNN-slug/`；仓库根 `drafts/` 已废弃，出现即由 clean-room 检查阻断。
- 文章根只放标准门禁产物；一次性脚本/日志进文章 `work/`，交付副本进 `exports/`，恢复快照进 `snapshots/`。路由和素材索引进外部 `registry/`。
- 具体编号、生命周期、迁移和归档规则以 [`docs/article-workspace-governance.md`](docs/article-workspace-governance.md) 和 [`workspace-contract.yaml`](workspace-contract.yaml) 为准。

## 核心工作流 Skill 路由

- **X超玩•未来智能 AI 项目实战与解决方案工作流** -> [SKILL.md](skills/ai-thinktank-workflow/SKILL.md)
- **X超玩•未来智能定位与调性合同** -> [合同](profiles/thinktank-positioning.yaml)
- **内容策略与选题简报** -> [SKILL.md](skills/content-strategy/SKILL.md)
- **通用主题边界与防跑偏检查** -> [脚本](scripts/topic_integrity.py) + `topic-contract.yaml` / `topic-cluster.md`
- **转化闭环设计** -> [SKILL.md](skills/opc-conversion-loop/SKILL.md)
- **微信文章 TTS 语音朗读生成器** -> [SKILL.md](skills/wechat-tts-audio/SKILL.md)
- **微信纯 SVG 交互排版组件库** -> [SKILL.md](skills/wechat-svg-interactive/SKILL.md)
- **微信 SVG 粘贴兼容合同** -> [脚本](scripts/check_wechat_svg_compatibility.py)（仅在直接粘贴 SVG 到公众号编辑器时启用 `wechat-paste` profile）
- **微信搜一搜 SEO 算法优化器** -> [SKILL.md](skills/wechat-seo-optimizer/SKILL.md)
- **公众号关注卡片与二维码合成器** -> [SKILL.md](skills/wechat-card-qrcode/SKILL.md)
- **微信高级 HTML 排版引擎** -> [SKILL.md](skills/gzh-design-skill/SKILL.md)
- **视觉简报与图片质量检查** -> [脚本](scripts/visual_qa.py) + [视觉配置](profiles/visual-styles.yaml)
- **视觉语义合同与配图关联检查** -> [脚本](scripts/visual_semantic_qa.py) + `visual-contract.json` / `visual-semantic-review.json`
- **视觉路由一致性与执行 provenance** -> [脚本](scripts/visual_route_consistency.py) + `visual-route-consistency.json` + `visual-run-manifest.jsonl`
- **视觉合同漂移与审美旁路** -> `scripts/visual_contract_audit.py` + `scripts/visual_taste_review.py` + `visual-contract-audit.json` / `visual-taste-review.json`
- **视觉几何拓扑与正文背景一致性检查** -> [脚本](scripts/visual_geometry_qa.py) + `geometry-contract-v1` / `background-contract-v1`
- **视觉美学卫生与箭头/标签检查** -> [脚本](scripts/visual_aesthetic_qa.py) + `visual-aesthetic-review.json`
- **视觉读者理解测试包** -> [脚本](scripts/visual_reader_test.py) + `visual-reader-test.json`（默认 pending-human，不冒充真人测试）
- **可信信源混合证据层** -> [SKILL.md](skills/source-evidence-layer/SKILL.md) + [脚本](scripts/source_evidence.py) + `evidence-plan.json` / `source-evidence.json` / `evidence-provenance.json` / `evidence-lineage.json`
- **主题证据隔离** -> [脚本](scripts/topic_evidence_isolation.py) + `topic-evidence-isolation.json`；证据计划绑定当前 `topic-contract.yaml`，换主题必须重新绑定并清理旧 evidence。
- **视觉产物完整性检查** -> [脚本](scripts/visual_artifact_qa.py)：源 SVG/HTML 重复属性、未解析 CSS 变量、最终 PNG 异常黑色连通域
- **手绘 Excalidraw 可编辑关系图** -> [脚本](scripts/render_excalidraw_style.py)：原生 `.excalidraw.json` + SVG/PNG sidecar；native renderer 不可用时回退 Chrome SVG
- **图片理解视觉审查** -> [SKILL.md](skills/vision/SKILL.md) + `skills/vision/vision.py`：原生多模态或外部 Vision provider 的最终像素复核
- **视觉模型职责路由** -> [配置](profiles/visual-model-policy.yaml)：文本模型负责编排，多模态模型/人工负责像素审查，技术图由确定性渲染器生成
- **LaTeX 公式渲染与审计** -> [脚本](scripts/formula_pipeline.py) + `formula-manifest.json` + `formula-src/`
- **公众号视觉导演与生图编排** -> [SKILL.md](skills/gzh-visual-director/SKILL.md) + [导演计划](scripts/build_image_prompt_plan.py)
- **公众号 Art Direction 与审美审查** -> [策略](profiles/visual-taste-policy.yaml) + `scripts/build_art_direction.py` + `scripts/visual_taste_review.py`；硬缺陷阻断，未完成人眼确认时保持 pending-human
- **Agnes Image 2.1 Flash 视觉增强** -> [SKILL.md](skills/agnes-image-21-flash/SKILL.md) + [提示词计划脚本](scripts/build_image_prompt_plan.py)
- **公众号选题/固定账号路由** -> [脚本](scripts/route_content.py)（账号固定为 thinktank）
- **公众号派生媒体门禁** -> [脚本](scripts/media_guard.py)
- **主张 provenance 与独立事实复核** -> [脚本](scripts/verify_claims.py) + [事实复核包](scripts/fact_review.py)
- **素材内容寻址索引** -> [脚本](scripts/build_asset_index.py)
- **素材孤儿清理** -> [脚本](scripts/check_orphan_assets.py)：重建前阻断未被正文或视觉合同引用的旧图片/可编辑源
- **本地检查点与恢复** -> [脚本](scripts/checkpoint.py)
- **T+1/T+7 原始数据导入** -> [脚本](scripts/import_metrics.py)
- **批准事件完整性签名（HMAC；非身份认证）** -> [脚本](scripts/sign_approval_events.py)
- **Clean-room 工作区与 manifest 完整性** -> [脚本](scripts/workspace_hygiene.py) + [manifest 刷新](scripts/update_split_manifest.py)
- **逐图视觉审查回执** -> [脚本](scripts/vision_review.py)：绑定图片 SHA-256、读者任务、实际 native/external/human 能力和可读性结果
- **微信代码样式与对比度门禁** -> [脚本](scripts/style_lint.py)：最终 HTML 的 code/pre 必须使用等宽栈、浅色账号色板和 WCAG AA 对比度
- **主题绑定 CTA 合同** -> [脚本](scripts/cta_contract.py) + `cta-contract.json`：回复关键词、lead magnet 和主 CTA 必须非空、唯一并绑定当前主题
- **关注卡片 CTA 资产（可选）** -> [脚本](scripts/render_footer_card.py)：仅在明确需要公众号关注卡片时调用，输出放入文章 `work/` 或 `exports/`，并将生成的 snippet 纳入排版输入后重新通过 `formatted` 门禁
- **handoff 输入质量门** -> [脚本](scripts/validate_handoff.py) + `handoff-contract-v1`：人工卡片必须带来源 SHA-256、升级信号、目标主题和人工批准
- **Skill 能力盘点** -> [脚本](scripts/audit_skill_inventory.py)：只扫描当前仓库 SKILL.md，输出哈希和 frontmatter，不读取凭证

## Agent 加载规范

- 视觉解释深度合同：涉及原理、架构、流程、状态、checkpoint、API 边界或后端选型的正文图，必须运行 scripts/visual_depth_qa.py --article <文章目录> check；该脚本检查 reader_question、answer_sentence、typed relations、claim/evidence/source_locator 和机器可读 fallback。结构检查通过不等于真人 reader test 通过。
- 视觉美学卫生合同：确定性 SVG 还必须运行 scripts/visual_aesthetic_qa.py --article <文章目录>；检查箭头方向、路由终点箭头唯一性、标签/节点/连线碰撞、safe frame 和 footer 裁切。几何不穿节点不等于视觉通过。
- 读者理解测试：深度视觉合同必须生成 `visual-reader-test.json`；没有真实回答时状态必须是 `pending-human`，不得把结构分数写成读者或审美通过。

1. 当用户要求进行“项目部署教程”、“原理拆解”、“深度长文”时，加载 `ai-thinktank-workflow`。
2. 本工作流账号固定为 **X超玩•未来智能（thinktank，对外 X超玩•未来智能）**；任何路由、初始化、门禁脚本遇到其他账号一律阻断。
3. 生成完 HTML 文章后，自动执行 `python skills/gzh-design-skill/scripts/validate_gzh_html.py <html_file>` 进行合规性校验。
4. 生成配图后，必须执行 `python scripts/visual_qa.py check --article <文章目录>`；封面选择必须在 `visual-brief.yaml` 中记录。
5. X超玩•未来智能涉及原理、架构或概念插图时，先执行 `python scripts/visual_qa.py plan --article <文章目录>`，再执行 `python scripts/visual_semantic_router.py --article <文章目录>` 完成语义路由状态闭环，随后执行 `python scripts/build_art_direction.py --article <文章目录>` 和 `python scripts/build_image_prompt_plan.py --article <文章目录> --provider agnes`；生成后必须通过 `python scripts/visual_contract_audit.py --article <文章目录>`、`python scripts/visual_taste_review.py --article <文章目录>`、`python scripts/visual_artifact_qa.py --article <文章目录>`、`python scripts/visual_semantic_qa.py --article <文章目录>` 和 `python scripts/visual_route_consistency.py --article <文章目录>`。`visual_semantic_qa.py` 会记录 `skills/vision/SKILL.md` 的路由探测；有原生图片输入时由多模态模型/人工完成最终像素复核，无原生能力时必须改走外部 Vision provider 或保持 pending-human，不能仅凭文本模型自报通过。架构/代码/流程图优先走可编辑的 Mermaid/SVG/HTML/Excalidraw。已有 `visual-contract.json` 时，语义路由器只输出合同绑定的实际视觉锚点，不能把正文小节误报成另一种图片版式。
   有连线的确定性图还必须通过 `scripts/visual_geometry_qa.py` 的 `geometry-contract-v1`；正文画布背景遵守文章级 `background-contract-v1`，封面可使用独立品牌背景。`visual_semantic_qa.py` 之后必须运行 `python scripts/vision_review.py --article <文章目录> record --reviewer-mode native|external|human`，再运行 `... check`；routing= native 只是能力路由，不是完成审图的证明。`visual-routing.json` 是 route/claim 唯一事实源，`visual-contract-audit.json` 必须无 error；`art-direction.yaml` 与 `visual-taste-review.json` 记录审美旁路，不得把 receipt 存在写成 workflow gate 已推进。
   确定性 SVG 在视觉语义检查后还必须通过 `python scripts/visual_aesthetic_qa.py --article <文章目录>`；失败时不得推进 illustrated/final_reviewed。
   模型职责遵守 `profiles/visual-model-policy.yaml`：文本模型不能自称完成像素级图片审核；需要判断线段、裁切、层级和可读性时必须有真实图片输入的多模态模型或人工终审。
6. 文章包含 `$...$` 或 `$$...$$` 时，先执行 `python scripts/formula_pipeline.py prepare --article <文章目录>`，再运行排版器；必须通过 `python scripts/formula_pipeline.py check --article <文章目录>`。
7. 首次写稿前，先执行 `python scripts/bootstrap_article_environment.py`；初稿完成后必须执行 `python scripts/record_revision.py` 登记新稿或复用稿；复用必须显式批准并记录来源规范化 SHA-256。
8. 每篇新内容必须先执行 `python scripts/route_content.py --interactive`（或 `--topic-mode` 直连），账号固定 thinktank；再把路由文件传给 `matrix_init.py --route`。
9. 每篇新内容在 `topic_selected` 前必须批准 `topic-contract.yaml`；必须明确 canonical_topic、主题锚点、in/out scope、子题回链和偏题阈值。初稿、内容审稿和终审会重复运行 `python scripts/topic_integrity.py`，支撑概念没有回到主主题时阻断。
10. `content-brief.yaml` 必须填写 `risk_level` 和 `human_review_required`；`primary_keyword`、`reply_keyword`、`lead_magnet` 和 `primary_cta` 必须围绕当前主题填写，终审会阻断沿用旧主题 CTA、无公式却承诺“公式资料”等错配文案；high/critical 内容只有真人在 `final-review.md` 中确认后才能通过终审。
11. 需要微信草稿时，先执行 `python scripts/publish_preflight.py --article <文章目录> --env <仓库外凭证> --approve --draft-permission-confirmed --ip-whitelist-confirmed`。
12. 可选输入：人工放入 `inbox/handoff/<handoff_id>/` 且通过 `python scripts/validate_handoff.py` 的已批准卡片副本可作为 user_material 选题来源；本工作流不读取任何外部目录。

## 工作流约束（单账号）

- 技术视觉的深度回执 visual-depth-review.json 是 illustrated 的附加证据；所有 relations 必须 verification_status=verified，并绑定 evidence_id/source_locator。reader_test_status=pending-human 时不得写成真人审美或读者测试通过。
- 技术图必须保留 source-to-raster 可重建证据；Excalidraw 图同时保留 `.excalidraw.json` 与 SVG sidecar。SVG/HTML/Excalidraw 源禁止 script、事件处理器、外部 URL 和未清洗 Mermaid DSL。
- 技术视觉还必须有 visual-reader-test.json；默认 pending-human 只表示测试包已生成，不能作为真人理解通过。

- 账号配置位于 `profiles/thinktank.yaml`，身份合同位于 `workflow-identity.yaml`；不得把 AppID、AppSecret 或模型 Key 写入配置。
- 本地 skill 路径以 `skills/skill-registry.yaml` 为准；兼容 slug 仅用于 Agent 触发，不用于拼接文件路径。
- 公众号主流程默认走草稿箱；只有用户明确要求对外发布时才允许切换发布模式。
- 每次结构性修改后运行 `python scripts/validate_matrix.py`；生成 HTML 后再运行公众号 HTML 校验器。
- 新建文章必须先完成选题路由（账号固定 thinktank），再使用 `matrix_init.py --route <routing.yaml>` 生成 schema v4 工作区。
- `content_medium` 固定为 `wechat_article`；视频、音频和跨平台切片只能在公众号主稿 `final_reviewed` 后作为派生附件，并通过 `scripts/media_guard.py`。
- 对外文章不得包含本机绝对路径、凭证变量名或模型密钥变量名；门禁会阻断并要求脱敏。
- 内容生产必须通过 `profiles/workflow-gates.yaml` 定义的 10 个顺序门禁：
  `environment_ready` → `topic_selected` → `research_complete` → `research_reviewed` →
  `draft_complete` → `content_reviewed` → `formatted` → `illustrated` → `final_reviewed` → `draft_submitted`。
- 每推进一个阶段，执行 `python scripts/workflow_gate.py --article <文章目录> --stage <阶段> --advance`；失败时不得手工修改 `matrix-state.json` 跳过阶段。
- `sources.json` 的 claim 必须先通过 `python scripts/verify_claims.py --article <文章目录>`；benchmark/paper-fact/高风险 claim 还必须通过 `python scripts/fact_review.py --article <文章目录> --check`，pending_human 或 agent 回执不能进入 `content_reviewed`。
- 每个正文采用的可信信源必须在 `evidence-plan.json` 中分级，并且每个 evidence 单元都要声明 `claim_ids`、`captured_at`、定位、授权和 SHA-256；运行 `python scripts/source_evidence.py audit --article <文章目录>` 后才能推进 `research_complete`。审计会把 `sources.json`、`source-verification.json`、主题合同、快照和证据文件绑定为 `evidence-provenance.json.pack_sha256`，并生成受 OpenLineage/in-toto 启发的离线 `evidence-lineage.json`（run/job/material/product；无签名、非身份认证），再校验 `topic-evidence-isolation.json`：主题指纹、来源主题命中和 evidence 目录无孤儿文件；换题必须重新绑定，不能把 LangGraph 的证据包带到 vLLM（或反向）。证据覆盖只统计 `used_in_article=true` 的来源；该回执只证明本地完整性，不证明真人身份或来源真伪。定稿后必须运行 `source_evidence.py append`，把原始证据与参考资料清单写入 `article.md` / `article.html`；后续 `audit --require-appendix` 会校验篇尾全文 SHA-256，防止手工替换引用块；截图或代码复用必须记录 `license_status`、`reuse_approved`、`reuse_reason`。
- 外部 software/API/benchmark 来源必须记录 `official_source`、`freshness_days`、`version_scope`/`package_version`；每条 claim 必须记录 `as_of`，过期或版本未知时不得进入 `research_complete`。
- 每次 `reopen_article.py` 会先创建 `checkpoint-manifest.json` 与 `snapshots/checkpoints/<id>/` 快照；可用 `python scripts/checkpoint.py verify/resume` 恢复，但恢复后必须从第一道未通过门禁重新推进。
- `image-sources.json` 完成后必须运行 `python scripts/build_asset_index.py --article <文章目录>`；`asset-index.json` 只证明素材字节、授权字段和复用 provenance，不代表已经上传微信。
- 重新生成图片前必须运行 `python scripts/check_orphan_assets.py <文章目录>`；视觉合同声明的 SVG/HTML 可编辑源也属于在用资产，不能误删或被旧产物覆盖。
- `visual-capability-registry.yaml` 中 `integrated` 才能成为执行后端；`advisory` 只能作为参考，不能写入 primary/secondary route。视觉终审还必须生成 `preview-fullpage.png` 与 `preview-slices/`，并将全部哈希写入 `preview-capture.json`。
- T+1/T+7 只能由 `python scripts/import_metrics.py` 导入带 `captured_at`、`source`、原始文件 `source_sha256` 的 JSON/CSV；没有真实导出时保持空对象，不得填入推测值。
- 高风险或显式要求签名的工作区，必须通过外部 `APPROVAL_SIGNATURE_POLICY_PATH` 与 `APPROVAL_SIGNATURE_KEY_PATH` 验证批准事件链；HMAC 只证明完整性，不能证明真人身份或不可抵赖性。
- 本目录不读取、不依赖任何外部工作流目录；handoff 卡片仅经人工放入 inbox 后作为参考来源。
- `cta-contract.json` 记录当前文章的主题指纹与转化字段；主题或 CTA 修改后必须重新生成并检查。
- `z5_review`、`fallback_publisher` 和 `cross_platform_repurpose` 仅在 registry 明确 opt-in、`final_reviewed` 通过且 `media_guard` 通过后可调度。
