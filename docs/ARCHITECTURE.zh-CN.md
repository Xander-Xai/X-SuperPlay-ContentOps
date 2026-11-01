---
translation_of: docs/ARCHITECTURE.md
language: zh-CN
translation_status: synced
---

# 架构

[English](ARCHITECTURE.md) | [简体中文](ARCHITECTURE.zh-CN.md)

> 系统是什么。边界在哪里。组件如何调用。
> 描述 `main`（2026-11-01，PR #89 合并后），不是未来分支。

## 系统边界

```text
X-SuperPlay-OPC-Blueprint
= 业务事实来源（独立仓库）
    │
    │ Source / Proof / Permission / PD State
    ▼
X-SuperPlay-ContentOps  ← 本仓库
= 可执行内容生产运行时
    │
    ├── SourceArtifact 摄取          （已实现，M5）
    ├── 证据 + 声明绑定              （已实现，M5）
    ├── 脚本 → 分镜                  （已实现，M5 / V1）
    ├── 资产规划 + media-use         （已实现，M4.5 / M5）
    ├── 媒体生成（MiniMax）          （已实现，部分能力已验证）
    ├── 语音合成                     （edge-tts、Windows SAPI）
    ├── 视频合成（Easel 适配器）      （已实现）
    ├── 自动 QC                      （已实现）
    ├── 人工审核门禁                 （已实现，永不自动批准）
    └── 凭证（完整来源链）            （已实现）
    │
    ▼
Easel v0.2.1（固定上游）
= 内容工作流 / 技能引擎
    ├── tts.py（edge-tts 封装）
    ├── auto-short-video/scripts/assemble.py
    └── 114 个 Skill
    │
    ▼
FFmpeg / 确定性工具
= 渲染 / 媒体工具
```

## 分支层

仓库正处于收敛过程中。一个组件只有在 ```main``` 上才算“系统的一部分”。

| 层 | 所在位置 | ```main``` 状态 |
|---|---|---|
| M5 证据链、媒体、QC、Skill 路由/授权 | ```main```（PR #89） | 已实现 |
| X 发帖门禁、growth→编辑门禁 | ```main```（PR #87、#88） | 已实现 |
| 账号感知内容路由、工作流门禁、Brief/脚本/设计阶段 | `feat/content-router`（PR #49） | **未合并** |
| 小红书八步工作流 | `feat/xhs-fa-migration` | **未合并** |
| X 平台轨道（迁移记录、提示词引用、表格门禁） | `feat/47-x-platform-track`（PR #50） | **未合并** |
| 公众号十阶段 vendored 工作流 | 本地 `vendor/` + `fix/56-gzh-provenance`（PR #58） | **未合并 / 权利受阻** |

合并顺序见
[CONVERGENCE-REQUIREMENTS-2026-11-01.md](CONVERGENCE-REQUIREMENTS-2026-11-01.md)。
引用未合并层的 Skill 在 [SKILL-REGISTRY.md](SKILL-REGISTRY.md) 中如实声明，
不会在 ```main``` 上被描述为可运行。

## 组件图

```text
scripts/
├── run_v1.py             ← V1 编排（easel + fallback 引擎）
├── m5_production.py      ← 证据优先链（来源 → … → 评审）
├── assemble_easel.py     ← Easel 编排适配器（Windows 字幕变通）
├── qc_video.py           ← 自动技术与证据 QC
├── resolve_easel.py      ← 唯一运行时解析器
├── verify_easel_runtime.py ← 内容哈希校验
├── doctor.py             ← 环境检查
├── process_utils.py      ← 隐藏窗口子进程层
├── media_use_adapter.py  ← media-use 运维 CLI
├── media_use_runtime.py  ← 已批准基线 / 安装 / 锁定 / 校验
├── skill_route.py        ← 发现 + 权利感知解析（不执行）
├── skill_execute.py      ← 通过可信授权执行
├── dev_check.py          ← 统一本地门禁
└── test_basic.py         ← 脚本级冒烟套件

src/contentops/
├── evidence/             ← SourceArtifact、ClaimLedger
├── media/                ← 合约、计费、供应商、清单、校验、
│                           变换、QC 规范化、权利门禁、media-use
├── skills/               ← 授权、执行门禁、授权来源
└── golden/               ← Golden 身份、证据锁、评审、A/B 变体

runtime/
├── easel.lock.json               ← 规范 Easel 固定版本
├── easel-runtime.json            ← 来源记录
├── media-use-runtime-baseline.json
├── media-use-package-lock.json
└── skill-registry.json           ← 已声明能力（仅 media-use）

projects/<slug>/
├── project.yaml          ← 元数据 + source_refs + media_use 请求
├── sources/              ← 真实证据
├── script/               ← 主脚本、分镜、声明
├── assets/               ← 语音、字幕、导入/生成资产
├── work/                 ← 中间渲染（gitignored）
├── final/                ← 输出 MP4（gitignored）
└── receipts/             ← 构建、QC、运行时、人工审核凭证
```

