# PRD — 动画 Skill 与多引擎短镜头接入

[简体中文](PRD-ANIMATION-SKILLS-INTEGRATION.md) | [English](PRD-ANIMATION-SKILLS-INTEGRATION.en.md)

> Last verified: 2026-11-17
> 状态：**各后端/模板的验收状态须按当前源模板分别判断；生产与发布仍未授权。** 本机运行时检测和历史渲染不等于所有机器上的普遍安装状态,CI 合同测试也不等于真实媒体验收或正式就绪。Remotion、Manim、Huashu 与 Motion Canvas 的实际验收证据/限制分别见下文。Motion Canvas 的 `mc-arch01` 导出只证明当时模板的历史媒体验收；当前模板源已变化,`capability-matrix-after-export.json` 明确为 `STALE_SOURCE_TEMPLATE`,必须从当前源模板重新由编辑器导出并复验。`mc-state01` 仍必须由编辑器导出。任何状态都不授予生产、发布或人审批准。

## 1. 背景、目标和非目标

ContentOps 已经有冻结的 Easel v0.3.0 总合成、Huashu 解释性片段、证据门和双账号 DNA。缺的是按镜头类型选择代码动画后端，并把短镜头交回现有时间线。

目标：以 Easel 为唯一成片合成器，增加可审计的短镜头渲染器。P0 是固定版本的 Remotion。Huashu 保持可用。

非目标：升级或替换 Easel；第二套总时间线；把 18 个仓库都装进依赖；把 Remotion 源码打进本仓库再分发；付费生成、自动发布、放松人审或证据占比。

## 2. 可复用的现有能力

| 已有 | 复用方式 |
|---|---|
| `scripts/m5_production.py` `stage_motion` | 显式 `remotion` 镜头改调 `scripts/animation_render.py`，不走 Huashu 自动计划 |
| `src/contentops/media/motion_sample.py` | 2–8 秒、静音、1080×1920、H.264、yuv420p、恒定 30fps |
| `motion_handoff.py` | 仍只接受 MotionClone。新后端不得冒充它 |
| `motion_planner.py` | Huashu 自动计划已扩展六种 DNA 约束的镜头模板；仍只写入现有 shot plan/spec，不新增时间线 |
| 账号 DNA | 调色板从 DNA 读取，不另写一套品牌色 |
| `recording_intake.py` | 录屏入场规则不因新后端放宽 |
| `real_source_duration.py` | 对 1024 证据主导的正式生产，按可见真实素材时长核验 ≥70% 下限；`vector_animation` 永不计入。未来智能没有录屏时长下限，且禁止手工桌面录屏。 |
| Easel `assemble_easel.run` | 仍是唯一成片合成入口 |

## 3. 18 个上游项目

审计日 2026-11-16。事实来自 `gh api`。无人归档。Remotion 许可证另读了 `LICENSE.md`：GitHub SPDX 为 `NOASSERTION` 是因为许可证是自定义的，不是“未读”。

| # | 仓库 | 是什么 | 许可证 | 最近活动 | 能否自己出片 | 结论 |
|---|---|---|---|---|---|---|
| 1 | remotion-dev/skills | Agent Skill 包，不是渲染器 | 无独立 license 对象；内容属于 Remotion 4.0.543 | 2026-11-11，tip `7e541aa` | 否 | P0 的技能层，本地安装，不入库分发 |
| 2 | motion-canvas/motion-canvas | Vite 编辑器 + 浏览器播放 | MIT | 3.17.2（2024-12-14，npm `latest`）；alpha 3.18.0-alpha.0 未固定 | 编辑器 websocket 导出，无 headless CLI | P3-B 模板与适配器已实现；`EDITOR_EXPORT_REQUIRED` |
| 3 | motiondivision/motion | React 补间库 | MIT | 2026-11-15 | 否 | REJECT |
| 4 | franciscop/ola | 数值插值 | MIT | 2026-10-24 | 否 | REJECT |
| 5 | juliangarnier/anime | JS 动画引擎 | MIT | 2026-11-02 | 否；HyperFrames 已有适配 | REJECT |
| 6 | ManimCommunity/manim | Python 数学动画 | MIT | v0.22.1，2026-10-27 | 能出视频；需要 cairo/pango | P3-A，隔离 venv 已装并本机渲染；IMPLEMENTED_NOT_VERIFIED |
| 7 | jeremyckahn/shifty | 补间引擎 | MIT | 2026-11-14 | 否 | REJECT |
| 8 | jonobr1/two.js | 2D 绘图 API | MIT | 2026-11-13 | 否 | REJECT |
| 9 | airbnb/lottie-web | 动画播放器 | MIT | 推送 2025-09 | 播放 JSON，不编码视频 | P2 |
| 10 | CreateJS/TweenJS | 补间库 | MIT | 2023-12-18 | 否 | REJECT |
| 11 | lume/lume | 3D HTML 元素 | MIT | 2026-09-08 | 否 | REJECT |
| 12 | mattdesl/gifenc | GIF 编码器 | MIT | 2024-09-19 | 只出 GIF | P2，出现 GIF 交付再装 |
| 13 | konvajs/konva | Canvas 场景图 | NOASSERTION | 2026-11-10 | 否 | REJECT |
| 14 | blender/blender | 完整 DCC | API 为 NOASSERTION，不据此猜 GPL | 2026-11-15 | 完整软件，不是短镜头助手 | REJECT |
| 15 | mrdoob/three.js | 3D 库 | MIT | r187，2026-10-30 | 否；优先以后评估 `@remotion/three` | REJECT |
| 16 | godotengine/godot | 游戏引擎 | MIT | releases 接口返回的第一条是 `3.6.3-stable`，不把它当成最新稳定版的证明 | 否 | REJECT |
| 17 | BabylonJS/Babylon.js | 游戏/渲染引擎 | Apache-2.0 | 9.36.0，2026-11-12 | 否 | REJECT |
| 18 | drawcall/Proton | 粒子库 | MIT | 2026-03-06 | 否 | REJECT |

