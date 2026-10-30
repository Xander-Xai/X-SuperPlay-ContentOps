---
translation_of: docs/RUNBOOK.md
language: zh-CN
translation_status: synced
---

# 运行手册

[English](RUNBOOK.md) | [简体中文](RUNBOOK.zh-CN.md)

> 真实可执行命令。从实际脚本行为推导，非假设。
> 最后更新：2026-10-04

## 0. 环境检查

```powershell
python scripts/doctor.py
```

## 1. 引导（首次或清理后）

```powershell
python scripts/bootstrap.ps1    # Windows
bash scripts/bootstrap.sh       # WSL/Linux
```

如 Easel 运行时缺失/损坏：

```powershell
python scripts/resolve_easel.py --bootstrap
```

## 2. 验证 Easel 运行时

```powershell
python scripts/verify_easel_runtime.py --resolve-tag
```

## 3. 创建新项目

```powershell
python scripts\new_project.py --slug my-video --title "My Video Title"
```

### 3.1 这个项目该走哪条流水线？

账号决定。两个账号、两条链路，一条命令给出答案：

```powershell
python scripts\account_route.py projects\easel-fi-audio-first
python scripts\account_route.py projects\easel-1024-proof --json
```

它读 `project.yaml` → `account_slug` → 账号 DNA，输出该账号 `evidence.mode` 决定的
生产者顺序，以及同一份 DNA 里声明的创作类 skill 归属：

| 账号 | 模式 | 流水线 |
|---|---|---|
| `x-superplay-1024` | `EVIDENCE_LED` | `audio_first_plan` → `recording_plan` → `capture_terminal_evidence` → `build_evidence_package` → `qc_video` |
| `x-superplay-future-intelligence` | `EXPLANATORY` | `audio_first_plan` → `build_evidence_package` → `qc_video` |

- 两条链路最后都落到同一个打包器和同一个 QC。正因为收据底座共用，门禁才是同一套，
  而生产者不是。
- 没有声明流水线的模式会被拒绝（`EVIDENCE_MODE_UNMAPPED`），路由器不猜；没有
  `account_slug` 的项目根本得不到流水线。
- 路由器只说明该跑哪条链，不认证结果。成片是否属于该账号仍由 `cut_qc`
  （`account_composition`、`manual_recording_forbidden`、`account_duration`）和人决定。

## 4. 运行生产流水线

> 这是最早的一代流水线，**不读任何账号 DNA**。凡是属于 1024 或未来智能的项目，先用
> §3.1 解析出链路并按它执行；账号的配比、录屏与时长规则随后由 `cut_qc` 强制。只有
> 账号没有声明流水线的项目，或下面诊断用的 fallback 引擎，才直接用 V1。

```powershell
python scripts\run_v1.py projects\my-video
```

## 5. QC

```powershell
python scripts\qc_video.py projects\my-video
```

## 6. 开发门控

```bash
python scripts/dev_check.py            # 完整门禁：策略、文档、i18n、DNA、全部套件
python scripts/dev_check.py --quick    # 跳过仓库策略与套件运行
python scripts/run_tests.py            # 单独跑全部 tests/test_*.py
python scripts/run_tests.py --list
python scripts/run_tests.py --only workflow
python scripts/run_tests.py --missing-from .github/workflows/ci.yml   # CI 漂移守卫
```

共 55 个套件（`tests/test_*.py` 加 `scripts/test_basic.py`），采用**发现**而非手工清单：门禁曾在一个迁移套件失败的同时打印
"ALL CHECKS PASSED"，因为那个套件从未被调用。每个套件独立进程运行；自行跳过
（缺 ffmpeg 或被 gitignore 的夹具）的套件退出 0 记为通过，但**无法启动**的套件
一律算失败，绝不算跳过。

`--missing-from` 让 CI 保持诚实：它只认 workflow 的 `run:` 步骤（注释不算），
某个套件存在却没有任何步骤执行它时就会失败。2026-10-28 之前有四个套件处于该状态。

## 7. Easel 上游监控

```bash
python scripts/check_easel_upstream.py
```

## 8. i18n 一致性检查

