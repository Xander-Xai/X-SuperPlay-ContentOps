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