---
status: experiment
canonical: false
issue: "#34"
date: 2026-10-28
---

# 生产合同与编辑门禁（P0 + P1 落地记录）

> 来源判断：`research/video-replication/cross-repo-borrow-2026-10-28.md` 尚未落盘，
> 本文件直接记录实际实现，不引用未写入的设计文档。
> 事实优先级：本文件描述的是**已合并进代码**的内容；以代码与测试为准。

## 1. 为什么要加，而不是再加一个引擎

仓库此前已经有收据、证据边界和 QC，但没有任何机械约束阻止一次制作：

- 跳过阶段（先有分镜，后补 Brief）；
- 用旧的上游产物继续往下做（Brief 改了，Audience 的批准仍显示有效）；
- 把计划文件当成执行证据；
- 把"技术 QC 通过"读成"可以发布"。

这些都不是代码缺陷，是**顺序缺陷**，收据本身抓不到。所以本轮只加两类东西：

1. **阶段合同 + 双相门禁**（`src/contentops/workflow/`）；
2. **三件代码检查看不到的编辑门禁**（`src/contentops/quality/`）。

## 2. 阶段合同

合同是十段，按本仓库真实链路裁剪，不照搬 dy_x1024 的十三段：

```
brief → audience → research → script → audio → storyboard → assets → compose → quality → delivery
```

| 事实 | 值 |
|---|---|
| 合同 id | `contentops.copy-to-video/v1` |
| 阶段状态 | `pending` / `running` / `ready_for_review` / `approved` / `blocked` |
| 产物 | 每段一个 canonical 路径（`00_brief/brief.json` … `08_delivery/delivery-manifest.json`） |
| 批准记录 | reviewer + 时间 + **产物 SHA-256** + **上游指纹** |
| 失效规则 | 产物或任一上游变化 → 该段 `stale: true`，不再满足下游前置 |
| 绕过开关 | **没有** |

`approve` 必须同时满足：上一轮 `check` 成功、产物未变、上游未变、有 `--confirm`、
有具名 reviewer。检查失败不会静默降级，状态直接是 `blocked`。

### 从哪里借鉴

只借鉴 dy_x1024 的**机制**，不借鉴它的实现与 provider：

| 借鉴项 | dy_x1024 位置 | 本仓库实现 |
|---|---|---|
| 阶段常量与唯一事实源 | `scripts/canonical_workflow.py` | `contract.STAGES` |
| `check` + `approve` 双相门禁 | `scripts/workflow_gate.py` | `gate.check_stage` / `approve_stage` |
| 输入变化使下游失效 | 同上（fingerprint） | `is_current` / `reconcile` |
| 无 force/bypass | 同上 | 无该参数 |

**未取用**：它的本地 CUDA/ComfyUI 数字人、本地 IndexTTS、ChatGPT bridge 生图、
Gemini 可见会话、gflow 付费 i2v、OpenChatCut、Remotion 运行时。这些都由 MiniMax
订阅 API 或既有 Easel/HyperFrames 路径替代。

## 3. 编辑门禁

| 模块 | 检查什么 | 为什么代码 QC 看不到 |
|---|---|---|
| `quality/report.py` | 单一 `verdict`、单一 `graded_target`、确定性输出 | 两份并列报告曾同时像"当前结论" |
| `quality/script_rhythm.py` | 行长、钩子长度、时长窗口、模板话术、未声明第一人称、连续连接词、问题链 | 这些决定"能不能说"，不是"画面对不对" |
| `quality/subtitle.py` | 时间戳、重叠、空 cue、行长、行数 | 字幕存在 ≠ 字幕可读；ASS 厘秒缺陷就是这样漏过的 |

三条共同规则：

- 全部 fail-closed：校验器抛异常也算失败；
- 不修改输入：字幕与脚本只检查，不改；
- `production_ready` 永远是 `false`，人工审阅是独立产物。

## 4. 使用方式

```powershell
# 新项目启用合同（显式 opt-in；旧项目不受影响）
python scripts/workflow_gate.py init --project projects/<slug> --slug <slug> --account x-superplay-1024

# 每段先检查，再具名批准
python scripts/workflow_gate.py check   --project projects/<slug> --stage brief
python scripts/workflow_gate.py approve --project projects/<slug> --stage brief --reviewer Founder --confirm

# 查看当前应做的阶段
python scripts/workflow_gate.py status --project projects/<slug>

# 生成唯一质量报告
python scripts/quality_report.py --project projects/<slug> --target final.mp4 `
  --script 02_script/script.json --srt assets/captions/default.srt
