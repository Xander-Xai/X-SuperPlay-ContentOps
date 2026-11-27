"""Reusable Graphic Template Library & Platform-Native Article Generators (T07).

Replaces ad-hoc HTML writing with six structurally distinct, account-DNA-driven
editorial templates + native platform adapters (WeChat GZH HTML, Zhihu Markdown,
CSDN Markdown, X Post/Thread).

Design principles:
- Strictly light account palettes from ``config/design/design-tokens.json``
  (FI: #E9EDEF / #F9FBFA / #157F8B; 1024: #F4F2ED / #FFFFFF / #087FA6).
- Six genuinely distinct information architectures — NOT one card with swapped
  colors:
    1. ``tech_cover``             — Asymmetric editorial cover (2.35:1 / 16:9 / 3:4 / 9:16)
    2. ``mechanism_architecture`` — SVG vector system architecture & flow diagram
    3. ``code_annotated``         — Light github-light code excerpt + line callouts
    4. ``measured_comparison``    — Side-by-side real test/selection matrix & bars
    5. ``step_workflow_timeline`` — Vertical numbered engineering playbook + pitfall
    6. ``case_teardown_article``  — Multi-platform native long-form article pack
- Xiaohongshu is strictly VIDEO-only in ContentOps and refused here.
- Every output passes ``design_system.lint_html_design`` and stays
  ``production_ready: false`` / ``publish_authorized: false``.
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .design_system import account_tokens, css_variables_block, lint_html_design

CATALOG_SCHEMA = "contentops.graphic-template-catalog/v1"

TEMPLATE_CATALOG: Sequence[Dict[str, Any]] = (
    {
        "template_id": "tech_cover",
        "name": "Editorial Tech / Teardown Cover",
        "accounts": ["x-superplay-future-intelligence", "x-superplay-1024"],
        "platforms": ["wechat_article", "zhihu", "csdn", "x"],
        "content_types": ["tech_news_cover", "tutorial_cover", "opinion_cover"],
        "native_sizes": {"wechat_cover": [900, 383], "wide_16_9": [1600, 900], "card_3_4": [1080, 1440]},
        "capacity": {"kicker_max": 28, "title_max": 26, "subtitle_max": 48},
    },
    {
        "template_id": "mechanism_architecture",
        "name": "System Architecture & Data-Flow Diagram",
        "accounts": ["x-superplay-future-intelligence", "x-superplay-1024"],
        "platforms": ["wechat_article", "zhihu", "csdn", "x"],
        "content_types": ["principle_explainer", "architecture_flow"],
        "native_sizes": {"wide_16_9": [1600, 900], "card_3_4": [1080, 1440]},
        "capacity": {"nodes_min": 3, "nodes_max": 5, "title_max": 32},
    },
    {
        "template_id": "code_annotated",
        "name": "Focused Code Excerpt & Engineering Callouts",
        "accounts": ["x-superplay-future-intelligence", "x-superplay-1024"],
        "platforms": ["wechat_article", "zhihu", "csdn"],
        "content_types": ["code_walkthrough", "bug_root_cause"],
        "native_sizes": {"wide_16_9": [1600, 900], "card_3_4": [1080, 1440]},
        "capacity": {"code_lines_max": 12, "callouts_max": 3},
    },
    {
        "template_id": "measured_comparison",
        "name": "Measured Test / Selection Comparison Matrix",
        "accounts": ["x-superplay-future-intelligence", "x-superplay-1024"],
        "platforms": ["wechat_article", "zhihu", "csdn", "x"],
        "content_types": ["measured_comparison", "tech_selection", "cost_limits"],
        "native_sizes": {"wide_16_9": [1600, 900], "card_3_4": [1080, 1440]},
        "capacity": {"rows_max": 6, "metrics_max": 4},
    },
    {
        "template_id": "step_workflow_timeline",
        "name": "Step-by-Step Playbook & Gotcha Rail",
        "accounts": ["x-superplay-future-intelligence", "x-superplay-1024"],
        "platforms": ["wechat_article", "zhihu", "csdn"],
        "content_types": ["software_steps", "troubleshooting", "timeline"],
        "native_sizes": {"card_3_4": [1080, 1440], "wide_16_9": [1600, 900]},
        "capacity": {"steps_max": 5},
    },
    {
        "template_id": "case_teardown_article",
        "name": "Platform-Native Long-Form Article Pack (GZH HTML + Zhihu/CSDN/X MD)",
        "accounts": ["x-superplay-future-intelligence", "x-superplay-1024"],
        "platforms": ["wechat_article", "zhihu", "csdn", "x"],
        "content_types": ["long_article", "case_teardown", "tutorial_article"],
        "native_sizes": {"wechat_html": [677, 0]},
        "capacity": {"sections_min": 3, "sections_max": 8},
    },
)

SUPPORTED_GRAPHIC_PLATFORMS = {"wechat_article", "zhihu", "csdn", "x"}


def _e(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _page_shell(*, title: str, width: int, height: int, tokens: Dict[str, Any], extra_css: str, body: str) -> str:
    css_vars = css_variables_block(tokens)
    return (
        "<!doctype html>\n"
        '<html lang="zh-CN">\n<head>\n<meta charset="utf-8">\n'
        f"<title>{_e(title)}</title>\n<style>\n"
        f"{css_vars}"
        "* { box-sizing: border-box; }\n"
        f"html, body {{ margin: 0; padding: 0; width: {width}px; height: {height}px; overflow: hidden; background: var(--bg); color: var(--ink); font-family: var(--font-sans); }}\n"
        f".canvas {{ position: relative; width: {width}px; height: {height}px; background: var(--bg); color: var(--ink); padding: var(--margin); display: flex; flex-direction: column; justify-content: space-between; overflow: hidden; }}\n"
        ".eyebrow { font: 700 18px/1.2 var(--font-mono); letter-spacing: 0.14em; text-transform: uppercase; color: var(--accent); display: flex; align-items: center; gap: 10px; }\n"
        ".eyebrow .dot { width: 9px; height: 9px; border-radius: 50%; background: var(--accent); display: inline-block; }\n"
        ".footer-bar { display: flex; justify-content: space-between; align-items: center; padding-top: 18px; border-top: 1px solid var(--border); font: 500 17px/1.3 var(--font-mono); color: var(--sub); }\n"
        ".brand-pill { background: var(--brand-dark); color: #F9FBFA; padding: 6px 14px; border-radius: 6px; font: 700 15px/1 var(--font-mono); letter-spacing: 0.08em; }\n"
        ".brand-pill b { color: var(--brand-cyan); }\n"
        f"{extra_css}\n"
        "</style>\n</head>\n<body>\n"
        f'<div class="canvas" data-composition-id="card" data-width="{width}" data-height="{height}">\n'
        f"{body}\n"
        "</div>\n</body>\n</html>\n"
    )


def render_tech_cover(tokens: Dict[str, Any], data: Mapping[str, Any], *, width: int = 1600, height: int = 900) -> str:
    """Template 1: Asymmetric Editorial Cover with architectural SVG wireframe & >=35% whitespace."""
    kicker = _e(data.get("kicker") or "ENGINEERING TEARDOWN")
    title = _e(data.get("title") or "")
    subtitle = _e(data.get("subtitle") or "")
    tag = _e(data.get("conflict_tag") or data.get("badge") or "")
    source = _e(data.get("source_note") or "")
    account_label = _e(tokens.get("label") or "X-SuperPlay")
    is_compact = height <= 450
    title_px = 46 if is_compact else (64 if width >= 1400 else 60)
    pad = 36 if is_compact else 64

    extra_css = f"""
