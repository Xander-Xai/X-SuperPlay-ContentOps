#!/usr/bin/env python3
"""Run one optimization cycle over the checked-in signals and backlog.

Usage
-----
```
python scripts/optimization_cycle.py            # markdown report
python scripts/optimization_cycle.py --json     # report as JSON
python scripts/optimization_cycle.py --write    # also write evaluated artifacts
python scripts/optimization_cycle.py --flywheel # current flywheel state
```

Exit codes: 0 = valid cycle; 2 = malformed signal/candidate or policy refusal.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from contentops.optimization import (  # noqa: E402
    OptimizationError,
    build_report,
    load_backlog,
    load_flywheel,
    load_policy,
    load_signals,
    render_markdown,
)
from contentops.optimization.cycle import CONFIG, EVALUATED_PATH  # noqa: E402


def _write(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--flywheel", action="store_true")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    try:
        policy = load_policy()
        signals = load_signals()
        backlog = load_backlog()
        flywheel = load_flywheel()
        report = build_report(policy, signals, backlog, flywheel)
    except OptimizationError as exc:
        print(f"REFUSED [{exc.code}]: {exc.detail}", file=sys.stderr)
        return 2

    if args.flywheel:
        print(json.dumps(flywheel, ensure_ascii=False, indent=2))
    elif args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report), end="")

    if args.write:
        CONFIG.mkdir(parents=True, exist_ok=True)
        _write(CONFIG / "optimization-report.json", report)
        _write(EVALUATED_PATH, {
            "schema": "contentops.optimization-backlog-evaluated/v1",
            "cycle": report["cycle"],
            "candidates": report["ranked"],
        })
        print(f"wrote {EVALUATED_PATH.relative_to(ROOT).as_posix()}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
