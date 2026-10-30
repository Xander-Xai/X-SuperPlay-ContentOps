# gzh-design-skill

A local WeChat Official Account article formatter and deterministic HTML quality checker. It converts reviewed Markdown into inline-styled WeChat HTML and checks platform restrictions, image alt text, `span leaf` wrapping, and unsafe tags before delivery.

```powershell
python scripts/validate_gzh_html.py --strict article.html
python scripts/component_lint.py .
python scripts/wrap_preview.py article.html --output article_preview.html
```

Themes live under `references/`. The matrix selects the two account themes from `profiles/visual-styles.yaml`. Formatting does not write content, publish drafts, or store credentials; the repository gate must pass first.
