#!/usr/bin/env python3
"""Build the per-article art-direction sidecar.

This is intentionally a planning artifact, not a renderer.  It gives the
visual director a style thesis and anti-template constraints while preserving
the existing visual contract and deterministic backends.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STYLES = ROOT / "profiles" / "visual-styles.yaml"


def _yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore
    except Exception as exc:  # pragma: no cover - runtime dependency is already used by the workflow
        raise RuntimeError("需要 PyYAML 才能生成 art-direction.yaml") from exc
    if not path.is_file():
        return {}
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return value if isinstance(value, dict) else {}


def _write_yaml(path: Path, value: dict[str, Any]) -> None:
    import yaml  # type: ignore

    path.write_text(yaml.safe_dump(value, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def canonical_visual_brief_sha(article_dir: Path) -> str:
    """Hash visual intent, excluding mutable cover approval metadata."""
    brief_path = article_dir.resolve() / "visual-brief.yaml"
    brief = _yaml(brief_path)
    if not brief:
        return ""
    brief = dict(brief)
    brief.pop("approval", None)
    try:
        import yaml  # type: ignore

        raw = yaml.safe_dump(brief, allow_unicode=True, sort_keys=True).encode("utf-8")
    except Exception:
        raw = json.dumps(brief, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_art_direction(article_dir: Path, *, overwrite: bool = False) -> Path:
    article_dir = article_dir.resolve()
    brief_path = article_dir / "visual-brief.yaml"
    brief = _yaml(brief_path)
    if not brief:
        raise ValueError(f"缺少 visual-brief.yaml：{article_dir}")
    output = article_dir / "art-direction.yaml"
    if output.is_file() and not overwrite:
        return output

    account = str(brief.get("account") or "thinktank")
    title = str(brief.get("title") or article_dir.name)
    styles = _yaml(STYLES)
    account_cfg = styles.get("accounts", {}).get(account, {}) if isinstance(styles.get("accounts"), dict) else {}
    tokens = account_cfg.get("design_tokens", {}) if isinstance(account_cfg, dict) else {}
    if not isinstance(tokens, dict):
        tokens = {}
    visual_direction = str(brief.get("art_direction") or account_cfg.get("art_direction") or "证据优先的编辑型技术视觉")
    body = brief.get("body_visuals") if isinstance(brief.get("body_visuals"), list) else []
    route_families = []
    for item in body:
        if not isinstance(item, dict):
            continue
        family = str(item.get("layout_archetype") or item.get("visual_type") or "editorial-structure").strip()
        if family and family not in route_families:
            route_families.append(family)
    if not route_families:
        route_families = ["editorial-split", "evidence-structure"]

    payload = {
        "schema_version": 1,
        "contract": "art-direction-v1",
        "status": "proposed",
        "owner": "gzh-visual-director",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "article_title": title,
        "account": account,
        "visual_thesis": f"{visual_direction}；本篇不把每个认知锚点都画成等宽卡片，而是用结构差异帮助读者完成理解。",
        "reader_promise": "读者在 390px 宽度下先抓住主论点，再沿证据路径回到正文与代码。",
        "palette": {
            "background": str(tokens.get("background") or "#F4F0E8"),
            "surface": str(tokens.get("surface") or "#FFFCF7"),
            "ink": str(tokens.get("ink") or "#17324D"),
            "accent": str(tokens.get("vermilion") or tokens.get("accent") or "#B24A2B"),
            "signal": str(tokens.get("signal") or "#557A96"),
        },
        "material_language": ["paper-grain restraint", "thin editorial rules", "one signal accent", "asymmetric whitespace"],
        "layout_families": route_families + ["editorial-split", "hand-drawn-flow", "evidence-strip"],
        "continuity_group": "thinktank-editorial-visual-system-v2",
        "anti_patterns": [
            "uniform-card-grid",
            "centered-title-plus-two-row-boxes",
            "generic-ai-gradient",
            "generated-long-text",
            "decorative-visual-without-reader-job",
        ],
        "variation_policy": {
            "max_same_layout_run": 2,
            "min_layout_families_when_body_visuals_gte_3": 2,
            "min_backend_families_when_body_visuals_gte_3": 2,
            "prefer_different_composition": True,
        },
        "references": [],
        "data_egress": "none-unless-explicitly-approved",
        "fallback_policy": {
            "technical_visual": "block-on-render-or-geometry-failure",
            "cover": "brand-cover-only-with-explicit-fallback-reason",
            "concept_visual": "deterministic-local-illustration-or-block",
        },
        "source_visual_brief_sha256": canonical_visual_brief_sha(article_dir),
    }
    _write_yaml(output, payload)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    path = build_art_direction(args.article, overwrite=args.overwrite)
    print(f"ART DIRECTION READY: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
