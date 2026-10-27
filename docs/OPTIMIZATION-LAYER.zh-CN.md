---
translation_of: docs/OPTIMIZATION-LAYER.md
language: zh-CN
translation_status: synced
---

# 优化层

[English](OPTIMIZATION-LAYER.md) | [简体中文](OPTIMIZATION-LAYER.zh-CN.md)

> 把外部信号、人工反馈和生产数据变成有优先级的流程改动。这是一个决策层，
> 不是第二套生产系统。

## 它是什么

优化层把四类输入变成一个排序后的待办：

| 输入 | 例子 | 入口 |
|---|---|---|
| 外部信号 | X 帖子、GitHub 仓库 | `config/optimization/signals.json`（`X`、`GITHUB`） |
| 人工信号 | Founder 评审、观众反馈 | `FOUNDER`、`VIEWER` |
| 生产信号 | QC 凭证、实测 skill 结果 | `PRODUCTION` |
| 平台信号 | 浏览、收藏、评论、咨询 | `PLATFORM_METRIC` |

它对每个候选打分、套用策略、记录决策。真正的视频产线仍由 ContentOps 拥有；
优化层不渲染、不发布。

## 它不是什么

- 不是第二套生产系统；
- 不替代凭证、QC 或人工评审；
- 不编造数据。没有真实发布 URL 和指标前，`MEASURE` 和 `LEARN` 保持
  `BLOCKED`；
- 不走 GPU。需要本地 GPU 模型的候选会被降级为 `DEFER`。

## 飞轮

```
SIGNAL -> NORMALIZE -> SCORE -> DECIDE -> EXPERIMENT -> RESULT -> SHIP
   ^                                                              |
   |                                                              v
 LEARN <---------------- MEASURE <-------------------------- PUBLISH
```

- **SIGNAL**：记录帖子/仓库/反馈/凭证，附链接与指标。
- **NORMALIZE**：映射到受影响阶段（`body`、`claims`、`audio`、`captions`、
  `architecture`、`measurement`、`feedback`）。
- **SCORE**：`priority = 2*impact + evidence - effort - risk`。
- **DECIDE**：`ADOPT`、`EXTEND`、`BUILD`、`DEFER`、`REJECT`。
- **EXPERIMENT**：一次只改一个变量；结果写成凭证。
- **SHIP**：带测试的流程改动。
- **MEASURE**：真实发布 URL 加平台指标。
- **LEARN**：Founder/观众反馈进入下一轮信号。

## 决策规则

| 决策 | 含义 |
|---|---|
| `ADOPT` | 使用已有能力，必须有可链接的 GitHub 来源和证据 |
| `EXTEND` | 借用已有能力的一部分，不引入第二套栈 |
| `BUILD` | 实现缺失的、归我们所有的能力 |
| `DEFER` | 值得做，但被凭据、数据或后续阶段卡住 |
| `REJECT` | 会重复生产系统或违反策略 |

满足任一条件时，`ADOPT` 会被降级为 `DEFER`：

- 没有可链接的 GitHub 仓库；
- `evidence < min_evidence_score`（默认 2）；
- `gpu_required: true`。

降级和原因会写进报告，不会静默改写提案。

## 文件

```
config/optimization/
  policy.json          # 权重、下限、允许的决策、飞轮阶段
  signals.json         # X/GitHub/Founder/生产/平台输入
  backlog.json         # 候选、声明的分数与决策
  flywheel.json        # 当前周期状态与阻塞阶段
  backlog-evaluated.json  # --write 生成
  optimization-report.json # --write 生成
scripts/optimization_cycle.py  # CLI
src/contentops/optimization/   # 评分、校验、排序
tests/test_optimization_layer.py
```

## 命令

```powershell
python scripts/optimization_cycle.py            # markdown 报告
python scripts/optimization_cycle.py --json     # 机器可读报告
python scripts/optimization_cycle.py --write    # 写出评估产物
python scripts/optimization_cycle.py --flywheel # 当前周期状态
```

退出码 `2` 表示信号/候选格式错误或策略拒绝。

## 当前周期（2026-10-27）

- 9 个信号，12 个候选。
- 最高采纳：`CAND-001` HyperFrames 正片动效，优先级 12。
- 下一个构建：`CAND-002` 最小 Claim Ledger，优先级 8。
- `MEASURE` 与 `LEARN` 为 `BLOCKED`：还没有真实发布 URL。
- `OpenMontage` 与 `MoneyPrinterTurbo` 作为重复生产系统被 `REJECT`。

## 添加信号

1. 追加信号，包含 `source`、`captured_at`、`title`、`observation`、
   `affected_stage`、`evidence` 和可选 `metrics`。
2. 添加候选，包含 `signal_ids`、1–5 分、`gpu_required` 和声明决策。
3. 运行 `python scripts/optimization_cycle.py`，读实际生效的决策。
4. 之后才写代码。被降级为 `DEFER` 的候选不是“现在就去实现”的指令。

## 度量交接

人工发布后：

1. 在 `publish-receipt.json` 填真实 URL 与时间；
2. 在 `metrics-snapshot.json` 填平台只读数据；
3. 追加 `PLATFORM_METRIC` 与 `VIEWER` 信号；
4. 运行周期；下一轮待办反映真实使用，而不是猜测。
