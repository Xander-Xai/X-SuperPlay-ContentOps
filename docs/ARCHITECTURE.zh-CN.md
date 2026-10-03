---
translation_of: docs/ARCHITECTURE.md
language: zh-CN
translation_status: synced
---

# 架构

[English](ARCHITECTURE.md) | [简体中文](ARCHITECTURE.zh-CN.md)

> 系统是什么。边界在哪里。组件如何调用。

## 系统边界

```text
X-SuperPlay-OPC-Blueprint
= 业务事实来源（独立仓库）
    │
    │ Source / Proof / Permission / PD State
    ▼
X-SuperPlay-ContentOps  ← 本仓库
= 可执行内容生产运行时
    │
    ├── SourceArtifact 摄取
    ├── 证据 + 声明绑定
    ├── 内容简报 → 主脚本 → 分镜
    ├── 资产规划（真实优先，生成为次）
    ├── 媒体生成（MiniMax 套餐，实现后）
    ├── 语音合成
    ├── 视频合成（Easel assemble.py）
    ├── 自动 QC
    ├── 人工审查门控
    └── 凭证（完整来源链）
    │
    ▼
Easel v0.2.1（固定上游）
= 内容工作流 / 技能引擎
    ├── tts.py（edge-tts 封装）
    ├── auto-short-video/scripts/assemble.py
    └── 114 Skills（发现/策划/生产/发布/归因）
    │
    ▼
FFmpeg / 确定性工具
= 渲染 / 媒体工具
```

## 扩展策略

```text
ADAPTER     → 封装外部 API，不修改上游
EXTENSION   → 在 X-SuperPlay 空间新增模块
CUSTOM SKILL → 在 extensions/ 或 skills/ 新增 Easel skill
UPSTREAM PATCH → 修改 Easel 源码（需补丁文件 + 测试）
FORK        → 最后手段
```

当前：无 fork。无上游修改。```assemble_easel.py``` 是 ADAPTER（编排变通，非源码编辑）。

## ContentOps 不拥有

- 业务判断（在 OPC Blueprint）
- 商业事实（在 OPC）
- 平台发布（保持人工，人工门控）
- 指标抓取（尚未实现）
- 自动发布（明确不在范围内）