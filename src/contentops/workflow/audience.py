"""Audience insight: who a cut is for and what they must be able to do after it.

A brief names a candidate and a route; it rarely names the person on the other
side of the screen. Without that, "audience" collapses into "everyone", and a
cut tries to explain a mechanism to a beginner and a caveat to an expert in the
same 30 seconds.

This module turns the account profile and the brief into one explicit audience
record. It is a planning artifact: it never contacts a person, never claims a
survey, and never turns a guess into evidence. The fields are derived from what
the account already declares, and an unrecognised segment fails closed.

What is not claimed
-------------------
A valid record does not prove the audience exists, is reachable, or will care.
It proves the cut has one named reader and one stated outcome, so the script can
be judged against something specific.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional

from .contract import WorkflowError

SCHEMA = "contentops.audience-insight/v1"

#: Segments the accounts already use. A new segment is a product decision, not
#: a free-form string.
SEGMENTS = ("practitioner", "operator", "founder", "researcher", "generalist")

#: What the viewer must be able to do after the cut. Not a mood.
OUTCOMES = ("reproduce", "evaluate", "decide", "understand", "adopt")

#: Whether the cut must show a real observation or may explain.
EVIDENCE_NEEDS = ("direct_observation", "explanation", "none")


def plan_audience(account: Dict[str, Any], brief: Dict[str, Any]) -> Dict[str, Any]:
    """Build one audience record from an account profile and a brief.

    ``account`` is the content account document (the profile block or the whole
    file); ``brief`` is a ``contentops.content-brief/v1`` payload. The function
    reads only declared fields and refuses an unknown segment or outcome.
    """
    profile = account.get("profile") if isinstance(account.get("profile"), dict) else account
    segment = str(profile.get("audience_segment") or "").strip().lower()
    if not segment:
        segment = "practitioner"
    if segment not in SEGMENTS:
        raise WorkflowError(
            "AUDIENCE_SEGMENT_UNKNOWN",
            f"segment {segment!r} is not one of {', '.join(SEGMENTS)}",
        )

    intent = brief.get("intent") if isinstance(brief.get("intent"), dict) else {}
    candidate = brief.get("candidate") if isinstance(brief.get("candidate"), dict) else {}
    outcome = str(intent.get("desired_outcome") or candidate.get("decision") or "").strip().lower()
    if not outcome:
        outcome = "understand"
    if outcome not in OUTCOMES:
        raise WorkflowError(
            "AUDIENCE_OUTCOME_UNKNOWN",
            f"outcome {outcome!r} is not one of {', '.join(OUTCOMES)}",
        )

    evidence_need = str(intent.get("evidence_status") or "").strip().lower()
    if evidence_need == "verification_required":
        evidence_need = "direct_observation"
    elif evidence_need in ("verified", "approved"):
        evidence_need = "explanation"
    if evidence_need not in EVIDENCE_NEEDS:
        evidence_need = "explanation"

    topic = str(intent.get("topic") or candidate.get("title") or "").strip()
    if not topic:
        raise WorkflowError("AUDIENCE_TOPIC_MISSING", "the brief names no topic")

    return {
        "schema": SCHEMA,
        "account_id": str(profile.get("account_id") or account.get("account_id") or ""),
        "segment": segment,
        "desired_outcome": outcome,
        "evidence_need": evidence_need,
        "topic": topic,
        "language": str(profile.get("language") or "zh-CN"),
        # A planning record, never a claim about real people.
        "basis": "declared account profile + brief; no survey, no inference",
        "production_ready": False,
    }


def validate_audience(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Validate an audience record, returning it unchanged on success."""
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise WorkflowError("AUDIENCE_SCHEMA", f"expected schema {SCHEMA}")
    if payload.get("segment") not in SEGMENTS:
        raise WorkflowError("AUDIENCE_SEGMENT_UNKNOWN", str(payload.get("segment")))
    if payload.get("desired_outcome") not in OUTCOMES:
        raise WorkflowError("AUDIENCE_OUTCOME_UNKNOWN", str(payload.get("desired_outcome")))
    if payload.get("evidence_need") not in EVIDENCE_NEEDS:
        raise WorkflowError("AUDIENCE_EVIDENCE_NEED", str(payload.get("evidence_need")))
    if not str(payload.get("topic") or "").strip():
        raise WorkflowError("AUDIENCE_TOPIC_MISSING", "topic is empty")
    if payload.get("production_ready") is not False:
        raise WorkflowError("AUDIENCE_PRODUCTION_READY", "a plan may not claim production readiness")
    return payload
