---
title: MiniMax M Plan Explore 能力核验
canonical: false
type: research
status: current
issue: "#4"
milestone: M2.0
checked_at: "2026-10-04"
language: zh-CN
translation_of: research/providers/minimax-mplan-explore-capability.md
translation_status: synced
---

# MiniMax M Plan Explore —— 能力核验（M2.0，Issue #4）

> 研究材料，不是规范设计。规范事实以 `docs/CURRENT-STATE.md`、
> `docs/adr/ADR-003-minimax-plan-provider.md` 以及
> `research/providers/receipts/` 下的脱敏凭证为准。
>
> English: [minimax-mplan-explore-capability.md](minimax-mplan-explore-capability.md)

## 结论速览

| 能力 | 状态 | 一句话理由 |
|---|---|---|
| 认证 | `VERIFIED` | 订阅 Key 存在且被接受，region 已解析 |
| 额度可见性 | `VERIFIED` | 两个窗口可读；只有单个 `general` 桶，没有分模态拆分 |
| 计费来源 | `VERIFIED_INCLUDED_PLAN_QUOTA` | PAYG 余额、积分包、代金券、欠费全部为 `0.00` |
| 文本 | `VERIFIED` | 用订阅凭证可读取模型列表 |
| 图像 | `VERIFIED` | `image-01` 为 9:16 请求返回 768x1360 JPEG |
| 语音 | `VERIFIED` | `speech-2.8-hd` 返回 32 kHz 单声道 WAV，内容经 ASR 校验 |
| 音色设计 | `DOCUMENTED_BUT_NOT_TESTED` | 文档已记录；M2.0 不需要 |
| 声音克隆 | `DOCUMENTED_BUT_NOT_TESTED` | 文档已记录；M2.0 不需要 |
| H3 视频 | `NOT_ENTITLED` → `BLOCKED` | 官方指引要求 H3 使用按量或积分 Key |
| H3 参考模式 | `NOT_ENTITLED` → `BLOCKED` | 与 H3 相同的凭证规则 |
| H3-Context-IR | `DOCUMENTED_BUT_NOT_TESTED` | 文档已记录；受 H3 凭证阻断限制 |

两个模态可以安全地进入实现。一个被服务商自己的凭证规则挡住，不是我们没试。

## 实际验证了什么，以及怎么验证的

使用的权威顺序，从高到低：

1. 账号所属 region 的当前 M Plan 概览 / FAQ / 用量页面
2. 当前开发文档（视频、语音、图像 API 参考）
3. 当前官方 CLI 仓库、tag 与 skill 文件
4. 真实账号输出：`mmx auth status`、`mmx quota`、余额读取
5. 真实生成，每次都在 fail-closed 计费前置检查之后

已丢弃过时的 Token Plan Plus / Max / Ultra 命名。M Plan 已取代它：
Go、Explore、Build。

### 传输通道

| 属性 | 取值 |
|---|---|
| 官方 CLI | `mmx`，npm 包 `mmx-cli` |
| 核验版本 | `1.0.27`，tag `v1.0.27`，发布于 2026-09-29 |
| 核验时仓库 `main` | `06e47c70b76f419196678367dae62acca4c94076`，2026-09-29 |
| 安装 | `npm install -g mmx-cli` |
| 运行时 | Node.js 18+（本机为 24.16.0） |
| 使用中的 region | `cn`（国内平台） |
| Windows | 支持，已在本机验证 |
| 结构化输出 | `--output json` |
| 异步视频 | 文档支持（`--async`），被权限阻断 |

本机原本残留一个 `mmx` 启动脚本，但包目录已缺失，`npm ls -g` 里也没有这个包。
核验前先重新安装了 CLI，因此下面每一条观察都来自 `1.0.27`。

### 认证

```
subscription_credential_present: true
credential_class: SUBSCRIPTION
auth_method: api_key 保存在官方 CLI 配置中
auth_status: VERIFIED
```

本文档与凭证文件中都不包含任何 Key 值、片段或账号标识。分类只依据 Key 前缀族。

### 额度与计费语义

两个窗口，均从首次使用开始计时：

| 窗口 | 适用 | 实测剩余 |
|---|---|---|
| 5 小时 | 非视频模型 | 99% |
| 周窗口 | 全部模型，含视频 | 65% |

只暴露一个桶，名称为 `general`。不暴露绝对次数，也没有分模态拆分，
因此 ContentOps 无法计算"还剩几张图"。它只能回答"是否还有套餐额度"，
而这正是前置检查真正需要的。

视频按文档只受周窗口约束。

### 计费前置检查 —— 硬门禁

必须排除的风险不是按量付费，而是积分包。

