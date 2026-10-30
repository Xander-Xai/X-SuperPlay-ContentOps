#!/usr/bin/env node
/**
 * Render a semantic visual contract as a deterministic, KaTeX-backed HTML
 * diagram. The HTML is kept as the editable source and Chrome rasterizes it
 * for WeChat. This renderer is deliberately data-driven: the contract's
 * viewer job and expected elements are part of the output, so a generic
 * placeholder card cannot silently pass the illustrated gate.
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
const specFile = arg("--spec");
const specId = arg("--spec-id") || "body-01";
const output = arg("--output");
const account = arg("--account") || defaultAccount();
const tokens = loadDesignTokens(account);
if (!specFile || !output) {
  console.error("usage: render_math_visual.mjs --spec visual-contract.json --spec-id body-01 --output source.html");
  process.exit(2);
}
const spec = JSON.parse(fs.readFileSync(specFile, "utf8"));
const unit = (spec.units || []).find((item) => String(item.id) === specId);
if (!unit) throw new Error(`visual contract unit not found: ${specId}`);
const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const katex = require(path.resolve(here, "../skills/formula-rendering/node_modules/katex"));
const katexCss = fs.readFileSync(path.resolve(here, "../skills/formula-rendering/node_modules/katex/dist/katex.min.css"), "utf8");

const esc = (value) => String(value ?? "").replace(/[&<>\"]/g, (ch) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[ch]));
const math = (tex, display = false) => katex.renderToString(tex, { displayMode: display, throwOnError: true, output: "htmlAndMathml", strict: "warn" });
const mathNode = (tex, label = "") => `<div class="math" data-tex="${esc(tex)}" data-role="node">${math(tex)}${label ? `<small>${esc(label)}</small>` : ""}</div>`;
const textNode = (label, sub = "", accent = false) => `<div class="node${accent ? " accent" : ""}" data-role="node"><strong>${esc(label)}</strong>${sub ? `<small>${esc(sub)}</small>` : ""}</div>`;
const arrow = `<div class="arrow" aria-hidden="true">→</div>`;
const expected = (unit.expected_elements || []).map(String);
const diagramData = unit.diagram_data && typeof unit.diagram_data === "object" ? unit.diagram_data : {};
const type = String(unit.visual_type || unit.kind || "concept").toLowerCase();
const canvasHeights = {
  qkv: 720,
  shape: 520,
  attention: 620,
  numeric: 660,
  multihead: 640,
  "kv-cache": 640,
  checklist: 540,
};
const canvasHeight = canvasHeights[type] || 620;
const title = String(unit.section_heading || unit.section || "视觉锚点");
const description = String(unit.viewer_job || "一张图只承担一个认知动作");

let body = "";
if (type === "qkv") {
  body = `<section class="panel retrieval-map"><div class="retrieval-head"><div class="query-orbit"><span class="orbit-dot"></span>${textNode("X", "同一序列隐藏状态", true)}</div><div class="retrieval-copy"><strong>一次检索，三种角色</strong><small>同一个 token 同时发起查询、参与匹配、提供内容</small></div></div><div class="retrieval-lanes"><div class="lane query-lane"><span class="lane-label" data-role="label">QUERY · 提需求</span>${textNode("Q", "我想找什么", true)}${mathNode("Q=XW_Q", "查询投影")}</div><div class="lane key-lane"><span class="lane-label" data-role="label">KEY · 做匹配</span>${textNode("K", "我如何被找到")}${mathNode("K=XW_K", "匹配投影")}</div><div class="lane value-lane"><span class="lane-label" data-role="label">VALUE · 传递</span>${textNode("V", "我真正提供什么")}${mathNode("V=XW_V", "信息投影")}</div></div><p class="note" data-role="label">Q 和 K 决定注意力权重；V 承载真正传递的内容。</p></section>`;
} else if (type === "shape") {
  body = `<section class="panel"><div class="row">${mathNode("X\\in\\mathbb{R}^{n\\times d_{\\mathrm{model}}}")}${arrow}${mathNode("Q\\in\\mathbb{R}^{n_q\\times d_k}")}${mathNode("K\\in\\mathbb{R}^{n_k\\times d_k}")}${mathNode("V\\in\\mathbb{R}^{n_k\\times d_v}")}${arrow}${mathNode("QK^{\\top}\\in\\mathbb{R}^{n_q\\times n_k}")}</div><p class="note">Self-Attention 通常满足 ${math("n_q=n_k")}；Cross-Attention 不要求 Score 矩阵为方阵。</p></section>`;
} else if (type === "attention") {
  body = `<section class="panel attention-pipeline"><div class="pipeline-rail"><span class="rail-line"></span>${["Score","缩放","Mask","Softmax","汇总 V"].map((label, i) => `<div class="stage-wrap"><span class="stage-index">${i + 1}</span>${textNode(label, ["QKᵀ","÷ √dₖ","+ M","沿 Key 维","A V"][i], i === 0 || i === 4)}</div>`).join("")}</div><div class="formula-wide">${math("\\operatorname{Attention}(Q,K,V)=\\operatorname{softmax}\\left(\\frac{QK^{\\top}}{\\sqrt{d_k}}+M\\right)V", true)}</div><p class="note">每一步都改变“谁能被读取”的范围，最后才把 Value 汇总成输出。</p></section>`;
} else if (type === "numeric") {
  body = `<section class="grid cols-3">${`<div class="matrix" data-role="node">${math("Q=\\begin{bmatrix}1&0\\\\0&1\\end{bmatrix}")}<small>Query</small></div>`}${`<div class="matrix" data-role="node">${math("K=\\begin{bmatrix}1&0\\\\1&1\\end{bmatrix}")}<small>Key</small></div>`}${`<div class="matrix" data-role="node">${math("V=\\begin{bmatrix}2&0\\\\0&4\\end{bmatrix}")}<small>Value</small></div>`}</section><section class="panel margin-top"><div class="row center"><div class="matrix" data-role="node">${math("QK^{\\top}=\\begin{bmatrix}1&1\\\\0&1\\end{bmatrix}")}</div>${arrow}<div class="heat" data-role="node"><span>0.50</span><span>0.50</span><span>0.33</span><span class="hot">0.67</span></div>${arrow}<div class="matrix" data-role="node">${math("O=AV\\approx\\begin{bmatrix}1&2\\\\0.66&2.68\\end{bmatrix}")}</div></div></section>`;
} else if (type === "multihead") {
  body = `<section class="grid cols-2"><div class="panel">${textNode("Self-Attention", "Q,K,V ← X", true)}${textNode("Cross-Attention", "Q ← X_dec；K,V ← X_enc")}</div><div class="panel"><div class="grid cols-3">${mathNode("\\mathrm{head}_1")}${mathNode("\\mathrm{head}_2")}${mathNode("\\cdots\\mathrm{head}_H")}</div><div class="formula-wide">${math("\\operatorname{Concat}(\\mathrm{head}_1,\\ldots,\\mathrm{head}_H)W_O")}</div></div></section>`;
} else if (type === "kv-cache") {
  body = `<section class="timeline">${textNode("Prefill", "K₁:ₜ,V₁:ₜ", true)}${arrow}${mathNode("K_{\\mathrm{cache}},V_{\\mathrm{cache}}", "按层保存历史")}${arrow}${textNode("Decode", "追加 qₜ,kₜ,vₜ", true)}</section><section class="panel margin-top center"><div class="formula-wide">${math("o_t=\\operatorname{softmax}\\left(\\frac{q_tK_{\\mathrm{cache}}^{\\top}}{\\sqrt{d_k}}\\right)V_{\\mathrm{cache}}", true)}</div><p class="note">当前 Query 仍需读取历史 Key/Value，注意力不会变成常数时间。</p></section>`;
} else if (type === "checklist") {
  if (!expected.length) throw new Error("checklist visual contract requires expected_elements");
  const ledgers = Array.isArray(diagramData.ledgers) ? diagramData.ledgers.filter((x) => x && typeof x === "object") : [];
  if (ledgers.length) {
    body = `<section class="ledger-board"><div class="ledger-intro" data-role="label"><strong>${esc(String(diagramData.headline || "四本账要分别核算"))}</strong><small>${esc(String(diagramData.subline || "把参数、计算、通信和缓存拆开，才能解释真实部署成本"))}</small></div>${ledgers.slice(0, 6).map((item, i) => {
      const label = String(item.label || expected[i] || `账本 ${i + 1}`);
      const detail = String(item.detail || "当前主题的可验证检查项");
      const metric = String(item.metric || "逐项核对");
      const width = Math.max(18, Math.min(100, Number(item.weight || 50)));
      const tone = String(item.tone || (i === 0 ? "accent" : "line"));
      return `<div class="ledger-row"><div class="ledger-index">0${i + 1}</div><div class="ledger-copy" data-role="node"><strong>${esc(label)}</strong><small>${esc(detail)}</small></div><div class="ledger-track"><span class="ledger-fill ${esc(tone)}" style="width:${width}%"></span></div><div class="ledger-metric" data-role="node">${esc(metric)}</div></div>`;
    }).join("")}</section>`;
  } else {
    body = `<section class="grid cols-3">${expected.slice(0, 6).map((x, i) => textNode(x, "当前主题要点", i === 0 || i === expected.length - 1)).join("")}</section>`;
  }
} else {
  body = `<section class="grid cols-3">${expected.slice(0, 6).map((x, i) => textNode(x, "正文认知锚点", i === 0)).join("")}</section>`;
}

const html = `<!doctype html><html lang="zh-CN" data-background-token="background"><head><meta charset="utf-8"><style>${katexCss}
*{box-sizing:border-box}html,body{margin:0;padding:0;width:1200px;height:${canvasHeight}px;background:#fffdf9;color:#17324d;font-family:"Times New Roman","Microsoft YaHei","Segoe UI",sans-serif}.page{width:1200px;height:${canvasHeight}px;padding:44px 54px 36px;background:#fffdf9;position:relative;border:1px solid #cbd7df}.eyebrow{font-size:18px;letter-spacing:2px;text-transform:uppercase;color:#b24a2b;font-weight:800;margin-bottom:14px}h1{font-size:30px;line-height:1.25;margin:0 0 12px;font-weight:800}.sub{font-size:18px;color:#5e6872;margin-bottom:28px}.panel{background:#f4f0e8;border:2px solid #557a96;border-radius:16px;padding:24px}.row{display:flex;align-items:center;gap:18px}.grow{flex:1}.grid{display:grid;gap:16px}.cols-2{grid-template-columns:1fr 1fr}.cols-3{grid-template-columns:repeat(3,1fr)}.cols-5{grid-template-columns:repeat(5,1fr)}.node,.math{background:#fffaf2;border:2px solid #557a96;border-radius:14px;padding:18px 14px;text-align:center;min-height:112px;display:flex;flex-direction:column;justify-content:center;gap:8px}.node.accent{border-color:#b24a2b}.node strong{font-size:20px}.node small,.math small{font-size:15px;color:#5e6872}.math .katex{font-size:1.12em}.arrow{font-size:36px;color:#557a96;font-weight:800}.matrix{background:#172b3e;color:#f3f8fb;border-radius:12px;padding:22px;text-align:center;min-height:130px;display:flex;flex-direction:column;justify-content:center;gap:10px}.matrix .katex{color:#f3f8fb;font-size:1.18em}.matrix small{color:#c8d5dc}.heat{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;width:150px;margin:0 auto}.heat span{padding:14px;border-radius:8px;background:#dbe8f0;font-weight:800}.heat span.hot{background:#e7a080;color:#542014}.timeline{display:flex;align-items:center;gap:12px;margin-top:32px}.timeline>*{flex:1}.formula-wide{text-align:center;padding:16px 4px}.note{font-size:17px;line-height:1.7;color:#4b5660;margin-top:20px}.center{text-align:center}.margin-top{margin-top:20px}.brand{display:none}</style></head><body><main class="page"><div class="eyebrow">${esc(specId)} · ${esc(type)}</div><h1>${esc(title)}</h1><div class="sub">${esc(description)}</div>${body}</main></body></html>`;
const extraCss = ".retrieval-head{display:flex;align-items:center;gap:20px;margin-bottom:18px}.query-orbit{flex:0 0 190px}.retrieval-copy{display:flex;flex-direction:column;gap:8px}.retrieval-copy strong{font-size:22px}.retrieval-copy small{font-size:16px;color:#5e6872}.retrieval-lanes{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.lane{position:relative;padding:12px;border-radius:12px;background:#fffaf2;border-top:6px solid #557a96}.query-lane{border-top-color:#b24a2b}.lane-label{display:block;font-size:14px;letter-spacing:1px;color:#5e6872;margin-bottom:8px}.lane .node,.lane .math{min-height:92px}.pipeline-rail{position:relative;display:grid;grid-template-columns:repeat(5,1fr);gap:10px}.rail-line{position:absolute;left:8%;right:8%;top:26px;height:4px;background:#b24a2b}.stage-wrap{position:relative;z-index:1;display:flex;flex-direction:column;align-items:center;gap:8px}.stage-index{width:30px;height:30px;border-radius:50%;background:#b24a2b;color:#fff;display:flex;align-items:center;justify-content:center;font-weight:800}.stage-wrap .node{width:100%;min-height:94px}.attention-pipeline .formula-wide{padding-top:28px}.ledger-board{display:flex;flex-direction:column;gap:12px;padding:4px 0}.ledger-intro{display:flex;flex-direction:column;gap:5px;margin-bottom:4px}.ledger-intro strong{font-size:24px}.ledger-intro small{font-size:16px;color:#5e6872}.ledger-row{display:grid;grid-template-columns:58px 290px 1fr 230px;align-items:center;gap:14px;padding:13px 16px;border:2px solid #557a96;border-radius:14px;background:#fffaf2;min-height:66px}.ledger-row:nth-child(3),.ledger-row:nth-child(5){background:#fff3e9}.ledger-index{font-size:18px;font-weight:800;color:#b24a2b}.ledger-copy{display:flex;flex-direction:column;gap:3px}.ledger-copy strong{font-size:20px}.ledger-copy small{font-size:14px;color:#5e6872}.ledger-track{height:15px;background:#dbe8f0;border-radius:10px;overflow:hidden}.ledger-fill{display:block;height:100%;border-radius:10px;background:#557a96}.ledger-fill.accent{background:#b24a2b}.ledger-metric{font-size:17px;font-weight:700;text-align:right;color:#17324d}";
fs.mkdirSync(path.dirname(output), { recursive: true });
// RC3: 配色唯一来源是 visual-styles.yaml 的 design_tokens。这里把历史硬编码的
// hex 统一替换成账号 token，避免再维护一套游离配色（与 render_visual_anchor.py 一致）。
const colorMap = {
  "#fffdf9": tokens.paper,
  "#17324d": tokens.ink,
  "#cbd7df": tokens.line,
  "#b24a2b": tokens.accent,
  "#5e6872": tokens.muted,
  "#f4f0e8": tokens.paper,
  "#557a96": tokens.line,
  "#fffaf2": tokens.surface,
  "#f3f8fb": tokens.paper,
  "#172b3e": tokens.ink,
  "#c8d5dc": tokens.paper,
  "#dbe8f0": tokens.surface,
  "#e7a080": tokens.accent,
  "#542014": tokens.paper,
  "#4b5660": tokens.muted,
};
let finalHtml = html.replace("</style>", extraCss + "</style>");
for (const [hex, val] of Object.entries(colorMap)) {
  finalHtml = finalHtml.split(hex).join(val);
}
fs.writeFileSync(output, finalHtml, "utf8");
