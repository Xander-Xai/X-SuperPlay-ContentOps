"""The managed execution gate: Router -> Authorization -> Existing adapter.

Why a gate and not a bigger module
----------------------------------
The decision is pure (:mod:`~contentops.skills.authorization`). The trusted
source is read-only (:mod:`~contentops.skills.grant_source`). What is left is
orchestration that must happen in one order and produce one receipt:

1. the router has already resolved the capability;
2. an approval is loaded from a human-written record;
3. the decision is evaluated;
4. the approval is re-read so a revocation mid-flight is visible;
5. exactly one use is consumed atomically;
6. the existing adapter runs, with its own gates untouched;
7. a sanitized receipt records what happened.

Nothing here re-implements a provider gate. The adapter still verifies the
runtime lock, refuses network and paid paths, and the M5 stage still applies
``rights_reviewed``. A grant authorizes *the attempt*; it never replaces an
existing check.

Exactly one operation
---------------------
The gate runs ``operations[0]``. To make that honest it refuses a request with
any other number of operations rather than silently ignoring the rest. Batch
execution needs its own atomicity and budget semantics.

Legacy independence
-------------------
``scripts/m5_production.py`` does not import this module. The verified M5 chain
keeps its existing trust boundary; this gate is an additional, opt-in entry.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional

from contentops.skills.authorization import (
    STATE_AUTHORIZED,
    STATE_BLOCKED,
    STATE_EXECUTED,
    Decision,
    ExecutionRequest,
    evaluate,
)
from contentops.skills.grant_source import (
    GrantSourceError,
    consume,
    load_grant,
)

__all__ = ["GATE_SCHEMA", "GateResult", "execute", "sanitize_text"]

GATE_SCHEMA = "contentops.skill-execution/v1"
EXECUTION_RELPATH = Path("receipts") / "executions"

#: An executor takes the operation name and the request, and returns a mapping
#: with ``ok`` and, optionally, ``receipt``. It is injected so the gate stays
#: testable without a runtime, and so the adapter remains the thing that runs.
Executor = Callable[[str, ExecutionRequest], Mapping[str, Any]]

_SECRET_PATTERNS = (
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{4,}"), r"\1<redacted>"),
    (re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|token|secret|"
                r"password)\b\s*[:=]\s*\S+"), r"\1=<redacted>"),
    (re.compile(r"\b(?:sk|pk|ghp|gho|ghs|github_pat)[-_][A-Za-z0-9_\-]{6,}"), "<redacted>"),
)
_PATH_PATTERNS = (
    (re.compile(r"[A-Za-z]:[\\/][^\s\"'<>|]+"), "<path>"),
    (re.compile(r"/(?:home|Users|root|tmp|var|opt|mnt|srv)/[^\s\"'<>|]*"), "<path>"),
)


def sanitize_text(value: str) -> str:
    """Remove credentials and host paths from anything written to disk.

    Receipts are committed to a public repository, so the adapter's error text
    and its own receipt values pass through here first.
    """
    text = str(value)
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    for pattern, replacement in _PATH_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, Mapping):
        return {sanitize_text(str(key)): _sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    return value


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
    return {"state": STATE_BLOCKED, "reason": reason, "detail": sanitize_text(detail)}


def _blocked(request: ExecutionRequest, reason: str, detail: str,
             grant_id: Optional[str] = None) -> GateResult:
    decision = Decision(state=STATE_BLOCKED, reason=reason, detail=detail,
                        request_id=request.request_id, grant_id=grant_id)
    return GateResult(decision=decision, gate=_blocked_gate(reason, detail),
                      execution={"state": "NOT_EXECUTED"})


def execute(request: ExecutionRequest, *,
            verdict: Optional[Mapping[str, Any]],
            registry_entry: Optional[Mapping[str, Any]],
            project_dir: Path,
            owner_identities: Iterable[str],
            executor: Executor,
            now: Any = None,
            write_receipt: bool = True) -> GateResult:
    """Authorize and, only if authorized, run exactly one operation.

    Returns a :class:`GateResult` on every path; it never raises for a refusal
    or for a filesystem failure.
    """
    moment = _iso_now(now)
    project = Path(project_dir)

    if len(request.operations) != 1:
        return _blocked(request, "OPERATIONS_MUST_BE_SINGLE",
                        "the managed gate runs exactly one operation: a batch needs "
                        "its own atomicity and budget semantics")

    try:
        grant = load_grant(project, owner_identities=owner_identities)
    except GrantSourceError as exc:
        return _blocked(request, "NO_TRUSTED_GRANT", f"{exc.code}: {exc.detail}")

    decision = evaluate(request, verdict=verdict, registry_entry=registry_entry,
                        grant=grant, now=moment)
    if decision.state == STATE_BLOCKED:
        return GateResult(decision=decision,
                          gate=_blocked_gate(decision.reason, decision.detail),
                          execution={"state": "NOT_EXECUTED"})

    # Re-read immediately before spending: a revocation written while the
    # request was being evaluated must not be spendable.
    try:
        fresh = load_grant(project, owner_identities=owner_identities)
    except GrantSourceError as exc:
        return _blocked(request, "GRANT_CHANGED", f"{exc.code}: {exc.detail}",
                        grant.grant_id)
    if fresh.provenance != grant.provenance:
        return _blocked(request, "GRANT_CHANGED",
                        "the approval record changed after it was evaluated",
                        grant.grant_id)
    if fresh.revoked:
        return _blocked(request, "GRANT_REVOKED", "the grant was revoked", grant.grant_id)

    try:
        spent = consume(project, grant=grant, request_id=request.request_id, now=moment)
    except GrantSourceError as exc:
        return _blocked(request, exc.code, exc.detail, grant.grant_id)

    gate = {
        "state": STATE_AUTHORIZED,
        "reason": "AUTHORIZED",
        "detail": sanitize_text(decision.detail),
        "use": spent["use"],
        "approval_digest": grant.provenance,
    }

    try:
        outcome = executor(request.operations[0], request)
        execution = {
            "state": STATE_EXECUTED if outcome.get("ok") else "FAILED",
            "operation": request.operations[0],
            # ``state`` records whether the operation resolved; ``health`` is the
            # adapter's own verdict and can be false on a successful diagnosis.
            "health": outcome.get("health"),
            "adapter_receipt": outcome.get("receipt"),
            "error": outcome.get("error"),
        }
    except Exception as exc:  # the adapter refused; the use is still spent
        execution = {
            "state": "FAILED",
            "operation": request.operations[0],
            "health": None,
            "adapter_receipt": None,
            "error": f"{type(exc).__name__}: {exc}",
        }

    receipt_path = None
    receipt_error = None
    if write_receipt:
        directory = project / EXECUTION_RELPATH
        try:
            directory.mkdir(parents=True, exist_ok=True)
            checked = directory.resolve(strict=False)
            if checked != project.resolve() and not checked.is_relative_to(project.resolve()):
                raise OSError("the execution directory resolves outside the project")
            target = directory / f"{grant.grant_id}-use-{spent['use']:04d}.json"
            payload = _sanitize({
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
            })
            # Exclusive create: an existing receipt is never overwritten.
            try:
                handle = open(target, "x", encoding="utf-8")
            except FileExistsError:
                raise OSError("an execution receipt already exists for this use")
            with handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
            receipt_path = target.as_posix()
        except OSError as exc:
            receipt_error = sanitize_text(str(exc))
            # The execution already happened; reporting a missing receipt is
            # honest, reporting success without one is not.
            execution["receipt_write_failed"] = True
            execution["receipt_error"] = receipt_error

    return GateResult(decision=decision, gate=gate, execution=execution,
                      receipt_path=receipt_path)
