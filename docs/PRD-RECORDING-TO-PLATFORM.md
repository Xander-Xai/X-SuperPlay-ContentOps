# PRD — 手动录屏 → 双账号 → 多平台交付（Recording-First Delivery）

[简体中文](PRD-RECORDING-TO-PLATFORM.md) | [English](PRD-RECORDING-TO-PLATFORM.en.md)

> Last verified: 2026-11-16 on `feat/173-easel-m0-pin`.
> 状态：**Proposed** — 需求书；R1 已落地，其余里程碑未开始。
> 本文把「我手动录屏 → 项目加工 → 两个账号 → 多个平台」这条真实生产线写成
> 可验收的需求。文中「目标 / 计划 / 未执行」均指尚未发生的事。

## 0. 元信息

| 项目 | 值 |
|---|---|
| 文档角色 | 生产线需求书：录屏素材入场、双账号分叉、平台适配、发布授权 |
| 与 `PRD-EASEL-V030-FOUNDATION.md` 的关系 | 那份解决「换发动机 + 换驾驶舱」，本文解决「发动机接上之后，我自己的活怎么跑」 |
| 与 `PRD.md` 的关系 | 不取代；把 §6 的发布非目标按四档重开，把 GRAPHIC_TEXT / VIDEO 双线展开到平台交付 |
| 当前生效底座 | Easel v0.3.0 / `bb3c8ff0463f36c202454d74171682ba6e470cb1`（`runtime/easel-pins.json`，`active`） |
| 本次已执行 | R1（录屏入场策略门）+ 账号 DNA pin 漂移修正 + M3 收尾；未做发布、未清理 `Easel/` |
| 批准人 | Founder（Xander-Xai） |

---

## 1. 三个问题，先直接回答

### 1.1 「我的需求完成了吗」

**没有全部完成。** 已完成的是「底座接入」，未完成的是「你的生产线跑通」。逐项对账：

| 诉求 | 状态 | 证据 |
|---|---|---|
| 把 ZJU-REAL/Easel 最新版本接入为底座 | **已完成** | `runtime/easel-pins.json` 的 `active=v0.3.0`；`.runtime/easel-v030` 实例 VERIFIED（1071 baseline blob + 14 overlay，树摘要 `c26fc96a…`） |
| 换底座后仍能出片 | **已完成** | `projects/m5-easel-pin` 在 v0.3.0 出片，QC PASS，产物 sha256 与 v0.2.1 **逐字节相同** |
| 工作台（驾驶舱）可用 | **已完成** | `HOST_READY`，blockers 为空；离线任务 API 一次 POST/GET 读回四份产物，两个授权标志均 false |
| 治理门控挂进底座 | **本轮完成** | `extensions/contentops-gates/SKILL.md` + `runtime/skill-registry.json` 条目；`skill_route.py` 支持 `root: repo` |
| 我手动录屏 → 项目当素材加工 | **部分（本轮完成第一刀）** | 现状：`local_assets` 把用户视频登记为 `evidence_capable: false`、`LOCAL_PREVIEW_ONLY`，**不能算证据**；本轮新增策略门，仍不等同于「录屏自动变证据」 |
| 两个账号不同要求 | **部分** | 账号 DNA 已有 `manual_recording` 轴（1024 `ALLOWED_CROPPED` / 未来智能 `FORBIDDEN`），但只在 QC 事后拦截，入场时无门 |
| 适配不同自媒体平台 | **部分** | `config/platforms/video-platforms.yaml` 有 9 平台形状规格并有 `check()`；但**0 条真实发布**，8/9 行 `PLANNED` |

一句话：**发动机换了，驾驶舱通了，油门（录屏素材）和变速箱（平台交付）还没接上。**

### 1.2 `D:\Projects\X-SuperPlay-ContentOps\Easel` 在项目里起作用了吗

**没有。零调用，零产物，零回执。** 它是一次遗留浅克隆：

| 事实 | 值 | 怎么验的 |
|---|---|---|
| 身份 | gitignored 目录，HEAD `4b9c03c`（v0.2.1 之后 24 个提交），2 处未提交修改 | `git -C Easel status` |
| 体量 | 2.2 GB | 目录扫描 |
| 是否被解析器接受 | **否**，被主动拒绝 | `scripts/resolve_easel.py` 只接受注册表登记的 root |
| 生产真正在跑的树 | `.runtime/easel-v030` | `runtime/easel-pins.json` 的 `root` |
| 谁 import 过它 | 无人 | `grep -rn "Easel/" scripts src` 无业务命中 |

