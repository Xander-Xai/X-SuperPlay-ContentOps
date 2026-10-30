# Repository Audit Report

> Audited: 2026-10-03
> Auditor: Claude Code (Principal Software Architect)
> Branch: `refactor/contentops-easel-minimax-plan` (from `feat/v1-video-pipeline@8b5fce7`)
> Related Issue: #2

## Git State (verified)

| Branch | HEAD | Role |
|---|---|---|
| `main` | `4a42791` | Canonical history |
| `feat/v1-video-pipeline` | `8b5fce7` | FROZEN_BASELINE |
| `codex/photo-avatar-api-clarification` | `d25543c` | SUPERSEDED |
| `refactor/contentops-easel-minimax-plan` | `8b5fce7` | ACTIVE development |

Ancestry: `feat/v1-video-pipeline` strictly contains `codex/photo-avatar-api-clarification`.
PR #1 closed without merge (superseded by PR #8).

## Easel Runtime (verified)

| Aspect | Value |
|---|---|
| Version | v0.2.1 |
| Commit | `3fe2d9904c1619281ef57f81d9ee0b7854998399` |
| Path | `.runtime/easel/` |
| Acquisition | GitHub Release tarball via `gh api` |
| Verification | 982/982 blob SHA-1 matched upstream tree |
| Re-verified | 2026-10-03 via `scripts/verify_easel_runtime.py` |
| Legacy clone | `Easel/` at commit `4b9c03c` — gitignored, NOT production |

## Code Reality

| Component | What it does | Status |
|---|---|---|
| `run_v1.py` | Two engines: `easel` (production) + `fallback` (diagnostic) | Working |
| `assemble_easel.py` | Upstream Easel orchestration with Windows subtitle workaround | Working |
| `qc_video.py` | Technical + evidence-first QC gate | Working |
| `resolve_easel.py` | Single resolver for pinned runtime | Working |
| `verify_easel_runtime.py` | Content hash verification against upstream tree | Working |
| `doctor.py` | Environment checker | Working |
| `test_basic.py` | 9 tests | All PASS |

## Production Voice

- Production engine uses **edge-tts** via Easel's `tts.py` (zh-CN-YunxiNeural)
- Fallback uses Windows SAPI → espeak → silence
- Build receipt correctly marks `voice_quality: edge_tts_fallback`
- `production_ready: false` — awaiting human review and MiniMax voice upgrade

## Contradictions Found (15)

| # | Fact | Contradiction | Runtime Truth | Resolution |
|---|---|---|---|---|
| 1 | Easel version | 0.1.1 in experiment docs | v0.2.1 | Archive docs, mark superseded |
| 2 | Easel version | 0.1.1 in scorecard | v0.2.1 | Archive, update metadata |
| 3 | Easel version | 0.1.1 in 02-Runtime README | v0.2.1 | Archive doc |
| 4 | Easel path | `runtime/Easel/` in 02-Runtime | `.runtime/easel/` | Fix in canonical docs |
| 5 | Voice engine | "SAPI" in README | edge-tts (production) | Rewrite README |
| 6 | Voice engine | "SAPI" in Runbook | edge-tts (production) | Rewrite Runbook |
| 7 | Experiment status | "Queued" in experiment | Work completed | Archive, mark COMPLETED |
| 8 | Project output | `fallback.mp4` in project.yaml | `easel.mp4` is latest | Reconcile in M1 |
| 9 | Voice quality | `windows_sapi` in project.yaml | `edge_tts_fallback` | Reconcile in M1 |
| 10 | Fork policy | "❌ Fork / 改造 Easel" | New: Extension Policy | Update AGENTS.md |
| 11 | MiniMax billing | "PAYG" in provider doc | Subscription only | Doc stays local-only |
| 12 | Governance docs | 6 files in 00-Governance/ | Directory doesn't exist | Remove all references |
| 13 | Docs links | 4 docs files referenced | Files don't exist | Remove references |
| 14 | Easel acquisition | "git clone" in deployment doc | Release archive | Archive doc |
| 15 | Web workbench | "localhost:7860" as daily entry | 6 doctor FAILs | Mark unverified |

## Broken Links (10)

All files referenced in README.md that do not exist:

1. `00-Governance/PRINCIPLES.md`
2. `00-Governance/PRE-CODE-GATE.md`
3. `00-Governance/PROJECT-STATES.md`
4. `00-Governance/MEASUREMENT.md`
5. `00-Governance/douyin-1024-STRATEGY.md`
6. `00-Governance/decisions/ADR-WS008-Presenter-Layer.md`
7. `docs/OPEN-SOURCE-VERSION-HEURISTICS.md`
8. `docs/PRESENTER-LAYER-SPEC.md`
9. `docs/PRESENTER-PROVIDER-ROUTING.md`
10. `docs/DIGITAL-HUMAN-PROVIDER-ANALYSIS.md`

## Security State

| Item | Status |
|---|---|
| `.env` | Gitignored ✓ |
| `.verify-tmp/` | Gitignored ✓ (added in 8b5fce7) |
| `docs/ai-provider-selection.md` | Gitignored ✓ (added in 8b5fce7) |
| `runtime-config-backups/` | Gitignored ✓ |
| `Easel/` clone | Gitignored ✓ |
| Provider endpoint in receipts | Redacted ✓ (8b5fce7) |
| API keys in tracked files | None found ✓ |

## Golden Sample