2026-11-16 用户环境侧证：当时曾检测到 Node v24.16.0、npm 11.13.0、FFmpeg 8.1.1、Chrome 与 Edge。Manim v0.22.1 曾在隔离 venv 检测到（`runtime/manim.lock.json` 记录路径与创建命令），未安装进系统 Python。以上均仅代表该次用户环境检测，**不等于普遍安装状态或当前可用性**。

## 4. 选型与许可证

P0 选 Remotion 渲染器的历史理由：该工具可输出 MP4，且当时在用户本机检测到 Node 与 Chrome；许可证文本允许个人以及不超过 3 名雇员的营利组织用它制作视频。禁止把 Remotion 改造成再销售的衍生渲染器。因此只提交本仓库自己的模板和锁文件，不提交 `node_modules`，也不把上游源码拷进仓库。上述环境检测不代表当前或其它机器的可用性。

`remotion-dev/skills` 没有独立许可证对象。技能文件不提交到本仓库，避免把许可不清的第三方文本打进公开发布。

Motion Canvas 与 Manim 的许可证是 MIT。Motion Canvas 已接入模板和适配器，但官方导出要求从编辑器发起、没有无人值守 CLI；这限制自动化形态，不代表未接入。其当前模板媒体验收状态见第 20 节：旧 `mc-arch01` 导出因源模板变化已 stale，当前模板须重新从编辑器导出。Manim 曾在隔离 venv 通过官方 `python -m manim` 本机渲染，版本记录为 v0.22.1；渲染走 Pango `Text`，不使用 MathTex/LaTeX（历史记录称本机管理员权限下 LaTeX 会卡住）。安装运行时或旧本机渲染不等于 VERIFIED；能力矩阵只接受与当前源/状态相符的回执证据。

## 5. 实施顺序（历史阶段记录；不代表当前通用就绪状态）

| 阶段 | 历史记录 | 当前解释 |
|---|---|---|
| M0 环境 | Node、FFmpeg、Chrome 曾在用户本机核到；`npx skills add` 曾被本机权限分类器拒绝 | 仅为该次本机检测结果，不代表其他环境或当前安装状态；技能未安装记录仍是历史检测，不构成通用状态 |
| M1 Remotion | 历史记录为 4.0.543 锁文件、模板与本机渲染 | 锁文件可证明固定版本；本机渲染是历史/测试证据，不单独构成正式验收 |
| M2 Motion Canvas / Manim | 曾分别记录阻断、安装和本机渲染 | 见第 20–22 节；状态须由当前源代码与可复核回执决定 |
| M3 双账号 | 双账号合同与阻断测试曾通过 | 测试只能证明合同；真实素材、整片 QC 与 Founder 人审仍需单独完成 |
| M4 工作台 | 未做整页 UI；技能注册表有发现指针 | 不改 Easel 上游、不重写 Web UI；发现指针不授予执行权 |

## 6. 双账号策略

规则来自现有 DNA，不另写品牌配置。

1024：账号内容目标配比为 70% 真实录屏、25% 矢量动画、5% 对比卡；45–60 秒。**两个门须分开看：**账号 DNA 的 ≥70% 真实录屏是内容目标；`real_source_duration.py` 的证据主导时长门按成片可见时长计算获权真实来源素材（可包括录屏、截图、文档、日志等），不是要求这 ≥70% 全部为录屏，也不是按镜头数计算。另一方面，`production_gate()` 仍要求登记真实裁切录屏；缺失时 `purpose=production` 返回 `MISSING_REAL_RECORDING`。动画是视觉辅助，`source_kind=vector_animation`，`generated=true`，`evidence_capable=false`，`counts_as_real_recording=false`。测试用途可以渲染，回执标明不是已验收案例。

