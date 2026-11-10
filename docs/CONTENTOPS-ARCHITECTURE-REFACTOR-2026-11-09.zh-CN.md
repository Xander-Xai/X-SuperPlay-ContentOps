# ContentOps 全局架构重构审查（2026-11-09）

> 状态：**提议 + 第一条独立 Adapter 试点已提交至本分支**。本文件不是生产验收证明。
> 基线：`main` 对应 tree `545b64cd5c40d1f3aa1ce13c7f313a017a3fa77c`；并检查未合并 Draft PR #132，HEAD `ccf01310416292fd31951a7e3695fd7ba963a628`。本重构分支从该 HEAD 派生，因此不能把本文件误当作 main 的现状。
> 保护：不得覆盖开发者本地未提交素材、MP4、音频、缓存、人工审批记录；不得自动发布、修改 API Key 或扣除付费服务额度。

## 1. 结论：保留证据闭环，重构运行边界

当前仓库不是空壳：main 有 Content Router、账户 DNA、TrendRadar/NewsNow/GitHub 候选源、SourceArtifact/ClaimLedger、V1/M5 视频生产、Easel 固定运行时、MiniMax 若干能力、离线图文包、X 手动交付与离线指标，以及可拒绝的质量/人工审查。未合并 #132 另有 `produce_video.py`、Huashu 语义镜头、真实旁白时间线、分层增量缓存、视觉 QC、Pexels/Pixabay B-roll 搜索和供应商调用收据。

**保留**：SourceArtifact 和 ClaimLedger；Bundle 的跨形式证据共享；版权与执行授权分离；供应商显式配额；digest/收据；不同内容形态独立 QC；人工最终审看；Easel adapter 而非 fork。

**改造**：众多顶层命令与 M5 阶段紧耦合；`m5_production.py`（审查时约 2732 行）和 `produce_video.py`（约 907 行）的编排、平台/渲染/计划/审批权责混杂；CLI、主工作流与 Agent Driver 对相同能力的包装重复；运维文档中的历史时间点混入当前实现；缺少真实可核验的跨平台发布后分析闭环。

**不做**：为个人项目立即引入微服务、分布式队列、全量 LangGraph、第二个视频生成大平台或另一个证据库。这些并不直接解决现有视频“可看、可信、可发”的缺口。

## 2. 能力地图：实有 vs 未具备

| 域 | main | #132 未合并分支 | 真正差距 |
|---|---|---|---|
| 选题 / 账号 | 路由、账户配置、候选数据去重与本地运行记录 | 延用 | 候选到真实受众反馈没有验证回路 |
| 证据 | GitHub / 手工来源、claim 引用、权限检查 | 源码片段选择与真实素材改进 | 真实终端/UI/实验录屏不足，源码声明不能冒充实验结果 |
| 文案 | Brief、脚本、审稿和 bridge | raw draft、AUTO/REVIEW | 内容价值判断仍需人工，事实与措辞需逐条核对 |
| 视频 | M5、Easel、FFmpeg、MiniMax TTS/图/视频 | Huashu 动效、分段旁白、可恢复缓存 | 语义画面、片尾来源展示、数字人和真实 TTS 验收 |
| 图文 | 图文工作流、XHS/GZH verify-only adapter、手工交付 | 未形成真发布 | 两条渠道的版权、真实运行和人工审查 |
| QC | 技术 QC、Rights Gate、证据和人工门 | 镜头重复检测、技术/视觉/人工状态分层 | 自动指标不能替代逐帧/逐 claim 审看 |
| 发布/复盘 | X 手动包、部分离线 CSV 指标 | 不包含自动发布 | 平台授权发布收据、实际曝光/转化归因仍缺 |

不能把 `QC_PASSED`、`TECHNICAL_PASS`、`VISUAL_PASS` 或 CI 全绿映射为 `PUBLISH_APPROVED`。当前已知的 A 成片仍存在 0 个真实终端/UI/日志指标画面、源码自述冒充运行证据的风险，且人工审看未完成；B/C 的增量计划并非重渲染验收。

## 3. 推荐目标架构

```text
               Business/Research/GitHub/manual input
                            │
  ┌─────────────────────────▼─────────────────────────┐
  │ Intake: account profile / topic / source rights   │
  │ Discovery adapters: TrendRadar, NewsNow, GitHub    │
  └─────────────────────────┬─────────────────────────┘
                            ▼
               SourceArtifact + ClaimLedger
                 (canonical evidence boundary)
                            │
                            ▼
                 Content Brief / Content Bundle
                     Human brief approval
                  ┌─────────┴─────────┐
                  ▼                   ▼
          VIDEO WORKFLOW        GRAPHIC/TEXT WORKFLOW
        script / narration       outline / copy / images
        storyboard / shots       platform formats
        asset / render/QC        layout / format/QC
          │  Provider ports         │
          │  Easel / FFmpeg          │
          │  Huashu / MiniMax        │
          └─────────┬─────────┘
                    ▼
         Unified Receipt & Artifact Store
          (input and output digest, rights,
           provider usage, cost, state)
                    ▼
       Technical / Visual / Content Review
                    ▼
         Owner-approved delivery package
                    ▼
       MANUAL publication / read-back receipt
                    ▼
         Metrics ingestion / analysis
         (only actual, timestamped values)
```

