"""The spoken-script stage: original text -> editorial spoken derivative.

What this stage is, and what it deliberately is not
---------------------------------------------------
The original narration text is **locked** (evidence lock, digest pinned) and
stays exactly as it is. A spoken derivative is authored **beside** it for the
voice track only: long sentences split, clause order kept, explicit pauses at
emphasis and transitions, and semantic role segmentation
(:data:`contentops.media.t2a_segments.ROLES`). The derivative never replaces the
original and never clears the lock; it cites it.

What is mechanical here, and what is not
----------------------------------------
The repository rule is Evidence before Claim, so this module is explicit about
the line:

Mechanically checked
    - the source digest equals the evidence lock's digest (the derivative
      cannot be authored from some other text);
    - every digit token in the original survives in the derivative, and no digit
      token is invented (multiset equality, checked for the full script and for
      the declared sample scope);
    - every protected phrase -- the curated list that carries the conclusions
      and the fact-bearing terms -- is present in the derivative;
    - every pause marker is valid per the provider's documented ``<#x#>`` rules;
    - every segment declares a valid role and the full script covers all five
      roles;
    - segment texts carry no newlines (paragraph structure is expressed by the
      segment boundaries, not smuggled inside a segment).

**Not** mechanically checkable, and therefore not claimed
    - semantic equivalence sentence by sentence, tone, or whether a rewrite
      "sounds better";
    - that a conclusion phrased differently still means the same thing.

Those stay human review. The validator can fail loudly on a lost number or a
dropped conclusion keyword; it can never certify style. A pass here means the
script is *admissible*, not that it is good.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .minimax_native_tts import (
    DOCUMENTED_EMOTIONS,
    EMOTIONS_2_6_ONLY,
    NativeTtsRefusal,
    strip_pause_markers,
    validate_pause_markers,
)
from .t2a_segments import ROLES

__all__ = [
    "SCHEMA",
    "SpokenScript",
    "SpokenScriptError",
    "SpokenSegment",
    "digit_tokens",
    "load_spoken_script",
    "sample_original_text",
    "split_paragraphs",
    "synthesis_versions",
    "verify_script",
]

SCHEMA = "contentops.spoken-script/v1"

#: Digit-run tokens: ``982``, ``114``, and the ``0.2.1`` inside ``v0.2.1``.
#: Extracted after whitespace normalisation so the two sides compare as the
#: reader sees them. Chinese numerals (五层, 六项) are not digit tokens; they are
#: covered by ``protected_phrases`` instead, because a converter that turns any
#: lone 一 inside 一致 into a digit creates more noise than signal.
_DIGIT_TOKEN_RE = re.compile(r"\d+(?:\.\d+)*")
_WS_RE = re.compile(r"\s+")


class SpokenScriptError(RuntimeError):
    """The spoken script is not admissible. Every failure is listed."""


@dataclass(frozen=True)
class SpokenSegment:
    """One authored segment in display form.

    ``c_emotion``/``c_speed`` are the C-variant segment-level parameters; they
    are optional and validate against the same documented emotion rules the
    payload builder enforces.
    """

    id: str
    role: str
    text: str
    c_emotion: Optional[str] = None
    c_speed: Optional[float] = None
    pause_after_s: float = 0.0


@dataclass(frozen=True)
class SpokenScript:
    source_path: str
    source_digest: str
    authoring_mode: str
    segments: Tuple[SpokenSegment, ...]
    protected_phrases: Tuple[str, ...]
    sample_segment_ids: Tuple[str, ...]
    sample_original_paragraphs: Tuple[int, ...]
    target_duration_s: Tuple[float, float]

    def segment(self, segment_id: str) -> SpokenSegment:
        for spec in self.segments:
            if spec.id == segment_id:
                return spec
        raise KeyError(segment_id)

    def full_text(self) -> str:
        return "\n".join(spec.text for spec in self.segments)

    def sample_segments(self) -> Tuple[SpokenSegment, ...]:
        return tuple(self.segment(sid) for sid in self.sample_segment_ids)

    def sample_text(self) -> str:
        return "\n".join(spec.text for spec in self.sample_segments())


def _normalise_ws(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


def digit_tokens(text: str) -> Counter:
    """Multiset of digit-run tokens, whitespace-insensitive, markers stripped.

    Pause markers are instructions, not speech: ``<#0.3#>`` must not register as
    the number 0.3, or every added pause would look like an invented fact.
    """
    return Counter(_DIGIT_TOKEN_RE.findall(_normalise_ws(strip_pause_markers(text))))


def split_paragraphs(original_text: str) -> List[str]:
    """Non-empty paragraphs of the original, in order, 1-based addressed."""
    return [line.strip() for line in original_text.splitlines() if line.strip()]


def sample_original_text(original_text: str, paragraphs: Tuple[int, ...]) -> str:
    """The original paragraphs the sample covers, joined with newlines."""
    lines = split_paragraphs(original_text)
    selected: List[str] = []
    for number in paragraphs:
        if number < 1 or number > len(lines):
            raise SpokenScriptError(
                f"sample paragraph {number} does not exist (original has "
                f"{len(lines)} paragraphs)"
            )
        selected.append(lines[number - 1])
    return "\n".join(selected)


def load_spoken_script(path: Path) -> SpokenScript:
    """Parse and structurally validate the tracked spoken-script document.

    Structural only: digests against the original are checked by
    :func:`verify_script`, which needs the original and the evidence lock.
    """
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SpokenScriptError(f"spoken script is not readable JSON: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise SpokenScriptError(f"spoken script schema must be {SCHEMA!r}")

    source = payload.get("source") or {}
    authoring = payload.get("authoring") or {}
    sample = payload.get("sample") or {}
    raw_segments = payload.get("segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        raise SpokenScriptError("segments must be a non-empty list")

    segments: List[SpokenSegment] = []
    for raw in raw_segments:
        if not isinstance(raw, dict):
            raise SpokenScriptError("every segment must be an object")
        try:
            segments.append(
                SpokenSegment(
                    id=str(raw["id"]),
                    role=str(raw["role"]),
                    text=str(raw["text"]),
                    c_emotion=raw.get("c_emotion"),
                    c_speed=(
                        float(raw["c_speed"]) if raw.get("c_speed") is not None else None
                    ),
                    pause_after_s=float(raw.get("pause_after_s") or 0.0),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise SpokenScriptError(f"segment is malformed: {raw!r} ({exc})") from exc

    target = sample.get("target_duration_s") or [0.0, 0.0]
    if not isinstance(target, list) or len(target) != 2:
        raise SpokenScriptError("sample.target_duration_s must be [min_s, max_s]")
    try:
        paragraph_numbers = tuple(int(n) for n in (sample.get("original_paragraphs") or []))
        target_tuple = (float(target[0]), float(target[1]))
    except (TypeError, ValueError) as exc:
        raise SpokenScriptError(f"sample block is malformed: {exc}") from exc
    return SpokenScript(
        source_path=str(source.get("path") or ""),
        source_digest=str(source.get("canonical_blob_sha256") or ""),
        authoring_mode=str(authoring.get("mode") or ""),
        segments=tuple(segments),
        protected_phrases=tuple(str(p) for p in (payload.get("protected_phrases") or [])),
        sample_segment_ids=tuple(str(s) for s in (sample.get("segments") or [])),
        sample_original_paragraphs=paragraph_numbers,
        target_duration_s=target_tuple,
    )


def verify_script(
    script: SpokenScript,
    *,
    original_text: str,
    canonical_original_digest: Optional[str],
    evidence_lock_digest: Optional[str],
) -> Dict[str, Any]:
    """Check every mechanical invariant. Raises with the complete failure list."""
    failures: List[str] = []

    if not canonical_original_digest:
        failures.append(
            "the original text's canonical blob digest could not be computed; "
            "refusing rather than substituting a weaker digest"
        )
    if script.source_digest != canonical_original_digest:
        failures.append(
            f"spoken script cites source sha256 {script.source_digest!r} but the "
            f"original's canonical digest is {canonical_original_digest!r}"
        )
    if evidence_lock_digest != canonical_original_digest:
        failures.append(
            f"evidence lock records {evidence_lock_digest!r} but the original's "
            f"canonical digest is {canonical_original_digest!r}; the lock and the "
            "text disagree"
        )

    ids = [spec.id for spec in script.segments]
    if len(set(ids)) != len(ids):
        failures.append(f"segment ids are not unique: {ids}")
    for spec in script.segments:
        if spec.role not in ROLES:
            failures.append(f"segment {spec.id}: unknown role {spec.role!r}")
        if "\n" in spec.text or "\r" in spec.text:
            failures.append(
                f"segment {spec.id}: text contains a newline; paragraph structure "
                "belongs to the segment boundaries, not inside a segment"
            )
        if not spec.text.strip():
            failures.append(f"segment {spec.id}: empty text")
        try:
            validate_pause_markers(spec.text)
        except NativeTtsRefusal as exc:
            failures.append(f"segment {spec.id}: {exc.detail}")
        if spec.c_emotion is not None:
            if spec.c_emotion not in DOCUMENTED_EMOTIONS:
                failures.append(
                    f"segment {spec.id}: c_emotion {spec.c_emotion!r} is not "
                    f"documented ({', '.join(DOCUMENTED_EMOTIONS)})"
                )
            elif spec.c_emotion in EMOTIONS_2_6_ONLY:
                failures.append(
                    f"segment {spec.id}: c_emotion {spec.c_emotion!r} only takes "
                    "effect on speech-2.6 models; this narration targets speech-2.8"
                )
        if spec.c_speed is not None and not (0.5 <= spec.c_speed <= 2):
            failures.append(
                f"segment {spec.id}: c_speed {spec.c_speed} outside [0.5, 2]"
            )
    roles_present = {spec.role for spec in script.segments}
    missing_roles = [role for role in ROLES if role not in roles_present]
    if missing_roles:
        failures.append(
            f"the full script does not cover every semantic role; missing "
            f"{missing_roles}"
        )

    for sid in script.sample_segment_ids:
        if sid not in ids:
            failures.append(f"sample references unknown segment {sid!r}")
    try:
        original_sample = sample_original_text(
            original_text, script.sample_original_paragraphs
        )
    except SpokenScriptError as exc:
        original_sample = ""
        failures.append(str(exc))

    if len(script.protected_phrases) == 0:
        failures.append("protected_phrases must not be empty")

    spoken_full = _normalise_ws(script.full_text())
    full_digit_diff = digit_tokens(original_text) - digit_tokens(script.full_text())
    invented_digit_diff = digit_tokens(script.full_text()) - digit_tokens(original_text)
    if full_digit_diff or invented_digit_diff:
        failures.append(
            "digit tokens changed between original and full spoken script: "
            f"missing={dict(full_digit_diff)}, invented={dict(invented_digit_diff)}"
        )

    if original_sample:
        sample_digit_diff = digit_tokens(original_sample) - digit_tokens(script.sample_text())
        sample_invented = digit_tokens(script.sample_text()) - digit_tokens(original_sample)
        if sample_digit_diff or sample_invented:
            failures.append(
                "digit tokens changed between the sample original and the sample "
                f"spoken text: missing={dict(sample_digit_diff)}, "
                f"invented={dict(sample_invented)}"
            )

    sample_original = _normalise_ws(original_sample)
    for phrase in script.protected_phrases:
        if _normalise_ws(phrase) not in spoken_full:
            failures.append(f"protected phrase {phrase!r} is absent from the spoken text")
        elif _normalise_ws(phrase) in sample_original and _normalise_ws(
            phrase
        ) not in _normalise_ws(script.sample_text()):
            failures.append(
                f"protected phrase {phrase!r} is present in the sample original "
                "but absent from the sample spoken text"
            )

    if failures:
        raise SpokenScriptError(
            "spoken script failed mechanical verification:\n  - "
            + "\n  - ".join(failures)
        )
    return {
        "verified": True,
        "mechanically_checked": [
            "source digest equals the evidence lock",
            "digit tokens preserved (full script and sample)",
            "protected phrases preserved (full script and sample scope)",
            "pause markers valid per documented <#x#> rules",
            "segment roles valid and all five roles covered",
            "segment texts carry no newlines",
        ],
        "not_proven_by_this_check": [
            "semantic equivalence of paraphrased sentences",
            "tone and naturalness",
            "that a reworded conclusion keeps its meaning",
        ],
    }


def synthesis_versions(
    script: SpokenScript,
    lexicon: Any,
    *,
    sample_only: bool = True,
) -> Dict[str, Dict[str, Any]]:
    """SHA256 of every synthesis text derived from this script.

    The three-way mapping the round requires: original (recorded by the caller
    from the canonical digest), spoken script (the authored display text), and
    synthesis text (lexicon applied -- what the provider actually receives).
    """
    def entry(display_text: str) -> Dict[str, Any]:
        synthesis = (
            lexicon.spoken_text(display_text) if lexicon is not None else display_text
        )
        return {
            "display_characters": len(display_text),
            "display_sha256": hashlib.sha256(display_text.encode("utf-8")).hexdigest(),
            "synthesis_characters": len(synthesis),
            "synthesis_sha256": hashlib.sha256(synthesis.encode("utf-8")).hexdigest(),
        }

    versions: Dict[str, Dict[str, Any]] = {
        "full": entry(script.full_text()),
    }
    if sample_only:
        versions["sample"] = entry(script.sample_text())
        for spec in script.sample_segments():
            versions[f"segment:{spec.id}"] = entry(spec.text)
    return versions