.canvas {{ padding: {pad}px; }}
.cover-grid {{ display: grid; grid-template-columns: {('1.45fr 0.55fr' if width > height else '1fr')}; gap: {28 if is_compact else 48}px; align-items: center; flex: 1; }}
.cover-main {{ display: flex; flex-direction: column; gap: {14 if is_compact else 26}px; }}
.cover-title {{ margin: 0; font-family: var(--font-display); font-size: {title_px}px; line-height: 1.16; font-weight: 800; letter-spacing: -0.02em; color: var(--ink); text-wrap: balance; }}
.cover-sub {{ margin: 0; font-size: {20 if is_compact else 28}px; line-height: 1.5; color: var(--sub); max-width: 92%; }}
.conflict-pill {{ display: inline-flex; align-items: center; gap: 10px; width: fit-content; background: var(--surface); border: 1px solid var(--border); border-left: 5px solid var(--accent); padding: {8 if is_compact else 12}px {16 if is_compact else 20}px; border-radius: 6px; font-size: {16 if is_compact else 22}px; font-weight: 600; color: var(--ink); }}
.wireframe-box {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: {16 if is_compact else 28}px; display: flex; flex-direction: column; gap: 12px; }}
.wireframe-box svg {{ width: 100%; height: auto; display: block; }}
.wf-cap {{ font: 600 {12 if is_compact else 15}px/1.3 var(--font-mono); color: var(--sub); letter-spacing: 0.06em; }}
"""
    svg_nodes = data.get("wireframe_labels") or ["SOURCE", "VERIFY", "COMPOSE", "REVIEW"]
    n0, n1, n2, n3 = (_e(svg_nodes[i] if i < len(svg_nodes) else "") for i in range(4))
    wireframe = (
        '<div class="wireframe-box">'
        '<svg viewBox="0 0 360 240" fill="none" xmlns="http://www.w3.org/2000/svg">'
        '<rect x="14" y="18" width="144" height="58" rx="8" fill="var(--bg)" stroke="var(--accent)" stroke-width="2.2"/>'
        f'<text x="86" y="53" text-anchor="middle" fill="var(--ink)" font-family="monospace" font-size="14" font-weight="700">{n0}</text>'
        '<line x1="158" y1="47" x2="202" y2="47" stroke="var(--accent)" stroke-width="2.2"/>'
        '<polygon points="202,42 212,47 202,52" fill="var(--accent)"/>'
        '<rect x="212" y="18" width="134" height="58" rx="8" fill="var(--bg)" stroke="var(--border)" stroke-width="2"/>'
        f'<text x="279" y="53" text-anchor="middle" fill="var(--ink)" font-family="monospace" font-size="14" font-weight="700">{n1}</text>'
        '<line x1="279" y1="76" x2="279" y2="122" stroke="var(--sub)" stroke-width="2" stroke-dasharray="4 4"/>'
        '<rect x="212" y="128" width="134" height="58" rx="8" fill="var(--accent-soft)" stroke="var(--accent)" stroke-width="2.2"/>'
        f'<text x="279" y="163" text-anchor="middle" fill="var(--accent)" font-family="monospace" font-size="14" font-weight="700">{n2}</text>'
        '<line x1="212" y1="157" x2="168" y2="157" stroke="var(--accent)" stroke-width="2.2"/>'
        '<polygon points="168,152 158,157 168,162" fill="var(--accent)"/>'
        '<rect x="14" y="128" width="144" height="58" rx="8" fill="var(--surface-alt)" stroke="var(--ink)" stroke-width="2"/>'
        f'<text x="86" y="163" text-anchor="middle" fill="var(--ink)" font-family="monospace" font-size="14" font-weight="700">{n3}</text>'
        '</svg>'
        f'<div class="wf-cap">SCHEMATIC · {_e(tokens.get("variant"))}</div>'
        '</div>'
    )
    pill_html = f'<div class="conflict-pill">{tag}</div>' if tag else ""
    body = (
        f'<div class="eyebrow"><span class="dot"></span>{kicker}</div>'
        '<div class="cover-grid">'
        f'  <div class="cover-main"><h1 class="cover-title">{title}</h1><p class="cover-sub">{subtitle}</p>{pill_html}</div>'
        f'  {wireframe}'
        '</div>'
        f'<div class="footer-bar"><span>{source}</span><span class="brand-pill"><b>X</b> · {account_label}</span></div>'
    )
    return _page_shell(title=str(data.get("title") or "Cover"), width=width, height=height, tokens=tokens, extra_css=extra_css, body=body)


def render_mechanism_architecture(tokens: Dict[str, Any], data: Mapping[str, Any], *, width: int = 1600, height: int = 900) -> str:
    """Template 2: True Vector System Architecture & Directional Flow Diagram."""
    title = _e(data.get("title") or "")
    kicker = _e(data.get("kicker") or "ARCHITECTURE & DATA FLOW")
    nodes = list(data.get("nodes") or [])[:5]
    boundary = _e(data.get("boundary_note") or "")
    source = _e(data.get("source_note") or "EXPLANATORY ARCHITECTURE · SOURCE-BOUND")
    account_label = _e(tokens.get("label") or "X-SuperPlay")

    horizontal = width >= height
    extra_css = f"""
