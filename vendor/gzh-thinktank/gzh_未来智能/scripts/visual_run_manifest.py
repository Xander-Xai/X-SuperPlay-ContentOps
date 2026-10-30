#!/usr/bin/env python3
"""Append immutable-ish execution provenance for visual workflow commands."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


MANIFEST = "visual-run-manifest.jsonl"


def _sha(path: Path) -> str:
    if not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_record(article: Path, raw: str) -> dict[str, Any]:
    path = Path(str(raw or ""))
    if not path.is_absolute():
        path = article / path
    path = path.resolve()
    return {
        "path": str(path.relative_to(article)) if path.is_relative_to(article) else str(path),
        "exists": path.is_file(),
        "sha256": _sha(path),
        "size": path.stat().st_size if path.is_file() else 0,
    }


def record(
    article: Path,
    *,
    stage: str,
    command: Iterable[str],
    inputs: Iterable[str] = (),
    outputs: Iterable[str] = (),
    status: str = "passed",
    run_id: str | None = None,
) -> dict[str, Any]:
    article = article.resolve()
    entry = {
        "schema_version": 1,
        "contract": "visual-run-provenance-v1",
        "run_id": run_id or f"vrun-{uuid.uuid4().hex}",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "stage": stage,
        "status": status,
        "command": [str(value) for value in command],
        "python": sys.version,
        "platform": platform.platform(),
        "python_executable": sys.executable,
        "inputs": [_file_record(article, value) for value in inputs],
        "outputs": [_file_record(article, value) for value in outputs],
    }
    path = article / MANIFEST
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n")
    return entry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", required=True, type=Path)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--command", nargs="+", required=True)
    parser.add_argument("--input", action="append", default=[])
    parser.add_argument("--output", action="append", default=[])
    parser.add_argument("--status", default="passed")
    args = parser.parse_args()
    entry = record(
        args.article,
        stage=args.stage,
        command=args.command,
        inputs=args.input,
        outputs=args.output,
        status=args.status,
    )
    print(json.dumps({"run_id": entry["run_id"], "status": entry["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
