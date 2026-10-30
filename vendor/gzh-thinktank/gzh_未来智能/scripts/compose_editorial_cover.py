#!/usr/bin/env python3
"""Compose a trustworthy English information layer over an Agnes cover.

Agnes supplies only the illustrative background.  This renderer owns exact
English topic copy so a cover can communicate its article at a glance without
depending on image-model typography.  The generated SVG embeds the background
as data (no external URL), remains editable, and Chrome creates the final PNG.
"""

from __future__ import annotations

import argparse
import base64
import html
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHROME_CANDIDATES = (
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
)
CANVAS_W = 1880
CANVAS_H = 800


def esc(value: str) -> str:
    return html.escape(str(value or ""), quote=True)


def chrome_path() -> Path | None:
    for candidate in CHROME_CANDIDATES:
        if candidate.is_file():
            return candidate
    found = shutil.which("chrome")
    return Path(found) if found else None


def image_data_uri(path: Path) -> str:
    suffix = path.suffix.lower()
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(suffix)
    if not mime:
        raise ValueError(f"unsupported cover background format: {path.suffix}")
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def motif_markup(motif: str) -> str:
    """Return a visible, topic-bound right-hand cover motif.

    The old compositor had one hard-coded StateGraph/AgentState drawing for
    every topic.  That made a RAG article look like an agent article even
    when the left-hand copy was correct.  Motifs are now explicit contract
    values so the renderer and the semantic QA can reject cross-topic drift.
    """
    motif = str(motif or "generic-engineering-loop").strip().lower()
    if motif == "rag-retrieval-loop":
        return '''
  <text x="1040" y="142" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="700" letter-spacing="4" fill="#B24A2B">RETRIEVAL MAP</text>
  <line x1="1040" y1="168" x2="1770" y2="168" stroke="#D7B09E" stroke-width="2"/>
  <g data-role="node"><circle cx="1190" cy="360" r="82" fill="#17324D"/><circle cx="1190" cy="360" r="62" fill="none" stroke="#557A96" stroke-width="3"/><text x="1190" y="366" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="22" font-weight="800" letter-spacing="2" fill="#FFFCF7">QUERY</text></g>
  <g data-role="node"><rect x="1415" y="242" width="210" height="94" rx="20" fill="#FFFCF7" stroke="#557A96" stroke-width="3"/><text x="1450" y="281" font-family="Arial, Helvetica, sans-serif" font-size="16" font-weight="800" letter-spacing="2" fill="#17324D">EMBED</text><text x="1450" y="309" font-family="Arial, Helvetica, sans-serif" font-size="15" font-weight="600" fill="#5E6872">query vector</text></g>
  <g data-role="node"><rect x="1415" y="456" width="210" height="94" rx="20" fill="#FFFCF7" stroke="#B24A2B" stroke-width="3"/><text x="1450" y="495" font-family="Arial, Helvetica, sans-serif" font-size="15" font-weight="800" letter-spacing="1.5" fill="#17324D">VECTOR DB</text><text x="1450" y="523" font-family="Arial, Helvetica, sans-serif" font-size="15" font-weight="600" fill="#5E6872">chunks + metadata</text></g>
  <g data-role="node"><rect x="1640" y="318" width="160" height="94" rx="20" fill="#FFF2EA" stroke="#B24A2B" stroke-width="3"/><text x="1720" y="357" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="15" font-weight="800" letter-spacing="1" fill="#17324D">TOP-K</text><text x="1720" y="386" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="14" font-weight="600" fill="#5E6872">rerank</text></g>
  <g data-role="node"><rect x="1130" y="590" width="300" height="72" rx="20" fill="#EAF4EA" stroke="#557A96" stroke-width="3"/><text x="1280" y="634" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="16" font-weight="800" letter-spacing="1" fill="#17324D">GROUNDED ANSWER</text></g>
  <path data-role="edge" d="M1278 330 C1335 292 1360 289 1406 289" fill="none" stroke="#557A96" stroke-width="5" stroke-linecap="round"/>
  <path data-role="arrowhead" d="M1406 289 L1388 278 L1393 298 Z" fill="#557A96"/>
  <path data-role="edge" d="M1261 407 C1326 472 1363 494 1406 494" fill="none" stroke="#557A96" stroke-width="5" stroke-linecap="round"/>
  <path data-role="arrowhead" d="M1406 494 L1388 483 L1393 503 Z" fill="#557A96"/>
  <path data-role="edge" d="M1629 289 C1650 300 1660 320 1670 338" fill="none" stroke="#B24A2B" stroke-width="4" stroke-linecap="round"/>
  <path data-role="arrowhead" d="M1670 338 L1657 327 L1662 348 Z" fill="#B24A2B"/>
  <path data-role="edge" d="M1629 505 C1650 490 1660 430 1670 398" fill="none" stroke="#B24A2B" stroke-width="4" stroke-linecap="round"/>
  <path data-role="arrowhead" d="M1670 398 L1657 411 L1678 407 Z" fill="#B24A2B"/>
  <path data-role="edge" d="M1190 442 C1190 500 1240 560 1280 590" fill="none" stroke="#557A96" stroke-width="4" stroke-linecap="round"/>
  <path data-role="arrowhead" d="M1280 590 L1265 575 L1260 595 Z" fill="#557A96"/>
  <text x="1190" y="714" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="700" letter-spacing="1" fill="#17324D">RETRIEVE · GROUND · EVALUATE</text>'''
    if motif == "stateful-agent-loop":
        return '''
  <text x="1040" y="142" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="700" letter-spacing="4" fill="#B24A2B">SYSTEM MAP</text>
  <line x1="1040" y1="168" x2="1770" y2="168" stroke="#D7B09E" stroke-width="2"/>
  <g data-role="node"><circle cx="1190" cy="360" r="82" fill="#17324D"/><circle cx="1190" cy="360" r="62" fill="none" stroke="#557A96" stroke-width="3"/><text x="1190" y="352" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="20" font-weight="800" letter-spacing="2" fill="#FFFCF7">STATE</text><text x="1190" y="382" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="14" font-weight="600" fill="#D7E0E6">AGENTSTATE</text></g>
  <g data-role="node"><rect x="1415" y="242" width="210" height="94" rx="20" fill="#FFFCF7" stroke="#557A96" stroke-width="3"/><text x="1450" y="281" font-family="Arial, Helvetica, sans-serif" font-size="16" font-weight="800" letter-spacing="2" fill="#17324D">FLOW</text><text x="1450" y="309" font-family="Arial, Helvetica, sans-serif" font-size="15" font-weight="600" fill="#5E6872">nodes + edges</text></g>
  <g data-role="node"><rect x="1415" y="456" width="210" height="94" rx="20" fill="#FFFCF7" stroke="#B24A2B" stroke-width="3"/><text x="1450" y="495" font-family="Arial, Helvetica, sans-serif" font-size="15" font-weight="800" letter-spacing="1.5" fill="#17324D">CHECKPOINT</text><text x="1450" y="523" font-family="Arial, Helvetica, sans-serif" font-size="15" font-weight="600" fill="#5E6872">persist + resume</text></g>
  <g data-role="node"><path d="M1714 314 L1784 384 L1714 454 L1644 384 Z" fill="#FFF2EA" stroke="#B24A2B" stroke-width="3"/><text x="1714" y="379" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="14" font-weight="800" letter-spacing="1" fill="#17324D">HUMAN</text><text x="1714" y="400" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="14" font-weight="800" letter-spacing="1" fill="#17324D">GATE</text></g>
  <path data-role="edge" d="M1278 330 C1335 292 1360 289 1406 289" fill="none" stroke="#557A96" stroke-width="5" stroke-linecap="round"/><path data-role="arrowhead" d="M1406 289 L1388 278 L1393 298 Z" fill="#557A96"/>
  <path data-role="edge" d="M1261 407 C1326 472 1363 494 1406 494" fill="none" stroke="#557A96" stroke-width="5" stroke-linecap="round"/><path data-role="arrowhead" d="M1406 494 L1388 483 L1393 503 Z" fill="#557A96"/>
  <path data-role="edge" d="M1629 289 C1662 310 1680 336 1689 356" fill="none" stroke="#B24A2B" stroke-width="4" stroke-linecap="round"/><path data-role="arrowhead" d="M1689 356 L1675 344 L1681 365 Z" fill="#B24A2B"/>
  <path data-role="edge" d="M1629 505 C1662 484 1680 447 1689 414" fill="none" stroke="#B24A2B" stroke-width="4" stroke-linecap="round"/><path data-role="arrowhead" d="M1689 414 L1676 427 L1697 423 Z" fill="#B24A2B"/>
  <text x="1190" y="642" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="700" letter-spacing="1" fill="#17324D">ONE EXECUTION · ONE TRACE · ONE DECISION</text>'''
    return '''
  <text x="1040" y="142" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="700" letter-spacing="4" fill="#B24A2B">ENGINEERING MAP</text>
  <line x1="1040" y1="168" x2="1770" y2="168" stroke="#D7B09E" stroke-width="2"/>
  <g data-role="node"><circle cx="1190" cy="360" r="82" fill="#17324D"/><text x="1190" y="368" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="20" font-weight="800" letter-spacing="2" fill="#FFFCF7">INPUT</text></g>
  <g data-role="node"><rect x="1415" y="242" width="210" height="94" rx="20" fill="#FFFCF7" stroke="#557A96" stroke-width="3"/><text x="1450" y="281" font-family="Arial, Helvetica, sans-serif" font-size="16" font-weight="800" letter-spacing="2" fill="#17324D">PROCESS</text><text x="1450" y="309" font-family="Arial, Helvetica, sans-serif" font-size="15" font-weight="600" fill="#5E6872">transform</text></g>
  <g data-role="node"><rect x="1415" y="456" width="210" height="94" rx="20" fill="#FFFCF7" stroke="#B24A2B" stroke-width="3"/><text x="1450" y="495" font-family="Arial, Helvetica, sans-serif" font-size="15" font-weight="800" letter-spacing="1.5" fill="#17324D">CHECK</text><text x="1450" y="523" font-family="Arial, Helvetica, sans-serif" font-size="15" font-weight="600" fill="#5E6872">verify</text></g>
  <g data-role="node"><path d="M1714 314 L1784 384 L1714 454 L1644 384 Z" fill="#FFF2EA" stroke="#B24A2B" stroke-width="3"/><text x="1714" y="390" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="14" font-weight="800" letter-spacing="1" fill="#17324D">OUTPUT</text></g>
  <path data-role="edge" d="M1278 330 C1335 292 1360 289 1406 289" fill="none" stroke="#557A96" stroke-width="5" stroke-linecap="round"/><path data-role="arrowhead" d="M1406 289 L1388 278 L1393 298 Z" fill="#557A96"/>
  <path data-role="edge" d="M1261 407 C1326 472 1363 494 1406 494" fill="none" stroke="#557A96" stroke-width="5" stroke-linecap="round"/><path data-role="arrowhead" d="M1406 494 L1388 483 L1393 503 Z" fill="#557A96"/>
  <path data-role="edge" d="M1629 289 C1662 310 1680 336 1689 356" fill="none" stroke="#B24A2B" stroke-width="4" stroke-linecap="round"/><path data-role="arrowhead" d="M1689 356 L1675 344 L1681 365 Z" fill="#B24A2B"/>
  <path data-role="edge" d="M1629 505 C1662 484 1680 447 1689 414" fill="none" stroke="#B24A2B" stroke-width="4" stroke-linecap="round"/><path data-role="arrowhead" d="M1689 414 L1676 427 L1697 423 Z" fill="#B24A2B"/>
  <text x="1190" y="642" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="18" font-weight="700" letter-spacing="1" fill="#17324D">ONE INPUT · ONE CHECK · ONE OUTPUT</text>'''


