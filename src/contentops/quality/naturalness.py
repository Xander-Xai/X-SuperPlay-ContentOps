"""Naturalness gate: colloquial copy stays bounded and keeps its facts.

A technical script has two failure modes that the evidence gates cannot see.
One is register: copy that reads like a status report, with every sentence
closing the same way, is not something a person would say to a camera. The
other is the fix for the first one -- a rewrite that sprinkles "其实" through
every line until the script sounds like a persona instead of a speaker.

So this checks production decisions rather than taste. It does not score
whether prose is "human". It verifies that a script that declares a colloquial
register has a *budget* for human touches, that the touches are the declared
ones, that no filler phrase became a verbal tic, and that every fact the
rewrite was allowed to rephrase is still present afterwards.

What is not claimed
-------------------
Passing this does not mean the copy is good or natural to listen to. That is a
listening decision. This proves the rewrite stayed inside the line it drew for
itself.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

SCHEMA = "contentops.naturalness/v1"

VOICES = ("neutral-technical", "controlled-colloquial", "formal")

HUMAN_TOUCHES = ("none", "direct_address", "reaction", "aside", "short_pause")

#: Fillers that stop being a voice and become a tic when they repeat.
REPEATED_FILLERS = ("其实", "说白了", "你看", "简单来说", "我跟你说", "大家都知道")

#: A filler used more than this many times in the whole script is a tic.
MAX_FILLER_USES = 2


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _tokens(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def metrics(document: Dict[str, Any]) -> Dict[str, Any]:
    """The numbers a reviewer needs, computed once so the gate and a receipt agree."""
    lines = document.get("lines") if isinstance(document.get("lines"), list) else []
    touches = [_text(line.get("human_touch")) for line in lines if isinstance(line, dict)]
    touched = [touch for touch in touches if touch and touch != "none"]
    consecutive = longest = 0
    for touch in touches:
        if touch and touch != "none":
            consecutive += 1
            longest = max(longest, consecutive)
        else:
            consecutive = 0
    text = " ".join(_text(line.get("text")) for line in lines if isinstance(line, dict))
    fillers = {phrase: text.count(phrase) for phrase in REPEATED_FILLERS if text.count(phrase)}
    return {
        "line_count": len([line for line in lines if isinstance(line, dict)]),
        "touch_count": len(touched),
        "longest_touch_streak": longest,
        "fillers": fillers,
    }


def validate_naturalness(document: Any) -> List[str]:
    """Return hard failures. An empty list means the copy stayed inside its line."""
    if not isinstance(document, dict):
        return ["naturalness document must be a JSON object"]
    errors: List[str] = []
    if document.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA!r}")

    voice = _text(document.get("narrative_voice"))
    if voice not in VOICES:
        errors.append(f"narrative_voice must be one of {VOICES}")

    allowed = _tokens(document.get("allowed_human_touches"))
    unknown = [touch for touch in allowed if touch not in HUMAN_TOUCHES or touch == "none"]
    if unknown:
        errors.append(f"allowed_human_touches contains unknown types: {', '.join(unknown)}")
    if voice == "controlled-colloquial" and not allowed:
        errors.append("controlled-colloquial must declare which human touches it allows")

    budget = _int(document.get("colloquial_budget"))
    if voice == "controlled-colloquial" and budget is None:
        errors.append("controlled-colloquial must declare an integer colloquial_budget")
    if budget is not None and budget < 0:
        errors.append("colloquial_budget cannot be negative")
    max_consecutive = _int(document.get("max_consecutive"))
    if voice == "controlled-colloquial" and max_consecutive is None:
        errors.append("controlled-colloquial must declare an integer max_consecutive")

    lines = document.get("lines")
    if not isinstance(lines, list) or not lines:
        errors.append("lines must be a non-empty array")
        return errors

    seen: Dict[str, int] = {}
    for index, line in enumerate(lines):
        label = f"lines[{index}]"
        if not isinstance(line, dict):
            errors.append(f"{label} must be an object")
            continue
        unit_id = _text(line.get("unit_id"))
        if not unit_id:
            errors.append(f"{label}.unit_id must be a non-empty string")
        elif unit_id in seen:
            errors.append(f"duplicate unit_id {unit_id!r}")
        else:
            seen[unit_id] = index
            label = f"{label} ({unit_id})"
        if not _text(line.get("text")):
            errors.append(f"{label}.text must be a non-empty string")
        touch = _text(line.get("human_touch")) or "none"
        if touch not in HUMAN_TOUCHES:
            errors.append(f"{label}.human_touch must be one of {HUMAN_TOUCHES}")
            continue
        if touch != "none" and touch not in allowed:
            errors.append(f"{label} uses undeclared human touch {touch!r}")
        if touch != "none" and not _text(line.get("delivery_note")):
            errors.append(f"{label} has human_touch={touch} but no delivery_note")

    numbers = metrics(document)
    if budget is not None and numbers["touch_count"] > budget:
        errors.append(f"colloquial touch count {numbers['touch_count']} exceeds "
                      f"budget {budget}")
    if max_consecutive is not None and numbers["longest_touch_streak"] > max_consecutive:
        errors.append(f"consecutive human touches {numbers['longest_touch_streak']} "
                      f"exceed max_consecutive {max_consecutive}")
    tics = {phrase: count for phrase, count in numbers["fillers"].items()
            if count > MAX_FILLER_USES}
    if tics:
        errors.append("repeated filler phrases exceed two uses: "
                      + ", ".join(f"{phrase}={count}" for phrase, count in sorted(tics.items())))

    locks = _tokens(document.get("fact_lock_tokens"))
    source = _text(document.get("source_text"))
    humanized = _text(document.get("humanized_text"))
    if locks and not source:
        errors.append("fact_lock_tokens declared without the source_text they must come from")
    if locks and source:
        invented = [token for token in locks if token not in source]
        if invented:
            errors.append("fact_lock_tokens not present in the source: " + ", ".join(invented))
    if locks and not humanized:
        errors.append("fact_lock_tokens declared but humanized_text is missing")
    if locks and source and humanized:
        lost = [token for token in locks if token not in humanized]
        if lost:
            errors.append("humanized copy dropped fact-lock tokens: " + ", ".join(lost))
    return errors


def verdict(document: Any) -> Tuple[str, Dict[str, Any]]:
    """One word and the numbers behind it, for a receipt header."""
    errors = validate_naturalness(document)
    numbers = metrics(document) if isinstance(document, dict) else {}
    return ("BLOCKED" if errors else "PASSED", numbers)
