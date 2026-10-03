# Easel 实测：它到底能不能直接干活？

> 引擎：Easel v0.2.1 (`.runtime/easel`)
> 画幅：9:16 · 1080×1920 · 竖版
> 时长：约 60 秒
> 风格：Result-first · Evidence-first · 克制 · 技术实测
>
> 本脚本由 Easel `video-script` Skill 生成初稿
> （原始输出：[`easel-video-script-output.txt`](easel-video-script-output.txt)），
> 并按实测证据人工校正。校正记录见文末「与 Skill 初稿的差异」。

## 事实边界

这是本视频唯一的事实来源。**违反即作废。**

### 本机实测（本次真的跑过）

| 结论 | 依据 |
|---|---|
| `easel doctor` 可运行；Python / Node / FFmpeg / openclaw / OpenClaw / Playwright / Skills synced 等 12 项 OK | `10-easel-doctor.png` |
| `easel doctor` 有 7 项 FAIL：fastapi、uvicorn、sse_starlette、multipart、Web 前端构建、`.env` API Key（以上 6 项全在 Web 工作台路径），外加网关 healthz 行（原因见下一条） | `15-easel-doctor-fails.png`（镜 5 画面）+ `10-easel-doctor.png` 计数行 |
| 网关端口坑：doctor/ping 的 healthz 探测写死 `127.0.0.1:18789`（upstream `commands/ping.py:56`、`commands/doctor.py:120`），而 easel profile 网关配置在 37289；`EASEL_GATEWAY_PORT` 只影响 WS 通道，不影响 healthz 探测 | `11-easel-ping.png`（Step 1 FAIL / Step 2 OK 实拍） |
| `easel ping`：Step 2（OpenClaw Agent 真实往返，走 easel 网关 37289）OK；Step 1（healthz@18789）因上述端口写死 + 默认网关未运行而 FAIL | `11-easel-ping.png` |
| 本次真实调用了一次 `easel skill video-script`，Agent 返回了完整脚本 | `easel-video-script-output.txt` |
| 上游 `assemble.py` 是纯标准库，可独立运行 | 见 `runtime-receipt.md` |
| 2026-10-03 复核：runtime 982/982 blob 哈希与上游 `3fe2d99` 一致（`scripts/verify_easel_runtime.py` 复跑 VERIFIED）；doctor/ping 状态以采集日实拍为准 | 本轮复跑 |

### 源码实测（数出来的 / 读出来的）

| 结论 | 依据 |
|---|---|
| 版本 `0.2.1`，`CHANGELOG.md` 记录日期 2026-09-24 | `pyproject.toml` / `CHANGELOG.md` |
| 上游 tag `v0.2.1` 指向 commit `3fe2d99...`；982 个文件逐个哈希校验一致 | `runtime-receipt.md` |
| `skills/openclaw/` 下 **114** 个 SKILL.md | 目录计数 |
| 分层：produce 52 / publish 20 / plan 16 / attribute 11 / discover 9 / general 6 | frontmatter `layer:` 统计 |

### 官方声明（本次**没有**验证）

- 自动发布、跨平台分发、数字人、归因分析、Web 工作台等能力
  —— 仅见于 README 与 `docs/skill-function-mapping.md`。
- 视频内**不得**把这些写成"我实测过"。

### 禁止出现的说法

- ❌ 「doctor 全绿 / 全部通过」—— 实际有 7 项 FAIL（6 项 Web 路径 + 网关 healthz 端口行）
- ❌ 「ping 两步全通」—— Step 1（healthz@18789）是红的；只有 Step 2（Agent 往返，走 37289）是通的
- ❌ 「网关跑在 18789」—— 那是默认 OpenClaw 网关；Easel profile 实际在 **37289**
- ❌ 「Easel 已经跑通完整流水线」
- ❌ 「开箱即用 / 开箱即调」—— 需要先配环境和依赖
- ❌ 把 README 宣称写成个人实测

