---
name: gzh-draft-publisher
description: 公众号发布｜公众号草稿箱｜公众号群发｜图文推送｜微信 API｜wechat automation｜WeChat API automation｜auto publish｜scheduled publish — 公众号 API 发布工具，图文入草稿箱或直接群发，支持封面素材上传、发布前检查与 draft/published 模式切换。面向公众号运营、自动化内容团队、开发者。触发词：「发布」「提交」「群发」「推送」「发出去」「上传到公众号」「发到公众号」「可以发了吗」「发布前检查」。需要多环节串联（写+审+排+配图+发）请走 gzh-article-orchestrator。
homepage: https://localhost
metadata:
  openclaw:
    requires:
      env:
        - WECHAT_1_APPID
        - WECHAT_1_APPSECRET
      bins:
        - python3
    primaryEnv: aws.env
---

# 发布

**公众号 API 直连发布** —— 图文入草稿箱或直接群发，素材上传、发布前检查一站式完成。

> **独立工作流说明** · 本 skill 是当前工作流的草稿箱环节；发布器只接受完成固定路由、停在 `final_reviewed` 的公众号文章目录。
>
> **当前账号合同** · 本仓库只有 `account_id: thinktank`（X超玩•未来智能）一个账号，固定使用微信公众号第 1 槽位。发布本工作流文章时不得询问或切换账号，不得使用 `--account 2` 或其他槽位覆盖；以 `workflow-identity.yaml` 为唯一事实源。

## 能力披露（Capabilities）

本 skill 调 `publish.py` **直连微信公众号官方 API** 发布图文。**会把本篇 `article.html` 与 `imgs/*` 文件作为 POST body 上传到微信服务器。** 具体行为：

- **凭证读取**：本工作流固定读取 `aws.env` 的 `WECHAT_1_APPID` / `WECHAT_1_APPSECRET`
- **凭证外发**：`APPID` / `APPSECRET` 以 query string 形式发给 `api.weixin.qq.com/cgi-bin/token` 换 `access_token`；后续请求带 `access_token` query string。微信返回的 `access_token` 在进程内存短期缓存，**不落盘**
- **内容外发**：本篇封面、正文插图以 multipart upload 发给 `material/add_material`；`article.html` 正文与标题/摘要以 JSON POST 发给 `draft/add`、`freepublish/submit`
- **网络目标**：默认 `api.weixin.qq.com`；用户可在 `WECHAT_{N}_API_BASE` / `config.yaml.wechat_api_base` 自配反代
- **文件读**：仓库内 `.aws-article/config.yaml`、仓库外层项目目录的 `aws.env`、本篇 `article.yaml`、`article.html`、`imgs/*`
- **文件写**：仅本篇 `article.yaml` 的状态字段（`media_id`、`publish_id`、`publish_completed`）
- **shell**：仅 `python3 {baseDir}/scripts/publish.py`、`getdraft.py`、`article_init.py`

**建议**：首次运行用 `publish_method: draft` 只入草稿箱确认效果，再切 `published` 真正群发。

## 配套 skill（informational）

本 skill 是 `公众号内容技能套件` 一条龙公众号套件的**发布环节**（入口 `gzh-article-orchestrator`）。工作流中的若干步骤会读取同级 `../gzh-article-orchestrator/references/*.md` 等共享文档（首次引导、articlescreening schema、env/config 示例等）。

- **套件完整装齐到同一 `skills/` 根目录**时，跨 skill 引用都能读到。
- **单独安装本 skill** 时，跨 skill 引用的步骤会在读取阶段遇到 `file not found`；但 `publish.py`、`getdraft.py`、`article_init.py` 这几个脚本本身可独立运行（只要 `aws.env` 与 `.aws-article/config.yaml` 就绪）。

完整能力清单与本地路径见仓库根目录 `skills/skill-registry.yaml`。

通过微信公众号 API 将排版稿写入**草稿箱**或再**提交发布**（由 **`config.yaml`** 的 **`publish_method`** 与命令行 **`--publish`** 控制）。