未来智能：70% 矢量动画、25% 代码片段、5% 图表；90–120 秒。**禁止手工桌面录屏**；`input_kind` 为桌面/手动录屏时 `RECORDING_FORBIDDEN`。不得以桌面捕获替代图解/代码视觉。RAG 示例字幕写明“原理示意，不是系统输出”，不含未证实的性能数字。

此处所述配比是账号内容目标；1024 的真实录屏门是正式生产硬门，未来智能不设录屏最低比例且禁止手工桌面录屏。

未声明账号：`ACCOUNT_REQUIRED` 或 `UNKNOWN_ACCOUNT`。不跨账号继承调色板。

## 7. 架构

```text
shot spec + account DNA
        |
        v
animation_backend.select_backend   # 显式引擎不静默替换
        |
        v
scripts/animation_render.py        # 只渲染一个短镜头
        |
        v
Easel assemble_easel.run           # 唯一成片合成
        |
        v
现有 QC + PENDING_FOUNDER_REVIEW
```

Huashu 仍走原来的适配器。新后端只是候选镜头素材。

## 8. 接口

`src/contentops/media/animation_backend.py`：

- `select_backend()`：账号、镜头类型、显式引擎、就绪状态、预先声明的后备
- `preflight()`：解释调用方给出的环境探针，不在库模块里拉起进程
- `plan_clip()`：参数化镜头计划
- `build_receipt()`：只接受 `project://` 路径
- `resolve_skill()`：发现不等于执行授权
- `production_gate()` 的技术放行不是生产或发布许可。即使渲染与技术 QC 成功，仍须通过真实来源/权利与证据门、整片质量验收及人工 Founder 审核；在相应人工签署和独立发布授权之前，始终保持 `production_ready=false`、`publish_authorized=false`、`human_review=PENDING_FOUNDER_REVIEW`。

进程、ffprobe 和 Remotion CLI 只在 `scripts/animation_render.py`，经 `process_utils.hidden_run`，不用 `shell=True`。

## 9. Skill 发现与安装

共享技能库 `C:\Users\Administrator\.agents\skills` 和 `~\.claude\skills` 没有被覆盖。仓库 `.claude/` 被 gitignore，不能把技能链接提交进去。

官方安装命令是 `npx skills add remotion-dev/skills` 或在 Remotion 工程里 `npx remotion skills add`。本机权限分类器拒绝了 `npx skills add`（Code from External）。因此技能层记为 **NOT_INSTALLED**，不是 PASS。

发现指针在 `runtime/skill-registry.json` 的 `contentops-remotion-clips`。`execution.authorizes_execution` 为 false。它指向本仓库自己的模板目录，不是上游技能副本。

锁文件：`runtime/remotion.lock.json`，版本 4.0.543。安装：

```text
npm install --ignore-scripts --no-audit --no-fund --prefix extensions/animation-remotion
```

不要在渲染时拉取 latest。

## 10. 与 Easel / Huashu 的关系

Easel pin 仍是 `runtime/easel-pins.json` 的 `v0.3.0` / `bb3c8ff`（实际完整 commit 见 pin 文件），且已冻结。本变更不改 `.runtime/easel-v030`。Huashu 别名 `art-motion` 与 `motion` 仍解析到原后端。未写 `motion.shot_plan` 的 `remotion` 配置不会掉进 Huashu 自动计划。

## 11. 与 M5 的关系

`stage_motion` 在镜头 `backend` 为 `remotion` 或 `motion-canvas` 时调用 `animation_render.py`；`manim` 镜头按其声明的渲染入口 `scripts/manim_render.py` 由隔离 venv 渲染，仍复用同一个 backend selector、receipt、可信缓存、M45 manifest 与资产登记合同，不建第二套系统。失败是 `M5Blocked`，不改调 Huashu。测试 `test_m5_dispatches_an_explicit_remotion_shot_to_the_clip_adapter` 断言命令行含该适配器且不含 `huashu_motion`。

## 12. 素材分类

生成动画：`generated=true`，`evidence_capable=false`，`evidence_use=VISUAL_SUPPORT`，`source_kind=vector_animation`。权利字段是 `GENERATED_LOCAL_NO_COMMERCIAL_CLEARANCE`，不是已确认的商业授权。

## 13. 平台适配

不新建平台表。继续用 `config/platforms/video-platforms.yaml` 和 `scripts/platform_adapt.py`。本变更不把未启用平台改成 ACTIVE，也不把封装成功写成发布成功。`x-superplay-english` 不是第三个视频品牌。

## 14. 安全与人审

