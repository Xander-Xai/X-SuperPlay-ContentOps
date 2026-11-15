# PRD — Easel v0.3.0 底座接入（Workbench Foundation）

[简体中文](PRD-EASEL-V030-FOUNDATION.md) | [English](PRD-EASEL-V030-FOUNDATION.en.md)

> Last verified: 2026-11-15 on `main`. 状态：**Proposed** — 等待 Founder 批准。
> 本文是**需求文档**，不是完成报告。文中「目标 / 计划 / 未执行 / 待授权」都指尚未发生的事；
> 任何一段都不能当作「已经接入」的证据。

## 0. 文档元信息

| 项目 | 值 |
|---|---|
| 文档角色 | 「成熟底座 + 微调成自有工作台」这一方向的开发需求书（PRD） |
| 与 `PRD.md` 的关系 | `PRD.md` 描述运行时是什么；本文描述**如何把底座从 v0.2.1 换成 v0.3.0 并接管工作台**。本文不取代 `PRD.md`，只把它的 §6 非目标与 §14 Easel 集成两节展开成可执行需求 |
| 当前生效 pin | v0.2.1 / `3fe2d9904c1619281ef57f81d9ee0b7854998399`（`runtime/easel.lock.json`，未改动） |
| 目标 pin | v0.3.0 / `bb3c8ff0463f36c202454d74171682ba6e470cb1` + 内容摘要（见 §9） |
| 本次已执行的动作 | 仅限文档：本文 + 英文镜像 + 文档门禁接线。**未改代码、未改 pin、未装依赖、未起服务** |
| 批准人 | Founder（Xander-Xai） |

---

## 1. 背景与决策依据

### 1.1 一句话

项目已经把 Easel 当「视频拼接器」用了半年，但它的技能库、账号画像、工作台、Agent、发布通道一件都没进场。
本 PRD 把「先换发动机、再换驾驶舱」写成可验收的需求，让底座真正成为自有工作台，同时保住现有出片能力。

### 1.2 术语纠正（必须写进文档，否则后续全错）

| 口头说法 | 事实 | 依据 |
|---|---|---|
| 「接入 Easel 3.0」 | 上游**没有 2.x，也没有 3.0**。版本序列：v0.1.0 → v0.1.1 → v0.2.0 → v0.2.1 → **v0.3.0（2026-10-12）** | 上游仅 5 个 tag / 5 个 release；`pyproject.toml` version=0.3.0；CHANGELOG 顶部即 0.3.0 |
| 「2.0 接入 3.0 后清理掉」 | 「2.0」= 本仓库 pin 的 **v0.2.1**，跑在 `.runtime/easel` | `runtime/easel.lock.json` |
| 「项目没接底座」 | 接了，但很窄：6 个上游脚本以子进程调用，其中**只有 1 个在真跑** | §2 |

本文一律使用 **v0.2.1 / v0.3.0**，不再使用「2.0 / 3.0」。

### 1.3 已有决策链（本 PRD 不重新决策，只落实）

| 决策 | 内容 | 与本文的关系 |
|---|---|---|
| ADR-016 D1（2026-11-02，Owner 授权） | Easel 是生产底座，ContentOps 是治理扩展 | 本文是它的执行级展开 |
| 2026-11-12 Owner 决策 | 「跑一套成熟的 Easel 当底座并调优，而不是继续调 v0.2.1 那个库」 | 本文的直接授权来源 |
| ADR-022 D1（2026-11-13） | v0.3.0 只作 workbench 候选，不动生产 pin | 本文的 M2 沿用该边界 |
| ADR-022 D4 | 没有验证过的 OS 级隔离，禁止真跑 Agent | 本文的硬红线，M3 之前不松动 |
| ADR-012 D3 | v0.3.0 未采纳；采纳时按**内容摘要** + 全量升级门 | 本文 §9 的 pin 策略来源 |
| ADR-014 | 交付验证暂停 | 本文 §11 保留其结论，改为分级授权 |
| ADR-015 D2–D8 | 平台注册表是唯一机器可读真相源 | 本文 §11 不新增第二份注册表 |

### 1.4 与 `docs/PRD.md` 的边界

| `PRD.md` 条目 | 本文如何处理 |
|---|---|
| §6「Auto-publishing to any platform」为非目标 | **重开**（已授权、未执行），但受 §11 四档约束 |
| §6「n8n / OpenClaw total orchestration」 | **继续关闭**。底座提供技能与 agent，不等于让 OpenClaw 接管总编排 |
| §6「Database / complex FastAPI」 | **继续关闭**。工作台自带 FastAPI 宿主，那是上游产物，不是我们新增服务 |
| §14「Executed surface today: two files」 | **本文不改写这行**。它在 M1 落地前是事实；M1 完成、有回执后才允许改并 bump 日期 |
| §14「采纳上游 skills/agent/workbench 需 ADR-002 被取代」 | 本文只**提议**新 ADR（§17），不代签 |

---

## 2. 现状与差距

### 2.1 已接线且被真实调用的上游脚本（6 个，全部子进程，从不 import）

| # | 上游路径（v0.2.1） | 我方调用点 | 状态 | 副作用 |
|---|---|---|---|---|
| 1 | `skills/openclaw/auto-short-video/scripts/assemble.py` | `scripts/assemble_easel.py` ← `scripts/m5_production.py` | `INTEGRATED` + **有真实产物** | 本地渲染，无网络 |
| 2 | `skills/shared/scripts/tts.py` | `scripts/run_v1.py` | `INTEGRATED`，仅 V1，CLI 已封 | edge-tts，联网 |
| 3 | `skills/shared/scripts/render_card.py` | `scripts/render_cards.py` | `INTEGRATED`，**无真实产物** | 本地 HTML→PNG |
| 4 | `skills/openclaw/card-design/scripts/card_audit.py` | `scripts/render_cards.py` | 同上 | 本地密度门 |
| 5 | `skills/openclaw/gzh-design/scripts/validate_gzh_html.py` | `scripts/render_article.py` | `INTEGRATED`，**无真实产物** | 本地校验 |
| 6 | `skills/openclaw/gzh-design/scripts/wrap_preview.py` | `scripts/render_article.py` | 同上 | 本地包装 |

### 2.2 完全没有接线的底座能力

