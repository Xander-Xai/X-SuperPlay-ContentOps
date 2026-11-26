---
translation_of: docs/MOTION-WORKFLOW-SPEC.md
language: zh-CN
translation_status: synced
---

# 动效工作流规范

[English](MOTION-WORKFLOW-SPEC.md) | [简体中文](MOTION-WORKFLOW-SPEC.zh-CN.md)

> 双账号视频工作流的可执行契约。本分支从 `origin/main` 建立；以下内容记录本次收尾
> 核实的代码与回执，而非愿望。根目录的 `VIDEO-WORKFLOW-OPTIMIZATION-PLAN.md` 是
> Owner 草稿；本文件是代码与 CI 指向的规范版本。

## 1. 边界

- **Easel v0.3.0 (`bb3c8ff`) 是唯一整片合成器。** MotionClone 是外部工具,只通过 handoff
  记录提供一段自有短片段;不复制其代码,不与 `media-use` 0.8.222 混用运行时。引擎
  pin 已冻结;本工作流不授权修改上游。
- VIDEO 与 GRAPHIC_TEXT 是两条独立产线;本规范只覆盖 VIDEO。
- 本规范不授权 provider 花费、凭据使用、依赖安装、升级或发布。渲染片段或技术 QC
  通过不代表生产发布已获授权:`production_ready: false`、`publish_authorized: false`、
  `human_review: PENDING_FOUNDER_REVIEW` 持续有效,直至完成人工审核及单独的发布授权。

## 2. 已交付契约

| 契约 | 代码 | 强制内容 |
|---|---|---|
| 动效样片门 | `src/contentops/media/motion_sample.py`、`scripts/check_motion_sample.py` | 2–8 秒、静音、1080×1920、H.264/yuv420p、**由帧时间戳验证 CFR 30**、SHA-256 绑定;`TECHNICALLY_CHECKED` 仍是 `PENDING_FOUNDER_REVIEW` |
| 动效交接 | `src/contentops/media/motion_handoff.py` | 仅 `project://`、哈希绑定的 MP4、MotionClone 2.0.0 / HyperFrames 0.8.33、工程哈希、源窗口 ≤8 秒、仅内部权利、所有权限标志为 false |
| 真实素材时长 | `src/contentops/media/real_source_duration.py`、`scripts/qc_video.py` | 仅适用于 1024 证据主导内容:成片可见时长中 ≥70% 必须是获权真实来源素材（如录屏、截图、文档、日志等），不要求这 70% 全为录屏;按可见时长而非镜头数计,图解、卡片、生成与动效不计。另有独立的 1024 正式生产门：必须登记真实裁切录屏。未来智能无录屏时长要求,且禁止手工桌面录屏。重叠只算一次 |
| Driver QC 绑定 | `src/contentops/easel/driver.py` | `receipts/qc-report*.json` 在计划期由 `_step_receipts_ok` 解析;匹配但未评分或 `FAIL` 不算完成 |
| Router → brief → M5 | `src/contentops/routing/`、`src/contentops/script/`、`scripts/content_route.py`、`scripts/brief_to_m5.py`、`scripts/m5_production.py` | 账号 DNA → 候选 → 已批准 brief → `script/script.json` + claims + source refs;`copy_review.require_if_brief_driven` 拦截未审文案 |
| S4 阶段策略 | `src/contentops/workflow/{audience,duration,copy_strategy,platform,delivery,visual_route}.py` | 受众/时长/策略/平台限制、人工交付清单与视觉路由;不授予发布权 |
| 图文工作流适配器 | `scripts/graphic_workflow.py`、`src/contentops/gzh/runtime.py`、`src/contentops/x/runtime.py` | 仅 GZH 与 X；定位/哈希校验/描述及人工包表面；不执行工作流、不调用平台 API、不拟稿、不发布。小红书图文已排除；仅配置 `xiaohongshu_video` VIDEO 目标。 |

### 图文与编辑部工作流(GZH / X)

