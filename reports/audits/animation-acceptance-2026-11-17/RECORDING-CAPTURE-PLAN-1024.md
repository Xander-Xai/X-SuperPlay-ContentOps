# X超玩·1024 真实录屏采集方案（生产前置条件）

> Archive provenance: generated 2026-11-17 as the concrete 1024 capture contract. Commands reference repo-relative scripts only; no credentials or local paths are embedded.


生成时间：2026-11-17（Asia/Shanghai）
账号：`x-superplay-1024`（X超玩·1024）
状态：**BLOCKED — `MISSING_REAL_RECORDING`**。本文件是采集**合同与操作说明**，不是录屏已发生的证据。仓库当前没有任何授权原始录屏；在下面的素材登记完成前，正式片不得生产、不得审核通过、不得发布。

## 1. 为什么必须 BLOCKED

- 账号 DNA `config/accounts/x-superplay-1024.json`：`evidence.mode=EVIDENCE_LED`、`manual_recording=ALLOWED_CROPPED`、`required_evidence_class=EXECUTED`。
- `visual.composition` 按时长加权要求 `screen_recording_evidence=70%` / `vector_animation=25%` / `comparison_card=5%`。
- `render.qc_checks` 含 `real_source_ratio_min_70` 与 `no_uncropped_desktop_in_frame`。
- 仓库门禁（`src/contentops/media/animation_backend.py::production_gate` 与 `src/contentops/media/recording_intake.py`）拒绝用 Remotion / Huashu 生成片段冒充录屏：`generated=true` 的素材 `evidence_capable=false`。
- 结论：缺少真实录屏时，动画只能跑 TEST_ONLY 诊断样本，动画时长**不能计入** 70% 录屏占比，正式片维持 `production_ready=false`。

## 2. 需要的真实画面（按 DNA 叙事位）

45–60 秒成片，按 30fps / 1080×1920。前 3 秒必须是明确问题 / 失败 / 反常识结果（`narrative.opening=CONFLICT`、`HOOK_3S_CONFLICT`）。DNA 覆盖的叙事位：`U05 → U01 → U06 → U08`（`COST_AND_LIMITS` 明确声明为 deferred，因为锁定的脚本没有成本数据，禁止编造）。

| 叙事位 | 需要录到的真实画面 | 时长权重目标 | 对应分镜角色 |
|---|---|---|---|
| U05 HOOK（0–3s） | 一次**真实的失败或反常识输出**：命令报错、测试失败、模型给出错误答案 | 录屏 ~3s | `screen_recording_evidence`（problem 帧） |
| U01 任务陈述 | 同一次捕获里带上下文的完整命令行 + 输入 | 录屏 ~6s | `screen_recording_evidence` |
| U06 实测过程 | **同一次录制**中命令→输出→校验的连续过程；先完整结果，后放大 | 录屏 ~20s | `screen_recording_evidence` + `evidence_zoom` 矢量放大 |
| U08 结果验证 / 失败边界 | 验证通过的真实回执/日志，或明确的局限与坑 | 录屏 ~10s | `screen_recording_evidence` |
| 对比卡 | 前后状态对比（可用真实截图裁切 + 矢量卡） | 5% 卡 | `comparison_card` |
| 解释 | 架构 / 数据流矢量动画（非证据） | 25% | `vector_animation` |

> 时长口径：`visual.composition` 是时长加权。70% 录屏 ≈ 31.5–42s（按 45–60s），25% 矢量 ≈ 11–15s，5% 对比 ≈ 2–3s。录屏段必须来自真实捕获；矢量段只做解释。

## 3. 采集命令与预期操作步骤

真实采集由**人工在本机完成**；以下给出可复现的操作步骤与核验命令。不得用伪造或生成的画面替代。

### 3.1 采集前准备
1. 关闭通知、输入法候选、无关窗口、浏览器标签栏与任何凭据页面（DNA `evidence.forbidden` 明令禁止整屏桌面 / 无关窗口 / 弹窗 / 通知 / 凭据 / 个人信息）。
2. 使用只覆盖终端 / 目标应用窗口的录屏工具；保持窗口最大化并在录制前清空滚动历史。
3. 一次捕获覆盖 U05→U08 的连续过程；**命令与结果必须来自同一次录制**（`evidence.rules`）。