| 面 | 上游规模 | 本仓状态 |
|---|---|---|
| 技能库 | 114 个 skill 目录 | 仅发现（`scripts/skill_route.py` 读 front matter 后即返回 `execution_authorized: false`） |
| OpenClaw Agent | `easel/openclaw_*`、`agents/` | 未接线；Windows 隔离未验证 |
| Gateway | `easel/gateway_*` | 未接线 |
| CLI | `easel/cli.py`（chat/doctor/gateway/ping/skill） | 从未调用 |
| Workbench 宿主 | `web/app.py` | 只经 `src/contentops/easel/host.py` 的 loopback + 只读 guard；当前 `HOST_BLOCKED`（缺 fastapi/uvicorn/pydantic/sse_starlette） |
| 发布通道 | `skill-*-upload`、`skill-*-publisher` | 被 guard 与 driver 双重 deny |

### 2.3 磁盘上的四个副本（必须一次说清）

| 路径 | 体量 | 身份 | 是否被 resolver 接受 |
|---|---|---|---|
| `.runtime/easel` | 996 文件 | **生产运行时**，v0.2.1 pin `3fe2d99`，工作区干净 | 是 |
| `D:\Projects\_worktrees\easel-v030-rebuild-20261113b` | — | **v0.3.0 候选**，1073 blob + 树摘要 + 14 个 overlay 文件校验通过 | 仅经 `resolve_easel_workbench()` |
| `D:\Projects\Easel-Workbench` | — | 更早快照，`profile_status: STALE` | 否 |
| `Easel/`（仓库内） | 2.2 GB | **gitignored 遗留浅克隆**，HEAD `4b9c03c`（v0.2.1 之后 24 个提交），2 处未提交修改 | 否（被主动拒绝） |

### 2.4 真实产物证据（唯一一条完整链）

| 项 | 值 |
|---|---|
| 项目 | `projects/m5-easel-pin` |
| 回执 | `receipts/compose.json`：`status=OK`、`subtitles_burned=true`、`upstream=easel@v0.2.1:skills/openclaw/auto-short-video/scripts/assemble.py` |
| 成品 | `final/m5-easel-pin.mp4`：h264 1080×1920 + aac，`duration=45.142`，1,061,877 B |
| QC | `receipts/qc-report-m5-easel-pin.json` PASS（19 项） |
| 已知噪声 | 同目录 `qc-report-final.json` 因文件名漂移记为 FAIL，不代表渲染失败 |

### 2.5 差距（本 PRD 要闭合的）

| 差距 | 现状 | 目标 |
|---|---|---|
| 引擎版本 | v0.2.1（2026-09-24） | v0.3.0（2026-10-12），158 commit / 300 文件差距 |
| 技能目录布局 | `skills/openclaw/` | `skills/builtin/`（上游破坏性改名） |
| 交互面 | 命令行 + 一堆脚本 | 一个工作台页面 |
| 平台发布 | 9 平台全 `PLANNED`（除 `x` 为 `INTEGRATED/MANUAL_ONLY`），0 条真实发布 | 四档分级，终态全自动 |
| pin 单源性 | **5 处代码字面量 + 3 份 JSON** | 1 份注册表 + 派生 |
| 卡片/文章线 | 有代码无产物 | 有真实产物与回执 |

---

## 3. 用户与 JTBD

| 用户 | JTBD |
|---|---|
| Founder（唯一操作者） | 在**出片不中断**的前提下，把底座换到 v0.3.0，并让能力面（技能/画像/工作台）真正可用 |
| Founder | 打开一个页面就能看草稿、看回执、看门控结论，不必在十几个脚本间切换 |
| Founder | 终态：内容从选题到发布不需要逐步手工搬运；每一步都有回执 |
| 治理（代码/CI） | 任何「已接入」都必须能由一个命令或一份回执证明 |

成功长什么样：
1. 一条命令能切换引擎，另一条命令能回切，两次都有回执；
2. 同一份 storyboard 在两棵树下都能出片，QC 都 PASS；
3. 工作台页面能读草稿、读回执、读门控结论，但读不到凭据、发不了稿；
4. 每个平台的发布自主等级写在注册表里，且能从回执里查出来。

---

## 4. 目标态架构

### 4.1 两层边界

