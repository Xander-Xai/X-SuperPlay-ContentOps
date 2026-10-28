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

## 4. 运行生产流水线

```powershell
python scripts\run_v1.py projects\my-video
```

## 5. QC

```powershell
python scripts\qc_video.py projects\my-video
```

## 6. 开发门控

```bash
python scripts/dev_check.py
```

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
