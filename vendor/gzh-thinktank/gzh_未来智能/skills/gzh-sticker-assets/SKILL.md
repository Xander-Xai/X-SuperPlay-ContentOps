---
name: gzh-sticker-assets
description: 公众号贴图｜九宫格｜多图推送｜图片消息｜表情包 — 贴图与多图推送：从创意构思、AI 生图到公众号图片消息发布全流程，含九宫格自动排布、多图压缩、组图打包。面向公众号运营、自媒体、IP 账号。触发词：「贴图」「多图推送」「发组图」「图片消息」「九宫格」「做一组图」「图片帖子」「发几张图」「不写正文发图」「只发图不写字」。是文章内配图/封面请走 gzh-visual-assets；需要多环节串联（写+审+排+配图+发）请走 gzh-article-orchestrator。
homepage: https://localhost
metadata:
  openclaw:
    requires:
      env:
        - AGNES_API_KEY
        - WECHAT_1_APPID
        - WECHAT_1_APPSECRET
      bins:
        - python3
    primaryEnv: aws.env
---

# 贴图 / 多图推送

**贴图 / 多图推送一条龙** —— 构思→生图→图片消息群发，九宫格自动排布、多图打包。

> **本地矩阵说明** · 本 skill 是公众号图片消息与九宫格的独立分支；长文图文仍须回到主工作流，避免把贴图流程混入文章门禁。

## 能力披露（Capabilities）

本 skill 编排贴图与多图推送，调用同套件的 `image_create.py`（images）生图；可选调用 `publish.py` 发布。**会把图片 prompt 发给外部图像 API；若走发布路径，会把图片作为 POST body 上传到微信 API。** 具体行为：

- **凭证读取**：仓库外环境文件的 `AGNES_API_KEY`；走发布时额外读取 `WECHAT_{N}_APPID` / `WECHAT_{N}_APPSECRET`
- **凭证外发**：`AGNES_API_KEY` 以 `Authorization: Bearer` 头发送到固定 Agnes 端点；`WECHAT_{N}_APPID/APPSECRET` 用于换 `access_token` 后调用微信 API
- **内容外发**：图片 prompt 发给图像 API；图片文件（PNG/WEBP）发给微信 `material/add_material` / `draft/add`
- **文件读**：仓库内 `.aws-article/config.yaml`、本篇 `article.yaml`、`imgs/prompts/*.md`
- **文件写**：本篇 `imgs/*.{png,webp}`、`imgs/outline.md`、`article.yaml` 状态字段
- **shell**：`python3 {baseDir}/../gzh-visual-assets/scripts/image_create.py`；可选 `python3 {baseDir}/../gzh-draft-publisher/scripts/publish.py`

## 配套 skill（informational）

本 skill 属 `公众号内容技能套件` 一条龙公众号套件的**贴图/多图推送专用分支**（入口 `gzh-article-orchestrator`）。工作流中的生图步骤与发布步骤依赖同套件其他 slug 提供的能力。

- **至少需要同时安装** `gzh-visual-assets`（用于生图）；若要走发布链路，建议再装 `gzh-draft-publisher`。
- **套件完整装齐到同一 `skills/` 根目录**时，跨 skill 引用都能读到。
- **单独安装本 skill** 时，生图/发布相关步骤会在执行阶段遇到缺失文件；本 skill 内的选题规划、图序、风格约定等本地步骤仍可用。

完整能力清单与本地路径见仓库根目录 `skills/skill-registry.yaml`。

## 路由

长文图文（标题+正文+插图+后台发文）→ [gzh-article-orchestrator](../gzh-article-orchestrator/SKILL.md)；长文内单篇插图 → [gzh-visual-assets](../gzh-visual-assets/SKILL.md)。

创作以图片为主的公众号内容：多张图片 + 每张配文，统一风格。

## 产出目标（先看这个）

- 输入：主题 / 选题卡 / 用户素材图（任选其一）
- 输出：`imgs/`（outline + prompts + 图片）与可发布的多图内容
- 风格：整组统一（避免每张图风格漂移）

## 配置检查 ⛔

任何操作执行前，**必须**按 **[首次引导](../gzh-article-orchestrator/references/first-time-setup.md)** 执行其中的 **「检测顺序」**。检测通过后才能进行以下操作（或用户明确书面确认「本次不检查」）：

从选题到发布的**前置规则**见 [gzh-article-orchestrator/SKILL.md](../gzh-article-orchestrator/SKILL.md)；本 skill 描述贴图子流程。

**图片模型**：**`image_model`** 固定为 Agnes Image 2.1 Flash；**`AGNES_API_KEY`** 在仓库外环境文件。键名对照 **`{baseDir}/../gzh-article-orchestrator/references/env.example.yaml`**（与 **`image_create.py`** 一致）。

**交互约定**：须遵守 main 的**智能体行为约束**——未通过环境校验且未获用户明确「本次例外」时，不得假装已走专用生图 API。