当前官方文档说明：订阅 Key 同时消耗套餐内额度和积分包，套餐额度优先，
达到上限后**默认**从积分包扣除，且没有任何已文档化的开关可以关闭该回退。
因此"我用了订阅 Key"并不能证明只消耗了订阅额度。

唯一可证明的排除方式是积分包余额为零。实测：

| 字段 | 取值 |
|---|---|
| 按量付费账户余额 | `0.00` |
| 积分包余额 | `0.00` |
| 代金券余额 | `0.00` |
| 欠费金额 | `0.00` |

结论：`VERIFIED_INCLUDED_PLAN_QUOTA`。按量付费无法扣费，积分包也无法被扣，
因此此刻的生成可证明消耗的是套餐内额度。

两个必须强调的前提：

- 余额读取使用的是一个第一方端点，官方 CLI 自身也在调用它，但它不在公开文档索引里。
  它不是逆向出来的网页接口，应当视为可能变化实现细节。
- 因此前置检查必须在**每一次生成之前**运行，并且 fail-closed。如果余额读不到，
  或四个字段中任何一个非零，结论就是 `BLOCKED_BILLING_SOURCE_UNCERTAIN`，
  不发送任何请求。只查一次不构成充分证据。

## 实测结果

### 语音

| 属性 | 中文样本 | 英文样本 |
|---|---|---|
| 模型 | `speech-2.8-hd` | `speech-2.8-hd` |
| 音色 | `Chinese (Mandarin)_Reliable_Executive` | `English_expressive_narrator` |
| 容器 / 编码 | WAV / `pcm_s16le` | WAV / `pcm_s16le` |
| 采样率 | 32000 Hz | 32000 Hz |
| 声道 | 1 | 1 |
| 时长 | 5.503 s | 6.223 s |
| 峰值 | -1.5 dB | -0.5 dB |
| 平均 | -20.0 dB | -15.1 dB |

共列出 303 个音色 ID，其中包含大量中文（普通话）音色。同步 TTS 单次少于
10000 字符；异步长文本 TTS 另有文档。

**峰值电平是第一个质量发现。** -0.5 dB 属于合法但几乎没有余量。
进入合成之前必须加一层响度归一化门禁。

### 发音 —— 第二个质量发现

技术词汇样本，三种变体，文本完全相同，每次生成后做 ASR 回检。
ASR 只作为低成本探测器，不作为质量结论。

| 变体 | 机制 | 时长 | 结果 |
|---|---|---|---|
| A | 不加规则 | 17.41 s | `Claude` 读成 "Cloud"，`Qwen` 读成 "Quen"，`H3` 读成"H三"，`v0.2.1` 塌缩成 "V0.21" |
| B | `pronunciation_dict` + IPA | 24.58 s（+41%） | 复合名被拆开：`Claude Code` 丢词，`GitHub` 变成两个词，`LangGraph` 变成两个词，`H3` 读成 "A Three" |
| C | `pronunciation_dict` + 纯文本替换 + 文本正规化 | 18.39 s（+6%） | 采样到的每个 token 都正确，包括 `v0.2.1` 和日期 |

结论，按置信度排序：

1. `pronunciation_dict.tone[]` 是当前支持的机制，格式为 `原文/替换内容`。
   **不支持 SSML**，不要自造 SSML。
2. 对品牌名和中英混合技术词，**纯文本替换有效，而 IPA 有害**。变体 B 比什么都不做更差。
3. 不加词表时的失败模式是具体且可预测的：带连字符和驼峰的 token 会被拆成独立词。
4. ASR 回检必要但不充分。它与明显的胜负一致，但无法判断自然度、节奏与情绪。
   人工试听仍然是必须的，当前状态为 `PENDING_FOUNDER_REVIEW`。

由此推出的 ContentOps 形态：把显示文本与口播文本分开，维护一份
token → 口播形式的 `PronunciationLexicon`，按语言输出为纯文本
`pronunciation_dict` 条目。这是 M2 的设计项，M2.0 刻意不实现。

### 图像

| 属性 | 取值 |
|---|---|
| 模型 | `image-01`（另有 `image-01-live`） |
| 请求 | 768x1360，9:16 竖版，seed 42 |
| 实得 | 768x1360，容器 **JPEG**，编码 `mjpeg` |
| SHA-256 | `27f8f3d9…f062bf1` |
| 视觉检查 | 有效、非空白、无文字、无 logo、无 UI、无明显瑕疵、上下留白适合压字幕、略有柔化 |

**第三个发现，也是最容易在生产中静默出问题的一个：** 输出容器由服务商决定。
请求 `.png` 路径却拿到 JPEG 字节。任何按文件名选择解码器的消费方，
都会在一个完全有效的素材上失败。ContentOps 必须从字节嗅探容器，
图像质量门禁必须断言容器，而不是相信扩展名。

