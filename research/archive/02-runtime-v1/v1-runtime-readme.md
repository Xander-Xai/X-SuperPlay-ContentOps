```yaml
status: superseded
superseded_by: docs/CURRENT-STATE.md, docs/ARCHITECTURE.md, docs/PRD.md
historical_context: Assumed Easel 0.1.1 and runtime/Easel/ path. Actual: v0.2.1 at .runtime/easel/.
notes: Directory structure described here (runtime/Easel/) does not match reality (.runtime/easel/).
```
# X-SuperPlay-ContentOps — V1 Runtime

> **当前唯一可生产的自媒体 V1 Runtime。**

## 范围

V1 目标：**先稳定做出质量过关的视频并发出去。**

不要在这个阶段做：自动选题 / 自动抓 Source / API Trigger / 批量生产 / 自动发布 / 数据回收 / Winner 学习。

## 角色

| 角色 | 负责 | 谁 |
|---|---|---|
| Brain | 决策、Review、QA | ChatGPT Plus |
| Factory | 内容生产 | **Easel 0.1.1（locked）** |
| Engineer | Workflow / Skill 开发 | OpenCode Go |

## 仓库治理

**5 个旧仓库全部停止开发**：

- `douyin-1024`
- `xhs-FA`
- `bilibili-matrix-skills`
- `shipinhao-matrix-skills`
- `gzh-Future-Intelligence`

V1 跑通后：

- 有独有价值的 Prompt / 模板 / 平台经验 → 抽到 V1
- 没有独有价值 → 直接删除仓库

## 目录结构

```
X-SuperPlay-ContentOps/
├── 00-Governance/
│   └── decisions/
│       └── ADR-WS008-ContentOps-Runtime.md
├── 01-Experiments/
│   └── EXP-WS008-EASEL-001/
│       ├── README.md
│       └── results/
│           └── scorecard.md
├── 02-Runtime/
│   └── v1/
│       ├── README.md (本文件)
│       ├── templates/
│       │   └── short-video-v1.md
│       ├── sources/
│       ├── projects/
│       ├── outputs/
│       └── receipts/
├── runtime/
│   └── Easel/  (Easel 0.1.1 锁定版本)
├── research/
└── ai-provider-selection.md
```

## V1 自媒体基础链路

```text
真实 Source Artifact
→ Easel video-script
→ 分镜
→ 真实素材整理
→ 配音
→ Easel video-production
→ Quality Gate
→ 生成最终 MP4
→ 人工检查
→ 人工发布
→ 记录数据
```

### 核心原则

**不要**：

```text
主题 → AI 随机找素材 → 拼一个"能看"的视频
```

**要**：

```text
真实实测 → 真实截图/录屏/结果 → AI 负责包装和剪辑
```

## V1 视频质量保证

### 素材结构（45–90 秒技术短视频）

| 占比 | 类型 |
|---|---|
| 50–70% | 真实录屏 / Demo / 网页 / GitHub / 软件操作 |
| 20–40% | 真实截图 / 架构图 / 对比表 / 关键文字卡片 |
| 0–20% | AI 生图 / AI 视频 / 装饰 B-roll |

### 视频结构示例（Easel 测评 60s）

```text
0–3s   Hook："我找了很久的 AI 自媒体自动化，
         终于找到一个不是 PPT 的项目。"
3–8s   直接展示最终效果
8–20s  展示 Easel 工作台
20–35s 真实运行：选题 → 脚本 → 视频
35–48s 展示生成结果
48–58s 说清楚缺点：自动发布、小红书风控、当前成熟度
58–65s 结论："我会把它接进自己的 OPC 工作流继续实测。"
```

## V1 仅调用的 Easel Skill

```text
video-script
        ↓
storyboard / 内容分镜
        ↓
TTS / voice
        ↓
video-production
        ↓
video-reframe
        ↓
video-intro-outro
        ↓
quality-gate
        ↓
risk-scanner
        ↓
publish-checklist
```

### 暂时不要用

- AI 短剧
- 复杂数字人
- 大量文生视频
- 全自动跨平台发布
- 热点自动追踪
- ROI Agent
- 评论 Agent

## 发布策略

**V1：生产自动化 ✅，发布自动化 ❌**

```text
Easel → final.mp4
        ↓
    你看一遍
        ↓
抖音手动发
小红书手动发
B站手动发
视频号手动发
```

原因：

1. 当前瓶颈是"视频做不出来 / 质量不稳定"，不是"手动发布太慢"。
2. Easel 官方也明确提醒，小红书自动发布可能触发验证、限流或风控。
3. 等连续 3–5 条能稳定产生合格 MP4 后，再接 `skill-cross-platform-publish`。

## 验收标准（5 个全部满足 → V1 PASS）

- [ ] ① 一个 Source 能生成成片
- [ ] ② 连续 3 条不用大量人工返工
- [ ] ③ 视频不是随机 B-roll 拼接
- [ ] ④ 每个重要 Claim 都能看到真实证据
- [ ] ⑤ 最终 MP4 你愿意直接发到自己的账号

V1 PASS 后才进入：

```text
自动选题 → 自动抓 Source → API Trigger →
批量生产 → 自动发布 → 数据回收 → Winner 学习
```

## 第一条视频执行步骤

1. 从近期已完成真实工作中选 1 个项目
2. 准备 5 类素材（见 `templates/short-video-v1.md`）
3. 在 `sources/<project>/` 建立项目目录，存放素材
4. 在 `projects/<project>-video-001/` 建立视频工作目录
5. 用 `templates/short-video-v1.md` 中的 Master Workflow Prompt 提交给 Easel
6. 检查生成的 final.mp4，记录到 `outputs/`
7. 人工审核 → 人工发布
8. 在 `receipts/` 记录发布数据

## 今天的动作（P0）

```text
建 X-SuperPlay-ContentOps
+ 安装并锁定 Easel 0.1.1
+ 选一个你已经实测过的 GitHub 项目
+ 用真实录屏/截图跑出第一条 60 秒 MP4
```

**不要**：

- 修旧仓库
- 接发布 API
- 研究更多视频模型
- 设计架构