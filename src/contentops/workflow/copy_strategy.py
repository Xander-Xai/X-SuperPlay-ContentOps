"""Copy strategy: the argument shape a route is allowed to make.

"Write a script" is not a strategy. A hot-list item and a user-selected topic
need different arguments, and a claim that still needs verification cannot be
opened with a conclusion. Choosing the shape explicitly stops the script from
drifting between a news brief, a tutorial and a contrarian take in one cut.

The mapping is deliberately small and fails closed on an unknown route or
evidence state. It is a planning decision; it does not write copy.

What is not claimed
-------------------
The strategy does not make a claim true, and it is not a style guide for the
writer. It names the argument the later copy has to earn.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .contract import WorkflowError

SCHEMA = "contentops.copy-strategy/v1"

STRATEGIES = (
    "evidence_walkthrough",
    "contrarian_claim",
    "tutorial",
    "case_study",
    "news_brief",
)

#: Routes the router already produces.
ROUTES = ("HOTSPOT_DISCOVERY", "USER_TOPIC")

#: Evidence states a brief can declare.
EVIDENCE_STATES = ("verification_required", "verified", "approved")


def choose_strategy(route_mode: str, evidence_status: str, *,
                    has_real_material: bool = False) -> Dict[str, Any]:
    """Choose the argument shape for a route/evidence pair.

    A route that still needs verification never gets a conclusion-first shape;
    a verified route with real material may use a case study; a user topic
    without verification is a tutorial, not a claim.
    """
    route = str(route_mode or "").strip().upper()
    if route not in ROUTES:
        raise WorkflowError("COPY_ROUTE_UNKNOWN", f"route {route!r} is not one of {', '.join(ROUTES)}")
    evidence = str(evidence_status or "").strip().lower()
    if evidence not in EVIDENCE_STATES:
        raise WorkflowError(
            "COPY_EVIDENCE_UNKNOWN",
            f"evidence status {evidence!r} is not one of {', '.join(EVIDENCE_STATES)}",
        )

    if evidence in ("verified", "approved") and has_real_material:
        strategy = "case_study"
    elif evidence in ("verified", "approved"):
        strategy = "evidence_walkthrough"
    elif route == "USER_TOPIC":
        strategy = "tutorial"
    else:
        strategy = "news_brief"

    return {
        "schema": SCHEMA,
        "route_mode": route,
        "evidence_status": evidence,
        "strategy": strategy,
        "reason": _reason(strategy, route, evidence, has_real_material),
        "production_ready": False,
    }


def _reason(strategy: str, route: str, evidence: str, real: bool) -> str:
    if strategy == "case_study":
        return "verified evidence with real material: show the case, then the conclusion"
    if strategy == "evidence_walkthrough":
        return "verified evidence without real material: walk the evidence in order"
    if strategy == "tutorial":
        return "user-selected topic without verification: teach the method, not a claim"
    return "hot-list item without verification: report what is known and what is not"


def validate_strategy(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise WorkflowError("COPY_SCHEMA", f"expected schema {SCHEMA}")
    if payload.get("strategy") not in STRATEGIES:
        raise WorkflowError("COPY_STRATEGY_UNKNOWN", str(payload.get("strategy")))
    if payload.get("route_mode") not in ROUTES:
        raise WorkflowError("COPY_ROUTE_UNKNOWN", str(payload.get("route_mode")))
    if payload.get("evidence_status") not in EVIDENCE_STATES:
        raise WorkflowError("COPY_EVIDENCE_UNKNOWN", str(payload.get("evidence_status")))
    if payload.get("production_ready") is not False:
        raise WorkflowError("COPY_PRODUCTION_READY", "a plan may not claim production readiness")
    return payload
