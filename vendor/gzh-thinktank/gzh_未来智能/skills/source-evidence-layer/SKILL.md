---
name: source-evidence-layer
display_name: "可信信源混合证据层"
description: "把官方文档、官方仓库、论文和本地复现统一为可核验的证据账本，并在篇尾生成原始摘录、截图与参考资料清单。"
category: research-and-provenance
version: 1.0.0
visibility: public
---

# 可信信源混合证据层

这不是“给 AI 文章加几个链接”，而是把内容生产拆成三件可审计的事：

1. 来源是否值得信任（第一方、标准、论文、维护者资料，还是二手评论）；
2. 文章中的每个关键判断能否回链到来源和快照；
3. 读者能否看到少量真实原文/截图，而不是只看到模型改写。

## 工作契约

- `sources.json` 是事实来源登记册，负责 URL、检索时间、版本和 claims。
- `source-verification.json` 是抓取/快照哈希回执，证明来源确实被抓取过。
- `source-review.json` 是研究来源相关性审查回执，证明每个来源已被提取摘要/短摘录、定位、主题匹配、范围/局限和采用决策；它与 `source-verification.json` 分工不同，来源可访问不等于来源可采用。
- `evidence-plan.json` 是人工可编辑的使用计划，声明 trusted/tier、claim_ids、摘录、截图、授权与复用原因。
- `source-evidence.json` 是机器审计回执，记录可信信源数量、域名多样性、逐主张证据覆盖、证据文件哈希和错误。
- `evidence-provenance.json` 是本次审计的内容寻址回放回执：把 `sources.json`、`source-verification.json`、主题合同、快照和 evidence 单元的字节哈希绑定为 `pack_sha256`。篇尾生成后还会把 `article.md` / `article.html` 作为产品材料纳入下一次 pack；它只证明本地输入/输出完整性，不证明来源真伪、真人身份或不可抵赖性。
- `evidence-lineage.json` 是受 OpenLineage 的 run/job/dataset 与 in-toto 的 materials/products 启发的离线血缘回执；它记录本次审计的 run、job、输入和输出摘要，但明确是 unsigned、`identity_authenticated: false`，不能替代签名或真人批准。
- `topic-evidence-isolation.json` 是主题隔离回执；证据计划必须保存当前 `topic-contract.yaml` 的指纹，正文采用的每个来源必须命中当前主题锚点。换主题时必须重新绑定，不能复制上一主题的 evidence 目录。
- `article.md` / `article.html` 的篇尾由脚本自动写入“原始证据摘录 + 可信信源清单”。

## 推荐命令

```powershell
python scripts/source_evidence.py init --article <文章目录>
python scripts/topic_evidence_isolation.py bind --article <文章目录>
python scripts/source_evidence.py capture --article <文章目录> --source-id <source_id>
python scripts/source_evidence.py audit --article <文章目录>
python scripts/source_evidence.py append --article <文章目录>
python scripts/source_evidence.py audit --article <文章目录> --require-appendix
```

`source_evidence.py audit` 会同时写入 `topic-evidence-isolation.json`。若主题指纹不一致、正文来源未命中当前主题，或 `evidence/` 中存在未登记的旧文件，研究门禁会阻断；只有换题后重新绑定并重建证据计划，才能继续。

截图不是事实证明的替代品：截图、短摘录和原始快照必须同时保留来源 URL、定位信息、`claim_ids`、`captured_at`、SHA-256、授权状态和人工复用决定。只有 `used_in_article=true` 的来源证据可以满足正文 claim 覆盖；隐藏来源不能为公开主张制造“已举证”假象。没有明确授权时，证据可以留在工作区，但不得自动进入对外发布稿。

审计还会验证外部来源与 `source-verification.json` 的双向绑定、`retrieved_at + freshness_days` 新鲜度，以及每个 claim 至少拥有一个有效 evidence 单元；只声明“来源存在”不能通过研究门禁。

## GitHub 能力适配

- ArchiveBox：可选的多格式存档后端（HTML/PDF/截图/WARC）；通过离线导入接入，不改变本地账本。
- Playwright：可选的浏览器截图后端；当前脚本用系统 Chrome/Edge，后续可替换为 Playwright。
- Trafilatura：可选的正文/元数据抽取后端；当前无依赖模式保留人工摘录。
- Citation.js / Zotero：适合论文密集型内容；可以把 CSL-JSON 导出映射到 `sources.json`，但公众号文章仍以本地可读参考资料清单为最终交付。

## 内容寻址与血缘适配

- in-toto 的 materials/products 思路对应本地 `pack_sha256`：先冻结输入，再记录产物；这里保留无签名模式，不冒充身份认证。
- OpenLineage 的 run/job/dataset 思路对应 `run_id`、主题指纹、来源/claim/evidence 集合；后续可把 `evidence-provenance.json` 映射到事件系统。
- DVC/lakeFS 的版本指针思路对应快照和 evidence 文件哈希；当前不引入服务依赖，先保证工作区内可回放。
- Playwright/ArchiveBox 仍是可替换的捕获后端，必须写回同一份 evidence 单元合同，不能绕开 claim 绑定与授权门。
