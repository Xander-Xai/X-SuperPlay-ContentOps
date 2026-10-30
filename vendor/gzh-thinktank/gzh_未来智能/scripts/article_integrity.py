#!/usr/bin/env python3
"""Small, dependency-free integrity helpers shared by article gates."""

from __future__ import annotations

import hashlib
import html
import re
from pathlib import Path


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# Evidence files are often checked out on both Windows and Unix.  Git may
# rewrite CRLF/LF line endings without changing the actual text, so text
# evidence needs a stable digest distinct from the raw byte digest used for
# binary assets and transport receipts.
TEXT_EVIDENCE_SUFFIXES = frozenset({
    ".c",
    ".cc",
    ".cpp",
    ".css",
    ".csv",
    ".go",
    ".h",
    ".html",
    ".htm",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".markdown",
    ".py",
    ".rs",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
})

# Public-facing article files must not expose workstation paths, credential
# filenames, or environment variable names.  These patterns intentionally
# target operational markers rather than ordinary prose such as “公众号 API”.
PUBLIC_CONTENT_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("local-path", re.compile(r"(?i)(?:\b[A-Z]:[\\/]|(?:/Users|/home|/root|/mnt)/)")),
    ("credential-file", re.compile(r"(?i)\baws\.env\b")),
    ("wechat-secret-key", re.compile(r"(?i)\bWECHAT_[0-9]+_(?:APPSECRET|APPID|API_BASE)\b")),
    ("model-secret-key", re.compile(r"(?i)\bAGNES_API_KEY\b")),
    ("access-token", re.compile(r"(?i)\baccess[_ -]?token\b\s*[:=]")),
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_text_sha256_file(path: Path) -> str:
    """Hash UTF-8 text after normalizing all line endings to LF.

    The helper is intentionally separate from :func:`sha256_file`: binary
    assets, screenshots, and API receipts must remain byte-for-byte bound,
    while source evidence and Markdown content should survive a platform
    checkout without producing a false freshness failure.
    """

    raw = path.read_bytes()
    text = raw.decode("utf-8")
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return sha256_bytes(normalized.encode("utf-8"))


def is_text_evidence_path(path: Path) -> bool:
    """Return whether a local evidence path has a text-like suffix."""

    return path.suffix.lower() in TEXT_EVIDENCE_SUFFIXES


def stable_sha256_file(path: Path) -> str:
    """Return the platform-stable digest used for content/revision evidence."""

    if is_text_evidence_path(path):
        try:
            return canonical_text_sha256_file(path)
        except UnicodeDecodeError:
            # A file with a text-like suffix but non-UTF-8 bytes is still
            # evidence; fall back to the raw digest rather than crashing a
            # gate.  ``sources.json`` can explicitly use ``hash_mode: raw``.
            pass
    return sha256_file(path)


def public_content_findings(value: str) -> list[dict[str, str]]:
    """Return operational secrets/path markers found in public article text.

    The function returns structured findings so gates can report the exact
    rule and line without dumping any credential value.
    """

    findings: list[dict[str, str]] = []
    for line_no, line in enumerate(value.splitlines(), 1):
        for rule_name, pattern in PUBLIC_CONTENT_RULES:
            match = pattern.search(line)
            if match:
                findings.append({
                    "rule": rule_name,
                    "line": str(line_no),
                    "excerpt": line[:160],
                })
    return findings


def canonical_html(value: str) -> str:
    """Normalize harmless WeChat rewrites before comparing local/remote HTML.

    The draft API preserves the article but commonly HTML-escapes quotes,
    changes ``img src`` into ``data-src`` with a remote media URL, and moves
    image attributes (for lazy loading).  Those transport-level rewrites must
    not look like a content mismatch, while the text and non-image markup
    remain part of the digest.
    """

    normalized = html.unescape(value)

    def normalize_img(match: re.Match[str]) -> str:
        attrs: dict[str, str] = {}
        raw = match.group(0)
        for attr in re.finditer(
            r"([:\w-]+)\s*=\s*([\"'])(.*?)\2", raw, flags=re.S
        ):
            name = attr.group(1).lower()
            attr_value = attr.group(3)
            if name in {"src", "data-src"}:
                name = "src"
                attr_value = "__IMAGE__"
            attrs[name] = attr_value
        rendered = " ".join(
            f'{name}="{attrs[name]}"' for name in sorted(attrs)
        )
        return f"<img {rendered}>" if rendered else "<img>"

    normalized = re.sub(r"<img\b[^>]*?/?>", normalize_img, normalized, flags=re.I)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def canonical_html_digest(value: str) -> str:
    return sha256_bytes(canonical_html(value).encode("utf-8"))


def is_sha256(value: object) -> bool:
    return bool(SHA256_RE.fullmatch(str(value or "").strip().lower()))
