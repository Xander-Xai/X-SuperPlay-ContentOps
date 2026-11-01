---
translation_of: README.md
language: zh-CN
translation_status: synced
---

# X-SuperPlay-ContentOps

> 证据优先、跨平台的内容运营运行时，为 Xander-Xai 服务。

[English](README.md) | [简体中文](README.zh-CN.md)

## 是什么

一个统一的运行时，将真实的业务工作（GitHub 仓库、实验、研究）转化为可追溯的视频；
公众号文章、小红书图文和 X 帖子是后续轨道，各自走自己的生产门禁。

本分支同时承载文档与代码的对齐需求：
[docs/CONVERGENCE-REQUIREMENTS-2026-11-01.md](docs/CONVERGENCE-REQUIREMENTS-2026-11-01.md)。

## 为什么

此前使用 5 个独立平台仓库，从未产出稳定结果。ContentOps 将视频生产整合到一个运行时中，
并保留诚实、不可绕过的人工审核与质量门禁。

## 当前状态

下表区分**`main` 上已存在**与**仅存在于未合并分支**。一条轨道不会因为草稿分支写了它就算完成。

| 项目 | 所在层 | 状态 |
|---|---|---|
| Easel 运行时 | `main` | 固定 v0.2.1（commit `3fe2d99`，982 blobs 验证通过）。上游稳定版为 v0.3.0 —— 未采用 |
| 视频流水线（`run_v1.py`） | `main` | 已实现（`easel` + 诊断用 `fallback`）；`production_ready: false` |
| M5 证据优先链（`m5_production.py`） | `main` | 已在 `projects/m5-media-use` 上完成集成验证；`production_ready: false`、`PENDING_FOUNDER_REVIEW` |
| media-use 适配器（HyperFrames） | `main` | 已实现；仅本地、零联网/零付费。需要主机运行时锁 —— 默认判定为 `BLOCKED / MISSING_RUNTIME` |
| MiniMax 媒体 | `main` | 语音、图片、H3 视频已实现；已验证子集见 CURRENT-STATE；`PENDING_FOUNDER_REVIEW` |
| Skill 路由 / 执行授权 | `main` | 已实现；仅 `media-use` 是已声明能力；路由器从不授予执行权 |
| 内容路由、账号 DNA、工作流门禁 | **部分** | S1（#93，阶段门禁）与 S2（#95，素材候选契约）已在 `main`；S3–S4 在 Issue #94 中开放 |
| 公众号 | **未合并 / 本地 vendor** | vendored 十阶段工作流；溯源/权利审查在 Issue #56 中开放 |
| 小红书图文 | **未合并** | `feat/xhs-fa-migration`；仅人工上传 |
| X | **部分** | 发帖门禁与 growth→编辑门禁已在 `main`（PR #87、#88）；平台轨道的其余部分在 Issue #47 中跟踪 |
| 自动发布 | — | **不在范围内** |
| 测试 | `main` | `tests/test_*.py` 下每个套件都接入 CI；此处不声明数量；见 [docs/TEST-PLAN.md](docs/TEST-PLAN.md)；统一门禁 `python scripts/dev_check.py` |
| 生产就绪 | — | **否** —— 没有任何轨道达到 `PRODUCTION_ACCEPTED` |

### 分支现实

`main` 现已承载集成栈：media-use 适配器、权利门禁、Skill 路由与 Skill 执行授权
已作为 PR #89 合入，随后是 PR #87 与 PR #88。原集成分支
`fix/57-m5-media-fixtures` 已合并，远端分支已删除。

仍**不在** `main` 上的内容见上表。曾经跟踪它们的草稿 PR 已按 Issue #94 的切片流程
以「被取代」关闭：内容路由（#49）、X 平台轨道（#50）、公众号溯源修复（#58）。
receipt 基线修复（#62）与 media-use 合并前 ADR（#90）已合并。
截至 2026-11-01，没有开放 PR。

文档描述的是 `main`。未合并的层明确标注为未合并，而不是当作已工作的功能来
描述；详见
[docs/CONVERGENCE-REQUIREMENTS-2026-11-01.md](docs/CONVERGENCE-REQUIREMENTS-2026-11-01.md)。

## 快速开始

### Windows PowerShell

```powershell
python scripts\doctor.py
python scripts\dev_check.py
python scripts\new_project.py --slug my-video --title "My Video"
python scripts\run_v1.py   projects\my-video
python scripts\m5_production.py projects\m5-media-use
python scripts\qc_video.py projects\my-video
```

### WSL2 Ubuntu / Linux

```bash
python3 scripts/doctor.py
python3 scripts/dev_check.py
python3 scripts/new_project.py --slug my-video --title "My Video"
python3 scripts/run_v1.py   projects/my-video
python3 scripts/m5_production.py projects/m5-media-use
python3 scripts/qc_video.py projects/my-video
```

## 架构概要

本分支实际运行的链：

