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
| 真实素材时长 | `src/contentops/media/real_source_duration.py`、`scripts/qc_video.py` | 按账号 DNA 的证据模式执行：`EVIDENCE_LED` 保留真实可见时长 ≥70% 门禁；`EXPLANATORY` 不以该全片比例为门禁。来源、权利、时长或账号策略缺失仍会阻断；证据与声明仍独立验证。生成与动效画面永不计作真实捕获。 |
| Driver QC 绑定 | `src/contentops/easel/driver.py` | `receipts/qc-report*.json` 在计划期由 `_step_receipts_ok` 解析;匹配但未评分或 `FAIL` 不算完成 |
| Router → brief → M5 | `src/contentops/routing/`、`src/contentops/script/`、`scripts/content_route.py`、`scripts/brief_to_m5.py`、`scripts/m5_production.py` | 账号 DNA → 候选 → 已批准 brief → `script/script.json` + claims + source refs;`copy_review.require_if_brief_driven` 拦截未审文案 |
| S4 阶段策略 | `src/contentops/workflow/{audience,duration,copy_strategy,platform,delivery,visual_route}.py` | 受众/时长/策略/平台限制、人工交付清单与视觉路由;不授予发布权 |
| 图文工作流适配器 | `src/contentops/gzh/runtime.py`、`src/contentops/xhs/runtime.py`、`scripts/graphic_workflow.py` | 定位/哈希校验/描述本地安装的 GZH 或 XHS 工作流;GRAPHIC_TEXT 人工包表面;不执行、不拟稿、不发布 |
| Huashu Motion 适配层 | `src/contentops/media/huashu_motion.py`、`scripts/huashu_motion_adapter.py`、`runtime/huashu-motion.lock.json` | 校验固定版 v0.3.1 运行时,用上游自己的语法描述 `om check`/`om still`/`om render`/`om qa`,写「已阻止/未执行」回执;从不拼接 `om` 命令行,也从不启动引擎 |
| Huashu 动效统一记录 | `src/contentops/media/huashu_motion.py`(`contentops.huashu-motion-asset/v1`) | 两个引擎共用一份记录:`engine/version/commit/spec_sha256/asset_hashes/clip_path/clip_sha256/duration/resolution/fps/audio_policy/rights/review_status`,始终 `generated=true`、`evidence_capable=false`、`production_ready=false` |
| Huashu 动效 → M4.5 | `src/contentops/media/motion_manifest.py`、`src/contentops/media/manifest_m5_bridge.py` | 通过校验的片段变成源回执 + 无音轨派生片段 + 唯一活动时间线 placement;片段缺失、哈希不符、字节被改或 `KEEP` 策略一律拒绝 |
| Huashu 受管执行 | `src/contentops/skills/huashu_execution.py`、`scripts/huashu_execute.py` | 先校验运行时,再读批准,再判定,再重读,再消费一次使用额度,最后执行;运行时不可用时直接拒绝且不消耗额度;上游调用是注入的,不是拼接出来的 |

### 图文与编辑部工作流(GZH / XHS / X)

GZH 与 XHS 工作流由操作者安装在公开仓库之外,仓库不 vendored 它们。X 是本仓库
自己的、仅人工的编辑部门禁。`scripts/graphic_workflow.py` 是唯一入口
(`status`、`verify`、`plan`,`--workflow gzh|xhs|x`):校验工作区或锁,然后描述
操作者步骤。它绝不执行工作流步骤、不调用平台 API、不启动 Easel host、不拟稿、
不发布。GZH/XHS 使用 GRAPHIC_TEXT 人工包,停在 `AWAITING_MANUAL_REVIEW`;X 使用
人工发帖包。

权利:XHS 根目录为 Apache-2.0,但有一个 AGPL-3.0 skill 必须排除;GZH 的 50 个
skill 中有 45 个无许可,在清权前只允许本地内部使用。通过校验不等于再分发许可。

## 3. 命令

