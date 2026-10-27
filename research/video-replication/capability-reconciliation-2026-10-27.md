---
status: experiment
canonical: false
issue: "#34"
date: 2026-10-27
---

# 能力对账：对标蓝图 M1–M9 → 现有 ContentOps 运行时

> 任务：`research/video-replication/claude-code-video-replication-prompt.md` 第 2 节。
> 对账依据只取当前代码、配置、receipt 与 V2 设计规格；不按蓝图推测仓库能力。
> 事实优先级：REAL EXECUTION RECEIPT > CURRENT CODE > CONFIG > ADR > CURRENT-STATE > RUNBOOK > RESEARCH > OLD PLAN。

## 0. 结论先行

复刻不是“从零搭一条视频流水线”，而是**把 M1–M9 里缺失的 4 个环节补进既有运行时**：

1. Capture Proof + redaction + Claim Map（已覆盖一半）；
2. 分镜的“视图停留”约束（本轮新增 `shots` 与 `max_visual_hold_ms`）；
3. 账号 DNA 真正驱动字幕/封面（本轮接通）；
4. 发布前合规（以 Claim Map + QC 内嵌，不单建 M9）。

明确不建：n8n 编排、发布自动化、独立选题库、第二套渲染引擎。

## 1. M1–M9 逐模块对账

状态定义：**已覆盖** = 现有代码可直接承担；**需扩展** = 有骨架但要补字段/校验；
**需新增** = 当前没有可执行实现；**明确不建** = 与仓库边界冲突，附理由。

| 蓝图模块 | 蓝图要求 | 现状与依据 | 判定 |
|---|---|---|---|
| M1 选题库 | 栏目词库 + 选题卡 + 素材可行性预检 | 无选题库代码。账号 DNA 有 `content_pillars`（1024 权重 40/35/25）、`not_doing`、`benchmarks`，但只服务写作，不做去重或批量生成 | **明确不建**（见 §4） |
| M2 脚本生成 | 三段式、前 3 秒钩子、字数/时长校验、断言词扫描 | `narrative`（`mode`/`opening`/`beats`/`template`/`speech_rate_cpm`/`cta`/`template_coverage`）与 `forbidden` 在 DNA 里；`scripts/verify_creator_script.py` 有创作稿校验（禁编数字/模板话术/未声明第一人称）；`src/contentops/media/creator_script.py`。**缺口**：证据型 cut 的 `script/master.md` 仍是人工撰写，没有走 `video-script` skill | **需扩展** |
| M3 分镜 | 镜头号/时长/画面类型/口播字幕句 + 白名单校验 | `src/contentops/media/cut_plan.py` 校验 placement 单调、crop 在源内、context 先于放大、reading hold 下限；`src/contentops/media/cut_qc.py` 按最终时长计真实/生成占比。**本轮新增**：placement 内 `shots`（多视图）、`max_visual_hold_ms` / `min_visual_hold_ms`、视图必须铺满 placement、放大视图必须被上下文视图包含 | **已扩展** |
| M4a Explore 素材（裁切录屏/看板） | 干净裁切、1080×1920、敏感字段扫描 | `scripts/capture_terminal_evidence.py`（可见终端 + allowlist + 收据）、`scripts/redact_terminal_evidence.py`、`src/contentops/evidence/{capture,redaction}.py`；`build_evidence_cut._segment` 做 crop/scale/pad，卡片的 panel 与证据 panel 分离 | **已覆盖**（redaction 仅在有计划时执行） |
| M4b Build 素材（矢量/图表/代码截图） | 禁录屏禁鼠标、矢量导出 | `slideshow-video` / `infographic` / `chart-visualization` / `card-design` skill 存在；工程 cut 的 `v3` 视图与 `easel-engineering-proof` 使用静态卡+证据裁切。**缺口**：没有自动生成“数据流矢量动画”的亲生实现，仍依赖 Easel skill | **需扩展** |
| M5 配音 | 220–260 字/分、固定声线、禁改写、atempo 校正 | `scripts/synthesize_narration.py`（MiniMax `speech-2.8-hd`，按文本 hash 缓存）、`src/contentops/media/{minimax_speech,audio,billing_guard}.py`；v2/v3 有 ASR 反查与语速实测 | **已覆盖**（语速实测闭环仍属 P1） |
| M6 字幕 | SRT + 断句 + 安全区 | `scripts/assemble_easel.py` 生成 ASS（centisecond 时间戳、WrapStyle 2、逐 cue 缩放）；`tests/test_subtitle_timing.py`。**本轮新增**：中文禁则（句读不落行首、括号不落行尾）、caption style 从 DNA 读取 | **已扩展** |
| M7 合成 | 9:16 主版 + 16:9 派生、libx264/yuv420p/aac | 上游 `auto-short-video/assemble.py` 经 `assemble_easel.py`；`build_evidence_cut.py` 逐 view 渲染后 concat | **已覆盖** |
| M8 封面 | 标题+钩子、无断言词、平台比例 | `scripts/build_evidence_cover.py` + `card-xiaohongshu`/`card-design`；1080×1440，标题 claim 绑定，留白/密度审计 | **已覆盖** |
| M9 发布前合规 | 证据阶梯、Stage 0、软广、分组素材红线、语速、链接真实性 | Claim Map（`src/contentops/evidence/claim_map.py`）强制 SUPPORTED/PARTIAL/BLOCKED；`review_bundle.py` 阻断未 redaction 的 internal 捕获；`qc_video.py` 真实素材比。**未实现**：发布前独立扫描器与 URL 可达性校验 | **需扩展**（不建独立系统） |

