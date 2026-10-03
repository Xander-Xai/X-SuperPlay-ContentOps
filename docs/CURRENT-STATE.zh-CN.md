---
translation_of: docs/CURRENT-STATE.md
language: zh-CN
translation_status: synced
---

# 当前状态

[English](CURRENT-STATE.md) | [简体中文](CURRENT-STATE.zh-CN.md)

> 当前运行状态。仅经验证的事实。无展望，无过时声明。
>
> 最后验证：2026-10-04

## Git

| 属性 | 值 |
|---|---|
| 默认分支 | ```main```（唯一持久分支） |
| Main 保护 | **已保护** — 必需状态检查 + PR + 禁止 force push + 禁止删除 + 线性历史 |
| 必需检查 | ```Tests (ubuntu-latest)``, ```Tests (windows-latest)``, ```Repo policy checks``` |
| 分支策略 | Issue 作用域短生命周期分支，Squash 合并，合并后自动删除 |

## Easel 运行时

| 属性 | 值 |
|---|---|
| 版本 | v0.2.1 |
| Commit | ```3fe2d9904c1619281ef57f81d9ee0b7854998399``` |
| 路径 | ```.runtime/easel/``` |
| 获取方式 | Release archive（GitHub tarball via ```gh api```） |
| 验证 | 982/982 blob SHA-1 匹配上游 tree |
| 锁文件 | ```runtime/easel.lock.json``` |
| 来源记录 | ```runtime/easel-runtime.json``` |

## 流水线

| 属性 | 值 |
|---|---|
| 生产引擎 | ```easel```（Easel ```auto-short-video/assemble.py```） |
| 诊断引擎 | ```fallback```（仅 ffmpeg，非生产） |
| 生产语音 | edge-tts via Easel ```tts.py```（zh-CN-YunxiNeural） |
| 语音质量 | ```edge_tts_fallback``` — 非生产级 |
| 生产就绪 | **否** — READY_FOR_HUMAN_REVIEW |
| 字幕变通 | ```scripts/assemble_easel.py``` — 移除字幕，运行上游，单独烧录（不修改上游） |

## MiniMax

| 属性 | 值 |
|---|---|
| 集成 | **未实现** |
| 能力验证 | **已完成**（Issue #4，2026-10-04） |
| PAYG 允许 | **否** |
| 计费模式 | subscription，**已验证** |
| 传输通道 | 官方 MiniMax CLI `mmx`（`mmx-cli` v1.0.27） |
| 语音 | **VERIFIED** —— `speech-2.8-hd`，32 kHz 单声道 WAV |
| 图像 | **VERIFIED** —— `image-01`，9:16 竖版，支持 seed |
| H3 视频 | **NOT_ENTITLED / BLOCKED** —— H3 需要按量或积分 Key |
| 积分包余额 | 实测 `0.00`，每次生成前重新检查 |
| 证据 | `research/providers/minimax-mplan-explore-capability.md` |

## 已知阻碍

1. 语音质量 — edge-tts 机械感重，非生产级。MiniMax 语音集成（M2）的主要动机。
2. Web 工作台 — 6 项 doctor 失败。不阻塞视频流水线。
3. Gateway healthz — 上游硬编码端口 18789；easel profile 使用 37289。不阻塞视频流水线。
4. 人工审查 — easel-review 项目无 ```human-review.json``` 凭证。
5. ~~Main 分支未保护~~ — **已解决**（G0.6）：main 现已通过 GitHub 分支保护机制保护。