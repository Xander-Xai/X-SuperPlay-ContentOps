"""Semantic segment delivery for the native T2A adapter. Issue #34, narration v2.

Why segments exist
------------------
A whole narration in one request can only carry one set of generation
parameters, and one provider failure or one bad sentence costs the entire
take. The narration this round corrects was mechanically flat for a related
reason at the text level; at the delivery level the fix is to make the unit of
generation the *semantic segment*:

- **segment-level parameters** -- an emotion and a speed that can differ per
  segment (``voice_setting.emotion`` / ``voice_setting.speed``);
- **partial regeneration** -- a named segment can be re-synthesised on its own
  without touching the others and without paying for the others again;
- **a content-addressed segment cache** -- audio is keyed by everything that
  changes what the provider would produce, so an unchanged segment is never
  re-requested (the same principle as :mod:`contentops.media.minimax_speech`'s
  cache, applied per segment);
- **deterministic concatenation** -- the joins are a pure function of the
  segment order and the declared gaps, so the joined file can be rebuilt from
  the cache without any provider call.

What the cache fingerprint covers
---------------------------------
Everything that changes the audio: provider, transport, model, voice, the
synthesis text (lexicon applied, pause markers included), emotion, speed,
sample rate, format, channel and the lexicon fingerprint component. It
deliberately does **not** cover ``pause_after_s``: a gap after a segment alters
the joined file, not the segment's own audio, so changing a gap must not throw
away a perfectly valid cached take. The join records its own gaps.

Cache validation is fail-closed in the same direction as the rest of the
repository: a missing, corrupt or hash-mismatched cache entry is a **miss**
(the segment is regenerated), never a reason to trust bytes that cannot be
proven to be the ones the receipt describes.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

from process_utils import hidden_run  # noqa: E402

from .clone_route import billable_characters  # noqa: E402
from .minimax_native_tts import (  # noqa: E402
    build_t2a_payload,
    normalize_paragraph_newlines,
)

__all__ = [
    "ACTION_GENERATE",
    "ACTION_REUSE_CACHE",
    "ROLES",
    "CachedSegment",
    "RenderPlanEntry",
    "SegmentSpec",
    "build_segment_payload",
    "cache_paths",
    "concatenate_segments",
    "estimated_billable_characters",
    "lookup_cached_segment",
    "make_silence",
    "plan_segment_renders",
    "segment_fingerprint",
    "segment_synthesis_text",
    "store_cached_segment",
]

#: The semantic roles a script segment can declare. Kept here rather than in the
#: spoken-script module so the delivery layer and the editorial layer share one
#: vocabulary instead of two lists that can drift.
ROLES: Tuple[str, ...] = ("INTRO", "PROBLEM", "EVIDENCE", "TURN", "CONCLUSION")

ACTION_GENERATE = "GENERATE"
ACTION_REUSE_CACHE = "REUSE_CACHE"

SEGMENT_CACHE_SCHEMA = "contentops.t2a-segment-cache/v1"
SEGMENT_FINGERPRINT_SCHEMA = "contentops.t2a-segment/v1"


@dataclass(frozen=True)
class SegmentSpec:
    """One semantic segment, decided before anything is sent.

    ``text`` is the display-form segment text (the spoken script's segment as
    authored); the lexicon is applied when the payload is built. ``emotion``
    follows the same rule as the payload builder: ``None`` means "let the model
    auto-detect", never a guessed default.
    """

    id: str
    role: str
    text: str
    emotion: Optional[str] = None
    speed: float = 1.0
    pause_after_s: float = 0.0

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("segment id must be non-empty")
        if self.role not in ROLES:
            raise ValueError(f"segment {self.id}: role {self.role!r} not in {ROLES}")
        if self.speed <= 0:
            raise ValueError(f"segment {self.id}: speed must be positive")
        if self.pause_after_s < 0:
            raise ValueError(f"segment {self.id}: pause_after_s must not be negative")


def segment_synthesis_text(spec: SegmentSpec, lexicon: Any = None) -> str:
    """The exact text this segment will synthesise, lexicon applied."""
    spoken = lexicon.spoken_text(spec.text) if lexicon is not None else spec.text
    return normalize_paragraph_newlines(spoken)


def build_segment_payload(
    spec: SegmentSpec,
    *,
    voice_id: str,
    model: str,
    lexicon: Any = None,
    sample_rate: int = 32000,
    fmt: str = "wav",
    channel: int = 1,
) -> Dict[str, Any]:
    """Build the documented payload for one segment.

    Everything that could differ from the authorised request -- speech text,
    voice, model, emotion, speed, stream mode -- is validated by
    :func:`contentops.media.minimax_native_tts.build_t2a_payload` before the
    payload exists. Pause markers in the segment text are validated there too.
    """
    payload = build_t2a_payload(
        text=segment_synthesis_text(spec, lexicon),
        voice_id=voice_id,
        model=model,
        speed=spec.speed,
        emotion=spec.emotion,
        sample_rate=sample_rate,
        fmt=fmt,
        channel=channel,
        pronunciation_entries=lexicon.tone_entries() if lexicon is not None else None,
    )
    if payload["voice_setting"]["voice_id"] != voice_id:
        raise RuntimeError("payload voice_id disagrees with the authorised voice")
    if payload["model"] != model:
        raise RuntimeError("payload model disagrees with the authorised model")
    if payload["stream"] is not False:
        raise RuntimeError("payload must be non-streaming")
    return payload


def segment_fingerprint(
    *,
    voice_id: str,
    model: str,
    synthesis_text: str,
    emotion: Optional[str],
    speed: float,
    sample_rate: int,
    fmt: str,
    channel: int,
    lexicon_component: str,
) -> str:
    """Content-address one segment's audio.

    Deterministic by construction: the canonical JSON below is the entire
    fingerprint input, and any field that could change the provider's output is
    present. See the module docstring for why ``pause_after_s`` is not.
    """
    blob = json.dumps(
        {
            "schema": SEGMENT_FINGERPRINT_SCHEMA,
            "provider": "minimax",
            "transport": "native_http_cn",
            "model": model,
            "voice_id": voice_id,
            "synthesis_text_sha256": hashlib.sha256(
                synthesis_text.encode("utf-8")
            ).hexdigest(),
            "emotion": emotion,
            "speed": float(speed),
            "sample_rate": int(sample_rate),
            "format": fmt,
            "channel": int(channel),
            "output_format": "hex",
            "lexicon_component": lexicon_component,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def cache_paths(cache_dir: Path, fingerprint: str) -> Tuple[Path, Path, Path]:
    """``(raw, normalised, meta)`` paths for one fingerprint."""
    base = Path(cache_dir)
    return (
        base / f"{fingerprint}-raw.wav",
        base / f"{fingerprint}.wav",
        base / f"{fingerprint}.json",
    )


@dataclass(frozen=True)
class CachedSegment:
    """A validated cache entry. The meta is the stored provenance record."""

    fingerprint: str
    raw_path: Path
    normalised_path: Path
    meta: Dict[str, Any]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def lookup_cached_segment(cache_dir: Path, fingerprint: str) -> Optional[CachedSegment]:
    """Return the validated cache entry, or ``None`` for a miss.

    Every failure is a miss and nothing more: a partial write, a json that does
    not parse, a fingerprint that does not match the request, or either file's
    hash disagreeing with the record. Regenerating is cheap; trusting bytes
    that cannot be proven to be the recorded ones is not possible to undo.
    """
    raw_path, normalised_path, meta_path = cache_paths(cache_dir, fingerprint)
    if not meta_path.is_file() or not raw_path.is_file() or not normalised_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(meta, dict) or meta.get("schema") != SEGMENT_CACHE_SCHEMA:
        return None
    if meta.get("fingerprint") != fingerprint:
        return None
    if raw_path.stat().st_size <= 1024 or normalised_path.stat().st_size <= 1024:
        return None
    try:
        if _sha256_file(raw_path) != meta.get("raw_sha256"):
            return None
        if _sha256_file(normalised_path) != meta.get("normalised_sha256"):
            return None
    except OSError:
        return None
    return CachedSegment(
        fingerprint=fingerprint,
        raw_path=raw_path,
        normalised_path=normalised_path,
        meta=meta,
    )


def store_cached_segment(
    cache_dir: Path,
    fingerprint: str,
    *,
    raw_bytes: bytes,
    normalised_path: Path,
    meta: Dict[str, Any],
) -> CachedSegment:
    """Persist one segment's raw bytes and normalised audio under its fingerprint.

    The raw provider bytes are the provenance artefact and are stored verbatim;
    the normalised copy is a deterministic local derivative that the join
    consumes. Both hashes go into the record, so a later cache hit is checkable
    against exactly what is on disk.
    """
    base = Path(cache_dir)
    base.mkdir(parents=True, exist_ok=True)
    raw_path, cached_normalised, meta_path = cache_paths(base, fingerprint)
    raw_path.write_bytes(raw_bytes)
    shutil.copyfile(normalised_path, cached_normalised)
    record = {
        "schema": SEGMENT_CACHE_SCHEMA,
        "fingerprint": fingerprint,
        "raw_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "normalised_sha256": _sha256_file(cached_normalised),
        "raw_bytes": len(raw_bytes),
        "normalised_bytes": cached_normalised.stat().st_size,
        **meta,
    }
    meta_path.write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return CachedSegment(
        fingerprint=fingerprint,
        raw_path=raw_path,
        normalised_path=cached_normalised,
        meta=record,
    )


@dataclass(frozen=True)
class RenderPlanEntry:
    """One segment's decided fate: reuse the cache or make one provider call."""

    spec: SegmentSpec
    synthesis_text: str
    fingerprint: str
    action: str
    cached: Optional[CachedSegment] = None


