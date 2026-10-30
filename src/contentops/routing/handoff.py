"""Hand an approved brief to the pipeline that will produce the episode.

Why this exists
---------------
The router's job ends with an approved brief. The pipeline's job starts with
a project that declares an account and, later, a reviewed script. Nothing in
between used to check that the brief was still the one a person approved, so
a project could be filled from an old package and nobody would notice.

This module is that check, and the smallest honest adapter between the two:

- it re-derives the approval digest from the brief on disk and refuses a brief
  that changed after it was approved;
- it refuses a brief whose evidence forecast says the episode needs a capture
  nobody has, rather than letting the pipeline discover that after paying for
  narration;
- it writes ``00_brief/handoff.json`` — what the next stage reads — and says
  in that record which gates are still ahead of it.

What it does not do
-------------------
It does not write a script, a storyboard or narration lines. Those come from
a person and the copy review, and inventing them here would be the exact
failure this repository keeps guarding against: a produced episode whose
claims never had a source.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .brief import BRIEF_DIR, BRIEF_FILE, content_digest

HANDOFF_SCHEMA = "contentops.brief-handoff/v1"
HANDOFF_FILE = "handoff.json"

#: Where the pipeline's own entry point expects the written episode.
SCRIPT_DIR = "script"


def script_state(project: Path) -> Dict[str, Any]:
    """Whether the episode has been written yet, and what is missing.

    The brief stops where a person starts: it says what the episode is about
    and what evidence it needs, not what the narration says. This reports the
    two files the production entry point reads, so "not written yet" is a
    named state with a next action rather than a crash somewhere downstream.
    """
    project = Path(project)
    lines = project / SCRIPT_DIR / "lines.json"
    assets = project / SCRIPT_DIR / "assets.json"
    problems: List[str] = []
    if not lines.is_file():
        problems.append("script/lines.json is missing: the narration has not been "
                        "written (a person writes it; the copy review approves it)")
    if not assets.is_file():
        problems.append("script/assets.json is missing: the evidence assets have not "
                        "been listed")
    return {"ready": not problems, "problems": problems,
            "lines": str(lines), "assets": str(assets)}


def read_brief(project: Path) -> Optional[Dict[str, Any]]:
    """The brief a project carries, or ``None`` when it carries none."""
    path = Path(project) / BRIEF_DIR / BRIEF_FILE
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def approval_of(package: Dict[str, Any]) -> Dict[str, Any]:
    intent = package.get("intent") or {}
    return ((intent.get("route_context") or {}).get("detail") or {}).get(
        "approval") or {}


def check(package: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Everything that must hold before the pipeline may start.

    Returns ``{"ok": bool, "reason": str, "detail": str}`` plus the facts the
    handoff record needs. A missing or changed approval is a refusal; a
    degraded forecast is a refusal too, because "the evidence is not there" is
    a decision for a person, not a detail to discover mid-production.
    """
    if package is None:
        return {"ok": False, "reason": "BRIEF_MISSING",
                "detail": "the project has no 00_brief/brief.json"}
    intent = package.get("intent") or {}
    approval = approval_of(package)
    if not approval:
        return {"ok": False, "reason": "NOT_APPROVED",
                "detail": "the brief carries no approval record"}
    approved_digest = str(approval.get("content_digest") or "")
    if not approved_digest:
        return {"ok": False, "reason": "APPROVAL_UNBOUND",
                "detail": "the approval records no content digest, so it cannot be "
                          "tied to what was reviewed"}
    current = content_digest(package)
    if current != approved_digest:
        return {"ok": False, "reason": "APPROVAL_STALE",
                "detail": f"the brief changed after approval (approved "
                          f"{approved_digest[:12]}, now {current[:12]}); review it again"}
    if intent.get("approval_status") != "approved":
        return {"ok": False, "reason": "NOT_APPROVED",
                "detail": f"the brief says approval_status "
                          f"{intent.get('approval_status')!r}"}
    if str(approval.get("actor_kind")) == "automation":
        # An acceptance run's approval is evidence that the path works, not a
        # permission for an episode. It cannot travel into a real pipeline.
        from .router import sandbox_environment
        if not sandbox_environment():
            return {"ok": False, "reason": "AUTOMATION_APPROVAL",
                    "detail": "the brief was approved by an automation, which may be "
                              "used in an acceptance sandbox but never handed to the "
                              "pipeline", "content_digest": current}
    if str(package.get("forecast_verdict")) == "DEGRADED":
        return {"ok": False, "reason": "EVIDENCE_REQUIRED",
                "detail": "the evidence forecast is DEGRADED: the episode needs a "
                          "capture this brief has not produced, and a person has to "
                          "decide whether to get it or narrow the claim",
                "content_digest": current}
    return {"ok": True, "reason": "READY", "detail": "the brief is approved and "
                                                   "unchanged", "content_digest": current}


def handoff_record(project: Path, package: Dict[str, Any],
                   route: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """What the next stage reads, once the checks above have passed."""
    intent = package.get("intent") or {}
    approval = approval_of(package)
    return {
        "schema": HANDOFF_SCHEMA,
        "brief_id": package.get("brief_id"),
        "content_digest": content_digest(package),
        "account_id": intent.get("account_id"),
        "account_profile_version": intent.get("account_profile_version"),
        "route_mode": intent.get("route_mode"),
        "topic": intent.get("topic"),
        "content_angle": intent.get("content_angle"),
        "source_artifact_refs": list(intent.get("source_artifact_refs") or []),
        "evidence_status": intent.get("evidence_status"),
        "target_pipeline": intent.get("target_pipeline"),
        "approval": {
            "reviewer": approval.get("reviewer"),
            "actor_kind": approval.get("actor_kind"),
            "approved_at": approval.get("approved_at"),
            "content_digest": approval.get("content_digest"),
        },
        "route": route or {},
        # The gates that are still ahead. This record is the start of the
        # pipeline, not a permission slip through it.
        "still_gated_by": [
            "copy review (receipts/script-review.json) before any narration is "
            "synthesised",
            "the account's own evidence policy at capture time",
        ],
    }


def write_handoff(project: Path, record: Dict[str, Any]) -> Path:
    path = Path(project) / BRIEF_DIR / HANDOFF_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return path
