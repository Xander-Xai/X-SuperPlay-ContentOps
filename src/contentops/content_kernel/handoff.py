"""Turn one Strategy Content Bundle into a form-specific production handoff.

A Bundle says what the content is about and which account treatment it serves.
It does not say that a video or an article has been produced. This module creates
the small, hash-bound record that lets one Bundle enter either production line,
and records the platform as a delivery placeholder rather than an executable
capability.

Nothing here publishes, renders, spends or approves. A handoff is a plan.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .bundle import BundleError, load_bundle, validate_bundle

HANDOFF_SCHEMA = "contentops.bundle-handoff/v1"
VIDEO = "VIDEO"
GRAPHIC_TEXT = "GRAPHIC_TEXT"
FORMATS: Tuple[str, ...] = (VIDEO, GRAPHIC_TEXT)
READY_VIDEO = "READY_FOR_PRODUCTION"
READY_GRAPHIC = "READY_FOR_MANUAL_PACKAGE"
SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,120}$")


class HandoffError(ValueError):
    """A Bundle cannot enter a production line, with a stable reason code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


def _canonical(value: Any) -> str:
    if isinstance(value, dict):
        value = {key: value[key] for key in sorted(value)}
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def bundle_digest(document: Dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(document).encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_slug(value: Any) -> str:
    slug = str(value or "").strip()
    if not SLUG.match(slug):
        raise HandoffError("PROJECT_SLUG_INVALID",
                           "project_slug must be a relative slug (letters, digits, . _ -)")
    return slug


def _source_map(value: Any) -> Dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise HandoffError("SOURCE_MAP_REQUIRED",
                           "source_map must map Strategy source ids to ContentOps source ids")
    result: Dict[str, str] = {}
    for key, item in value.items():
        key_text = str(key or "").strip()
        item_text = str(item or "").strip()
        if not key_text or not item_text:
            raise HandoffError("SOURCE_MAP_INVALID", "source_map keys and values must be non-empty")
        if not _identifier_ok(key_text) or not _identifier_ok(item_text):
            raise HandoffError("SOURCE_MAP_INVALID",
                               f"{key_text!r} -> {item_text!r} must be identifiers, not paths")
        result[key_text] = item_text
    return result


def _identifier_ok(value: str) -> bool:
    return bool(IDENTIFIER.match(value))


def _platform(registry_root: Optional[Path], platform_id: Optional[str],
              content_format: str) -> Optional[Dict[str, Any]]:
    if not platform_id:
        return None
    if registry_root is None:
        return {"platform_id": platform_id, "status": "UNVERIFIED", "delivery": "UNVERIFIED"}
    # Imported lazily so a Bundle handoff does not require the registry on every
    # use, and so the registry remains the only platform source.
    from contentops.platforms import RegistryError, load_platforms

    try:
        entries = load_platforms(Path(registry_root))
    except RegistryError as exc:
        raise HandoffError("PLATFORM_REGISTRY_INVALID", exc.detail) from None
    entry = entries.get(platform_id)
    if entry is None:
        raise HandoffError("PLATFORM_UNKNOWN", f"{platform_id!r} is not registered")
    expected = "VIDEO" if content_format == VIDEO else "EDITORIAL"
    if expected == "VIDEO" and entry.pipeline != "VIDEO":
        raise HandoffError("PLATFORM_FORMAT_MISMATCH",
                           f"{platform_id} serves {entry.pipeline}, not VIDEO")
    if expected == "EDITORIAL" and entry.pipeline == "VIDEO":
        raise HandoffError("PLATFORM_FORMAT_MISMATCH",
                           f"{platform_id} serves VIDEO, not graphic text")
    return {
        "platform_id": entry.platform_id,
        "strategy_platform": entry.strategy_platform,
        "pipeline": entry.pipeline,
        "status": entry.status,
        "delivery": "PLACEHOLDER" if entry.status == "PLANNED" else "MANUAL_PACKAGE_ONLY",
        "not_claimed": entry.not_claimed,
    }


def build_handoff(
    bundle: Dict[str, Any],
    account: str,
    content_format: str,
    *,
    project_slug: str,
    source_map: Dict[str, str],
    platform_id: Optional[str] = None,
    registry_root: Optional[Path] = None,
    host_capability: str = "UNVERIFIED",
) -> Dict[str, Any]:
    """Validate a Bundle and return a form-specific handoff record."""
    failures = validate_bundle(bundle)
    if failures:
        raise HandoffError("BUNDLE_INVALID", "; ".join(failures))
    if content_format not in FORMATS:
        raise HandoffError("FORMAT_UNKNOWN", f"{content_format!r} is not one of {list(FORMATS)}")
    treatments = bundle.get("account_treatments") or {}
    treatment = treatments.get(account)
    if not isinstance(treatment, dict):
        raise HandoffError("ACCOUNT_TREATMENT_MISSING",
                           f"{account!r} is not an account treatment in this Bundle")
    mapping = _source_map(source_map)
    source = bundle.get("source") or {}
    source_id = str(source.get("source_id") or "")
    if source_id not in mapping:
        raise HandoffError("SOURCE_MAP_INCOMPLETE",
                           f"source_map must include the Bundle source {source_id!r}")
    slug = _safe_slug(project_slug)
    platform = _platform(registry_root, platform_id, content_format)

    blockers: List[str] = []
    if platform and platform.get("delivery") == "PLACEHOLDER":
        blockers.append("PLATFORM_PLACEHOLDER")
    if content_format == GRAPHIC_TEXT and host_capability == "UNVERIFIED":
        blockers.append("HOST_CAPABILITY_UNVERIFIED")

    state = READY_VIDEO if content_format == VIDEO else READY_GRAPHIC
    return {
        "schema": HANDOFF_SCHEMA,
        "bundle_id": bundle.get("bundle_id"),
        "bundle_sha256": bundle_digest(bundle),
        "source_id": source_id,
        "source_map": {key: mapping[key] for key in sorted(mapping)},
        "account": account,
        "role": treatment.get("role"),
        "production_lane": treatment.get("production_lane"),
        "execution_profile_hint": treatment.get("execution_profile_hint", "default"),
        "content_format": content_format,
        "project_slug": slug,
        "platform": platform,
        "host_capability": host_capability,
        "state": state,
        "blockers": blockers,
        "production_ready": False,
        "human_review": "NOT_STARTED",
        "publish_authorized": False,
        "created_at": _now(),
        "note": "A handoff is a plan. It is not a produced work, a review or a publication.",
    }


def handoff_filename(content_format: str) -> str:
    if content_format not in FORMATS:
        raise HandoffError("FORMAT_UNKNOWN", f"{content_format!r} is not one of {list(FORMATS)}")
    return f"bundle-handoff-{content_format.lower()}.json"


def write_handoff(project_dir: Path, handoff: Dict[str, Any]) -> Path:
    """Write a handoff under the project's receipts directory.

    The path is derived from a validated format, never from an untrusted string.
    """
    if handoff.get("schema") != HANDOFF_SCHEMA:
        raise HandoffError("HANDOFF_SCHEMA_INVALID", f"expected {HANDOFF_SCHEMA}")
    fmt = handoff.get("content_format")
    target = Path(project_dir).resolve() / "receipts" / handoff_filename(fmt)
    root = Path(project_dir).resolve()
    if root not in target.parents and target != root:
        raise HandoffError("HANDOFF_ESCAPES_PROJECT", target.as_posix())
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(handoff, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    return target


def load_bundle_for_handoff(path: Path) -> Dict[str, Any]:
    try:
        return load_bundle(Path(path))
    except BundleError as exc:
        raise HandoffError(exc.code, exc.detail) from None