.hdr {{ margin-bottom: 24px; }}
.hdr h1 {{ margin: 12px 0 0; font-size: {44 if horizontal else 48}px; line-height: 1.18; font-weight: 800; }}
.arch-stage {{ flex: 1; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 34px; display: flex; flex-direction: {'row' if horizontal else 'column'}; align-items: stretch; justify-content: space-between; gap: 16px; }}
.arch-node {{ flex: 1; background: var(--bg); border: 1.5px solid var(--border); border-top: 6px solid var(--accent); border-radius: 10px; padding: 22px 20px; display: flex; flex-direction: column; justify-content: space-between; gap: 10px; }}
.arch-node.alert {{ border-top-color: var(--problem); background: var(--problem-soft); }}
.arch-idx {{ font: 700 16px/1 var(--font-mono); color: var(--accent); letter-spacing: 0.1em; }}
.arch-node.alert .arch-idx {{ color: var(--problem); }}
.arch-title {{ font-size: {24 if horizontal else 28}px; font-weight: 800; color: var(--ink); line-height: 1.25; }}
.arch-desc {{ font-size: {18 if horizontal else 21}px; color: var(--sub); line-height: 1.5; }}
.arch-io {{ font: 600 15px/1.3 var(--font-mono); color: var(--ink); background: var(--surface); padding: 8px 10px; border-radius: 6px; border: 1px solid var(--border); }}
.arch-arrow {{ display: flex; align-items: center; justify-content: center; flex: 0 0 28px; color: var(--accent); font-size: 28px; font-weight: 800; }}
.boundary-strip {{ margin-top: 20px; padding: 16px 22px; background: var(--surface); border: 1px solid var(--border); border-left: 6px solid var(--problem); border-radius: 8px; font-size: 20px; line-height: 1.45; color: var(--ink); }}
.boundary-strip b {{ color: var(--problem); font-family: var(--font-mono); margin-right: 10px; }}
"""
    parts: List[str] = []
    arrow = "→" if horizontal else "↓"
    for idx, node in enumerate(nodes, start=1):
        cls = "arch-node alert" if node.get("status") == "failure" else "arch-node"
        io_html = f'<div class="arch-io">{_e(node.get("artifact"))}</div>' if node.get("artifact") else ""
        parts.append(
            f'<div class="{cls}">'
            f'  <div><div class="arch-idx">STEP 0{idx}</div><div class="arch-title">{_e(node.get("label"))}</div></div>'
            f'  <div class="arch-desc">{_e(node.get("detail"))}</div>'
            f'  {io_html}'
            '</div>'
        )
        if idx < len(nodes):
            parts.append(f'<div class="arch-arrow">{arrow}</div>')

    boundary_html = f'<div class="boundary-strip"><b>BOUNDARY</b>{boundary}</div>' if boundary else ""
    body = (
        f'<div class="hdr"><div class="eyebrow"><span class="dot"></span>{kicker}</div><h1>{title}</h1></div>'
        f'<div class="arch-stage">{"".join(parts)}</div>'
        f'{boundary_html}'
        f'<div class="footer-bar"><span>{source}</span><span class="brand-pill"><b>X</b> · {account_label}</span></div>'
    )
    return _page_shell(title=str(data.get("title") or "Architecture"), width=width, height=height, tokens=tokens, extra_css=extra_css, body=body)


def render_code_annotated(tokens: Dict[str, Any], data: Mapping[str, Any], *, width: int = 1600, height: int = 900) -> str:
    """Template 3: Focused Light-Theme Code Excerpt + Numbered Engineering Callouts."""
    title = _e(data.get("title") or "")
    kicker = _e(data.get("kicker") or "KEY CODE EXCERPT")
    file_path = _e(data.get("file_path") or "source.py")
    start_line = int(data.get("start_line") or 1)
    highlight_lines = {int(x) for x in (data.get("highlight_lines") or [])}
    code_lines = list(data.get("code_lines") or [])[:12]
    callouts = list(data.get("callouts") or [])[:3]
    source = _e(data.get("source_note") or f"VERBATIM EXCERPT · {file_path}")
    account_label = _e(tokens.get("label") or "X-SuperPlay")

    horizontal = width >= height
    extra_css = f"""
