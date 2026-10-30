"""Is this file actually a raster image at the canvas the account requires?

The delivery gate says an *actual* 1600x900 PNG or JPEG, and that an SVG alone is
not uploadable to X. A path with the right extension proves nothing, so this
reads the file's own header: PNG IHDR, or the JPEG start-of-frame segment.

Standard library only. Reading eight bytes correctly does not justify a Pillow
dependency, and the repository's rule is that a new dependency has to answer why
the stdlib is insufficient.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

#: X's own upload cap is far higher, but a card larger than this is not a card.
MAX_IMAGE_BYTES = 20 * 1024 * 1024

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

#: Frame headers that carry the dimensions. C4 (DHT), C8 (JPG) and CC (DAC) do
#: not, and a decoder that read them as if they did would report nonsense.
JPEG_SOF_MARKERS = frozenset(
    {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
)


class UndecodableImage(ValueError):
    """The bytes are not a PNG or JPEG this module can measure."""


@dataclass(frozen=True)
class ImageFacts:
    format: str
    width: int
    height: int

    def as_dict(self) -> dict:
        return {"format": self.format, "width": self.width, "height": self.height}


def sniff(data: bytes) -> Optional[str]:
    """``"png"``, ``"jpeg"``, or ``None`` when the bytes are neither."""
    if data.startswith(PNG_SIGNATURE):
        return "png"
    if data[:2] == b"\xff\xd8":
        return "jpeg"
    return None


def _png_size(data: bytes) -> Tuple[int, int]:
    # signature (8) | length (4) | "IHDR" (4) | width (4) | height (4)
    if len(data) < 24 or data[12:16] != b"IHDR":
        raise UndecodableImage("PNG does not start with an IHDR chunk")
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def _jpeg_size(data: bytes) -> Tuple[int, int]:
    position = 2
    while position + 4 <= len(data):
        if data[position] != 0xFF:
            position += 1
            continue
        marker = data[position + 1]
        # Standalone markers carry no length field.
        if marker in (0x01, 0xD8) or 0xD0 <= marker <= 0xD7:
            position += 2
            continue
        if marker == 0xD9:  # end of image, before any frame header
            break
        length = int.from_bytes(data[position + 2:position + 4], "big")
        if length < 2:
            raise UndecodableImage(f"JPEG segment 0x{marker:02X} has length {length}")
        if marker in JPEG_SOF_MARKERS:
            if position + 9 > len(data):
                raise UndecodableImage("JPEG frame header is truncated")
            height = int.from_bytes(data[position + 5:position + 7], "big")
            width = int.from_bytes(data[position + 7:position + 9], "big")
            return width, height
        position += 2 + length
    raise UndecodableImage("JPEG has no start-of-frame segment")


def image_facts(path: Path) -> ImageFacts:
    """Measure the file at ``path``. Raises for a missing or unreadable image."""
    path = Path(path)
    size = path.stat().st_size
    if size > MAX_IMAGE_BYTES:
        raise UndecodableImage(f"{path.name} is {size} bytes, over the {MAX_IMAGE_BYTES}-byte limit")
    data = path.read_bytes()
    kind = sniff(data)
    if kind is None:
        raise UndecodableImage(f"{path.name} is not a PNG or JPEG (no matching magic bytes)")
    width, height = _png_size(data) if kind == "png" else _jpeg_size(data)
    if width <= 0 or height <= 0:
        raise UndecodableImage(f"{path.name} reports a {width}x{height} canvas")
    return ImageFacts(format=kind, width=width, height=height)
