---
translation_of: docs/CURRENT-STATE.md
language: zh-CN
translation_status: synced
---

# 当前状态

[English](CURRENT-STATE.md) | [简体中文](CURRENT-STATE.zh-CN.md)

> 当前运行状态。仅经验证的事实。无展望，无过时声明。
>
> 最后验证：2026-10-14

## Git

| 属性 | 值 |
|---|---|
| 默认分支 | ```main```（唯一持久分支） |
| Main 保护 | **已保护** — 必需状态检查 + PR + 禁止 force push + 禁止删除 + 线性历史 |
| 必需检查 | ```Tests (ubuntu-latest)``, ```Tests (windows-latest)``, ```Repo policy checks``` |
| 分支策略 | Issue 作用域短生命周期分支，Squash 合并，合并后自动删除 |

## Easel 运行时

| 属性 | 值 |
|---|---|
| 版本 | v0.2.1 |
| Commit | ```3fe2d9904c1619281ef57f81d9ee0b7854998399``` |
| 路径 | ```.runtime/easel/``` |
| 获取方式 | Release archive（GitHub tarball via ```gh api```） |
| 验证 | 982/982 blob SHA-1 匹配上游 tree |
| 锁文件 | ```runtime/easel.lock.json``` |
| 来源记录 | ```runtime/easel-runtime.json``` |

## 流水线

| 属性 | 值 |
|---|---|
| 生产引擎 | ```easel```（Easel ```auto-short-video/assemble.py```） |
| 诊断引擎 | ```fallback```（仅 ffmpeg，非生产） |
| 生产语音 | edge-tts via Easel ```tts.py```（zh-CN-YunxiNeural） |
| 语音质量 | ```edge_tts_fallback``` — 非生产级 |
| 生产就绪 | **否** — READY_FOR_HUMAN_REVIEW |
| 字幕变通 | ```scripts/assemble_easel.py``` — 移除字幕，运行上游，单独烧录（不修改上游） |

## MiniMax

| 属性 | 值 |
|---|---|
| 集成 | 语音**已实现**（Issue #19），`PENDING_FOUNDER_REVIEW` |
| 图像集成 | **已实现**（Issue #20，PR #25），`PENDING_FOUNDER_REVIEW` |
| 视频集成 | **已实现**（Issue #22，PR 待审），`PENDING_FOUNDER_REVIEW` |
| 语音传输通道 | 官方 MiniMax CLI `mmx`；锁定的 Easel 路径为 `EASEL_MPLAN_AUTH_INCOMPATIBLE` |
| 图像传输通道 | 官方 MiniMax CLI `mmx` |
| 视频传输通道 | **公开文档 API** `POST /v2/video_generation` —— CLI 无法设置分辨率 |
| 声音克隆 | **DOCUMENTED_BUT_NOT_TESTED**（Issue #23），需要权利清晰的样本 |
| 能力验证 | **已完成**（Issue #4，2026-10-04） |
| PAYG 允许 | **否** |
| 计费模式 | subscription，**已验证** |
| 语音 | **VERIFIED** —— `speech-2.8-hd`，32 kHz 单声道 WAV |
| 图像 | **VERIFIED** —— `image-01`，9:16 竖版，支持 seed |
| H3 视频 T2VA | **VERIFIED** —— 用订阅 Key 真实创建 `MiniMax-H3` 768P 4 秒任务并成功（M2.0） |
| H3 视频 I2VA | **VERIFIED** —— 真实参考图任务成功，2026-10-05（M4） |
| H3 Ref2VA / FL2VA / L2VA、H3-Max | **DOCUMENTED_BUT_NOT_TESTED** —— 已实现并有 fixture 测试，未实测 |
| 积分包余额 | 实测 `0.00`，每次生成前重新检查 |
| 余额读取依赖 | `UNDOCUMENTED_FIRST_PARTY_IMPLEMENTATION_DEPENDENCY`，fail closed |
| H3 时长 | 整数枚举 4-15（H3）、5-15（H3 Max）；测试最短 4 秒 / 5 秒 |
| 证据 | `research/providers/minimax-mplan-explore-capability.md`、`research/providers/minimax-voice-clone-entitlement.md` |

## 已知阻碍

1. 语音质量 — edge-tts 机械感重，非生产级。MiniMax 语音集成（M2）的主要动机。
2. Web 工作台 — 6 项 doctor 失败。不阻塞视频流水线。
3. Gateway healthz — 上游硬编码端口 18789；easel profile 使用 37289。不阻塞视频流水线。
4. 人工审查 — easel-review 项目无 ```human-review.json``` 凭证。
5. ~~Main 分支未保护~~ — **已解决**（G0.6）：main 现已通过 GitHub 分支保护机制保护。

## M3 图片生成（Issue #20）—— 已验证 2026-10-04

分支 `feat/20-minimax-mplan-image`。已执行一次真实 provider 生成。

| 属性 | 值 |
|---|---|
| 传输 | 官方 CLI `mmx 1.0.27`，`mmx image generate` |
| 模型 | `image-01` |
| 请求 | 768x1360，seed 42 |
| **请求扩展名** | `.png` |
| **实际检测容器** | **`JPEG`** |
| **规范扩展名** | `.jpg`（保留原始字节，未转码） |
| 实际尺寸 | 768x1360（已用 `ffprobe` 独立确认：`mjpeg`） |
| 宽高比 | 0.564706，9:16 = 0.5625，在 0.02 容差内 |
| 输出 SHA-256 | `fb0ee9489df856bc2cd554ab98d34fd73e0737ca733cdd0af6022342512f8e21` |
| 技术 QC | 通过 — 亮度标准差 29.97（下限 6）、极差 146（下限 24）、可解码 |
| `text_contamination_suspected` | `false`（边缘密度 0.0668，阈值 0.18） |
| 计费预检 | `SAFE_INCLUDED_PLAN`，凭据类别 `SUBSCRIPTION` |
| 生成前配额 | 5 小时 99%，周度 58% |
| 生成后配额 | 5 小时 99%，周度 58% |
| 观测差值 | 两个窗口均为 **0 个百分点** |
| `production_ready` | `false` |
| `human_review` | `PENDING_FOUNDER_REVIEW` |

### 容器缺陷第二次复现

provider 从 `.png` 请求返回了 **JPEG 字节**，内独重现了 M2.0 测到的现象。
若流程相信扩展名，一个 JPEG 会被存为 `.png`，并交给每个按后缀选择解码器的工具。
最终规范文件为 `.jpg`，凭据分别记录了请求与现实。

### 配额只报告差值，不报告价格

套餐仅暴露百分比。一张图片未造成任何窗口的变化，故观测差值为 0 个百分点。
这并不等于“生成一张图不花钱”，也未据此推导单张成本：MiniMax 在此处未暴露精确单位。

### 证据边界

生成资产已登记为 `GENERATED_IMAGE` / `VISUAL_SUPPORT`，`generated=true`、`evidence_capable=false`。
尝试任何事实引用角色都会在代码中抛出 `GeneratedAssetEvidenceError`。

### 人工评审

`.verify-tmp/m3/human-review.json` 已生成评审字段，但 **所有评分均为 null**。
技术 QC 通过不等于可作为发布。
## M4 H3 视频生成（Issue #22）—— VERIFIED 2026-10-05

分支 `feat/22-minimax-h3-video`。执行了一次真实生成，是一次**参考图**测试，
因为 M2.0 只验证了 T2VA，完全没有图像内容。

| 属性 | 值 |
|---|---|
| 传输通道 | 公开文档 API `POST /v2/video_generation`，API schema `v2` |
| 模型 / 模式 | `MiniMax-H3`，**I2VA**（首帧参考） |
| 请求 | 4 秒、`768P`、比例 `adaptive`（i2va 由输入图决定比例） |
| 参考图 | `data:image/jpeg;base64`，768x1360，45 800 字节，`role: first_frame` |
| 对齐指令 | 作为第一行输出，逐字采用上游措辞 |
| 任务创建数 | **恰好 1 次**，轮询至 `succeeded`，仅下载一次 |
| 实际产出 | h264 / mp4，768x1344，24 fps，**4.458 秒**，424 543 字节，可完整解码 |
| 画面比例 | 0.571429 对参考图 0.5647 —— 用容差，不做等值判断 |
| 时长偏差 | 请求 4.000 秒 → 实际 4.458 秒（偏差 0.458 秒，阈值 1.0 秒） |
| 音频 | 出现**未被请求的 AAC**，与 M2.0 实测一致；`audio_policy=REPLACE` |
| 黑帧 / 冻结 | 最长黑帧段 0.0 秒，最长冻结段 0.0 秒，帧间差均值 0.0131 |
| 产出 SHA-256 | `b761ea2a69b3ad6181b8a48b93dddefb56edd897867f42a8b160610e74ac249a` |
| 计费前置检查 | `SAFE_INCLUDED_PLAN`，凭证类别 `SUBSCRIPTION` |
| 配额（生成前） | weekly 58% |
| 配额（生成后） | weekly **51%** |
| 实测变化 | weekly **7 个百分点**，与声明的 `7pp` 预算一致 |
| 现金 / 积分包 / 券 / 欠款 | 前后均为 `0.00` |
| `production_ready` | `false` |
| `human_review` | `PENDING_FOUNDER_REVIEW` |

### 参考路径此前确实没有被证明过

M2.0 的回执里只有一个 `text` 项，**没有任何图像内容**。因此它对参考路径的每个
环节都没有发言权：`image_url` 项是否被接受、`role: first_frame` 是否被兑现、
`data:` URI 是否是受支持的 URL 形式、对齐指令能否与首帧同行、I2VA 在本账号上
能否渲染。该账号解析到的是区域 CN 镜像，而不是公开文档所描述的域名，所以参考
处理完全可能存在差异。用一次 4 秒调用补上这个缺口，是代价最低的做法。

### 配额只作为差值报告，绝不当作价格

7 个百分点是「一次 4 秒 / 768P 任务」的**实测**差值。它不是价格公式：没有据此推导
任何每秒、每条或按积分的单价。它只用于保守地规划测试预算。weekly 现为 **51%**。

### 用真实产物验证缓存复用

第二次运行走缓存，传输通道被指向一个**不可路由的地址**，因此任何网络调用都会立刻
失败暴露：

| 属性 | 值 |
|---|---|
| 命中复用 | `true` |
| 创建次数 | **0** |
| 轮询次数 | **0** |
| 计费调用 | **0** |
| 原始回执是否被覆盖 | `false` |

### 证据边界

该镜头注册为 `GENERATED_VIDEO` / `VISUAL_SUPPORT`，`generated=true`、
`evidence_capable=false`，并且**只在不可变回执写入之后**才注册。任何承载论断的
角色都会抛出 `GeneratedAssetEvidenceError`。

### 人工审阅

`<shot>.mp4.human-review.json` 带有 11 个具名审阅字段，**每一项分数都为 null**。
自动测量结果并列保留，并明确标注为测量而非判断。在这条真实片段上观察到的现象记录
为「观察」而非评分：首帧忠实复现了参考图；运动存在且与所要求的缓慢推进一致；但从
首帧到末帧，圆形前灯光从圆环变成了实心圆盘，且一块霓虹灯牌发生了位置漂移。几何形状
保持连贯，没有融化或扭曲。这种漂移对「辅助视觉」而言是否可接受，属于人的判断，
不该由本流水线代劳。

### 仍未验证

Ref2VA 的参考视频与参考音频路径、FL2VA、L2VA，以及 MiniMax-H3-Max（包括其 5 秒
下限和 480P 选项）均已实现并有 fixture 测试，但尚未对线上服务实测。
# M4.5 — 收敛的媒体层（Issue #27）

## 模态不是资产种类

M2–M4 产出了三个 provider，它们的回执 schema 几乎没有共同点：

|                          | speech                        | image                 | video                 |
|--------------------------|-------------------------------|-----------------------|-----------------------|
| `schema` 字段            | **不存在**                    | `...image-receipt/v1` | `...video-receipt/v1` |
| 资产摘要字段              | `normalized_sha256` / `raw_sha256` | `output_sha256`       | `output_sha256`       |
| `generated`              | **不存在**                    | `true`                | `true`                |
| `evidence_capable`       | **不存在**                    | `false`               | `false`               |
| `AssetKind`              | **无**                        | `GENERATED_IMAGE`     | `GENERATED_VIDEO`     |
| 是否注册进 registry       | **从不**                      | 由 CLI 脚本注册       | 由 provider 注册      |

因此 `MediaModality`（SPEECH / IMAGE / VIDEO）是一个与 `AssetKind` **相互独立**的
维度，而 `MediaAssetEnvelope` 总是携带 `modality`，`asset_kind` 可选——语音为 `None`。

我们刻意**没有**发明 `GENERATED_SPEECH`。那会把非视觉内容塞进视觉证据枚举，并且
暗示旁白拥有它并不拥有的证据边界。旁白是确定性的，不是证明。

