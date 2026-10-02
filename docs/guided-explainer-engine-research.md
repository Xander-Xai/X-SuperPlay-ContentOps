# Guided Explainer Engine — Architecture Research Report

> **研究日期**: 2026-10-02
> **研究目的**: 收敛数字人视频生产技术路线，为 `douyin-1024` + Easel 确定下一阶段核心建设方向

---

## 核心结论

> **你真正应该立项的不是"更好的 CS Board"，而是一个 Guided Explainer Engine：旁白是主时钟，Agent 生成结构化导演指令，不直接生成最终视频；不同 Renderer 负责不同类型的讲解，Remotion 只负责最终总时间线和合成。**

**你已有的生产门禁和 Baseline/Enhanced/Strict 体系不需要推倒重来。** 真正的核心资产是一个**与 Renderer 无关的中间表示**：Semantic Beat IR。

---

## 一、数字人分辨率实战指南

### 数字人分辨率档位对照（9:16 竖屏）

| 档位 | 竖屏分辨率 | 像素量 | 数字人实际观感 |
|---|---|---:|---|
| **480P** | 480×854 | 约41万 | 明显模糊，脸部细节少 |
| **540P** | 540×960 | 约52万 | 比480P好一点，仍偏糊 |
| **720P** | 720×1280 | 约92万 | 手机小窗基本够用 |
| **1080P** | 1080×1920 | 约207万 | 自媒体主流，清晰度较好 |
| **2K / 1440P** | 1440×2560 | 约369万 | 更清晰，但生成成本明显增加 |
| **4K** | 2160×3840 | 约829万 | 非常清晰，但对数字人通常没必要 |

### 重要区分

- **480P/540P**: 测试和超小窗（数字人只占画面 10%~20%）
- **720P**: 性价比最高的小窗数字人（右下角讲解员、左下角主播）
- **1080P**: 全屏数字人的实用标准
- **2K**: 多数情况下收益有限，AI 瑕疵会暴露
- **4K**: 普通自媒体数字人基本没必要

### 最关键的一点

> **最终视频1080P ≠ 数字人必须1080P。**
> 可以是 **720P数字人 + 1080P素材 + 1080P最终输出。**

数字人效果不能简单理解成 `4K > 2K > 1080P > 720P`。真实情况是：

> **模型质量 × 驱动效果 × 人物素材 × 分辨率 × 编码质量**

---

## 二、本轮最重要的新发现

| 新项目 | 最值得吸收的东西 | 对你用途 |
|---|---|---|
| **Minitour/clipwright** | Remotion 主时间线 + Manim 子镜头 + 音频驱动 + 人工批准 | **整体架构蓝本** |
| **vibe-motion/remotion-code-motion-explainer** | 连续空间叙事 + 63 镜头/65 composition + choreography IR | **核心 Remotion Skill 候选** |
| **Excalimate** | Excalidraw + 动画时间线 + 相机 + MCP + MP4 | **白板/架构图 Renderer 首选** |
| **PaulLemaistre/explainer-video** | 逐词时间戳 → 动画 Beat 精确落词 | **你的 Timing 层** |
| **Archscribe** | 技术架构图/流程图 + JSON Spec + 动画 + Agent 验证 | **技术内容 Renderer** |
| **gqy20/vid-agent** | Manim/Remotion 双引擎 + production gate | **工程生产参考** |
| **Kineto** | JSON → 校验 → deterministic render | **你的 IR/Compiler 设计参考** |
| **manim-mcp** | 3Blue1Brown RAG + ScenePlanner + CodeReviewer | **Manim 能力增强** |
| **mcp_excalidraw** | Agent 可画、看、截图、修正 Excalidraw | 辅助 authoring |
| **MotionSpec** | LLM 只写受约束 Spec，编译器确定执行 | **架构思想，不直接接视频** |

---

## 三、第一优先研究：Minitour/clipwright

这个项目和你的需求高度同构。它不是 `Prompt → AI → 视频`，而是：

```
需求
  ↓
Storyboard
  ↓
人工批准
  ↓
Scene-by-Scene 实现
  ↓
预览
  ↓
最终视频
```

**关键设计原则：**

