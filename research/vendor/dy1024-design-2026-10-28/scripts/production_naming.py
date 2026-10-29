#!/usr/bin/env python3
"""Deterministic naming and layout rules for production content packages.

The production root is deliberately supplied by ``DY_ARTIFACT_ROOT`` (or the
CLI ``--root`` option).  A package is always one direct child of that root and
its directory name is exactly its ``content_id``.  This keeps final media,
intermediate files, QC receipts, and approvals together without allowing
accidental writes beside the production packages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any


POLICY_ID = "douyin-production-naming-v1"
DEFAULT_ARTIFACT_ROOT = Path(__file__).resolve().parents[2] / "production"
CONTENT_ID_RE = re.compile(
    r"^douyin-(?P<date>\d{8})-(?P<sequence>\d{3})-(?P<slug>[a-z0-9][a-z0-9-]{2,47})$"
)


def slugify(value: str) -> str:
    """Return a stable lowercase ASCII topic slug.

    Chinese or otherwise non-ASCII-only titles use a short content hash rather
    than an unstable transliteration dependency.  The title remains in the
    package manifest, while the directory name stays portable and predictable.
    """

    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").casefold()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    if len(slug) < 3:
        digest = hashlib.sha256(str(value or "topic").encode("utf-8")).hexdigest()[:10]
        slug = f"topic-{digest}"
    return slug[:48].rstrip("-")


def validate_content_id(content_id: str) -> dict[str, str]:
    value = str(content_id or "").strip()
    match = CONTENT_ID_RE.fullmatch(value)
    if not match:
        raise ValueError(
            "content_id must match douyin-YYYYMMDD-NNN-topic-slug "
            "(lowercase ASCII, for example douyin-20260824-001-topic-a1b2c3)"
        )
    try:
        datetime.strptime(match.group("date"), "%Y%m%d")
    except ValueError as error:
        raise ValueError("content_id contains an invalid calendar date") from error
    return match.groupdict()


def next_content_id(topic: str, root: Path, date: str = "") -> str:
    """Allocate the next three-digit sequence for a local production day."""

    root = Path(root).expanduser().resolve()
    day = date or datetime.now().astimezone().strftime("%Y%m%d")
    try:
        datetime.strptime(day, "%Y%m%d")
    except ValueError as error:
        raise ValueError("date must use YYYYMMDD and be a valid calendar date") from error

    used: set[int] = set()
    if root.is_dir():
        for child in root.iterdir():
            if not child.is_dir():
                continue
            match = CONTENT_ID_RE.fullmatch(child.name)
            if match and match.group("date") == day:
                used.add(int(match.group("sequence")))
    sequence = 1
    while sequence in used:
        sequence += 1
    if sequence > 999:
        raise ValueError(f"no free sequence remains for {day}")
    return f"douyin-{day}-{sequence:03d}-{slugify(topic)}"


def resolve_artifact_root(root: str | Path | None = None) -> Path:
    value = str(root or os.environ.get("DY_ARTIFACT_ROOT", "")).strip()
    if not value:
        return DEFAULT_ARTIFACT_ROOT.resolve()
    return Path(value).expanduser().resolve()


def validate_project_layout(project: Path, content_id: str, artifact_root: Path) -> None:
    """Fail closed unless the package is a direct child of production root."""

    validate_content_id(content_id)
    project = Path(project).expanduser().resolve()
    artifact_root = Path(artifact_root).expanduser().resolve()
    try:
        relative = project.relative_to(artifact_root)
    except ValueError as error:
        raise ValueError(f"project must be inside DY_ARTIFACT_ROOT: {artifact_root}") from error
    if len(relative.parts) != 1:
        raise ValueError("project must be a direct child of DY_ARTIFACT_ROOT")
    if project.name != content_id:
        raise ValueError("project directory name must exactly equal content_id")


def policy_document() -> dict[str, Any]:
    return {
        "policy_id": POLICY_ID,
        "artifact_root_env": "DY_ARTIFACT_ROOT",
        "default_artifact_root": str(DEFAULT_ARTIFACT_ROOT.resolve()),
        "default_behavior": "fail-closed; resolve workflow parent production when DY_ARTIFACT_ROOT is absent",
        "non_production_override": "--allow-caller-selected or DY_ALLOW_CALLER_SELECTED=1",
        "package_layout": "<DY_ARTIFACT_ROOT>/<content_id>/",
        "content_id_pattern": "douyin-YYYYMMDD-NNN-<lowercase-ascii-topic-slug>",
        "sequence": "next unused NNN (001-999) per local calendar day",
        "title_policy": "keep the original Chinese title in content.json; do not put raw title text in paths",
        "package_rule": "all works, intermediates, QC reports, approvals, and delivery receipts stay inside the package directory",
        "final_filename_pattern": "08_exports/versions/<content_id>__vNN__<kind>.<ext>; current QC input remains 08_exports/final/<canonical-name>",
        "examples": {
            "content_id": "douyin-20260824-001-topic-a1b2c3",
            "project": "production/douyin-20260824-001-topic-a1b2c3",
            "current_final_video": "04_video/render-project/08_exports/final/master.mp4",
            "archived_final_video": "04_video/render-project/08_exports/versions/douyin-20260824-001-topic-a1b2c3__v01__master.mp4",
        },
    }


def _cmd_new_id(args: argparse.Namespace) -> int:
    root = resolve_artifact_root(args.root)
    content_id = next_content_id(args.topic, root, args.date)
    print(json.dumps({"policy_id": POLICY_ID, "artifact_root": str(root), "content_id": content_id}, ensure_ascii=False))
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    try:
        root = resolve_artifact_root(args.root)
        validate_project_layout(Path(args.project), args.content_id, root)
    except (OSError, ValueError) as error:
        print(json.dumps({"policy_id": POLICY_ID, "passed": False, "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps({"policy_id": POLICY_ID, "passed": True, "artifact_root": str(root), "project": str(Path(args.project).expanduser().resolve()), "content_id": args.content_id}, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate and validate production package names.")
    sub = parser.add_subparsers(dest="command", required=True)
    new_id = sub.add_parser("new-id", help="allocate the next content_id for a topic")
    new_id.add_argument("--topic", required=True)
    new_id.add_argument("--root", default="")
    new_id.add_argument("--date", default="")
    new_id.set_defaults(handler=_cmd_new_id)
    validate = sub.add_parser("validate", help="validate a project path and content_id")
    validate.add_argument("--project", required=True)
    validate.add_argument("--content-id", required=True)
    validate.add_argument("--root", default="")
    validate.set_defaults(handler=_cmd_validate)
    return parser


if __name__ == "__main__":
    arguments = build_parser().parse_args()
    raise SystemExit(arguments.handler(arguments))