```

退出码：`0` 通过，`1` 门禁拒绝或检查失败，`2` 用法错误。

## 5. 测试

| 套件 | 覆盖 |
|---|---|
| `tests/test_workflow_contract.py` | 阶段 DAG、状态词表、保存/读取、stale 判定、policy lock |
| `tests/test_workflow_gate.py` | 缺产物、坏 JSON、上游未批准、确认缺失、批准后改字节、路径逃逸、校验器崩溃 |
| `tests/test_quality_gates.py` | verdict 优先级与确定性、脚本七类拒绝、字幕五类拒绝 |

三套均纯 stdlib、无 provider、无媒体文件，已接入 `.github/workflows/ci.yml`。

## 6. P2：逐 claim 证据模型（2026-10-28）

全局"真实素材 ≥70%"是**整片**统计量，它会同时放过两种错误：一个 claim 完全无证据，
以及一条每条 claim 都有证据但动画占比更高的解释型视频。所以 P2 把门禁改成逐 claim：

| 事实 | 值 |
|---|---|
| 模块 | `src/contentops/media/claim_coverage.py` |
| 规则 | claim 必须存在；BLOCKED 不可引用；事实类 claim（runtime/source/historical）必须 SUPPORTED；至少一个承载它的视图必须用真实素材（recording / real_source / real_document / real_screenshot） |
| 允许无实拍 | judgement / editorial_transition / cta 不算事实断言 |
| 未出现的 SUPPORTED claim | 记为 warning + `uncovered`，不硬失败 |
| 证据模式 | `EVIDENCE_LED`（比例 FAIL）/ `CLAIM_LED`（比例降为 WARN，逐 claim 为 FAIL）/ `EXPLANATORY`（比例 INFO） |
| 接线 | `workflow_gate.py check --stage storyboard` 自动读取同目录 `claim-map.json` 与 `assets.json` |

这解决了 CURRENT-STATE 记录的 65/30/5 与 ≥70% 冲突，但**没有替创始人改默认值**：
新项目可选择 `CLAIM_LED`，旧项目行为不变。

## 7. 受众 Lens 与时长策略（2026-10-28）

这两项是 dy_x1024 有、本仓库完全缺失的纯逻辑能力，已作为独立模块移植：

| 模块 | 规则 | 接线 |
|---|---|---|
| `src/contentops/workflow/audience.py` | 每条视频必须声明主分群（capability_decider / workflow_adopter / opportunity_builder）、触发情境、现有替代、代价、期望进展、需要的证明、反对意见、价值类型、情绪转折；`validated` 要 ≥2 个来源且至少 1 个直接信号；`exploratory` 要写可学习问题、可证伪信号和 CTA；禁止"所有人"这类泛人群词 | `workflow_gate.py check --stage audience` |
| `src/contentops/workflow/duration.py` | 内容类型 → 时长档位（60/120/180/240/300），目标必须落在档位区间；未知内容类型不猜；policy 可被项目覆盖 | `workflow_gate.py check --stage script`（与节奏检查并行） |

两条共同边界：不替作者选分群、不替作者定时长；只拒绝**声明不出来**或**声明与档位冲突**的文档。

## 8. 明确没做的

1. **没有改 `scripts/qc_video.py` 的判定逻辑**；`cut_qc.py` 只新增了 `CLAIM_LED` 分支，
   `EVIDENCE_LED` 与 `EXPLANATORY` 的既有分支语义不变。
2. **没有把账号 DNA 的默认 `evidence_mode` 改成 `CLAIM_LED`**。这是 Founder 决策，
   需要一条真实样片作依据。
3. **没有接发布与指标回流**。`09_feedback` 的 schema 设计仍待 P3。
4. **没有把合同写进 `new_project.py`**。旧项目结构保持不变，合同是显式启用。
5. **没有更新 CURRENT-STATE / RUNBOOK**（Tier-1 双语文档）。本轮事实以本文件与
   代码为准，待下一轮连同 zh-CN 镜像一起更新。

## 9. dy_x1024 吸收清单（2026-10-28）

源仓库将以 `a5952a44dbf47d44c1a4bf475e3653b542c25ac1` 为准退役。删除前做了两层保底：

### 9.1 归档（可重建）

`research/vendor/dy1024-design-2026-10-28/`——114 个文件、1.2 MB，包含设计层脚本、
配置、51 个 JSON Schema、profiles 与操作文档。**它是档案，不是依赖**：没有任何
`src/`、`scripts/` 或 CI 代码从该目录 import。逐项状态见该目录的 `MANIFEST.md`。

排除项：本地 GPU/ComfyUI/IndexTTS/FunASR、ChatGPT bridge、Gemini web、gflow 付费、
OpenChatCut、Remotion 运行时、`production/`、`runtime/`、`state/`、审计叙事。

### 9.2 已启用（代码 + 测试 + CI）

| 能力 | 模块 | 接线 |
|---|---|---|
| 选题 backlog + 候选加权评分 | `src/contentops/workflow/topics.py` | `scripts/workflow_docs.py` |
| 证据可行性预判 | `src/contentops/workflow/human_forecast.py` | `workflow_docs.py check --kind forecast` |
| 平台安全发布策略 | `src/contentops/workflow/platform.py` | `delivery` 阶段读取同级 `publish-plan.json` |
| 版权台账 | `src/contentops/workflow/rights.py` | `assets` 阶段读取同级 `rights-ledger.json` |
| 工作流改进日志 | `src/contentops/workflow/improvement.py` | `workflow_docs.py check --kind improvement` |
| 反馈与指标导入 | `src/contentops/workflow/feedback.py` | `workflow_docs.py check --kind feedback/metrics` |
| Skill 执行 provenance | `src/contentops/workflow/provenance.py` | `workflow_docs.py fingerprint-skill` |
| 包命名与 content id | `src/contentops/workflow/naming.py` | `workflow_docs.py next-id` |
| 交付清单 | `src/contentops/workflow/delivery.py` | `delivery` 阶段校验自身清单 |
| 语义视觉路由 | `src/contentops/workflow/visual_route.py` | `compose` 阶段读取同级 `visual-route.json` |
| 文案策略卡 | `src/contentops/workflow/copy_strategy.py` | `script` 阶段读取同级 `copy-strategy.json` |
| 技术解释编辑门禁 | `src/contentops/quality/technical_explainer.py` | `script` 阶段按 `content_type` 自动启用 |
| 受众 Lens / 时长策略 / 逐 claim 证据 | 见 §6–7 | `workflow_gate.py check` |

测试：`tests/test_absorbed_workflow_docs.py`（35 项）、`tests/test_audience_duration.py`
（17 项）、`tests/test_claim_coverage.py`（14 项）、`tests/test_naming_delivery_route.py`
（24 项），均已接入 CI。十阶段 `check → approve` 链路已用真实文档做端到端烟测。

### 9.3 Skill 迁移

共享库 `C:\Users\Administrator\.agents\skills`，主机目录只放 junction：

| Skill | 许可证 | 迁移范围 |
|---|---|---|
| `jacky-motion` | MIT | SKILL.md、references、styles、base-template、validators |
| `ian-xiaohei-illustrations` | MIT + NOTICE | 文本与 references；不含 13 MB 示例图 |
| `ian-xiaohei-scenes` | MIT + NOTICE | 文本与 references；不含 8.6 MB 示例图 |
| `x-superplay-broll-production` | first-party | SKILL.md + references（含 material-source-rights） |
| `x-superplay-copy-orchestrator` | first-party | SKILL.md + components + directions |
| `x-superplay-design-direction` | first-party | SKILL.md + references |
| `video-shotcraft` | Apache-2.0 | 112 张镜头卡；不含 838 MB Remotion 资产 |

未迁移：`jacky-de-ai`（许可证未知，且 `text-polisher` 更强）、`b-roll-finder`
（依赖 GPU Whisper 与浏览器捕获）。两个账号的 `skill_route` 已声明 shared 路由，
`check_account_dna.py` 新增 `path_base: "shared"` 解析与校验。

### 9.4 删除安全性

- 所有 HIGH 价值设计层能力：已移植、已归档或已明确拒绝（`MANIFEST.md` 逐项列出）。
- 第三方 skill：已带许可证复制到共享库，不再依赖源仓库。
- 源仓库中的本地 provider、运行产物、审计叙事：**有意不吸收**。
- 因此删除 `D:\Projects\dy_x1024` 不会丢失本仓库尚需的能力。
