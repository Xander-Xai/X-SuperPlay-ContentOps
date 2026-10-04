"""Determine what a reference file *actually* is, from its content.

Why the filename is not evidence
--------------------------------
This is the same rule M3 established, reproduced twice by the real provider: a
``.png`` request came back as **JPEG bytes**. Trusting a suffix therefore breaks
in two directions — it can declare a format the bytes are not, and it can hide a
format the caller believed they had excluded.

For H3 references the cost of guessing is higher than for a local file. The
request body is a ``data:`` URI whose declared subtype the provider matches
against the bytes, so ``data:image/png`` carrying JPEG is a rejection the operator
would read as a generation problem rather than an encoding problem.

So the extension is never consulted to decide a media type. It is recorded beside
the detected type so a mismatch is **visible** rather than normalised away.

How each kind is determined
---------------------------
- **image** — M3's byte sniffer, reused as-is. That module is the single place
  allowed to decide an image's container, and duplicating its magic-byte logic
  here would create two places that could disagree. It recognises ``PNG``,
  ``JPEG`` and ``WEBP``, and raises for anything else.
- **video / audio** — ``ffprobe``, already the sanctioned probe in this
  repository. Codec and container are read from the file rather than its name.

What is deliberately **not** claimed
-----------------------------------
The documented H3 reference set includes HEIC/HEIF, and this module **does not
accept them**. The local ffmpeg build exposes no HEIF demuxer (only an AVIF
*encoder*), and M3's byte sniffer deliberately supports just PNG/JPEG/WEBP, so
there is no reliable way here to verify what a ``.heic`` file actually contains.
Declaring ``image/heic`` on the strength of the suffix would be exactly the
behaviour this module exists to remove, so a HEIC/HEIF reference is refused
locally instead. Converting it to PNG, JPEG or WEBP resolves it.

The same reasoning applies to any container outside the documented set: a refusal
before the billing gate, never a guessed subtype.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from contentops.media.image_container import (
    ImageContainerError,
    sniff_image_file,
)

__all__ = [
    "AUDIO_MIME_BY_CODEC",
    "IMAGE_MIME_BY_CONTAINER",
    "MEDIA_KINDS",
    "REFERENCE_ROLES",
    "ReferenceMediaError",
    "ValidatedReference",
    "detect_reference_mime",
    "resolve_reference",
]


class ReferenceMediaError(ValueError):
    """A reference file's real media type could not be determined.

    Raised before any billing read. An unverifiable reference is not a request
    worth sending, and guessing its type would move the failure to a place where
    nobody can see its cause.
    """


#: The three content kinds the documented API distinguishes.
MEDIA_KINDS: Tuple[str, ...] = ("image", "video", "audio")

#: Roles the documented schema defines. Assigned once, here, so a role can never
#: drift between validation and transport.
REFERENCE_ROLES: Tuple[str, ...] = (
    "first_frame",
    "last_frame",
    "reference_image",
    "reference_video",
    "reference_audio",
)

#: Detected image container -> declared data-URI subtype. Reused from M3's
#: canonical container names rather than restated, so the two cannot drift.
IMAGE_MIME_BY_CONTAINER: Dict[str, str] = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "WEBP": "image/webp",
}

#: The documented audio containers, keyed by the codec ffprobe reports. Only WAV
#: and MP3 are documented for H3 references, so an AAC-in-MP4 file is refused
#: rather than quietly accepted: it is a container the API has not documented for
#: reference audio.
AUDIO_MIME_BY_CODEC: Dict[str, str] = {
    "pcm_s16le": "audio/wav",
    "pcm_s24le": "audio/wav",
    "pcm_s32le": "audio/wav",
    "pcm_u8": "audio/wav",
    "pcm_f32le": "audio/wav",
    "pcm_f64le": "audio/wav",
    "mp3": "audio/mpeg",
    "mp3float": "audio/mpeg",
}

#: ffprobe reports a comma-separated *family*, not one container: both an MP4 and
#: a MOV come back as ``mov,mp4,m4a,3gp,3g2,mj2``. Both are documented for H3
#: references, and the only documented video data-URI subtype is ``video/mp4``,
#: so the whole family declares that and the precise name is recorded separately.
_VIDEO_DOCUMENTED_FAMILY = ("mp4", "mov", "m4a", "3gp", "3g2", "mj2")

#: Video codecs the documentation accepts for references. Anything else is a
#: real, readable file in an undocumented format, which is a refusal, not a guess.
_VIDEO_DOCUMENTED_CODECS = ("h264", "hevc", "av1")


@dataclass(frozen=True)
class ValidatedReference:
    """One reference, with the media type actually determined from its content.

    ``declared_extension`` and ``extension_matches`` are kept so a mismatch stays
    visible in the receipt. Normalising it away would hide the fact that a caller
    and the provider disagree about what a file is.
    """

    path: Path
    role: str
    media_kind: str
    mime_type: str
    detected_container: str
    declared_extension: str
    extension_matches: bool

    def as_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "media_kind": self.media_kind,
            "mime_type": self.mime_type,
            "detected_container": self.detected_container,
            "declared_extension": self.declared_extension,
            "extension_matches": self.extension_matches,
        }


def _expected_extension(mime_type: str, path: Path) -> Tuple[str, ...]:
    """Suffixes a file carrying this MIME would plausibly be named."""
    if mime_type == "image/jpeg":
        return (".jpg", ".jpeg")
    if mime_type == "image/png":
        return (".png",)
    if mime_type == "image/webp":
        return (".webp",)
    if mime_type == "video/mp4":
        return (".mp4", ".mov", ".m4v")
    if mime_type == "audio/wav":
        return (".wav",)
    if mime_type == "audio/mpeg":
        return (".mp3",)
    return (path.suffix.lower(),)


def detect_reference_mime(path: Path, *, media_kind: str) -> ValidatedReference:
    """Determine a reference's real media type and return it with its role.

    Args:
        path: the local reference file.
        media_kind: ``image``, ``video`` or ``audio``. Chooses the detection path;
            it is a caller assertion about intent, and a disagreement between it
            and the bytes is reported rather than resolved silently.

    Raises:
        ReferenceMediaError: the real media type could not be determined, or it is
            outside the documented set for H3 references.
    """
    target = Path(path)
    if media_kind not in MEDIA_KINDS:
        raise ReferenceMediaError(
            f"unknown media_kind {media_kind!r}; expected one of "
            f"{', '.join(MEDIA_KINDS)}"
        )
    if media_kind == "image":
        return _detect_image(target)
    return _detect_av(target, media_kind)


def _detect_image(path: Path) -> ValidatedReference:
    """Reuse M3's byte sniffer. No magic-byte logic is duplicated here."""
    try:
        container = sniff_image_file(path)
    except ImageContainerError as exc:
        raise ReferenceMediaError(
            f"reference {path.name} could not be verified as a PNG, JPEG or WEBP "
            f"image: {exc} HEIC/HEIF and AVIF are not accepted because this "
            f"environment has no reliable way to verify those containers; convert "
            f"the file to PNG, JPEG or WEBP."
        ) from exc
    mime = IMAGE_MIME_BY_CONTAINER.get(container)
    if mime is None:
        raise ReferenceMediaError(
            f"reference {path.name} was detected as {container}, which has no "
            f"declared subtype for an H3 reference"
        )
    return _reference(path, "image", mime, container)


