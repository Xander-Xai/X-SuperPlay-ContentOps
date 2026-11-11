# X-SuperPlay-ContentOps

> 证据优先、跨平台的内容运营运行时，为 Xander-Xai 服务。

简体中文 | [English](README.en.md)

> 最后验证：2026-11-12，`main` 的 `c1da6dd`。状态表描述 `main`，不描述草稿分支。

## 是什么

一个统一的运行时，将真实的业务工作（GitHub 仓库、实验、研究）转化为可追溯的视频、
公众号文章、图文包和 X 帖子；每条轨道走自己的生产门禁。它负责渲染、校验和打包，
**不负责发布**：交付包停在人工记录 URL 那一步。

用于把文档与代码对齐的收敛需求记录在
[docs/CONVERGENCE-REQUIREMENTS-2026-11-01.md](docs/CONVERGENCE-REQUIREMENTS-2026-11-01.md)
（2026-11-01 获批；其余步骤在 2026-11-04 至 2026-11-11 落地）。

## 为什么

此前使用 5 个独立平台仓库，从未产出稳定结果。ContentOps 将视频生产整合到一个运行时中，
并保留诚实、不可绕过的人工审核与质量门禁。

## 当前状态

下表描述 `c1da6dd` 上的 **`main`**（2026-11-12 复核）。一条轨道不会因为草稿分支写了它
就算完成；代码存在也不等于它发布过任何东西。

| 项目 | 所在层 | 状态 |
|---|---|---|
| Easel 运行时 | `main` | 固定 v0.2.1（commit `3fe2d99`，982 blobs 验证通过）。上游稳定版为 v0.3.0 —— 未采用 |
| 稳定生产入口（`make_content.py`、`production_gates.py`） | `main` | 已实现：六项显式决策、7 个失败即拒绝的 VIDEO 门禁与 5 个 GRAPHIC_TEXT 门禁。直接运行 `m5_production.py` / `produce_video.py` 仍是**诊断**路径，不过门禁 |
| 视频流水线（`run_v1.py`） | `main` | 已实现（`easel` + 诊断用 `fallback`）；`production_ready: false` |
| M5 证据优先链（`m5_production.py`） | `main` | 已实现，并在 `projects/m5-media-use` 上完成集成验证；可选 ASR 旁白回检门禁；`production_ready: false`、`PENDING_FOUNDER_REVIEW` |
| M5 特征基线 | `main` | `docs/m5-baseline/m5-characterization-2026-11-10.md` —— `5ff621c1` 上 10 套件 / 165 项测试，作为 #140 slice 1 的凭证（164 通过、1 项已知失败保留可见） |
| 卡片与文章渲染（`render_cards.py`、`render_article.py`） | `main` | 已实现：HTML 卡片转 PNG 并跑密度审计，文章 HTML 由固定版本 Easel Skill 校验并生成预览。各自写出防篡改凭证；PASS 不等于批准 |
| media-use 适配器（HyperFrames） | `main` | 已实现；仅本地、零联网/零付费。需要主机运行时锁 —— 默认判定为 `BLOCKED / MISSING_RUNTIME` |
| MiniMax 媒体 | `main` | 语音、图片、H3 视频已实现；已验证子集见 CURRENT-STATE；`PENDING_FOUNDER_REVIEW` |
| Skill 路由 / 执行授权 | `main` | 已实现；仅 `media-use` 是已声明能力；路由器从不授予执行权 |
| 内容路由、账号 DNA、工作流门禁 | `main` | 已通过 PR #114、#118 合入。注册 15 个热点源 —— 仅 1 个原生搜索（GitHub）、14 个纯列表 —— 两个账号 DNA 均已对全部源开放（#157）。热点和主动主题入口均可生成 Brief；审批与文案审核仍受门禁约束 |
| 视频交付（`video_deliver.py`） | `main` | 已实现：`plan` / `pack` / `status` 生成各平台交付包与缩略图，`dispatch` 需要运营授权。上传器 exit 0 只记为 `UPLOADER_EXIT_0`，永不算发布 —— 只有人真正看到的 URL 才被登记 |
| 图文交付（`platform_delivery.py`、`graphic_deliver.py`、`wechatsync_browser.py`） | `main` | 已实现：先离线打包，再经进程边界调用外部 CLI，且只创建草稿。没有 `PUBLISHED` 分支，代码永不写 URL |
| 公众号 | `main` 渲染 + 草稿路径 | 文章 HTML 可渲染并校验；`wechat_draft.py` 可停在真实平台草稿，`wechat_metrics.py` 可读取数据立方，两者都需运营授权且为 `DRAFT_ONLY`。注册表状态仍为 `PLANNED`；Issue #56 权利未解决 |
| 小红书图文 | `main` 规格 + 交付渠道 | 图文规格与交付渠道记录存在；注册表无图文行（按 2026-11-09 运营指令，整个平台归 VIDEO 线）。权利与迁移验收仍开放于 Issue #51 |
| X | `main` 人工编辑轨道 | 已有编辑门禁、人工发布包、URL 记录及离线指标分析；不调用发布 API，也不自动采集指标 |
| 自动发布 | — | **不在范围内** |
| 发布计数 | — | **0** —— 没有任何交付包持有真实平台 URL |
| 测试 | `main` | `tests/test_*.py` 下 98 个套件，每个都作为具名步骤接入 CI；完整本地门禁为 `python scripts/dev_check.py` |
| 生产就绪 | — | **否** —— 没有任何轨道达到 `PRODUCTION_ACCEPTED` |

