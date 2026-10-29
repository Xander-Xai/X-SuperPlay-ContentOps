"""Audience Lens: who this video helps make which decision.

A positioning statement lives in the account DNA, but it cannot answer the
per-video question: *which* person is this cut for, what are they doing now,
and what proof would move them? Without that, scripts drift into describing the
topic instead of advancing a viewer.

This module validates one plain JSON document per video. It does not choose the
segment, write the copy, or grade quality -- it refuses a document that asserts
a viewer it cannot describe.

The three segments come from `configs/content-positioning` in the source
workflow and match this repository's `core_audience` split. They are a working
hypothesis, not eternal truth; changing them requires evidence, which is why
`validated` demands a direct source.
"""

from __future__ import annotations

from typing import Any, Dict, List

SCHEMA = "contentops.audience-insight/v1"

SEGMENTS = ("capability_decider", "workflow_adopter", "opportunity_builder")
VALUE_TYPES = ("practical", "cognitive", "emotional", "social", "identity")
CONFIDENCE = ("validated", "mixed", "exploratory")
SOURCE_KINDS = ("direct", "secondary")

#: Terms that name an audience but cannot route a video. Using one is not a
#: style problem; it means nobody decided who the cut is for.
BROAD_AUDIENCE_TERMS = (
    "所有人", "互联网用户", "对AI感兴趣的人", "泛用户", "大众",
    "everyone", "internet users", "general audience",
)

REQUIRED_TEXT = (
    "trigger_context",     # what happened right before they opened this
    "current_workaround",  # what they do today instead
    "pain_or_cost",        # what the workaround costs them
    "desired_progress",    # what they want to be able to do afterwards
    "proof_needed",        # what evidence would change their mind
    "opposition",          # their strongest objection
)

EMOTION_FIELDS = ("emotion_from", "emotion_to")


def _text(document: Dict[str, Any], key: str) -> str:
    value = document.get(key)
    return value.strip() if isinstance(value, str) else ""


def _sources(document: Dict[str, Any], errors: List[str]) -> List[Dict[str, str]]:
    raw = document.get("sources")
    if raw is None:
        return []
    if not isinstance(raw, list):
        errors.append("sources must be an array")
        return []
    result = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            errors.append(f"sources[{index}] must be an object")
            continue
        kind = item.get("kind")
        ref = item.get("ref")
        if kind not in SOURCE_KINDS:
            errors.append(f"sources[{index}].kind must be one of {SOURCE_KINDS}")
            continue
        if not isinstance(ref, str) or not ref.strip():
            errors.append(f"sources[{index}].ref must be a non-empty string")
            continue
        result.append({"kind": kind, "ref": ref.strip()})
    return result


def validate_audience_insight(document: Any) -> List[str]:
    """Return hard failures. An empty list means the document can route a cut."""
    if not isinstance(document, dict):
        return ["audience insight must be a JSON object"]
    errors: List[str] = []
    if document.get("schema") != SCHEMA:
        return [f"audience insight schema must be {SCHEMA!r}, got {document.get('schema')!r}"]

    segment = document.get("primary_segment")
    if segment not in SEGMENTS:
        errors.append(f"primary_segment must be one of {SEGMENTS}, got {segment!r}")

    for key in REQUIRED_TEXT:
        if not _text(document, key):
            errors.append(f"{key} must be a non-empty string")

    value_type = document.get("value_type")
    if value_type not in VALUE_TYPES:
        errors.append(f"value_type must be one of {VALUE_TYPES}, got {value_type!r}")

    emotion_from = _text(document, "emotion_from")
    emotion_to = _text(document, "emotion_to")
    if not emotion_from or not emotion_to:
        errors.append("emotion_from and emotion_to must both be stated")
    elif emotion_from == emotion_to:
        errors.append("emotion_from and emotion_to are identical; a cut needs one turn")

    confidence = document.get("conclusion_status")
    if confidence not in CONFIDENCE:
        errors.append(f"conclusion_status must be one of {CONFIDENCE}, got {confidence!r}")

    sources = _sources(document, errors)
    if confidence == "validated":
        if len(sources) < 2:
            errors.append("validated requires at least two independent sources")
        if not any(item["kind"] == "direct" for item in sources):
            errors.append("validated requires at least one direct audience signal")
    elif confidence == "mixed":
        if not sources:
            errors.append("mixed requires at least one source")
    elif confidence == "exploratory":
        for key in ("learnable_question", "disconfirming_signal", "cta"):
            if not _text(document, key):
                errors.append(f"exploratory requires {key}")

    haystack = " ".join(_text(document, key) for key in REQUIRED_TEXT + ("primary_segment",)).lower()
    for term in BROAD_AUDIENCE_TERMS:
        if term.lower() in haystack:
            errors.append(f"broad audience term {term!r} does not identify who this is for")
    return errors
