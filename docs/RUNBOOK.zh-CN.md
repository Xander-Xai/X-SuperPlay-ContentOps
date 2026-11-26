---
translation_of: docs/RUNBOOK.md
language: zh-CN
translation_status: synced
---

# 运行手册

[English](RUNBOOK.md) | [简体中文](RUNBOOK.zh-CN.md)

> 真实可执行命令。从实际脚本行为推导，非假设。
> 最后验证：2026-11-25——新增 `scripts/topic_to_m5.py`（TOPIC 文案派生稿 → M5 脚本投影）与 `tests/test_topic_m5.py`（10/10）。该工具在 `agentguide-learning-roadmap` 上端到端实测：QC PASS、视觉运动门 green（fast_ratio 0.0981）。未授予人审、发布或 provider 花费。
> 最后验证：2026-11-23——离线检查：图文工作流 55/55、生产门禁 39/39、预研相关回归 26/26、MiniMax 图像回归 86/86、media-use 权利门 7/7。按授权运行两次 Codex：第一次被旧解析器阻断；第二次通过修复后的适配器，并在临时项目写入图片和生成回执。额度变化未报告。临时项目不是经批准的文章，尚未打包、审核权利/质量或发布。
> X / 跨平台本地数据回流只生成待审主题，不授予自动平台动作；X / 跨平台本地数据回流只生成待审主题，不授予自动平台动作。
> X 命令行 `--new` 增加 `--post-format text|image`（旧记录默认 image）。纯文字发布包不含图片/ALT步骤；图文仍须真图与ALT。`--package`只准备待发布包，`--mark-published`只记录真人确认的X URL。
> 本分支增加离线 X 数据分析工具，指标结果仅写本地，策略审查后才可路由下一轮内容。

## 0. 环境检查

```powershell
python scripts/doctor.py
```

## 1. 引导（首次或清理后）

```powershell
python scripts/bootstrap.ps1    # Windows
bash scripts/bootstrap.sh       # WSL/Linux
```

如 Easel 运行时缺失/损坏：

```powershell
python scripts/resolve_easel.py --bootstrap
```

## 2. 验证 Easel 运行时

```powershell
python scripts/verify_easel_runtime.py --resolve-tag
```

## 3. 创建新项目

```powershell
python scripts\new_project.py --slug my-video --title "My Video Title"
```

## 3.1 视频与共享选题的写前预研

VIDEO 文案和共享的媒介无关 `TOPIC` 包，在文案审批／生产前需要签署预研回执。
单独的 GRAPHIC_TEXT 草稿不用先填这套表：先写草稿，事实保留来源链接，未核实内容标记待查。
契约 `contentops.precopy-research/v1` 详见 [PRECOPY-RESEARCH.md](PRECOPY-RESEARCH.md)。

```powershell
python scripts\preresearch.py init --project projects\my-video
python scripts\preresearch.py intent --project projects\my-video
# 核实来源并完成预研材料
python scripts\preresearch.py check --project projects\my-video
python scripts\preresearch.py approve --project projects\my-video `
  --reviewer "你的名字" --opinion "已核对来源" --confirm