`AssetKind` 仍是证据真值表的唯一所有者。收敛层向它**询问**，从不复述。

## 一个校验器，三个适配器

```
validate_media_asset(envelope, adapter)
        |
        +-- SpeechValidationAdapter
        +-- ImageValidationAdapter
        +-- VideoValidationAdapter
```

校验器只负责真正共通的部分：文件存在、回执存在且可解析、摘要一致、指纹、
仅订阅计费、有针对性的凭证与任务隐私不变量、审阅状态、回退必须显式，以及血缘。

适配器负责差异部分。协议边界上有一张分派表；公共路径**没有**任何模态分支，
并有一条测试强制保证这一点。

实现中新增、原始设计未提及的两条规则：

- **provider 生成**必须声明其模态的 schema
- **非生成**资产**不得**声明，因为没有 provider 的 API 生产过它
- `technical_qc` 缺失会让**生成**失败，但对**导入**或**变换**属于**不适用**——
  没有 provider 运行过，也就没有可报告的内容；强制要求它只会要么拦截诚实的
  记录，要么诱使有人编造一份

凭证检查是有针对性的，而不是无边界的正则扫描：公开回执中任何字符串值都不得
匹配封闭的 provider key 形状，且不得出现 `Authorization` 头值。provider 层的
哨兵测试仍是权威依据，因为它们知道真实的 key。

## 不可变性与派生资产

provider 生成的规范资产不可变。`AudioPolicy` 的应用方式是产出一个**派生资产**，
并附上一份 `contentops.media-transform/v1` 回执，其中记录来源摘要：

```
shot.mp4（provider，不可变）
  └─ shot-mute.mp4 / shot-replace.mp4（派生）
       └─ <name>.transform.json → source_asset_sha256、output_sha256、tool、command
            └─ shot.mp4.receipt.json（未被触碰）
```

| 策略 | 派生资产 | 输出中的音频 | 是否需要旁白 |
|------|----------|--------------|--------------|
| `KEEP` | **无** —— 复用原件 | 有（已记录） | 否 |
| `MUTE` | 有 | 无 | 否 |
| `REPLACE` | 有 | 无 | **是** |

`KEEP` 不写任何东西：没有移动过的字节，不应获得暗示它们移动过的来源证明。
`REPLACE` 不混流旁白——那由合成阶段从确定性音轨完成，因此这一步不可能产出
无声混音。移除音频时视频流是**复制**而非重新编码，静音因此不会劣化画面。

## 能力注册表

| 能力 | 状态 | 证据 |
|------|------|------|
| `SPEECH/NARRATION` | `VERIFIED` | PR #24 |
| `IMAGE/GENERATED_SUPPORT_VISUAL` | `VERIFIED` | PR #25 |
| `VIDEO/H3_T2VA` | `VERIFIED` | M2.0 真实任务 |
| `VIDEO/H3_I2VA` | `VERIFIED` | M4 真实任务 |
| `VIDEO/H3_FL2VA` / `H3_L2VA` / `H3_REF2VA` / `H3_MAX` | `DOCUMENTED_BUT_NOT_TESTED` | 仅 fixture |
| `VISUAL/REAL_EVIDENCE` / `VISUAL/DIAGRAM` | `MANUAL_ONLY` | 人工 / 本地渲染 |

能力标识符中不含任何厂商名。注册接受一个**可调用对象**，而不是 provider 对象，
因此注册表无法持有凭证或计费状态。`VERIFIED` 能力若不引用证据就无法构造，
这防止该表退化成一张愿望清单。不支持的能力抛出 `CapabilityNotSupported`，
绝不替换。

Fixture 证据证明代码的行为，但绝不能证明账号被授予了什么权限，二者未被混同。

## 配额策略不是成本模型

`MediaQuotaPolicy` 保存显式的操作者取值。周配额下限是**选定的**，并非由实测的
约 7pp H3 增量推导而来——那只是保守规划的输入，不是价格，因为 provider 只暴露
百分比，且单一时长、单一分辨率的一次观测并不构成费率。

`QuotaScheduler` 对所有动作只取**一次**快照，因为三个模态共享同一份账号套餐状态。
优先级由策略固定：

1. 可复用资产
2. 必需的实或已采集证据
3. 旁白
4. 确定性本地资产
5. 生成的图像辅助视觉
6. 生成的视频辅助视觉

视频排在最后，因为它是 ContentOps 最昂贵的调用，也是对视频真实性最不具
负载意义的一项。它绝不能挤占旁白或某个论断所依赖的证据。

决策：`ALLOW` / `REUSE_REQUIRED` / `DEFER` / `MANUAL_REQUIRED` / `BLOCKED`，
每一条都记录了当时生效的策略与所做的观测。

**调度决策不授权任何事情。** 每个 provider 在调用前仍会运行自己的 `BillingGuard`，
因为在此期间配额可能被别的东西消耗。

## 证据优先的执行

承载论断的 beat 只能解析为 `REAL` / `SCREENSHOT` / `SCREEN_RECORDING`。
若所需素材缺失，beat 返回 `EVIDENCE_ASSET_REQUIRED`——一个结构化的拒绝，
而不是异常，也不是替代品。定位器报告 `MISSING_REAL_ASSET` 或 `NEEDS_CAPTURE`。

采纳真实素材会写下一份 `contentops.media-import/v1` 回执，记录其来源、摘要，
以及没有 provider 参与。只有摘要的导入会成为整条链上最薄弱的一环。

回退是一个被记录下来的字段，而不是一种行为。替代品必须说明请求了什么、
实际用了什么、以及原因；未命名的替换会被拒绝。

## 收敛的门禁词汇

| 状态 | 含义 |
|------|------|
| `BLOCKED` | 校验或技术 QC 失败 |
| `DEGRADED_FALLBACK` | 技术上正常，但使用了已声明的替代品 |
| `PENDING_HUMAN_REVIEW` | 技术上正常，等待人来判断 |
| `PRODUCTION_READY` | 技术上正常**且**有人已批准 |
| `REJECTED` | 人已查看并拒绝 |

技术 PASS 不等于批准。没有记录在案的人工决定，门禁无法到达 `PRODUCTION_READY`；
**校验器**也会拒绝那些一边声明 `production_ready: true`、一边仍是
`PENDING_FOUNDER_REVIEW` 的回执——这种矛盾正是流水线相信自己已过关的途径。

## Manifest 是唯一的资产清单

`contentops.media-manifest/v1` 是合成与最终 QC 读取的唯一清单。它是一个
**索引**而非回执：模态专属细节仍留在各自回执中，因为一份复制了每个字段的
manifest 只会成为可能与前者矛盾的第二个事实来源。

按构造即确定：资产按 `asset_id` 排序、键序固定、正文**不含时间戳**。
时间戳属于回执，那里已经记录了某件事何时发生；放在 manifest 里只会让每次构建
都无信息增益地产生差异。没有门禁决定的资产，或重复的 `asset_id`，会被拒绝
而不是被接纳。

### 路径是逻辑引用，不是本机路径

已提交 manifest 中的资产路径是**逻辑引用**：`project://assets/shot.mp4`
（相对项目）或 `repo://docs/x.png`（相对仓库），在使用时才解析为本地路径。

绝对路径**永不写入**。第一份已提交的 manifest 带有 8 处
`D:\Projects\...`，这让「确定性 manifest」只在一个检出根目录下成立——因此既不能
当缓存键，也无法在评审中比较。位于两个根之外的路径无法用逻辑形式表达，
于是被拒绝，而不是被写成某个机器的路径。

### 资产清单与时间线是两件事

`assets` 是**库存**，`timeline` 才是**时间线**，两者都必需。

`usable_assets()` 回答的是「这个资产**可以**出现吗」，而不是「这个资产**在这里**
出现吗」。一次 AudioPolicy 变换会保留原片**并**新增派生资产，两者都声称占用
`beat-05`——而遍历库存会把 `beat-05` 与 `beat-05-h3-replaced` 一起放上时间线，
于是变换前的原生音轨叠在 REPLACE 本应保证是唯一音轨的旁白之上。

因此合成读取 `active_visual_assets()`：每个 placement 恰好一个资产，并记录
`selection_reason` 与被取代的 `superseded_asset_ids`。MUTE/REPLACE 时派生资产
取代原片；KEEP 不产生派生资产。两个派生资产争夺同一 placement 会被以
`AMBIGUOUS_DERIVED_ASSETS` 拒绝，而不是用某种平局规则解决——因为这个选择无法从
数据推导出来。

每个在用镜头的音频结果都写为 `audio_postcondition`，因此「REPLACE：无原生音轨、
必须旁白」是可核对的声明，而不是需要评审者自行推断的结论。

### 变换改变字节，不改变来源

变换回执记录三件独立的事，而不是一个被重载的布尔值：
`provider_generated_bytes`（本次变换的字节是否由 API 产生）、`derived`
（是否运行了变换）、`source_generated`（**来源链**是否为生成内容）。

因此派生 envelope 保持 `generated: true`。本地编辑不会抹掉来源：对生成的镜头
去掉音轨，它仍然是生成内容。`MediaAssetEnvelope` 拒绝构造出
`GENERATED_*` 类型配 `generated=False` 的 envelope——**两个方向都拒绝**，派生与否
都一样。派生的记录方式是 `derived_from`，而不是把 `generated` 降级。

## 合成复用锁定的 Easel 路径

```
manifest → 轻量的 manifest-to-storyboard 转换
         → 锁定的 Easel v0.2.1（assemble_easel.run）
         → final.mp4
         → qc_video.qc，读取同一份由 manifest 生成的 storyboard
```

没有构建第二个合成器。上游保持未修改。`qc_video` 读取 manifest 产出的那份
storyboard，因此最终 QC 是对 manifest 的检查，而不是另一份独立意见——
并且回退引擎保持其仅诊断的语义，绝不声称 `production_ready`。

## 技术集成证明了什么、没有证明什么

`scripts/m45_media_integration.py` 用本地、fixture 驱动的方式产出一个
`project://final/m45.mp4`，证明 `registry → manifest → compose → 最终 QC`，
且 **provider 调用为零**。周配额未被触碰。

| 规范事实 | 值 |
|---|---|
| 产出 | `project://final/m45.mp4` |
| QC 报告 | `receipts/qc-report-m45.json` — `overall: WARN`，`currency: CURRENT` |
| `production_ready` | `false` |
| `human_review` | `PENDING_FOUNDER_REVIEW` |
| provider 调用 | speech 0 / image 0 / video 0 |
| 时间线 | 5 个 placement，每个恰好一个在用资产 |
| 库存 | 7 个资产（5 个在用 + 1 个被取代 + 1 个旁白） |

每一个资产都是确定性 fixture，并在其回执、manifest 头部以及集成报告中
被如此标注。媒体二进制文件被 gitignore；manifest、回执与 storyboard 会被提交。

**只有一份 QC 报告、一个结论。** `qc-report-m45.json` 是 M4.5 的规范 QC 报告，
也是唯一一份。另一份已跟踪的 `qc-report-final.json` 记录 `FAIL`，因为它评分的是
`final/final.mp4`——本阶段从不产出该文件——并与真实的 `WARN` 并列，看起来像一个
同样当前、却互相矛盾的结果。它是早期某次调用的过期产物，已删除。

QC 回执在被提交前会经过一道净化边界（`contentops.qc_canonical`）。`qc_video`
是运行时工具，运行时保留本地路径是正确的；而已跟踪的回执会被就地改写为
`contentops.qc-canonical/v1`，使用逻辑引用，并显式声明 `currency` 与
`graded_target`。于是读者无需从文件名猜测**结论针对什么**以及**它是否当前**。
另有一条回归测试扫描规范产物中的宿主相关路径。

**H3 复用是显式的，绝不靠发现。** `--reuse-h3-shot PATH` 表示复用真实镜头而不
生成 fixture；不传该参数就**始终**使用 fixture。不做任何文件系统扫描。此前版本会
在 `.verify-tmp/m4` 中 glob 任意 `*.mp4.receipt.json`，于是干净克隆产出 fixture，
而残留 M4 产物的机器会静默产出真实 provider 媒体——两次运行都被当作
「本次集成」提交。一次运行的含义必须是其参数的函数。

复用是被校验的，而不是被信任的：镜头及其回执都必须存在，回执必须是真实的
`contentops.video-receipt/v1` 生成回执，且其 `output_sha256` 必须与文件匹配。
没有回执的镜头会被拒绝——否则一个来历不明的文件就进入了已提交的运行。
报告中的 `h3_shot_source` 会说明用的是 `fixture_generated` 还是
`explicit_reuse`，无需从「本地恰好存在哪些产物」去推断。

## 最终评审在已提交产物中发现并修复的五个缺陷

这些阻塞项是通过阅读已提交的回执（而不是读代码）发现的，现均已修复并附
回归测试：