## 2. 制作手法 T1–T12 落点

| 手法 | 落点 | 状态 |
|---|---|---|
| T1 Dashboard 录屏 | `capture_terminal_evidence` + `build_evidence_cut` | 具备；无浏览器捕获（见 §3） |
| T2 终端/CLI 录屏 | 同上；本轮 1024 全片 4 条真实终端捕获 | **已用** |
| T3 成品网页演示 | 需要浏览器捕获；`capture_terminal_evidence` 只录终端 | 缺口 |
| T4 PPT 静态录屏 | `card-design` + `render_card.py` | 具备，但不作为主线 |
| T5 手绘坐标系 | 无（可映射到 `infographic`） | 未建 |
| T6 AI 生成 MG 动画 | `slideshow-video` / `video-production` skill | 具备，未在本轮使用 |
| T7 图文卡片 | `card-design` / `card-xiaohongshu` | **已用**（引用卡、CTA 卡、封面） |
| T8 截图+流程图 | 无 graphviz 生成器 | 未建 |
| T9 口播配音 | MiniMax speech | **已用** |
| T10 字幕压制 | `assemble_easel` + DNA style | **已用** |
| T11 BGM | `audio-mix` skill；DNA 记 `OMITTED_BY_POLICY` | 明确不做（缺 key） |
| T12 封面 | `build_evidence_cover.py` | **已用** |

## 3. 本轮修复与实测

| 项 | 修复前 | 修复后 | 依据 |
|---|---|---|---|
| 品牌色 | 引用卡/封面为米白 `#F2EDE4` + 红 `#C0392B` | `#0F1117` 底、`#F5F7FA` 字、`#38BDF8` 强调、`#F07167` 失败标记 | `projects/easel-1024-proof/assets/cards/*.html`、`assets/covers/xhs.html` |
| 静态停留 | 最长冻结 5.27s，QC 以“declared reading hold”放过 | 22 个视图，每视图 2.0s；最长冻结 **1.80s** | `receipts/qc-report.json` |
| 证据可读性 | 整窗 1086×693 铺满 1080 宽，正文约 12–14px | 上下文视图 + 关键行放大（revision 1.8×、exit 2.25–2.57×），其余块保持全宽不切行 | `script/cut-plan.json` 的 `shots` |
| 字幕样式 | 黑底方块、47→54px 由代码常量决定 | 从 DNA 读 `caption_style`（无描边/无阴影/白字/安全区 120px） | `scripts/build_evidence_cut.py:_caption_style` |
| 字幕断行 | 边界句把“。”挤到第二行 | 中文禁则生效，单行显示 | `scripts/assemble_easel.py:_wrap` |
| 技能归属断言 | 口播“auto-subtitle 接管”，证据捕获输出里没有 auto-subtitle | 新增捕获 `CAP-20261028-SKILLROUTE-AUTO`（`--match auto-subtitle`），首条即 auto-subtitle | `receipts/captures/CAP-20261028-SKILLROUTE-AUTO.json` |

