# 外部适配器与可选补充项目

主流程不要求安装这些项目。它们只在用户明确启用、凭证已就绪且回执可追踪时运行。

| 适配器 | 目录 | 用途 | 默认状态 |
|---|---|---|---|
| Z5-WeChat-SOP | `skills/z5-wechat-sop` | 三层审核、配图提示词、Playbook | disabled |
| wemp-operator | `skills/wemp-operator` | 日报、周报、评论和互动 | disabled |
| AiToEarn | `skills/aitoearn` | 跨平台分发、互动、变现 | disabled |
| Wechat Publisher | `skills/wechat-publisher` | 本地 Markdown → 草稿箱回退 | fallback |
| Mermaid diagram adapter | `integrations/diagram-mermaid.md` + `integrations/diagram_mermaid.py` | 本地实现 Mermaid 图形类型与导出契约 | enabled-local |
| X-SuperPlay-Strategy reference | `integrations/x-superplay-strategy.yaml` + `integrations/x-superplay-strategy-contract.yaml` | X超玩•未来智能账号的私有战略参考与 Explore/Build 需求信号映射 | reference-verified-private |

## 接入规则

1. 主发布器始终是 `skills/gzh-draft-publisher`，默认 `draft`。
2. 外部适配器必须记录项目 URL、版本/commit、许可证、命令和结果。
3. 适配器失败不得改变主流程状态，也不得静默宣称完成。
4. 评论回复、跨平台发布、群发和变现属于有副作用动作，必须单独确认。
5. 公众号 API、模型 API 和第三方平台凭证只通过 `aws.env`/`.env` 提供。

草稿提交后的回读由 `scripts/verify_draft_submission.py` 负责；只有
`draft/get`、标题/作者/摘要、正文合规和图片数量全部通过，才会写入
`publish-receipt.json` 并标记本篇草稿流程完成。

## 调研过但不直接内置的项目

- [`doocs/md`](https://github.com/doocs/md)：作为成熟的微信排版产品和主题交互对标，不替换当前排版引擎。
- [`langchain-ai/social-media-agent`](https://github.com/langchain-ai/social-media-agent)：只吸收人工审核、接受/拒绝和可恢复执行模式。
- [`microsoft/lida`](https://github.com/microsoft/lida)：只在隔离沙箱中考虑数据图表，默认关闭生成代码执行。
- [`llmsresearch/paperbanana`](https://github.com/llmsresearch/paperbanana)：高级技术图后端候选，第二阶段再评估。
- [`trypostit/trypost`](https://github.com/trypostit/trypost)：AGPL 运营日历参考，不直接合并到核心仓库。

外部项目的功能通过本仓库自己的接口表达，不复制上游实现，也不把外部发布器接入主门禁。

## X-SuperPlay-Strategy 接入边界

`x-superplay-strategy.yaml` 是已授权读取后的可审计项目登记；当前仓库为私有仓库，已锁定到 commit `73fa34f0ecd4aa38bfc7c63d681e600f879f677e`。`x-superplay-strategy-contract.yaml` 只消费其战略文档中的账号定位、内容支柱、需求信号和 30/60/90 天验证框架，不把参考仓库当作运行时依赖、渲染器或发布器。仓库未声明许可证和代码依赖，因此不复制或执行上游代码。
