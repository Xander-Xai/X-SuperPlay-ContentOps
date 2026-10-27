"""Redaction receipts: a derived artifact never hides where it came from.

The raw capture is the evidence. A redacted copy is what may be published, and it
is publishable only if a reviewer can answer three questions from the receipt:

- which raw bytes, by hash, this copy was derived from;
- which regions of which frames, and which audio, were removed;
- who reviewed the result and whether they approved it.

Redaction therefore never overwrites the raw source and never edits it in place.
The raw file keeps its hash, the derivative gets its own, and the receipt links
them. A derivative without that link cannot be published, because at that point
nobody can tell whether it still shows the warning that changed the conclusion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ._common import (
    ContractError,
    iso_utc,
    parse_time_range,
    require,
    require_schema,
    require_sha256,
    require_text,
)

REDACTION_SCHEMA = "contentops.redaction-transform/v1"

REVIEW_PENDING = "PENDING"
REVIEW_APPROVED = "APPROVED"
REVIEW_REJECTED = "REJECTED"
REVIEW_STATUSES = (REVIEW_PENDING, REVIEW_APPROVED, REVIEW_REJECTED)

AUDIO_REMOVED = "REMOVED"
AUDIO_KEPT_APPROVED = "KEPT_APPROVED"
AUDIO_POLICIES = (AUDIO_REMOVED, AUDIO_KEPT_APPROVED)

SCOPE_PUBLISHABLE = "publishable"


def _validate_source(value: Any, name: str) -> Dict[str, Any]:
    require(isinstance(value, dict), "MISSING_FIELD", f"{name} must be an object")
    logical = require_text(value.get("logical_path"), f"{name}.logical_path")
    require(logical.startswith(("project://", "repo://")), "NON_LOGICAL_PATH",
            f"{name}.logical_path must be project:// or repo://")
    require_sha256(value.get("sha256"), f"{name}.sha256")
    return dict(value)


def _validate_dimensions(value: Any) -> Dict[str, int]:
    require(isinstance(value, dict), "MISSING_FIELD",
            "source_dimensions must be an object")
    for axis in ("width", "height"):
        size = value.get(axis)
        require(isinstance(size, int) and not isinstance(size, bool) and size > 0,
                "INVALID_DIMENSIONS", f"source_dimensions.{axis} must be a positive int")
    return {"width": value["width"], "height": value["height"]}


def _validate_mask(mask: Any, dimensions: Dict[str, int], index: int) -> Dict[str, Any]:
    require(isinstance(mask, dict), "INVALID_MASK", f"masks[{index}] must be an object")
    require_text(mask.get("mask_id"), f"masks[{index}].mask_id")
    require_text(mask.get("reason"), f"masks[{index}].reason")
    parse_time_range(mask.get("time_range"), f"masks[{index}].time_range")
    rect = mask.get("rect")
    require(isinstance(rect, dict), "INVALID_MASK", f"masks[{index}].rect must be an object")
    values = {}
    for key in ("x", "y", "width", "height"):
        item = rect.get(key)
        require(isinstance(item, int) and not isinstance(item, bool) and item >= 0,
                "INVALID_MASK", f"masks[{index}].rect.{key} must be a non-negative int")
        values[key] = item
    require(values["width"] > 0 and values["height"] > 0, "INVALID_MASK",
            f"masks[{index}] has a zero-area rectangle")
    require(values["x"] + values["width"] <= dimensions["width"], "MASK_OUT_OF_BOUNDS",
            f"masks[{index}] extends past the source width")
    require(values["y"] + values["height"] <= dimensions["height"], "MASK_OUT_OF_BOUNDS",
            f"masks[{index}] extends past the source height")
    return {"mask_id": mask["mask_id"], "reason": mask["reason"],
            "time_range": mask["time_range"], "rect": values}


@dataclass
class RedactionReceipt:
    redaction_id: str
    raw_source: Dict[str, Any]
    output: Dict[str, Any]
    source_dimensions: Dict[str, int]
    audio_policy: str
    tool: Dict[str, Any]
    review_status: str
    reviewer: Optional[str] = None
    reviewed_at: Optional[str] = None
    masks: List[Dict[str, Any]] = field(default_factory=list)
    publishable_scope: bool = False
    notes: List[str] = field(default_factory=list)

    @property
    def audio_removed(self) -> bool:
        return self.audio_policy == AUDIO_REMOVED

    def validate(self) -> "RedactionReceipt":
        require_text(self.redaction_id, "redaction_id")
        raw = _validate_source(self.raw_source, "raw_source")
        output = _validate_source(self.output, "output")
        require(raw["sha256"] != output["sha256"], "RAW_EQUALS_OUTPUT",
                "a redaction must produce a distinct artifact; this receipt names "
                "one SHA for both source and output")
        require(raw["logical_path"] != output["logical_path"], "RAW_OVERWRITTEN",
                "the derivative must not overwrite the raw source path")
        dimensions = _validate_dimensions(self.source_dimensions)
        require(self.audio_policy in AUDIO_POLICIES, "INVALID_AUDIO_POLICY",
                f"audio_policy must be one of {AUDIO_POLICIES}")
        require(isinstance(self.tool, dict), "MISSING_FIELD", "tool must be an object")
        require_text(self.tool.get("name"), "tool.name")
        require_text(self.tool.get("version"), "tool.version")
        require(self.review_status in REVIEW_STATUSES, "INVALID_REVIEW_STATUS",
                f"review_status must be one of {REVIEW_STATUSES}")

        seen = set()
        validated = []
        for index, mask in enumerate(self.masks):
            item = _validate_mask(mask, dimensions, index)
            require(item["mask_id"] not in seen, "DUPLICATE_MASK_ID",
                    f"duplicate mask_id {item['mask_id']!r}")
            seen.add(item["mask_id"])
            validated.append(item)

        if self.publishable_scope:
            require(self.review_status == REVIEW_APPROVED, "REVIEW_NOT_APPROVED",
                    "a publishable derivative requires an APPROVED redaction review")
            require_text(self.reviewer, "reviewer")
            iso_utc(self.reviewed_at, "reviewed_at")
            require(self.audio_policy == AUDIO_REMOVED, "AUDIO_RETAINED",
                    "a publishable terminal derivative must have its audio removed "
                    "unless an approved audio use is declared separately")
        elif self.review_status == REVIEW_APPROVED:
            require_text(self.reviewer, "reviewer")
            iso_utc(self.reviewed_at, "reviewed_at")
        self.masks = validated
        return self

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": REDACTION_SCHEMA,
            "redaction_id": self.redaction_id,
            "raw_source": self.raw_source,
            "output": self.output,
            "source_dimensions": self.source_dimensions,
            "masks": self.masks,
            "audio_policy": self.audio_policy,
            "audio_removed": self.audio_removed,
            "tool": self.tool,
            "review_status": self.review_status,
            "reviewer": self.reviewer,
            "reviewed_at": self.reviewed_at,
            "publishable_scope": self.publishable_scope,
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, document: Dict[str, Any]) -> "RedactionReceipt":
        require_schema(document, REDACTION_SCHEMA)
        known = {
            "schema", "redaction_id", "raw_source", "output", "source_dimensions",
            "masks", "audio_policy", "audio_removed", "tool", "review_status",
            "reviewer", "reviewed_at", "publishable_scope", "notes",
        }
        unknown = sorted(set(document) - known)
        require(not unknown, "UNKNOWN_FIELD",
                f"unknown redaction fields: {', '.join(unknown)}")
        stored_removed = document.get("audio_removed")
        if stored_removed is not None:
            require(stored_removed == (document.get("audio_policy") == AUDIO_REMOVED),
                    "AUDIO_STATE_CONTRADICTION",
                    "audio_removed disagrees with audio_policy")
        try:
            receipt = cls(
                redaction_id=document["redaction_id"],
                raw_source=document["raw_source"],
                output=document["output"],
                source_dimensions=document["source_dimensions"],
                audio_policy=document["audio_policy"],
                tool=document["tool"],
                review_status=document["review_status"],
                reviewer=document.get("reviewer"),
                reviewed_at=document.get("reviewed_at"),
                masks=list(document.get("masks") or []),
                publishable_scope=bool(document.get("publishable_scope")),
                notes=list(document.get("notes") or []),
            )
        except KeyError as exc:
            raise ContractError("MISSING_FIELD",
                                f"redaction receipt is missing {exc.args[0]!r}") from None
        return receipt.validate()
