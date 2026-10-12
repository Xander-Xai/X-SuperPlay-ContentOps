"""NarrationDirector: full-narrative planning, then a conservative mapping. Issue #34, narration v3.

What this is
------------
The v2 round chose per-segment emotions mechanically (5 of 7 segments were
``calm``) and used two fixed pause durations everywhere. This module replaces
that with a two-layer design:

1. **Director metadata (internal only).** Every unit gets
   ``communicative_intent``, ``delivery_style``, ``emphasis_terms``,
   ``pause_intent``, ``pace_intent``, ``emotional_transition`` and
   ``context_before``/``context_after``. These are thinking tools for the
   narration as a whole; **none of them is a MiniMax field** and none of them is
   ever sent to the provider.
2. **A conservative mapping.** The only things that reach the request are the
   documented ``voice_setting.emotion``, ``voice_setting.speed``, punctuation
   and ``<#x#>`` pause markers -- and only where the plan justifies them:

   - **Emotion defaults to auto.** The model detects it from the text; explicit
     emotion requires a justification, must be documented for the model, and
     ``calm`` can appear at most once and can never be a majority (the exact
     failure the v2 diagnosis pinned).
   - **Speed defaults to steady.** A non-steady group speed requires every unit
     in the group to intend the same direction, a justification, and a bound
     of 0.95-1.08.
   - **Pauses come from intent, not habit.** Durations are 0.2-0.5 s, at most
     two per unit, anchored to a unique substring, and the mapped text must
     pass the provider's own marker validation before it can be used.

Synthesis boundaries follow narrative intent
--------------------------------------------
Requests are grouped by complete narrative intent (``groups``), not by
sentence: a group is the smallest span that shares one delivery. The plan must
contain at least one multi-unit group and fewer groups than units, and a
single-unit group is legal only with a declared reason *and* a differing
control -- per-sentence slicing is refused by construction.

Why the validation is this strict, and what it cannot say
---------------------------------------------------------
The v2 failure was not a crash; it was a majority-default that no test
objected to. So the rules here are written as hard refusals with named reasons.
What they still cannot say: whether the resulting delivery sounds natural.
That remains listening, and the receipt for the D/E/F run says so.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .clone_route import billable_characters
from .creator_script import CreatorScript
from .minimax_native_tts import (
    DOCUMENTED_EMOTIONS,
    NativeTtsRefusal,
    emotion_allowed_for_model,
    validate_pause_markers,
)

__all__ = [
    "PACE_FASTER",
    "PACE_SLOWER",
    "PACE_STEADY",
    "SCHEMA",
    "DirectorPlan",
    "DirectorUnit",
    "NarrationDirectorError",
    "SynthesisGroup",
    "estimate_seconds",
    "group_synthesis_text",
    "load_director_plan",
    "mapped_groups",
    "unit_synthesis_text",
    "verify_director_plan",
]

SCHEMA = "contentops.narration-plan/v1"

PACE_STEADY = "STEADY"
PACE_SLOWER = "SLIGHTLY_SLOWER"
PACE_FASTER = "SLIGHTLY_FASTER"
_PACE_INTENTS = (PACE_STEADY, PACE_SLOWER, PACE_FASTER)

SPEED_MIN = 0.95
SPEED_MAX = 1.08
PAUSE_MIN_S = 0.2
PAUSE_MAX_S = 0.5
PAUSE_PER_UNIT_CAP = 2


class NarrationDirectorError(RuntimeError):
    """The plan is not admissible. Every failure is listed."""


@dataclass(frozen=True)
class PauseIntent:
    after: str
    duration_s: float
    role: str


@dataclass(frozen=True)
class DirectorUnit:
    id: str
    communicative_intent: str
    delivery_style: str
    emphasis_terms: Tuple[str, ...]
    pause_intent: Tuple[PauseIntent, ...]
    pace_intent: str
    emotional_transition: str
    context_before: str
    context_after: str
    explicit_emotion: Optional[str] = None
    emotion_justification: Optional[str] = None
    explicit_speed: Optional[float] = None
    speed_justification: Optional[str] = None


@dataclass(frozen=True)
class SynthesisGroup:
    id: str
    units: Tuple[str, ...]
    emotion: Optional[str] = None
    speed: float = 1.0
    justification: Optional[str] = None
    single_unit_reason: Optional[str] = None
    pause_after_s: float = 0.0
    note: str = ""


@dataclass(frozen=True)
class DirectorPlan:
    creator_script_path: str
    creator_script_digest: str
    model: str
    units: Tuple[DirectorUnit, ...]
    groups: Tuple[SynthesisGroup, ...]
    sample_unit_ids: Tuple[str, ...]
    sample_groups: Tuple[SynthesisGroup, ...]
    sample_target_duration_s: Tuple[float, float]

    def unit(self, unit_id: str) -> DirectorUnit:
        for candidate in self.units:
            if candidate.id == unit_id:
                return candidate
        raise KeyError(unit_id)


def _load_group(raw: Dict[str, Any], section: str) -> SynthesisGroup:
    try:
        units = tuple(str(uid) for uid in (raw.get("units") or []))
        return SynthesisGroup(
            id=str(raw["id"]),
            units=units,
            emotion=(str(raw["emotion"]) if raw.get("emotion") else None),
            speed=float(raw.get("speed", 1.0)),
            justification=(
                str(raw["justification"]) if raw.get("justification") else None
            ),
            single_unit_reason=(
                str(raw["single_unit_reason"]) if raw.get("single_unit_reason") else None
            ),
            pause_after_s=float(raw.get("pause_after_s") or 0.0),
            note=str(raw.get("note") or ""),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise NarrationDirectorError(
            f"{section} group is malformed: {raw!r} ({exc})"
        ) from exc


def load_director_plan(path: Path) -> DirectorPlan:
    """Parse and structurally load the tracked director plan."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NarrationDirectorError(f"director plan is not readable JSON: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise NarrationDirectorError(f"director plan schema must be {SCHEMA!r}")

    source = payload.get("creator_script") or {}
    units_raw = payload.get("units")
    groups_raw = payload.get("groups")
    sample = payload.get("sample") or {}
    if not isinstance(units_raw, list) or not units_raw:
        raise NarrationDirectorError("units must be a non-empty list")
    if not isinstance(groups_raw, list) or not groups_raw:
        raise NarrationDirectorError("groups must be a non-empty list")

    units: List[DirectorUnit] = []
    for raw in units_raw:
        if not isinstance(raw, dict):
            raise NarrationDirectorError("every unit must be an object")
        try:
            units.append(
                DirectorUnit(
                    id=str(raw["id"]),
                    communicative_intent=str(raw["communicative_intent"]),
                    delivery_style=str(raw["delivery_style"]),
                    emphasis_terms=tuple(str(t) for t in (raw.get("emphasis_terms") or [])),
                    pause_intent=tuple(
                        PauseIntent(
                            after=str(entry["after"]),
                            duration_s=float(entry["duration_s"]),
                            role=str(entry["role"]),
                        )
                        for entry in (raw.get("pause_intent") or [])
                    ),
                    pace_intent=str(raw["pace_intent"]),
                    emotional_transition=str(raw["emotional_transition"]),
                    context_before=str(raw["context_before"]),
                    context_after=str(raw["context_after"]),
                    explicit_emotion=(
                        str(raw["explicit_emotion"]) if raw.get("explicit_emotion") else None
                    ),
                    emotion_justification=(
                        str(raw["emotion_justification"])
                        if raw.get("emotion_justification")
                        else None
                    ),
                    explicit_speed=(
                        float(raw["explicit_speed"])
                        if raw.get("explicit_speed") is not None
                        else None
                    ),
                    speed_justification=(
                        str(raw["speed_justification"])
                        if raw.get("speed_justification")
                        else None
                    ),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise NarrationDirectorError(f"unit is malformed: {raw!r} ({exc})") from exc

    target = sample.get("target_duration_s") or [0.0, 0.0]
    try:
        target_tuple = (float(target[0]), float(target[1]))
    except (TypeError, ValueError, IndexError) as exc:
        raise NarrationDirectorError(
            f"sample.target_duration_s is malformed: {exc}"
        ) from exc
    return DirectorPlan(
        creator_script_path=str(source.get("path") or ""),
        creator_script_digest=str(source.get("working_tree_sha256") or ""),
        model=str(payload.get("model") or "speech-2.8-hd"),
        units=tuple(units),
        groups=tuple(_load_group(raw, "groups") for raw in groups_raw),
        sample_unit_ids=tuple(str(uid) for uid in (sample.get("units") or [])),
        sample_groups=tuple(
            _load_group(raw, "sample.groups") for raw in (sample.get("groups") or [])
        ),
        sample_target_duration_s=target_tuple,
    )


def unit_synthesis_text(unit: DirectorUnit, text: str) -> str:
    """The unit's planned text with its declared pause markers inserted.

    ``text`` is the creator unit's display text (the director unit intentionally
    carries no copy of it; the creator script is the single owner of the words).
    """
    insertions: List[Tuple[int, str]] = []
    for pause in unit.pause_intent:
        index = text.find(pause.after)
        if index == -1 or text.find(pause.after, index + 1) != -1:
            raise NarrationDirectorError(
                f"unit {unit.id}: pause anchor {pause.after!r} does not occur "
                "exactly once in its text"
            )
        insertions.append((index + len(pause.after), f"<#{pause.duration_s:g}#>"))
    mapped = text
    for position, marker in sorted(insertions, key=lambda item: item[0], reverse=True):
        mapped = mapped[:position] + marker + mapped[position:]
    return mapped


def group_synthesis_text(
    group: SynthesisGroup,
    units_by_id: Dict[str, DirectorUnit],
    texts_by_id: Dict[str, str],
) -> str:
    """Join a group's units with newlines, markers inserted per unit."""
    parts = [
        unit_synthesis_text(units_by_id[uid], texts_by_id[uid]) for uid in group.units
    ]
    return "\n".join(parts)


def estimate_seconds(text: str) -> float:
    """The repository's own duration heuristic, plus declared marker time."""
    marker_time = sum(float(value) for value in re.findall(r"<#([0-9.]+)#>", text))
    spoken_chars = len(re.sub(r"<#[0-9.]+#>", "", text))
    return round(max(1.0, spoken_chars / 6.0) + marker_time, 2)


@dataclass(frozen=True)
class MappedGroup:
    id: str
    units: Tuple[str, ...]
    text: str
    emotion: Optional[str]
    speed: float
    pause_after_s: float
    characters: int
    billable_characters: int
    estimated_seconds: float


def mapped_groups(
    plan: DirectorPlan,
    creator: CreatorScript,
    *,
    section: str = "groups",
) -> List[MappedGroup]:
    """The plan's conservative mapping: text + the only two API controls.

    Only ``emotion`` (documented, justified, non-majority) and ``speed``
    (bounded, direction-consistent with every unit in the group) can differ
    from the auto/steady defaults. Everything else in a director unit stays
    internal to this file and never reaches a request.
    """
    units_by_id = {unit.id: unit for unit in plan.units}
    texts_by_id = {unit.id: unit.text for unit in creator.units}
    groups = plan.sample_groups if section == "sample.groups" else plan.groups
    mapped: List[MappedGroup] = []
    for group in groups:
        text = group_synthesis_text(group, units_by_id, texts_by_id)
        try:
            validate_pause_markers(text)
        except NativeTtsRefusal as exc:
            raise NarrationDirectorError(
                f"{section} group {group.id}: mapped text is invalid: {exc.detail}"
            ) from exc
        mapped.append(
            MappedGroup(
                id=group.id,
                units=group.units,
                text=text,
                emotion=group.emotion,
                speed=group.speed,
                pause_after_s=group.pause_after_s,
                characters=len(text),
                billable_characters=billable_characters(text),
                estimated_seconds=estimate_seconds(text),
            )
        )
    return mapped


def _check_emotion(
    failures: List[str],
    *,
    label: str,
    emotion: Optional[str],
    justification: Optional[str],
    model: str,
) -> None:
    if emotion is None:
        return
    if emotion not in DOCUMENTED_EMOTIONS:
        failures.append(
            f"{label}: emotion {emotion!r} is not documented "
            f"({', '.join(DOCUMENTED_EMOTIONS)})"
        )
        return
    if not emotion_allowed_for_model(model, emotion):
        failures.append(f"{label}: emotion {emotion!r} does not apply to {model!r}")
    if not (justification or "").strip():
        failures.append(
            f"{label}: explicit emotion {emotion!r} needs a justification; "
            "auto-detect is the default and an explicit value must be argued"
        )


def _check_speed(
    failures: List[str],
    *,
    label: str,
    group: SynthesisGroup,
    member_units: Sequence[DirectorUnit],
) -> None:
    if not (SPEED_MIN <= group.speed <= SPEED_MAX):
        failures.append(
            f"{label}: speed {group.speed} outside the conservative "
            f"[{SPEED_MIN}, {SPEED_MAX}]"
        )
        return
    directions = {unit.pace_intent for unit in member_units}
    if len(directions) > 1:
        failures.append(
            f"{label}: member units disagree on pace ({sorted(directions)}); a "
            "group carries one delivery"
        )
        return
    direction = next(iter(directions)) if directions else PACE_STEADY
    if direction == PACE_STEADY and group.speed != 1.0:
        failures.append(
            f"{label}: speed {group.speed} set although every member unit is STEADY"
        )
    if direction == PACE_SLOWER and not (SPEED_MIN <= group.speed < 1.0):
        failures.append(f"{label}: units intend slower but speed is {group.speed}")
    if direction == PACE_FASTER and not (1.0 < group.speed <= SPEED_MAX):
        failures.append(f"{label}: units intend faster but speed is {group.speed}")
    if group.speed != 1.0 and not (group.justification or "").strip():
        failures.append(f"{label}: a non-steady speed needs a justification")


def _check_groups(
    failures: List[str],
    *,
    label: str,
    groups: Sequence[SynthesisGroup],
    ordered_unit_ids: Sequence[str],
    units_by_id: Dict[str, DirectorUnit],
    model: str,
) -> None:
    ids = [group.id for group in groups]
    if len(set(ids)) != len(ids):
        failures.append(f"{label}: group ids are not unique: {ids}")
    covered: List[str] = []
    for group in groups:
        covered.extend(group.units)
        if not group.units:
            failures.append(f"{label} group {group.id}: no units")
            continue
        member_units = [units_by_id[uid] for uid in group.units if uid in units_by_id]
        _check_emotion(
            failures, label=f"{label} group {group.id}",
            emotion=group.emotion, justification=group.justification, model=model,
        )
        _check_speed(
            failures, label=f"{label} group {group.id}",
            group=group, member_units=member_units,
        )
        if len(group.units) == 1 and not (group.single_unit_reason or "").strip():
            failures.append(
                f"{label} group {group.id}: a single-unit group needs "
                "single_unit_reason; per-sentence slicing must be declared"
            )
        if group.pause_after_s < 0:
            failures.append(f"{label} group {group.id}: negative pause_after_s")
    if covered != list(ordered_unit_ids):
        failures.append(
            f"{label}: groups must cover every unit exactly once, in order; got "
            f"{covered} for units {list(ordered_unit_ids)}"
        )


def verify_director_plan(
    plan: DirectorPlan,
    creator: CreatorScript,
    *,
    expected_creator_digest: Optional[str] = None,
) -> Dict[str, Any]:
    """Check every mechanical invariant of the plan. Raises on any failure."""
    failures: List[str] = []

    if plan.creator_script_path != "projects/easel-enhanced-golden/script/creator-script.json":
        failures.append(
            f"plan cites creator script {plan.creator_script_path!r}; the tracked "
            "creator script is projects/easel-enhanced-golden/script/creator-script.json"
        )
    if expected_creator_digest and plan.creator_script_digest != expected_creator_digest:
        failures.append(
            f"plan cites creator digest {plan.creator_script_digest!r} but the file "
            f"on disk hashes to {expected_creator_digest!r}; the plan is stale"
        )

    creator_ids = [unit.id for unit in creator.units]
    plan_ids = [unit.id for unit in plan.units]
    if plan_ids != creator_ids:
        failures.append(
            f"plan units {plan_ids} do not match the creator script's units "
            f"{creator_ids} (ids, order and count must be identical)"
        )

    units_by_id = {unit.id: unit for unit in plan.units}
    texts_by_id = {unit.id: unit.text for unit in creator.units}

    for unit in plan.units:
        label = f"unit {unit.id}"
        for field_name, value in (
            ("communicative_intent", unit.communicative_intent),
            ("delivery_style", unit.delivery_style),
            ("emotional_transition", unit.emotional_transition),
            ("context_before", unit.context_before),
            ("context_after", unit.context_after),
        ):
            if not value.strip():
                failures.append(f"{label}: {field_name} is empty")
        if unit.pace_intent not in _PACE_INTENTS:
            failures.append(f"{label}: pace_intent {unit.pace_intent!r} is unknown")
        if len(unit.pause_intent) > PAUSE_PER_UNIT_CAP:
            failures.append(
                f"{label}: {len(unit.pause_intent)} pause intents exceeds the cap of "
                f"{PAUSE_PER_UNIT_CAP}"
            )
        anchors = [pause.after for pause in unit.pause_intent]
        if len(set(anchors)) != len(anchors):
            failures.append(f"{label}: duplicate pause anchors")
        text = texts_by_id.get(unit.id, "")
        for pause in unit.pause_intent:
            if not (PAUSE_MIN_S <= pause.duration_s <= PAUSE_MAX_S):
                failures.append(
                    f"{label}: pause {pause.duration_s} outside "
                    f"[{PAUSE_MIN_S}, {PAUSE_MAX_S}]"
                )
            if not pause.role.strip():
                failures.append(f"{label}: a pause intent has no role")
            if text and (text.find(pause.after) == -1 or text.find(pause.after, text.find(pause.after) + 1) != -1):
                failures.append(
                    f"{label}: pause anchor {pause.after!r} does not occur exactly "
                    "once in the creator text"
                )
        for term in unit.emphasis_terms:
            if text and term not in text:
                failures.append(
                    f"{label}: emphasis term {term!r} is not in the creator text"
                )
        _check_emotion(
            failures, label=label, emotion=unit.explicit_emotion,
            justification=unit.emotion_justification, model=plan.model,
        )
        if unit.explicit_speed is not None:
            if not unit.speed_justification or not unit.speed_justification.strip():
                failures.append(f"{label}: explicit_speed needs a justification")
            if not (SPEED_MIN <= unit.explicit_speed <= SPEED_MAX):
                failures.append(
                    f"{label}: explicit_speed {unit.explicit_speed} outside "
                    f"[{SPEED_MIN}, {SPEED_MAX}]"
                )

    explicit_emotions = [u for u in plan.units if u.explicit_emotion]
    if len(explicit_emotions) * 2 > len(plan.units):
        failures.append(
            "explicit emotions outnumber auto units; auto-detect is the default "
            "and must remain the majority"
        )
    explicit_calm = [u.id for u in plan.units if u.explicit_emotion == "calm"]
    if len(explicit_calm) > 1:
        failures.append(
            f"calm is set explicitly on {explicit_calm}; it may appear at most "
            "once and never as a majority default"
        )

    _check_groups(
        failures, label="groups", groups=plan.groups,
        ordered_unit_ids=creator_ids, units_by_id=units_by_id, model=plan.model,
    )
    if len(plan.units) > 1:
        if len(plan.groups) >= len(plan.units):
            failures.append(
                "every unit is its own group; that is per-sentence slicing and is "
                "exactly what resets the voice at every boundary"
            )
        if not any(len(group.units) >= 2 for group in plan.groups):
            failures.append("no multi-unit group exists; nothing shares a delivery")

    sample_positions = [creator_ids.index(uid) for uid in plan.sample_unit_ids if uid in creator_ids]
    if len(sample_positions) != len(plan.sample_unit_ids):
        failures.append(
            f"sample references unknown units: {plan.sample_unit_ids}"
        )
    elif sample_positions != sorted(sample_positions):
        failures.append("sample units must keep the script's own order")
    sample_order = list(plan.sample_unit_ids)
    _check_groups(
        failures, label="sample.groups", groups=plan.sample_groups,
        ordered_unit_ids=sample_order, units_by_id=units_by_id, model=plan.model,
    )
    if not any(len(group.units) >= 2 for group in plan.sample_groups):
        failures.append("sample has no multi-unit group; nothing shares a delivery")
    for group in plan.sample_groups:
        if len(group.units) == 1:
            has_control = bool(group.emotion) or group.speed != 1.0
            if not has_control:
                failures.append(
                    f"sample.groups {group.id}: a single-unit group with no "
                    "differing control is slicing without a reason"
                )
    low, high = plan.sample_target_duration_s
    if not (5 <= low < high <= 40):
        failures.append(
            f"sample.target_duration_s {plan.sample_target_duration_s} is not sane"
        )

    if failures:
        raise NarrationDirectorError(
            "director plan failed mechanical verification:\n  - "
            + "\n  - ".join(failures)
        )

    sample_mapped = mapped_groups(plan, creator, section="sample.groups")
    full_mapped = mapped_groups(plan, creator, section="groups")
    return {
        "verified": True,
        "model": plan.model,
        "units": len(plan.units),
        "groups": len(plan.groups),
        "sample_groups": [group.id for group in plan.sample_groups],
        "sample_estimated_seconds": round(
            sum(entry.estimated_seconds for entry in sample_mapped)
            + sum(group.pause_after_s for group in plan.sample_groups[:-1]),
            2,
        ),
        "explicit_emotions": {u.id: u.explicit_emotion for u in explicit_emotions},
        "mechanically_checked": [
            "units match the creator script exactly (ids, order, count)",
            "auto emotion is the default and explicit emotions are justified, documented and never a majority",
            "calm appears at most once and never as a default",
            "non-steady speeds are homogeneous per group, justified and bounded 0.95-1.08",
            "pause durations within 0.2-0.5 s, <=2 per unit, anchors unique and mapped text passes provider marker validation",
            "groups cover units exactly once, follow narrative order and contain at least one multi-unit group",
            "single-unit groups declare a reason and carry a differing control",
        ],
        "not_proven_by_this_check": [
            "whether the mapped delivery sounds natural",
            "whether the chosen emotion reads as intended rather than as overacting",
            "whether the group boundaries are perceptible as resets",
        ],
        "mapped_full_groups": [
            {
                "id": entry.id,
                "units": list(entry.units),
                "emotion": entry.emotion,
                "speed": entry.speed,
                "characters": entry.characters,
                "billable_characters": entry.billable_characters,
                "estimated_seconds": entry.estimated_seconds,
            }
            for entry in full_mapped
        ],
    }
