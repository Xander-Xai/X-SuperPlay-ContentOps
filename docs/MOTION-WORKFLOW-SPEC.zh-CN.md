---
translation_of: docs/MOTION-WORKFLOW-SPEC.md
language: zh-CN
translation_status: synced
---

# 动效工作流规范

[English](MOTION-WORKFLOW-SPEC.md) | [简体中文](MOTION-WORKFLOW-SPEC.zh-CN.md)

> 双账号视频工作流的可执行契约。记录 `main` 上代码**实际强制**的内容,不是愿望。
> 根目录的 `VIDEO-WORKFLOW-OPTIMIZATION-PLAN.md` 是 Owner 草稿;本文件是代码与 CI
> 指向的规范版本。

## 1. 边界

- **Easel v0.2.1 是唯一合成器。** MotionClone 是外部工具,只通过 handoff 记录提供
  一段自有的短片段;不复制其代码,不与 `media-use` 0.8.222 混用运行时。
- VIDEO 与 GRAPHIC_TEXT 是两条独立产线;本规范只覆盖 VIDEO。
- 本规范不授权 provider 花费、凭据使用、依赖安装、升级或发布。

## 2. 已交付契约

| 契约 | 代码 | 强制内容 |
|---|---|---|
| 动效样片门 | `src/contentops/media/motion_sample.py`、`scripts/check_motion_sample.py` | 4–8 秒、静音、1080×1920、H.264/yuv420p、**由帧时间戳验证 CFR 30**、SHA-256 绑定;`TECHNICALLY_CHECKED` 仍是 `PENDING_FOUNDER_REVIEW` |
| 动效交接 | `src/contentops/media/motion_handoff.py` | 仅 `project://`、哈希绑定的 MP4、MotionClone 2.0.0 / HyperFrames 0.8.33、工程哈希、源窗口 ≤8 秒、仅内部权利、所有权限标志为 false |
| 真实素材时长 | `src/contentops/media/real_source_duration.py`、`scripts/qc_video.py` | 成片可见秒数中 ≥70% 为真实拍摄;图解、卡片、生成与动效不计,重叠只算一次 |
| Driver QC 绑定 | `src/contentops/easel/driver.py` | `receipts/qc-report*.json` 在计划期由 `_step_receipts_ok` 解析;匹配但未评分或 `FAIL` 不算完成 |
| Router → brief → M5 | `src/contentops/routing/`、`src/contentops/script/`、`scripts/content_route.py`、`scripts/brief_to_m5.py`、`scripts/m5_production.py` | 账号 DNA → 候选 → 已批准 brief → `script/script.json` + claims + source refs;`copy_review.require_if_brief_driven` 拦截未审文案 |
| S4 阶段策略 | `src/contentops/workflow/{audience,duration,copy_strategy,platform,delivery,visual_route}.py` | 受众/时长/策略/平台限制、人工交付清单与视觉路由;不授予发布权 |
| 图文工作流适配器 | `src/contentops/gzh/runtime.py`、`src/contentops/xhs/runtime.py`、`scripts/graphic_workflow.py` | 定位/哈希校验/描述本地安装的 GZH 或 XHS 工作流;GRAPHIC_TEXT 人工包表面;不执行、不拟稿、不发布 |

### 图文工作流(GZH / XHS)

GZH 与 XHS 工作流由操作者安装在公开仓库之外,仓库不 vendored 它们。
`scripts/graphic_workflow.py` 是唯一入口(`status`、`verify`、`plan`,
`--workflow gzh|xhs`):校验锁中的字节与身份,然后描述操作者步骤。它绝不执行
工作流步骤、不启动 Easel host、不拟稿、不发布。GRAPHIC_TEXT 表面是人工包,
停在 `AWAITING_MANUAL_REVIEW`。

权利:XHS 根目录为 Apache-2.0,但有一个 AGPL-3.0 skill 必须排除;GZH 的 50 个
skill 中有 45 个无许可,在清权前只允许本地内部使用。通过校验不等于再分发许可。

## 3. 命令

```bash
python scripts/check_motion_sample.py <sample.mp4> [--sha256 <hex>]
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
- 在人签署之前,始终 `production_ready: false`、`human_review: PENDING_FOUNDER_REVIEW`。
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
| 两条真实 A/B 样片 | 真实任务录屏 / 可复现 RAG 项目及已清权的源窗口 |
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
