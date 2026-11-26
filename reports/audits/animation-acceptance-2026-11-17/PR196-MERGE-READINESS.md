# PR #196 合并准备审查报告

> Archive provenance: 2026-11-17 PR-readiness review. Live GitHub metadata may have changed since this historical snapshot; verify PR state before acting. External media artifacts are not accessible in the current environment. No machine-specific path or credential is retained.


生成时间：2026-11-17（Asia/Shanghai）
结论：**技术上可合并（mergeStateStatus=CLEAN）、但本轮不合并、不推 main**。是否合并需创始人授权。

## 1. 实时状态（本轮重新核实）

| 项 | 值 |
|---|---|
| PR | #196 `[M5] P0-P3 animation engine integration and two-account video closure (Issue #196)` |
| 分支 | `feat/196-animation-dna-integration` → `main` |
| PR head | `7b2068bce25837e68b5eef75e068834a884bf164`（= 本地 HEAD） |
| main HEAD | 本地与远端均 `10017c2b74dca40a0d2f0df85c8023ccb01c3566` |
| 合并状态 | `MERGEABLE` / `CLEAN` |
| CI | Repo policy checks、Tests (ubuntu-latest)、Tests (windows-latest) 全部 pass（run 44012134219 与 44012139438） |
| 规模 | 36 commits，220 files，+39,366 / −186 |
| 本地工作树 | 干净（仅有本报告归档目录为新增，未提交） |
| #193 / #195 | 均 OPEN，未合并；其原始提交均为 #196 HEAD 祖先 |

## 2. 已解决问题

- P0：统一 `capability_matrix()`，锁文件/安装/编译通过都不提升 VERIFIED；只读带 `verified_at`+`sha256`+receipt 的真实渲染证据。
- 缓存可信：指纹绑定版本/模板/账号 DNA/来源/参数/源码摘要；登记链审计（canonical receipt + sources + script + m45 清单）修复 ping-pong 与多镜头互相覆盖缺陷；21/21 缓存完整性测试。
- P1：Huashu 六模板真实 MP4（1080×1920/30/h264/yuv420p/静音），参数变更→精确缓存失效→局部重渲。
- P2：未来智能 99.744s TEST_ONLY 整片，M5→14 镜头→Easel v0.3.0→QC 闭环；1024 缺真实录屏 `MISSING_REAL_RECORDING` BLOCKED；B站 16:9 `NATIVE_16_9_RENDER_UNAVAILABLE` BLOCKED；均未伪造通过。
- P3：Manim 0.22.1 隔离 venv 两模板真实 MP4；Motion Canvas 3.17.2 两模板 + 编辑器真实导出 mc-arch01（mc-state01 仍 EDITOR_EXPORT_REQUIRED）；Three.js 经 `@remotion/three` 真实 MP4（字节非确定已记录）。
- CI：相关测试套件已接线；Motion Canvas 缺外置媒体时明确报告 `REAL_MEDIA_NOT_RUN`，本地有真实导出时 `REAL_MEDIA_VERIFIED`。
- 治理：219 文件基线审计 0 路径穿越、0 严格凭据命中；分支注册、doc-freshness、governance ledger 对齐。

## 3. 遗留问题（不阻断合并，但阻断"生产可用"）

| 项 | 状态 | 阻断原因 / 后续 |
|---|---|---|
| 全部成片生产可用 | NO | 所有 `production_ready=false`、`publish_authorized=false`、`PENDING_FOUNDER_REVIEW`；自动发布关闭 |
| 1024 正式片 | BLOCKED | 无授权真实录屏；见归档 `RECORDING-CAPTURE-PLAN-1024.md` |
| B站原生 1920×1080 | BLOCKED | 渲染/QC 仅 1080×1920；blur-pad 载体不算原生；见 `PRD-NATIVE-16-9-DESIGN.md`（独立 Issue/PR） |
| mc-state01 编辑器导出 | EDITOR_EXPORT_REQUIRED | 官方 3.17.2 无 headless；需人工在编辑器 Render 并回灌 |
| P2 视觉门黄灯 | WARN（pass） | `fast_ratio≈0.05` 为 Huashu grammar 表现力边界；本轮已修复真正影响理解的深色标签问题（见下），未放宽阈值 |
| Three.js 字节确定性 | 记录项 | WebGL 抗锯齿；fingerprint 级确定，字节 SHA 不稳定 |
| ASR backcheck | SKIPPED | TEST_ONLY 未绑账号；正式生产需凭据 + 账号绑定 |

