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
| 成本 | 每周 H3 配额 7 pp（81 % → 74 %），一次 create |
| 披露 | `labelled_ai_synthesised: true`、`speech_text_verified: false` —— 本机无 ASR，必须由创始人听一遍确认台词 |
| 状态 | `production_ready: false`、`PENDING_FOUNDER_REVIEW` |

本次构建暴露的三个缺陷被记录而非抹平：

- ERAS 表最初沿用旧的 43.5 s 节奏；新增回归测试把每一段时长绑定到 `motion/timeline.json`；
- p03 源片长 2.900 s，而窗口 3.009 s，适配器只允许用末帧补齐**连续尾部**，中间缺帧仍然失败；
- 引擎在加载时绑定 `#scrub`/`#tt`/`#play`，并按相对路径声明 `lib/fonts/*.woff`，因此项目页面需要这些控件和 `<base href="/engine/">`，两者都有测试覆盖。

变体的 `freeze_s` 为 2.4 s，基线为 0.6 s。对桥段做 PSNR 比对（t=23.0 与 t=24.2，y = 21.8 dB）说明桥段并非静止帧，因此该数字按实测报告，不做解释性掩盖。加入数字人开场后，又用 5 fps 帧差把冻结定位到 **5.2–7.8 s**，即 p02 架构图卡片；HEAD 上未含开场的旧构建存在同样的 2.4 s 冻结与同样的 reason 字符串，因此它早于本次开场存在，不是开场造成的。该缺陷保持未修、可见。

数字人构建中的两个缺陷：

- presenter 段必须声明 `"variant": "eras"`；不声明就会进入基线时间线、说出没人写过的台词，因此 `_validate_segments` 直接拒绝；
- eras 构建器最初到 `work/clips/` 找所有片段，这会要求覆盖基线产物；现在 `_clip_path` 只在 eras 变体下读取 `work/eras/clips/`。

两者都有测试覆盖，BGM 铺底的 `amix` 延迟同样有测试——它保证铺底不会压在清唱人声下面开始。
