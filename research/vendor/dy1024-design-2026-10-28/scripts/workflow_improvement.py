#!/usr/bin/env python3
"""Record evidence-backed workflow improvement items for a canonical package."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from canonical_workflow import CONTRACT_ID, LEGACY_CONTRACT_ID, SUPPORTED_CONTRACT_IDS, STAGE_IDS
except ImportError:  # imported as scripts.workflow_improvement
    from scripts.canonical_workflow import CONTRACT_ID, LEGACY_CONTRACT_ID, SUPPORTED_CONTRACT_IDS, STAGE_IDS


CONTRACT = CONTRACT_ID
LEGACY_CONTRACT = LEGACY_CONTRACT_ID
ACCOUNT = "X•超玩1024"
STAGES = set(STAGE_IDS) | {"feedback", "workflow"}
CATEGORIES = {"content", "gate", "path", "renderer", "provider", "environment", "documentation", "other"}
SEVERITIES = {"low", "medium", "high", "blocker"}
STATUSES = {"reported", "triaged", "reproduced", "planned", "fixed", "verified", "wont_fix"}


def fail(message: str) -> None:
    raise SystemExit(message)


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"{label} is invalid: {error}")
    if not isinstance(value, dict):
        fail(f"{label} must be a JSON object")
    return value


def project_path(project: Path, value: str) -> Path:
    candidate = (project / value).resolve()
    try:
        candidate.relative_to(project.resolve())
    except ValueError as error:
        raise ValueError(f"path escapes content package: {value}") from error
    return candidate


def manifest_log_path(project: Path, manifest: dict[str, Any]) -> Path:
    if manifest.get("workflow_contract") not in SUPPORTED_CONTRACT_IDS:
        fail(f"workflow improvement log requires a supported canonical workflow contract: {sorted(SUPPORTED_CONTRACT_IDS)}")
    if manifest.get("account") != ACCOUNT:
        fail(f"content package account must be {ACCOUNT}")
    paths = manifest.get("paths") if isinstance(manifest.get("paths"), dict) else {}
    raw = str(paths.get("workflow_improvement_log") or paths.get("canonical_workflow_improvement_log") or "09_feedback/workflow-improvement-log.json")
    try:
        return project_path(project, raw)
    except ValueError as error:
        fail(str(error))


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def evidence_items(project: Path, values: list[str]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for raw in values:
        parts = raw.split("|", 2)
        relative = parts[0].strip()
        if not relative:
            fail("--evidence requires path|sha256|note")
        try:
            path = project_path(project, relative)
        except ValueError as error:
            fail(str(error))
        digest = parts[1].strip().lower() if len(parts) > 1 else ""
        if digest and (len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest)):
            fail(f"evidence SHA-256 must be 64 lowercase hex characters: {relative}")
        if path.is_file():
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest and digest != actual:
                fail(f"evidence hash mismatch: {relative}")
            digest = actual
        elif not digest:
            fail(f"evidence file is missing and has no recorded hash: {relative}")
        result.append({"path": relative.replace("\\", "/"), "sha256": digest, "note": parts[2].strip() if len(parts) > 2 else ""})
    return result


def atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def record(args: argparse.Namespace) -> int:
    project = Path(args.project).expanduser().resolve()
    manifest = load_json(project / "content.json", "content.json")
    if manifest.get("content_id") != args.content_id:
        fail("--content-id must match content.json")
    target = manifest_log_path(project, manifest)
    if target.is_file():
        log = load_json(target, "workflow improvement log")
    else:
        log = {"schema_version": 1, "contract": str(manifest.get("workflow_contract") or CONTRACT), "content_id": args.content_id, "status": "empty", "entries": []}
    if log.get("schema_version") != 1 or log.get("contract") not in SUPPORTED_CONTRACT_IDS or log.get("content_id") != args.content_id:
        fail("workflow improvement log contract or content_id mismatch")
    entries = log.get("entries") if isinstance(log.get("entries"), list) else []
    issue_id = args.issue_id.strip() or f"wi-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    if any(isinstance(item, dict) and item.get("issue_id") == issue_id for item in entries):
        fail(f"issue_id already exists: {issue_id}")
    evidence = evidence_items(project, args.evidence)
    entry = {
        "issue_id": issue_id,
        "reported_at": now(),
        "reported_by": args.reporter.strip(),
        "stage": args.stage,
        "category": args.category,
        "severity": args.severity,
        "status": args.status,
        "summary": args.summary.strip(),
        "observed": args.observed.strip(),
        "expected": args.expected.strip(),
        "reproduction": args.reproduction.strip(),
        "evidence": evidence,
        "root_cause": args.root_cause.strip(),
        "proposed_change": args.proposed_change.strip(),
        "verification_plan": args.verification_plan.strip(),
        "resolution": args.resolution.strip(),
    }
    entries.append(entry)
    log["entries"] = entries
    log["status"] = "open"
    atomic_write(target, log)
    print(json.dumps({"project": str(project), "log": str(target), "issue_id": issue_id, "status": log["status"]}, ensure_ascii=False, indent=2))
    return 0


def show(args: argparse.Namespace) -> int:
    project = Path(args.project).expanduser().resolve()
    manifest = load_json(project / "content.json", "content.json")
    target = manifest_log_path(project, manifest)
    value = load_json(target, "workflow improvement log")
    print(json.dumps(value, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record evidence-backed workflow improvement items.")
    sub = parser.add_subparsers(dest="command", required=True)
    record_parser = sub.add_parser("record", help="append one reproducible improvement item")
    record_parser.add_argument("--project", required=True)
    record_parser.add_argument("--content-id", required=True)
    record_parser.add_argument("--stage", choices=sorted(STAGES), required=True)
    record_parser.add_argument("--category", choices=sorted(CATEGORIES), required=True)
    record_parser.add_argument("--severity", choices=sorted(SEVERITIES), required=True)
    record_parser.add_argument("--status", choices=sorted(STATUSES), default="reported")
    record_parser.add_argument("--summary", required=True)
    record_parser.add_argument("--observed", required=True)
    record_parser.add_argument("--expected", required=True)
    record_parser.add_argument("--reproduction", required=True)
    record_parser.add_argument("--evidence", action="append", default=[], help="path|sha256|note; repeatable")
    record_parser.add_argument("--root-cause", default="")
    record_parser.add_argument("--proposed-change", default="")
    record_parser.add_argument("--verification-plan", default="")
    record_parser.add_argument("--resolution", default="")
    record_parser.add_argument("--reporter", default="operator")
    record_parser.add_argument("--issue-id", default="")
    record_parser.set_defaults(handler=record)
    show_parser = sub.add_parser("show", help="print the package improvement log")
    show_parser.add_argument("--project", required=True)
    show_parser.set_defaults(handler=show)
    return parser


if __name__ == "__main__":
    arguments = build_parser().parse_args()
    raise SystemExit(arguments.handler(arguments))