`projects/easel-review/` contains:
- 15 real screenshots
- Master script (6 shots, evidence-first)
- Storyboard (6 shots, all `real_screenshot`, 0 generated)
- Build receipts (easel + fallback)
- QC reports (easel + fallback)
- Runtime receipt (acquisition + verification log)
- Final videos: easel.mp4, fallback.mp4 (gitignored)

## What Does NOT Exist

- MiniMax integration code
- `config/` directory
- `src/` directory
- `tests/` directory (tests in `scripts/test_basic.py`)
- Human Review receipt
- `00-Governance/` directory

---

# 视频复刻与生产稳定性审查 — 2026-10-29

> 本节是对上方 2026-10-03 历史审查的独立增补；上方的“当前状态”只代表当时，不得用于判断今天是否能出片。审查分支：`feat/34-video-replication`，基线 `d068083`。已有两处未提交的研究文件改动属于用户工作，未覆盖、未整理。

## 结论和证据边界

**当前不能承诺“稳定、高质量地复刻对标视频并发布”。** 已有证据片、动效片、MiniMax 旁白、字幕、质检和人审包，但没有“对标原视频 → 实测镜头/节奏拆解 → 账号原创选题/脚本 → 权利与证据绑定 → 一条可重建的成片”的通用入口。现有对标研究没有取得原片 MP4，不能验证其真实转场、字幕、镜头时长和音频。所有现存账号项目都没有 `receipts/script-review.json`；人审不能由测试或本报告代签。

本次核对：仓库规则、当前配置、生产脚本、测试、五个本机成片的历史收据/路径、GitHub 候选项目和 `doctor.py`。没有读取密钥、`.env`、浏览器配置或私有声音样本；没有访问收费模型、克隆对标素材、重渲影片、发布到平台或播放全片。本机媒体的历史 SHA/收据不等于本次视觉验收，绿灯单元测试也不等于干净机器连续三次 E2E。

### 此轮已实现的防线

| 故障 | 改动和验证 |
|---|---|
| CI 步骤把两条命令粘成了非法 YAML | 拆开 [.github/workflows/ci.yml](../.github/workflows/ci.yml)，新增 [test_run_tests.py](../tests/test_run_tests.py) 回归；原测试对该错误误报通过。 |
| 5.927 秒口播字幕只显示 3.900 秒 | [build_code_animation_sample.py](../scripts/build_code_animation_sample.py) 改为覆盖完整实测口播时长；[test_code_animation_composition.py](../tests/test_code_animation_composition.py) 复现了 4.458–8.358 与正确 4.458–10.385 的差异。旧 MP4 不会自动重烧。 |
| 证据片入口能未经审稿调用 TTS | [build_evidence_cut.py](../scripts/build_evidence_cut.py) 和 [audio_first_plan.py](../scripts/audio_first_plan.py) 在读取输入/合成前调用同一 `copy_review`；[build_evidence_package.py](../scripts/build_evidence_package.py) 把阻塞变成可读状态。审批指纹还包含 `script/lines.json`、`script/claim-map.json`，改词即 STALE。 |
| 动效片 QC FAIL 仍返回 OK，并可能读旧收据 | [build_motion_film.py](../scripts/build_motion_film.py) 从本次 QC 子进程输出取结果，失败/无效输出返回非零并留下失败收据；明确把本次渲染的 storyboard 传给 [qc_video.py](../scripts/qc_video.py)，避免用旧的 `script/storyboard.json` 把 14 个动效镜头错算为 8 个“真实证据”镜头。 |
| `--variant eras` 默认为 `easel` 输出名，曾覆盖基线 | [build_code_animation_sample.py](../scripts/build_code_animation_sample.py) 默认输出名跟随变体；显式冲突在渲染前拒绝。回归测试和 CLI 拒绝测试已执行。 |

这些是**阻断错误成功**的增量，不代表原始 1024 视频已重渲或通过人眼质检。此轮代码没有写入用户已有的两个研究改动，也没有改 `.runtime/easel/`。

### 复刻入口（本轮新增，2026-10-30 补记）

第 2 条 P0“复刻入口缺失”的代码侧已补齐，**素材侧仍然缺失**：仓库现在有可执行的观察→计划→对账契约，但本机没有取得原片，因此没有任何真实复刻计划被生成。

| 组件 | 作用 |
|---|---|
| [replication.py](../src/contentops/workflow/replication.py) | `contentops.reference-observation/v1` → `contentops.replication-plan/v1` → `contentops.replication-check/v1`。观察记录必须绑定项目内文件的 SHA-256 且该文件可被 ffprobe 解码；`TRANSCRIPT_ONLY` 观察**不允许**带任何 `start_s/end_s`，切点只能来自 `FRAME_VIEWED`。计划按账号 DNA 的 7 拍模板从参考片各拍实测秒数加权，预算被夹进账号时长窗口，并写入 `reuse_reference_media: false`。 |
| [replicate_reference.py](../scripts/replicate_reference.py) | `--observe` / `--frames` / `--plan` / `--check`。无 DNA 的 `script` 技能路由返回 2；无观察或计划返回 4；契约失败返回 1。收据 `receipts/replication.json` 带 `skill_route`、计划 SHA、参考片 SHA 与 `render_present`，状态 `DERIVED` 并注明“派生预算不是审批”。 |
| [qc_video.py](../scripts/qc_video.py) | 项目只要写了 `script/replication-plan.json`，质检即逐条执行复刻契约：不得引用 `reference/` 下任何素材、时长在预算内、3 秒钩子、静帧上限、每镜声明 `function` 与 `dna_role`、节奏顺序、画面占比与 DNA 差值 ≤ ±8pp。没有计划的项目不受影响。 |
| [cut_qc.py](../src/contentops/media/cut_qc.py) | 修复第 9 条：真实/生成素材时长改按**实际 shot 区间**计时，placement 内部换成生成画面不会再被记成录屏。 |
| [run_v1.py](../scripts/run_v1.py) + [build_evidence_package.py](../scripts/build_evidence_package.py) | `replication.stage_gate()`：写了计划的项目在**渲染前**就会被拦下，未写计划的普通集行为不变。此前契约只约束“碰巧调用 qc_video 的构建器”，证据片与 `run_v1` 路径可以绕过。 |