---

## 分镜脚本

| # | 时间轴 | 口播 | 字幕 | 画面（真实素材） | source_type | motion |
|---|---|---|---|---|---|---|
| 1 | 0–5s | 装了 Easel 之后，最先要回答的是：它到底跑不跑得起来。 | 先看它跑不跑得起来 | `10-easel-doctor.png` | real_screenshot | static |
| 2 | 5–12s | 我把它锁在 v0.2.1，982 个文件逐个比对过哈希，和上游 tag 完全一致。 | v0.2.1 · 逐文件哈希校验一致 | `12-easel-version-evidence.png` | real_screenshot | static |
| 3 | 12–26s | 它不是一个 SaaS，是一层 Skill 库：114 个 Skill，分成发现、策划、创作、发布、归因五层，创作层最大，52 个。 | 114 个 Skill · 创作层 52 个 | `13-easel-skill-layers.png` | real_screenshot | static |
| 4 | 26–40s | doctor 跑起来了，Python、Node、FFmpeg 这些核心项是绿的；ping 里 Agent 真实往返也通了。但有个坑：网关健康检查探的是写死的默认端口，和 easel 实际网关端口对不上，那一行是红的。 | 核心项 OK · Agent 往返通 · healthz 端口对不上 | `11-easel-ping.png` | real_screenshot | static |
| 5 | 40–52s | Web 工作台这条路有六项没过：fastapi、uvicorn 这些依赖没装，前端也没构建，.env 也没有 API Key。所以 Web 界面现在还没验证。 | Web 路径 6 项未通过 · Web UI 未验证 | `15-easel-doctor-fails.png` | real_screenshot | static |
| 6 | 52–62s | 结论：它不是开箱即用的产品，但是一个真能被调起来的生产引擎。CLI 和 Skill 这条线，今天是通的。 | 不是 SaaS · 是一个能调用的生产引擎 | `14-easel-skills-dir.png` | real_screenshot | static |

> 共 6 镜，约 62 秒。所有画面 `motion=static` —— 内容是终端输出与 UI，
> Ken Burns 会裁掉字，不允许。

---

## 镜头要点

**镜 1（0–5s）冲突** — 用 doctor 输出开场，直给问题，不铺垫。
**镜 2（5–12s）身份** — 版本与哈希校验证明"这确实是 v0.2.1"。
**镜 3（12–26s）能力** — Skill 分层数据，数量是数出来的，不是抄文档。
**镜 4（26–40s）实测** — 核心项绿 + Agent 往返通，同时把网关 healthz 端口写死这个坑讲出来；ping 实拍图里 Step 1 红 / Step 2 绿，不藏。
**镜 5（40–52s）限制** — 主动揭短。Web 路径 6 项 FAIL 写在字幕上，画面就是 FAIL 行的实拍，不藏。
**镜 6（52–62s）结论** — 克制收尾，只给判断，不给营销词。

---

## 与 Skill 初稿的差异

Easel `video-script` 初稿有三处与实测不符，已按证据改正（**保留初稿原文作为审计痕迹**）：

| 初稿说法 | 实际 | 处理 |
|---|---|---|
| 「doctor 报环境全绿」 | doctor 有 5 项 FAIL | 改为如实报 FAIL，并把它做成镜 5 的限制段 |
| 「Gateway 跑在 18789 端口」 | easel profile 实际是 37289（18789 是默认网关） | 删除该端口表述，不在片中提端口 |
| 「发现 9 / 策划 16 / 创作 51 / …」 | 实际 frontmatter 统计为 produce 52（`skill-function-mapping.md` 的 51 已过期） | 采用数出来的 52，并注明来源是 frontmatter 统计 |

另：初稿称「assemble.py 自检通过」，实际自检在 Windows 上因字幕路径转义失败。
该结论已从片中移除，详见 `runtime-receipt.md` 与 QC 报告。
