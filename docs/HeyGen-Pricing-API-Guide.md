# HeyGen Pricing & API Guide

> 来源：HeyGen 官方定价页 + Help Center + Developer Docs
> 整理时间：2026-10-02
> 适用场景：数字人视频自动流水线（Python / n8n / REST API）

---

## 1. 个人套餐（Web 端）

| 套餐 | 价格 | 额度 | 单视频长度 | 分辨率 | 更适合 |
|---|---:|---:|---:|---:|---|
| Free | $0 | 3 条/月 | ≤1 分钟/条 | 基础输出 | 测试 HeyGen |
| Creator | $29/月 | 600 credits/月 | ≤30 分钟/条 | 1080p | 正常个人创作 |
| Pro | $49/月起 | 1000 credits/月起 | ≤30 分钟/条 | 4K | 高频生成/高级模型 |

**关键澄清：**
- Free 的 "Videos up to 1 min" = **每个视频最长 1 分钟**，不是三视频加起来 1 分钟
- Creator/Pro 的 "Videos up to 30 mins" = **单视频最长 30 分钟**，不是每月只能生成 30 分钟
- Creator/Pro 已改为 **Credit 制**，不同模型消耗差异极大

### Creator/Pro Credit 消耗参考

| 模型/功能 | 消耗（credits/分钟） |
|---|---:|
| Avatar III Video Look | 4 |
| Avatar III Photo Look | 7 |
| Avatar IV Photo Look | 16 |
| Avatar IV Video Look | 31 |
| Avatar V | 48 |
| Video Agent Standard | 40 |
| Video Agent Seedance | 120 |

**600 credits 粗算：**

| 模型 | 理论可生成量 |
|---|---|
| Avatar III Video | ≈150 分钟 |
| Avatar III Photo | ≈86 分钟 |
| Avatar IV Photo | ≈37.5 分钟 |
| Avatar IV Video | ≈19.4 分钟 |

**1000 credits 粗算：**

| 模型 | 理论可生成量 |
|---|---|
| Avatar III Video | ≈250 分钟 |
| Avatar III Photo | ≈143 分钟 |
| Avatar IV Photo | ≈62.5 分钟 |
| Avatar IV Video | ≈32 分钟 |
| Video Agent Standard | ≈25 分钟 |

### Creator vs Pro 的核心差异

Pro 比 Creator 多出的能力主要是：

1. **Credits 翻倍且可升档**：1000 credits 起，最高可配置到 **100,000 credits/月**
2. **4K 导出**：Creator 仅 1080p，Pro 支持最高 4K
3. **Advanced AI Models**：Pro 可访问全部高级模型（含 Avatar V、Video Agent Seedance）
4. **翻译脚本编辑/校对**：Pro 包含翻译后脚本编辑与校对能力

Creator 已能完成多数常规数字人任务。是否升 Pro 主要看 **是否需要 4K、是否需要高级模型、是否需要规模化 credits**。

### Creator/Pro 共同包含

- 1080p+ 导出（Pro 可升 4K）
- 无水印
- Voice Cloning
- 175+ 语言和方言
- Unlimited Photo Avatars
- 更快的处理速度
- 月付用户未使用 credits 可按规则滚存一个 billing cycle

---

## 2. REST API / Direct API

HeyGen 提供完整的 REST API，包括：

- Video Generation API
- Video Agent API
- Avatar API
- Voice API / TTS
- Video Translation API
- Lipsync
- Template
- Webhook
- Batch API（单批最高 100 请求）
- MCP（Model Context Protocol）

### ⚠️ 最重要：Web Plan Credits ≠ Direct API 余额

这是最容易踩的坑：

```
HeyGen 账户
├── Web Plan
│   ├── Creator ($29) → 600 credits → 仅限网页生成
│   └── n8n/Make/Zapier 集成（可用 Web Credits）
│
└── Direct API
    └── Pay-As-You-Go 独立钱包（API Key 调用）
```

**Creator 的 600 Web Credits 不会自动变成 Direct API 余额。**

### Direct API 定价（Pay-As-You-Go）

| Avatar 类型 | 720p/1080p | 4K |
|---|---:|---:|
| Avatar III (Photo/Digital Twin/Studio) | $1/分钟 | $1.2/分钟 |
| Avatar IV Photo | $3/分钟 | $4/分钟 |
| Avatar IV Digital Twin/Studio | $4/分钟 | $5/分钟 |

| 服务 | 价格 |
|---|---:|
| Video Agent | ~$2/分钟 |
| Video Translation (无 lip-sync) | ~$1/分钟 |
| Video Translation (Speed lip-sync) | ~$2/分钟 |
| Video Translation (Precision lip-sync) | ~$4/分钟 |

**最低充值：$5 起，无需购买 Creator/Pro。**

---

## 3. 三种接入路线对比

| 方案 | 计费 | 适合场景 | 自动化程度 |
|---|---|---|---|
| A. HeyGen 网页 | Web Plan Credits | 手动测试 | 人工操作 |
| B. REST API + PAYG | Direct API 余额 | 自建流水线（Python/FastAPI/OpenClaw） | 全自动 |
| C. n8n/Make/Zapier | Web Plan Credits（可用 Creator 额度） | 以 n8n 为核心编排 | 半自动 |

> **n8n/Make/Zapier 集成可以直接消耗 Web Plan Credits**，这是与 Direct API 的本质区别。

---

## 4. 自动化流水线推荐路径

### 阶段一：MVP 验证

```
HeyGen Web: Free
+
API PAYG: $5～$10

验证：
选题 → LLM 写脚本 → TTS → HeyGen API → Webhook → 下载 MP4 → FFmpeg 合成
```

### 阶段二：稳定生产

**若以 Python/FastAPI 为主：**

```
Direct API PAYG（按需充值）
成本估算：Avatar III + 1分钟视频 ≈ $1/条
```

**若以 n8n 为主：**

```
Creator $29 + 600 Credits ≈ 150分钟 Avatar III 视频
```

### 阶段三：规模化

```
Pro / Business / 更大规模 Direct API PAYG
```

---

## 5. 相关文档链接

- [HeyGen API Pricing](https://www.heygen.com/api-pricing)
- [HeyGen Developer Docs](https://developers.heygen.com/)
- [Credit-based Pricing Plans](https://help.heygen.com/en/articles/15125761-heygen-credit-based-pricing-plans-subscriptions-explained)
- [How to Use Credits](https://help.heygen.com/en/articles/15126059-how-to-use-credits-on-heygen)
- [HeyGen API Pricing Explained](https://help.heygen.com/en/articles/10060327-heygen-api-pricing-explained)

---

## 6. 关键结论

1. **Free = 每月 3 个视频，每个最长 1 分钟**
2. **Creator = $29/月 + 600 Credits，单视频最长 30 分钟，1080p**
3. **Pro = $49/月起 + 1000 Credits，支持 4K 和高级模型**
4. **HeyGen 完全支持 API 调用，无需网页人工操作**
5. **Creator/Pro 的 Web Credits 和 Direct API 钱包是两个独立账户**
6. **API 可以不购买 Creator/Pro，直接 Pay-As-You-Go 充值**
7. **n8n 集成可用 Web Plan Credits，与 Direct API 钱包互斥**
8. **Pro 与 Creator 的差异是 4K + Advanced Models + 更多 credits；多数常规场景 Creator 已够用**