def svg_document(background: Path, *, eyebrow: str, headline: str, keywords: str, caption: str, motif: str) -> str:
    data_uri = image_data_uri(background)
    copy = {
        "eyebrow": eyebrow,
        "headline": headline,
        "keywords": keywords,
        "caption": caption,
        "motif": motif,
    }
    import json

    metadata = esc(json.dumps({"contract": "cover-copy-v1", "copy": copy}, ensure_ascii=False, separators=(",", ":")))
    # The left editorial card is a hard 680px safe frame (x=150..830).  Do
    # not let a headline's nominal character count decide fit: Latin glyphs
    # have very different widths.  Wrap on word boundaries and record the
    # resulting line count so the visual QA can reject a future one-line
    # overflow even if the copy itself is correct.
    headline_size = 88 if len(headline) <= 18 else 62
    max_headline_width = 650.0

    def _headline_weight(value: str) -> float:
        return sum(1.0 if ord(ch) > 0x2E80 else 0.56 for ch in value)

    headline_lines: list[str] = []
    current = ""
    for word in str(headline).split():
        candidate = word if not current else f"{current} {word}"
        if current and _headline_weight(candidate) * headline_size > max_headline_width:
            headline_lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        headline_lines.append(current)
    if not headline_lines:
        headline_lines = [str(headline)]
    headline_line_gap = int(headline_size * 1.04)
    headline_y = 330 if len(headline_lines) == 1 else 288
    keywords_y = 420 if len(headline_lines) == 1 else headline_y + headline_line_gap * len(headline_lines) + 48
    divider_y = 468 if len(headline_lines) == 1 else keywords_y + 48
    caption_y = 535 if len(headline_lines) == 1 else divider_y + 67
    keyword_size = 28 if len(keywords) <= 34 else 24
    caption_size = 34 if len(caption) <= 36 else 29
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{CANVAS_H}" viewBox="0 0 {CANVAS_W} {CANVAS_H}" data-backend="agnes-background+deterministic-cover-overlay" data-cover-copy-contract="cover-copy-v1" data-cover-motif="{esc(motif)}" data-cover-safe-frame="150,120,830,620" data-cover-headline-lines="{len(headline_lines)}">
  <metadata id="cover-copy-contract">{metadata}</metadata>
  <defs>
    <linearGradient id="veil" x1="0" x2="1" y1="0" y2="0">
      <stop offset="0%" stop-color="#F8F4EB" stop-opacity="1"/>
      <stop offset="52%" stop-color="#F8F4EB" stop-opacity="0.96"/>
      <stop offset="72%" stop-color="#F8F4EB" stop-opacity="0.30"/>
      <stop offset="100%" stop-color="#F8F4EB" stop-opacity="0.00"/>
    </linearGradient>
    <filter id="soft-shadow" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="8" stdDeviation="10" flood-color="#17324D" flood-opacity="0.12"/>
    </filter>
    <filter id="background-soften" x="-5%" y="-5%" width="110%" height="110%">
      <feGaussianBlur stdDeviation="4"/>
    </filter>
  </defs>
  <rect width="{CANVAS_W}" height="{CANVAS_H}" fill="#F8F4EB"/>
  <image href="{data_uri}" x="0" y="0" width="{CANVAS_W}" height="{CANVAS_H}" preserveAspectRatio="xMidYMid slice" filter="url(#background-soften)" opacity="0.72"/>
  <rect width="{CANVAS_W}" height="{CANVAS_H}" fill="url(#veil)"/>
  <!-- The right panel intentionally replaces untrusted model typography and
       fake UI with a sparse, exact, topic-specific system motif. -->
  <rect x="970" y="42" width="850" height="716" rx="34" fill="#F8F4EB" fill-opacity="0.93"/>
{motif_markup(motif)}
  <rect x="54" y="50" width="12" height="700" rx="6" fill="#B24A2B"/>
  <g filter="url(#soft-shadow)">
    <rect x="102" y="82" width="830" height="618" rx="28" fill="#FFFCF7" fill-opacity="0.78"/>
  </g>
  <text x="150" y="174" font-family="Arial, Helvetica, sans-serif" font-size="26" font-weight="700" letter-spacing="5" fill="#B24A2B">{esc(eyebrow)}</text>
  <line x1="150" y1="214" x2="300" y2="214" stroke="#B24A2B" stroke-width="6" stroke-linecap="round"/>
  <text x="150" y="{headline_y}" font-family="Arial, Helvetica, sans-serif" font-size="{headline_size}" font-weight="800" letter-spacing="-1.5" fill="#17324D">{''.join(f'<tspan x="150" dy="{0 if idx == 0 else headline_line_gap}">{esc(line)}</tspan>' for idx, line in enumerate(headline_lines))}</text>
  <text x="150" y="{keywords_y}" font-family="Arial, Helvetica, sans-serif" font-size="{keyword_size}" font-weight="700" letter-spacing="2.5" fill="#557A96">{esc(keywords)}</text>
  <line x1="150" y1="{divider_y}" x2="830" y2="{divider_y}" stroke="#D7B09E" stroke-width="2"/>
  <text x="150" y="{caption_y}" font-family="Arial, Helvetica, sans-serif" font-size="{caption_size}" font-weight="500" fill="#4B5660">{esc(caption)}</text>
