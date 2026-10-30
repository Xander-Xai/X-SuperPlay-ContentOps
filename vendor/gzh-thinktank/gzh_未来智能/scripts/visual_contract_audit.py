#!/usr/bin/env python3
"""Cross-check visual routing, contract, provenance and rendered metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def _size(path: Path) -> tuple[int, int] | None:
    try:
        from PIL import Image  # type: ignore

        with Image.open(path) as image:
            return int(image.width), int(image.height)
    except Exception:
        return None


def audit(article_dir: Path, *, write: bool = True) -> dict[str, Any]:
    article_dir = article_dir.resolve()
    brief_path = article_dir / "visual-brief.yaml"
    try:
        import yaml  # type: ignore

        brief_value = yaml.safe_load(brief_path.read_text(encoding="utf-8")) if brief_path.is_file() else {}
    except Exception:
        brief_value = {}
    brief = brief_value if isinstance(brief_value, dict) else {}
    routing = _load_json(article_dir / "visual-routing.json")
    contract = _load_json(article_dir / "visual-contract.json")
    sources = _load_json(article_dir / "image-sources.json")
    warnings: list[str] = []
    errors: list[str] = []
    brief_by_id = {str(item.get("id")): item for item in brief.get("body_visuals", []) if isinstance(item, dict)}
    route_by_id = {str(item.get("id")): item for item in routing.get("routes", []) if isinstance(item, dict)}
    contract_by_id = {str(item.get("id")): item for item in contract.get("units", []) if isinstance(item, dict)}

    ids = sorted(set(brief_by_id) | set(route_by_id) | set(contract_by_id))
    records: list[dict[str, Any]] = []
    for ident in ids:
        b, r, c = brief_by_id.get(ident, {}), route_by_id.get(ident, {}), contract_by_id.get(ident, {})
        record = {"id": ident, "checks": {}}
        for field in ("route_rule", "layout_archetype", "recommended_skill"):
            bv, rv = str(b.get(field) or ""), str(r.get(field) or "")
            if bv and rv and bv != rv:
                errors.append(f"{ident} {field} 不一致：visual-brief={bv!r} vs visual-routing={rv!r}")
            record["checks"][field] = {"brief": bv, "routing": rv}
        bclaims = sorted(str(v) for v in b.get("claim_ids", []) if str(v).strip())
        cclaims = sorted(str(v) for v in c.get("claim_ids", []) if str(v).strip())
        if bclaims != cclaims:
            errors.append(f"{ident} claim_ids 不一致：visual-brief={bclaims} vs visual-contract={cclaims}")
        record["checks"]["claim_ids"] = {"brief": bclaims, "contract": cclaims}
        execution = str(c.get("execution_backend") or c.get("render_backend") or "")
        requested = str(c.get("requested_backend") or c.get("render_backend") or "")
        primary = str(r.get("primary_backend") or "")
        if primary and execution and primary != execution:
            warnings.append(f"{ident} evaluated/requested/execution backend 语义不同：primary={primary}, execution={execution}")
        record["checks"]["backend"] = {"requested": requested, "routing_primary": primary, "execution": execution}
        records.append(record)

    source_by_path = {str(item.get("path")): item for item in sources.get("assets", []) if isinstance(item, dict)}
    for raw, item in source_by_path.items():
        if not raw or raw.startswith(("http://", "https://", "data:")):
            continue
        path = (article_dir / raw.replace("\\", "/")).resolve()
        actual = _size(path)
        generation = item.get("generation") if isinstance(item.get("generation"), dict) else {}
        declared = str(generation.get("size") or "")
        if actual and declared and "x" in declared.lower():
            try:
                dw, dh = [int(part) for part in declared.lower().split("x", 1)]
                if (dw, dh) != actual:
                    errors.append(f"{raw} 尺寸 metadata 不一致：declared={dw}x{dh}, actual={actual[0]}x{actual[1]}")
            except ValueError:
                warnings.append(f"{raw} generation.size 无法解析：{declared}")
        if actual:
            item.setdefault("actual_width", actual[0])
            item.setdefault("actual_height", actual[1])
            item["actual_sha256"] = _sha256(path)
    result = {
        "schema_version": 1,
        "contract": "visual-contract-audit-v1",
        "status": "blocked" if errors else ("warning" if warnings else "passed"),
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "records": records,
        "warnings": warnings,
        "errors": errors,
        "source_hashes": {name: _sha256(article_dir / name) for name in ("visual-brief.yaml", "visual-routing.json", "visual-contract.json", "image-sources.json")},
    }
    if write:
        (article_dir / "visual-contract-audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if sources.get("assets"):
            (article_dir / "image-sources.json").write_text(json.dumps(sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, type=Path)
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()
    result = audit(args.article, write=not args.no_write)
    print(json.dumps({"status": result["status"], "warnings": result["warnings"], "errors": result["errors"]}, ensure_ascii=False))
    return 1 if result["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