在 **application 层**维持单体 Python 项目即可。外部项目走 **ports/adapters**，而不是复制整套应用：

- `core`：ContentRun ID、版本化输入契约、Artifact URI、证据 hash、权限/配额状态和事件；避免将平台字段塞入核心。
- `application`：薄的 workflow/stage runner，只有确定性依赖、幂等、断点续跑与失败收据；人审是不可自动执行的节点。
- `adapters`：趋势源、GitHub/媒体源、语音/ASR、镜头分析、Easel/Huashu/FFmpeg、平台交付；显式 optional dependency。
- `presentation`：CLI / Easel Host / Agent Driver 共用同一 application service；CLI 不再持有另一套业务规则。
- `observability`：本地、离线的收据聚合和指标导入；真实供应商花费未核实就标 `unknown`，不得用额度百分点折算人民币。

这是一份**目标逻辑分层**，不是要求立即移动所有现有源文件。保留现有 `src/contentops/{routing,evidence,media,workflow,platforms,publish}` 接口，在薄 façade 背后逐段抽离。

## 4. 必须避免的冗余

1. **多入口一致性**：`run_v1.py`、`m5_production.py`、`produce_video.py`、`agent_drive.py` 的业务阶段应汇聚至统一的 run/stage contract。保留兼容命令，禁止额外创造 `run_v2.py`。旧入口退役必须在真实 fixture 和黄金样片对齐后进行。
2. **重复 Gate**：保留四种不能相互提升的结论：`TECHNICAL`、`VISUAL`、`CONTENT_REVIEW`、`PUBLISH_AUTHORIZATION`。不要让重复 QC 文件各自成为权威；统一索引指向唯一的 current receipt，其历史版本保留。
3. **资产/素材注册**：Pexels/Pixabay、MiniMax、Huashu、本地录屏、SceneDetect 候选都回到既有 `sources/assets.json` / source record / rights check；不能再造并行 Asset Registry。
4. **工作流抽象**：视频和图文共享 evidence/receipt/review 的约束，不共享声音、镜头、转场等业务 stage；防止“万能 Stage”。
5. **能力/供应商发现**：先查已有 `runtime/skill-registry.json`、media capability registry 和固定 Easel pin，已有就加 adapter，不重复拉一个新的平台。
6. **历史文档**：`README`、`CURRENT-STATE`、`DEVELOPMENT-PLAN` 与 PR 中历史实现状态要加上 `main / PR head / local-only / proposed` 标识，不能依据 11 月 1 日的旧表声称 11 月 9 日真实运行。
7. **测试纪律**：保持离线/零 Key CI，不因每个文案/README 修改都重跑真实视频或扣费探针；L0–L3 按影响分层，全量 CI 在 PR 完成前执行。

## 5. 开源组件筛选与引入决策

