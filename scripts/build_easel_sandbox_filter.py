#!/usr/bin/env python3
"""Build the candidate Linux seccomp preload into a new file; do not run it."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "extensions" / "easel-workbench" / "sandbox" / "no_subprocess.c"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", help="absolute absent path for the candidate shared object")
    args = parser.parse_args()
    target = Path(args.output)
    if os.name != "posix" or not target.is_absolute() or ".." in target.parts:
        print("BLOCKED: build requires an absolute Linux path without parent traversal", file=sys.stderr)
        return 4
    current = Path(target.anchor)
    for component in target.parts[1:]:
        current /= component
        if current.is_symlink():
            print("BLOCKED: output path contains a link", file=sys.stderr)
            return 4
    receipt = target.with_name(target.name + ".build.json")
    if (target.exists() or receipt.exists() or receipt.is_symlink()
            or not target.parent.is_dir() or SOURCE.is_symlink() or not SOURCE.is_file()):
        print("BLOCKED: output, receipt, or source path is unsafe", file=sys.stderr)
        return 4
    compiler = shutil.which("cc")
    if not compiler:
        print("BLOCKED: Linux C compiler is unavailable", file=sys.stderr)
        return 4
    source_bytes = SOURCE.read_bytes()
    try:
        with tempfile.TemporaryDirectory(prefix="easel-filter-build-", dir=target.parent) as tmp:
            source = Path(tmp) / "filter.c"
            binary = Path(tmp) / "filter.so"
            source.write_bytes(source_bytes)
            proc = subprocess.run([compiler, "-shared", "-fPIC", "-O2", "-o", str(binary), str(source)],
                                  stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  timeout=120, check=False)
            if proc.returncode != 0 or not binary.is_file():
                print("BLOCKED: compilation failed", file=sys.stderr)
                return 4
            digest = hashlib.sha256(binary.read_bytes()).hexdigest()
            os.link(binary, target)  # fails rather than replacing an existing file
        data = {"schema": "contentops.easel-sandbox-filter-build/v1",
                "source_sha256": hashlib.sha256(source_bytes).hexdigest(), "binary_sha256": digest,
                "compiler": compiler, "architecture": "linux-x86_64",
                "status": "BUILT_UNVERIFIED", "execution_authorized": False}
        with receipt.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except (OSError, subprocess.TimeoutExpired):
        print("BLOCKED: build or receipt write failed; inspect output before retry", file=sys.stderr)
        return 4
    print(json.dumps(data, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