1. **Remotion 永远是最终 composition engine。**
2. **ManimGL 只用于数学/算法/几何/LaTeX，渲染出的 MP4 作为素材嵌进 Remotion。**
3. **Audio-driven timing**：不是先做动画再让配音硬塞，而是：
   ```
   生成旁白 Segment
        ↓
   实际测量音频长度
        ↓
   决定视觉 Segment Duration
        ↓
   动画适配真实音频
   ```

> **不要 Fork Clipwright 重做项目。应该吸收它的 engine-selection 和 production contract。你的 `douyin-1024` 已经比它更完整，没有必要换底座。**

---

## 四、最值得直接试的 Skill：vibe-motion/remotion-code-motion-explainer

**这是本轮最意外的发现。** 公开版已有：

- **63 个可检索镜头条目**
- **65 个 Remotion Compositions**
- 横屏、竖屏、方形；AI Workflow、产品 UI、数据、代码、架构、时间线、A-roll/B-roll、画中画、证据桥接

### 核心思想：持续对象 Persistent Objects

它不是每句话清屏，而是**对象一直存在，只改变状态**：

```
                 第一个 Beat
用户 → Query
               │

                 第二个 Beat
用户 → Query → Retriever
               │

                 第三个 Beat
用户 → Query → Retriever → Documents
               │

                 第四个 Beat
用户 → Query → Retriever → Documents
                           ↓
                          LLM
```

每个 Beat 必须先拆解成：

```json
{
  "input_state": "...",
  "dominant_verb": "...",
  "visible_transformation": "...",
  "output_state": "...",
  "viewer_focus": "...",
  "handoff": "..."
}
```

并落盘成 `src/data/choreography-plan.json`。

**截至检查：MIT，~32 stars / 9 forks。建议直接做 POC。**

---

## 五、白板/架构解释首选：Excalimate

**不是通用"AI 视频平台"，而是：**

```
Excalidraw Scene
       ↓
Animation Sequence
       ↓
Keyframes
       ↓
Camera
       ↓
MP4 / WebM / GIF / SVG / Lottie
```

**关键优势：**

- 原生 **MCP Server**，35 个 MCP tools
- 实时 Live Preview、Auto Animate、Smart Transition
- **Agent → Structured Actions → Deterministic Animation Core → Video**，不是每次直接魔改动画代码

```
project-schema
animation-core
player-runtime
export-runtime
```

**与 mcp_excalidraw（AI 绘图工作台）的区别：**

| 项目 | 定位 |
|---|---|
| mcp_excalidraw | Agent 绘图工作台，文章→架构图→截图验证 |
| Excalimate | AI 动态图表/白板动画引擎 |

> **Excalimate 优先级更高。** 截至检查：MIT，~76 stars / 13 forks，2026-09 仍有活跃更新。

---

## 六、旁白同步：PaulLemaistre/explainer-video

**解决的问题非常正确：动画不能根据"估计一句话 4 秒"来卡点。**

```
TTS
  ↓
word_times.json
  ↓
Beat Anchor
  ↓
Animation
```

例如旁白"这里真正起作用的是 Retriever"，时间戳：

```
这里       12.10
真正       12.42
起作用     12.81
的是       13.22
Retriever 13.51
```

动画在 `13.51s` 精确触发。

还专门处理了 Manim 的 frame quantization drift（使用真实 renderer clock，而不是把一堆 `run_time` 简单相加）。MIT。

---

## 七、Archscribe：技术自媒体专用

专门做**系统架构、Agent Workflow、CI/CD、流程、分类、数据链路、技术解释**。

- 三种布局：`panorama / swimlane / graph`
- 六套 animation preset：`flow / draw / relay / trace / chapter / failure-recovery`
- 输入是 JSON spec，输出 `.excalidraw / .png / .gif / .mp4 / .svg / .html`
- `--validate-only / --check / --verify`，Agent 可自动修复配置

**非常适合：**

```
RAG Pipeline 是什么
Agent 为什么需要状态机
Claude Code Skill 怎么运行
MCP 是什么
Easel 如何编排 Agent
LangGraph Workflow
```

> **Archscribe 是 Scene Renderer，不要让它控制整条视频。** ~353 stars / 23 forks，MIT。

---

## 八、Manim 这条线：vid-agent + manim-mcp

### vid-agent（工程生产参考）

定位接近你：技术课程 + 技术视频。已实现：

```
candidate → audit → approval → current
→ release candidate → release audit → release approval → published
```

