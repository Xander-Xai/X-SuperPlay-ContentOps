---
name: aws-wechat-article-images
description: 公众号封面｜公众号配图｜公众号插图｜AI 生图 — 公众号 AI 封面与配图生成，按文章标题与内容自动匹配画风，一稿多方案，多风格预设可复用。面向公众号编辑、自媒体、品牌设计。触发词：「封面」「配图」「插图」「生成图片」「给文章加图」「做个封面」「文章插图」「配个图」。不写正文只发一组图请走 aws-wechat-sticker；需要多环节串联（写+审+排+配图+发）请走 aws-wechat-article-main。
homepage: https://aiworkskills.cn
url: https://github.com/aiworkskills/wechat-article-skills
metadata:
  openclaw:
    requires:
      env:
        - IMAGE_MODEL_API_KEY
      bins:
        - python3
    primaryEnv: aws.env
---

# 配图

**公众号封面 & 配图 AI 生成** —— 按文章内容自动匹配画风，一稿多方案，风格体系可复用。

> **套件说明** · 本 skill 属 `aws-wechat-article-*` 一条龙套件（共 9 个 slug，入口 `aws-wechat-article-main`）。跨 skill 的相对引用依赖同一 `skills/` 目录，建议一并 `clawhub install` 全套。源码：<https://github.com/aiworkskills/wechat-article-skills>

## 能力披露（Capabilities）

本 skill 调 `image_create.py` **调外部图像 API** 生成封面与正文配图。**会把图片提示词（可能含文章主题片段）发给用户配置的图像生成端点。** 具体行为：

- **凭证读取**：`aws.env` 的 `IMAGE_MODEL_API_KEY`
- **凭证外发**：该 key 以 `Authorization: Bearer` 头发送到 `image_model.base_url` 指定端点（常见为 DALL-E、gpt-image 兼容 `/v1/images/generations`，或多模态模型 `/v1/chat/completions`，具体由用户配置）
- **内容外发**：每张图片的 prompt（文本）作为 JSON POST body 发送；prompt 内容来自本篇 `imgs/prompts/*.md`（可能包含文章标题、章节摘要）
- **下图 SSRF 防御**：若 API 响应返回图片 URL（而非 base64），脚本**仅允许下载 http/https 公网地址**；内网 / 环回 / 链路本地 / 保留地址全部拒绝（防止恶意或被劫持的模型端点把脚本当作 SSRF 跳板）
- **文件读**：仓库内 `.aws-article/config.yaml`、本篇 `article.yaml`、`article.md`、`imgs/prompts/*.md`、`.aws-article/products/{产品名}/images/*`（业务配图库，本篇涉及用户业务时优先复用）
- **文件写**：本篇 `imgs/*.{png,webp}`、可选 `img_analysis.md`
- **shell**：仅 `python3 {baseDir}/scripts/image_create.py`、`user_image_prepare.py`

**建议**：用专用 key（最低权限、独立计费），避免使用 account 级 master key。

## 配套 skill（informational）

本 skill 是 `aws-wechat-article-*` 一条龙公众号套件的**配图环节**（入口 `aws-wechat-article-main`）。工作流中的若干步骤会读取同级 `../aws-wechat-article-main/references/*.md` 等共享文档（首次引导、env/config 示例、articlescreening schema 等）。

- **套件完整装齐到同一 `skills/` 根目录**时，跨 skill 引用都能读到。
- **单独安装本 skill** 时，跨 skill 引用的步骤会在读取阶段遇到 `file not found`；本 skill 内的生图脚本仍可用。