### X 原创内容奖励——拟定增长实验

[X 项目入口](projects/x-growth-en/README.md) 已加入 [90 天证据驱动增长方案](projects/x-growth-en/original-content-rewards-90d.md) 和空白资格/周复盘模板。这些是**文档与人工数据记录**，不是自动采集、自动发布、收益资格或实际发表的证明。现有 X 内容与图片审核门禁仍是执行依据；原私有 `X-SuperPlay-X-Growth-OS` 仅作为待下线的历史迁移来源，不再作为独立执行权威。

### 分支现状

本文描述当前 `main` 上的能力，而非早期功能分支的状态。2026-11-12 复核结果：`main` 是唯一
长期分支；一个非运行时目录分支以 PR #158 开放；4 个 issue 开放（#7 EPIC、#51 与 #56 权利
门禁、#140 M5 阶段拆分）。X、XHS、GZH 适配器都在 `main` 上，但执行边界不同，见上表。
每条内容线都已有交付代码，但除 `x` 外没有任何平台状态高于 `PLANNED`，因为没有绑定公开账号，
也没有任何作品拿到真实平台 URL。需要说明的一处变化：小红书的运行时适配器已于 2026-11-09
随图文工作流移除（`src/contentops/xhs/` 目录已空），`main` 上只剩它的注册表记录与视频
交付渠道配置，不存在"小红书适配器"这层代码。带日期的证据见
[docs/CURRENT-STATE.md](docs/CURRENT-STATE.md)，未完成事项见
[docs/DEFERRED-WORK.md](docs/DEFERRED-WORK.md)。

### 海外渠道预候选（未启用）

独立的**非运行时**清单 `config/registry/channel-candidates.json` 已记录 **Threads、Instagram、Facebook** 三个预候选；它们**未进入**正式平台注册表，没有账号绑定、可运行生产/发布链或自动指标。WhatsApp、LINE 仅属于私域转化触点观察，不是内容发布目标。详见[候选范围与验收约束](docs/OVERSEAS-CHANNEL-CANDIDATES-20261111.md)。此项不改变 Strategy 的 14 平台正式口径，也不改变生产就绪状态。

## 项目架构

一句话：**来源 → 证据 → 决策 → 两条生产线 → 门禁 → 交付包 → 人**。每一层只做一件事，
跨层的捷径都要付代价（跳过证据层就是没有出处的视频；跳过门禁就是不可复现的成片；
跳过交付层就是靠人肉复制粘贴）。

### 分层

```text
真实来源                            Strategy
GitHub 仓库 / 实验 / 研究  →  业务方向 · Bundle 模板
                    │
                    ▼
┌─ 证据层 ─────────────────────────────────────────────────┐
│ SourceArtifact（权限感知）· ClaimLedger（引文校验）      │
│ Content Bundle（计划，不是发布）                         │
└──────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─ 决策层 ─────────────────────────────────────────────────┐
│ 内容路由：热点（15 源）/ 主动主题                        │
│ → 账号 DNA → Brief → 脚本 / 分镜 / 设计                  │
└──────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─ 生产层（两条线，渲染前分叉） ───────────────────────────┐
│ VIDEO   旁白 · 字幕 · 分镜 → Easel 合成 → QC             │
│ GRAPHIC 提纲 · 正文 → 卡片 PNG / 文章 HTML → 校验        │
└──────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─ 门禁层 ─────────────────────────────────────────────────┐
│ make_content.py：7 个 VIDEO / 5 个 GRAPHIC_TEXT 门禁     │
│ 文案审核（指纹绑定）· QC · ASR 回检（只检测）            │
└──────────────────────────────────────────────────────────┘
                    │
                    ▼
┌─ 交付层（只打包，绝不发布） ─────────────────────────────┐
│ video_deliver：各平台包 + 缩略图                         │
│ platform_delivery / graphic_deliver：草稿（进程边界）    │
└──────────────────────────────────────────────────────────┘
                    │
                    ▼
        人工审核 → 人工记录 URL（发布计数仍为 0）
```

