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

## 4. 待完成任务（Jobs-to-be-Done）

- 将任何业务仓库的工作转化为可发布视频
- 在能力验证后使用 MiniMax 套餐进行语音/图片/视频生成
- 维持证据优先完整性（不编造声明）
- 为审计产出完整凭证
- 在任何发布前通过人工批准门控

## 5. 产品目标

一个统一的 ContentOps 运行时，任何 Xander-Xai 业务仓库都可调用以产出高质量、可追溯、可发布的视频。

## 6. 非目标（当前阶段）

- 自动发布到任何平台
- 评论抓取 / ROI Agent
- 数字人 / AI 短剧
- 指标抓取 / 胜者学习
- n8n / OpenClaw 全编排
- 数据库 / 复杂 FastAPI

## 7. 当前基线

2026-11-01 在 ```main``` 上验证（PR #89）：

- Easel v0.2.1 固定并内容校验（982/982 blobs）。上游 v0.3.0 可用但未采用
  （Skill 路径迁移；见 UPSTREAM-EASEL）。
- 两条已实现路径：`run_v1.py`（分镜驱动、edge-tts）与 `m5_production.py`
  （证据优先、本地旁白）。两者都通过固定版本 Easel 适配器合成。
- 媒体层已实现：MiniMax 语音/图片/H3、媒体收敛、media-use 适配器、计费/配额门禁、
  权利门禁。
- 31 个测试套件（704 个顶层 `test_*` 函数，另有列表驱动与 unittest 风格套件）。
- 账号感知内容路由、账号 DNA、工作流门禁、小红书、X、公众号**未合并**
  （PR #49 及其他分支）。
- 语音：edge-tts（V1）与 Windows SAPI（M5）；两者都非生产级。
- 0 个已发布视频；所有结果停留在 `PENDING_FOUNDER_REVIEW`。

## 8. 功能需求

| ID | 需求 | 本分支状态 |
|---|---|---|
| FR-1 | 从任何 Xander-Xai 业务仓库摄取 SourceArtifact | **部分** — M5 摄取仓库文档/锁；跨仓库适配器未合并 |
| FR-2 | 从证据生成主脚本（LLM 起草，证据校验） | M5 fixture 路径**已实现**；创作仍属编辑工作 |
| FR-3 | 产出带逐镜来源的结构化分镜 | **已实现** |
| FR-4 | 通过 MiniMax 套餐生成语音（回退：edge-tts） | **已实现**，`PENDING_FOUNDER_REVIEW` |
| FR-5 | 通过 MiniMax 套餐生成图片 | **已实现**，`PENDING_FOUNDER_REVIEW` |
| FR-6 | 通过 MiniMax 套餐生成视频片段（配额受限） | **已实现**（H3 子集已验证），`PENDING_FOUNDER_REVIEW` |
| FR-7 | 通过 Easel assemble.py 合成最终视频（不修改上游） | 通过适配器**已实现** |
| FR-8 | 运行自动 QC（技术 + 内容 + 事实） | 技术/证据**已实现**；内容/事实仍由人工判断 |
| FR-9 | 人工审核门控（100 分评分卡） | **门控已实现；尚未被满足** |
| FR-10 | 每次运行产出完整凭证 | **已实现** |

## 9. 非功能需求

| ID | 需求 |
|---|---|
| NFR-1 | Windows 一等公民（路径、PowerShell、UTF-8、FFmpeg） |
| NFR-2 | Git 中无密钥 |
| NFR-3 | 无 PAYG 回退（仅订阅） |
| NFR-4 | 幂等生成（内容哈希指纹） |
| NFR-5 | 配额感知调度（无无限重试） |
| NFR-6 | 诚实凭证（回退永不报告 production_ready） |

## 10. SourceArtifact 合约

见 [SOURCE-ARTIFACT-CONTRACT.md](SOURCE-ARTIFACT-CONTRACT.md)。

## 11. ContentRun 合约

状态机：SOURCE_CAPTURED → SOURCE_NORMALIZED → EVIDENCE_EXTRACTED → CLAIMS_BOUND →
CONTENT_BRIEF_CREATED → MASTER_SCRIPT_CREATED → STORYBOARD_CREATED →
ASSET_PLAN_CREATED → MEDIA_ASSETS_READY → VOICE_READY → VIDEO_COMPOSED →
TECHNICAL_QC → CONTENT_QC → FACT_QC → HUMAN_REVIEW → PRODUCTION_READY。

## 12. MediaProvider 合约

见 [MEDIA-PROVIDER-CONTRACT.md](MEDIA-PROVIDER-CONTRACT.md)。

## 13. MiniMax 订阅要求

- `billing_mode: subscription`
- `allow_payg: false`
- 实现前必须完成能力验证（Issue #4）
- 凭证必须记录 quota_before/after
- `MANUAL_ONLY` 对不支持的能力是有效状态

## 14. Easel 集成

- 固定 v0.2.1，Release 归档，内容校验
- 扩展优先级：ADAPTER > EXTENSION > CUSTOM SKILL > PATCH > FORK
- 不修改上游源码
- 升级需要 Founder 批准 + 回归套件

## 15. 质量标准

见 [QUALITY-STANDARD.md](QUALITY-STANDARD.md)。

## 16. 人工门控

- 自动 QC PASS ≠ 生产就绪
- Founder 审核使用 100 分评分卡
- 硬失败阻止 production_ready
- 见 [ADR-005](adr/ADR-005-human-approval.md)

## 17. 安全

- Git 中无 API key、cookie、token
- `.env.example` 只有变量名
- 凭证必须脱敏
- `docs/ai-provider-selection.md` 保持 gitignored（商业策略）

## 18. 配额 / 资源模型

- 视频：每次运行最多 N 条，每日最多 M 条，每镜最多 R 次重试
- 图片：真实素材基线 50-70%，AI 生成 0-20%
- 语音：订阅配额记入凭证

## 19. 错误 / 回退模型

- 供应商失败 → LocalFallbackProvider
- 回退在凭证中记录 `quality_impact`
- 回退永不报告 `production_ready: true`
- 配额耗尽 → 转向真实资产，绝不 PAYG

## 20. 验收标准

见 [DEVELOPMENT-PLAN.md](DEVELOPMENT-PLAN.md) 的里程碑退出标准。

## 21. 发布

M0 → M1 → M2.0 → M2-M4 → M5 → M6

## 22. 终止 / 回滚条件

- MiniMax 套餐不支持程序化 API → MANUAL_ONLY
- 连续 3 次 E2E 失败 → HOLD，根因分析
- Founder 审核拒绝所有输出 → STOP，重新评估