授权范围内：本地非付费渲染、项目级 npm 依赖、本仓库代码。未做：升级 Easel、改凭据、MiniMax 调用、自动发布、下载大型模型、关闭人审。技术 QC 通过后 `human_review` 仍是 `PENDING_FOUNDER_REVIEW`，`production_ready` 与 `publish_authorized` 保持 false。

## 15. 测试

本轮历史测试记录：`tests/test_animation_backend.py` 曾注册到 `.github/workflows/ci.yml` 且不渲染视频。历史 PR #188 基线为 56/56；曾记录 Huashu 集成 58/58、真实素材时长 19/19。以上是对应时间/提交的测试结果，不证明当前代码、当前真实媒体或正式生产就绪。

## 16. 验收

| 项 | 状态 | 证据 |
|---|---|---|
| 18 项调研 | 历史记录 | 本文第 3 节 |
| PRD | 文档记录 | 本文件与英文镜像 |
| Remotion skills 安装 | 历史检测为拒绝 | `npx skills add` 曾被拒绝；不可推断当前或其它机器安装状态 |
| Remotion 渲染 | 历史本机 TEST_ONLY 证据 | 本机样片不构成正式验收 |
| Motion Canvas | `STALE_SOURCE_TEMPLATE` | `mc-arch01` 旧导出/矩阵仅是历史证据；当前模板需重新编辑器导出并验收，`mc-state01` 也须编辑器导出 |
| Manim | 历史 TEST_ONLY / `IMPLEMENTED_NOT_VERIFIED` | 隔离环境曾渲染；不等于通用安装或正式就绪 |
| 1024 规则 | 合同记录 | 正式生产缺真实录屏仍 `MISSING_REAL_RECORDING`；测试片段不算录屏 |
| 未来智能规则 | 合同记录 | 手工桌面录屏 `RECORDING_FORBIDDEN` |
| M5 接线 | 代码/测试记录 | 调度通过不代表媒体验收 |
| Easel | 当前 pin `v0.3.0` / `bb3c8ff` | pin 已冻结；不推断运行时普遍安装 |
| 人审与安全 | 强制边界 | `production_ready=false`，`publish_authorized=false`，Founder 人审待完成 |

**以下 Remotion、Manim 与 Huashu 输出记录均为历史本机/TEST_ONLY 产物。** 它们只说明当时曾生成并登记的内容，不证明当前机器仍可用、来源证据已验证、整片生产 QC 已通过或已具备发布就绪状态。

| 片段 | 路径 | sha256 | ffprobe |
|---|---|---|---|
| 1024 标注测试 | `projects/_local/animation-1024-sample/assets/generated/remotion/clip-annotation.mp4` | `4c31e531dbed90070b5d61159acf56f07a70d56a009167cbd1d483ac11327b62` | h264, 1080x1920, yuv420p, 30/1, 4.000s, 无音轨 |
| 未来智能 RAG | `projects/_local/animation-fi-sample/assets/generated/remotion/clip-rag.mp4` | `417019d985f440b4f910f91ed37192118353e01c1b0a5f66b78ca67568c067c0` | h264, 1080x1920, yuv420p, 30/1, 6.000s, 无音轨 |

回执：`project://receipts/animation-clip-annotation.json` 与 `project://receipts/animation-clip-rag.json`。没有主机绝对路径。

## 17. 风险与回滚

风险：Remotion 免费许可证只覆盖符合资格的主体；若组织超过 3 名雇员，必须先取得公司许可证再渲染。Chrome 启动在 Windows 上需要 `--gl angle`，已写入适配器。`yuvj420p` 会被样本门拒绝，转码强制 `yuv420p` 与 `color_range tv`。

回滚：删除本分支对 `stage_motion` 的调度分支，并移除 `extensions/animation-remotion` 与锁文件。Huashu 与 Easel pin 不依赖这些文件。`npm` 卸载是删掉该目录的 `node_modules`，不要动 `.runtime/easel-v030`。

故障：`RUNTIME_MISSING` 表示未执行上面的 npm 安装或没有 Node/FFmpeg/浏览器。`VERSION_MISMATCH` 表示锁文件不是 4.0.543。`RENDER_FAILED` 时看 `projects/<slug>/work/animation/*.render.log`。不要把静态图当成渲染成功。

## 18. DNA 驱动的 Huashu 镜头模板（Issue #192）

本轮把 Huashu Art Motion 纳入同一条 M5 shot-plan/spec 链，不创建第二 timeline、资产注册表或合成器。`motion_planner.py` 以 `brand.palette` 为有效 DNA 调色板；palette、刷新声明及视觉输入进入计划指纹。旧 `motion_profile.style_variants` 不得覆盖已声明的品牌色，品牌刷新目标不支持时 fail-closed。

六类显式 `animation_type`：

