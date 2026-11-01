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
- 将同一份工作转化为可发布的图文内容，而不必重做证据工作
- 在能力验证后使用 MiniMax 套餐进行语音/图片/视频生成
- 维持证据优先完整性（不编造声明）
- 为审计产出完整凭证
- 在任何发布前通过人工批准门控

## 5. 产品目标

一套内容生产系统，任何 Xander-Xai 业务仓库都可调用，把真实工作转化为可追溯、适配平台的内容——通过**两条共享证据与审核机制、随后各自进入独立生产流程的产线**：

| 产线 | 产出 | 目标平台 |
|---|---|---|
| **视频线** | MP4、封面、标题、简介、标签 | 抖音、视频号、B站 |
| **图文线** | Markdown / HTML、图片组、预览 | X、小红书、公众号、知乎 |

两条产线共享：账号定位、选题、`SourceArtifact` 证据、`ClaimLedger` 声明、权利校验，以及同一套审核原则。**分化早于渲染步骤**——视频脚本与图文大纲本身就是不同的产物；视频需要配音、分镜和合成，图文不需要。审核原则共享，但**每条产线的产物分别批准**。

内容形态与交付目标是两个独立维度。小红书和 X 也可以承载视频，B站也可以有图文。第一阶段按**内容形态**划分产线，平台适配器保持跨形态可复用。**不要按平台拆分仓库。**

**所有平台交付均为人工。** 系统止步于可审核的交付包与回执；由人发布，由人回填 URL。见 §6。

## 6. 非目标（当前阶段）

以下各条同样适用于 §5 的双产线范围。新增图文线不重新开启其中任何一条。

- 自动发布到任何平台
- 评论抓取 / ROI Agent
- 数字人 / AI 短剧
- 指标抓取 / 胜者学习
- n8n / OpenClaw 全编排
- 数据库 / 复杂 FastAPI

```config/registry/platforms.json``` 里的一行**不是**集成，Content Bundle 也**不是**发布。
新增其中任何一项都不重新开启上述任何非目标（ADR-015）。

### 6.1 人工交付收据（尚未实现）

由人发布、由人记录。下面的形状是先占位，代码尚未产出；任何字段都不得推断或
默认为 0：

```json
{
  "schema": "contentops.manual-delivery/v1",
  "bundle_id": "CB-YYYYMMDD-NNN",
  "platform_id": "douyin",
  "url": null,
  "published_at": null,
  "recorded_by": null,
  "checkpoints": {"T+2H": "unknown", "T+24H": "unknown",
                  "T+72H": "unknown", "T+7D": "unknown"}
}
```

缺失的度量写作 `"unknown"`，绝不写 `0`。只有 URL 而没有记录人，不构成交付记录。
这是占位，不是发布能力。

## 7. 当前基线

2026-11-02 在 `feat/106-easel-host-dual-line` 上验证（基于 PR #101）：

- Easel v0.2.1 固定并内容校验（982/982 blobs）。上游 v0.3.0 可用但未采用
  （Skill 路径迁移；见 UPSTREAM-EASEL）。
- Owner 已把完整 Easel 系统定为生产底座（ADR-016）。宿主只能通过回环、只读门禁启动；
  本机因缺少 FastAPI/uvicorn 报告 `HOST_BLOCKED`。未启动宿主进程，未使用账号或凭据。
- 两条已实现路径：`run_v1.py`（分镜驱动、edge-tts）与 `m5_production.py`
  （证据优先、本地旁白）。两者都通过固定版本 Easel 适配器合成。
  `project.yaml` 可绑定 Content Bundle；视频运行会在 sources 之前写
  `receipts/bundle-handoff-video.json`。
- 图文线：`contentops.copy-to-graphic/v1` 与 `scripts/graphic_package.py`
  产出停在 `AWAITING_MANUAL_REVIEW` 的人工包；它不是 HTML 渲染器或平台发布器。
- 媒体层已实现：MiniMax 语音/图片/H3、媒体收敛、media-use 适配器、计费/配额门禁、
  权利门禁。
- `tests/test_*.py` 下的每个套件都接入了 CI。此处不声明数量；
  用 `git ls-files 'tests/test_*.py' | wc -l` 读取实时值。
- 账号感知内容路由：切片 S1（#93，工作流阶段门禁）与 S2（#95，素材候选契约）
  已在 `main`；S3–S4 仍在 Issue #94 中开放。小红书与公众号仍未合并且受权利阻断。
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
- **当前实际执行面：两个文件** —— ```auto-short-video/scripts/assemble.py```
  与 ```tts.py```（仅 V1）。上游的 Skill、Agent、工作台与浏览器发布在**本仓库未接入**。
  采用其中任何一项都是独立决策，且需要取代 ADR-002（ADR-015 D1）

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