1. **一个 placement，两个镜头。** `manifest_to_storyboard` 遍历的是
   `usable_assets()`——那是**库存**，不是时间线。`beat-05` 与 `beat-05-h3-replaced`
   都是门禁可接纳的，于是两者都落在 placement `beat-05` 上。
2. **生成来源被降级。** 派生 H3 envelope 写着 `asset_kind=GENERATED_VIDEO` 却
   `generated=False`，因为变换回执用一个布尔值同时表达「这些字节是否由 provider
   产生」与「内容是否生成」。现在构造时即拒绝，双向拒绝。
3. **已提交 manifest 中含本机路径。** 8 处 `D:\Projects\...` 使「确定性 manifest」
   只在一个检出根下成立，因而无法作为缓存键或评审对比依据。路径现为逻辑引用。
4. **`--reuse-h3-shot` 毫无作用。** `main()` 解析了它却没有传参，而 provider
   另行 glob `.verify-tmp/m4`。复用现改为按路径显式指定并校验。
5. **两个看起来都当前的 QC 结论。** `qc-report-m45.json`（WARN，评分
   `final/m45.mp4`）与 `qc-report-final.json`（FAIL，评分 `final/final.mp4`——
   本阶段从不产出该文件）被同时跟踪，且两者都带有绝对 `D:\Projects\...` 路径。
   过期的那份已删除，规范的那份现在显式声明 `currency` 与 `graded_target`。

它**不**证明真实的 `SourceArtifact` 摄取、`Claim Ledger` 完整性、创始人批准、
生产黄金样本，或三次连续生产构建。产出为 `production_ready=false` /
`PENDING_FOUNDER_REVIEW`，且代码路径中没有任何分支能给出相反结论。

## MiniMax 旁白 v2（Issue #34）—— A/B/C 样本等待 Founder 试听

分支 `feat/34-narration-v2-spoken-script-ab`（堆叠在 PR #44 之上）。设计决策见
`adr/ADR-008-native-narration-v2.md`。凭证：
`projects/easel-enhanced-golden/review/ab-c-sample-receipt.json` 与
`ab-c-sample-receipt-term-check.json`。

| 属性 | 值 |
|---|---|
| 原生文本控制 | 保留段落换行；`<#x#>` 停顿在本地校验；`emotion` 可选（缺省时由模型自动判断） |
| 口播稿 | `projects/easel-enhanced-golden/script/narration-spoken.json` —— 锁定原文的衍生版本；原文与 evidence lock 未改动 |
| 版本映射 | `narration-version-map.json` —— 原文/口播/合成文本（整体、样本与逐片段）的 SHA256 |
| 交付方式 | 片段级 emotion/speed、内容寻址片段缓存、局部重生成、确定性拼接 |
| 计费 | 仅订阅凭据解析；每次请求前后读取套餐额度与余额并通过 M Plan 门控；`--execute` 显式开关；硬上限 1500 字符 / 6 次 ASR |
| 样本 A / B / C | 27.55 秒复用节选（0 成本）/ 30.24 秒单请求（换行+停顿，自动情绪）/ 28.70 秒三段（calm 0.98、auto 1.05、calm 1.00）按声明间隔拼接 |
| 用量 | 5 次调用、584 计费字符；全部 `M_PLAN_ONLY_VERIFIED`；5 小时窗口 99% → 98%，所有付费余额不变 |
| C 拼接精度 | 5.478 + 8.833 + 13.436 + 0.95 秒间隔 = 28.697 秒，实际拼接 28.698 秒 |
| ASR 结论 | “doctor” 本次读音正确（S04 术语检查）；“伊泽尔” 一致；版本号实际读对——检测器 v0.21/v0.2.1 差异仍是归一化误报 |
| 评审状态 | `production_ready: false`，`human_review: PENDING_FOUNDER_REVIEW`；未发布，未生成数字人视频 |

## MiniMax 旁白 v3（Issue #34）—— D/E/F 样本等待盲听

分支 `feat/34-narration-v3-creator-director`（堆叠在 PR #44/#45 之上）。
v2 轮**未通过 Founder 听感验收**（情绪与节奏机械）。只读诊断见
`projects/easel-enhanced-golden/review/narration-v3-diagnosis.md`，设计决策见
`adr/ADR-009-narration-v3-creator-director.md`。

| 属性 | 值 |
|---|---|
| 口播稿（新） | `script/creator-script.json` —— 结论前置钩子、一处声明式省略、价值单元、自然结尾；对虚构数字/事实、模板化语言、无依据第一人称的机械拒绝 |
| 导演计划 | `script/narration-plan.json` —— 逐单元意图元数据（永不发送）；默认自动情绪；`calm` 至多一次；速度有界且组内同向；按意图设停顿；8 个单元 → 4 个合成组 |
| 版本映射 | `script/creator-version-map.json` —— 事实稿/口播稿/导演计划/合成文本 |
| 候选（盲听） | `candidate-1/2/3.wav`：D 克隆+自动、E 导演控制、F 预置音色；对应关系在凭证中 |
| 用量 | 4 次调用、676 计费字符 / 上限 1200；全部 `M_PLAN_ONLY_VERIFIED`；付费余额零变动；无重新克隆/充值/上传 |
| 机器事实 | 同一文本：克隆音色 28.74 秒 vs 预置音色 22.56 秒；E 六处有意停顿 vs D 九处；三者技术 QC 全部通过 |
| 评审状态 | `production_ready: false`，`human_review: PENDING_FOUNDER_REVIEW`；盲听 + `listening-review-v3.md` 是唯一验收门 |

## 旁白 v3 样片视频（Issue #34）—— 2026-10-27 已构建，等待 Founder 评审

D/E/F 阶段此前止步于音频。`scripts/build_v3_sample_video.py` 现在把已有候选接到
视频，**零 provider 调用**。

| 属性 | 值 |
|---|---|
| 渲染臂 | E（`candidate-3.wav`，26.585 秒） |
| 单元 → 证据 | U01 → `shot_00`（doctor）· U03 → `shot_01`（版本证据）· U05 → `shot_03`（ping/网关） |
| 时长 | 6.584 + 9.679 + 10.323 = 26.585 秒；U01/U03 边界取自检测到的静音 |
| 产物 | `project://final/v3-sample.mp4` —— h264 / 1080x1920 / aac，26.6 秒 |
| 凭证 | `receipts/v3-sample-video.json`、`receipts/qc-report-v3-sample.{json,md}` |
| QC | **WARN** —— 时长低于 30 秒；`real_evidence_present` 只扫项目目录，读数为 0 |
| Provider 调用 | 语音 0 / 图像 0 / 视频 0；额度未动 |
| 评审状态 | `production_ready: false`，`human_review: PENDING_FOUNDER_REVIEW` |

这是三单元节选，不是完整八单元脚本；候选音频在 gitignored 的 `outputs/` 下，
因此按设计只能在生成过它的机器上构建。完整 v3 旁白（4 个合成组、约 466 字符）
仍未生成。

第二个构建 `projects/easel-enhanced-golden/v3-sample-motion/` 使用同一段 E 音频，
启用 pinned 上游的 `ken-burns` 推近与分句级字幕（9 条而非 3 条）。QC 同为 WARN，
provider 调用仍为 0。推近是 1.0→1.08 的缓慢过程；在 1080x1920 下不裁掉内容，因为
证据截图本身已填满画幅。两个构建都保持 `production_ready=false`。

## 字幕烧录时间轴缺陷 —— 2026-10-27 已修复

`assemble_easel._srt_to_ass` 把 ASS 时间戳写成 `H:MM:SS.mmm`，而 ASS 规范是
`H:MM:SS.cc`（厘秒）。libass 把 `.584` 读成 584 厘秒，导致每条字幕被拉长约十倍：
本应在 6.584 秒结束的字幕一直显示到 11.84 秒。`qc_video` 只检查字幕“是否存在”，
所以这个不同步在多次全绿运行中一直存在，最终通过对真实渲染逐帧抽图才发现。

现已改为厘秒，并以 `tests/test_subtitle_timing.py` 作为回归。**此提交之前的渲染
仍带旧的不同步**，包括 A/B 变体；在对其做任何字幕同步声明之前需要重新烧录。

## 账号 DNA v2 —— 2026-10-27

`config/accounts/*.json` 现在除账号设定外，还承载品牌基座、画面配比、字幕样式、
封面规则和叙事模板，并指向对应的“一键粘贴”账号提示词。

| 属性 | 值 |
|---|---|
| Schema | `contentops.account-dna/v2` —— 两个账号 |
| 品牌基座 | `#0F1117` 炭黑，`#38BDF8` 强调色；`visual.accent` 镜像 `brand.palette.accent`，强调色只有一个归属 |
| 1024 画面配比 | 65% 裁剪录屏证据 / 30% 矢量动画 / 5% 对比卡片 |
| 未来智能画面配比 | 70% 矢量动画 / 25% 代码截图 / 5% 指标图表 |
| 录屏政策 | 1024 为 `ALLOWED_CROPPED`（录屏片段与真实捕获的静态裁切是同等证据）；未来智能为 `FORBIDDEN` |
| 字幕样式 | 无描边、无阴影，底色 `#F5F7FA`、高亮 `#38BDF8`；`burn_style` 由 `build_account_variants.py` 从 DNA 读取，不再写死在代码里 |
| 封面 | 单行主标题，留白 ≥ 30% |
| 一键提示词 | `config/accounts/prompts/*.prompt.md` —— 全局基座与账号提示词合并，纯文本，无说明性注释 |
| 渲染参数 | `render` —— pinned v0.2.1 运行时上的 `easel` 引擎、1080×1920 竖版画布（未来智能另有 16:9 模糊衍生版）、Noto Sans/Serif CJK 与 Cascadia Mono、`speech-2.8-hd` 音色、九项 QC 检查 |
| 校验器 | `scripts/check_account_dna.py` —— schema、配色、配比求和、动效允许/禁止列表、字幕样式、封面留白下限、录屏政策，以及提示词与 DNA 的一致性 |
| 测试 | `tests/test_account_dna.py` |

有两件事是刻意不声称的：

- **逐条字幕高亮只是声明，没有实现。** DNA 为关键术语声明了 `#38BDF8` 和
  `<hl>…</hl>` 标记，并记录 `highlight_rendering: DECLARED_NOT_RENDERED`。
  烧录路径对每条字幕只施加一种统一样式，因此带标记的字幕仍以底色渲染。
- **已渲染的卡片、动效片段与封面仍是旧配色。** 它们是在采用深色品牌基座之前渲染
  的：纸面底色 `#f2f4f5`、墨色 `#0a1f3d`，强调色分别是 `#b03a2e`（1024）和
  `#315d93`（未来智能）。DNA 用 `brand.refresh.rendered_artifacts:
  PREVIOUS_PALETTE` 记录了这一点，并列出了过期位置。下一次渲染必须按
  `brand.palette` 重新生成，才能发布新的剪辑。

账号视频本身没有为本次改动重新构建；在下一次构建之前，它们仍是按旧样式烧录的字幕。

## 账号定位层 —— 2026-10-27

DNA 现在承载 `X-SuperPlay-Strategy` 拥有的战略事实，让流水线和提示词读同一套定位，
而不是两份。

| 字段 | 含义 |
|---|---|
| `mission` | 两个账号共用的品牌使命 |
| `promise` | 内部定位陈述，逐字取自 `X-SuperPlay-Strategy/02-Accounts` |
| `tagline` | 对外一句话；单独成字段，因为定位陈述不等于口号 |
| `decision_question` | 一条片子只回答一个问题：1024「值不值得用」，未来智能「怎么才能跑起来」 |
| `audience` 与 `core_audience` | 触达名单（谁可能看）宽于核心名单（口播对谁写） |
| `audience_layers` | 指明写作对象是哪一层 |
| `content_pillars` | 三大栏目；1024 有权重 40 / 35 / 25，未来智能不加权 |
| `platform_roles` | 每个平台的角色、观察信号与 CTA，取自 `Platform-Operating-Matrix` |
| `non_negotiable` | 九条铁律；`forbidden` 保留三条机器可检的基线 |
| `evidence_ladder` | 浏览 < 点赞 < 提问 < 咨询 < 付费，并写明低阶信号不能证明高阶 |
| `business` | 事实源为 `X-SuperPlay-OPC-Blueprint`，Stage 0；内容不得改变阶段 |
| `cadence` | 每周 4 条基线视频，来自 1–2 份真实母素材，Founder 6–10 小时 |
| `acceptance_metrics` | 十项验收；发布率、Founder 分钟数、返工次数、有效信号排在最前 |

有两处和解是刻意做的：

- **定位陈述与口号是两种东西。** 定位陈述是对内的战略断言，口号是对外的钩子。
  Strategy 的原文进 `promise`；更窄的那句「一个人，一个真实业务，一次跑给你看的实测」
  进 `tagline`，用于文案，不冒充定位。