验证：`tests/test_reference_replication.py` 35 项全部通过（缺文件、字节被改、字幕冒充切点、时间重叠、无共拍、预算夹取、引用参考素材、占比漂移、未声明角色、钩子过长、静帧过长、无帧可比的泄漏检查不算通过，以及近纯色帧只报告不通过，qc_video 接线、无计划普通集不被误判，以及两条生产路径确实调用了 producer gate）；`tests/test_evidence_cut_qc.py` 13 项（含 shot 级归因、账号策略不可被单集改写、证据角色必须落在实拍来源）。截至第三轮增至 37 项与 16 项。未做的部分：真实原片观察、真实复刻计划、成片人审——这三项不能由测试代签。

### 复刻契约的四条自证漏洞（本轮发现并修复）

对契约做了对抗式复核：这四条都能让一份文档替一部不存在的影片背书。四条同源——**下一关读的是上一关的断言，而不是影片**。

| 漏洞 | 旧行为（实测可复现） | 修复 |
|---|---|---|
| 手打镜头表 | 只要写 `mode: FRAME_VIEWED` 加几个秒数，`--plan` 就派生预算；切片清单可完全凭空生成 | 每个 `FRAME_VIEWED` 镜头必须携带从原片切出的帧：`--frames` 写 `reference/frames/NNN.gray`（32×32，最近邻，字节稳定）与可查看的 `NNN.png`，并记录 `frame_sha256`；`probe_reference` 按 `frame_at_s` 重新切帧逐字节比对，不一致即 `FRAME_NOT_FROM_REFERENCE` |
| 预算来自故事板算术 | `check()` 累加 storyboard 的 `duration`，47.2 秒的计划可以为 2 秒成片发 PASS | `check()` 用 ffprobe 实测 `final/easel.mp4` 并以此计时；没有成片就是 `render_present` FAIL，`--check` 不再能只凭计划退出 0 |
| 计划自带阈值 | 只改 `script/replication-plan.json`（`target_s`、`max_hook_s`、`max_static_hold_s`、占比、`beats`）就能让原本 4 项失败的成片变成 PASS，`plan_matches_observation` 仍然报“一致” | 新增 `plan_matches_derivation`：用已核验的观察与账号 DNA 重新派生，要求与磁盘上的计划完全相等 |
| 账号策略是单集开关 | `cut_qc` 从 cut plan 的 `target` 读 `evidence_mode` / `manual_recording` / `composition`：改成 `EXPLANATORY` 让 50% 真实的片不再失败，`ALLOWED` 取消禁录检查，删掉 `composition` 直接跳过占比关 | `cut_qc` 从 `project.yaml` 的 `account_slug` 解析 DNA：账号的值执行、单集声明不一致即 `account_policy` FAIL；新增 `account_composition` 用 asset `kind` → DNA 角色别名按最终时长实测 |

代价是真实的：`cut_qc` 现在按 1024 自己的 DNA 评判旗舰证据片——73% 录屏 / 27% 对比卡，而 DNA 预算是 70/25/5，于是 `account_composition` FAIL，`build_evidence_package` 返回 FAIL。片没变，是关卡不再跳过它计划里从未声明的那个问题（见下方 P1 第 4 条）。

### 第二轮对抗复核：门禁还信标签（本轮发现并修复）

修完四条自证漏洞后再复核一次，发现门禁学会了量**长度**，但仍然相信故事板/资产图对自己写的每一个**标签**。十条全部改为失败即拦，每条都有回归用例。

