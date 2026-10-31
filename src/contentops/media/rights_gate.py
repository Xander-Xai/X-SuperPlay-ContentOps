"""Fail-closed rights validation for media entering the M5 production chain.

This module is a policy gate, not an asset registry and not a licence
verifier. It answers one question before any media-use adapter call: does this
request carry a complete, internally consistent, traceable rights record whose
declared licence permits production use?

It cannot prove that the declared licence is the asset's actual licence. That
remains a human decision. What it does prove is that nobody can enter production
with a bare ``rights_reviewed: true`` self-declaration, an unknown licence, a
software licence misapplied to media, or a review record that does not match
the request. Everything not proven is refused.

Licence policy is a small table below. It is deliberately *not* a list of
assets, so it does not become a second registry.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict

RIGHTS_SCHEMA = "contentops.media-rights-review/v1"
RIGHTS_CLAIM_SCHEMA = "contentops.media-rights/v1"


class RightsError(ValueError):
    """A media request cannot prove its rights; the caller must fail closed."""


# third_party: the asset comes from outside the operator's own authorship.
# attribution_required: the licence obliges credit in the produced work.
# synthetic_allowed: generated material may declare this licence (and is never
#                    evidence).
LICENCES: Dict[str, Dict[str, Any]] = {
    "OWNED-BY-OPERATOR": {
        "third_party": False, "attribution_required": False, "synthetic_allowed": False,
        "note": "captured or authored by the operator; ownership still needs a review record",
    },
    "OWNED-GENERATED-LOCAL": {
        "third_party": False, "attribution_required": False, "synthetic_allowed": True,
        "note": "generated deterministically on this machine; never evidence",
    },
    "CC0-1.0": {
        "third_party": True, "attribution_required": False, "synthetic_allowed": False,
        "note": "public-domain dedication",
    },
    "CC-BY-4.0": {
        "third_party": True, "attribution_required": True, "synthetic_allowed": False,
        "note": "attribution required",
    },
    "Pixabay-Content-License": {
        "third_party": True, "attribution_required": False, "synthetic_allowed": False,
        "note": "free commercial use; no standalone redistribution; attribution appreciated",
    },
    "Pexels-License": {
        "third_party": True, "attribution_required": False, "synthetic_allowed": False,
        "note": "free use; no standalone redistribution; attribution appreciated",
    },
    "Unsplash-License": {
        "third_party": True, "attribution_required": False, "synthetic_allowed": False,
        "note": "free use; no compiling a competing service",
    },
}

SOFTWARE_LICENCES = {
    "apache-2.0", "mit", "bsd-2-clause", "bsd-3-clause", "isc", "mpl-2.0",
    "gpl-2.0", "gpl-2.0-only", "gpl-2.0-or-later", "gpl-3.0", "gpl-3.0-only",
    "gpl-3.0-or-later", "agpl-3.0", "agpl-3.0-only", "agpl-3.0-or-later",
    "lgpl-2.1", "lgpl-3.0",
}

NONCOMMERCIAL_PREFIXES = ("CC-BY-NC", "CC-BY-ND", "CC-BY-NC-SA", "CC-BY-NC-ND")

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_URL = re.compile(r"^https?://[^\s]+$")


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _policy(license_id: str) -> Dict[str, Any]:
    key = _text(license_id)
    if not key:
        raise RightsError("rights.license_id is required")
    lowered = key.lower()
    if lowered in SOFTWARE_LICENCES:
        raise RightsError(
            f"{key} is a software licence and cannot license media; "
            "use the media asset's own licence"
        )
    if lowered.upper().startswith(NONCOMMERCIAL_PREFIXES):
        raise RightsError(f"{key} is non-commercial and cannot enter production output")
    policy = LICENCES.get(key)
    if policy is None:
        raise RightsError(f"unknown media licence {key!r}; add it to the reviewed policy first")
    return policy


def _inside(project_dir: Path, relative: str) -> Path:
    candidate = (project_dir / relative).resolve()
    try:
        candidate.relative_to(project_dir.resolve())
    except ValueError:
        raise RightsError(f"rights record {relative!r} lies outside the project")
    return candidate


def _load_record(path: Path) -> Dict[str, Any]:
    if not path.is_file():
        raise RightsError(f"rights review record is missing: {path.name}")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RightsError(f"rights review record is unreadable: {path.name}") from exc
    if not isinstance(record, dict) or record.get("schema") != RIGHTS_SCHEMA:
        raise RightsError(f"rights review record {path.name} is not {RIGHTS_SCHEMA}")
    return record


def _check_equal(label: str, claimed: Any, recorded: Any) -> None:
    if _text(claimed) != _text(recorded):
        raise RightsError(f"rights.{label} does not match the review record")


def validate_request_rights(
    request: Dict[str, Any], project_dir: Path
) -> Dict[str, Any]:
    """Return a normalised rights record or raise ``RightsError``.

    A bare ``rights_reviewed: true`` is never sufficient: the request must carry
    a ``rights`` mapping and a committed review record whose fields agree with
    the request.
    """
    rights = request.get("rights")
    if not isinstance(rights, dict) or not rights:
        raise RightsError(
            "a rights block is required; a bare rights_reviewed flag is a "
            "self-declaration, not reviewable evidence"
        )
    if rights.get("schema") not in (None, RIGHTS_CLAIM_SCHEMA):
        raise RightsError(f"rights.schema must be {RIGHTS_CLAIM_SCHEMA}")

    license_id = _text(rights.get("license_id"))
    policy = _policy(license_id)

    declared_license = _text(request.get("license"))
    if declared_license and declared_license != license_id:
        raise RightsError(
            f"request license {declared_license!r} disagrees with "
            f"rights.license_id {license_id!r}"
        )

    evidence_rel = _text(rights.get("review_evidence"))
    if not evidence_rel:
        raise RightsError("rights.review_evidence is required")
    evidence_path = _inside(project_dir, evidence_rel)
    record = _load_record(evidence_path)

    _check_equal("license_id", license_id, record.get("license_id"))
    source_url = _text(rights.get("source_url")) or _text(record.get("source_url"))
    if not source_url:
        raise RightsError("rights.source_url is required")
    _check_equal("source_url", source_url, record.get("source_url"))
    if policy["third_party"] and not _URL.match(source_url):
        raise RightsError(
            "a third-party asset needs an http(s) source_url; a name alone is not traceable"
        )

    reviewed_by = _text(rights.get("reviewed_by")) or _text(record.get("reviewed_by"))
    if not reviewed_by:
        raise RightsError("rights.reviewed_by is required")
    _check_equal("reviewed_by", reviewed_by, record.get("reviewed_by"))

    reviewed_at = _text(rights.get("reviewed_at")) or _text(record.get("reviewed_at"))
    if not _DATE.match(reviewed_at):
        raise RightsError("rights.reviewed_at must be an ISO date (YYYY-MM-DD)")
    try:
        if date.fromisoformat(reviewed_at) > date.today():
            raise RightsError("rights.reviewed_at cannot be in the future")
    except ValueError as exc:
        raise RightsError("rights.reviewed_at is not a valid date") from exc
    _check_equal("reviewed_at", reviewed_at, record.get("reviewed_at"))

    attribution = _text(rights.get("attribution")) or _text(record.get("attribution"))
    _check_equal("attribution", attribution, record.get("attribution"))
    if policy["attribution_required"] and not attribution:
        raise RightsError(f"{license_id} requires attribution in the produced work")

    synthetic = bool(rights.get("synthetic", False))
    if bool(record.get("synthetic", False)) != synthetic:
        raise RightsError("rights.synthetic does not match the review record")
    if synthetic and not policy["synthetic_allowed"]:
        raise RightsError(f"{license_id} cannot be declared synthetic")

    if rights.get("rights_reviewed") is not None and rights.get("rights_reviewed") is not True:
        raise RightsError("rights.rights_reviewed must be true when present")

    digest = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    return {
        "schema": RIGHTS_CLAIM_SCHEMA,
        "license_id": license_id,
        "license_note": policy["note"],
        "source_url": source_url,
        "reviewed_by": reviewed_by,
        "reviewed_at": reviewed_at,
        "review_evidence": evidence_rel,
        "review_evidence_sha256": digest,
        "attribution": attribution,
        "synthetic": synthetic,
        "third_party": policy["third_party"],
        "evidence_capable": False,
    }


def license_policy(license_id: str) -> Dict[str, Any]:
    """Public, read-only view of the media licence policy.

    Raises :class:`RightsError` for unknown, software and non-commercial
    licences, exactly like :func:`validate_request_rights`.
    """
    return dict(_policy(license_id))


def validate_declared_asset(asset: Dict[str, Any], project_dir: Path) -> Dict[str, Any]:
    """Validate a ``sources/assets.json`` entry against the same policy.

    Owned entries (``OWNED`` / ``CREATED_BY_OWNER``) keep their existing trust
    semantics: they need no third-party URL. Any entry carrying a ``rights``
    block is validated exactly like a media_use request, so a third-party
    ``LICENSED`` entry cannot reach production with only a permission label.
    """
    permission = _text(asset.get("permission"))
    rights = asset.get("rights")
    if isinstance(rights, dict) and rights:
        request = {"license": _text(asset.get("license")), "rights": rights}
        return validate_request_rights(request, project_dir)
    if permission in {"OWNED", "CREATED_BY_OWNER"}:
        return {
            "schema": RIGHTS_CLAIM_SCHEMA,
            "license_id": _text(asset.get("license")) or permission,
            "third_party": False,
            "synthetic": False,
            "evidence_capable": False,
        }
    raise RightsError(
        f"a {permission or 'missing'} asset needs a rights block and a review "
        "record; a permission label alone is not a rights review")
