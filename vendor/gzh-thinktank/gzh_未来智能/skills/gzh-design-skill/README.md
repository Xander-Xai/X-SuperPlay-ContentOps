# gzh-design-skill

公众号图文排版与确定性质量校验引擎。它把已经审核的 Markdown 文章转换为样式内联的微信 HTML，并在交付前检查平台限制、图片替代文本、`span leaf` 文本包裹和危险标签。

## 本地用法

```powershell
python scripts/validate_gzh_html.py --strict article.html
python scripts/component_lint.py .
python scripts/wrap_preview.py article.html --output article_预览.html
```

主题模板位于 `references/`，公众号矩阵的两套默认主题由 `profiles/visual-styles.yaml` 选择。排版本身不写稿、不发布，也不保存账号凭证；发布前必须通过仓库根目录的顺序门禁。

## 质量契约

- 最终 HTML 必须 `0 ERROR / 0 WARNING`；
- 禁止 `<style>`、`<script>`、`<div>`、外部字体和固定定位；
- 图片必须有非空 `alt`，本地图片必须能从文章目录解析；
- 代码、引用和正文文字使用安全的内联样式；
- 修改主题后先跑组件检查，再重新生成并校验文章 HTML。

完整主题说明见 [`docs/all-themes.md`](docs/all-themes.md)，组件示例见 [`references/common-components.md`](references/common-components.md)。