- **触达受众不等于目标受众。** 五类触达人群留在 `audience`，保证选题空间诚实；
  三类（1024）或四类（未来智能）决策人群进 `core_audience`，只有它们决定措辞与结论。

栏目、平台角色、排期与证据阶梯都是配置层，不改变渲染路径，也没有为此重出任何视频。

## 证据型成片：视图、停留上限与 DNA 字幕 — 2026-10-27

一个 placement 可以跟口播一样长，但它的画面不行。`CutPlan` 的 placement 现在可以带
`shots`，`target.max_visual_hold_ms`（1024 切为 2000 ms）限制每一个视图；放大视图必须
被同一 placement 更早的上下文视图包含，所以“先给上下文，再放大”是被校验的，不只是写在文档里。

| 属性 | 值 |
|---|---|
| 新增计划字段 | `shots[]`（每个视图：裁切、源时间段、语义进展、`context_shot_id`）、`max_visual_hold_ms`、`min_visual_hold_ms` |
| QC 门禁 | `views_declared`（超过停留上限的静态 placement 必须声明视图）与 `static_hold_within_limit`（实测冻结 run ≤ 上限 + 0.2 s）；旧的 `freeze_is_declared` 放行已删除 |
| 字幕样式 | `build_evidence_cut` 从账号 DNA 读 `visual.caption_style` 并传给 `assemble_easel`；`_wrap` 增加中文禁则，句读不落行首 |
| 面板版面 | 录屏按自身比例放在 `brand.palette.surface` 面板上；卡片 1:1 映射到画布 |
| 技能路由修复 | `CAP-20261028-SKILLROUTE-AUTO` 重新采集字幕路由；2026-10-27 那次问的是 `final cut subtitles burn`，输出里没有 `auto-subtitle` |

重建后的 `projects/easel-1024-proof`：44.0 s、1080×1920、h264/aac、`qc_cut`
**PASS**、最长冻结 **1.80 s**、真实素材 **72.7 %**、生成 **0 %**、8 个 placement 共
22 个视图。`production_ready: false`、`PENDING_HUMAN_REVIEW`；四条捕获都是
`internal_review` 且尚无 redaction receipt，因此分发仍被阻断。

有两点刻意不声称：

- **工程 cut 早于新门禁。** `projects/easel-engineering-proof` 为 62.0 s，placement 是
  7–8 s 单视图，收紧后的 QC 重跑会 FAIL；它已提交的 PASS receipt 在重建前是过期的。
- **账号 DNA 配比与 V2 门禁冲突。** 1024 DNA 要求 65 % 录屏 / 30 % 矢量 / 5 % 卡片，
  V2 要求真实素材 ≥ 70 %。重建后的片满足 V2（72.7 % 真实、0 % 矢量），因此没有满足
  DNA 的 30 % 矢量。这是创始人的决定，记录在
  `research/video-replication/capability-reconciliation-2026-10-27.md`。

## 未来智能 audio-first 样片（Issue #34）— 2026-10-28

`scripts/audio_first_plan.py` 让声音先成为产物：先逐句合成、实测时长，再据此写 CutPlan 的
窗口；`scripts/build_evidence_package.py` 一条命令完成构建、评级与审核包。

| 属性 | 值 |
|---|---|
| 项目 | `projects/easel-fi-audio-first` — Build 账号，1080×1920 |
| 长度 | 25.0 s（5 个 beat、10 个视图）；账号模板目标 90–120 s，所以这是蓝图里的 20–30 s P0 闭环 |
| 配音 | MiniMax `speech-2.8-hd`，5 次调用，逐句缓存 |
| 画面 | 三张矢量卡、一张静态代码快照、一张指标卡；零生成媒体 |
| QC | PASS — 最长冻结 2.40 s（上限 3.20 s），配比 70/20/10 对 70/25/5 |
| 状态 | `production_ready: false`，`PENDING_FOUNDER_REVIEW` |

为这个账号新增三道门：`manual_recording_forbidden`（不得出现录屏素材）、
`composition_ratio`（声明的矢量/代码/指标占比偏差 ≤8 个百分点）、
`evidence_mode: EXPLANATORY`（不适用 ≥70% 真实素材下限，由配比门替代）。视图现在可以
自带 `asset_id`，所以一个 placement 能从指标卡切到矢量总结；`burns_caption` 让图解卡
保留字幕，而引用卡仍然用卡面替代字幕。

不声称：矢量卡是静态的、没有动画；BGM 按政策省略；样片不是完整一期。

## 未来智能样片的动效 B-roll（Issue #34）— 2026-10-28

Build 组样片不再使用静态卡片。六个 HyperFrames 工程在
`projects/easel-fi-audio-first/motion/` 下各渲染 5 s / 1080×1920 / 30 fps 片段，
`build_evidence_cut` 以 `kind: motion` 素材接入。

| 属性 | 值 |
|---|---|
| 渲染器 | HyperFrames CLI `0.8.208`（Apache-2.0），`check` 0 error，`render -q delivery` |
| 片段 | `narration-bar`、`view-swap`、`arch-flow`、`code-sweep`、`metric-count`、`result-chain` |
| 处理 | 5% 细颗粒、1.0→1.035 缓慢推镜、焦点压暗，只用 transform/opacity |
| 证据角色 | 仅解释性画面；`evidence_capable: false`，不计入真实素材，也不计入生成媒体 |
| 样片 | 25.0 s，QC PASS，最长冻结 1.60 s，配比 70/20/10 对 70/25/5 |

动效片段的 SHA 同时写进 `assets.json` 与构建收据，重渲染后的片段无法冒充已审核版本。

## 代码动画层：huashu-art-motion（Issue #34）— 2026-10-28

Build 组的动画层是一个外部 skill，不是自研引擎。`huashu-art-motion`
（MIT，commit `8a0d7d7`，SKILL 1.2.0）装在共享 skill 库，通过它的
`scripts/engine/render.py` 使用。

| 属性 | 值 |
|---|---|
| 引擎路径 | `C:\Users\Administrator\.agents\skills\huashu-art-motion` |
| Windows 适配 | Chrome/Edge 通道回退；运行时设 `PYTHONUTF8=1`（spec 读取用默认编码） |
| 解释器 | 宿主 Python，让 Playwright 命中 `D:\DevCaches\ms-playwright\chromium-1223` |
| 使用语法 | 两个机制 beat 用 `y1_kurzgesagt`（竖屏三颗卫星），三个支撑 beat 用 `t2_keynote_ui`；片段时长精确 |
| 样片 | `projects/easel-fi-what-is-agent/` — 45.0 s、1080×1920、h264/aac、12 个可变 beat（2.6–4.1 s）+ 一个 4.0 s 生成插入 |
| 配音 | MiniMax `speech-2.8-hd` + 克隆音 `founder_primary_v1`，12 句，实测 36.758 s；每个窗口 = 语音 + 0.35 s |
| 字幕 | 按实测句长生成 SRT，用未来智能 DNA 样式烧录 |
| 配乐 | 本机合成暗氛围底，峰值 −24.4 dBFS 对 −1.5 dBFS 人声（余量 22.9 dB）；无采样库、无 provider |
| QC | `qc_video` **WARN**（纯动画：真实素材比与真实证据检查不适用；未声明 `source_refs`），时长/解码/音频/字幕/响度通过 |
| 状态 | `production_ready: false`、`PENDING_FOUNDER_REVIEW`，无发布链接 |

样片是定义型内容，不是断言型（`claim_bearing: false`）；零录屏、零鼠标。
一个 MiniMax H3 片段作为无口播、无断言的桥段（4.0 s = 全片 8.9%，低于 10% 上限）；
另生成的一张静帧因为读起来像黑帧，已从时间线移除。两个决定与配额变化记录在
`receipts/generated-media.json`。收据绑定 spec、片段与输出 SHA；
`receipts/qc-summary.json` 也把 QC 结论绑定到输出 SHA。

## ERAS 整片变体（Issue #34）— 2026-10-28

讲解片新增一支平行成片：**由一条 Huashu ERAS 时间线负责所有转场**，不再把十二段单独渲染的 clip 硬拼。基线 `final/easel.mp4` 与其收据未被改动；变体构建后重新计算四个基线文件的哈希，全部字节一致。

**基线文件的当前本地状态：** `final/easel.mp4` 已不存在。之后一次 ERAS 合成漏传 `--out-name eras`，把变体成片写到了基线路径。`projects/*/final/` 已在 git 忽略范围内，因此没有改动任何受跟踪文件，但该文件被替换成与 `final/eras.mp4` 字节一致的副本；它已被移出仓库而非删除。它无法用本机当前输入重建：p03 的 clip 为 2.900 s，而其窗口为 3.009 s，基线合成器拒绝补尾（同一缺陷上文已为 ERAS 适配器记录，后者选择补帧）。`receipts/sample.json` 未被改动，仍描述原始构建——sha `f5234901…`、37.9 s。

| 属性 | 值 |
|---|---|
| 项目 | `projects/easel-fi-what-is-agent` — Build 账号，1080×1920 |
| 视觉轨 | 一次 ERAS 渲染 `project://work/huashu-eras.mp4` — 38.900 s、30 fps、1167 帧、h264 |
| 时长构成 | 31.503 s 语音（29.593 s 讲解 + 1.910 s 开场）+ 4.890 s 尾音 + 2.5 s 静音桥段 = **38.893 s** |
| 转场 | `push` / `matchCut` / `blurPush` / `fadeShift` 只挂在进入段；无 `xfade`、无 clip 拼接 |
| 适配器 | `motion/film/render.py` — 只读挂载外部引擎 `/engine/` 与项目 `/project/`；未修改上游 |
| 片子配置 | `motion/film/eras.js`（clip 帧 ERAS + 显式空 drawer）、`motion/film/index.html` |
| 配音 | 克隆音 `founder_primary_v1`，1.20×，12 句，全部 `SAFE_INCLUDED_PLAN`，技术 QC 通过；开场来自 MiniMax H3 Ref2VA，不属这支克隆音 |
| 架构图 | p02 使用重绘后的 `motion/specs/diagram-workflow-vs-agent.png`（Anthropic 一手定义），卡片审计 PASS |
| 输出 | `project://final/eras.mp4` — 38.9 s、1080×1920、h264/aac |
| 收据 | `receipts/eras/` 下的 sample、timing-reconciliation、review-bundle、human-review、cover、runtime-receipt，以及 `receipts/qc-report-eras.{json,md}` |
| 生成物占比 | 桥段 2.5 / 38.893 = **6.43 %**；AI 数字人 2.6 s = **6.69 %**，在 `generated_media.ai_presenter` 中单独声明；合计 13.11 %，10 % 上限只约束无断言桥段 |
| QC | `qc_video` **WARN** — 与基线同类（纯动画、无真实素材）；分辨率、比例、时长、编码、音频、字幕烧录与响度通过 |
| 状态 | `production_ready: false`、`PENDING_FOUNDER_REVIEW` |

### 数字人开场（仅 eras 变体）— 2026-10-28

eras 成片以一张脸开场。一条 MiniMax H3 `Ref2VA` 镜头（请求 4 s；参考图 = 数字人本人，
参考音 = 本片克隆的第一句）说出钩子 `这条视频，只讲一个问题。` 并收住。片中其它一切未动：
十二句配音清单、`final/easel.mp4`、`receipts/sample.json`、`assets/captions/default.srt`
均未重建，基线时间线会被过滤，因此永远看不到这段开场。

| 属性 | 值 |
|---|---|
| 镜头 | `project://work/generated/shot-b666f8c64dc7a901.mp4` — 768×1344、24 fps、4.458 s、`KEEP` 音频、`sha256 9cb09c9e…` |
| 落位 | `work/eras/clips/p00.mp4` — 裁切 756×1344 → 1080×1920、30 fps、2.6 s、静音；该段位于最前，`p01` 获得进入式 `fadeShift` |
| 人声 | 从镜头本身重切：1.910 s、32 kHz 单声道、−3 dB，使其与 `speech-2.8-hd` 的 −18.2 dB 均值对齐 |
| 时间线 | `motion/timeline.json` 中的该段带 `"variant": "eras"`；构建器与适配器都按变体过滤 |
| 台账 | `receipts/generated-media.json` 的 `presenter`，以及 `eras.{insert_ratio,presenter_ratio,ai_generated_total_ratio}` |
| BGM | 铺底整体后移 2.6 s，开场保持干声，铺底仍在 38.893 s 收尾 |
| 成本 | 按镜头收据实测，每周配额**未移动**（74 % → 74 %，0 pp）；81 % → 74 % 的 7 pp 属于更早那条同长度桥段镜头，因此开场自身的成本无法测量，也不做声张 |
| 披露 | `labelled_ai_synthesised: true`；`speech_text_verified: true` —— MiniMax `asr-1.0` 转写结果为 `这条视频只讲一个问题。`，覆盖率 1.0 |
| 契约 | `motion/presenter/contract.json` 只写策略（变体、clip、台词、10 % 上限、必须通过核验）；事实仍在 `receipts/voice-lines.json` |
| 闸门 | 契约不满足时构建器拒绝 eras 构建（`status: BLOCKED`，退出码 4）：presenter 段消失、哈希漂移、资产缺失或台词未核验，任一成立即拒绝 |
| 其它产出管线 | 项目声明了开场而该管线无法放置它时，`scripts/run_v1.py` 直接返回 `BLOCKED`，不会拍出一条没有他的片子还当作完成 |
| 状态 | `production_ready: false`、`PENDING_FOUNDER_REVIEW` |