结论：它是**磁盘残留**，不是运行时。删它对生产零影响；保留它只会让下一个人（或下一个 Agent）误判「底座在哪」。
清理动作列为 R4，且**必须你确认后执行**（2.2 GB 删除不可逆，且要先 diff 那 2 处未提交修改）。

### 1.3 「最新版本」到底是哪个

| 说法 | 事实 | 依据 |
|---|---|---|
| 「2.0」 | 上游**没有 2.x**。序列是 v0.1.0 → v0.1.1 → v0.2.0 → v0.2.1 → **v0.3.0** | 上游 5 个 tag / 5 个 release |
| 「最新版本」= 最新 release | **v0.3.0（2026-10-12）**，已是当前生产底座 | `check_easel_upstream.py`：`release_update_available=false`、`recommendation=NO_ACTION` |
| 上游 `main` 头 | `e9d86ab4`（2026-11-15），比 tag 领先 **154 个提交 / 300 个文件**，**未发版** | GitHub compare `v0.3.0...main` |

所以：**你要的「最新版」已经接入完成**。`main` 上那 154 个提交里确实有对你直接相关的东西
（公众号扫码登录重复换码作废修复、头条登录页误判修复），但它们没有 tag，
按本仓 `ADR-012 D3` 与 `docs/UPSTREAM-EASEL.md` 的「按内容摘要 pin、不发版不升级」规则，
**不能因为「看起来更新」就直接换生产**。要跟进就按 R3 的候选引擎流程走，单独授权。

---

## 2. 用户意图还原（我理解的，请你纠错）

1. **录屏是你唯一的真实素材来源。** 你手动录下真实终端 / 真实网页 / 真实模型输出，
   项目负责裁切、配旁白、烧字幕、成片。你不接受 AI 图冒充实测。
2. **两个账号是两条不同的生产规则，不是同一套模板换个壳。**
   - `x-superplay-1024`：证据驱动（`EVIDENCE_LED`），录屏**允许但必须裁切**，
     成片 70% 时长是录屏证据，25% 矢量动画，5% 对比卡。
   - `x-superplay-future-intelligence`：解释驱动（`EXPLANATORY`），
     **全片零手动录屏、零鼠标操作、零桌面窗口**，70% 时长是矢量动画。
   - `x-superplay-english`：只发 X，一条英文帖 + 一张 16:9 真图，不走视频线。
3. **平台差异是硬约束，不是偏好。** 抖音 9:16 前三秒钩子；小红书 3:4 封面、标题 ≤20 字；
   B 站 16:9 加长版 + 章节；公众号/知乎/CSDN 走图文改写；X 走单条帖。

本 PRD 的所有功能需求都从这三条推出。**如果哪条理解错了，先改这一节，再改代码。**

---

## 3. 现状事实（只写能验的）

| 能力 | 状态 | 落点 |
|---|---|---|
| 录屏文件导入项目 | 有，但**降级为预览素材** | `src/contentops/media/local_assets.py`：`evidence_capable: false`、`usage_scope: LOCAL_PREVIEW_ONLY` |
| 录屏算真实证据 | 判定层认（`REAL_EVIDENCE_KINDS` 含 `screen_capture`），**入口层不给** | `src/contentops/media/claim_coverage.py` vs `local_assets.py` |
| 账号录屏策略 | 有，但只在 QC 阶段拦 | `src/contentops/media/cut_qc.py::manual_recording_forbidden` |
| 真实素材时长占比门 | 有，硬门 70% | `cut_qc.MIN_REAL_SOURCE_RATIO = 0.70` |
| 平台形状规格 | 有，9 平台，带 `*_basis` 溯源 | `config/platforms/video-platforms.yaml` |
| 平台打包 | 有（离线） | `scripts/video_deliver.py pack` |
| 真实发布 | **0 条** | 8/9 注册表行 `PLANNED`，`x` 为 `MANUAL_ONLY` |
| 底座出片 | 有，v0.3.0 | `.runtime/easel-v030` |
| 工作台 | 有，只读 + 离线任务 | `scripts/easel_host.py` |