完整 9 slug 清单见 [源码仓库](https://github.com/aiworkskills/wechat-article-skills)。

## 路由

完整长文从选题到发布 → [aws-wechat-article-main](../aws-wechat-article-main/SKILL.md)；图片消息/九宫格等多图推送 → [aws-wechat-sticker](../aws-wechat-sticker/SKILL.md)。

读取文章中的配图标记，按 Type × Style 体系生成图片。专注于**长文配图**，贴图请用 sticker。


## 多风格配图方案（无需 API Key）

本 skill 支持多种**零 API Key** 配图方式，适用于不同文章场景。Agent 执行配图步骤时，应根据文章内容类型和配图标记中的 `style` 字段自动选择最合适的方案。

### 方案选择指南

| 文章场景 | 推荐方案 | 风格特点 | 需要截图 |
|----------|----------|----------|----------|
| 技术教程/流程说明 | **Mermaid 图表** | 专业图表、流程图、架构图 | 是（SVG→PNG） |
| 概念解释/轻松科普 | **Excalidraw 手绘** | 手绘涂鸦风、白板风、亲切 | 是（SVG→PNG） |
| 数据展示/信息图 | **HTML 信息图** | 扁平/极简/杂志风、手机优先 | 是（HTML→PNG） |
| 科技/AI 文章封面 | **p5.js 生成艺术** | 抽象几何、粒子流场、科技感 | 是（Canvas→PNG） |
| 品牌感/高品质封面 | **Canvas 设计** | 博物馆级、海报级品质 | 是（PDF/PNG） |
| 步骤说明/场景插画 | **SVG 矢量插画** | 扁平插画、图标风 | 否（SVG 直接用） |
| 多图推送/贴图装饰 | **像素/贴纸** | 像素风、贴纸、GIF 动图 | 否 |
| 需要照片级真实感 | **Agnes API 生图** | AI 照片、写实风格 | 否（API 直出） |

### 方案 A：Mermaid 图表（beautiful-mermaid）

**适用**：流程图、架构图、序列图、ER 图、甘特图、思维导图、对比表格

**Skill 路径**：`{skills_root}/beautiful-mermaid/SKILL.md`

**调用方式**：
1. Agent 根据文章内容生成 Mermaid 语法
2. 使用 `beautiful-mermaid` 渲染为 SVG（15+ 主题可选）
3. 将 SVG 转换为 PNG（使用浏览器截图或 Puppeteer）
4. 保存到 `imgs/` 目录

**⛔ 标签规范**（必须遵守，否则渲染出转义符号）：
- **禁止** `<br/>`、`<b>` 等 HTML 标签
- **禁止**双引号包裹：不用 `A["标签"]`，用 `A[标签]`
- 用 `-` 分隔，≤10 字：`A[ChatGPT - 全能助手]`

**主题推荐**：
- 科技类文章：`tokyo-night` / `one-dark` / `dracula`
- 轻松科普类：`catppuccin-latte` / `github-light` / `nord-light`
- 数据图表：`solarized-dark` / `zinc-dark`

### 方案 B：Excalidraw 手绘风格（excalidraw-skill-pack）

**适用**：概念解释、流程示意、轻松教程、笔记风配图

**Skill 路径**：`{skills_root}/excalidraw-diagram/SKILL.md`

**调用方式**：
1. Agent 生成 Excalidraw JSON 格式的图元素数据
2. 使用 Excalidraw 导出为 SVG 或 PNG
3. 保存到 `imgs/` 目录

**风格特点**：手绘线条、涂鸦感、不完美的真实感——天然反 AI 味

### 方案 C：HTML 信息图（openclaw-article-to-image）

**适用**：文章配图、章节插图、数据卡片、小红书风格信息图

**Skill 路径**：`{skills_root}/openclaw-article-to-image/SKILL.md`

**调用方式**：
1. Agent 分析文章内容，提取核心信息
2. 自由设计 HTML 信息图（9 种风格模板可参考：手账/波普/终端/蓝图/极简/杂志等）
3. 后处理脚本优化 HTML
4. Chrome/Puppeteer 截图生成 PNG
5. 保存到 `imgs/` 目录

**注意**：手机优先设计，字号必须够大（3 倍缩放）

### 方案 D：p5.js 生成艺术（algorithmic-art）

**适用**：科技/AI 文章封面、抽象背景、视觉冲击

**Skill 路径**：`{skills_root}/algorithmic-art/SKILL.md`

**调用方式**：
1. Agent 创建算法哲学描述
2. 用 p5.js 实现生成艺术（粒子流场、分形、有机形态等）
3. 自包含 HTML，浏览器打开后截图
4. 保存到 `imgs/` 目录

**优势**：每张图独一无二、可通过调整 seed 生成变体

### 方案 E：Canvas/PDF 设计（canvas-design）

**适用**：高品质封面、品牌海报、视觉大片

**Skill 路径**：`{skills_root}/canvas-design/SKILL.md`

**调用方式**：
1. Agent 创建设计哲学
2. 用代码生成 Canvas/PNG/PDF
3. 保存到 `imgs/` 目录

**风格特点**：博物馆级品质、极简/Brutalist/有机/几何

### 方案 F：SVG 矢量插画

**适用**：步骤说明、场景插画、扁平图标

**调用方式**：Agent 直接生成 SVG 代码 → 浏览器渲染 → 可选截图为 PNG

### 方案 G：像素/贴纸（sprite-gen + slack-gif-creator）

**适用**：多图推送、表情贴纸、装饰元素

**Skill 路径**：
- `{skills_root}/sprite-gen/SKILL.md`（像素艺术）
- `{skills_root}/slack-gif-creator/SKILL.md`（GIF 动图）

**调用方式**：
1. 像素风：用 sprite-gen 生成像素 art sprite → PNG
2. 动图：用 slack-gif-creator 的 GIFBuilder 逐帧绘制 → GIF

### 配图策略（按文章类型确定性匹配） ⛔

**禁止随机选择或全部设为可选。** Agent 根据选题内容和 `article_category`（默认 AI工具/科技）自动判断文章类型，按以下策略**锁定**配图方案。

#### 文章类型判断规则

| 文章类型 | 判断依据 | 典型选题 |
|----------|---------|---------|
| **tool_review**（工具推荐/盘点） | 标题含"推荐/盘点/最好用/XX个工具/合集" | "5个AI工具推荐" |
| **tutorial**（教程/实操指南） | 标题含"教程/如何/手把手/入门/实战" | "如何用Claude Code做XX" |
| **hot_news**（热点快讯） | 标题含"发布/上线/开源/重磅/速报"或时效性强 | "GPT-5发布了" |
| **deep_analysis**（深度分析） | 标题含"分析/趋势/未来/深度/解读" | "AI编程的未来" |
| **product_review**（产品测评） | 标题含"测评/体验/试用/对比评测" | "我试用了XX" |

#### 各类型配图方案

| 文章类型 | 封面（确定性） | 章节主配图（确定性） | 辅助/点缀（可选） |
|----------|--------------|-------------------|-----------------|
| tool_review | `openclaw-article-to-image` HTML 信息图 | `beautiful-mermaid` 对比表格 | HTML 信息图卡片 |
| tutorial | `openclaw-article-to-image` HTML 信息图 | `excalidraw-diagram` 手绘步骤图 | Mermaid 流程图 |
| hot_news | `og-image-creator` 社媒卡片 | `openclaw-article-to-image` 信息图排版 | — |
| deep_analysis | `algorithmic-art` p5.js 科技封面 | `beautiful-mermaid` 架构图/思维导图 | — |
| product_review | `canvas-design` 海报 | Agnes API 写实产品图 | HTML 信息图 |

#### 降级链路

```
确定性方案 → 可选辅助方案 → text_poster.py（最后兜底）
```

**text_poster.py 严格限定**：仅当确定性方案 + 可选方案全部失败时才使用。不作为默认方案。

#### Mermaid 标签规范 ⛔

Mermaid 节点标签**必须遵守以下规则**，违反会导致渲染时出现转义符号（如 `<br/>`、`&quot;`）：

- **禁止**使用 `<br/>`、`<b>`、`<i>` 等 HTML 标签
- **禁止**用双引号包裹标签内容（即不用 `A["标签内容"]`，用 `A[标签内容]`）
- 用 `-` 或 `·` 分隔多个信息，保持标签 ≤10 字
- **正确示例**：`A[ChatGPT - 全能助手]`、`B[Notion AI · 知识管理]`
- **错误示例**：`A["ChatGPT<br/>全能写作助手"]`、`B["Notion AI"]`

#### 执行要求

1. **选题阶段确定文章类型** → 锁定配图方案
2. **封面必须生成**：按文章类型选择对应封面方案
3. **章节配图必须生成**：按文章类型选择主配图方案，每个章节至少一张
4. **风格统一**：同一篇文章的章节配图使用同一方案，不混搭超过 2 种风格
5. **告知用户**：

**必须告知用户当前使用的配图方案**：
- `ℹ️ 本次使用 {方案名} 生成配图（风格：{风格描述}）`


## 脚本目录

**Agent 执行**：确定本 SKILL.md 所在目录为 `{baseDir}`。

| 脚本 | 用途 |
|------|------|
| `scripts/image_create.py` | 专用生图 API：读 **`.aws-article/config.yaml`** 的 **`image_model`** + 仓库根 **`aws.env`** 的 **`IMAGE_MODEL_API_KEY`**|
| `scripts/user_image_prepare.py` | 用户供图模式：确保本篇 `imgs/` 存在并生成 `img_analysis.md` 模板（封面仅 1 张） |

## ⛔ 配图前置校验（进入本步骤前必须通过）

**进入配图步骤前**，Agent 必须确认以下条件全部满足：

1. **`article.md` 存在且非空**
2. **`image_source` 不为 `user` 时**，`article.md` 中**必须含有** `![类型：描述](placeholder)` 格式的配图占位标记
3. **占位标记数量**须满足 `image_density`（未配置则默认**每节一图**）
4. **封面占位** `![封面：描述]()` 必须放在文章标题**之前**

**若不满足**：
- **禁止**进入配图步骤
- Agent **回溯 writing 步骤**，按 `image_density` 在 `article.md` 中补齐 `![类型：描述](placeholder)` 占位符
- 补齐后**重新审稿** → **重新排版** → 再进入配图

**为什么需要这个校验**：配图步骤依赖 `article.md` 中的占位标记来确定"在哪里放什么图"。如果写稿时漏掉了占位标记，配图步骤会跳过所有图片位置，导致最终文章没有配图。

## 配置检查 ⛔

任何操作执行前，**必须**按 **[首次引导](../aws-wechat-article-main/references/first-time-setup.md)** 执行其中的 **「检测顺序」**。检测通过后才能进行以下操作（或用户明确书面确认「本次不检查」）：

从选题到发布的**前置规则**见 [aws-wechat-article-main/SKILL.md](../aws-wechat-article-main/SKILL.md)；本 skill 只描述配图步骤。

**图片模型**：**`image_model`**（`provider`、`base_url`、`model`、`default_size`、`default_quality` 等）在 **`config.yaml`**；**`IMAGE_MODEL_API_KEY`** 在 **`aws.env`**。键名对照 **`{baseDir}/../aws-wechat-article-main/references/env.example.yaml`**。

**`base_url` 须为完整端点路径**，脚本根据路径判断调用模式：
- `https://xxx.com/v1/images/generations` — DALL-E / gpt-image 等
- `https://xxx.com/v1/chat/completions` — Gemini 等多模态模型（通过中转站生图）

**交互约定**：可提示用户上述项是否已填；**一条龙**下通常已通过 **`validate_env.py`**。须遵守 main 的**智能体行为约束**——未通过环境校验且未获用户明确「本次例外」时，不得假装已走专用生图 API。

## 封面风格 + 正文配图

- **封面风格**：独立预设体系，见 [references/cover-styles/](references/cover-styles/)。每个预设 `.md` 自包含视觉关键词。
- **正文配图**：Type（画面构成）决定"画什么"，Style（视觉风格）由 Agent 根据 tone/category 内部选择。Type 列表与 prompt 模板见 [references/image-styles/](references/image-styles/) 目录。

### 封面 vs 正文（资源策略）⛔

| 类型 | 要求 |
|------|------|
| **封面** | **必须**通过 **`image_create.py`** 生成（`generate` 或 `batch` 读 `imgs/prompts/*.md`），产出并保存为文章目录下的 **`cover.png`**（或 `cover.jpg` / `cover.jpeg` / `cover.webp`）。**禁止**将 `.aws-article/products/{产品名}/images/`（或其它素材库文件）**直接复制**为 `cover.*` 充当封面。**例外**：用户**明确上传**封面文件并声明「封面只用这一张」时，可跳过脚本，须在 **`img_analysis.md`** 与审稿记录中注明「用户指定封面」。 |
| **正文** | **优先使用业务配图库**：`.aws-article/products/{相关产品}/images/`（先读同名 `.md` 再复制到本篇 `imgs/` 或引用路径），见下文「正文配图来源优先级」。缺图时再走 **`image_create.py`** 或 Agent 降级生图。 |

> 说明：全局 `config.yaml` 的 **`image_source: user`** 表示「正文以用户/素材引用为主」；**不豁免**上述「封面须脚本生成」规则，除非用户同时提供了封面文件并声明仅用该封面。

## 工作流

```
配图进度：
- [ ] 第1步：环境检查 + 本篇约束与文章
- [ ] 第2步：解析配图标记
- [ ] 第3步：确定风格
- [ ] 第4步：生成配图方案
- [ ] 第5步：展示方案并等待确认 ⛔
- [ ] 第6步：生成图片（**脚本失败时**见同节「调用失败」分支，勿静默吞掉报错）
- [ ] 第7步：插入文章
```

### 正文配图来源优先级（Agent）⛔

**仅适用于正文插图**（不含封面；封面见上文「封面 vs 正文」）。**在**为正文 `placeholder` 调用 `image_create.py`、写入 `imgs/prompts/` **之前**，须先判断是否可用**本地业务配图库**，避免**业务相关文章**（教程 / 产品介绍 / 案例 / 自家界面截图）「有现成业务配图却重新生成」：

1. **仓库业务配图库**：若本篇涉及用户业务，先 `ls .aws-article/products/`，进入相关产品的 **`images/`** 子目录，列出并阅读 **同名 `.md`**（含路径与画面说明），按主题匹配后，在 `article.md` 中直接引用对应 **`.png` / `.webp`**（或复制到本篇 `imgs/` 再引用）。**与正文严格相关才用**，避免硬凑。
2. **用户上传 / 本篇 `image_source: user`**：用户提供的图或上述引用策略，走「用户供图模式」与 `img_analysis.md`（正文部分）。
3. **仍缺图或须原创插画**：再进入 **Type × Style**、`imgs/prompts/` 与 **`image_create.py`**（或 Agent 降级生图）。

> 说明：业务配图库属「仓库内业务资源」，**不必**等用户手动上传才查；与「用户供图模式」并列，而非仅附属于后者。

### 第1步：环境检查 + 本篇约束与文章

- **全局**：读 **`.aws-article/config.yaml`** — `cover_aspect`、`cover_style`、`image_density`、`caption_style`、`multi_image_count`、`tone` 等以之为准（完整字段见 [articlescreening-schema.md](../aws-wechat-article-main/references/articlescreening-schema.md) 与 **`config.example.yaml`**）。
- **本篇**：若同目录有 **`article.yaml`**，读取 **`default_cover_image_style`**、**`default_article_image_style`**（应为单元素列表，代表本篇已选预设）及 `cover_image` 等字段。
- 读取 **`article.md`**（或当前流程规定的正文来源）。
- 当 `image_source: user`（全局或本篇）时，进入「用户供图模式」：先创建本篇 `imgs/` 并生成/更新 `img_analysis.md`，记录每张图的内容分析、建议章节与推荐用途。

### 第2步：解析配图标记

提取所有 `![类型：描述](placeholder)`。`实证` 类型提示用户提供素材或从 `.aws-article/products/{相关产品}/images/` 搜索（业务配图库）。

### 用户供图模式（新增分支）

当用户上传图片并指定主题时，按以下顺序执行：

1. 立即确保 `{article_dir}/imgs/` 存在，并将用户图片放入该目录。
2. 生成/维护 `{article_dir}/img_analysis.md`（每图至少包含：文件名、图片内容、建议章节、推荐用途、图注建议）。
3. **硬性约束**：`img_analysis.md` 中“推荐用途：封面”**必须且只能出现 1 次**；其余图片用途应为“正文”。
4. 同步更新本篇 `article.yaml`：`image_source: user`（从模型生图切换到用户供图状态）。
   - 字段取值只允许 `generated` / `user`。
5. 写稿阶段直接使用用户图片路径（如 `imgs/淘米.png`），**不再使用 placeholder**。

**顺序说明**：`imgs/` 落图 → 分析并写好 `img_analysis.md` → 再跑 `write.py`；写稿时以 `img_analysis.md` 为准，把图片插到与内容匹配的章节位置。

### 发布后换图重发（新增分支）

当用户明确说「这篇文章配图不满意，换成我上传的新图并重新发草稿箱」时，按以下流程：

1. 用户指定目标文章目录（`drafts/YYYYMMDD-slug/`）。
2. 将新图放入该目录 `imgs/`，并更新 `img_analysis.md`（仍需满足“封面仅 1 张”）。
   - 同步把本篇 `article.yaml.image_source` 更新为 `user`。
3. 按 `img_analysis.md` 重新映射图片到 `article.md` 对应章节（允许重排章节以匹配图序）。
4. 运行 `format.py` 重新生成 `article.html`（不要只改旧 html 局部）。
5. 进入终审：确认 `article.md` / `article.html` 无 `placeholder`，且引用图片文件均存在。
6. 回到发布步骤执行 `publish.py full`（`publish_method: draft` 时写入草稿箱）。

**可用素材库**（与上文「配图来源优先级」一致）：

- `.aws-article/products/{产品名}/images/`：业务配图库（产品截图、品牌素材等）；本篇涉及用户业务时**优先读同名 `.md` 再选图**。若已用业务配图满足正文，可不再走生图 API。

### 第3步：确定风格

封面与正文配图**分别**确定风格，走各自的预设目录。

#### 封面风格

**预设发现**：Agent 扫描两个目录合并可用封面预设列表：
1. **内置**：`{baseDir}/references/cover-styles/`（随 skill 安装）
2. **用户自定义**：`.aws-article/presets/cover-styles/`（用户创建或预设包导入）

**加载优先级**：
1. 用户当次指定（如「封面要简约风」）
2. **本篇 `article.yaml.default_cover_image_style`**（单元素列表）→ 从内置或 **`.aws-article/presets/cover-styles/<名>.md`** 加载（用户文件同名优先于内置）
3. **fallback**：根据 `tone` / `article_category` 从可用封面预设中自动推荐（规则见 [auto-selection.md](references/image-styles/auto-selection.md)）

每个封面预设 `.md` 自包含视觉关键词（`Prompt 要点`），无须引用外部 Style 维度。Schema 见 [cover-styles/README.md](references/cover-styles/README.md)。

#### 正文配图风格

**预设发现**：Agent 扫描 `.aws-article/presets/image-styles/` 获取可用正文配图预设。

**加载优先级**：
1. 用户当次指定（如「正文要扁平插画」）
2. **本篇 `article.yaml.default_article_image_style`**（单元素列表）→ 加载 **`.aws-article/presets/image-styles/<名>.md`**
3. **fallback**：根据正文内容信号与 `tone` 自动推荐 Type 和视觉风格（规则见 [auto-selection.md](references/image-styles/auto-selection.md)），视觉风格为 Agent 内部决策

### 第4步：生成配图方案

为每张图生成方案（类型、风格、prompt 要点）。

**封面 prompt frontmatter 必须包含 `aspect`**：从 `config.yaml` 的 `cover_aspect` 读取（如 `2.35:1`），写入 YAML frontmatter。`image_create.py` 据此转换为实际像素尺寸；**缺少 aspect 会导致 fallback 到 1:1**。

**图片内文字**：画面中出现的文字必须为中文。在 prompt 里**直接写出要显示的中文文案**（如「传统对话AI」「OpenClaw」），禁止只写 “labels in Chinese” 或 “Chinese or English OK”，否则模型会生成英文。

Prompt 构建：[references/image-styles/prompt-construction.md](references/image-styles/prompt-construction.md)

### 第5步：展示方案并等待确认 ⛔

### 第6步：生成图片

**封面**：见「封面 vs 正文」— **默认必须先**写好 **`imgs/prompts/`** 中封面 prompt（含 `aspect` 与 `config.yaml` 的 **`cover_aspect`** 一致），再执行 **`image_create.py generate … -o ../cover.png`**（或等价输出路径）。

**生成方式（优先级，正文）**：

0. **已在「正文配图来源优先级」中用尽素材库 / 用户图**：本节不再对**该图位**重复生图（封面仍须单独按上款处理）。
1. **缺图时优先：调用专用生图 API**（`scripts/image_create.py`）— 依赖 **`config.yaml` 的 `image_model` + `aws.env` 的 `IMAGE_MODEL_API_KEY`**
2. **自动降级：模型未配置**（退出码 2、stderr 含 `[NO_MODEL]`）且当前 Agent 支持图片生成、并已获用户明确同意代生图 → Agent 读取 `imgs/prompts/*.md` 中的 prompt + frontmatter（size/quality），用自身多模态能力按**相同 prompt** 生图 → 告知用户 `ℹ️ 图片模型未配置，本次由当前对话模型直接生图（使用相同配图方案）` → 生成后**正常执行第 7 步**（插入文章）
3. **故障降级**（退出码 1）→ 按本节下方「调用失败」表格分类处理
4. **用户供图：跳过生图** — 当 `image_source=user` 或用户明确”使用我上传的图片”时，不调用 `image_create.py`，改为”读图分析 + 写稿引用 + 重排版”

**必须告知用户当前使用的方式**：

- 已配置且调用脚本 → `ℹ️ 使用 image_create.py 调用专用生图模型（{model}）`
- Agent 降级生图（退出码 2）→ `ℹ️ 图片模型未配置，本次由当前对话模型直接生图（使用相同配图方案）`
- 故障降级 / 仅 prompts → `ℹ️ 本次未走 image_create.py（原因：…）`

**⛔ 故障降级（退出码 1）时的终点**：只做到第 4 步（或第 5 步）。产出 `imgs/prompts/*.md` 与方案；**不执行**「替换 article 中的 placeholder」或「修复 HTML」。若 `imgs/README.md` 尚不存在或需补充当前方案的说明，可创建/更新（如何配置 **`aws.env` / `config.yaml`**、如何跑 `image_create.py batch`、如何在 `article.html` 中替换）；若已存在且已涵盖当前方案，**不必重写**。

**注意**：退出码 2（模型未配置）且 Agent 支持图片生成、并已获用户明确同意代生图时，**不受上述终点限制**——Agent 降级生图后继续执行第 7 步。

**调用专用 API 时**（在**仓库根**执行，`{baseDir}` 按上表解析；路径按本篇 `imgs/` 调整）：

```bash
python {baseDir}/scripts/image_create.py batch drafts/YYYYMMDD-slug/imgs/prompts/ -o drafts/YYYYMMDD-slug/imgs/
```

单张：`python {baseDir}/scripts/image_create.py generate imgs/prompts/01-cover.md -o imgs/01-cover.png`

连通性自检：`python {baseDir}/scripts/image_create.py test`

图片规格：[references/specs.md](references/specs.md)

#### `image_create.py` 调用失败时（智能体必选分支）

只要执行了 `image_create.py` 且**非零退出或 stderr 有 API/网络错误**，就必须走本节，**不得**只说「生图失败」而不分类、不摘要报错。

运行脚本后**须把终端 stderr 中的具体报错摘要给用户**（含 `❌`、HTTP 状态码、`【配置/认证】`、`网络错误（可重试）`、`[NO_MODEL]` 等关键行），勿只说「失败」。

| 类型 | 判断线索 | 智能体动作 |
|------|----------|------------|
| **未配置** | 退出码 2、`[NO_MODEL]` | Agent 支持图片生成且用户明确同意代生图 → 读取 `imgs/prompts/*.md` 中的 prompt + frontmatter（size/quality），用自身多模态能力按相同 prompt 生图并继续第 7 步。Agent 不支持图片生成，或 Agent 代生图失败 → 明确告知“我当前不能完成生图”，给用户二选一：**配置图片模型后重试**，或**本篇不配图继续**（保留 prompts 并在结果中标注无配图）。 |
| **网络类** | `URLError`、`网络错误（可重试）`、超时、临时 502/503 | **必须自动再试 1 次**（可短暂等待后重跑同一命令）。**第二次仍为网络类** → 可降级为 **Agent 多模态生图** 或仅保留 prompts；**须明确告知**用户本次未走专用 API。 |
| **配置/凭证类** | 401/403、图片模型配置不完整、`【配置/认证】` | **不要**静默降级。**列出须检查项**（**`config.yaml` 的 `image_model`**、**`aws.env` 的 `IMAGE_MODEL_API_KEY`**、端点、权限），请用户改正后重跑。用户**明确打字**接受本次仅用 Agent/仅 prompts 时，再按 main「本次例外」处理。 |
| **业务/参数类** | `【请求参数】`、400、返回体提示 model/size 不支持 | 将响应摘要给用户；可改 **`config.yaml` 或 env** 中的 model/尺寸后再试；仍失败则与用户商定是否 Agent 生图。 |

**禁止**：配置明显错误时静默改用 Agent 却不说明；网络降级后不告知「本次未走专用生图」。

#### 文本海报自动降级（所有生图方案均失败时）

当以下条件**全部满足**时，Agent **必须**自动启动文本海报降级：

1. image_create.py 调用失败（退出码 1 或 2）
2. Agent 多模态生图不可用或用户未同意
3. 零 API Key 方案（Mermaid / Excalidraw / HTML 信息图等）也不可用或全部失败

**降级流程**：

`ash
# 为整篇文章自动生成封面 + 章节配图（仓库根执行）
python {baseDir}/scripts/text_poster.py article --dir drafts/YYYYMMDD-slug/ --theme tech-blue

# 单独生成封面海报
python {baseDir}/scripts/text_poster.py generate --title "文章标题" --subtitle "副标题" -o imgs/cover.png

# 单独生成章节配图
python {baseDir}/scripts/text_poster.py section --title "章节标题" --icon "💡" -o imgs/section-01.png
`

**可用主题**：	ech-blue（科技蓝）/ warm-orange（暖橙）/ green-forest（森林绿）/ purple-dream（梦幻紫）/ minimal-light（极简白）/ dark-red（暗红）

**执行规则**：
- Agent 根据文章调性自动选择最匹配的主题
- 封面海报包含文章标题、副标题（可选）、品牌名（默认取 config.yaml 的 default_author）
- 章节配图从 rticle.md 的二级标题自动提取，每节一张
- 截图优先用 Chrome headless；不可用时降级为保存 HTML 文件
- 生成后**必须告知用户**：ℹ️ 所有生图方案均失败，已使用文本海报降级方案（{theme} 主题），生成了 {N} 张配图
- 文本海报**不受「故障降级终点」限制**——生成后继续执行第 7 步（插入文章）

### 第7步：插入文章

仅当**已生成图片**时执行：替换 placeholder 为实际图片路径，输出到 `imgs/`。

**封面排除**：封面图（`![封面：...]`）**仅用于微信文章封面上传**，**禁止**作为 `<img>` 嵌入 HTML 正文。替换 placeholder 时**跳过封面标记行**（或直接删除该行），封面图单独复制到文章根目录 `cover.{ext}`。`publish.py` 也支持从 `imgs/` 目录自动发现封面图（`cover.*` 或 `*-cover.*`）。

**修复 HTML 的触发条件**：仅当在 `article.html` 中**确实存在** `href="placeholder"` 或 placeholder 被渲染成可点击链接时，才将误转的 `<a>` 改为 `<img>` 或占位说明；**不要**默认每次都执行「修复流程图占位」或「修复 HTML」。

## 过程文件

| 读取 | 产出 |
|------|------|
| **`article.md`**、**`.aws-article/config.yaml`**、本篇可选 **`article.yaml`** 中的标记与配图约束 | `imgs/`（outline + prompts + 图片；未走 API 时为 prompts + 可选 imgs/README.md） |