```

VIDEO 的 `approve` 需要具名审核人、书面理由和 `--confirm`；签后修改会使回执过期。
单独图文草稿不再被这张表挡住。

## 4. 运行生产流水线

```powershell
python scripts\run_v1.py projects\my-video
```

## 5. QC

```powershell
python scripts\qc_video.py projects\my-video
```

默认时长 QC 为 30–120 秒；未来智能使用账号级 30–300 秒范围（单条最高 5 分钟）。

## 5.1 证据优先生产链（M5）

```powershell
python scripts\m5_production.py projects\m5-easel-pin
```

来源 → 素材 → 声明 → 脚本 → 旁白 → 字幕 → 分镜 → 合成 → QC → 评审，每个阶段写一份凭证。
任何阶段无法被证据支撑即拒绝（`exit 4`，`state: BLOCKED`）：来源在仓库外、素材 SHA-256 变化、
声明的引文不在来源中逐字出现、素材未声明、字幕覆盖率低于 0.8。

外部视觉素材的权利审核可按相同来源、许可、审核范围和处理方式分组。`review_batch()` 生成绑定每个资产 ID 与 SHA-256 的待审批次；它本身不清权。具名人工决定作出后，`apply_batch_decision()` 写入逐资产 sidecar 并返回更新后的 manifest；调用方保存该 manifest 后，再运行 M5 `stage_assets`。哈希或范围变化都需要重新决定。assets 阶段 PASS 不等于最终 QC、人审通过或发布授权。

`--skip-compose` 在分镜后停止（不调用 ffmpeg、不调用 Easel）。

#### 共享 TOPIC 派生稿 → M5 脚本

当一个选题已作为中立的 TOPIC 审核过一次，且视频子项目已持有获批准的
`00_brief/copy-derivative.json` 时，不要手写 `script/script.json`，使用投影工具：

~~~powershell
python scripts\topic_to_m5.py projects\my-video --json
python scripts\topic_to_m5.py projects\my-video --check
~~~

它读取已审派生稿和 `sources/assets.json` 中登记的 CREATED_BY_OWNER 视觉卡片，
**只**写 `script/script.json`。工具把长段拆成 ≤28 字的行，让每个旁白 Huashu 镜头
不超过 8 秒；逐字保留口播（caption == narration、每段拼接回原文），覆盖每条
`claim_refs`；使用能通过视觉运动门的相机推近语法（`evidence_zoom`）；轮换卡片与
聚焦矩形，避免相邻镜头重复。`--check` 对照以上全部不变量校验现有脚本；两种模式
都不签发审核、不授予发布。

两个前置条件刻意不自动化：已批准的文案派生稿，以及登记为 `CREATED_BY_OWNER`
真实位图的原创视觉卡片。LICENSED 来源截图始终是证据，绝不用作 Huashu 视觉源；
没有原创卡片的项目会以 `NO_VISUAL_CARDS` 阻断。解释型视频先用项目自带的卡片
生成器产出卡片，再以匹配的 SHA-256 和 `evidence_capable: false` 登记到
`sources/assets.json`，然后运行本工具。

#### 归档一次完成的运行

M5 会把每个渲染出的 Huashu 镜头注册为 `sources/assets.json` 中的 `huashu-*`
资产，指向 `assets/generated/huashu/` 下的文件。搬迁项目时必须连生成镜头文件
一起复制：manifest 声明了 `huashu-*` 但 `repo_path` 文件不存在即为孤儿资产，
assets 阶段会在任何重渲染之前就以 `file missing` 阻断下一次运行。若确实不搬
生成镜头，就从 `sources/assets.json` 移除这些声明，让下次运行干净地重新生成。
无论哪种情况都保留成片 MP4 与回执。

#### 动效 skill：混合编排，而非账号单一后端

仓库提供五种渲染后端：`huashu-art-motion` 与 `huashu-motion`（本地、非付费，经 M5
专用适配器渲染），以及剪辑渲染器 `remotion`、`motion-canvas`、`manim`（经
`animation_render.py`）。Remotion 另声明十三个固定版本的 skill 包。每种镜头类型能由
哪些后端绘制，写在 `SHOT_COMPATIBILITY` 里；一支片可以混用。

生产前先规划混合方案：

~~~powershell
python scripts\plan_motion.py projects\my-video --json
~~~

它按各后端真实就绪路径探测——Huashu 走 M5 适配器 preflight，剪辑渲染器走
`animation_render.preflight`——写入 `receipts/motion-orchestration.json`，为每个镜头
分配一个后端。这只是**规划回执**，无害：它绝不阻断普通 Huashu 自动计划。只选 READY
的后端；显式指定的镜头后端不被替换；默认后端是偏好而非强制单一后端；无法分类且无
就绪兜底的镜头直接 BLOCKED，不降级成静帧。

要真正渲染混合方案，materialize 有合法 clip spec 的镜头：

~~~powershell
python scripts\plan_motion.py projects\my-video --materialize
~~~

它写入 `motion/orchestrated-plan.json`，这是**剪辑覆盖层**，只列出能被赋予契约合法、
无声称字卡 spec 的镜头（当前是 Remotion 上的编辑性片头卡）。下一次 M5 运行会先用实测
旁白时长生成所有 Huashu spec，再应用覆盖层把指定镜头切到剪辑后端，其余保持 Huashu。
**不要**设置 `motion.shot_plan` 指向覆盖层——那会跳过自动计划，让 Huashu 镜头没有
生成的 spec。只有 materialized 回执才被执行校验：后端不一致时 BLOCK 而非降级。混合
运行记为 `hybrid`，在人审前仍是技术草稿，`production_ready: false`。

#### 旁白默认：MiniMax 创始人克隆

两个视频账号 DNA 都声明 `provider_hint: minimax_m_plan/speech-2.8-hd` 与
`voice_alias: founder_primary_v1`；`make_content.py answer` 现在在交互和非交互路径
都默认使用创始人克隆。离线诊断音色需显式传 `--narration sapi`，SAPI 绝不是克隆失败后
的静默回退。克隆路径需要环境或 `.env` 中的 MiniMax 订阅 key 或 API key；
`runtime_readiness` 在发起任何付费调用前检查二者之一。只有 `MINIMAX_CLONE_KEY`
的机器走的是按量克隆通道，不满足计费门禁。门禁通过只是允许尝试调用，不等于
克隆已合成。运行始终停在
`PENDING_FOUNDER_REVIEW`，`production_ready: false` —— QC 通过不等于允许发布。

`asr_backcheck` 阶段会转写旁白并与"实际朗读的脚本"比对。没有 `SILICONFLOW_API_KEY`
时它报告 `SKIPPED` —— 那不是通过。覆盖率不达标会阻断人工审核；通过也从不构成批准。
模型、端点覆盖与比对规则见 [ASR-BACKCHECK.md](ASR-BACKCHECK.md)。

### M5 本地用户素材预览

为现有项目显式导入图片或视频素材：

```powershell
python scripts\m5_production.py projects\my-video --assets D:\media\selected-for-preview
```

M5 将支持的文件复制到 `assets/imported/user/`，把 SHA-256 写入
`sources/assets.json`，并生成 `receipts/user-assets-import.json`。视频保留原片，记录
编码、时长、分辨率、帧率和音轨信息，抽取起始、中段、末段三帧，并生成
`receipts/user-assets-contact-sheet.jpg`。所有导入素材仍为
`USER_PROVIDED_LOCAL` / `LOCAL_PREVIEW_ONLY`：导入不授予分发权，也不能作为事实证据。
发布前须单独核查权利；事实声明仍须绑定独立来源。此选项不修改脚本素材 ID，亦不批准发布。


### M5 自动调用 media-use 素材（仅离线）

当已合并的适配器可用、本机已配置经验证的运行时锁时，
在项目 project.yaml 中声明素材需求。执行原来的 M5 命令时，
系统会自动调用 media-use，而不需要单独运行适配器命令：

~~~yaml
media_use:
  enabled: true
  mode: local-only
  requests:
    - id: support_visual
      kind: image
      intent: local support image
      rights:
        license_id: OWNED-BY-OPERATOR
        source_url: OWNED
        reviewed_by: <reviewer>
        reviewed_at: "2026-10-31"
        review_evidence: assets/support.rights.json
        attribution: project owner
        synthetic: false
~~~

单独的 `rights_reviewed: true` 会被拒绝。每个请求必须附带复核记录
（`assets/<id>.rights.json`，schema `contentops.media-rights-review/v1`），
其许可证、来源 URL、复核人、日期与署名必须与请求完全一致。
软件许可证与非商业许可证不能用于媒体；合成素材永远不能作为证据。

把已核实权利的候选图片放入该项目 assets/，然后在
script/script.json 对应镜头使用 asset_id=support_visual。
仅在诊断时可直接运行 M5：

~~~powershell
python scripts\m5_production.py projects\my-video
~~~

正式生产应使用受门禁保护的 `make_content.py` 入口；直接运行 M5 属于诊断，
不代表生产门禁已通过。

素材阶段会自动 adopt 本项目文件、通过批准的运行时离线 resolve、
生成导入回执并核验 SHA-256，再交给原有素材校验、分镜、合成及 QC。
已有 sources/assets.json 声明的素材优先。找不到素材则明确 BLOCKED，
不擅自联网或调用付费服务。

新增 receipts/media-use-stage.json 和每个文件的来源回执。
导入的授权素材只用于视觉辅助，不自动变成事实证据。
这一版支持 image/icon/logo 的自动画面接入，以及 BGM/SFX 辅助音轨；
音频不进入事实证据。
未设置 media_use.enabled=true 的旧项目保持原行为。

该适配器已通过 PR #71 合并，执行仍需经验证的主机运行时锁和适用的素材权利。
CI 使用离线合成测试数据，不运行第三方 Provider。

## 5.2 Bundle handoff 与双线

可在 `project.yaml` 中可选地绑定 Strategy Content Bundle：

```yaml
content_bundle:
  path: bundle.json          # 相对项目目录或仓库根
  account: explorer          # explorer | thinktank
  platform: x                # 可选的交付占位
  source_map:
    SRC-20261102-001: SRC-RUNTIME-001
