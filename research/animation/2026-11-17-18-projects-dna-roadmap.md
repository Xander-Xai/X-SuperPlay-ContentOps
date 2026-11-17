---
status: experiment
canonical: false
issue: "#196"
date: 2026-11-17
---

# 18 个动画开源项目 × X-SuperPlay 双账号 DNA：复核与 Claude Code 落地任务

> 复核日期：2026-11-17。此文是**非规范性调研/实施交接**，不是已完成验收。事实优先级与准则以 [AGENTS.md](../../AGENTS.md)、[动画 PRD](../../docs/PRD-ANIMATION-SKILLS-INTEGRATION.md)、[录屏与平台 PRD](../../docs/PRD-RECORDING-TO-PLATFORM.md)、账号 JSON、机器回执及**当前代码**为准。调研基线为 PR [#196](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/196) 的 `7b2068bc`；`main` 尚不包含该 PR。仓库或版本状态会变化，使用时须重新读取。

## 0. 结论（不是“装 18 个 Skill”）

- 18 个链接**不是 18 个可直接安装的 Claude Code Skill**：只有 `remotion-dev/skills` 是直接面向 Agent 的技能指令集；其他是动画框架、补间库、播放/导出库或完整创作环境。`git clone`、`npm install`、Skill 发现、构建成功、技术 MP4 与具备商业可用/可发布权是不同状态。
- 本项目应该是 **Easel v0.3.0（固定 pin）唯一整片合成器 + 现有 M5 证据链/时间线 + 按镜头选择 Remotion/Huashu/Manim/Motion Canvas/Remotion-Three**。不得再造一套编辑器、总时间线、素材注册表、缓存身份或 QC。
- **立即优先事项不是新增 14 个库**，而是：解决 PR #196 的真实交付缺口、完成双账号各自可核验的成片样例、保持平台原生规格和人审门控；只有真实任务无法由已有后端表达时才引入候选。
- GitHub 18 仓库于 2026-11-17 均可访问、均未标记 archived；维护/更新时间仅作参考，**不等于适合当前工作流**。表内“许可证”基于仓库元信息及少数 LICENSE 原文；不是法律意见。

## 1. 18 项逐项核验及决策

| # | 仓库（核验入口） | 类型/输出能力 | 许可证核验 | 本项目决策与适用画面 |
|---|---|---|---|---|
| 1 | [remotion-dev/skills](https://github.com/remotion-dev/skills) | Agent Skills，指导写 Remotion；**自身不渲染 MP4** | 本轮 GitHub 仓库元信息 `license` 为空（未识别独立许可）；不得推定可原样再分发整包 | **P0 学习/可选本地安装**；已有 Remotion 模板可先运行；不能以 Skill 未安装否认已产出的 MP4 |
| 2 | [motion-canvas/motion-canvas](https://github.com/motion-canvas/motion-canvas) | 时序化 2D 解释动画；视频导出经编辑器 FFmpeg 插件 | MIT | **已部分接入**；AI 架构图、Agent 状态机；`mc-state01` 仍待真实编辑器导出，禁止编造 CLI |
| 3 | [motiondivision/motion](https://github.com/motiondivision/motion) | React/JS 动效库，不是成片器 | MIT | **暂不加**；已有 Remotion/Canvas 逐帧时间轴 |
| 4 | [franciscop/ola](https://github.com/franciscop/ola) | 数值平滑插值，无独立视频导出 | MIT | **暂不加**；数字动画优先复用现有模板 |
| 5 | [juliangarnier/anime](https://github.com/juliangarnier/anime) | JS timeline/easing，本身不编码 MP4 | MIT | **暂不加**；避免与现有动画时间轴竞争 |
| 6 | [ManimCommunity/manim](https://github.com/ManimCommunity/manim) | Python 场景可渲染 MP4，依赖字体/Cairo/Pango | MIT | **已部分接入**；Attention、矩阵、公式、流程可视化；隔离 venv 与回执审查必须保留 |
| 7 | [jeremyckahn/shifty](https://github.com/jeremyckahn/shifty) | Tween engine，不导 MP4 | MIT | **暂不加** |
| 8 | [jonobr1/two.js](https://github.com/jonobr1/two.js) | 2D 矢量绘制 API，不导 MP4 | MIT | **暂不加**；有独特图形需求再评估 |
| 9 | [airbnb/lottie-web](https://github.com/airbnb/lottie-web) | Lottie JSON 动画播放，不是视频编码器 | MIT | **条件候选**；仅真实片头/图标资产复用需求出现时；需验证帧捕获与许可 |
| 10 | [CreateJS/TweenJS](https://github.com/CreateJS/TweenJS) | Tween 补间，不导 MP4 | MIT | **暂不加**；仓库最近 push 为 2023-12-18，不把 stars 当维护证明 |
| 11 | [lume/lume](https://github.com/lume/lume) | 基于 HTML 的 3D 场景描述，不导 MP4 | MIT | **暂不加**；已有 Remotion-Three |
| 12 | [mattdesl/gifenc](https://github.com/mattdesl/gifenc) | GIF 编码而非 MP4 视频引擎 | MIT | **按需**；有 GIF 原生交付任务才考虑 |
| 13 | [konvajs/konva](https://github.com/konvajs/konva) | 可交互 Canvas 编辑器/标注，不是视频引擎 | **LICENSE 原文 MIT**（GitHub API SPDX 为 NOASSERTION） | **当前不加**；若未来做人工拖拽动画编辑 UI 再评估 |
| 14 | [blender/blender](https://github.com/blender/blender) | 完整 3D DCC 与动画工具，能输出视频 | **Blender 官方 GPL**（GitHub 镜像 API NOASSERTION 不能取代 LICENSE） | **不作为轻量默认后端**；角色绑定/电影级 3D 的真实需求触发专项评估 |
| 15 | [mrdoob/three.js](https://github.com/mrdoob/three.js) | 3D 渲染库，本身不负责可核验成片 | MIT | **已经通过 `@remotion/three` 试接入**；只做必要 3D 原理镜头，不再新建独立 Three 管线 |
| 16 | [godotengine/godot](https://github.com/godotengine/godot) | 游戏/交互动画引擎，可录制或导出但非本工作流必需 | MIT | **暂不加**；游戏职业/交互模拟另立需求 |
| 17 | [BabylonJS/Babylon.js](https://github.com/BabylonJS/Babylon.js) | Web 3D 渲染与动画库，本身不等于 MP4 工作流 | Apache-2.0 | **暂不加**；与 Three 重叠 |
| 18 | [drawcall/Proton](https://github.com/drawcall/Proton) | 粒子动画，无独立成片流程 | MIT | **暂不加**；且双账号拒绝炫目效果 |

注意：REJECT / 暂不加只表示**当下的需求优先级**，不是断言开源项目本身无用。许可证和依赖须在实际纳入时按固定版本再次审查。

### 许可证差异与官方来源

- Remotion 使用[自定义许可证](https://github.com/remotion-dev/remotion/blob/main/LICENSE.md)，官方[条款](https://www.remotion.dev/docs/terms)明确指出其**不是 OSI 意义上的开源软件**，而是 source-available；个人及符合条件的最多 3 人团队可用免费许可证进行商业视频创作与自动化，但仍有服务形态限制。为客户交付**成品视频**与让客户**拥有/运行 Remotion 工程**的授权判定不同；共同参与运营工程的企业/合同人员可能需要合并核算人数；让用户上传自己的 Remotion 代码供服务端渲染也受限制。正式产品化、SaaS 或对外交付前须按当时最新[License FAQ](https://www.remotion.dev/docs/license/faq)及条款逐项核对，必要时联系权利人。不能简单说“GitHub 免费 = 开源 / 一切商业化方式不限”。
- Remotion [官方 Agent Skills 文档](https://www.remotion.dev/docs/ai/skills) 提供 `npx remotion skills add`（项目已有 Remotion）及 `npx skills add remotion-dev/skills`。技能文件安装与渲染器不是同一件事；仓库此前本机安装被权限规则拦截，必须如实报告 `NOT_INSTALLED`，不绕过执行策略。
- Motion Canvas [渲染](https://motion-canvas.io/docs/rendering/)与[FFmpeg exporter](https://motion-canvas.io/docs/rendering/video/)文档描述的是**编辑器 Video Settings → Render**；当前项目 adapter 明确是 `EDITOR_EXPORT_REQUIRED`，不要编造 `npx mc render` 为官方无人值守 CLI。
- Manim [官方 CLI](https://docs.manim.community/en/stable/guides/configuration.html) 支持 `manim render` / `python -m manim render`，实际执行受隔离运行时、字体与原生依赖影响。
- Konva [LICENSE](https://github.com/konvajs/konva/blob/master/LICENSE)、Blender [官方许可证](https://www.blender.org/about/license/)是 SPDX 为 NOASSERTION 时的正确核验来源；Blender 产出的作品与 Blender 软件本身的许可应区分。
- Remotion [Three 适配文档](https://www.remotion.dev/docs/three)表明 Three.js 可经 `@remotion/three` 并入逐帧渲染，而不是自行维护第二套视频编码栈。

## 2. 账号 DNA → 镜头与成片约束（JSON 优先）

规范来源：`config/accounts/x-superplay-1024.json`、`config/accounts/x-superplay-future-intelligence.json` 和各自 prompt。**以 JSON 可执行配置与验证器为准**，尤其当 prompt 里的 65/30/5 草案同 JSON 的 70/25/5 不一致时，必须显式标注差异，不可暗改生产门槛。

| 属性 | X超玩·1024 | X超玩·未来智能 |
|---|---|---|
| 账号 | `x-superplay-1024`，Explore，`RESULT_FIRST` | `x-superplay-future-intelligence`，Build，`ENGINEERING_WALKTHROUGH` |
| 片长/开篇 | 45–60s，前三秒冲突/翻车/结果前置 | 90–120s，前三秒工程痛点/证据 |
| 时长权重（DNA） | 70%真实录屏证据 + 25%矢量动画 + 5%对比卡 | 70%矢量动画 + 25%代码截图 + 5%指标图 |
| 镜头顺序 | 冲突钩子 → 本次任务 → 实测/失败 → 成本与边界 → 适用对象 → 下一验证 | 痛点 → 需求取舍 → 架构链路 → 核心代码 → 故障根因 → 评估/上线风险 → 复现 |
| 允许素材 | 用户**手动真实录屏**，登记后裁剪终端、日志、错误和运行结果；动画仅标注/解释 | 动态架构/数据流、静态局部代码、真实有据的指标；**禁止手动桌面录屏与鼠标操作画面** |
| 动效 | 淡入淡出、箭头、数字过渡、crossfade | 模块逐步淡入、单向箭头、节点状态切换 |
| 适合首批模板 | `title_card`、`evidence_zoom`、`code_focus`、`comparison_reveal`、`metric_transition` | `architecture_flow`、`state_transition`、`rag_flow`、`attention_matrix_flow`、`animated_system_graph` |
| 证据与阻断 | 无合格真实素材时正式生产 `MISSING_REAL_RECORDING`；生成片段不计 70% | 解释动画不能冒充真实日志或 bench；桌面录屏 `RECORDING_FORBIDDEN` |

**共同样式与工程边界**：品牌 DNA `brand.palette.base=#0F1117`、`accent=#38BDF8`，不是允许整片铺深色；主动画画布使用 DNA 的浅色 motion profile，但最终 resolved palette 要遵守品牌优先级，不能复用旧配色缓存。禁止 bounce/flash/shake/sticker/蓝紫渐变/玻璃态/大黑条。字数/字幕安全区/字号读 JSON；不要凭印象固定。素材变化、颜色变化须触发缓存失效。所有生成动画标记 `generated=true`、`evidence_capable=false`、`counts_as_real_recording=false`、`evidence_use=VISUAL_SUPPORT`。禁止伪造性能数字、真实客户反馈及来源。

## 3. 当前代码证据（仅引用 PR #196 与仓库已记录的回执，不声称本次本地复跑）

| 层 | 当前实况（PR #196, HEAD `7b2068bc`） | 必须保留的边界 |
|---|---|---|
| Easel | `runtime/easel-pins.json`：v0.3.0，`bb3c8ff`，冻结 | 唯一整片合成；不升级、不修改上游、不把模型生成片当事实 |
| Huashu | 六类 DNA 驱动解释镜头，M5 shot-plan，PR 记载本机真实样片 | 不是把动画升级为“录屏”；回执 + 模板身份 |
| Remotion 4.0.543 | `extensions/animation-remotion/` + `scripts/animation_render.py`；`title_card`/`rag_flow`/`Technical3DExplainer` 等有真实短镜头 | `runtime/remotion.lock.json`；复用可信缓存、素材清单、M45、QC |
| Manim 0.22.1 | `scripts/manim_render.py`、`scripts/manim_scenes.py`、隔离 venv；两个模板已有真实渲染与合同测试 | “已安装”不自动 `VERIFIED`；正式证据按 SHA/receipt；不可将本机绝对路径当可移植安装 |
| Motion Canvas 3.17.2 | `extensions/motion-canvas/`、`scripts/motion_canvas_adapter.py`；`mc-arch01` 编辑器真实导出经 SHA/ffprobe/QC；`mc-state01` 未完成真实导出 | `EDITOR_EXPORT_REQUIRED`；CI 无外置 MP4 时是 `REAL_MEDIA_NOT_RUN`，绝不假称渲染通过 |
| Remotion-Three | `@remotion/three` 实渲样片，走已有 Remotion 渲染入口 | 非独立 3D 合成器；WebGL 字节级不确定性如实记录 |
| 生产与发布 | PR #196 说明本机 11 条 MP4 证据、合成过一条未来智能 TEST_ONLY ~99.744s 全片 | 不是生产准入；`production_ready=false`，`publish_authorized=false`，`human_review=PENDING_FOUNDER_REVIEW` |
| 平台 | 现有 `config/platforms/video-platforms.yaml`、`scripts/platform_adapt.py` | B站**原生 16:9** 仍未有可核验渲染；不要拉伸 9:16 假冒 native；0 真实发布不因打包变成已发布 |

**重要纠偏**：既有 `docs/PRD-ANIMATION-SKILLS-INTEGRATION.md` 第 3、5、16 节有早期“Motion Canvas 未出片”“Three REJECT”等**历史叙述**，第 20–22 节及 PR #196 记录了后续实现。不要只引用前表而否认已做过的能力。后续由实现任务统一梳理 PRD 的当前状态及英文镜像，按 `DOC-SYNC` 更新，不在本研究报告冒称已经修完规范文档。

## 4. “指示 → 制作 → 动起来 → 修改 → 导出”应落在一条链上

`账号 DNA + source/claim → 脚本/分镜 → 按 shot_type 显式选已有后端 → 2–8s 静音 MP4 短镜头 → project:// 资产登记、SHA-256/ffprobe/首中末帧/视觉 QC → M45 清单与统一时间线 → Easel 组成两条账号各自的成片 → 各平台 native variant → QC → Founder 审核（不得自动发布）`。

- 渲染和合成分开：**一个短镜头后端只能产短镜头**；不允许 Remotion、Motion Canvas 另起 45–120s 的总时间线。
- 明确 `backend`；用户指定的后端不可静默换 Huashu/静态图。降级需预先声明且兼容，并保留实际执行者/画质影响/阻断回执。
- 2–8s 静音、1080×1920、H.264、`yuv420p`、CFR 30fps 是**现有短镜头入场门**，不是所有平台成片规格；如生产原生 16:9，先做独立规格/适配合同与测试，不能偷偷修改现有门。
- 动画可用不代表事实能发：`TECHNICALLY_CHECKED`/`VERIFIED`/`QC PASS` 均不等于 Founder 已批准发布。
- 用户提供的录屏素材由项目加工、裁剪、匿名化、记录 source/rights/claim 绑定；未来智能不接收手动桌面录屏。

## 5. 按阻塞程度排序的实施 Backlog

| 优先级 | Task / 首要动作 | 成功证据 | 不应做 |
|---|---|---|---|
| P0 | 先比对最新 `main`/PR #196 HEAD、分支和 PR 文档；重用 PR #196；**不另造重复接入** | 报出真实 SHA/文件/测试/未验收项；保持 #196 唯一集成路径 | 不先合并 #193/#195；不强推主干 |
| P1 | 让 `mc-state01` 有可审计真实导出：保留手动编辑器导出；缺人工交互就准确 BLOCKED | MP4 + 原始/归一化 SHA、ffprobe、帧与视觉审查、import receipt、模板级矩阵 | 不能把 `vite build` 当成 MP4；不能编造官方 headless CLI |
| P1 | **1024 实际录屏入场 → 成片**；没有用户录屏时先输出清楚的 capture-plan 和阻断原因 | 真实用户录屏绑定来源与 claim；70% 真实可见时长；45–60s；QC/人工审核待定 | 不用生成图/截图拼接伪装录屏；不制造通过截图 |
| P1 | **未来智能解释视频 e2e**，优先核验已有 TEST_ONLY 再补必要缺口 | 90–120s，架构/代码/指标时长权重、来源可信、没有手动桌面录屏；Easel 出片与审查 | 不因 TEST_ONLY 就报生产准入 |
| P2 | 真实平台变体：抖音 9:16、B站独立 16:9；小红书封面按已知 DNA 派生 | 每种格式独立实渲+安全区+帧/字幕抽查；不改原始技术结论 | 不把中心裁切/拉伸当“原生支持” |
| P2 | Remotion Skills **许可与权限审查后仅本机安装**（可选） | Skill 实际存在、Claude Code 可识别，安装来源/版本记本地回执 | 不覆盖共享 Skill、不把第三方 Skill 原文提交到公开库、不绕过权限分类器 |
| P3 | 有实需才分别 spike Lottie / gifenc / Konva / Blender | 先有具体镜头问题、可测试样片、许可证与扩展成本评估 | 不为“18 项全绿”安装 14 个无用依赖 |

### 交付验收清单

1. 逐个任务报告 `VERIFIED / IMPLEMENTED_NOT_VERIFIED / EDITOR_EXPORT_REQUIRED / BLOCKED / NOT_RUN`；不得把合同测试当真实媒体测试。
2. 视频物理证据：实际文件存在且哈希核对、`ffprobe` 编码/分辨率/fps/时长/音轨、完整解码、首中末帧与 contact sheet；原生平台改幅重新审查。
3. 证据语义：claim→真实来源映射；素材权利、录屏与动画分类；1024 的真实时长比例；未来智能禁止手动录屏。
4. 只跑本次变更需要的 L0–L3 检查；如建 PR，按项目要求跑一次 `python scripts/dev_check.py`；不把 CI green 解释为本机真实 MP4 验证。
5. 成片默认 `production_ready=false`、`publish_authorized=false`、`PENDING_FOUNDER_REVIEW`；**没有人工批准不发布**。

## 6. 可直接粘贴给 Claude Code 的执行提示词

> 以下提示词针对**已经存在的仓库**，目标是继承当前成果、做真正缺口的交付，不是重构或装全家桶。执行前先读最新代码。没有用户录屏或人工编辑器操作时要保留明确阻断，不要编造完成。

```text
你现在是 X-SuperPlay-ContentOps 的资深视频工程与验收负责人。请在当前仓库开展“18 项开源动画工具选型的落地收尾”，不是从零新建动画引擎。必须实际读源码、配置、现有 PR/Issue、运行回执后再动手。

【首要事实核对】
1. 运行 git status、git branch -vv、git log，核对 origin/main 与 PR #196 的最新 HEAD/CI，保护当前用户未提交改动。读取 AGENTS.md、CLAUDE.md、docs/PRD-ANIMATION-SKILLS-INTEGRATION.md 及英文镜像、docs/PRD-RECORDING-TO-PLATFORM.md、docs/FILE-PLACEMENT-POLICY.md、docs/TEST-PLAN.md。
2. 阅读 research/animation/2026-11-17-18-projects-dna-roadmap.md。这只是 2026-11-17 的研究基线；以当前代码/实时回执为准，特别核对是否已有人在其他 worktree 修好相同问题。
3. 读取两个账号 JSON 与各自 prompt、config/platforms/video-platforms.yaml、runtime/easel-pins.json、runtime/*motion*.json、runtime/*manim*.json、相关 animation backend、M5、Easel、QC、素材登记及缓存。建立“已有实现/真实验证/合同测试/真实缺口/外部阻断”的证据矩阵；每项列文件、行号/命令和回执。不得凭历史 PRD 中旧表推断现在未接入。
4. 保持 Easel v0.3.0 / bb3c8ff 固定。PR #196 是既有集成主线，不合并 #193/#195，不重建 M5 timeline、资产注册表、后端矩阵、合成器或第三套账号配置。未经授权不修改上游、不发布、不付费调用、不公开凭据。

【优先开发任务：先堵缺口，再加功能】
A. 核验已有 Remotion、Huashu、Manim、Motion Canvas、Remotion-Three 的模板、版本、实际 render receipt 与缓存完整性；必要时做最小补丁，不重复开发已存在的模板。不得以“已安装包”“编译成功”“CI 合同测试通过”冒充已生成合格 MP4。
B. 优先收口 Motion Canvas 的 mc-state01：检查是否已经有真实编辑器导出；有则按现有 scripts/motion_canvas_adapter.py --import-editor-export 合同回灌并验证 SHA/ffprobe/帧/QC/清单/矩阵；没有则保留 EDITOR_EXPORT_REQUIRED，产出本机手工导出的准确步骤和接收路径。禁止编造不存在的 headless 导出命令，也不允许用 Remotion 假扮 Motion Canvas 成功。
C. 对 1024（x-superplay-1024）做真实录屏加工能力验收：45–60 秒，前 3s 冲突钩子；依据 DNA 70% 真实已登记录屏/25%矢量动画/5%对比卡，录屏必须由我手动提供并裁切到终端、错误、结果，claim 与来源绑定；无真实素材时真实报告 MISSING_REAL_RECORDING 并生成最小 capture-plan，不得使用生成镜头充当实测。
D. 对未来智能（x-superplay-future-intelligence）核验已有 90–120s TEST_ONLY 影片，再只补未满足的缺口：70%动态矢量架构/25%局部静态代码/5%真实有源指标，完整讲述需求、架构、关键实现、故障、验证与风险；全片禁止任何手动桌面录屏、鼠标操作画面。RAG/Agent 动画必须标注“原理示意”，不能捏造日志、指标和客户反馈。
E. 若短镜头需修改，始终经过现有 backend selector → 2–8s 静音 1080x1920 CFR30 H.264 yuv420p → SHA256/ffprobe/抽帧/QC → project:// 资产登记/M45 → Easel 唯一合成；缓存仅在输入、DNA、模板与物理文件一致时复用。
F. 将平台适配与出片证明分开：抖音 9:16；B站原生 16:9 若尚不支持则标记 NATIVE_16_9_RENDER_UNAVAILABLE，不得用拉伸视频伪造；小红书封面/标题按现有规则适配。没有平台上传/发布的真实回执就不要写已发布。

【工具采用纪律】
- 18 个仓库并非 18 个 Skill，禁止统一安装。
- Remotion Skills 只有在当前缺失、许可证/权限合规且对开发有价值时才通过官方命令安装在本地允许位置；遇到权限阻断写 NOT_INSTALLED 并继续使用已有代码，不绕过策略，不将第三方指令全文推到 Git。
- Motion / Ola / Anime.js / Shifty / Two.js / TweenJS / LUME / Godot / Babylon / Proton 默认不装；Lottie、gifenc、Konva、Blender 必须先给具体需求/成本/许可与独立 spike，不能污染生产依赖。
- 绝不静默切后端或删掉失败回执；所有新动画 produced 资产必须为 generated=true, evidence_capable=false, counts_as_real_recording=false。
- 不用本机绝对路径作为跨机器默认安装指令；隔离 venv / npm 锁须可复建。

【交付与验收】
1. 交付“缺口→改动→命令→文件/回执→真实结果”的逐项矩阵，区分 NOT_RUN、合同测试 PASS、真实媒体 PASS、BLOCKED。每个视频有实际 SHA-256、ffprobe、首/中/末帧、视觉 QC 和 artifact 路径；没有就写未完成。
2. 依据 docs/TEST-PLAN.md 风险分级执行最小相关测试；PR 前按规则执行一次 dev_check，观察 GitHub CI。禁止为了显得工作多而扩张无关测试。
3. 如果更改规范文档，按 docs/DOC-SYNC.md 同步中英文镜像和 freshness，纠正动画 PRD 前后历史状态矛盾；调研放 research/，可执行步骤归 RUNBOOK，不在根目录丢报告。
4. 合成后必须保留 human_review=PENDING_FOUNDER_REVIEW, production_ready=false, publish_authorized=false；用户亲自审核前不能自动发布。
5. 以最小可审 PR 提交，复用 #196 已有成果；不擅自合并，不能覆盖当前未提交用户改动。最终给出 PR URL、commit SHA、具体复现命令、实际通过/阻断项、下一步需要我提供的最小输入。没有真实录屏、人工编辑器导出或批准时，诚实地将对应环节置为 BLOCKED。
```

## 7. 回溯入口与时间

- 本仓现状：[#196 集成 PR](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/pull/196)、[动画 PRD](../../docs/PRD-ANIMATION-SKILLS-INTEGRATION.md)、[录屏 PRD](../../docs/PRD-RECORDING-TO-PLATFORM.md)。
- 外部：上表 18 个**实际** GitHub 仓库链接；详情取 GitHub Repo API 的 `pushed_at`、`archived`、`license.spdx_id` 于 2026-11-17 查询，**不以网站 updated_at 代表代码维护**。
- 版本/后端结论优先使用本仓 `runtime/remotion.lock.json`（4.0.543）、`runtime/manim.lock.json`（0.22.1）、`runtime/motion-canvas.lock.json`（3.17.2）及实际回执；不要把这些版本声明为未来一直最新。
- 本次研究使用 GitHub 已提交源代码、PR 描述和官方文档；**没有在本会话重跑本机 MP4 渲染或声称新增片子**。