GZH 工作流由操作者安装在公开仓库之外,仓库不 vendored 它。X 是本仓库
自己的、仅人工的编辑部门禁。`scripts/graphic_workflow.py` 接受 `gzh`、`x`、`video`;
图文/编辑部入口仅为 `gzh` 和 `x`(`status`、`verify`、`plan`)。它校验工作区或锁,
然后描述操作者步骤。`video` 路由列出支持的视频目标,不执行平台工作流;使用 `--handoff --project <path>` 时,会调用 `scripts/video_deliver.py pack` 与
`dispatch`，针对路由导出的受支持视频目标（小红书具体为 `xiaohongshu_video`）构造多平台交付包和
argv。视频目标只接收视频素材；该 handoff 不会把图文内容转换成视频。handoff 仍设置
`execute=false`、`publish_authorized=false`：不运行上传器，也不授权发布。GZH 使用 GRAPHIC_TEXT 人工包，停在 `AWAITING_MANUAL_REVIEW`;X 使用人工发帖包。
XHS 没有图文适配器或 CLI 路由；小红书仅作为 VIDEO 目标。

权利:GZH 的 50 个 skill 中有 45 个无许可,清权前只允许本地内部使用。通过校验不等于再分发许可。

## 3. 命令

```bash
python scripts/check_motion_sample.py <sample.mp4> [--sha256 <hex>]
python scripts/graphic_workflow.py status --workflow gzh
python scripts/graphic_workflow.py plan   --workflow x --json
python scripts/graphic_workflow.py status --workflow video --json
python tests/test_motion_sample.py
python tests/test_motion_handoff.py
python tests/test_real_source_duration.py
python tests/test_s4_stages.py

python scripts/content_route.py accounts
python scripts/brief_to_m5.py --check projects/<slug>
python scripts/m5_production.py projects/<slug>
python scripts/qc_video.py projects/<slug> --video <slug>.mp4
python scripts/qc_visual.py projects/<slug> --video <slug>.mp4
```

动效交接**故意没有 CLI**:它是调用方在把资产放上唯一活动时间线之前验证的契约。
通过验证的记录不会自动进入 M5。

## 4. Always / Ask / Never

**Always**

- 一份 manifest,一个 placement 只有一个活动资产。
- 审批绑定产物与上游 digest;Bundle 变更即撤销审批。
- VIDEO 常规阶段在机器校验通过后推进，记录为 `checked` 而非 `approved`；产物或上游
  digest 变化即失效。明确要求人工决定的阶段仍等待该决定。图文阶段不变。
- 权利按来源与许可审核一次，而非按文件审核一次。批次列出其覆盖的每个资产与哈希；
  请求审核不是审核，哈希变化即是新批次。
- 必须在人审通过前保持 `production_ready: false`、`publish_authorized: false`、
  `human_review: PENDING_FOUNDER_REVIEW`。技术 PASS 或渲染完成不是 Founder 验收或发布授权。
- 对账号 `x-superplay-1024`，DNA 中 70% 真实录屏配比是内容目标。独立的真实素材时长门
  衡量成片中可见的获权真实来源素材（录屏、截图、文档、日志等）；不要求所有计入时长
  都是录屏。正式生产另要求登记真实裁切录屏。两个门都不能按镜头数量替代。
- 对账号 `x-superplay-future-intelligence`，每条视频按选题选择 30–300 秒；300 秒为硬上限。禁止手工桌面录屏；无最低录屏时长要求。不得以桌面捕获替代图解或代码聚焦视觉。
- **创作者改过的文案优先。** 创作者修改 AI 初稿并说明自己的版本为最终稿后，必须逐字保留，包括口播语气词、口语表达、重复和标点。不得擅自润色、缩短、删除语气词或套用 AI 式改写；只修改创作者明确要求改动的部分。分镜指示、项目链接和证据备注写在口播行之外。若文案存在事实或证据问题，单独指出；不得暗中改写创作者的文案。
- 回执只用逻辑路径(`project://`、`repo://`),不写绝对主机路径。
- 每个新 `tests/test_*.py` 必须注册进 `.github/workflows/ci.yml`。

**Ask the Owner**

- 任何真实 A/B 来源片段或第三方衍生物。
- 任何 provider 调用、花费或凭据使用。
- 任何 MotionClone / Easel / media-use 固定版本变更。
- 任何发布或外部交付。

**Never**

- 把 handoff 记录当作公开复用许可。
- 把生成、图解、卡片或动效算作真实素材秒数。
- 让技术 PASS 变成 G6 或发布批准。
- 未经明确决定重写公开历史、关闭未解决 Issue 或删除归档。