```

M5 会在 sources 阶段之前写 `receipts/bundle-handoff-video.json`。来源映射缺失或
不匹配会阻断运行；`PLANNED` 平台只记录交付阻断，不阻断视频生产。

每个 handoff 都记录 Bundle 的逻辑路径、作用域与 SHA-256，两条线的构建步骤都会
重新核对：Bundle 已变更时以 `BUNDLE_CHANGED` 拒绝，未记录 Bundle 时以
`HANDOFF_UNBOUND` 拒绝。改动 Bundle 后必须重建 handoff。Bundle 必须位于项目或
仓库之内，因此从 Strategy 检出复制来的文件以相对路径记录，绝不写绝对路径。

单独生成 handoff（不生产、不发布）：

```powershell
python scripts\bundle_handoff.py projects\my-video\bundle.json `
  --account explorer --format VIDEO --project-slug my-video `
  --source-map SRC-20261102-001=SRC-RUNTIME-001 --out-project projects\my-video

python scripts\bundle_handoff.py projects\my-video\bundle.json `
  --account explorer --format GRAPHIC_TEXT --project-slug my-article `
  --platform wechat_article --out-project projects\my-article
```

## 5.3 图文生图与人工包

### 日常用法：直接说要做什么

给出文章／选题和平台即可。助手应先复用当前项目、账号和 Bundle，直接起草；**正文工作稿是唯一常规人工审核点**。收到你的正文审核通过后，助手继续准备配图、排版、运行阶段检查并生成离线交付包，不再要求 brief、提纲、图片、排版、QC 各自签字。真实调用生图服务仍须明确授权具体提供商和张数；无法证实权利的素材会被排除或阻断，不会伪造审核。创建平台草稿仍需单独明确授权，本流程不会自动发布。

正文审核通过后记录一次审核（也可以直接在项目中编辑 `draft.md`）：

```powershell
python scripts\copy_review.py projects\my-article --approve `
  --reviewer "审核人" --opinion "已审核图文工作稿" --confirm
```

