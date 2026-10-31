"""The growth-to-manual-package pipeline, offline and human-gated.

Stages, in order:

    growth skill -> account DNA -> enrichment -> X Post Gate -> package

There is no stage after the package that posts anything. A record only reaches
``AWAITING_MANUAL_PUBLISH``; the publication itself is a person's action and the
real status URL is recorded separately.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from contentops.publish import x_growth_bridge
from contentops.publish.x_paths import ensure_inside, is_single_component, resolve_inside
from contentops.publish.publisher import build_package
from contentops.publish.x_post import post_verdict, validate_post
from contentops.x_organic_growth import process as growth_process

SCHEMA = "contentops.x-growth-pipeline/v1"
MANUAL = "AWAITING_MANUAL_PUBLISH"


def _envelope(status: str, **extra: Any) -> Dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": status,
        "reasons": list(extra.pop("reasons", [])),
        "stages": [],
        "publication_mode": "MANUAL_ONLY",
        "execution_authorized": False,
        "external_action": "none",
        **extra,
    }


def _write_record(project: Path, record: Dict[str, Any]) -> Path:
    content_id = str(record.get("content_id") or "")
    if not is_single_component(content_id):
        raise ValueError(
            f"content_id {content_id!r} is not one safe file-name component")
    posts = project / "posts"
    if posts.exists() and not ensure_inside(project, posts):
        raise ValueError(f"{posts} resolves outside the project; refusing to write")
    posts.mkdir(parents=True, exist_ok=True)
    if not ensure_inside(project, posts):
        raise ValueError(f"{posts} resolves outside the project; refusing to write")
    target = resolve_inside(posts, f"{content_id}.json")
    if target is None or target.parent != posts.resolve():
        raise ValueError(
            f"content_id {content_id!r} does not resolve to a file directly under posts/")
    if target.exists():
        raise FileExistsError(
            f"{target} already exists; this pipeline will not overwrite a record")
    target.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    return target


def run(project: Path, growth_request: Dict[str, Any], enrichment: Dict[str, Any],
        account: Dict[str, Any], *,
        weekly_request: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run every offline stage and stop at the first refusal."""
    project = Path(project)
    if not project.is_dir():
        return _envelope("GROWTH_BLOCKED", reasons=[f"{project} is not a directory"])
    expected = str(account.get("slug") or "")
    declared = str(((growth_request or {}).get("account_id")) if isinstance(
        growth_request, dict) else "")
    if expected and declared and declared != expected:
        return _envelope("GROWTH_BLOCKED", reasons=[
            f"growth request names {declared!r}, project resolves {expected!r}"])

    growth = growth_process(growth_request)
    result = _envelope("", growth=growth)
    result["stages"].append({"stage": "growth", "status": growth.get("status")})
    if (growth.get("status") != "REVIEW_REQUIRED"
            or growth.get("contract_completeness") != "PARTIAL_CONTRACT"
            or not isinstance(growth.get("draft"), dict)):
        result["status"] = "GROWTH_BLOCKED"
        result["reasons"] = growth.get("reasons") or ["growth operation is not x_contract"]
        del result["growth"]
        return result

    try:
        record = x_growth_bridge.enrich(growth["draft"], enrichment, project, account)
    except x_growth_bridge.BridgeBlocked as blocked:
        result["status"] = "ENRICHMENT_BLOCKED"
        result["reasons"] = blocked.reasons
        del result["growth"]
        return result
    result["stages"].append({"stage": "enrichment", "status": "ENRICHED"})

    issues = validate_post(record, account, root=project)
    verdict = post_verdict(record, account, root=project)
    result["stages"].append({"stage": "editorial_gate", "status": verdict})
    if issues or verdict != "READY":
        result["status"] = "EDITORIAL_BLOCKED"
        result["reasons"] = [f"{issue.code}: {issue.detail}" for issue in issues]
        result["verdict"] = verdict
        del result["growth"]
        return result

    try:
        record_path = _write_record(project, record)
    except (FileExistsError, ValueError) as exc:
        result["status"] = "EDITORIAL_BLOCKED"
        result["reasons"] = [str(exc)]
        del result["growth"]
        return result
    result["stages"].append({"stage": "record", "status": "WRITTEN"})

    package = build_package(record, account, project)
    result["stages"].append({"stage": "package", "status": package["status"]})
    result.update({
        "status": package["status"],
        "verdict": verdict,
        "record_path": record_path.relative_to(project).as_posix(),
        "package_path": package["receipt"],
        "package": package,
        "review_provenance": (record.get("enrichment") or {}).get("review_provenance"),
        "review_trust": "NOT_VERIFIED",
    })
    del result["growth"]

    if weekly_request is not None:
        metrics = growth_process(weekly_request)
        result["metrics"] = metrics
        result["stages"].append({"stage": "metrics", "status": metrics.get("status")})
    else:
        result["metrics"] = {
            "status": "DATA_UNAVAILABLE",
            "reasons": ["no weekly metric request was supplied"],
            "network_used": False,
            "external_action": "none",
        }
    return result