def plan_segment_renders(
    segments: Sequence[SegmentSpec],
    *,
    voice_id: str,
    model: str,
    lexicon: Any,
    cache_dir: Path,
    regenerate_ids: Iterable[str] = (),
    sample_rate: int = 32000,
    fmt: str = "wav",
    channel: int = 1,
) -> List[RenderPlanEntry]:
    """Decide, before any network access, which segments need a provider call.

    ``regenerate_ids`` forces a fresh call for the named segments even when a
    valid cache entry exists -- the partial-regeneration switch. An id that is
    not in ``segments`` is a refusal rather than a silent no-op, because the
    likely cause is a typo and a typo that regenerates nothing looks exactly
    like a regeneration that happened.
    """
    by_id = {spec.id: spec for spec in segments}
    if len(by_id) != len(segments):
        raise ValueError("segment ids must be unique")
    regenerate = set(regenerate_ids)
    unknown = sorted(regenerate - set(by_id))
    if unknown:
        raise ValueError(f"regenerate ids not in this segment set: {unknown}")

    lexicon_component = (
        lexicon.fingerprint_component() if lexicon is not None else "no-lexicon"
    )
    plan: List[RenderPlanEntry] = []
    for spec in segments:
        synthesis = segment_synthesis_text(spec, lexicon)
        fingerprint = segment_fingerprint(
            voice_id=voice_id,
            model=model,
            synthesis_text=synthesis,
            emotion=spec.emotion,
            speed=spec.speed,
            sample_rate=sample_rate,
            fmt=fmt,
            channel=channel,
            lexicon_component=lexicon_component,
        )
        cached = lookup_cached_segment(cache_dir, fingerprint)
        if spec.id in regenerate or cached is None:
            plan.append(
                RenderPlanEntry(
                    spec=spec,
                    synthesis_text=synthesis,
                    fingerprint=fingerprint,
                    action=ACTION_GENERATE,
                )
            )
        else:
            plan.append(
                RenderPlanEntry(
                    spec=spec,
                    synthesis_text=synthesis,
                    fingerprint=fingerprint,
                    action=ACTION_REUSE_CACHE,
                    cached=cached,
                )
            )
    return plan