| 模板 | Huashu grammar | 参数与拒绝边界 |
|---|---|---|
| `architecture_flow` | `y3_whiteboard` | 2–6 个节点，逐个绘制并连单向流程箭头 |
| `state_transition` | `y3_whiteboard` | 2–5 个状态，必须同时声明 transition、success、failure 分支 |
| `code_focus` | `t2_keynote_ui` | 仅接受带 `source_document_sha256` 的 `CODE_SNAPSHOT` 图片和有界 focus rect |
| `evidence_zoom` | `t2_keynote_ui` | 只接受已登记真实静帧与来源区域；未来智能拒绝录屏输入 |
| `metric_transition` | `t3_finance_chart` | JSON 来源记录必须与 title、unit、citation、每个 label/value 完全相同；只允许 bar/line |
| `comparison_reveal` | `y3_whiteboard` | before/after 两个显式标签，使用交叉/确认图标 |

所有模板都要求登记素材、仓库内路径、字节 SHA-256、permission 与 claim/source_refs 或 `editorial_only=true`。输出 spec 记录 `animation_type`、`source_asset_id`、claim/editorial 关系及来源哈希；品牌色和来源变化会使对应 spec 缓存失效。生成动画的 `visual_role` 固定为解释性，不能声明为 proof；动画仍是 `generated=true`、`evidence_capable=false`、`evidence_use=VISUAL_SUPPORT`，真实来源的 claim gates 独立验证。1024 的 `EVIDENCE_LED` 70% 可见真实素材时长门不被 `tech_review` 等内容类型放宽；未来智能解释型内容不强制录屏，但事实仍须有来源。

**本轮验收边界：**六类模板合同与拒绝测试通过。公共规划器现仅对 `y3_whiteboard` 暗色画布（相对亮度 < 0.25）且 ink/background 对比低于 3:1 的绘图文字，改用账号 DNA 明确声明且对比达到 3:1 的 `surface` token；其它颜色保持原值。`t2_keynote_ui` 浅色代码卡和已可读白板不变；缺少合格 token 时 fail closed。planner 源哈希进入 plan identity，调整后的 spec 字节进入现有 Huashu 单镜头缓存指纹；实际调整写入 `contentops_scene.readability_adjustment`，记录原/新 ink、背景及前后对比度。两账号新项目规划测试覆盖了 1024 与未来智能；另在 `projects/_local/animation-readability-20261117/` 生成一个 5 秒未来智能真实 Huashu 短镜头：源 SHA-256 `fc3863e64a7947ea7484f7f2b9298532d0a15392dfee1d7ef3b7d119676d7bb8`，spec SHA-256 `7d3096ad2471d8e6f80a14c09f0d5a6626cc3d0c428934708ca318e872c40554`，H.264/1080×1920/yuv420p/30fps/150 帧/无音轨，片段 SHA-256 `dc1e4c5240e5330985fcd35df36b3143764160978f798645ef8affc057e8057c`，短样片技术 QC `TECHNICALLY_CHECKED`。该片已由 Easel v0.3.0 合成，合成片 SHA-256 `e4a91c30ddfcdcf0e7902ffee64de7f4bc655d273fd27bb6cae9cbb6d12ac5fb`，短样片技术 QC 通过。该实验的 `receipts/readability-lineage.json` 将旧 99 秒记录（原 SHA `66ca2673dd915fad41bb6acde1396e5017be17b09bbde389538abc4f4cd24905`、历史参数重渲 SHA `3aafc7290e16f8f28b08f858dab9a6df5757518ae53abd924684f434ed1f3511`）与本次 5 秒 spec/片段/合成片 SHA 关联；旧媒体与旧回执未覆盖，但当前不可访问，旧 SHA 仅为历史记录，未在本轮复验。帧的人工可读性复核仍待完成；这不是整片 production QC 或发布验收。M5 motion integration 为 61/61，源锚点回归为 6/6。1024 正式生产仍需要真实录屏。所有输出继续保持 `production_ready=false`、`publish_authorized=false`、`human_review=PENDING_FOUNDER_REVIEW`。
## 19. DNA 冲突式标题镜头与可信渲染缓存（2026-11-17）

本节独立于 Issue #192 / PR #193 跟踪的 Huashu 六模板工作，不新增第二时间线，也不新增品牌配置。

**冲突式标题镜头。** `title_card` 此前已在 `SHOT_COMPATIBILITY` 声明，但没有 composition 和渲染路由。`extensions/animation-remotion/src/TitleCard.tsx` 补齐这一空白：面向 1024 账号的 3 秒冲突钩子镜头。所有颜色都从账号 DNA 调色板解析（`animation_backend.palette_from_dna`），包括从 `brand.palette.problem` 复制的 `problem` 令牌。镜头 spec 不能注入颜色或证据声明——`plan_clip` 在规划前丢弃 `claim`、`source_refs`、`recording_asset_id` 与任何录屏路径，该镜头始终为 `generated=true`、`evidence_capable=false`、`counts_as_real_recording=false`。动效只有淡入/位移，符合两账号的 `forbidden_effects`。逐帧检查发现正文用 `ink` 令牌压在 DNA 深色底上不可读，正文已改用 DNA 的 `surface` 令牌；组件内没有硬编码颜色。