### 命令参考（需要时再看）

图文线产出可审核的包，而不是平台草稿。打包和生图是两个步骤：

```powershell
python scripts\graphic_package.py `
  --project projects\my-article `
  --handoff projects\my-article\receipts\bundle-handoff-graphic_text.json `
  --input projects\my-article\graphic-input.json
```

新包只能选择以下三种生图方式：

| 方法 | 路由 | 边界 |
|---|---|---|
| `codex_imagegen` | Codex CLI 原生 `image_gen` 工具 | 每次授权生成一张；不走 API、浏览器、MCP 或回退。记录实际尺寸，保证 16:9 比例，但不保证精确像素尺寸。 |
| `ian_xiaohei_codex` | 宿主先调用 `ian-xiaohei-illustrations` 生成分镜/提示词，再使用同一 Codex 原生 `image_gen` 后端 | CLI 不会执行 Skill；Skill JSON 必须绑定当前文章哈希。 |
| `minimax_subscription` | 通过 `generate_image.py` 和 `BillingGuard` 复用现有 `image-01` Provider | 仅订阅额度；PAYG 和 Credit Pack 仍阻断。默认 1024×576；宽高须符合 Provider 合约且为 16:9。Provider 缓存和临时回执保存在指定 scratch root；项目内写入唯一图片及摘要回执。 |

漫画式说明图必须由宿主在写提示词前参考 GitHub 上固定版本的
[comic-explainer-illustration skill](https://github.com/chujianyun/awesome-gpt-image2-ppt-skills/blob/aa5fec05a1d1991d7653ed31c0407d513d0fa6d3/comic-explainer-illustration/SKILL.md)，仅用作分镜/提示词辅助。采用其 16:9、精简视觉叙事时仍须保留账号 DNA 和人物设定，不强制四格，也不引入其默认角色。整理后的 prompt 文件与后端无关，所选路线为 `codex_imagegen` 或 `minimax_subscription` 时都可直接使用；`ian_xiaohei_codex` 仅在 Ian Skill 生成 shot/prompt 后把它作为辅助润色。它不是新 Provider/CLI 方法，不由 CLI 安装或执行。已审查的 GitHub 修订版没有声明 `LICENSE`/`COPYING`，不把其文字或脚本复制进本仓库。

生图命令每次只处理一个提示词/shot。仅查看计划时不会请求 Provider。真实生成必须同时传入 `--execute` 和 `--authorize-provider-usage`；每次只尝试一次，不重试、不切换方式。所有执行方式都需要操作者指定位于
`D:\Temp\AI-Agents\<agent>\<task>` 的 scratch root；Codex 会在其中创建唯一运行目录，MiniMax 则在其中保留 Provider 缓存和临时回执：

```powershell
python scripts\graphic_generate.py `
  --method codex_imagegen --project projects\my-article --asset-id shot-01 `
  --prompt-file 03_images\prompts\shot-01.md `
  --scratch-root "D:\Temp\AI-Agents\<agent>\<task>" `
  --execute --authorize-provider-usage