```bash
python scripts/check_i18n.py
```

## 9. 原生旁白 v2（A/B/C 样本）

设计决策：`adr/ADR-008-native-narration-v2.md`。口播稿对照锁定原文与
evidence lock 校验，三方版本映射（原文 / 口播 / 合成文本）用 `--write` 重新生成：

```powershell
python scripts\verify_spoken_script.py --write
```

干跑（完全离线；不发送任何请求，也不读取余额）：

```powershell
python scripts\run_ab_sample.py
```

真实执行。`--execute` 是显式开关；每次请求前后都会读取套餐额度与余额，
订阅类凭据未通过 `SAFE_INCLUDED_PLAN` 时直接拒绝。`--budget-chars` 与
`--budget-asr-calls` 是硬上限：

```powershell
python scripts\run_ab_sample.py --execute
python scripts\run_ab_sample.py --execute --a-mode fresh     # 精确文本对照（付费）
python scripts\run_ab_sample.py --execute --regenerate S02   # C 组局部重生成
python scripts\run_ab_sample.py --execute --variants N --extra-segment S04 --receipt-suffix term-check
python scripts\run_ab_sample.py --recheck                    # 仅重算测量；无 provider、无 ASR
```

- A 默认复用已有 Golden 旁白的本地节选（0 provider 成本）；`--a-mode fresh`
  则重新合成对照。
- 样本凭证与术语检查凭证是两个独立文件；辅助运行不会覆盖样本凭证。
- 真实音频写入 `outputs/`（gitignored）。运行停止于 Founder 试听：
  `production_ready` 保持 `false`，不发布任何内容。

## 10. 旁白 v3（口播稿、导演、D/E/F 样本）

设计决策：`adr/ADR-009-narration-v3-creator-director.md`。校验口播稿与导演计划，
并刷新版本映射：

```powershell
python scripts\verify_creator_script.py --write
```

干跑（离线；不发送请求，也不读取余额）：

```powershell
python scripts\run_creator_sample.py
```

真实执行。`--execute` 是显式开关；沿用 v2 的仅订阅凭据解析、M Plan 门控与逐请求
前后额度/余额读取；`--budget-chars` / `--budget-asr-calls` 是硬上限：

```powershell
python scripts\run_creator_sample.py --execute
python scripts\run_creator_sample.py --execute --budget-chars 1200 --budget-asr-calls 5
python scripts\run_creator_sample.py --summary-only   # 仅重新渲染 md 凭证；无 provider、无 ASR
```

先盲听，再对答案：

- 文件：`outputs/founder-v3-sample/candidate-1.wav` … `candidate-3.wav`
  （文件名不含任何版本信息）；
- 对应关系：`projects/easel-enhanced-golden/review/narration-v3-sample-receipt.json`
  的 `listening_key`；
- 先按六项标准打分再揭晓：`projects/easel-enhanced-golden/review/listening-review-v3.md`。

ASR 与 CI 通过不是自然度结论；在 Founder 批准前 `production_ready` 保持 `false`。

## 11. 旁白 v3 样片视频（旁白 → 视频桥接）

`scripts/build_v3_sample_video.py` 把一个已生成的 v3 候选渲染成可观看的视频，
证据仍是锁定素材。**不产生任何 provider 调用。**

```powershell
python scripts\build_v3_sample_video.py --arm E
python scripts\build_v3_sample_video.py --arm D --out-name v3-sample-D
python scripts\build_v3_sample_video.py --arm E --audio outputs\founder-v3-sample\candidate-3.wav
```

- `--arm` 通过样本凭证的 `listening_key` 解析候选；文件必须与该臂的
  `audio.sha256` 一致，否则拒绝构建。
- 单元 → 证据位置来自口播稿的 `source_paragraphs` 与 evidence lock；不使用任何
  生成素材。
- 逐单元时长从音频实测。内部边界取距离“按字符数比例预期”最近的静音中点；
  每个边界的方法写入凭证。
- 这是三单元节选（U01、U03、U05），候选音频位于 gitignored 的 `outputs/`，
  因此按设计只能在生成过它的机器上构建。
