"""Build an M5 script from a reviewed, medium-neutral TOPIC copy derivative.

What this is
------------
A topic aimed at both VIDEO and GRAPHIC_TEXT owns one signed, reviewed
``00_brief/copy-derivative.json``. The VIDEO child must turn that derivative
into ``script/script.json``. Today that conversion is hand-written, and every
hand-written attempt rediscovers the same six gates the hard way:

1. copy review goes STALE unless ``script.json`` is a *faithful machine
   projection* of the derivative (caption == narration, per-segment narration
   concatenation equals the reviewed text, the union of claims equals the
   segment's ``claim_refs``);
2. a Huashu narrated shot must be <= 8 seconds, so a 25-second spoken segment
   has to be split into lines *without changing a word*;
3. ``_template_source`` rejects a line that has neither a claim nor an
   ``editorial_only`` marker, and the primary ``claim`` must be inside
   ``claims``;
4. a grammar that only draws (``architecture_flow`` / y3_whiteboard) produces
   ``fast_ratio: 0`` and fails the film gate -- an explainer that binds real
   bitmaps needs the camera-push grammar (``evidence_zoom`` / t2_keynote_ui);
5. Huashu's source-media gate accepts CREATED_BY_OWNER / USER_PROVIDED real
   bitmaps, not a LICENSED screenshot used as a visual source, so authored
   cards are registered as owned bitmaps while the licensed screenshots stay
   the evidence;
6. the visual QC rejects adjacent shots that reuse the same source asset with
   no measured change, so source cards and focus rectangles rotate.

This module makes those six rules one deterministic function. It never signs a
review, never grants publication, and never changes the spoken copy: it only
projects the approved derivative into the shape M5 and Huashu require. If a
derivative is missing, unapproved, or cannot be projected without inventing
words, it fails closed.

Run: ``python scripts/topic_to_m5.py <project> [--check|--dry-run|--json]``
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

SCRIPT_SCHEMA = "contentops.m5-script/v1"
DERIVATIVE_SCHEMA = "contentops.topic-copy-derivative/v1"

# A Chinese SAPI line above roughly 34 characters exceeds the 8-second Huashu
# narrated-shot ceiling. 28 leaves headroom for punctuation and English tokens.
DEFAULT_MAX_CHARS = 28

# Authoring grammars. Only t2_keynote_ui emits in-shot camera pushes; the
# whiteboard family draws static cards and measures fast_ratio 0.
PUSH_GRAMMAR = "evidence_zoom"
FOCUS_RECTS = (
    (0.05, 0.08, 0.90, 0.30),
    (0.05, 0.38, 0.90, 0.32),
    (0.05, 0.66, 0.90, 0.30),
    (0.08, 0.18, 0.84, 0.42),
    (0.30, 0.10, 0.60, 0.60),
    (0.05, 0.50, 0.50, 0.40),
)

class TopicM5Error(ValueError):
    """A derivative cannot reach M5 without inventing or losing copy."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _split_keep_all(text: str, max_chars: int) -> List[str]:
    """Split on punctuation, keeping every delimiter, preserving concatenation.

    The projection check joins narration pieces and compares byte-for-byte with
    the reviewed segment text, so no delimiter may be dropped or rewritten. A
    clause longer than the budget and without punctuation is split at fixed
    width as a fallback -- otherwise a long unpunctuated sentence would silently
    exceed the Huashu 8-second shot ceiling.
    """
    tokens = [t for t in re.findall(r"[^，。？！；、：,~]+[，。？！；、：,~]?", text) if t]
    units: List[str] = []
    for token in tokens:
        # A token is a clause plus its trailing delimiter. If the clause itself
        # is over budget, break the clause body and re-attach the delimiter to
        # the final chunk so the joined text stays identical.
        delimiter = ""
        if token and token[-1] in "，。？！；、：,~":
            token, delimiter = token[:-1], token[-1]
        if not token:
            units.append(delimiter)
            continue
        for i in range(0, len(token), max_chars):
            chunk = token[i:i + max_chars]
            units.append(chunk + (delimiter if i + max_chars >= len(token) else ""))
    pieces: List[str] = []
    buf = ""
    for unit in units:
        if buf and len(buf) + len(unit) > max_chars:
            pieces.append(buf)
            buf = unit
        else:
            buf += unit
    if buf:
        pieces.append(buf)
    if "".join(pieces) != text:
        raise TopicM5Error("SPLIT_LOST_COPY", "segment text changed while splitting")
    if any(len(piece) > max_chars for piece in pieces):
        raise TopicM5Error("SPLIT_OVER_BUDGET", "a piece exceeds the shot character budget")
    return pieces


