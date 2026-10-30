#!/usr/bin/env python3
"""Render a card-deck visual anchor for WeChat (Enhancement #5).

WeChat strips JavaScript, so this renderer produces:
1. A deterministic SVG that visually groups 3-5 cards into a single anchor
   image (one visual slot, multiple information chunks).
2. A static HTML fallback where every card is readable inline as plain text,
   satisfying the wechat-svg-interactive Skill's "no content hidden behind
   interaction" rule.

The PNG is what gets inserted into the article; the SVG source is kept for
future editing.
"""

from __future__ import annotations

import argparse
import html
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from render_visual_anchor import chrome_path, load_design_tokens  # noqa: E402

CARD_W = 320
CARD_H = 420
MARGIN_X = 40
CANVAS_W = 1200
CANVAS_H = 560



def _default_account() -> str:
    """Return the fixed account id of this split workflow target."""
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
        from account_context import ACCOUNT_ID
        return ACCOUNT_ID
    except Exception as exc:
        raise RuntimeError("workflow identity unavailable") from exc

def esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def wrap_text(text: str, max_chars: int = 22) -> list[str]:
    out: list[str] = []
    for word in text.split():
        if out and len(out[-1]) + len(word) + 1 <= max_chars:
            out[-1] += " " + word
        else:
            out.append(word)
    return out


def build_svg(title: str, description: str, cards: list[dict], tokens: dict) -> str:
    n = max(1, min(len(cards), 5))
    paper = tokens["paper"]
    surface = tokens["surface"]
    ink = tokens["ink"]
    muted = tokens["muted"]
    accent = tokens["accent"]
    line = tokens["line"]

    total_width = n * CARD_W + (n - 1) * MARGIN_X
    start_x = (CANVAS_W - total_width) // 2
    start_y = 140

    rects = []
    labels = []
    bullets = []
    for i, card in enumerate(cards[:n]):
        x = start_x + i * (CARD_W + MARGIN_X)
        y = start_y + i * 12  # slight cascade
        shadow_x = x + 6
        shadow_y = y + 6
        rects.append(f'<rect x="{shadow_x}" y="{shadow_y}" width="{CARD_W}" height="{CARD_H}" rx="16" fill="{ink}" opacity="0.08"/>')
        rects.append(f'<rect x="{x}" y="{y}" width="{CARD_W}" height="{CARD_H}" rx="16" fill="{surface}" stroke="{line}" stroke-width="2"/>')
        # top accent bar
        bar_h = 6
        rects.append(f'<rect x="{x}" y="{y}" width="{CARD_W}" height="{bar_h}" rx="16" fill="{accent}"/>')
        rects.append(f'<rect x="{x}" y="{y + bar_h}" width="{CARD_W}" height="16" fill="{accent}"/>')
        # number badge
        badge_r = 14
        badge_cx = x + CARD_W - 30
        badge_cy = y + 34
        labels.append(f'<circle cx="{badge_cx}" cy="{badge_cy}" r="{badge_r}" fill="{accent}"/>')
        labels.append(f'<text x="{badge_cx}" y="{badge_cy + 5}" text-anchor="middle" fill="{surface}" font-size="14" font-weight="700">{i + 1}</text>')
        # card title
        labels.append(f'<text x="{x + 22}" y="{y + 54}" fill="{ink}" font-size="20" font-weight="700">{esc(card.get("title") or f"卡片 {i+1}")}</text>')
        # bullets
        items = card.get("items") or card.get("bullets") or []
        if not items and card.get("body"):
            items = [line.strip("- ") for line in str(card.get("body")).split("\n") if line.strip()]
        by = y + 90
        for item in items[:6]:
            for line in wrap_text(str(item), 20):
                bullets.append(f'<text x="{x + 36}" y="{by}" fill="{muted}" font-size="16">{esc(line)}</text>')
                by += 24
            by += 8

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{CANVAS_H}" viewBox="0 0 {CANVAS_W} {CANVAS_H}">
  <rect width="{CANVAS_W}" height="{CANVAS_H}" fill="{paper}"/>
  <text x="{CANVAS_W // 2}" y="54" text-anchor="middle" fill="{accent}" font-size="16" font-weight="700" letter-spacing="2">CARD DECK · {esc(title)[:30]}</text>
  <text x="{CANVAS_W // 2}" y="90" text-anchor="middle" fill="{ink}" font-size="28" font-weight="700">{esc(title)}</text>
  <text x="{CANVAS_W // 2}" y="118" text-anchor="middle" fill="{muted}" font-size="18">{esc(description)}</text>
  {''.join(rects)}
  {''.join(labels)}
  {''.join(bullets)}
