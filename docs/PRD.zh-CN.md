---
translation_of: docs/PRD.md
language: zh-CN
translation_status: synced
---

# PRD — X-SuperPlay ContentOps 运行时

[English](PRD.md) | [简体中文](PRD.zh-CN.md)

## 1. 背景

X-SuperPlay 运营自媒体账号（抖音/小红书/B站），从真实业务工作生产证据优先的技术视频内容。此前 5 个独立平台仓库未能产出稳定结果。ContentOps 将生产整合到一个运行时。

## 2. 问题

- 无稳定视频生产流水线 → 零发布视频
- 语音质量（edge-tts）机械感 → 内容被拒
- 无跨仓库源摄取 → 每个仓库需要自定义工作
- 无 MiniMax 套餐集成 → 已购套餐未用
- 文档与代码矛盾 → 基于过时事实决策

## 3. 用户

Founder（Xander-Xai）— 需要从真实工作产出高质量视频，最少人工投入，可追溯证据，诚实质量门控。

## 4. 目标

一个统一的 ContentOps 运行时，任何 Xander-Xai 业务仓库都可调用以产出高质量、可追溯、可发布的视频。

## 5. 非目标（当前阶段）

- 自动发布到任何平台
- 评论抓取 / ROI Agent
- 数字人 / AI 短剧
- 指标抓取 / 胜者学习
- n8n / OpenClaw 全编排