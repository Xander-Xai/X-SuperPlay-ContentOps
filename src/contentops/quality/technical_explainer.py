"""Technical-explainer editorial gate: mechanism, boundary, condition.

A technical explanation fails in two ways a codec check cannot see: it explains
a mechanism without ever naming the problem it solves, or it turns a conditional
result into a universal promise ("supports more concurrency" with no workload).

The gate requires the beats the content type promises, and refuses an
unqualified benefit phrase. It does not judge whether the explanation is
correct; the claim map and the evidence do that.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List

SCHEMA = "contentops.script-rhythm/v1"

BEATS = (
    "problem",            # what problem the mechanism solves
    "mechanism",          # how it works
    "terms",              # the key terms are defined or used precisely
    "boundary",           # how it differs from the adjacent capability
    "conditional_benefit",  # what it improves, under which condition
    "applicability",      # where it fits and where it does not
    "action",             # what the viewer can do next
)

#: Phrases that are not always false, but are unsafe without a condition in the
#: same sentence.
UNQUALIFIED_BENEFITS = (
    "核心收益就是",
    "提升推理吞吐",
    "支持更多并发",
    "大幅提升",
    "显著提升",
    "彻底解决",
    "永久解决",
)

CONDITION = re.compile(
    r"条件|取决于|相同|配置|工作负载|可能|有助于|通常|测量|实测|benchmark|视",
    re.IGNORECASE,
)

_SENTENCE_SPLIT = re.compile(r"[。；;\n]")


def _sentence_around(text: str, phrase: str) -> str:
    index = text.find(phrase)
    if index < 0:
        return ""
    start = 0
    for match in _SENTENCE_SPLIT.finditer(text, 0, index):
        start = match.end()
    end_match = _SENTENCE_SPLIT.search(text, index)
    end = end_match.start() if end_match else len(text)
    return text[start:end]


def audit_text(text: str, beats: Iterable[str]) -> List[str]:
    """Return hard failures for one technical explanation."""
    errors: List[str] = []
    body = str(text or "").strip()
    if not body:
        return ["technical explainer has no spoken text"]
    declared = list(beats or [])
    unknown = [beat for beat in declared if beat not in BEATS]
    if unknown:
        errors.append(f"unknown technical-explainer beats: {unknown}")
    missing = [beat for beat in BEATS if beat not in declared]
    if missing:
        errors.append(f"technical explainer is missing declared beats: {missing}")
    for phrase in UNQUALIFIED_BENEFITS:
        if phrase in body and not CONDITION.search(_sentence_around(body, phrase)):
            errors.append(
                f"unqualified benefit {phrase!r}: state the workload or measurement "
                f"condition in the same sentence, or bind a local measurement")
    return errors


def validate_script_document(document: Dict[str, Any]) -> List[str]:
    if not isinstance(document, dict):
        return ["script must be a JSON object"]
    if document.get("content_type") != "technical_explainer":
        return []
    lines = document.get("lines")
    if not isinstance(lines, list) or not lines:
        return ["technical explainer script has no lines"]
    text = " ".join(str(item.get("text", "")) for item in lines if isinstance(item, dict))
    beats = document.get("beats")
    if not isinstance(beats, list):
        beats = []
    return audit_text(text, beats)


def validate_script_file(path: Path) -> List[str]:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"script is not readable JSON: {exc}"]
    return validate_script_document(document)
