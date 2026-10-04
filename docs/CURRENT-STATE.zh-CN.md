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
| 集成 | 语音**已实现**（Issue #19），`PENDING_FOUNDER_REVIEW` |
| 图像 / 视频集成 | **未实现**（Issue #20、#22） |
| 语音传输通道 | 官方 MiniMax CLI `mmx`；锁定的 Easel 路径为 `EASEL_MPLAN_AUTH_INCOMPATIBLE` |
| 声音克隆 | **DOCUMENTED_BUT_NOT_TESTED**（Issue #23），需要权利清晰的样本 |
| 能力验证 | **已完成**（Issue #4，2026-10-04） |
| PAYG 允许 | **否** |
| 计费模式 | subscription，**已验证** |
| 传输通道 | 官方 MiniMax CLI `mmx`（`mmx-cli` v1.0.27） |
| 语音 | **VERIFIED** —— `speech-2.8-hd`，32 kHz 单声道 WAV |
| 图像 | **VERIFIED** —— `image-01`，9:16 竖版，支持 seed |
| H3 视频 | **VERIFIED** —— 用订阅 Key 真实创建 `MiniMax-H3` 768P 4 秒任务并成功 |
| H3 参考 / 关键帧模式 | **DOCUMENTED_BUT_NOT_TESTED** —— 同一凭证可达，未实测 |
| 积分包余额 | 实测 `0.00`，每次生成前重新检查 |
| 余额读取依赖 | `UNDOCUMENTED_FIRST_PARTY_IMPLEMENTATION_DEPENDENCY`，fail closed |
| H3 时长 | 整数枚举 4-15（H3）、5-15（H3 Max）；测试最短 4 秒 / 5 秒 |
| 证据 | `research/providers/minimax-mplan-explore-capability.md`、`research/providers/minimax-voice-clone-entitlement.md` |

## 已知阻碍

1. 语音质量 — edge-tts 机械感重，非生产级。MiniMax 语音集成（M2）的主要动机。
2. Web 工作台 — 6 项 doctor 失败。不阻塞视频流水线。
3. Gateway healthz — 上游硬编码端口 18789；easel profile 使用 37289。不阻塞视频流水线。
4. 人工审查 — easel-review 项目无 ```human-review.json``` 凭证。
5. ~~Main 分支未保护~~ — **已解决**（G0.6）：main 现已通过 GitHub 分支保护机制保护。

## M3 图片生成（Issue #20）—— 已验证 2026-10-04

分支 `feat/20-minimax-mplan-image`。已执行一次真实 provider 生成。

| 属性 | 值 |
|---|---|
| 传输 | 官方 CLI `mmx 1.0.27`，`mmx image generate` |
| 模型 | `image-01` |
| 请求 | 768x1360，seed 42 |
| **请求扩展名** | `.png` |
| **实际检测容器** | **`JPEG`** |
| **规范扩展名** | `.jpg`（保留原始字节，未转码） |
| 实际尺寸 | 768x1360（已用 `ffprobe` 独立确认：`mjpeg`） |
| 宽高比 | 0.564706，9:16 = 0.5625，在 0.02 容差内 |
| 输出 SHA-256 | `fb0ee9489df856bc2cd554ab98d34fd73e0737ca733cdd0af6022342512f8e21` |
| 技术 QC | 通过 — 亮度标准差 29.97（下限 6）、极差 146（下限 24）、可解码 |
| `text_contamination_suspected` | `false`（边缘密度 0.0668，阈值 0.18） |
| 计费预检 | `SAFE_INCLUDED_PLAN`，凭据类别 `SUBSCRIPTION` |
| 生成前配额 | 5 小时 99%，周度 58% |
| 生成后配额 | 5 小时 99%，周度 58% |
| 观测差值 | 两个窗口均为 **0 个百分点** |
| `production_ready` | `false` |
| `human_review` | `PENDING_FOUNDER_REVIEW` |

### 容器缺陷第二次复现

provider 从 `.png` 请求返回了 **JPEG 字节**，内独重现了 M2.0 测到的现象。
若流程相信扩展名，一个 JPEG 会被存为 `.png`，并交给每个按后缀选择解码器的工具。
最终规范文件为 `.jpg`，凭据分别记录了请求与现实。

### 配额只报告差值，不报告价格

套餐仅暴露百分比。一张图片未造成任何窗口的变化，故观测差值为 0 个百分点。
这并不等于“生成一张图不花钱”，也未据此推导单张成本：MiniMax 在此处未暴露精确单位。

### 证据边界

生成资产已登记为 `GENERATED_IMAGE` / `VISUAL_SUPPORT`，`generated=true`、`evidence_capable=false`。
尝试任何事实引用角色都会在代码中抛出 `GeneratedAssetEvidenceError`。

### 人工评审

`.verify-tmp/m3/human-review.json` 已生成评审字段，但 **所有评分均为 null**。
技术 QC 通过不等于可作为发布。
