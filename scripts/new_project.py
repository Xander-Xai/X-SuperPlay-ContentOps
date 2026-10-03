#!/usr/bin/env python3
"""Create a new V1 video project under projects/<slug>/.

Idempotent: refuses to overwrite an existing project. UTF-8 / Windows-safe.
"""

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_YAML = ROOT / "templates" / "project.yaml"
PROJECTS_DIR = ROOT / "projects"

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9\-]{1,80}$")


def make_yaml(slug: str, title: str, created_at: str) -> str:
    return f"""id: {slug}
title: "{title.replace(chr(34), chr(92) + chr(34))}"
created_at: "{created_at}"

source_refs: []

content_type: tech_review
topic_cluster: ""

target:
  platform_primary: douyin
  aspect_ratio: "9:16"
  resolution: "1080x1920"
  duration_target_sec: 60

evidence_policy:
  real_assets_first: true
  ai_visuals_allowed: auxiliary_only
  fabricated_claims: forbidden

status: initialized

outputs:
  final_video: ""
  qc_report: ""
"""


def ensure_dirs(project_dir: Path) -> None:
    subdirs = [
        "sources/urls",
        "sources/screenshots",
        "sources/recordings",
        "sources/diagrams",
        "sources/documents",
        "script",
        "assets/voice",
        "assets/captions",
        "assets/generated",
        "assets/processed",
        "work",
        "final",
        "receipts",
    ]
    for sub in subdirs:
        (project_dir / sub).mkdir(parents=True, exist_ok=True)

    placeholders = [
        "sources/urls/README.md",
        "sources/screenshots/README.md",
        "sources/recordings/README.md",
        "sources/diagrams/README.md",
        "sources/documents/README.md",
        "assets/generated/README.md",
        "assets/processed/README.md",
        "work/README.md",
        "final/README.md",
        "receipts/README.md",
    ]
    for pid in placeholders:
        path = project_dir / pid
        if not path.exists():
            path.write_text(
                "# TODO: drop real evidence here. AI-generated assets are auxiliary only.\n",
                encoding="utf-8",
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a new V1 video project.")
    parser.add_argument("--slug", required=True, help="kebab-case id, e.g. easel-review")
    parser.add_argument("--title", default="", help="human-readable title")
    parser.add_argument("--force", action="store_true", help="(reserved) refuse overwrite")
    args = parser.parse_args()

    if not SLUG_RE.match(args.slug):
        print(f"ERROR: invalid slug '{args.slug}'. Use kebab-case, 3-80, [a-z0-9-].", file=sys.stderr)
        return 2

    project_dir = PROJECTS_DIR / args.slug
    if project_dir.exists():
        print(f"ERROR: project '{args.slug}' already exists at {project_dir}", file=sys.stderr)
        print("       refused to overwrite (idempotent).", file=sys.stderr)
        return 3

    title = args.title or args.slug.replace("-", " ").title()
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    project_dir.mkdir(parents=True, exist_ok=False)
    ensure_dirs(project_dir)

    yaml_path = project_dir / "project.yaml"
    yaml_path.write_text(make_yaml(args.slug, title, created_at), encoding="utf-8")

    print(f"Created project: {project_dir}")
    print(f"  - project.yaml: {yaml_path}")
    print(f"  - created_at:   {created_at}")
    print("Next: drop real source assets into sources/, then run scripts/run_v1.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())