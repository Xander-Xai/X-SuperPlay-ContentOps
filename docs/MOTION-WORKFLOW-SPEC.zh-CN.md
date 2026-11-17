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
| 图文工作流适配器 | `scripts/graphic_workflow.py`、`src/contentops/gzh/runtime.py`、`src/contentops/x/runtime.py` | 仅 GZH 与 X;定位/哈希校验/描述及人工包表面;不执行工作流、不调用平台 API、不拟稿、不发布。XHS 图文适配器已移除;小红书属于 VIDEO 交付线。 |

### 图文与编辑部工作流(GZH / X)

GZH 工作流由操作者安装在公开仓库之外,仓库不 vendored 它。X 是本仓库
自己的、仅人工的编辑部门禁。`scripts/graphic_workflow.py` 接受 `gzh`、`x`、`video`;
图文/编辑部入口仅为 `gzh` 和 `x`(`status`、`verify`、`plan`)。它校验工作区或锁,
然后描述操作者步骤。`video` 路由列出支持的视频目标,不执行平台工作流;使用 `--handoff --project <path>` 时,会调用 `scripts/video_deliver.py pack` 与
`dispatch`,针对路由导出的所有受支持视频平台 ID（包括小红书）构造多平台交付包和
分发 argv。handoff 仍设置 `execute=false`、`publish_authorized=false`:不运行上传器,
也不授权发布。GZH 使用 GRAPHIC_TEXT 人工包,停在 `AWAITING_MANUAL_REVIEW`;X 使用人工发帖包。
XHS 没有图文适配器或 CLI 路由;小红书只作为 VIDEO 交付目标。

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
- 必须在人审通过前保持 `production_ready: false`、`publish_authorized: false`、
  `human_review: PENDING_FOUNDER_REVIEW`。技术 PASS 或渲染完成不是 Founder 验收或发布授权。
- 对账号 `x-superplay-1024`，DNA 中 70% 真实录屏配比是内容目标。独立的真实素材时长门
  衡量成片中可见的获权真实来源素材（录屏、截图、文档、日志等）；不要求所有计入时长
  都是录屏。正式生产另要求登记真实裁切录屏。两个门都不能按镜头数量替代。
- 对 `x-superplay-future-intelligence`，禁止手工桌面录屏；无最低录屏时长要求。不得以桌面捕获
  替代图解或代码聚焦视觉。
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
