---
name: content-production
display_name: "账号化内容生产"
description: "按账号画像把研究证据转成初稿、审核定稿和发布资产，所有产物都进入公众号矩阵的顺序门禁。"
category: content-creation
version: 1.0.0
author: Matrix Ops
visibility: public
---

# 账号化内容生产

## 生产契约

输入必须包含 `content-brief.yaml`、`topic-card.md` 和 `research.md`。输出顺序固定为：

`draft.md` → `review-report.md` → `article.md` → `article.html` → `visual-brief.yaml` → `publish-receipt.json`。

初稿、定稿和草稿箱正文不能混用。没有证据、版本或限制说明时，停止在调研阶段。

## 账号差异

### AI哨兵

- 800～1500 字；
- 首屏给出判断；
- 必须包含实测结果、适用人群、部署难度和“值得/观望/避坑”结论；
- 公众号定稿通过 `final_reviewed` 后，才可输出小红书笔记和短视频口播草稿；这些是派生附件，不自动跨平台发布，也不计入公众号主链路完成。

### X超玩•未来智能

- 2500～5000 字；
- 依次完成问题、原理、实践、失败处理和资产化；
- 至少包含一个可复现流程或架构图；
- 文末转化区必须与文章结论相关，发布前可删除。

## 阻断规则

- 不以“模型已经写完”代替事实审核；
- 不以“图片已生成”代替视觉质量审核；
- 不调用发布器跳过 `draft_submitted` 门禁；
- 不以短视频脚本、渲染视频或音频文件替代 `article.html`；派生媒体必须通过 `scripts/media_guard.py`。
- 所有外部 API 和凭证使用情况写入回执，不打印密钥。
