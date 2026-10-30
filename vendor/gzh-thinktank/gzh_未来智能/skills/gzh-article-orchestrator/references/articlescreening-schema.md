# 配置字段说明（`config.yaml` + `article.yaml`）

**账号与流程级** → **`.aws-article/config.yaml`**；**本篇发文与发布状态** → **`article.yaml`**；**密钥** → 仓库外层项目目录 **`aws.env`**。

路径与模板：

| 用途 | 路径 | 模板 / 示例 |
|------|------|-------------|
| 账号、文风、模型 endpoint、微信元数据、发布方式等 | **`.aws-article/config.yaml`** | **`config.example.yaml`**（同目录） |
| 本篇标题、摘要、封面、**发布是否完成**等 | **`<GZH_ARTIFACT_ROOT>/active/THK-YYYYMMDD-NNN-slug/article.yaml`** | **`matrix_init.py` 分配工作区；`article_init.py` 仅补全元数据** |
| API Key、微信 AppID/AppSecret | **`aws.env`**（仓库外层项目目录） | **`env.example.yaml`**（同目录） |

全局校验与首次引导：[first-time-setup.md](first-time-setup.md)；总览流程：[SKILL.md](../SKILL.md)。

**优先级**：用户当次说法 > 本篇 **`article.yaml`**（仅本篇字段）> **`.aws-article/config.yaml`**（`custom_*` 覆盖 `default_*`）> 各 skill 内置默认。

---

## `.aws-article/config.yaml` 字段（按模板分组）

**完整字段与分组**以仓库内 **`config.example.yaml`**（同目录）为准（含逐行注释）。本文不重复粘贴整段 YAML，避免与模板更新分叉。可按项目在该示例基础上增删键；未出现的键由各子 skill 使用内置默认。

**说明**：**`publish_completed`** 请放在本篇 **`article.yaml`**（见下节），勿写在全局 **`config.yaml`**；若旧稿或历史模板仍把「是否发完」放在 config 里，以 **`article.yaml`** 为准并逐步从 config 中清理。

**配图风格**：**封面**预设目录为 **`cover-styles/`**（内置随 `gzh-visual-assets` + **`.aws-article/presets/cover-styles/`**）；**正文配图**为 **`presets/image-styles/`** 下同名 `.md`。配置键：**`default_cover_image_style`** / **`default_article_image_style`**（账号默认候选）与 **`custom_cover_image_style`** / **`custom_article_image_style`**（覆盖层）；**`custom_*` 非空时优先于同名 `default_*`**。

**预设候选列表**：**`default_structure`**、**`default_closing_block`**、**`default_title_style`**、**`default_format_preset`**、**`default_cover_image_style`**、**`default_article_image_style`**（及 **`default_sticker_style`**）**须为 YAML 字符串列表**：`[]`、单元素 `[名]`，或多项候选；**多项时**智能体须在本篇 **`article.yaml`** 同键改为**单元素列表**后，再运行 **`write.py`**（结构/文末）与 **`format.py`**（排版主题）。**勿使用字符串标量。** 配图风格字段（`custom_cover_image_style`、`custom_article_image_style` 及对应的 `default_*`）同理。

**`custom_*` 覆盖层**：`default_structure`、`default_closing_block` 等字段均有对应的 `custom_*`（如 `custom_structure`、`custom_format_preset` 等），格式相同。当 `custom_*` 非空时，优先于同名 `default_*`。合并优先级：**`article.yaml` > `custom_*` > `default_*`**；配图风格在解析完上述合并后的列表后，再按 skill 规则从内置与用户 **`cover-styles` / `image-styles`** 目录加载预设文件。

---

## 本篇 `article.yaml` 字段

路径：`<GZH_ARTIFACT_ROOT>/active/THK-YYYYMMDD-NNN-slug/article.yaml`。初始化工作区后可用 **`skills/gzh-draft-publisher/scripts/article_init.py`** 补全元数据。

| 键 | 说明 |
|----|------|
| `title` | 文章标题 |
| `author` | 作者；可空时部分流程会回退 **`config.yaml`** 的 **`default_author`** |
| `digest` | 摘要（微信 digest 上限 128 字） |
| `cover_image` | 封面路径或 URL（强烈建议） |
| `content_source` | 正文 HTML 来源，默认 **`article.html`** |
| `need_open_comment` | 是否开启留言（与微信能力一致） |
| `only_fans_can_comment` | 是否仅粉丝可留言 |
| **`publish_completed`** | **`false`** / **`true`**。新建本篇为 **`false`**；**发布闭环结束后**由智能体改为 **`true`**。**`publish.py` 不读写此键**；用于对话分流与运营备忘。 |
| **`default_structure`** / **`custom_structure`** 等全局同名预设键 | 可选。与 **`config.yaml`** 合并时**本篇覆盖**（`custom_*` 优先于 `default_*`）；若全局某键为**多元素候选列表**，须在本篇写入**单元素列表** `[名]`，再运行 **`write.py`** / **`format.py`**。 |
| **`topic_domain`** | 可选，视觉合同领域开关（默认 **`generic`**）。取值：**`generic`** = 领域无关合同，`claim_ids` 置空、`viewer_job` 由标题/正文派生，适合大多数 AI 应用/科普文；**`transformer`** = 保留 Transformer 注意力机制专属精细模板，仅当本篇是「注意力机制/Transformer 架构深度拆解」类强 Transformer 选题时显式设置。被 `scripts/visual_qa.py` 的 `_visual_contract_for` 读取，缺省回退 `.aws-article/config.yaml` 的 `topic_domain`，最终回退 **`generic`**，不会继承历史主题。 |

---

## `aws.env`（仓库外层项目目录）

与 **`validate_env.py`**、**`publish.py`** 共用。键名见 **`env.example.yaml`**（同目录）。

| 用途 | 典型键 |
|------|--------|
| 图片模型 | `AGNES_API_KEY`（仅 Agnes Image 2.1 Flash） |
| 微信 | `NUMBER_ACCOUNTS`（与 `publish.py` 一致）、`WECHAT_{i}_NAME`、`WECHAT_{i}_APPID`、`WECHAT_{i}_APPSECRET`、可选 `WECHAT_{i}_API_BASE` |

**`validate_env.py`**（环境检测）：写作、图片、微信**三组**未配齐任一组即 **`failed`**、退出码 1；**`publish_method: none`** 时跳过微信组。详见脚本 docstring。

---

## 发布相关（`publish_method`、`publish_completed`、槽位）

| 键 | 所在文件 | 说明 |
|----|-----------|------|
| **`publish_method`** | **`config.yaml`** | **`draft`**（默认）：**`full`** 仅写入**公众号草稿箱**。**`published`**：仍先创建草稿，完成回读和外部 `external_publish` 审批后，才可单独提交公开发布。**`none`**：用户明确不填微信时写入；**`full`** 不调接口、直接跳过。 **`full --publish`** 只兼容旧参数，创建草稿后安全阻断。 |
| **`publish_completed`** | **`article.yaml`** | 新建 **`false`**；发布真正结束后由智能体写 **`true`**。 |
| **`wechat_publish_slot`** | **`config.yaml`**（可选） | 多账号时指定本篇默认槽位 **1..N**；与 **`publish.py --account`** 二选一，**命令行优先**。 |
| 微信凭证 | **`aws.env`** | **`WECHAT_{i}_APPID`** / **`WECHAT_{i}_APPSECRET`** 等；**`validate_env.py`** 默认要求配齐，除非 **`publish_method: none`**。 |