## 4. 本轮新增发现与处理（关键）

**逐镜头视觉验收发现真实缺陷**：`y3_whiteboard` 的 `draw` 标签用权威 DNA 的深色 `ink:#202B31` 画在深色 `bg:#0F1117` 上，对比约 1.30:1，架构/状态/输入清单不可读。已用 DNA 自身浅色 `surface` 令牌做模板参数修复，并在独立 worktree 真实重渲整片：
- 影片 SHA `66ca2673…` → `3aafc729…`；同格式/时长/帧数；visual-qc PASS，视觉门 WARN/yellow；`still_ratio` 0.604→0.573。
- 详细证据见 `CONTRAST-FIX-EVIDENCE.md`、`VISUAL-ACCEPTANCE-P2-FILM.md`。

**对合并的影响**：该修复**不在** PR #196 HEAD（`7b2068bc`）里。合并本身不受阻断（PR CLEAN、CI 全绿）。但若要让"已修复的成片"进入 main，需要创始人决定：
1. 把修复 patch  cherry-pick / 应用到 PR 分支并重跑 CI（影片 SHA 与一批 hash-bound 回执会变化）；或
2. 先合并 #196，再开独立 PR 纳入可读性修复；或
3. 保留 #196 为"能力集成"，把可读性修复作为后续独立 PR。

推荐方案 2 或 3：#196 的范围是能力集成与治理，视觉可读性修复是独立质量改进，分开 PR 更利于审阅与回执一致。

## 5. 合并风险

- **低风险（技术）**：PR CLEAN、CI 全绿、无未提交改动、无冲突；main 受保护规则（squash/linear/required checks）均满足。
- **中风险（语义）**：#193/#195 与 #196 内容重叠，必须只合并 #196 并把 #193/#195 标记 superseded 后关闭，**不得**重复合并（否则回执/能力矩阵双写）。
- **中风险（证据一致性）**：外置真实媒体不在 Git；CI 明确 `REAL_MEDIA_NOT_RUN`。合并后 main 的 CI 仍不会验证外置 MP4；这是设计如此，不要误读为"媒体已验"。
- **治理风险**：合并消息需遵循前缀与 Issue 引用规范；不得 direct push / force push。

## 6. 后续独立 Issue/PR 建议

1. **Issue（录屏采集）**：为 1024 提供授权真实录屏 + crop 矩形，解除 `MISSING_REAL_RECORDING`。输入见 `RECORDING-CAPTURE-PLAN-1024.md`。
2. **Issue/PR（视觉可读性修复）**：把本轮 `theme.ink := surface` 修复（含补丁、重渲回执、新片 SHA）纳入独立 PR，并决定是否替换 P2 交付片。
3. **Issue/PR（B站原生 16:9）**：1920×1080 布局 + 渲染分支 + 独立 QC 档；设计见 `PRD-NATIVE-16-9-DESIGN.md`。
4. **Issue（Motion Canvas mc-state01）**：人工编辑器导出 + `--import-editor-export` 回灌。
5. **Issue（视觉门绿灯）**：如创始人要求 `fast_ratio` 绿灯，评估给 Huashu 增加 `CAM.track` 缓推（新功能，独立设计，不放宽阈值、不为指标乱推镜）。
6. **Issue（正式旁白）**：授权 `minimax_m_plan/speech-2.8-hd` 或接受本地 SAPI 作为人审决定。

## 7. 三态区分

| 状态 | 本轮结论 |
|---|---|
| 技术测试通过 | 是：6 个必需套件全绿、dev_check 全绿、PR CI 三项 PASS |
| 视觉人工验收 | 未完成：逐镜头工程复核已做并记录；仍需创始人逐片人审（`PENDING_FOUNDER_REVIEW`），本轮修复已提供可复核证据 |
| 正式生产就绪 | 否：全部 `production_ready=false`、`publish_authorized=false`，无自动发布 |
