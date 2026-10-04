"""Detect what an image file *actually* is, from its bytes.

Why the filename is not evidence
--------------------------------
M2.0 measured this on the real MiniMax image API:

======================  ==================  ==========================
what was requested      what came back      what the file was called
======================  ==================  ==========================
``output.png``          JPEG bytes          ``output.png``
======================  ==================  ==========================

The provider returned a JPEG from a ``.png`` request. ContentOps asked for PNG,
received JPEG, and — had it trusted the extension — would have handed a JPEG to
every downstream tool that selects a decoder by suffix. ``ffmpeg``, ``Pillow``
and the browser would each behave differently, and the failure would surface
somewhere far from its cause.

So this module is the only place allowed to decide an image's format, and it
decides from the **magic bytes**, never from the name.

Rules
-----
- ``detect_image_container`` returns ``"PNG"``, ``"JPEG"`` or ``"WEBP"``.
- Anything unknown, truncated or malformed raises :class:`ImageContainerError`.
  A guess is worse than a refusal: a wrong container silently produces a broken
  asset, whereas an exception stops the run while the cause is still visible.
- :func:`canonical_extension_for` maps a container to the suffix the canonical
  file must actually carry, so the extension and the bytes agree.

This is deliberately tiny and dependency-free. It runs before any decoder is
chosen, so it cannot itself depend on one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

__all__ = [
    "CANONICAL_EXTENSIONS",
    "SUPPORTED_CONTAINERS",
    "ImageContainerError",
    "canonical_extension_for",
    "detect_image_container",
    "image_container_extension",
    "sniff_image_file",
]


class ImageContainerError(ValueError):
    """The bytes are not a recognisable image, or are truncated.

    Raised instead of returning a best guess, because a wrong container
    produces a broken asset rather than a visible failure.
    """


#: Signatures, longest-first where prefixes overlap.
_MAGIC: Tuple[Tuple[str, bytes, int], ...] = (
    ("PNG", b"\x89PNG\r\n\x1a\n", 8),
    ("JPEG", b"\xff\xd8\xff", 3),
    ("WEBP", b"RIFF", 4),
)

#: What each container must be saved as. JPEG becomes ``.jpg``: it is the
#: extension every tool in the pipeline understands, and writing ``.jpeg``
#: invites suffix-based decoder selection to diverge again.
CANONICAL_EXTENSIONS: Dict[str, str] = {
    "PNG": ".png",
    "JPEG": ".jpg",
    "WEBP": ".webp",
}

SUPPORTED_CONTAINERS = tuple(CANONICAL_EXTENSIONS)


def _webp_container(data: bytes) -> bool:
    """A RIFF file is only WEBP when its form type says so.

    ``RIFF`` alone is not enough: AVI and WAV start the same way. The form type
    sits at offset 8, so the header must be at least 12 bytes.
    """
    if len(data) < 12:
        return False
    if data[0:4] != b"RIFF":
        return False
    return data[8:12] == b"WEBP"


def detect_image_container(data: bytes) -> str:
    """Return ``"PNG"``, ``"JPEG"`` or ``"WEBP"`` for the given bytes.

    Args:
        data: the leading bytes of the file. The whole file is not required for
            recognition, but the header must be complete.

    Raises:
        ImageContainerError: the data is empty, truncated before a signature can
            be read, or matches no supported container.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise ImageContainerError(
            f"expected image bytes, got {type(data).__name__}"
        )
    blob = bytes(data)
    if not blob:
        raise ImageContainerError("cannot detect a container from 0 bytes")

    for name, signature, header_len in _MAGIC:
        if name == "WEBP":
            if _webp_container(blob):
                return "WEBP"
            continue
        if len(blob) < header_len:
            raise ImageContainerError(
                f"only {len(blob)} byte(s) supplied; at least {header_len} are "
                f"needed to recognise a {name} header"
            )
        if blob[: len(signature)] == signature:
            return name

    shown = blob[:8].hex(" ")
    raise ImageContainerError(
        f"unrecognised image container; first bytes were [{shown}]. Supported "
        f"containers are {', '.join(SUPPORTED_CONTAINERS)}. The file extension "
        f"is not consulted, because a provider may return a different container "
        f"than the one requested."
    )


def sniff_image_file(path) -> str:
    """Detect the container of an image on disk.

    Only the first 64 KiB are read, which is far more than any of the signatures
    need and keeps this cheap for large files.
    """
    target = Path(path)
    try:
        with target.open("rb") as handle:
            head = handle.read(65536)
    except OSError as exc:
        raise ImageContainerError(f"cannot read {target}: {exc}") from exc
    return detect_image_container(head)


def canonical_extension_for(container: str) -> str:
    """The extension a canonical image of this container must carry."""
    try:
        return CANONICAL_EXTENSIONS[container]
    except KeyError:
        raise ImageContainerError(
            f"no canonical extension for container {container!r}; supported "
            f"containers are {', '.join(SUPPORTED_CONTAINERS)}"
        ) from None


def image_container_extension(container: str) -> str:
    """The extension the provider is asked to use, before sniffing.

    Recorded in the receipt as ``requested_extension`` so a mismatch is visible
    rather than normalised away silently.
    """
    return canonical_extension_for(container)