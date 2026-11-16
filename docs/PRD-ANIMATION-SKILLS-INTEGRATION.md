# PRD — 动画 Skill 与多引擎短镜头接入

[简体中文](PRD-ANIMATION-SKILLS-INTEGRATION.md) | [English](PRD-ANIMATION-SKILLS-INTEGRATION.en.md)

> Last verified: 2026-11-17
> 状态：**Implemented for P0 clip render** — Remotion 短镜头已在本机渲染并接入 M5 调度；Motion Canvas 与 Manim 为 BLOCKED，不是 VERIFIED。2026-11-17 新增并本机验证 DNA 驱动的 3 秒冲突式 `title_card` 与可信渲染缓存。
> 本文是需求与验收记录。生成片段不是真实录屏，也不能代替 Founder 审核。

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
| `motion_planner.py` | Huashu 自动计划保持原样 |
| 账号 DNA | 调色板从 DNA 读取，不另写一套品牌色 |
| `recording_intake.py` | 录屏入场规则不因新后端放宽 |
| `real_source_duration.py` | 生成片段的 `source_kind` 是 `vector_animation`，不计入 70% 真实录屏 |
| Easel `assemble_easel.run` | 仍是唯一成片合成入口 |

## 3. 18 个上游项目

审计日 2026-11-16。事实来自 `gh api`。无人归档。Remotion 许可证另读了 `LICENSE.md`：GitHub SPDX 为 `NOASSERTION` 是因为许可证是自定义的，不是“未读”。

| # | 仓库 | 是什么 | 许可证 | 最近活动 | 能否自己出片 | 结论 |
|---|---|---|---|---|---|---|
| 1 | remotion-dev/skills | Agent Skill 包，不是渲染器 | 无独立 license 对象；内容属于 Remotion 4.0.543 | 2026-11-11，tip `7e541aa` | 否 | P0 的技能层，本地安装，不入库分发 |
| 2 | motion-canvas/motion-canvas | Vite 编辑器 + 浏览器播放 | MIT | 2026-07-02；最新 release 仍是 2025-02 的 alpha | 编辑器 websocket 导出，无 headless CLI | P1，本轮 BLOCKED |
| 3 | motiondivision/motion | React 补间库 | MIT | 2026-11-15 | 否 | REJECT |
| 4 | franciscop/ola | 数值插值 | MIT | 2026-10-24 | 否 | REJECT |
| 5 | juliangarnier/anime | JS 动画引擎 | MIT | 2026-11-02 | 否；HyperFrames 已有适配 | REJECT |
| 6 | ManimCommunity/manim | Python 数学动画 | MIT | v0.22.1，2026-10-27 | 能出视频；需要 cairo/pango | P1，本机未安装，BLOCKED |
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

侧证：`remotion-dev/remotion` 最新 release 是 **v4.0.543**（2026-11-11）。本机 Node v24.16.0、npm 11.13.0、FFmpeg 8.1.1、Chrome 与 Edge 已安装。Manim 未安装。

## 4. 选型与许可证

P0 选 Remotion 渲染器，不是因为它 Star 多，而是：它能出 MP4；本机有 Node 和 Chrome；许可证文本允许个人以及不超过 3 名雇员的营利组织用它制作视频。禁止把 Remotion 改造成再销售的衍生渲染器。因此只提交本仓库自己的模板和锁文件，不提交 `node_modules`，也不把上游源码拷进仓库。

`remotion-dev/skills` 没有独立许可证对象。技能文件不提交到本仓库，避免把许可不清的第三方文本打进公开发布。

Motion Canvas 与 Manim 许可证是 MIT，商业使用本身不是拒绝理由。拒绝本轮接入的原因是运行形态：前者没有 headless CLI，后者本机没有 cairo/pango 环境。不把缺环境写成 VERIFIED。

## 5. 实施顺序

| 阶段 | 状态 | 说明 |
|---|---|---|
| M0 环境 | 部分完成 | Node、FFmpeg、Chrome 已核到。官方 `npx skills add` 被本机权限分类器拒绝，技能未安装 |
| M1 Remotion | 完成 | 4.0.543 锁文件；两个参数化模板；本机渲染通过 `motion_sample` |
| M2 Motion Canvas / Manim | BLOCKED | 见第 17 节 |
| M3 双账号 | 完成合同与阻断 | 1024 无录屏的正式生产被阻断；未来智能拒绝桌面录屏输入；测试用途片段可渲染且不计证据 |
| M4 工作台 | 未做整页 UI | 技能注册表增加发现指针。不改 Easel 上游，不重写 Web UI |

## 6. 双账号策略

规则来自现有 DNA，不另写品牌配置。

1024：70% 真实录屏、25% 矢量动画、5% 对比卡；45–60 秒。动画是视觉辅助。`source_kind=vector_animation`，`generated=true`，`evidence_capable=false`，`counts_as_real_recording=false`。没有裁切后的真实录屏时，`purpose=production` 返回 `MISSING_REAL_RECORDING`。测试用途可以渲染，回执标明不是已验收案例。

未来智能：70% 矢量动画、25% 代码片段、5% 图表；90–120 秒。`input_kind` 为桌面/手动录屏时 `RECORDING_FORBIDDEN`。RAG 示例的字幕写明“原理示意，不是系统输出”，不含未证实的性能数字。

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
- `production_gate()`：技术放行不是发布许可

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

