# 微信公众号文章样例：质检全过，为什么还是被毙了？

这是 PR-2 的完整文章正文输入样例，当前处于 **BLOCKED**，不是已验证通过或已发布的内容。正文层级、标题摘要、来源、组件样式和待补配图占位均已撰写；请先满足下列素材与执行阻断，不能把它视作可直接发布的成品。

## 输入与预期产物

- 输入契约：`article-input.json`，schema 为 `contentops.gzh-article-input/v1`
- 正文 HTML：`assets/article/article.html`
- 封面：`assets/images/cover.png` 当前缺失；PNG 按仓库全局媒体策略忽略，须先提供已授权、可复现的素材，并走精确路径例外流程
- 预期规则回执与预览：`receipts/gzh-article.json` 和 `assets/article/article_preview.html`；当前回执明确标为 `BLOCKED`/`NOT_RUN`，预览尚未生成

## 内容与来源

文章基于仓内真实失败记录；具体引用见输入 JSON 与正文末尾。复盘数字不被推广为普遍结论。待补图片是占位，不是事实证据，也不是伪造的已生成素材。

## 运行

```bash
python scripts/render_article.py projects/gzh-qc-gap
python tests/test_render_articles.py
```

CLI 只允许使用 `CONTENTOPS_PYTHON` 指定的解释器，未设置时用当前 `sys.executable`，不扫描其他 Python、不安装依赖。它只调用固定 Easel `gzh-design` 的 `validate_gzh_html.py` 和 `wrap_preview.py`，不调用网络、不登录、不运行公众号 API。

本次会话的权限分类器阻止了自动执行上游脚本，因此尚无真实生成的文章预览，也无规则校验 PASS。源码检查不是规则检查，更不是微信公众号编辑器兼容性保证。

## 审核状态

- `status`: `BLOCKED`
- 校验：`NOT_RUN`
- 人工观感审核：`NOT_STARTED`
- `production_ready`: `false`
- `publish_authorized`: `false`
- 微信公众号草稿/API：未调用、未模拟

## 上游资产与许可

复用范围计划限定为 Easel v0.2.1 `gzh-design` 的校验器、预览包装器及 Graphite Minimal / 通用图片组件参考；固定 runtime commit `3fe2d9904c1619281ef57f81d9ee0b7854998399`。资产位于 `.runtime/easel/skills/openclaw/gzh-design/`，目录 LICENSE 为 AGPL-3.0（Copyright 2026 甲木 × 摸鱼小李）。本仓不复制或再分发该 skill。全局 `runtime/gzh-runtime.lock.json` 权利状态仍是 `UNRESOLVED`，此实现不解除该状态。
