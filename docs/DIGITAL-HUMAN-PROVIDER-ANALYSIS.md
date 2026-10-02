# 数字人技术路线分析报告

> **研究日期**: 2026-10-01
> **汇率**: 1 USD ≈ 6.70475 CNY
> **目标**: 为 `douyin-1024` 确定数字人 Provider 策略

---

## 一、核心结论

数字人存在三条技术路线，**不是替代关系，而是分层使用**：

| 路线 | 特点 | 典型场景 | 代表方案 |
|---|---|---|---|
| **照片数字人** | 图片 + 音频 → 直接生成 | 普通 Hook、批量生产 | LivePortrait、百度照片数字人 |
| **小样本克隆** | 先训练一次 → 永久复用 | 长期 IP 建设 | 百度曦灵、HeyGen Digital Twin |
| **真人母版 + AI 改嘴** | 真人动作视频 + AI 只改嘴型 | 高自然度口播 | MuseTalk 1.5、LatentSync |

**战略定位**：
- 照片数字人 = 低成本快速铺量
- 小样本克隆 = 长期 IP 稳定性投资
- 真人母版 + 改嘴 = **自然度最高的一档**（身体是真的，AI 只管嘴）
- 本地 H3 = 高级动态 Hook

> **2026-10-02 补充**：第三条路线为新识别路线，详见 §2.3。
> 画面定位（数字人 = 小窗主持人层而非主画面）见
> [PRESENTER-LAYER-SPEC.md](PRESENTER-LAYER-SPEC.md)。

---

## 二、三条路线的详细分析

### 2.1 照片数字人路线

#### 2.1.1 路线特点

```
人物图片.png
     +
你的配音.wav
     ↓
数字人 API
     ↓
口型同步视频.mp4
```

**优点**：
- 不需要训练，立即可用
- 单次成本极低
- 可以随时换人物图

**缺点**：
- 每次生成都是"重新驱动照片"
- 人物一致性依赖模型能力
- 不适合长期 IP 建设

#### 2.1.2 推荐 Provider 矩阵

| 优先级 | 方案 | 6秒成本 | 需要训练 | 图片+自己音频 | 适合场景 |
|---|---|---:|---|---|---|
| **S** | **阿里百炼 LivePortrait** | **¥0.12** | ❌ | ✅ | 最值得先测，默认廉价方案 |
| **S** | **本地 H3** | ≈¥0 | ❌ | ✅ | 高级动态 Hook |
| **A** | **百度曦灵照片数字人** | **≈¥0.45** | ❌* | ✅ | 国内生产备选 |
| **A** | **阿里 EMO 1:1** | **≈¥0.48** | ❌ | ✅ | 便宜备选 |
| **A-** | **Hedra Character 3 540p** | **≈¥1.01** | ❌ | ✅ | 海外低成本备选 |
| **B+** | 阿里 EMO 3:4 | ≈¥0.96 | ❌ | ✅ | 画面更适合人物 |
| **B** | HeyGen Photo Avatar | ≈¥1.7~4 | ❌ | ✅ | API成熟但贵 |
| **B-** | D-ID | ≈¥235/月起 | ❌ | ✅ | 不适合短 Hook 模式 |
| C | 阿里 wan2.2-s2v 480P | ¥3.00 | ❌ | ✅ | 效果强但没必要 |
| C | 云端 MiniMax H3 | ≈¥3.2+ | ❌ | ✅ | 你已有本地 H3 |
| C | 腾讯照片免训练 | ≈¥4.17 | ❌ | ✅ | 功能完美但太贵 |
| D | fal OmniHuman 1.5 | ≈¥6.44 | ❌ | ✅ | 成本明显不合适 |

\* 百度照片数字人需要创建可复用资产（¥20），但不同于"训练数字分身"

#### 2.1.3 重点方案详解

##### 阿里百炼 LivePortrait（S 级推荐）

> **名称归属纠正（2026-10-02）**：**LivePortrait 是快手 / KlingAI 团队的项目，不是阿里。**
> EMO 才是阿里 Institute for Intelligent Computing 的项目。
> 本节的"阿里百炼"指 **API 提供方**（阿里云托管该模型），与 **模型作者**（快手）不矛盾。

**为什么最值得测**：
- 专门做"图片 + 音频 → 稳定人脸播报"
- 原图脸型保持好，不变形
- 参数可控：`template_id`、`head_move_strength`、`mouth_move_strength`

