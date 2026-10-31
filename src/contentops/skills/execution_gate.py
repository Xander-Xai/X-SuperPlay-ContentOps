"""The managed execution gate: Router -> Authorization -> Existing adapter.

Why a gate and not a bigger module
----------------------------------
The decision is pure (:mod:`~contentops.skills.authorization`). The trusted
source is read-only (:mod:`~contentops.skills.grant_source`). What is left is
orchestration that must happen in one order and produce one receipt:

1. the router has already resolved the capability;
2. a grant is loaded from a human-approved record;
3. the decision is evaluated;
4. exactly one use is consumed atomically;
5. the existing adapter runs, with its own gates untouched;
6. a receipt records what happened.

Nothing here re-implements a provider gate. The adapter still verifies the
runtime lock, refuses network and paid paths, and the M5 stage still applies
``rights_reviewed``. A grant authorizes *the attempt*; it never replaces an
existing check.

Legacy independence
-------------------
``scripts/m5_production.py`` does not import this module. The verified M5 chain
keeps its existing trust boundary; this gate is an additional, opt-in entry
point.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional

from contentops.skills.authorization import (
    STATE_BLOCKED,
    STATE_EXECUTED,
    Decision,
    ExecutionRequest,
    evaluate,
)
from contentops.skills.grant_source import GrantSourceError, consume, load_grant

__all__ = ["GATE_SCHEMA", "GateResult", "execute"]

GATE_SCHEMA = "contentops.skill-execution/v1"
EXECUTION_RELPATH = Path("receipts") / "executions"

#: An executor takes the operation name and the request, and returns a mapping
#: with ``ok`` and, optionally, ``receipt``. It is injected so the gate stays
#: testable without a runtime, and so the adapter remains the thing that runs.
Executor = Callable[[str, ExecutionRequest], Mapping[str, Any]]


def _iso_now(value: Any) -> str:
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    elif value is None:
        moment = datetime.now(timezone.utc)
    else:
        try:
            moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            moment = datetime.now(timezone.utc)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
    return moment.isoformat()


@dataclass(frozen=True)
class GateResult:
    """Decision plus what actually happened, if anything."""

    decision: Decision
    gate: Dict[str, Any]
    execution: Dict[str, Any]
    receipt_path: Optional[str] = None

    @property
    def executed(self) -> bool:
        return self.execution.get("state") == STATE_EXECUTED

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": GATE_SCHEMA,
            "decision": self.decision.as_dict(),
            "gate": self.gate,
            "execution": self.execution,
            "receipt": self.receipt_path,
        }


def _blocked_gate(reason: str, detail: str) -> Dict[str, Any]:
    return {"state": STATE_BLOCKED, "reason": reason, "detail": detail}


def execute(request: ExecutionRequest, *,
            verdict: Optional[Mapping[str, Any]],
            registry_entry: Optional[Mapping[str, Any]],
            project_dir: Path,
            owner_identities: Iterable[str],
            executor: Executor,
            now: Any = None,
            write_receipt: bool = True) -> GateResult:
    """Authorize and, only if authorized, run one operation.

    Returns a :class:`GateResult` on every path; it never raises for a refusal.
    """
    moment = _iso_now(now)
    project = Path(project_dir)

    try:
        grant = load_grant(project, owner_identities=owner_identities)
    except GrantSourceError as exc:
        decision = Decision(
            state=STATE_BLOCKED,
            reason="NO_TRUSTED_GRANT",
            detail=f"{exc.code}: {exc.detail}",
            request_id=request.request_id,
        )
        return GateResult(decision=decision,
                          gate=_blocked_gate(exc.code, exc.detail),
                          execution={"state": "NOT_EXECUTED"})

    decision = evaluate(request, verdict=verdict, registry_entry=registry_entry,
                        grant=grant, now=moment)
    if decision.state == STATE_BLOCKED:
        return GateResult(decision=decision,
                          gate=_blocked_gate(decision.reason, decision.detail),
                          execution={"state": "NOT_EXECUTED"})

    try:
        spent = consume(project, grant=grant, request_id=request.request_id, now=moment)
    except GrantSourceError as exc:
        decision = Decision(
            state=STATE_BLOCKED,
            reason=exc.code,
            detail=exc.detail,
            request_id=request.request_id,
            grant_id=grant.grant_id,
        )
        return GateResult(decision=decision,
                          gate=_blocked_gate(exc.code, exc.detail),
                          execution={"state": "NOT_EXECUTED"})

    gate = {
        "state": "AUTHORIZED",
        "reason": "AUTHORIZED",
        "detail": decision.detail,
        "use": spent["use"],
        "approval_digest": grant.provenance,
    }

    try:
        outcome = executor(request.operations[0], request)
        execution = {
            "state": STATE_EXECUTED if outcome.get("ok") else "FAILED",
            "operation": request.operations[0],
            "adapter_receipt": outcome.get("receipt"),
            "error": outcome.get("error"),
        }
    except Exception as exc:  # the adapter refused; the use is still spent
        execution = {
            "state": "FAILED",
            "operation": request.operations[0],
            "adapter_receipt": None,
            "error": f"{type(exc).__name__}: {exc}",
        }

    receipt_path = None
    if write_receipt:
        directory = project / EXECUTION_RELPATH
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{grant.grant_id}-use-{spent['use']:04d}.json"
        payload = {
            "schema": GATE_SCHEMA,
            "request_id": request.request_id,
            "grant_id": grant.grant_id,
            "issuer": grant.issuer,
            "subject": grant.subject,
            "skill": {"id": request.skill_id, "version": request.skill_version},
            "scope": {"account": request.account, "pipeline": request.pipeline,
                      "stage": request.stage, "operations": list(request.operations)},
            "decision": decision.as_dict(),
            "execution": execution,
            "consumed_at": spent["consumed_at"],
        }
        target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8")
        receipt_path = target.as_posix()

    return GateResult(decision=decision, gate=gate, execution=execution,
                      receipt_path=receipt_path)
