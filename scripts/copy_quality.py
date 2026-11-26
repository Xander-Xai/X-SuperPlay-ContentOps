#!/usr/bin/env python3
"""Diagnose the structure of a finished script: opening, ending, body.

This is a read-only tool. It reads narration lines from a project's
``script/script.json`` (or a script file you point it at), measures opening
hook, ending call-to-action, second-person presence, concreteness and filler,
and prints advice. It never edits the script, never touches claims or evidence,
and never gates production.

Examples:
    python scripts/copy_quality.py --project projects/my-episode
    python scripts/copy_quality.py --script projects/my-episode/script/script.json
    python scripts/copy_quality.py --script ... --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.workflow import copy_quality  # noqa: E402


def _load_lines(path: Path) -> list:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        lines = data.get("lines")
        if lines is None:
            raise SystemExit(f"{path}: no 'lines' in script json")
        return lines
    if isinstance(data, list):
        return data
    raise SystemExit(f"{path}: unsupported script json shape")


def _resolve_script(args: argparse.Namespace) -> Path:
    if args.script:
        p = Path(args.script)
        if not p.is_file():
            raise SystemExit(f"script not found: {p}")
        return p
    if args.project:
        p = Path(args.project) / "script" / "script.json"
        if not p.is_file():
            raise SystemExit(f"script not found under project: {p}")
        return p
    raise SystemExit("give --project or --script")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only script structure diagnosis")
    parser.add_argument("--project", default="", help="project directory containing script/script.json")
    parser.add_argument("--script", default="", help="direct path to a script.json")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    script = _resolve_script(args)
    lines = _load_lines(script)
    report = copy_quality.diagnose(lines)
    report["source"] = str(script)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print(f"copy-quality: {report['score']}/100  ({report['line_count']} lines)  ← {script}")
    print(f"  opening [{report['opening']['status']}] {report['opening']['text']}")
    print(f"          {report['opening']['note']}")
    print(f"  ending  [{report['ending']['status']}] {report['ending']['text']}")
    print(f"          {report['ending']['note']}")
    body = report["body"]
    print(f"  body    sentences={body['sentence_count']}  you={body['person_ratio']}  "
          f"concrete={body['concrete_ratio']}  filler={body['filler_hits'] or 'none'}")
    if report["suggestions"]:
        print("  suggestions:")
        for s in report["suggestions"]:
            print(f"    - {s}")
    print(f"  note: {report['disclaimer']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
