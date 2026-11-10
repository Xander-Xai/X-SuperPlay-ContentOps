# Huashu 双动效引擎：Owner 执行授权申请

状态：**待批准**。本文件是申请，不是授权。在 Owner 明确签署之前，两个引擎都保持 `BLOCKED / NOT_EXECUTED`。

- 申请日期：2026-11-06
- 适用范围：`huashu-motion` 与 `huashu-art-motion` 两个引擎，在本仓库的受控执行适配层内
- 依据：ADR-009（技能执行授权）、ADR-010（受信 Grant 与执行门）、ADR-014（能力登记不是执行授权）
- 拒绝记录：两个引擎当前均未安装运行时，且无任何批准记录；执行路径全部返回 `BLOCKED`

## 1. 为什么需要这份授权

两个引擎都是**本地外部渲染器**，不是本仓库的一部分：

- `huashu-motion` 需要 Node ≥ 22、Chrome/Chromium/Edge、FFmpeg，驱动本机浏览器逐帧渲染；
- `huashu-art-motion` 需要 Playwright Chromium 与 ffmpeg。

本仓库的适配层只能做三件事：核对固定版本、描述操作、检查产物。**它不构造任何上游命令行，也不启动任何进程。**真正执行时，适配层会：
1. 先核对运行时（版本、commit、入口、LICENSE、Git 状态）；
2. 再从项目自己的 `receipts/skill-execution-approval.json` 读取批准记录；
3. 核对操作名、账户、流水线、阶段、版本、次数与有效期；
4. 消费一次使用额度；
5. 在真正调用之前**再核对一次**运行时；
6. 写一份 `receipts/executions/<grant>-use-NNNN.json` 回执。

缺任何一环，适配层返回 `BLOCKED`，执行器一次都不会被调用。

## 2. 申请授权的具体范围

| 项目 | 申请值 |
|---|---|
| 固定版本 | `huashu-motion` v0.3.1 @ `52467f99c602b76ba86d511d37acdfe93fa1e16e`；`huashu-art-motion` v1.2.0 @ `8f0a349a18b4bdf802b8d58715a2259c3e1ce709` |
| 允许的操作 | `om check`、`om still`、`om render`、`om qa`；以及 Art Motion 的 `render.py --spec` / `--solo` |
| 明确排除 | `om studio`、`om grab`、`om voice`、`om sound`、`om samples build`、`om share`、`om export html`、`om learn`、`om install`/`npx skills add`、任何下载或依赖安装 |
| 账户范围 | 仅 `x-superplay-1024`（禁止 `*`） |
| 流水线 / 阶段 | `M5` / `motion` |
| 项目范围 | 仅 `projects/huashu-motion-sample` |
| 输出目录 | `projects/huashu-motion-sample/work/clips/`（原始片段）与 `projects/huashu-motion-sample/assets/processed/`（音频替换后的派生片段）；渲染目录 `projects/huashu-motion-sample/huashu-motion/shots/*/out/` |
| 最大执行次数 | 每个批准记录 `max_uses = 12`（6 个镜 × 2 个引擎，各含一次失败重试余量）；`max_units = 1`（单次执行单位＝一次上游调用） |
| 资源预算 | 单次渲染最长 10 分钟；并发浏览器最多 2（上游默认 8，本申请降到 2）；峰值内存 ≤ 4 GB；磁盘新增 ≤ 2 GB；不调用任何付费接口、不消耗任何额度 |
| 有效期 | 自签署起 72 小时，到期自动失效；过期后需重新签署 |

## 3. 签署方式

批准记录写在项目的 `receipts/skill-execution-approval.json`（schema `contentops.skill-execution-approval/v1`，`purpose` 必须是 `skill_execution`）。执行主体由环境变量声明：

```
CONTENTOPS_OWNER_IDENTITIES=<owner 标识>
CONTENTOPS_EXECUTION_SUBJECT=<owner 标识>
```

未设置时，`load_grant` 会因为「没有任何 Owner 身份被信任」而拒绝。授权记录一旦被消费，`receipts/grants/<approval_id>/` 里会出现使用标记；同一请求 id 不能重复消费。

## 4. 这份授权**不**包含什么

- 不包含任何发布、投放或外发权限；
- 不包含把生成画面当作事实证据的权限（生成素材永远是 `generated=true`、`evidence_capable=false`、待人审）；
- 不包含安装依赖、下载运行时、下载字体或采样包；
- 不包含修改上游 CLI；
- 不包含任何付费 API 调用或额度消耗；
- 不包含对 `Easel` 上游的任何改动。

## 5. 执行前必须先满足的条件（与授权独立）

1. 运行时按固定版本安装到 `D:/Toolchains/huashu-motion/0.3.1` 与 `D:/Toolchains/huashu-art-motion/1.2.0`，且 Git HEAD、远端、干净状态三项核对通过；
2. `om doctor` 在本机报告 Node、FFmpeg、Chrome 全部就绪（**上游声明只在 macOS 上实测过，Windows 属于未验证路径**）；
3. 样片设计文件中列出的「未核对上游语法」三项，已在真实运行时用 `om check` 确认或修正。

第 1 条需要单独的下装授权；本文件只申请**执行**授权，不申请下载授权。
