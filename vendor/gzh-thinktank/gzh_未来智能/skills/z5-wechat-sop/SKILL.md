---
name: z5-wechat-sop
display_name: "Z5 公众号生产 SOP"
display_name_en: "Z5 WeChat Production SOP"
description: "微信公众号端到端 SOP：采集→编辑→审核→发布 四步标准化流程，含 3 层审核（数据校验/来源核实/合规检查）+ AI 配图 + Playbook 自我学习。本 Skill 是对开源项目 Z5-WeChat-SOP 的包装入口；脚本需从 GitHub 克隆后使用。适合需要批量稳定产出、想要标准化 SOP 的团队或单人。"
description_zh: "Z5 公众号 4 步 SOP：热点采集 → AI 写作 → 3 层审核 → 草稿发布，附 AI 配图 + Playbook 学习。封装自开源 Z5-WeChat-SOP。"
description_en: "End-to-end WeChat OA SOP: collect→edit→audit→publish with 3-layer audit, AI image gen, and Playbook learning. Wraps Z5-WeChat-SOP."
category: content-creation
version: 1.0.0
author: WeChat Matrix Team
source: https://github.com/Z5Research/Z5-WeChat-SOP
license: MIT
visibility: "public"
---

# Z5-WeChat-SOP · 公众号 4 步生产 SOP

> **重要**：本 Skill 是对 GitHub 开源项目 `Z5-WeChat-SOP`（MIT 协议）的**本地包装入口**。脚本本体不直接放在这里，使用前需先克隆到本地。

---

## 📋 补的缺口（与现有 Skill 互补）

| 缺口 | 解决方式 |
|---|---|
| 团队协作（4 角色代理） | 采集代理 → 编辑代理 → 审核代理 → 发布代理 模拟团队分工 |
| 校对/合规（强化） | **3 层审核**：数据校验 / 来源核实 / 合规检查（S/A/B/C 评级） |
| 文中配图（强化） | 统一路由 Agnes Image 2.1 Flash 生成，保留原有 3 轮提示词优化 |
| 单兵作战 SOP | 4 步标准化流程 + Playbook 持续学习 |

> 与已有 Skill 的关系：**补强型**。不替代 `gzh-article-writing`/`khazix-writer` 的写作品质，而是把它们作为「编辑代理」的可选后端；不替代 `gzh-draft-publisher` 的发布能力，而是作为「发布代理」前的标准化前道。

---

## 🚀 安装（一次性）

### 前置依赖
- Python 3.10+
- 微信公众号 AppID + AppSecret
- Agnes Image 2.1 Flash 的 `AGNES_API_KEY`（配图）

### 拉源码
```bash
git clone https://github.com/Z5Research/Z5-WeChat-SOP.git ~/.wechat-matrix/skills/z5-wechat-sop-src
cd ~/.wechat-matrix/skills/z5-wechat-sop-src
pip install -r requirements.txt
```

### 配置环境变量
```bash
export WECHAT_APP_ID=your_app_id
export WECHAT_APP_SECRET=your_app_secret
export VOLC_ACCESS_KEY=your_volc_access_key   # 配图（首选）
export VOLC_SECRET_KEY=your_volc_secret_key
# 备选：export BAILIAN_API_KEY=your_bailian_key
```

### 配置公众号风格
新建 `clients/你的公众号名/style.yaml`：
```yaml
name: "你的公众号名"
industry: "行业"
topics: ["内容方向 1", "内容方向 2"]
tone: "写作风格（如：卡兹克风/刘润风/轻松幽默）"
cover_style: "封面风格描述"
author: WeChat Matrix Team
theme: "professional-clean"
```

---

## 🔄 4 步 SOP 工作流

### 全自动模式
```bash
python3 scripts/main.py --client 你的公众号名 --mode auto
```

### 分步执行（推荐先试这个）

```bash
# Step 1: 热点采集（30 分钟内可上素材）
python3 scripts/01-collect-hotspots.py --limit 30

# Step 2: 撰写文章
python3 scripts/03-write-article.py --client 你的公众号名 --topic "选题"

# Step 3: 审核（3 层）
python3 scripts/06-audit-article.py --client 你的公众号名

# Step 4: 草稿发布
python3 scripts/07-publish-draft.py --client 你的公众号名
```

### 辅助脚本
- `02-write-article.py` — 调内部写作后端（可接 khazix-writer 风格）
- `05-seo-optimize.py` — SEO 优化
- `06-generate-images.py` — 文中配图（委托主工作流的 Agnes 适配器）
- `07-publish-draft.py` — 推送草稿到公众号
- `08-archive-data.py` — 数据归档
- `09-fetch-stats.py` — 拉自家数据
- `09-learn-edits.py` — 人工修改学习（更新 Playbook）

---

## 🔍 3 层审核机制（核心亮点）

| 审核维度 | 评级 | 说明 |
|---|---|---|
| **数据校验** | S/A/B/C | 核心数据 S/A 才发布 |
| **来源核实** | S/A/B/C | 官方 > 权威 > 主流 > 一般 |
| **合规检查** | 通过/不通过 | 标题合规、客观性、逻辑、法规 |

**不通过 → 自动回退到 Step 2 重写**（最多 6 轮迭代），确保输出 S 级。

---

## 💬 自然语言触发词

| 用户说 | 触发 |
|---|---|
| "按 SOP 出一篇 AI Agent 的文章" | 全流程 auto |
| "先采点今天的热点" | Step 1 |
| "把选题'AI Agent 创业'写成文章" | Step 2 |
| "审一下这篇稿子" | Step 3 |
| "推到草稿箱" | Step 4 |
| "给这篇加配图" | Step 6 |
| "看看学习到的编辑偏好" | Playbook |

---

## ⚠️ 注意事项

1. **必须服务号/认证订阅号** — 草稿 API 需认证
2. **Agnes 配图** — 使用仓库外环境中的 `AGNES_API_KEY`
3. **Playbook 学习** — 首次使用为空，跑几轮后会越来越贴你风格
4. **审核不通过兜底** — 6 轮迭代仍不通过会进入人工介入队列

---

## 🔗 资源

- 源项目：https://github.com/Z5Research/Z5-WeChat-SOP
- SPEC 详细规范：https://github.com/Z5Research/Z5-WeChat-SOP/blob/main/docs/SPEC.md
- Agnes Image 2.1 Flash 配图：请使用主工作流的 `skills/gzh-visual-assets/scripts/image_create.py`