| 项目 | 用途 | 仓库已具备什么 | 引入意见 | 状态 |
|---|---|---|---|---|
| [PySceneDetect](https://github.com/Breakthrough/PySceneDetect) v0.7.2 / BSD-3-Clause | 外来原片的真实切镜头检测 | 只针对输出的视觉 QC 与语义镜头规划 | **P0**：read-only 候选镜头 adapter；不改 M5 时间线 | 本分支代码试点；无实片验收 |
| [WhisperX](https://github.com/m-bain/whisperX) / BSD-2-Clause | 真实音频强制对齐、逐词时间戳 | ASR 回听与按旁白时间线切镜头 | **P1**：先用真实中文/英文技术视频做对齐对照；按需启用 | 调研，未接入 |
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | 本地 ASR、成本友好 | 已有 `asr_backcheck.py` 比较器 | **P1**：用 provider 适配现有比较器，不另建转录流程 | 调研，未接入 |
| [Easel](https://github.com/ZJU-REAL/Easel) v0.3.0 | 既有 Host 的多 Agent 和工作台能力 | pinned v0.2.1，Host 安全审核阻断 | **P1**：独立 pin 升级评估；绝不在本 PR 偷换 runtime | 已有旧版锁；升级未执行 |
| [RSSHub](https://github.com/DIYgod/RSSHub) | 扩展公开信息源 | TrendRadar、NewsNow、GitHub | **P2**：只有出现可量化的源覆盖率缺口时才部署外部服务 | 候选 |
| [Postiz](https://github.com/gitroomhq/postiz-app) / AGPL-3.0 | 多平台排期/数据；API 集成 | Easel 自带平台发布接口，ContentOps 不持发布权限 | **P2 / 不进入当前产线**：许可、资源、权限和平台兼容成本高 | 候选，未部署 |
| [rea-video](https://github.com/JuneYaooo/rea-video) / Apache-2.0（需落地复核） | 参考视频拆镜头与创作方式 | M5 生成链，不做“参考视频教案” | **P2**：离线观摩/分析试验，不当作事实或 AI 鉴定权威 | 候选，未接入 |

**拒绝立即集成**：第二套端到端自动短视频流水线、未经批准的浏览器发布机器人、大体积多 Agent orchestration；已有链路未验收前增加其数量反而降低可维护性。

外部项目不得复制源代码至仓库。每个 adapter 记录上游 URL、版本/tag、许可证、运行依赖、可信安装来源、网络/费用/权限边界、所需测试与撤回方法。商用或在线部署前单独审查每项许可证与第三方素材权利。

## 6. 本分支已实施的狭窄试点

新增：

- `src/contentops/media/scene_analysis.py`：接入 PySceneDetect 的 `detect / ContentDetector` API，按视频 SHA-256 生成镜头候选，独立严格校验时间线。
- `scripts/scene_detect.py`：显式手工运行；输入必须是项目内本地视频。
- `tests/test_scene_analysis.py`：无网络、无依赖安装、可注入 detector 的拒绝路径与输出契约测试。
- CI 单独运行该文件，不将它与现有付费生产烟测绑定。

```bash
# 仅当确需分析外来原片时，在隔离环境安装可选依赖
python -m pip install "scenedetect==0.7.2"

# 在本分支运行
python scripts/scene_detect.py projects/<slug> --source assets/reference.mp4

# 查看镜头建议，不代表批准使用
cat projects/<slug>/receipts/scene-candidates.json
```

此操作不调用供应商 API、不下载素材、不修改 storyboard、不批准版权、不认定视频为事实证据、不产生公开发布行为。场景切分只解决**镜头边界**，不会解决技术论证、画面美感、来源真实性。

## 7. 后续重构交付切片（每个单独 PR）

**P0a — 产线真实性**：对 A 已有成片执行人工时间码审看；补真实演示/终端/指标来源；重录缺失证据；让视频片尾真的呈现承诺的来源；完成账号视觉模板定稿。退出标准：人审收据为真实审核人+时间+版本，且 claim 和渲染 digest 一致。不可用 CI 替代。

**P0b — 统一 ContentRun 与 Stage Runner**：先对 `m5_production.py` 的 `stage_sources/claims/script/narration/storyboard/compose/qc/review` 做 characterize tests；提取 `RunContext`、`StageResult`、统一回执/缓存状态，两个入口薄包装；历史兼容无损。退出：同一 fixture 输入输出相同、无重复收费/违规升级；三条黄金样片无回归。

**P1 — 语音/镜头同步与分镜升级**：真实 MiniMax/H3、本地 TTS+ASR 对照，WhisperX 只做可选对齐；明确汉语数字、代码、专业词汇和长停顿案例；逐镜视觉语义评估与 B/C 增量计划复核。

**P1 — 图文双线产出**：在 XHS/GZH 许可证与本地 runtime 审计通过后，选择一个 format 真正输出可人工上传的成品，维持独立内容审查。

**P2 — 运营闭环**：先允许手工导入 X/小红书/公众号实际数据（内容 ID、链接、统计时间、指标来源），做按账号和发布批次的对比。真实平台 API/OAuth 方案具备授权、费用预算、回读与幂等后再评估；未经授权不自动发布。

## 8. 验收和止损

- `main` 和 #132 原分支不得直接被本试点修改；本分支用 Draft PR 叠加到 #132，合并顺序不倒置。
- 验证阶梯：离线单测 → Windows/Linux CI → 本地真实输入无付费样片 → 明确预算批准后的供应商调用 → 人工逐镜审看 → 手工交付。只有前一层证据完整才进入下一层。
- 评估 3 个不同真实选题，不只固定 synthetic fixture。每条要核实：原始来源、技术讲述、视觉证据、声音与字幕同步、过度重复、片尾来源、素材版权、片长与账号风格。
- 量化追踪：一次真实成片的人工作业分钟数、每分钟实际现金成本/额度消耗（分开）、QC FAIL 率、人工返工原因、单镜增量重渲是否节省费用；没测就写 `UNKNOWN`。
- 只有产量、审看通过率与实际分发反馈改善时才保留外部集成；否则删除 adapter，不发展成第二个大系统。

## 9. 可验证范围与限制

本次通过 GitHub 连接核查了完整受管理文件树、main/PR 当前提交、执行入口、热点与证据域、视频/图文/审核/交付域、关键测试、CI 和现有文档。没有下载并逐行运行全部 800 个文件；用户机器上未提交的 A/B/C 视频、缓存与素材无法由 GitHub 查询，本次不能替代这些本地验收。此文将“已经写入分支”和“已在真实视频跑通”严格分开。