.hdr {{ margin-bottom: 22px; }}
.hdr h1 {{ margin: 10px 0 0; font-size: {42 if horizontal else 46}px; line-height: 1.18; font-weight: 800; }}
.split {{ flex: 1; display: grid; grid-template-columns: {('1.35fr 0.85fr' if horizontal else '1fr')}; gap: 28px; min-height: 0; }}
.code-win {{ background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; display: flex; flex-direction: column; }}
.code-bar {{ background: var(--surface-alt); padding: 14px 20px; border-bottom: 1px solid var(--border); font: 600 17px/1 var(--font-mono); color: var(--sub); display: flex; justify-content: space-between; }}
.code-body {{ padding: 18px 0; flex: 1; overflow: hidden; }}
.cl {{ display: flex; gap: 16px; padding: 6px 20px; font: 500 {19 if horizontal else 20}px/1.45 var(--font-mono); color: var(--ink); border-left: 5px solid transparent; }}
.cl.hl {{ background: var(--accent-soft); border-left-color: var(--accent); font-weight: 700; }}
.ln {{ color: var(--sub); min-width: 46px; text-align: right; user-select: none; }}
.cd {{ white-space: pre-wrap; overflow-wrap: break-word; word-break: normal; }}
.callouts {{ display: flex; flex-direction: column; gap: 16px; justify-content: center; }}
.co {{ background: var(--surface); border: 1px solid var(--border); border-left: 5px solid var(--accent); border-radius: 10px; padding: 20px 22px; }}
.co.problem {{ border-left-color: var(--problem); background: var(--problem-soft); }}
.co-tag {{ font: 700 15px/1 var(--font-mono); color: var(--accent); margin-bottom: 8px; letter-spacing: 0.08em; }}
.co.problem .co-tag {{ color: var(--problem); }}
.co-title {{ font-size: 22px; font-weight: 800; color: var(--ink); margin-bottom: 6px; }}
.co-body {{ font-size: 19px; line-height: 1.48; color: var(--sub); }}
"""
    code_html = []
    for idx, raw in enumerate(code_lines):
        lineno = start_line + idx
        cls = "cl hl" if lineno in highlight_lines else "cl"
        code_html.append(f'<div class="{cls}"><span class="ln">{lineno:03d}</span><span class="cd">{_e(raw)}</span></div>')

    co_html = []
    for idx, co in enumerate(callouts, start=1):
        cls = "co problem" if co.get("kind") == "problem" else "co"
        co_html.append(
            f'<div class="{cls}">'
            f'<div class="co-tag">POINT 0{idx} · {_e(co.get("line_ref") or "")}</div>'
            f'<div class="co-title">{_e(co.get("title"))}</div>'
            f'<div class="co-body">{_e(co.get("detail"))}</div>'
            '</div>'
        )

    body = (
        f'<div class="hdr"><div class="eyebrow"><span class="dot"></span>{kicker}</div><h1>{title}</h1></div>'
        '<div class="split">'
        f'  <div class="code-win"><div class="code-bar"><span>{file_path}</span><span>github-light · FOCUSED</span></div><div class="code-body">{"".join(code_html)}</div></div>'
        f'  <div class="callouts">{"".join(co_html)}</div>'
        '</div>'
        f'<div class="footer-bar"><span>{source}</span><span class="brand-pill"><b>X</b> · {account_label}</span></div>'
    )
    return _page_shell(title=str(data.get("title") or "Code"), width=width, height=height, tokens=tokens, extra_css=extra_css, body=body)


def render_measured_comparison(tokens: Dict[str, Any], data: Mapping[str, Any], *, width: int = 1600, height: int = 900) -> str:
    """Template 4: Real Measured Comparison Matrix & Status Bars."""
    title = _e(data.get("title") or "")
    kicker = _e(data.get("kicker") or "MEASURED COMPARISON")
    columns = list(data.get("columns") or ["项目", "实测结果", "状态", "边界说明"])
    rows = list(data.get("rows") or [])[:6]
    metrics = list(data.get("metrics") or [])[:4]
    verdict = _e(data.get("verdict") or "")
    source = _e(data.get("source_note") or "")
    account_label = _e(tokens.get("label") or "X-SuperPlay")

    extra_css = """
