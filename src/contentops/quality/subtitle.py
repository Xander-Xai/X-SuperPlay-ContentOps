"""Deterministic subtitle checks for a vertical delivery.

The burn path already had one timing defect that every green run missed: ASS
timestamps are centiseconds, and a millisecond value stretched every cue by ten
times. QC only checked that a subtitle was *present*. This module checks the
properties that defect would have failed:

- timestamps parse, and a cue ends after it starts;
- cues do not overlap;
- no cue is empty;
- a cue fits the line and character budget a portrait frame can actually read.

It reads SRT and never rewrites it. Timing is checked, not corrected -- a
subtitle that needs correction needs a new narration measurement, not a silent
edit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

#: Portrait captions at 47-54 px fit roughly this many CJK glyphs per line.
DEFAULT_MAX_CHARS_PER_LINE = 22
DEFAULT_MAX_LINES = 2
#: Overlap smaller than this is rounding, not a bug.
OVERLAP_TOLERANCE_MS = 1

_TIMESTAMP = re.compile(
    r"^(?P<h>\d{1,2}):(?P<m>\d{2}):(?P<s>\d{2})[,.](?P<ms>\d{3})\s*-->\s*"
    r"(?P<h2>\d{1,2}):(?P<m2>\d{2}):(?P<s2>\d{2})[,.](?P<ms2>\d{3})"
)


@dataclass(frozen=True)
class Cue:
    index: int
    start_ms: int
    end_ms: int
    lines: Tuple[str, ...]

    @property
    def text(self) -> str:
        return " ".join(self.lines).strip()


def _to_ms(hours: str, minutes: str, seconds: str, millis: str) -> int:
    return ((int(hours) * 60 + int(minutes)) * 60 + int(seconds)) * 1000 + int(millis)


def parse_srt(text: str) -> List[Cue]:
    """Parse SRT text. Raises nothing; a malformed cue is skipped."""
    cues: List[Cue] = []
    for block in re.split(r"\r?\n\s*\r?\n", text.strip()):
        rows = [row for row in block.splitlines() if row.strip()]
        if not rows:
            continue
        timestamp_at = next((i for i, row in enumerate(rows) if _TIMESTAMP.match(row.strip())), None)
        if timestamp_at is None:
            continue
        match = _TIMESTAMP.match(rows[timestamp_at].strip())
        assert match is not None
        start = _to_ms(match["h"], match["m"], match["s"], match["ms"])
        end = _to_ms(match["h2"], match["m2"], match["s2"], match["ms2"])
        body = tuple(row.strip() for row in rows[timestamp_at + 1:])
        cues.append(Cue(index=len(cues) + 1, start_ms=start, end_ms=end, lines=body))
    return cues


def _cjk_length(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def validate_srt(path: Path,
                 max_chars_per_line: int = DEFAULT_MAX_CHARS_PER_LINE,
                 max_lines: int = DEFAULT_MAX_LINES) -> List[str]:
    """Return hard failures. An empty list means the subtitle is deliverable."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"subtitle is not readable UTF-8: {exc}"]

    cues = parse_srt(text)
    if not cues:
        return ["subtitle has no readable cues"]

    errors: List[str] = []
    previous: Optional[Cue] = None
    for cue in cues:
        where = f"cue {cue.index}"
        if cue.end_ms <= cue.start_ms:
            errors.append(f"{where} ends at or before it starts")
        if cue.end_ms - cue.start_ms < 300:
            errors.append(f"{where} is shorter than 0.3 s and cannot be read")
        if not cue.text:
            errors.append(f"{where} is empty")
        if len(cue.lines) > max_lines:
            errors.append(f"{where} has {len(cue.lines)} lines, over the {max_lines}-line budget")
        for line in cue.lines:
            length = _cjk_length(line)
            if length > max_chars_per_line:
                errors.append(f"{where} line is {length} chars, over the "
                              f"{max_chars_per_line}-char budget")
        if previous is not None:
            overlap = previous.end_ms - cue.start_ms
            if overlap > OVERLAP_TOLERANCE_MS:
                errors.append(f"{where} overlaps cue {previous.index} by {overlap / 1000:.3f} s")
            if cue.start_ms < previous.start_ms:
                errors.append(f"{where} starts before cue {previous.index}")
        previous = cue
    return errors


def make_srt_validator(max_chars_per_line: int = DEFAULT_MAX_CHARS_PER_LINE,
                       max_lines: int = DEFAULT_MAX_LINES):
    """Bind a project's caption budget once, then use it as a stage validator."""
    def validator(path: Path) -> List[str]:
        return validate_srt(path, max_chars_per_line, max_lines)
    validator.__name__ = "srt_validator"
    return validator


def measure_srt(path: Path) -> dict:
    """Soft facts for a receipt: cue count, span and longest line."""
    try:
        cues = parse_srt(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return {"cue_count": 0, "span_seconds": 0.0, "longest_line_chars": 0}
    span = (cues[-1].end_ms - cues[0].start_ms) / 1000.0 if cues else 0.0
    longest = max((_cjk_length(line) for cue in cues for line in cue.lines), default=0)
    return {"cue_count": len(cues), "span_seconds": round(span, 3), "longest_line_chars": longest}


_PAUSE_MARKER = re.compile(r"<#\s*\d+(?:\.\d+)?\s*#>")
_SPOKEN_NOISE = re.compile(
    r"[\s。，、；：！？…—·~「」『』“”‘’（）()【】\[\]《》<>\"'`,.!?;:\-]"
)


def normalize_spoken(text: str) -> str:
    """The text a caption and a narration can be compared on.

    Captions drop punctuation, split sentences at different points and may
    carry TTS pause markers; none of that changes which words were spoken.
    """
    without_pauses = _PAUSE_MARKER.sub("", text or "")
    return _SPOKEN_NOISE.sub("", without_pauses).casefold()


def validate_caption_agreement(path: Path, narration: str) -> List[str]:
    """A caption must transcribe the narration it is burned under.

    Timing checks cannot see this: a caption built from an older script still
    parses, still fits the frame and still lands on its cue. It just says
    something the voice does not say.
    """
    try:
        cues = parse_srt(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        return [f"subtitle is not readable UTF-8: {exc}"]
    spoken = normalize_spoken(narration)
    if not spoken:
        return ["narration text is empty; nothing for the caption to agree with"]
    if not cues:
        return ["subtitle has no readable cues to compare with the narration"]
    caption = normalize_spoken(" ".join(cue.text for cue in cues))
    if caption == spoken:
        return []
    limit = min(len(caption), len(spoken))
    at = next((i for i in range(limit) if caption[i] != spoken[i]), limit)
    where = f"cue 1-{len(cues)}"
    return [
        f"caption does not transcribe the narration ({where}): first difference at "
        f"character {at}; caption has {caption[at:at + 12]!r}, narration has "
        f"{spoken[at:at + 12]!r}"
    ]