def estimated_billable_characters(synthesis_texts: Iterable[str]) -> int:
    """The published counting rule, applied ahead of a budget decision."""
    return sum(billable_characters(text) for text in synthesis_texts)


def make_silence(
    path: Path,
    *,
    seconds: float,
    sample_rate: int = 32000,
    channels: int = 1,
) -> Path:
    """Write a silent mono 16-bit WAV with stdlib ``wave``. No ffmpeg needed."""
    if seconds <= 0:
        raise ValueError("silence duration must be positive")
    frames = int(round(seconds * sample_rate))
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as fh:
        fh.setnchannels(channels)
        fh.setsampwidth(2)
        fh.setframerate(sample_rate)
        fh.writeframes(b"\x00\x00" * frames * channels)
    return path


def concatenate_segments(
    normalised_paths: Sequence[Path],
    *,
    gaps_after_s: Sequence[float],
    out_path: Path,
    work_dir: Path,
    sample_rate: int = 32000,
    channels: int = 1,
) -> Path:
    """Join normalised segment WAVs, inserting declared silence between them.

    The join is deterministic: same segments, same order, same gaps, same
    bytes. Every input carries the same sample rate, channel count and codec
    (they are produced by one normalisation), and the gap after the final
    segment is ignored because there is nothing to separate it from. A path
    containing a single quote is refused rather than escaped: the concat list
    format is line-oriented and a silently mis-quoted path would join the
    wrong file.
    """
    paths = [Path(p) for p in normalised_paths]
    if not paths:
        raise ValueError("no segments to concatenate")
    if len(gaps_after_s) < len(paths):
        raise ValueError("gaps_after_s must cover every segment")
    for path in paths:
        if "'" in str(path):
            raise ValueError(f"single quote in path is refused: {path}")

    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    inputs: List[Path] = []
    for index, path in enumerate(paths):
        inputs.append(path)
        gap = float(gaps_after_s[index])
        if gap > 0 and index < len(paths) - 1:
            inputs.append(
                make_silence(
                    work_dir / f"gap-{index:02d}-{gap:g}s.wav",
                    seconds=gap,
                    sample_rate=sample_rate,
                    channels=channels,
                )
            )

    list_path = work_dir / "concat-list.txt"
    list_path.write_text(
        "ffconcat version 1.0\n"
        + "".join(f"file '{p.as_posix()}'\n" for p in inputs),
        encoding="utf-8",
        newline="\n",
    )
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result = hidden_run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(list_path),
            "-c:a", "pcm_s16le", "-ar", str(sample_rate), "-ac", str(channels),
            str(out_path),
        ],
        timeout=300,
    )
    if result.returncode != 0 or not out_path.is_file():
        raise RuntimeError(
            "segment concatenation failed: " + (result.stderr or "")[-400:]
        )
    return out_path