`--seed` 受支持，这给了幂等性一个真实的锚点。

## H3 视频 —— 被服务商自己的凭证规则挡住

两个当前官方来源说明 H3 需要按量或积分 Key：

- 视频生成指南，两个 region 都写明："若需要使用 MiniMax H3 或 MiniMax H3 Max，
  请点击按量购买 API"
- 官方 CLI 自己的 H3 skill（tag `v1.0.27`）："Use a standard Pay-as-you-go/Credit
  API Key for H3. Do not use an OAuth credential or Token Plan Subscription Key
  for H3"，失败处理规则为："If error `2013` says TokenPlan or Credit does not
  support H3, stop"

一个当前官方页面给出不同说法：M Plan FAQ 写明 Explore 和 Build 包含 H3 视频模型。

能同时成立的解释是：套餐内 H3 权益通过登录 MiniMax Code 应用交付，
而 **H3 的编程 CLI 与 API 路径需要按量或积分 Key**。在 `allow_payg: false`
和 `allow_credit_pack_fallback: false` 下，H3 对本仓库不可用。

状态：`NOT_ENTITLED`，结论 `BLOCKED`，**未发送任何生成，未消耗任何额度**。

这是靠阅读当前官方来源解决的，不是靠花额度试出来的。剩余风险是不对称的，
并且是被刻意接受的：如果限制性解读是错的，一次 4 秒 768P 的生成就白花了。
相比之下，官方规则明写"stop"，不值得赌。

已文档化的 H3 能力记录在此，便于权益由人工解决后 M4 可以立刻开工：

| 属性 | 取值 |
|---|---|
| 模型 | `MiniMax-H3`、`MiniMax-H3-Max` |
| 模式 | 文生视频；首帧和/或尾帧图生视频；多模态参考生成 |
| 参考输入 | 最多 9 图、3 视频、3 音频，混合合计最多 12 个文件 |
| 分辨率 | 768P / 2K（H3）；480P / 768P（H3 Max） |
| 时长 | 4-15 秒整数（H3）；5-15 秒整数（H3 Max） |
| 比例 | adaptive、21:9、16:9、4:3、1:1、3:4、9:16 |
| 提示词上限 | 7000 字符 |
| 请求体上限 | 64 MB |
| 工作流 | 创建任务 → 轮询 → 下载，完全异步 |
| 另有文档 | H3-Context-IR 提示词增强、768P → 2K 再生成 |

## 当前官方 H3 提示词指引

执行时从官方 CLI 仓库读取，仅在此总结，**不做 vendor**。

| 字段 | 取值 |
|---|---|
| 仓库 | `MiniMax-AI/cli` |
| Skill 路径 | `skill/h3-video/SKILL.md` |
| 参考文件 | `skill/h3-video/references/h3-video.md` |
| tag / 日期 | `v1.0.27`，2026-09-29 |
| `main` sha | `06e47c70b76f419196678367dae62acca4c94076` |
| 次要来源 | 平台文档中的官方 H3 特性Highlights 页面 |

提示词编译器必须遵守的实质指引：

1. 请求欠明确时按固定顺序展开：输出目标、主体与素材、时间线、场景、镜头、
   视觉基调、声音、约束。
2. 使用**两级时间线**：每个参考一个主区间，区间内再切微区间 ——
   建立、准备、核心动作、收势、停留。
3. 区间必须连续、不重叠，且最后结束时间必须等于请求时长。
4. 在每个边界维护**状态账本**，并让第 N 镜的锁定结束状态严格等于第 N+1 镜的初始状态。
5. 动作必须在 4-15 秒内物理可行；每镜一个清晰动作节拍；按动作复杂度重新分配
   时间，而不是平均切分。
6. 使用明确的镜头语言，并明确写出"保持什么 / 可以改变什么"。
7. 把硬性连续性约束与审美偏好分开陈述，并在关键不变量容易失效的时间线块中重复它。
8. 绝不静默添加品牌、台词、文字叠加或不安全内容。
9. 默认 0.5 秒精度；只有短的精确转场才用更细粒度。
10. 用户提供的完整结构化分镜必须原样保留，不得压缩或替换为通用提示词。

其中与钱直接相关、值得现在就采纳的失败处理规则：一旦存在 task id，
所有恢复动作都必须作用于该 task id；绝不会因为轮询、终端处理或下载失败
而新建一个付费任务；下载失败时重试同一个 URL，而不是重新生成。

## Easel 复用评估

在推荐任何实现之前，于执行时检查。