**关键矛盾（本文的核心）**：`x-superplay-1024` 要求 70% 时长是录屏证据，
而记录你录屏的那个入口把文件标成「不可作证据」。这两个事实同时成立时，
**这条片子永远过不了 70% 门**，只能靠人肉改 `sources/assets.json` 绕过门 —— 这正是要修的洞。

---

## 4. 差距

| # | 差距 | 后果 | 本文需求 |
|---|---|---|---|
| G1 | 录屏入场不给证据资格 | 1024 线永远缺 70% 真实素材，靠手改 JSON 绕过 | FR-REC |
| G2 | 账号策略只在 QC 事后拦 | 录完、剪完、渲染完才被告知「本账号禁止录屏」，浪费一轮 | FR-ACC |
| G3 | 录屏与 claim 无绑定关系 | 出现「画面是 A，口播说的是 B」的错配，只有人能看出来 | FR-REC-03 |
| G4 | 平台适配只有形状校验，没有变体计划 | 一个 9:16 成片要手工判断 B 站是否需要 16:9、公众号要不要改写 | FR-ADP |
| G5 | 发布 0，无档位 | 所有交付停在「人肉上传」 | FR-PUB（沿用四档） |
| G6 | `Easel/` 残留 + 账号 DNA 写旧 pin | 误判底座身份；文档与数据自相矛盾 | FR-CLN / FR-DOC |

---

## 5. 目标态

```text
你手动录屏 (mp4/mov)
        │
        ▼
[R1 录屏入场门]  账号策略 → 裁切矩形 → 时长/分辨率 → claim 绑定 → 回执
        │                                    (FORBIDDEN 账号在此直接拒)
        ▼
sources/assets.json  (kind=recording, evidence_capable=true, 边界声明)
        │
        ▼
[VIDEO 线] 脚本 → 旁白 → 分镜 → CutPlan → 合成（Easel v0.3.0）→ QC
        │                                       ▲ 底座只出片，不做判定
        ▼
[R2 平台适配]  账号 × 平台 → 变体计划（画幅/时长/标题/封面/标签/CTA）→ 回执
        │
        ▼
[R3 发布四档]  MANUAL → DRAFT_AUTO → GRAY_AUTO → FULL_AUTO（逐平台单独授权）
```

三条边界不变：

1. 底座不改字节（调优只进 overlay 登记文件）；
2. 治理层能否决底座（QC/门控不过，渲了也不算成品）；
3. 底座不得自行发布（发布是治理层授权动作）。

---

## 6. 功能需求

风险级按 `docs/TEST-PLAN.md` L0–L3。

### 6.1 REC — 录屏入场

| ID | 需求 | 验收信号 | 风险 | 里程碑 |
|---|---|---|---|---|
| FR-REC-01 | 新增录屏入场门：读 `project.yaml` 的 `account_slug` → 读账号 DNA 的 `evidence.manual_recording` → `FORBIDDEN` 直接 `REFUSED`，`ALLOWED_CROPPED` 缺裁切矩形即 `BLOCKED`，未声明账号即 `BLOCKED` | `python scripts/ingest_recording.py --project <p> --file <f> --claim <id>` 四种路径各有明确 verdict | L2 | R1 ✅ |
| FR-REC-02 | 入场即登记为**可作证据**：`type=recording`、`origin=SELF_CAPTURED`、`evidence_capable=true`、`distribution_authorized=false`、`requires_human_review=true`；不得改动既有行的语义 | `sources/assets.json` 新增行字段齐全；`cut_qc` 的 70% 门可被真实录屏满足 | L2 | R1 ✅ |
| FR-REC-03 | 每条录屏必须绑定 `claim_id`（口播声称的那条事实）；绑定不存在的 claim → `BLOCKED` | 回执 `bindings[]` 与 `script/claim-map.json` 一致 | L2 | R1 ✅ |
| FR-REC-04 | 裁切矩形必须在源画面内，且必须在回执里留档，供人审「桌面/弹窗/凭据是否被裁掉」 | 越界矩形 → `BLOCKED CROP_OUT_OF_BOUNDS`；回执含 `crop` 与 `frame_size` | L2 | R1 ✅ |
| FR-REC-05 | 回执 `receipts/recording-intake.json` 恒含 `production_ready:false`、`publish_authorized:false` | schema 校验 + 单测 | L1 | R1 ✅ |
| FR-REC-06 | 录屏自动切片（按静音段/画面变化切候选片段并生成 CutPlan 草稿） | 一段 90s 录屏自动产出候选片段列表 | L3 | R2（未开始） |

