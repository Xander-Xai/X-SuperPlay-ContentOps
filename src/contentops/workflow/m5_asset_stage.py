"""M5 visual-asset verification stage, extracted without changing the evidence contract.

The original m5_production.stage_assets API remains as a facade. All
permissions, path containment, source hashes, rights policy and receipt
writing are delegated to the exact existing dependencies, not copied.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


def stage_assets(project: Path, extra_assets: Optional[Dict[str, Dict[str, Any]]] = None, *,
                 repo_root: Path, blocked_error: type[Exception], file_sha: Any,
                 validate_rights: Any, rights_error_type: type[Exception],
                 write_json: Any) -> Dict[str, Any]:
    """Check every declared visual against its recorded hash before it is used."""
    from contentops.media.local_assets import is_valid_local_preview_asset

    manifest_path = project / "sources" / "assets.json"
    if not manifest_path.is_file():
        raise blocked_error("sources/assets.json is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    verified = {}
    problems = []
    generated = list((extra_assets or {}).values())
    declared = list(manifest.get("assets") or [])
    all_ids = [str(asset.get("id")) for asset in declared + generated]
    if len(all_ids) != len(set(all_ids)):
        raise blocked_error("duplicate declared/media-use asset id")
    root = repo_root.resolve()
    for asset in declared + generated:
        path = (root / asset["repo_path"]).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            problems.append(f"{asset['id']}: path escapes the repository: {asset['repo_path']}")
            continue
        if not path.is_file():
            problems.append(f"{asset['id']}: file missing: {asset['repo_path']}")
            continue
        actual = file_sha(path)
        if actual != asset.get("sha256"):
            problems.append(f"{asset['id']}: sha256 {actual[:12]} != recorded {str(asset.get('sha256'))[:12]}")
            continue
        local_preview = is_valid_local_preview_asset(asset, project, repo_root)
        if (asset.get("permission") not in {"OWNED", "CREATED_BY_OWNER", "LICENSED"}
                and not local_preview):
            problems.append(f"{asset['id']}: permission {asset.get('permission')} is not usable")
            continue
        if not local_preview:
            try:
                validate_rights(asset, project)
            except rights_error_type as exc:
                problems.append(f"{asset['id']}: {exc}")
                continue
        verified[asset["id"]] = {**asset, "verified_sha256": actual}
    payload = {
        "schema": "contentops.m5-assets-check/v1",
        "ok": not problems,
        "problems": problems,
        "assets": len(verified),
    }
    write_json(project / "receipts" / "asset-manifest.json", payload)
    if problems:
        raise blocked_error("; ".join(problems[:4]))
    return verified