```text
┌──────────────────────── 底座层（Easel v0.3.0，只读基线 + 已登记 overlay）────────────────────────┐
│  渲染引擎 (assemble.py / 卡片 / 文章校验)   │  技能库 114 个 (skills/builtin/)                  │
│  账号画像 profiles/ (2 个账号，由 DNA 生成)  │  工作台宿主 web/app.py (React 前端)                │
│  Agent 执行引擎 (harnesses: OpenClaw/Codex/ACP) — 未验证隔离，禁跑                                 │
│  发布通道 (skill-*-upload / *-publisher) — 默认 deny，按 §11 四档逐平台放行                        │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
                                        ▲ 调用（子进程 / guard 代理）
                                        │ 唯一允许的写入面：outputs/、profiles/（经生成器）、overlay 登记文件
┌──────────────────────── 治理扩展层（ContentOps，本仓库拥有）──────────────────────────────────┐
│  证据层 SourceArtifact / ClaimLedger    │  9 门控 (7 VIDEO + 5 GRAPHIC_TEXT)                     │
│  M5 生产链 20+ 阶段                     │  QC 19 项 / ASR 旁白回检                               │
│  回执体系 (receipts/)                   │  平台规格 / 打包 / 交付 (9 平台注册表)                  │
│  素材权利门 / MiniMax provider 层        │  guard / driver / 离线任务 API                         │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 三条铁律

1. **底座不得修改上游字节。** 调优只能进 `runtime/easel-workbench-overlay.json` 登记的文件（当前 14 个：2 个 skill 覆盖 + 12 个画像文件）。未登记文件与上游不一致 = 校验失败，不是「微调」。
2. **治理层能否决底座。** 证据不足、权利未清、QC FAIL、门控未过，底座无论渲染出什么都不能被标记为 `production_ready`。
3. **底座不得自行发布。** 发布是治理层的授权动作，等级写在平台注册表 `autonomy` 字段，不由底座决定。

### 4.3 谁调谁

| 方向 | 形态 | 说明 |
|---|---|---|
| 治理层 → 底座 | 子进程（`hidden_run`） | 沿用现有 ADAPTER 模式，不改上游源码 |
| 治理层 → 底座宿主 | `src/contentops/easel/host.py` 的 guard 代理 | loopback、只读白名单、未知路由 fail-closed |
| 底座 → 治理层 | **不允许**。底座不能回调治理层改状态 | 防止「渲染器自己给自己发通行证」 |

---

## 5. 范围

| 里程碑 | 覆盖 | 不含 |
|---|---|---|
| M0 | pin 单源化、路径去硬编码、文档口径统一 | 任何运行时行为变化 |
| M1 | 生产引擎迁 v0.3.0，双 root 并存，回执锚定 `engine_id` | 工作台、agent、发布 |
| M2 | 工作台接管交互面（只读 + 离线任务 API） | Agent 真跑、发布 |
| M3 | 9 门控以 skill 声明挂入底座 | Agent 真跑（仍禁） |
| M4 | 发布四档落地（a 草稿自动 → b 单平台灰度 → c 全平台） | 抖音放开（直到 FULL_AUTO 单独授权） |

---

## 6. 非目标（对 `PRD.md` §6 逐条对账）

| `PRD.md` §6 原文 | 本文裁定 | 依据 |
|---|---|---|
| Auto-publishing to any platform | **REOPENED（已授权，未执行）**，受 §11 四档与逐平台授权约束 | 本 PRD D-C |
| Comment scraping / ROI agent | **STILL CLOSED** | 与底座接入无关 |
| Digital human / AI short drama | **STILL CLOSED** | 同上 |
| Metrics scraping / winner learning | **STILL CLOSED**（`bilibili_metrics` / `wechat_metrics` 保持只读回采，不扩） | 同上 |
| n8n / OpenClaw total orchestration | **STILL CLOSED**。底座提供 agent 能力，不等于把总编排交出去 | ADR-002、ADR-015 D2–D8 |
| Database / complex FastAPI | **STILL CLOSED**。上游自带 FastAPI 宿主属上游产物，我方不新增服务、不建库 | ADR-016 D2 |

新增非目标（本 PRD 明确不做）：

- 不改上游源码（无 fork、无 patch）；
- 不用 tag 当身份（上游强推过一次 tag）；
- 不在 M3 之前真跑 Agent；
- 不把 `Easel/` 遗留克隆接进生产路径；
- 不为「让门禁变绿」而调整日期或放宽校验。

---

## 7. 功能需求（FR）

编号规则：`FR-<域>-<序号>`。域：PIN / ENG / GOV / WB / PUB / DOC。风险级按 `docs/TEST-PLAN.md` L0–L3。

### 7.1 PIN — 版本身份与单源性

| ID | 需求 | 验收信号 | 风险 | 里程碑 |
|---|---|---|---|---|
| FR-PIN-01 | 新增 `runtime/easel-pins.json` 作为唯一 pin 注册表，含 `active`、`engines{v0.2.1,v0.3.0}`，每引擎含 `tag/commit/tree_sha256/layout/root/license/agpl_vendored/role` | `runtime/easel-pins.json` 存在且 schema 校验通过 | L3 | M0 |
| FR-PIN-02 | 消除 4 处代码字面量：`scripts/resolve_easel.py:48`、`scripts/verify_easel_runtime.py:62`、`src/contentops/graphic/articles.py:483`、`src/contentops/easel/agent_workspace.py:24` | `grep -rn "3fe2d99\|bb3c8ff" scripts src` 只命中注册表读取与测试夹具 | L3 | M0 |
| FR-PIN-03 | `runtime/easel.lock.json` 降为**派生值**（顶层 `tag`/`commit` 保留，schema 不变），加 `derived_from` 字段 | `check_docs.py` 的 lock 一致性检查 PASS | L3 | M0 |
| FR-PIN-04 | 引擎身份 = `commit` + `tree_sha256`；`tag` 只作注释，不得单独作为身份 | `verify_easel_runtime.py --json` 输出 `VERIFIED` 且含 `tree_sha256` | L3 | M1 |
| FR-PIN-05 | 双 root 并存：`.runtime/easel`（v0.2.1）原地不动，新增 `.runtime/easel-v030`；`--engine` 可显式选择 | `python scripts/resolve_easel.py --engine v0.2.1` 与 `--engine v0.3.0` 均 `status=OK` | L3 | M1 |
| FR-PIN-06 | 每份渲染回执写入 `easel: {engine_id, tag, commit, tree_sha256, layout, skill_rel}` | `projects/*/receipts/compose.json` 含 `easel.engine` 段 | L2 | M1 |

### 7.2 ENG — 生产引擎

| ID | 需求 | 验收信号 | 风险 | 里程碑 |
|---|---|---|---|---|
| FR-ENG-01 | 合成走 v0.3.0 的 `assemble.py`，字幕仍由我方生成 SRT→ASS 并单独烧制（绕上游 Windows 路径问题） | `final.mp4` 存在 + QC PASS + sha256 回执 | L3 | M1 |
| FR-ENG-02 | 技能解析改由引擎的 `layout` 字段驱动，不再靠「先试 openclaw 再试 builtin」的顺序猜测 | `src/contentops/easel/skill_paths.py` 提供 `layout` 入参；单测覆盖两种布局 | L2 | M1 |
| FR-ENG-03 | 上游改名影响面一次性收敛：`config/accounts/*.json` 内 skill 绑定、`config/registry/platforms.json` 的 8 处 `easel_capability.evidence`、`scripts/m5_production.py` 与 `scripts/package_code_animation_sample.py` 的路径引用 | `grep -rn "skills/openclaw" config scripts src` 只命中「v0.2.1 布局」显式分支 | L2 | M1 |
| FR-ENG-04 | TTS **不迁**：M5 旁白用 Windows SAPI / MiniMax，V1 的 `tts.py` 路径保持封存 | `docs/EASEL-CAPABILITY-INVENTORY.md` 明确标注「不迁」 | L0 | M1 |

### 7.3 GOV — 治理扩展

| ID | 需求 | 验收信号 | 风险 | 里程碑 |
|---|---|---|---|---|
| FR-GOV-01 | 9 门控以 skill 声明形式挂入底座，不自成第二引擎 | `scripts/skill_route.py` 解析到 ContentOps 扩展条目 | L2 | M3 |
| FR-GOV-02 | 回执 schema 字段可加不可删（版本化） | 新增字段不破坏既有 `check_receipt_secrets.py` | L1 | M3 |
| FR-GOV-03 | 素材权利门与 ASR 回检在 v0.3.0 路径下行为不变（`SKIPPED` 在账号绑定项目上仍阻断） | `tests/test_m5_asr_gate.py` + `tests/test_asr_siliconflow.py` + 权利门测试全绿 | L2 | M1 |

### 7.4 WB — 驾驶舱

| ID | 需求 | 验收信号 | 风险 | 里程碑 |
|---|---|---|---|---|
| FR-WB-01 | 宿主判据不放宽：`HOST_READY` 必须同时满足上游字节校验 + overlay 校验 + 前端构建回执 | `python scripts/easel_host.py status --json` | L2 | M2 |
| FR-WB-02 | 离线任务 API 语义不变（profile / draft / receipt 三条只读 + 一条离线写） | 一次 POST/GET 读回三份产物，`production_ready:false`、`publish_authorized:false` | L2 | M2 |
| FR-WB-03 | Agent 真跑仍被拒，直到有 OS 级隔离证据（专用工作区、受限可写、默认拒网、命名工具集） | `host_status` blockers 含隔离项 | L3 | M2/M3 |
| FR-WB-04 | 前端构建策略补工具链区间（当前只有精确观测值 `v24.16.0`，无上界；上游明确 25.x 不兼容） | `runtime/easel-workbench-build-policy.json` 含区间字段，不匹配即 `HOST_BLOCKED` | L2 | M2 |

### 7.5 PUB — 发布分级

| ID | 需求 | 验收信号 | 风险 | 里程碑 |
|---|---|---|---|---|
| FR-PUB-01 | 平台注册表新增 `autonomy{level,granted_by,granted_at,evidence[],rollback_to}` 正交维度（schema v2） | `scripts/check_platform_status_sync.py --strict` 0 条不一致 | L3 | M4 |
| FR-PUB-02 | 四档：`MANUAL → DRAFT_AUTO → GRAY_AUTO → FULL_AUTO`；`delivery_gate.authorize_delivery` 返回对应 outcome | 决策回执含档位与理由 | L3 | M4 |
| FR-PUB-03 | 抖音 `UNCONDITIONALLY_REFUSED` 保留到该平台获得 `FULL_AUTO` 单独授权为止；现有 6 条拒收规则一条不删 | `authorize_delivery("douyin").outcome == "REFUSED"` 回归通过 | L3 | M4 |

### 7.6 DOC — 文档与门禁

| ID | 需求 | 验收信号 | 风险 | 里程碑 |
|---|---|---|---|---|
| FR-DOC-01 | 本文与英文镜像成对存在，双向语言切换链接有效 | `python scripts/check_i18n.py` exit 0 | L0 | M0（本次） |
| FR-DOC-02 | 新文档纳入 `config/docs/doc-freshness.json` 分类，带验证日期 | `python scripts/check_doc_freshness.py` 0 stale / 0 error | L0 | M0（本次） |
| FR-DOC-03 | M1 落地后才允许改写 `docs/PRD.md` §14「Executed surface today」并 bump 日期 | 改写 PR 必须附 M1 回执 | L0 | M1 |

---

## 8. 非功能需求（NFR）

| ID | 需求 | 判定方式 |
|---|---|---|
| NFR-1 | **出片不中断**：切换窗口内任意时刻至少一棵树的 `resolve_easel.py` 返回 `OK` | 切换前后各跑一次，两次都 OK |
| NFR-2 | 回退 ≤ 1 条命令 ≤ 5 分钟 | 回切脚本存在且有 dry-run 回执 |
| NFR-3 | 引擎可复现：同 commit + 同树摘要 → 同校验结论 | `verify_easel_runtime.py --json` 的 `tree_sha256` 稳定 |
| NFR-4 | fail-closed：注册表缺失/损坏 → `BLOCKED`，绝不回退到某个内置默认 commit | 单测覆盖「注册表缺失 → BLOCKED」 |
| NFR-5 | 磁盘预算：受控副本共存 ≤ 4 GB | `du -sh` 结果记入切换回执 |
| NFR-6 | 发布诚实：0 个平台处于某档位时，注册表与文档都不得出现该档位 | `check_platform_status_sync.py --strict` |
| NFR-7 | 回执诚实：任何降级/跳步都写进回执，`production_ready` 保持 false | 回执 schema 校验 + 人工复核 |
| NFR-8 | Windows 一等公民：路径、UTF-8、子进程隐藏窗口策略不变 | `tests/test_windows_paths.py` 等全绿 |

---

## 9. 版本与 pin 策略

### 9.1 目标引擎身份

| 字段 | 值 |
|---|---|
| Repo | `https://github.com/ZJU-REAL/Easel.git` |
| Tag（仅注释） | `v0.3.0`（2026-10-12） |
| Commit | `bb3c8ff0463f36c202454d74171682ba6e470cb1` |
| 树摘要 | `c26fc96a653c0ff25ef3bc7486eee372c81f44e67d5ff2c30f1786c63c7d4ec8`（方法：按 POSIX 路径排序后 `path + NUL + blob SHA-1 + LF` 的 sha256） |
| blob 数 | 1073（`runtime/easel-workbench-overlay.json` 的 `tree_blob_count`） |
| 技能根 | `skills/builtin`（v0.2.1 为 `skills/openclaw`，114 个目录为同一集合） |
| 许可 | Apache-2.0（`LICENSE` sha256 `c71d239d…d0ab4`）；**例外**：`skills/builtin/gzh-design/` 为 vendored **AGPL-3.0** |

### 9.2 为什么必须按摘要而不是按 tag

v0.3.0 发布后，上游**用同一版本号替换过 tag**。一个可以被移动的 tag 不是身份。因此：

- 注册表拒绝「只有 tag、没有 `tree_sha256`」的引擎条目；
- `python scripts/check_easel_upstream.py` / `verify_easel_runtime.py --resolve-tag` 的 tag 漂移只作**告警**，不作判定；
- 任何回执引用引擎时必须同时写 `commit` 与 `tree_sha256`。

### 9.3 双引擎并存期的规则

| 规则 | 内容 |
|---|---|
| 默认选择 | 注册表 `active` 字段 |
| 显式覆盖 | `--engine v0.2.1` / `--engine v0.3.0`，只对单次命令有效，不改 `active` |
| 切换 | 只能通过 `scripts/easel_engine.py switch <engine>`（拟新增），并写 `runtime/easel-engine-switch.json` 回执 |
| 产物归属 | 新产物落当前 active 树的 `outputs/`；历史产物不迁移，以 `projects/*/final/` 为交付真相 |
| 保留期 | v0.2.1 树在 M2 验收通过后**至少再保留一个完整的发布周期**，之后才允许按 §12 R8 归档 |

---

## 10. 迁移路径

### 10.1 里程碑

| 里程碑 | 目标 | 入口条件 | 退出条件（可机器核验） | 失败回退 |
|---|---|---|---|---|
| **M0** | 治理与真相源收敛，**零行为变更** | 本 PRD 获批准 | `dev_check.py` 全 PASS；pin 只存在于注册表；5 处字面量清零 | revert 该 PR |
| **M1** | **换发动机**：v0.3.0 成为 `active` | M0 退出 + 3 份 golden 基线回执齐备 | `resolve_easel.py` → `engine=v0.3.0`；golden 项目出片 + QC PASS + 回执含 `engine_id` | `easel_engine.py switch v0.2.1` |
| **M2** | **换驾驶舱**：workbench 接管交互面，Agent 仍禁跑 | M1 退出 + 前端构建在目标机可复现 | `verify --overlay --frontend-build` VERIFIED；`host status` HOST_READY；离线任务 API 一次读回 | 关 host，退回 CLI 面 |
| **M3** | 治理扩展挂入底座 | M2 退出 | 9 门控被解析为 skill 条目；dry-run 出门控回执 | 撤注册表条目 |
| **M4a** | 草稿自动（人点最后一下） | M3 退出 + ADR-025 生效 | `autonomy=DRAFT_AUTO` 的平台产生真实草稿 + 回执 | 回落到 `MANUAL` |
| **M4b** | 单平台灰度全自动 | M4a 稳定 + 单独授权 | 一次真实发布 + 24h 观察回执 | 回落到 `DRAFT_AUTO` |
| **M4c** | 逐平台推进到全自动 | 每平台单独授权 | 每平台一份授权 + 一份发布回执 | 该平台回落一档 |

### 10.2 「出片不中断」的四个机制

| 机制 | 做法 | 落点 |
|---|---|---|
| 双 root 并存 | `.runtime/easel` 原地不动；v0.3.0 装到 `.runtime/easel-v030`。**不覆盖式替换**（覆盖会在窗口期让两棵树同时不通过校验） | `scripts/resolve_easel.py` 的候选表改读注册表 `roots` |
| 布局驱动解析 | `resolve_skill_dir(..., layout=...)`；删除「先 openclaw 再 builtin」的隐式顺序 | `src/contentops/easel/skill_paths.py` |
| 回执锚定 | 回执写 `easel.engine_id`，让「这一版是谁渲的」可查 | `scripts/assemble_easel.py`、`scripts/m5_production.py` |
| 一键回切 | 改注册表 `active` + 重派生 lock + 写切换回执（含前后 `engine_id` 与复验结果） | `scripts/easel_engine.py`（拟新增） |

### 10.3 建议 PR 序列

| PR | 内容 | 风险 | 依赖 |
|---|---|---|---|
| PR-01 | 本 PRD（中文 + 英文镜像）+ 文档门禁接线。不碰代码、不碰 pin | L0 | — |
| PR-02 | 新增 `runtime/easel-pins.json`（先只登记 v0.2.1，`active` 不变）+ lock 派生说明 | L2 | — |
| PR-03 | 5 处字面量改为读注册表；删除 `_FALLBACK_PIN` 的静默回退；新增「无字面量」单测 | L3 | PR-02 |
| PR-04 | `skill_paths` 加 `layout`；`assemble`/`render` 适配；上游改名影响面批量替换 | L2–L3 | PR-03 |
| PR-05 | `docs/UPSTREAM-EASEL.md` pin 表 + `docs/CURRENT-STATE.md` 双引擎段 | L1 | PR-02（可与 PR-04 并行） |
| PR-06 | `scripts/easel_engine.py` + 切换回执 + 回切演练测试 | L3 | PR-03 |
| PR-07 | 注册表登记 v0.3.0 条目（`active` 仍 v0.2.1）+ `verify --record` | L3 | PR-02 |
| PR-08 | **切 active 到 v0.3.0** + 3 份 golden 重跑 + 回执 diff | L3 | PR-04/06/07 |
| PR-09 | 工作台接管：构建策略区间 + 宿主判据 + 离线 API 读回 | L2 | PR-08 |
| PR-10 | 9 门控作为 skill 声明挂入 | L2 | PR-09 |
| PR-11 | 平台注册表 schema v2 + `autonomy` + `delivery_gate` 四档 | L3 | PR-10 + ADR-025 |
| PR-12 | M4a 首次真实草稿自动 | L3 | PR-11 + 单独授权 |

**不可压缩的三处串行点**：PR-08（切 active）、PR-11（autonomy 生效）、PR-12（首次真实外部写）。

---

## 11. 发布分级模型

### 11.1 四档定义

| 档位 | 含义 | 谁能升 | 前置证据 |
|---|---|---|---|
| `MANUAL` | 现状：系统产出交付包与回执，人发布、人记 URL | — | 默认值 |
| `DRAFT_AUTO` | 系统自动创建平台草稿，人点最后一下发布 | Founder | 该平台有 `draft_only` 通道 + 一次真实草稿回执 |
| `GRAY_AUTO` | 单平台 / 单账号 / 单题材全自动，24h 观察期 | Founder 单独授权 | 上一档连续成功 + 降级预案 + 观察回执 |
| `FULL_AUTO` | 全自动 | Founder 逐平台授权 | 灰度观察通过 + 该平台风控记录 |

### 11.2 硬约束

1. **不可批量跳档**：一次授权只能覆盖一个平台。
2. **抖音例外**：`UNCONDITIONALLY_REFUSED` 保持到该平台获得 `FULL_AUTO` 授权为止。现有理由（官方接口限定主体、需逐次用户主动触发、禁止同质化内容）不因技术进步自动消失。
3. **回执先行**：没有回执的档位视为未授权；注册表写 `FULL_AUTO` 但无 `evidence[]` 的条目必须被 `check_platform_status_sync.py` 判 FAIL。
4. **降级是单向最快路径**：任何一次平台侧异动（限流、警告、审核拒绝）→ 立即回落一档并留记录，不需要审批。
5. **状态与档位正交**：`status`（PLANNED…PRODUCTION_ACCEPTED）回答「证据到哪一步」，`autonomy` 回答「允许做到哪一步」，两者不得互相推导。

### 11.3 当前基线（填表即事实）

| 平台 | status | publish_mode | draft_support | easel_capability | autonomy（目标） |
|---|---|---|---|---|---|
| douyin | PLANNED | NOT_IMPLEMENTED | NONE | UPSTREAM_DECLARED | MANUAL（保持拒收） |
| bilibili | PLANNED | NOT_IMPLEMENTED | NONE | UPSTREAM_DECLARED | MANUAL |
| xiaohongshu_video | PLANNED | NOT_IMPLEMENTED | NONE | UPSTREAM_DECLARED | MANUAL |
| shipinhao | PLANNED | NOT_IMPLEMENTED | NONE | UPSTREAM_DECLARED | MANUAL |
| wechat_article | PLANNED | **DRAFT_ONLY** | NONE | UPSTREAM_DECLARED | MANUAL → DRAFT_AUTO 首选 |
| x | **INTEGRATED** | MANUAL_ONLY | NONE | ABSENT | MANUAL |
| zhihu | PLANNED | NOT_IMPLEMENTED | NONE | UPSTREAM_DECLARED | MANUAL |
| csdn | PLANNED | NOT_IMPLEMENTED | NONE | ABSENT | MANUAL |
| youtube | PLANNED | NOT_IMPLEMENTED | NONE | ABSENT | MANUAL |

注意两个容易误读的点：
- `wechat_article` 是唯一 `publish_mode: DRAFT_ONLY` 的平台，但 `draft_support` 为 `NONE`——**目标态与能力态是两回事**，M4a 必须先补通道；
- `x` 是唯一 `INTEGRATED`，但它的集成含义是「本地离线门禁」，`publisher.py` 没有任何返回 `PUBLISHED` 的分支。

---

## 12. 风险与回滚

| # | 风险 | 触发条件 | 可观测信号 | 缓解 | 阶段 |
|---|---|---|---|---|---|
| R1 | **AGPL 合规** | `skills/builtin/gzh-design/` 为 vendored AGPL-3.0；若随服务对外提供则触发源码开放义务 | `grep -r gzh-design` 命中图文线；`articles.py` 已把 `upstream_license: AGPL-3.0` 写进回执 | 只在本地进程内调用、不进服务端分发路径；回执加 `license_boundary`；商用前评估删除该 skill | M1 起持续 |
| R2 | tag 再次被强推 | 上游替换同版本 tag | `--resolve-tag` 报告指向不同 commit | 身份按 `commit + tree_sha256`；注册表拒绝无摘要条目 | M0/M1 |
| R3 | Node 25.x 不兼容 | 用 Node 25 构建前端 | 构建回执 `toolchain.node` 不匹配 | 构建策略补区间 `>=20 <25`，不匹配即 `HOST_BLOCKED` | M2 |
| R4 | 技能目录改名导致硬编码失效 | v0.3.0 生效瞬间 | assemble / render / 注册表证据集中报错 | 20+ 处路径一次性替换；`layout` 驱动解析；新增残留扫描 | M1 |
| R5 | 114 个 skill 描述被上下文预算截断 | 工作台一次性加载全部技能 | agent 输出「不知道有某技能」 | 只声明用到的 skill，不接全量库；扩展走注册表 | M3 |
| R6 | Windows Agent 隔离未验证 | 把 `HOST_READY` 误读为「可执行」 | 沙箱原型无条件拒绝执行 | 保留 ADR-022 D4：M3 之前 Agent 禁跑，隔离验收单独成门 | M2/M3 |
| R7 | 自动发布封号不可逆 | M4b 起真实外部写 | 平台限流/警告/封禁 | 只按四档推进；单平台单账号灰度；24h 观察；抖音保持拒收 | M4b/M4c |
| R8 | 多副本磁盘混乱 | 复制/重建时未指定目标 | 三副本 > 3 GB；resolver 误选遗留克隆 | `Easel/` 先 diff 再归档（AGENTS §10）；注册表只登记受控 root | M0 |
| R9 | pin 真相源漂移 | 手工改一处忘另一处 | 文档说 A、校验用 B | 单源注册表 + 5 处字面量清零 + 单测 grep 断言 | M0 |
| R10 | 回执硬编码 commit 导致 golden 全红 | M1 重跑比对 | 差异全部集中在 `easel_runtime_commit` | 先抽象 `engine_id` 字段**再**切 active | M1 |
| R11 | 前端依赖审计历史告警（1 critical / 3 high） | 工作台进入信任边界 | `npm audit` 输出；构建回执已记录计数 | 归档审计结果；不自动 `npm audit fix`（会破 lockfile 摘要）；接受需 ADR 记录 | M2 |
| R12 | `outputs/` 产物跨树残留 | 切换后旧产物仍在旧 root | 校验器把 `outputs/` 排除在字节比对之外，不报错 | 切换回执登记两棵树的产物清单；交付真相固定为 `projects/*/final/` | M1 |
| R13 | `docs/UPSTREAM-EASEL.md` 无时效门 | 改 pin 忘改该文档 | 该文档在 doc-freshness **exempt** 列表 | M0 把它移入 tracks（`code: runtime/easel-pins.json`），并加「Current Pin 表必须与注册表一致」检查 | M0 |

### 回滚按钮

| 场景 | 动作 | 时限 |
|---|---|---|
| M1 后出片异常 | `easel_engine.py switch v0.2.1` → 复跑 golden | ≤ 5 分钟 |
| M2 后宿主异常 | 停 host，回到 CLI 面（宿主与生产解耦） | ≤ 2 分钟 |
| M4 后平台异动 | 该平台 `autonomy` 回落一档 | 立即 |
| 任何阶段治理事故 | 关闭 active 引擎的写权限，进入只读复验 | 立即 |

---

## 13. 验收标准

### M0

| # | 命令 | 期望 |
|---|---|---|
| 1 | `python scripts/check_docs.py` | `All documentation checks passed.` |
| 2 | `python scripts/check_i18n.py` | exit 0，无 `MISSING mirror` / `STALE second Chinese copy` |
| 3 | `python scripts/check_doc_freshness.py` | 0 STALE / 0 ERROR |
| 4 | `python scripts/dev_check.py` | 全步骤 PASS |
| 5 | `grep -rn "3fe2d99" --include=*.py scripts src` | 0 条业务常量（仅测试夹具与注册表读取） |

### M1

| # | 命令 | 期望 | 回执 |
|---|---|---|---|
| 1 | `python scripts/resolve_easel.py` | `status=OK`、`engine=v0.3.0`、`commit=bb3c8ff…`、含 `tree_sha256` | — |
| 2 | `python scripts/verify_easel_runtime.py --runtime .runtime/easel-v030 --commit bb3c8ff… --json --record` | `VERIFIED`，`tree_sha256=c26fc96a…4ec8` | `runtime/easel-runtime.json` |
| 3 | `python scripts/assemble_easel.py projects/m5-easel-pin` | exit 0，`final/` 有 mp4 | `receipts/compose.json`（含 `easel.engine`） |
| 4 | `python scripts/qc_video.py projects/m5-easel-pin` | PASS，0 hard fail | `receipts/qc-report-*.json` |
| 5 | `python scripts/resolve_easel.py --engine v0.2.1` | 仍 `status=OK`（回滚树可用） | — |
| 6 | `python scripts/easel_engine.py switch v0.2.1` 再切回（拟新增） | 两次 `status=OK`，耗时被记录 | `runtime/easel-engine-switch.json` |

### M2

| # | 命令 | 期望 |
|---|---|---|
| 1 | `python scripts/verify_easel_runtime.py --overlay --frontend-build --json` | `VERIFIED`，14 个 overlay digest 全匹配 |
| 2 | `python scripts/easel_host.py status --workbench --json` | `HOST_READY`，`blockers: []` |
| 3 | 离线任务 API 一次 POST + GET | profile / draft / receipt 可读，两个授权标志均 false |
| 4 | Agent 执行请求 | 仍 `BLOCKED`（回归：D4 未松动） |

### M3

| # | 命令 | 期望 |
|---|---|---|
| 1 | `python scripts/skill_route.py` | 解析到 ContentOps 门控扩展条目 |
| 2 | `python scripts/check_skill_references.py` | exit 0 |
| 3 | 一次 dry-run 全链（`m5_production.py <project> --skip-compose`） | 门控回执齐全，`production_ready:false` |

### M4

| # | 命令 | 期望 |
|---|---|---|
| 1 | `python scripts/check_platform_status_sync.py --strict` | 0 条不一致 |
| 2 | 注册表 `autonomy.level` 取值 | 除已授权平台外全为 `MANUAL` |
| 3 | `python -c "from contentops.platforms.delivery_gate import authorize_delivery as a; print(a('douyin').outcome)"` | `REFUSED` |
| 4 | M4a 真实草稿 | 草稿回执 + 人工确认时间戳 |
| 5 | M4b 灰度发布 | 平台侧成功回执 + 24h 观察记录 |

---

## 14. 里程碑节奏与协作约束

- 每个里程碑一个 PR 序列，不允许 mega-commit（AGENTS §9）。
- 新分支必须在 `config/governance/branch-registry.json` 登记，`expires` 为复核日（非删除日），提交前先跑 `python scripts/check_branch_registry.py --today 2026-11-15`。
- `main` 受保护：3 项必需检查、squash 合并、线性历史、0 审批（单人期）。
- 每个里程碑结束必须 `git status --porcelain` 干净（AGENTS §10）。

---

## 15. 未决决策（不猜，写到决策为止）

| # | 待定 | 谁定 | 确认方式 |
|---|---|---|---|
| 1 | golden #2 / #3 选哪两个项目 | Founder | `ls projects/*/receipts/compose.json` + 是否存在 `final/*.mp4` |
| 2 | M4b 首个灰度平台 | Founder | 需真实账号就绪；候选 `wechat_article`（唯一 `DRAFT_ONLY` 目标） |
| 3 | v0.3.0 blob 计数口径（1073 与 1071 baseline 之差） | 治理 | `verify_easel_runtime.py --overlay --json` 的 `baseline_files` / `overlay_files` |
| 4 | ADR-024 是否独立于 ADR-023 | Founder | 取决于 Agent 隔离验收是否单独成门 |
| 5 | `Easel/`（2.2G）归档还是删除 | Founder | 先 diff 两处未提交修改，再决定（AGENTS §10） |
| 6 | 是否把 `docs/UPSTREAM-EASEL.md` 移出 exempt | 治理 | M0 一并处理 |
| 7 | v0.2.1 树的保留截止日 | Founder | M2 验收后至少一个发布周期 |
| 8 | gzh-design（AGPL）长期是否保留 | Founder + 法务 | 商用前评估 |
| 9 | 上游 #156（skill 描述截断）的量化影响 | 治理 | 查上游 issue 实测 |

---

## 16. 追溯矩阵

| FR 域 | 关联 ADR | 主要代码/配置 | 回执 |
|---|---|---|---|
| PIN | ADR-006、ADR-012 D3、ADR-022 D1 | `runtime/easel-pins.json`（新增）、`runtime/easel.lock.json`、`scripts/resolve_easel.py`、`scripts/verify_easel_runtime.py` | `runtime/easel-engine-switch.json`（新增） |
| ENG | ADR-001、ADR-007 | `scripts/assemble_easel.py`、`src/contentops/easel/skill_paths.py`、`scripts/m5_production.py` | `receipts/compose.json`、`receipts/m5-run.json` |
| GOV | ADR-005、ADR-021 | `scripts/production_gates.py`、`runtime/skill-registry.json` | `receipts/production-gates*.json` |
| WB | ADR-016 D2、ADR-022 D2/D3/D4 | `src/contentops/easel/host.py`、`guard.py`、`scripts/easel_host.py` | 项目内 offline task 回执 |
| PUB | ADR-014、ADR-015、ADR-016 D4 | `config/registry/platforms.json`、`src/contentops/platforms/delivery_gate.py` | 发布/草稿回执 |
| DOC | AGENTS §1 规则 10 | `scripts/check_i18n.py`、`config/docs/doc-freshness.json` | CI 检查结果 |

---

## 17. 变更记录与待建 ADR

### 17.1 本文需要的决策记录（只提议，不代签）

| 编号（拟） | 标题 | 作用 | 取代/修订 |
|---|---|---|---|
| ADR-023 | 采纳 v0.3.0 作为生产引擎：按内容摘要 pin、双引擎并存 | 解决「v0.3.0 到底采不采」 | 取代 ADR-012 D3；修订 ADR-016 D1 的 pin 值；收窄 ADR-022 D1 的「只作候选」 |
| ADR-024 | 工作台作为交互面与 Agent 隔离验收门 | 把「驾驶舱」写成边界 | 细化 ADR-022 D2/D3/D4，不松动 D4 |
| ADR-025 | 发布自主等级四档与授权流程 | 让自动发布有法可依 | 取代 ADR-014；修订 ADR-015 的发布部分，保留 D2–D8 |

### 17.2 实施进度（M0）

分支 `feat/173-easel-m0-pin`。以下全部可变核验，命令与结果见括号。

| PR | 状态 | 证据 |
|---|---|---|
| PR-01 文档 + 门禁接线 | **已完成** | `check_i18n.py` / `check_doc_freshness.py` / `check_docs.py` 全绿 |
| PR-02 pin 注册表 | **已完成** | `runtime/easel-pins.json`；`active` 现为 `v0.3.0`、`workbench_engine=v0.3.0`；两个引擎都带 `repo_id` 与 layout |
| PR-03 字面量清零 + 失败即拒 | **已完成** | 4 处常量改为读注册表；`_FALLBACK_PIN` 删除；注册表不可读 → `BLOCKED / PINS_UNREADABLE`；`tests/test_easel_pins.py` 14/14 |
| PR-04 skill 布局驱动（M1） | **已完成** | `resolve_skill_dir(..., layout=)`；`REQUIRED_PATHS` 按 layout 生成（这一条没做会直接把 v0.3.0 判成「缺少脚本」）；`--engine` 可显式解析任一引擎 |
| PR-05 文档双引擎段（M1） | **已完成** | `UPSTREAM-EASEL` 的 pin 表、双树规则、delta ledger；`CURRENT-STATE` 的运行时表与切换记录；README / ARCHITECTURE / PRD §14 同步 |
| PR-06 切换器（M1） | **已完成** | `scripts/easel_engine.py` 的 `show / verify / switch / install`；切换前先验证，写入 registry + 派生 lock + 追加回执；`tests/test_easel_engine.py` 7/7（含 4 条拒绝路径） |
| PR-07 v0.3.0 实例（M1） | **已完成** | `install` 逐字节比对后落盘 1086 文件（1073 baseline + 14 overlay）到 `.runtime/easel-v030`；`verify` 在 overlay 模式下 VERIFIED，1071 baseline blob 命中，license Apache-2.0 VERIFIED |
| PR-08 切 active（M1） | **已完成** | `switch v0.3.0` → 出片 → QC PASS → 产物 sha256 `07ff16dd…` **与 v0.2.1 逐字节相同**；回切演练 v0.3.0→v0.2.1→v0.3.0 三次全部 VERIFIED |

M1 的关键结论：**引擎换了，产物一个字节都没变**。这把「换底座」的风险从「画质/时长/字幕可能变」压到「只改了来源路径」，也让 M2 可以放心做工作台接管。

仍未做：M2（工作台接管，Agent 仍禁跑）、M3（9 门控挂成 skill）、M4（发布四档）。golden 仍只有 `projects/m5-easel-pin` 一份完整链，M2 之前需要补第二、三份。

顺带修复的既有失败（这些测试在 2026-11-13 的工作里就已经是红的，不是本次引入）：

| 套件 | 修复前 | 修复后 | 原因 |
|---|---|---|---|
| `tests/test_easel_host_guard.py` | 23/27 | **28/28** | 三处断言停留在旧契约：`/api/status` 已被 guard 拒绝、`mutations` 取值、离线依赖清单多了 PyYAML；另加一条 `/api/status` 必须被拒的回归 |
| `tests/test_easel_workbench_overlay.py` | 45/46 | **46/46** | generated 模式新增 DNA 新鲜度校验，假账号无法投影 → 如实断言 MISMATCH |
| `tests/test_easel_offline_task.py` | 5/18 | **19/19** | 夹具缺 `project.yaml`；POST 缺同源 `Origin`；错误码顺序；中断写现在落失败回执而非裸 OSError |
| `tests/test_m5_evidence.py` | 21/22 | **22/22** | workbench 解析器夹具不是合法 overlay |

一处代码行为变更（不属 pin，但为恢复既定契约）：`offline_task.run_offline_draft_task` 先校验 account 形状再查项目绑定，使非字符串账号返回 `ACCOUNT_INVALID` 而不是 `PROJECT_ACCOUNT_MISMATCH`。

### 17.3 变更记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-11-15 | v0.1 | 首版。状态 Proposed，等待 Founder 批准。本次只新增文档与文档门禁接线，未改代码、未改 pin |
| 2026-11-15 | v0.2 | 记录 M0 落地：pin 单源注册表、4 处字面量清零、失败即拒；修正 FR-PIN-02 的字面量数量（原写 5 处，实测为 4 处代码常量 + 1 处截图内容描述，后者不改） |

---

## 附：本 PRD 的证据边界

| 本文断言 | 证据等级 |
|---|---|
| 当前 pin 为 v0.2.1 / `3fe2d99` | 机器可读锁文件 |
| 6 个上游脚本被调用、其中 1 个有真实产物 | 代码 + 回执 + 实测 mp4 |
| v0.3.0 存在且 tag 被强推过 | 上游 tag/release 记录 + 本仓 overlay 记录 |
| 114 个 skill、1073 blob、树摘要 | 本仓 overlay 记录 + 校验器 |
| 9 平台状态与档位基线 | `config/registry/platforms.json` |
| 「工作台能跑起来」「Agent 能安全执行」 | **无证据**。前者 `HOST_BLOCKED`，后者 ADR-022 D4 明令禁止 |

最后一行是本文最重要的一行：**读这份 PRD 时，请把「目标」和「已发生」严格分开。**
