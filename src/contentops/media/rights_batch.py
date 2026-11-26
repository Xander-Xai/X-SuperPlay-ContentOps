"""Group assets that share a source and licence into one rights decision.

A production run lists every asset separately, and the rights gate checks each
one. Asking a person to repeat the same decision once per file is not a
stronger review; it is the same review, copied. This module collects the assets
that a single decision can honestly cover and, once that decision exists,
writes the per-asset record the gate already requires.

What it will not do is decide. A batch with no named decision stays pending,
and applying it writes nothing the gate will accept.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

from contentops.media.rights_gate import RIGHTS_SCHEMA

_BATCH_FIELDS = ("origin", "license", "review_scope", "modifications")


class RightsBatchError(ValueError):
    """A batch was stale, incomplete, or does not match this manifest."""


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _batch_id(key: Dict[str, str], assets: List[Dict[str, Any]]) -> str:
    """Identity of a decision: the shared facts plus every asset hash it covers.

    A changed file changes its hash, which changes the batch, so an earlier
    decision cannot be reused against bytes it never named.
    """
    payload = dict(key)
    payload["assets"] = sorted(
        (str(asset.get("id")), str(asset.get("sha256"))) for asset in assets)
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def review_batch(manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Group a manifest's assets by the facts one decision can cover.

    Every batch comes back ``PENDING_HUMAN_REVIEW``. Grouping is not a
    decision, and this function records none.
    """
    groups: Dict[tuple, List[Dict[str, Any]]] = {}
    for asset in manifest.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        key = tuple(_text(asset.get(field)) for field in _BATCH_FIELDS)
        groups.setdefault(key, []).append(asset)

    batches = []
    for key, assets in groups.items():
        shared = dict(zip(_BATCH_FIELDS, key))
        batches.append({
            "batch_id": _batch_id(shared, assets),
            "license": shared["license"],
            "source_url": shared["origin"],
            "review_scope": shared["review_scope"],
            "modifications": shared["modifications"],
            "asset_ids": [str(asset.get("id")) for asset in assets],
            "sha256": {str(asset.get("id")): str(asset.get("sha256")) for asset in assets},
            "decision": "PENDING_HUMAN_REVIEW",
        })
    return batches


def apply_batch_decision(project: Path,
                         manifest: Dict[str, Any],
                         batches: List[Dict[str, Any]],
                         decisions: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    """Attach a named decision to the assets its batch covers.

    A batch with no decision is returned unchanged: asking for a review is not
    the review. The record written is the one ``validate_declared_asset``
    already checks, so this adds no second rights path.
    """
    current_batches = review_batch(manifest)
    current_by_id = {batch["batch_id"]: batch for batch in current_batches}
    submitted_by_id = {batch.get("batch_id"): batch for batch in batches}
    if len(submitted_by_id) != len(batches) or set(submitted_by_id) != set(current_by_id):
        raise RightsBatchError("stale rights batch set; rebuild the review from current assets")
    for batch_id, current in current_by_id.items():
        submitted = submitted_by_id[batch_id]
        if any(submitted.get(field) != current.get(field)
               for field in ("asset_ids", "sha256", "source_url", "license",
                             "review_scope", "modifications")):
            raise RightsBatchError("stale rights batch contents; rebuild the review")
    if set(decisions) - set(current_by_id):
        raise RightsBatchError("decision references an unknown or stale rights batch")
    for batch_id, decision in decisions.items():
        if not all(_text(decision.get(field))
                   for field in ("reviewer", "reviewed_at", "attribution")):
            raise RightsBatchError(f"batch {batch_id} decision needs reviewer, date, and attribution")

    by_id = current_by_id
    asset_batch = {}
    for batch in current_batches:
        for asset_id in batch["asset_ids"]:
            asset_batch[asset_id] = batch["batch_id"]

    updated = dict(manifest)
    updated["assets"] = []
    for asset in manifest.get("assets") or []:
        asset = dict(asset)
        batch_id = asset_batch.get(str(asset.get("id")))
        decision = decisions.get(batch_id) if batch_id else None
        if decision:
            batch = by_id[batch_id]
            relative = f"assets/{asset['id']}.rights.json"
            record = {
                "schema": RIGHTS_SCHEMA,
                "license_id": batch["license"],
                "source_url": batch["source_url"],
                "license_url": _text(asset.get("license_url")),
                "reviewed_by": decision["reviewer"].strip(),
                "reviewed_at": decision["reviewed_at"].strip(),
                "attribution": decision["attribution"].strip(),
                "synthetic": False,
                "asset_id": str(asset.get("id")),
                "asset_sha256": str(asset.get("sha256")),
                "review_batch_id": batch_id,
                "review_scope": batch["review_scope"],
                "modifications": batch["modifications"],
            }
            path = Path(project) / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
            asset["rights"] = {
                "schema": "contentops.media-rights/v1",
                "license_id": record["license_id"],
                "source_url": record["source_url"],
                "reviewed_by": record["reviewed_by"],
                "reviewed_at": record["reviewed_at"],
                "review_evidence": relative,
                "attribution": record["attribution"],
                "synthetic": False,
                "review_batch_id": batch_id,
                "review_scope": batch["review_scope"],
                "modifications": batch["modifications"],
            }
            asset["rights_review_status"] = "REVIEWED"
            asset["rights_review_record"] = relative
        updated["assets"].append(asset)
    return updated
