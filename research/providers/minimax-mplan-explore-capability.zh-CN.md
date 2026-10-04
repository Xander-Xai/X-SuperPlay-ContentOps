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
| H3 视频 | `VERIFIED` | 用订阅 Key 真实创建 `MiniMax-H3` 任务并成功 |
| H3 参考模式 | `DOCUMENTED_BUT_NOT_TESTED` | 文档已记录，同一凭证可达，但未实测 |
| H3-Context-IR | `DOCUMENTED_BUT_NOT_TESTED` | 文档已记录；未实测 |

三个生成模态现在在订阅下全部 `VERIFIED`，包括视频。早期版本把 H3 记为
`NOT_ENTITLED`，那个判断过强 —— 原因与纠正过程见 H3 章节。

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
| 异步视频 | 实测可行：创建 → 轮询 → 下载 |
| 已文档化的公开 API | 视频使用，因为 CLI 无法设置分辨率 |

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
因此此刻的生成可证明消耗的是套餐内额度。视频后来端到端验证了这一点：
套餐额度下降，而四项付费余额始终为零。

### 余额读取是一项未文档化的依赖

这四个余额字段来自一个本仓库确实以字面量形式持有的路径：API base 之下的
账户余额端点。诚实地分类它是：

```
UNDOCUMENTED_FIRST_PARTY_IMPLEMENTATION_DEPENDENCY
```

| 属性 | 取值 |
|---|---|
| 第一方 | 是，MiniMax 自有 API |
| 官方 CLI 是否使用 | 是，`mmx-cli` 为同一目的调用它 |
| 是否列在公开 API 文档中 | **否** |
| 是否可能无通知变更 | 是 |
| 使用范围 | 仅研究用途，除非单独验收后才可用于生产 |
| 失败时的行为 | fail closed |

它是一个依赖，而且确实在仓库里，所以把它描述成"仓库不含端点字面量"是假的。
它唯一的正当理由是目前找到的唯一能观察积分包余额的途径，而积分包余额正是
"只消耗订阅额度"得以被证明的关键。所有失败模式都是硬阻断：网络错误、
schema 变更或字段缺失。读不到余额时绝不等同于零。

生产使用（若被单独验收）必须封装在唯一的 `BillingGuard` 之内，配套基于脱敏
fixture 的契约测试，并为 MiniMax 将来提供官方等价接口准备好迁移路径。
它不得散落在 provider 代码中，也不得悄悄变成永久的生产契约。

另外两个必须强调的前提：

- 前置检查必须在**每一次生成之前**运行，并且 fail-closed。如果余额读不到，
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

## H3 视频 —— 真实账号上 `VERIFIED`

本节取代早期"H3 为 `NOT_ENTITLED`"的结论。那个判断过强，纠正过程值得记录，
而不是悄悄改掉。

### 文档冲突确实存在

两个当前官方来源互相矛盾：

| 来源 | region | 指名的产品 | 说法 |
|---|---|---|---|
| M Plan 概览 | global 与 CN | **M Plan** | Explore 和 Build 包含 H3；在 API 请求或工具配置中选择模型 |
| 视频生成指南 | global 与 CN | 未指明 | "若需要使用 MiniMax H3 或 MiniMax H3 Max，请点击按量购买 API" |
| 官方 CLI H3 skill，tag `v1.0.27` | 不适用 | **Token Plan** | "Do not use an OAuth credential or Token Plan Subscription Key for H3"；失败规则："If error `2013` says TokenPlan or Credit does not support H3, stop" |

2026-10-04 复核。CN M Plan 概览仍为 `视频模型 | 不可用 | 可用 H3 | 可用 H3`。

决定性的细节是**产品名**。CLI skill 的禁止条款是针对 **Token Plan** 写的，
并且明确点出了 `2013` 这一错误类。M Plan 已取代 Token Plan，而 M Plan 页面才是
判断"当前订阅包含什么"的更新权威。把 Token Plan 时代的限制当作"M Plan 订阅
不含该模型"的证明，是一种推断，不是证据。

因此在账号实测之前，诚实的状态是 `BLOCKED`，理由 `OFFICIAL_DOC_CONFLICT` ——
而不是 `NOT_ENTITLED`，后者断言了一个没人核对过的事实。

### 账号实际做了什么

一次授权的创建请求，没有自动重试：

| 字段 | 取值 |
|---|---|
| 模型 | `MiniMax-H3` |
| 模式 | 文生视频（T2VA） |
| 请求 | 4 秒、`768P`、`9:16` |
| 任务已创建 | **是**，HTTP 200，无错误体 |
| 任务引用 | 加盐哈希前缀 `082bb142725f`（不记录原始 ID） |
| 轮询结果 | `running` ×6 → `succeeded` |
| 已下载 | 是，231,770 字节 |
| SHA-256 | `37749196a11a5e5d9e0e52ad5e95abdc93ea91cd691db8fa43f213839404d7ea` |