- 产物：`projects/easel-enhanced-golden/v3-sample-video/final/v3-sample.mp4`、
  `receipts/v3-sample-video.json`、`receipts/qc-report-v3-sample.{json,md}`。
  `production_ready` 保持 `false`。

观感选项，同样使用既有音频、无 provider 调用：

```powershell
python scripts\build_v3_sample_video.py --arm E `
  --project projects\easel-enhanced-golden\v3-sample-motion `
  --out-name v3-sample-motion --motion ken-burns --caption-mode phrase
```

- `--motion static`（默认）或 `ken-burns`。Ken Burns 来自 pinned 上游滤镜，
  由于该滤镜未设置 `x`/`y` 表达式，会朝左上角推近。
- `--caption-mode sentence`（每单元一条）或 `phrase`（每分句一条；单元时长按
  字符数分配，少于六字的碎片并入相邻分句）。
- 对比版请用独立的 `--project`，避免两份凭证互相覆盖。

## 13. 账号 DNA

两个账号的定位写在 `config/accounts/*.json`。DNA 承载品牌基座、画面配比、字幕
样式、封面规则和叙事模板；每个账号的一键提示词放在同目录的
`config/accounts/prompts/`。

按品牌基座和它自己的提示词校验 DNA：

```powershell
python scripts\check_account_dna.py
python scripts\check_account_dna.py --json
```

schema、配色、配比求和、动效允许/禁止列表、字幕样式、封面留白下限、录屏政策，
以及 DNA 与提示词之间的一致性，任一不成立即报错。该检查是只读的，并已并入
`scripts/dev_check.py` 与 CI。

按 DNA 重建某个账号变体（无 provider 调用；旁白与卡片来自本地 `outputs/`）：

```powershell
python scripts\build_account_variants.py
python scripts\build_account_variants.py --only x-superplay-1024
```

字幕的 `burn_style` 从 DNA 读取，而不是写死在脚本里，所以改字幕样式属于配置改动。
变体视频止步于 `PENDING_FOUNDER_REVIEW`，不声称任何发布链接。
## 14. 证据捕获与证据型成片包

只通过已批准的 plan 捕获；plan 是 allowlist，它给的是 argv，不是 shell 字符串：

```powershell
python scripts\capture_terminal_evidence.py projects\easel-evidence-capture\script\capture-plan.json --dry-run
python scripts\capture_terminal_evidence.py projects\easel-evidence-capture\script\capture-plan.json --only CAP-20261028-SKILLROUTE-AUTO
```

- `hold_after_exit_s` 让结果在屏幕上停留到能读完；两秒内结束的捕获不是可读证据。
- 非 ASCII 的 argv 会被 `cmd.exe` 包装层损坏，所以 plan 用 ASCII 查询
  （`--match auto-subtitle`，而不是中文词表）。
- 往 APPROVED plan 里加捕获是一次新的批准，不是一次编辑。

构建、评级并打包一条证据型成片：

```powershell
python scripts\build_evidence_package.py projects\easel-1024-proof
python scripts\build_evidence_package.py projects\easel-1024-proof --skip-build
```

依次执行：`build_evidence_cut` → `build_evidence_cover` → `cut_qc` →
`write_review_bundle`，QC 为 FAIL 时以非零码退出。它从不记录人工决定。

- placement 带 `shots`；每个视图受 `target.max_visual_hold_ms` 限制，放大视图必须被
  它的上下文视图包含；
- `cut_qc` 现在会让“超上限却没有声明视图”的静态 placement FAIL，也会让实测冻结 run
  超过声明停留的片子 FAIL；
- 字幕从账号 DNA 的 `visual.caption_style` 读取，`_wrap` 应用中文禁则。

QC PASS 只是技术结论。在记录创始人 ≥80 分之前，成片保持 `production_ready: false`；
只要还有 `internal_review` 且没有 redaction receipt 的捕获，分发就保持阻断。

## 15. audio-first 分镜规划（Build 账号）

先写台词，再让声音决定时长：

```powershell
python scripts\audio_first_plan.py projects\easel-fi-audio-first
python scripts\build_evidence_package.py projects\easel-fi-audio-first
```