### 6.2 ACC — 双账号分叉

| ID | 需求 | 验收信号 | 风险 | 里程碑 |
|---|---|---|---|---|
| FR-ACC-01 | 账号策略在**入场**和 **QC** 两处一致：同一份 DNA 字段，同一套取值，不允许两处各写一份 | `cut_qc.STRICTNESS` 与入场门读同一字段；单测覆盖 FORBIDDEN 账号 | L2 | R1 ✅ |
| FR-ACC-02 | 账号 DNA 的 `render.runtime_pin` 不得与 `runtime/easel-pins.json` 矛盾 | 两处 pin 字符串一致（本轮已修 v0.2.1 → v0.3.0） | L1 | R1 ✅ |
| FR-ACC-03 | 1024 线的 70% 录屏 / 25% 矢量 / 5% 卡片配比，在未来智能线必须镜像为 70% 矢量 / 25% 代码 / 5% 图表，且两条线的门控各自生效 | 同一 storyboard 在两账号下产出不同的合规结论 | L2 | R2 |
| FR-ACC-04 | 账号未声明 `account_slug` 的项目一律 `BLOCKED`，不允许「默认账号」 | 无 slug 项目跑生产线 → `ACCOUNT_UNANNOUNCED` | L2 | R1 ✅ |

### 6.3 ADP — 平台适配

| ID | 需求 | 验收信号 | 风险 | 里程碑 |
|---|---|---|---|---|
| FR-ADP-01 | 由「账号 DNA 的 platform_roles」× 「`video-platforms.yaml` 的规格」生成**变体计划**：每个平台一行，含画幅、时长上限、标题字数、标签数、封面比例、CTA、上传器 | `python scripts/platform_adapt.py plan --project <p>` 输出 9 行（或账号声明的子集） | L2 | R2 |
| FR-ADP-02 | 变体计划必须标出「哪些平台需要二次成片」（如 B 站 16:9 加长），而不是假装一个文件通吃 | 计划含 `requires_variant: true/false` 与理由 | L2 | R2 |
| FR-ADP-03 | 未知平台 / 账号未声明的平台 → `BLOCKED`，不静默跳过 | 单测覆盖 | L2 | R2 |
| FR-ADP-04 | 变体计划只做计划，不改成片、不发布；`publish_authorized` 恒 false | 回执 schema | L1 | R2 |

### 6.4 PUB — 发布四档

沿用 `PRD-EASEL-V030-FOUNDATION.md` §11：`MANUAL → DRAFT_AUTO → GRAY_AUTO → FULL_AUTO`，
逐平台单独授权，抖音 `UNCONDITIONALLY_REFUSED` 保持。本文不重复定义，只要求：

| ID | 需求 | 风险 | 里程碑 |
|---|---|---|---|
| FR-PUB-01 | 首个 `DRAFT_AUTO` 试点选 `wechat_article`（唯一 `publish_mode: DRAFT_ONLY`），但仍需先补 `draft_support: NONE` 的通道 | L3 | R3 |
| FR-PUB-02 | 任何真实外部写之前，变体计划与 QC 回执必须同时在场 | L3 | R3 |

### 6.5 CLN / DOC

| ID | 需求 | 验收信号 | 风险 | 里程碑 |
|---|---|---|---|---|
| FR-CLN-01 | `Easel/` 清理前先 diff 那 2 处未提交修改，结论写进回执；清理用归档或删除，**必须 Founder 逐条确认** | 一份 `diff` 结论 + 一次确认记录 | L3 | R4 |
| FR-CLN-02 | v0.2.1 回滚树在 R2 验收后再保留一个完整发布周期，之后才可归档 | 注册表 `role: rollback` 仍在 | L2 | R4 |
| FR-DOC-01 | 本文与英文镜像成对，双向语言切换有效；纳入 `doc-freshness` 跟踪 | `check_i18n.py` / `check_doc_freshness.py` 全绿 | L0 | R1 |

