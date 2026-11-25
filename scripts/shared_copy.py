#!/usr/bin/env python3
"""Derive one graphic draft from a current reviewed VIDEO source, offline only."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from contentops.workflow import shared_copy


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--project", type=Path, required=True)
    a = p.parse_args(argv)
    try:
        result = shared_copy.prepare(ROOT, a.source, a.project)
        print(json.dumps({"status": "DERIVED_REVIEWABLE_COPY", "shared_copy_id": result["shared_copy_id"],
                          "title": result["title"], "draft": "shared-copy.md",
                          "publish_authorized": False}, ensure_ascii=False))
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        print("BLOCKED: " + str(exc), file=sys.stderr)
        return 4


if __name__ == "__main__":
    sys.exit(main())
