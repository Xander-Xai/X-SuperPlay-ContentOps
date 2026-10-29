---
status: superseded
superseded_by: research/archive/dy1024-skills-2026-10-28/README.md
historical_context: copied contract from the retired dy_x1024 workspace; archived, not routed to
source: dy_x1024@a5952a44dbf47d44c1a4bf475e3653b542c25ac1
date: 2026-10-28
name: clean-talking-video
description: Use when a single raw talking-head or spoken video contains filler words, breaths, false starts, repeated takes, or long pauses and must become a polished edited video with an exactly matching SRT, without processing a second recording.
---

# 口播视频自动剪辑

## 核心边界

把一支原始口播视频剪成可继续包装或直接交付的成片，同时生成与成片时间线严格一致的 SRT。

- 只输入一支含有效人声的视频；
- 删除无意义气口、口头禅、口误、连续重复、失败重说和过长停顿；
- 润色字幕中的识别错误、术语、标点和断句，不改写讲者观点；
- 不接收第二支视频，不做音视频对齐，不制作 MG；
- 固定交付 `edited-video.mp4` 和 `final-clean.srt`。

不要依赖用户电脑上的其他项目或 skill。只调用本目录的脚本和公开依赖。

## 1. 检查环境与输入

从当前 `SKILL.md` 所在目录确定 `SKILL_DIR`，不要硬编码安装路径。
使用 Python 3.9–3.13，并在工作目录创建独立虚拟环境。默认调用 `python3`；
如果它指向 Conda/Anaconda，先把 `PYTHON_BIN` 设置为系统或独立安装的 Python。

```bash
ffmpeg -version
ffprobe -version
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" -c 'import sys; assert (3, 9) <= sys.version_info[:2] <= (3, 13); print(sys.executable, sys.version)'
"$PYTHON_BIN" -m venv "WORK_DIR/.venv"
SKILL_PYTHON="WORK_DIR/.venv/bin/python"
"$SKILL_PYTHON" -m pip --version
"$SKILL_PYTHON" -m pip install -r "$SKILL_DIR/requirements.txt"
ffprobe -v error -show_streams -show_format -of json "SOURCE_VIDEO"
```

确认输入同时含视频流和清晰的人声轨。保留原文件，把所有中间产物写入独立工作目录。
如果虚拟环境没有 pip，或 macOS 上出现 `OMP: Error #15`、重复加载
`libiomp5.dylib`，说明选错了 Python 或混入多个 OpenMP 运行库。删除工作目录里的
虚拟环境，把 `PYTHON_BIN` 指向系统/Homebrew/官方 Python 后重新创建；不要用 Conda
Python 创建。

## 2. 生成带逐词时间戳的转录

