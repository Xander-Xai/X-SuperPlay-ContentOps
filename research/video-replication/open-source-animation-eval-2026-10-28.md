---
status: experiment
canonical: false
issue: "#34"
date: 2026-10-28
---

# Build 组动画层：开源代码渲染 skill 选型评估

> 目的：为 X超玩·未来智能（Build 组）选一个**已有的开源代码渲染 skill** 作为动画层，
> 不自研动画引擎。红线：零录屏、零鼠标、只允许矢量图/静态截图/指标图/代码动画。
> 本文件是只读调研结论；**尚未集成、尚未渲染样片**，等创始人确认选型后进入第三步。

## 0. 评估环境（本机实测）

| 项 | 值 |
|---|---|
| 系统 | Windows 11，PowerShell |
| Python | 3.13.15，`playwright` 与 `numpy` 已安装 |
| `uv` | 0.11.18（x86_64-pc-windows-msvc） |
| Node | 24.16.0 |
| ffmpeg / ffprobe | 8.1.1 |
| 仓库获取 | `git clone --depth 1`；两个大仓库用 `--filter=blob:none --no-checkout`，只读树与指定文件，不下载 78–145 MB 资产 |
| 本次未做 | 未运行任何仓库的渲染脚本，未安装任何依赖；以下结论来自 README/SKILL.md/源码契约 |

## 1. 三个仓库是什么（不是同一层东西）

| 仓库 | 本质 | 规模 | 许可证 |
|---|---|---|---|
| `Kianzzz/xilo-opus-video` | **流程 Skill**：三方案 → 预览 → brief → 逐镜渲染；自带一个 `render(t)` 截图器 | 302★，1.9 MB | MIT |
| `alchaincyf/huashu-art-motion` | **讲解动画引擎 + 语法库**：镜头表、8 个参数化讲解语法、scenes、lint/qa/deliver | 5,538★，78 MB | MIT |
| `lemomo-ai/lemo-opuscar` | **风格库 + 完整影视工具链**：59 种风格，画面/TTS/ASR/配乐/字幕/混音一条龙 | 8,673★，145 MB | MIT（素材 CC BY 4.0） |

## 2. 逐项回答四个问题

### 2.1 Windows + PowerShell + Python 3.13 能否跑通？依赖是 Node 还是 Python？

| 仓库 | 依赖 | Windows 结论 | 证据 |
|---|---|---|---|
| xilo-opus-video | Python 3.9+、`numpy`、`playwright`(Python)、ffmpeg；浏览器按自带 Chromium → Chrome → Edge 依次回退 | **可以**。`check_env.py` 直接给 winget 的 ffmpeg 安装提示；`render.py` 的浏览器回退里包含 `msedge` | `scripts/check_env.py`、`scripts/render.py` |
| huashu-art-motion | `uv` + Python + `playwright` + ffmpeg；引擎是 HTML/JS，由无头 Chromium 逐帧截图 | **大概率可以，但仓库没有声明 Windows 验证**。`render.py` 是纯 Python（http.server + playwright + ffmpeg 管道）；示例里的 `sh` 只是命令示例。兼容性文档写明 CI 在 Linux、真实媒体测试在 macOS | `references/compatibility.md`、`scripts/engine/render.py` |
| lemo-opuscar | Node 20+、ffmpeg、Python 3.11+；核心依赖 `playwright-core`、`three`；3D/着色器风格要 GPU | **官方要求 Windows 用 WSL**，原生 Windows 不在支持范围 | `TECHNIQUE.md` §1：*"on Windows use WSL"*；`package.json` |

**结论**：原生 Windows 的可行性排序 `xilo ≈ huashu > lemo`。lemo 的 WSL 要求会在我们“Windows-first、无 WSL 边界”的仓库里多出一层运行环境，这是硬减分项。

### 2.2 输入输出契约：吃什么，吐什么？

| 仓库 | 吃 | 吐 | 时长控制 |
|---|---|---|---|
| xilo-opus-video | 想法 / 文章 / 口播稿 / 产品网址 / 参考视频；确认后的 `brief.md` | 工程目录：`source/ previews/ brief.md index.html audio/ qa/ out/final.mp4`；页面暴露 `window.render(t)` | `render.py --duration` / `--start`，按帧截取；无逐段精确契约 |
| huashu-art-motion | `镜头表.md`（逐镜：时间/物/动作/镜头/屏上字/做法），可选 `文稿.txt` | 每镜一个 mp4（spec 模式）或整片 mp4；另有静帧、audit JSON、QA 报告 | **`--spec` 时严格 `duration = spec.duration`**；单参数化片段上限 8 s（超了警告并建议拆镜） |
| lemo-opuscar | 风格名 + 故事/主题；可选素材、自有声音 | 工程目录 + `video.mp4` + `mix.wav` + `.srt` + 成片；页面暴露 `DUR/render(t)/EV/TEXTS` | `--duration`/`--fps`/`--size`；按 `render(t)` 帧渲染 |

**对我们的关键差异**：我们是 **audio-first**（先配音、按实测时长生成分镜）。huashu 的 `--spec` 天然接受“精确到毫秒的片段时长”，正好把实测语音长度写进 spec；xilo 是“先定总时长再渲染”，需要我们自己把每段时长切好；lemo 是自带一条完整时间线，接我们的音频要先绕开它的混音。

### 2.3 怎么接现有配音（220–260 字/分男声）和字幕模块？