| 漏洞 | 旧行为 | 修复 |
|---|---|---|
| 只量了长度 | 一张静帧拉满 47 秒能过静帧关；镜头不写 `duration` 读成 `0.00 s` 钩子仍 PASS | `static_hold_within_limit` 用 `measure_video` 实测最长冻结段（量不出即 FAIL）；`hook_within_limit` 要求 `0 < hook <= limit` |
| 证据角色是自由标签 | `dna_role=screen_recording_evidence` + `source_type=generated` 仍算 70% 录屏 | `dna_role_matches_source`（复刻契约）与 `role_matches_source`（`cut_qc` 资产图）要求证据角色落在实拍来源 |
| 参考片复用只是路径子串 | 复制参考片帧、改掉路径即可通过 | `reference_frames_not_in_cut` 以 2 fps 抽 32×32 灰度逐字节比对；`claims_do_not_cite_the_reference` 禁止用参考片摘要做事实证据 |
| 观察可以写另一个账号 | 为未来智能写的观察派生的计划拿 1024 DNA 评判 | `--plan`/`--check` 拒绝不一致；`qc_video` 从 `project.yaml` 取账号并输出 `replication_plan_account` |
| `--target-seconds` 离开账号窗口 | 给只发 45–60 秒的账号排 20/90 秒 | 只在 DNA `target_duration_s` 内选点 |
| 纯音频冒充影片 | 摘要匹配的音频“证明”了一份镜头表 | `REFERENCE_NOT_A_FILM`；缺 ffmpeg/ffprobe 为 `REFERENCE_UNVERIFIED`，不再静默通过 |
| 对账收据抹掉派生记录 | `--check` 用一句 PASS 覆盖计划摘要/参考片摘要/技能路由 | 派生字段跨多次对账保留 |
| 未要求权利决定 | 没有任何地方记录参考片可用来做什么 | `rights.cleared_by/decided_at/scope` 必填（`RIGHTS_MISSING`/`RIGHTS_SCOPE`） |
| `qc_video` 真实占比只是 WARN | 证据型账号可放过低于下限的片，生成画面无上限 | `EVIDENCE_LED` 账号低于下限即 FAIL，新增 `generated_ratio`（≤10%） |
| 人审不覆盖门禁字段 | 审批后改 `function`/`dna_role` 人审仍有效 | 两者纳入 `COPY_FIELDS`，改标签即 STALE |
| “没有复用”可以不看就打印 | 没存帧或存下的帧全是近纯色时，泄漏检查返回空列表并打印“干净” | 区分 `compared`/`flat`/`none`：只有真正比对过才 PASS；近纯色帧 WARN（“已报告、未测量”）；一帧未存为 FAIL |


### 第三轮对抗复核：门禁会不会误杀诚实的片（本轮发现并修复）

前两轮补的是“不诚实的片能通过”。这一轮反过来问：**有没有干净的片被拒**。同一次扫描提出八条，逐条先复现再采信——六条属实并已修复，两条被实验否掉，没有为了迁就它们放松阈值。

| 误判 | 旧行为（已复现） | 修复 |
|---|---|---|
| 没量过的占比读成 0% | 全是 `vector_animation` 的故事板既非实拍也非生成，`real_source_ratio` 打出 `0.0`，一部没被量过的片被报成“0% 真实” | 输出 `value: null`、说明“未测量”；对 EVIDENCE_LED 账号仍须 FAIL，不能让未测量成为通过证明 |
| 生成上限写死 10% | 1024 DNA 的 25% 矢量 + 5% 对比卡经别名表已被映射进生成预算，符合自己 DNA 的片被另一个常数拒掉 | 上限取账号非证据份额（1024 为 30%），无 DNA 才用 10%；`qc_video` 与 `cut_qc` 同步 |
| 单集不能比账号更严 | 账号值无条件覆盖单集值：一部自声明禁录却用了录屏的片，被当成允许录屏评 | 录屏策略按严格度排序；证据模式的逐句门槛与整片占比不可互相替代，不允许单集改写账号模式 |
| 单个未列名画面判死 | 4% 标题卡单独报“没有 DNA 预算”，尽管在 ±8pp 容差内 | 未列名角色合成一个残差，只有残差整体超容差才漂移 |
| 0 字节 SRT 打败真字幕 | 空文件“存在”被选中，烧了字幕的片被报成没字幕 | 无 `-->` 行的文件视为占位符；优先第一条有 cue 的候选，全无 cue 时仍点名占位符 |
| 缺字幕时 `qc_video` 崩溃 | 对 `None` 调 `.exists()`，整份报告在第一个占比之前中断 | 缺字幕是 WARN 行，报告跑完 |
| 四道门禁各拼一种“实拍” | 诚实的 `screen_recording` 在一处算证据、另一处不算、第三处丢占比 | 统一 `CAPTURE_SPELLINGS`（claim/cut/QC 共用），手绘 `diagram` 纳入真实产物 |
| 权利范围六种合法答案只认四种 | `licensed`、`permission_granted` 被判 `RIGHTS_SCOPE` | 两种都接受，比较前规范化 |