**API 示例**：
```json
{
  "model": "liveportrait",
  "input": {
    "image_url": "https://xxx/avatar.png",
    "audio_url": "https://xxx/hook.wav"
  },
  "parameters": {
    "template_id": "calm",
    "video_fps": 30,
    "mouth_move_strength": 1,
    "head_move_strength": 0.4,
    "paste_back": true
  }
}
```

**成本**：
- **¥0.02/秒 = ¥1.20/分钟**
- 6秒 Hook ≈ **¥0.12**
- 100条/月 × 6秒 ≈ **¥12/月**

**规格**：
- 图片最长边 ≤ 4096px
- 音频 1秒 ~ 3分钟
- 输出跟随输入图（可达 4K）
- 异步 API

---

##### 百度曦灵照片数字人（A 级）

**特点**：
- 官方定位：照片 + 语音 → 播报视频
- 支持透明背景视频

**成本**：
- 照片数字人创建：¥20/次
- 视频生成：¥4.5/分钟
- 6秒 Hook ≈ **¥0.45**

---

##### 阿里 EMO（A 级）

> **名称归属**：EMO 是 **阿里 Institute for Intelligent Computing** 的项目（与上面 LivePortrait 的归属相反）。

**限制**：
- 分辨率固定：1:1 → 512×512，3:4 → 512×704
- 最高 15fps
- 更适合半屏/角落主播

**成本**：
- 1:1 = ¥0.08/秒 = ¥4.80/分钟
- 3:4 = ¥0.16/秒 = ¥9.60/分钟

---

##### Hedra Character 3（A- 级，海外）

**优点**：
- 明确支持 Start Frame + Audio
- 支持 9:16、16:9、1:1、3:4

**成本**：
- 540P ≈ ¥10.06/分钟 → 6秒 ≈ **¥1.01**

---

### 2.2 小样本克隆路线

#### 2.2.1 路线特点

```
拍摄本人 30秒~几分钟视频
        ↓
训练 / 克隆人物
        ↓
avatar_id / figureId
        ↓
以后反复：
avatar_id + audio.wav
        ↓
数字人视频
```

**优点**：
- 人物一致性高
- 表情、动作更自然
- 长期批量生产更稳定

**缺点**：
- 需要一次性训练投入
- 不适合快速换人物
- 投入回本周期长

#### 2.2.2 推荐 Provider 矩阵

| 方案 | 克隆素材 | 训练成本 | 后续成本 | 适合场景 |
|---|---|---:|---:|---|
| **百度曦灵 2D小样本通用口型** | 1~4分钟视频 | **¥1000/人** | **¥3/分钟** | 国内首选 |
| **HeyGen Digital Twin + Avatar III** | 30秒~5分钟 | Studio自助创建* | **≈¥6.70/分钟** | 海外首选 |
| **D-ID V3 Instant Avatar** | 1~2分钟视频 | 订阅内 | **订阅制** | 全API化备用 |
| **火山引擎克隆数字人** | 单人视频 | **¥2599/人** | **¥6/分钟** | 国内备选 |
| **腾讯云2D小样本** | **5秒以上**视频 | **¥2500/人** | **¥3.33/分钟** | 高用量备选 |
| Tavus Replica | 1~2分钟 | 套餐含 3次/月 | **¥395/月** | 30秒最低计费，不适合短 Hook |
| AKOOL Instant Avatar | 短视频训练 | 套餐包含 | **≈¥6~10/分钟** | Business License 成本不友好 |
| Synthesia Personal Avatar | 1~5分钟 | 套餐内 | Creator ≈¥429/月 | 自传音频需 Enterprise |
| Elai Selfie Avatar | 短视频 | ¥1334/年/Avatar | Creator ≈¥194/月 | 处理周期 3~5 个工作日 |

\* API 创建 Digital Twin 仅 Enterprise 权限，但 Studio 自助创建后可用 API 调用

#### 2.2.3 重点方案详解

##### 百度曦灵 2D小样本（A 级，国内首选）

**训练要求**：
- 1~4分钟自然闭嘴真人视频
- 1080p/2K/4K 支持
- 官方 API：`POST /api/digitalhuman/open/v1/figure/lite2d/train`

**成本分析**：
- 训练：¥1000
- 视频生成：¥3/分钟
- 100条/月 × 6秒 = 10分钟/月
- 月生成费：¥30
- **第一年合计：≈¥1360**

**核心价值**：
- 跨几百条视频保持同一个"轩轩"
- 支持透明背景（`keepBackground: false`）
- 训练后是固定身份资产

---

##### HeyGen Digital Twin（A 级，海外首选）