</svg>'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--background", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--svg-output", required=True, type=Path)
    parser.add_argument("--eyebrow", required=True)
    parser.add_argument("--headline", required=True)
    parser.add_argument("--keywords", required=True)
    parser.add_argument("--caption", required=True)
    parser.add_argument("--motif", default="generic-engineering-loop")
    args = parser.parse_args()

    background = args.background.expanduser().resolve()
    output = args.output.expanduser().resolve()
    svg_output = args.svg_output.expanduser().resolve()
    if not background.is_file():
        raise SystemExit(f"cover background does not exist: {background}")
    output.parent.mkdir(parents=True, exist_ok=True)
    svg_output.parent.mkdir(parents=True, exist_ok=True)
    svg_output.write_text(
        svg_document(background, eyebrow=args.eyebrow, headline=args.headline, keywords=args.keywords, caption=args.caption, motif=args.motif),
        encoding="utf-8",
    )
    chrome = chrome_path()
    if not chrome:
        raise SystemExit("COVER COMPOSITOR BLOCKED: Chrome not found")
    result = subprocess.run(
        [str(chrome), "--headless", "--disable-gpu", "--no-sandbox", f"--window-size={CANVAS_W},{CANVAS_H}", f"--screenshot={output}", svg_output.as_uri()],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=45,
    )
    if result.returncode or not output.is_file() or output.stat().st_size < 1024:
        raise SystemExit(result.stderr.strip() or "COVER COMPOSITOR BLOCKED: Chrome rasterization failed")
    print(f"COVER COMPOSED: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