这条核验边界要说清：ASR 证明的是**说了哪些字**，不是这条表演能不能用。交付判断仍归创始人。`speech_check` 与标志一起落盘，结论可复跑而不只是被相信：

```bash
python scripts/presenter_opening.py projects/easel-fi-what-is-agent --check
python scripts/presenter_opening.py projects/easel-fi-what-is-agent --verify-speech
```

本次构建暴露的三个缺陷被记录而非抹平：

- ERAS 表最初沿用旧的 43.5 s 节奏；新增回归测试把每一段时长绑定到 `motion/timeline.json`；
- p03 源片长 2.900 s，而窗口 3.009 s，适配器只允许用末帧补齐**连续尾部**，中间缺帧仍然失败；
- 引擎在加载时绑定 `#scrub`/`#tt`/`#play`，并按相对路径声明 `lib/fonts/*.woff`，因此项目页面需要这些控件和 `<base href="/engine/">`，两者都有测试覆盖。

变体的 `freeze_s` 原为 2.4 s，基线为 0.6 s。对桥段做 PSNR 比对（t=23.0 与 t=24.2，y = 21.8 dB）说明桥段并非静止帧，因此该数字按实测报告，不做解释性掩盖。加入数字人开场后，又用 5 fps 帧差把冻结定位到 **5.2–7.8 s**，即 p02 架构图卡片；HEAD 上未含开场的旧构建存在同样的 2.4 s 冻结与同样的 reason 字符串，因此它早于本次开场存在，不是开场造成的。

该冻结现已修复，且结论来自实测而非声称。`p02.json` 用两个 `highlight` cue 取代了单一的 `image` cue，由全幅镜头运动带动整段；**`final/eras.mp4` 的最长冻结段为 0.367 s**（`freezedetect=n=-60dB:d=0.25`），合成器自身的门禁报 `0.4`。

这次修复的第一版引入了更严重的第二个缺陷，这也正是约束落在卡片而非镜头上的原因。highlight 矩形除缩放外还会驱动平移——引擎把 `z` 卡在 1.18 下限，`fill` 无法削弱它——一次推镜会把卡片内容下移约 330 px。影片把字幕烧在固定的 **y 1760–1798 / 1920** 条带里，因此任何触到字幕基线的卡片版式都会被扫过：收尾句“关键不在……”在 6.9 s 与烧入字幕重叠。卡片因此重建为在 **y 1233** 结束：出处署名移入刊头行，h1 上方留白加倍，使收尾推镜裁到的是空背景而不是一行字，底部三分之一留给字幕。该片段 99 帧全部在 1750–1810 行扫描，非字幕墨迹为 **零**；任意一帧的最低墨迹为第 1728 行。


数字人构建中的两个缺陷：

- presenter 段必须声明 `"variant": "eras"`；不声明就会进入基线时间线、说出没人写过的台词，因此 `_validate_segments` 直接拒绝；
- eras 构建器最初到 `work/clips/` 找所有片段，这会要求覆盖基线产物；现在 `_clip_path` 只在 eras 变体下读取 `work/eras/clips/`。

两者都有测试覆盖，BGM 铺底的 `amix` 延迟同样有测试——它保证铺底不会压在清唱人声下面开始。

## 有序生产合同与门禁 — 2026-10-28

| 属性 | 值 |
|---|---|
| 合同 | `contentops.copy-to-video/v1`，10 个有序阶段 |
| 状态 | `pending` / `running` / `ready_for_review` / `approved` / `blocked` |
| 批准绑定 | 产物 SHA-256 + 上游指纹；任一变化即失效 |
| 绕过 | 无 |
| 阶段校验 | 受众 Lens；脚本节奏、时长、技术解释、文案策略与自然度；逐 claim 证据覆盖与拍摄计划；版权台账与素材候选；视觉路由；交付清单与发布计划 |
| 文档门禁 | 选题 backlog、候选评分、证据可行性、平台策略、版权、改进日志、反馈/指标、skill provenance |
| 共享 skill | `C:\Users\Administrator\.agents\skills` 中 9 个 skill，账号 DNA 以 `path_base: "shared"` 声明 |
| 测试 | 55 个套件（`tests/test_*.py` 加 `scripts/test_basic.py`），由 `scripts/run_tests.py` 发现并逐个运行；开发者门禁会跑全部，CI 拒收"存在但从未被点名"的套件 |
| `production_ready` | **false** —— 尚无成片通过人工审阅 |

### 素材候选先于台账 — 2026-10-28

版权台账记录"某素材已获授权"，却无法证明该素材是从一份受审阅的候选清单里挑出来的。`src/contentops/workflow/sources.py` 负责这份更早的记录（`contentops.source-candidates/v1`）：规范页面、创作者、许可正文与许可链接、采集日期、三项评分，且 `status` 固定为 `candidate`。

- 校验器拒绝：自行宣告已清权的清单、非自有许可却缺许可正文或链接的候选、未来的采集日期、超出 0–10 的评分；
- 加权分 = `0.4·relevance + 0.4·evidence + 0.2·rights`；`promotable()` 是晋升辅助函数，列出仍挡住的项（许可未知或非法、缺许可链接、记录不是 `candidate`、评分不全、低于 6.0 复审线），门禁执行的是许可一致性，分数线只作建议；
- 当台账行引用 `source_candidate_id` 时，`validate_ledger_provenance` 要求该候选存在且 `license` 一致；
- 只要产物旁有 `source-candidates.json`，`assets` 阶段就会像跑台账一样跑它。

这是从已退役的 `dy_x1024` `material-source-research` skill 吸收来的契约。此前只有 skill 文本、没有代码支撑，现在有了。

### 门禁会跑每一个套件 — 2026-10-28

`scripts/dev_check.py` 曾在一个迁移套件失败的同时打印 "ALL CHECKS PASSED"，因为那个套件从未被调用。现在它运行 `scripts/run_tests.py`：发现 `tests/test_*.py`，每个套件独立进程运行。`python scripts/run_tests.py --missing-from .github/workflows/ci.yml` 会在"套件存在但 CI 从未点名"时让 CI 失败；此前有四个套件处于该状态（`test_script_quality`、`test_repo_policy`、`test_presenter_opening`、`test_code_animation_composition`），现已接入。

`--quick` 跳过仓库策略与套件运行；完整门禁约五分钟，主要耗时在离线的语音夹具套件。

### dy_x1024 吸收收口 — 2026-10-28

该工作区即将删除，因此本轮按"今天真正跑得起来的东西"复核吸收，而不是按"复制过来了什么"：

| 项目 | 状态 |
|---|---|
| `b-roll-finder`（MIT，Louise de Sadeleer） | 原样收入共享 skill 库；在 `x-superplay-1024` 中路由为 `broll_finder` 步 |
| `material-source-research` | 改写为 `x-superplay-source-research`；其契约已成为代码（见上） |
| 30 个 skill 的契约文本 | 归档于 `research/archive/dy1024-skills-2026-10-28/`，附 adopt / hold / reject 决策表 |
| `clean-talking-video`、`manim-video`、`auto-editor*` | **hold** —— 各自需要当前技术栈之外的工具链或供应商，未接入路由 |
| `model-selector`、`prompt-translator`、`seedance-2.0-director` | **暂不采纳** —— 推荐的供应商在 MiniMax-only、`allow_payg: false` 边界之外 |
| 第三步脚本冒烟 | 收口并复核：md 口播与 `.narration.txt` 逐行一致（8/8、10/10），`wordcount.py check` 在 200/202 与 389/385 均退出 0，两条 CTA 未改 |

### OpenClaw 桥接层与字幕声明 — 2026-10-28

`scripts/openclaw_agent.py` 是唯一执行 OpenClaw agent turn 的地方。此前流水线直接调用
Easel 的 skill 脚本，harness 层（模型选择、工具循环、skill 选择）从未真正运行。

| 事实 | 值 |
|---|---|
| Harness | OpenClaw 2026.9.7，profile `easel`（`~/.openclaw-easel`），模型 `anthropic/MiniMax-M2.7-highspeed` |
| 原语 | `openclaw agent exec --json` 配持久化 `--state-dir`；临时 state 目录在 Windows 上会以 `EBUSY: openclaw.sqlite-shm` 失败 |
| 收据 | `contentops.openclaw-agent/v1`，包括账号 slug 错误或 CLI 缺失在内的每条路径都写 |
| `skill_route` | 复制自账号 DNA，不猜测；stage 属于契约阶段时记录 `contract` |
| 路径 | 已提交收据不含绝对路径（`repo://` / `project://` / 占位符） |
| 批准 | `human_review: required`；agent turn 永远不是批准 |
| 测试 | `tests/test_openclaw_agent.py`，已接入 CI；无 Easel 运行时则跳过路由用例 |

本机已验证：gateway 处于停止状态，`agent exec` 可独立运行；114 个 Easel skill 已同步到
`~/.openclaw-easel/workspace/skills`，但 harness 只注册自己的 22 个、未注册任何 Easel
skill（26 条 `skills.entries` 全部关闭）。有一把 anthropic 凭据返回 401，运行会轮转到
`models.json` 中的 key，每次约多花 4.5 秒。

两个账号 DNA 的 `captions` 路由原先声明 `auto-subtitle` 与
`skills/shared/scripts/subtitle_ops.py`，但二者从未被调用：真正拥有者是
`scripts/assemble_easel.py`（`_srt_to_ass`、溢出闸门、ffmpeg 烧录）。两个 DNA 现已改为
声明 `assemble_easel` 与 `path_base: repo`，旁白时间轴归入 audio 阶段。尚未声明
`contract_stage`，因此 `captions` 收据记录 `contract: null`。

### 文案门禁阻断所有生产链路 — 2026-10-29

写完文案不再直接进入渲染。`src/contentops/workflow/copy_review.py` 把人工决定绑定到文案指纹上，
没有决定的生产链路一律拒绝执行：

| 生产入口 | 停在哪里 |
|---|---|
| `scripts/run_v1.py` | `run_easel`，TTS 之前 |
| `scripts/build_code_animation_sample.py` | `main`，读取 voice-lines 之前 |
| `scripts/build_motion_film.py` | `build`，任何渲染之前 |
| `scripts/build_account_variants.py` | 逐账号，`build_variant` 之前 |

| 事实 | 值 |
|---|---|
| 记录 | `receipts/script-review.json`，schema `contentops.copy-review/v1` |
| 决定 | `APPROVED` 或 `CHANGES_REQUESTED`，必须有具名审核人与书面意见 |
| 指纹 | `script/master.md`、`script/*.srt`，以及每个镜头的 `unit`、`narration`、`image`、`source_type`、`duration`、`designer_card`、`placement`，另加 `size` |
| 排除 | `narration`、`subtitle`、`engine`、`runtime`、`voice_provider` —— 这些由流水线自己写回，不得让审核失效 |
| 绕过 | 没有 |
| 状态 | `NOT_REVIEWED` 与 `STALE` 停住，需重新决定；`CHANGES_REQUESTED` 停住，需改文案 |

`python scripts/copy_review.py <project>` 查看门禁；带 `--approve` 或 `--request-changes`
并给出 `--reviewer`、`--opinion` 即为记录一次决定。截至本条目，两个账号项目均为
`NOT_REVIEWED`，因此在创始人审核前，它们的所有流水线都被阻断。

### 只保留一条强制门禁 — 2026-10-29

十阶段契约（`contentops.copy-to-video/v1`）与文案审核都声称保护"脚本之后"的交接，
但真正生效的只有一个，因此把决定记录下来，并用测试固化。

| 问题 | 答案 |
|---|---|
| 哪条门禁强制执行？ | `copy_review` —— `NOT_REVIEWED` 与 `STALE` 会让所有生产链路停止 |
| 契约是什么？ | 一套经过测试的顺序与指纹规则库，已声明但未接入任何生产入口 |
| 为什么不采纳它？ | 它的标准产物（`00_brief/…`、`02_script/script.json`）在任何项目里都不存在；采纳等于为每个项目发明十条路径，并在每次构建前再加一道审批 |
| 什么情况会推翻这个决定 | 当流水线长到"上游交接过期"成为主要风险，而不是"文案没人看过"时 |
| 守护方式 | `tests/test_copy_review.py::test_no_producer_wires_a_second_gate`：若有生产入口改接契约而非文案审核，测试即失败 |