**训练**：
- 官方建议 2~5分钟连续视频
- Studio 自助创建（不需要 Enterprise）
- 创建后用 `avatar_id + audio_url` API 调用

**成本**：
- Avatar III：≈¥6.70/分钟 → 6秒 ≈ **¥0.67**
- Avatar IV：≈¥26.82/分钟（明显过剩）

**关键限制**：
- API 创建 Custom Digital Twin 仅 Enterprise
- 但 Studio 创建 + API 调用完全可行

---

##### D-ID V3 Instant Avatar（B 级，全API化）

**优点**：
- 训练、授权、生成全部 API 化
- 支持 body/hand 运动
- 1080p 输出

**缺点**：
- 每 credit 最多 15 秒（6秒按15秒计）
- Launch 有 AI watermark
- Scale 套餐约¥929/月

---

##### Tavus Replica（C 级，技术好但不适合短 Hook）

**定位**：
- Starter 套餐约 ¥395.58/月，含 3 次自定义 Replica 训练 + 约 10 分钟 AI Video Generation
- 支持透明背景（alpha channel）

**关键问题**：
- **每条 Video Generation 存在 30 秒 minimum charge**
- 6 秒内容按 30 秒消耗计费

**结论**：不适合当前离线 Hook 模式，更适合未来"实时数字员工 / AI 分身"路线。

---

##### AKOOL Instant Avatar（C 级）

**特点**：
- 1080p 每 10 秒消耗 5 credits
- 约 ¥6~10/分钟（与 HeyGen Avatar III 接近）

**商业授权问题**：
- Pro Max 标的是 Personal License
- Business License（你需要的）月费约 **¥1169/月**
- 对 OPC 自媒体明显不划算

---

##### Synthesia（C 级）

**特点**：
- 1~5 分钟视频训练，约 1 个工作日生成
- Creator 年付等效 ≈ ¥429/月，含 5 个 Personal Avatar

**核心问题**：
- **上传自己的 Script Audio 需要 Enterprise 功能**
- 与你的"Voice Clone 解耦"架构冲突

---

##### Elai（C 级）

**特点**：
- Selfie Avatar：约 ¥1334/年/Avatar
- Creator 月费 ≈ ¥194/月

**限制**：
- Selfie Avatar 通常需 3~5 个工作日处理
- API 权益偏高阶方案

**结论**：有 HeyGen/D-ID/百度的情况下，无需优先接。

---

### 2.3 真人母版 + AI 改嘴路线（2026-10-02 新增）

#### 2.3.1 与照片数字人的本质区别

照片数字人（EMO / LivePortrait）需要 AI **凭空创造**：头部运动、表情、嘴型、眨眼、身体运动。
需要"猜"的东西太多 → 非常容易假。

真人母版路线反过来：**身体是真的，AI 只管嘴。**

```text
【照片数字人】
一张照片 → AI 猜测 → 头部运动/表情/嘴型/眨眼/身体 → 视频

【真人母版 + 改嘴】
提前录制一批真人动作视频
        ↓
保留真实的 头部 / 身体 / 手势 / 眨眼 / 光影 / 皮肤
        ↓
AI 只修改嘴巴
        ↓
自动生成新的口播
```

#### 2.3.2 母版素材库（一次录制，永久复用）

| 文件 | 内容 |
|---|---|
| `idle_01.mp4` | 正常说话 |
| `idle_02.mp4` | 微微点头 |
| `explain_01.mp4` | 手势解释 |
| `explain_02.mp4` | 比数字 |
| `think_01.mp4` | 思考 |
| `emphasis_01.mp4` | 强调 |
| `intro_01.mp4` | 开场 |
| `outro_01.mp4` | 结尾 |

每段 **8 ~ 20 秒**，一次录制后可长期复用。

#### 2.3.3 流程

```text
脚本
 ↓
TTS / 声音克隆
 ↓
语义分析
 ↓
选择真人动作模板
 ↓
MuseTalk 1.5
 ↓
嘴型同步
 ↓
FFmpeg 拼接
 ↓
B-roll
 ↓
字幕
 ↓
成片
```

全程可自动化，与 `douyin-1024` 契合度高。

#### 2.3.4 Provider 对比

| 方案 | 机制 | 特点 | 显存需求 |
|---|---|---|---|
| **MuseTalk 1.5** | 已有视频 → 嘴型同步 | 已针对清晰度、身份一致性、唇形改进，**支持中文**；官方设计本身即用已有视频做同步 | 未记录 |
| **LatentSync 1.5** | 已有视频 → 嘴型同步 | 最低推理显存 **8GB** | **8GB** |
| **LatentSync 1.6** | 同上，更高分辨率 | 脸部训练分辨率提升到 **512×512**，解决嘴唇/牙齿模糊 | **18GB** |

