#!/usr/bin/env python3
"""Manual publish receipt and feedback intake boundary."""
from __future__ import annotations
import argparse, json
from pathlib import Path

def main(args: argparse.Namespace) -> int:
    project = Path(args.project).expanduser().resolve(); project.joinpath("05_publish").mkdir(parents=True, exist_ok=True); project.joinpath("06_metrics").mkdir(parents=True, exist_ok=True)
    if args.command == "init":
        project.joinpath("05_publish/publish-receipt.json").write_text(json.dumps({"schema_version": 1, "content_id": args.content_id, "platform": args.platform, "publish_method": "manual-or-official", "published_at": "", "media_id": "", "url": "", "operator": "", "notes": ""}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        project.joinpath("06_metrics/metrics.json").write_text(json.dumps({"schema_version": 1, "content_id": args.content_id, "platforms": [], "captured_at": "", "next_action": ""}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"project": str(project), "command": args.command}, ensure_ascii=False)); return 0

parser = argparse.ArgumentParser(); parser.add_argument("command", choices=["init", "validate"]); parser.add_argument("--project", required=True); parser.add_argument("--content-id", default=""); parser.add_argument("--platform", default="douyin")
if __name__ == "__main__": raise SystemExit(main(parser.parse_args()))