**可信渲染缓存。** `animation_render.py` 此前会计算指纹但从不据此跳过渲染（`reused` 恒为 False）。`animation_backend.clip_fingerprint` 现在绑定后端版本、模板、账号、placement、资产、用途、时长、props、完整 DNA 摘要、引用来源摘要，以及 composition 源码摘要（`src/*.tsx` + `package.json`）。只有当新指纹与 sidecar 一致、文件实际 SHA-256 仍等于记录值、样本仍通过 `check_motion_sample` 时，才会复用缓存。仅凭文件名命中永远不成立。DNA、参数、来源、模板或版本任一变化都会使缓存失效。

**本机验证（2026-11-17，Remotion 4.0.543、Chrome、FFmpeg 8.1.1）：**

| 样片 | 模板 | 路径（逻辑） | SHA-256 | ffprobe |
|---|---|---|---|---|
| 1024 冲突钩子 | `title_card` | `project://assets/generated/remotion/clip-title-hook.mp4` | `9c1b5d54f7e5d55bd4251a8eb740cf032f48734da52e7ace18f1cda098a8657c` | h264, 1080x1920, yuv420p, 30/1, 3.000s, 无音轨 |
| 未来智能 RAG | `rag_flow` | `project://assets/generated/remotion/clip-rag-fi.mp4` | `c9582e235e103d948cef0c62e5ea961eb577a7a62afba3dc750c97e121ce9730` | h264, 1080x1920, yuv420p, 30/1, 6.000s, 无音轨 |

`python tests/test_animation_backend.py` 通过 34/34。`tsc --noEmit` 通过。同一命令重渲返回 `state=REUSED, reused=true` 且 SHA 不变；把 `duration_s` 由 3 改为 4 返回 `EXECUTED` 并产生新指纹与新 SHA；修改模板源码使标题镜头缓存失效并强制重渲。修复前后都抽取了帧做肉眼检查。

**验收边界。** 两个样片均为 `purpose=test`、`TEST_PURPOSE` 门控、`production_ready=false`、`publish_authorized=false`、`human_review=PENDING_FOUNDER_REVIEW`。当前没有用户提供的 1024 真实录屏，因此 1024 正式生产仍为 `MISSING_REAL_RECORDING`。未来智能 RAG 节点是原理示意（`原理示意，非真实系统输出`），不是真实系统轨迹。未合成任何整片，未发布任何视频。

### 19.1 合并前加固（2026-11-17，同一分支）

PR #195 复查发现并修复三个问题，未新增功能：

1. **缓存复用不再跳过 M5 登记。** 缓存命中时按可信 MP4 的指纹与磁盘 SHA-256 审计 canonical receipt 及 `sources/assets.json`、`script/assets.json`、m45 媒体清单。缺失或过期的行通过重跑既有幂等 `register_generated_clip` 修复并重新审计；已存在但与字节矛盾或抬高 `generated`/`evidence_capable`/`production_ready`/`publish_authorized`/人审状态的行 **BLOCKED**，绝不静默覆盖。`REUSED` 现带 `registration_repaired` 与修复行名。canonical receipt 带 `fingerprint`，sidecar 带 `source_spec` 以便修复时忠实重建。
2. **缓存身份覆盖全部真实输入。** `_template_digest` 现哈希 `package.json`、`package-lock.json`、`tsconfig.json` 与所有 `src/**/*.tsx|ts`；`_source_digests` 递归收集嵌套 props 中的 SHA-256 引用。锁文件变化、嵌套组件、藏在列表里的来源哈希现在都会使缓存失效。
3. **TitleCard 遵守 DNA 版式。** `hook_visual_contract` 从账号 DNA 派生字体、字号、18 字行上限、120px 上下边距与 0.07 侧边距；镜头 spec 的字体/边距/动效覆盖被剥离，超过行上限 3 倍的钩子文案被拒绝（`DNA_VISUAL`）。正文用 DNA `surface` 令牌保证深色底对比度。正式生产 spec 不能注入测试横幅。

