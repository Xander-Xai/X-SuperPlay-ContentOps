---
title: MiniMax M Plan 声音克隆权益核验
canonical: false
type: research
status: current
issue: "#23"
checked_at: "2026-10-04"
language: zh-CN
translation_of: research/providers/minimax-voice-clone-entitlement.md
translation_status: synced
---

# MiniMax M Plan 声音克隆权益核验（Issue #23）

> 研究材料，不是规范设计。规范的能力状态以
> `docs/MEDIA-PROVIDER-CONTRACT.md` 与 `docs/CURRENT-STATE.md` 为准。
>
> English: [minimax-voice-clone-entitlement.md](minimax-voice-clone-entitlement.md)

## 结论

```
DOCUMENTED_BUT_NOT_TESTED
```

没有尝试任何克隆。有两个阻碍，都不是 agent 能自行清除的：账号实名认证状态未知，
并且本仓库中不存在权利清晰的真人语音样本。

## 当前官方来源怎么说

2026-10-04 在账号所属 region 复核。

| 问题 | 答案 | 来源 |
|---|---|---|
| 是否有编程可用的声音克隆 API？ | 有，`POST /v1/voice_clone` | 当前声音克隆 API 参考 |
| 是否需要旧的 `GroupId`？ | **不需要。** 当前 schema 没有 `GroupId` 参数 | 同上 |
| 官方 CLI 是否暴露该能力？ | **没有。** `mmx speech` 只有 `synthesize`、`generate`、`transcribe`、`recognize`、`voices` | `mmx speech --help`，v1.0.27 |
| M Plan 档位说明中是否提到？ | **没有。** 档位承诺的是"图像与音频生成"；克隆属于音色管理，未被提及 | 当前 M Plan FAQ，两个 region |
| 是否有权益相关错误码？ | 有：**`2038` 无复刻权限，请检查账号认证状态** | 声音克隆 API 参考 |
| 是否有单独计费说明？ | 可选的**试听**按 T2A 正常计费，定价与 T2A 一致。克隆调用本身没有单独计费说明 | 同上 |
| 是否要求先实名认证？ | **是。** "调用本接口前，请先完成个人或企业认证" | 同上 |
| 克隆是否会过期？ | 会，若 7 天内未正式调用将被删除 | 同上 |

### 语音权益不等于克隆权益

M2.0 已经确认语音合成被覆盖。M Plan 页面承诺"图像与音频生成"，全文没有任何地方
提到声音克隆，而 API 为此定义了独立的权益错误码。由语音覆盖推出克隆覆盖，正是本
仓库拒绝做出的那种推断，因此状态保持未证实，而不是往任一方向假设。

## 为什么没有尝试克隆

### 阻碍一 —— 没有权利清晰的语音样本

克隆需要一段真人录音。本仓库中唯一被追踪的音频是项目自己脚本的**合成 TTS 输出**
（`projects/easel-review/assets/voice_easel/narration.mp3` 以及各分镜文件）。
克隆一个合成声音既是拙劣的技术测试，也没有任何权利基础，因此没有尝试。

本仓库对此的禁止是绝对的：不使用名人、创作者、播客主、公共人物或未知数据集说话人。

**需要 Founder 提供。** 一份符合当前官方规范的权利清晰样本：

| 要求 | 取值 |
|---|---|
| 格式 | `mp3`、`m4a`、`wav` |
| 时长 | **至少 10 秒**，最多 5 分钟 |
| 大小 | 不超过 20 MB |
| 说话人 | 仅限一人 |
| 录音条件 | 干净，无背景音乐，无重叠说话 |
| 可选提示片段 | 少于 8 秒，并附其准确文字作为 `prompt_text` |
| 可选 ASR 校验 | `text_validation` 不超过 200 字符，`accuracy` 默认 0.7 |

`need_noise_reduction` 与 `need_volume_normalization` 存在但默认关闭，因此一段干净
录音可以避免依赖它们。

### 阻碍二 —— 认证状态未知

API 要求首次调用前完成个人或企业认证，缺失时返回 `2038`。本账号是否已认证，
不实际调用就无法确定，而不实际调用正是当前被拦住的动作。

## 如果将来授权测试

1. 确认 `MINIMAX_SUBSCRIPTION_KEY` 的类别为 `SUBSCRIPTION`。
2. 运行计费前置检查：按量付费余额、积分包、代金券、欠费全部为零，且周套餐额度
   可读且有剩余。任何一项非零或读不到即 `BLOCKED_BILLING_SOURCE_UNCERTAIN`，
   不发送请求。
3. 上传样本，然后创建**一个**克隆。不自动重试。
4. 记录：前后额度、克隆状态与 `base_resp.status_code`、模型兼容性、新
   `voice_id`（**仅以加盐哈希记录**）、输出哈希。绝不记录原始样本、原始
   `voice_id` 或私有身份数据。
5. 可选用克隆音色合成**一句**短文本以证明 `voice_id` 可用，同样受该门禁约束。
6. 若账号已认证却返回 `2038`，则判定为 `NOT_ENTITLED`。若订阅 Key 克隆成功且
   所有余额仍为零，则判定为 `VERIFIED`，并同时证明克隆路径只消耗套餐内额度。

## 传输通道影响

声音克隆需要使用**已文档化的公开 API**，因为官方 CLI 没有克隆命令。这与现行传输
优先级一致：官方 CLI 优先，能力缺口使用已文档化公开 API，绝不使用未文档化端点。
未文档化的余额读取仍然只来自 `BillingGuard`。