"""Text matching helpers for quote verification against pinned evidence."""

from __future__ import annotations

import re
from pathlib import PurePosixPath


def markdown_quote_key(text: str) -> str:
    """Remove Markdown presentation syntax without changing quote words."""
    value = str(text or "")
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"^\s{0,3}#{1,6}\s*", "", value, flags=re.MULTILINE)
    value = re.sub(r"^\s*>\s?", "", value, flags=re.MULTILINE)
    value = re.sub(r"^\s*[-+*]\s+", "", value, flags=re.MULTILINE)
    value = re.sub(r"^\s*\|?\s*:?-{3,}.*$", " ", value, flags=re.MULTILINE)
    value = re.sub(r"\|\s*:?-{3,}:?\s*(?=\|)", " ", value)
    value = value.replace("|", " ")
    value = re.sub(r"[*_`]{1,3}", "", value)
    return " ".join(value.split())


def quote_occurs(quote: str, text: str, path: str = "") -> bool:
    """Check a literal quote, or a Markdown-rendered quote in a Markdown file."""
    if not quote or not text:
        return False
    if quote in text:
        return True
    if PurePosixPath(str(path).replace("\\", "/")).suffix.casefold() not in (
            ".md", ".markdown"):
        return False
    return markdown_quote_key(quote) in markdown_quote_key(text)
