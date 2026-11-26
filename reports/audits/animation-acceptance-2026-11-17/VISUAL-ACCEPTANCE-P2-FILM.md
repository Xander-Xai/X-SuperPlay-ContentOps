# 99.744 秒测试影片逐镜头视觉验收报告

> Archive provenance: 2026-11-17 visual-acceptance work. External frame captures are not accessible in the current environment; the recorded shot review is historical and has not been independently re-verified in this turn. No machine-specific path or credential is retained.


生成时间：2026-11-17（Asia/Shanghai）
对象：`projects/e2e-p2-fi-video`，未来智能账号 DNA 路由的 TEST_ONLY 技术演示片
方法：抽取 14 个镜头各自的中点帧（按 `receipts/narration.json` 的 14 段旁白时间），以 1080×1920 原分辨率目视检查，并与脚本文案、字幕、DNA 配色、现有视觉门禁逐项对照。**不依据 `fast_ratio` / `still_ratio` 单独判定质量。**

> 三态声明：本报告是**技术+视觉工程验收**，不是人工终审，也不代表正式生产就绪。全片 `production_ready=false` / `publish_authorized=false` / `human_review=PENDING_FOUNDER_REVIEW`。

## 1. 验收口径

| 维度 | 检查内容 | 依据 |
|---|---|---|
| 信息清晰 | 每帧能否直接看懂它在讲什么；标签/节点是否可读 | 抽帧目视 + 文案对照 |
| 动效同步 | 画面变化是否与旁白/解释内容对应 | `script.json` 14 段文案 vs 抽帧 |
| 静止等待 | 是否出现无意义的过长静止 | 视觉门 `max_event_gap_s` + 抽帧 |
| 概念可懂 | 架构流程、Agent 状态、代码重点是否直接可理解 | 对应镜头目视 |
| DNA 一致 | 背景/强调色/配色令牌、禁用效果 | 账号 `brand.palette` + 视觉门 |

## 2. 逐镜头结果（14 镜）

字幕/旁白来自 `script/script.json`；动画类型来自 `motion/shot-plan.json`。抽帧见 `deliverables/visual-improvement/evidence/frames/` 与 `_tmp/visual-review/`。

| # | 镜头 | 动画类型 | 文案要点 | 信息清晰 | 动效同步 | 概念可懂 | DNA 一致 | 结论 |
|---|---|---|---|---|---|---|---|---|
| 1 | fi01 | comparison_reveal | 三类镜头不是万能库 | 部分：X/check 符号可见，说明字偏小 | 与钩子旁白一致 | 可懂 | 一致 | 可读性问题（见 3.1） |
| 2 | fi02 | code_focus | 分镜→镜头→Easel 四阶段 | 清晰：四阶段卡可读 | 一致 | 架构链清晰 | 一致 | 通过 |
| 3 | fi03 | code_focus | 版本/commit 写在 pin 文件 | 清晰：真实截图 + 关键行高亮 | 一致 | 代码重点明确 | 一致 | 通过 |
| 4 | fi04 | state_transition | 升级要批准不是配置 | **差：状态标签深色压深底，几乎不可读** | 一致 | 状态迁移看不出先后 | **配色令牌冲突** | 修复（见 3.1） |
| 5 | fi05 | code_focus | 2–8 秒静音竖屏 30 帧 | 清晰：截图 + 关键行 | 一致 | 明确 | 一致 | 通过 |
| 6 | fi06 | code_focus | 无真实录屏就阻断 | 清晰：MISSING_REAL_RECORDING 行高亮 | 一致 | 明确 | 一致 | 通过 |
| 7 | fi07 | code_focus | 解释账号拒绝录屏 | 清晰：FORBIDDEN 行高亮 | 一致 | 明确 | 一致 | 通过 |
| 8 | fi08 | architecture_flow | 六个模板编译到三个语法 | **差：architecture_flow/state_transition/code_focus 标签深色压深底，几乎不可读；画面约 70% 空白** | 一致 | 节点链勉强可辨但读不出 | **配色令牌冲突** | 修复（见 3.1） |
| 9 | fi09 | comparison_reveal | 生成动画不是证据 | 部分：符号可见，说明字偏小 | 一致 | 可懂 | 一致 | 可读性问题（见 3.1） |
| 10 | fi10 | state_transition | 缓存看身份不看文件名 | **差：状态标签深色压深底** | 一致 | 状态顺序不可读 | **配色令牌冲突** | 修复（见 3.1） |
| 11 | fi11 | architecture_flow | 任一变就重渲（五类输入） | **差：模板/参数/来源等标签深色压深底** | 一致 | 五类输入看不清 | **配色令牌冲突** | 修复（见 3.1） |
| 12 | fi12 | code_focus | PASS 之后还要人审 | 清晰：截图 + 关键行 | 一致 | 明确 | 一致 | 通过 |
| 13 | fi13 | architecture_flow | 三步复现 | **差：步骤标签深色压深底** | 一致 | 三步顺序不可读 | **配色令牌冲突** | 修复（见 3.1） |
| 14 | fi14 | comparison_reveal | 能跑通≠能发布 | 部分：符号可见，说明字偏小 | 一致 | 可懂 | 一致 | 可读性问题（见 3.1） |