.hdr { margin-bottom: 20px; }
.hdr h1 { margin: 10px 0 0; font-size: 44px; line-height: 1.18; font-weight: 800; }
.metric-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 18px; margin-bottom: 22px; }
.m-card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 20px 22px; }
.m-label { font: 600 15px/1.2 var(--font-mono); color: var(--sub); text-transform: uppercase; letter-spacing: 0.08em; }
.m-val { font-size: 46px; font-weight: 900; color: var(--accent); line-height: 1.15; margin: 8px 0 4px; font-variant-numeric: tabular-nums; }
.m-val.bad { color: var(--problem); }
.m-val.good { color: var(--success); }
.m-sub { font-size: 17px; color: var(--sub); }
.tbl-wrap { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
table { width: 100%; border-collapse: collapse; font-size: 20px; }
th { text-align: left; padding: 16px 20px; background: var(--surface-alt); color: var(--sub); font: 700 16px/1.2 var(--font-mono); border-bottom: 1px solid var(--border); }
td { padding: 16px 20px; border-bottom: 1px solid var(--border); color: var(--ink); line-height: 1.4; }
tr:last-child td { border-bottom: none; }
.pill { display: inline-block; padding: 4px 12px; border-radius: 999px; font: 700 15px/1.2 var(--font-mono); }
.pill.pass { background: var(--success-soft); color: var(--success); }
.pill.fail { background: var(--problem-soft); color: var(--problem); }
.pill.warn { background: var(--accent-soft); color: var(--accent); }
.verdict { margin-top: 18px; padding: 16px 22px; background: var(--surface); border: 1px solid var(--border); border-left: 6px solid var(--accent); border-radius: 8px; font-size: 21px; font-weight: 600; }
"""
    m_html = []
    for m in metrics:
        tone = "bad" if m.get("tone") == "problem" else ("good" if m.get("tone") == "success" else "")
        m_html.append(
            f'<div class="m-card"><div class="m-label">{_e(m.get("label"))}</div>'
            f'<div class="m-val {tone}">{_e(m.get("value"))}</div>'
            f'<div class="m-sub">{_e(m.get("note"))}</div></div>'
        )
    th_html = "".join(f"<th>{_e(c)}</th>" for c in columns)
    tr_html = []
    for r in rows:
        st = str(r.get("status") or "").upper()
        pcls = "pass" if st in ("PASS", "OK", "READY") else ("fail" if st in ("FAIL", "BLOCKED", "NO") else "warn")
        tr_html.append(
            "<tr>"
            f"<td><b>{_e(r.get('item'))}</b></td>"
            f"<td>{_e(r.get('measured'))}</td>"
            f'<td><span class="pill {pcls}">{_e(st or "INFO")}</span></td>'
            f"<td>{_e(r.get('boundary'))}</td>"
            "</tr>"
        )
    verdict_html = f'<div class="verdict">{verdict}</div>' if verdict else ""
    body = (
        f'<div class="hdr"><div class="eyebrow"><span class="dot"></span>{kicker}</div><h1>{title}</h1></div>'
        f'<div class="metric-row">{"".join(m_html)}</div>'
        f'<div class="tbl-wrap"><table><thead><tr>{th_html}</tr></thead><tbody>{"".join(tr_html)}</tbody></table></div>'
        f'{verdict_html}'
        f'<div class="footer-bar"><span>{source}</span><span class="brand-pill"><b>X</b> · {account_label}</span></div>'
    )
    return _page_shell(title=str(data.get("title") or "Comparison"), width=width, height=height, tokens=tokens, extra_css=extra_css, body=body)


def render_step_workflow_timeline(tokens: Dict[str, Any], data: Mapping[str, Any], *, width: int = 1080, height: int = 1440) -> str:
    """Template 5: Vertical Numbered Engineering Playbook with Command Boxes & Pitfall Callout."""
    title = _e(data.get("title") or "")
    kicker = _e(data.get("kicker") or "REPRODUCIBLE PLAYBOOK")
    steps = list(data.get("steps") or [])[:5]
    pitfall = _e(data.get("pitfall") or "")
    source = _e(data.get("source_note") or "")
    account_label = _e(tokens.get("label") or "X-SuperPlay")

    extra_css = """
.hdr { margin-bottom: 24px; }
.hdr h1 { margin: 12px 0 0; font-size: 46px; line-height: 1.2; font-weight: 800; }
.rail { flex: 1; display: flex; flex-direction: column; gap: 18px; position: relative; }
.step-row { display: grid; grid-template-columns: 76px 1fr; gap: 18px; align-items: stretch; }
.badge-col { display: flex; flex-direction: column; align-items: center; }
.step-num { width: 58px; height: 58px; border-radius: 50%; background: var(--accent); color: #FFFFFF; font: 800 24px/58px var(--font-mono); text-align: center; }
.step-line { width: 3px; flex: 1; background: var(--border); margin-top: 8px; }
.step-row:last-child .step-line { display: none; }
.step-card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 20px 24px; display: flex; flex-direction: column; gap: 8px; }
.step-title { font-size: 25px; font-weight: 800; color: var(--ink); }
.step-detail { font-size: 20px; line-height: 1.48; color: var(--sub); }
.step-cmd { font: 600 17px/1.35 var(--font-mono); background: var(--bg); color: var(--ink); padding: 10px 14px; border-radius: 6px; border: 1px solid var(--border); }
.pitfall { margin-top: 18px; padding: 18px 22px; background: var(--problem-soft); border: 1px solid var(--problem); border-radius: 10px; font-size: 20px; line-height: 1.48; color: var(--ink); }
.pitfall b { color: var(--problem); margin-right: 8px; }
"""
    rows_html = []
    for idx, st in enumerate(steps, start=1):
        cmd_html = f'<div class="step-cmd">$ {_e(st.get("command"))}</div>' if st.get("command") else ""
        rows_html.append(
            '<div class="step-row">'
            f'  <div class="badge-col"><div class="step-num">0{idx}</div><div class="step-line"></div></div>'
            f'  <div class="step-card"><div class="step-title">{_e(st.get("title"))}</div>'
            f'  <div class="step-detail">{_e(st.get("detail"))}</div>{cmd_html}</div>'
            '</div>'
        )
    pitfall_html = f'<div class="pitfall"><b>PITFALL / 边界提醒：</b>{pitfall}</div>' if pitfall else ""
    body = (
        f'<div class="hdr"><div class="eyebrow"><span class="dot"></span>{kicker}</div><h1>{title}</h1></div>'
        f'<div class="rail">{"".join(rows_html)}</div>'
        f'{pitfall_html}'
        f'<div class="footer-bar"><span>{source}</span><span class="brand-pill"><b>X</b> · {account_label}</span></div>'
    )
    return _page_shell(title=str(data.get("title") or "Playbook"), width=width, height=height, tokens=tokens, extra_css=extra_css, body=body)


def render_native_article_pack(tokens: Dict[str, Any], article: Mapping[str, Any], *, platforms: Sequence[str] = ("wechat_article", "zhihu", "csdn", "x")) -> Dict[str, str]:
    """Template 6: Generate platform-native WeChat GZH HTML, Zhihu MD, CSDN MD, and X Post."""
    for p in platforms:
        if "xiaohongshu" in p.casefold() or p.casefold() == "xhs":
            raise ValueError("Xiaohongshu is VIDEO-only in ContentOps; graphic article output is unsupported.")
        if p not in SUPPORTED_GRAPHIC_PLATFORMS:
            raise ValueError(f"Unsupported graphic platform: {p!r}")

    c = tokens["colors"]
    title = str(article.get("title") or "")
    lead = str(article.get("lead") or "")
    sections = list(article.get("sections") or [])
    sources = list(article.get("sources") or [])
    tags = list(article.get("tags") or [])
    code_lang = str(article.get("code_lang") or "bash")
    outputs: Dict[str, str] = {}

    if "wechat_article" in platforms:
        sec_blocks = [
            f'<section style="font-family:-apple-system,BlinkMacSystemFont,\'PingFang SC\',\'Noto Sans SC\',sans-serif;color:{c["ink"]};background:{c["surface"]};padding:18px 16px;line-height:1.78;font-size:16px;">',
            f'<section style="margin-bottom:20px;padding:16px 18px;background:{c["bg"]};border-left:4px solid {c["accent"]};border-radius:6px;">'
            f'<p style="margin:0;font-size:15px;color:{c["ink"]};"><span leaf="">{_e(lead)}</span></p></section>',
        ]
        for idx, sec in enumerate(sections, start=1):
            sec_blocks.append(
                f'<section style="margin:26px 0 12px;padding-bottom:6px;border-bottom:1px solid {c["border"]};">'
                f'<p style="margin:0;font-size:19px;font-weight:700;color:{c["ink"]};">'
                f'<span style="color:{c["accent"]};margin-right:8px;">0{idx}</span><span leaf="">{_e(sec.get("heading"))}</span></p></section>'
            )
            for para in sec.get("paragraphs") or []:
                sec_blocks.append(f'<p style="margin:12px 0;font-size:16px;color:{c["ink"]};"><span leaf="">{_e(para)}</span></p>')
            if sec.get("code"):
                sec_blocks.append(
                    f'<section style="margin:14px 0;padding:14px 16px;background:{c["bg"]};border:1px solid {c["border"]};border-radius:6px;font-family:Consolas,monospace;font-size:13px;line-height:1.55;color:{c["ink"]};white-space:pre-wrap;">'
                    f'<span leaf="">{_e(sec["code"])}</span></section>'
                )
            if sec.get("callout"):
                sec_blocks.append(
                    f'<section style="margin:14px 0;padding:12px 16px;background:{c["problem_soft"]};border-left:4px solid {c["problem"]};border-radius:4px;font-size:15px;color:{c["ink"]};">'
                    f'<span leaf="">{_e(sec["callout"])}</span></section>'
                )
        if sources:
            src_items = "".join(
                f'<p style="margin:6px 0;font-size:13px;color:{c["sub"]};"><span leaf="">[{i}] {_e(s)}</span></p>'
                for i, s in enumerate(sources, start=1)
            )
            sec_blocks.append(
                f'<section style="margin-top:28px;padding-top:14px;border-top:1px solid {c["border"]};">'
                f'<p style="margin:0 0 8px;font-size:14px;font-weight:700;color:{c["sub"]};"><span leaf="">可核对来源与边界</span></p>{src_items}</section>'
            )
        sec_blocks.append("</section>")
        outputs["wechat_article"] = "\n".join(sec_blocks) + "\n"

    if "zhihu" in platforms:
        zh_var = (article.get("platform_variants") or {}).get("zhihu") or {}
        zh_title = str(zh_var.get("title") or title)
        zh_lead = str(zh_var.get("lead") or lead)
        zh_sections = list(zh_var.get("sections") or sections)
        lead_prefix = "" if zh_lead.startswith(("直接说结论", "结论先行", "结论：")) else "**结论先行**："
        zh_lines = [f"# {zh_title}", "", f"> {lead_prefix}{zh_lead}", ""]
        for sec in zh_sections:
            zh_lines.append(f"## {sec.get('heading')}")
            zh_lines.append("")
            for para in sec.get("paragraphs") or []:
                zh_lines.append(str(para))
                zh_lines.append("")
            if sec.get("code"):
                zh_lines.extend([f"```{code_lang}", str(sec["code"]).rstrip(), "```", ""])
            if sec.get("callout"):
                co = str(sec["callout"])
                co_prefix = "" if "：" in co[:10] else "**边界与限制**："
                zh_lines.extend([f"> {co_prefix}{co}", ""])
        if sources:
            zh_lines.append("## 参考与可核对依据")
            zh_lines.append("")
            for idx, s in enumerate(sources, start=1):
                zh_lines.append(f"{idx}. {s}")
            zh_lines.append("")
        if tags:
            zh_lines.append(f"话题标签：{' / '.join(tags[:5])}")
        outputs["zhihu"] = "\n".join(zh_lines).rstrip() + "\n"

    if "csdn" in platforms:
        cs_var = (article.get("platform_variants") or {}).get("csdn") or {}
        cs_title = str(cs_var.get("title") or title)
        cs_lead = str(cs_var.get("lead") or lead)
        cs_sections = list(cs_var.get("sections") or sections)
        csdn_lines = [
            f"# {cs_title}",
            "",
            "## 问题背景与结论",
            "",
            cs_lead,
            "",
        ]
        for idx, sec in enumerate(cs_sections, start=1):
            csdn_lines.append(f"## {idx}. {sec.get('heading')}")
            csdn_lines.append("")
            for para in sec.get("paragraphs") or []:
                csdn_lines.append(str(para))
                csdn_lines.append("")
            if sec.get("code"):
                csdn_lines.extend([f"```{code_lang}", str(sec["code"]).rstrip(), "```", ""])
            if sec.get("callout"):
                co = str(sec["callout"])
                co_prefix = "" if "：" in co[:10] else "**避坑提醒**："
                csdn_lines.extend([f"{co_prefix}{co}", ""])
        if sources:
            csdn_lines.extend(["## 复现来源与参考", ""])
            for s in sources:
                csdn_lines.append(f"- {s}")
            csdn_lines.append("")
        if tags:
            csdn_lines.append(f"推荐标签：{', '.join(tags[:6])}")
        outputs["csdn"] = "\n".join(csdn_lines).rstrip() + "\n"

    if "x" in platforms:
        x_lines = [f"{title}", "", lead, ""]
        for idx, sec in enumerate(sections[:4], start=1):
            first_para = (sec.get("paragraphs") or [""])[0]
            x_lines.append(f"{idx}/ {sec.get('heading')}: {first_para}")
            x_lines.append("")
        if sources:
            x_lines.append(f"Source: {sources[0]}")
        outputs["x"] = "\n".join(x_lines).rstrip() + "\n"

    return outputs


def render_template_html(root: Path, *, template_id: str, account_slug: str, data: Mapping[str, Any], width: Optional[int] = None, height: Optional[int] = None) -> Dict[str, Any]:
    """Render one graphic card/cover template to HTML + run anti-slop design lint."""
    tokens = account_tokens(root, account_slug)
    renderers = {
        "tech_cover": (render_tech_cover, 1600, 900),
        "mechanism_architecture": (render_mechanism_architecture, 1600, 900),
        "code_annotated": (render_code_annotated, 1600, 900),
        "measured_comparison": (render_measured_comparison, 1600, 900),
        "step_workflow_timeline": (render_step_workflow_timeline, 1080, 1440),
    }
    if template_id not in renderers:
        raise ValueError(f"Unknown card/cover template_id {template_id!r}; expected one of {sorted(renderers)}")
    fn, def_w, def_h = renderers[template_id]
    w, h = int(width or def_w), int(height or def_h)
    rendered = fn(tokens, data, width=w, height=h)
    lint = lint_html_design(rendered)
    return {
        "template_id": template_id,
        "account_slug": account_slug,
        "width": w,
        "height": h,
        "html": rendered,
        "design_lint": lint,
        "production_ready": False,
        "publish_authorized": False,
    }