实测（ffprobe + `qc_cut`）：44.0s / 1080×1920 / h264 / aac / 真实素材 72.7% / 生成 0% / QC **PASS**。

## 4. 明确不建

| 项 | 理由 |
|---|---|
| n8n 编排 | 单机、单人、每两周 1–2 个源；编排层会增加一个需要维护的运行时，当前瓶颈是素材与审核，不是调度 |
| 发布自动化 | 红线：人工审核必经、无真实 URL 不得声明发布；自动发布把门禁变成建议 |
| 独立选题库 | 选题由真实业务源驱动（OPC Blueprint Stage 0），做词库会鼓励“为配额造选题” |
| 第二套渲染引擎 | 上游 Easel 已 pin 且经 982 blob 校验；再建一套等于把已验证的合成路径作废 |
| 浏览器 UI 捕获工具 | 只有出现“必须证明 Web 状态”的选题时才建；当前以文档引用卡表达，并在 Product 层阻断分发 |

## 5. 外部资产采用记录

| 资产 | 版本 | 许可证 | 采用方式 | 为什么 / 备注 |
|---|---|---|---|---|
| Easel | v0.2.1 / `3fe2d99` | 见上游仓库；pin 记录在 `runtime/easel.lock.json` | 直接 pin，未改源码 | 合成、卡片渲染、字幕烧录的既有路径 |
| HyperFrames | `0.8.206`（`npx`，不落库） | 本轮未复核；采用记录见 `research/x-media-workflow-skills-2026-10-27.md` | ADOPT（冷开场） | 不和主生产链耦合；**许可证待补** |
| card-design / card-xiaohongshu / card-quote | Easel v0.2.1 内置 | 随 Easel | 通过 `render_card.py` + `card_audit.py` 调用 | 卡片/封面的密度与层级门禁 |
| auto-short-video / auto-subtitle / slideshow-video | Easel v0.2.1 内置 | 随 Easel | 合成与字幕 | 不手搓 ffmpeg 滤镜链 |
| MoneyPrinterTurbo / OpenMontage / short-video-factory | — | 未采用 | REJECT | 整条产线，与“不建第二套系统”冲突 |
| remotion / manim | — | 未采用 | DEFER | 现有 `infographic`/`slideshow-video` 覆盖不到时再评估 |

## 6. 已知缺口与冲突（需要创始人决策）

1. **DNA 配比 vs V2 门禁冲突**：1024 DNA 要求 65% 录屏 + 30% 矢量 + 5% 卡片，V2 门禁要求真实素材 ≥70%。两者不能同时满足。本轮样片选择满足 V2（72.7% 真实 / 0% 矢量 / 27.3% 卡片），因此**未满足 DNA 的 30% 矢量**。需要决定：把 DNA 改为 70/25/5，或把 V2 门禁降到 65%。
2. **捕获分辨率上限**：终端捕获为 1086×693，正文约 14px。1080×1920 成片里，全宽上下文视图只能保持 1.0×；再放大就要切行。真正解决需要重新捕获（更高 DPI / 更小终端字号 / 更长窗口），不是后处理能补的。
3. **工程 cut 已过期**：`projects/easel-engineering-proof/final/easel.mp4` 为 62.0s（规格 78–90s），且其 cut-plan 是 7–8s 单视图；新的 `views_declared` 与 `static_hold_within_limit` 会让它 FAIL。原 qc receipt 仍在库里，重跑后才能作为当前结论。
4. **脚本未走 `video-script` skill**：本片脚本为人工撰写 + 证据绑定，`build-easel.json` 只声明 `auto-short-video` 一跳。若要求全 skill 路由，需要补 `video-script` 与其输入契约。
5. **分发仍被阻断**：4 条捕获都是 `internal_review`，`review-bundle.json` 正确标记 `distribution_blocked: true`。上平台前必须有 redaction receipt。
6. **doctor 计数的可见性**：doctor 输出 7 项，但捕获窗口把 python/node 滚动到画外；画面可见 5 项 + exit 0。Claim Map 已记 limitation，未改口播。