仓库级发布门禁：在指定文章目录执行
`python scripts/workflow_gate.py --article <目录> --stage final_reviewed --all`，只有输出
`GATE CHECKED` 且全部阶段 `[PASS]` 后，才允许调用本 Skill 的 `full`。`full` 会在上传前再次复核该门禁；草稿回读成功后，才推进最后的 `draft_submitted` 门禁。门禁失败时不得用 `--publish` 或手工回写状态绕过。

若当前配置为 `publish_method: draft`，已经处于 `draft_submitted` 的文章允许再次执行 `full` 生成新的草稿副本；仍必须重新运行预检、`final_reviewed` 全链路检查和草稿回读，不能借此公开发布。

在调用微信 API 前，还必须先生成并通过发布预检：
`python scripts/publish_preflight.py --article <目录> --env <仓库外凭证> --approve --draft-permission-confirmed --ip-whitelist-confirmed`。
预检只记录凭证变量名、草稿权限和 IP 白名单确认，不保存或打印密钥。

## 配置检查 ⛔

任何操作执行前，**必须**按 **[首次引导](../gzh-article-orchestrator/references/first-time-setup.md)** 执行其中的 **「检测顺序」**。检测通过后才能进行以下操作（或用户明确书面确认「本次不检查」）：

## 脚本目录

**Agent 执行**：确定本 SKILL.md 所在目录为 `{baseDir}`。发布子命令在 **`{baseDir}/scripts/publish.py`**（项目根执行）。

| 脚本 / 子命令 | 用途 |
|--------|------|
| **`article_init.py`** | 初始化或更新本篇 **`article.yaml`**（及可选 **`closing.md`**）。用于总览 **本篇准备**（建目录后）或 **发布前** 补全元数据。仓库根执行：`python {baseDir}/scripts/article_init.py <文章目录> [--title … --author … --digest …]` |
| **`getdraft.py`** | 独立于 `publish.py`：用于正式文章查询（`published-list` / `published-fields` / `publish-get` / `article-get`，对应 `freepublish/*`），可用于 `embeds.related_articles.manual` 为空时自动补全推荐链接。注意：`freepublish/*` 需要公众号具备对应接口权限。仓库根：`python {baseDir}/scripts/getdraft.py published-fields` |
| `check-screening` | 校验 **`config.yaml`** 的 **`publish_method`**（**`draft`** / **`published`** / **`none`**） |
| `check-wechat-env` | 按 **`config.yaml` 槽位**检查 `aws.env` 的 `WECHAT_N_APPID` / `WECHAT_N_APPSECRET` 是否已填（**调用 `publish.py` 前建议跑**） |
| `check` | 环境检查：`aws.env`、目标槽位、依赖、可选探测 token；传 `--account` 时只检查目标槽位 |
| `accounts` | 列出 **`config.yaml`** 中各微信槽位名称，并标记 `aws.env` 凭证缺项 |
| `full` / `token` / … | 调微信 API（需 **`aws.env`** 微信凭证） |

草稿创建成功后，发布器会把 media_id 写入本篇 `publish-attempt.json`；优先在仓库根执行
`python scripts/verify_draft_submission.py --article <文章目录> --env <外部凭证>`，无需人工复制 media_id。
仍支持显式传入 `--media-id` / `--account` 作为覆盖。
该命令调用 `draft/get`，核对标题、作者、摘要、正文、图片和 HTML 合规性；未通过
时不会写入成功回执，也不会把草稿状态标记为已回读。

## 凭证与 `publish_method` ⛔

### `publish_method`（以仓库 **`config.yaml`** 为准）

| 值 | 含义 | 行为 |
|----|------|------|
| **`draft`**（默认） | 只进公众号**草稿箱** | **`full`** 创建草稿后**不**调用 freepublish 提交发布。 |
| **`published`** | 允许进入公开发布流程 | **`full`/`full --publish`** 只创建草稿；必须完成 `draft/get` 回读、外部 `external_publish` 人工审批、manifest/审批签名后，再运行 `publish --article <文章目录> <media_id>`。 |
| **`none`** | 用户明确不填微信 | **`full`** **立即退出**，不调任何微信接口（**`--publish`** 也会被忽略）。其它子命令（`token` 等）仍要凭证。 |

