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

## 5.1 证据优先生产链（M5）

```powershell
python scripts\m5_production.py projects\m5-easel-pin
```

来源 → 素材 → 声明 → 脚本 → 旁白 → 字幕 → 分镜 → 合成 → QC → 评审，每个阶段写一份凭证。
任何阶段无法被证据支撑即拒绝（`exit 4`，`state: BLOCKED`）：来源在仓库外、素材 SHA-256 变化、
声明的引文不在来源中逐字出现、素材未声明、字幕覆盖率低于 0.8。

`--skip-compose` 在分镜后停止（不调用 ffmpeg、不调用 Easel）。

旁白使用离线 Windows SAPI 语音，不调用任何联网 TTS。运行始终停在
`PENDING_FOUNDER_REVIEW`，`production_ready: false` —— QC 通过不等于允许发布。


### M5 自动调用 media-use 素材（仅离线）

当 PR #64 的适配器已进入当前版本、本机已有批准后的运行时锁时，
在项目 project.yaml 中声明素材需求。执行原来的 M5 命令时，
系统会自动调用 media-use，而不需要单独运行适配器命令：

~~~yaml
media_use:
  enabled: true
  mode: local-only
  requests:
    - id: support_visual
      kind: image
      intent: local support image
      license: OWNED
      rights_reviewed: true
      attribution: project owner
~~~

把已核实权利的候选图片放入该项目 assets/，然后在
script/script.json 对应镜头使用 asset_id=support_visual。
只执行正常的工作流：

~~~powershell
python scripts\m5_production.py projects\my-video
~~~

素材阶段会自动 adopt 本项目文件、通过批准的运行时离线 resolve、
生成导入回执并核验 SHA-256，再交给原有素材校验、分镜、合成及 QC。
已有 sources/assets.json 声明的素材优先。找不到素材则明确 BLOCKED，
不擅自联网或调用付费服务。

新增 receipts/media-use-stage.json 和每个文件的来源回执。
导入的授权素材只用于视觉辅助，不自动变成事实证据。
这一版支持 image/icon/logo 的自动画面接入；
bgm/sfx 尚未接入已有音频时间轴，不声称已混音。
未设置 media_use.enabled=true 的旧项目保持原行为。

本接线 PR 叠加在 M5 PR #68 上，真实外部调用还需要 PR #64。
CI 使用离线合成测试数据，不运行第三方 Provider。

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