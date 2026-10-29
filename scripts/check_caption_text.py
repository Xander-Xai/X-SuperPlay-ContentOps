#!/usr/bin/env python3
"""Prove a burned caption transcribes the narration it sits under.

    python scripts/check_caption_text.py --srt assets/captions/default.srt \\
        --narration script/narration.txt

Timing checks cannot see this defect: a caption built from an older script
still parses, still fits the frame and still lands on its cue -- it just says
words the voice never speaks. Comparison ignores punctuation, whitespace and
TTS pause markers; everything else must match.

Exit 0 = the caption transcribes the narration, 1 = it does not, 2 = usage.
No media, no provider, no rewrite.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.quality.subtitle import validate_caption_agreement  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--srt", required=True, help="the caption file that will be burned")
    parser.add_argument("--narration", required=True, help="the narration text file")
    parser.add_argument("--json", action="store_true", help="print a machine-readable result")
    args = parser.parse_args(argv)

    srt = Path(args.srt)
    narration_path = Path(args.narration)
    if not srt.is_file():
        parser.error(f"caption not found: {srt}")
    if not narration_path.is_file():
        parser.error(f"narration not found: {narration_path}")
    narration = narration_path.read_text(encoding="utf-8")

    errors = validate_caption_agreement(srt, narration)
    if args.json:
        print(json.dumps({
            "schema": "contentops.caption-agreement/v1",
            "caption": srt.name,
            "narration": narration_path.name,
            "passed": not errors,
            "errors": errors,
        }, ensure_ascii=False, indent=2))
    else:
        for message in errors:
            print(f"  - {message}")
        print(f"[{'FAIL' if errors else 'PASS'}] caption agrees with narration")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
