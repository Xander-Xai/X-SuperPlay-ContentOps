# handoff 输入契约

把已批准的 handoff 卡片复制到 `inbox/handoff/<handoff_id>/handoff-card.md` 后，先运行：

```powershell
python scripts/validate_handoff.py --card inbox/handoff/<handoff_id>/handoff-card.md
```

卡片必须以 YAML frontmatter 开头：

```yaml
---
schema_version: 1
contract: handoff-contract-v1
source_article_ref: "原哨兵文章路径、URL 或文章 ID"
source_article_sha256: "64 位 SHA-256"
signal_count: 3
required_signals:
  - repeated_deployment_questions
  - source_or_code_requests
  - above_baseline_engagement
target_topic: "准备深挖的主题"
human_confirmed_by: "人工确认人"
approved_at: "2026-08-10T12:00:00+08:00"
---

# 读者问题与升级理由

## 读者问题样本

## 复现/源码线索
```

该目录只允许人工复制输入；工作流不会读取源仓库或其他外部目录。
