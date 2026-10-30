#!/usr/bin/env python3
"""Create, verify, and resume an article checkpoint.

The checkpoint is local and content-addressed.  It is a recovery mechanism,
not a substitute for WeChat's remote draft readback: a restored local state
still has to pass every workflow gate again.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from workspace_paths import resolve_article_workspace  # noqa: E402
CONTRACT = "checkpoint-v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _article_path(raw: Path) -> Path:
    return resolve_article_workspace(raw, allow_test_fixture=True)


def _safe_relative(path: Path, article: Path) -> str | None:
    try:
        relative = path.resolve().relative_to(article.resolve()).as_posix()
    except ValueError:
        return None
    if relative == "snapshots" or relative.startswith("snapshots/checkpoints/"):
        return None
    return relative


def _iter_files(article: Path) -> list[tuple[str, Path]]:
    rows: list[tuple[str, Path]] = []
    for path in article.rglob("*"):
        if not path.is_file():
            continue
        relative = _safe_relative(path, article)
        if relative is not None:
            rows.append((relative, path))
    return sorted(rows, key=lambda item: item[0])


def create(article: Path, label: str, reason: str = "") -> tuple[int, Path | None]:
    state_path = article / "matrix-state.json"
    if not state_path.is_file():
        print("CHECKPOINT BLOCKED: 缺少 matrix-state.json")
        return 1, None
    state = _read_json(state_path)
    if not isinstance(state, dict):
        print("CHECKPOINT BLOCKED: matrix-state.json 无效")
        return 1, None
    safe_label = re.sub(r"[^A-Za-z0-9_-]+", "-", str(label).strip()).strip("-") or "checkpoint"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    checkpoint_id = f"{timestamp}-{safe_label}"
    root = article / "snapshots" / "checkpoints" / checkpoint_id
    snapshot = root / "files"
    file_rows: list[dict[str, Any]] = []
    for relative, source in _iter_files(article):
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        file_rows.append({"path": relative, "bytes": source.stat().st_size, "sha256": sha256_file(source)})
    manifest = {
        "schema_version": 1,
        "contract": CONTRACT,
        "checkpoint_id": checkpoint_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "label": label,
        "reason": reason,
        "article_id": article.name,
        "current_stage": state.get("current_stage"),
        "state_sha256": sha256_file(state_path),
        "files": file_rows,
    }
    _write_json(root / "manifest.json", manifest)
    index_path = article / "checkpoint-manifest.json"
    index = _read_json(index_path)
    if not isinstance(index, dict) or index.get("contract") != CONTRACT:
        index = {"schema_version": 1, "contract": CONTRACT, "checkpoints": []}
    checkpoints = index.get("checkpoints") if isinstance(index.get("checkpoints"), list) else []
    checkpoints.append({"checkpoint_id": checkpoint_id, "path": f"snapshots/checkpoints/{checkpoint_id}/manifest.json", "created_at": manifest["created_at"], "current_stage": manifest["current_stage"], "file_count": len(file_rows)})
    index.update({"schema_version": 1, "contract": CONTRACT, "updated_at": manifest["created_at"], "checkpoints": checkpoints})
    _write_json(index_path, index)
    print(f"CHECKPOINT CREATED: {checkpoint_id} ({len(file_rows)} files)")
    return 0, root


def _manifest(article: Path, checkpoint_id: str) -> tuple[Path | None, dict[str, Any] | None]:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", checkpoint_id):
        return None, None
    path = article / "snapshots" / "checkpoints" / checkpoint_id / "manifest.json"
    data = _read_json(path)
    return path, data if isinstance(data, dict) else None


def verify(article: Path, checkpoint_id: str) -> int:
    manifest_path, manifest = _manifest(article, checkpoint_id)
    if manifest_path is None or manifest is None or manifest.get("contract") != CONTRACT:
        print("CHECKPOINT VERIFY BLOCKED: checkpoint manifest 无效")
        return 1
    snapshot = manifest_path.parent / "files"
    errors: list[str] = []
    for row in manifest.get("files", []):
        if not isinstance(row, dict):
            errors.append("files 中存在非对象条目")
            continue
        relative = str(row.get("path") or "")
        target = snapshot / relative
        if _safe_relative(target, snapshot) is None or not target.is_file():
            errors.append(f"快照文件缺失：{relative}")
            continue
        if sha256_file(target) != str(row.get("sha256") or ""):
            errors.append(f"快照哈希不一致：{relative}")
    if errors:
        print("CHECKPOINT VERIFY BLOCKED:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"CHECKPOINT VERIFY PASSED: {checkpoint_id} ({len(manifest.get('files', []))} files)")
    return 0


def resume(article: Path, checkpoint_id: str) -> int:
    if verify(article, checkpoint_id) != 0:
        return 1
    manifest_path, manifest = _manifest(article, checkpoint_id)
    assert manifest_path is not None and manifest is not None
    snapshot = manifest_path.parent / "files"
    for row in manifest.get("files", []):
        relative = str(row.get("path") or "")
        source = snapshot / relative
        target = article / relative
        if _safe_relative(target, article) is None:
            print(f"CHECKPOINT RESUME BLOCKED: 非法恢复路径 {relative}")
            return 1
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    print(f"CHECKPOINT RESUMED: {checkpoint_id}; 请重新推进所有顺序门禁")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create_parser = sub.add_parser("create")
    create_parser.add_argument("--article", required=True, type=Path)
    create_parser.add_argument("--label", required=True)
    create_parser.add_argument("--reason", default="")
    for name in ("verify", "resume"):
        item = sub.add_parser(name)
        item.add_argument("--article", required=True, type=Path)
        item.add_argument("--checkpoint", required=True)
    args = parser.parse_args()
    article = _article_path(args.article)
    if args.command == "create":
        return create(article, args.label, args.reason)[0]
    if args.command == "verify":
        return verify(article, args.checkpoint)
    return resume(article, args.checkpoint)


if __name__ == "__main__":
    raise SystemExit(main())
