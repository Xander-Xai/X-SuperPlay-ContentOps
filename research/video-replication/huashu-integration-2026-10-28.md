---
status: experiment
canonical: false
issue: "#34"
date: 2026-10-28
---

# huashu-art-motion 接入记录（Build 组动画层）

> 选型依据：`open-source-animation-eval-2026-10-28.md`。
> 本文件记录实际接入的东西：版本、提交、补丁、样例、收据、以及没做到的部分。

## 1. 接入方式：外部 skill，不复制进主仓库

| 项 | 值 |
|---|---|
| 仓库 | `alchaincyf/huashu-art-motion`（MIT） |
| 版本 / 提交 | SKILL.md `1.2.0` / `8a0d7d72ca65fcce6f8ba82c4a6c8dfe35b8422c`（2026-10-17） |
| 安装位置 | `C:\Users\Administrator\.agents\skills\huashu-art-motion`（共享 skill 库） |
| 取用范围 | `SKILL.md`、`scripts/`（引擎与语法）、`references/`（语法卡与规范）、`defaults/`、`LICENSE` |
| 未取用 | 仓库的示例资产、角色库、长卷 demo；不整包进主仓库 |

仓库只保留我们自己的 spec、组装脚本和收据，引擎本体留在共享 skill 库。

## 2. Windows 适配（两处，已写入 LOCAL-PATCH.md）

1. **浏览器**：本机 Playwright Chromium 在 `D:\DevCaches\ms-playwright\chromium-1223`，
   宿主 Python 的 Playwright 正好匹配。`uv run --with playwright` 会安装更新的
   Playwright 并索要 `chromium_headless_shell-1248`（本机没有，下载也被网络卡住）。
   因此引擎用**宿主 Python**运行；同时给 `render.py` 加了
   bundled → Chrome → Edge 的通道回退，作为保险。
2. **编码**：`render.py` 用默认编码读 spec，Windows 下是 GBK，中文 JSON 直接
   `UnicodeDecodeError`。运行时设 `PYTHONUTF8=1`（仓库既定的子进程约定）。

除这两处外未改引擎。

## 3. 冒烟

| 项 | 结果 |
|---|---|
| 命令 | `python scripts/engine/render.py --spec smoke.json --out smoke.mp4` |
| 规格 | 1080×1920 / 30 fps / 3.0 s |
| 结果 | 90 帧全部渲染，中文标题与卡片正常，无 pageerror |
| 结论 | **Windows 原生可跑通**，不需要 WSL |

## 4. 样片：什么是 Agent

内容：5 句定义型口播，每句一个 4 s 窗口，共 20.0 s；纯代码动画，零录屏、零鼠标、零生成画面。

| 项 | 值 |
|---|---|
| 项目 | `projects/easel-fi-what-is-agent/` |
| 语法 | 机制 beat 用 `y1_kurzgesagt`（中心物 + 3 卫星 + 流动信号），支撑 beat 用 `t2_keynote_ui`（标题 + 步骤卡） |
| Specs | `motion/specs/p01..p05.json`（4 s / 1080×1920 / 30 fps，brand accent `#38BDF8`） |
| 片段 | `work/clips/p01..p05.mp4`（每段 4.000 s） |
| 配音 | MiniMax `speech-2.8-hd`，5 句，实测合计 10.762 s；逐句收据 `receipts/voice-0N.json` |
| 字幕 | `assets/captions/cut.srt`，按实测句长；DNA 样式烧录（无描边、安全区 120 px） |
| 输出 | `final/easel.mp4` — 20.0 s / 1080×1920 / h264 + aac / SHA `309cf5a7…871ff3b` |
| 技术 QC | 可解码；最长黑场 0.0 s；最长冻结 0.6 s |
| qc_video | **WARN**（20 s 低于 30 s 下限；纯动画无真实素材；未声明 source_refs），非 FAIL |
| 状态 | `production_ready: false`，`PENDING_FOUNDER_REVIEW`，无发布链接 |

收据：`receipts/sample.json`（spec/clip/输出 SHA、引擎出处、红线自查）、
`receipts/qc-summary.json`（绑定输出 SHA 的 QC 结论）、`receipts/qc-report-easel.{json,md}`。

## 5. 复现

```powershell
$env:PYTHONUTF8 = "1"
python C:\Users\Administrator\.agents\skills\huashu-art-motion\scripts\engine\render.py `
  --spec projects\easel-fi-what-is-agent\motion\specs\p01.json `
  --out  projects\easel-fi-what-is-agent\work\clips\p01.mp4
python scripts\build_code_animation_sample.py projects\easel-fi-what-is-agent
python scripts\qc_video.py projects\easel-fi-what-is-agent --video easel.mp4
```

## 6. 没做到的 / 下一步

1. **机制 beat 已换 y1，支撑 beat 仍是 t2**：y1 的中心物 + 卫星 + 流动信号读起来是机制；
   但竖屏最多 3 颗卫星，第 4 颗会被底部裁掉（已用 3 节点规避）。t1_3b1b 未验证。
2. **没有转场**：五段之间是硬切；引擎支持整片模式与转场库，但需要把 spec 换成
   段落表（`eras.js`），本轮未做。
3. **语速未实测闭环**：配音时长已测，但没有做 220–260 字/分的自动校正。
4. **X 仍未登录**：对标动效的最新数据缺口还在。
