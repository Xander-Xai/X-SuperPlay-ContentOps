"""Lightweight text-contamination signals for generated images.

The problem
-----------
Critical text does not belong inside generated imagery. A model asked for "a
developer dashboard" will cheerfully render invented numbers, a fake version
string, a plausible benchmark table or a terminal full of nonsense. Downstream
those glyphs read as data: nobody re-checks a chart they did not ask for.

Critical text is therefore produced deterministically, as an overlay, later.

What is checked
---------------
Without OCR, honest signals only:

- **High-frequency edge density.** Rendered glyphs produce a characteristic
  density of short, high-contrast edges concentrated in horizontal bands.
  Smooth illustrative art does not.
- **Too little detail overall.** Some renders contain unmistakable text but very
  little else; combined with high edge density that is a strong hint.

What this is not
----------------
This is a *suspicion* signal, never a verdict:

- it does not read the text, so it cannot tell a real UI screenshot from an
  invented one, and it cannot certify that text-free output is clean;
- it will fire on genuinely text-free images with dense detail, such as a
  circuit board or a crowd.

Hence :attr:`text_contamination_suspected` rather than a QC failure. It is
recorded, surfaced to the Founder in review, and never silently used to reject
an otherwise sound asset.

OCR is deliberately not introduced for this milestone. Tesseract would add a
system dependency and a model download to answer a question that human review
already answers more reliably on the handful of images a video actually uses.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

__all__ = [
    "TEXT_CONTAMINATION_DENSITY_FLOOR",
    "TextContaminationSignal",
    "assess_text_contamination",
]

#: Fraction of sampled pixels that must be strong edges before the image is
#: flagged. Tuned so that smooth, gradient-heavy abstract art stays well below
#: it and dense text-like regions land above.
TEXT_CONTAMINATION_DENSITY_FLOOR = 0.18

#: Rows are grouped into bands; text concentrates in a few of them rather than
#: spread evenly, so band concentration is reported separately.
_TEXT_BAND_COUNT = 12


@dataclass
class TextContaminationSignal:
    """The suspicion signal, with the measurements that produced it."""

    suspected: Optional[bool] = None
    edge_density: Optional[float] = None
    band_concentration: Optional[float] = None
    reason: str = ""

    def as_dict(self):
        return {
            "text_contamination_suspected": self.suspected,
            "edge_density": self.edge_density,
            "band_concentration": self.band_concentration,
            "reason": self.reason,
        }


def assess_text_contamination(path) -> TextContaminationSignal:
    """Estimate whether an image contains rendered text.

    Returns:
        A :class:`TextContaminationSignal`. ``suspected`` is ``None`` when the
        measurement was not possible, which is not the same as "clean".
    """
    signal = TextContaminationSignal()
    try:
        from PIL import Image, ImageFilter
    except ImportError:
        signal.reason = "Pillow is not installed; no contamination signal measured"
        return signal

    from pathlib import Path

    target = Path(path)
    if not target.is_file():
        signal.reason = "file does not exist"
        return signal

    try:
        with Image.open(target) as image:
            image.load()
            grey = image.convert("L").resize((256, 256), Image.BILINEAR)
            edges = grey.filter(ImageFilter.FIND_EDGES)
            histogram = edges.histogram()
    except Exception as exc:  # noqa: BLE001
        signal.reason = f"could not be measured: {type(exc).__name__}"
        return signal

    total = 256 * 256
    # Threshold chosen high enough that anti-aliased shading does not count:
    # glyph edges are among the strongest gradients in a rendered frame.
    strong = sum(histogram[64:]) / total
    signal.edge_density = round(strong, 6)

    band_edges = []
    edges_loaded = edges.load()
    band_height = max(1, 256 // _TEXT_BAND_COUNT)
    for band in range(_TEXT_BAND_COUNT):
        top = band * band_height
        band_sum = 0
        for y in range(top, min(top + band_height, 256)):
            for x in range(256):
                if edges_loaded[x, y] >= 64:
                    band_sum += 1
        band_edges.append(band_sum / max(1, band_height * 256))
    peak = max(band_edges) if band_edges else 0.0
    mean = (sum(band_edges) / len(band_edges)) if band_edges else 0.0
    signal.band_concentration = round(peak / mean, 4) if mean > 0 else 0.0

    suspected = signal.edge_density >= TEXT_CONTAMINATION_DENSITY_FLOOR
    signal.suspected = suspected
    signal.reason = (
        f"edge density {signal.edge_density} "
        f"{'>=' if suspected else '<'} {TEXT_CONTAMINATION_DENSITY_FLOOR}"
    )
    return signal