## 5. 阻塞项

| 项目 | 阻塞 |
|---|---|
| 两条真实 A/B 样片 | 1024:权利可用的真实捕获;未来智能:可复现 RAG 项目及已清权来源窗口,不含桌面录屏 |
| 模块扩展与整片 | 样片通过后逐账号 G6 决定 |
| 发布 | 单独的人工授权与真实平台 URL |
| GZH/XHS 接入 | 许可问题而非架构:XHS 需排除 1 个 AGPL skill;GZH 45 个 skill 无许可 |

## 6. 验证

```bash
python tests/test_motion_sample.py
python tests/test_motion_handoff.py
python tests/test_real_source_duration.py
python tests/test_s4_stages.py
python scripts/dev_check.py
```

绿灯证明契约成立,不证明真实样片存在或可用。

## 7. B-roll 优先制作(标准视频路径)

带口播的 VIDEO 项目不得退化为静态文字卡幻灯片。默认路径是**已登记的真实素材当主画面**,
由口播驱动镜头选择、运镜与镜头时长。

### 7.1 必须成立的默认值

| 设置 | 必守默认值 | 强制处 |
|---|---|---|
| 配音 | 账号 DNA 里的 MiniMax M Plan 克隆音色。SAPI 仅是显式诊断选项;缺 DNA 时绝不可静默降级为离线机械音。 | `m5_production.build` 回退(`or "minimax"`);`stage_narration(provider="minimax")` |
| 画布 | 账号已审核的 `visual.motion.motion_profile.render_variant`,而非深蓝 `brand.palette`。账号声明一次,换风格无需改代码。 | `motion_planner.build_auto_plan`、`scripts/animation_render.py` 的 `style_variant` |
| 画面 | 已清权的静态素材(真实截图或生成插画)当主画面;只有没有可信真实素材时才用信息图。 | `scripts/plan_broll.py` |
| 时长 | 每镜覆盖实测口播槽(本行 start 到下一行 start),夹到 clip 2–8 秒契约。不使用固定猜测值。 | `plan_broll._line_slot` |
| 标注 | 与口播对应的 2–6 字语义关键词。绝不截断字幕原句(那样同一句会显示两遍)。 | `plan_broll._callout` |
| 证据标签 | 只有已授权的Capture才能标"证据画面";生成插画标"概念示意·不是证据";本地原创卡根本不进 B-roll 池。 | `plan_broll._usable_stills` 等级过滤 |

### 7.2 标准命令顺序

```bash
# 1. 生成 M5 项目到配音阶段,绑定账号。
python scripts/m5_production.py <project> --skip-compose

# 2. 从已登记素材 + 实测口播生成 materialized B-roll 分镜。
python scripts/plan_broll.py <project> --json

# 3. 用 materialized 分镜渲染并合成。
python scripts/m5_production.py <project>
```

`plan_broll.py` 写 `motion/broll/<line>.json`、`motion/broll-plan.json`
(schema `contentops.m5-motion-shots/v1`),并在 `project.yaml` 设置
`motion.backend: remotion` / `motion.shot_plan`。缺少已登记素材、实测口播、
账号绑定或已审核画布变体时一律 fail closed。它不渲染、不审批文案、不授权发布。

### 7.3 生成插画的权利登记

一次性登记完整字段,否则 `verify_assets` 会逐道门禁拒绝:

- `repo_path` 是**仓库根相对**(`projects/<slug>/...`),不是项目相对。
- `permission: CREATED_BY_OWNER`;`license` 与 `rights.license_id: OWNED-GENERATED-LOCAL`。
- `rights.review_evidence: assets/<id>.rights.json`,指向 `contentops.media-rights-review/v1` 记录。
- `rights.source_url: local://minimax-m-plan/image-01/<id>`(非第三方来源标识;
  `OWNED-GENERATED-LOCAL` 不要求 http URL)。
- `rights.synthetic: true`,`reviewed_by`、`reviewed_at` 两处一致。

### 7.4 机制回归测试

```bash
python tests/test_broll_workflow_mechanism.py
python tests/test_default_narration.py
python tests/test_animation_orchestrator.py
```

这些测试锁定"不静默用 SAPI、已审核画布、证据分级、关键词标注、实测时长"规则,
防止后续改动重新引入静态文字卡或机械配音。
