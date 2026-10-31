#!/usr/bin/env python3
"""Run the offline growth -> editorial-gate -> manual-package pipeline.

Every input is a local JSON file. Nothing here connects to X, approves a post,
or publishes one. A successful run ends at AWAITING_MANUAL_PUBLISH.

Usage
-----
    python scripts/x_growth_pipeline.py projects/x-growth-en \
        --request projects/x-growth-en/sources/growth-request.json \
        --enrichment projects/x-growth-en/sources/enrichment.json --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import x_post  # noqa: E402
from contentops.publish.x_growth_pipeline import run  # noqa: E402
from x_organic_growth import safe_input_path  # noqa: E402


def _load(path: str) -> dict:
    candidate = Path(path)
    if not safe_input_path(candidate):
        raise SystemExit(
            f"refusing {candidate}: inputs must live under tests/fixtures or "
            "projects/<slug>/sources and must not be credential files")
    raw = candidate.read_bytes()
    if len(raw) > 1024 * 1024:
        raise SystemExit(f"refusing {candidate}: larger than 1 MiB")
    return json.loads(raw.decode("utf-8"))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", help="X project directory")
    parser.add_argument("--request", required=True, help="growth request JSON")
    parser.add_argument("--enrichment", required=True, help="enrichment JSON")
    parser.add_argument("--weekly", help="optional weekly metrics request JSON")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    project = Path(args.project)
    if not project.is_dir():
        print(f"project not found: {project}", file=sys.stderr)
        return 2
    try:
        account = x_post.account_for(project)
    except x_post.Refusal as refusal:
        print(json.dumps({"schema": "contentops.x-growth-pipeline/v1",
                          "status": "GROWTH_BLOCKED",
                          "reasons": [f"{refusal.code}: {refusal.detail}"],
                          "external_action": "none",
                          "execution_authorized": False}, indent=2),
              file=sys.stdout)
        return 1

    result = run(
        project,
        _load(args.request),
        _load(args.enrichment),
        account,
        weekly_request=_load(args.weekly) if args.weekly else None,
    )
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"status    {result['status']}")
        for reason in result["reasons"]:
            print(f"reason    {reason}")
        for stage in result["stages"]:
            print(f"stage     {stage['stage']}: {stage['status']}")
        if result.get("package_path"):
            print(f"package   {result['package_path']}")
    return 0 if result["status"] == "AWAITING_MANUAL_PUBLISH" else 1


if __name__ == "__main__":
    raise SystemExit(main())
