"""Bind one skill execution to one explicit grant.

Why this module exists
----------------------
The skill router answers two questions: what exists (discovery) and which
declared capability may be handed to an adapter (resolution). Neither answers
"may *this subject* run *this operation* of *this pinned version* now?".
Treating `RESOLVABLE`, a licence declaration or a reachable provider as
permission is exactly the mistake this module exists to prevent.

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

Trusted source — what this module can and cannot prove
------------------------------------------------------
A pure function receives objects. It cannot prove where an object came from.
Two provenance defects are therefore made loud instead of silent:

* a verdict that contradicts itself by claiming ``execution_authorized: true``
  is refused (:data:`REASON_UNTRUSTED_VERDICT`);
* a grant with no ``provenance`` reference is refused
  (:data:`REASON_UNTRUSTED_GRANT`). Provenance is a digest of the approval
  record the grant was derived from, written by
  :mod:`contentops.skills.grant_source`.

What remains the gate's responsibility, and is **not** claimed here: verifying
that digest against a real approval record, and making grant consumption atomic
under concurrency. See ADR-009 and ADR-010.

Default deny
------------
Every path returns ``BLOCKED`` unless a grant is present, provable, unexpired,
unrevoked, unexhausted and bound to the exact request. A caller cannot widen a
grant by asking for a different account, stage, operation, version or budget.

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
    "REASON_CONTEXT_MISMATCH",
    "REASON_EMPTY_FIELD",
    "REASON_GRANT_EXPIRED",
    "REASON_GRANT_NOT_YET_VALID",
    "REASON_GRANT_REVOKED",
    "REASON_GRANT_WINDOW_INVALID",
    "REASON_INVALID_NUMBER",
    "REASON_NO_GRANT",
    "REASON_NOT_RESOLVABLE",
    "REASON_OPERATION_NOT_GRANTED",
    "REASON_SUBJECT_MISMATCH",
    "REASON_UNKNOWN_SKILL",
    "REASON_UNTRUSTED_GRANT",
    "REASON_UNTRUSTED_VERDICT",
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
REASON_UNTRUSTED_VERDICT = "UNTRUSTED_VERDICT"
REASON_VERSION_MISMATCH = "VERSION_MISMATCH"
REASON_NO_GRANT = "NO_GRANT"
REASON_UNTRUSTED_GRANT = "UNTRUSTED_GRANT"
REASON_GRANT_REVOKED = "GRANT_REVOKED"
REASON_GRANT_EXPIRED = "GRANT_EXPIRED"
REASON_GRANT_NOT_YET_VALID = "GRANT_NOT_YET_VALID"
REASON_GRANT_WINDOW_INVALID = "GRANT_WINDOW_INVALID"
REASON_CONTEXT_MISMATCH = "CONTEXT_MISMATCH"
REASON_OPERATION_NOT_GRANTED = "OPERATION_NOT_GRANTED"
REASON_SUBJECT_MISMATCH = "SUBJECT_MISMATCH"
REASON_BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
REASON_USES_EXHAUSTED = "USES_EXHAUSTED"
REASON_EMPTY_FIELD = "EMPTY_FIELD"
REASON_INVALID_NUMBER = "INVALID_NUMBER"


@dataclass(frozen=True)
class ExecutionRequest:
    """One concrete execution a subject asks for.

    Frozen because a request that can be edited after the fact cannot be bound
    to a grant. ``operations`` are the exact verbs being requested; an adapter
    may accept fewer, never more.

    ``subject`` is the actor performing the execution. It is deliberately a
    different field from the grant's ``issuer`` so a delegated run never
    collapses "who approved" into "who ran".
    """

    request_id: str
    skill_id: str
    skill_version: str
    account: str
    pipeline: str
    stage: str
    operations: Tuple[str, ...]
    subject: str
    units: int = 1


@dataclass(frozen=True)
class ExecutionGrant:
    """An approval bound to one exact context.

    ``issuer`` is the authorizing party; ``subject`` is the actor allowed to
    use it. ``provenance`` is the digest of the approval record this grant was
    derived from — it is what stops a grant from being invented in memory.
    """

    grant_id: str
    issuer: str
    subject: str
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
    provenance: str = ""


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
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _now(value: Any) -> Optional[datetime]:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return _parse(str(value))


def _is_count(value: Any) -> bool:
    """A real integer, not a bool (``True`` is an ``int`` in Python)."""
    return isinstance(value, int) and not isinstance(value, bool)


def _blank(*values: Any) -> bool:
    for value in values:
        if not isinstance(value, str) or not value.strip():
            return True
    return False


def _blocked(reason: str, detail: str, request: ExecutionRequest,
             grant: Optional[ExecutionGrant] = None) -> Decision:
    return Decision(
        state=STATE_BLOCKED,
        reason=reason,
        detail=detail,
        request_id=getattr(request, "request_id", "") or "",
        grant_id=grant.grant_id if grant else None,
        execution_authorized=False,
    )


def evaluate(request: ExecutionRequest, *,
             verdict: Optional[Mapping[str, Any]],
             registry_entry: Optional[Mapping[str, Any]],
             grant: Optional[ExecutionGrant] = None,
             now: Any = None) -> Decision:
    """Decide one execution request. Default deny.

    ``verdict`` is the router's resolution record and ``registry_entry`` is the
    declaration it was resolved against. Both are required: an omitted registry
    entry would silently skip the identity and version pins.
    """
    if _blank(request.request_id, request.skill_id, request.skill_version,
              request.account, request.pipeline, request.stage, request.subject):
        return _blocked(REASON_EMPTY_FIELD,
                        "request_id, skill, version, account, pipeline, stage and "
                        "subject must all be non-empty", request)
    if not request.operations or _blank(*request.operations):
        return _blocked(REASON_EMPTY_FIELD, "at least one non-empty operation is required",
                        request)
    if not _is_count(request.units) or request.units < 1:
        return _blocked(REASON_INVALID_NUMBER,
                        "units must be an integer of at least 1", request)

    if not isinstance(verdict, Mapping):
        return _blocked(REASON_NOT_RESOLVABLE, "no resolution record", request)
    if verdict.get("execution_authorized") is True:
        return _blocked(REASON_UNTRUSTED_VERDICT,
                        "the resolution record claims execution authority; a resolver "
                        "never grants it", request)
    if verdict.get("verdict") != STATE_RESOLVABLE:
        reason = verdict.get("reason") or "no resolution record"
        return _blocked(REASON_NOT_RESOLVABLE,
                        f"the router did not resolve this skill: {reason}", request)

    if not isinstance(registry_entry, Mapping) or not registry_entry:
        return _blocked(REASON_UNKNOWN_SKILL,
                        "no registry entry was supplied for the resolved capability",
                        request)
    declared_id = registry_entry.get("id") or registry_entry.get("name")
    if declared_id != request.skill_id:
        return _blocked(REASON_UNKNOWN_SKILL,
                        f"requested {request.skill_id!r}, declared {declared_id!r}",
                        request)
    declared_version = (registry_entry.get("source") or {}).get("version")
    if not declared_version:
        return _blocked(REASON_VERSION_MISMATCH,
                        "the declaration pins no version", request)
    if declared_version != request.skill_version:
        return _blocked(REASON_VERSION_MISMATCH,
                        f"requested version {request.skill_version!r}, "
                        f"declared {declared_version!r}", request)

    if grant is None:
        return _blocked(REASON_NO_GRANT,
                        "resolution is a pointer, not an execution authorization", request)

    if _blank(grant.grant_id, grant.issuer, grant.subject, grant.provenance):
        if _blank(grant.provenance):
            return _blocked(REASON_UNTRUSTED_GRANT,
                            "the grant carries no provenance digest", request, grant)
        return _blocked(REASON_EMPTY_FIELD,
                        "grant_id, issuer and subject must be non-empty", request, grant)
    if not (_is_count(grant.max_units) and _is_count(grant.max_uses)
            and _is_count(grant.uses_consumed)):
        return _blocked(REASON_INVALID_NUMBER,
                        "max_units, max_uses and uses_consumed must be integers",
                        request, grant)
    if grant.max_units < 1 or grant.max_uses < 1 or grant.uses_consumed < 0:
        return _blocked(REASON_INVALID_NUMBER,
                        "max_units and max_uses must be at least 1; uses_consumed "
                        "cannot be negative", request, grant)

    if grant.revoked:
        detail = "the grant was revoked"
        if grant.revoked_reason:
            detail = f"the grant was revoked: {grant.revoked_reason}"
        return _blocked(REASON_GRANT_REVOKED, detail, request, grant)

    moment = _now(now)
    if moment is None:
        return _blocked(REASON_GRANT_NOT_YET_VALID,
                        "the evaluation time is not a usable timestamp", request, grant)
    issued = _parse(grant.issued_at)
    expires = _parse(grant.expires_at)
    if issued is None or expires is None:
        return _blocked(REASON_GRANT_NOT_YET_VALID,
                        "the grant has no usable issued_at/expires_at", request, grant)
    if issued >= expires:
        return _blocked(REASON_GRANT_WINDOW_INVALID,
                        "issued_at must be earlier than expires_at", request, grant)
    if moment < issued:
        return _blocked(REASON_GRANT_NOT_YET_VALID,
                        "the grant is not valid yet", request, grant)
    if moment >= expires:
        return _blocked(REASON_GRANT_EXPIRED, "the grant has expired", request, grant)

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
                            f"{field} does not match the grant", request, grant)

    if request.subject != grant.subject:
        return _blocked(REASON_SUBJECT_MISMATCH,
                        "the executing subject is not the party the grant names",
                        request, grant)

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
        detail="one exact context matched a provable, unexpired, unrevoked, "
               "unexhausted grant",
        request_id=request.request_id,
        grant_id=grant.grant_id,
        execution_authorized=True,
    )
