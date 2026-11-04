#!/usr/bin/env python3
"""Render a project's HTML cards to PNG and gate each one on the density audit.

    python scripts/render_cards.py projects/my-note
    python scripts/render_cards.py projects/my-note --html assets/cards/cards.html \\
        --width 1080 --height 1440 --scale 1
    python scripts/render_cards.py projects/my-note --json

What it runs (nothing else):
    1. ``.runtime/easel/skills/shared/scripts/render_card.py``  — HTML -> PNG
    2. ``.runtime/easel/skills/openclaw/card-design/scripts/card_audit.py`` — density gate

and writes ``projects/<slug>/receipts/card-render.json``.

It adds no renderer, starts no host, calls no agent and no network provider.
A density PASS is not an approval: the receipt keeps
``production_ready: false`` and ``publish_authorized: false``.

The interpreter: the card tools need a Playwright build whose Chromium is
actually installed. Point ``CONTENTOPS_CARD_PYTHON`` at a matching interpreter
when the default one does not match, and set ``PLAYWRIGHT_BROWSERS_PATH``.

Exit codes: 0 every card passed the audit; 4 blocked or an audit failed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.graphic.cards import (  # noqa: E402
    CardRenderError,
    plan,
    run,
    write_receipt,
)
from process_utils import hidden_run  # noqa: E402

BLOCKED_EXIT = 4
RUNTIME_ROOT = ROOT / ".runtime" / "easel"


def _card_python() -> str:
    """The interpreter for the card tools, defaulting to this one.

    The renderer needs a Playwright whose bundled Chromium is present on this
    machine; a project venv may pin a Playwright that expects an absent build.
    """
    return os.environ.get("CONTENTOPS_CARD_PYTHON") or sys.executable


def _runner(argv, *, timeout: int = 300):
    """Run one card tool through the repository's hidden-window subprocess layer.

    The child inherits this process's environment, so ``PATH`` and
    ``PLAYWRIGHT_BROWSERS_PATH`` reach the renderer unchanged.
    """
    return hidden_run(argv, timeout=timeout, check=False)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project")
    parser.add_argument("--html", default=None,
                        help="HTML file (default: <project>/assets/cards/cards.html)")
    parser.add_argument("--out-dir", default=None,
                        help="PNG output directory (default: <project>/assets/cards)")
    parser.add_argument("--selector", default=".card", help="CSS selector per card")
    parser.add_argument("--width", type=int, default=1080)
    parser.add_argument("--height", type=int, default=1440)
    parser.add_argument("--scale", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    # The card tools are Chinese-first; make their inherited child environment
    # UTF-8 so a GBK console cannot corrupt an audit message into a false failure.
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    project = Path(args.project)
    if not project.is_absolute():
        project = (ROOT / project).resolve()

    try:
        p = plan(project,
                 runtime_root=RUNTIME_ROOT,
                 html=Path(args.html) if args.html else None,
                 out_dir=Path(args.out_dir) if args.out_dir else None,
                 selector=args.selector,
                 width=args.width, height=args.height, scale=args.scale)
        receipt = run(p, card_python=_card_python(), runner=_runner,
                      timeout=args.timeout)
    except CardRenderError as exc:
        payload = {**exc.as_dict(), "project": project.as_posix()}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"project    {project.as_posix()}")
            print(f"status     BLOCKED ({exc.code})")
            print(f"detail     {exc.detail}")
        return BLOCKED_EXIT

    target = write_receipt(project, receipt)

    if args.json:
        print(json.dumps({**receipt, "written": target.as_posix()},
                         ensure_ascii=False, indent=2))
    else:
        print(f"project    {project.as_posix()}")
        print(f"html       {receipt['html']['path']}")
        print(f"cards      {receipt['card_count']}")
        for card in receipt["cards"]:
            mark = "PASS" if card["pass"] else "FAIL"
            print(f"  {mark:4} {card['path']:14} {card['size']}  "
                  f"span {card['span']}  dead {card['bottom_dead']}  gap {card['max_gap']}")
            for problem in card["problems"]:
                print(f"        - {problem}")
        if receipt["ignored_existing"]:
            print(f"ignored    {', '.join(receipt['ignored_existing'])} (not produced by this run)")
        print(f"audit      {receipt['audit_status']}")
        print(f"status     {receipt['status']}")
        print(f"publish    {receipt['publish_authorized']}")
        print(f"receipt    {target.as_posix()}")

    return 0 if receipt["audit_status"] == "PASS" else BLOCKED_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