## 脚本目录

**Agent 执行**：确定本 SKILL.md 所在目录为 `{baseDir}`。

| 脚本 | 路径（相对仓库 `skills/`） | 用途 |
|------|---------------------------|------|
| `image_create.py` | `gzh-visual-assets/scripts/image_create.py` | Agnes Image 2.1 Flash：读取 **`.aws-article/config.yaml`** 的 `image_model` + 仓库外环境的 `AGNES_API_KEY` |
| `publish.py` | `{baseDir}/../gzh-draft-publisher/scripts/publish.py` | 发布（与 [publish skill](../gzh-draft-publisher/SKILL.md) 一致） |

## 工作流

```
贴图进度：
- [ ] 第1步：环境检查 + 本篇约束（合并 YAML）
- [ ] 第2步：确定选题
- [ ] 第3步：确定风格
- [ ] 第4步：规划图序
- [ ] 第5步：展示方案并等待确认 ⛔
- [ ] 第6步：生成图片（**脚本失败时**见同节「调用失败」分支）
- [ ] 第7步：审稿
- [ ] 第8步：发布
```

### 第1步：环境检查 + 本篇约束（合并 YAML）

若本篇在外部 **`active/THK-…/`** 下：按 **`.aws-article/config.yaml` → 本篇 `article.yaml`** 合并读取约束（同键本篇优先，最后层覆盖），重点字段：`multi_image_count`、`tone`、`target_reader`、`custom_sticker_style` > `default_sticker_style`（**须为 YAML 字符串列表**；`custom_*` 非空时优先于 `default_*`；多候选时智能体择一并写回本篇为**单元素列表**）。若无有效 YAML，以用户口述主题 + skill 默认值作为约束。

### 第2步：确定选题

topics 产出的贴图卡片 / 用户直接给主题 / 用户提供素材图片。

### 第3步：确定风格

**贴图风格加载优先级**：
1. 用户指定（「用知识卡片风格」）
2. 本篇合并配置中的 `custom_sticker_style` > `default_sticker_style`（若有；`custom_*` 优先；列表多元素时须先择一）
3. `.aws-article/presets/sticker-styles/` 下的自定义风格
4. **fallback**：根据贴图主题自动选择 Type（氛围 or 信息图）× 默认 Style（扁平矢量），使用共享 [image-styles/](../gzh-visual-assets/references/image-styles/)

全组图统一风格。

### 第4步：规划图序

产出 `imgs/outline.md`：每张图的用途、文案要点、文件名。详见：[references/workflow.md](references/workflow.md)

### 第5步：展示方案并等待确认 ⛔

### 第6步：生成图片

**生成方式（优先级）**：

1. **优先**：调用 **`image_create.py`** — 依赖固定 Agnes **`image_model`** + 仓库外环境的 **`AGNES_API_KEY`**
2. **降级**：当前 Agent 多模态 / 仅出 prompts — 仅当环境未就绪、用户接受 main「本次例外」、或**已按本节下方「调用失败」表格处理**（网络重试后仍失败等）时

**必须告知用户当前使用的方式**：

- 已配置且调用脚本 → `ℹ️ 使用 image_create.py 调用专用生图模型（{model}）`
- Agent 生图 / 仅 prompts → `ℹ️ 本次未走 image_create.py（原因：…）`

**调用专用 API 时**（在**仓库根**执行，路径按本篇 `imgs/` 调整）：

```bash
python {baseDir}/../gzh-visual-assets/scripts/image_create.py batch <外部active/THK-...>/imgs/prompts/ -o <外部active/THK-...>/imgs/
```

单张：`python {baseDir}/../gzh-visual-assets/scripts/image_create.py generate imgs/prompts/01.md -o imgs/01.png`

连通性自检：`python {baseDir}/../gzh-visual-assets/scripts/image_create.py test`

图片内文字与 prompt 构建规则与长文配图一致，见 [gzh-visual-assets/SKILL.md](../gzh-visual-assets/SKILL.md) 与 [prompt-construction.md](../gzh-visual-assets/references/image-styles/prompt-construction.md)。

#### `image_create.py` 调用失败时（智能体必选分支）

沿用配图 skill 的同一规则：必须摘要 stderr 关键行，按 **网络 / 配置·凭证 / 业务·参数** 分类处理；**禁止**配置错误时静默降级。细则参照 [gzh-visual-assets/SKILL.md](../gzh-visual-assets/SKILL.md) 第 6 步「调用失败」表格。

### 第7步：审稿

贴图专用清单：[references/checklist.md](references/checklist.md)

### 第8步：发布

```bash
python {baseDir}/../gzh-draft-publisher/scripts/publish.py full article/
```

## 过程文件

| 读取 | 产出 |
|------|------|
| `topic-card.md`（可选）、**`.aws-article/config.yaml` + 本篇 `article.yaml`** | `imgs/`（outline + prompts + 图片） |
