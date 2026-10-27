"""CutPlan: what actually appears, when, from which crop, for which claim.

A storyboard says what a compositor should do. A CutPlan says what the finished
cut *shows*, in final-cut milliseconds, with a crop rectangle and the claims that
range is allowed to assert. That difference matters because the two failure
modes here are invisible in a storyboard:

- a crop that removes the warning line above the result it is quoting;
- a re-used asset whose "enlarged" view appears before any contextual view, so
  the viewer never sees the evidence in a frame that supports the conclusion.

Both are structural, so both are checked structurally. Semantic completeness of a
crop still needs human review; this module refuses only what it can prove is
wrong (out-of-bounds, out-of-order context, overlapping placements).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set

from contentops.evidence._common import (
    ContractError,
    fingerprint,
    parse_ms_range,
    parse_time_range,
    require,
    require_schema,
    require_text,
)

CUT_PLAN_SCHEMA = "contentops.cut-plan/v1"

READING_CLASSES = ("reading", "non_reading")
TRANSITIONS = ("cut", "none", "fade", "dissolve")


def _validate_target(value: Any) -> Dict[str, Any]:
    require(isinstance(value, dict), "MISSING_FIELD", "target must be an object")
    for axis in ("width", "height"):
        size = value.get(axis)
        require(isinstance(size, int) and not isinstance(size, bool) and size > 0,
                "INVALID_TARGET", f"target.{axis} must be a positive integer")
    duration = value.get("duration_ms_range")
    require(isinstance(duration, list) and len(duration) == 2, "INVALID_TARGET",
            "target.duration_ms_range must be [min_ms, max_ms]")
    minimum, maximum = duration
    for name, item in (("min", minimum), ("max", maximum)):
        require(isinstance(item, int) and not isinstance(item, bool) and item > 0,
                "INVALID_TARGET", f"target.duration_ms_range {name} must be > 0")
    require(maximum > minimum, "INVALID_TARGET",
            "target.duration_ms_range max must exceed min")
    safe = value.get("caption_safe_area")
    if safe is not None:
        require(isinstance(safe, dict), "INVALID_TARGET",
                "target.caption_safe_area must be an object")
        for key in ("x", "y", "width", "height"):
            item = safe.get(key)
            require(isinstance(item, int) and not isinstance(item, bool) and item >= 0,
                    "INVALID_TARGET", f"caption_safe_area.{key} must be >= 0")
        require(safe["width"] > 0 and safe["height"] > 0, "INVALID_TARGET",
                "caption_safe_area has zero area")
        require(safe["x"] + safe["width"] <= value["width"], "INVALID_TARGET",
                "caption_safe_area extends past the frame width")
        require(safe["y"] + safe["height"] <= value["height"], "INVALID_TARGET",
                "caption_safe_area extends past the frame height")
    min_hold = value.get("min_reading_hold_ms")
    if min_hold is not None:
        require(isinstance(min_hold, int) and not isinstance(min_hold, bool) and min_hold > 0,
                "INVALID_TARGET", "target.min_reading_hold_ms must be > 0")
    return dict(value)


def _validate_crop(value: Any, placement_id: str) -> Dict[str, Any]:
    require(isinstance(value, dict), "MISSING_FIELD",
            f"{placement_id}.crop must be an object")
    keys = ("x", "y", "width", "height", "source_width", "source_height")
    numbers = {}
    for key in keys:
        item = value.get(key)
        require(isinstance(item, int) and not isinstance(item, bool) and item >= 0,
                "INVALID_CROP", f"{placement_id}.crop.{key} must be a non-negative int")
        numbers[key] = item
    require(numbers["width"] > 0 and numbers["height"] > 0, "INVALID_CROP",
            f"{placement_id}.crop has zero area")
    require(numbers["source_width"] > 0 and numbers["source_height"] > 0,
            "INVALID_CROP", f"{placement_id}.crop has zero source dimensions")
    require(numbers["x"] + numbers["width"] <= numbers["source_width"],
            "CROP_OUT_OF_BOUNDS",
            f"{placement_id}.crop extends past the source width")
    require(numbers["y"] + numbers["height"] <= numbers["source_height"],
            "CROP_OUT_OF_BOUNDS",
            f"{placement_id}.crop extends past the source height")
    return numbers


@dataclass
class Placement:
    placement_id: str
    start_ms: int
    end_ms: int
    asset_id: str
    source_time_range: str
    crop: Dict[str, int]
    reading_class: str = "non_reading"
    semantic_progress: str = ""
    claim_ids: List[str] = field(default_factory=list)
    caption_cue_ids: List[str] = field(default_factory=list)
    claim_bearing: bool = True
    context_first: bool = False
    context_placement_id: Optional[str] = None
    transition: str = "cut"

    def validate(self) -> "Placement":
        require_text(self.placement_id, "placement_id")
        parse_ms_range(self.start_ms, self.end_ms, self.placement_id)
        require_text(self.asset_id, f"{self.placement_id}.asset_id")
        parse_time_range(self.source_time_range, f"{self.placement_id}.source_time_range")
        self.crop = _validate_crop(self.crop, self.placement_id)
        require(self.reading_class in READING_CLASSES, "INVALID_READING_CLASS",
                f"{self.placement_id}.reading_class must be one of {READING_CLASSES}")
        require_text(self.semantic_progress,
                     f"{self.placement_id}.semantic_progress")
        require(self.transition in TRANSITIONS, "INVALID_TRANSITION",
                f"{self.placement_id}.transition must be one of {TRANSITIONS}")
        require(isinstance(self.claim_bearing, bool), "INVALID_CLAIM_BEARING",
                f"{self.placement_id}.claim_bearing must be a boolean")
        if self.claim_bearing:
            require(bool(self.claim_ids), "CLAIM_BEARING_WITHOUT_CLAIM",
                    f"{self.placement_id} is claim-bearing but binds no claim_ids")
        if self.claim_ids:
            require(isinstance(self.claim_ids, list)
                    and all(isinstance(c, str) and c for c in self.claim_ids),
                    "INVALID_CLAIM_ID", f"{self.placement_id}.claim_ids must be strings")
        if self.caption_cue_ids:
            require(isinstance(self.caption_cue_ids, list)
                    and all(isinstance(c, str) and c for c in self.caption_cue_ids),
                    "INVALID_CAPTION_CUE", f"{self.placement_id}.caption_cue_ids must be strings")
        if self.context_first:
            require_text(self.context_placement_id,
                         f"{self.placement_id}.context_placement_id")
        return self


@dataclass
class CutPlan:
    package_id: str
    target: Dict[str, Any]
    placements: List[Placement] = field(default_factory=list)

    def validate(self) -> "CutPlan":
        require_text(self.package_id, "package_id")
        self.target = _validate_target(self.target)
        require(bool(self.placements), "EMPTY_CUT_PLAN",
                "a cut plan must contain at least one placement")

        seen_ids: Set[str] = set()
        seen_cues: Set[str] = set()
        by_id: Dict[str, Placement] = {}
        previous_end = 0
        for index, placement in enumerate(self.placements):
            require(isinstance(placement, Placement), "INVALID_PLACEMENT",
                    f"placements[{index}] is not a Placement")
            placement.validate()
            require(placement.placement_id not in seen_ids, "DUPLICATE_PLACEMENT_ID",
                    f"duplicate placement_id {placement.placement_id!r}")
            seen_ids.add(placement.placement_id)
            by_id[placement.placement_id] = placement

            require(placement.start_ms >= previous_end, "OVERLAPPING_PLACEMENTS",
                    f"{placement.placement_id} starts at {placement.start_ms}ms, "
                    f"before the previous placement ends at {previous_end}ms")
            previous_end = placement.end_ms

            for cue in placement.caption_cue_ids:
                require(cue not in seen_cues, "DUPLICATE_CAPTION_CUE",
                        f"caption cue {cue!r} is used by more than one placement")
                seen_cues.add(cue)

            minimum_hold = self.target.get("min_reading_hold_ms")
            if minimum_hold and placement.reading_class == "reading":
                require(placement.end_ms - placement.start_ms >= minimum_hold,
                        "READING_HOLD_TOO_SHORT",
                        f"{placement.placement_id} holds a reading beat for "
                        f"{placement.end_ms - placement.start_ms}ms, below "
                        f"{minimum_hold}ms")

        maximum = self.target["duration_ms_range"][1]
        minimum = self.target["duration_ms_range"][0]
        require(previous_end <= maximum, "CUT_TOO_LONG",
                f"the last placement ends at {previous_end}ms, beyond the "
                f"{maximum}ms target maximum")
        require(previous_end >= minimum, "CUT_TOO_SHORT",
                f"the plan ends at {previous_end}ms, below the {minimum}ms "
                f"target minimum")

        for placement in self.placements:
            if not placement.context_first:
                continue
            context = by_id.get(placement.context_placement_id or "")
            require(context is not None, "UNKNOWN_CONTEXT_PLACEMENT",
                    f"{placement.placement_id} cites unknown context placement "
                    f"{placement.context_placement_id!r}")
            require(context is not placement, "CONTEXT_SELF_REFERENCE",
                    f"{placement.placement_id} cannot be its own context")
            require(context.start_ms < placement.start_ms, "CONTEXT_AFTER_CROP",
                    f"{placement.placement_id} cites context "
                    f"{context.placement_id!r} that starts later; context must "
                    f"appear first")
            require(context.asset_id == placement.asset_id, "CONTEXT_ASSET_MISMATCH",
                    f"{placement.placement_id} and its context "
                    f"{context.placement_id!r} come from different assets, so the "
                    f"crop is not an enlargement of the context shown")
        return self

    def claim_ids(self) -> Set[str]:
        return {cid for placement in self.placements for cid in placement.claim_ids}

    def validate_claims(self, claim_map) -> "CutPlan":
        """Every placement claim must exist in the package Claim Map."""
        known = {claim.claim_id for claim in claim_map.claims}
        for placement in self.placements:
            for claim_id in placement.claim_ids:
                require(claim_id in known, "UNKNOWN_CLAIM",
                        f"{placement.placement_id} cites claim {claim_id!r} that is "
                        f"not in the Claim Map")
        return self

    def validate_assets(self, known_asset_ids: Iterable[str]) -> "CutPlan":
        known = set(known_asset_ids)
        for placement in self.placements:
            require(placement.asset_id in known, "UNKNOWN_ASSET",
                    f"{placement.placement_id} cites asset {placement.asset_id!r} "
                    f"that is not selected in the manifest")
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": CUT_PLAN_SCHEMA,
            "package_id": self.package_id,
            "target": self.target,
            "placements": [
                {
                    "placement_id": p.placement_id,
                    "start_ms": p.start_ms,
                    "end_ms": p.end_ms,
                    "asset_id": p.asset_id,
                    "source_time_range": p.source_time_range,
                    "crop": dict(p.crop),
                    "reading_class": p.reading_class,
                    "semantic_progress": p.semantic_progress,
                    "claim_ids": list(p.claim_ids),
                    "caption_cue_ids": list(p.caption_cue_ids),
                    "claim_bearing": p.claim_bearing,
                    "context_first": p.context_first,
                    "context_placement_id": p.context_placement_id,
                    "transition": p.transition,
                }
                for p in self.placements
            ],
        }

    def fingerprint(self) -> str:
        return fingerprint(self.to_dict())

    @classmethod
    def from_dict(cls, document: Dict[str, Any]) -> "CutPlan":
        require_schema(document, CUT_PLAN_SCHEMA)
        known = {"schema", "package_id", "target", "placements"}
        unknown = sorted(set(document) - known)
        require(not unknown, "UNKNOWN_FIELD",
                f"unknown cut-plan fields: {', '.join(unknown)}")
        placements = []
        allowed = {
            "placement_id", "start_ms", "end_ms", "asset_id", "source_time_range",
            "crop", "reading_class", "semantic_progress", "claim_ids",
            "caption_cue_ids", "claim_bearing", "context_first",
            "context_placement_id", "transition",
        }
        for index, raw in enumerate(document.get("placements") or []):
            require(isinstance(raw, dict), "INVALID_PLACEMENT",
                    f"placements[{index}] must be an object")
            extra = sorted(set(raw) - allowed)
            require(not extra, "UNKNOWN_FIELD",
                    f"placements[{index}] has unknown fields: {', '.join(extra)}")
            try:
                placements.append(Placement(
                    placement_id=raw["placement_id"],
                    start_ms=raw["start_ms"],
                    end_ms=raw["end_ms"],
                    asset_id=raw["asset_id"],
                    source_time_range=raw["source_time_range"],
                    crop=raw["crop"],
                    reading_class=raw.get("reading_class", "non_reading"),
                    semantic_progress=raw.get("semantic_progress", ""),
                    claim_ids=list(raw.get("claim_ids") or []),
                    caption_cue_ids=list(raw.get("caption_cue_ids") or []),
                    claim_bearing=raw.get("claim_bearing", True),
                    context_first=raw.get("context_first", False),
                    context_placement_id=raw.get("context_placement_id"),
                    transition=raw.get("transition", "cut"),
                ))
            except KeyError as exc:
                raise ContractError("MISSING_FIELD",
                                    f"placements[{index}] is missing {exc.args[0]!r}") from None
        return cls(
            package_id=document.get("package_id", ""),
            target=document.get("target") or {},
            placements=placements,
        ).validate()
