---
translation_of: docs/RUNBOOK.md
language: zh-CN
translation_status: synced
---

# 运行手册

[English](RUNBOOK.md) | [简体中文](RUNBOOK.zh-CN.md)

> 真实可执行命令。从实际脚本行为推导，非假设。
> 最后更新：2026-10-31

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

需要 `~/.agents/skills/media-use` 固定版本技能与 Node ≥ 22（HyperFrames 官方 CLI 下限）。**默认不授权网络、付费供应商、跨项目复用或自动发布。** 可信运行时只证明执行了什么，不授予任何发现素材的许可证。

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

### 运行时信任（任何外部调用前必需）

必须同时具备两层，任一层都不能替代另一层：

- `runtime/media-use-runtime-baseline.json` —— 提交到仓库并由所有者批准
  （2026-10-31，仅限离线范围）。批准是记录在文件里的人为决定；它不会安装运行时。
- 本机生成的锁 —— 绝对路径、node 哈希、逐文件哈希，以及已批准基线的摘要 —— 由
  `CONTENTOPS_MEDIA_USE_RUNTIME_LOCK` 指向，绝不提交。

干净检出的机器在生成机器锁之前仍拒绝执行。基线批准记录一旦变化，基线文件摘要也会
变化，之前生成的锁将不再匹配：任何批准变更后都要重新生成锁。不要通过手工编辑锁来
让它匹配新基线。

在一台机器上准备一次：

```powershell
# 1. 人审查证据后批准已提交的基线
python scripts\media_use_runtime.py approve --approved-by "Your Name"

# 2. 安装已批准的发布（唯一需要联网的步骤）
python scripts\media_use_runtime.py install --runtime-dir D:\Data\contentops-media-use --node D:\Toolchains\node\node.exe

# 3. 生成机器锁，并与基线比对验证
python scripts\media_use_runtime.py lock --runtime-dir D:\Data\contentops-media-use --node D:\Toolchains\node\node.exe --out D:\Data\contentops-media-use\runtime-lock.json

# 4. 通过生产适配器执行本地、离线操作
python scripts\media_use_runtime.py selfcheck --lock D:\Data\contentops-media-use\runtime-lock.json --project projects\demo
```

```powershell
$env:CONTENTOPS_MEDIA_USE_RUNTIME_LOCK = "D:\Data\contentops-media-use\runtime-lock.json"
python scripts\media_use_adapter.py status
```

`install` 使用仓库内的 `runtime/media-use-package-lock.json` 执行
`npm ci --ignore-scripts`；该文件的 SHA-256 必须等于基线的
`dependency_lock_sha256`，依赖树不同即被拒绝。

`status` 每次都会重新哈希整棵运行时树，并报告 `TRUSTED_RUNTIME`、
`RUNTIME_MISSING`、`INTEGRITY_MISMATCH`、`VERSION_MISMATCH`、
`BASELINE_MISMATCH` 或 `DEPENDENCY_UNVERIFIED` 之一。重新生成锁永远不会批准发布。
没有可信锁时，项目内本地导入仍然可用，但所有外部调用都会被拒绝。

### 升级或回退 HyperFrames

升级是显式、经过审核的变更；适配器从不自动更新。

1. 更新 `runtime/media-use-runtime-baseline.json` 中的版本、官方 SRI、依赖锁摘要与包树摘要。
2. 人工审查证据后运行 `python scripts\media_use_runtime.py approve --approved-by "<name>"`。
3. 安装到**新的**运行时目录（不要覆盖可信目录），再执行 `lock` 与 `verify`。
4. 离线运行 `selfcheck`，再运行 `tests/test_media_use_adapter.py` 与 `tests/test_media_convergence.py`。
5. 将 `CONTENTOPS_MEDIA_USE_RUNTIME_LOCK` 指向新锁。

回退：保留旧的运行时目录与其锁，把环境变量指回旧锁，并验证它针对生成时的基线报告
`TRUSTED_RUNTIME`。绝不要手工编辑锁或逐文件哈希。

### 隔离 Easel 演示不等于原始运行时

media-use 演示通过另一套已验证的 Easel 运行时合成。演示成功与 QC `WARN` **不**表示
原始 `.runtime/easel` 检出已健康或已恢复；那仍是一个独立的完整性问题是。