## 3. 发现的问题与修复

### 3.1 深色压深底导致解释性标签不可读（已修复并重渲）

**根因（代码级、可复现）**：`y3_whiteboard` 语法把 `draw` cue 的文字与笔画直接用 `INK = spec.theme.ink` 画在 `BOARD = spec.theme.bg` 上（真实运行时 `.../engine/clips/y3_whiteboard.js` 第 163–164、B.text 调用处确认）。未来智能权威 `brand.palette` 为 `ink:#202B31`、`base/bg:#0F1117` —— 这是一个"浅底深字"的 ink 令牌被用在了深底上。WCAG 相对亮度对比约 **1.30:1**，远低于 3:1 可读性下限。

**影响**：fi04 / fi08 / fi09 / fi10 / fi11 / fi13 / fi14（及同类 fi01 的 draw 部分）的架构节点、状态标签、输入清单、对比说明字在深底上几乎消失；观众无法直接从画面理解"六模板→三语法"、状态先后、五类指纹输入。这不是动效指标问题，而是信息表达失败。

**修复（模板参数，非上游改动）**：在项目自己的 `scripts/prepare_motion_plan.py` 加一个受语法与亮度双重约束的重写：
- 仅当 `grammar == y3_whiteboard`、板面为深色（`bg` 相对亮度 < 0.25）、ink/bg 对比 < 3.0、且同一权威调色板存在更亮的 `surface` 令牌时，才把该镜头 spec 的 `theme.ink` 设为 `theme.surface`（`#F9FBFA`）。
- 不改 `accent`、不改 `bg`、不恢复旧版嵌套 `motion_profile` 调色板、`t2_keynote_ui` 代码卡镜头（深字压浅卡，本来就可读）保持不动。
- 不触碰 Easel 上游、不触碰冻结的 Huashu 运行时、不新增依赖、不加镜头运动。
- 新 spec 以内容寻址文件名写入并由 `motion/shot-plan.json` 重新指向，因此缓存指纹变化、触发真实重渲；修复决策写入 `receipts/motion-plan-preparation.json.readability_fix`。

**修改前后对比证据**：见 `CONTRAST-FIX-EVIDENCE.md` 与 `deliverables/visual-improvement/`。

### 3.2 静止等待与动效指标（不修改）

视觉门 `fast_ratio=0.0497`（黄灯 6% 线）、`max_event_gap_s=28.33`、`still_ratio=0.604`。逐镜头复核后确认：
- 缺口落在解释性镜头的中后段，但画面并非空白；字幕与旁白持续推进，观众有明确阅读对象（代码关键行 / 节点链）。
- 唯一真正影响理解的是 3.1 的标签不可读，已通过配色修复；未通过"加推镜/闪动"去抬高 `fast_ratio`，符合任务禁止项。
- QC 阈值与检查逻辑保持原样，黄灯判定 `verdict=pass` 不阻断。

### 3.3 代码重点与素材来源

fi03/fi05/fi06/fi07/fi12 为 `t2_keynote_ui` + 已登记真实代码截图 + 关键行 highlight，逐帧可读、重点明确，且绑定 `contentops_source.sha256`。这类镜头无需修改，也不得把生成画面冒充实测证据。

## 4. 双账号 DNA 一致性

- 未来智能（本片）：90–120s 目标、工程解释主体、70% 矢量 / 25% 代码 / 5% 图表、拒绝桌面录屏、`#0F1117` + `#38BDF8`、禁用弹跳/闪烁/摇晃/蓝紫渐变/玻璃拟态。逐镜头复核：无桌面录屏、无鼠标操作、配色与 DNA 一致（修复后 ink 仍取自 DNA 的 `surface` 令牌），禁用效果未见。本片为 99.744s，落在区间内。
- 1024：本片不是 1024 账号成片；缺少授权真实录屏，正式生产保持 `MISSING_REAL_RECORDING` BLOCKED（见 `RECORDING-CAPTURE-PLAN-1024.md`）。动画不计入 70% 录屏时长。

## 5. 结论

- 逐镜头信息表达：11/14 镜头直接可读；3.1 修复使 7 个解释性镜头从"标签不可读"提升为"清晰可读"，另 3 个 comparison 镜头符号可读、说明字偏小但不影响核心信息。
- 本次为**视觉工程验收 + 修复后重渲**，仍不是人工终审；全部状态维持 `production_ready=false` / `publish_authorized=false` / `PENDING_FOUNDER_REVIEW`。
