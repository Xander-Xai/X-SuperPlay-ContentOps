---
status: experiment
canonical: false
issue: "#34"
date: 2026-10-28
---

# B-roll 动效：外部资产评估与接入记录

> 触发：创始人评估上一版样片「水平很差，b-roll 动效都垃圾」，要求先看 X，再引入 GitHub 仓库，可以克隆接入。
> 结论：X 检索被登录拦截，未获得新数据；动效能力从 HyperFrames（GitHub，Apache-2.0）接入，花叔/xilo 仓库作为语法与流程参考，未整包接入运行时。

## 1. X 渠道结果（如实记录）

`agent-reach twitter search "AI video b-roll motion graphics workflow"` 返回：

```json
{"ok": false, "error": {"code": "NEED_LOGIN",
 "message": "Not logged into x.com (no ct0 cookie)"}}
```

公开网页后端 `public-web/exa` 有过一次返回，但内容校验为 `INSUFFICIENT_CONTENT`，没有任何可用条目。
按 agent-reach 规则：未代登录、未换后端重试。**本轮没有拿到 X 上的新工作流证据**；此前的 X 扫描结论
（`x-media-workflow-skills-2026-10-27.md`，71 posts / 9 repos）仍是最新可用数据。

## 2. GitHub 仓库评估

数据来自 `gh api repos/<owner>/<name>`（2026-10-28）。

| 仓库 | Star | 许可证 | 版本/状态 | 决策 | 理由 |
|---|---:|---|---|---|---|
| `heygen-com/hyperframes` | 73,951 | Apache-2.0 | CLI `0.8.208`，当日仍在提交 | **ADOPT** | HTML→视频、seek-safe、可本地渲染；许可最干净；仓库此前已用它做冷开场 |
| `alchaincyf/huashu-art-motion` | 5,538 | MIT | 78 MB，含 35 风格 + 9 讲解语法 | **REFERENCE** | 是配方/参考库，不是渲染器；完整克隆超时，改用 GitHub tree 核对结构与语法文件 |
| `Kianzzz/xilo-opus-video` | 302 | MIT | 已浅克隆 | **REFERENCE** | 「三方案→预览→brief→逐镜静帧→渲染」的流程骨架；依赖 Playwright/Chromium，与本仓库 HyperFrames 渲染层重复，不引入第二套运行时 |
| `lemomo-ai/lemo-opuscar` | 8,673 | MIT | 145 MB | **DEFER** | 59 种代码风格片；风格库，等动效语法稳定后再取 |
| `Vincentwei1021/mg-styles-15` | 2,440 | MIT | 568 MB | **DEFER** | 15 种 MG 风格；体积大，先不整包 |
| `remotion-dev/remotion` | 68,269 | NOASSERTION（非 OSI） | 活跃 | **REJECT** | 自定义公司许可，需要额外的许可判断；现有 HyperFrames 已覆盖同一能力 |
| `ManimCommunity/manim` | 41,925 | MIT | 活跃 | **DEFER** | 数学动画强，但讲解链路已由 HyperFrames 覆盖；引入会多一套 Python 渲染依赖 |

registry 块（GitHub 源）也做了抽样：`flowchart-vertical`、`code-snippet-dark-2026`。
两者分别是 1440×2560 白底与 1920×1080 编辑器尺寸，**不能直接用于 1080×1920 深色品牌画幅**，
需要重排全部坐标；因此只作为构图参考，未接入成片。

## 3. 本轮实际接入

`projects/easel-fi-audio-first/motion/` 下 6 个 HyperFrames 工程，每个 5 s / 1080×1920 / 30 fps：

| 工程 | 内容 | 用途 |
|---|---|---|
| `narration-bar` | 44 s 口播条 + 22 个视图单元逐个弹入 | Hook：窗口与视图 |
| `view-swap` | 一个 placement 内 V1/V2/V3 按语义切换、进度条推进 | 取舍：按语义换 |
| `arch-flow` | 节点/箭头绘制、光点巡游、焦点压暗 | 架构链路 |
| `code-sweep` | 代码逐行显现、高亮条扫到关键行 | 关键代码 |
| `metric-count` | 0→1.80 s 计数、2.20 s 限位线、QC PASS | 验收指标 |
| `result-chain` | 8 → 22 → 1.80 s → PASS 链路复算 | 结果收口 |

统一动效规则：5% 细颗粒、1.0→1.035 缓慢推镜、焦点节点压暗其余元素、只用 transform/opacity。
`npx hyperframes check` 全部 0 error；`render -q delivery` 输出 mp4，接入 `kind: motion` 素材。

## 4. 仍然不够的地方（不粉饰）

1. 这是**图解动效**，不是电影感 b-roll（没有实拍/材质/景深镜头）。工程讲解用图解是对的，但如果要“高级感”，
   还需要风格化层（花叔 35 风格里的 3Blue1Brown / VOX / kinetic-type 语法）。
2. X 没有拿到新数据，无法判断对标账号最近是否换了动效语言。
3. registry 专业块尺寸不匹配，未接入；若要用，需要按 1080×1920 重排。
4. 合成本身仍是硬切，Easel 上游没有转场；片段内部连续，切点落在 5 s 边界。