```

包装器运行 `codex exec --ephemeral --sandbox workspace-write`，带上
`--ignore-user-config` 并通过 stdin 传提示词。若输出含已完成的原生生图事件，需与一张全新图片绑定；常见 JSONL 路径则要求有唯一 `thread.started`、成功的 `turn.completed`，并且 `CODEX_HOME\generated_images\<thread_id>` 是本次新建且仅含一张图的线程目录。缺少、重复、陈旧或路径不匹配都会阻断；不保存 Codex 对话。最近一次现场调用未报告额度变化，因此额度记为未知；未报告的模型版本和精确像素尺寸不会猜测。

MiniMax 使用相同的授权标记并复用现有计费门：

```powershell
python scripts\graphic_generate.py `
  --method minimax_subscription --project projects\my-article --asset-id shot-01 `
  --prompt-file 03_images\prompts\shot-01.md `
  --scratch-root "D:\Temp\AI-Agents\<agent>\<task>" `
  --width 1024 --height 576 `
  --execute --authorize-provider-usage
```

`ian_xiaohei_codex` 先生成只读、绑定文章哈希的 handoff：

```powershell
python scripts\graphic_workflow.py plan `
  --workflow x --project projects\my-article --article 02_draft\draft.md `
  --illustration-skill ian-xiaohei-illustrations --json
```

宿主调用所选 Skill 后，将 shot list 保存为项目内的
`contentops.ian-illustration-result/v1` JSON，并原样保留 handoff 返回的文章路径和哈希。再选择一个 shot 生成：

```powershell
python scripts\graphic_generate.py `
  --method ian_xiaohei_codex --project projects\my-article `
  --article 02_draft\draft.md --skill-output receipts\ian-skill-result.json `
  --asset-id shot-01 --scratch-root "D:\Temp\AI-Agents\<agent>\<task>" `
  --execute --authorize-provider-usage
```

生图命令会写入真实图片和项目内的生成回执，记录方法、提示词哈希、文件哈希、格式、尺寸及不可作证据标记；状态为 `GENERATED_PENDING_REVIEW`。它不会批准 AIGC 披露、权利、质量或发布。将命令返回的 `path`、`asset_id`、ALT 和 `generation` 回执引用写入 `graphic-input.json`。远程生成图片还需要一份单独、具名、绑定精确 generation ID 和图片 SHA-256 的权利审核。使用 `license_id: GENERATED-REMOTE-REVIEWED`、适用 Provider 条款 URL、生效日期、明确的 `permitted_use` 和有限的 `review_scope`。这只是操作者针对具体图片的审核记录，不是保证或法律结论。远程输出不能标成 `OWNED-GENERATED-LOCAL`；M5 权利门也不接受此远程生成分类。

随后运行打包命令。它会校验该工作稿的审核回执，然后自动生成各阶段工件并运行结构与质量检查；常规阶段只记机器检查，不再要求人工逐项批准。包仍不会自动创建平台草稿或发布，`publish_authorized` 保持 false。生成式图片只能作辅助视觉，不能作事实证据；真实素材的权利证据和收费生图授权仍按各自安全边界处理。
`manual_chatgpt_web`、通用 `api` 和 `local_svg_html` 已从新包退役，不会静默替换。历史回执保留原值并继续校验。离线合约测试通过。第一次现场 Codex 调用被旧解析器阻断；第二次经单独授权后，通过修复后的适配器，在临时验收项目写入图片和生成回执。它不是经批准的用户文章，尚未进入文章打包或权利/质量审核。