被**否掉**的两条（实验记录在 `D:\Temp\AI-Agents\claude\replication-e2e-2026-10-30\`，未入仓）：两张共用背景的 6 秒卡量出 5.8 秒静帧而非 12 秒，且所引真实作品自己声明的镜头本就超过 10 秒；两张无关画面的 32×32 缩略图平均绝对差 31.1/255，并不撞字节。门禁经受住这两个实验，没有为它们调整阈值。

写回归时又暴露一处：`--check` 从磁盘旧收据**继承** `plan_sha256`/`target_s`/`beats`/`reference_video_sha256`（无旧收据则一个都不写），PASS 可能指向一份已变过的计划；`--frames` 会覆盖派生收据。现在帧有自己的收据，`--check` 绑定它实际评过的计划与成片，两条都有回归。

### 质检读错文档：四个真缺陷（本轮发现并修复）

在把复刻契约接到 `qc_video` 之后，用它重跑本机旗舰项目 `projects/easel-1024-proof`，发现质检与 `cut_qc` 对同一部片给出相反结论。四个缺陷同源：**质检读的文档不是生产实际写的那一份**。

| 缺陷 | 旧行为（实测） | 修复 |
|---|---|---|
| 分级故事板路径漏掉 `work/storyboard.json` | 只找 `work/<target>/storyboard.json` 与 `script/storyboard.json`；证据片两个都没有，于是 8 个镜头的片子被报成“没有 storyboard”，真实占比在 0 个镜头上计算 | 增加 `work/storyboard.json` 兜底；`script/` 仍优先（`test_qc_grades_the_storyboard_the_build_actually_rendered`） |
| 真实素材占比不看 cut plan | storyboard 只有 `video`+`duration`，`source_type` 缺失 → 报 0% 真实、来源全缺；同一部片 `cut_qc` 实测 72.7% 真实（32 s 录屏 / 12 s 卡片） | 有 `script/cut-plan.json` + `assets.json` 时以 cut plan 按时长计量，并列出未声明来源的资产；无 cut plan 时仍走旧路径（`test_qc_measures_provenance_from_the_cut_plan_when_there_is_one`） |
| 字幕烧录检测按片长固定比例取帧 | 5 条字幕在 44 s 片里覆盖不到 15%/30%/45%/60%/75%/90% 任一取帧点，实测最大亮像素比 0.00000 → 字幕明明烧了却报未烧 | 有 SRT 时取每条字幕的中点；无 SRT 才退回固定比例。同一部片实测 0.01417 → 通过（`test_subtitle_sampling_lands_on_cues_not_on_gaps`） |
| 证据存在性找 `sources/` 目录 | 证据片把录屏放在 `projects/easel-evidence-capture`，用 `repo://` 引用，本目录没有 `sources/` → 警告“无真实证据” | 有 cut plan 时以计划里**有来源的** recording 资产为准 |

修复后 `python scripts/qc_video.py projects/easel-1024-proof` 由 WARN 变为 PASS，且与 `cut_qc` 的 72.7% 一致。这不代表该片可以发布：人审仍为 `NOT_REVIEWED`、`distribution_blocked=true`，本次只修了“门禁读错文档”。

**仍需承认的边界：** 节奏现在是实测的（时长与最长冻结段都来自 `final/easel.mp4`），参考片帧被逐字节比对，证据角色必须落在实拍来源上；但**没有任何一关证明成片每一拍就是 cut plan 点名的那个拍**——长度和运动量对得上、内容不对的片仍可能通过。密码学上绑定成片与计划仍缺（需要渲染时把输入指纹写进收据）。参考片泄漏检查只抓逐字节复制的帧，裁剪过或调过色的搬运抓不到，仍需人眼。这是下一步，不是已完成项。

## 2026-10-30 后续修复记录

- 动效合成前新增语音文本、时间线顺序与已审批字幕的比对；动效 review bundle 纳入时间线、主持人契约和已声明主持人素材的摘要。当前未完成真实合成验证，且旧人审结果没有通用的消费端新鲜度验证，不能声称旧审批自动失效。
- 主持人 ASR 最近一次检测未通过或跳过时，撤销此前的 `speech_text_verified`；这仍然不是人工听审。
- 动效 `--skip-render` 因外部引擎传递依赖无法完整证明，暂时一律重渲；组合器结果解析完整 JSON，并核对输出文件 SHA-256。该行为以可靠性优先，尚非经过验证的可复用缓存。
- 证据型账号来源占比无法测量时明确为未测量并 FAIL；`CLAIM_LED` 和 `EVIDENCE_LED` 的保障不同，不再把二者视为可互相替换的强弱等级。
- 原 locked-input 测试会改真实仓库索引和文件；现使用独立临时 Git 测试仓库。另一语音克隆测试仍会短暂改动真实索引，完整门禁需先隔离该用例，不能误称已完成验证。
- 对 `COST_AND_LIMITS` 的账号决策仍未作出：派生维持原模板语义，不以代码静默决定是否延后。
- **两个账号确实各有工作流，但此前没有任何按账号选路的入口。** 账号 DNA 里的 `skill_route` 只被 `check_account_dna.py` 校验能否解析到 skill，生产代码一处都没读；"1024 走证据链、未来智能走音频优先链"这件事只写在 RUNBOOK 的两节里，靠执行者记得。新增 [account_route.py](../scripts/account_route.py)：读 `project.yaml → account_slug → DNA`，按 `evidence.mode` 给出有序生产者链与创作类 skill 归属，未声明模式直接拒绝，不猜。两条链共用 `build_evidence_package` 与 `qc_video`，所以门禁是同一套、生产者不是。[test_account_route.py](../tests/test_account_route.py) 9/9 锁住这些事实（含"命令指向的脚本必须存在"）。它只说明该跑哪条链，**不认证结果**——成片是不是这个账号的，仍由 `cut_qc` 判。

## 未来智能工作流现状（2026-10-30 核查）

本轮是只读核查加一条门禁修正，没有重渲、没有 provider 调用、没有改动任何既有收据。

**有的东西：** 两个真实产物在本机存在——`projects/easel-fi-audio-first/final/easel.mp4`（25.0 秒，历史 `cut_qc` 为 PASS）与 `projects/easel-fi-what-is-agent/final/eras.mp4`（38.9 秒，历史 `qc_video` 为 WARN）。两者都短于账号 DNA 的 90–120 秒，`production_ready:false`，人审为 `PENDING_FOUNDER_REVIEW`。

**没有的东西：** 一条 90–120 秒、符合账号基因、通过全部门禁的整集；以及一份能让守卫式流水线重跑的脚本审批（两个项目都没有 `receipts/script-review.json`，`audio_first_plan`、`build_motion_film`、`build_evidence_package` 都会在 TTS/渲前阻断——这是设计如此，不是缺陷）。

