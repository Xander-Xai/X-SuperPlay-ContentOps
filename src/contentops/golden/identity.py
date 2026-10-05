"""Cross-arm evidence identity — the check that decides whether A/B/C/D is an
experiment at all.

If any factual placement differs between arms in digest, path, kind, evidence role,
claim refs or source ref, then the four videos differ in their evidence and any
apparent quality difference belongs to the evidence rather than to the enhancement
under test. There is no partial credit: one mismatch returns
``EXPERIMENT_INVALID``.

Kept separate from the builder because it is a property of the *set* of arms, not of
any one build, and because it is the last thing that should run before a human is
asked to spend attention on four videos.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

__all__ = ["EVIDENCE_IDENTITY_VERDICT", "compare_evidence_identity"]

EVIDENCE_IDENTITY_VERDICT = "EXPERIMENT_VALID"

#: The fields that must be identical for a factual placement across every arm.
IDENTITY_FIELDS = (
    "asset_path",
    "asset_sha256",
    "asset_kind",
    "evidence_use",
    "claim_refs",
    "source_ref",
)


def compare_evidence_identity(
    per_variant: Dict[str, Sequence[Dict[str, Any]]]
) -> Dict[str, Any]:
    """Compare every arm's factual placements field by field.

    Args:
        per_variant: ``variant_id -> factual asset list``, each entry shaped like
            :meth:`EvidenceLock.asset_identity` output.

    Returns:
        A report with ``verdict`` set to ``EXPERIMENT_VALID`` only when every arm
        agrees on every placement for every identity field, and ``EXPERIMENT_INVALID``
        otherwise, with the specific mismatches listed.

    Raises:
        ValueError: fewer than two arms were supplied. A single arm cannot be
            identical "across arms", and reporting ``EXPERIMENT_VALID`` for one arm
            would be a meaningless green light.
    """
    if len(per_variant) < 2:
        raise ValueError(
            f"evidence identity needs at least two arms to compare; got "
            f"{sorted(per_variant) or 'none'}"
        )

    arm_ids = sorted(per_variant)
    reference_arm = arm_ids[0]
    reference = {item["placement_id"]: item for item in per_variant[reference_arm]}

    mismatches: List[Dict[str, Any]] = []
    placements = set(reference)
    for arm_id in arm_ids:
        placements |= {item["placement_id"] for item in per_variant[arm_id]}

    for placement_id in sorted(placements):
        present: Dict[str, Dict[str, Any]] = {}
        for arm_id in arm_ids:
            match = next(
                (
                    item for item in per_variant[arm_id]
                    if item["placement_id"] == placement_id
                ),
                None,
            )
            present[arm_id] = match if match is not None else {}

        missing = [arm for arm, item in present.items() if not item]
        if missing:
            mismatches.append({
                "placement_id": placement_id,
                "kind": "EVIDENCE_ASSET_REMOVED",
                "arms_missing": missing,
                "detail": (
                    f"placement {placement_id!r} is absent from arm(s) "
                    f"{', '.join(missing)}"
                ),
            })
            continue

        for field_name in IDENTITY_FIELDS:
            values = {arm: present[arm].get(field_name) for arm in arm_ids}
            distinct = {repr(value) for value in values.values()}
            if len(distinct) > 1:
                mismatches.append({
                    "placement_id": placement_id,
                    "kind": "CLAIM_BINDING_CHANGED" if field_name == "claim_refs"
                    else "EVIDENCE_SHA_CHANGED" if field_name == "asset_sha256"
                    else "EVIDENCE_ASSET_REPLACED",
                    "field": field_name,
                    "values_by_arm": values,
                    "detail": (
                        f"{field_name} for placement {placement_id!r} differs across "
                        f"arms: {values}"
                    ),
                })

    all_identical = not mismatches
    return {
        "verdict": EVIDENCE_IDENTITY_VERDICT if all_identical else "EXPERIMENT_INVALID",
        "arms_compared": arm_ids,
        "reference_arm": reference_arm,
        "placements_compared": len(placements),
        "fields_compared": list(IDENTITY_FIELDS),
        "all_identical": all_identical,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
    }
