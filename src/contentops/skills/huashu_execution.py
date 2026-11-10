"""Managed execution for the pinned Huashu Motion engine. Default deny.

Why this module exists
-----------------------
The Huashu Motion adapter (:mod:`contentops.media.huashu_motion`) can describe
and verify an upstream operation, but describing an operation is not permission
to run it. The existing managed gate
(:mod:`contentops.skills.execution_gate`) already knows how to bind one
operation to one human approval; this module connects that gate to a *local*
engine instead of to a provider adapter, and adds the two things a local engine
needs and a provider does not:

* the runtime is verified **before** the approval is spent, so a missing
  checkout never burns one of the Owner's approved uses;
* the runtime is verified **again** inside the executor, so a checkout that
  disappeared between the two checks still refuses the attempt.

What it does not do
-------------------
- It does not construct a shell command. The upstream invocation is injected as
  a *runner*; this repository has no code that builds an ``om`` command line.
- It does not widen an approval. The grant's operation list, account, pipeline,
  stage, version and budget are checked by
  :func:`contentops.skills.authorization.evaluate` exactly as they are for
  every other capability.
- It does not claim execution authority anywhere. The resolution record this
  module builds carries ``execution_authorized: False``; the authorization
  module refuses a verdict that claims otherwise.

Order of checks
---------------
1. the runtime is verified against the committed pin;
2. the approval is loaded from the project's own approval record;
3. the request is evaluated against the pin and the approval;
4. the approval is re-read so a mid-flight revocation is visible;
5. exactly one use is spent;
6. the executor runs, and it verifies the runtime once more before it calls the
   injected runner;
7. a sanitized receipt records what happened.

See ADR-009 and ADR-010 for the authorization model and its stated limits.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional

from contentops.media import huashu_motion
from contentops.skills.authorization import (
    STATE_BLOCKED,
    Decision,
    ExecutionRequest,
)
from contentops.skills.execution_gate import GateResult, execute

__all__ = [
    "ALLOWED_OPERATIONS",
    "REASON_NO_RUNNER",
    "REASON_RUNTIME_NOT_TRUSTED",
    "SKILL_ID",
    "build_registry_entry",
    "build_request",
    "build_verdict",
    "execute_huashu",
    "make_executor",
]

#: The capability id the approval record must name.
SKILL_ID = huashu_motion.ENGINE_MOTION

#: The upstream operations a grant may name. ``check``, ``still`` and ``qa``
#: read or write project state; ``render`` produces media. All four are refused
#: until an approval names the exact one.
ALLOWED_OPERATIONS = tuple(sorted(huashu_motion.OPERATIONS))

REASON_RUNTIME_NOT_TRUSTED = "RUNTIME_NOT_TRUSTED"
REASON_NO_RUNNER = "NO_RUNNER_CONFIGURED"

#: A runner performs one upstream operation. It is injected so this module
#: never builds a command line and so the call contract can be tested offline
#: without a runtime, a browser or a render.
Runner = Callable[[str, ExecutionRequest], Mapping[str, Any]]


def _load_lock(lock: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    if isinstance(lock, Mapping):
        return dict(lock)
    try:
        return json.loads(huashu_motion.LOCK_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def build_registry_entry(lock: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    """Return the declaration an approval is checked against.

    The declaration comes from the committed pin, so the version an approval
    names is the version the runtime verifier will check. It is a pointer, not
    a permission.
    """
    payload = _load_lock(lock)
    identity = huashu_motion.engine_identity(SKILL_ID)
    version = str(payload.get("version") or identity["version"])
    return {
        "id": SKILL_ID,
        "name": SKILL_ID,
        "summary": "Pinned local motion-clip producer; a clip is not a composition.",
        "source": {
            "publisher": "alchaincyf",
            "upstream": identity["repository"],
            "version": version,
            "source_commit": identity["commit"],
            "baseline": identity["lock"],
        },
        "canonical_path": "src/contentops/media/huashu_motion.py",
        "role": identity["role"],
    }


def build_verdict(runtime: Mapping[str, Any]) -> Dict[str, Any]:
    """Return the resolution record for a verified runtime.

    ``RESOLVABLE`` means the pinned engine and its adapter were found. It never
    means the operation may run: ``execution_authorized`` stays false and the
    authorization module refuses a verdict that says otherwise.
    """
    trusted = isinstance(runtime, Mapping) and runtime.get("status") == "TRUSTED_RUNTIME"
    record = {
        "verdict": "RESOLVABLE" if trusted else "UNRESOLVED",
        "reason": "PINNED_RUNTIME_VERIFIED" if trusted else str(
            runtime.get("reason", "RUNTIME_UNVERIFIED") if isinstance(runtime, Mapping)
            else "RUNTIME_UNVERIFIED"),
        "skill_id": SKILL_ID,
        "execution_authorized": False,
        "capability_registration_is_not_authority": True,
    }
    if trusted:
        record["runtime_root"] = str(runtime.get("runtime_root", ""))
        record["version"] = runtime.get("version")
        record["commit"] = runtime.get("commit")
    return record


def build_request(*, request_id: str, operation: str, account: str,
                  pipeline: str, stage: str, subject: str,
                  version: Optional[str] = None,
                  lock: Optional[Mapping[str, Any]] = None) -> ExecutionRequest:
    """Build the one concrete request the gate may authorize."""
    entry = build_registry_entry(lock)
    return ExecutionRequest(
        request_id=request_id,
        skill_id=SKILL_ID,
        skill_version=str(version or entry["source"]["version"]),
        account=account,
        pipeline=pipeline,
        stage=stage,
        operations=(operation,),
        subject=subject,
    )


def _blocked(reason: str, detail: str, request: ExecutionRequest) -> GateResult:
    decision = Decision(state=STATE_BLOCKED, reason=reason, detail=detail,
                        request_id=request.request_id, grant_id=None,
                        execution_authorized=False)
    return GateResult(
        decision=decision,
        gate={"state": STATE_BLOCKED, "reason": reason, "detail": detail},
        execution={"state": "NOT_EXECUTED"},
    )


def make_executor(*, runtime_root: Path, runner: Optional[Runner],
                  lock: Optional[Mapping[str, Any]] = None,
                  git_probe: Optional[Callable[..., tuple[int, str]]] = None
                  ) -> Callable[[str, ExecutionRequest], Mapping[str, Any]]:
    """Build the executor the gate calls once an approval is spent.

    The executor refuses on its own terms even when the gate authorized the
    attempt: the runtime is verified again, and a missing runner is refused
    rather than replaced by a command this repository would have to invent.
    """

    def run(operation: str, request: ExecutionRequest) -> Mapping[str, Any]:
        if operation not in ALLOWED_OPERATIONS:
            return {"ok": False, "health": False,
                    "error": f"unsupported Huashu Motion operation {operation!r}"}
        runtime = huashu_motion.verify_runtime(
            Path(runtime_root), lock=_load_lock(lock), git_probe=git_probe)
        if runtime.get("status") != "TRUSTED_RUNTIME":
            return {"ok": False, "health": False,
                    "error": f"{REASON_RUNTIME_NOT_TRUSTED}: {runtime.get('reason')}",
                    "receipt": {
                        "schema": "contentops.huashu-motion-execution/v1",
                        "engine": SKILL_ID,
                        "operation": operation,
                        "status": "BLOCKED",
                        "execution_status": "NOT_EXECUTED",
                        "runtime_status": runtime.get("status"),
                        "runtime_reason": runtime.get("reason"),
                        "runner_invoked": False,
                        "execution_authorized": False,
                        "production_ready": False,
                        "human_review": "PENDING_FOUNDER_REVIEW",
                    }}
        if runner is None:
            return {"ok": False, "health": False,
                    "error": REASON_NO_RUNNER,
                    "receipt": {
                        "schema": "contentops.huashu-motion-execution/v1",
                        "engine": SKILL_ID,
                        "operation": operation,
                        "status": "BLOCKED",
                        "execution_status": "NOT_EXECUTED",
                        "runtime_status": runtime.get("status"),
                        "runner_invoked": False,
                        "execution_authorized": False,
                        "note": "no upstream invocation is configured; this "
                                "repository does not build an om command line",
                    }}
        outcome = runner(operation, request)
        payload = dict(outcome or {})
        payload.setdefault("ok", False)
        payload.setdefault("health", payload.get("ok"))
        return payload

    return run


def execute_huashu(request: ExecutionRequest, *,
                   project_dir: Path,
                   owner_identities: Iterable[str],
                   runtime_root: Optional[Path] = None,
                   runner: Optional[Runner] = None,
                   lock: Optional[Mapping[str, Any]] = None,
                   git_probe: Optional[Callable[..., tuple[int, str]]] = None,
                   now: Any = None,
                   write_receipt: bool = True) -> GateResult:
    """Authorize and, only if authorized, run exactly one Huashu operation.

    Returns a :class:`GateResult` on every path and never raises for a refusal.
    The runtime is checked first so an unusable checkout costs the Owner
    nothing.
    """
    try:
        if request.skill_id != SKILL_ID:
            return _blocked("UNKNOWN_SKILL",
                            f"this gate serves {SKILL_ID!r}, not {request.skill_id!r}",
                            request)
        if len(request.operations) != 1:
            return _blocked("OPERATIONS_MUST_BE_SINGLE",
                            "the managed gate runs exactly one operation", request)
        operation = request.operations[0]
        if operation not in ALLOWED_OPERATIONS:
            return _blocked("OPERATION_NOT_SUPPORTED",
                            f"{operation!r} is not one of {', '.join(ALLOWED_OPERATIONS)}",
                            request)
        root = Path(runtime_root) if runtime_root else huashu_motion.DEFAULT_RUNTIME
        runtime = huashu_motion.verify_runtime(
            root, lock=_load_lock(lock), git_probe=git_probe)
        if runtime.get("status") != "TRUSTED_RUNTIME":
            return _blocked(REASON_RUNTIME_NOT_TRUSTED,
                            f"the pinned runtime is not usable: {runtime.get('reason')}",
                            request)
        if runner is not None:
            preflight = getattr(runner, "preflight", None)
            if callable(preflight):
                try:
                    preflight(operation, request)
                except Exception as exc:  # noqa: BLE001 - fail closed before consuming use
                    return _blocked("RUNNER_PREFLIGHT_FAILED",
                                    f"{type(exc).__name__}: {exc}", request)
        if runner is None:
            return _blocked(REASON_NO_RUNNER,
                            "no upstream invocation is configured", request)
        return execute(
            request,
            verdict=build_verdict(runtime),
            registry_entry=build_registry_entry(lock),
            project_dir=Path(project_dir),
            owner_identities=owner_identities,
            executor=make_executor(runtime_root=root, runner=runner, lock=lock,
                                    git_probe=git_probe),
            now=now,
            write_receipt=write_receipt,
        )
    except Exception as exc:  # noqa: BLE001 - the gate reports, it does not raise
        return _blocked("EXECUTION_ERROR", f"{type(exc).__name__}: {exc}", request)
