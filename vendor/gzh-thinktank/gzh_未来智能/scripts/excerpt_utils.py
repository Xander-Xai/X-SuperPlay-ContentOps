"""Single source of truth for article-section excerpt extraction and hashing.

Both ``visual_semantic_qa.py`` and ``formula_pipeline.py`` import from this module
so that ``source_excerpt_sha256`` is computed identically everywhere.  Previously the
excerpt logic was duplicated (and the stored digest was hand-synced in two JSON
files), which caused stale-hash gate failures whenever ``article.md`` changed.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

_EXCERPT_LIMIT = 1200
_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)


def _canonical_excerpt(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()[:_EXCERPT_LIMIT]


def section_excerpt(article: Path | str, heading: str) -> str:
    """Return the canonical first-1200-char excerpt of ``heading``'s section.

    Mirrors the legacy ``_article_excerpt`` behaviour in ``visual_semantic_qa.py``
    so existing stored digests stay valid.
    """
    source = Path(article) / "article.md"
    if not source.is_file() or not heading:
        return ""
    text = source.read_text(encoding="utf-8", errors="replace")
    matches = list(_HEADING_RE.finditer(text))
    for index, match in enumerate(matches):
        if match.group(1).strip() != heading:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        return _canonical_excerpt(text[match.end():end])
    return ""


def section_excerpt_sha256(article: Path | str, heading: str) -> str:
    """SHA-256 of the canonical section excerpt (empty string -> zero digest)."""
    return hashlib.sha256(section_excerpt(article, heading).encode("utf-8")).hexdigest()
