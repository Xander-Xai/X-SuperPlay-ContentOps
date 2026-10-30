#!/usr/bin/env python3
"""Build and verify a content-addressed visual asset index.

This is deliberately a ledger, not an uploader.  It proves which bytes an
article referenced, records rights/reuse provenance, and de-duplicates the
same bytes across articles.  It never invents a license or treats a URL as a
downloaded local asset.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from workflow_security import load_json as strict_load_json  # noqa: E402
from workspace_paths import artifact_root  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "asset-index-v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    return strict_load_json(path, default=None)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _relative_asset(article: Path, raw: str) -> tuple[str, Path | None, str | None]:
    normalized = str(raw or "").strip().replace("\\", "/")
    if not normalized:
        return "", None, "asset path is empty"
    if normalized.startswith(("http://", "https://", "data:")):
        return normalized, None, None
    candidate = (article / normalized).resolve()
    try:
        relative = candidate.relative_to(article.resolve()).as_posix()
    except ValueError:
        return normalized, None, "asset path escapes article workspace"
    return relative, candidate, None


def _asset_rows(article: Path) -> tuple[list[dict[str, Any]], list[str]]:
    source_path = article / "image-sources.json"
    source_doc = _read_json(source_path)
    errors: list[str] = []
    if not isinstance(source_doc, dict) or not isinstance(source_doc.get("assets"), list):
        return [], ["image-sources.json 缺少 assets 列表"]
    rows: list[dict[str, Any]] = []
    seen_paths: set[str] = set()
    for index, item in enumerate(source_doc["assets"]):
        if not isinstance(item, dict):
            errors.append(f"assets[{index}] 不是对象")
            continue
        raw_path = str(item.get("path") or item.get("asset") or "").strip()
        path, local, path_error = _relative_asset(article, raw_path)
        if path_error:
            errors.append(f"assets[{index}] {path_error}")
            continue
        if path in seen_paths:
            errors.append(f"重复素材路径：{path}")
            continue
        seen_paths.add(path)
        reuse = bool(item.get("reuse_approved", False))
        if reuse and (not str(item.get("source_ref") or "").strip() or not str(item.get("reuse_reason") or "").strip()):
            errors.append(f"复用素材 {path} 缺少 source_ref/reuse_reason")
        record: dict[str, Any] = {
            "path": path,
            "origin": str(item.get("origin") or "unknown"),
            "source": str(item.get("source") or ""),
            "license": str(item.get("license") or ""),
            "reuse_approved": reuse,
            "source_ref": str(item.get("source_ref") or ""),
            "reuse_reason": str(item.get("reuse_reason") or ""),
            "status": "external" if local is None else "verified",
        }
        if local is not None:
            if not local.is_file():
                errors.append(f"素材不存在：{path}")
                record["status"] = "missing"
            else:
                actual = sha256_file(local)
                expected = str(item.get("sha256") or "").strip().lower()
                if expected and expected != actual:
                    errors.append(f"素材哈希不匹配：{path}")
                    record["status"] = "hash_mismatch"
                record.update({"sha256": actual, "bytes": local.stat().st_size})
        else:
            record.update({"sha256": "", "bytes": 0})
        record["asset_id"] = record["sha256"] or hashlib.sha256(path.encode("utf-8")).hexdigest()
        rows.append(record)
    return rows, errors


def build(article: Path, library: Path) -> int:
    rows, errors = _asset_rows(article)
    if errors:
        print("ASSET INDEX BLOCKED:")
        for error in errors:
            print(f"- {error}")
        return 1
    generated = datetime.now(timezone.utc).isoformat()
    article_doc = {
        "schema_version": 1,
        "contract": CONTRACT,
        "status": "passed",
        "article_id": article.name,
        "generated_at": generated,
        "assets": rows,
    }
    _write_json(article / "asset-index.json", article_doc)

    library_doc = _read_json(library)
    if not isinstance(library_doc, dict) or library_doc.get("contract") != CONTRACT:
        library_doc = {"schema_version": 1, "contract": CONTRACT, "assets": []}
    # The library is an active fallback source, not an archive.  Do not let
    # deleted/retired article folders (often old topic-specific diagrams) leak
    # into a new topic's fallback pool.  Explicitly approved reusable assets
    # may remain; all other orphaned article assets are pruned.
    external_active_root = artifact_root(create=False) / "active"
    active_article_ids = {
        item.name for item in external_active_root.iterdir() if item.is_dir()
    } if external_active_root.is_dir() else set()
    existing: dict[str, dict[str, Any]] = {}
    for item in library_doc.get("assets", []):
        if not isinstance(item, dict):
            continue
        asset_id = str(item.get("asset_id") or "").strip()
        article_id = str(item.get("article_id") or "").strip()
        if article_id and article_id not in active_article_ids and not bool(item.get("reuse_approved")):
            continue
        if article_id == article.name:
            # Rebuild the active article's rows from image-sources.json below;
            # stale hashes/candidates from earlier runs must not survive.
            continue
        if asset_id:
            existing[asset_id] = item
    for row in rows:
        item = dict(row)
        item["article_id"] = article.name
        existing[str(row["asset_id"])] = item
    library_doc.update({"schema_version": 1, "contract": CONTRACT, "generated_at": generated, "assets": sorted(existing.values(), key=lambda item: str(item.get("asset_id", "")))})
    _write_json(library, library_doc)
    print(f"ASSET INDEX PASSED: {len(rows)} assets; article=asset-index.json; library={library}")
    return 0


def check(article: Path) -> int:
    expected, errors = _asset_rows(article)
    index = _read_json(article / "asset-index.json")
    if errors:
        print("ASSET INDEX CHECK BLOCKED:")
        for error in errors:
            print(f"- {error}")
        return 1
    if not isinstance(index, dict) or index.get("contract") != CONTRACT or index.get("status") != "passed":
        print("ASSET INDEX CHECK BLOCKED: asset-index.json contract/status 无效")
        return 1
    actual = index.get("assets")
    if not isinstance(actual, list):
        print("ASSET INDEX CHECK BLOCKED: assets 不是列表")
        return 1
    canonical = lambda rows: json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if canonical(expected) != canonical(actual):
        print("ASSET INDEX CHECK BLOCKED: image-sources.json、文件哈希与 asset-index.json 不一致")
        return 1
    print(f"ASSET INDEX CHECK PASSED: {len(actual)} assets")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, type=Path)
    parser.add_argument(
        "--library", type=Path,
        help="素材索引；默认写入外部 artifact root/registry/assets/index.json",
    )
    parser.add_argument("--check", action="store_true", help="只校验，不写入索引")
    args = parser.parse_args()
    article = args.article.expanduser()
    if not article.is_absolute():
        article = ROOT / article
    article = article.resolve()
    library = (args.library or (artifact_root(create=True) / "registry" / "assets" / "index.json")).expanduser()
    if not library.is_absolute():
        library = ROOT / library
    library = library.resolve()
    return check(article) if args.check else build(article, library)


if __name__ == "__main__":
    raise SystemExit(main())
