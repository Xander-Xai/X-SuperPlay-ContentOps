---
translation_of: README.md
language: zh-CN
translation_status: synced
---

# X-SuperPlay-ContentOps

> 证据优先的视频内容运营运行时，为 Xander-Xai 多仓库内容生产服务。

[English](README.md) | [简体中文](README.zh-CN.md)

## 是什么

一个统一的运行时，将真实的业务工作（GitHub 仓库、实验、研究）转化为高质量、可追溯、可发布的视频内容。

## 为什么

此前使用 5 个独立平台仓库，从未产出稳定结果。ContentOps 将生产整合到一个运行时中，配以诚实质量门控。

## 当前状态

| 项目 | 状态 |
|---|---|
| Easel 运行时 | 固定 v0.2.1（commit 3fe2d99，982 blobs 验证通过） |
| 生产引擎 | Easel ssemble.py（上游，未修改） |
| 生产语音 | edge-tts via Easel 	ts.py（zh-CN-YunxiNeural） |
| 语音质量 | dge_tts_fallback — 等待 MiniMax 升级（M2） |
| 诊断引擎 | 仅 ffmpeg 回退路径（非生产） |
| MiniMax 集成 | 未实现（能力验证待定，Issue #4） |
| 自动发布 | 不在范围内 |
| 黄金样本 | 1 个（projects/easel-review/） |
| 测试 | 9 项通过 |
| 生产就绪 | **否** — READY_FOR_HUMAN_REVIEW |

## 快速开始

### Windows PowerShell

```powershell
python scripts\doctor.py
python scripts\new_project.py --slug my-video --title "My Video"
python scripts\run_v1.py   projects\my-video
python scripts\qc_video.py projects\my-video
```

### WSL2 Ubuntu / Linux

```bash
python3 scripts/doctor.py
python3 scripts/new_project.py --slug my-video --title "My Video"
python3 scripts/run_v1.py   projects/my-video
python3 scripts/qc_video.py projects/my-video
```

## 架构概要

```text
Source → Script → Storyboard → Voice → Compose → QC → Human Review → final.mp4
```

详见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 治理

- **禁止直接推送到 main** — 所有变更通过 PR
- main 已**保护**：必需状态检查 + PR + 禁止 force push + 禁止删除 + 线性历史
- 见 [GitHub Issues](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues) 跟踪里程碑

## 扩展策略

```text
ADAPTER > EXTENSION > CUSTOM SKILL > UPSTREAM PATCH > FORK
```

Fork 是最后手段。当前状态：无 fork，无上游修改。

## 核心原则

```text
采用优先于构建。发布优先于自动化。
测量优先于优化。删除优先于扩展。
证据优先于声明。合约优先于集成。
额度优先于生成。质量优先于规模。
运行时现实优先于文档。
```

## 规范文档

| 文档 | 用途 |
|---|---|
| [docs/INDEX.md](docs/INDEX.md) | 导航中心 |
| [docs/CURRENT-STATE.md](docs/CURRENT-STATE.md) | 当前运行状态 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 系统边界 |
| [docs/PRD.md](docs/PRD.md) | 产品需求 |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | 真实可执行命令 |
| [docs/DEVELOPMENT-PLAN.md](docs/DEVELOPMENT-PLAN.md) | M0–M6 里程碑 |
| [docs/QUALITY-STANDARD.md](docs/QUALITY-STANDARD.md) | 质量门控 |
| [docs/UPSTREAM-EASEL.md](docs/UPSTREAM-EASEL.md) | Easel 固定版本策略 |
| [AGENTS.md](AGENTS.md) | AI Agent 执行纪律 |