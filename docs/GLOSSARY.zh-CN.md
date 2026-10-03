---
translation_of: docs/GLOSSARY.md
language: zh-CN
translation_status: synced
---

# 术语表

[English](GLOSSARY.md) | [简体中文](GLOSSARY.zh-CN.md)

> X-SuperPlay-ContentOps 高频术语。每个术语一个规范定义。

| 术语 | 定义 |
|---|---|
| ContentOps | X-SuperPlay 可执行内容运营运行时 — 将真实业务工件转化为可追溯视频工作流 |
| Easel Runtime | 上游运行时 / 技能引擎 — 固定的 Easel 发布版本，提供 TTS、视频合成和 Provider 能力 |
| Upstream | Easel 仓库（ZJU-REAL/Easel），ContentOps 跟踪和适配的来源 |
| Pinned Release | 特定稳定 Easel 版本，锁定在 ```runtime/easel.lock.json``` — 生产运行时 |
| Capability Spike | 验证阶段，测试套餐/计划在实现前是否真能执行某操作 |
| Receipt | 机器生成的证据文件，证明特定操作已执行（如渲染、QC、测试） |
| Golden Sample | 具有已知良好输出的参考项目，用于回归测试 |
| Human Review | 发布前的最终门控 — 必须有人批准输出 |
| Production Ready | 状态指示输出已通过所有自动化门控，等待人工审查 |
| Subscription Key | MiniMax 绑定到订阅套餐的凭据（非 PAYG） |
| PAYG | 按量付费 API 计费 — 在 ContentOps 中显式禁用（```allow_payg: false```） |
| SourceArtifact | 来自真实业务源（仓库、实验、研究）的结构化输入 |
| ContentRun | 针对一个项目的视频生产流水线单次执行 |
| Adapter | 封装上游 Easel 行为而不修改上游代码的模式 |
| dev_check | 统一开发门控：```python scripts/dev_check.py``` — 运行仓库策略、文档、i18n、测试、空格检查 |