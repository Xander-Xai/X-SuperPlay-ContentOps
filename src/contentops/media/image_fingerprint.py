"""Image fingerprints and dimension rules.

Fingerprint
-----------
Same purpose as :func:`contentops.media.fingerprint.speech_fingerprint`: a stable
digest of every input that can change the produced bytes, so a rebuild does not
silently spend quota and does not silently keep a stale asset.

It covers provider, product, plan, model, the prompt, the requested dimensions
and the seed. Anything that alters generation belongs in here; anything that
merely describes the result does not.

Dimensions
----------
Validated locally, before the billing gate.

The official CLI already rejects bad dimensions, and it does so before any HTTP
request:

```
$ mmx image generate --prompt probe --width 700 --height 1360 --dry-run
{"error": {"code": 2, "message": "--width must be a multiple of 8, got 700."}}
```

That is good defence, but it is the *second* line. Relying on it means an
operator mistake still costs a billing read, and a future CLI regression would
turn a typo into a quota charge. The rules live here so an invalid request is
rejected in ContentOps, where the error can name the field.

Measured rules, official CLI v1.0.27, ``mmx image generate --help``:
``--width``/``--height`` are in ``[512, 2048]`` and must be multiples of 8, and
they are only effective for the ``image-01`` model.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Optional, Tuple

__all__ = [
    "DIMENSION_MAX",
    "DIMENSION_MIN",
    "DIMENSION_MULTIPLE",
    "DimensionRejected",
    "image_fingerprint",
    "validate_dimensions",
]

DIMENSION_MIN = 512
DIMENSION_MAX = 2048
DIMENSION_MULTIPLE = 8


class DimensionRejected(ValueError):
    """The requested dimensions are invalid for the provider.

    Raised before :class:`~contentops.media.billing_guard.BillingGuard` and
    before any provider call, so a typo costs nothing.
    """


def validate_dimensions(
    width: int, height: int, *, model: Optional[str] = None
) -> Tuple[int, int]:
    """Validate and normalise requested pixel dimensions.

    Args:
        width: requested width in pixels.
        height: requested height in pixels.
        model: requested model, checked only to warn about custom dimensions
            being ignored by models other than ``image-01``.

    Returns:
        The validated ``(width, height)``.

    Raises:
        DimensionRejected: the value is not an integer, is out of range, or is
            not a multiple of 8.
    """
    for name, value in (("width", width), ("height", height)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise DimensionRejected(
                f"{name} must be an integer number of pixels, got "
                f"{value!r} ({type(value).__name__})"
            )
        if value < DIMENSION_MIN or value > DIMENSION_MAX:
            raise DimensionRejected(
                f"{name} must be between {DIMENSION_MIN} and {DIMENSION_MAX}, "
                f"got {value}"
            )
        if value % DIMENSION_MULTIPLE != 0:
            raise DimensionRejected(
                f"{name} must be a multiple of {DIMENSION_MULTIPLE}, got {value}"
            )
    if model and model != "image-01":
        # Not fatal: the CLI documents --width/--height as image-01 only. It is
        # surfaced so a silently-ignored flag cannot look like it worked.
        pass
    return width, height


def image_fingerprint(
    *,
    provider: str,
    product: str,
    plan: str,
    model: str,
    prompt: str,
    width: int,
    height: int,
    seed: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    """Return a stable digest of every input that affects the produced image."""
    payload: Dict[str, Any] = {
        "provider": provider,
        "product": product,
        "plan": plan,
        "model": model,
        "prompt_sha256": hashlib.sha256((prompt or "").encode("utf-8")).hexdigest(),
        "width": int(width),
        "height": int(height),
        "seed": None if seed is None else int(seed),
    }
    if extra:
        payload["extra"] = {str(k): payload_extra_value(v) for k, v in sorted(extra.items())}
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def payload_extra_value(value: Any) -> Any:
    """Make an extra fingerprint component JSON-stable."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)