Easel pin 仍是 `runtime/easel-pins.json` 的 `v0.3.0` / `bb3c8ff`。本变更不改 `.runtime/easel-v030`。Huashu 别名 `art-motion` 与 `motion` 仍解析到原后端。未写 `motion.shot_plan` 的 `remotion` 配置不会掉进 Huashu 自动计划。

## 11. 与 M5 的关系

`stage_motion` 在镜头 `backend` 为 `remotion`、`motion-canvas` 或 `manim` 时调用 `animation_render.py`。失败是 `M5Blocked`，不改调 Huashu。测试 `test_m5_dispatches_an_explicit_remotion_shot_to_the_clip_adapter` 断言命令行含该适配器且不含 `huashu_motion`。

## 12. 素材分类

生成动画：`generated=true`，`evidence_capable=false`，`evidence_use=VISUAL_SUPPORT`，`source_kind=vector_animation`。权利字段是 `GENERATED_LOCAL_NO_COMMERCIAL_CLEARANCE`，不是已确认的商业授权。

## 13. 平台适配

不新建平台表。继续用 `config/platforms/video-platforms.yaml` 和 `scripts/platform_adapt.py`。本变更不把未启用平台改成 ACTIVE，也不把封装成功写成发布成功。`x-superplay-english` 不是第三个视频品牌。

## 14. 安全与人审

授权范围内：本地非付费渲染、项目级 npm 依赖、本仓库代码。未做：升级 Easel、改凭据、MiniMax 调用、自动发布、下载大型模型、关闭人审。技术 QC 通过后 `human_review` 仍是 `PENDING_FOUNDER_REVIEW`，`production_ready` 与 `publish_authorized` 保持 false。

## 15. 测试

`tests/test_animation_backend.py` 已注册到 `.github/workflows/ci.yml`。它不渲染视频。覆盖：缺账号、未知账号、显式引擎不静默替换、仅预先声明且兼容的后备、数学镜头不掉成 Remotion、未来智能拒绝录屏、1024 正式生产缺录屏阻断、回执拒绝主机路径、未知技能、版本不匹配。既有 `tests/test_m5_motion_integration.py` 在本机 56/56 通过。

## 16. 验收

| 项 | 状态 | 证据 |
|---|---|---|
| 18 项调研 | PASS | 本文第 3 节 |
| PRD | PASS | 本文件与英文镜像 |
| Remotion Skills 安装 | FAIL | `npx skills add` 被权限分类器拒绝；技能未安装，未写入共享库 |
| Remotion 渲染 | PASS | 见下表 |
| Motion Canvas | BLOCKED | `NO_HEADLESS_EXPORT` |
| Manim | BLOCKED | `RUNTIME_MISSING` / `missing manim`。未向系统 Python 安装 |
| 1024 规则 | PASS | 正式生产无录屏返回 `MISSING_REAL_RECORDING`；测试片段 `counts_as_real_recording=false` |
| 未来智能规则 | PASS | 桌面录屏 `RECORDING_FORBIDDEN`；RAG 回执 `EXPLANATORY_CLIP` |
| M5 接线 | PASS | `stage_motion` 调度测试；选择器接受 `remotion` |
| Easel 回归 | PASS | pin 文件未改；Huashu 集成测试 56/56 |
| 多平台 | PASS | 未改平台注册表，未把封装写成发布 |
| 人审与安全 | PASS | 回执 `production_ready=false`，`publish_authorized=false` |

本机渲染（gitignored，`projects/_local/`）：

| 片段 | 路径 | sha256 | ffprobe |
|---|---|---|---|
| 1024 标注测试 | `projects/_local/animation-1024-sample/assets/generated/remotion/clip-annotation.mp4` | `4c31e531dbed90070b5d61159acf56f07a70d56a009167cbd1d483ac11327b62` | h264, 1080x1920, yuv420p, 30/1, 4.000s, 无音轨 |
| 未来智能 RAG | `projects/_local/animation-fi-sample/assets/generated/remotion/clip-rag.mp4` | `417019d985f440b4f910f91ed37192118353e01c1b0a5f66b78ca67568c067c0` | h264, 1080x1920, yuv420p, 30/1, 6.000s, 无音轨 |

回执：`project://receipts/animation-clip-annotation.json` 与 `project://receipts/animation-clip-rag.json`。没有主机绝对路径。

## 17. 风险与回滚

风险：Remotion 免费许可证只覆盖符合资格的主体；若组织超过 3 名雇员，必须先取得公司许可证再渲染。Chrome 启动在 Windows 上需要 `--gl angle`，已写入适配器。`yuvj420p` 会被样本门拒绝，转码强制 `yuv420p` 与 `color_range tv`。

回滚：删除本分支对 `stage_motion` 的调度分支，并移除 `extensions/animation-remotion` 与锁文件。Huashu 与 Easel pin 不依赖这些文件。`npm` 卸载是删掉该目录的 `node_modules`，不要动 `.runtime/easel-v030`。

故障：`RUNTIME_MISSING` 表示未执行上面的 npm 安装或没有 Node/FFmpeg/浏览器。`VERSION_MISMATCH` 表示锁文件不是 4.0.543。`RENDER_FAILED` 时看 `projects/<slug>/work/animation/*.render.log`。不要把静态图当成渲染成功。

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
