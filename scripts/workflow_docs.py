"""Print the workflow contract as documentation (Markdown or JSON).

The stage list lives in ``contentops.workflow.contract``. This CLI is the only
place that renders it, so a doc cannot drift from the code by retyping the
stage names.

Usage:
    python scripts/workflow_docs.py [--json]
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

from contentops.workflow.contract import (  # noqa: E402
    CONTRACT_ID,
    GRAPHIC_CONTRACT_ID,
    GRAPHIC_STAGES,
    STAGES,
)


def as_dict() -> dict:
    def rows(stages):
        return [
            {"id": stage.id, "label": stage.label, "artifact": stage.artifact,
             "requires": list(stage.requires)}
            for stage in stages
        ]

    return {
        "schema": "contentops.workflow-docs/v1",
        "contract_id": CONTRACT_ID,
        "graphic_contract_id": GRAPHIC_CONTRACT_ID,
        "stages": rows(STAGES),
        "graphic_stages": rows(GRAPHIC_STAGES),
        "note": "generated from contentops.workflow.contract; do not retype this table",
    }


def as_markdown() -> str:
    data = as_dict()
    lines = [
        "# Workflow stages",
        "",
        f"Generated from `contentops.workflow.contract` (`{data['contract_id']}`).",
        "",
        "| # | Stage | Artifact | Requires |",
        "|---:|---|---|---|",
    ]
    for index, stage in enumerate(data["stages"], 1):
        requires = ", ".join(stage["requires"]) or "—"
        lines.append(f"| {index} | `{stage['id']}` | `{stage['artifact']}` | {requires} |")
    lines += [
        "",
        f"Graphic contract: `{data['graphic_contract_id']}`",
        "",
        "| Stage | Artifact | Requires |",
        "|---|---|---|",
    ]
    for stage in data["graphic_stages"]:
        requires = ", ".join(stage["requires"]) or "—"
        lines.append(f"| `{stage['id']}` | `{stage['artifact']}` | {requires} |")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Render the workflow stage contract.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.json:
        print(json.dumps(as_dict(), ensure_ascii=False, indent=2))
    else:
        print(as_markdown(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
