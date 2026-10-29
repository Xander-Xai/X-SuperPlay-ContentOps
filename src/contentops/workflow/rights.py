"""Rights ledger: every asset names its owner, licence and scope.

The failure this prevents is a video that is technically finished and legally
unpublishable because one clip's origin was never recorded. The ledger is
per-asset, not per-project, and it is checked before delivery.

An asset with an unknown licence is allowed to exist; it is not allowed to be
marked publishable. That distinction keeps research material useful without
letting it leak into a post.
"""

from __future__ import annotations

from typing import Any, Dict, List
from urllib.parse import urlparse

SCHEMA = "contentops.rights-ledger/v1"

PERMISSION_SCOPES = ("publishable", "internal")
LICENCE_STATUSES = ("owned", "licensed", "public_domain", "permission", "unknown")


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _is_http(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def validate_ledger(document: Any) -> List[str]:
    if not isinstance(document, dict):
        return ["rights ledger must be a JSON object"]
    if document.get("schema") != SCHEMA:
        return [f"rights ledger schema must be {SCHEMA!r}"]
    assets = document.get("assets")
    if not isinstance(assets, list) or not assets:
        return ["rights ledger assets must be a non-empty array"]
    errors: List[str] = []
    seen = set()
    for index, asset in enumerate(assets):
        where = f"assets[{index}]"
        if not isinstance(asset, dict):
            errors.append(f"{where} must be an object")
            continue
        asset_id = _text(asset.get("asset_id"))
        if not asset_id:
            errors.append(f"{where}.asset_id must be a non-empty string")
        elif asset_id in seen:
            errors.append(f"{where}.asset_id duplicates {asset_id!r}")
        else:
            seen.add(asset_id)
        owner = _text(asset.get("owner"))
        if not owner:
            errors.append(f"{where}.owner must name the creator or rights holder")
        licence = asset.get("license")
        if licence not in LICENCE_STATUSES:
            errors.append(f"{where}.license must be one of {LICENCE_STATUSES}")
        scope = asset.get("permission_scope")
        if scope not in PERMISSION_SCOPES:
            errors.append(f"{where}.permission_scope must be one of {PERMISSION_SCOPES}")
        source = _text(asset.get("source_url"))
        if source and not (source.startswith("project://") or _is_http(source)):
            errors.append(f"{where}.source_url must be http(s) or project://")
        if scope == "publishable":
            if licence == "unknown":
                errors.append(f"{where} is publishable but its licence is unknown")
            if licence in ("licensed", "permission", "public_domain"):
                if not _is_http(_text(asset.get("license_url"))):
                    errors.append(f"{where} is publishable but has no http(s) license_url")
            if not _text(asset.get("attribution")):
                errors.append(f"{where} is publishable but has no attribution line")
    return errors


def publishable_assets(document: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [asset for asset in (document.get("assets") or [])
            if isinstance(asset, dict) and asset.get("permission_scope") == "publishable"]


def blocked_assets(document: Dict[str, Any]) -> List[str]:
    return [str(asset.get("asset_id")) for asset in (document.get("assets") or [])
            if isinstance(asset, dict)
            and asset.get("permission_scope") == "publishable"
            and asset.get("license") == "unknown"]
