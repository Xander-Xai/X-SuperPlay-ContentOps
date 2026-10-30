# 调研与实测

- 状态：research_complete，等待研究来源审查门禁
- 调研时间：2026-08-25（Asia/Shanghai）
- 选题：MCP工具调用的生产治理

## 调研结论

本轮只保留三类与正文直接相关的官方来源：MCP规范用于协议边界，Dogwood用于相邻的时间序列授权机制，Anthropic Claude Code文档用于显式工具许可实现。每条来源都必须在 `source-review.json` 中提取原文短摘录、定位、主题匹配、支持范围和局限后才能进入正文。

## 来源与版本

1. [MCP 2026-07-28 specification changelog](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/changelog.mdx)，版本范围：MCP specification 2026-07-28。
2. [Dogwood authorization guide](https://github.com/dogwood-policy/dogwood/blob/main/dogwood-docs/guide/00-introduction.md)，版本范围：main 分支快照，正式实现前需锁定 commit。
3. [Claude Code CLI MCP permissions](https://docs.anthropic.com/en/docs/claude-code/cli-usage)，版本范围：当前公开 CLI 文档快照。

## 可复现命令

```powershell
python scripts/verify_sources.py --article <article> --offline-import <article>\\work\\offline-source-snapshots
python scripts/verify_claims.py --article <article>
python scripts/source_evidence.py audit --article <article>
python scripts/source_review.py --article <article> --audit
```

## 限制

- 来源验证证明抓取快照与哈希一致，不证明来源内容本身永远正确。
- Dogwood是相邻策略实现，不能被改写成MCP协议原生能力。
- Anthropic文档是具体客户端实现案例，不能外推为所有MCP客户端的统一行为。
- 本轮没有运行真实MCP服务或生产部署；可复现指研究证据流水线可重放。

## 证据等级

- MCP规范：official-repo / primary
- Dogwood指南：official-repo / primary / adjacent
- Anthropic CLI文档：official-docs / primary / adjacent
