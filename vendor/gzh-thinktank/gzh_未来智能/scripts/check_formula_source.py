#!/usr/bin/env python3
"""Check article.md for double-escaped LaTeX.

Scans $...$ and $$...$$ regions for patterns like \\\\in, \\\\mathbb,
\\\\text that indicate markdown double-escaping (the source used \\ in
place of \\ because of markdown escaping). KaTeX treats \\\\ as a line
break command and renders the rest as plain text, which is exactly
what was happening in the 65 broken formulas.

Exit code 0 = clean. Exit code 1 = issues found.

Usage:
    python scripts/check_formula_source.py <article_dir>
"""
from __future__ import annotations
import re
import sys
import pathlib

# Patterns of double-escaped LaTeX commands commonly produced by LLM-generated
# markdown that wasn't carefully LaTeX-aware.
SUSPICIOUS_COMMANDS = (
    "in", "mathbb", "text", "operatorname", "langle", "rangle",
    "widetilde", "frac", "sqrt", "sum", "prod", "int",
    "ldots", "cdots", "dots", "rightarrow", "leftarrow",
    "uparrow", "downarrow", "times", "div", "pm", "mp",
    "le", "ge", "ne", "approx", "equiv", "sim", "cong",
    "cup", "cap", "subset", "supset", "subseteq", "supseteq",
    "alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta",
    "theta", "iota", "kappa", "lambda", "mu", "nu", "xi", "omicron",
    "pi", "rho", "sigma", "tau", "phi", "varphi", "chi", "psi", "omega",
    "Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi", "Sigma",
    "Upsilon", "Phi", "Psi", "Omega",
    "partial", "nabla", "forall", "exists", "infty",
    "quad", "qquad", " ", ",",
)

def build_pattern() -> re.Pattern[str]:
    # Match \\<cmd>(\b) inside formula regions.
    alts = "|".join(re.escape(c) for c in SUSPICIOUS_COMMANDS)
    return re.compile(rf"\\\\({alts})(?![A-Za-z])")

INLINE_RE = re.compile(r"(?<!\\)\$(?!\$)(.+?)(?<!\\)\$(?!\$)", flags=re.S)
BLOCK_RE = re.compile(r"(?ms)^\s*\$\$(.+?)\$\$\s*$")

def collect_regions(text: str) -> list[tuple[str, int, int]]:
    """Return list of (matched_text, start_offset, end_offset)."""
    regions = []
    # Block first
    for m in BLOCK_RE.finditer(text):
        regions.append((m.group(1), m.start(1), m.end(1)))
    # Then inline (skip those overlapping with blocks)
    block_spans = [(m.start(), m.end()) for m in BLOCK_RE.finditer(text)]
    for m in INLINE_RE.finditer(text):
        if any(s <= m.start(1) < e for s, e in block_spans):
            continue
        regions.append((m.group(1), m.start(1), m.end(1)))
    return regions

def check_article(article_dir: pathlib.Path) -> tuple[int, list[str]]:
    article = article_dir / "article.md"
    if not article.is_file():
        return 1, [f"article.md not found in {article_dir}"]
    text = article.read_text(encoding="utf-8")
    pattern = build_pattern()
    issues: list[str] = []
    for region, start, end in collect_regions(text):
        for m in pattern.finditer(region):
            issues.append(
                f"DOUBLE-ESCAPED LaTeX at offset {start + m.start()}: "
                f"\\\\{m.group(1)} (should be \\{m.group(1)})"
            )
    return (0 if not issues else 1), issues

def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: check_formula_source.py <article_dir>", file=sys.stderr)
        return 2
    article_dir = pathlib.Path(sys.argv[1])
    rc, issues = check_article(article_dir)
    if rc == 0:
        print(f"FORMULA SOURCE CLEAN: {article_dir}/article.md")
        return 0
    print(f"FORMULA SOURCE BLOCKED: {len(issues)} double-escaped LaTeX issues", file=sys.stderr)
    for issue in issues[:20]:
        print(f"  - {issue}", file=sys.stderr)
    if len(issues) > 20:
        print(f"  ... and {len(issues) - 20} more", file=sys.stderr)
    return 1

if __name__ == "__main__":
    sys.exit(main())