#!/usr/bin/env python3
"""Smoke-test the local Mermaid adapter without network access."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "integrations" / "diagram_mermaid.py"


def main() -> int:
    # beautiful-mermaid is a thinktank-only optional backend.  In split
    # sentinel targets it is intentionally absent; skip without pretending
    # the capability exists (plan v0.2: optional-missing is not a main-chain fail).
    if not (ROOT / "skills" / "beautiful-mermaid" / "scripts" / "render-diagram.ts").is_file():
        print("DIAGRAM ADAPTER TEST SKIPPED (beautiful-mermaid not present in this target)")
        return 0
    with tempfile.TemporaryDirectory(prefix="diagram-adapter-") as raw:
        work = Path(raw)
        source = work / "workflow.mmd"
        output = work / "workflow.svg"
        source.write_text("graph LR\n  A[选题] --> B[审稿] --> C[草稿箱]", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(ADAPTER), "--input", str(source), "--output", str(output)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode:
            print(result.stdout + result.stderr)
            return result.returncode
        if not output.is_file() or not output.read_text(encoding="utf-8").lstrip().startswith("<svg"):
            print("DIAGRAM ADAPTER TEST FAILED: SVG missing")
            return 1
    print("DIAGRAM ADAPTER TEST PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