---

## 7. 里程碑与验收

| 里程碑 | 目标 | 状态 | 验收命令 |
|---|---|---|---|
| **R0** | 底座接入（v0.3.0 生产 + 工作台 + 门控挂载） | **已完成** | `python scripts/easel_engine.py show`；`python scripts/easel_host.py status --workbench` |
| **R1** | 录屏能合法成为证据，账号策略在入场生效 | **本轮完成** | `python tests/test_recording_intake.py`；`python scripts/ingest_recording.py --project <p> --file <f> --claim <id>` |
| **R2** | 平台变体计划 + 自动切片 | 未开始 | `python scripts/platform_adapt.py plan --project <p>` |
| **R3** | 首个平台真实草稿 | 未开始 | 草稿回执 + 人工确认时间戳 |
| **R4** | 清理 `Easel/` 与旧 pin 残留 | 未开始（待确认） | diff 结论 + `Easel/` 不存在 + `resolve_easel.py` 仍 OK |

R1 的退出条件（可机器核验）：

1. `FORBIDDEN` 账号（未来智能）任何录屏入场都被 `REFUSED`，且原因点名 DNA 字段；
2. `ALLOWED_CROPPED` 账号（1024）缺裁切矩形被 `BLOCKED`，给了合法矩形则 `ACCEPTED` 且写入 `evidence_capable: true`；
3. 回执恒 `production_ready:false` / `publish_authorized:false`；
4. 未声明 `account_slug` 的项目 `BLOCKED`，不回退默认账号。

---

## 8. 风险

| # | 风险 | 信号 | 缓解 |
|---|---|---|---|
| R1 | 把录屏标成「可作证据」被读成「可以随便发」 | 有人拿 `evidence_capable` 当发布授权 | 回执与行内同时写 `distribution_authorized:false` / `requires_human_review:true`；发布仍走四档 |
| R2 | 录屏内含第三方仓库/AI 输出，画面版权与合规边界未清 | 有人质疑「这是别人的界面」 | 证据只主张「屏幕显示过什么」；权利结论留人审；商用前单独评估（沿用原 PRD R1 AGPL 边界） |
| R3 | 裁切矩形合法但实际没裁掉桌面/凭据 | `CROP_OUT_OF_BOUNDS` 通过，人审才发现 | 回执留 `crop` + `frame_size`，人审必看；R2 补自动抽帧人审图 |
| R4 | 跟进上游 `main`（154 提交）带来行为漂移 | 换完出片变了 | 按候选引擎流程：装第三棵树 → 校验 → golden 重跑 → 再切；不覆盖 v0.3.0 |
| R5 | 删除 `Easel/` 误伤 | 删到归档区或生产树 | 先 diff、先确认、按 AGENTS §10 记录；Junction 禁 `Remove-Item -Recurse` |

---

## 9. 未决决策（不猜）

| # | 待定 | 谁定 |
|---|---|---|
| 1 | 是否把上游 `main`（`e9d86ab4`）作为候选引擎接入，还是等 v0.4.0 发版 | Founder |
| 2 | `Easel/`（2.2 GB）归档还是删除；2 处未提交修改是否有价值 | Founder |
| 3 | 首个 `DRAFT_AUTO` 平台是 `wechat_article` 还是先做小红书 | Founder |
| 4 | 录屏是否允许包含第三方 AI 产品界面（合规边界） | Founder + 法务 |
| 5 | v0.2.1 回滚树的保留截止日 | Founder |

---

## 10. 附录：本轮实际执行

见 §7 R1 的验收命令；代码落点：

| 文件 | 作用 |
|---|---|
| `src/contentops/media/recording_intake.py` | 录屏入场门（策略 → 探测 → 裁切校验 → claim 绑定 → 素材行 → 回执） |
| `scripts/ingest_recording.py` | CLI 入口 |
| `tests/test_recording_intake.py` | 四种 verdict 路径 + 回执诚实性 |
| `config/accounts/*.json` | `render.runtime_pin` 由 v0.2.1 修正为 v0.3.0 |
| `extensions/contentops-gates/SKILL.md` | 门控技能声明（R0 收尾） |