验证：`test_animation_backend.py` 37/37，新增 `tests/test_animation_cache_integrity.py` 11/11（逐一删除/篡改每个登记文件），`tsc --noEmit` 通过。真实 TEST_ONLY 渲染：长钩子 3s 片段 SHA-256 `18556d0894c2f8798c4c106978fa651e00807109467f9b4cb4571abf40f48c6a`、刷新后钩子片段 `62d2f2b20ea7f7b5d762ffc4b760bdad2bf734a7e1636e2183b374495cc10e6e`，均 h264/1080x1920/yuv420p/30fps/无音轨；抽帧确认换行、安全边距与可读对比。验收边界不变：TEST_PURPOSE、production_ready=false、publish_authorized=false、人审待定。

### 19.2 多镜头共享清单合并（2026-11-17，同一分支）

PR #195 复查发现：`register_generated_clip` 每次用 `[envelope]` 整文件重写 `work/m45/remotion-media-manifest.json`，而 19.1 的登记审计又要求当前镜头存在于该清单。同一项目连续生成 A、B 两个镜头时，后者覆盖前者，缓存命中反复触发 REPAIRABLE，修复互相破坏（ping-pong）。先用现有逻辑真实复现（两个 asset_id、两个 placement，真实渲染 A→B→A→B）：B 登记后 A 的 envelope 消失，A 缓存命中修复后又轮到 B 消失；MP4、来源行与 canonical receipt 因走合并逻辑全部保留，损失仅限共享清单。

修复沿用 M5 单一素材清单与时间线合同，未引入第二套系统：`register_generated_clip` 现在把当前 envelope 按 `asset_id` 合并进既有清单——同 id 原位替换（保持声明顺序与时间线稳定选择），其余 envelope 与 gate_states 原样保留，时间线由 `build_manifest`/`build_timeline` 重建（每 placement 恰好一个活动资产），`scheduling`/`narration` 保留。三类异常 loud-fail 并由渲染修复路径报 `REGISTRATION_REPAIR_FAILED` BLOCKED：清单不可解析（`MEDIA_MANIFEST_UNREADABLE`，损坏文件原样保留待人工处理）、其他资产缺门控状态（`MEDIA_MANIFEST_GATE_MISSING`）、不同 asset_id 争用同一输出路径（`MEDIA_MANIFEST_PATH_COLLISION`）。

回归（`tests/test_animation_cache_integrity.py` 新增 10 项，21/21）：A,B,A,B 连续登记与审计全程 CONSISTENT；A,B,C 三镜头各占时间线槽位；改 B 指纹不使 A 缓存失效；删 A 登记修复后 B 的四件记录行字节不变；证据提升在合并后仍 BLOCKED；同一 placement 始终单活动资产；同镜头重复登记字节级幂等；修复前旧单镜头清单原地升级且保留 scheduling/narration。真实管线复现前后对比：修复前 `repeated_repairable=true`、`repair_mutual_harm=true`；修复后清单全程双登记、两次缓存重放 `registration_repaired=false`、双方审计 CONSISTENT。

## 20. 统一后端能力矩阵（2026-11-17）

`animation_backend.capability_matrix()` 在既有 backend selector 合同上扩展出一份可执行能力表（schema `contentops.animation-capability-matrix/v1`），不再平行维护另一份能力清单。六个后端 `remotion`、`remotion-three`、`huashu-art-motion`、`huashu-motion`、`manim`、`motion-canvas` 各自记录：运行时版本与来源、锁文件、安装环境、支持 shot_type、模板、渲染入口、输入/输出合同、输出规格、许可证字段、适用账号、阻断状态、是否整片合成器。每行 `is_compositor=false`；`remotion-three` 复用 `scripts/animation_render.py` 渲染入口，是 Remotion 内的 3D composition，不是新合成器。P3-B 扩展：`motion-canvas` 的渲染入口为 `scripts/motion_canvas_adapter.py`，新增 `export_mode` 字段（Motion Canvas 为 `EDITOR_EXPORT_REQUIRED`，其余为 `HEADLESS`），模板为 `animated_system_graph` 与 `agent_state_machine`。

**当前状态**：`projects/e2e-p3-motion-canvas/receipts/capability-matrix-after-export.json` 的 `current_status` 为 `STALE_SOURCE_TEMPLATE`。旧 `mc-arch01` 导出只支持该旧模板的历史验收，当前模板需重新从编辑器导出与复验；`mc-state01` 仍必须编辑器导出。后端矩阵历史 `VERIFIED` 不等于当前模板已验收，也不授予执行、生产或发布权限。

**可信边界**：矩阵读取锁文件只得到「版本/安装」事实，绝不据此把后端标成 VERIFIED。只有调用方传入带 `verified_at`、`sha256` 与 `receipt` 的 `render_evidence` 才能将该后端标为 VERIFIED；当前存在阻断码（`block_state`）时阻断优先于历史回执。所有行 `execution_authorized=false`、`publish_authorized=false`、`production_ready=false`。`tests/test_animation_backend.py` 40/40（历史记录，不代表当前媒体验收）。

## 21. P3-B Motion Canvas 接入（历史实现与验收记录；当前状态已过期）