#### 2.3.5 本机适用性（重要）

本机 GPU 为 **RTX 5060 Ti 16GB**：

```text
LatentSync 1.5  需要 8GB   → ✅ 本地可跑
LatentSync 1.6  需要 18GB  → ❌ 超显存
```

**结论：本地现实选择是 LatentSync 1.5，不要直接折腾 1.6。**

#### 2.3.6 定位

| 阶段 | 方案 |
|---|---|
| 第一阶段（马上落地） | EMO / LivePortrait → 3:4 → 缩到 260~360px → 小窗主持人 |
| **第二阶段（最推荐）** | 真人母版 + 声音克隆/TTS → MuseTalk 1.5 → 自动 lip sync → 小窗 / 偶尔全屏 |
| 第三阶段（账号商业化后） | 购买商业数字人 API 做真全屏（HeyGen Avatar IV、D-ID Full-HD V3 Pro） |

**第二阶段最大的优势**：身体是真的，自然度通常比"单图 → 全身运动"高一个层级。

> 运行本路线需要本地 GPU 与模型权重，属于 Provider 接入，
> 须先过 Pre-Code Gate。路由与成本见 [PRESENTER-PROVIDER-ROUTING.md](PRESENTER-PROVIDER-ROUTING.md)。

---

### 2.4 小样本 vs 照片数字人：回本分析

**百度曦灵对比**：
| 类型 | 首次投入 | 单分钟成本 |
|---|---|---:|
| 照片数字人 | ¥20 | ¥4.5 |
| 小样本克隆 | ¥1000 | ¥3 |

回本需要：
```
(1000 - 20) / (4.5 - 3) = 653 分钟
= 约 6533 条 6秒 Hook
```

**结论**：小样本的价值不在"省钱"，而在**长期 IP 稳定性**。

---

## 三、架构设计建议

### 3.1 分层使用架构

```
                    Digital Human Layer
                             │
          ┌──────────────────┼─────────────────┐
          │                  │                 │
          ▼                  ▼                 ▼
    PhotoAvatarProvider  CloneAvatarProvider  H3Provider
          │                  │                 │
    低成本普通Hook     长期稳定个人IP      高级动态Hook
          │                  │                 │
   LivePortrait/Baidu  Baidu Xiling         Local H3
                      HeyGen Twin
                      D-ID V3
          │                  │                 │
          └──────────────────┼─────────────────┘
                             ▼
                    canonical_hook.mp4
                             │
                       Identity QC
                             │
                      OpenChatCut
                             │
                        Remotion
                             │
                     多平台发布
```

### 3.2 推荐 Provider 策略

#### RUN / 批量模式（默认）
```
Alibaba LivePortrait
目标：¥0.1~0.2 / 条 Hook
```

#### GROW / 重要内容
```
Local H3
场景：本地 GPU 空闲、需要动作、想要更生动
```

#### FALLBACK
```
LivePortrait 失败 → 百度曦灵
```

#### PREMIUM / 海外
```
Hedra / HeyGen
场景：海外平台特殊需求
```

### 3.3 小样本克隆策略

**现在阶段**：
1. 继续跑 Photo Avatar / Local H3
2. 流水线稳定后，测试百度曦灵通用口型（¥1000）
3. 海外先用 HeyGen Digital Twin 做一个真实 POC

**未来升级路径**：
```
普通视频 → Small Sample Avatar（稳定、批量）
重要视频 → H3（强动作、强镜头）
```

### 3.4 适配器目录结构建议

```
adapters/digital_human/
├── photo/
│   └── liveportrait.py          # 阿里百炼，默认廉价云 API
│
├── clone/
│   ├── baidu_xiling.py          # 国内主力小样本
│   ├── heygen_twin.py           # 海外主力小样本
│   └── did_instant.py           # 全 API 化备用
│
├── lip_sync/                    # 真人母版 + AI 改嘴（见 §2.3）
│   ├── musetalk.py              # 中文优先，需本地 GPU
│   └── latentsync_15.py         # 8GB 显存可跑；1.6 需 18GB，本机不可用
│
└── generative/
    └── local_h3.py              # 高级动态 Hook
```

**统一接口**：
```python
generate(
    avatar_id="xuanxuan_v1",
    audio_uri="hook.wav",
    aspect_ratio="9:16",
    transparent=True
)
```