approval 绑定 Candidate SHA，输入改变就让旧 verdict 失效。

> **这进一步证明：你的生产治理架构方向本身没问题，缺的是 Visual Explanation Engine。**

### manim-mcp（RAG 增强）

索引：
- 3140 个 3Blue1Brown Scene
- 1652 个 ManimGL API Signature
- 101 个 Animation Pattern
- 470 个文档
- Error/Fix Pattern

```
ConceptAnalyzer
      ↓
ScenePlanner
      ↓
CodeGenerator
      ↓
CodeReviewer
```

失败以后还会存 `error → fix` 继续进入 RAG。

---

## 九、Kineto：JSON IR + Checker

**核心思想：Video as a build artifact。**

```
JSON Document
       ↓
Validator
       ↓
Compiler
       ↓
Renderer
       ↓
MP4
```

有 `check_document`，不用真正渲染视频就检查：
- 文字超出画布
- 文字与背景对比不足
- Element 动出屏幕
- Scene 太短来不及阅读

> **Agent 操作的是 JSON，不是程序。** 这对 Easel 的意义非常大。

---

## 十、核心资产：Guided Explainer IR

**真正的核心资产不是 CS Board / Xiaohei / Manim / Remotion / Excalidraw，这些全是 Renderer。**

真正的核心是：

```
Script
  ↓
Audio Alignment
  ↓
Semantic Beat IR         ← 你的核心 IP
  ↓
Visual Compiler
  ↓
Renderer
```

### IR 进化方向

**不要只写：**

```json
{
  "visual_mode": "xiaohei"
}
```

**应该是：**

```json
{
  "beat_id": "b07",

  "timing": {
    "start_ms": 12420,
    "end_ms": 18350,
    "anchor_ms": 16680
  },

  "narration": {
    "text": "RAG真正解决的问题，是模型拿不到你的私有知识。",
    "anchor_text": "私有知识"
  },

  "semantic": {
    "purpose": "explain_mechanism",
    "input_state": ["llm_isolated", "private_knowledge"],
    "action": "connect",
    "output_state": ["retrieval_path_available"],
    "viewer_focus": "knowledge_gap"
  },

  "visual": {
    "persistent_objects": ["llm", "knowledge_base"],
    "new_objects": ["retriever"],
    "transformation": "bridge",
    "camera": "push_to_gap"
  },

  "renderer": {
    "preferred": "remotion_code_motion",
    "fallback": "excalimate"
  }
}
```

> **这是在描述观众应该看到什么变化，而不是"给我生成一张漂亮图片"。**

---

## 十一、Renderer Router 收敛到 5 个核心引擎

| Renderer | 用途 |
|---|---|
| **Evidence** | GitHub、网站、论文、新闻、真实 UI |
| **Remotion Code Motion** | 默认主力：UI、Agent、数据流、产品、技术逻辑 |
| **Excalimate / Archscribe** | 白板、架构、流程、手绘技术图 |
| **Manim** | 算法、数学、抽象机制、几何关系（不默认调用） |
| **Generated Media** | AI Image / AI Video / 数字人 |

### 对应内容 Router 示例

**"Claude Code Skill 怎么运行？"**
```
真实仓库目录    → Evidence (screenshots)
Skill → Agent → Tool  → Remotion Code Motion
上下文加载关系  → Excalimate
复杂 Agent Loop → Remotion / Manim
抽象比喻         → Xiaohei style
```

**"RAG 为什么会幻觉？"**
```
LLM + 问题 + 知识断层  → Remotion continuous space
"Retriever 像一座桥"   → Xiaohei Metaphor
Dense/BM25/Rerank 流程 → Excalimate / Archscribe
向量空间 / cosine      → Manim
数字人 PIP 总结        → Generated Media
```

---

## 十二、接入现有 douyin-1024 的方式

**不需要新增第 14 个 stage。** Guided Explainer 设计成 `visual_plan` 的一种机器可读子合同，对现有架构侵入最小。

```
03_audio/audio-handoff.json
             │
             ├── audio
             ├── word timing
             └── semantic timing
                     ↓
04_visual/visual-plan.json
                     │
                     └── guided_explainer
                           ├── beats[]
                           ├── persistent_objects[]
                           ├── transformations[]
                           └── camera_plan[]
                     ↓
04_visual/visual-route.json
                     │
       ┌─────────────┼──────────────┐
       ▼             ▼              ▼
   evidence       remotion       excalimate
  screenshots                     archscribe
                       │
                       └──── manim
```

