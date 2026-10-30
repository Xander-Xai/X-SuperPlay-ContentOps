#!/usr/bin/env node
/**
 * Render a formula ↔ code side-by-side mapping card (Enhancement #4).
 *
 * The card shows the LaTeX formula on the left, the runnable code snippet on
 * the right, and explicit mappings between sub-terms and code lines.
 * This turns abstract formulas into executable intuition, which is the
 * strongest "theory + practice" single visual for deep tutorials.
 */
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { defaultAccount, loadDesignTokens } from "./read_design_tokens.mjs";

const arg = (name) => {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : "";
};

const esc = (value) => String(value ?? "").replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch]));

// NOTE: readYaml + loadDesignTokens were moved to scripts/read_design_tokens.mjs
// (RC3 single source of truth). That module's parseYaml now handles the nested
// accounts.<name>.design_tokens block, so design tokens actually resolve
// instead of silently falling back to hardcoded defaults.

const specFile = arg("--spec");
const specId = arg("--spec-id") || "body-01";
const account = arg("--account") || defaultAccount();
const output = arg("--output");
if (!specFile || !output) {
  console.error("usage: render_formula_code_map.mjs --spec visual-contract.json --spec-id body-01 --account thinktank --output source.html");
  process.exit(2);
}

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const katex = require(path.resolve(here, "../skills/formula-rendering/node_modules/katex"));
const katexCss = fs.readFileSync(path.resolve(here, "../skills/formula-rendering/node_modules/katex/dist/katex.min.css"), "utf8");

const spec = JSON.parse(fs.readFileSync(specFile, "utf8"));
const unit = (spec.units || []).find((item) => String(item.id) === specId);
if (!unit) throw new Error(`visual contract unit not found: ${specId}`);

const tokens = loadDesignTokens(account);
const diagramData = unit.diagram_data && typeof unit.diagram_data === "object" ? unit.diagram_data : {};
const title = String(unit.section_heading || unit.section || "公式与代码对照");
const description = String(unit.viewer_job || "每一行公式，都有对应的代码实现");
const formula = String(unit.formula || unit.latex || diagramData.formula || "\\operatorname{Attention}(Q,K,V)=\\operatorname{softmax}\\left(\\frac{QK^{\\top}}{\\sqrt{d_k}}\\right)V");
const codeLines = String(unit.code || unit.snippet || "# 示例代码").split(/\r?\n/);
const mappings = (unit.mappings || unit.formula_code_mappings || diagramData.mappings || []).map((m) => ({
  term: String(m.term || m.formula_term || ""),
  lines: Array.isArray(m.lines) ? m.lines.map(Number) : [Number(m.line || 1)],
  note: String(m.note || ""),
}));

const renderInline = (tex) => {
  try { return katex.renderToString(tex, { displayMode: false, throwOnError: false, strict: "warn" }); }
  catch (e) { return esc(tex); }
};
const mapAnchors = mappings.map((m, i) => `<div class="map-anchor" data-term="${esc(m.term)}"><span class="map-dot">${i + 1}</span><span class="map-term">${renderInline(m.term)}</span></div>`).join("");
const highlightedCode = codeLines.map((line, i) => {
  const idx = i + 1;
  const matched = mappings.filter((m) => m.lines.includes(idx));
  const badges = matched.map((_, mi) => `<span class="line-badge">${mi + 1}</span>`).join("");
  const cls = matched.length ? "line mapped" : "line";
  return `<div class="${cls}" data-line="${idx}"><span class="line-no">${idx}</span><code>${esc(line)}</code>${badges}</div>`;
}).join("");

const canvasHeight = Math.max(620, 320 + codeLines.length * 34 + mappings.length * 40);

const html = `<!doctype html>
<html lang="zh-CN" data-background-token="background"><head><meta charset="utf-8">
<style>
${katexCss}
* { box-sizing: border-box; margin: 0; padding: 0; }
html, body { width: 1200px; height: ${canvasHeight}px; background: ${tokens.paper}; color: ${tokens.ink}; font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif; }
.page { width: 1200px; height: ${canvasHeight}px; padding: 44px 54px 36px; background: ${tokens.surface}; border: 1px solid ${tokens.line}40; position: relative; }
.eyebrow { font-size: 16px; letter-spacing: 2px; color: ${tokens.accent}; font-weight: 800; text-transform: uppercase; margin-bottom: 10px; }
h1 { font-size: 30px; line-height: 1.25; margin: 0 0 10px; font-weight: 800; color: ${tokens.ink}; }
.sub { font-size: 18px; color: ${tokens.muted}; margin-bottom: 26px; }
.columns { display: grid; grid-template-columns: 1fr 1fr; gap: 32px; height: ${canvasHeight - 220}px; }
.col { background: ${tokens.paper}; border: 2px solid ${tokens.line}55; border-radius: 16px; padding: 22px; overflow: hidden; }
.col-title { font-size: 16px; font-weight: 700; color: ${tokens.accent}; margin-bottom: 16px; letter-spacing: 1px; }
.formula-box { display: flex; flex-direction: column; justify-content: center; min-height: 140px; }
.formula-box .katex { font-size: 1.22em; }
.map-list { margin-top: 22px; display: flex; flex-direction: column; gap: 12px; }
.map-anchor { display: flex; align-items: center; gap: 10px; font-size: 17px; color: ${tokens.ink}; }
.map-dot { width: 24px; height: 24px; border-radius: 50%; background: ${tokens.accent}; color: #fff; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 800; flex-shrink: 0; }
.map-term { font-weight: 700; }
.code-box { font-family: "JetBrains Mono", "SFMono-Regular", Consolas, monospace; font-size: 16px; line-height: 1.65; }
.line { display: flex; align-items: baseline; gap: 10px; padding: 3px 0; border-radius: 6px; }
.line.mapped { background: ${tokens.accent}12; }
.line-no { width: 28px; text-align: right; color: ${tokens.muted}; font-size: 13px; user-select: none; }
.line code { flex: 1; white-space: pre-wrap; word-break: break-all; color: ${tokens.ink}; }
.line-badge { width: 20px; height: 20px; border-radius: 50%; background: ${tokens.accent}; color: #fff; font-size: 11px; display: flex; align-items: center; justify-content: center; font-family: "PingFang SC", sans-serif; font-weight: 700; flex-shrink: 0; }
.foot { position: absolute; left: 54px; right: 54px; bottom: 24px; font-size: 15px; color: ${tokens.muted}; border-top: 1px solid ${tokens.line}30; padding-top: 12px; }
</style></head>
<body data-background-token="background"><main class="page">
  <div class="eyebrow">FORMULA · CODE MAP · ${esc(account)}</div>
  <h1>${esc(title)}</h1>
  <div class="sub">${esc(description)}</div>
  <div class="columns">
    <div class="col">
      <div class="col-title">数学公式</div>
      <div class="formula-box">${katex.renderToString(formula, { displayMode: true, throwOnError: true, output: "htmlAndMathml", strict: "warn" })}</div>
      <div class="map-list">${mapAnchors}</div>
    </div>
    <div class="col">
      <div class="col-title">代码实现</div>
      <div class="code-box">${highlightedCode}</div>
    </div>
  </div>
  <div class="foot">数字徽章与代码行号一一对应；每个可见术语都必须能在正文或代码中找到出处。</div>
</main></body></html>`;

fs.mkdirSync(path.dirname(output), { recursive: true });
fs.writeFileSync(output, html, "utf8");