- `audio_first_plan.py` 用 MiniMax 逐句合成、实测时长，写
  `receipts/audio-first-plan.json` 并生成 `script/cut-plan.json`。改
  `script/lines.json`，不要改生成出来的 plan；改完用 `--replan` 重跑（音频缓存复用，
  不会二次调用 provider）。
- 需要超过 6.0 s 的台词会被拒绝，而不是让一个视图硬撑；应当拆句，不要拉长画面。
- 之后 `build_evidence_package.py` 依次执行 构建 → 封面 → QC → 审核包。
- Build 账号的门禁是 `manual_recording_forbidden`、`composition_ratio` 与
  `evidence_mode: EXPLANATORY`；声明配比为矢量 70% / 代码 25% / 指标 5%，容差 ±8 个百分点。
- 本机 edge-tts 需要外网代理；没有代理时规划器 fail closed，不会静默换声线。

### 15.1 动效 B-roll（HyperFrames）

```powershell
cd projects\easel-fi-audio-first\motion\arch-flow
npx --yes hyperframes@0.8.208 check
npx --yes hyperframes@0.8.208 render . -o ../../work/motion/arch-flow.mp4 -q delivery
```

- 六个工程逐个执行；清单见 `motion/README.md`
- `work/motion/` 被忽略；HTML 是源，mp4 可重新生成
- 重渲染后必须再跑一次 `build_evidence_package.py`：它会重读每个片段的 SHA，
  片段在已审核收据下发生变化会被拒绝
- 这些片段是解释性画面（`evidence_capable: false`），永远不是证据

## 16. 通过外部 skill 做代码动画

```powershell
$env:PYTHONUTF8 = "1"
python C:\Users\Administrator\.agents\skills\huashu-art-motion\scripts\engine\render.py `
  --spec projects\easel-fi-what-is-agent\motion\specs\p01.json `
  --out  projects\easel-fi-what-is-agent\work\clips\p01.mp4
python scripts\build_code_animation_sample.py projects\easel-fi-what-is-agent
python scripts\qc_video.py projects\easel-fi-what-is-agent --video easel.mp4
```

- 用宿主 Python，不要用 `uv run --with playwright`：宿主能命中本机已有的
  Playwright Chromium，uv 会装更新的 Playwright 并索要本机没有的浏览器版本
- 必须设 `PYTHONUTF8=1`；引擎用默认编码读 spec
- 组装脚本把每句配音放到对应窗口起点，按实测时长写 SRT，并用账号 DNA 字幕样式烧录
- 短视频纯动画样片的 `qc_video` WARN 是可预期的；如实记录，不要当成 PASS

给代码动画样片打包审核材料（封面 + 指纹 + 空评分审核单）：

```powershell
python scripts\package_code_animation_sample.py projects\easel-fi-what-is-agent
```

它用共享卡片渲染器出封面，密度审计失败就报错；写出 `receipts/cover.json`、
`receipts/review-bundle.json`、`receipts/human-review.json`（所有分数为 null）与
`receipts/runtime-receipt.md`。它从不记录分数。

克隆音与本机配乐：

```powershell
$env:PYTHONUTF8 = "1"
python scripts\synthesize_narration.py --text "..." --voice founder_primary_v1 `
  --out-dir projects\easel-fi-what-is-agent\assets\voice --receipt projects\easel-fi-what-is-agent\receipts\voice-01.json
