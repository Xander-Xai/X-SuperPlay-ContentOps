---
name: wemp-operator
display_name: "公众号数据复盘+互动管理"
display_name_en: "WeChat OA Analytics & Interaction"
description: "微信公众号自动化运营 — 内容采集 / 数据分析 / 互动管理。触发词：采集热点、公众号日报、公众号周报、检查评论、回复评论、精选评论、公众号数据复盘、涨粉分析。本 Skill 是对开源项目 wemp-operator 的包装入口；实际脚本需从 GitHub 克隆后使用。"
description_zh: "微信公众号数据复盘（日报/周报/涨粉/阅读）+ 评论管理（检查/回复/精选），封装自开源项目 wemp-operator。"
description_en: "WeChat Official Account automation — analytics, comments, and content collection. Wraps open-source wemp-operator."
category: content-creation
version: 1.0.0
author: WeChat Matrix Team
source: https://github.com/gaozejie/wemp-operator
license: MIT
visibility: "public"
---

# wemp-operator · 公众号数据复盘 + 互动管理

> **重要**：本 Skill 是对 GitHub 开源项目 `wemp-operator`（作者 IanShaw027，地址 https://github.com/gaozejie/wemp-operator）的**本地包装入口**。脚本本体不直接放在这里，使用前需先克隆到本地。

---

## 📋 补的缺口

| 缺口 | 解决方式 |
|---|---|
| ③ 数据复盘 | 日报 / 周报 / 涨粉 / 阅读分析 |
| ④ 评论 / 读者运营 | 检查评论 / 智能回复 / 批量精选 |

**额外能力**：70 个微信公众号 API、20+ 数据源采集、评论智能回复建议。

---

## 🚀 安装（一次性）

### 前置依赖
- Node.js ≥ 18
- 已认证的微信公众号（服务号 / 订阅号）
- 公众号 AppID + AppSecret

### 拉源码
```bash
# 推荐装到 本地技能运行时 的 skills 目录旁边
git clone https://github.com/gaozejie/wemp-operator.git ~/.wechat-matrix/skills/wemp-operator-src
cd ~/.wechat-matrix/skills/wemp-operator-src
node scripts/setup.mjs   # 自动检查依赖并提示配置
```

### 配置凭证
在 `~/.openclaw/openclaw.json`（或环境变量）里填：
```json
{
  "env": {
    "WECHAT_APP_ID": "wx你的AppID",
    "WECHAT_APP_SECRET": "你的AppSecret",
    "WECHAT_IP_WHITELIST": "你的服务器公网IP"
  }
}
```

> ⚠️ 公众号后台「开发 → 基本配置 → IP 白名单」必须加上你跑脚本的机器公网 IP。

---

## 🔄 工作流（3 大模块）

### 1️⃣ 数据复盘（补缺口 ③）

| 用途 | 命令 | 触发词 |
|---|---|---|
| 公众号日报 | `node scripts/analytics/daily-report.mjs` | "公众号日报"、"昨天的数据"、"日数据" |
| 公众号周报 | `node scripts/analytics/weekly-report.mjs` | "公众号周报"、"本周数据" |
| 指定日期日报 | `node scripts/analytics/daily-report.mjs --date 2026-07-30` | "7月30日数据" |

日报输出：用户数据（关注/取关/净增）、阅读数据（总阅读/人均）、热门文章 TOP 3、互动数据（留言/分享）、AI 洞察建议。

### 2️⃣ 评论 / 互动管理（补缺口 ④）

| 用途 | 命令 | 触发词 |
|---|---|---|
| 检查新评论 | `node scripts/interact/check-comments.mjs` | "检查评论"、"有新留言吗" |
| 列出全部评论 | `node scripts/interact/check-comments.mjs --list` | "列出所有评论" |
| 回复评论 | `node scripts/interact/reply.mjs --comment-id <id> --content "回复内容"` | "回复评论"、"回复这条" |
| 精选 / 取消精选 | `node scripts/interact/manage.mjs` | "精选这条"、"取消精选" |

### 3️⃣ 内容采集（拓展能力）

```bash
node scripts/content/smart-collect.mjs \
  --query "AI Agent 行业" \
  --keywords "Agent,智能体,LLM" \
  --sources "tech,china" \
  --deep
```

数据源分类：
- `tech` — hackernews / github / v2ex / 36kr / producthunt / 少数派
- `china` — weibo / zhihu / baidu / 抖音 / 头条 / 澎湃
- `finance` — 36kr / 华尔街见闻 / 财联社
- `all` — 全部

---

## 💬 自然语言触发词速查

| 用户说 | 触发 |
|---|---|
| "帮我采集今天的 AI 热点" | 内容采集 |
| "公众号日报" / "看看昨天数据" | 日报 |
| "本周公众号数据" | 周报 |
| "涨了多少粉" | 日报中提取 |
| "检查公众号新评论" | 评论检查 |
| "回复这条评论：感谢支持" | 评论回复 |
| "把这条评论精选" | 精选 |
| "生成文章" / "发布草稿" | 草稿管理 |

---

## ⚠️ 注意事项

1. **必须用认证过的服务号/订阅号** — 个人订阅号无 API 权限
2. **IP 白名单** — 服务器公网 IP 必须加到公众号后台
3. **调用频率** — 公众号 API 有 QPS 限制，脚本已内置节流
4. **数据缓存** — 日报默认读昨日数据，公众号 API 通常 T+1 更新
5. **数据安全** — 留言/用户信息属敏感数据，脚本处理时建议脱敏

---

## 🔗 资源

- 源项目：https://github.com/gaozejie/wemp-operator
- 微信公众平台 API 文档：https://developers.weixin.qq.com/doc/offiaccount/
- IP 白名单配置入口：mp.weixin.qq.com → 开发 → 基本配置