`python scripts/workflow_gate.py` 仍可用，且每次调用都会提示它未接入生产链路。
没有任何代码被删除：若日后顺序规则确实有价值，改一行导入即可启用，决定是可见的，
而不是需要重新发现。

### 拍摄合同与自然度门禁 — 2026-10-29

退役的 `dy_x1024` 有三项能力是当前流水线没有的，现在都已变成代码、有测试、且接入了门禁。
它们都不是新引擎；每一项都只是拒绝一份无法诚实产出的文档。

| 能力 | 模块 | 接入位置 |
|---|---|---|
| 逐 beat 的拍摄简报：画面来源、必须可见的内容、9:16 裁切、光标、脱敏 | `src/contentops/workflow/capture_plan.py` + `scripts/recording_plan.py` | `storyboard` 阶段读取同级 `capture-plan.json` |
| 口语预算、口头禅上限、事实锁留存 | `src/contentops/quality/naturalness.py` | `script` 阶段读取同级 `naturalness.json`；`workflow_docs.py check --kind naturalness` |
| 烧进画面的字幕必须转录该段旁白 | `contentops.quality.subtitle.validate_caption_agreement` + `scripts/check_caption_text.py` | 由烧字幕步骤调用；以退出码判定 |

| 事实 | 值 |
|---|---|
| 1024 策略 | `evidence.manual_recording: ALLOWED_CROPPED`；实跑把 8 个分镜 beat 路由为 browser 5 / task_screen 3（写到临时路径，未提交进项目） |
| 未来智能策略 | `FORBIDDEN`；要求"直接观察"的 beat 无法产出合法计划，CLI 退出 1 且不写文件 |
| 脱敏默认 | 由分镜推导出的 beat 默认 `true`，且声明了脱敏就必须写进拍摄合同 |
| Skill | 共享库新增 `x-superplay-capture-plan`，两个账号都以 `capture_plan` 步骤接入 |
| 测试 | `tests/test_capture_plan.py`（16 项）、`tests/test_naturalness.py`（18 项），均已写入 CI |

两条边界是有意声明的：

- **拍摄计划是简报，不是拍摄结果。** 通过它不证明素材存在或在手机尺寸下可读；可用性仍由人判断。
- **自然度通过不是听感结论。** 它证明改写没有超出自己声明的预算，且保留了锁定事实。字幕一致性是文本同一性，不是读音。

### 对标复刻契约 — 2026-10-30

对标视频现在可以变成一份原创集的计划，既不需要假装知道没看过的切点，也不需要搬用参考博主的素材。契约由三份文档和一个质检关组成。

| 阶段 | Schema | 由谁写 | 绑定到 |
|---|---|---|---|
| 观察 | `contentops.reference-observation/v1` → `reference/observation.json` | 人，逐段实看 | 项目内可解码影片的 SHA-256 |
| 计划 | `contentops.replication-plan/v1` → `script/replication-plan.json` | `replicate_reference.py --plan` | 观察的哈希、账号 DNA、`reuse_reference_media: false` |
| 对账 | `contentops.replication-check/v1` | 写了计划的项目的 `qc_video.py` | 计划与实际上线的 storyboard |

| 规则 | 为什么存在 |
|---|---|
| `TRANSCRIPT_ONLY` 观察不得带 `start_s`/`end_s` | 字幕描述的是词，不是切点；用它猜秒数正是这道关要挡的伪造 |
| 计划预算被夹进账号声明的时长窗口 | 参考片可能长于账号允许的长度，以账号为准 |
| 成片不得引用 `reference/` 下任何素材或来源 | 可复用的是镜头功能，不是画面和事实 |
| 每镜声明 `function`（封闭词表）与 `dna_role` | “看着像”不是测量；占比与 DNA 相差不得超过 ±8 个百分点 |
| 钩子 ≤ DNA 的 `max_hook_s`，静帧不超过 DNA 上限，节奏顺序遵循模板 | 观众在内容之前先注意到的三件事 |
| 只有写了 `script/replication-plan.json` 的项目才按复刻对账 | 普通一集不欠任何参考契约 |

| 事实 | 值 |
|---|---|
| 入口 | `scripts/replicate_reference.py` — `--observe`、`--plan`、`--check` |
| 退出码 | 0 通过 · 1 契约失败 · 4 尚未观察或尚无计划 · 2 输入矛盾或无 `script` 技能路由 |
| 收据 | `receipts/replication.json`，状态 `DERIVED`——派生预算不是审批 |
| 生产拦截 | `replication.stage_gate()`——`run_v1.py` 与 `build_evidence_package.py` 拒绝渲染偏离计划的成片；没有计划的项目不受影响 |
| 同批修复 | `cut_qc.source_shares` 按 shot 而非 placement 计时；`qc_video.real_source_ratio` 按时长而非镜头数加权 |
| 测试 | `tests/test_reference_replication.py`（20）、`tests/test_evidence_cut_qc.py`（10），均在 CI 中列出 |

两条边界是有意声明的：

- **尚未取得原片，因此没有任何真实计划。** 每个测试都自建夹具。命令在没有可解码且有哈希的影片时拒绝出计划——拒绝就是正确答案，不是没实现。
- **对账通过不是人的结论。** 它证明成片没有超出自己声明的预算、占比和顺序。值不值得看仍由 Founder 与 `copy_review` 一起决定。

### 质检读生产实际写的文档 — 2026-10-30

对 `projects/easel-1024-proof` 复查时暴露出一组同源缺陷：`qc_video` 与 `cut_qc` 对同一部片结论相反，因为各自读了不同的文档。三处均已修复并有回归测试；旗舰证据片现在由警告变为 PASS，而此前是“以错误的理由警告”。

| 事实 | 值 |
|---|---|
| 故事板 | 依次为 `work/<target>/storyboard.json` → `script/storyboard.json` → `work/storyboard.json` |
| 真实素材占比 | 存在 `script/cut-plan.json` + `assets.json` 时按最终成片时长从计划计量，故事板仅作兜底 |
| 来源完整 | 被引用的资产必须声明 `sha256`/`path`/`png`/`html`；无来源的录屏计时间，但不计入证据 |
| 字幕存在 | `assets/captions/<target>.srt` → `default.srt` → `cut.srt` |
| 字幕烧录 | 按每条 SRT 字幕的中点取帧；按片长固定比例只是兜底，因为稀疏字幕覆盖不到六个等距点 |
| 证据片结果 | 72.7% 真实（32 秒录屏 / 12 秒卡片），字幕存在且烧录实测亮像素比 0.0142，整体 PASS |

这**不**做两件事：不证明成片画面等于 cut plan（两个质检都信任计划），也不批准该片——人审与分发在本人审核前仍被阻断。

### 复刻契约不再信任自己的输入 — 2026-10-30

对契约的对抗式复核找到四条“证明一部不存在的片”的路径。它们的形状相同：某份文档断言了影片从未发生的事，而下一关直接读这份断言。现在四条都失败即拦。

| 漏洞 | 它允许了什么 | 现在的行为 |
|---|---|---|
| 手打的镜头表 | 写 `mode: FRAME_VIEWED` 加几个像样的秒数，就能从没人打开过的影片派生预算 | `--frames` 按每镜中点从原片切出 32×32 帧并记录 SHA-256；没有帧的镜头被拒绝，`probe_reference` 按各自时间点重新切帧逐字节比对（`FRAME_NOT_FROM_REFERENCE`） |
| 预算只是故事板的算术 | 累加 `duration` 字段让 47.2 秒的计划为 2 秒的成片背书 | `check()` 用 ffprobe 实测 `final/easel.mp4` 并以实测为准；没有成片即 `render_present` FAIL，`--check` 不能只凭计划退出 0 |
| 计划自己带着阈值 | 改 `target_s` / `max_hook_s` / `max_static_hold_s` / 占比，把失败的成片改成 PASS | `plan_matches_derivation` 用已核验的观察与账号 DNA 重新派生计划，要求完全相等 |
| 账号策略被写成单集字段 | `evidence_mode: EXPLANATORY` 关掉 70% 下限，`manual_recording: ALLOWED` 取消禁录，删掉 `composition` 跳过占比关 | `cut_qc` 从 `project.yaml` 解析 DNA；以账号的值执行，声明不一致即 FAIL，`account_composition` 按 DNA 的画面预算实测成片 |

| 事实 | 值 |
|---|---|
| 帧 | `reference/frames/NNN.png`（可查看，160 px）与 `NNN.gray`（32×32，按字节绑定）。用最近邻缩放，因此重新切帧在不同 ffmpeg 构建间字节稳定 |
| 观察 | 帧切在镜头中点；中点落到影片最后一帧之后时，在同一镜头内向前回退，绝不换到别的镜头 |
| 成片 | `final/easel.mp4`，用 ffprobe 实测。`require_render=False` 是 `stage_gate` 在成片存在前所做的“渲染前声明” |
| 测试 | `tests/test_reference_replication.py`（26）、`tests/test_evidence_cut_qc.py`（12）；`dev_check.py` 61/61 suites |
| 新暴露的失败 | `cut_qc` 现在按自己的 DNA 评判 `projects/easel-1024-proof`：73% 录屏 / 27% 对比卡，而预算是 70/25/5，于是 `account_composition` FAIL、证据包返回 FAIL。片没变，是关卡不再跳过它计划里从未声明的那个问题。 |

这**不**做两件事：不证明成片每一拍就是计划点名的那个拍（只核了成片时长与故事板），也不批准该片——人审与分发仍被阻断。

### 契约不再信任故事板上的标签 — 2026-10-30（第二轮）

对修好的契约又做了一轮对抗式复核。结论是：门禁已经学会量**长度**，但仍然相信故事板和资产图对自己写的每一个**标签**。以下全部改为失败即拦。

| 漏洞 | 它允许了什么 | 现在怎么处理 |
|---|---|---|
| 只量了长度 | 一张静帧拉满 47 秒能过静帧关；镜头不写 `duration` 会读成 `0.00 s` 的钩子并“合格” | `static_hold_within_limit` 改用 ffmpeg 实测的最长冻结段，量不出来就 FAIL；`hook_within_limit` 要求钩子大于 0 |
| 证据角色是自由标签 | `dna_role: screen_recording_evidence` 挂在 `source_type: generated` 上，仍被算成 70% 录屏 | 新增 `dna_role_matches_source`（故事板）与 `role_matches_source`（资产图，在 `cut_qc`）：证据角色必须落在实拍来源上 |
| 参考片复用只是路径子串 | 把参考片帧复制过来、再改掉 `image`/`video` 路径即可通过 | `reference_frames_not_in_cut` 以 2 fps 把成片抽成 32×32 灰度，与参考片帧逐字节比对，命中即 FAIL；`claims_do_not_cite_the_reference` 拒绝用参考片摘要做事实证据 |
| 观察记录可以写着另一个账号 | 为“未来智能”写的观察可以派生出一份拿 1024 DNA 评判的计划 | `--plan`/`--check` 拒绝不一致；`qc_video` 从 `project.yaml` 读账号（`replication_plan_account`） |
| `--target-seconds` 可以离开 DNA 窗口 | 给一个只发 45–60 秒的账号排了 20 秒或 90 秒的片 | 该参数只能在该账号 `target_duration_s` 窗口内选点 |
| 纯音频文件可以冒充影片 | 一个可解码、摘要匹配的音频“证明”了一份没人看得到的镜头表 | `REFERENCE_NOT_A_FILM`；缺 ffmpeg/ffprobe 是 `REFERENCE_UNVERIFIED`，不再静默通过 |
| 对账收据抹掉了派生记录 | `--check` 用一句 PASS 覆盖了计划摘要、参考片摘要与技能路由 | 派生字段在多次对账间保留 |
| 没有要求权利决定 | 没有任何地方记录这部参考片能用来做什么 | `reference/observation.json` 必须带 `rights.cleared_by / decided_at / scope`（`RIGHTS_MISSING`） |
| `qc_video` 的真实来源占比只是提示 | 证据型账号可以按 WARN 放过低于下限的片，生成画面也没有上限 | `EVIDENCE_LED` 账号低于下限即 FAIL，并有 `generated_ratio` 把生成时长压在 10% 以内 |
| 人审不覆盖门禁读的字段 | 审批后把镜头重新标成别的 `function`/`dna_role`，人审仍然有效 | 两者纳入 `COPY_FIELDS`，改标签即 STALE |
| “没有复用”可以不看就打印 | 没有存下帧、或存下的帧全是近纯色时，泄漏检查返回空列表并打印“干净” | 检查区分 `compared` / `flat` / `none`：只有真正比对过才能通过；全是近纯色帧记 WARN（“已报告、未测量”）；一帧未存为 FAIL |

