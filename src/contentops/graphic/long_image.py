"""Stack normalized cards into one vertical long image.

Why this module exists
----------------------
Both content lines already produce single cards — the Xiaohongshu route
normalizes one to 1080x1440 (``xhs_未来智能/scripts/normalize_xhs_image.py``)
and the card renderer saves one PNG per card — but nothing turned "these N
cards" into the one long image a 一图流 post actually needs. A human doing it
by hand produced a file with no receipt, and a later reader could not tell
which cards went into it.

This is the missing step, and it is deliberately the smallest one that works:
paste the cards in the order given, on a uniform background, and record what
went in.

What it deliberately does not do
--------------------------------
- It does not render, resize or re-encode a card. The input cards are the
  artifact; this module only decides where they sit.
- It does not reorder, dedupe or drop a card. The caller's order is the order.
- It does not decide whether a long image is the right format for a platform.
  That is a delivery policy, so the caller passes ``--with-long-image``
  explicitly; there is no default-on path.
- It never approves or publishes. ``production_ready`` and
  ``publish_authorized`` are not fields here because they are not this
  layer's to set.

Input contract
--------------
Every card must already be the final size. Cards of differing widths are
refused rather than padded or scaled: silently letterboxing a 1080 card next
to a 1200 card produces a picture nobody signed off on.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

SCHEMA = "contentops.long-image/v1"

#: PIL's own decompression-bomb threshold. Past this the paste is refused here
#: rather than left to raise as a warning the caller never reads.
MAX_PIXELS = 89_478_485

DEFAULT_GAP = 36
DEFAULT_PAD = 60
DEFAULT_BACKGROUND: Tuple[int, int, int] = (11, 10, 9)


class LongImageError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class LongImagePlan:
    """Resolved geometry. Nothing here has touched a pixel yet."""

    cards: Tuple[Path, ...]
    out: Path
    widths: Tuple[int, ...]
    heights: Tuple[int, ...]
    gap: int
    pad: int
    background: Tuple[int, int, int]
    canvas_width: int
    canvas_height: int
    offsets: Tuple[int, ...] = field(default=())

    @property
    def pixels(self) -> int:
        return self.canvas_width * self.canvas_height


def _positive_int(value: Any, label: str, *, allow_zero: bool) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LongImageError("GEOMETRY_INVALID", f"{label} must be an int, got {value!r}")
    if value < 0 or (value == 0 and not allow_zero):
        raise LongImageError("GEOMETRY_INVALID", f"{label} must be positive, got {value}")
    return value


def _background(value: Any) -> Tuple[int, int, int]:
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        raise LongImageError(
            "BACKGROUND_INVALID", f"background must be an (r, g, b) triple, got {value!r}")
    channels: List[int] = []
    for channel in value:
        if isinstance(channel, bool) or not isinstance(channel, int) or not 0 <= channel <= 255:
            raise LongImageError(
                "BACKGROUND_INVALID", f"background channel {channel!r} is not 0-255")
        channels.append(channel)
    return (channels[0], channels[1], channels[2])


def _require_pillow():
    try:
        from PIL import Image  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - exercised only on a bare host
        raise LongImageError(
            "PILLOW_MISSING",
            "Pillow is not installed in this interpreter; refusing to guess at image sizes",
        ) from exc
    return Image


def plan(
    cards: Sequence[Path],
    out: Path,
    *,
    gap: int = DEFAULT_GAP,
    pad: int = DEFAULT_PAD,
    background: Tuple[int, int, int] = DEFAULT_BACKGROUND,
    max_pixels: int = MAX_PIXELS,
) -> LongImagePlan:
    """Resolve and validate every input. Raises before any file is written."""
    Image = _require_pillow()

    paths: List[Path] = []
    for candidate in cards:
        path = Path(candidate)
        if not path.is_file():
            raise LongImageError("CARD_MISSING", path.as_posix())
        paths.append(path.resolve())
    if not paths:
        raise LongImageError("EMPTY_INPUT", "no cards were given; a long image needs at least one")

    gap = _positive_int(gap, "gap", allow_zero=True)
    pad = _positive_int(pad, "pad", allow_zero=True)
    background = _background(background)
    max_pixels = _positive_int(max_pixels, "max_pixels", allow_zero=False)

    widths: List[int] = []
    heights: List[int] = []
    for path in paths:
        try:
            with Image.open(path) as image:
                width, height = image.size
        except LongImageError:
            raise
        except Exception as exc:
            raise LongImageError("CARD_UNDECODABLE", f"{path.as_posix()}: {exc}") from exc
        if width <= 0 or height <= 0:
            raise LongImageError("CARD_UNDECODABLE", f"{path.as_posix()} reports {width}x{height}")
        widths.append(width)
        heights.append(height)

    distinct = sorted(set(widths))
    if len(distinct) > 1:
        raise LongImageError(
            "MIXED_WIDTH",
            "cards must share one width, got " + ", ".join(str(w) for w in distinct),
        )

    canvas_width = distinct[0] + pad * 2
    canvas_height = pad * 2 + sum(heights) + gap * (len(heights) - 1)

    offsets: List[int] = []
    cursor = pad
    for height in heights:
        offsets.append(cursor)
        cursor += height + gap

    resolved_out = Path(out)
    if resolved_out.suffix.lower() not in (".png", ".jpg", ".jpeg"):
        raise LongImageError(
            "OUT_INVALID", f"expected .png/.jpg/.jpeg, got {resolved_out.suffix!r}")
    if not resolved_out.parent.is_dir():
        raise LongImageError("OUT_DIR_MISSING", resolved_out.parent.as_posix())

    plan_obj = LongImagePlan(
        cards=tuple(paths),
        out=resolved_out,
        widths=tuple(widths),
        heights=tuple(heights),
        gap=gap,
        pad=pad,
        background=background,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        offsets=tuple(offsets),
    )
    if plan_obj.pixels > max_pixels:
        raise LongImageError(
            "CANVAS_TOO_LARGE",
            f"{canvas_width}x{canvas_height} is {plan_obj.pixels} pixels, over the {max_pixels} limit",
        )
    return plan_obj


def build_receipt(p: LongImagePlan) -> Dict[str, Any]:
    """Bind inputs, geometry and the written output by digest."""
    if not p.out.is_file():
        raise LongImageError("OUTPUT_MISSING", p.out.as_posix())
    return {
        "schema": SCHEMA,
        "card_count": len(p.cards),
        "gap": p.gap,
        "pad": p.pad,
        "background": list(p.background),
        "canvas": {"width": p.canvas_width, "height": p.canvas_height},
        "inputs": [
            {
                "path": card.as_posix(),
                "sha256": _sha256(card),
                "width": width,
                "height": height,
                "offset_y": offset,
            }
            for card, width, height, offset in zip(p.cards, p.widths, p.heights, p.offsets)
        ],
        "output": {
            "path": p.out.as_posix(),
            "sha256": _sha256(p.out),
            "bytes": p.out.stat().st_size,
            "width": p.canvas_width,
            "height": p.canvas_height,
        },
        "authoritative": False,
        "note": "a long image is a deliverable, not an approval; publication stays a separate gate",
    }


def stitch(
    cards: Sequence[Path],
    out: Path,
    *,
    gap: int = DEFAULT_GAP,
    pad: int = DEFAULT_PAD,
    background: Tuple[int, int, int] = DEFAULT_BACKGROUND,
    max_pixels: int = MAX_PIXELS,
) -> Dict[str, Any]:
    """Paste the cards top to bottom and return the receipt.

    The output is written through a sibling temporary file and moved into place
    only once the canvas is complete, so an interrupted run never leaves a
    half-image that a later reader would mistake for a finished one.
    """
    Image = _require_pillow()
    p = plan(cards, out, gap=gap, pad=pad, background=background, max_pixels=max_pixels)

    canvas = Image.new("RGB", (p.canvas_width, p.canvas_height), p.background)
    try:
        for card, offset in zip(p.cards, p.offsets):
            with Image.open(card) as image:
                canvas.paste(image.convert("RGB"), (p.pad, offset))
    except Exception as exc:
        raise LongImageError("PASTE_FAILED", str(exc)) from exc

    temp = p.out.with_name(p.out.stem + ".partial" + p.out.suffix)
    try:
        save_kwargs: Dict[str, Any] = {}
        if p.out.suffix.lower() in (".jpg", ".jpeg"):
            save_kwargs["quality"] = 95
        else:
            save_kwargs["optimize"] = True
        canvas.save(temp, **save_kwargs)
        temp.replace(p.out)
    except Exception as exc:
        if temp.exists():
            temp.unlink()
        raise LongImageError("SAVE_FAILED", f"{p.out.as_posix()}: {exc}") from exc

    return build_receipt(p)


def write_receipt(project: Path, receipt: Dict[str, Any]) -> Path:
    """Write ``receipts/long-image.json`` under ``project``."""
    project = Path(project).resolve()
    if not project.is_dir():
        raise LongImageError("PROJECT_MISSING", project.as_posix())
    target = project / "receipts" / "long-image.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


__all__ = [
    "DEFAULT_BACKGROUND",
    "DEFAULT_GAP",
    "DEFAULT_PAD",
    "MAX_PIXELS",
    "SCHEMA",
    "LongImageError",
    "LongImagePlan",
    "build_receipt",
    "plan",
    "stitch",
    "write_receipt",
]
