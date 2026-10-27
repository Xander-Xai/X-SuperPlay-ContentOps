---
status: experiment
canonical: false
issue: "#34"
date: 2026-10-27
---

# X 高流量自媒体视频 skill 调研与采纳清单

> 目的：找出高互动自媒体账号在用的开源视频能力，只采纳能补我们两条账号工作流的
> 部分。不是把看到的项目全部装进来。所有仓库数据取自 `gh repo view`，帖子数据取自
> `twitter search --json`，链接由 `t.co` 展开。

## 方法与样本

- 使用 `agent-reach` 的 X/Twitter 后端（`twitter-cli`，Cookie-Editor 凭据已配置）。
- 8 个查询，去重后 **71 条帖子**：
  `AI 短视频 工作流`、`AI 视频 自动化 github`、`Claude 动画 视频`、
  `short video factory github`、`Kokoro TTS github`、`AI 自媒体 工作流`、
  `HyperFrames`、`AI presenter video github`。
- 按 `likes + 2×bookmarks + views/100` 排序，取前 15 条读正文与链接。
- `t.co` 链接用 `curl -sIL -o /dev/null -w '%{url_effective}'` 展开；
  仓库 star 数用 `gh repo view --json stargazerCount` 核对。

## 高互动信号（原帖）

| 作者 | 互动 | 内容 | 链接 |
|---|---|---|---|
| @shanyanggm | 13,153 L · 28,368 B · 1,113,896 V | 6 个免费开源项目，含 HyperFrames、MoneyPrinterTurbo | https://x.com/shanyanggm/status/2098941338297458746 |
| @KinGao476942 | 8,434 L · 21,381 B · 664,313 V | 8 个 Opus 5.5 视频仓库，含 lemo-opuscar、awesome-opus5-5-videos | https://x.com/KinGao476942/status/2112729924943634602 |
| @bkdgiffug | 4,216 L · 6,254 B · 247,241 V | OpenMontage：一句话出脚本/素材/配音/字幕/成片 | https://x.com/bkdgiffug/status/2108996989639880965 |
| @Saccc_c | 2,757 L · 3,433 B · 424,493 V | HyperFrames 视频版教程 | https://x.com/Saccc_c/status/2051959327557034478 |
| @taozi0929 | 1,535 L · 2,118 B · 104,321 V | lanshu-create-ai-presenter-video，本地数字人成片 | https://x.com/taozi0929/status/2103709398325727546 |
| @GeekCatX | 1,323 L · 1,905 B · 158,818 V | Vox 风格 4 步：拆镜 → 生图 → 转视频 → 自动剪辑 | https://x.com/GeekCatX/status/2078488413045747814 |
| @HyperFrames_ | 993 L · 977 B · 549,301 V | HyperFrames Studio 上线 Windows | https://x.com/HyperFrames_/status/2114773205651275793 |
| @Xian0063 | 195 L · 294 B · 16,466 V | Claude 动画攻略：4 条路线、11 种风格、30+ 工具 | https://x.com/Xian0063/status/2113191730778640822 |

> 以上均为真实 post id（`twitter search --json` 返回）。X 文章页对未登录抓取返回 404，未把文章正文当作已读事实。

## GitHub 仓库与采纳决策

| 仓库 | Stars | 它做什么 | 决策 | 理由 |
|---|---:|---|---|---|
| `heygen-com/hyperframes` | 73,396 | Write HTML. Render video. Built for agents. | **ADOPT** | 项目已装该 skill；用来做冷开场/动效层，不改主生产链；无本地 AI 模型 |
| `calesthio/OpenMontage` | 72,277 | Agentic 视频生产系统，12 条产线 | **REJECT** | 与 ContentOps 主引擎重复，违反“不建第六套生产系统” |
| `harry0703/MoneyPrinterTurbo` | 135,591 | 主题/关键词一键生成高清短视频 | **REJECT** | 同上；只借鉴“一源多平台”包装思路 |
| `YILS-LIN/short-video-factory` | 5,930 | 一键产品营销短视频，桌面端 | **REJECT** | 完整产线，重复 |
| `Anil-matcha/AI-Youtube-Shorts-Generator` | 5,623 | 长视频 → 9:16 Shorts | **DEFER** | 对已发布内容做二次分发时有用；需 ASR/LLM，当前先不引入 |
| `cclank/lanshu-create-ai-presenter-video` | 2,819 | 文案 + 授权照片 → 数字人成片 | **DEFER** | 属于 Presenter 层；当前两条讲解片不需要人脸/口型 |
| `hexgrad/kokoro` | 9,699 | Kokoro-82M 本地 TTS | **DEFER** | 我们已有 MiniMax 克隆声 API；本地 TTS 不升级音色 |
| `lemomo-ai/lemo-opuscar` | 8,316 | 59 种代码化片头/电影风格，Claude Code skill | **EXTEND** | 不整包安装；借它的动效风格命名与节奏，写进 HyperFrames 冷开场 |
| `yihui-dev/awesome-opus5-5-videos` | 11,662 | 爆款视频 prompt 合集 | **REFERENCE** | 只做选题/画面参考，不进生产链 |

## 本次实际接入

### 1. HyperFrames 冷开场（两个账号各一条）

- 1024：2.5 s 暖纸红印章，开场即结论——`实测结论 / 能跑，但 Web 不行。`
  - 源：`projects/x-superplay-1024/motion/index.html`
  - 渲染：`npx hyperframes@0.8.206 render`，75 帧，2.5 s
- 未来智能：2.5 s 靛蓝工程 slate，逐行证明——`先证明，再谈能不能用。`
  - 源：`projects/x-superplay-future-intelligence/motion/index.html`
  - 渲染：同版本，75 帧，2.5 s
- 接入点：`config/accounts/*.json` 的 `visual.motion_intro`；
  `scripts/build_account_variants.py` 读取后作为 `intro_outro.attach --intro`。

### 2. 没有接入的，以及为什么

- 不是“能力不够”，而是“会重复建设”或“现在不需要”：OpenMontage、
  MoneyPrinterTurbo、Short Video Factory 都是整条产线；接进来会与
  ContentOps 的所有权规则冲突。
- Presenter、长视频切片、Kokoro 属于后续阶段；在两条讲解片没有发布数据前，
  引入它们只会增加变量。
- 全部方案遵守无 GPU 模型：HyperFrames 用 Chromium 截图渲染，不是本地
  diffusion/LLM；MiniMax 语音/图片/视频仍走 API。

## 复现

```powershell
# 1024 冷开场
cd projects/x-superplay-1024/motion
npx hyperframes@0.8.206 render
# 把 renders/*.mp4 复制为 outputs/account-variants/1024-stamp.mp4

# 未来智能冷开场
cd projects/x-superplay-future-intelligence/motion
npx hyperframes@0.8.206 render
# 复制为 outputs/account-variants/fi-slate.mp4

python scripts/build_account_variants.py
```

## 约束

- 不因动效阻塞 Baseline：冷开场失败时，`build_account_variants.py` 仍可用静态
  `intro-editorial.mp4`。
- 不自动发布；发布包停在 `PENDING_FOUNDER_REVIEW`。
- 不把 X 帖子的互动量当作我们的增长证据；它只用于筛选工具。