### 当前工作流的固定槽位

1. 直接使用 **`wechat_publish_slot: 1`**；当前工作流不展示账号列表，也不要求用户选择槽位。
2. 禁止用 **`--account 2`** 或其他值覆盖固定槽位；若文章配置与身份合同不一致，门禁必须阻断发布。

### 全局环境

在仓库外层项目目录放置 **`aws.env`**（微信密钥），仓库内 `.aws-article/config.yaml` 只放固定槽位 1 的非密钥发布配置。新文章必须先通过 `route_content.py --interactive`，由 `matrix_init.py --route` 生成 schema v4 工作区，且 `content_medium` 必须是 `wechat_article`。运行发布命令时通过 **`WECHAT_ENV_PATH`** 或显式 **`publish.py --env <文件> ...`** 指向该项目外层凭证文件；显式参数优先，脚本不会复制或打印密钥。新建 schema v4 文章应在预检时追加 `--probe`，实际探测 token 接口后才可进入环境门禁。**`publish_method: none`** 时 **`full`** 会跳过；**`draft`/`published`** 发布前建议 **`check-wechat-env`**。API 端点使用 **`WECHAT_1_API_BASE`**，若未配则回退 **`config.yaml.wechat_api_base`**（两者都空时使用官方）。

### 作者名回退

`full` / `create-draft` 若 **`article.yaml` 无 author**，回退 **`config.yaml`** 的 **`default_author`**。

### `publish_completed`（兼容字段；新流程分离草稿与公开发布状态）

- 字段在**本篇** **`article.yaml`**。**`publish.py` 不读、不改**；由智能体维护。
- **`false`**：发布流程未闭环。
- **`true`**：兼容旧流程的闭环标记；新流程同时写入 `draft_submitted`、`draft_verified`、`public_published`，避免把草稿误解为已群发。

**本篇发布真正结束后**：将 **`publish_completed: true`** 写回 **`article.yaml`**。

**写回 `true` 的前置门禁（缺啥补啥）**：

1. `article.html` 存在；
2. 文章目录存在封面图 `cover.(png/jpg/jpeg/webp)`；
3. `article.md` 与 `article.html` 中均不含 `placeholder`；
4. 发布命令成功并拿到回执（`media_id` 或 `publish_id`）。

任一不满足：只可标记为“已提交草稿，未闭环”，**不得**写回 `publish_completed: true`。

## 用户仅说「发布」且未明确路径时 ⛔

在用户**未给出**外部 `active/THK-…` 路径、仅说「发布文章」「帮我发一下」等时：

1. **确定本篇目录**：列出 `GZH_ARTIFACT_ROOT/active/` 下的 `THK-YYYYMMDD-NNN-…` 子目录；若**多篇**，请用户**指定一篇**或选「最新修改」的一篇再读该目录 **`article.yaml`**。**勿**在未确认目录时假定路径；不得回到仓库 `drafts/`。
2. 读取该目录 **`article.yaml`** 中的 **`publish_completed`**（YAML 布尔：`true` / `false`；**缺省按 `false` 处理**）。

| `publish_completed` | 智能体对用户说明（可略作口语化，勿改含义） |
|---------------------|---------------------------------------------|
| **`true`** | 告知：**项目里本篇文档已按记录成功发布**；问：**您是否需要编写新文章？** 若需要 → 转交 [main](../gzh-article-orchestrator/SKILL.md) / [writing](../gzh-article-writing/SKILL.md) 从本篇准备或选题起走。 |
| **`false`** 或缺省 | 读取 **`article.yaml`** 的 **`title`**（若无则用目录名简述），说明：**《{title}》尚未执行完成（发布流程未闭环）**；问：**是否需要继续并完成发布？** 或 **编写新文章？** 若继续本篇 → 再核对 **`config.yaml`** 的 **`publish_method`**、**`check-screening`**、**`check-wechat-env`** 等。 |