### 架构全景

```
                    Narration
                        │
                        ▼
                 Word Alignment
                        │
                        ▼
                Semantic Beat IR
                        │
                        ▼
                 Visual Compiler
                        │
        ┌───────────────┼────────────────┐
        │               │                │
        ▼               ▼                ▼
    Evidence         Code Motion       Diagram
 screenshots         Remotion          Excalimate
 browser                 │             Archscribe
        │                │                │
        │                ├──────┐         │
        │                │      ▼         │
        │                │    Manim       │
        │                │                │
        └────────────────┴────────────────┘
                         │
                         ▼
                  Scene Artifacts
                         │
                         ▼
                Remotion Master
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
          Digital Human         Captions/BGM
              PIP
                 \               /
                  ▼             ▼
                   Final 1080×1920
```

---

## 十三、落地优先级

### P0：马上做 POC

**① vibe-motion/remotion-code-motion-explainer**
- 验证：技术类 60 秒 9:16 视频能否达到"带着观众讲"

**② Excalimate**
- 验证：架构图能否自动生成 → animation sequence → camera → MP4

**③ 旁白 Timing**
- 吸收 `PaulLemaistre/explainer-video` 的 word-timing → semantic beat 机制

三项组合：`旁白 → Beat → Remotion/Excalimate → Final`，已可做一支完整视频。

### P1：再加入

**④ Archscribe** — 专门服务 AI / Agent / 软件架构技术图

**⑤ Manim** — 专门服务数学/算法/原理动画，**不默认每支视频都调用**

### P2：吸收架构，不直接作为依赖

```
Kineto      → JSON IR + checker
MotionSpec  → constrained motion catalog
manim-mcp   → pattern RAG + self-repair
vid-agent   → gate / candidate / audit
clipwright  → engine selection + audio-first
```

---

## 十四、最终建议

> **`douyin-1024` 继续当 Production OS；Easel 当 Agent Orchestrator；新增 Guided Explainer IR 当导演协议；Remotion Code Motion 当默认讲解引擎；Excalimate/Archscribe 当图解引擎；Manim 当专业原理引擎；真实截图/录屏承担事实证据；数字人只作为小窗 Host。**

**最应该立即拉下来实验的顺序：**
1. `vibe-motion/remotion-code-motion-explainer`
2. `Excalimate`
3. `Archscribe`
4. `PaulLemaistre/explainer-video` 的逐词 Timing 机制

**你真正应该自己开发的只有中间这一层（你的核心 IP）：**

```
Narration
    ↓
Semantic Beat
    ↓
Guided Explainer IR
    ↓
Renderer Selection
    ↓
QC Contract
```

这比"CS Board + Xiaohei 再拼几个 Skill"更接近一套真正可以规模化运行的 **AI 技术自媒体导演系统**。

---

## 十五、参考项目索引

| 项目 | URL | License | Stars | 用途 |
|---|---|---|---|---|
| Minitour/clipwright | github.com/Minitour/clipwright | MIT | — | 整体架构蓝本 |
| vibe-motion/remotion-code-motion-explainer | github.com/vibe-motion/remotion-code-motion-explainer | MIT | ~32 | 核心 Remotion Skill |
| Excalimate | github.com/excalimate/excalimate | MIT | ~76 | 白板/架构图 Renderer |
| PaulLemaistre/explainer-video | github.com/PaulLemaistre/explainer-video | MIT | — | Timing 层 |
| lazypay/Archscribe | github.com/lazypay/Archscribe | MIT | ~353 | 技术内容 Renderer |
| gqy20/vid-agent | github.com/gqy20/vid-agent | — | — | 工程生产参考 |
| Kineto | (JSON IR 项目) | — | — | IR/Compiler 设计参考 |
| manim-mcp | github.com/manim-mcp | MIT | — | Manim 能力增强 |
| yctimlin/mcp_excalidraw | github.com/yctimlin/mcp_excalidraw | MIT | — | 辅助 authoring |
| MotionSpec | (相关项目) | — | — | 架构思想参考 |

---

*本文件是 research findings，已写入 memory 系统。*