| 事实 | 值 |
|---|---|
| 实测静帧 | `measure_video` 的 `longest_freeze_run_s`（作用于 `final/easel.mp4`）；`require_render=False`（`stage_gate` 的渲染前声明）回退到声明镜头时长 |
| 参考片泄漏 | 能抓逐字节复制的帧；裁剪过或调过色的搬运抓不到——那仍需人眼 |
| 测试 | `tests/test_reference_replication.py`（37）、`tests/test_evidence_cut_qc.py`（16）、`tests/test_code_animation_composition.py`（27）；`dev_check.py` 61/61 suites |

### 第三轮：问一句“这些门禁会不会误杀诚实的片” — 2026-10-30

第二轮补的是“不诚实的片能通过”。同一轮对抗扫描也提出了八条“**干净的片被拒**”
的说法。每一条都先复现再采信：六条属实并已修复，两条被实验**否掉**，没有为了让它们
通过而放松任何阈值。

| 误判 | 对诚实项目做了什么 | 现在的行为 |
|---|---|---|
| 没量过的占比读成 0% | 全是 `vector_animation` 的故事板既非实拍也非生成，占比打出 `0.0`——一部根本没被量过的片被报成“0% 真实” | 占比输出 `value: null` 和“未测量”；EVIDENCE_LED 账号仍为 FAIL，未测量不能证明符合要求 |
| 生成上限写死 10% | 1024 DNA 的画面预算里 25% 是矢量、5% 是对比卡，别名表又把这些生成画面映射进该预算，于是**符合自己 DNA** 的片被另一个常数拒掉 | 上限取账号自己的非证据份额（1024 为 30%）；无 DNA 时仍用 10% 地板。`qc_video` 与 `cut_qc` 同步修正 |
| 单集不能比账号更严 | 账号的值被无条件覆盖到单集上，一部自己声明“禁录”却仍用了录屏的片，被当成允许录屏来评 | 录屏限制可以更严格；证据模式各有不同保护，不允许单集替换账号模式 |
| 一个未列名画面单独判死 | 4% 的标题卡被判“没有 DNA 预算”，而它本就在已声明预算自带的 ±8pp 容差内 | 未列名角色合成一个残差，只有残差整体超过容差才算漂移 |
| 0 字节 SRT 打败真字幕 | 空文件“存在”所以被选中，烧了字幕的片被报成没字幕 | 没有时间轴行的文件是占位符；优先选第一条有 cue 的候选；全都只有占位符时仍点名占位符 |
| 没有字幕时 `qc_video` 直接崩 | 对 `None` 调 `.exists()`，整份报告在算出第一个占比之前就中断 | 缺字幕是一行 WARN，报告完整跑完 |
| 四道门禁各拼一种“实拍” | 诚实的 `screen_recording` 在一处算证据、在另一处什么都不算、在第三处丢掉占比 | 统一 `CAPTURE_SPELLINGS`，由 claim、cut、QC 共用；手绘 `diagram` 也作为真实产物纳入 |
| 权利范围六种合法答案只认四种 | `licensed` 与 `permission_granted` 被判 `RIGHTS_SCOPE` | 两种都接受；比较前统一规范化范围字符串 |

被**否掉**的两条：两张共用背景的 6 秒卡会被量成一段 12 秒静帧（实测 5.8 秒，且所引
真实作品自己声明的镜头本来就超过 10 秒）；两张无关画面的 32×32 缩略图会撞成同一字节
（实测平均绝对差 31.1/255）。门禁经受住了这两个实验，没有为它们调整阈值。

写这些回归时又发现一处缺陷：`--check` 会从磁盘上已有的收据**继承** `plan_sha256`、
`target_s`、`beats`、`reference_video_sha256`（没有旧收据时则一个都不写），于是 PASS
可能指向一份已经变过的计划；`--frames` 又会用帧清单覆盖派生收据。现在帧有自己的收据，
`--check` 绑定到它实际评过的计划与成片。

### 后续可靠性修复 — 2026-10-30

动效合成现在将时间线和语音文本与已审批 SRT 比对，并将时间线及声明的主持人输入绑定到审核包。后续 ASR 失败会撤销先前的主持人验证。由于尚不能证明外部渲染器的完整依赖，`--skip-render` 当前仍会重新渲染；组合结果必须带有与输出匹配的摘要。这些已用测试夹具验证，而非真实生产重渲；现有人工审核的新鲜度仍缺少通用的下游验证。锁定输入回归测试改用独立的临时 Git 仓库，不再修改当前工作区索引。

**这仍然不做两件事。** 一是不证明成片每一拍就是计划点名的那个拍——节奏现在是实测的，但一部长度和运动量都对、内容却不对的片仍可能通过。二是 1024 DNA 自身存在一个只有 Founder 能定的矛盾：`narrative.template` 包含 `COST_AND_LIMITS`，而 `narrative.template_coverage.deferred` 又把同一个拍声明为延后。计划跟随 `template`；改它属于账号决策，不是代码能替它决定的事。

### 账号拥有成片时长 — 2026-10-30

`audio_first_plan.py` 用刚合成出来的口播长度去定义 `target.duration_ms_range`，于是成片
自己声明了它恰好占据的那个窗口，自己的 `duration` 检查永远不可能失败。一个 25 秒的未来智能
样片因此看起来“符合”，而该账号 DNA 要求的是 90–120 秒，整条流水线没有一处发现。

`cut_qc` 现在把实测媒体与账号自己的 `narrative.target_duration_s` 单独比对，产出
`account_duration` 检查（FAIL 级）；音频优先收据同时写入 `duration_contract`，实测落在窗口
之外时给出警告。计划仍然会写出——允许原型存在——但它不能再被报成符合账号合同。这条检查
不接受单集自己的声明，只认账号窗口。

对当前门禁的实测（在项目副本上运行，未覆盖任何既有收据）：

| 项目 | 结论 | 细节 |
|---|---|---|
| `easel-fi-audio-first` | **FAIL** | `account_duration` 25.00 秒 vs 90–120 秒；其余检查全部通过，含 `account_composition` 70/20/10 |
| `easel-fi-what-is-agent` | 无法评级 | 没有 `script/cut-plan.json`；它的历史只有 `qc_video`（WARN），而那条路径从来没有账号时长门 |

`qc_video.py` 保留通用的 30–120 秒 `duration_range`，级别是 WARN。它是技术检查，不是验收
路径：`build_evidence_package.py` 走的是 `cut_qc`，账号窗口现在落在那里。

**需要账号主人决定、而不是由代码决定：** 未来智能的画面配比 100% 不是实拍（70/25/5），
因此“账号没花在实拍上的份额”推导出的生成素材上限对这个账号等于 100%。一张 AI 生成插图
可以填满整部片且仍然通过 `generated_ratio`。DNA 禁止用生成物冒充证据，但没有给数字；
旧门禁的固定 10% 在这个账号上同样没有依据。这个数字需要人来定。

**同一轮修掉的两处测试安全问题。** `test_locked_input_reproducibility.py` 在导入时依赖被
Git 忽略的历史字幕，干净检出会让整个模块失败；现在它是可选项，唯一需要它的场景按名跳过。
`test_minimax_voice_clone.py` 会把合成 WAV 暂存进本仓库的真实索引，现在改为在独立临时
测试仓库里进行。锁定输入套件也不再在有场景被跳过时打印“All 10 passed”。

**本轮未改变：** 固定运行时仍是 981/982 个 blob 匹配，一处不一致
（`skills/openclaw/video-script/SKILL.md`）、一处额外文件
（`skills/openclaw/video-script/references/benchmark-playbook.md`）。被改的正是未来智能
脚本步骤路由到的那个 skill，而这处改动与 ADR-001 的“不修改上游源码”相冲突。恢复它属于
受保护目录决策，需要 Founder 批准。

### 两条工作流，一个入口 — 2026-10-30

两个账号都能独立出片，而且出的不是同一种片：

| 账号 | 模式 | 链路 | 画面配比 |
|---|---|---|---|
| `x-superplay-1024` | `EVIDENCE_LED` | `audio_first_plan` → `recording_plan` → `capture_terminal_evidence` → `build_evidence_package` → `qc_video` | 70% 实拍录屏 / 25% 矢量 / 5% 对比卡 |
| `x-superplay-future-intelligence` | `EXPLANATORY` | `audio_first_plan` → `build_evidence_package` → `qc_video` | 70% 矢量 / 25% 代码 / 5% 指标图 |

在这之前，生产代码里**没有任何一处**读账号来决定走哪条：DNA 的 `skill_route` 表只被
`check_account_dna.py` 校验能否解析，没有任何生产者读它；选路只存在于运行手册和执行者的
记忆里。

`scripts/account_route.py` 把它变成可执行的：`project.yaml` → `account_slug` → DNA →
由账号 `evidence.mode` 推出的有序链路，同时回显同一份 DNA 里的创作类 skill 归属。没有账号
的项目、没有声明流水线的模式，一律拒绝，绝不猜。一条命令，让“这个项目走哪条工作流”由账号
回答，而不是由记忆回答。

两条链最后都汇到 `build_evidence_package` 与 `qc_video`。这是有意的：目标不是共用生产者，
而是共用收据底座。路由器只说明该跑哪条链，**不认证结果**——成片是否属于该账号，仍由
`cut_qc` 判定。

### 一条片，三个平台 — 2026-10-30

抖音、B站、小红书要的不是同一个画幅，而在此之前流水线只能产出并校验竖屏那一个。

- `qc_video.py` 一直用常量 1080x1920 判所有项目，于是仓库里自己的横屏项目
  （`easel-engineering-proof`，64 秒，1920x1080）被读成"坏掉的竖屏"。现在它按
  `project.yaml` 声明的 `format` 判，没有项目的文件可用 `--expect WxH` 指定。
- `derive_variants.py` 用固定运行时的 `reframe.py` 从已评级的母片派生其它画幅
  （不允许手写滤镜链），逐个探测输出，并写 `receipts/variants.json`，把母片、
  每个衍生片和实际运行的工具文件摘要一起绑定。
- 它拒绝没有评级的母片、比母片更旧的收据，以及自己 QC 就 FAIL 的母片。
  **一个 FAIL 就够了**——另一个门禁更新的 PASS 不能覆盖它，因为两个门禁查的是
  不同的东西。
- 封面只报告、不裁剪：收据按平台写 PRESENT / ABSENT / WRONG_FRAME，修法是按该
  画幅重新出卡，而不是把为另一个画幅排好版的卡裁一刀。

对真实项目的实测：`easel-1024-proof` 今天不能被派生。它的 `qc-report.json` 是
FAIL（`account_composition` 73/27/0 对 70/25/5），所以派生步骤以
`MASTER_QC_FAILED` 阻断。这正是"下次能不能三平台发布"的答案：母片先过自己的门，
给一部没过的片换三种画幅，只会得到三份没过的片。

仍挡在"可发布"之前的、且不是代码能解决的：带评分的人工审核、任何录制证据的
拍摄权利与去敏，以及——对 未来智能——一部达到自己 90–120 秒窗口的母片。

### 一个仓库，三条平台轨道 — 2026-10-30

仓库现在承载它发布到的每个平台的工作流，而不是"一条轨道 + 一个即将消失的外部依赖"。

| 轨道 | 位置 | 状态 |
|---|---|---|
| 视频（抖音 / B站 / 小红书 / 视频号） | `src/contentops`、`scripts/` | 生产者与门禁齐全；母片仍须先过自己的 QC 才允许派生 |
| 公众号 | `vendor/gzh-thinktank/` | 逐字节导入：679 个文件、8 MB、十阶段门禁、自铸收据 |
| X | — | 未开始：没有账号 DNA，也没有发布能力 |

**公众号为什么改为入库而不是留外部。** 那个工作副本的历史与 GitHub origin **分叉**
（`origin/main` 是 `e9303d1`，副本是 `93645f1`），而且副本（可能连远端）即将退役。
一个注定会消失的外部依赖不是依赖，是缺口。导入保持逐字节、不修改；要变更就是重新
导入并更新摘要。