> 本节保留实现背景与历史证据。当前源模板状态以第 20 节和回执为准：`STALE_SOURCE_TEMPLATE`。旧 `mc-arch01` 导出/矩阵状态不表示当前模板验收；重新验收必须从当前模板经编辑器导出。`mc-state01` 也必须编辑器导出。

- 本节详细模板/本机渲染/缓存/阶段/矩阵文字含历史记录，不能覆盖本节标题、回执 `current_status=STALE_SOURCE_TEMPLATE` 或上述生产边界。特别是旧 `mc-arch01` 的 `REAL_MEDIA_VERIFIED`、旧矩阵的 `VERIFIED`、CI 的合同测试，以及本机运行时信息均不代表当前模板已验收或适用于所有环境。


- `extensions/motion-canvas/` 是最小可运行工程：Motion Canvas 全家桶固定为 3.17.2（npm registry `latest`，发布 2024-12-14），npm lockfile 入库，`node_modules` 不入 Git。官方 `@motion-canvas/ffmpeg` exporter 已在 `vite.config.ts` 注册；1080x1920 / 30fps / sRGB 写在 `src/project.meta`。
- 两个模板：`animated_system_graph`（组件按步骤出现、单向箭头连接、逐步解释）与 `agent_state_machine`（状态、条件分支、失败回退）。颜色全部来自账号 `brand.palette`；失败色只在失败步出现，下一步恢复品牌色；不使用弹跳、频闪、贴纸或炫目转场。`tsc --noEmit` 与 `vite build` 通过，但这只是编译证据，不是渲染。
- `scripts/motion_canvas_adapter.py` 复用既有 receipt、fingerprint/缓存、M45 清单、资产登记与 QC，不建第二套系统。`--preflight`/`--prepare` 产出带原始证据与修复条件的 `EDITOR_EXPORT_REQUIRED` 回执；`--import-editor-export` 只接受项目内真实编辑器导出 MP4，经技术检查后才登记。
- e2e：`projects/e2e-p3-motion-canvas/`（TEST_ONLY）。`tests/test_p3_motion_canvas.py` 16/16 并已接入 CI。`mc-arch01` 的真实编辑器导出已回灌：SHA-256 `8741f5c56612f712a296e9a4cb347366b63b310badf07fc1a191af6610d238e1`，h264 / 1080x1920 / yuv420p / 30/1 / 7.233s / 217 帧 / 无音轨，首/中/末帧与 QC 已登记；`mc-state01` 仍为 `EDITOR_EXPORT_REQUIRED`。CI 不携带 gitignored 外置 MP4 时报告 `REAL_MEDIA_NOT_RUN`，合同测试通过不等于真实媒体验收通过。
- 官方依据：<https://github.com/motion-canvas/motion-canvas>、<https://motion-canvas.io/docs/rendering/video/>、<https://github.com/motion-canvas/exporters>。官方 exporter 无 CLI 入口，渲染必须从编辑器 Video Settings 发起。

## 22. 导出前后状态快照与最终集成治理（2026-11-17）

**矩阵快照说明：** `projects/e2e-p3-motion-canvas/receipts/capability-matrix.json` 是 PRE_EXPORT 历史证据；`capability-matrix-after-export.json` 虽为 POST_EXPORT_ACCEPTANCE 快照，但其当前状态字段是 `STALE_SOURCE_TEMPLATE`，因为源模板已改变。它保留旧导出和当时矩阵状态的来源链，不是当前验收结论。要恢复当前模板验收，必须由 Motion Canvas 编辑器重新导出 `mc-arch01`，再回灌并重核；`mc-state01` 仍单独需要编辑器导出。CI 只有外置 MP4 缺失时的合同/来源/治理校验，输出 `REAL_MEDIA_NOT_RUN`，不可视为真实媒体验收。

- `projects/e2e-p3-motion-canvas/receipts/capability-matrix.json` 曾作为 PRE_EXPORT 历史证据保留，早于旧真实导出；其中当时的 `BLOCKED` 不代表现状。
- `capability-matrix-after-export.json` 曾记录旧源模板下的 POST_EXPORT_ACCEPTANCE 证据，包括生成函数/输入哈希、历史导出 MP4 哈希与回执路径。当前 `current_status=STALE_SOURCE_TEMPLATE` 覆盖其历史阶段标签。
- `mc-arch01` 的旧导出 SHA-256 `8741f5c56612f712a296e9a4cb347366b63b310badf07fc1a191af6610d238e1` 与 `mc-state01` 的 `EDITOR_EXPORT_REQUIRED` 回执均是历史记录。它们不能互相继承状态，也不构成当前模板就绪。
- `production_ready`、`publish_authorized` 与人工审核授权始终关闭；任何重新验收均不会自动授予这些权限。