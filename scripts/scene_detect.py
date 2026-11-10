#!/usr/bin/env python3
"""Optional read-only raw footage scene discovery; never edits M5 storyboard."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.media.scene_analysis import (  # noqa: E402
    SceneAnalysisError, analyze, write_receipt,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--source", required=True,
                        help="Project-relative local video, e.g. assets/reference.mp4")
    parser.add_argument("--threshold", type=float, default=27.0,
                        help="PySceneDetect ContentDetector threshold (0, 255]")
    args = parser.parse_args(argv)
    try:
        result = analyze(args.project, args.source, threshold=args.threshold)
        receipt = write_receipt(args.project, result)
    except (SceneAnalysisError, FileNotFoundError, OSError) as exc:
        print(json.dumps({"state": "BLOCKED", "reason": str(exc),
                          "production_ready": False,
                          "publish_authorized": False}, ensure_ascii=False),
              file=sys.stderr)
        return 2
    print(json.dumps({"state": result["state"], "scene_count": result["scene_count"],
                      "receipt": str(receipt), "production_ready": False,
                      "publish_authorized": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
