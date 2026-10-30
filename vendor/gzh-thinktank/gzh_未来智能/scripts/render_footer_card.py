#!/usr/bin/env python3
"""Render the account follow card (brand + CTA + QR) for the article footer.

Enhancement #1 of the visual roadmap.  The original
``skills/wechat-card-qrcode/scripts/generate_card.py`` hardcoded a slate
palette and drew CJK text with Pillow's bitmap default font, which renders
Chinese as tofu boxes.  This production renderer instead:

* reads the palette from ``profiles/visual-styles.yaml`` design_tokens (RC3
  single source), so the card matches the account it belongs to;
* reads brand copy from ``profiles/<account>.yaml`` (display name, CTA,
  reply keyword, lead magnet) instead of CLI defaults;
* renders HTML and lets Chrome rasterize it, which is the same path the rest
  of the visual pipeline uses and is CJK-safe;
* degrades gracefully when the optional ``qrcode`` dependency is missing.

The card is a *footer* asset: it is deliberately excluded from the body visual
quota enforced by ``build_image_prompt_plan``.
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

FOOTER_ROLE = "footer-card"
CARD_WIDTH = 1080
CARD_HEIGHT = 420



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


def load_profile(account: str) -> dict:
    """Brand copy for the account, tolerant of a missing profile file."""
    path = ROOT / "profiles" / f"{account}.yaml"
    if not path.is_file():
        return {}
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def qr_matrix(url: str) -> list[list[bool]] | None:
    """Return the QR module matrix, or None when the encoder is unavailable.

    Only the matrix is needed -- it is drawn as inline SVG rects, so neither
    Pillow nor a raster QR image is required.
    """
    if not url:
        return None
    try:
        import qrcode  # type: ignore
    except Exception:
        return None
    try:
        qr = qrcode.QRCode(version=None, border=1, error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(url)
        qr.make(fit=True)
        return [[bool(cell) for cell in row] for row in qr.get_matrix()]
    except Exception:
        return None


def qr_svg(matrix: list[list[bool]] | None, size: int, ink: str, paper: str) -> str:
    """Inline SVG for the QR, or a dashed placeholder when encoding failed."""
    if not matrix:
        return (
            f'<svg width="{size}" height="{size}" viewBox="0 0 100 100" '
            f'xmlns="http://www.w3.org/2000/svg" role="img" aria-label="二维码占位">'
            f'<rect x="1" y="1" width="98" height="98" rx="6" fill="{paper}" '
            f'stroke="{ink}" stroke-width="2" stroke-dasharray="6 4" opacity="0.55"/>'
            f'<text x="50" y="46" text-anchor="middle" font-size="11" fill="{ink}" '
            f'opacity="0.75">扫码关注</text>'
            f'<text x="50" y="62" text-anchor="middle" font-size="8" fill="{ink}" '
            f'opacity="0.5">QR 待生成</text>'
            f"</svg>"
        )
    n = len(matrix)
    rects = []
    for y, row in enumerate(matrix):
        run_start = None
        for x in range(n + 1):
            filled = x < n and row[x]
            if filled and run_start is None:
                run_start = x
            elif not filled and run_start is not None:
                rects.append(f'<rect x="{run_start}" y="{y}" width="{x - run_start}" height="1"/>')
                run_start = None
    body = "".join(rects)
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 {n} {n}" '
        f'xmlns="http://www.w3.org/2000/svg" shape-rendering="crispEdges" role="img" aria-label="公众号二维码">'
        f'<rect width="{n}" height="{n}" fill="#FFFFFF"/>'
        f'<g fill="{ink}">{body}</g>'
        f"</svg>"
    )


def build_html(account: str, url: str, overrides: dict | None = None) -> str:
    tokens = load_design_tokens(account)
    profile = load_profile(account)
    over = overrides or {}

    name = over.get("name") or profile.get("public_display_name") or profile.get("display_name") or account
    slogan = over.get("slogan") or profile.get("primary_cta") or profile.get("role") or ""
    keyword = over.get("keyword") or profile.get("reply_keyword") or ""
    magnet = over.get("magnet") or profile.get("lead_magnet") or ""

    paper = tokens["paper"]
    surface = tokens["surface"]
    ink = tokens["ink"]
    muted = tokens["muted"]
    accent = tokens["accent"]
    line = tokens["line"]

    initial = esc(name[:1] or "A")
    keyword_pill = ""
    if keyword:
        keyword_pill = (
            f'<div class="pill"><span class="pill-k">回复</span>'
            f'<span class="pill-v">{esc(keyword)}</span>'
            f'<span class="pill-t">{esc(magnet or "获取本期资料")}</span></div>'
        )

    qr = qr_svg(qr_matrix(url), 168, ink, surface)

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html,body {{ width:{CARD_WIDTH}px; height:{CARD_HEIGHT}px; background:{paper};
    font-family:"PingFang SC","Microsoft YaHei","Noto Sans CJK SC",sans-serif; }}
  .card {{ width:{CARD_WIDTH - 80}px; height:{CARD_HEIGHT - 80}px; margin:40px;
    background:{surface}; border:2px solid {line}33; border-radius:20px;
    display:flex; align-items:center; padding:36px 40px; gap:36px;
    box-shadow:0 6px 24px {ink}0F; }}
  .brand {{ flex:1; min-width:0; }}
  .row {{ display:flex; align-items:center; gap:16px; margin-bottom:18px; }}
  .mark {{ width:64px; height:64px; border-radius:16px; background:{accent};
    color:{surface}; font-size:32px; font-weight:700; display:flex;
    align-items:center; justify-content:center; flex-shrink:0; }}
  .name {{ font-size:38px; font-weight:700; color:{ink}; letter-spacing:.5px; }}
  .slogan {{ font-size:21px; line-height:1.55; color:{muted}; margin-bottom:20px;
    display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }}
  .pill {{ display:inline-flex; align-items:center; gap:10px; padding:9px 18px;
    border-radius:999px; background:{accent}14; border:1px solid {accent}40; }}
  .pill-k {{ font-size:16px; color:{muted}; }}
  .pill-v {{ font-size:19px; font-weight:700; color:{accent}; }}
  .pill-t {{ font-size:16px; color:{ink}; opacity:.78; }}
  .qr {{ text-align:center; flex-shrink:0; }}
  .qr-box {{ padding:12px; background:#fff; border-radius:14px;
    border:1px solid {line}33; line-height:0; }}
  .qr-cap {{ margin-top:12px; font-size:16px; color:{muted}; letter-spacing:2px; }}
</style></head>
<body><div class="card">
  <div class="brand">
    <div class="row"><div class="mark">{initial}</div><div class="name">{esc(name)}</div></div>
    <div class="slogan">{esc(slogan)}</div>
    {keyword_pill}
  </div>
  <div class="qr"><div class="qr-box">{qr}</div><div class="qr-cap">扫码关注</div></div>
</div></body></html>"""