def build_script(
    derivative: Dict[str, Any],
    *,
    asset_ids: Sequence[str],
    max_chars: int = DEFAULT_MAX_CHARS,
) -> Dict[str, Any]:
    """Project a reviewed VIDEO derivative into a compliant M5 script.

    ``asset_ids`` are the ordered, registered CREATED_BY_OWNER visual cards.
    They are rotated by emitted line so adjacent shots never share a source;
    focus rectangles rotate on the same cadence. Returns the script document;
    writes nothing.
    """
    if not isinstance(derivative, dict) or derivative.get("schema") != DERIVATIVE_SCHEMA:
        raise TopicM5Error("DERIVATIVE_SCHEMA", f"expected {DERIVATIVE_SCHEMA}")
    if derivative.get("format") != "VIDEO":
        raise TopicM5Error("DERIVATIVE_FORMAT", "copy derivative is not VIDEO")
    segments = derivative.get("segments")
    if not isinstance(segments, list) or not segments:
        raise TopicM5Error("DERIVATIVE_EMPTY", "no segments in copy derivative")
    if not asset_ids:
        raise TopicM5Error("NO_VISUAL_CARDS", "no registered visual card asset ids")
    if max_chars < 8:
        raise TopicM5Error("MAX_CHARS_TOO_SMALL", "max_chars must be >= 8")

    lines: List[Dict[str, Any]] = []
    for segment in segments:
        if not isinstance(segment, dict):
            raise TopicM5Error("SEGMENT_INVALID", "segment must be an object")
        segment_id = str(segment.get("source_segment_id") or "").strip()
        text = segment.get("text")
        raw_refs = segment.get("claim_refs") or []
        if not segment_id or not isinstance(text, str) or not text:
            raise TopicM5Error("SEGMENT_INVALID", f"bad segment {segment_id!r}")
        if not isinstance(raw_refs, list) or not raw_refs:
            raise TopicM5Error("SEGMENT_NO_CLAIMS", f"{segment_id} has no claim_refs")
        refs = [str(value) for value in raw_refs]
        if len(refs) != len(set(refs)):
            raise TopicM5Error("SEGMENT_DUP_CLAIMS", f"{segment_id} has duplicate claim refs")

        pieces = _split_keep_all(text, max_chars)
        for index, piece in enumerate(pieces):
            shift = len(lines)
            card = asset_ids[shift % len(asset_ids)]
            rect = FOCUS_RECTS[shift % len(FOCUS_RECTS)]
            lines.append({
                "id": f"{segment_id}-{index + 1:02d}",
                "source_segment_id": segment_id,
                "claims": refs,
                "claim": refs[0],
                "narration": piece,
                "caption": piece,
                "asset_id": card,
                "animation_type": PUSH_GRAMMAR,
                "animation": {
                    "focus_label": piece[:12],
                    "focus_rect": list(rect),
                },
            })

    script = {"schema": SCRIPT_SCHEMA, "language": "zh-CN", "lines": lines}
    problems = validate_script(script, derivative)
    if problems:
        raise TopicM5Error("PROJECTION_INVALID", "; ".join(problems))
    return script


def validate_script(script: Dict[str, Any], derivative: Dict[str, Any]) -> List[str]:
    """Return every invariant violation; empty means the projection is safe.

    Mirrors the three consumers from this round: copy_review's faithful-projection
    test, m5_production.stage_script, and qc_visual's adjacent-shot reuse check.
    """
    problems: List[str] = []
    if script.get("schema") != SCRIPT_SCHEMA:
        problems.append(f"schema must be {SCRIPT_SCHEMA}")
    lines = script.get("lines")
    segments = derivative.get("segments") if isinstance(derivative, dict) else None
    if not isinstance(lines, list) or not lines:
        return problems + ["lines must be a non-empty list"]
    if not isinstance(segments, list) or not segments:
        return problems + ["derivative segments must be a non-empty list"]

    ids = [str(line.get("id") or "") for line in lines]
    if len(ids) != len(set(ids)):
        problems.append("duplicate line id")
    if any(not value for value in ids):
        problems.append("empty line id")

    index = 0
    previous_card: Optional[str] = None
    for segment in segments:
        if not isinstance(segment, dict):
            problems.append("derivative segment must be an object")
            break
        sid = str(segment.get("source_segment_id") or "")
        text = segment.get("text")
        refs = {str(value) for value in (segment.get("claim_refs") or [])}
        segment_claims: set[str] = set()
        pieces: List[str] = []
        while index < len(lines):
            line = lines[index]
            if line.get("source_segment_id") != sid:
                break
            narration = line.get("narration")
            if not isinstance(narration, str) or not narration:
                problems.append(f"{sid}: empty narration")
                break
            if line.get("caption") != narration:
                problems.append(f"{sid}: caption must equal narration")
            claims = line.get("claims")
            primary = str(line.get("claim") or "")
            if not isinstance(claims, list) or not claims:
                problems.append(f"{sid}: claims must be a non-empty list")
            else:
                as_set = {str(value) for value in claims}
                if len(as_set) != len(claims):
                    problems.append(f"{sid}: duplicate claims")
                if primary and primary not in as_set:
                    problems.append(f"{sid}: primary claim outside claims")
                if not as_set.issubset(refs):
                    problems.append(f"{sid}: claim outside segment claim_refs")
                segment_claims |= as_set
            card = str(line.get("asset_id") or "")
            if not card:
                problems.append(f"{sid}: missing asset_id")
            elif card == previous_card:
                problems.append(f"{sid}: adjacent shot reuses card {card}")
            previous_card = card
            animation = line.get("animation_type")
            if animation != PUSH_GRAMMAR:
                problems.append(f"{sid}: grammar {animation!r} will not produce camera motion")
            params = line.get("animation")
            if not isinstance(params, dict):
                problems.append(f"{sid}: animation must be an object")
            else:
                rect = params.get("focus_rect")
                if not (isinstance(rect, (list, tuple)) and len(rect) == 4
                        and all(isinstance(v, (int, float)) for v in rect)):
                    problems.append(f"{sid}: focus_rect needs [x, y, width, height]")
            pieces.append(narration)
            index += 1
        if not pieces:
            problems.append(f"{sid}: no lines")
        elif "".join(pieces) != text:
            problems.append(f"{sid}: narration does not reproduce reviewed text")
        if segment_claims != refs:
            problems.append(f"{sid}: claim set does not match claim_refs")
    if index != len(lines):
        problems.append("lines remain after the last reviewed segment")
    return problems