## 工作流

```
发布进度：
- [ ] 前置：配置检查（见本节「配置检查」）⛔
- [ ] 第0步：若用户未给路径 → 选本篇目录 → 读 publish_completed → 按上表分流（true/false）
- [ ] 第1步：读 **`config.yaml`** → **`draft` / `published`**；`published` 与 `full --publish` 仍必须走两阶段审批
- [ ] 第2步：固定使用 **`wechat_publish_slot: 1`**，不询问账号或槽位；随后跑 **`check-wechat-env`** 校验 `WECHAT_1_*` 凭证
- [ ] 第3步：发布前检查（checklist + **`check-screening`** + **`check`**）
- [ ] 第3.5步：运行仓库根目录 `scripts/publish_preflight.py`，确认草稿权限与 IP 白名单
- [ ] 第4步：确认 `routing.yaml`、`content_medium: wechat_article` 和 `final_reviewed` 门禁
- [ ] 第5步：**`full`** 创建草稿；`full --publish` 在创建草稿后安全阻断，不直接调用 freepublish
- [ ] 第6步：运行 `scripts/verify_draft_submission.py` 完成草稿回读并写入签名 attempt/receipt
- [ ] 第7步：在独立环境记录 `external_publish` human approval，并配置外部批准签名与 manifest 签名
- [ ] 第8步：仅用 `publish --article <文章目录> <media_id>` 提交公开发布；结果写入 `publish-result.json`
- [ ] 第9步：确认结果与用户说明；成功后写回 **`article.yaml`** 的 **`publish_completed: true`**
```

## 交互顺序（最小提问）

0) **未给路径时**：先按上文 **「用户仅说发布」** 处理 **`publish_completed`**；用户选 **继续本篇** 后再做下列步骤。  
1) **先看 `config.yaml` 的 `publish_method`**：**`draft`** = 默认只进草稿箱；**`published`** / **`full --publish`** 也必须等待外部 `external_publish` 审批后单独提交。  
2) **固定槽位**：本工作流直接使用第 1 槽位；不展示账号列表、不询问用户选槽位，也不接受 `--account` 覆盖。
3) 缺微信字段：运行 **`check-wechat-env`**，补全 **`aws.env`** 后再发。  
4) **发布失败**（由脚本 stderr / 微信 errcode 判断）：  
   - **网络类**（超时、连接失败、5xx）：脚本已对单次请求 **自动重试 1 次**；仍失败 → 告知「网络不可用，请稍后重试或检查代理」。  
   - **凭证/配置类**（如 token 失败带 errcode、缺字段）→ 提示 **第几槽位**、检查 **APPID/SECRET、IP 白名单**，用户改正后再执行 **`full`** / **`publish`**。
5) **中间产物缺失**（封面缺失 / 存在 `placeholder`）：先补产物再发；若用户坚持先发草稿，必须明确告知“正文配图未完成”，且保持 `publish_completed: false`。

## 命令示例（仓库根）

```bash
python {baseDir}/scripts/publish.py check-screening
python {baseDir}/scripts/publish.py check-wechat-env
python {baseDir}/scripts/publish.py check
python {baseDir}/scripts/publish.py --env D:/secrets/aws.env full <外部active/THK-YYYYMMDD-NNN-slug>/
python {baseDir}/scripts/getdraft.py published-fields
```

详见 [references/usage.md](references/usage.md)、[references/submit-guide.md](references/submit-guide.md)、[references/api-reference.md](references/api-reference.md)。

## 过程文件

| 读取 | 产出 |
|------|------|
| `article.html`、`imgs/`、**`article.yaml`**（含 **`publish_completed`** 等）、**`.aws-article/config.yaml`**、**`aws.env`**（微信槽位） | 发布到公众号草稿或提交发布；**成功后**由智能体将 **`publish_completed: true`** 写回 **`article.yaml`**（`publish.py` 不改此键） |
