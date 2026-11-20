"""M5 human-review receipt stage (Issue #140 slice).

The stage records automated QC context and a pending review receipt only. It
never approves production or publication; bundle changes revoke prior review.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional

from contentops.paths import relative_label


def stage_review(
    project: Path,
    slug: str,
    qc: Dict[str, Any],
    bundle: Optional[Dict[str, Any]] = None,
    *,
    read_json_or_none: Callable[[Path], Any],
    write_json: Callable[[Path, Dict[str, Any]], None],
) -> Dict[str, Any]:
    """Write a pending human-review receipt bound to the current Bundle."""
    report = qc["report"]
    fails = [c["id"] for c in report.get("checks", []) if c.get("severity") == "FAIL"]
    warns = [c["id"] for c in report.get("checks", []) if c.get("severity") == "WARN"]
    bundle_id = (bundle or {}).get("bundle_id")
    bundle_sha = (bundle or {}).get("bundle_sha256")

    # A review is bound to the Bundle bytes it saw. If those bytes moved, the
    # old review is revoked rather than left standing next to fresh evidence.
    previous = read_json_or_none(project / "receipts" / "human-review.json")
    revoked = None
    if previous and bundle_sha is not None:
        reviewed = previous.get("reviewer") or previous.get("decision")
        if reviewed and previous.get("bundle_sha256") != bundle_sha:
            revoked = previous

    voice_check = next((check for check in report.get("checks", [])
                        if check.get("id") == "voice_quality_declared"), {})
    voice_quality = (voice_check.get("voice_quality")
                     or voice_check.get("voice_provider") or "unknown")

    payload = {
        "project": relative_label(project),
        "video": f"{relative_label(project)}/final/{slug}.mp4",
        "engine": "easel",
        "voice_quality": voice_quality,
        "bundle_id": bundle_id,
        "bundle_sha256": bundle_sha,
        "production_ready": False,
        "state": "PENDING_FOUNDER_REVIEW",
        "auto_qc_result": report.get("overall"),
        "auto_qc_checks": len(report.get("checks", [])),
        "auto_qc_fails": fails,
        "auto_qc_warns": warns,
        "reviewer": None,
        "reviewed_at": None,
        "scores": None,
        "decision": None,
        "note": "scores are null until a human fills them; this file is not an approval",
    }
    if revoked:
        payload["review_revoked_reason"] = "BUNDLE_CHANGED"
        payload["revoked_review"] = {
            key: revoked.get(key)
            for key in ("reviewer", "reviewed_at", "decision", "bundle_sha256")
        }
    write_json(project / "receipts" / "human-review.json", payload)
    return payload
