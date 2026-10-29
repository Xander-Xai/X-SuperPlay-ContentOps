#!/usr/bin/env python3
"""Verify and explicitly promote the v2 stable-production milestone.

The strict media status command proves one content package. It must not be
used to infer that the whole v2 workflow is stable. This module requires
three different, ordered v2 packages, re-runs the strict status check for each
package, and requires an approved Delivery stage before it can emit a
``stable-production`` marker.

The default operation is read-only. ``--promote`` is an explicit, separate
write that creates the caller-selected marker only after all three packages
pass. A failed audit never writes or downgrades an existing marker.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    from canonical_workflow import CONTRACT_ID, project_file
    from strict_media_orchestrator import strict_status
except ImportError:  # imported as scripts.stability_gate
    from scripts.canonical_workflow import CONTRACT_ID, project_file
    from scripts.strict_media_orchestrator import strict_status


SCHEMA_VERSION = 1
REQUIRED_RUNS = 3
MARKER_STATUS = "stable-production"
BLOCKED_STATUS = "blocked"


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_created_at(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _package_file(project: Path, value: Any, default: str) -> Path | None:
    candidate = str(value or default).strip()
    if not candidate:
        return None
    return project_file(project, candidate)


def _delivery_errors(project: Path, manifest: dict[str, Any], content_id: str) -> tuple[list[str], Path | None]:
    paths = manifest.get("paths") if isinstance(manifest.get("paths"), dict) else {}
    delivery = _package_file(project, paths.get("canonical_delivery"), "08_delivery/delivery-manifest.json")
    if delivery is None or not delivery.is_file():
        return ["canonical Delivery manifest is missing or outside the content package"], delivery
    payload = _load(delivery)
    if not isinstance(payload, dict):
        return ["canonical Delivery manifest is invalid JSON"], delivery
    errors: list[str] = []
    if payload.get("contract") != CONTRACT_ID:
        errors.append("Delivery manifest must use canonical-copy-to-video-v2")
    if payload.get("content_id") != content_id:
        errors.append("Delivery manifest content_id does not match content package")
    if payload.get("status") not in {"ready_for_review", "approved"}:
        errors.append("Delivery manifest must be ready_for_review or approved")
    files = payload.get("files")
    if not isinstance(files, list) or not files:
        errors.append("Delivery manifest must list at least one evidence file")
        return errors, delivery
    for index, item in enumerate(files):
        if not isinstance(item, dict):
            errors.append(f"Delivery manifest file {index} must be an object")
            continue
        path = project_file(project, item.get("path"))
        if path is None or not path.is_file():
            errors.append(f"Delivery manifest file {index} is missing or outside the package")
            continue
        declared = str(item.get("sha256") or "").strip().lower()
        if len(declared) != 64 or _sha256(path) != declared:
            errors.append(f"Delivery manifest file {index} SHA-256 is stale")
    return errors, delivery


def inspect_package(project_value: str | Path) -> dict[str, Any]:
    """Return auditable evidence for one candidate production package."""

    project = Path(project_value).expanduser().resolve()
    errors: list[str] = []
    manifest_path = project / "content.json"
    manifest = _load(manifest_path)
    if not isinstance(manifest, dict):
        return {
            "project": str(project),
            "content_id": "",
            "created_at": "",
            "passed": False,
            "errors": ["content.json is missing or invalid"],
        }
    content_id = str(manifest.get("content_id") or "").strip()
    created_at = str(manifest.get("created_at") or "").strip()
    if manifest.get("workflow_contract") != CONTRACT_ID:
        errors.append("workflow_contract must be canonical-copy-to-video-v2")
    if manifest.get("execution_contract_version") != 2:
        errors.append("execution_contract_version must be 2")
    if manifest.get("strict_media_execution") is not True:
        errors.append("strict_media_execution must be true")
    if not content_id:
        errors.append("content_id is missing")
    if _parse_created_at(created_at) is None:
        errors.append("created_at must be an ISO-8601 timestamp")

    workflow = manifest.get("workflow") if isinstance(manifest.get("workflow"), dict) else {}
    steps = workflow.get("steps") if isinstance(workflow.get("steps"), dict) else {}
    delivery_step = steps.get("delivery") if isinstance(steps.get("delivery"), dict) else {}
    if delivery_step.get("status") != "approved":
        errors.append("workflow delivery step must be approved")

    strict = strict_status(project)
    if strict.get("passed") is not True or strict.get("status") != "ready":
        strict_errors = strict.get("errors") if isinstance(strict.get("errors"), list) else []
        errors.append("strict media status did not pass")
        errors.extend(f"strict: {item}" for item in strict_errors[:20])

    delivery_errors, delivery_path = _delivery_errors(project, manifest, content_id)
    errors.extend(delivery_errors)
    evidence: dict[str, str] = {"manifest_sha256": _sha256(manifest_path)} if manifest_path.is_file() else {}
    if delivery_path is not None and delivery_path.is_file():
        evidence["delivery_manifest_sha256"] = _sha256(delivery_path)
    paths = manifest.get("paths") if isinstance(manifest.get("paths"), dict) else {}
    quality_path = _package_file(project, paths.get("canonical_quality"), "07_quality/quality-report.json")
    if quality_path is not None and quality_path.is_file():
        evidence["quality_report_sha256"] = _sha256(quality_path)
    return {
        "project": str(project),
        "content_id": content_id,
        "created_at": created_at,
        "passed": not errors,
        "errors": sorted(set(errors)),
        "evidence": evidence,
    }


def evaluate(projects: Iterable[str | Path]) -> dict[str, Any]:
    """Audit exactly three ordered, distinct packages without writing state."""

    values = [str(Path(item).expanduser().resolve()) for item in projects]
    packages = [inspect_package(item) for item in values]
    errors: list[str] = []
    if len(values) != REQUIRED_RUNS:
        errors.append(f"stability gate requires exactly {REQUIRED_RUNS} ordered content packages")
    if len(set(values)) != len(values):
        errors.append("stability gate packages must be distinct")
    content_ids = [str(item.get("content_id") or "") for item in packages]
    if len(set(content_ids)) != len(content_ids) or any(not item for item in content_ids):
        errors.append("stability gate content_id values must be present and distinct")
    timestamps = [_parse_created_at(item.get("created_at")) for item in packages]
    if any(value is None for value in timestamps):
        errors.append("stability gate requires valid created_at timestamps for all packages")
    elif any(left >= right for left, right in zip(timestamps, timestamps[1:])):
        errors.append("stability gate packages must be supplied in strictly increasing production order")
    passed_runs = sum(1 for item in packages if item.get("passed") is True)
    if passed_runs != REQUIRED_RUNS:
        errors.append(f"stability gate requires {REQUIRED_RUNS} passing v2 packages; observed {passed_runs}")
    return {
        "schema_version": SCHEMA_VERSION,
        "contract": CONTRACT_ID,
        "status": MARKER_STATUS if not errors else BLOCKED_STATUS,
        "required_runs": REQUIRED_RUNS,
        "passed_runs": passed_runs,
        "packages": packages,
        "errors": sorted(set(errors)),
    }


def promote(report: dict[str, Any], output: str | Path, *, force: bool = False) -> Path:
    """Write a stable marker only for a fully passing report."""

    if report.get("status") != MARKER_STATUS:
        raise ValueError("cannot promote a blocked stability report")
    target = Path(output).expanduser().resolve()
    if target.exists() and not force:
        raise FileExistsError(f"stability marker exists: {target}; use --force to replace it")
    payload = dict(report)
    payload["promoted_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload["marker"] = str(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify three complete v2 packages before stable-production promotion")
    parser.add_argument("--project", action="append", required=True, help="ordered v2 content package; repeat exactly three times")
    parser.add_argument("--promote", action="store_true", help="write the stable marker after a passing audit")
    parser.add_argument("--output", help="marker path required with --promote")
    parser.add_argument("--force", action="store_true", help="replace an existing marker only with --promote")
    args = parser.parse_args(argv)
    if args.promote and not args.output:
        parser.error("--output is required with --promote")
    report = evaluate(args.project)
    promoted = ""
    if args.promote and report.get("status") == MARKER_STATUS:
        try:
            marker_path = promote(report, args.output, force=args.force)
            promoted = str(marker_path)
            persisted_report = _load(marker_path)
            if (
                not isinstance(persisted_report, dict)
                or persisted_report.get("marker") != promoted
                or not persisted_report.get("promoted_at")
            ):
                raise ValueError("persisted stability marker could not be reloaded as a complete promotion report")
            report = dict(persisted_report)
        except (OSError, ValueError) as error:
            promoted = ""
            report = dict(report)
            report["status"] = BLOCKED_STATUS
            report.setdefault("errors", []).append(str(error))
    if promoted:
        report["promoted_marker"] = promoted
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") == MARKER_STATUS else 2


if __name__ == "__main__":
    raise SystemExit(main())
