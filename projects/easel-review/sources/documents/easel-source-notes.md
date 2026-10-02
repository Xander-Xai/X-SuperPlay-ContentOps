# Easel — 真实 Source 调研笔记

> 本文件记录 `ZJU-REAL/Easel` 项目的真实公开信息，作为视频文案的证据来源。
> 引用必须可追溯到具体 commit / 文件 / 命令。

## Source

- 仓库：https://github.com/ZJU-REAL/Easel
- 本次锁定版本：v0.2.1
- Commit：`3fe2d9904c1619281ef57f81d9ee0b7854998399`

## 官方公开能力（基于 README / Skills 列表）

> 这些是仓库本身的声明。本视频会引用，但不会声称"我本地实测过"，除非本任务真的运行了对应命令。

### 已声明的工作流阶段

Discover → Plan → Produce → Publish → Attribute

### 已声明的 Skill 数量

`skill-function-mapping.md` 文档中已列出多个 Skill，
覆盖 video / image / text / audio / publish / analytics 等类别。

### 官方运行依赖（README）

- Python
- Node.js
- FFmpeg
- OpenClaw（部分 Skill 依赖）

## 本视频允许的写法

- "Easel v0.2.1 官方仓库声明的工作流包含 Discover / Plan / Produce / Publish / Attribute。"
- "skill-function-mapping.md 显示 Skill 覆盖了视频生产、字幕、配音、发布、归因等环节。"
- "README 列出本地运行需要 Python、Node、FFmpeg、OpenClaw 等依赖。"

## 本视频禁止的写法

- "我本地实测 Easel 跑通了完整流水线。" — 除非本任务真的跑通。
- "我已经成功发布到抖音 / 小红书。" — 本任务不做自动发布。
- "Easel 数字人 API 完美支持任意长视频。" — 官方未声明。

## 当前状态（2026-10-02）

- `python scripts/doctor.py` 检查：本机 Python / Node / FFmpeg / FFprobe 全部 OK。
- Easel runtime 锁定在 v0.2.1，正在初始化到 `.runtime/easel/`。