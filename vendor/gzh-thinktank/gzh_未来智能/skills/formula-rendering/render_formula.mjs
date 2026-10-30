#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import katex from "katex";

function arg(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : "";
}

const input = arg("--input");
const output = arg("--output");
const mode = arg("--mode") || "block";
if (!input || !output) {
  console.error("usage: render_formula.mjs --input formula.tex --output formula.html --mode inline|block");
  process.exit(2);
}

const tex = fs.readFileSync(input, "utf8").trim();
let rendered;
try {
  rendered = katex.renderToString(tex, {
    displayMode: mode === "block",
    throwOnError: true,
    output: "htmlAndMathml",
    strict: "warn",
  });
} catch (error) {
  console.error(`KaTeX render failed: ${error.message}`);
  process.exit(1);
}

const cssPath = path.join(path.dirname(fileURLToPath(import.meta.url)), "node_modules", "katex", "dist", "katex.min.css");
const css = fs.readFileSync(cssPath, "utf8");
const html = `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><style>
html,body{margin:0;padding:0;width:max-content;height:max-content;background:transparent;font-family:"Times New Roman","KaTeX_Main",serif;}
${css}
.formula{display:inline-block;padding:2px 4px;color:#17324D;background:transparent;font-family:"Times New Roman","KaTeX_Main",serif;font-size:${mode === "inline" ? "20px" : (tex.length > 150 ? "19px" : "24px")};line-height:1.2;-webkit-text-stroke:0.18px #0D1F2A;}
.formula .katex,.formula .katex *{color:#17324D !important;font-family:"Times New Roman","KaTeX_Main",serif !important;-webkit-text-stroke:0.12px #0D1F2A;}
.formula .katex-display{margin:0;}
.baseline-marker{display:inline-block;width:0;height:0;padding:0;margin:0;vertical-align:baseline;}
</style></head><body><div id="formula-box" class="formula">${rendered}<span id="baseline-marker" class="baseline-marker"></span></div>
<script>
document.addEventListener('DOMContentLoaded', function () {
  const box = document.getElementById('formula-box');
  const marker = document.getElementById('baseline-marker');
  if (!box || !marker) return;
  const boxRect = box.getBoundingClientRect();
  const markerRect = marker.getBoundingClientRect();
  const metrics = document.createElement('div');
  metrics.id = 'formula-metrics';
  metrics.style.display = 'none';
  metrics.setAttribute('data-baseline-y', String(markerRect.top - boxRect.top));
  metrics.setAttribute('data-box-height', String(boxRect.height));
  box.appendChild(metrics);
});
</script></body></html>`;
fs.mkdirSync(path.dirname(output), { recursive: true });
fs.writeFileSync(output, html, "utf8");