为保证识别、剪点和最终 SRT 的效果，本 Skill 只走两条转写路径。默认使用 `auto`：如果环境中有 `DASHSCOPE_API_KEY`，优先调用[阿里云 DashScope](https://help.aliyun.com/zh/model-studio/non-realtime-speech-recognition-user-guide) 的 `qwen3-asr-flash-filetrans`；否则直接使用官方本地 [Qwen3-ASR](https://github.com/QwenLM/Qwen3-ASR)。

```bash
"$SKILL_PYTHON" "$SKILL_DIR/scripts/transcribe.py" \
  --input "SOURCE_VIDEO" \
  --output-dir "WORK_DIR/asr" \
  --provider auto \
  --language zh \
  --prompt "课程专有名词，用逗号分隔"
```

DashScope 路径会生成保持原时间原点的 16 kHz 单声道音频，并上传到 DashScope 官方 48 小时临时存储。它只需要 API Key，不需要用户配置 OSS Bucket、OSS AccessKey 或本地其他项目。临时上传完成后，脚本以 `enable_words=true` 获取逐词时间戳。

不要把 Base64 的 `qwen3-asr-flash` 当成这里的首选：它虽然能直接识别短音频，但响应不含剪辑所需的逐词时间戳。只有 `qwen3-asr-flash-filetrans` 的异步接口适合本流程。

选择规则：

- `--provider auto`：先尝试 DashScope；没有 API Key 或云端不可用时自动切换到本地 Qwen3-ASR；
- `--provider dashscope`：强制使用 DashScope，缺少 API Key 或调用失败时直接报错；
- `--provider qwen-local`：跳过云端，直接使用本地 Qwen3-ASR。

本地路径必须额外安装官方 `qwen-asr` 包：

本地 Qwen 路径使用 Python 3.9–3.12；Python 3.13 没有本流程所锁定的
PyTorch/NumPy 兼容组合。使用 Python 3.13 时应走 DashScope，或另建
Python 3.9–3.12 的工作环境。

```bash
"$SKILL_PYTHON" -m pip install -r "$SKILL_DIR/requirements-qwen-local.txt"
```

默认使用 `Qwen/Qwen3-ASR-1.7B` 做识别，同时加载 `Qwen/Qwen3-ForcedAligner-0.6B` 输出词/字级时间戳；不要删除 ForcedAligner，也不要关闭 `return_time_stamps`，否则无法可靠剪气口和重建 SRT。两者都支持替换为预先下载的本地模型目录：

```bash
"$SKILL_PYTHON" "$SKILL_DIR/scripts/transcribe.py" \
  --input "SOURCE_VIDEO" \
  --output-dir "WORK_DIR/asr" \
  --provider qwen-local \
  --language zh \
  --local-model "/models/Qwen3-ASR-1.7B" \
  --local-aligner "/models/Qwen3-ForcedAligner-0.6B"
```

这一步生成：

- `transcript.json`：逐句、逐词原始时间戳；
- `draft.srt`：只用于复核 ASR，不是最终字幕。

使用 DashScope 前先在环境中设置 `DASHSCOPE_API_KEY`；区域或工作区有专用入口时，可同时设置 `DASHSCOPE_ASR_BASE_URL`。`--prompt` 只传给 DashScope 作为术语上下文。本地 Qwen3-ASR 首次运行会下载 1.7B 识别模型和 0.6B ForcedAligner，模型文件约 6 GB，连同依赖和工作文件应预留至少 10 GB 空闲磁盘；只有 CPU 时可以运行但会很慢，16 GB 内存机器可能大量使用交换空间，应优先使用 NVIDIA GPU。不要为了省资源擅自换成低质量模型并把未经完整复核的字幕作为正式交付。

## 3. 生成停顿压缩草案

```bash
"$SKILL_PYTHON" "$SKILL_DIR/scripts/build_edit_plan.py" \
  --transcript "WORK_DIR/asr/transcript.json" \
  --output "WORK_DIR/edit-plan.json"
```

草案会压缩片头片尾静音和过长停顿，并在 `review_items` 中标出明显口头禅与紧邻重复。它不会擅自删除有语义风险的词。
review_items 只是提示，不是完整删除清单；短句重启、隔句重说和换一种说法重新录制，未必能被机械规则发现。

## 4. 用 Agent 完成内容精剪与字幕润色

读取 `transcript.json`、`draft.srt` 和 `edit-plan.json`，必要时听取对应时间段，再修改 `edit-plan.json`：

1. 逐段检查整份 `transcript.json`，不能只处理 `review_items`。
2. 把确定要删的区间加入 `delete_ranges`，使用原视频时间码。
3. 连续重复或失败重说默认保留最后一次完整、自然的表达。
4. 删除“嗯、呃”等口头禅前先听上下文；承担语气或语义时保留。
5. 删除气口或呼吸声时，把剪点放在静音处，不要切到相邻字头、爆破音或尾音。
6. 保留正常的强调、思考停顿，以及文字相似但语义作用不同的句子。
7. 更新 `subtitles`：删掉已剪内容，只修正识别错误、术语、标点和断句；不要总结、缩写或补写原视频没说的话。
8. 长字幕要拆行时，使用对应的 `source_start` 和 `source_end`，确保每条字幕仍能映射到保留片段。

`base_keep_segments` 负责停顿压缩，`delete_ranges` 负责内容删除。不要手算输出时间码；渲染脚本会统一重映射视频、音频和字幕。

## 5. 渲染成片与最终 SRT

```bash
"$SKILL_PYTHON" "$SKILL_DIR/scripts/render_edit.py" \
  --video "SOURCE_VIDEO" \
  --plan "WORK_DIR/edit-plan.json" \
  --output-dir "OUTPUT_DIR" \
  --full-decode
```

渲染脚本只处理这一支视频，会：

- 根据审核后的计划生成连续剪辑时间线；
- 同步裁切画面与原音频；
- 把字幕从原始时间码重映射到成片时间码；
- macOS 硬件编码器初始化失败时自动回退到 `libx264`；
- 完整解码成片并检查容器、视频流和音频流时长。

## 6. 验收

交付前必须确认：

- `edited-video.mp4` 与 `final-clean.srt` 都存在；
- 视频、音频从 `00:00` 开始，声音与口型同步；
- SRT 第一条不早于 0，最后一条不超过成片时长；
- 每条字幕都忠实对应保留下来的实际口播；
- 首段、中段、末段及所有短剪点无吞字、跳音、黑帧或语义断裂；
- `edit-report.json` 的容器、视频流、音频流时长均通过校验。

## 最终交付

- `edited-video.mp4`：删除气口、重复、口误和冗长停顿后的口播成片；
- `final-clean.srt`：与成片逐段匹配的润色字幕。

`edit-plan.json`、`edit-timeline.json` 和 `edit-report.json` 是可追溯中间产物，不要冒充主交付。需要继续制作 MG 时，可把成片与最终 SRT 作为下一流程的输入；本 skill 本身不依赖任何后续流程。

脚本或流程出现缺陷时，先增加失败测试，再修复。
