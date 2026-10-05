---
translation_of: docs/CURRENT-STATE.md
language: zh-CN
translation_status: synced
---

# 当前状态

[English](CURRENT-STATE.md) | [简体中文](CURRENT-STATE.zh-CN.md)

> 当前运行状态。仅经验证的事实。无展望，无过时声明。
>
> 最后验证：2026-10-04

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
