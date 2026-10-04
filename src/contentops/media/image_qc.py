"""Image technical QC: measurable facts only.

What this may and may not conclude
----------------------------------
It may say the file is a decodable PNG, 768x1360, with a luminance standard
deviation of 41. It may **not** say the image is beautiful, on-brand,
publishable or high quality. Those are human judgements and :mod:`phase16`-level
review exists for them. An automated gate that reports "publishable" teaches the
pipeline to trust itself, which is how a broken frame reaches the Founder.

``approved`` therefore means "technically sound", never "good".

Blank and near-uniform detection
--------------------------------
A generated image that fails to render often returns a solid fill, a mid-grey
canvas or a flat gradient. Those decode fine and look like a real image to every
naive check, so they are caught here by pixel statistics: a standard deviation
below the floor, or a luma range below the span floor, is a blank.

Decoding
--------
``Pillow`` is used because decoding is the only way to measure real pixels. It is
imported lazily so that container sniffing, fingerprinting and dimension
validation keep working on a host without it, and so that CI can skip the
decode-dependent tests rather than fail on a missing optional dependency.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

__all__ = [
    "HAVE_PILLOW",
    "IMAGE_QC_MIN_LUMA_STDDEV",
    "IMAGE_QC_MIN_LUMA_SPAN",
    "IMAGE_QC_MIN_FILE_BYTES",
    "TechnicalImageQC",
    "measure_image",
    "technical_image_qc",
]

#: A real render has luminance spread. Below this standard deviation the image is
#: treated as blank or flat.
IMAGE_QC_MIN_LUMA_STDDEV = 6.0

#: A real render spans a meaningful brightness range end to end.
IMAGE_QC_MIN_LUMA_SPAN = 24.0

#: Floor applied to *provider output* by verify_output(), not to arbitrary
#: images. Kept here as the shared constant for both modules.
IMAGE_QC_MIN_FILE_BYTES = 1024

#: Aspect-ratio tolerance. 9:16 is 0.5625; providers may return nearby
#: dimensions, so exact equality is the wrong test.
IMAGE_QC_ASPECT_TOLERANCE = 0.02

#: How often the image is sampled for pixel statistics. Full-resolution
#: statistics on a 4K PNG are slow and no more informative than a grid.
IMAGE_QC_SAMPLE_COUNT = 96

try:  # pragma: no cover - availability differs per host
    from PIL import Image  # noqa: F401

    HAVE_PILLOW = True
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]
    HAVE_PILLOW = False


@dataclass
class TechnicalImageQC:
    """Measurable facts about one image file."""

    approved: bool = False
    reasons: list = field(default_factory=list)
    container: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    aspect_ratio: Optional[float] = None
    aspect_ratio_expected: Optional[float] = None
    luma_stddev: Optional[float] = None
    luma_span: Optional[float] = None
    luma_mean: Optional[float] = None
    file_bytes: int = 0
    alpha_present: Optional[bool] = None
    decoder: Optional[str] = None
    text_contamination_suspected: Optional[bool] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "approved": self.approved,
            "reasons": list(self.reasons),
            "container": self.container,
            "width": self.width,
            "height": self.height,
            "aspect_ratio": self.aspect_ratio,
            "aspect_ratio_expected": self.aspect_ratio_expected,
            "luma_stddev": self.luma_stddev,
            "luma_span": self.luma_span,
            "luma_mean": self.luma_mean,
            "file_bytes": self.file_bytes,
            "alpha_present": self.alpha_present,
            "decoder": self.decoder,
            "text_contamination_suspected": self.text_contamination_suspected,
        }


def _sample_luma_stats(image) -> Dict[str, float]:
    """Mean, standard deviation and span of luma over a sampled grid."""
    width, height = image.size
    xs = [int((i + 0.5) * width / IMAGE_QC_SAMPLE_COUNT) for i in range(IMAGE_QC_SAMPLE_COUNT)]
    xs = [min(max(x, 0), width - 1) for x in xs]
    ys = [int((j + 0.5) * height / IMAGE_QC_SAMPLE_COUNT) for j in range(IMAGE_QC_SAMPLE_COUNT)]
    ys = [min(max(y, 0), height - 1) for y in ys]

    grid = image.convert("L").resize((32, 32), Image.BILINEAR)
    pixels = list(grid.getdata())
    count = len(pixels)
    mean = sum(pixels) / count
    variance = sum((p - mean) ** 2 for p in pixels) / count
    return {
        "luma_mean": round(mean, 4),
        "luma_stddev": round(math.sqrt(variance), 4),
        "luma_span": round(float(max(pixels) - min(pixels)), 4),
    }


def measure_image(path) -> TechnicalImageQC:
    """Measure one image file. Never raises for a merely-bad image.

    A container that cannot be recognised, or bytes that cannot be decoded, are
    reported as failures in the result rather than raised, so a caller gets one
    object describing everything wrong with the file.
    """
    from contentops.media.image_container import ImageContainerError, sniff_image_file

    result = TechnicalImageQC()
    target = Path(path)

    if not target.is_file():
        result.reasons.append(f"file does not exist: {target}")
        return result

    size = target.stat().st_size
    result.file_bytes = size
    if size == 0:
        result.reasons.append("file is empty")
        return result
    # A small file is NOT itself a QC failure. PNG compresses hard, so a valid
    # 64x112 image can be well under a kilobyte, and rejecting it would be wrong.
    # Truncated provider output is caught twice over: verify_output() refuses a
    # too-small response before QC ever runs, and a truncated body fails to
    # decode below. The byte count is recorded for diagnosis, not used as a gate.

    try:
        result.container = sniff_image_file(target)
    except ImageContainerError as exc:
        result.reasons.append(f"container could not be detected: {exc}")
        return result

    if not HAVE_PILLOW:
        result.reasons.append(
            "decoder unavailable: Pillow is not installed, so pixels could not "
            "be measured"
        )
        return result

    try:
        with Image.open(target) as image:
            image.load()
            result.decoder = "pillow"
            result.width, result.height = image.size
            mode = image.mode
            result.alpha_present = mode in ("RGBA", "LA", "PA")
            if result.width <= 0 or result.height <= 0:
                result.reasons.append("decoded image has a zero dimension")
                return result
            if result.alpha_present and max(image.getextrema()[-1]) == 0:
                result.reasons.append("alpha channel is entirely transparent")
            result.aspect_ratio = round(result.width / result.height, 6)
            result.__dict__.update(_sample_luma_stats(image))
    except Exception as exc:  # noqa: BLE001 - a decoder error is a QC failure
        result.reasons.append(f"image could not be decoded: {type(exc).__name__}")
        return result

    if result.luma_stddev is not None and result.luma_stddev < IMAGE_QC_MIN_LUMA_STDDEV:
        result.reasons.append(
            f"image is blank or nearly uniform (luma stddev "
            f"{result.luma_stddev} < {IMAGE_QC_MIN_LUMA_STDDEV})"
        )
    if result.luma_span is not None and result.luma_span < IMAGE_QC_MIN_LUMA_SPAN:
        result.reasons.append(
            f"image is nearly uniform (luma span {result.luma_span} < "
            f"{IMAGE_QC_MIN_LUMA_SPAN})"
        )

    result.approved = not result.reasons
    return result


def technical_image_qc(
    path,
    *,
    expected_width: Optional[int] = None,
    expected_height: Optional[int] = None,
    expected_aspect: Optional[float] = None,
    aspect_tolerance: float = IMAGE_QC_ASPECT_TOLERANCE,
    require_container: Optional[str] = None,
) -> TechnicalImageQC:
    """Measure an image and check it against what was asked for.

    Aspect ratio is compared with a tolerance rather than exactly. A provider may
    return 768x1360 when 9:16 was requested, which is close enough for a video
    frame; demanding exact equality would reject correct output.

    Args:
        expected_width: required exact width, or ``None`` to skip.
        expected_height: required exact height, or ``None`` to skip.
        expected_aspect: required aspect ratio, within ``aspect_tolerance``.
        aspect_tolerance: allowed relative deviation, default 0.02.
        require_container: the container the receipt claims; a mismatch is a
            cache-miss signal upstream and a failure here.
    """
    result = measure_image(path)

    if expected_aspect and result.aspect_ratio is not None:
        result.aspect_ratio_expected = expected_aspect
        deviation = abs(result.aspect_ratio - expected_aspect) / expected_aspect
        if deviation > aspect_tolerance:
            result.reasons.append(
                f"aspect ratio {result.aspect_ratio} deviates from the expected "
                f"{expected_aspect} by {deviation:.4f}, beyond the tolerance "
                f"{aspect_tolerance}"
            )

    if expected_width is not None and result.width is not None and result.width != expected_width:
        result.reasons.append(
            f"width {result.width} does not match the requested {expected_width}"
        )
    if expected_height is not None and result.height is not None and result.height != expected_height:
        result.reasons.append(
            f"height {result.height} does not match the requested {expected_height}"
        )

    if require_container and result.container and result.container != require_container:
        result.reasons.append(
            f"container {result.container} does not match the receipt's "
            f"{require_container}"
        )

    result.approved = not result.reasons
    return result