| 问题 | 答案 |
|---|---|
| 锁定版本 | `v0.2.1`，commit `3fe2d99` |
| 最新稳定发布 | 仍是 `v0.2.1`，发布于 2026-09-24 —— 没有更新的发布 |
| 上游 `main` | `d80b26c`，2026-10-03，领先 78 个提交 |
| 是否修改上游 | 否，也不计划修改 |

| 能力 | 分类 |
|---|---|
| MiniMax TTS / 语音 | `UPSTREAM_AVAILABLE_IN_PIN` |
| MiniMax 声音克隆 | `UPSTREAM_AVAILABLE_IN_PIN` |
| MiniMax 图像 | `UPSTREAM_AVAILABLE_IN_PIN`，provider 列表在 M3 确认 |
| MiniMax H3 视频 | `NOT_AVAILABLE` |

锁定的 Easel 已经带了一条 MiniMax 语音链路：
`skills/shared/scripts/multivoice.py` 接受 `--provider minimax`，
`skills/shared/scripts/voice_clone.py` 接受 `--provider minimax`，
`skills/shared/scripts/model_registry.py` 已注册 `minimax` 语音 provider，
包含 `MINIMAX_API_KEY`、`MINIMAX_GROUP_ID`、`MINIMAX_MODEL`、`MINIMAX_BASE_URL`。
Easel 的 `ai_video.py` 完全没有 MiniMax 相关引用。

**决策：语音复用锁定的上游。** 不要造第二个 MiniMax TTS 客户端。
ContentOps 负责上游没有的层：仅订阅凭证处理、计费前置检查、脱敏凭证、
发音词表、响度与 ASR 质量门禁、幂等性，以及无弹窗的子进程契约。

M2 有一个具体的兼容性风险：Easel 的 MiniMax 链路是按
`MINIMAX_API_KEY` 加 `MINIMAX_GROUP_ID` 编写的，那是更老的凭证形态。
它是否接受 `sk-cp-` 订阅 Key **未核验**，这是 M2 必须首先测试的事。
如果不接受，回退方案是包在官方 `mmx` CLI 外的一层薄 ContentOps 适配器，
而不是 fork。

## 实现建议

| 里程碑 | 决策 |
|---|---|
| M2 语音 | 推进。适配锁定的 Easel MiniMax TTS，补上前置检查、词表、质量门禁、凭证、幂等性 |
| M3 图像 | 推进。基于官方 CLI 的 ContentOps provider 适配器；Easel 没有 MiniMax 图像 provider |
| M4 H3 视频 | 不启动。权限上 `BLOCKED`；设计可以准备，不写代码 |
| 旧版 Hailuo 视频 | 未调查，非必需 |

由上述发现直接推导出的质量门禁：

- 语音技术项：容器有效、时长、采样率、削波、静音、
  **响度归一化**（因为服务商峰值接近 0 dB）
- 语音语义项：脚本全覆盖、数字、专有名词、术语，ASR 回检作为探测器
- 语音人工项：自然度、节奏、情绪、发音 —— 必须，不可省略
- 图像技术项：**嗅探出的**容器、可解码尺寸、宽高比
- 图像语义项：请求主体存在、无捏造事实、无游离文字
- 视频：在阻断期间不适用

真正成立的幂等性锚点：语音用 模型 + 音色 + 文本 + 词表版本；
图像用 模型 + 提示词 + seed + 尺寸；视频用 模型 + 模式 + 提示词 + 参考哈希。

重试预算：每个素材最多 2 次，且第二次必须给出具体失败原因并改变输入。

## 未知项

| 未知 | 为什么重要 | 如何关闭 |
|---|---|---|
| Easel 的 MiniMax TTS 是否接受 `sk-cp-` 订阅 Key | 决定 M2 是"适配"还是"适配器" | 在 M2 对锁定版 Easel 做一次测试 |
| 语音与图像的分模态额度成本 | 重试预算需要真实数字 | 在受控生成中观察额度变化 |
| 订阅 Key 到底能不能访问 H3 | 通往 M4 的唯一路径 | Founder 决策，或向 MiniMax 确认 |
| 音色的自然度 / 节奏 / 情绪 | 无法自动化 | Founder 试听评审 |
| 固定 seed 的图像输出是否字节稳定 | 影响幂等强度 | 再生成一次并比较哈希 |

## 刻意没有做的事

- 没有发送 H3 生成，因此没有为一个未解决的问题消耗额度。
- 没有申请、创建或使用任何按量付费 Key。
- 没有把任何 Key 值、片段、账号 ID、task ID 或私有端点写进本仓库。
- 没有写 provider 集成代码。M2.0 产出的是证据和决策，不是 provider。