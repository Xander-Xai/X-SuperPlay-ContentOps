---
translation_of: README.md
language: zh-CN
translation_status: synced
---

# X-SuperPlay-ContentOps

> 证据优先、跨平台的内容运营运行时，为 Xander-Xai 服务。

[English](README.md) | [简体中文](README.zh-CN.md)

## 是什么

一个统一的运行时，将真实的业务工作（GitHub 仓库、实验、研究）转化为可追溯的视频、
公众号文章、小红书图文和 X 帖子；每种内容走自己的生产门禁。

## 为什么

此前使用 5 个独立平台仓库，从未产出稳定结果。ContentOps 将生产整合到一个运行时中，
并保留诚实、不可绕过的人工审核与质量门禁。

## 当前状态

| 项目 | 状态 |
|---|---|
| Easel 运行时 | 固定 v0.2.1（commit `3fe2d99`，982 blobs 验证通过） |
| 视频流水线 | 已实现生产者与 QC；`production_ready: false`；等待人工审核 |
| 公众号 | vendored 十阶段工作流；停在公众号草稿；许可审计未完成（#56） |
| 小红书图文 | `feat/xhs-fa-migration` 上的八步工作流；未合并；仅人工上传 |
| X | PR #50；仅人工发布的编辑包；未合并 |
| MiniMax 媒体 | 语音、图片与 H3 视频已实现并做过真实调用；`PENDING_FOUNDER_REVIEW` |
| 自动发布 | **不在范围内** |
| 测试 | 见 [docs/CURRENT-STATE.md](docs/CURRENT-STATE.md) 与 `python scripts/run_tests.py` |
| 生产就绪 | **否** —— 没有任何平台达到 `PRODUCTION_ACCEPTED` |

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
路线（HOTSPOT_DISCOVERY / USER_TOPIC）
  -> 账号 DNA -> 内容格式 -> Brief -> 平台门禁 -> 人工审核
     ├ 视频        -> 分镜规划 -> 采集 -> 合成 -> QC -> final.mp4
     ├ 公众号        -> vendored 十阶段 -> 公众号草稿
     ├ 小红书图文    -> 八步门禁 -> 人工上传说明包
     └ X            -> 编辑包 -> 人工发布
```

没有任何路线会自动发布。详见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) 与
[docs/CURRENT-STATE.md](docs/CURRENT-STATE.md)。

## 规范文档

| 文档 | 用途 |
|---|---|
| [docs/INDEX.md](docs/INDEX.md) | 导航中心 |
| [docs/CURRENT-STATE.md](docs/CURRENT-STATE.md) | 当前运行状态 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 系统边界 |
| [docs/PRD.md](docs/PRD.md) | 产品需求 |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | 真实可执行命令 |
| [docs/DEVELOPMENT-PLAN.md](docs/DEVELOPMENT-PLAN.md) | M0-M6 里程碑 |
| [docs/QUALITY-STANDARD.md](docs/QUALITY-STANDARD.md) | 质量门控 |
| [docs/UPSTREAM-EASEL.md](docs/UPSTREAM-EASEL.md) | Easel 固定版本策略 |
| [AGENTS.md](AGENTS.md) | AI Agent 执行纪律 |

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