python scripts\synthesize_ambient_bed.py --duration 45 --out projects\easel-fi-what-is-agent\work\bgm.wav
python scripts\build_code_animation_sample.py projects\easel-fi-what-is-agent
```

- 克隆音别名 `founder_primary_v1`；provider voice id 留在私有配置，收据只存哈希
- 配乐在本机合成，峰值 −24.4 dBFS；混音余量低于 18 dB 时组装器直接拒绝
- beat 窗口 = 语音 + 0.35 s，不再用固定 4 s，口播不会落在长停顿里

## 17. 有序生产合同与文档门禁

新项目显式启用；旧项目保持原有目录结构。

```bash
python scripts/workflow_gate.py init    --project projects/<slug> --slug <slug> --account x-superplay-1024
python scripts/workflow_gate.py status  --project projects/<slug>
python scripts/workflow_gate.py check   --project projects/<slug> --stage script
python scripts/workflow_gate.py approve --project projects/<slug> --stage script --reviewer Founder --confirm
```

阶段校验自动运行：受众 Lens（`audience`）、脚本节奏 + 时长 + 技术解释 + 文案策略
（`script`）、逐 claim 证据覆盖（`storyboard`）、版权台账 + 素材候选（`assets`）、视觉路由
（`compose`）、交付清单 + 发布计划（`delivery`）。产物或任一上游产物变化，批准即失效；
没有 force 开关。

纯文档检查：

```bash
python scripts/workflow_docs.py check --kind forecast --input forecast.json
python scripts/workflow_docs.py check --kind rights   --input rights-ledger.json
python scripts/workflow_docs.py check --kind sources  --input source-candidates.json
python scripts/workflow_docs.py score --input candidate.json
python scripts/workflow_docs.py next-id --topic "topic" --root projects
python scripts/workflow_docs.py fingerprint-skill --dir <skill 目录>
```

退出码 `0` = 通过，`1` = 拒绝并列出原因，`2` = 用法错误。

### 17.1 素材候选

在采集之前，把 `source-candidates.json` 写在阶段产物旁边。只要它存在，`assets`
阶段就会校验它。

```json
{"schema": "contentops.source-candidates/v1", "package_id": "pkg",
 "candidates": [{"candidate_id": "SC-001", "creator": "Example Project",
   "source_url": "https://example.com/x", "license": "public_domain",
   "license_text": "CC0 1.0", "license_url": "https://creativecommons.org/...",
   "capture_date": "2026-10-01", "status": "candidate",
   "score": {"relevance": 9, "evidence": 8, "rights": 10}}]}
```

- `status` 永远是 `candidate`：能自行清权的研究清单，等于让台账无物可查；
- 除 `owned` 之外的任何许可都同时需要 `license_text` 与 `license_url`；
- `promotable(document, id)` 是晋升时调用的辅助函数，列出仍挡住的项（许可未知或非法、
  缺许可链接、记录不是 `candidate`、评分不全、加权分低于 6.0）。它给建议；门禁执行的是
  许可一致性，不是这条分数线；
- 台账行可以引用 `source_candidate_id`，此时许可必须一致。

skill 一侧：`x-superplay-source-research`（契约）在两个账号 DNA 中声明；
`b-roll-finder`（找素材的方法论）只在 `x-superplay-1024` 声明，因为 Build 账号的
视觉缺口是插画。

## 18. 一条片，三个平台

抖音、B站、小红书发布的不是同一个画幅：DNA 的竖屏母片是 1080x1920，B站版是
1920x1080，小红书用竖屏片 + 3:4 封面。

```powershell
# 按项目自己声明的画幅评级（不再用常量）
python scripts\qc_video.py projects\easel-1024-proof

# 先看要派生什么，不写任何文件
python scripts\derive_variants.py projects\easel-1024-proof --dry-run

# 派生，并在同一趟里打包
python scripts\build_evidence_package.py projects\easel-1024-proof --variants
```

- `qc_video` 按 `project.yaml` 的 `format` 判；没有项目归属的文件用
  `--expect 1920x1080` 覆盖。旧常量会把横屏片读成"坏掉的竖屏"。
- `derive_variants` 用固定运行时的 `reframe.py` 转画幅（不允许手写滤镜链），逐个
  探测输出，并写 `receipts/variants.json`，绑定母片、每个衍生片和工具摘要。
- 它拒绝没有评级的母片、比母片更旧的收据，以及自己 QC 就 FAIL 的母片——
  **一个 FAIL 就够了**，另一个门禁更新的 PASS 不能覆盖。
- 封面**只报告、不裁剪**：收据按平台写 PRESENT / ABSENT / WRONG_FRAME，修法是按
  该画幅重新出卡。
- 衍生片技术上正确，不代表内容通过。`production_ready` 仍为 false，仍由人工
  审核决定。

## 19. 内容路由器：选题

路由器运行在项目存在**之前**。它回答"这是为谁做的、这讲的是什么"，
并产出一份流水线可以直接接手的 Brief。

```powershell
# 哪些账号可以路由，是否可用
python scripts\content_route.py accounts

