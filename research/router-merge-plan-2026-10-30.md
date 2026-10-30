---
status: experiment
canonical: false
issue: "#7"
date: 2026-10-30
---

# 合并计划：路由器分支是堆叠分支，不能单独落 main

## 事实（实测）

| 项 | 值 |
|---|---|
| `feat/content-router` HEAD | `3f76030` |
| 基提交 | `8ff3dfa`（`feat/34-video-replication`） |
| `main` / `origin/main` | `5d1fcf2` |
| `main` 是否为 `8ff3dfa` 的祖先 | **是**（可干净合入） |
| `8ff3dfa` 相对 main 的提交数 | 91 |
| 路由器分支相对 `8ff3dfa` 的提交数 | 4 |

验证命令：

```powershell
git merge-base --is-ancestor main 8ff3dfa; echo $LASTEXITCODE   # 0 = 是祖先
git log --oneline main..8ff3dfa | Measure-Object -Line
git log --oneline 8ff3dfa..feat/content-router
```

## 为什么不能把路由器分支 rebase 到 main

路由器 import 了父亲分支上的模块，这些模块在 main 上**不存在**：

| 依赖 | 用途 | 在 main 上 |
|---|---|---|
| `src/contentops/workflow/topics.py` | `contentops.content-candidate/v1` 契约与校验 | 不存在 |
| `src/contentops/workflow/human_forecast.py` | `contentops.evidence-feasibility/v1`、`forecast_verdict` | 不存在 |
| `scripts/account_route.py` | 账号 → 流水线解析（读 `project.yaml` 的 `account_slug`） | 不存在 |
| `config/accounts/*.json` | 两个账号的完整 DNA | 不存在 |
| `scripts/new_project.py` | `create_project()`（`account_slug` 参数） | 仅旧版，无 `account_slug` |

在 main 上 rebase 会立刻得到 `ModuleNotFoundError`，而且 `brief.validate_brief_package`
会失去两个既有契约校验器——brief 就会静默降级成"只有形状没有校验"。**不要做。**

## 堆叠 PR 的合并顺序

**PR 1 —— 父亲分支 `feat/34-video-replication` → `main`**

合并前必须验：

```powershell
git switch feat/34-video-replication
python scripts\dev_check.py
python scripts\check_account_dna.py
python tests\test_workflow_contract.py
python tests\test_workflow_gate.py
python tests\test_account_dna.py
```

已知需处理：`test_gzh_pin.py` 需要 `vendor/gzh-thinktank`（见下节）；`test_windows_subprocess.py`
见单独的 Issue 草案。

**PR 2 —— `feat/content-router` → `main`，在 PR 1 合并之后**

它相对父亲只有 4 个提交、40 个文件，审查面很小：

```powershell
git log --oneline 8ff3dfa..feat/content-router
git diff --stat 8ff3dfa..feat/content-router
python scripts\dev_check.py
python tests\test_content_router.py
python tests\test_hotspot_sources.py
python tests\test_account_discovery.py
python scripts\router_e2e.py --actor "Founder"
```

PR 2 的描述里应写明：本分支不修改父亲分支的任何既有契约，只新增 `src/contentops/routing/`、
`src/contentops/hotspots/` 与三个脚本；对共享文件的改动仅是追加（`ci.yml` 三个测试步骤、
`docs/INDEX*` 一行、`check_docs.py`/`check_i18n.py` 各一行）。

## `vendor/` 与 `.runtime/easel`：如何合法获取

两者都**不是**路由器依赖——干净 worktree 里路由器三个套件全过，缺它们失败的是另外两个套件。

| 依赖 | 现状 | 合法获取方式 |
|---|---|---|
| `.runtime/easel` | 未跟踪；`test_derive_variants` 因此报告 `RUNTIME_TOOL_MISSING`（退出 4） | `python scripts\resolve_easel.py`：按锁定 tag 克隆并校验 HEAD，或下载 release tarball 按内容哈希校验；两条路都失败就 BLOCKED，绝不退回"随便一个像 Easel 的目录" |
| `vendor/gzh-thinktank` | 未跟踪；`test_gzh_pin.py` 因缺它失败 1/6 | 该目录是公众号工作流的唯一副本（原仓库已退役），靠 `scripts/gzh_pin.py` 的**内容摘要**钉住。它必须由该工作流的负责人决定入库还是提供获取脚本；**不能用未提交的本地目录冒充可复现** |

结论：要么把 `vendor/` 以受控方式入库或补一个 `scripts/fetch_gzh_vendor.py`，要么把
`test_gzh_pin.py` 明确标成"需要外部提供的 vendored 输入"。二选一，但现状（未跟踪且测试需要）
不能进入 main 后的 CI。

## 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| PR 1 因 `vendor/` 缺失在 CI 红 | PR 1 无法合并，PR 2 随之阻塞 | 先决定 vendor 的入库/获取方案；或让该套件在缺输入时 skip 并打印原因 |
| 两个 PR 同时改动同一批共享文件 | 合并冲突 | 路由器分支对共享文件只做尾部追加（已验证） |
| 父亲分支长期不合并 | 路由器分支继续累积 | 路由器分支保持 4 个提交不再扩张；新工作另开分支 |
