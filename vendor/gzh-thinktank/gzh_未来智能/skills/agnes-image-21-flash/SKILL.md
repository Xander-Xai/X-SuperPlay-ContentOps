---
name: agnes-image-21-flash
display_name: "Agnes Image 2.1 Flash 公众号视觉增强器"
description: "为公众号封面、概念插画和高信息密度视觉素材提供 Agnes Image 2.1 Flash 文生图/图生图适配。它必须在视觉简报、提示词计划、素材授权和图片质量检查之后执行；架构图、流程图和代码图优先使用可编辑的 Mermaid/SVG/HTML 方案。"
category: visual-assets
version: 1.1.0
visibility: public
---

# Agnes Image 2.1 Flash 公众号视觉增强器

这是公众号视觉链路的**统一外部生成器**，不是独立的发布流程。主路由仍然是：

`visual-brief.yaml` → `image-generation-plan.json` → 提示词文件 → 图片生成 → `image-sources.json` → `visual_qa.py` → 手机预览

## 适用范围

- AI哨兵：封面、工具场景图、实测氛围图和少量视觉钩子。
- X超玩•未来智能：封面、原理解释的概念场景图、抽象机制插画和知识地图背景。
- 不把模型生成的文字、代码、数字、产品界面或政策截图当作事实证据。
- 架构图、流程图、代码图和数据图优先由 Mermaid、SVG、HTML 或 Excalidraw 生成，再由公众号排版引擎处理。

## API 约定（同步个人 Agnes Image 2.1 Flash skill）

- Endpoint：`https://apihub.agnes-ai.com/v1/images/generations`
- Model：`agnes-image-2.1-flash`
- Key：仓库外的 `AGNES_API_KEY` 环境变量。
- 配置：`.aws-article/config.yaml` 的 `image_model`。
- 禁止把真实 Key 写入仓库、文章、日志或 provenance。
- `size` 优先使用 `1K` / `2K` / `3K` / `4K`，`ratio` 使用 `1:1`、`4:3`、
  `16:9`、`21:9` 等模型原生比例；旧式 `1024x768` 仅作为兼容输入。
- 文生图默认把 `extra_body.response_format` 设为 `b64_json`，避免再下载模型返回的
  不可信 URL；图生图/多图合成通过 `extra_body.image` 传入公共 HTTPS URL 或本地
  Data URI，适配器不会把本机绝对路径外发。

## 提示词契约

每张图必须先登记以下字段（`prompt-v2`）：

1. `viewer_job`：读者看完这张图要理解什么；
2. `visual_owner`：diagram / evidence / illustration / screen-recording；
3. `claim_ids`：如果对应文章事实，必须引用 `sources.json` 的 claim；
4. `subject`、`scene`、`style`、`lighting`、`composition`、`quality_requirements`；
5. `fallback`：正文必须登记当前主题语义 SVG/HTML/Excalidraw 方案；`text_poster.py` 仅允许登记为当前文章品牌封面 fallback；
6. `prompt_sha256`、provider、model、输出文件指纹。
7. `generation_mode`、`source_strategy`、`rights_status`、`continuity_group`、
   `safe_area`、`request_sha256`；确定性图还要保存可编辑 SVG 源文件。

推荐提示词结构：

`Subject + Scene/Environment + Style + Lighting + Composition + Quality Requirements + Constraints`

高信息密度图要分层描述主体、背景、次要细节、构图和安全区；不要用“随便画一张架构图”这种不可验收的提示词。

## 公众号专用约束

- 画面中的中文文字必须极少且可删；长标签、代码和数字放回 HTML/SVG 叠加。
- 生成图必须标记为 `illustrative`，不能伪装成真实产品截图、真实实验结果或官方页面。
- 每篇文章避免连续使用同一种卡片构图；至少混合封面、概念图、流程图或证据素材。
- 生成前必须通过封面/视觉简报确认；生成后必须通过 `visual_qa.py check` 和 390px 浏览器预览。
- 技术正文若含连线，必须同时通过 `visual_semantic_qa.py` 调用的 `geometry-contract-v1`；正文确定性图的画布背景必须符合 `background-contract-v1`，封面背景不纳入正文强一致比较。
- 失败时保留提示词和失败原因，切换到明确记录的 fallback，不得静默伪造完成。

## 执行入口

```powershell
python scripts/build_image_prompt_plan.py --article <文章目录> --provider agnes
python scripts/generate_article_images.py --article <文章目录> --provider agnes --execute
# Agnes 暂时不可达时，显式启用可审计本地降级（不会伪称为 Agnes 成图）
python scripts/generate_article_images.py --article <文章目录> --provider agnes --execute --fallback-on-error
python scripts/visual_qa.py check --article <文章目录>
```

生成器使用公众号现有的 `gzh-visual-assets/scripts/image_create.py`，因此所有外部请求、
SSRF 防护、Data URI 转换、图片落盘和错误分类仍由统一入口负责。个人 skill 的
`skills/agnes-image-21-flash` 作为本工作流的能力来源，公众号项目
不直接暴露该本机路径，也不把个人 API helper 当作第二套发布器。