```bash
python scripts/check_motion_sample.py <sample.mp4> [--sha256 <hex>]
python scripts/graphic_workflow.py status --workflow gzh|xhs|x
python scripts/graphic_workflow.py plan   --workflow x --json
python tests/test_motion_sample.py
python tests/test_motion_handoff.py
python tests/test_real_source_duration.py
python tests/test_s4_stages.py

python scripts/content_route.py accounts
python scripts/brief_to_m5.py --check projects/<slug>
python scripts/m5_production.py projects/<slug>
python scripts/qc_video.py projects/<slug> --video <slug>.mp4
python scripts/qc_visual.py projects/<slug> --video <slug>.mp4

python scripts/huashu_motion_adapter.py status
python scripts/huashu_motion_adapter.py plan render
python scripts/huashu_motion_adapter.py request render --project projects/huashu-motion-sample
python scripts/huashu_execute.py check projects/huashu-motion-sample --operation render --account x-superplay-1024
python tests/test_huashu_motion_sample.py
python tests/test_huashu_motion_manifest.py
python tests/test_huashu_execution_gate.py
```

动效交接**故意没有 CLI**:它是调用方在把资产放上唯一活动时间线之前验证的契约。
通过验证的记录不会自动进入 M5。

## 3.1 两个 Huashu 引擎

`huashu-motion`(上游 `alchaincyf/huashu-motion`)与 `huashu-art-motion`(上游
`alchaincyf/huashu-art-motion`)是两个独立程序、两个独立运行时。ContentOps 把它们
作为**片段生产者**接入,而不是第二套合成器:Easel 仍然是唯一合成器。

接入保证:

- 每个引擎一份运行时固定记录,放在 `runtime/`,核对版本、commit、Git remote、干净
  工作树、入口与许可证。文件缺失、路径越界、版本漂移、工作树不干净是四种不同
  的判定。
- 两个引擎共用一份资产记录(`contentops.huashu-motion-asset/v1`),消费方读时长或
  摘要时不必按引擎分支。
- 两个引擎共用一道技术门(`check_motion_clip`):静音、1080×1920、H.264/yuv420p、
  由帧时间戳验证恒定 30 fps、哈希绑定。技术通过仍然是 `PENDING_FOUNDER_REVIEW`。
- 进入 M4.5 只有一条路:通过校验的片段变成源回执和无音轨派生片段,只有派生片段
  可以被激活到时间线上。
- 生成动效保持 `generated=true`、`evidence_capable=false`。只有当独立的 `ClaimLedger` 已验证事实主张时，生成画面才可以作为该事实句的补充视觉；素材本身不得有 `claim_refs`、`evidence_use: EVIDENCE` 或证据能力标志。M5 会拒绝这些相互矛盾的声明。
- 真实 manifest 驱动的 M5 合成会拒绝来源回执中权利未解决或信息不全的生成动效。Fixture 资产只有在项目明确标记 `fixture: true` 时才能通过；回执仍只属于测试夹具，不授予发布或生产就绪状态。

它不做的事:不启动 `om`,不拼接上游命令行,不安装运行时,不合成。真实渲染需要 Owner
的批准记录;申请见 `docs/governance/HUASHU-EXECUTION-AUTHORIZATION-REQUEST.md`。

固定版本 `skills/huashu-motion/references/contract.md` 要求 composition root 声明
`data-composition-id`、`data-width` 和 `data-height`；暂停的 GSAP 时间轴注册在
`window.__timelines[composition-id]`；场景标签使用 `scene:<id>`。`data-om-id` 只标记
可指向区域。当前 CSS keyframes 草稿缺少这些原生结构，已明确标为
`NOT_HUASHU_MOTION_COMPATIBLE`；不得对其运行任何 `om` 命令。固定版合约/运行时要求
时间驱动渲染具确定性，但草稿没有已注册的暂停时间轴，因而无法提供该行为。`om render
--silent` 只抑制“无配乐”警告，不能证明导出文件没有音轨；渲染或执行现有
`AudioPolicy` 转换后，必须用 ffprobe 检查实际音轨。

### 已准备好的样片

`projects/huashu-motion-sample` 是一支 21 秒样片的**设计**,不是成片:分镜与节奏
表、一份统一视觉规范、六份 Art Motion 片段 Spec、Huashu Motion HTML 概念草稿,以及
M4.5 素材映射。第一镜 Art Motion Spec 为 4.0 秒,其余五镜各 3.4 秒。这样准备了
4–8 秒首个 motion-sample 候选,没有改动 `motion_sample.py`;其余镜头走普通片段门,
不走样片门。Huashu Motion HTML 在按原生契约重写前仍不兼容。没有渲染任何一帧,
状态仍是 `RENDER_NOT_VERIFIED`。题材是原创抽象 AI Agent 工作流,不使用真实截图或
第三方素材。


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