# 路线 A：由账号圈定范围去找选题
python scripts\content_route.py start --account x-superplay-1024 --mode hotspot

# 只看检索计划，不抓取任何东西
python scripts\content_route.py start --account x-superplay-1024 --mode hotspot --plan-only

# 路线 B：由所有者指定主题
python scripts\content_route.py start --account x-superplay-future-intelligence --mode topic `
    --topic "如何使用 LangGraph 开发可靠的 Agent？"

# 由人具名选定一个候选
python scripts\content_route.py select --candidate CAND-XXXXXXXX --by "Founder"

# 这次运行到哪了，下一步需要什么
python scripts\content_route.py status --run RUN-20261030-XXXXXXXX

# 由人审核通过 Brief，并创建项目
python scripts\content_route.py approve --run RUN-20261030-XXXXXXXX `
    --reviewer "Founder" --note "值得做" --confirm --project langgraph-reliable-agent
```

- `--mode` 是必填的。不指定会被 `ROUTE_SELECTION_REQUIRED` 拒绝；路由器绝不推断
  路线，运行恢复时也绝不改变路线。
- `start --mode hotspot` 会写下计划、采集、过滤、排序，停在 `CANDIDATES_READY`。
  它**不**创建项目，也**不**调用任何媒体生成接口。
- `select` 是人做的那一步。`--by` 必填，不存在匿名选择。
- `approve --confirm` 是 Brief 进入流水线前人做的那一步。`--project <slug>` 用
  `scripts/new_project.py` 创建项目，并把 `00_brief/brief.json` 放进去，
  于是这一集从和其他每一集相同的地方开始。
- 偏离定位的主题会停在 `OUT_OF_PROFILE_REVIEW_REQUIRED`。所有者要么改主题，
  要么用 `--accept-off-profile --note "为什么"` 重跑。
- 候选池是 SQLite，位于 `.local/content-router/`（已被 gitignore）。
  `CONTENTOPS_ROUTER_HOME` 可以搬走它。
- 任何命令加 `--json` 都会输出同样的 JSON 结果。

Brief 生成之后，这一集继续走普通流水线。复制评审
（`scripts\copy_review.py <project>`）仍然是渲染之前的门禁。

合约与状态见 [CONTENT-ROUTER.zh-CN.md](CONTENT-ROUTER.zh-CN.md)。

### 19.1 验收运行

`scripts/router_e2e.py` 把两条路线端到端跑一遍，并写出一份回执。

```powershell
# 两条路线都走，针对真实来源
python scripts\router_e2e.py --actor "Founder"

# 只走指定主题路线；热点那条腿报为阻塞，而不是拿 fixture 冒充
python scripts\router_e2e.py --actor "Founder" --offline
```

- 它把项目建在 `.verify-tmp\router-e2e\projects\`，而不是仓库自己的
  `projects\`，所以一次验收运行不会留下任何成片项目。
- **选题与 Brief 审核都由验收运行代为完成**，用的是 `--actor` 给的名字。
  回执里原样写明这一点。这是验收运行，不是长期授权：渲染之前的门禁仍然是
  复制评审。
- 它不发布任何内容，也不生成任何媒体。
- 某个来源不可达时，回执会指名这次失败，运行跳过它继续。`--offline` 完全
  跳过网络，并把热点那条腿报为 `OFFLINE_BY_REQUEST`，而不是拿 fixture 填上。
- 验收脚本以 `actor_kind="automation"` 与 `allow_automation=True` 批准。生产调用方
  不可能误打误撞做到这一点：同样的调用不带该显式选项会以
  `AUTOMATION_APPROVAL_REFUSED` 被拒绝。

### 19.2 校验一次审批，并把 Brief 交接出去

```powershell
# 审批是否仍然匹配磁盘上的 Brief
python scripts\content_route.py verify --run RUN-20261030-XXXXXXXX

