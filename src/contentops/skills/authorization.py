"""Bind one skill execution to one explicit grant.

Why this module exists
----------------------
The skill router answers two questions: what exists (discovery) and which
declared capability may be handed to an adapter (resolution). Neither answers
"may *this caller* run *this operation* now?". Treating `RESOLVABLE`, a licence
declaration or a reachable provider as permission is exactly the mistake this
module exists to prevent.

What it is not
--------------
It is not a second policy engine and not a second source of truth. It re-checks
nothing the existing gates already decide:

* rights verification and provider-path permission stay in the registry and the
  adapter;
* runtime integrity stays in the adapter's lock verifier;
* asset-level rights stay in the M5 stage's ``rights_reviewed`` gate.

This module only composes those verdicts with a *grant*: an auditable record of
who approved which skill version, for which account, pipeline, stage and
operations, with a budget and an expiry. Its only output is a decision.

Default deny
------------
Every path returns ``BLOCKED`` unless a grant is present, unexpired, unrevoked,
unexhausted and bound to the exact request. A caller cannot widen a grant by
asking for a different account, stage, operation, version or budget.

States
------
``DISCOVERED`` -> ``RESOLVABLE`` -> ``EXECUTION_REQUESTED`` -> ``AUTHORIZED``
-> ``EXECUTED``, with ``BLOCKED`` reachable from every step. Only
``AUTHORIZED`` is produced here; ``EXECUTED`` is recorded by the adapter that
actually ran, from its own receipt.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Tuple

__all__ = [
    "STATE_AUTHORIZED",
    "STATE_BLOCKED",
    "STATE_DISCOVERED",
    "STATE_EXECUTED",
    "STATE_EXECUTION_REQUESTED",
    "STATE_RESOLVABLE",
    "REASON_AUTHORIZED",
    "REASON_BUDGET_EXCEEDED",
    "REASON_CALLER_MISMATCH",
    "REASON_CONTEXT_MISMATCH",
    "REASON_GRANT_EXPIRED",
    "REASON_GRANT_NOT_YET_VALID",
    "REASON_GRANT_REVOKED",
    "REASON_NO_GRANT",
    "REASON_NOT_RESOLVABLE",
    "REASON_OPERATION_NOT_GRANTED",
    "REASON_UNKNOWN_SKILL",
    "REASON_USES_EXHAUSTED",
    "REASON_VERSION_MISMATCH",
    "Decision",
    "ExecutionGrant",
    "ExecutionRequest",
    "evaluate",
]

# Lifecycle. Only AUTHORIZED and BLOCKED are produced by :func:`evaluate`.
STATE_DISCOVERED = "DISCOVERED"
STATE_RESOLVABLE = "RESOLVABLE"
STATE_EXECUTION_REQUESTED = "EXECUTION_REQUESTED"
STATE_AUTHORIZED = "AUTHORIZED"
STATE_EXECUTED = "EXECUTED"
STATE_BLOCKED = "BLOCKED"

REASON_AUTHORIZED = "AUTHORIZED"
REASON_UNKNOWN_SKILL = "UNKNOWN_SKILL"
REASON_NOT_RESOLVABLE = "NOT_RESOLVABLE"
REASON_VERSION_MISMATCH = "VERSION_MISMATCH"
REASON_NO_GRANT = "NO_GRANT"
REASON_GRANT_REVOKED = "GRANT_REVOKED"
REASON_GRANT_EXPIRED = "GRANT_EXPIRED"
REASON_GRANT_NOT_YET_VALID = "GRANT_NOT_YET_VALID"
REASON_CONTEXT_MISMATCH = "CONTEXT_MISMATCH"
REASON_OPERATION_NOT_GRANTED = "OPERATION_NOT_GRANTED"
REASON_CALLER_MISMATCH = "CALLER_MISMATCH"
REASON_BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
REASON_USES_EXHAUSTED = "USES_EXHAUSTED"


@dataclass(frozen=True)
class ExecutionRequest:
    """One concrete execution a caller asks for.

    Frozen because a request that can be edited after the fact cannot be bound
    to a grant. ``operations`` are the exact verbs being requested; an adapter
    may accept fewer, never more.
    """

    request_id: str
    skill_id: str
    skill_version: str
    account: str
    pipeline: str
    stage: str
    operations: Tuple[str, ...]
    caller: str
    units: int = 1


@dataclass(frozen=True)
class ExecutionGrant:
    """An approval bound to one exact context.

    ``principal`` is the authorizing party, ``caller`` in the request is the
    actor. They must match for a grant to apply, so a grant cannot be borrowed
    by another caller.
    """

    grant_id: str
    principal: str
    skill_id: str
    skill_version: str
    account: str
    pipeline: str
    stage: str
    operations: Tuple[str, ...]
    issued_at: str
    expires_at: str
    max_units: int = 1
    max_uses: int = 1
    uses_consumed: int = 0
    revoked: bool = False
    revoked_reason: str = ""


@dataclass(frozen=True)
class Decision:
    """The outcome. Never carries a capability, only a verdict and its reason."""

    state: str
    reason: str
    detail: str
    request_id: str = ""
    grant_id: Optional[str] = None
    execution_authorized: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "reason": self.reason,
            "detail": self.detail,
            "request_id": self.request_id,
            "grant_id": self.grant_id,
            "execution_authorized": self.execution_authorized,
        }


def _parse(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _now(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    parsed = _parse(str(value))
    return parsed or datetime.now(timezone.utc)


def _blocked(reason: str, detail: str, request: ExecutionRequest,
             grant: Optional[ExecutionGrant] = None) -> Decision:
    return Decision(
        state=STATE_BLOCKED,
        reason=reason,
        detail=detail,
        request_id=request.request_id,
        grant_id=grant.grant_id if grant else None,
        execution_authorized=False,
    )


def evaluate(request: ExecutionRequest, *,
             verdict: Optional[Mapping[str, Any]],
             grant: Optional[ExecutionGrant] = None,
             now: Any = None,
             registry_entry: Optional[Mapping[str, Any]] = None) -> Decision:
    """Decide one execution request. Default deny.

    ``verdict`` is the router's resolution record. It is a *precondition*, not a
    decision: a ``RESOLVABLE`` verdict without a matching grant is still blocked.
    """
    if not verdict or verdict.get("verdict") != STATE_RESOLVABLE:
        reason = (verdict or {}).get("reason") or "no resolution record"
        return _blocked(REASON_NOT_RESOLVABLE,
                        f"the router did not resolve this skill: {reason}", request)

    if registry_entry is not None:
        declared_id = registry_entry.get("id") or registry_entry.get("name")
        if declared_id != request.skill_id:
            return _blocked(REASON_UNKNOWN_SKILL,
                            f"requested {request.skill_id!r}, declared {declared_id!r}",
                            request)
        declared_version = (registry_entry.get("source") or {}).get("version")
        if declared_version and declared_version != request.skill_version:
            return _blocked(REASON_VERSION_MISMATCH,
                            f"requested version {request.skill_version!r}, "
                            f"declared {declared_version!r}", request)

    if grant is None:
        return _blocked(REASON_NO_GRANT,
                        "resolution is a pointer, not an execution authorization", request)

    if grant.revoked:
        detail = "the grant was revoked"
        if grant.revoked_reason:
            detail = f"the grant was revoked: {grant.revoked_reason}"
        return _blocked(REASON_GRANT_REVOKED, detail, request, grant)

    moment = _now(now)
    issued = _parse(grant.issued_at)
    expires = _parse(grant.expires_at)
    if issued is None or expires is None:
        return _blocked(REASON_GRANT_NOT_YET_VALID,
                        "the grant has no usable issued_at/expires_at", request, grant)
    if moment < issued:
        return _blocked(REASON_GRANT_NOT_YET_VALID,
                        f"the grant is not valid before {grant.issued_at}", request, grant)
    if moment >= expires:
        return _blocked(REASON_GRANT_EXPIRED,
                        f"the grant expired at {grant.expires_at}", request, grant)

    bound = (
        ("skill_id", request.skill_id, grant.skill_id),
        ("skill_version", request.skill_version, grant.skill_version),
        ("account", request.account, grant.account),
        ("pipeline", request.pipeline, grant.pipeline),
        ("stage", request.stage, grant.stage),
    )
    for field, wanted, approved in bound:
        if wanted != approved:
            return _blocked(REASON_CONTEXT_MISMATCH,
                            f"{field}: requested {wanted!r}, granted {approved!r}",
                            request, grant)

    if request.caller != grant.principal:
        return _blocked(REASON_CALLER_MISMATCH,
                        f"caller {request.caller!r} is not the granting principal "
                        f"{grant.principal!r}", request, grant)

    missing = sorted(set(request.operations) - set(grant.operations))
    if missing:
        return _blocked(REASON_OPERATION_NOT_GRANTED,
                        f"operations not granted: {missing}", request, grant)

    if grant.uses_consumed >= grant.max_uses:
        return _blocked(REASON_USES_EXHAUSTED,
                        f"{grant.uses_consumed}/{grant.max_uses} uses already consumed",
                        request, grant)

    if request.units > grant.max_units:
        return _blocked(REASON_BUDGET_EXCEEDED,
                        f"requested {request.units} units, grant allows {grant.max_units}",
                        request, grant)

    return Decision(
        state=STATE_AUTHORIZED,
        reason=REASON_AUTHORIZED,
        detail="one exact context matched an unexpired, unrevoked, unexhausted grant",
        request_id=request.request_id,
        grant_id=grant.grant_id,
        execution_authorized=True,
    )
