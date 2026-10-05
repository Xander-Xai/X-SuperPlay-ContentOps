"""The Founder review package: neutral by construction.

The temptation in an experiment like this is to describe D as the most advanced arm
and B as an improvement. Doing that before a human has watched would be deciding the
result and then inviting review of it, so this module makes that awkward rather
than easy:

- arms are labelled ``A``/``B``/``C``/``D`` with no adjective attached anywhere;
- the builder order is deliberately **not** presented as a preference order;
- the rubric is the same for every arm and asks the same questions in the same order;
- the allowed outcomes are ``A``, ``B``, ``C``, ``D`` and ``NONE`` — with ``NONE``
  treated as a real answer, not a formality;
- no score is ever synthesised. There is no field on this object that a program can
  fill in.

``selection`` stays ``PENDING_FOUNDER_REVIEW`` until a human writes a value, and
``reviewer``/``reviewed_at`` stay ``None`` so an unrun review is visibly unrun.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

__all__ = [
    "ALLOWED_SELECTIONS",
    "RUBRIC_DIMENSIONS",
    "FounderReview",
    "ReviewPackageError",
    "render_review_markdown",
]

PathLike = Union[str, Path]

#: A is allowed to win. So is NONE. Both are first-class outcomes.
ALLOWED_SELECTIONS = ("A", "B", "C", "D", "NONE")

PENDING = "PENDING_FOUNDER_REVIEW"

#: The rubric, in a fixed order, identical for every arm.
RUBRIC_DIMENSIONS: Sequence[Dict[str, str]] = (
    {
        "key": "voice_naturalness",
        "question": "Does the voice sound like a person speaking, and is it easy to follow?",
    },
    {
        "key": "visual_consistency",
        "question": "Does the video look like one piece, or do the visual sources clash?",
    },
    {
        "key": "pacing",
        "question": "Do the cuts and durations hold attention without dragging or rushing?",
    },
    {
        "key": "generated_image_usefulness",
        "question": "Where present, does the generated image add understanding, or is it decoration?",
    },
    {
        "key": "h3_usefulness",
        "question": "Where present, does the H3 insert earn its place, or would the video be tighter without it?",
    },
    {
        "key": "artifact_severity",
        "question": "Any deformation, garbled text, bad frame or unwanted audio?",
    },
    {
        "key": "overall_publishability",
        "question": "Would you publish this as-is?",
    },
)


class ReviewPackageError(ValueError):
    """The review package does not describe a reviewable experiment."""


@dataclass
class FounderReview:
    """A neutral review package over a set of variant receipts.

    Args:
        variant_ids: the arms included, in a **neutral** order. Callers should not
            sort these by "how advanced" the arm is.
        variant_receipts: the per-arm receipts, keyed by variant id.
        evidence_identity: the #25 cross-arm comparison. Required, because a review
            of four videos whose evidence differed is a review of nothing.
        artifacts: ``variant_id -> logical video reference``.
        notes: anything a reviewer needs that is not in a receipt.
    """

    variant_ids: List[str]
    variant_receipts: Dict[str, Dict[str, Any]]
    evidence_identity: Dict[str, Any]
    artifacts: Dict[str, str] = field(default_factory=dict)
    review: Dict[str, Any] = field(
        default_factory=lambda: {
            "selection": PENDING,
            "reviewer": None,
            "reviewed_at": None,
            "per_variant": {},
            "comments": {},
        }
    )
    notes: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": "contentops.founder-review/v1",
            "variant_ids": list(self.variant_ids),
            "rubric": [dict(dimension) for dimension in RUBRIC_DIMENSIONS],
            "allowed_selections": list(ALLOWED_SELECTIONS),
            "neutrality_note": (
                "The arms are labelled only. This package attaches no ranking "
                "language to any arm, and the order is not an ordering of merit."
            ),
            "artifacts": dict(self.artifacts),
            "variant_receipts": self.variant_receipts,
            "evidence_identity": self.evidence_identity,
            "review": self.review,
            "notes": dict(self.notes),
        }

    def write(self, path: PathLike) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(self.as_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return target

    # -- recording a human decision ---------------------------------------

    def record_review(
        self,
        *,
        reviewer: str,
        selection: str,
        reviewed_at: str,
        per_variant: Optional[Dict[str, Dict[str, Any]]] = None,
        comments: Optional[Dict[str, str]] = None,
    ) -> None:
        """Record a review a human actually performed.

        Raises:
            ReviewPackageError: the selection is not one of the allowed values, or a
                variant is missing. A partial review is refused rather than stored,
                because a package that looks reviewed but covers three of four arms
                is worse than one that plainly is not.
        """
        if selection not in ALLOWED_SELECTIONS:
            raise ReviewPackageError(
                f"selection must be one of {', '.join(ALLOWED_SELECTIONS)}; "
                f"got {selection!r}. NONE is a valid answer."
            )
        recorded = dict(per_variant or {})
        missing = [v for v in self.variant_ids if v not in recorded]
        if missing:
            raise ReviewPackageError(
                f"no review recorded for arm(s) {', '.join(missing)}. Every arm is "
                f"reviewed, including the ones that will not win."
            )
        self.review = {
            "selection": selection,
            "reviewer": reviewer,
            "reviewed_at": reviewed_at,
            "per_variant": recorded,
            "comments": dict(comments or {}),
        }

    def selection(self) -> str:
        return self.review.get("selection", PENDING)


def render_review_markdown(review: FounderReview) -> str:
    """Human-readable package, with no arm adjectives and no scores invented."""
    identity = review.evidence_identity
    verdict = identity.get("verdict")
    if verdict == "EXPERIMENT_VALID":
        claim = (
            "The factual evidence was compared across all four arms and is identical, "
            "so a difference between them belongs to the declared variable."
        )
    elif verdict == "EXPERIMENT_INVALID":
        claim = (
            "**The evidence identity check failed.** The arms do not share the same "
            "factual material, so any difference between them belongs to the evidence "
            "rather than to the declared variable. This package is not reviewable until "
            "that is fixed."
        )
    else:
        claim = (
            "**The evidence identity check has not been run**, so it is not yet known "
            "whether the arms share the same factual material. That check must read "
            "EXPERIMENT_VALID before the comparison means anything."
        )

    lines: List[str] = [
        "# Enhanced Golden A/B/C/D — Founder review",
        "",
        "**Status: `PENDING_FOUNDER_REVIEW`.** No score has been recorded and none "
        "will be inferred. Only a person who has watched and listened can fill this "
        "in.",
        "",
        "The four arms differ by one declared variable each. " + claim,
        "",
        "> The arms are labelled, not ranked. **A** is a legitimate outcome, and so is "
        "**NONE**. This package attaches no ranking language to any arm, and the order "
        "carries no merit.",
        "",
        "## What each arm changes",
        "",
        "| Arm | Declared change | Artifact |",
        "|---|---|---|",
    ]
    labels = {
        "A": "baseline narration, no generated image, no H3",
        "B": "narration changed, nothing else",
        "C": "narration as B, plus one generated support image",
        "D": "narration and image as C, plus one H3 support insert",
    }
    for variant_id in review.variant_ids:
        receipt = review.variant_receipts.get(variant_id, {})
        declared = receipt.get("declared_changes", {}) or {}
        summary = labels.get(variant_id, "see receipt")
        if variant_id == "A":
            summary = "the pinned baseline, nothing changed"
        lines.append(
            f"| **{variant_id}** | {summary} | "
            f"`{review.artifacts.get(variant_id, 'not yet built')}` |"
        )

    lines.extend([
        "",
        "## Evidence identity check",
        "",
        f"- verdict: **{verdict}**",
        f"- factual placements compared: **{identity.get('placements_compared', 'n/a')}**",
        f"- identical across all arms: **{identity.get('all_identical')}**",
    ])
    if identity.get("mismatches"):
        lines.append("")
        lines.append("Mismatches — these invalidate the experiment:")
        for item in identity["mismatches"]:
            lines.append(f"- `{json.dumps(item, ensure_ascii=False)}`")

    lines.extend([
        "",
        "## Rubric",
        "",
        "The same questions, in the same order, for every arm.",
        "",
    ])
    for index, dimension in enumerate(RUBRIC_DIMENSIONS, start=1):
        lines.append(f"{index}. **{dimension['key']}** — {dimension['question']}")

    lines.extend([
        "",
        "## Per-arm notes",
        "",
        "| Arm | Observations |",
        "|---|---|",
    ])
    comments = review.review.get("comments") or {}
    for variant_id in review.variant_ids:
        lines.append(f"| **{variant_id}** | {comments.get(variant_id, '_to be filled_')} |")

    lines.extend([
        "",
        "## Selection",
        "",
        f"**{review.selection()}**",
        "",
        f"Allowed: {', '.join(ALLOWED_SELECTIONS)}.",
        "",
        "If a later arm is selected, record why. If the baseline is selected, record "
        "that too: an outcome where the unchanged baseline stands is a real and useful "
        "result, and recording it honestly is the point of running the comparison.",
    ])
    if review.notes:
        lines.extend(["", "## Notes", ""])
        for key, value in sorted(review.notes.items()):
            lines.append(f"- **{key}**: {value}")
    return "\n".join(lines) + "\n"
