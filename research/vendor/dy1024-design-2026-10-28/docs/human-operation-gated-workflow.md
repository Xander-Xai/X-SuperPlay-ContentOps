---
status: archived
canonical: false
issue: "#34"
date: 2026-10-28
source: dy_x1024@a5952a44dbf47d44c1a4bf475e3653b542c25ac1
---

# 人工操作可行性闸门与录屏回传合同

## 目的

X•超玩1024 不再在选题确认后直接进入 Brief/脚本。每个选题先生成一份人工操作可行性预判，明确：

- 需要用户亲自做哪些操作；
- 哪些画面必须录屏、哪些信息必须隐藏；
- 选题实际声明的资源、权限、账号和本地服务要求（没有声明的要求不会被工作流凭标题臆测）；
- 失败时是换方案、改写 claim，还是停止该选题；
- 哪些步骤由工作流自动完成，哪些步骤必须由用户完成。

这份预判是“可行性决策”，不是模型成功证明，也不是生产审批。

## 新链路

```text
用户选题/热点候选
  → workflow_start.py route
  → human_operation_forecast.py draft
  → 用户审阅并 accept/reject
  → Brief / research / script / review
  → audio 锁定
  → Visual Plan
  → Visual Route
  → Assets Plan
  → human_operation_manual.py
  → 用户审阅素材操作手册并录屏
  → Assets：回传原始录屏及实际素材 intake、来源/rights/hash ledger
  → Media Generation：仅在计划要求时执行获批 provider generation（`gflow-cli i2v` 在此阶段）
  → Edit & Render：OpenChatCut 时间线、Remotion 最终合成
  → Quality → Delivery
```

## 选题后的预判闸门

```powershell
python scripts/human_operation_forecast.py draft `
  --route <route.json> `
  --output <forecast.json> `
  --guide-output <forecast.md> `
  --assessment-basis "说明本选题需要哪些额外人工操作，或为什么不需要额外操作" `
  --workflow-root D:\Projects\dy_x1024\dy_1024

python scripts/human_operation_forecast.py check --input <forecast.json>
python scripts/human_operation_forecast.py accept `
  --input <forecast.json> `
  --route <route.json> `
  --guide <forecast.md> `
  --reviewer "用户" `
  --note "已确认人工操作、录屏负担和选题特定风险" `
  --confirm
```

工作流不会因为标题里出现“模型”“部署”或其他关键词，就自动把本地模型、MCP、GPU 或显存写成固定步骤。只有选题确实需要额外实操时，才把它作为 `operation_requirements` 数据声明；如果没有额外操作，也必须用 `--assessment-basis` 写明判断依据。例如，某个选题需要一个“运行环境预检”，可以准备一个要求文件：

```powershell
@'
{
  "operations": [
    {
      "operation_id": "runtime-preflight",
      "phase": "topic-specific",
      "title": "选题指定运行环境预检",
      "surface": ["目标产品界面", "PowerShell"],
      "preconditions": ["目标版本已锁定", "资源要求已确认"],
      "resource_requirements": [{"kind": "gpu_memory_gb", "minimum": 16, "label": "选题声明的计算资源"}],
      "must_show": ["输入条件", "运行过程", "成功输出或原始错误"],
      "acceptance_criteria": ["结果可复现", "失败被如实记录"]
    }
  ]
}
'@ | Set-Content operation-requirements.json -Encoding utf8
python scripts/human_operation_forecast.py draft ... --requirements-json operation-requirements.json
```

如果该声明本身包含显存、权限或服务门槛，再把具体门槛作为这个操作的 `preconditions` 或 `resource_requirements` 交给预判器检查。机器可检查的资源不足时，报告会给出阻断、降级或换路线建议；只能由用户确认的权限/账号条件则保留为人工前置条件。没有这类声明的普通选题不会被强行增加本地部署步骤。

`workflow_gate.py check --step brief` 会拒绝没有 accepted forecast 的 Brief。

## 音频后的人工素材手册

Visual Route 完成后，在 Assets Plan 运行：

```powershell
python scripts/human_operation_manual.py --project <project> --broll-plan 04_visual/broll-plan.json
```

它读取 `04_visual/broll-plan.json`，生成：

- `04_visual/human-operation-plan.json`：机器可读的自动/人工责任、录屏要求和验收条件；
- `04_visual/human-operation-manual.md`：用户可照着执行的逐镜头操作手册。

人工操作手册是 Assets Plan 的前置/交接产物；`assets_plan` Gate 在计划和手册都存在、状态 ready、且与当前 B-roll 计划 SHA-256 一致前，不允许要求用户录屏，也不允许获取或装配素材。

用户接受手册后执行：

```powershell
python scripts/human_operation_manual.py --project <project> --broll-plan 04_visual/broll-plan.json --accept --reviewer "用户" --confirm
```

## 用户回传合同

用户回传的每个录屏属于 Assets 阶段的真实素材 intake（由 `human_operation_receipt.py` 登记并由 Assets checker 校验），不是 Media Generation provider 生成物。它应至少能证明：

1. 输入条件；
2. 实际操作；
3. 结果或原始错误；
4. 结束状态和来源 URL/文件名；
5. 没有密码、Cookie、Token、私人聊天或未授权素材。

工作流收到录屏后才执行哈希、可播放性、scene/claim 绑定、来源/权利和画面 QC。录屏失败时只能重录、降低 claim 或停止选题，不得用静态截图或生成卡片伪造运行证据。

录屏文件复制到内容包内后，由工作流登记回执：

```powershell
python scripts/human_operation_receipt.py --project <project> --operation capture-scene-01=<absolute-path-inside-project>
```

canonical `Assets` stage artifact 是 `05_assets/asset-ledger.json`；录屏回执是该阶段校验的支持证据，位于 `05_assets/human-operation-receipt.json`。没有该文件的 `received` 状态，Assets Gate 不会通过。provider generation receipt 属于独立 `Media Generation` stage artifact `05_assets/media-generation-receipt.json`。不得引入 `video_production` 伪阶段。
