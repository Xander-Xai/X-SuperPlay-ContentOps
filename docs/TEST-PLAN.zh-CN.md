---
translation_of: docs/TEST-PLAN.md
language: zh-CN
translation_status: synced
---

# 测试计划

[English](TEST-PLAN.md) | [简体中文](TEST-PLAN.zh-CN.md)

> 测试策略、真实套件清单，以及 CI 接线。
>
> 最后验证：2026-11-01，分支 `fix/57-m5-media-fixtures`。

## 测试如何运行

本仓库**不使用 pytest**。每个套件都是独立脚本：构建 `TESTS` 列表，由 `main()` 运行。

```bash
python tests/test_m5_evidence.py
python tests/test_media_convergence.py
```

提交前运行本地门禁：

```bash
python scripts/dev_check.py
```

依次运行：仓库策略 → 子进程策略 → Skill 引用 → 文档 → i18n →
`scripts/test_basic.py` → `git diff --check`。

CI 为每个套件设置具名步骤。**新增 `tests/test_*.py` 却没有加入
`.github/workflows/ci.yml`，它就永远不会运行**，绿色 CI 也就不再是证据。
M4/M4.5 套件曾因此被合并且未接线。

## 当前清单

31 个套件。`grep -c '^def test_'` 统计到 704 个顶层 `test_*` 函数；列表驱动与 unittest
风格的套件定义方式不同，因此函数数是下限而非总数。

| 套件 | 文件 | 数量 | CI |
|---|---|---|---|
| 脚本冒烟 | `scripts/test_basic.py` | 10 | 是 |
| Windows 子进程 | `tests/test_windows_subprocess.py` | 47 | 是 |
| Windows 路径 | `tests/test_windows_paths.py` | 6 | 是 |
| M2 语音 | `tests/test_minimax_speech.py` | 86 | 是 |
| M2.1 声音克隆 | `tests/test_minimax_voice_clone.py` | 41 | 是 |
| M2.2 克隆路线 | `tests/test_minimax_clone_route.py` | 23 | 是 |
| M2.2 体验金激活 | `tests/test_voucher_activation.py` | 9 | 是 |
| 现金激活恢复 | `tests/test_cash_activation_recovery.py` | 20 | 是 |
| 原生 T2A 适配器 | `tests/test_minimax_native_tts.py` | 13 | 是 |
| 主机绑定审计 | `tests/test_host_binding_audit.py` | 9 | 是 |
| M3 图片 | `tests/test_minimax_image.py` | 85 | 是 |
| M4 H3 视频 | `tests/test_minimax_h3.py` | 108 | 是 |
| M4.5 媒体收敛 | `tests/test_media_convergence.py` | 97 | 是 |
| media-use 适配器 | `tests/test_media_use_adapter.py` | 56 | 是 |
| M4.6 Enhanced Golden | `tests/test_enhanced_golden.py` | 18 | 是 |
| Golden A/B 变体 | `tests/test_golden_variant_ab.py` | 13 | 是 |
| Golden 语音资产 | `tests/test_golden_voice_assets.py` | 10 | 是 |
| Golden 干净检出重建 | `tests/test_golden_voice_rebuildability.py` | 6 | 是 |
| 锁定输入可复现性 | `tests/test_locked_input_reproducibility.py` | 10 | 是 |
| 源证据 gitignore | `tests/test_gitignore_evidence_policy.py` | 14 | 是 |
| 本地批准 gitignore | `tests/test_local_approval_gitignore.py` | 5 | 是 |
| M5 证据 | `tests/test_m5_evidence.py` | 18 | 是 |
| M5 media-use 工作流 | `tests/test_m5_media_use_workflow.py` | 列表驱动 | 是 |
| M5 媒体可追溯性 | `tests/test_m5_media_traceability.py` | 列表驱动 | 是 |
| Skill doctor | `tests/test_skill_doctor.py` | 列表驱动 | 是 |
| Skill 引用完整性 | `tests/test_skill_references.py` | 6 | 是 |
| Skill 路由能力 | `tests/test_skill_router_capabilities.py` | 列表驱动 | 是 |
| Skill 执行授权 | `tests/test_skill_execution_authorization.py` | 列表驱动 | 是 |
| 受管 media-use 状态 | `tests/test_skill_execute_status.py` | 列表驱动 | 是 |
| 可信授权来源 | `tests/test_trusted_grant_source.py` | 列表驱动 | 是 |
| 执行门禁 | `tests/test_execution_gate.py` | 列表驱动 | 是 |

CI 还会运行：`scripts/check_subprocess_policy.py`、`scripts/check_docs.py`、
`scripts/check_i18n.py`、`scripts/check_repo_policy.py`、
`scripts/check_receipt_secrets.py`、`scripts/check_skill_references.py`。

### 媒体套件不会访问 provider

供应商套件驱动 `tests/fixtures/fake_mmx_cli.py`（以及 `fake_h3_api.py`），并注入
假计费传输。CI 无需 MiniMax 账号，也不会消耗配额。需要 `ffmpeg` 或 `Pillow` 的
测试在工具缺失时输出 `[skip]`；CI 会安装两者并打印可用性行，避免被跳过的套件
伪装成绿色。

## CI 检查

| 任务 | 内容 |
|---|---|
| `Tests (ubuntu-latest)` | 上述全部套件 + 策略/文档/i18n/空格 |
| `Tests (windows-latest)` | 同一矩阵 |
| `Repo policy checks` | 文件放置、凭证密钥、子进程策略、文档、i18n |

## 新增套件

1. 编写 `tests/test_<area>.py`，包含 `TESTS` 列表与 `main()`。
2. 在 `.github/workflows/ci.yml` 增加具名步骤。
3. 在本表与 `docs/CURRENT-STATE.md` 增加行。
4. 本地运行 `python scripts/dev_check.py` 与新套件。

第 2 步由检查强制：`check_repo_policy.check_test_suites_registered_in_ci` 会在
`tests/test_*.py` 未被工作流命名时失败。

## 计划中

- 跨仓库 `SourceArtifact` 适配器合约测试（依赖未合并的 content-router 层）。
- 3 个不同来源 → 3 个 final MP4 → QC → 人工审核的 E2E 测试（M6）。