- 排除项：`node_modules`（32 MB）与 excalidraw 包里的 `.venv`（可重建）、
  `.aws-article/config.yaml`（凭据）、账号的 `production/` 产物。完整的原始仓库
  （含分叉时没上 GitHub 的全部提交）是 `D:\Archives\repos\gzh-thinktank\` 下的
  15 MB git bundle。
- `scripts/gzh_pin.py` 两样都校验：bundle 按摘要、vendored 树按 679 个文件的内容
  摘要。`tests/test_gzh_pin.py` 锁住拒绝行为。
- 工作流仍要求作品目录在它自己的根之外，因此文章落在 `projects/gzh-thinktank/`
  （通过 `GZH_ARTIFACT_ROOT`），手建文章目录仍会被拒绝。

**三个预期内的失败，都不是导入造成的。** vendored 的 `validate_matrix.py` 报三项：
故意排除的凭据配置，以及 `gzh-draft-publisher` 的两处 hash drift——这两处在原副本里
一模一样，因为它的 `split-manifest.json` 在发布脚本改动后没有重新生成。导入的树
不打算掩盖这一点。

**发布行为不变。** vendored 流程仍然止于公众号草稿 + `draft/get` 回读。本仓库不会
公开发布任何内容，凭据也没有进入任何一棵树。

### 内容路由器——账号感知的选题层——2026-10-30

流水线能做出片子，却答不上前置的两个问题：**这是为谁做的**，以及**这讲的是什么**。
答案原本散在两份没人要求过的热榜和某个人的脑子里，两边都没有留下记录。
下游因此分辨不出这两者，也就无法对其中任何一种施加约束。

`src/contentops/routing/` 就是这两个答案与流水线之间的一层。两条路线从这里进入，
产出同一个合约。

| 属性 | 取值 |
|---|---|
| 入口 | `scripts/content_route.py`——`accounts`、`start`、`candidates`、`select`、`status`、`resume`、`approve` |
| 路线 | `HOTSPOT_DISCOVERY` 与 `USER_TOPIC`，必须显式指定；不指定返回 `ROUTE_SELECTION_REQUIRED` |
| 合约 | `contentops.content-intent/v1`——两条路线同一个形状；与路线相关的字段全部放在 `route_context`，其键在两种模式下完全相同 |
| 磁盘上的 Brief | `00_brief/brief.json`——`contentops.content-brief/v1`，内含 intent，外加 `contentops.content-candidate/v1` 与 `contentops.evidence-feasibility/v1` |
| 账号输入 | 账号 DNA 新增的 `discovery` 块：关键词、来源白名单与黑名单、权重、审核策略 |
| 排序 | 七个分量，权重由账号自己给出（合计 100），每个分量都带解释；榜单自身名次从不作为排序依据 |
| 来源 | 注册表共 15 个；每个都声明 `NATIVE_SEARCH` 或 `LIST_ONLY`，计划会为列出的每个来源写明是哪种 |
| 存储 | SQLite，位于 `.local/content-router/`，按账号隔离；候选的每次读写都带账号 id |
| 测试 | `tests/test_content_router.py`、`tests/test_hotspot_sources.py`、`tests/test_account_discovery.py`——全部离线运行，均已写入 CI |

### 由 DNA 决定检索，而且不能被改写成别的意思

账号定位在抓取之前就被读取。它的关键词决定向来源问什么，白名单决定哪些来源会被访问，
内容支柱决定候选落在哪个货架，not_doing 决定哪些候选在人工看到之前就被淘汰，
权重决定候选列表的顺序。

**每个关键词都引用它取自的 DNA 字段，而且这条引用由机器校验。**
`scripts/check_account_dna.py` 会在同一份 DNA 里解析它；凡是 origin 无法解析的关键词，
DNA 检查直接失败。不存在任何一条路径，能让一个无出处的词进入检索。
英文关键词可以声明为某个中文词的 `translation`——翻译是换一种语言表达已有的词，
而不是新增一个定位主张——但中文出处同样必须能解析。

没有 `discovery` 块的账号，热点检索会被 `ACCOUNT_DNA_MISSING` 拒绝。
它只被警告而不算失败，因为路由器会指名拒绝它，而指定主题路线对它仍然可用。

### 状态机才是重点

一台状态机，没有强制路径。

| 状态 | 含义 |
|---|---|
| `ROUTE_SELECTION_REQUIRED` | 没有指定路线；不会发生任何别的事 |
| `ACCOUNT_DNA_MISSING` | 账号没有可用的 discovery 块 |
| `SEARCH_PLAN_READY` | 检索计划已写下；尚未抓取任何东西 |
| `CANDIDATES_READY` | 候选列表已生成。这里到 `BRIEF_READY` **没有边**：选题由人决定，否则不做 |
| `TOPIC_SELECTED` | 有人具名选定了一个候选 |
| `OUT_OF_PROFILE_REVIEW_REQUIRED` | 用户主题不在账号自身声明覆盖范围内；所有者可以改主题，也可以明确批准例外，例外会记录是谁、为什么 |
| `BRIEF_READY` | Brief 包已写盘，并通过仓库既有的校验器 |
| `AWAITING_HUMAN_APPROVAL` | Brief 等待人工审核 |
| `APPROVED_FOR_PRODUCTION` | 有人确认这份 Brief 可以进入流水线 |
| `BLOCKED` | 终态；记录是什么拦住了它 |

运行不会改变路线。来源挂了是报告失败的理由，不是绕道找题的理由。

### 三件刻意不宣称的事

- **Brief 不是事实核查。** `evidence_status: verified` 指的是证据**路径**已被记录。
  下游那道复制评审关卡保持原样，仍然是脚本与渲染之间唯一的门。这里是**另一道处于
  不同位置的关卡**——生产之前，而不是渲染之前——它本身不授予发布或付费媒体权限。
  有一条测试断言 `src/contentops/routing/` 下没有任何模块触及媒体或发布路径。
- **过滤后的榜单不是搜索。** NewsNow 和 TrendRadar 发布的是预先排好的榜单，不接受
  关键词查询；GitHub 搜索 API 才是真正的服务端查询。每个来源都写明自己是哪一种，
  计划也会重复一遍。读一份热门榜单并留下合适的部分是正当做法；把它称作搜索不是。
- **不同平台的计数器绝不相加。** 浏览量和热度指数不是同一个量纲。它们被记录在候选上，
  标记为 `metrics_comparable: false`，并且不进入评分。唯一的跨源信号是"不同来源的
  数量"，这是关于覆盖范围的事实，而不是不可比的量纲之间的比较。

### 尚未完成的部分

- **TrendRadar 已部署，且只固定一个版本。** `D:\Software\sansan0\TrendRadar\v6.11.0`
  的真实部署在 2026-10-30 完成了一次采集，写出 `output/news/2026-10-30.db`
  （255 行、11 个平台），适配器只读它。此前"适配器能读本地数据库"的说法只对
  *fixture* 成立：真实 v6 的 Schema 是 `news_items` + `platforms`，适配器已按其重写。
  没有 `TRENDRADAR_DB_PATH` 时仍返回 `SOURCE_UNAVAILABLE_STATE`，运行跳过它继续。
- **真实采集发生过一次。** 两条路线在 2026-10-30 都对真实来源跑通并到达
  `APPROVED_FOR_PRODUCTION`；数字见 `research/router-precision-audit-2026-10-30.md`。
  当天有三个 NewsNow 端点返回 500，被记为失败，而不是被当作不存在。
- **七天的观察数据并不存在。** `scripts/router_observe.py` 每账号每天记录一行，
  目前只记录了一次；说法到此为止。
- **1024 的候选产出很差，且没有做任何定位变更。** 211 条里只出 3 条且都偏弱；
  能改变这一点的建议写在审计里，等账号所有者批准。

### 第二轮——加固，2026-10-30

| 方面 | 现在为真的事实 |
|---|---|
| TrendRadar | 真实 v6 Schema、平台名、UTC+8 时间戳、超过 24h 标记 `stale`、条目以 `STALE_SOURCE` 被拒 |
| 失败处理 | 429/5xx/超时/截断响应重试 3 次并退避；401/403/422 不重试；本进程内连续 3 次失败后熔断 |
| 审批 | 必须 `--confirm`；`automation` 身份除非显式允许一律拒绝；审批与内容摘要绑定；`verify` 报 `APPROVAL_STALE`；失效审批无法创建工程 |
| 交接 | `scripts/brief_handoff.py` 校验摘要与证据预测，写出 `00_brief/handoff.json`；真正流水线入口在 copy review 处阻塞，不花钱 |
| 观察 | `scripts/router_observe.py` 每账号每次运行写一行 JSONL；`--report --days 7` 打印窗口 |

### 第三轮——精准度、定时任务与审批边界，2026-10-30

| 方面 | 现在为真的事实 |
|---|---|
| 查询表达式 | `discovery.query_expressions` 让账号按适配器选择：把自己已声明的哪些关键词花在某个来源有限的 operator 预算上；每个词都引用它渲染的关键词，DNA 检查逐条验链。用 `scripts/router_query_experiment.py` 实测：future-intelligence 在 GitHub 上 0.233 → 0.567，保留其表达式；1024 实测**更差**（0.200 → 0.133），因此移除而不是为对称而保留 |
| 候选精确率 | 按各自定位人工判读：future-intelligence **11/12 = 92%**，1024 **1/8 = 12.5%**——见 `research/router-precision-audit-2026-10-30.md`。1024 的短板是匹配语义（垃圾仓库能通过它的门禁），不是查询问题，修它属于定位决策，等账号所有者 |
| 定时采集 | `scripts/router_schedule.py` 跑一个周期：经 TrendRadar 入口抓取、发现最新数据库、采集、写回执。锁让第二个运行以 `ALREADY_RUNNING` 结束，超过三小时的锁视为废弃，数据库被锁时回退到前一天，`status` 报告漏跑 |
| 审批边界 | 自动审批例外现在同时需要 `allow_automation=True` **和** `CONTENTOPS_TEST_SANDBOX=1`；命令行不再暴露它，因此生产的工作流参数无法开启。保证被明确限定为内容绑定加审计留痕——没有身份提供方，文档也这么说 |
| 下游 | 两条路线经同一个 `contentops.brief-handoff/v1` 记录交接；`script_state()` 把缺失的 `script/lines.json` 与 `script/assets.json` 作为命名状态报出，而不是留到下游崩溃。脚本与分镜生产仍未实现，已登记为独立里程碑 |

### 尚未开始：M-ROUTER-SCRIPT（脚本与分镜生产）

路由器把已批准的 Brief 交给工程后即停止。把 Brief 变成 `script/lines.json` 与
`script/assets.json`——也就是旁白与分镜——的部分尚不存在，`scripts/brief_handoff.py`
把这两个文件作为命名缺口报出，而不是写一个占位文件。

该里程碑的范围：以 `00_brief/handoff.json` 为输入，在 `script/` 下产出这两个文件，
每条主张都要能追溯到 Brief 的 `source_artifact_refs`，并且和其他生产者一样停在
copy review。它不得自行调用付费服务，也不得把自己标记为已审核。

### 第四轮——质量门禁、无人值守与依赖台账，2026-10-30

| 方面 | 现在为真的事实 |
|---|---|
| 来源质量 | `contentops.hotspots.quality` 只在**两个相互独立**的信号上拒绝仓库，证据留在记录里；无法检视的一律 `UNVERIFIED` 通过。在 1024 的同一快照上实测：7 → 6 条候选，移除 1 条夹具，**误杀 0**；剩下两条"真实但跑题"的项目不归它管 |
| 精确率，如实分开 | 自动门禁通过率 6/7 = 86%，人工标注精确率 4/6 = 67%（宽口径）、0/6（严格口径）。门禁移除的是夹具，不是跑题 |
| 回归 | 未来智能：40 条候选，门禁拒绝 0 条。无跨账号变化 |
| 无人值守 | 调度器在回执旁写每次运行的日志；`pythonw` 无控制台（`sys.stdout is None`）也能跑通，并已用隐藏的 `Start-Process` 实测 |
| 审批边界 | 自动审批的 Brief 现在**根本无法交接**给流水线（`AUTOMATION_APPROVAL`），而不只是标个记号 |
| 依赖台账 | 91 个父提交里只有 12 个碰过路由器依赖的文件；真实依赖是 **8 个路径、+2051 行、全部为新增** |

### 第五轮——脚本阶段，2026-10-30

| 方面 | 现在为真的事实 |
|---|---|
| 脚本草稿 | `scripts/brief_script.py` 把已批准的 Brief 变成 `lines.json`、`claim-map.json`、`storyboard.json`、`master.md` 和"主张→来源"报告。**没有任何模型调用**：每一句被念出来的话都是转场、来源自己标题的引用（绑定到记录下来的文档），或 CTA |
| 契约复用 | 它说仓库既有的 `contentops.claim-map/v1` 与 `contentops.audio-first-lines/v1`；复制评审本来就会对两者取指纹，所以之后改动会让评审失效，无需新代码 |
| 拒绝 | 证据预测 `DEGRADED` 或缺来源 → `EVIDENCE_REQUIRED`；Brief 被改动 → `APPROVAL_STALE`；沙箱之外 → `AUTOMATION_APPROVAL` |
| 终态 | 草稿停在复制门禁的 `NOT_REVIEWED`，且不写任何评审记录。M-ROUTER-SCRIPT 不再是"未开始"；剩下的缺口是人写的文案，不是机器 |
| 已知限制 | 草稿的事实内容只有一句被引用的标题。没有模型的生成器写不出实质内容，假装能写才是这一阶段存在要防的事 |
