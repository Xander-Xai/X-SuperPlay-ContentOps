"""Create a form-specific production handoff from a Strategy Content Bundle.

    python scripts/bundle_handoff.py bundle.json --account explorer \
        --format VIDEO --project-slug my-video \
        --source-map SRC-20261102-001=SRC-RUNTIME-001 \
        [--platform x] [--out-project projects/my-video]

This writes a plan and never starts production, renders or publishes.
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

from contentops.content_kernel.handoff import (  # noqa: E402
    FORMATS,
    HandoffError,
    build_handoff,
    load_bundle_for_handoff,
    write_handoff,
)


def _pairs(values):
    result = {}
    for value in values or []:
        if "=" not in value:
            raise HandoffError("SOURCE_MAP_INVALID", f"{value!r} must be KEY=VALUE")
        key, item = value.split("=", 1)
        result[key.strip()] = item.strip()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("bundle", help="Strategy Content Bundle JSON/YAML")
    parser.add_argument("--account", required=True, choices=("explorer", "thinktank"))
    parser.add_argument("--format", required=True, choices=FORMATS)
    parser.add_argument("--project-slug", required=True)
    parser.add_argument("--source-map", action="append", default=[],
                        help="STRATEGY_SOURCE_ID=CONTENTOPS_SOURCE_ID (repeatable)")
    parser.add_argument("--platform", default=None)
    parser.add_argument("--host-capability", default="UNVERIFIED")
    parser.add_argument("--registry-root", default=str(ROOT))
    parser.add_argument("--out-project", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        bundle = load_bundle_for_handoff(Path(args.bundle))
        handoff = build_handoff(
            bundle, args.account, args.format,
            project_slug=args.project_slug,
            source_map=_pairs(args.source_map),
            platform_id=args.platform,
            registry_root=Path(args.registry_root),
            host_capability=args.host_capability,
        )
        if args.out_project:
            target = write_handoff(Path(args.out_project), handoff)
            handoff = {**handoff, "written_to": target.as_posix()}
    except HandoffError as exc:
        print(json.dumps({"ok": False, "state": "BLOCKED",
                          "error": exc.code, "detail": exc.detail},
                         ensure_ascii=False, indent=2))
        return 4

    if args.json:
        print(json.dumps(handoff, ensure_ascii=False, indent=2))
    else:
        print(f"bundle     {handoff['bundle_id']}  {handoff['bundle_sha256'][:12]}")
        print(f"format     {handoff['content_format']}")
        print(f"state      {handoff['state']}")
        print(f"blockers   {', '.join(handoff['blockers']) or 'none'}")
        print(f"publish    {handoff['publish_authorized']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
