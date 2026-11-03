#!/usr/bin/env python3
"""Check a Strategy Content Bundle before ContentOps consumes it.

The Bundle is a plan, not a publication. This CLI answers only whether the
record is intact: identity, account treatments, asset requirements, invariants.
It never renders, publishes or spends.

Usage
-----
    python scripts/content_bundle.py check path/to/content-bundle.yaml
    python scripts/content_bundle.py summary path/to/content-bundle.yaml
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

from contentops.content_kernel import (  # noqa: E402
    BundleError,
    consumption_summary,
    load_bundle,
    validate_bundle,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="validate a Content Bundle record")
    check.add_argument("path")
    summary = sub.add_parser("summary", help="print the consumption view")
    summary.add_argument("path")
    args = parser.parse_args()

    try:
        document = load_bundle(Path(args.path))
    except BundleError as exc:
        print(f"{exc.code}: {exc.detail}")
        return 3

    failures = validate_bundle(document)
    if args.command == "check":
        if args.json:
            print(json.dumps({"status": "FAIL" if failures else "OK", "failures": failures},
                             ensure_ascii=False, indent=2))
        elif failures:
            for failure in failures:
                print(f"FAIL {failure}")
        else:
            print("OK: content bundle may be consumed")
        return 1 if failures else 0

    print(json.dumps(consumption_summary(document), ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
