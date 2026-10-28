---
status: experiment
canonical: false
issue: "#34"
date: 2026-10-28
---

# 免费配乐与权威素材：方案调研与落地

> 触发：创始人反馈「当前太呆了」，要求找免费配乐与配素材项目；权威资料的架构图优先。
> 结论先说：**配乐用本机合成，素材用 Mermaid 重绘官方架构**；不引入无许可证的素材包。

## 1. 配乐

### GitHub 检索结果（`gh search repos`）

| 仓库 | Star | 许可证 | 判断 |
|---|---:|---|---|
| `timothymeehan/ambient_music_generator` | 10 | none | 无许可证，不能接入 |
| `ianjamesburke/nooise` | 10 | none | 同上 |
| `madmonk13/relax`、`joeld42/astral`、`kili-d/aether` | ≤3 | none | 实验代码，不适合生产 |
| `sevagh/OnAir-Music-Dataset` | 37 | none | 数据集，非生成工具 |
| `Tonejs/Tone.js`（未在短列表中出现，但为已知 MIT 项目） | — | MIT | 可用于程序化音乐；本轮不需要额外依赖 |

**判断**：免费 BGM 的可靠来源是 CC0 曲库（FreePD、Pixabay Music）或程序化合成，而不是这些无许可证的小仓库。CC0 曲库仍需下载、记来源与时长；对 45 秒工程讲解，程序化合成更可控。

### 本轮落地：本机合成

`scripts/synthesize_ambient_bed.py`：

- 三个失谐正弦（55 / 82.5 / 110 Hz）+ 慢速 LFO + 低通噪声底；
- 固定 seed，逐样本确定性；
- 峰值 −24.4 dBFS，和声峰值 −1.5 dBFS，**余量 22.9 dB**（规则要求 ≥18 dB）；
- 无采样库、无 provider、无许可证义务；
- 混音在组装器内完成，收据记录两个峰值与余量。

DNA 里 BGM 原本是 `OMITTED_BY_POLICY`（缺 DashScope key，禁止 video_ops 响度回退）。本轮按创始人明确指示改为**本地合成**，不是被禁的回退路径；收据 `bgm.status: CODE_SYNTH` 如实标注。

## 2. 权威架构素材

### 检索结果

GitHub 上「AI Agent architecture」类仓库多为个人笔记（0–2 star、无许可证），不能作为权威来源。可用的**渲染器**是：

| 项目 | 许可证 | 用途 |
|---|---|---|
| `mermaid-js/mermaid` | MIT | 从文本渲染流程图/时序图，适合重绘官方架构 |
| `mingrammer/diagrams` | MIT | Python 画云架构图；本轮不需要 |

### 路线

不直接搬运官方文档图片（版权与授权不明）。改用 **Mermaid 重绘**，并在画面与收据里标注「重绘自 <来源>」：

1. 以官方文档（如 Anthropic《Building effective agents》的 workflow vs agent 区分、MCP 规范的 host/client/server 结构）为**内容来源**；
2. 用 Mermaid 重新绘制结构，不复制原图；
3. 画面角落标注来源与「重绘」，收据记录来源 URL 与访问日期；
4. 生成的图作为 `image` 素材进入 t2 的满幅卡，不冒充截图。

本轮未落地该图：45 秒片已经排满，下一轮先做「workflow vs agent」这一张，替换 P02 的纯文字卡。

## 3. X 渠道

`agent-reach twitter search` 仍返回 `NEED_LOGIN`。创始人已表示可以协助登录；登录后补跑「AI 讲解视频 动效 / BGM / 架构图」三组查询，结果并入本文件。