### 入口：该跑哪一个

| 目的 | 命令 | 会发布吗 |
|---|---|---|
| 检查环境 | `python scripts/doctor.py` | — |
| 完整本地门禁 | `python scripts/dev_check.py` | — |
| 生产（受门禁，推荐） | `python scripts/make_content.py run --project <项目> --mode STRICT` | 否 |
| 诊断跑 M5 | `python scripts/m5_production.py <项目>` | 否 |
| 卡片 / 文章渲染 | `render_cards.py` / `render_article.py` | 否 |
| 视频交付包 | `video_deliver.py plan` / `pack` / `status` | 否 |
| 图文交付 | `platform_delivery.py pack`、`graphic_deliver.py --all` | 只建草稿 |
| 公众号草稿 | `wechat_draft.py`（需运营授权） | 只建草稿 |
| 登记真实 URL | `video_deliver.py record --url <真实URL>` | 登记，不是发布 |
| 平台状态 | `python scripts/platforms.py check` / `list` | 否 |

### 模块地图

| 位置 | 职责 |
|---|---|
| `src/contentops/evidence/` | `SourceArtifact`、`ClaimLedger`：一切断言的出处 |
| `src/contentops/content_kernel/` | Bundle 校验 + 两种形式的 handoff（VIDEO / GRAPHIC_TEXT） |
| `src/contentops/routing/` | 路线（热点 / 主动主题）、账号 DNA、Brief、脚本与设计阶段 |
| `src/contentops/hotspots/` | 15 个源的能力注册表、抓取、去重、质量与排序 |
| `src/contentops/script/` | 文案草稿的生成与拒绝路径 |
| `src/contentops/media/` | 媒体合约、计费门、provider、manifest、QC 归一化、ASR 回检、场景分析（只读） |
| `src/contentops/workflow/` | 有序阶段契约与人工门禁 |
| `src/contentops/easel/` | 固定版本 Easel 的宿主门禁与步骤驱动（不改上游） |
| `src/contentops/platforms/` | 唯一平台注册表 + 交付渠道规格（视频/图文） |
| `src/contentops/publish/` | X 人工发布门禁（没有 `PUBLISHED` 分支） |
| `src/contentops/graphic/` | 人工图文包、卡片、公众号文章（渲染后仍不是批准） |
| `src/contentops/gzh/` | 公众号运行时适配器（`VERIFY_ONLY`） |
| `src/contentops/skills/` | Skill 解析、执行门禁与授权来源 |
| `src/contentops/golden/` | Golden 身份、证据锁、复核与 A/B 变体 |
| `scripts/` | 全部 CLI 入口（上表）+ 门禁脚本（`check_*`、`dev_check`） |

### 三条硬边界

1. **生产不发布。** 交付层最多产出交付包与平台草稿；`PUBLISHED` 不存在于代码里，
   URL 只能由人登记。上传器 exit 0 记作 `UPLOADER_EXIT_0`，不算发布。
2. **证据先于声明。** LLM 起草、证据校验；QC PASS 不是批准，`production_ready`
   恒为 `false`，直到有人工审核回执。
3. **文档跟着代码走。** 每份跟踪文档带验证日期，代码在日期之后有提交即判定过期
   （[docs/DOC-SYNC.md](docs/DOC-SYNC.md)）。过期的状态表不是小问题，它是错的。

## 快速开始

### Windows PowerShell

```powershell
python scripts\doctor.py
python scripts\dev_check.py
python scripts\new_project.py --slug my-video --title "My Video"
python scripts\make_content.py check --project projects\my-video
python scripts\run_v1.py   projects\my-video
python scripts\m5_production.py projects\m5-media-use
python scripts\qc_video.py projects\my-video
```

