"""Stack normalized cards into one vertical long image and write its receipt.

    python scripts/graphic_long_image.py --project projects/my-article \
        --cards projects/my-article/assets/cards/*.png \
        --out projects/my-article/assets/long-image.png

    python scripts/graphic_long_image.py --project projects/my-article \
        --cards-dir projects/my-article/assets/cards \
        --out projects/my-article/assets/long-image.png --gap 36 --pad 60

Cards are pasted in the order given; with ``--cards-dir`` they are taken in
filename order. The receipt lands at ``receipts/long-image.json`` and records
both the input digests and the output digest. A long image is a deliverable,
not an approval: nothing here publishes or sets ``production_ready``.
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

from contentops.graphic.long_image import (  # noqa: E402
    DEFAULT_BACKGROUND,
    DEFAULT_GAP,
    DEFAULT_PAD,
    LongImageError,
    plan,
    stitch,
    write_receipt,
)

CARD_SUFFIXES = (".png", ".jpg", ".jpeg")


def _cards_from_dir(directory: Path) -> list[Path]:
    return sorted(
        path for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in CARD_SUFFIXES
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", required=True, help="project root for the receipt")
    parser.add_argument("--cards", nargs="+", type=Path, help="card images, in paste order")
    parser.add_argument("--cards-dir", type=Path, help="directory of cards, taken in filename order")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--gap", type=int, default=DEFAULT_GAP)
    parser.add_argument("--pad", type=int, default=DEFAULT_PAD)
    parser.add_argument("--background", default=",".join(str(c) for c in DEFAULT_BACKGROUND),
                        help="r,g,b in 0-255; default '%(default)s'")
    parser.add_argument("--dry-run", action="store_true", help="resolve geometry, write nothing")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        channels = tuple(int(part) for part in args.background.split(","))
    except ValueError:
        print(json.dumps({"ok": False, "state": "BLOCKED", "error": "BACKGROUND_INVALID",
                          "detail": f"--background {args.background!r} is not r,g,b"},
                         ensure_ascii=False, indent=2))
        return 4

    if args.cards and args.cards_dir:
        print(json.dumps({"ok": False, "state": "BLOCKED", "error": "ARGS_CONFLICT",
                          "detail": "pass --cards or --cards-dir, not both"},
                         ensure_ascii=False, indent=2))
        return 4
    if args.cards_dir:
        if not args.cards_dir.is_dir():
            print(json.dumps({"ok": False, "state": "BLOCKED", "error": "CARDS_DIR_MISSING",
                              "detail": args.cards_dir.as_posix()},
                             ensure_ascii=False, indent=2))
            return 4
        cards = _cards_from_dir(args.cards_dir)
    else:
        cards = list(args.cards or [])
    if not cards:
        print(json.dumps({"ok": False, "state": "BLOCKED", "error": "EMPTY_INPUT",
                          "detail": "no cards found; pass --cards or a non-empty --cards-dir"},
                         ensure_ascii=False, indent=2))
        return 4

    try:
        geometry = plan(cards, args.out, gap=args.gap, pad=args.pad, background=channels)
        if args.dry_run:
            payload = {
                "ok": True,
                "state": "PLANNED",
                "dry_run": True,
                "card_count": len(geometry.cards),
                "canvas": {"width": geometry.canvas_width, "height": geometry.canvas_height},
                "offsets": list(geometry.offsets),
                "gap": geometry.gap,
                "pad": geometry.pad,
            }
        else:
            receipt = stitch(cards, args.out, gap=args.gap, pad=args.pad, background=channels)
            target = write_receipt(Path(args.project), receipt)
            payload = {**receipt, "ok": True, "state": "WRITTEN",
                       "receipt": target.as_posix()}
    except LongImageError as exc:
        print(json.dumps({"ok": False, "state": "BLOCKED",
                          "error": exc.code, "detail": exc.detail},
                         ensure_ascii=False, indent=2))
        return 4

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif args.dry_run:
        canvas = payload["canvas"]
        print(f"cards      {payload['card_count']}")
        print(f"canvas     {canvas['width']}x{canvas['height']}")
        print("dry-run    nothing written")
    else:
        canvas = payload["canvas"]
        print(f"cards      {payload['card_count']}")
        print(f"canvas     {canvas['width']}x{canvas['height']}")
        print(f"image      {payload['output']['path']}")
        print(f"receipt    {payload['receipt']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
