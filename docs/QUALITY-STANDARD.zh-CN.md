---
translation_of: docs/QUALITY-STANDARD.md
language: zh-CN
translation_status: synced
---

# 质量标准

[English](QUALITY-STANDARD.md) | [简体中文](QUALITY-STANDARD.zh-CN.md)

> 视频和内容质量门控。无凭证 = 任务未完成。

## 视频质量门控

| 门控 | 要求 |
|---|---|
| 分辨率 | ≥1080p |
| 帧率 | ≥30fps |
| 音频 | 48kHz / 立体声 |
| 时长 | ≤5min（短视频标准） |
| 字幕 | 正确显示，无遮挡 |

## 仅用于测试的视频时长策略

**本策略只约束开发、研究、冒烟与回归用的视频请求，对生产镜头时长没有任何约束力。**
生产镜头由叙事与北极星决定，不由本规则决定。

视频是 MiniMax M Plan Explore 订阅中最贵的模态：一次 4 秒 768P 的 H3 任务消耗了
**周窗口的 7 个百分点**，而视频只计入周窗口。因此一次随意的 10 秒"快速检查"，
成本会高于最短的合法检查。

```yaml
TEST_VIDEO_DURATION_POLICY:
  preferred_seconds: [1, 3]
  effective_duration:
    if provider_min <= 3: 1-3 秒区间内最短的受支持时长
    else:                 provider_min
  never: 绝不因为"更便宜"就发送不被支持的 1 秒 / 2 秒 / 3 秒请求
  longer_than_minimum_requires:
    - test_objective
    - why_minimum_is_insufficient
    - quota_budget
  production_duration: NOT_CONSTRAINED_BY_THIS_POLICY
```

已核验的输出时长范围，2026-10-04 对照当前公开 API schema、官方 CLI 帮助与 M2.0
真实回执复核：

| 模型 | 范围 | 类型 | 有效测试时长 |
|---|---|---|---|
| `MiniMax-H3` | 4-15 | 整数枚举 | **4 秒** |
| `MiniMax-H3-Max` | 5-15 | 整数枚举 | **5 秒** |

分辨率不改变该范围（H3 的 `768P` 与 `2K` 都接受 4-15）。参考**输入**素材是另一条
约束：每段 2-15 秒，合计不超过 15 秒。

实现与测试：`src/contentops/media/test_duration_policy.py`，由
`tests/test_minimax_speech.py` 覆盖。CI 不发起任何 provider 请求。

> "测试用 4 秒"指的是该 provider **最短的合法测试时长**，
> **不表示**生产视频只能有 4 秒。

## 证据优先原则

所有声明必须可追溯到真实执行凭证。无凭证 = 声明无效。

## 人工审查门控

发布前必须有人工审查。自动化检查通过 ≠ 可发布。

## 生成图片质量（M3，Issue #20）

生成图片可以支持视频，但绝不能作为证据。

| 要求 | 规则 | 实现位置 |
|---|---|---|
| 容器已知 | PNG、JPEG 或 WEBP，仅根据魔数字判定 | `image_container.py` |
| 请求与实际均记录 | `requested_extension` 与 `detected_container` | `minimax_image.py` |
| 保留 provider 原始字节 | 只改名，绝不转码 | `minimax_image.py` |
| 尺寸合法 | `[512, 2048]`、8 的倍数，本地校验 | `image_fingerprint.py` |
| 计费可证 | 订阅、四项付费余额均为零、5 小时与周度均大于零 | `billing_guard.py` |
| 凭据绑定 | 门禁与子进程使用同一密钥 | `credentials.py` |
| 可解码且非均匀 | 亮度标准差与极差下限 | `image_qc.py` |
| 容异比 | 允许误差，不要求完全相等 | `image_qc.py` |
| 不得作为证据 | 生成资产拒绝所有事实引用角色 | `image_contract.py` |

**技术 QC 绝不对美术做肯定。** `approved` 只表示“技术上可用”，不表示美观、符合品牌或可发布。那些是人类判断；
一个能报出“可发布”的自动门禁，会训练流程去相信自己。

**空白或近乎均匀的图片不通过。** 纯色填充能正常解码，在所有天真检查眼前跟真图一样，
因此改用像素统计捕获，而不是依赖文件读不出来。

**不向模型索取关键文字。** 若询问“一张基准比较图”，模型会凭空绘制，
而假造的字形会被当成数据阅读。关键文字由后续的确定性叠加层生成。
`text_contamination_suspected` 是基于边缘密度的“可能含文字”信号，而非定论。

### 硬性失败：仅装饰用资产被当作证据

可承载事实的类型，且仅限于这三种：

| 类型 | |
|---|---|
| `REAL` | 真实录制、照片或采集 |
| `SCREENSHOT` | 真实屏幕截图 |
| `SCREEN_RECORDING` | 真实屏幕录制 |

仅装饰用的类型：

| 类型 | 可以 | 绝不可以 |
|---|---|---|
| `DIAGRAM` | 解释架构、流程、关系、概念、序列 | 作为基准、测试结果、分析指标、客户结果、UI 状态、源码事实或生产行为的证人 |
| `GENERATED_IMAGE` | 引子、封面、概念、软试、背景、过渡 | 承载任何事实声称 |
| `GENERATED_VIDEO` | 引子、主视觉、概念、过渡、难以实拍的镜头 | 承载任何事实声称 |

图表是合法且有用的资产。它负责**解释**，而不负责**证明**。
当图表用于说明某个声称时，其后的真实来源必须通过 `claim_refs` 单独可追溯。

将上述任一类登记为 `EVIDENCE`、`CLAIM_SOURCE`、`BENCHMARK_PROOF`、`TEST_RESULT`、
`ANALYTICS_PROOF`、`UI_SCREENSHOT`、`CUSTOMER_PROOF` 或 `SOURCE_CODE_PROOF`，会抛出
`GeneratedAssetEvidenceError`，**即使调用方传入 `evidence_capable=True` 也一样**。
生成资产还要求 `evidence_capable=False` 与 `receipt_ref`。

能力只能下调，不能上调：

```
调用方可以降低能力
调用方绝不能提升能力
```

“是否生成”是**内在溯源属性**，由 `kind` 推导，绝不允许覆盖：

| 内在（由 `kind` 推导） | | 用法（调用方，有边界） | |
|---|---|---|---|
| `generated` | **绝不允许覆盖** | `evidence_use` | 可覆盖 |
| | | `evidence_capable` | **仅能下调** |

```
生成性由 kind 推导，不可被覆盖
调用方可以降低能力
调用方绝不能提升能力
```

`GENERATED_IMAGE` 与 `GENERATED_VIDEO` 始终是生成的；`REAL`、`SCREENSHOT`、
`SCREEN_RECORDING` 与 `DIAGRAM` 始终不是。调用方传入冲突值时**拒绝而非静默归一**，
因为冲突意味着调用方逻辑有误、迁移有误，或有人想绕过溯源。

能力与溯源互相独立。真实材料仅作装饰使用是合法的；
把图表提升为证明不是；把真实材料标成模型生成同样不是。

这是在资产进入系统的唯一入口处抛出的领域错误，而不是一条可被提示词忽略的文档说明。
