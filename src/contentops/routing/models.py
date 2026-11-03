"""The unified content input contract and the one state machine both routes use.

Why this exists
---------------
The repository could produce a film, but nothing owned the *question* that
precedes it: "who is this for, and what is it about?". Two answers were
available before this module: a hot list nobody asked for, or a title a person
typed. Both ended up in the same place — a project directory — and neither
carried a record of where it came from.

So there is exactly one object, :class:`ContentIntent`, and it carries its own
provenance. The two ways in produce it differently, but the object they produce
has the same shape, the same fields and the same downstream contract. A module
that consumes an intent therefore never asks which route made it.

Two deliberate properties:

- **The route never branches downstream.** Everything route-specific lives under
  one ``route_context`` object with the same keys in both modes. A consumer
  reads ``route_context.candidate_id`` and does not care whether it is
  ``None`` because the user typed the topic or because a person picked a
  hot-list candidate.
- **A state is earned, not assigned.** :data:`TRANSITIONS` is the only way a
  run changes state, and it has no ``force`` path. A run that collected
  hotspots cannot claim a topic was selected, and a run with a topic cannot
  claim candidates were offered.

What is deliberately not claimed
--------------------------------
A brief that says ``evidence_status: verified`` means the evidence *paths*
were recorded and checked for presence. It does not mean the claims inside
them are true; that is the copy review's job, further downstream.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..canonical import canonical_bytes, digest, utcnow

CONTENT_INTENT_SCHEMA = "contentops.content-intent/v1"
CANDIDATE_SCHEMA = "contentops.hotspot-candidate/v1"

#: The two ways a run can enter. Both are explicit; neither is inferred.
ROUTE_MODES: Tuple[str, ...] = ("HOTSPOT_DISCOVERY", "USER_TOPIC")

#: The states a run occupies. Exactly one at a time.
ACCOUNT_REQUIRED = "ACCOUNT_REQUIRED"
ACCOUNT_DNA_MISSING = "ACCOUNT_DNA_MISSING"
ROUTE_SELECTION_REQUIRED = "ROUTE_SELECTION_REQUIRED"
INPUT_REQUIRED = "INPUT_REQUIRED"
SEARCH_PLAN_READY = "SEARCH_PLAN_READY"
CANDIDATES_READY = "CANDIDATES_READY"
TOPIC_SELECTED = "TOPIC_SELECTED"
OUT_OF_PROFILE_REVIEW_REQUIRED = "OUT_OF_PROFILE_REVIEW_REQUIRED"
EVIDENCE_REQUIRED = "EVIDENCE_REQUIRED"
BRIEF_READY = "BRIEF_READY"
AWAITING_HUMAN_APPROVAL = "AWAITING_HUMAN_APPROVAL"
APPROVED_FOR_PRODUCTION = "APPROVED_FOR_PRODUCTION"
BLOCKED = "BLOCKED"

STATES: Tuple[str, ...] = (
    ACCOUNT_REQUIRED,
    ACCOUNT_DNA_MISSING,
    ROUTE_SELECTION_REQUIRED,
    INPUT_REQUIRED,
    SEARCH_PLAN_READY,
    CANDIDATES_READY,
    TOPIC_SELECTED,
    OUT_OF_PROFILE_REVIEW_REQUIRED,
    EVIDENCE_REQUIRED,
    BRIEF_READY,
    AWAITING_HUMAN_APPROVAL,
    APPROVED_FOR_PRODUCTION,
    BLOCKED,
)

#: The only legal moves. A state that is not a key here is terminal.
#:
#: ``BLOCKED`` is reachable from everywhere and leads nowhere: a blocked run is
#: a record of what stopped it, not a stage to be resumed past. Resuming a
#: blocked run is a *new* run, because the reason it blocked may no longer
#: hold.
TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    ACCOUNT_REQUIRED: (ACCOUNT_DNA_MISSING, ROUTE_SELECTION_REQUIRED, BLOCKED),
    ACCOUNT_DNA_MISSING: (BLOCKED,),
    ROUTE_SELECTION_REQUIRED: (INPUT_REQUIRED, SEARCH_PLAN_READY, BLOCKED),
    INPUT_REQUIRED: (OUT_OF_PROFILE_REVIEW_REQUIRED, EVIDENCE_REQUIRED, BLOCKED),
    SEARCH_PLAN_READY: (CANDIDATES_READY, BLOCKED),
    CANDIDATES_READY: (TOPIC_SELECTED, BLOCKED),
    TOPIC_SELECTED: (EVIDENCE_REQUIRED, BRIEF_READY, BLOCKED),
    OUT_OF_PROFILE_REVIEW_REQUIRED: (EVIDENCE_REQUIRED, BLOCKED),
    EVIDENCE_REQUIRED: (BRIEF_READY, BLOCKED),
    BRIEF_READY: (AWAITING_HUMAN_APPROVAL, BLOCKED),
    AWAITING_HUMAN_APPROVAL: (APPROVED_FOR_PRODUCTION, BLOCKED),
    APPROVED_FOR_PRODUCTION: (),
    BLOCKED: (),
}

#: ``evidence_status`` values on an intent.
EVIDENCE_STATUSES = ("verification_required", "collected", "verified")

#: ``approval_status`` values on an intent. ``pending`` is the only state in
#: which the run may still be waiting for a person.
APPROVAL_STATUSES = ("pending", "approved", "rejected", "changes_requested")

#: ``target_pipeline`` values. ``VIDEO`` is the only pipeline this repository
#: can currently run, but the field exists so a text-only account can be
#: represented honestly instead of being forced into the video generator.
TARGET_PIPELINES = ("VIDEO", "TEXT_ARTICLE")


class RoutingError(Exception):
    """A refusal with a machine-readable code.

    The code is the contract. ``detail`` is the human sentence; callers branch
    on the code, never on the prose.
    """

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail





@dataclass
class RouteContext:
    """Everything route-specific, in one object with the same keys either way.

    A downstream consumer reads these keys without branching on the route. The
    values differ; the shape does not. That is the whole point: the two
    entrances are adapted away here, once, instead of being branched on for
    the rest of the pipeline.
    """

    mode: str
    #: Route A: the id of the search plan that produced the candidates.
    #: Route B: ``None`` — no hot list was consulted.
    search_plan_id: Optional[str] = None
    #: Route A: the id of the candidate a person chose.
    #: Route B: ``None`` — the topic came from the user.
    candidate_id: Optional[str] = None
    #: Where the topic came from. The two values are the only honest answers.
    topic_origin: str = ""
    #: The person's own words, preserved verbatim in both routes.
    user_input: Optional[str] = None
    #: When a person made a choice, and which choice it was.
    selected_at: Optional[str] = None
    selected_by: Optional[str] = None
    #: A person's explicit override of an off-profile topic. Never inferred.
    off_profile_override: Optional[Dict[str, Any]] = None
    #: Free-form provenance for the route: the plan, the collection receipt.
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mode": self.mode,
            "search_plan_id": self.search_plan_id,
            "candidate_id": self.candidate_id,
            "topic_origin": self.topic_origin,
            "user_input": self.user_input,
            "selected_at": self.selected_at,
            "selected_by": self.selected_by,
            "off_profile_override": self.off_profile_override,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "RouteContext":
        return cls(
            mode=payload.get("mode", ""),
            search_plan_id=payload.get("search_plan_id"),
            candidate_id=payload.get("candidate_id"),
            topic_origin=payload.get("topic_origin", ""),
            user_input=payload.get("user_input"),
            selected_at=payload.get("selected_at"),
            selected_by=payload.get("selected_by"),
            off_profile_override=payload.get("off_profile_override"),
            detail=dict(payload.get("detail") or {}),
        )


@dataclass
class ContentIntent:
    """The unified input every downstream stage reads.

    Field names are the repository's, not a fresh dialect: ``route_mode``,
    ``approval_status`` and ``evidence_status`` are the same words the copy
    review and the evidence forecast already use.
    """

    account_id: str
    account_profile_version: str
    route_mode: str
    topic: str
    content_angle: Optional[str] = None
    source_artifact_refs: List[str] = field(default_factory=list)
    evidence_status: str = "verification_required"
    approval_status: str = "pending"
    target_pipeline: str = "VIDEO"
    brief_status: str = "draft"
    route_context: RouteContext = field(default_factory=lambda: RouteContext(mode=""))
    profile: Dict[str, Any] = field(default_factory=dict)
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    #: Set when the account's own positioning says this topic is off-profile.
    profile_alignment: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": CONTENT_INTENT_SCHEMA,
            "account_id": self.account_id,
            "account_profile_version": self.account_profile_version,
            "route_mode": self.route_mode,
            "topic": self.topic,
            "content_angle": self.content_angle,
            "source_artifact_refs": list(self.source_artifact_refs),
            "evidence_status": self.evidence_status,
            "approval_status": self.approval_status,
            "target_pipeline": self.target_pipeline,
            "brief_status": self.brief_status,
            "route_context": self.route_context.to_dict(),
            "profile": dict(self.profile),
            "evidence": list(self.evidence),
            "profile_alignment": dict(self.profile_alignment),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ContentIntent":
        if not isinstance(payload, dict):
            raise RoutingError("MALFORMED_INTENT", "a content intent must be a JSON object")
        if payload.get("schema") != CONTENT_INTENT_SCHEMA:
            raise RoutingError(
                "UNSUPPORTED_SCHEMA",
                f"expected {CONTENT_INTENT_SCHEMA!r}, got {payload.get('schema')!r}")
        return cls(
            account_id=payload.get("account_id", ""),
            account_profile_version=payload.get("account_profile_version", ""),
            route_mode=payload.get("route_mode", ""),
            topic=payload.get("topic", ""),
            content_angle=payload.get("content_angle"),
            source_artifact_refs=list(payload.get("source_artifact_refs") or []),
            evidence_status=payload.get("evidence_status", "verification_required"),
            approval_status=payload.get("approval_status", "pending"),
            target_pipeline=payload.get("target_pipeline", "VIDEO"),
            brief_status=payload.get("brief_status", "draft"),
            route_context=RouteContext.from_dict(payload.get("route_context") or {}),
            profile=dict(payload.get("profile") or {}),
            evidence=list(payload.get("evidence") or []),
            profile_alignment=dict(payload.get("profile_alignment") or {}),
            created_at=payload.get("created_at", ""),
        )

    def intent_id(self) -> str:
        """A stable id for this intent, so a brief can be cited by digest."""
        return f"INTENT-{digest(self.to_dict())[:16].upper()}"


def validate_intent(payload: Any) -> List[str]:
    """Structural failures for an intent document. Empty list means it is sound."""
    if not isinstance(payload, dict):
        return ["a content intent must be a JSON object"]
    if payload.get("schema") != CONTENT_INTENT_SCHEMA:
        return [f"schema must be {CONTENT_INTENT_SCHEMA!r}"]
    errors: List[str] = []
    if not str(payload.get("account_id") or "").strip():
        errors.append("account_id must be a non-empty string")
    if not str(payload.get("account_profile_version") or "").strip():
        errors.append("account_profile_version must be a non-empty string")
    if payload.get("route_mode") not in ROUTE_MODES:
        errors.append(f"route_mode must be one of {list(ROUTE_MODES)}")
    if not str(payload.get("topic") or "").strip():
        errors.append("topic must be a non-empty string")
    if payload.get("evidence_status") not in EVIDENCE_STATUSES:
        errors.append(f"evidence_status must be one of {list(EVIDENCE_STATUSES)}")
    if payload.get("approval_status") not in APPROVAL_STATUSES:
        errors.append(f"approval_status must be one of {list(APPROVAL_STATUSES)}")
    if payload.get("target_pipeline") not in TARGET_PIPELINES:
        errors.append(f"target_pipeline must be one of {list(TARGET_PIPELINES)}")
    context = payload.get("route_context")
    if not isinstance(context, dict):
        errors.append("route_context must be an object")
    else:
        if context.get("mode") not in ROUTE_MODES:
            errors.append(f"route_context.mode must be one of {list(ROUTE_MODES)}")
        if context.get("topic_origin") not in ("USER_INPUT", "HOTSPOT_SELECTION"):
            errors.append("route_context.topic_origin must be USER_INPUT or "
                          "HOTSPOT_SELECTION")
    return errors


def can_transition(current: str, target: str) -> bool:
    """Whether ``current -> target`` is a legal move. There is no force path."""
    return target in TRANSITIONS.get(current, ())


def assert_transition(current: str, target: str) -> None:
    if not can_transition(current, target):
        raise RoutingError(
            "ILLEGAL_TRANSITION",
            f"{current!r} -> {target!r} is not a legal move; legal targets are "
            f"{list(TRANSITIONS.get(current, ()))}")
