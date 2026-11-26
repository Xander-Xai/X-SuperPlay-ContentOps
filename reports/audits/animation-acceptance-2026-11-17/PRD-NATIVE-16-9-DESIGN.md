# 独立设计提案：未来智能 B站原生 1920×1080 横版能力

> Archive provenance: independent design proposal generated 2026-11-17. Explicitly outside PR #196. No local paths or credentials.


生成时间：2026-11-17（Asia/Shanghai）
状态：**提案 / BLOCKED — `NATIVE_16_9_RENDER_UNAVAILABLE`**
范围：**独立 Issue + 独立 PR**。本提案**不进入** PR #196，也不通过改标签 / 拉伸纵版画面伪装完成。

## 1. 为什么它是独立范围

- 账号 DNA `config/accounts/x-superplay-future-intelligence.json` 声明 B站加长版为 `1920×1080 horizontal`（`derivative.mode=blur`），`platform_note` 明确「B 站加长版 1920×1080 走 card-quote 封面，章节按架构链路拆解」。
- 但当前渲染合同只产出 `1080×1920@30`：`scripts/m5_production.py` 把所有合成画面缩放到 1080:1920，没有原生 1920×1080 分镜/渲染路径。
- `scripts/video_deliver.py` 能派生 blur-pad 的 1920×1080 **载体**，并明确标注它不是 DNA 要求的原生重排。
- 阻断证据：`projects/e2e-p2-bilibili-169-blocked/receipts/`（`NATIVE_16_9_RENDER_UNAVAILABLE`），其中登记了 DNA / registry / render / deliver / adaptation 五处源码 SHA。

## 2. 冲突审计（DNA vs 平台规格 vs 合成器 vs 镜头 vs QC）

| 层 | 声明 / 现状 | 冲突点 |
|---|---|---|
| 账号 DNA | B站 1920×1080 加长版，card-quote 封面，章节化 | 要求原生横版重排，不是 9:16 派生 |
| 平台 registry | `bilibili` `requires_variant=true`，canvas 1920×1080 blur | `limits.aspect_required=9:16` 与实际要求横版存在声明张力，需创始人确认口径 |
| 合成器 Easel v0.3.0 | 已验证的合成路径为 1080×1920 | 无横版画布/合成回执；不得用 blur-pad 冒充 |
| 镜头适配 | 六模板与 P3 后端均按 1080×1920 出短镜头 | 横版需重新布局安全区、字幕、节点图与代码聚焦的排布 |
| QC | `target_dimensions` 硬校验 1080×1920 | 横版需独立的 1920×1080 尺寸门禁，不能放宽纵版校验 |

结论：这是「新布局能力 + 新渲染分支 + 新 QC 档」三件事，属于架构调整，按任务要求生成独立 PRD/Issue，不扩大 PR #196。

## 3. 原生 1920×1080 实现设计（提案）

### 3.1 画布与安全区
- 主画布 1920×1080，30fps，H.264/yuv420p，与纵版**同源但独立布局**，不拉伸、不改标签。
- 16:9 安全区：左右各 8%（≈154px）、上 6%（≈65px）、下 12%（≈130px 字幕区）；封面 card-quote 留白 ≥30%。
- 每条镜头 spec 增 `orientation: horizontal` 与独立的 `safe` 矩形；纵版 spec 保持不动。

### 3.2 分镜重排规则（未来智能 DNA：70% 矢量 / 25% 代码 / 5% 图表）
- 架构链：横向节点图（左→右），一次呈现一条边，保留阅读时间。
- 代码展示：局部行聚焦，横向排布代码卡 + 右侧注释，绝不整屏 IDE、无鼠标指针。
- Attention / 矩阵：矩阵占左半，解释文字占右半。
- 图表：横向趋势图，端点标注真实来源。
- 禁止弹跳 / 闪烁 / 摇晃 / 蓝紫渐变 / 玻璃拟态；沿用 `brand.palette`（`#0F1117` / `#38BDF8`）。

### 3.3 渲染与 QC 分支
- 在 M5/Easel 增加显式 `canvas=1920×1080` 的渲染分支与对应 storyboard；分辨率由配置项驱动，不硬编码纵版。
- QC 增加 `target_dimensions_1920x1080` 档；`caption_safe_zone` 用横版安全区；`composition_ratio` 按横版口径核算。
- 交付：`ffprobe` 必须报 1920×1080 / 30fps / H.264 / yuv420p；抽帧 + SHA-256 + 回执齐全；纵版作为**单独注册的版本**保留。

### 3.4 里程碑（建议 Issue 拆分）
1. 布局 spec 合同 + 单镜头横版渲染（无 QC 放宽）。
2. Easel 横版合成分支 + 真实 1920×1080 整片验证。
3. 横版 QC 档 + 平台交付包；人工审核后才可发布。

## 4. 实际阻断点（现在不能做的原因）

1. **范围授权**：任务明确要求横版能力独立成 Issue/PR，不能塞进 PR #196。
2. **渲染路径缺失**：M5/Easel 当前只产出 1080×1920，需要新增横版画布分支（架构调整）。
3. **QC 门禁**：`target_dimensions` 硬校验纵版，横版需要独立档；放宽纵版校验是被禁止的伪装完成。
4. **无真实横版证据**：目前没有 1920×1080 原生整片、无 SHA、无 ffprobe、无抽帧；任何 VERIFIED 声明都是伪造。
5. **平台口径待确认**：registry 的 `aspect_required=9:16` 与 DNA 的横版要求需在 Issue 中由创始人确认最终交付规格。

## 5. 明确不做

- 不拉伸 9:16 文件、不改标签冒充原生横版。
- 不用 blur-pad 载体充当 DNA 加长版。
- 不在 PR #196 内实现，不自动发布，不放宽 QC。

> 本提案只描述设计、冲突与阻断点。当前状态保持 `NATIVE_16_9_RENDER_UNAVAILABLE`，与 `p2-bilibili-169-block.json` 一致。
