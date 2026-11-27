"""Four-Layer Content Quality Evaluation & Independent Review Contract (T10).

Separates four orthogonal quality layers so a green technical QC or custom
score can never masquerade as editorial quality or Owner approval:

- **L1 Technical**: file integrity, resolution, codec, audio, design lint, HTML checks.
- **L2 Instruction Following**: deterministic verification against ``task-contract.json``.
- **L3 Content & Aesthetic**: independent reviewer assessment of information gain,
  natural Chinese voice, visual craft, and real artifact inspection (with explicit
  inspection-scope honesty, e.g. ``sampled_frames_plus_ffprobe``).
- **L4 Operational Value**: real publication outcome & human feedback (never automated).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

SCHEMA = "contentops.layered-review/v1"

ALLOWED_INSPECTION_SCOPES = (
    "full_text_and_read_aloud",
    "rendered_png_visual_inspection",
    "sampled_frames_plus_ffprobe",
    "full_video_playback",
    "code_and_receipt_only",
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_layered_review(
    *,
    artifact_id: str,
    artifact_kind: str,
    l1_technical: Dict[str, Any],
    l2_instruction: Dict[str, Any],
    l3_independent_review: Optional[Dict[str, Any]] = None,
    inspection_scope: str = "code_and_receipt_only",
    reviewer_is_independent: bool = False,
) -> Dict[str, Any]:
    """Assemble an honest L1-L4 review record. Never sets Owner ACCEPTED state."""
    if inspection_scope not in ALLOWED_INSPECTION_SCOPES:
        raise ValueError(f"invalid inspection_scope {inspection_scope!r}")

    l1_ok = bool(l1_technical.get("passed"))
    l2_ok = bool(l2_instruction.get("passed"))
    l3_present = isinstance(l3_independent_review, dict) and bool(l3_independent_review.get("verdict"))
    l3_ok = bool(l3_present and l3_independent_review.get("verdict") == "PASS_CANDIDATE" and reviewer_is_independent)

    if not l1_ok or not l2_ok:
        stage_status = "BLOCKED"
    elif l3_ok:
        stage_status = "PENDING_HUMAN_ACCEPTANCE"
    else:
        stage_status = "ARTIFACT_GENERATED"

    warnings: List[str] = []
    if not reviewer_is_independent and l3_present:
        warnings.append("SELF_REVIEW_WARNING: generator self-review is not independent editorial review")
    if artifact_kind == "video" and inspection_scope != "full_video_playback":
        warnings.append(f"INSPECTION_SCOPE_LIMITED: video checked via {inspection_scope}, not full playback")

    return {
        "schema": SCHEMA,
        "reviewed_at": _now(),
        "artifact_id": artifact_id,
        "artifact_kind": artifact_kind,
        "stage_status": stage_status,
        "inspection_scope": inspection_scope,
        "reviewer_is_independent": reviewer_is_independent,
        "layers": {
            "L1_technical": {"passed": l1_ok, "details": l1_technical},
            "L2_instruction_following": {"passed": l2_ok, "details": l2_instruction},
            "L3_content_and_aesthetic": l3_independent_review or {"status": "NOT_RUN"},
            "L4_operational_value": {"status": "PENDING_REAL_PUBLICATION_AND_OWNER_FEEDBACK"},
        },
        "warnings": warnings,
        "owner_accepted": False,
        "production_ready": False,
        "publish_authorized": False,
    }
