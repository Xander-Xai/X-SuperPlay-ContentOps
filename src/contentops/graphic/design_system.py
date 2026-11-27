"""Executable Visual Design System & Anti-Slop Linter (T06).

Loads machine-readable account visual tokens from ``config/design/design-tokens.json``
(derived directly from FI and 1024 account DNAs) so every graphic template,
WeChat article layout, and Huashu video scene consumes ONE authoritative light
design system instead of inventing arbitrary dark cards or generic AI gradients.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

TOKENS_FILE = Path("config") / "design" / "design-tokens.json"

ANTI_SLOP_HTML_RULES = (
    ("BLUE_PURPLE_GRADIENT", re.compile(r"linear-gradient\([^)]*(?:#6366f1|#8b5cf6|#7c3aed|purple|violet)", re.I),
     "Forbidden blue/purple AI-slop gradient detected"),
    ("GLASSMORPHISM", re.compile(r"backdrop-filter\s*:\s*blur", re.I),
     "Forbidden glassmorphism backdrop-filter detected"),
    ("GRADIENT_TEXT", re.compile(r"-webkit-background-clip\s*:\s*text", re.I),
     "Forbidden gradient text effect detected"),
    ("FORBIDDEN_DARK_BODY_BG", re.compile(r"(?:body|#film|\.card|\.canvas)[^{]*\{[^}]*background(?:-color)?\s*:\s*(?:#000\b|#000000|#0b0f14|#0f1117|#111\b)", re.I),
     "Body canvas uses dark background; FI/1024 DNA restricts dark #0F1117 strictly to intro/outro brand marks"),
    ("OBJECT_FIT_COVER_SCREENSHOT", re.compile(r"\.source(?:[-_a-z]*)[^{]*\{[^}]*object-fit\s*:\s*cover", re.I),
     "Screenshot container uses object-fit: cover which clips code/UI lines; use contain"),
)


def load_tokens(root: Path) -> Dict[str, Any]:
    path = Path(root).resolve() / TOKENS_FILE
    return json.loads(path.read_text(encoding="utf-8"))


def account_tokens(root: Path, account_slug: str, *, variant_override: Optional[str] = None) -> Dict[str, Any]:
    """Return the exact color/typography/layout token dict for an account."""
    data = load_tokens(root)
    accounts = data.get("accounts") or {}
    if account_slug not in accounts:
        raise KeyError(f"unknown visual design account: {account_slug!r}")
    spec = json.loads(json.dumps(accounts[account_slug]))
    if variant_override and "warm-editorial" in variant_override:
        spec["colors"].update({
            "bg": "#F4F2ED", "surface": "#FFFFFF", "surface_alt": "#EAE6DD",
            "border": "#DBD5C9", "ink": "#18232B", "sub": "#5C6970",
            "accent": "#087FA6", "accent_soft": "#E2F2F7", "accent2": "#C4DCE3",
        })
        spec["variant"] = "warm-editorial (override)"
    return spec


def css_variables_block(tokens: Dict[str, Any]) -> str:
    """Emit deterministic CSS custom properties consumed by templates and video scenes."""
    c = tokens["colors"]
    t = tokens["typography"]
    l = tokens["layout"]
    return (
        ":root {\n"
        f"  --bg: {c['bg']};\n"
        f"  --surface: {c['surface']};\n"
        f"  --surface-alt: {c['surface_alt']};\n"
        f"  --border: {c['border']};\n"
        f"  --ink: {c['ink']};\n"
        f"  --sub: {c['sub']};\n"
        f"  --accent: {c['accent']};\n"
        f"  --accent-soft: {c['accent_soft']};\n"
        f"  --accent2: {c['accent2']};\n"
        f"  --problem: {c['problem']};\n"
        f"  --problem-soft: {c['problem_soft']};\n"
        f"  --success: {c['success']};\n"
        f"  --success-soft: {c['success_soft']};\n"
        f"  --brand-dark: {c['brand_dark_intro_only']};\n"
        f"  --brand-cyan: {c['brand_cyan']};\n"
        f"  --font-sans: {t['sans']};\n"
        f"  --font-display: {t['display']};\n"
        f"  --font-mono: {t['mono']};\n"
        f"  --margin: {l['margin_px']}px;\n"
        f"  --gap: {l['grid_gap_px']}px;\n"
        f"  --radius: {l['radius_card_px']}px;\n"
        "}\n"
    )


def lint_html_design(html_text: str, *, allow_dark_intro: bool = False) -> Dict[str, Any]:
    """Deterministic anti-slop HTML/CSS validator (zero LLM calls)."""
    findings: List[Dict[str, str]] = []
    for code, pattern, detail in ANTI_SLOP_HTML_RULES:
        if code == "FORBIDDEN_DARK_BODY_BG" and allow_dark_intro:
            continue
        if pattern.search(html_text):
            findings.append({"code": code, "detail": detail})
    return {
        "schema": "contentops.design-lint/v1",
        "ok": not findings,
        "finding_count": len(findings),
        "findings": findings,
    }