### WSL2 Ubuntu / Linux

```bash
python3 scripts/doctor.py
python3 scripts/dev_check.py
python3 scripts/new_project.py --slug my-video --title "My Video"
python3 scripts/make_content.py check --project projects/my-video
python3 scripts/run_v1.py   projects/my-video
python3 scripts/m5_production.py projects/m5-media-use
python3 scripts/qc_video.py projects/my-video
```

`make_content.py` 是生产入口：任一门禁不过就拒绝调用生产者；直接运行
`m5_production.py` / `produce_video.py` 属于诊断路径。交付命令
（`video_deliver.py`、`platform_delivery.py`、`graphic_deliver.py`）见
[docs/RUNBOOK.md](docs/RUNBOOK.md)；没有运营授权时它们都不会发布。

## 运行链路细节

### 两个视频入口，一个受门禁的生产入口

`run_v1.py`（分镜驱动、edge-tts）与 `m5_production.py`（证据优先、本地旁白）共享同一套
合成与 QC 引擎；两者之前是 `make_content.py`——它先跑门禁，任一门禁不过就拒绝调用生产者。
直接调用这两个脚本属于诊断路径，不受门禁保护，也不报告生产就绪。三者都不发布。

### 路由与文案审核

账号感知的内容路由（热点 / 主动主题 → 账号 DNA → Brief）在 `main` 上（PR #114）；
`router_e2e.py` 是验收工具，不是生产入口。由 Brief 驱动的项目必须先过文案审核
（指纹绑定当前文案），否则渲染会被拒绝。阶段归属与当前状态见
[docs/CONTENT-LIFECYCLE-STAGES.md](docs/CONTENT-LIFECYCLE-STAGES.md)。

### 边界与证据

系统边界、组件调用关系与规则见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)；当前实际
运行什么、哪些是历史记录见 [docs/CURRENT-STATE.md](docs/CURRENT-STATE.md)；平台状态由
[docs/PLATFORM-INTEGRATION-STATUS.md](docs/PLATFORM-INTEGRATION-STATUS.md) 从注册表导出。

## 规范文档

| 文档 | 用途 |
|---|---|
| [docs/INDEX.md](docs/INDEX.md) | 导航中心 |
| [docs/CURRENT-STATE.md](docs/CURRENT-STATE.md) | 当前运行状态 |
| [docs/DOC-SYNC.md](docs/DOC-SYNC.md) | 文档保鲜机制：触发条件、步骤与机器校验 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 系统边界 |
| [docs/PRD.md](docs/PRD.md) | 产品需求 |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | 真实可执行命令 |
| [docs/DEVELOPMENT-PLAN.md](docs/DEVELOPMENT-PLAN.md) | 里程碑与状态 |
| [docs/QUALITY-STANDARD.md](docs/QUALITY-STANDARD.md) | 质量门控 |
| [docs/TEST-PLAN.md](docs/TEST-PLAN.md) | 测试清单与 CI 接线 |
| [docs/PLATFORM-INTEGRATION-STATUS.md](docs/PLATFORM-INTEGRATION-STATUS.md) | 由注册表导出的各平台状态 |
| [docs/ASR-BACKCHECK.md](docs/ASR-BACKCHECK.md) | 旁白 ASR 门禁：只做检测，不做判定 |
| [docs/CONVERGENCE-REQUIREMENTS-2026-11-01.md](docs/CONVERGENCE-REQUIREMENTS-2026-11-01.md) | 2026-11-01 收敛计划及其结果 |
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
- `main` 已**保护**（2026-10-31 启用，2026-11-10 起管理员强制）：必需检查
  `Tests (ubuntu-latest)`、`Tests (windows-latest)`、`Repo policy checks`；必须 PR；
  禁止 force push；禁止删除；线性历史
- 单人所有者无法自审，因此必需批准数为 0；有第二位评审者时提高到 1
- 分支注册表：`config/governance/branch-registry.json`，由
  `python scripts/check_branch_registry.py --today <日期>` 离线校验
- 文档保鲜：每份跟踪文档带验证日期，代码变更后必须同步，由
  `python scripts/check_doc_freshness.py` 在本地与 CI 校验（规则见
  [docs/DOC-SYNC.md](docs/DOC-SYNC.md)）
- 未完成工作见 [GitHub Issues](https://github.com/Xander-Xai/X-SuperPlay-ContentOps/issues)

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