def _detect_av(path: Path, media_kind: str) -> ValidatedReference:
    """Derive the media type from ffprobe, never from the extension."""
    from contentops.media.transport import ffprobe_json

    try:
        payload = ffprobe_json(path)
    except Exception as exc:  # noqa: BLE001
        raise ReferenceMediaError(
            f"reference {path.name} could not be probed, so its real media type "
            f"could not be determined: {exc}"
        ) from exc

    streams = payload.get("streams") or []
    wanted = "video" if media_kind == "video" else "audio"
    stream = next(
        (s for s in streams if s.get("codec_type") == wanted), None
    )
    if stream is None:
        present = sorted({
            str(s.get("codec_type")) for s in streams if s.get("codec_type")
        })
        raise ReferenceMediaError(
            f"reference {path.name} was expected to be {wanted} but contains "
            f"{', '.join(present) if present else 'no media streams'}. The "
            f"extension is not trusted, so this is refused rather than guessed."
        )

    family = _format_family(payload)
    codec = str(stream.get("codec_name") or "").lower()

    if media_kind == "video":
        if not any(token in family for token in _VIDEO_DOCUMENTED_FAMILY):
            raise ReferenceMediaError(
                f"reference {path.name} is in container family "
                f"{family or 'unknown'!r}, which the H3 documentation does not "
                f"list for video references (MP4, MOV)"
            )
        if codec and codec not in _VIDEO_DOCUMENTED_CODECS:
            raise ReferenceMediaError(
                f"reference {path.name} carries video codec {codec!r}, which the "
                f"H3 documentation does not list for references (H.264, H.265)"
            )
        # One declared subtype for the family, because it is the only documented
        # video data URI. The precise container is recorded alongside it.
        container = "MP4" if "mp4" in family or not family else "MOV"
        return _reference(path, "video", "video/mp4", container)

    mime = AUDIO_MIME_BY_CODEC.get(codec)
    if mime is None:
        raise ReferenceMediaError(
            f"reference {path.name} carries audio codec {codec!r} in container "
            f"family {family or 'unknown'!r}. The H3 documentation lists only WAV "
            f"and MP3 for reference audio, so this is refused rather than guessed."
        )
    return _reference(path, "audio", mime, "WAV" if mime.endswith("wav") else "MP3")


def _format_family(payload: Dict[str, Any]) -> Tuple[str, ...]:
    raw = str((payload.get("format") or {}).get("format_name") or "")
    return tuple(token.strip().lower() for token in raw.split(",") if token.strip())


def _reference(
    path: Path, media_kind: str, mime: str, container: str
) -> ValidatedReference:
    suffix = path.suffix.lower()
    expected = _expected_extension(mime, path)
    return ValidatedReference(
        path=path,
        role="",
        media_kind=media_kind,
        mime_type=mime,
        detected_container=container,
        declared_extension=suffix,
        extension_matches=suffix in expected,
    )


def resolve_reference(path: Path, *, role: str, media_kind: str) -> ValidatedReference:
    """Detect the media type and bind it to a documented role."""
    if role not in REFERENCE_ROLES:
        raise ReferenceMediaError(
            f"unknown reference role {role!r}; expected one of "
            f"{', '.join(REFERENCE_ROLES)}"
        )
    detected = detect_reference_mime(path, media_kind=media_kind)
    return ValidatedReference(
        path=detected.path,
        role=role,
        media_kind=detected.media_kind,
        mime_type=detected.mime_type,
        detected_container=detected.detected_container,
        declared_extension=detected.declared_extension,
        extension_matches=detected.extension_matches,
    )