`ffprobe` 得到的实际属性：

| 属性 | 取值 |
|---|---|
| 视频编码 | `h264`，768x1344，24 fps，107 帧 |
| 时长 | 请求 4 秒，实得 4.458 秒 |
| 音频编码 | `aac`，未请求音频却存在 |
| 宽高比 | 实得 0.5714，请求 9:16 为 0.5625 |

三个运行期发现：

1. **订阅 Key 可以用于 H3。** 官方 CLI skill 的禁止条款不适用于 M Plan。
   照字面执行那份 skill 的人会错误地认为视频不可用。
2. **官方 CLI 无法请求 768P。** `mmx video generate` 没有分辨率开关，传入
   `--resolution 768P` 会被**静默丢弃**：一次 `--dry-run` 显示发出的载荷里
   仍然是 `"resolution": "2K"`。对付费 API 来说，静默丢标志本身就是隐患。
   因此 768P 实测使用了**已文档化的公开 API** `POST /v2/video_generation`，
   这正是能力缺口场景下被允许的传输方式。
3. **实得尺寸是近似的。** 请求 9:16，实得 768x1344。合成门禁必须断言容差，
   而不是精确相等。

### 视频的计费证据

这是整份审计中最强的计费证据，因为生成确实成功了：

| 字段 | 之前 | 之后 |
|---|---|---|
| 5 小时窗口剩余 | 99% | 99% |
| 周窗口剩余 | **65%** | **58%** |
| 按量付费余额 | `0.00` | `0.00` |
| 积分包余额 | `0.00` | `0.00` |
| 代金券余额 | `0.00` | `0.00` |
| 欠费金额 | `0.00` | `0.00` |

套餐额度下降 7 个周百分比，而全部付费余额保持为零。M Plan Explore 下的视频
生成**只消耗套餐内权益**。`allow_payg: false` 与
`allow_credit_pack_fallback: false` 两条都成立。

视频只受周窗口约束，这与观察到的变化一致：5 小时窗口完全没有移动。

### 视频技术质检

- 文件可解码，无黑帧、无静帧、无静音
- 音频存在但基本是环境音：平均 −47.2 dB，峰值 −32.9 dB
- 视觉抽帧检查：正是提示词要求的烛焰特写，无文字、无 logo、无明显瑕疵，
  竖版且上半部留有干净的压字幕空间

已文档化的 H3 能力，保留供 M4 设计：

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

只实测了文生视频。参考图、参考视频、参考音频、首尾帧与 H3-Context-IR 仍为
`DOCUMENTED_BUT_NOT_TESTED`：同一凭证可达，但每一项都消耗周额度，因此留到 M4
带着明确预算再做。

## 当前官方 H3 提示词指引

执行时从官方 MiniMax 仓库读取，仅在此总结，**不做 vendor**。

| 字段 | 取值 |
|---|---|
| 仓库 | `MiniMax-AI/MiniMax-H3` |
| Skill 路径 | `skills/h3-prompt-writing/SKILL.md` |
| 仓库 `main` sha | `d21241f0a4b3acbb34c97dae47fa417b7065e438`，2026-08-15 |
| 最后改动该 skill 的提交 | `a107547fa669c509b8e6363fe18378d46ab3066c`，2026-08-11 |
| 核验时间 | 2026-10-04 |
| 次要来源 | `MiniMax-AI/cli` tag `v1.0.27` 的 `skill/h3-video/` |
| 第三来源 | 平台文档中的官方 H3 特性 Highlights 页面 |

这是当前官方 H3 **提示词编写** skill，定义了五种输入模式及其各自的契约：

| 模式 | 契约 |
|---|---|
| `T2VA` | 从文本构建完整视听时间线 |
| `I2VA` | 从首帧出发，向后发展 |
| `FL2VA` | 描述首帧与尾帧之间的连续路径 |
| `L2VA` | 推断合理开场，并收敛到给定尾帧 |
| `Ref2VA` | 全参考改写，分六个带标签的小节 |

基础模式（`T2VA`、`I2VA`、`FL2VA`、`L2VA`）使用有序字段
`integrated_multimodal_description`、`overall_soundscape`、`non_diegetic_music`。
`Ref2VA` 使用 `subject_definitions`、`summary`、`retention_analysis`、
`detailed_description`、`overall_soundscape`、`non_diegetic_music`。