**本轮实测（在项目副本上跑 `cut_qc`，未覆盖既有收据）：**

| 项目 | 结论 | 依据 |
|---|---|---|
| `easel-fi-audio-first` | FAIL | 仅 `account_duration` 一项：25.00 秒 vs 90–120 秒；其余全 PASS（`account_composition` 70/20/10） |
| `easel-fi-what-is-agent` | 无法评级 | 没有 `script/cut-plan.json`，`cut_qc` 无法评价；历史上只跑过 `qc_video`（WARN） |

这条 `account_duration` 是本轮新增的：此前 `audio_first_plan.py` 用刚测出的口播长度定义 `target.duration_ms_range`，成片自我作证，`duration` 检查永远不可能失败。

**仍然挡在未来智能前面的四件事：**

1. **脚本人工审批缺失（人做）。** 三个生产者都在审批前阻断；没有审批就不能消耗 TTS/渲染。
2. **固定运行时被改过（需批准）。** `verify_easel_runtime.py --json` 实测 981/982，不一致的正是 `skills/openclaw/video-script/SKILL.md`，额外文件是 `skills/openclaw/video-script/references/benchmark-playbook.md`。未来智能的脚本步骤路由到这个 skill，而 ADR-001 写的是“不修改上游源码”。该补丁内容不在仓库里——两份副本都位于被 gitignore 的目录（`.runtime/`、`Easel/`）。恢复或登记都属受保护目录决策。
3. **逐句事实溯源不是硬门（需设计）。** `claim_coverage` 在 EXPLANATORY 模式被关闭，`cut_qc` 只检查 claim id 是否存在，不核对 `source_document` 是否支撑那句工程断言。“DOCUMENTED”目前是标签，不是已验证的链路。
4. **生成素材上限对它是空门（需账号主人定数）。** 未来智能配比 100% 非实拍，因此由“非实拍份额”推导的 `generated_ratio` 上限等于 100%。一张 AI 插图填满整片仍会通过。

另外：ERAS 实验的 5.1 秒（13.11%）是插入 + 主持人合计，且主持人被记在 10% 插入上限之外；不能表述为“低于 10%”。`CURRENT-STATE.md` 里 45.0 秒那一段说的是基线片（本机文件已缺失，文档本身已如实记录），38.9 秒是 ERAS 变体——两者不矛盾，但引用时必须分清是哪一个。

**下一步的诚实顺序：** 先由人定题、备真实资料并批准脚本（无授权来源则改题），再做一条 90–120 秒整集；同题冻结输入连做 3 次只为证明可重复，不能替代 Issue #6 要求的三个来源三条片。


## 尚未关闭的问题（按发布风险排序）

