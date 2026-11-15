---
translation_of: docs/UPSTREAM-EASEL.md
language: zh-CN
translation_status: synced
---

# 上游 Easel 策略

[English](UPSTREAM-EASEL.md) | [简体中文](UPSTREAM-EASEL.zh-CN.md)

> X-SuperPlay-ContentOps 如何关联 Easel 上游。

## 核心原则

```text
生产仅跟踪稳定发布。
上游 main 作为早期预警信号监控，
不作为生产运行时消费。
```

## 当前固定版本

| 属性 | 值 |
|---|---|
| 仓库 | https://github.com/ZJU-REAL/Easel |
| Tag | v0.2.1 |
| Commit | ```3fe2d9904c1619281ef57f81d9ee0b7854998399``` |
| 发布日期 | 2026-09-24 |
| 锁文件 | ```runtime/easel.lock.json``` |
| 本地路径 | ```.runtime/easel/```（gitignored） |
| 验证 | 982/982 blob SHA-1 匹配 |
| 上游稳定版 | v0.3.0（2026-10-12）—— **未采用**（见下文 *v0.3.0 差异*） |

## 规则

1. **禁止自动升级。** 上游升级需要 Founder 批准。
2. **禁止修改上游。** 仅通过 ADAPTER 模式扩展。
3. **禁止 fork。** Fork 是最后手段，需要 ADR。
4. **禁止 main 作为生产。** 上游 main 是兼容雷达，不是部署源。

## Easel 兼容矩阵

| Easel 领域 | ContentOps 依赖 | 回归要求 |
|---|---|---|
| TTS | 高 | 语音冒烟测试 |
| assemble/video | 关键 | 3 个黄金渲染 |
| Windows subprocess | 高 | Windows CI/本地 |
| model registry | 中 | Provider 合约 |
| doctor | 中 | doctor 回归 |
| gateway | 中（目标宿主） | gateway 测试；禁止直接运行 |
| publishing | 中（目标宿主），执行仍拒绝 | 门禁测试 |
| Web Workbench | 中（目标宿主），只读门禁 | 宿主门禁测试；禁止直接 `0.0.0.0` |

## 上游 Delta 台账

| 上游 | ContentOps | 决策 |
|---|---|---|
| Easel v0.2.1 | 固定 | 生产 |
| Easel v0.3.0 | 已发布，未采用 | **高**风险差异 —— 见下文（ADR-012 D3） |
| Easel main | 监控 | 不消费为生产 |
| 下一个 release | 待定 | 兼容门控 |

## v0.3.0 差异（2026-11-01 实测）

| 属性 | 值 |
|---|---|
| 发布日期 | 2026-10-12 |
| 与当前固定版本的距离 | 158 个提交、300 个文件变更 |
| 对本仓库是否破坏性 | **是** |
| 决策 | 不采用（ADR-012 D3） |

三个事实决定了它：

1. **Skill 路径迁移。** 全部 Skill 从 `skills/openclaw/` 迁到 `skills/builtin/`，
   `auto-short-video/scripts/assemble.py` 也已变更。ContentOps 合成、卡片、文章和
   skill 目录适配器现已同时支持两个根目录，生产 pin 优先使用 `openclaw`。路径与守卫
   定向测试通过，但这不代表渲染或运行时验收通过。
2. **tag 被强制替换。** 上游先发布 v0.3.0，随后在保持版本号不变的前提下替换了它。
   可被替换的 tag 不是固定版本。未来采用时必须记录**内容摘要**，而不只是 tag。
3. **影响面大。** 该版本加入多 Agent 执行引擎（OpenClaw / Codex / OpenCode / ACP /
   仅聊天），并改动安装、登录与产物处理——影响面远大于补丁版本。

将来采用时，走完整升级门禁，并使用按摘要固定的 Release 归档。

