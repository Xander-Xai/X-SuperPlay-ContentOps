#!/usr/bin/env python3
"""Move a registered article workspace between lifecycle directories safely."""
from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

from workspace_paths import LIFECYCLE_DIRS, WORKSPACE_ID_RE, artifact_root, registry_lock


def transition(workspace: str, target: str, *, root: Path | None = None) -> Path:
    base = (root or artifact_root(create=True)).resolve()
    if target not in LIFECYCLE_DIRS:
        raise ValueError(f"invalid lifecycle: {target}")
    source = Path(workspace).expanduser()
    if not source.is_absolute():
        source = base / source
    source = source.resolve()
    try:
        relative = source.relative_to(base)
    except ValueError as exc:
        raise ValueError("workspace must be inside artifact root") from exc
    if len(relative.parts) < 2 or relative.parts[0] not in LIFECYCLE_DIRS:
        raise ValueError("workspace must be under an artifact lifecycle directory")
    parts = source.name.split("-", 3)
    if len(parts) < 4 or not WORKSPACE_ID_RE.match("-".join(parts[:3])):
        raise ValueError("workspace directory must use THK-YYYYMMDD-NNN-slug")
    manifest_path = source / "workspace-manifest.json"
    if not manifest_path.is_file():
        raise ValueError("workspace-manifest.json is required")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    workspace_id = str(manifest.get("workspace_id") or "")
    if not WORKSPACE_ID_RE.fullmatch(workspace_id):
        raise ValueError("workspace manifest has invalid workspace_id")
    if relative.parts[0] == target:
        return source
    destination = base / target / source.name
    if destination.exists():
        raise FileExistsError(f"lifecycle destination exists: {destination}")
    with registry_lock(base):
        registry_path = base / "registry" / "workspace-index.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        rows = registry.get("workspaces", [])
        row = next((item for item in rows if isinstance(item, dict) and item.get("workspace_id") == workspace_id), None)
        if row is None:
            raise ValueError(f"workspace is not registered: {workspace_id}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        row["lifecycle"] = target
        row["relative_path"] = destination.relative_to(base).as_posix()
        row["updated_at"] = datetime.now().astimezone().isoformat()
        registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        moved_manifest = destination / "workspace-manifest.json"
        manifest["lifecycle"] = target
        manifest["relative_path"] = destination.relative_to(base).as_posix()
        moved_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        state_path = destination / "matrix-state.json"
        if state_path.is_file():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                state = {}
            if isinstance(state, dict):
                relative_path = destination.relative_to(base).as_posix()
                state.update({
                    "workspace_lifecycle": target,
                    "workspace_relative_path": relative_path,
                    "article_dir": relative_path,
                })
                state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--to", required=True, choices=LIFECYCLE_DIRS)
    args = parser.parse_args()
    try:
        destination = transition(args.workspace, args.to)
    except (OSError, ValueError, json.JSONDecodeError, TimeoutError) as exc:
        print(f"WORKSPACE LIFECYCLE BLOCKED: {exc}")
        return 1
    print(f"WORKSPACE LIFECYCLE MOVED: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