1. **P0：生产运行时不可信。** `python scripts/doctor.py --json` 返回 FAIL：固定 Easel v0.2.1 目录有 `skills/openclaw/video-script/SKILL.md` 一处内容不一致、`skills/openclaw/video-script/references/benchmark-playbook.md` 一处额外文件；旧 `Easel/` 的 HEAD 又不是 pin。`verify_easel_runtime.py --json` 实测 981/982 个原版 blob 匹配。任何依赖固定上游的当前生产构建都应停下。不得自动覆盖该受保护目录或把未 pin 的 clone 当生产运行时；恢复须先核实这两处本地改动的归属，再通过仓库提供的正式获取/验证流程。
2. **P0：对标镜头源缺失（入口已补齐，素材未取得）。** [verification-round-2026-10-28.md](../research/video-replication/verification-round-2026-10-28.md) 明说未取得原片；研究文档只可做叙事参考。观察→计划→对账的可执行入口已在上面“复刻入口”一节实现并有测试，但它**拒绝**在没有可解码原片时给出任何切点，所以现在仍无法产出真实复刻。补齐需要：取得可授权研究的原片、由人逐段实看并记录镜头功能、再由人确认计划。不能拿 ASR 字幕推断镜头运动、转场或节奏，更不能照搬博主素材并假定有使用权。
3. **P0：人审和分发权限未完成。** 现有项目脚本审稿均为 `NOT_REVIEWED`；[easel-1024-proof 的 review bundle](../projects/easel-1024-proof/receipts/review-bundle.json) 中四份拍摄为 `internal_review`，缺去敏审核，`distribution_blocked=true`。新入口正确阻断，任何声称“可发布”的产物都不成立。
4. **P1：当前 1024 账号样片不符合自己的画面基因——现在会被拦下。** [1024 DNA](../config/accounts/x-superplay-1024.json) 现为按时长 70% 录屏证据 / 25% 矢量 / 5% 对比卡（旧 CURRENT-STATE 的 65/30/5 已过时）。[x-superplay-1024 样片收据](../projects/x-superplay-1024/receipts/sample.json) 声明纯代码动画和 AI 主持人，并把具体网关/端口事实标成 `claim_bearing:false`。本轮新增的 `cut_qc.account_composition` 已把“最终实际镜头按时长与 DNA 对账”变成硬门：`projects/easel-1024-proof` 实测 73/27/0，`account_composition` FAIL。剩余缺口是“每句事实有证据”的逐句硬门（`claim_coverage` 只在 CLAIM_LED 模式强制）与样片本身需要重做。
5. **P1：动效脚本的审批指纹仍不覆盖全部最终语义。** [copy_review.py](../src/contentops/workflow/copy_review.py) 本轮把 `function` 与 `dna_role` 纳入 `COPY_FIELDS`（改标签即 STALE），并已覆盖证据片 `lines/claim-map`；但动效实际读 `receipts/voice-lines.json`、`motion/timeline.json`、主持人契约，而这些可由上游生成或单独修改。必须在最终合成前校验它们与已批准的 master/SRT/分镜逐词和顺序一致，不能机械地把会被生产步骤重写的文件塞进审批指纹。
6. **P1：历史 QC 和旧视频不能复用为当期通过结论。** [x-superplay-1024 旧 QC](../projects/x-superplay-1024/receipts/qc-report-easel.json) 把动效片记作 8 个真实镜头，本轮修复不会改写旧收据。工程片旧 QC 使用已移除的静帧规则，长达 11.88 秒的冻结曾被判通过；基线影片也有缺失的本地输出。必须重渲、重跑并比对真实生成输入，而不是追认旧 PASS。
7. **P1：主持人的话没有核准。** [1024 presenter contract](../projects/x-superplay-1024/motion/presenter/contract.json) 关闭了语音验证；收据的 ASR 有词错且 `speech_text_verified:false`。另一个验证器在最新检查失败时可能保留旧的 true 状态，需做 true→failed 的回归与撤销逻辑，随后由本人听审。
8. **P2：复用与路径身份不牢靠。** `build_motion_film.py --skip-render` 仅按片长复用 clip，改动 spec 内容仍可能重用旧画面；动效 composer 的多行 JSON 被父进程逐行解析，现有 `motion-build.json` 的 `compose.result` 为 null。要按 spec+引擎+素材摘要建缓存键，并将完整成功回执与输出 SHA 绑定。
9. ~~**P2：素材比例检查有误归因。**~~ **已修复。** [cut_qc.py](../src/contentops/media/cut_qc.py) 现在按 placement 内实际 shot 区间计时，placement 内部换成生成画面不再被记成录屏；[test_evidence_cut_qc.py](../tests/test_evidence_cut_qc.py) 的 2b 用例复现了旧归因。
10. **P2：文档与可重建性漂移。** [CURRENT-STATE.md](CURRENT-STATE.md) 的部分比例/旧状态与今天的 JSON/媒体不一致；当前 motion 样片的 WAV/SRT、外部 Huashu engine 和 AI 主持人媒体未纳入独立可复建输入契约。`scripts/run_tests.py` 允许无运行时/无本机素材的测试跳过，因此 suite 绿色只是离线逻辑验证。
11. **P1：1024 账号 DNA 自相矛盾，需要 Founder 决定。** [1024 DNA](../config/accounts/x-superplay-1024.json) 的 `narrative.template` 包含 `COST_AND_LIMITS`，同一文件的 `narrative.template_coverage.deferred` 又把该拍声明为“延后到下一集”。`derive_plan` 跟随 `template`，所以计划会要求这一拍；证据片也确实拍了成本镜头。两种解释都说得通，但只能由账号主人选一个——代码不应替账号改政策，因此本轮只把矛盾明确记录，没有静默改派生逻辑。


## 对标复刻应有的单一流程

**输入：**有权研究的对标视频原片或可核实的原始链接、许可/取用范围，以及本账号要讲的真实业务选题和证据。缺原片时只能产出“待核验”的叙事假设，不能填镜头秒数。以下每一关应记录 input SHA、技能路由、输出 SHA、审核人和状态：

1. **观察参考**：标注开头承诺、每镜起止、镜头功能、字幕/BGM/转场和观看节奏；把“逐帧实看”与“字幕/二手分析推测”分开。只抽象镜头功能，不搬运对方台词、脸、配乐、图像或事实。
2. **原创转译**：读取 [账号 DNA](../config/accounts/)，1024 的结论先行/成本与边界/真实录屏优先，未来智能的工程讲解/禁手工录屏。每条 episode 有自己的主题、目标受众、可验证主张与独立视觉 direction；不要把 Easel 样片的 U01/U05 顺序当所有话题的通用模板。脚本依 `video-script`，账号表达依 `x-superplay-copy-orchestrator`；其适配后的部分仅有契约而无可调用脚本，不宣称自动执行。
3. **证据与版权**：使用现有 `x-superplay-source-research` 的 candidate → rights ledger → 人工授权链；[capture_plan.py](../src/contentops/workflow/capture_plan.py) 只写录屏任务，不等于素材已录到。先备真实证据，再决定设计卡与动效，绝不让生成画面承担事实证明。
4. **制作**：人工核准 copy SHA 后，根据实际语音时长写 cut plan；录屏证据走现有 evidence builder，抽象机制动效走受控 motion/HyperFrames/Huashu 子层。封面遵循 `card-design`，字幕烧录及合成由既有 `assemble_easel` 负责；不能把 `slideshow-video` 的图片缓动或旧 Easel 通用云 TTS 降级当作“高质量复刻”。
5. **验收**：最终片绑定当次 storyboard、SRT、语音、来源、画面占比、输出 SHA 和 QC 收据；逐帧/全片检查节奏、真实性、隐私、字幕同步与语音自然度；人审通过后才允许标记可分发。本轮未完成这条端到端演练，不能宣称已经打通。

### GitHub 可用方案与不引入的理由

