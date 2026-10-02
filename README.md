# X-SuperPlay-ContentOps

> **V1 evidence-first video ContentOps runtime for X-SuperPlay accounts.**

## 这是什么

`X-SuperPlay-ContentOps` 是 X-SuperPlay 自媒体内容运营的 V1 Runtime。目标只有一个：

> **稳定生成可发布的 final.mp4。**

V1 不追求大一统架构、不做自动发布、不接数据库、不下搭歌 — 只打通：

```
Source  → Script → Storyboard → Voice → Subtitle → Compose → QC → final.mp4
```

## 当前 V1 状态

| 项 | 状态 |
|---|---|
| Easel runtime | 锁定 v0.2.1 / commit `3fe2d9904c1619281ef57f81d9ee0b7854998399` |
| 旧 5 个自媒体仓库 | 停止开发，本仓库不依赖、不迁移它们 |
| 自动发布 | **不做**（V1 阶段） |
| AI 文生视频 | **默认关闭**（V1 不依赖） |
| 数字人 / 短剧 | **不做** |

## Quick Start

### Windows PowerShell

```powershell
python scripts\bootstrap.ps1
python scripts\doctor.py
python scripts\new_project.py --slug easel-review --title "Easel 实测"
python scripts\run_v1.py   projects\easel-review
python scripts\qc_video.py  projects\easel-review
```

### WSL2 Ubuntu / Linux

```bash
bash scripts/bootstrap.sh
python3 scripts/doctor.py
python3 scripts/new_project.py --slug easel-review --title "Easel 实测"
python3 scripts/run_v1.py   projects/easel-review
python3 scripts/qc_video.py  projects/easel-review
```

## 创建项目

```bash
python scripts/new_project.py --slug <kebab-case> --title "<title>"
```

生成标准目录与 `project.yaml`。**拒绝覆盖**已有项目。

## 跑 V1

```bash
python scripts/run_v1.py projects/<slug>
```

V1 渲染：

1. 真实证据 PNG/JPG（按 `sources/screenshots|digrams|recordings` 顺序）
2. Windows SAPI 配音（fallback 时 QC 标注 `voice_quality: fallback`）
3. 6 段分镜 (HOOK / 问题 / 证据 / 发现 / 限制 / 结论)
4. ffmpeg 合成 → `final/final.mp4`

## QC

```bash
python scripts/qc_video.py projects/<slug>
```

输出 `receipts/qc-report.{json,md}`。状态：`PASS` / `WARN` / `FAIL`。

## Easel

| 项 | 值 |
|---|---|
| Repo | https://github.com/ZJU-REAL/Easel |
| Tag | v0.2.1 |
| Commit | `3fe2d9904c1619281ef57f81d9ee0b7854998399` |
| 本地路径 | `.runtime/easel/` |
| Lock | `runtime/easel.lock.json` |
| 升级 | 禁止自动升级，需 Founder 明确同意 |

## 当前明确不做什么

- ❌ 自动发布抖音 / 小红书 / B站 / 视频号
- ❌ 评论抓取 / 数据归因 / ROI Agent
- ❌ n8n / OpenClaw 总调度中心
- ❌ 数字人 / AI 短剧 / 复杂 AI 视频
- ❌ Fork / 改造 Easel
- ❌ 迁移 / 修复 5 个旧仓库

## 核心资产

- `AGENTS.md` — AI 代理规则（North Star + 能力证明原则 + Pre-Code Gate + 项目四态）
- `00-Governance/PRINCIPLES.md` — X-SuperPlay 能力证明原则
- `00-Governance/PRE-CODE-GATE.md` — coding 前 7 问 Gate
- `00-Governance/PROJECT-STATES.md` — 项目四态制度（RUN/HOLD/LIBRARY/KILL）
- `00-Governance/MEASUREMENT.md` — 新的 5 大衡量标准
- `00-Governance/douyin-1024-STRATEGY.md` — douyin-1024 战略定位
- `docs/V1-RUNBOOK.md` — 操作手册
- `docs/EASEL-DEPLOYMENT-DECISION.md` — Easel v0.2.1 部署决策（克隆 + Web 工作台）
- `docs/V1-EXECUTION-METHODOLOGY.md` — 先跑通原版再改造的执行方法论
- `docs/OPEN-SOURCE-VERSION-HEURISTICS.md` — 开源项目版本选择决策树
- `templates/short-video-v1.md` — 视频结构模板
- `templates/project.yaml` — 项目元数据模板
- `templates/qc-checklist.md` — QC 清单

## 能力证明原则（最高优先级）

> **X-SuperPlay 不以"自己开发了多少系统"为能力证明，而以"借助现有能力，多快完成真实业务闭环"为能力证明。**

四条铁律：

```
Adopt before Build.       Ship before Automate.
Measure before Optimize.  Delete before Expand.
```

详见 [00-Governance/PRINCIPLES.md](00-Governance/PRINCIPLES.md)。