`src/contentops/{workflow,routing,platforms,quality,script,hotspots,optimization}`
在本分支只是空的 `__pycache__` 残留目录。其代码在 `feat/content-router` 上；
不要把这些目录当作已实现模块。

## 流水线

### V1（分镜驱动）

```text
projects/<slug>/script/{master.md,storyboard.json}
  → 解析固定版本 Easel
  → 语音（Easel tts.py 的 edge-tts）
  → Easel assemble.py
  → 字幕烧录（assemble_easel 适配器）
  → final/easel.mp4
  → qc_video
```

### M5（证据优先）

```text
project.yaml source_refs
  → SourceArtifact（权限门禁）
  → ClaimLedger（引文校验）
  → media_use 阶段（可选，仅本地）
  → 脚本 → 旁白 → 字幕 → 分镜
  → MediaManifest（资产清单 + 时间线）
  → 固定版本 Easel 合成
  → qc_video → 人工审核
```

两条路径都以 `PENDING_FOUNDER_REVIEW`、`production_ready: false` 结束。

## 媒体收敛

唯一的 `MediaManifest` 是资产清单的唯一来源。`assets` 是库存（可同时保留源文件与其
派生变换）；`timeline` 为每个 placement 选择恰好一个活动资产。合成读取时间线，
绝不遍历库存。

所有路径都是逻辑路径（`project://`、`repo://`），在使用点解析。已提交的清单与凭证
拒绝绝对主机路径。QC 凭证会规范化为 `contentops.qc-canonical/v1`，显式携带
`currency` 与 `graded_target`。

## media-use 集成（Issue #57）

`media-use` 是上游 HyperFrames 仓库（Apache-2.0）中的技能。它以**固定版本的外部
依赖**方式使用，不复制进本仓库（ADR-008）。

```text
src/contentops/media/media_use_adapter.py  ← 唯一知道该技能存在的模块
scripts/media_use_adapter.py               ← 运维 CLI
   status | doctor | candidates | resolve | adopt | ingest | import | verify | demo
```

两项契约扩展使映射保持诚实：

- `AssetKind.LICENSED_EXTERNAL` —— 已授权的第三方素材。它既不是实拍捕获，也不是
  模型生成，因此同时排除在 `EVIDENCE_CAPABLE` 与 `GENERATED` 之外。
- `MediaModality.AUDIO` —— 背景音乐与音效。它不是旁白，因此不带 `asset_kind`，
  也永远不能作为证据。

导入结果写入 `contentops.media-import/v1` 回执，并进入唯一的 `MediaManifest`。
技能的 `.media/manifest.jsonl` 只用于按记录 ID 查询，绝不构成第二套资产清单。

默认全部关闭：无网络、无付费供应商、无跨项目复用、不强制指定供应商。可信主机锁
必须引用已批准的基线；干净检出默认是 `BLOCKED / MISSING_RUNTIME`。

## Skill 路由与执行

三个问题保持分离：

| 问题 | 层次 | 由谁回答 |
|---|---|---|
| 本机存在什么？ | 发现 | `skill_route.py --list/--sources/--match` |
| 可以交给适配器吗？ | 解析 | `skill_route.py --resolve` + `runtime/skill-registry.json` |
| 真的可以执行吗？ | 执行 | 适配器、运行时锁校验器、授权门禁 |

路由器从不授予执行权。每条记录都带 `execution_authorized: false`。声明必须指向
本分支上存在的代码；代码未合并的 Skill 不会被声明。

## 扩展策略

```text
ADAPTER     → 封装外部 API，不修改上游
EXTENSION   → 在 X-SuperPlay 空间新增模块
CUSTOM SKILL → 在 extensions/ 或 skills/ 新增 Easel skill
UPSTREAM PATCH → 修改 Easel 源码（需补丁文件 + 测试）
FORK        → 最后手段
```

当前：无 fork。无上游修改。`assemble_easel.py` 是 ADAPTER（编排变通，非源码编辑）。

## ContentOps 不拥有

- 业务判断（在 OPC Blueprint）
- 商业事实（在 OPC）
- 平台发布（保持人工，人工门控）
- 指标抓取（尚未实现）
- 自动发布（明确不在范围内）
