"""Packaging a post for a person, and refusing to be an API.

`MANUAL_ONLY` is the X track's real publication mode, and this module is where
that is made structural rather than promised. :meth:`PublishMode.MANUAL_ONLY`
writes a receipt and returns ``AWAITING_MANUAL_PUBLISH``; there is no branch in
this file that returns ``PUBLISHED``, because nothing here can post.

:meth:`PublishMode.API` exists only so the seam has a name. It raises. An X API
publisher needs a capability spike — tier, OAuth 1.0a media upload, app
permissions — and a credential kept outside the tree; none of that exists, so
none of it is pretended.

The package is the deliverable: the copy with its weighted lengths, the image
with its digest, the ALT text verbatim, and the manual steps that end at a real
status URL. `scripts/x_post.py --mark-published` is the only way a record ever
becomes `published`, and it demands that URL.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from contentops.publish import x_image, x_text
from contentops.publish.x_post import (
    copy_parts,
    post_verdict,
    validate_post,
)

#: What a package receipt declares it is.
PACKAGE_SCHEMA = "contentops.x-publish-package/v1"

#: The only status a package can carry. A person changes the record, not this.
AWAITING = "AWAITING_MANUAL_PUBLISH"

#: The vendor's own two-minute publish test, in order.
MANUAL_STEPS = (
    "Open https://x.com/compose/post and sign in on your own device.",
    "Paste each part in order. Check X's own weighted counter: the lengths in "
    "this package are an estimate and the composer is the authority.",
    "Attach the image, set the ALT text verbatim, then post once.",
    "Copy the real https://x.com/<handle>/status/<id> link and run "
    "`python scripts/x_post.py --mark-published <project> --id <content-id> "
    "--url <status-url>`.",
)


class PublishMode(str, Enum):
    """How a post could leave this repository. Only one of these exists."""

    MANUAL_ONLY = "MANUAL_ONLY"
    API = "API"


class PublisherUnavailable(RuntimeError):
    """A publication mode this repository has not earned the right to use."""


class PackageBlocked(RuntimeError):
    """The record is not ready, so there is nothing honest to package."""


def _now(now: Optional[datetime] = None) -> str:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")


def _resolve(root: Path, value: str) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else root / path


def _image_brief(post: Dict[str, Any], account: Dict[str, Any],
                 project: Path) -> Dict[str, Any]:
    image = post.get("image") or {}
    path = _resolve(project, str(image.get("path") or ""))
    raw = path.read_bytes()
    facts = x_image.image_facts(path)
    try:
        recorded = path.relative_to(project).as_posix()
    except ValueError:
        recorded = str(path)
    return {
        "path": recorded,
        "format": facts.format,
        "width": facts.width,
        "height": facts.height,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def build_package(post: Dict[str, Any], account: Dict[str, Any], project: Path,
                  *, out_dir: Optional[Path] = None,
                  now: Optional[datetime] = None) -> Dict[str, Any]:
    """Assemble the manual publish package and write its receipt.

    Raises :class:`PackageBlocked` when the record is not ``READY``. The returned
    status is always :data:`AWAITING`; this function cannot report a publication.
    """
    project = Path(project)
    verdict = post_verdict(post, account, root=project)
    if verdict not in ("READY", "PUBLISHED"):
        issues = validate_post(post, account, root=project)
        detail = "; ".join(str(issue) for issue in issues) or "no issues were reported"
        raise PackageBlocked(
            f"{post.get('content_id')!r} is {verdict}, not READY: {detail}")

    parts = copy_parts(post)
    lengths = x_text.parts_lengths(parts)
    content_id = str(post.get("content_id") or "x-post")
    budget = int((account.get("editorial") or {}).get("max_chars_per_post") or 280)

    package: Dict[str, Any] = {
        "schema": PACKAGE_SCHEMA,
        "content_id": content_id,
        "account_slug": account.get("slug"),
        "built_at": _now(now),
        "publication_mode": PublishMode.MANUAL_ONLY.value,
        "status": AWAITING,
        "verdict": verdict,
        "label": post.get("label"),
        "proof_grade": post.get("proof_grade"),
        "audience_job": post.get("audience_job"),
        "unique_artifact_ref": post.get("unique_artifact_ref"),
        "experiment_variable": post.get("experiment_variable"),
        "copy": {
            "budget": budget,
            "char_metric": (account.get("editorial") or {}).get("char_metric"),
            "parts": [
                {"index": index, "text": text, "weighted_length": length}
                for index, (text, length) in enumerate(zip(parts, lengths), start=1)
            ],
        },
        "image": _image_brief(post, account, project),
        "alt_text": str(post.get("alt_text") or "").strip(),
        "review": post.get("review"),
        "status_url": post.get("status_url"),
        "skill_route": account.get("skill_route") or [],
        "manual_steps": list(MANUAL_STEPS),
        "cannot": [
            "This package was not submitted to X by this repository.",
            "No API call, token or scheduler was involved.",
            "Nothing here is causal evidence about reach, demand or followers.",
        ],
    }

    receipts = Path(out_dir) if out_dir is not None else project / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    receipt_path = receipts / f"x-package-{content_id}.json"
    try:
        package["receipt"] = receipt_path.relative_to(project).as_posix()
    except ValueError:
        package["receipt"] = str(receipt_path)
    receipt_path.write_text(
        json.dumps(package, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return package


def publish(post: Dict[str, Any], account: Dict[str, Any], project: Path,
            mode: PublishMode = PublishMode.MANUAL_ONLY,
            **kwargs: Any) -> Dict[str, Any]:
    """Package for a person, or refuse. There is no third outcome."""
    if mode is PublishMode.API or mode == PublishMode.API.value:
        raise PublisherUnavailable(
            "X API publishing requires a capability spike (tier, OAuth 1.0a media "
            "upload, app permissions) and a credential outside the tree; MANUAL_ONLY "
            "is the current status")
    return build_package(post, account, project, **kwargs)
