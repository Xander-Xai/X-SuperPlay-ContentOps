#!/usr/bin/env node
/** Render an account-themed Mermaid diagram from the visual contract.
 *
 * Usage:
 *   node scripts/render_mermaid_visual.mjs \
 *     --spec article/visual-contract.json --spec-id body-05 \
 *     --output article/imgs/diagram-sources/body-05.svg \
 *     [--account sentinel|thinktank]
 *
 * The visual contract may carry the diagram source in:
 *   - unit.mermaid / unit.diagram
 *   - unit.expected_elements (auto-wired into a left-to-right flowchart)
 *   - unit.visual_type (fallback stock diagrams for multihead / kv-cache)
 *
 * Account theme colors come from profiles/visual-styles.yaml design_tokens so
 * every architecture/flow/relationship visual stays consistent with the rest
 * of the article assets.
 */
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { pathToFileURL, fileURLToPath } from "node:url";
import { defaultAccount, loadDesignTokens } from "./read_design_tokens.mjs";

const arg = (name) => {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : "";
};

const specPath = arg("--spec");
const specId = arg("--spec-id") || "body-05";
const output = arg("--output");
const account = arg("--account") || defaultAccount();

if (!specPath || !output) {
  console.error(
    "usage: render_mermaid_visual.mjs --spec visual-contract.json --spec-id body-05 --output diagram.svg [--account sentinel|thinktank]"
  );
  process.exit(2);
}

const root = path.dirname(fileURLToPath(import.meta.url));
const skillRoot = path.resolve(root, "../skills/beautiful-mermaid");
const mermaidModule = path.join(skillRoot, "node_modules/beautiful-mermaid/dist/index.js");
const { renderMermaid, THEMES } = await import(pathToFileURL(mermaidModule).href);

const spec = JSON.parse(fs.readFileSync(specPath, "utf8"));
const unit = (spec.units || []).find((item) => String(item.id) === specId);
if (!unit) throw new Error(`visual contract unit not found: ${specId}`);

const type = String(unit.visual_type || unit.kind || "architecture").toLowerCase();

// 账号主题色唯一来源：profiles/visual-styles.yaml 的 design_tokens（RC3）。
// 旧代码在此硬编码了一份 THEMES_BY_ACCOUNT 副本，会随 YAML 漂移；现统一从
// 共享 helper 读取。下游仍引用 bg/fg/line/accent/muted/surface/border 字段名。
const _tokens = loadDesignTokens(account);
const accountTheme = {
  bg: _tokens.paper,
  fg: _tokens.ink,
  line: _tokens.line,
  accent: _tokens.accent,
  muted: _tokens.muted,
  surface: _tokens.surface,
  border: _tokens.accent,
};

function buildDiagram() {
  const explicit = String(unit.mermaid || unit.diagram || "").trim();
  if (explicit) return explicit;

  const elements = (unit.expected_elements || [])
    .map((value) => String(value).trim())
    .filter(Boolean);
  if (elements.length >= 2) {
    const nodes = elements.map((text, index) => {
      const safe = text.replace(/[\[\]"()]/g, " ").replace(/\s+/g, " ").trim().slice(0, 32);
      return `  N${index}[${safe}]`;
    });
    const edges = elements
      .slice(0, -1)
      .map((_, index) => `  N${index} --> N${index + 1}`);
    return `graph LR\n${nodes.join("\n")}\n${edges.join("\n")}`;
  }

  throw new Error(`visual contract ${specId} lacks explicit mermaid diagram or at least two expected_elements`);
}

const diagramSource = buildDiagram();
const unsafeDiagram = /<\s*script\b|<\s*foreignObject\b|javascript\s*:|(?:^|\s)click\s+|href\s*=|style\s*:/i;
if (diagramSource.length > 20000) {
  throw new Error("Mermaid source too large: " + diagramSource.length + " chars");
}
if (unsafeDiagram.test(diagramSource)) {
  throw new Error("Mermaid source rejected by strict/sandbox policy");
}

let svg = await renderMermaid(diagramSource, {
  ...(THEMES["github-light"] || {}),
  font: "PingFang SC, Microsoft YaHei, Times New Roman",
  ...accountTheme,
});

// beautiful-mermaid 在 headless Chrome 离线环境下可能把 color-mix() / CSS var 当成
// 默认值回退，导致黑块。这里把 SVG 里的关键 var() 直接内联成账号主题色。
svg = svg.replace(/@import url\('https:\/\/fonts[^']*'\);/g, "");
svg = svg.replace(/font-family:\s*'Inter',\s*system-ui,\s*sans-serif;/g,
  "font-family: 'PingFang SC','Microsoft YaHei',system-ui,sans-serif;");
svg = svg.replace(/fill="var\(--_text\)"/g, `fill="${accountTheme.fg}"`);
svg = svg.replace(/fill="var\(--_node-fill\)"/g, `fill="${accountTheme.surface}"`);
svg = svg.replace(/stroke="var\(--_node-stroke\)"/g, `stroke="${accountTheme.border}"`);
svg = svg.replace(/stroke="var\(--_line\)"/g, `stroke="${accountTheme.line}"`);
svg = svg.replace(/fill="var\(--_arrow\)"/g, `fill="${accountTheme.accent}"`);
svg = svg.replace(/background:var\(--bg\)/g, `background:${accountTheme.bg}`);
svg = svg.replace(/<svg\b([^>]*)>/, `<svg$1 data-backend="beautiful-mermaid" data-visual-type="${type}" data-account="${account}">`);

fs.mkdirSync(path.dirname(output), { recursive: true });
fs.writeFileSync(output, svg, "utf8");

// 同时写出 HTML wrapper，方便 Chrome 截屏时保留背景色与居中。
const widthMatch = svg.match(/width="([0-9.]+)"/);
const heightMatch = svg.match(/height="([0-9.]+)"/);
const width = widthMatch ? Math.ceil(Number(widthMatch[1])) : 900;
const height = heightMatch ? Math.ceil(Number(heightMatch[1])) : 600;
// Do not inject a second `style` attribute into the SVG root.  HTML parsing
// treats duplicate attributes as a parse error and browsers keep only one of
// them; dropping the original CSS variables makes `fill="var(--bg)"` invalid
// and produces opaque black rectangles in the rasterized screenshot.  Merge
// the sizing declaration into the existing style instead.
const svgForHtml = svg.replace(/<svg\b([^>]*)>/, (match, attrs) => {
  const styleMatch = attrs.match(/\sstyle="([^"]*)"/i);
  if (styleMatch) {
    const merged = `${styleMatch[1].replace(/;?\s*$/, "")};max-width:100%`;
    const replaced = attrs.replace(styleMatch[0], ` style="${merged}"`);
    return `<svg${replaced}>`;
  }
  return `<svg${attrs} style="max-width:100%">`;
});

if (/<\s*script\b|<\s*foreignObject\b|\bon[a-z]+\s*=|javascript\s*:|href\s*=\s*["']https?:\/\//i.test(svg)) {
  throw new Error("Mermaid SVG rejected by output sanitizer");
}
const html = `<!doctype html><html><head><meta charset="utf-8"></head>
<body style="margin:0;background:${accountTheme.bg};display:flex;align-items:center;justify-content:center;width:${width + 40}px;height:${height + 40}px">
${svgForHtml}</body></html>`;
const htmlPath = output.replace(/\.svg$/, ".html");
fs.writeFileSync(htmlPath, html, "utf8");

console.log(`MERMAID VISUAL RENDERED: ${output} (${svg.length} bytes), html: ${htmlPath}`);