```text
project.yaml source_refs
  -> SourceArtifact（权限感知）
  -> ClaimLedger（引文校验的声明）
  -> 脚本 + 分镜
  -> MediaManifest（资产清单 + 时间线）
  -> 旁白 / 字幕
  -> 固定版本 Easel 合成（assemble_easel 适配器）
  -> qc_video
  -> 人工审核门禁
```

两个入口共享同一引擎：`run_v1.py`（分镜驱动、edge-tts）与 `m5_production.py`
（证据优先、本地旁白）。两者都不发布，也都不会报告生产就绪。

账号感知的内容路由（`HOTSPOT_DISCOVERY` / `USER_TOPIC` → 账号 DNA → Brief）
**不在本分支**。它是 [docs/CONVERGENCE-REQUIREMENTS-2026-11-01.md](docs/CONVERGENCE-REQUIREMENTS-2026-11-01.md)
与 PR #49 的主题。

系统边界详见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) 与
[docs/CURRENT-STATE.md](docs/CURRENT-STATE.md)。

## 规范文档

| 文档 | 用途 |
|---|---|
| [docs/INDEX.md](docs/INDEX.md) | 导航中心 |
| [docs/CURRENT-STATE.md](docs/CURRENT-STATE.md) | 当前运行状态 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 系统边界 |
| [docs/PRD.md](docs/PRD.md) | 产品需求 |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | 真实可执行命令 |
| [docs/DEVELOPMENT-PLAN.md](docs/DEVELOPMENT-PLAN.md) | 里程碑与状态 |
| [docs/QUALITY-STANDARD.md](docs/QUALITY-STANDARD.md) | 质量门控 |
| [docs/TEST-PLAN.md](docs/TEST-PLAN.md) | 测试清单与 CI 接线 |
| [docs/CONVERGENCE-REQUIREMENTS-2026-11-01.md](docs/CONVERGENCE-REQUIREMENTS-2026-11-01.md) | 当前收敛计划 |
| [docs/UPSTREAM-EASEL.md](docs/UPSTREAM-EASEL.md) | Easel 固定版本策略 |
| [AGENTS.md](AGENTS.md) | AI Agent 执行纪律 |

## Easel 固定版本

| 属性 | 值 |
|---|---|
| 仓库 | https://github.com/ZJU-REAL/Easel |
| Tag | v0.2.1 |
| Commit | `3fe2d9904c1619281ef57f81d9ee0b7854998399` |
| 本地路径 | `.runtime/easel/` |
| 锁文件 | `runtime/easel.lock.json` |
| 上游稳定版 | v0.3.0（未采用；Skill 路径已迁至 `skills/builtin/`） |
| 升级 | 需要 Founder 批准 + 回归套件 |

完整策略见 [docs/UPSTREAM-EASEL.md](docs/UPSTREAM-EASEL.md)。

## 治理

- **禁止直接推送到 main** —— 所有变更通过 PR
- `main` 已**保护**（2026-10-31 启用）：必需检查 `Tests (ubuntu-latest)`、
  `Tests (windows-latest)`、`Repo policy checks`；必须 PR；禁止 force push；禁止删除；
  线性历史
- 单人所有者无法自审，因此必需批准数为 0；有第二位评审者时提高到 1
- 见 [GitHub Issues](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues) 跟踪里程碑

## 扩展策略

```text
ADAPTER > EXTENSION > CUSTOM SKILL > UPSTREAM PATCH > FORK
```

Fork 是最后手段。当前状态：无 fork，无上游修改。

## 非目标（当前阶段）

- 自动发布到任何平台
- 评论抓取 / ROI agent
- 自主数字人产品 / AI 短剧
- 指标抓取 / 爆款学习
- n8n / OpenClaw 全量编排

## 核心原则

```text
采用优先于构建。发布优先于自动化。
测量优先于优化。删除优先于扩展。
证据优先于声明。合约优先于集成。
额度优先于生成。质量优先于规模。
运行时现实优先于文档。
```

## 作品集职责边界（2026-10-30）

本公开说明只界定技术职责。任何私有作品集登记或商业运营都不在本仓库内；本仓库不声称
其他私有系统可访问、已商业化或正在运营。

- **拥有：** 有来源依据的视频、公众号文章、小红书图文与 X 编辑产物的生产与人工审核。
- **产出：** 媒体资产、文章、上传说明包、QC 结果和可复现的生成工作流；实际平台发布由其授权运营者记录。
- **不拥有：** 不是社交平台账号、付费客户 CRM、收入事实来源或自动发布器。
- **公开接口与交接：** 技术公开示例可能来自
  [Beauty RAG](https://github.com/Xander-Xai/Beauty-Industry-RAG-QA-System) 与
  [Customer-Service AI Agent](https://github.com/Xander-Xai/Customer-Service-AI-Agent)；
  许可证与公开许可另行核查。
- 技术实现、测试和发布证据留在本仓库。上游作品集文档不能把草稿、本地测试或 CI
  提升为真实生产使用、付费或用户增长。
