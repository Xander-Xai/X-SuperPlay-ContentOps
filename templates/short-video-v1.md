# Short Video V1 — Master Workflow Prompt

> V1 阶段唯一标准化的视频制作 Prompt。所有视频都用这个 prompt 模板启动。

## 适用场景

- 45–90 秒技术短视频
- 真实实测类内容
- AI 工具 / GitHub 项目 / Coding / RAG / Agent 实战类

## 不适用场景

- AI 短剧
- 复杂数字人
- 大量文生视频
- 纯热点 / 流量型内容

---

## Master Workflow Prompt

```text
根据 sources/<project-name>/ 中的真实素材，
制作一条 60 秒中文竖屏技术实测短视频。

要求：
- Result-first
- 前 3 秒必须展示核心结论或结果
- 不允许虚构任何未实测能力
- 优先使用真实录屏、截图和结果素材
- AI 生成视觉只能辅助，不能替代证据
- 每 2–5 秒有视觉变化
- 字幕简洁
- 重点突出实测结果、适用场景、缺点
- 输出 1080×1920 MP4
- 完成后执行质量检查
```

---

## 视频结构模板

```text
0–3s    HOOK / 最终结果
3–10s   问题是什么
10–30s  真实证据 / 实际操作
30–45s  关键发现
45–55s  限制 / 缺点
55–65s  结论 / 下一步
```

不是每条必须严格 65 秒，但默认遵循：

```text
Result-first
Evidence-first
```

---

## 素材要求（5 类）

每条视频开始前，对应项目目录下应准备好：

### 1. 项目 GitHub 页面截图
### 2. README / 架构关键截图
### 3. 真实运行过程屏幕录制
### 4. 最终生成结果
### 5. 你自己的优缺点结论

---

## 素材存放规范

```
sources/
└── <project-name>/
    ├── 01-github-page/
    ├── 02-readme-architecture/
    ├── 03-screen-recording/
    ├── 04-results/
    └── 05-conclusion.md
```

---

## 真实性边界

### 允许

- "官方实现了 X"（引用 README / 源码）
- "v0.2.1 release 显示 Y"
- "Skill 文档说明 Z"
- "源码里可以看到 W"
- "本机 `doctor` 输出显示 A"

### 禁止

- "我本地实测跑通 X"（除非本任务真的跑过）
- "经测试 Y 稳定"（没有数据支撑）
- 虚构客户案例 / 数据 / 用户数