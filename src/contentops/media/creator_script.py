"""CreatorScriptEditor: the fact script -> creator script stage. Issue #34, narration v3.

Where this sits
---------------
Three texts now exist for one narration, and keeping them apart is the whole
point of the stage:

```
fact script     projects/easel-review/script/narration.txt  (locked, never edited)
creator script  a tracked editorial derivative: spoken register, re-ordered for
                a self-media listener, de-jargoned where safe, with a hook, a
                turn, a value statement and a natural ending
synthesis text  the creator script after the director's controls (see
                :mod:`contentops.media.narration_director`) and the pronunciation
                lexicon are applied -- what the provider actually receives
```

What the editor may do, and what it may not
-------------------------------------------
May: reorder the narrative; drop details that are noise for a listener when they
are declared (``omitted_details``); add questions and transitions that introduce
no new fact; frame value explicitly.

May **not**: invent facts, numbers, versions or conclusions; fabricate personal
experience or emotion; use template marketing language; make every sentence a
suspense hook.

Which of those are mechanically checkable, and which are not
------------------------------------------------------------
Checked here:

- the source digest equals the evidence lock's digest;
- no digit token is invented (creator digits must be a subset of the original's),
  and every dropped digit token must be covered by a declared omission;
- every declared ``preserved_facts`` entry exists in **both** the original and
  the creator text (so a fact cannot be "preserved" that was never there);
- every declared omission is genuinely absent from the creator text;
- the template-marketing blocklist is absent;
- every unit containing a first-person marker declares a ``first_person_basis``
  (traceable to the original's own first person, or explicitly an editorial
  judgement -- never a fabricated experience);
- the full script carries every required beat, opens on the hook and ends on
  the ending;
- question density is bounded (a proxy for "not every sentence creates
  suspense");
- units carry no newlines and no pause markers (paragraph structure and pauses
  belong to the director stage).

**Not** checkable here, and therefore not claimed: whether the copy is good,
whether the tone lands, and whether a sentence that keeps every fact still
reads as natural speech. Those stay Founder review.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .spoken_script import digit_tokens

__all__ = [
    "BEATS",
    "FACT_SCRIPT_PATH",
    "SCHEMA",
    "TEMPLATE_MARKETING_PHRASES",
    "CreatorScript",
    "CreatorScriptError",
    "CreatorUnit",
    "load_creator_script",
    "verify_creator_script",
]

SCHEMA = "contentops.creator-script/v1"

#: The narrative beats a creator script must cover. HOOK first, ENDING last;
#: the middle order is a narrative choice the editor makes (reordering is
#: explicitly allowed), so only the ends are structural.
BEATS: Tuple[str, ...] = (
    "HOOK",
    "SETUP",
    "EVIDENCE",
    "TURN",
    "PROBLEM",
    "VALUE",
    "ENDING",
)

#: Template self-media phrases this repository will not ship. The list is
#: deliberately short and specific: it is a floor, not a style guide.
TEMPLATE_MARKETING_PHRASES: Tuple[str, ...] = (
    "家人们",
    "姐妹们",
    "干货",
    "建议收藏",
    "一键三连",
    "点赞关注",
    "关注我",
    "全网最",
    "震惊体",
    "绝绝子",
    "必看",
    "天花板",
    "封神",
    "逆天",
    "血泪",
    "亲测有效",
)

#: The locked fact script, relative to the repository root. The creator script
#: cites this path and its digest; it never edits the file.
FACT_SCRIPT_PATH = "projects/easel-review/script/narration.txt"

_FIRST_PERSON_RE = re.compile(r"我|咱")
_WS_RE = re.compile(r"\s+")


class CreatorScriptError(RuntimeError):
    """The creator script is not admissible. Every failure is listed."""


@dataclass(frozen=True)
class CreatorUnit:
    """One narrative beat of the creator script. No markers, no newlines."""

    id: str
    beat: str
    text: str
    source_paragraphs: Tuple[int, ...] = ()
    facts_used: Tuple[str, ...] = ()
    first_person_basis: Optional[str] = None


@dataclass(frozen=True)
class CreatorScript:
    source_path: str
    source_digest: str
    units: Tuple[CreatorUnit, ...]
    preserved_facts: Tuple[str, ...]
    omitted_details: Tuple[Dict[str, str], ...]
    sample_unit_ids: Tuple[str, ...]
    target_duration_s: Tuple[float, float]

    def unit(self, unit_id: str) -> CreatorUnit:
        for candidate in self.units:
            if candidate.id == unit_id:
                return candidate
        raise KeyError(unit_id)

    def full_text(self) -> str:
        return "\n".join(unit.text for unit in self.units)

    def sample_units(self) -> Tuple[CreatorUnit, ...]:
        return tuple(self.unit(uid) for uid in self.sample_unit_ids)


def _normalise_ws(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


def load_creator_script(path: Path) -> CreatorScript:
    """Parse and structurally load the tracked creator script. Digests are
    checked by :func:`verify_creator_script`, which needs the original."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CreatorScriptError(f"creator script is not readable JSON: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise CreatorScriptError(f"creator script schema must be {SCHEMA!r}")

    source = payload.get("source") or {}
    units_raw = payload.get("units")
    if not isinstance(units_raw, list) or not units_raw:
        raise CreatorScriptError("units must be a non-empty list")
    units: List[CreatorUnit] = []
    for raw in units_raw:
        if not isinstance(raw, dict):
            raise CreatorScriptError("every unit must be an object")
        try:
            units.append(
                CreatorUnit(
                    id=str(raw["id"]),
                    beat=str(raw["beat"]),
                    text=str(raw["text"]),
                    source_paragraphs=tuple(
                        int(n) for n in (raw.get("source_paragraphs") or [])
                    ),
                    facts_used=tuple(str(f) for f in (raw.get("facts_used") or [])),
                    first_person_basis=(
                        str(raw["first_person_basis"])
                        if raw.get("first_person_basis")
                        else None
                    ),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CreatorScriptError(f"unit is malformed: {raw!r} ({exc})") from exc

    sample = payload.get("sample") or {}
    target = sample.get("target_duration_s") or [0.0, 0.0]
    try:
        target_tuple = (float(target[0]), float(target[1]))
    except (TypeError, ValueError, IndexError) as exc:
        raise CreatorScriptError(f"sample.target_duration_s is malformed: {exc}") from exc
    omitted = payload.get("omitted_details") or []
    if not isinstance(omitted, list):
        raise CreatorScriptError("omitted_details must be a list")
    return CreatorScript(
        source_path=str(source.get("path") or ""),
        source_digest=str(source.get("canonical_blob_sha256") or ""),
        units=tuple(units),
        preserved_facts=tuple(str(f) for f in (payload.get("preserved_facts") or [])),
        omitted_details=tuple(
            {"text": str(entry.get("text") or ""), "reason": str(entry.get("reason") or "")}
            for entry in omitted
            if isinstance(entry, dict)
        ),
        sample_unit_ids=tuple(str(uid) for uid in (sample.get("units") or [])),
        target_duration_s=target_tuple,
    )


def verify_creator_script(
    script: CreatorScript,
    *,
    original_text: str,
    canonical_original_digest: Optional[str],
    evidence_lock_digest: Optional[str],
) -> Dict[str, Any]:
    """Check every mechanical invariant. Raises with the complete failure list."""
    failures: List[str] = []

    if script.source_path != FACT_SCRIPT_PATH:
        failures.append(
            f"creator script cites source {script.source_path!r}; the locked fact "
            f"script is {FACT_SCRIPT_PATH!r}"
        )
    if not canonical_original_digest:
        failures.append(
            "the fact script's canonical digest could not be computed; refusing "
            "rather than substituting a weaker digest"
        )
    if script.source_digest != canonical_original_digest:
        failures.append(
            f"creator script cites source sha256 {script.source_digest!r} but the "
            f"fact script's canonical digest is {canonical_original_digest!r}"
        )
    if evidence_lock_digest != canonical_original_digest:
        failures.append(
            f"evidence lock records {evidence_lock_digest!r} but the fact script's "
            f"canonical digest is {canonical_original_digest!r}"
        )

    ids = [unit.id for unit in script.units]
    if len(set(ids)) != len(ids):
        failures.append(f"unit ids are not unique: {ids}")
    for unit in script.units:
        if unit.beat not in BEATS:
            failures.append(f"unit {unit.id}: unknown beat {unit.beat!r}")
        if not unit.text.strip():
            failures.append(f"unit {unit.id}: empty text")
        if "\n" in unit.text or "\r" in unit.text:
            failures.append(f"unit {unit.id}: text contains a newline")
        if "<#" in unit.text:
            failures.append(
                f"unit {unit.id}: text contains a pause marker; markers are the "
                "director's control, not the editor's text"
            )
        if _FIRST_PERSON_RE.search(unit.text) and not (unit.first_person_basis or "").strip():
            failures.append(
                f"unit {unit.id}: contains a first-person marker but declares no "
                "first_person_basis; first person must be traceable to the "
                "original's own voice or declared as an editorial judgement"
            )
        for paragraph in unit.source_paragraphs:
            if paragraph < 1:
                failures.append(f"unit {unit.id}: source_paragraphs contains {paragraph}")

    beats_present = {unit.beat for unit in script.units}
    missing_beats = [beat for beat in BEATS if beat not in beats_present]
    if missing_beats:
        failures.append(f"the script does not cover every beat; missing {missing_beats}")
    if script.units and script.units[0].beat != "HOOK":
        failures.append("the first unit must be the HOOK")
    if script.units and script.units[-1].beat != "ENDING":
        failures.append("the last unit must be the ENDING")

    question_units = [unit.id for unit in script.units if "？" in unit.text or "?" in unit.text]
    question_cap = max(2, len(script.units) // 3)
    if len(question_units) > question_cap:
        failures.append(
            f"{len(question_units)} units contain questions, above the cap of "
            f"{question_cap}; the script must not make every beat a suspense hook"
        )

    creator_digits = digit_tokens(script.full_text())
    original_digits = digit_tokens(original_text)
    invented = creator_digits - original_digits
    if invented:
        failures.append(f"digit tokens not present in the fact script: {dict(invented)}")
    missing_digits = original_digits - creator_digits
    if missing_digits:
        covered: Counter = Counter()
        for entry in script.omitted_details:
            covered += digit_tokens(entry["text"])
        uncovered = {token: count - covered[token] for token, count in missing_digits.items() if count > covered[token]}
        if uncovered:
            failures.append(
                "digit tokens dropped without a declared omission: "
                f"{uncovered}; add an omitted_details entry with a reason"
            )
        for entry in script.omitted_details:
            if not entry["reason"].strip():
                failures.append(f"omitted detail {entry['text']!r} has no reason")

    creator_norm = _normalise_ws(script.full_text())
    original_norm = _normalise_ws(original_text)
    for fact in script.preserved_facts:
        fact_norm = _normalise_ws(fact)
        if fact_norm not in original_norm:
            failures.append(
                f"preserved fact {fact!r} does not exist in the fact script; a fact "
                "cannot be preserved that was never there"
            )
        if fact_norm not in creator_norm:
            failures.append(f"preserved fact {fact!r} is absent from the creator script")
    for entry in script.omitted_details:
        if entry["text"].strip() and _normalise_ws(entry["text"]) in creator_norm:
            failures.append(
                f"omitted detail {entry['text']!r} is still present in the creator "
                "script; either restore it to the text or remove the omission"
            )
    for phrase in TEMPLATE_MARKETING_PHRASES:
        if phrase in creator_norm:
            failures.append(f"template marketing phrase {phrase!r} is present")

    unit_positions = {unit.id: index for index, unit in enumerate(script.units)}
    sample_positions: List[int] = []
    for uid in script.sample_unit_ids:
        if uid not in unit_positions:
            failures.append(f"sample references unknown unit {uid!r}")
        else:
            sample_positions.append(unit_positions[uid])
    if sample_positions != sorted(sample_positions):
        failures.append(
            "sample units must keep the script's own order; an excerpt may not "
            "re-order the narrative it excerpts"
        )
    if not script.sample_unit_ids:
        failures.append("sample.units must not be empty")
    low, high = script.target_duration_s
    if not (5 <= low < high <= 60):
        failures.append(
            f"sample.target_duration_s {script.target_duration_s} is not a sane range"
        )

    if failures:
        raise CreatorScriptError(
            "creator script failed mechanical verification:\n  - "
            + "\n  - ".join(failures)
        )
    return {
        "verified": True,
        "mechanically_checked": [
            "source digest equals the evidence lock",
            "no digit token invented; dropped digits declared as omissions",
            "preserved facts exist in the fact script and the creator script",
            "declared omissions are absent from the creator text",
            "template marketing phrases absent",
            "first-person markers carry a declared basis",
            "all beats covered; HOOK first; ENDING last",
            "question density bounded",
            "units carry no newlines or pause markers",
            "sample keeps script order",
        ],
        "not_proven_by_this_check": [
            "whether the copy is engaging or over-written",
            "whether tone matches the Founder's voice",
            "whether the result sounds like natural speech",
        ],
    }
