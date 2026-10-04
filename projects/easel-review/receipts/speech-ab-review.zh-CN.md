---
title: "语音 A/B 评审请求 —— edge-tts 与 MiniMax M Plan"
canonical: false
type: receipt
status: PENDING_FOUNDER_REVIEW
project: easel-review
created_at: "2026-10-04"
language: zh-CN
translation_of: projects/easel-review/receipts/speech-ab-review.md
translation_status: synced
---

# 语音 A/B 评审请求（Issue #19）

> English: [speech-ab-review.md](speech-ab-review.md)

**状态：`PENDING_FOUNDER_REVIEW`。** 尚未记录任何评分，也不会去推测。只有真正听过
的人才能填写。

## 对比内容

源、脚本、分镜、截图、合成方式完全相同，**只有声音不同**。本次实验不涉及图像生成，
也不涉及生成视频。

| | A — 基线 | B — 候选 |
|---|---|---|
| 提供方 | edge-tts（当前兜底） | MiniMax M Plan Explore |
| 模型 | 不适用 | `speech-2.8-hd` |
| 音色 | 系统默认 | `Chinese (Mandarin)_Reliable_Executive` |
| 发音词表 | 无 | `zh-2026.10.04.1` |
| 响度处理 | 无 | 两遍 `loudnorm`，目标 −16 LUFS，上限 −1.5 dBFS |
| 本地文件 | `.verify-tmp/m2/ab/A-edge-tts.mp3` | `.verify-tmp/m2/ab/B-minimax-mplan.wav` |

媒体文件被 gitignore，只存在于构建主机上。

## 实测差异

| 属性 | A — edge-tts | B — MiniMax |
|---|---|---|
| 容器 / 编码 | MP3 | WAV，`pcm_s16le` |
| 采样率 | 24 000 Hz | 32 000 Hz |
| 声道 | 1 | 1 |
| 时长 | 61.92 秒 | 61.77 秒 |
| 整体响度 | **−24.2 LUFS** | **−17.0 LUFS** |
| 真峰值 | −3.3 dBFS | −1.5 dBFS |

试听前请先了解两点：

1. **B 大约响 7 dB。** 这是响度门禁在起作用，不是质量差异。请评判音质而不是音量；
   如果要做公平的音量对比，请先把两者对齐电平。
2. **ASR 检测器在 B 中标记了若干项。** 覆盖率为 0.96，其中 `ping`、`FFmpeg`、
   `.env` 以及词表展开后的 `伊泽尔` 是它无法确认的 token。检测器只是转写检查，
   不是质量结论，因此这些需要用耳朵判断，而不是看转写文本。

## B 的自动化门禁结果

| 门禁 | 结果 |
|---|---|
| 计费前置检查 | `SAFE_INCLUDED_PLAN` |
| PAYG 余额 / 积分包 / 代金券 / 欠费 | `0.00` / `0.00` / `0.00` / `0.00` |
| 技术质检 | **通过**，13 项检查 |
| 归一化后峰值 | −1.5 dBFS，符合上限 |
| 前导 / 尾部静音 | 0.0 秒 / 0.0 秒 |
| 语义（ASR） | `DETECTED_PROBLEM`，覆盖率 0.96 —— 仅为检测 |
| `production_ready` | **false** |

## Founder 评分

请为每列打 1-5 分并附上意见。

| 维度 | A — edge-tts | B — MiniMax |
|---|---|---|
| 自然度 | | |
| 技术术语发音 | | |
| 节奏 | | |
| 情绪 / 表现力 | | |
| 清晰度（可懂度） | | |
| 无 AI 痕迹 | | |
| 总体偏好 | | |
| 是否愿意发布 | | |

## 需要评审者留意的已知问题

- `ping` 读得不清楚，且没有纯文本词表方案可以修复；它需要内联发音覆盖，而这一点是
  被刻意没有擅自猜测的。
- `Web` 在 ASR 听成 `外部` 之后，已用纯文本展开改为 `网页`。请确认这样读是否自然。
- 该黄金脚本包含 `Easel`、`v0.2.1`、`SaaS`、`Skill`、`doctor`、`Python`、`Node`、
  `FFmpeg`、`Agent`、`fastapi`、`uvicorn`、`.env`、`API Key` 与 `CLI`，
  因此这段样本检验的是真实技术词汇，而不是一句容易的话。

## 在填写完成之前

`production_ready` 保持 `false`，任何 narration 都不会被提升为项目素材。
伪造评分比没有评分更糟。