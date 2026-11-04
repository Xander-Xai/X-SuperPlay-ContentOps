"""Visual route: choose a surface per beat, and refuse when evidence is missing.

A beat that observes a real result needs a recording or a screenshot. A beat
that explains a mechanism may use a diagram. A generated image may support but
never stand in for an observation. Leaving that choice to the renderer is how a
cut ends up with a stock card over a claim that needed a screen.

This module maps a beat's evidence need and the material actually available to
one route, and fails closed when a direct observation has no real capture. A
generated route is always ``evidence_capable: false``.

What is not claimed
-------------------
A route does not prove the material is legible, current or correctly licensed.
It proves the routing decision is explicit and does not use generated material
as evidence.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from .contract import WorkflowError

SCHEMA = "contentops.visual-route/v1"

ROUTES = ("RECORDING", "SCREENSHOT", "DOCUMENT", "DIAGRAM", "CARD", "GENERATED_SUPPORT")

#: Routes that can carry a direct observation.
CAPTURE_ROUTES = ("RECORDING", "SCREENSHOT", "DOCUMENT")

#: Routes that explain rather than observe.
EXPLANATION_ROUTES = ("DIAGRAM", "CARD", "GENERATED_SUPPORT")

EVIDENCE_NEEDS = ("direct_observation", "explanation", "none")


def choose_visual_route(beat: Dict[str, Any]) -> Dict[str, Any]:
    """Choose one route for a beat, or refuse.

    ``beat`` declares ``evidence_need`` and the material available as
    ``available`` (a list of route names), plus ``rights_ok`` for that material.
    """
    if not isinstance(beat, dict):
        raise WorkflowError("VISUAL_BEAT", "beat must be an object")
    need = str(beat.get("evidence_need") or "").strip().lower()
    if need not in EVIDENCE_NEEDS:
        raise WorkflowError(
            "VISUAL_EVIDENCE_NEED",
            f"evidence_need {need!r} is not one of {', '.join(EVIDENCE_NEEDS)}",
        )
    available = [str(item).upper() for item in (beat.get("available") or [])]
    unknown = [item for item in available if item not in ROUTES]
    if unknown:
        raise WorkflowError("VISUAL_ROUTE_UNKNOWN", f"unknown material route(s): {', '.join(unknown)}")
    rights_ok = beat.get("rights_ok") is True

    if need == "direct_observation":
        usable = [item for item in CAPTURE_ROUTES if item in available]
        if not usable or not rights_ok:
            raise WorkflowError(
                "VISUAL_EVIDENCE_REQUIRED",
                "a direct observation needs a rights-cleared recording, screenshot or document",
            )
        route = usable[0]
        evidence_capable = True
    elif need == "explanation":
        usable = [item for item in EXPLANATION_ROUTES + CAPTURE_ROUTES if item in available]
        if not usable:
            raise WorkflowError("VISUAL_MATERIAL_REQUIRED", "an explanation needs at least one declared material route")
        route = usable[0]
        evidence_capable = route in CAPTURE_ROUTES
        if route == "GENERATED_SUPPORT" and not rights_ok:
            raise WorkflowError("VISUAL_GENERATED_RIGHTS", "generated support still needs a rights record")
    else:
        route = "CARD"
        evidence_capable = False

    return {
        "schema": SCHEMA,
        "beat_id": str(beat.get("beat_id") or beat.get("id") or ""),
        "evidence_need": need,
        "route": route,
        "evidence_capable": evidence_capable,
        "production_ready": False,
        "note": "generated support is never evidence; a direct observation needs a real capture",
    }


def validate_visual_route(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("schema") != SCHEMA:
        raise WorkflowError("VISUAL_SCHEMA", f"expected schema {SCHEMA}")
    if payload.get("route") not in ROUTES:
        raise WorkflowError("VISUAL_ROUTE_UNKNOWN", str(payload.get("route")))
    if payload.get("route") == "GENERATED_SUPPORT" and payload.get("evidence_capable") is not False:
        raise WorkflowError("VISUAL_GENERATED_EVIDENCE", "generated support must be evidence_capable: false")
    if payload.get("evidence_need") == "direct_observation" and payload.get("route") not in CAPTURE_ROUTES:
        raise WorkflowError("VISUAL_EVIDENCE_REQUIRED", "a direct observation cannot use an explanation route")
    if payload.get("production_ready") is not False:
        raise WorkflowError("VISUAL_PRODUCTION_READY", "a route may not claim production readiness")
    return payload
