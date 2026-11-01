"""Consumption contract for a Strategy Content Bundle.

Strategy owns the Bundle template and its meaning
(`90-Templates/content-bundle.yaml`, `01-Strategy/Content-Kernel-and-Bundle-Architecture-V1.md`).
This module only answers one question: is a Bundle record something ContentOps may
consume, and did it arrive intact?

It never re-derives a thesis, never re-decides a production lane, and never turns a
Bundle into published content. A Bundle is a plan; publication is a separate,
human-gated step with its own receipt.

The invariants here are the template's own, restated so that a consumer that skips
Strategy's documentation still fails closed.

Handoff is JSON by default. YAML needs PyYAML, which CI does not install; without
it the loader refuses with BUNDLE_NEEDS_PYYAML rather than reading partially.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

RECORD_TYPE = "content_bundle"
BUNDLE_ID = re.compile(r"^CB-\d{8}-\d{3}$")
SOURCE_ID = re.compile(r"^SRC-\d{8}-\d{3}$")

PRODUCTION_LANES = ("baseline", "enhanced", "experimental")
EXECUTION_PROFILES = ("default", "strict_evidence")
ACCOUNT_TREATMENTS = ("explorer", "thinktank")
CAPABILITIES = (
    "real_capture",
    "reusable_asset",
    "information_motion",
    "generated_image",
    "generated_video",
    "digital_human",
)
EVIDENCE_ROLES = ("direct_evidence", "illustration", "explanation")

REQUIRED_INVARIANTS = (
    "bundle_is_not_published_content",
    "generated_media_is_not_direct_evidence",
    "credentials_must_not_cross_repository_boundaries",
    "platform_adaptation_must_not_change_facts",
)

FORBIDDEN_KEYS = ("token", "cookie", "password", "api_key", "secret", "credential")


class BundleError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


def load_bundle(path: Path) -> Dict[str, Any]:
    """Read a Bundle record. JSON is native; YAML needs PyYAML, which is optional."""
    target = Path(path)
    if not target.is_file():
        raise BundleError("BUNDLE_MISSING", target.as_posix())
    text = target.read_text(encoding="utf-8")
    if not text.strip():
        raise BundleError("BUNDLE_EMPTY", target.as_posix())
    if target.suffix.lower() == ".json":
        try:
            document = json.loads(text)
        except json.JSONDecodeError as exc:
            raise BundleError("BUNDLE_MALFORMED", f"{target.as_posix()}: {exc}") from None
        return document
    try:
        import yaml  # type: ignore
    except ImportError:
        raise BundleError(
            "BUNDLE_NEEDS_PYYAML",
            f"{target.as_posix()} is YAML and PyYAML is not installed") from None
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:  # type: ignore[attr-defined]
        raise BundleError("BUNDLE_MALFORMED", f"{target.as_posix()}: {exc}") from None
    return document if isinstance(document, dict) else {}


def validate_bundle(document: Any) -> List[str]:
    """Structural failures. An empty list means the Bundle may be consumed."""
    failures: List[str] = []
    if not isinstance(document, dict):
        return ["bundle: document must be a mapping"]

    if document.get("record_type") != RECORD_TYPE:
        failures.append(f"bundle.record_type must be {RECORD_TYPE!r}")

    bundle_id = str(document.get("bundle_id") or "")
    if not BUNDLE_ID.match(bundle_id):
        failures.append(f"bundle.bundle_id must match CB-YYYYMMDD-NNN, got {bundle_id!r}")

    status = document.get("status")
    if status not in ("draft", "approved", "archived"):
        failures.append(f"bundle.status={status!r} is not draft/approved/archived")

    source = document.get("source")
    if not isinstance(source, dict):
        failures.append("bundle.source must be a mapping")
    else:
        source_id = str(source.get("source_id") or "")
        if not SOURCE_ID.match(source_id):
            failures.append(f"bundle.source.source_id must match SRC-YYYYMMDD-NNN, got {source_id!r}")
        if not isinstance(source.get("source_refs"), list):
            failures.append("bundle.source.source_refs must be a list")
        if source.get("topic_thesis") is None:
            failures.append("bundle.source.topic_thesis is required before consumption")

    treatments = document.get("account_treatments")
    if not isinstance(treatments, dict) or not treatments:
        failures.append("bundle.account_treatments must be a non-empty mapping")
    else:
        for key, treatment in treatments.items():
            where = f"account_treatments.{key}"
            if key not in ACCOUNT_TREATMENTS:
                failures.append(f"{where} is not one of {list(ACCOUNT_TREATMENTS)}")
            if not isinstance(treatment, dict):
                failures.append(f"{where} must be a mapping")
                continue
            if treatment.get("production_lane") not in PRODUCTION_LANES:
                failures.append(f"{where}.production_lane={treatment.get('production_lane')!r} "
                                f"is not one of {list(PRODUCTION_LANES)}")
            hint = treatment.get("execution_profile_hint", "default")
            if hint not in EXECUTION_PROFILES:
                failures.append(f"{where}.execution_profile_hint={hint!r} "
                                f"is not one of {list(EXECUTION_PROFILES)}")

    requirements = document.get("asset_requirements") or []
    if not isinstance(requirements, list):
        failures.append("bundle.asset_requirements must be a list")
    else:
        for index, requirement in enumerate(requirements):
            where = f"asset_requirements[{index}]"
            if not isinstance(requirement, dict):
                failures.append(f"{where} must be a mapping")
                continue
            if requirement.get("capability") not in CAPABILITIES:
                failures.append(f"{where}.capability={requirement.get('capability')!r} "
                                f"is not one of {list(CAPABILITIES)}")
            role = requirement.get("evidence_role")
            if role not in EVIDENCE_ROLES:
                failures.append(f"{where}.evidence_role={role!r} is not one of {list(EVIDENCE_ROLES)}")
            if role == "direct_evidence" and not requirement.get("claim_refs"):
                failures.append(f"{where} claims direct_evidence with no claim_refs; "
                                f"an asset that proves a claim must be bound to the claim")

    invariants = document.get("invariants")
    if not isinstance(invariants, dict):
        failures.append("bundle.invariants must be a mapping")
    else:
        for name in REQUIRED_INVARIANTS:
            if invariants.get(name) is not True:
                failures.append(f"bundle.invariants.{name} must be true")

    failures.extend(_forbidden_keys(
        {key: value for key, value in document.items() if key != "invariants"}, "bundle"))
    return failures


def _forbidden_keys(node: Any, where: str) -> List[str]:
    failures: List[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in FORBIDDEN_KEYS):
                failures.append(f"{where}.{key} looks like a credential field")
            failures.extend(_forbidden_keys(value, f"{where}.{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            failures.extend(_forbidden_keys(value, f"{where}[{index}]"))
    return failures


def consumption_summary(document: Dict[str, Any]) -> Dict[str, Any]:
    """What a consumer needs, without re-deciding anything Strategy owns."""
    treatments = document.get("account_treatments") or {}
    return {
        "bundle_id": document.get("bundle_id"),
        "source_id": (document.get("source") or {}).get("source_id"),
        "accounts": sorted(treatments),
        "production_lanes": {
            key: value.get("production_lane")
            for key, value in treatments.items()
            if isinstance(value, dict)
        },
        "execution_profile_hints": {
            key: value.get("execution_profile_hint", "default")
            for key, value in treatments.items()
            if isinstance(value, dict)
        },
        "asset_requirements": len(document.get("asset_requirements") or []),
        "platform_adapters": len((document.get("platform_adapters") or {}).get("refs") or []),
        "is_published": False,
        "note": "A bundle is a plan. It is never a publication and never a receipt.",
    }