</svg>"""


def build_fallback_html(title: str, cards: list[dict], tokens: dict) -> str:
    sections = "\n".join(
        f"<section style='margin:16px 0;padding:16px;border-radius:12px;background:{tokens['surface']};border:1px solid {tokens['line']}40;'>"
        f"<h3 style='margin:0 0 10px;color:{tokens['accent']}'>卡片 {i+1}：{esc(c.get('title') or '')}</h3>"
        f"<ul style='margin:0;padding-left:20px;color:{tokens['muted']};line-height:1.7'>"
        f"{''.join(f'<li>{esc(line)}</li>' for line in (c.get('items') or c.get('bullets') or []))}</ul></section>"
        for i, c in enumerate(cards)
    )
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"></head>
<body style="font-family:'PingFang SC','Microsoft YaHei',sans-serif;background:{tokens['paper']};padding:24px;">
  <h2 style="color:{tokens['ink']}">{esc(title)}</h2>
  <p style="color:{tokens['muted']}">以下内容为交互卡片的静态降级，无需点击即可完整阅读。</p>
  {sections}
</body></html>"""


def _spec_unit(spec_path: Path, spec_id: str) -> dict:
    data = json.loads(spec_path.read_text(encoding="utf-8"))
    units = data.get("units") if isinstance(data.get("units"), list) else []
    for unit in units:
        if str(unit.get("id")) == spec_id:
            return unit
    raise SystemExit(f"visual contract unit not found: {spec_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Render an interactive card deck visual anchor.")
    parser.add_argument("--account", default=_default_account(), choices=(_default_account(),))
    parser.add_argument("--title", default="要点卡组")
    parser.add_argument("--description", default="一个视觉位承载多张信息卡")
    parser.add_argument("--cards", default="", help="JSON list of {title, items[]} cards")
    parser.add_argument("--output", default="", help="Output PNG path (optional)")
    parser.add_argument("--svg-output", default="", help="Keep SVG source")
    parser.add_argument("--html-output", default="", help="Keep static HTML fallback")
    parser.add_argument("--spec", default="", help="visual-contract.json path")
    parser.add_argument("--spec-id", default="", help="unit id inside spec")
    args = parser.parse_args()

    title = args.title
    description = args.description
    cards: list[dict] = []
    if args.cards:
        try:
            cards = json.loads(args.cards)
        except json.JSONDecodeError:
            pass
    if args.spec and args.spec_id:
        unit = _spec_unit(Path(args.spec).resolve(), args.spec_id)
        title = str(unit.get("section_heading") or unit.get("section") or args.title)
        description = str(unit.get("viewer_job") or args.description)
        raw_cards = unit.get("cards") or unit.get("card_deck") or []
        if raw_cards:
            cards = raw_cards
    if not cards:
        cards = [{"title": "卡片 1", "items": ["要点 A", "要点 B"]}]

    tokens = load_design_tokens(args.account)
    svg = build_svg(title, description, cards, tokens)

    svg_path = Path(args.svg_output).resolve() if args.svg_output else None
    output = Path(args.output).resolve() if args.output else None
    if svg_path:
        svg_path.parent.mkdir(parents=True, exist_ok=True)
        svg_path.write_text(svg, encoding="utf-8")
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)

    chrome = chrome_path()
    if output:
        if not chrome:
            print("CARD DECK BLOCKED: 未找到 Chrome", flush=True)
            return 1
        source = svg_path or output.with_suffix(".svg")
        if not svg_path:
            source.write_text(svg, encoding="utf-8")
        command = [str(chrome), "--headless", "--disable-gpu", "--no-sandbox", f"--window-size={CANVAS_W},{CANVAS_H}", f"--screenshot={output}", source.as_uri()]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45)
        if result.returncode != 0 or not output.is_file() or output.stat().st_size < 1024:
            print("CARD DECK BLOCKED: Chrome 栅格化失败", flush=True)
            return 1

    if args.html_output:
        html_path = Path(args.html_output).resolve()
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(build_fallback_html(title, cards, tokens), encoding="utf-8")

    print(json.dumps({
        "role": "interactive-card-deck",
        "account": args.account,
        "png": str(output) if output else "",
        "svg": str(svg_path) if svg_path else "",
        "cards": len(cards),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