**设计意义**：从照片数字人 → 小样本克隆 → 实时数字人 升级时，上层不需要重新设计。

---

## 四、100条/月 × 6秒 Hook 成本汇总

| Provider | 类型 | 首次投入 | 月生成成本 | 第一年总成本 |
|---|---:|---:|---:|---:|
| **本地 H3** | 照片生成 | - | ≈¥0 | ≈¥0 |
| **阿里 LivePortrait** | 照片数字人 | - | **¥12** | **≈¥144** |
| **阿里 EMO 1:1** | 照片数字人 | - | **¥48** | **≈¥576** |
| **百度曦灵照片** | 照片数字人 | ¥20 | **¥45** | **≈¥560** |
| **Hedra 540P** | 照片数字人 | - | ≈¥101 | ≈¥1212 |
| **HeyGen Avatar III** | 小样本克隆 | Twin创建 | ≈¥67 | **≈¥805+** |
| **百度曦灵小样本** | 小样本克隆 | **¥1000** | ¥30 | **≈¥1360** |
| **D-ID Launch** | 小样本克隆 | 订阅 | **¥235/月** | ≈¥2816 |
| **火山引擎** | 小样本克隆 | ¥2599 | ¥60 | ≈¥3319 |
| **腾讯云** | 小样本克隆 | ¥4500+ | 包内 | 至少¥4500 |

---

## 五、立即可执行的 A/B 测试设计

### 测试目标
验证假设：**LivePortrait 可能只花 H3/HeyGen 几十分之一的费用，就已经满足"6秒、脸不变形、嘴会动"的最低生产标准**

### 测试材料
```
同一张主播图
同一个 6 秒 hook.wav
同一个脚本文案
```

### 测试分组
| 组 | Provider | 样本数 |
|---|---|---:|
| 1 | Local H3 | 20次 |
| 2 | Alibaba LivePortrait | 20次 |
| 3 | 百度曦灵照片数字人 | 20次 |
| 4 | Hedra Character 3 540P | 20次 |

### 评估指标
1. `first_try_success_rate` — 首次成功率
2. `face_failure_rate` — 脸崩率
3. `lip_sync_score` — 嘴型同步分
4. `generation_latency` — 生成延迟
5. `cost_cny` — 实际成本
6. `manual_intervention_count` — 人工干预次数

### 最终指标
```
Cost Per Accepted Hook = 总花费 / 合格视频数量
```

---

## 六、关键决策点

### Q1: 现在要不要训练小样本数字人？

**答案**：**不要**。

原因：
1. 先把照片数字人 + H3 流水线跑稳定
2. 确认长期使用某个 IP 后再投入训练费
3. 小样本的价值是 IP 稳定性，不是省钱

### Q2: HeyGen vs 百度曦灵选哪个？

**答案**：
- 国内内容 → 百度曦灵
- 海外内容 → HeyGen Digital Twin
- 两者不互斥，可以同时保留

### Q3: 阿里云数字人要接吗？

**答案**：**不接**。

阿里云数字人服务：
- 2026-10-11 停止新购
- 2027-04-11 停止续订更新
- 2027-10-11 全面停止

产品生命周期风险直接否决。

### Q4: 阿里 EMO/Wan2.2 要接吗？

**答案**：
- EMO：可以测，但分辨率限制（512px）适合半屏场景
- Wan2.2：效果强但成本高（¥3~5.4/6秒），不是当前优先级

---

## 七、文档变更历史

| 日期 | 变更说明 |
|---|---|
| 2026-10-02 | 新增 §2.3 真人母版 + AI 改嘴路线（MuseTalk 1.5 / LatentSync，含 RTX 5060 Ti 16GB 适用性）；纠正 LivePortrait（快手/KlingAI）与 EMO（阿里）的模型归属 |
| 2026-10-01 | 初始版本，整合照片数字人与小样本克隆两条路线分析（当时） |

---

## 八、相关文档

| 文档 | 内容 |
|---|---|
| [PRESENTER-LAYER-SPEC.md](PRESENTER-LAYER-SPEC.md) | 数字人画面规范（小窗主持人层、版式、出现节奏） |
| [PRESENTER-PROVIDER-ROUTING.md](PRESENTER-PROVIDER-ROUTING.md) | 分档路由、月度成本模型、身份一致性规则 |
| [HeyGen-Pricing-API-Guide.md](HeyGen-Pricing-API-Guide.md) | HeyGen 计费与 API 接入 |
| `00-Governance/decisions/ADR-WS008-Presenter-Layer.md` | 定位决策记录（含 Open Questions） |
