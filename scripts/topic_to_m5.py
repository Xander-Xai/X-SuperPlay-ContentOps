#!/usr/bin/env python3
"""Project a reviewed TOPIC copy derivative into the M5 VIDEO script contract.

Usage:
    python scripts/topic_to_m5.py projects/my-video
    python scripts/topic_to_m5.py projects/my-video --check
    python scripts/topic_to_m5.py projects/my-video --dry-run
    python scripts/topic_to_m5.py projects/my-video --json

Reads ``00_brief/copy-derivative.json`` (VIDEO format) and the registered
visual cards in ``sources/assets.json`` (permission CREATED_BY_OWNER). Writes
``script/script.json`` only. It never signs a review, never grants publication,
never edits the spoken copy, and never renders.

The generated script is a faithful machine projection: narration equals caption,
each segment's pieces concatenate byte-for-byte to the reviewed text, and each
segment's claim set equals its claim_refs. Lines are split to fit the 8-second
Huashu shot ceiling; authored cards and focus rectangles rotate so adjacent
shots differ; every line uses the camera-push grammar that passes the film gate.

Exit codes: 0 written / current; 4 blocked (derivative missing, no cards, or a
violation that cannot be projected without changing reviewed copy).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.script.topic_m5 import (  # noqa: E402
    DEFAULT_MAX_CHARS,
    DERIVATIVE_SCHEMA,
    TopicM5Error,
    build_script,
    validate_script,
)
from contentops.workflow.canonical_copy import DERIVATIVE_FILE  # noqa: E402

BLOCKED_EXIT = 4
SCHEMA_ASSETS = "contentops.m5-assets/v1"
VISUAL_ROLES = {"CREATED_BY_OWNER"}


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _visual_cards(project: Path) -> list[str]:
    """Registered authored bitmaps usable as Huashu visual sources.

    The film gate needs real bitmaps; the Huashu source-media gate needs
    CREATED_BY_OWNER / USER_PROVIDED. Authored cards satisfy both. LICENSED
    screenshots remain evidence and are deliberately excluded here.
    """
    path = project / "sources" / "assets.json"
    if not path.is_file():
        raise TopicM5Error("ASSETS_MISSING", "sources/assets.json not found")
    doc = _load_json(path)
    if doc.get("schema") != SCHEMA_ASSETS:
        raise TopicM5Error("ASSETS_SCHEMA", f"expected {SCHEMA_ASSETS}")
    cards = [str(row.get("id")) for row in doc.get("assets", [])
             if isinstance(row, dict)
             and str(row.get("permission") or "").upper() in VISUAL_ROLES
             and str(row.get("type") or "").upper() == "REAL_SCREENSHOT"
             and str(row.get("id") or "")]
    return cards


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("project")
    parser.add_argument("--check", action="store_true",
                        help="validate the script already on disk; write nothing")
    parser.add_argument("--dry-run", action="store_true", help="build but write nothing")
    parser.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS,
                        help=f"max narration characters per shot (default {DEFAULT_MAX_CHARS})")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    project = Path(args.project)
    derivative_path = project / DERIVATIVE_FILE
    script_path = project / "script" / "script.json"
    try:
        if not derivative_path.is_file():
            raise TopicM5Error("DERIVATIVE_MISSING", f"{DERIVATIVE_FILE} not found")
        derivative = _load_json(derivative_path)
        if derivative.get("schema") != DERIVATIVE_SCHEMA:
            raise TopicM5Error("DERIVATIVE_SCHEMA", f"expected {DERIVATIVE_SCHEMA}")
        if derivative.get("format") != "VIDEO":
            raise TopicM5Error("DERIVATIVE_FORMAT", "not a VIDEO derivative")

        cards = _visual_cards(project)
        built = build_script(derivative, asset_ids=cards, max_chars=args.max_chars)

        if args.check:
            if not script_path.is_file():
                raise TopicM5Error("SCRIPT_MISSING", "script/script.json not found")
            current = _load_json(script_path)
            problems = validate_script(current, derivative)
            if problems:
                raise TopicM5Error("CHECK_FAILED", "; ".join(problems))
            payload = {"state": "CURRENT", "lines": len(current.get("lines", [])),
                       "cards": len(cards)}
        elif args.dry_run:
            payload = {"state": "DRY_RUN", "lines": len(built["lines"]),
                       "cards": len(cards), "written": []}
        else:
            script_path.parent.mkdir(parents=True, exist_ok=True)
            script_path.write_text(
                json.dumps(built, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            payload = {"state": "PROJECTED", "lines": len(built["lines"]),
                       "cards": len(cards),
                       "written": [script_path.relative_to(project).as_posix()]}

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"{payload['state']}: {payload['lines']} lines, "
                  f"{payload['cards']} authored cards")
            for relative in payload.get("written", []):
                print(f"  wrote {relative}")
        return 0
    except (TopicM5Error, OSError, ValueError) as exc:
        code = exc.code if isinstance(exc, TopicM5Error) else "READ_FAILED"
        detail = exc.detail if isinstance(exc, TopicM5Error) else str(exc)
        if args.json:
            print(json.dumps({"state": code, "detail": detail}, ensure_ascii=False, indent=2))
        else:
            print(f"{code}: {detail}")
        return BLOCKED_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
