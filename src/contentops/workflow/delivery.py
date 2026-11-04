"""Delivery manifest: what a manual package contains, and what it may not claim.

The repository stops one step before a platform. A delivery manifest records the
reviewed package, its digest, the target platform and the reviewer, and it
always starts at ``AWAITING_MANUAL_REVIEW``. It cannot contain a platform URL
until a person has actually published and recorded one separately.

This module is the contract for that last step. It is deliberately inert: no
API call, no upload, no account, no metric.

What is not claimed
-------------------
A manifest is not a publication. It does not prove a post exists, and a
reviewed package is not a platform acceptance. ``REVIEWED`` means a person
signed the package, not that the platform accepted it.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, Optional

from .contract import WorkflowError

SCHEMA = "contentops.delivery-manifest/v1"

STATUSES = ("AWAITING_MANUAL_REVIEW", "REVIEWED", "REJECTED")

#: A URL may only appear after an external publication was observed. The
#: manifest records it as reported, never as verified by this repository.
URL_STATES = ("REPORTED_PUBLISHED", "VERIFIED_PUBLISHED")


def build_manifest(project: str, package_path: Path, *, platform: str,
                   package_sha256: Optional[str] = None,
                   reviewer: Optional[str] = None,
                   review_receipt: Optional[str] = None) -> Dict[str, Any]:
    """Build a delivery manifest for a package that is ready for a human.

    Without a reviewer the status is ``AWAITING_MANUAL_REVIEW``; with one, it is
    ``REVIEWED`` only when a review receipt is also named. No URL is written.
    """
    path = Path(package_path)
    if package_sha256 is None:
        try:
            package_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError:
            raise WorkflowError("DELIVERY_PACKAGE_MISSING", str(path))
    if not package_sha256:
        raise WorkflowError("DELIVERY_DIGEST", "a package digest is required")
    review = str(reviewer or "").strip()
    status = "REVIEWED" if review else "AWAITING_MANUAL_REVIEW"
    if status == "REVIEWED" and not str(review_receipt or "").strip():
        raise WorkflowError(
            "DELIVERY_REVIEW_RECEIPT",
            "REVIEWED requires a review receipt; a reviewer name alone is not a review",
        )
    return {
        "schema": SCHEMA,
        "project": project,
        "platform": str(platform or "").strip().lower(),
        "package_sha256": package_sha256,
        "status": status,
        "reviewer": review or None,
        "review_receipt": str(review_receipt or "").strip() or None,
        "platform_url": None,
        "publication_state": None,
        "publish_authorized": False,
        "production_ready": False,
        "note": "manual delivery only; a URL is recorded separately after publication",
    }


def record_reported_publication(manifest: Dict[str, Any], url: str, *,
                                state: str = "REPORTED_PUBLISHED") -> Dict[str, Any]:
    """Record a URL a human reports publishing; this never verifies it."""
    if state not in URL_STATES:
        raise WorkflowError("DELIVERY_URL_STATE", f"{state!r} is not one of {', '.join(URL_STATES)}")
    if manifest.get("status") != "REVIEWED":
        raise WorkflowError("DELIVERY_NOT_REVIEWED", "a publication cannot be recorded before review")
    text = str(url or "").strip()
    if not text:
        raise WorkflowError("DELIVERY_URL_MISSING", "a reported publication needs a URL")
    updated = dict(manifest)
    updated["platform_url"] = text
    updated["publication_state"] = state
    # Recording a URL still grants nothing; the flags stay false.
    updated["publish_authorized"] = False
    updated["production_ready"] = False
    return updated


def validate_manifest(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise WorkflowError("DELIVERY_SCHEMA", f"expected schema {SCHEMA}")
    if payload.get("status") not in STATUSES:
        raise WorkflowError("DELIVERY_STATUS", str(payload.get("status")))
    if payload.get("status") == "REVIEWED" and not payload.get("review_receipt"):
        raise WorkflowError("DELIVERY_REVIEW_RECEIPT", "REVIEWED requires a review receipt")
    if payload.get("publish_authorized") is not False:
        raise WorkflowError("DELIVERY_AUTHORITY", "a manifest may not authorize publication")
    if payload.get("production_ready") is not False:
        raise WorkflowError("DELIVERY_PRODUCTION_READY", "a manifest may not claim production readiness")
    if payload.get("publication_state") not in (None,) + URL_STATES:
        raise WorkflowError("DELIVERY_URL_STATE", str(payload.get("publication_state")))
    if payload.get("publication_state") and not payload.get("platform_url"):
        raise WorkflowError("DELIVERY_URL_MISSING", "a publication state needs a URL")
    return payload
