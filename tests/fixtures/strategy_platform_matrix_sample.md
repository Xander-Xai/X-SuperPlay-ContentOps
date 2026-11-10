# 自媒体平台运行矩阵（对账测试样例）

> 这是 `scripts/check_platform_status_sync.py` 的测试 fixture，结构与
> Strategy 仓 `03-Execution/Platform-Operating-Matrix.md` 的主表同构。
> 修改真实矩阵后，同步更新此文件与 `strategy_platform_status.json`。

| 平台 | 系统角色 | 原生内容入口 | 主要观察信号 | 典型 CTA | 状态 | 执行事实源 |
|---|---|---|---|---|---|---|
| 抖音 | Discovery / Hook Lab | 结果、冲突、Demo、挑战 | 停留/观看、分享、主页访问、具体评论 | 提交问题/职业/场景 | Active | [`douyin-1024`](https://github.com/Xander-Xai/douyin-1024) |
| 小红书 | Search / Save | 问题词、封面、清单、配置、案例 | 搜索、收藏、主页访问、私信、资料请求 | 求配置/代码/问题 | Active | [`xhs-FA`](https://github.com/Xander-Xai/xhs-FA) |
| B站 | Trust / Deep Proof | 完整实验、教程、失败复盘、Coding | 点击、留存、回访、收藏、技术提问 | GitHub/复现/问题 | Active | [`bilibili-matrix-skills`](https://github.com/Xander-Xai/bilibili-matrix-skills) |
| 视频号 | WeChat Relationship | 职场、效率、行业、商业价值 | 分享、关系链反馈、主页/公众号动作 | 公众号/微信生态承接 | Derived | [`shipinhao-matrix-skills`](https://github.com/Xander-Xai/shipinhao-matrix-skills) |
| 公众号 | Owned Depth Hub | 长文、SOP、资料、案例、更新 | 阅读深度、搜索、收藏/转发、后续咨询 | 资料/产品/服务 | Derived | [`gzh-Future-Intelligence`](https://github.com/Xander-Xai/gzh-Future-Intelligence) |
| 知乎 | Question Intent | 问答、比较、原因、方法与边界 | 搜索、赞同、收藏、追问、主页行为 | 完整案例/代码/深读 | Derived | 未绑定 |
| CSDN | Developer Search | Error/Root Cause/Solution/Code | 搜索、收藏、代码动作、技术评论 | GitHub/复现 | Derived | 未绑定 |
| YouTube | Global Deep / Search | 英文长视频、Shorts、Benchmark | Impression、CTR、Retention、Returning | Repo/subscribe/next video | Experiment | 未绑定 |
| X | Public Lab | Thread、GIF、Benchmark、Build in Public | Reply、Repost、Profile/Repo action | discuss/reproduce | Experiment | [`X-SuperPlay-X-Growth-OS`](https://github.com/Xander-Xai/X-SuperPlay-X-Growth-OS) |
| GitHub | Proof Infrastructure | Repo、README、Demo、Issue、Evidence | clone/visitor、Issue、Discussion、引用 | reproduce/contribute | Infrastructure | 多仓库基础设施，不单独绑定 |
