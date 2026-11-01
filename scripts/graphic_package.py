"""Build a manual graphic/text package from a GRAPHIC_TEXT handoff.

    python scripts/graphic_package.py --project projects/my-article \
        --handoff projects/my-article/receipts/bundle-handoff-graphic_text.json \
        --input projects/my-article/graphic-input.json

The package stops at AWAITING_MANUAL_REVIEW. It does not log in, draft or
publish to any platform.
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

from contentops.graphic import GraphicPackageError, build_package, write_package  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", required=True)
    parser.add_argument("--handoff", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--registry-root", default=str(ROOT))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        package = build_package(Path(args.project), Path(args.handoff),
                                Path(args.input), Path(args.registry_root), ROOT,
                                bundle_root=ROOT)
        paths = write_package(Path(args.project), package, ROOT)
    except GraphicPackageError as exc:
        print(json.dumps({"ok": False, "state": "BLOCKED",
                          "error": exc.code, "detail": exc.detail},
                         ensure_ascii=False, indent=2))
        return 4

    payload = {**package, "written": {key: value.as_posix() for key, value in paths.items()}}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"package    {paths['package'].as_posix()}")
        print(f"preview    {paths['preview'].as_posix()}")
        print(f"status     {package['status']}")
        print(f"publish    {package['publish_authorized']}")
        print(f"blockers   {', '.join(package['blockers']) or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