# 交接进流水线（写出 00_brief\handoff.json），或者只检查
python scripts\brief_handoff.py projects\my-episode --dry-run
python scripts\brief_handoff.py projects\my-episode
```

Brief 在审批之后被改动时，`verify` 返回 `APPROVAL_STALE`。
`brief_handoff.py` 同样拒绝，并且对 `DEGRADED` 的证据预测额外以
`EVIDENCE_REQUIRED` 拒绝。退出码 4 表示"尚未就绪"。

下一步是脚本阶段：把 Brief 变成文案、主张与分镜——并停在复制评审：

```powershell
python scripts\brief_script.py projects\my-episode
python scripts\brief_script.py projects\my-episode --check
```

它写出 `script/lines.json`、`script/claim-map.json`、`script/storyboard.json`、
`script/master.md` 与 `00_brief/script-report.json`。证据预测为 `DEGRADED` 时以
`EVIDENCE_REQUIRED`（退出码 4）拒绝，而不是写一份没人能背书的稿子。
草稿成功后复制门禁读到 `NOT_REVIEWED`：

```powershell
python scripts\copy_review.py projects\my-episode
python scripts\audio_first_plan.py projects\my-episode
# {"status": "BLOCKED", "stage": "copy_review", ...}（退出码 4，未合成任何内容）
```

批准复制是人的步骤：`copy_review.py ... --approve --reviewer <name> --opinion "<你决定的>"`。
路由器里的任何东西都不会写它。

### 19.3 使用真实的 TrendRadar 数据库

TrendRadar 运行在本仓库之外（`D:\Software\sansan0\TrendRadar\v6.11.0`）。
把路由器指向它要读的那一天：

```powershell
$env:TRENDRADAR_DB_PATH = "D:\Software\sansan0\TrendRadar\v6.11.0\output\news\2026-10-30.db"
python scripts\content_route.py start --account x-superplay-1024 --mode hotspot
```

也可以直接给目录——会使用最新的 `news\*.db`。文件以只读方式打开，绝不写入。
超过 24 小时的数据库会被报为 `stale`，其行以 `STALE_SOURCE` 被拒，
不会作为新热点进入候选池。

### 19.4 七天观察

```powershell
# 每天每账号一行，写在 .local\content-router\observation\ 下
python scripts\router_observe.py --trendradar-db "D:\Software\sansan0\TrendRadar\v6.11.0\output\news\2026-10-30.db"

# 目前窗口内的汇总
python scripts\router_observe.py --report --days 7
```

每天跑一次、连续七天。报告按来源打印：应答了多少次、给了多少行、多少次数据陈旧、
账号过滤产出了多少候选。这些才是保留或移除某个来源的依据，而不是某一天的好坏。

### 19.5 安全回滚

路由器的成果是 `feat/content-router` 上的三个提交。什么都没推送，所以下面每一步
都只在本地、都可逆。它们都不是默认动作：按你真正做出的决定，只跑对应的那一条。

```powershell
# 1. 先看。这一步不改变任何东西。
git status
git log --oneline -3

# 2. 留在原地、回到 main。分支仍然存在。
git switch main

# 3. 停用运行状态，但不删除。
Rename-Item .local\content-router .local\content-router.parked

# 4. 确认之后才删除分支，且只在本地。
#    -d 在分支未合并时会拒绝；这个拒绝本身就是信息。
git branch -d feat/content-router
```

不要做的事，以及原因：

- **不要 `git reset --hard`、不要 `git checkout --`。** 工作区里有别人未提交的
  工作（公众号/vendor 那条线），硬重置会丢掉它，且无法撤销。
- **不要 `rm -rf` 仓库目录。** `vendor/` 和 `.runtime/easel/` 无法从本仓库重新生成，
  删掉它们会把一次干净回滚变成一次重建。
- **不要直接删除 `.local/`。** 它是被忽略的运行状态，删掉是安全的，但改名能保留
  回执与候选池，万一改主意还在。
- **TrendRadar 不是服务。** 本机没有守护进程、没有端口、没有定时任务；"停止"就是
  不再运行它。它的目录留在原地对仓库没有任何影响。
