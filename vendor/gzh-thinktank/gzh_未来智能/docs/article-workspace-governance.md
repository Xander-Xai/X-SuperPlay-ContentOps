# X超玩•未来智能作品工作区治理规范

版本：`article-workspace-governance-v1`  
适用账号：`thinktank`（对外品牌：X超玩•未来智能）  
生效原则：工作流源代码与作品产物分离

机器可读合同：[`../workspace-contract.yaml`](../workspace-contract.yaml)。本文解释目录语义；脚本以合同和
`scripts/workspace_paths.py` 为执行事实源。

## 1. 目录边界

`gzh_未来智能` 是工作流源仓库，只放：Skill、脚本、配置、测试、规范、审计报告和必要的公开预设。生产文章、证据、图片、预览、草稿回执、临时脚本和发布数据统一写入外层 `production`，不得写入源仓库的 `drafts/`、`outputs/` 或任意临时目录。

作品默认写入工作流同级的外部 artifact root：

```text
<GZH_ARTIFACT_ROOT>\
├─ active\       # 正在制作的文章工作区
├─ delivered\    # 已完成交付/草稿提交后仍需保留的作品
├─ archive\      # 观察期结束后的只读归档
├─ quarantine\   # 异常、待人工判断或安全隔离对象
├─ registry\     # workspace-index.json、路由登记、锁文件
├─ inbox\        # 经批准后放入的 handoff/用户材料副本
└─ tmp\          # 可重建的跨文章临时缓存
```

默认 `GZH_ARTIFACT_ROOT` 为工作流目录外层的 `production`；也可通过环境变量改变根目录。环境变量指向工作流仓库内部时一律阻断。

## 2. 编号与命名

每篇文章由 `matrix_init.py` 自动编号，不能手写目录名：

```text
THK-YYYYMMDD-NNN-标题slug
```

- `THK`：固定 thinktank 账号前缀；
- `YYYYMMDD`：工作区创建日期；
- `NNN`：当天从 `001` 开始的原子递增序号，由 `registry/workspace-index.json` 登记；
- `标题slug`：标题的稳定短 slug，仅用于人读，不作为唯一身份。

示例：`THK-20260813-001-qlora-量化微调全解`。

工作区内部的唯一事实源是 `workspace-manifest.json` 的 `workspace_id`，`matrix-state.json`、`article.yaml`、路由和所有回执必须绑定同一 ID。

## 3. 工作区内部结构

标准门禁产物保留在文章工作区根部，因为现有检查器和发布器以文章目录为输入；它们已经在外部 root，不会污染工作流源仓库：

```text
THK-...-slug/
├─ workspace-manifest.json  # 身份、生命周期、目录契约
├─ article.yaml             # 标题/账号/发布模式
├─ matrix-state.json        # 十道门禁状态
├─ routing.yaml             # 本篇路由副本
├─ article.md / article.html / draft.md
├─ evidence/ source-snapshots/ imgs/ preview-slices/
├─ work/                    # 调研脚本、一次性转换器、调试输出、日志
├─ exports/                 # 对外交付副本；只从通过门禁的产物复制
└─ snapshots/               # checkpoint/reopen 的快照
```

根部只允许工作流标准 artifact；新产生的临时文件、实验脚本和命令输出必须放入 `work/`。工作区审计会阻断未分类的根部文件。

## 4. 生命周期

```text
registry reservation → active → final_reviewed → delivered → archive
                                      └────────────→ quarantine（异常/待判断）
```

- `active`：制作中，只能有一个本篇工作区；
- `delivered`：主稿完成并已提交草稿箱/交付，保留回执；
- `archive`：只读长期留存，不再作为新稿输入；
- `quarantine`：凭证、异常输出、未确认复用材料等隔离，不能被工作流读取；
- 删除前必须有 registry 记录、SHA-256、保留期限和人工批准。普通作品默认可逆归档，不自动永久删除。

## 5. 正确调用方式

```powershell
python scripts/route_content.py --interactive
python scripts/matrix_init.py --route <外部路由文件>
# 输出：<GZH_ARTIFACT_ROOT>\active\THK-...-slug
python scripts/workspace_audit.py --check
python scripts/workflow_gate.py --article <上述外部工作区> --stage <stage> --advance
python scripts/workspace_lifecycle.py --workspace <上述外部工作区> --to delivered
```

禁止：`python scripts/matrix_init.py --root drafts ...`、在工作流根目录手工创建文章目录、把过程脚本和图片放在工作流 `scripts/` 或 `asset-library/` 中。

## 6. 需要特别隔离的内容

- 凭证：只能位于仓库外的凭证路径，禁止复制到工作区；
- 用户 handoff：先复制到外部 `inbox/handoff/<id>/`，通过 `validate_handoff.py` 后才能引用；
- 外部模型请求：提示词计划和请求指纹写入文章工作区，密钥与未经批准的正文不外发；
- 缓存：可重建缓存进外部 `tmp/` 或工作区 `work/`，不进入 registry；
- 归档：不把归档目录加入 `skills/`、`drafts/` 或工作流 manifest 的运行时输入。

## 7. 完成定义

一次制作完成后必须满足：工作流仓库没有新增作品文件；外部工作区有 workspace manifest、十道门禁回执和完整 provenance；`workspace_audit.py`、`workspace_hygiene.py`、`validate_matrix.py` 全部通过；只有 `delivered/` 或 `archive/` 中的副本被视为作品存档。