官方参考：[Codex 图像生成工具](https://github.com/openai/codex/blob/main/codex-rs/ext/image-generation/src/tool.rs)、[Codex imagegen 示例](https://github.com/openai/codex/blob/main/codex-rs/skills/src/assets/samples/imagegen/SKILL.md)、[MiniMax CLI](https://platform.minimax.io/docs/m-plan/minimax-cli)、[MiniMax image-01 尺寸](https://platform.minimax.cn/docs/api-reference/image-generation-t2i)、[OpenAI 使用条款](https://openai.com/policies/terms-of-use/)、[MiniMax 服务条款](https://platform.minimax.io/protocol/terms-of-service)。

## 5.4 受门禁保护的 Easel 宿主

仅查看状态；不启动服务、不安装依赖：

```powershell
python scripts\easel_host.py status
python scripts\easel_host.py status --verify-bytes
```

`--verify-bytes` 增加内容比对：按 git 方式对运行时树做哈希，并通过 `gh` 与锁定
提交比较。它需要网络与 `gh`；两者缺失时结果为 `HOST_BYTES_UNVERIFIED`，这不是
通过。`serve` 总是执行该比对，因此离线或已被修改的树无法启动。

在 FastAPI/uvicorn 存在且宿主安全审查记录之前，`HOST_BLOCKED` 是预期结果。
`serve` 只监听 `127.0.0.1`、拒绝所有写操作，并在到达上游前关闭 websocket
scope；**不要**直接运行上游 `easel web` 或 `web/app.py`。见 ADR-016。

## 5.5 coding agent 驱动

coding agent（Claude Code、Codex CLI、OpenCode）无需 Web 宿主即可驱动流水线：
先取计划，再执行一步，然后读取回执。

```powershell
python scripts\agent_drive.py status
python scripts\agent_drive.py plan --project projects\my-video --json
python scripts\agent_drive.py run --project projects\my-video --step produce-video --execute
```

计划固定 argv，agent 只能选步骤 id，不能给命令。`run` 不带 `--execute` 时只打印
将要执行的命令。每次执行都会写 `receipts/agent-driver-<step>.json`，包含返回码、
截断输出与 `publish_authorized: false`。

`human-review` 标注为 `authority: HUMAN_ONLY`，驱动方尝试执行会被拒绝。计划中
不存在发布、凭据或安装步骤。该驱动不需要 FastAPI、uvicorn 或运行中的宿主；
`host-status` 只是让 agent 能报告宿主状态的只读步骤。

## 5.6 Brief 文案人工审核

Brief-to-M5 桥接写入最终脚本与分镜后，先检查或记录人工文案审核，再运行 M5：

```powershell
python scripts\copy_review.py projects\my-episode --check
python scripts\copy_review.py projects\my-episode --approve `
  --reviewer "审核人姓名" --opinion "已审核最终旁白" --confirm
python scripts\copy_review.py projects\my-episode --request-changes `
  --reviewer "审核人姓名" --opinion "补充缺失的来源引用" --confirm
```

审核决定必须填写审核人、书面意见并显式传入 `--confirm`。收据绑定当前文案指纹；
修改口播、字幕、逐行 claim 绑定、分镜或已登记素材后，旧批准会过期。仅新增或修正
`script/claims.json` 中的证据元数据，不会改变已审核文案。若 `script/script.json` 与已审核的
VIDEO derivative 在文字和 claim 绑定上严格一致，它作为机器投影不会重复触发文案审核；
任何偏差仍会计入指纹并使审核过期。M5 将来源链接单独写入
`receipts/script-citations.json`，不会覆盖已有的 `script/master.md`；旁白与创作者原稿
不一致时会阻断。该命令只记录审核决定，不会修改文案、运行 M5 或发布内容。

## 5.7 卡片与公众号文章渲染

两个渲染器都调用固定版本 Easel Skill 并写出回执。两者都不是批准。

```powershell
python scripts\render_cards.py   projects\my-note
python scripts\render_article.py projects\my-article
```

- `render_cards.py` 把 HTML 渲染为 PNG 并跑卡片密度审计；退出码 4 表示被阻断或审计未过。
  它需要真正装好 Chromium 的 Playwright 构建：设置 `CONTENTOPS_CARD_PYTHON` 与
  `PLAYWRIGHT_BROWSERS_PATH`。
- `render_article.py` 校验文章 HTML 并包装浏览器预览；退出码 4 表示被阻断或校验未过。
  它使用 `CONTENTOPS_PYTHON` 或当前解释器，从不扫描其他解释器。
- 回执：`receipts/card-render.json`、`receipts/gzh-article.json`，两者都保持
  `production_ready: false` 与 `publish_authorized: false`。
- 两个命令都不启动宿主、不调用 agent、不访问网络。

## 5.8 交付包（视频与图文）

打包全程离线。这里没有任何一步会发布：上传器 exit 0 只记为 `UPLOADER_EXIT_0`，
只有人真正看到的 URL 才被登记为 URL。

打包之前先问清账号声明的每个平台各自要什么：计划会给出画幅、上限，以及哪些平台需要
二次成片；账号没声明的平台会被拒绝，而不是被跳过。

```powershell
python scripts\platform_adapt.py plan --project projects\my-video
python scripts\platform_adapt.py plan --project projects\my-video --platform bilibili --json
```

```powershell
python scripts\video_deliver.py plan   --project projects\my-video
python scripts\video_deliver.py pack   --project projects\my-video --thumbnails
python scripts\video_deliver.py status --project projects\my-video
python scripts\video_deliver.py record --project projects\my-video --platform douyin --url <真实URL>
python scripts\platform_delivery.py list
python scripts\platform_delivery.py pack --package <已审核图文包的路径>
python scripts\graphic_deliver.py --package <已审核图文包的路径> --all --confirm-draft-write
```

- `dispatch` 会运行外部上传器，必须同时给出 `--execute` 和运营授权（`--grant`）；
  缺任一项时它只打印将要执行的 argv。
- `graphic_deliver.py` 让一个桥接进程在整个批次中存活，只有 CLI 打出 `✓` **且**返回
  URL 才算该平台交付成功。每次调用都只创建草稿。
- 上传器与 `wechatsync` 桥接位于被 gitignore 的 `.runtime/` 树，经进程边界调用，
  绝不被导入。

## 5.9 公众号工作流状态

```powershell
python scripts\gzh_workflow_run.py --workflow <公众号工作区> --article <文章目录>
python scripts\gzh_runtime.py status
```

`gzh_workflow_run.py` 运行只读链路（运行时依赖 → 身份 → 矩阵校验 → 洁净室检查 →
SDK 适配器自检 → 10 项门禁检查）并写出状态回执。它从不推进门禁，被阻断的门禁会
带上真实错误数上报。`gzh_runtime.py` 保持 `VERIFY_ONLY`：`execution_authorized` 与
`publish_authorized` 恒为 false。

## 6. 开发门控

```bash
python scripts/dev_check.py
```

依次运行：仓库策略 → 子进程策略 → Skill 引用 → 文档 → i18n → 冒烟测试 → 空格检查。

## 6.1 Skill 引用完整性

```bash
python scripts/check_skill_references.py
python scripts/check_skill_references.py --json
```

五个已安装的内容 Skill 引用了未合并分支上的代码。`runtime/content-skill-status.json`
记录了每一条这样的路径；当记录与当前检出不一致时检查失败：未记录的悬空引用、
已经落地（记录过时）的引用，或标记为已合并却缺少代码的 Skill。没有共享 Skill 库
的主机（CI）会跳过引用扫描，只运行“记录与分支”的一致性检查。

这里失败意味着记录需要更新——当某一层落地后，也意味着该能力现在可以在
`runtime/skill-registry.json` 中声明。

## 6.9 成片与人工发布

V1 与交付层都**不自动发布**。成片在 `final/` 下：V1 引擎写 `final/easel.mp4`
（跑过诊断引擎时另有 `final/fallback.mp4`）；受门禁的生产路径
（`make_content.py` → `produce_video.py` / `m5_production.py`）写
`final/<slug>.mp4`。`video_deliver.py pack` 取 `final/` 下第一个非 `before` 的
`*.mp4`，因此不依赖文件名。人工上传后执行
`python scripts\video_deliver.py record --project projects\my-video --platform <id> --url <真实URL>`
登记；工具退出码不是发布，URL 才是。

## 7. Easel 上游监控

```bash
python scripts/check_easel_upstream.py
```

## 8. i18n 一致性检查

```bash
python scripts/check_i18n.py
```

## 9. media-use 素材（可选）

需要 `~/.agents/skills/media-use` 固定版本技能与 Node ≥ 22（HyperFrames 官方 CLI 下限）。**默认不授权网络、付费供应商、跨项目复用或自动发布。** 可信运行时只证明执行了什么，不授予任何发现素材的许可证。

```powershell
python scripts\media_use_adapter.py status
python scripts\media_use_adapter.py doctor

python scripts\media_use_adapter.py candidates --type image --project projects\<slug>
python scripts\media_use_adapter.py resolve --type sfx --intent "soft transition" --project projects\<slug>

python scripts\media_use_adapter.py adopt --project projects\<slug>
python scripts\media_use_adapter.py import --type image --record-id img_001 `
  --license "CC-BY-4.0" --attribution "..." --project projects\<slug>

python scripts\media_use_adapter.py verify --project projects\<slug> --path assets\pic.png

python scripts\media_use_adapter.py demo --project projects\media-use-demo
```

退出码：`0` 完成，`2` 用法错误，`5` 被阻断／需要人工决定，`1` 意外失败。授权开关（`--allow-network`、`--allow-paid --budget`、`--allow-cross-project`、`--allowed-provider`）必须显式给出，默认关闭。

`import` 拒绝空 `--license`。media-use 记录本身没有许可证字段，因此许可证必须由人决定，不能被默认填充。

### 运行时信任（任何外部调用前必需）

必须同时具备两层，任一层都不能替代另一层：

- `runtime/media-use-runtime-baseline.json` —— 提交到仓库并由所有者批准
  （2026-10-31，仅限离线范围）。批准是记录在文件里的人为决定；它不会安装运行时。
- 本机生成的锁 —— 绝对路径、node 哈希、逐文件哈希，以及已批准基线的摘要 —— 由
  `CONTENTOPS_MEDIA_USE_RUNTIME_LOCK` 指向，绝不提交。

干净检出的机器在生成机器锁之前仍拒绝执行。基线批准记录一旦变化，基线文件摘要也会
变化，之前生成的锁将不再匹配：任何批准变更后都要重新生成锁。不要通过手工编辑锁来
让它匹配新基线。

在一台机器上准备一次：

```powershell
# 1. 人审查证据后批准已提交的基线
python scripts\media_use_runtime.py approve --approved-by "Your Name"

# 2. 安装已批准的发布（唯一需要联网的步骤）
python scripts\media_use_runtime.py install --runtime-dir D:\Data\contentops-media-use --node D:\Toolchains\node\node.exe

# 3. 生成机器锁，并与基线比对验证
python scripts\media_use_runtime.py lock --runtime-dir D:\Data\contentops-media-use --node D:\Toolchains\node\node.exe --out D:\Data\contentops-media-use\runtime-lock.json

# 4. 通过生产适配器执行本地、离线操作
python scripts\media_use_runtime.py selfcheck --lock D:\Data\contentops-media-use\runtime-lock.json --project projects\demo
```

```powershell
$env:CONTENTOPS_MEDIA_USE_RUNTIME_LOCK = "D:\Data\contentops-media-use\runtime-lock.json"
python scripts\media_use_adapter.py status
```

`install` 使用仓库内的 `runtime/media-use-package-lock.json` 执行
`npm ci --ignore-scripts`；该文件的 SHA-256 必须等于基线的
`dependency_lock_sha256`，依赖树不同即被拒绝。

`status` 每次都会重新哈希整棵运行时树，并报告 `TRUSTED_RUNTIME`、
`RUNTIME_MISSING`、`INTEGRITY_MISMATCH`、`VERSION_MISMATCH`、
`BASELINE_MISMATCH` 或 `DEPENDENCY_UNVERIFIED` 之一。重新生成锁永远不会批准发布。
没有可信锁时，项目内本地导入仍然可用，但所有外部调用都会被拒绝。

### 升级或回退 HyperFrames

升级是显式、经过审核的变更；适配器从不自动更新。

1. 更新 `runtime/media-use-runtime-baseline.json` 中的版本、官方 SRI、依赖锁摘要与包树摘要。
2. 人工审查证据后运行 `python scripts\media_use_runtime.py approve --approved-by "<name>"`。
3. 安装到**新的**运行时目录（不要覆盖可信目录），再执行 `lock` 与 `verify`。
4. 离线运行 `selfcheck`，再运行 `tests/test_media_use_adapter.py` 与 `tests/test_media_convergence.py`。
5. 将 `CONTENTOPS_MEDIA_USE_RUNTIME_LOCK` 指向新锁。

回退：保留旧的运行时目录与其锁，把环境变量指回旧锁，并验证它针对生成时的基线报告
`TRUSTED_RUNTIME`。绝不要手工编辑锁或逐文件哈希。

### M5 自动获取素材

在 `projects/<slug>/project.yaml` 里声明一次，主入口就会自动解析，无需单独调用 media-use：

```yaml
media_use:
  enabled: true
  mode: local-only
  requests:
    - {id: hero, kind: image, intent: "...", rights: {license_id: OWNED-BY-OPERATOR, source_url: OWNED, reviewed_by: me, reviewed_at: "2026-10-31", review_evidence: assets/hero.rights.json, attribution: "owner capture", synthetic: false}}
    - {id: bed, kind: bgm, intent: "...", volume: 0.18, rights: {license_id: OWNED-GENERATED-LOCAL, source_url: GENERATED, reviewed_by: me, reviewed_at: "2026-10-31", review_evidence: assets/bed.rights.json, attribution: "generated tone", synthetic: true}}
    - {id: click, kind: sfx, intent: "...", at: 6.15, volume: 0.55, rights: {license_id: Pixabay-Content-License, source_url: "https://pixabay.com/sound-effects/", reviewed_by: me, reviewed_at: "2026-10-31", review_evidence: assets/click.rights.json, attribution: "Pixabay", synthetic: false}}
```

```powershell
$env:CONTENTOPS_MEDIA_USE_RUNTIME_LOCK = "<本机已验证的锁>"
python scripts\m5_production.py projects\m5-media-use
```

`stage_media_use` 在素材门控之前执行 `adopt → resolve → import_record → verify`。
视觉导入会进入 `sources/assets.json` 校验；BGM 与 SFX 写入 `script/storyboard.json`
（`bgm`、`bgm_volume`、`sfx[].at`、`sfx[].volume`），由钉死的 Easel 合成器混在旁白之下。
`at` 必须落在旁白时间轴内，重复的音效放置会被拒绝。不会调用任何供应商。
运行时锁缺失或不匹配时，运行以退出码 `4` / `BLOCKED` 停止。`project.yaml`
没有 `media_use` 块的项目行为完全不变。

### 隔离 Easel 演示不等于原始运行时

media-use 演示通过另一套已验证的 Easel 运行时合成。演示成功与 QC `WARN` **不**表示
原始 `.runtime/easel` 检出已健康或已恢复；那仍是一个独立的完整性问题是。