| 缺口 | 官方开源项目 | 决策 |
|---|---|---|
| 有权参考片的候选切点 | [PySceneDetect](https://github.com/Breakthrough/PySceneDetect), BSD-3-Clause，[v0.7.2](https://github.com/Breakthrough/PySceneDetect/releases/tag/v0.7.2)，提供 Windows 构建及多种 cut detector | **可选研究试验**：只有取得原片后才在独立空目录测试切点召回/误报，再由人标注镜头功能；不能凭切点声称懂风格。暂不克隆/加依赖。 |
| 对标片缺转录时 | [whisper.cpp](https://github.com/ggml-org/whisper.cpp), MIT，[v1.9.5](https://github.com/ggml-org/whisper.cpp/releases/tag/v1.9.5)，Windows 本地推理/SRT | **条件试验**：已有字幕优先；确有反复转录需求再测试中文准确度、模型许可与 SHA，采用 Windows 安全子进程封装。 |
| 多人逐词对齐 | [WhisperX](https://github.com/m-bain/whisperX), BSD-2-Clause | 当前不引入，PyTorch/对齐模型/可选需授权 diarization 令牌的复杂度超过已证实需求。 |

这些项目只解决具体能力，不是“下载一个仓库就能自动达到账号基因”。不克隆另一个剪辑平台/合成器，不导入归档 `dy_x1024` 的旧 QC 脚本；后者使用另一套项目布局、审批和静态阈值，会与现有门禁冲突。

## 核验记录与交付状态

- 改动前：`python scripts/dev_check.py` 返回 0，60/60 suites；**并未发现**失效的生产运行时和非法 CI 结构。说明该 gate 不是运行时/线上 CI/视觉 E2E 的代替品。
- 复刻入口落地后（2026-10-30）：`python scripts/dev_check.py` 返回 0，**61/61 suites 通过**；`python scripts/run_tests.py --missing-from .github/workflows/ci.yml` 确认 61 个 suite 都有 CI 调用。两项新回归先复现旧行为再修复：`test_evidence_cut_qc.py` 的 shot 级归因、`test_reference_replication.py` 的 qc_video 接线。
- 同一 gate 经 Git Bash 的包装 shell 运行时 `test_windows_subprocess.py` 会以 `OSError(9)` 失败（句柄继承差异），在 PowerShell 下 49/49 通过。这是执行环境差异，不是仓库缺陷；判定以 PowerShell/CI 为准，但并不因此删掉该用例。
- 两轮契约加固后（2026-10-30）：`python scripts/dev_check.py` 返回 0，**61/61 suites**；`tests/test_reference_replication.py` 35/35、`tests/test_evidence_cut_qc.py` 13/13。`python scripts/qc_video.py projects/easel-1024-proof` 仍 PASS（零非 PASS 行）；`cut_qc` 对同一部片因 `account_composition` 返回 FAIL（73/27/0 对 70/25/5），这是本轮**新暴露**的真实漂移，不是回归。`role_matches_source`、`generated_ratio` 在旗舰上均 PASS。
- 第三轮（误杀修复）后（2026-10-30）：`python scripts/dev_check.py` 返回 0，**61/61 suites**；`tests/test_reference_replication.py` 37/37、`tests/test_evidence_cut_qc.py` 16/16、`tests/test_code_animation_composition.py` 27/27。新增回归先复现旧行为再修：13（更严单集）、14（未列名残差）、15（账号生成上限）、缺字幕时 `qc_video` 崩溃、0 字节 SRT。旗舰 `qc_video` 仍 PASS、`cut_qc` 仍因 `account_composition` FAIL——本轮没有改变这两个结论。
- 本轮 TDD：`python scripts/doctor.py --json` 返回 1；`python scripts/verify_easel_runtime.py --json` 返回 1；两账号 `check_account_dna.py` 通过；`copy_review.py` 对 1024 与未来智能返回 `NOT_REVIEWED`。真实证据包入口 `build_evidence_package.py projects/easel-1024-proof` 与 `audio_first_plan.py projects/easel-fi-audio-first` 都在审稿前返回阻断码 4，未进入 TTS。变体冲突 CLI 预期返回 2，且未写任何影片。`replicate_reference.py` 在无原片项目上 `--plan` 返回 4、`--check` 返回 1，未生成任何计划。
- 第四轮（未来智能核查，2026-10-30）：`python scripts/dev_check.py` 返回 0，**63/63 suites 通过**（`run_tests.py --missing-from ci.yml` 同样确认 63 个 suite 全部有 CI 调用）。逐套件：`test_evidence_cut_qc.py` 18/18（新增 13b）、`test_account_evidence_policy.py` 12/12、`test_locked_input_reproducibility.py` 10/10（历史字幕缺席时该场景按名 skip，套件不再谎报“All 10 passed”）、`test_minimax_voice_clone.py` 41/41。`verify_easel_runtime.py --json` 返回 1（981/982 + 1 extra），`doctor.py --json` 仍 FAIL。本轮没有重渲，也没有改动任何既有收据；两个未来智能项目的 QC 是在临时副本上跑的。
- 没有运行真实 provider 调用、全片重渲或人眼验收，发布状态仍 `production_ready:false`。

**完成判据尚未达到：**需要取得可授权研究的原片、确定复刻的具体主题和账号、新建与 #34 语音克隆区分开的任务范围、恢复固定运行时、补齐剩余 P1 门禁、按该账号 DNA 做一条从原片拆解到成片的无收费/明示收费试运行，再由 Founder 审稿和看完整视频。任何一项缺失都不是可以用自动化打勾替代的条件。
- 4 docs files referenced in README
