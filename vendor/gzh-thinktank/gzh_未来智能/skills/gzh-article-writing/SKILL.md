---
name: gzh-article-writing
description: Agent 本地公众号写作与修订；按已通过的选题、研究证据和账号约束生成 draft.md，不连接外部写作模型。
category: content
version: 2.0.0
visibility: public
---

# 公众号写作（Agent 本地执行）

本 skill 只负责把已通过门禁的 `topic-card.md`、`research.md` 和 `content-brief.yaml`
写成 `draft.md`。正文由当前 Agent 直接产出，不上传文章内容，也不读取写作模型凭证。

## 输入与前置

- 必须先完成 `environment_ready`、`topic_selected`、`research_complete`、`research_reviewed` 门禁。
- 读取 `.aws-article/config.yaml` 与本篇 `article.yaml` 的公开字段；本篇配置覆盖全局配置。
- `content-brief.yaml` 必须包含账号、目标读者、文章类型、风险级别和人工复核要求。
- 事实主张只能来自 `sources.json` / `research.md`；不确定内容标记为待核验，不得凭空补齐。

## 写作规则

1. 先提炼一个明确读者任务，再安排标题、导语、正文层级、案例/公式/结论和行动建议。
2. 本工作流固定为 X超玩•未来智能：偏原理拆解、教程、SOP 和可复用资产；账号身份以根目录 `workflow-identity.yaml` 为准。
3. 每个事实段落可回溯到 `claim_id`；引用路径只保留在 `draft.md`，由审稿阶段统一剥离。
4. 图片只写语义占位符和 `visual_job`，不在写稿阶段自行生成图片或伪造截图。
5. 保持移动端短段落、清晰小标题、可扫描列表；不得把密钥、本机路径或内部变量写入文章。
6. **thinktank 文章含数学公式（`$...$` 或 `$$...$$`）的章节，必须配套 1 块 fenced 代码（PyTorch / NumPy / Shell 实现）**：公式驱动代码上下文，避免"只讲原理不落地"。代码块按章节归属由 `scripts/build_image_prompt_plan.py:section_code_snippets` 自动提取到视觉合同，渲染为真实代码卡。示例：章节正文写 `$QK^T/\sqrt{d_k}$` 时紧跟一段 5~15 行 PyTorch 实现。无公式的章节不强制代码块。

## 辅助脚本

```powershell
python skills/gzh-article-writing/scripts/write.py prompt draft <topic-card.md>
python skills/gzh-article-writing/scripts/write.py strip-citations <draft.md> -o <article.md>
```

`prompt` 只输出约束提示词 JSON，便于审计；`strip-citations` 仅剥离资料路径标注。
`draft`、`rewrite`、`continue` 是兼容入口，会提示由 Agent 本地完成并退出，不会发起网络请求。

## 输出与门禁

写作完成后必须执行 `python scripts/record_revision.py --article <目录> --mode new`（复用稿
必须登记来源和规范化哈希），补齐 `content-revision.json`，再推进 `draft_complete`。
后续审稿、排版、视觉、终审和草稿提交不能在本 skill 内跳过。
