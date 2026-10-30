#!/usr/bin/env python3
"""Detect orphan visual assets.

An asset is "orphan" if it exists on disk but is not referenced anywhere
in the article pipeline (article.html, article.md, image-sources.json,
visual-brief.yaml, image-generation-plan.json, formula-manifest.json).

Run this BEFORE regenerating images so the previous run's leftovers
don't get re-uploaded to the WeChat asset library.

Exit 0 = clean.  Exit 1 = orphan files found.

Usage:
    python scripts/check_orphan_assets.py <article_dir>
"""
from __future__ import annotations
import json
import re
import sys
import pathlib
from typing import Iterable

RECOGNIZED_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
BODY_IMAGE_GLOB = ("section-*.png", "section-*.jpg", "section-*.webp")
ORPHAN_DRY_RUN_DIRS = (
    "imgs", "imgs/diagram-sources", "imgs/prompts",
    "formula-src", ".tmp-formulas",
)


def _read_text(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _collect_index(article_dir: pathlib.Path) -> set[str]:
    """Build the set of asset paths that ARE referenced somewhere."""
    referenced: set[str] = set()
    referenced |= _extract_md_image_paths(article_dir / "article.md")
    referenced |= _extract_md_image_paths(article_dir / "article.render.md")
    referenced |= _extract_html_image_paths(article_dir / "article.html")
    referenced |= _extract_sources_json(article_dir / "image-sources.json")
    referenced |= _extract_brief_yaml(article_dir / "visual-brief.yaml")
    referenced |= _extract_generation_plan(article_dir / "image-generation-plan.json")
    referenced |= _extract_formula_manifest(article_dir / "formula-manifest.json")
    # Editable SVG/HTML sources are referenced by the visual contract rather
    # than article.md/article.html.  Treat them as first-class assets so the
    # cleanup pass does not delete a live source or report a false orphan.
    referenced |= _extract_visual_contract_sources(article_dir / "visual-contract.json")
    return referenced


def _extract_visual_contract_sources(path: pathlib.Path) -> set[str]:
    if not path.is_file():
        return set()
    try:
        doc = json.loads(_read_text(path))
    except (OSError, json.JSONDecodeError):
        return set()
    out: set[str] = set()
    units = doc.get("units", []) if isinstance(doc, dict) else []
    for item in units if isinstance(units, list) else []:
        if not isinstance(item, dict):
            continue
        for key in ("diagram_source", "source_file", "editable_source", "cover_overlay_source", "cover_background"):
            raw = str(item.get(key) or "").strip().replace("\\", "/")
            if raw:
                out.add(raw)
    return out


def _extract_md_image_paths(path: pathlib.Path) -> set[str]:
    if not path.is_file():
        return set()
    text = _read_text(path)
    out: set[str] = set()
    for match in re.finditer(r"!\[.*?\]\(([^)]+)\)", text):
        out.add(match.group(1).strip())
    for match in re.finditer(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"']", text, flags=re.I):
        out.add(match.group(1).strip())
    return out


def _extract_html_image_paths(path: pathlib.Path) -> set[str]:
    if not path.is_file():
        return set()
    text = _read_text(path)
    return set(re.findall(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"']", text, flags=re.I))


def _extract_sources_json(path: pathlib.Path) -> set[str]:
    if not path.is_file():
        return set()
    try:
        doc = json.loads(_read_text(path))
    except (OSError, json.JSONDecodeError):
        return set()
    out: set[str] = set()
    for item in doc.get("assets", []) if isinstance(doc, dict) else []:
        if isinstance(item, dict):
            raw = str(item.get("path", "")).strip()
            if raw:
                out.add(raw)
    return out


def _extract_brief_yaml(path: pathlib.Path) -> set[str]:
    if not path.is_file():
        return set()
    text = _read_text(path)
    return set(re.findall(r"asset:\s*[\"']?([^\"'\s#]+)[\"']?", text))


def _extract_generation_plan(path: pathlib.Path) -> set[str]:
    """Keep planned source/background/editable assets live during cleanup."""

    if not path.is_file():
        return set()
    try:
        doc = json.loads(_read_text(path))
    except (OSError, json.JSONDecodeError):
        return set()
    out: set[str] = set()

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"asset", "output", "diagram_source", "source_file", "editable_source", "cover_background", "cover_overlay_source", "prompt_file"} and isinstance(item, str):
                    out.add(item.strip())
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(doc)
    return out


def _extract_formula_manifest(path: pathlib.Path) -> set[str]:
    if not path.is_file():
        return set()
    try:
        doc = json.loads(_read_text(path))
    except (OSError, json.JSONDecodeError):
        return set()
    out: set[str] = set()
    for item in doc.get("formulas", []) if isinstance(doc, dict) else []:
        if isinstance(item, dict):
            raw = str(item.get("output", "")).strip()
            if raw:
                out.add(raw)
    return out


def _scan_files(article_dir: pathlib.Path) -> Iterable[pathlib.Path]:
    seen: set[pathlib.Path] = set()
    for sub in ORPHAN_DRY_RUN_DIRS:
        root = article_dir / sub
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path in seen:
                continue
            if path.is_file() and (path.suffix.lower() in RECOGNIZED_IMAGE_EXT or path.suffix == ".tex"):
                seen.add(path)
                yield path


def _normalize(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def check_orphans(article_dir: pathlib.Path) -> tuple[int, list[str]]:
    referenced = {_normalize(p) for p in _collect_index(article_dir)}
    orphans: list[str] = []
    for path in _scan_files(article_dir):
        rel = _normalize(str(path.relative_to(article_dir)))
        # Cover.png is always implicitly referenced (uploaded as thumbnail).
        if rel.endswith("cover.png") or rel.endswith("cover.jpg"):
            continue
        # Formula PNGs are referenced by formula-manifest, but we also allow
        # them via the manifest extraction above; skip if matched.
        if rel in referenced:
            continue
        # Also try without the leading "imgs/" prefix because some configs
        # use one form and HTML another.
        if rel.startswith("imgs/"):
            if rel[len("imgs/"):] in referenced:
                continue
        orphans.append(rel)
    return (0 if not orphans else 1), orphans


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: check_orphan_assets.py <article_dir>", file=sys.stderr)
        return 2
    article_dir = pathlib.Path(sys.argv[1])
    rc, orphans = check_orphans(article_dir)
    if rc == 0:
        print(f"NO ORPHAN ASSETS: {article_dir}")
        return 0
    print(f"ORPHAN ASSETS FOUND ({len(orphans)}):")
    for orphan in orphans:
        print(f"  - {orphan}")
    print(
        "\nFix: delete these files manually, or update the article / "
        "manifest so they are referenced.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
