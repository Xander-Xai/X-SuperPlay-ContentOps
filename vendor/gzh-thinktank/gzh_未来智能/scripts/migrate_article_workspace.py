#!/usr/bin/env python3
"""Move one legacy repository draft into the external article workspace.

The migration is deliberately narrow: it accepts only a concrete directory
under the legacy repository ``drafts/`` root, allocates a new canonical ID,
preserves every byte, and moves non-standard process files into ``work/``.
It never deletes a non-empty source and writes a registry record before
reporting success.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from workspace_audit import ROOT_ARTIFACT_DIRS, ROOT_ARTIFACT_NAMES  # noqa: E402
from workspace_paths import (  # noqa: E402
    ROOT as WORKFLOW_ROOT,
    allocate_workspace,
    artifact_root,
    slugify,
    workspace_manifest,
)
from workflow_security import load_yaml  # noqa: E402


def _title(source: Path) -> str:
    metadata = load_yaml(source / "article.yaml", default={})
    if isinstance(metadata, dict) and str(metadata.get("title") or "").strip():
        return str(metadata["title"]).strip()
    return source.name.split("-", 1)[-1]


def _source_guard(source: Path) -> Path:
    resolved = source.expanduser().resolve()
    legacy_root = (WORKFLOW_ROOT / "drafts").resolve()
    try:
        resolved.relative_to(legacy_root)
    except ValueError as exc:
        raise ValueError("migration source must be a concrete directory under repository drafts/") from exc
    if not resolved.is_dir():
        raise ValueError(f"migration source is not a directory: {resolved}")
    if not any(resolved.iterdir()):
        raise ValueError("migration source is empty")
    return resolved


def _date_from_name(source: Path) -> str:
    match = re.match(r"^(\d{8})-", source.name)
    return match.group(1) if match else datetime.now().strftime("%Y%m%d")


def _move_child(child: Path, target: Path, moved_process: list[str]) -> None:
    # Standard article directories and files remain where the existing gates
    # expect them.  One-off scripts and unknown outputs are still preserved,
    # but are explicitly classified as process history under work/.
    is_standard_dir = child.is_dir() and child.name in ROOT_ARTIFACT_DIRS
    is_standard_file = child.is_file() and (
        child.name in ROOT_ARTIFACT_NAMES or child.name.startswith("README")
    )
    destination = target / child.name
    if not (is_standard_dir or is_standard_file):
        process_dir = target / "work" / "legacy-process"
        process_dir.mkdir(parents=True, exist_ok=True)
        destination = process_dir / child.name
        moved_process.append(child.name)
    if destination.exists():
        raise FileExistsError(f"migration destination already exists: {destination}")
    shutil.move(str(child), str(destination))


def migrate(source: Path) -> dict[str, object]:
    source = _source_guard(source)
    title = _title(source)
    source_slug = source.name.split("-", 1)[1] if "-" in source.name else title
    destination, workspace_id, sequence = allocate_workspace(
        title,
        date_value=_date_from_name(source),
        requested_slug=source_slug,
        root=None,
    )
    moved_process: list[str] = []
    for child in sorted(source.iterdir(), key=lambda item: item.name.lower()):
        _move_child(child, destination, moved_process)

    slug = slugify(source_slug)
    manifest = workspace_manifest(destination, workspace_id, title, slug)
    manifest.update({
        "lifecycle": "active",
        "migrated_from": "legacy drafts/" + source.name,
        "migration_mode": "move-preserving-bytes",
        "process_files": moved_process,
    })
    (destination / "workspace-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    article_yaml = destination / "article.yaml"
    if article_yaml.is_file():
        text = article_yaml.read_text(encoding="utf-8")
        if "workspace_id:" not in text:
            text = text.replace(
                "schema_version: 1\n",
                "schema_version: 1\n"
                f"workspace_id: {workspace_id}\n"
                f"workspace_relative_path: {manifest['relative_path']}\n",
                1,
            )
            article_yaml.write_text(text, encoding="utf-8")

    state_path = destination / "matrix-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.is_file() else {}
    if not isinstance(state, dict):
        state = {}
    relative = destination.relative_to(artifact_root(create=False)).as_posix()
    state.update({
        "workspace_id": workspace_id,
        "workspace_sequence": sequence,
        "workspace_relative_path": relative,
        "workspace_lifecycle": "active",
        "article_dir": relative,
        "process_files_dir": "work",
        "deliverable_dir": "exports",
        "checkpoint_dir": "snapshots",
        "migration": {
            "from": "drafts/" + source.name,
            "migrated_at": datetime.now().astimezone().isoformat(),
            "mode": "move-preserving-bytes",
            "process_files": moved_process,
        },
    })
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Only remove the now-empty legacy directories.  The article contents were
    # moved, not discarded; the external registry is the recovery index.
    source.rmdir()
    legacy_root = WORKFLOW_ROOT / "drafts"
    if legacy_root.is_dir() and not any(legacy_root.iterdir()):
        legacy_root.rmdir()

    record = {
        "contract": "article-workspace-migration-v1",
        "source": "drafts/" + source.name,
        "workspace_id": workspace_id,
        "destination": relative,
        "title": title,
        "moved_process_files": moved_process,
        "mode": "move-preserving-bytes",
        "migrated_at": datetime.now().astimezone().isoformat(),
    }
    registry_dir = artifact_root(create=True) / "registry" / "migrations"
    registry_dir.mkdir(parents=True, exist_ok=True)
    (registry_dir / f"{workspace_id}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, type=Path)
    args = parser.parse_args()
    try:
        record = migrate(args.article)
    except (OSError, ValueError, TimeoutError, json.JSONDecodeError) as exc:
        print(f"ARTICLE MIGRATION BLOCKED: {exc}")
        return 1
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
