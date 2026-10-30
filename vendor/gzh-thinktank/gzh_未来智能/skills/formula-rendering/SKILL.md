---
name: formula-rendering
description: 公众号技术文章的 LaTeX 公式确定性渲染器：保留 canonical LaTeX，使用 KaTeX 与 Chrome 生成紧致裁剪、移动端可读的 PNG，并校验源/图片/HTML 哈希。
---

# 公众号 LaTeX 公式渲染

技术文章中的 `$...$` 与 `$$...$$` 不是普通代码文本。此 skill 将 `article.md`
作为唯一公式源，生成可审计的 `formula-src/*.tex`、`formula-manifest.json` 和
`formula-src/*.svg`、`formula-src/*.html` 和 `imgs/formulas/*.png`，再由公众号排版器把 PNG 注入 `article.html`。

## 标准用法

```powershell
python scripts/formula_pipeline.py prepare --article <外部active/THK-...>
python skills/gzh-article-format/scripts/format.py <外部active/THK-...>/article.md `
  --theme thinktank-atlas -o <外部active/THK-...>/article.html
python scripts/formula_pipeline.py check --article <外部active/THK-...>
```

`prepare` 会调用本目录内锁定版本的 KaTeX，并使用本机 Chrome 生成高分辨率
PNG。发布 HTML 不加载外部 KaTeX runtime，也不能残留裸 `$...$`、`R^(...)`、
`QK^T` 或 `sqrt(d_k)` 正式公式。

## 强制审计

- `article.md` 保留规范 LaTeX；`article.render.md` 是可重建的排版输入，不作为
  内容源。
- 每个公式必须有 `formula_id`、模式、canonical 源文件、PNG、源/输出 SHA-256、
  `section_heading`、`source_excerpt_sha256` 和章节 `claim_ids`。
- 公式 PNG 使用 `katex-html-chrome-tight-v3`：先以 KaTeX 生成透明背景 HTML，再用 Chrome 2× DPR 截图并按 alpha 内容裁剪空白；公式采用纯白前景与深蓝细描边（不使用模糊阴影），并以 Times New Roman 作为拉丁字符字体。manifest 必须记录 `pixel_ratio`、`css_width`、`css_height`、`visual_metrics`、空白比例和 `mobile_readable`。排版器按 CSS 尺寸回写图片，避免高 DPI 资产在桌面或手机端被放大/缩小后失真；行内公式统一按 1.2em 级别和负基线对齐。
- 规范正文中的维度、下标、矩阵 Shape、复杂度表达必须使用 `$...$` 或 `$$...$$`；`formula_pipeline.py check` 会阻断仍写在反引号中的 `B×n_q×d_v`、`W_O`、`d_model`、`O(t·d)` 等数学表达。真正的 Python/CLI 代码（如 `dim=-1`）才允许保留反引号。
- v2 manifest 还必须记录 `svg_output/svg_sha256`、`html_output/html_sha256`、`clipped` 与 `unresolved_placeholder`；缺少任一中间资产时不得通过排版门禁。
- `formula_pipeline.py check` 失败时，`formatted` 和 `illustrated` 门禁都不能推进。
- 公式图只负责精确数学内容；架构、流程、矩阵 Shape 和 Cache 关系图仍由
  `visual-contract.json` 驱动的 SVG/HTML 确定性渲染器生成。
- KaTeX 依赖版本固定在 `package.json` / `package-lock.json`，许可证见
  `THIRD_PARTY_NOTICES.md`。