def build_snippet(account: str, image_ref: str) -> str:
    """WeChat-ready footer snippet.

    Prefers the native ``{embed:profile:...}`` follow card because it is a real
    subscribe button rather than a flat image; the rendered card is emitted
    right above it as the visual anchor.
    """
    profile = load_profile(account)
    name = profile.get("public_display_name") or profile.get("display_name") or account
    return (
        f"<!-- footer-card: {esc(account)} / 不计入正文配图配额 -->\n"
        f'<p style="text-align:center;margin:28px 0 12px;">'
        f'<img src="{esc(image_ref)}" alt="{esc(name)} 关注卡片" style="max-width:100%;border-radius:12px;"/></p>\n'
        f"{{embed:profile:{esc(name)}}}\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Render the account footer follow card.")
    parser.add_argument("--account", default=_default_account(), choices=(_default_account(),))
    parser.add_argument("--url", default="", help="QR target URL (account profile page)")
    parser.add_argument("--output", required=True, help="Output PNG path")
    parser.add_argument("--html-output", default="", help="Keep the intermediate HTML here")
    parser.add_argument("--snippet-output", default="", help="Write the footer HTML snippet here")
    parser.add_argument("--name", default="", help="Override the display name")
    parser.add_argument("--slogan", default="", help="Override the slogan / CTA line")
    parser.add_argument("--keyword", default="", help="Override the reply keyword")
    parser.add_argument("--magnet", default="", help="Override the lead magnet copy")
    args = parser.parse_args()

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    html_path = Path(args.html_output).resolve() if args.html_output else output.with_suffix(".html")
    html_path.parent.mkdir(parents=True, exist_ok=True)

    overrides = {
        "name": args.name,
        "slogan": args.slogan,
        "keyword": args.keyword,
        "magnet": args.magnet,
    }
    html_path.write_text(build_html(args.account, args.url, overrides), encoding="utf-8")

    chrome = chrome_path()
    if not chrome:
        print("FOOTER CARD BLOCKED: 未找到 Chrome，无法栅格化", flush=True)
        return 1

    command = [
        str(chrome),
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        f"--window-size={CARD_WIDTH},{CARD_HEIGHT}",
        f"--screenshot={output}",
        html_path.as_uri(),
    ]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=45)
    if result.returncode != 0 or not output.is_file() or output.stat().st_size < 1024:
        print("FOOTER CARD BLOCKED: Chrome 栅格化失败", flush=True)
        print((result.stdout or "") + (result.stderr or ""))
        return 1

    if args.snippet_output:
        snippet_path = Path(args.snippet_output).resolve()
        snippet_path.parent.mkdir(parents=True, exist_ok=True)
        snippet_path.write_text(build_snippet(args.account, output.name), encoding="utf-8")

    print(json.dumps({
        "role": FOOTER_ROLE,
        "account": args.account,
        "png": str(output),
        "html": str(html_path),
        "counts_toward_body_quota": False,
        "qr": bool(qr_matrix(args.url)),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