| 仓库 | 配音接入 | 字幕接入 |
|---|---|---|
| xilo | `render.py ... --audio audio/mix.wav` 直接吃一条整轨。我们的 MiniMax 逐句 WAV 可 concat 成 `narration.wav` 传入；但它的规范建议“配音整段合成，不要一句一句拼”，与我们的逐句缓存相反，需要在 receipt 里说明 | 无内建字幕；由我们的 `assemble_easel.py` 烧录 DNA 字幕 |
| huashu | 片段默认无声；整片模式 `--audio` 接受一条音轨；自带的可选语音（macOS 系统声 / 火山复刻）与本仓库无关，不启用 | 无内建字幕；同样由我们的 `assemble_easel.py` 烧录 |
| lemo | 内置 TTS（Kokoro/edge-tts）、ASR 回读、字幕、−14 LUFS 混音；要用我们的语音就得替换它的 `mix.py` 输入，侵入面最大 | 内建 `.srt` + 烧录，但样式不受我们 DNA 控制 |

**结论**：xilo / huashu 都能“只当渲染器”，音轨和字幕留在我们自己的管线里；lemo 的强项是整条声音链，但这也意味着更多替换工作，且被 WSL 卡住。

### 2.4 哪个当 P0 主管线，哪个只当风格库？

| 角色 | 推荐 | 理由 |
|---|---|---|
| **P0 主管线（动画层）** | **huashu-art-motion** | 唯一同时具备：讲解语法（3b1b / keynote UI / 财经图表 / kurzgesagt / VOX / 白板 / kinetic type）、逐段精确时长、竖屏 1080×1920、镜头表 lint、qa/deliver 门禁、MIT、原生 Python + playwright。正好补上我们“有动效但没有语法体系”的短板 |
| **流程层参考** | **xilo-opus-video** | “三方案 → 预览 → brief → 逐镜静帧自检”的流程值得照搬；它的渲染器很小，不需要再引入一套运行时 |
| **风格库参考** | **lemo-opuscar** | 59 种风格清单和 `STYLE.md` 写法可借鉴；但原生 Windows 不支持（WSL），暂不接入 |
| 不采用 | Remotion / Manim | Remotion 非 OSI 许可；Manim 与现有链路重复 |

## 3. 对比表（决策用）

| 维度 | xilo | huashu | lemo |
|---|---|---|---|
| 定位 | 流程 Skill | 讲解动画引擎 | 风格库 + 影视工具链 |
| 原生 Windows | ✅ 有 winget 提示与 Edge 回退 | ⚠️ 未声明验证，代码跨平台 | ❌ 官方要求 WSL |
| 依赖 | Python + playwright | uv + Python + playwright | Node + three + playwright-core |
| 精确片段时长 | ⚠️ 总时长/起点 | ✅ `duration = spec.duration` | ✅ 帧级 |
| 竖屏 1080×1920 | ✅ `--size` | ✅ spec / `--width --height` | ✅ `--size` |
| 讲解语法库 | ❌ 靠模型自由发挥 | ✅ 8 个参数化语法 + 9 种语法文档 | ✅ 59 风格（偏艺术） |
| 质量门禁 | 自检清单 | ✅ storyboard_lint / qa / deliver / audit | ✅ readcheck / film_gate |
| 接我们的配音 | 整轨 | 整轨或无声 | 替换其混音 |
| 接我们的字幕 | 我们的烧录 | 我们的烧录 | 替换其字幕 |
| 许可证 | MIT | MIT | MIT + CC BY 4.0 素材 |
| 体量 | 1.9 MB | 78 MB | 145 MB |

## 4. 推荐方案（待确认）

1. **接入 huashu-art-motion 作为 Build 组动画层**：只取 `scripts/engine`（render.py、clip.html、clips/、spec schema）与 `references/动画语法`，不启用它的语音模块；镜头表 lint 作为写分镜前的门禁。
2. **流程上吸收 xilo 的“三方案 + 预览”**：每个新选题先出三套构图/语法方案和一帧预览，再进入正式渲染；这一步用现有 HyperFrames 预览即可，不新增运行时。
3. **lemo 只做风格参考**，不接入。

### 接入前必须先验证的三件事（下一步）

1. **Windows 冒烟**：在 `D:\Temp\AI-Agents\claude\<task>` 用 huashu 的 `render.py --spec` 渲一个 3 s / 1080×1920 片段，确认 `uv run --with playwright` 在本机可用、无 WSL。
2. **时长契约**：用我们一条真实配音的实测时长（如 3.239 s）生成 spec，确认输出帧数 = `round(duration×fps)`，音画不漂移。
3. **许可证与署名**：MIT 代码可商用；若用到 lemo 的 CC BY 4.0 素材，必须署名——本轮不接 lemo，先不触发。

## 5. 风险与限制

- huashu 的 78 MB 仓库里含大量示例资产；接入只应复制 `scripts/engine` 与语法文档，不整包进主仓库。
- 它的参数化片段上限 8 s，与我们 5 s 的 beat 兼容；但如果以后做长镜头，需要拆段。
- 三个仓库的“风格”都依赖强模型生成代码；我们的实现要保留 receipt 和静帧 QA，不能把“生成成功”当成“可发布”。
- 本文件没有跑过任何渲染，因此**不声称**三者在本机已通过；Windows 兼容性结论来自源码与文档，不是实测。

## 6. 复现命令（只读）

```powershell
# 小仓库：普通浅克隆
git clone --depth 1 https://github.com/Kianzzz/xilo-opus-video.git D:\Temp\AI-Agents\claude\repos-inspect\xilo-opus-video

# 大仓库：blobless，不检出资产
git clone --depth 1 --filter=blob:none --no-checkout https://github.com/alchaincyf/huashu-art-motion.git
git -C huashu-art-motion ls-tree -r --name-only HEAD
git -C huashu-art-motion show HEAD:SKILL.md
```
