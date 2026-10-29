"""Deterministic rhythm checks for a spoken script.

What this is for
----------------
The evidence gates ask "is this claim supported?". This asks a different and
much cheaper question: "can this be *said* in the time the video has?". A script
that is 40% over its target is not a quality problem the compositor can fix, and
a 30-character hook is not a hook.

The document is deliberately plain, so a human can hand-write it and a model can
emit it without a schema library:

```json
{
  "schema": "contentops.script-rhythm/v1",
  "target_seconds": 60,
  "speech_rate_cpm": 220,
  "hook_unit_id": "U01",
  "declared_first_person": false,
  "lines": [{"unit_id": "U01", "text": "..."}]
}
```

What is not claimed
-------------------
This does not judge whether the copy is good, persuasive, or accurate. It only
refuses shapes that cannot work: an over-long line, an over-long hook, a script
that misses its window, template marketing language, and first person nobody
declared. Tone stays human review.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

SCHEMA = "contentops.script-rhythm/v1"

#: Same floor the creator-script stage enforces; imported rather than copied so
#: the two can never drift into disagreeing about what counts as template copy.
try:
    from contentops.media.creator_script import TEMPLATE_MARKETING_PHRASES
except Exception:  # pragma: no cover - keeps this module importable on its own
    TEMPLATE_MARKETING_PHRASES = (
        "家人们", "姐妹们", "干货", "建议收藏", "一键三连", "点赞关注", "关注我",
        "全网最", "绝绝子", "必看", "天花板", "封神", "逆天", "血泪", "亲测有效",
    )

CONNECTIVES: Tuple[str, ...] = ("然后", "所以", "但是", "接下来", "其实", "不过", "而且", "因此", "另外")
FIRST_PERSON_RE = re.compile(r"[我咱]")
PAUSE_RE = re.compile(r"<#\s*\d+(?:\.\d+)?\s*#>")
QUESTION_RE = re.compile(r"[？?]")

#: A single spoken line must be sayable inside one breath-sized window. Six
#: seconds at the declared rate is the same bound `audio_first_plan` rejects on.
MAX_LINE_SECONDS = 6.0
#: A hook has three seconds to land.
HOOK_SECONDS = 3.0
#: Tolerance around the declared target. Generous enough for a natural read,
#: tight enough that a 40%-over script is refused rather than "close enough".
DURATION_TOLERANCE = 0.20
DURATION_TOLERANCE_FLOOR_S = 5.0
#: Above this share of question lines the script reads as a suspense chain.
MAX_QUESTION_SHARE = 0.60


def _chars(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def _read(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def measure_script_rhythm(document: Dict[str, Any]) -> Dict[str, Any]:
    """Soft metrics for the receipt. Never raises on a merely unusual script."""
    lines = document.get("lines") or []
    cpm = float(document.get("speech_rate_cpm") or 220)
    total = sum(_chars(str(item.get("text", ""))) for item in lines if isinstance(item, dict))
    return {
        "line_count": len(lines),
        "char_count": total,
        "estimated_seconds": round(total / cpm * 60.0, 2) if cpm else 0.0,
        "speech_rate_cpm": cpm,
        "target_seconds": document.get("target_seconds"),
        "question_lines": sum(1 for item in lines
                              if isinstance(item, dict) and QUESTION_RE.search(str(item.get("text", "")))),
    }


def validate_script_rhythm(path: Path) -> List[str]:
    """Return hard failures. An empty list means the shape is sayable."""
    errors: List[str] = []
    try:
        document = _read(path)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"script is not readable JSON: {exc}"]
    if not isinstance(document, dict):
        return ["script must be a JSON object"]
    if document.get("schema") != SCHEMA:
        return [f"script schema must be {SCHEMA!r}, got {document.get('schema')!r}"]

    lines = document.get("lines")
    if not isinstance(lines, list) or not lines:
        return ["script.lines must be a non-empty array"]

    cpm = float(document.get("speech_rate_cpm") or 220)
    if cpm <= 0:
        errors.append("speech_rate_cpm must be positive")
        cpm = 220.0
    max_line_chars = max(1, round(MAX_LINE_SECONDS * cpm / 60.0))
    hook_max_chars = max(12, round(HOOK_SECONDS * cpm / 60.0) + 4)

    seen: set[str] = set()
    texts: List[str] = []
    for index, item in enumerate(lines):
        where = f"lines[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{where} must be an object")
            continue
        unit_id = item.get("unit_id")
        if not isinstance(unit_id, str) or not unit_id.strip():
            errors.append(f"{where}.unit_id must be a non-empty string")
        elif unit_id in seen:
            errors.append(f"{where}.unit_id duplicates {unit_id!r}")
        else:
            seen.add(unit_id)
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            errors.append(f"{where}.text must be a non-empty string")
            continue
        if "\n" in text or "\r" in text:
            errors.append(f"{where}.text contains a newline; paragraph structure belongs to the director")
        if PAUSE_RE.search(text):
            errors.append(f"{where}.text contains a pause marker; pauses belong to the director")
        length = _chars(text)
        if length > max_line_chars:
            errors.append(f"{where} is {length} chars, over the {max_line_chars}-char / "
                          f"{MAX_LINE_SECONDS:g}s line bound")
        for phrase in TEMPLATE_MARKETING_PHRASES:
            if phrase in text:
                errors.append(f"{where}.text uses template marketing language: {phrase!r}")
                break
        if not document.get("declared_first_person") and FIRST_PERSON_RE.search(text):
            errors.append(f"{where}.text uses first person without declared_first_person")
        texts.append(text)

    hook_id = document.get("hook_unit_id") or (lines[0].get("unit_id") if isinstance(lines[0], dict) else None)
    hook = next((item for item in lines
                 if isinstance(item, dict) and item.get("unit_id") == hook_id), None)
    if hook is None:
        errors.append(f"hook_unit_id {hook_id!r} does not match any line")
    else:
        hook_length = _chars(str(hook.get("text", "")))
        if hook_length > hook_max_chars:
            errors.append(f"hook is {hook_length} chars, over the {hook_max_chars}-char / "
                          f"{HOOK_SECONDS:g}s hook bound")

    target = document.get("target_seconds")
    if isinstance(target, (int, float)) and target > 0:
        total = sum(_chars(text) for text in texts)
        estimated = total / cpm * 60.0
        tolerance = max(target * DURATION_TOLERANCE, DURATION_TOLERANCE_FLOOR_S)
        if abs(estimated - target) > tolerance:
            errors.append(f"estimated {estimated:.1f}s is outside {target:g}s ± {tolerance:.1f}s")

    errors.extend(_connective_runs(texts))

    if texts:
        questions = sum(1 for text in texts if QUESTION_RE.search(text))
        if questions / len(texts) > MAX_QUESTION_SHARE:
            errors.append(f"{questions}/{len(texts)} lines are questions; the script reads as a suspense chain")
    return errors


def _connective_runs(texts: Iterable[str]) -> List[str]:
    """Three lines in a row opening with the same connective reads as filler."""
    run_word = ""
    run_length = 0
    for text in texts:
        word = next((item for item in CONNECTIVES if text.startswith(item)), "")
        if word and word == run_word:
            run_length += 1
        else:
            run_word, run_length = word, (1 if word else 0)
        if run_length >= 3:
            return [f"three consecutive lines open with {word!r}"]
    return []
