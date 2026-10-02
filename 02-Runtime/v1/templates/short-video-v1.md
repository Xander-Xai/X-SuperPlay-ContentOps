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

## 素材要求（5 类）

每条视频开始前，对应项目目录下应准备好：

### 1. 项目 GitHub 页面截图

- 仓库主页
- README 关键段落
- Star / Fork 数字

### 2. README / 架构关键截图

- 核心架构图
- 关键命令 / 配置
- 重要文档段落

### 3. 真实运行过程屏幕录制

- 安装 / 部署过程
- 实际运行界面
- 真实操作步骤

### 4. 最终生成结果

- 成品 MP4 截图
- 生成日志
- 任何可验证的输出物

### 5. 你自己的优缺点结论

- 你亲测后的判断
- 优点清单
- 缺点清单
- 适用场景
- 不适用场景

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

每个视频工作目录：

```
projects/
└── <project-name>-video-001/
    ├── script.md          (Easel 输出)
    ├── storyboard.md      (Easel 输出)
    ├── assets/
    ├── output.mp4
    └── receipt.md         (发布后填写)
```

---

## 验收前自检（5 个全过才发）

- [ ] 视频前 3 秒有 Hook / Result
- [ ] 每个 Claim 都有证据素材可对应
- [ ] 没有 AI 虚构未实测能力
- [ ] 字幕简洁可读
- [ ] 自己愿意发到账号

---

## 发布后回填

发布完成后，在 `receipts/<date>-<project>-<platform>.md` 记录：

```yaml
date: 
project: 
platform: 
content_id:
url:
metrics:
  T+2H:
    views:
    likes:
    comments:
  T+24H:
    views:
    likes:
    comments:
  T+72H:
    views:
    likes:
    comments:
  T+7D:
    views:
    likes:
    comments:
qualified_signal:
  comments_quality:
  dm_count:
  follow_attribution:
rework_needed:
founder_minutes:
```

---

## 例：今天的第一条视频

```text
project: easel
description: "实测 ZJU-REAL/Easel 这个 AI 自媒体自动化项目"

materials:
  01-github-page: Easel 仓库主页截图
  02-readme-architecture: Discover / Plan / Produce / Publish 流程图
  03-screen-recording: Easel 完整安装过程
  04-results: 第一条生成的 MP4 截图
  05-conclusion: 我对 Easel 的优缺点判断

prompt:
  根据 sources/easel/ 中的真实素材，
  制作一条 60 秒中文竖屏技术实测短视频。
  ...
```