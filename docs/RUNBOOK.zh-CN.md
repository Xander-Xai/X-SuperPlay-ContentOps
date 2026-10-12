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

## 9. 原生旁白 v2（A/B/C 样本）

设计决策：`adr/ADR-008-native-narration-v2.md`。口播稿对照锁定原文与
evidence lock 校验，三方版本映射（原文 / 口播 / 合成文本）用 `--write` 重新生成：

```powershell
python scripts\verify_spoken_script.py --write
```

干跑（完全离线；不发送任何请求，也不读取余额）：

```powershell
python scripts\run_ab_sample.py
```

真实执行。`--execute` 是显式开关；每次请求前后都会读取套餐额度与余额，
订阅类凭据未通过 `SAFE_INCLUDED_PLAN` 时直接拒绝。`--budget-chars` 与
`--budget-asr-calls` 是硬上限：

```powershell
python scripts\run_ab_sample.py --execute
python scripts\run_ab_sample.py --execute --a-mode fresh     # 精确文本对照（付费）
python scripts\run_ab_sample.py --execute --regenerate S02   # C 组局部重生成
python scripts\run_ab_sample.py --execute --variants N --extra-segment S04 --receipt-suffix term-check
python scripts\run_ab_sample.py --recheck                    # 仅重算测量；无 provider、无 ASR
```

- A 默认复用已有 Golden 旁白的本地节选（0 provider 成本）；`--a-mode fresh`
  则重新合成对照。
- 样本凭证与术语检查凭证是两个独立文件；辅助运行不会覆盖样本凭证。
- 真实音频写入 `outputs/`（gitignored）。运行停止于 Founder 试听：
  `production_ready` 保持 `false`，不发布任何内容。