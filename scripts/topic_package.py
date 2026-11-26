#!/usr/bin/env python3
"""Initialize, inspect, or bind a shared topic-copy package.

This is an offline file operation. It does not invoke the writing Skill, create
projects, access providers, spend credits, publish, or approve a human decision.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.workflow import topic_package  # noqa: E402

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,80}$")


def _project(value: str) -> tuple[Path, Path]:
    raw = Path(value)
    candidate = raw if raw.is_absolute() else ROOT / raw
    output_root = os.environ.get("CONTENTOPS_OUTPUT_ROOT", "").strip()
    try:
        relative = candidate.relative_to(ROOT).parts
    except ValueError:
        relative = ()
    if output_root and relative[:2] == ("projects", "_local") and len(relative) == 3:
        candidate = Path(output_root).expanduser() / "workspace" / relative[2]
    roots = [ROOT / "projects", ROOT / "projects" / "_local"]
    if output_root:
        roots.append(Path(output_root).expanduser() / "workspace")
    for configured_root in roots:
        if configured_root.is_symlink():
            continue
        root = configured_root.resolve()
        if candidate.is_symlink():
            continue
        project = candidate.resolve()
        if project.parent == root and SLUG_RE.fullmatch(project.name) and project.is_dir():
            return project, root
    raise ValueError(
        "PROJECT_OUTSIDE_TRUSTED_ROOT: use projects/<slug> or a project directly "
        "under CONTENTOPS_OUTPUT_ROOT/workspace; .env is not read")


def _emit(payload: Dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(f"action   {payload.get('action', '-')}")
    print(f"state    {payload.get('state', '-')}")
    if payload.get("package_id"):
        print(f"package  {payload['package_id']}")
    if payload.get("detail"):
        print(f"detail   {payload['detail']}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("init", "initialize a neutral topic package"),
                            ("check", "check the authority package and canonical review")):
        command = sub.add_parser(name, help=help_text)
        command.add_argument("project")
        command.add_argument("--json", action="store_true")
    bind = sub.add_parser("bind", help="bind one sibling production project")
    bind.add_argument("package")
    bind.add_argument("child")
    bind.add_argument("--format", required=True, choices=topic_package.FORMATS)
    bind.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command in ("init", "check"):
            project, _ = _project(args.project)
            if args.command == "init":
                result = topic_package.initialize(project)
                result.update(action="INITIALIZED", state="TOPIC_PACKAGE_INITIALIZED")
            else:
                result = topic_package.check_package(project)
                result.update(action="CHECKED")
        else:
            package, package_root = _project(args.package)
            child, child_root = _project(args.child)
            if package_root != child_root:
                raise ValueError("PROJECT_ROOT_MISMATCH: package and child must share a trusted root")
            result = topic_package.bind_child(package, child, args.format,
                                               projects_root=package_root)
            result.update(action="BOUND", state="TOPIC_PACKAGE_BOUND")
    except (OSError, ValueError) as exc:
        result = {"ok": False, "action": "BLOCKED", "state": "BLOCKED",
                  "code": str(exc).split(":", 1)[0], "detail": str(exc),
                  "production_ready": False, "publish_authorized": False}
    _emit(result, args.json)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
