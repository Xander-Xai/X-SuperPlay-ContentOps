# Agent 本地写作脚本用法

脚本位于 `{baseDir}/scripts/write.py`，不调用外部写作服务。

```powershell
python skills/gzh-article-writing/scripts/write.py prompt draft <外部active/THK-...>/topic-card.md
python skills/gzh-article-writing/scripts/write.py prompt rewrite <外部active/THK-...>/article.md --instruction "改成口语化"
python skills/gzh-article-writing/scripts/write.py strip-citations <外部active/THK-...>/draft.md -o <外部active/THK-...>/article.md
```

`prompt` 返回 `system_prompt`、`user_prompt` 和公开约束；当前 Agent 依据该结果直接生成正文。
`strip-citations` 是审稿前的纯文本清理，不改变事实内容。
