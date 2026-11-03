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
   `auto-short-video/scripts/assemble.py` 也已变更。Skill 路由器的第一个目录根是
   `.runtime/easel/skills/openclaw`，目录根随版本变化。
2. **tag 被强制替换。** 上游先发布 v0.3.0，随后在保持版本号不变的前提下替换了它。
   可被替换的 tag 不是固定版本。未来采用时必须记录**内容摘要**，而不只是 tag。
3. **影响面大。** 该版本加入多 Agent 执行引擎（OpenClaw / Codex / OpenCode / ACP /
   仅聊天），并改动安装、登录与产物处理——影响面远大于补丁版本。

将来采用时，走完整升级门禁，并使用按摘要固定的 Release 归档。

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