v0.3.0 的 `web/app.py` 还新增设置／bootstrap、gateway 重启、本地 Agent／模型选择及制品归档
路由。ContentOps 宿主仍拒绝这些路由，代表性拒绝测试位于 `tests/test_easel_host_guard.py`。
v0.3.0 依赖清单新增 `requests>=2.32,<3` 及广泛的媒体／运行时依赖；候选尚未安装完整依赖，
也未通过 `pip check` 验证。

候选本地合成、卡片审计、文章校验均提供显式 `--workbench-runtime` 开关，共用
`resolve_easel_workbench()`；只有上游、overlay 源文件和生成画像验证通过才会返回候选路径。
默认命令仍选择 v0.2.1 生产 runtime。

Windows 候选入口：

```powershell
python scripts/assemble_easel.py projects/<项目> --workbench-runtime --out-name easel
python scripts/render_article.py projects/<项目> --workbench-runtime
```

候选视频写入项目内 `work/easel-v030-candidate/<运行编号>/final/`，文章预览写入
`work/easel-v030-article/<运行编号>/`；回执分别写入项目的 `receipts/`。命令要求已有
项目输入以及校验通过的候选 runtime。当前修改尚未执行或验收；候选输出仍须经过 QC 和
人工审核，保持 `production_ready=false`、`publish_authorized=false`。这些命令不证明
Windows Agent 隔离或执行能力。

## 升级门控

```text
获取新版本
    ↓
验证来源
    ↓
运行上游 diff 分析
    ↓
运行单元测试
    ↓
运行 Windows 测试
    ↓
运行 3 个黄金渲染
    ↓
比较凭证
    ↓
人工审查
    ↓
Founder 批准
    ↓
更新锁文件
```

任何步骤失败 → 保持旧版本。

## 宿主接管（ADR-016，2026-11-02）

Owner 已把完整 Easel 系统定为生产底座。这改变了**目标**面，但不改变固定版本：
v0.2.1 仍只读，未授权升级 v0.3.0。宿主只能通过 `src/contentops/easel/`
在回环地址上以只读白名单启动；上游 `0.0.0.0`/`CORS *` 入口不会被直接执行。
上游存在某项能力，仍不等于本仓库已验证它。

## 上游监控

```bash
python scripts/check_easel_upstream.py
```

监控脚本只做：检测 → 分类 → 报告。绝不修改锁文件、下载替换生产 Easel、或打开自动升级 PR。

## 工作台实例

Owner 2026-11-12 的决定是用一套成熟的 Easel 作底座并在此基础上微调，而不是继续把
固定的 v0.2.1 当库调用。当前候选于 2026-11-13 从完整 commit 归档重建；此前的解压实例
作为历史快照原样保留：

```
D:\Projects\_worktrees\easel-v030-rebuild-20261113b  清单记录的 v0.3.0 候选 + 调优层
D:\Projects\Easel-Workbench                         此前的解压快照，保留
.runtime/easel                                       （本仓库）生产引擎，v0.2.1
```

| 属性 | 值 |
|---|---|
| 版本 | v0.3.0，commit `bb3c8ff0463f36c202454d74171682ba6e470cb1` |
| 上游树摘要 | `c26fc96a653c0ff25ef3bc7486eee372c81f44e67d5ff2c30f1786c63c7d4ec8` |
| skill 根 | `skills/builtin/`（v0.3.0 已从 `skills/openclaw/` 迁出） |
| 调优层记录在 | `runtime/easel-workbench-overlay.json` |
| 校验命令 | `python scripts/verify_easel_runtime.py --overlay` |
| 干净重建 | `python scripts/rebuild_easel_workbench.py --destination <新的绝对路径>` |
| 前端 | 已完成 `npm ci` 和 `npm run build`；完整 dist 清单见 `runtime/easel-workbench-frontend-build.json` |
| 宿主状态 | 2026-11-13 历史记录：不带 `b` 的较早候选因额外文件而失败关闭；独立的 `20261113b` 候选随后通过当时记录的源码、overlay 和前端检查。离线宿主曾完成画像、草稿和回执流程并停止。此后代码改动尚未重新运行，浏览器界面、真实 Agent 隔离和 gateway 执行仍未验证。详见 `projects/easel-live-ui-check-20261113-path-bound/receipts/local-acceptance-closeout.md` 及同目录 `windows-plan-status-20261114.md`。 |