未来的 `H3PromptCompiler` 必须遵守的输出规则：

1. 改写小节用英文书写；台词、歌词与画面内可见文字保留原语言。
2. 每个镜头按构图、主体、环境、动作、镜头运动、声音描述，并指出参考内容
   出现的准确时刻。
3. 不写剧情概述，不留未解析的参考标签，时间安排不得与请求时长不符。
4. 参考标签在所有小节中保持一致，例如 `<Picture 1>`、`<Video 1>`、`<Audio 1>`。
5. 用具体的视听细节，而不是"电影感"这类抽象词。
6. 关键帧模式必须说明首帧或尾帧如何与时间线衔接。
7. 描述的总时长始终与请求长度一致，4-15 秒。

CLI 自己的 H3 skill 补充了提示词 skill 未覆盖的时间线机制：两级时间线、
连续且不重叠且最终结束时间等于请求时长的区间、每个边界处的状态账本
（第 N 镜的锁定结束状态等于第 N+1 镜的初始状态），以及把硬性连续性约束与
审美偏好分开。

来自 CLI skill 的失败处理规则，因为它们直接关系到钱，因此采纳：一旦存在
task id，所有恢复动作都必须作用于该 task id；绝不会因为轮询、终端处理或下载
失败而新建一个付费任务；下载失败时重试同一个 URL，而不是重新生成。

M2.0 不实现 `H3PromptCompiler`。

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
| M4 H3 视频 | 推进，排在 M2 与 M3 之后。视频已验证，但它是套餐中最贵的模态且消耗周额度 |
| 旧版 Hailuo 视频 | 未调查，非必需 |

由上述发现直接推导出的质量门禁：

- 语音技术项：容器有效、时长、采样率、削波、静音、
  **响度归一化**（因为服务商峰值接近 0 dB）
- 语音语义项：脚本全覆盖、数字、专有名词、术语，ASR 回检作为探测器
- 语音人工项：自然度、节奏、情绪、发音 —— 必须，不可省略
- 图像技术项：**嗅探出的**容器、可解码尺寸、宽高比
- 图像语义项：请求主体存在、无捏造事实、无游离文字
- 视频技术项：可解码、时长、编码、分辨率、帧率、黑帧与静帧检测，以及**容差内的宽高比**（请求 9:16 实得 768x1344）
- 视频内容项：无捏造证据，且绝不用于仿制真实界面、截图、测试结果或客户证明

真正成立的幂等性锚点：语音用 模型 + 音色 + 文本 + 词表版本；
图像用 模型 + 提示词 + seed + 尺寸；视频用 模型 + 模式 + 提示词 + 参考哈希。

重试预算：每个素材最多 2 次，且第二次必须给出具体失败原因并改变输入。

## 未知项

| 未知 | 为什么重要 | 如何关闭 |
|---|---|---|
| Easel 的 MiniMax TTS 是否接受 `sk-cp-` 订阅 Key | 决定 M2 是"适配"还是"适配器" | 在 M2 对锁定版 Easel 做一次测试 |
| 语音与图像的分模态额度成本 | 重试预算需要真实数字 | 在受控生成中观察额度变化 |
| H3 每次调用的周额度成本 | 视频重试预算 | 一次 4 秒 768P 任务消耗 7 个周百分比 |
| H3 参考图 / 参考视频 / 参考音频模式 | M4 模式覆盖 | 每项都消耗周额度；在 M4 内带着预算实测 |
| 音色的自然度 / 节奏 / 情绪 | 无法自动化 | Founder 试听评审 |
| 固定 seed 的图像输出是否字节稳定 | 影响幂等强度 | 再生成一次并比较哈希 |

## 刻意没有做的事

- 只创建了**一个** H3 任务。没有第二个任务，没有盲目重试，没有换凭证尝试，
  也没有换 region 重试。
- 没有申请、创建或使用任何按量付费 Key，也没有购买积分包。
- 只实测了文生视频。参考与关键帧模式留到 M4，带着明确的周额度预算。
- 没有把任何 Key 值、片段、账号 ID 或原始 task ID 写进本仓库；任务引用是
  加盐哈希前缀。
- 没有写 provider 集成代码。M2.0 产出的是证据和决策，不是 provider。

## H3 在成片中的角色

H3 是**高价值的短生成插入镜头**，绝不是视频主干，也绝不是证据来源。

适合：钩子画面、英雄镜头、概念可视化、视觉隐喻、转场、无法实拍的场景。

禁止：任何对真实界面、仪表盘、截图、测试结果、分析视图、产品演示、客户证明
或源码输出的仿制。真实证据保持真实，生成素材永远不能被登记为证据。