### 3.2 需观察的结果（采集时逐项确认）
- U05：失败画面在镜头内真实可见，不是字幕补写。
- U06：命令执行与输出在同一录制里连续出现，可被逐帧定位。
- U08：结尾给出可核验的结果或明确的失败边界；局限与坑讲清楚（`qc_rules`）。
- 全程无鼠标指针、无输入过程（该条对 FI 账号是硬禁；1024 允许真实操作但必须裁掉杂乱桌面）。

### 3.3 采集后核验（真实命令）
```bash
# 1) 确认文件与基本信息
ffprobe -v error -show_entries format=duration:stream=codec_name,width,height,r_frame_rate -of default=noprint_wrappers=1 <recording.mp4>

# 2) dry-run 验证账号策略与裁切矩形是否合法（不落盘、不复制文件，仅写回执）
python scripts/ingest_recording.py --project <project> --file <recording.mp4> \
  --crop x,y,width,height --in-ms <start> --out-ms <end> \
  --claim <claim_id> --source-ref <url-or-repo-path> --notes "真实手动捕获" --dry-run

# 3) 正式 intake（复制进项目、写素材清单、登记 SHA-256 与权限）
python scripts/ingest_recording.py --project <project> --file <recording.mp4> \
  --crop x,y,width,height --in-ms <start> --out-ms <end> --claim <claim_id>
```

## 4. 裁切区域（crop）与脱敏

- DNA 裁切规则（`evidence.crop_rule`）：**只保留日志、报错、运行结果、模型输出区域**。
- `--crop x,y,width,height` 为 `ALLOWED_CROPPED` 账号必填（`scripts/ingest_recording.py` 帮助文本明确）。
- 裁切必须落在一个连续矩形内，覆盖终端/输出区，排除桌面、Dock、无关窗口、通知区、输入法候选。
- 若画面中出现密钥、Cookie、token、真实姓名或私有路径，必须重录或进一步裁切，不得提交（`AGENTS.md` 规则 4）。
- 裁切后的素材由 intake 复制进项目并登记 SHA-256；后续 claim 绑定该 SHA，禁止挂载 generated 素材。

## 5. 验收规则（通过条件）

采集素材只有在满足以下全部条件后，才允许把 1024 项目从 BLOCKED 推进到可进入人审：

1. `python scripts/ingest_recording.py` 非 dry-run 成功，素材清单含真实文件路径 + SHA-256 + crop + 权限备注。
2. `python scripts/recording_plan.py <project> --check` 通过：capture-plan.json 是 storyboard 的同级校验器，与账号策略矛盾会阻断 gate。
3. 时长加权满足 `real_source_ratio_min_70`；generated 素材不出现在任何 claim 区间（`no_generated_asset_in_claim_interval`）。
4. 抽帧确认 `no_uncropped_desktop_in_frame`：无整屏桌面、无凭据、无个人信息。
5. 重跑 M5：`python scripts/m5_production.py <project> --narration-provider <authorized> --json`，`has_real_recording=true`，Easel v0.3.0 合成，QC 目标尺寸 / H.264 / 音轨 / 字幕安全区 / 封面 / CTA 全部通过。
6. 人工审看后写 `human-review.json` APPROVED；在此之前 `production_ready=false`、`publish_authorized=false`，不生成任何发布链接。

## 6. 明确未完成事项

- 原始录屏：**尚不存在**，需真人按第 2–3 节采集。
- 裁切矩形与 claim 绑定：**待录屏后确定**。
- 授权旁白 provider：账号 DNA 写 `minimax_m_plan/speech-2.8-hd`，但本项目未获付费授权（MiniMax `allow_payg=false`）；需创始人决定本地 SAPI 兜底是否可接受，或授权正式 provider。
- 视频审核：全部 `PENDING_FOUNDER_REVIEW`。

> 本文件只说明如何解除阻断，不改变任何 QC 阈值，不把生成动画计入录屏证据，不声明任何真实录屏已存在。