重建命令按完整固定 commit 下载上游归档，拒绝链接／特殊文件和路径穿越，逐项校验上游 blob，
只复制仓库自有 skill 源文件，并从账号 DNA 重生成画像，再使用生成画像摘要复核。目标必须位于
现存父目录下且尚不存在；命令不会覆盖已有目录。重建命令本身不会安装 npm 包或构建前端；当前
候选已另行完成 `npm ci` 和 `npm run build`，并记录 dist 清单。复核其他重建实例时，显式传入
`python scripts/verify_easel_runtime.py --overlay --generated-profiles --workbench <绝对路径>`。
`--workbench` 会覆盖 overlay 清单中的实例路径；默认校验清单指定的实例。启用
`--generated-profiles` 时还会依据当前账号 DNA 校验画像。

`runtime/easel-workbench-upstream-tree.json` 保存上游路径和 Git blob 摘要；只有完整树摘要与条目数
均匹配 overlay 清单时才会使用，之后仍会逐项比较本地源码和调优文件。可用
`python scripts/cache_easel_upstream_tree.py` 从公开网络生成，命令不会覆盖现有索引。
新增索引后的离线启动路径尚未实际运行。

**两棵树、两个角色。** `.runtime/easel/`（v0.2.1）是流水线调用、所有回执锚定的
**生产引擎**；`D:\Projects\_worktrees\easel-v030-rebuild-20261113b` 是清单记录的 v0.3.0
**工作台候选**，此前的 `D:\Projects\Easel-Workbench` 快照仍原样保留。两者刻意分开：调优工作台
绝不能挪动生产 pin，挪动生产 pin 必须走完整升级门。

**为什么用校验模式而不是「放宽比对」。** 逐字节比对无法表达「上游加上我的改动」：
任何本地差异都是 MISMATCH；而放宽比对会让未登记的改动变得不可见。所以 overlay 模式
保留完整比对，只减去记录里点名的部分：

- **上游基线**必须与 pin 的 commit 逐字节一致；
- 每个已存在的调优文件都必须登记 SHA-256 且与记录匹配；
- 其他任何差异仍然是失败。

生成文件（包括提供给浏览器的前端构建产物）不在比较范围内，因此该校验不能证明前端产物的来源。
工作台宿主另要求 `runtime/easel-workbench-frontend-build.json`：清单绑定前端构建与固定源码
commit、`package-lock.json`、Node/npm 版本、审核过的 `npm run build` 命令及完整 `dist` 文件清单。
清单缺失或产物变更都会阻断宿主启动以及浏览器页面／资源读取。该清单是完整性回执，不是密码学签名。

这使调优可审计——记录点名了哪些文件是我们的，其他地方一改仍然会被抓到。
有测试钉住这一点：只要出现一个**未登记**的差异，overlay 套件就会失败。

**调优绝不是绕过门禁的理由。** 工作台仍然跑在 `src/contentops/easel/` 之后：
回环绑定、逐项审计的读取白名单，且上游 publish / login / 凭据 / settings / env-install / delete
路由在上游之前一律拒绝。候选还提供 ContentOps 自有的离线框架、证据草稿和 Agent 工作区准备／取消／结果收集接口；读取和写入均绑定已有项目和账号。这些接口不启动 Agent，也不调用模型或 gateway。调优过的工作台不构成发布授权。

## 历史 clone 仍在磁盘上

`Easel/`（commit `4b9c03c`，不是生产 pin）不被生产解析器接受。两个本地
video-script 文件已救入工作台调优层；原始 clone 和其未提交工作尚未删除。此前观察到的
环境泄漏来源尚未确定。

工作台候选的分阶段边界见 [ADR-022](adr/ADR-022-easel-v030-workbench-candidate.md)。
