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

## 9. media-use 素材（可选）

需要 `~/.agents/skills/media-use` 固定版本技能与 Node ≥ 18。**默认不授权网络、付费供应商或跨项目复用。**

```powershell
python scripts\media_use_adapter.py status
python scripts\media_use_adapter.py doctor

python scripts\media_use_adapter.py candidates --type image --project projects\<slug>
python scripts\media_use_adapter.py resolve --type sfx --intent "soft transition" --project projects\<slug>

python scripts\media_use_adapter.py adopt --project projects\<slug>
python scripts\media_use_adapter.py import --type image --record-id img_001 `
  --license "CC-BY-4.0" --attribution "..." --project projects\<slug>

python scripts\media_use_adapter.py verify --project projects\<slug> --path assets\pic.png

python scripts\media_use_adapter.py demo --project projects\media-use-demo
```

退出码：`0` 完成，`2` 用法错误，`5` 被阻断／需要人工决定，`1` 意外失败。授权开关（`--allow-network`、`--allow-paid --budget`、`--allow-cross-project`、`--allowed-provider`）必须显式给出，默认关闭。

`import` 拒绝空 `--license`。media-use 记录本身没有许可证字段，因此许可证必须由人决定，不能被默认填充。

### 运行时锁（任何外部调用前必需）

在存在经过审核的锁之前，不会执行任何外部程序：

```powershell
$env:CONTENTOPS_MEDIA_USE_RUNTIME_LOCK = "D:\path\to\runtime-lock.json"
python scripts\media_use_adapter.py status
```

`status` 每次都会重新哈希整棵运行时树，并报告 `TRUSTED_RUNTIME`、
`RUNTIME_MISSING`、`INTEGRITY_MISMATCH`、`VERSION_MISMATCH` 或
`DEPENDENCY_UNVERIFIED` 之一。锁记录包版本、官方 integrity、node 二进制哈希、
入口文件，以及每个文件的 SHA-256。锁与本机绑定，不提交到仓库。没有锁时，
项目内本地导入仍然可用，但所有外部调用都会被拒绝。