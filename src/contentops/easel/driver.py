"""Drive the ContentOps pipeline from a coding agent instead of a web host.

A coding agent (Claude Code, Codex CLI, OpenCode) is already the runtime this
repository is developed in. This module makes that runtime a first-class driver:
the agent asks for a plan, runs one allowlisted step at a time, and reads a
receipt. It does not need FastAPI, uvicorn, a browser or the upstream workbench.

What this does **not** do is grant authority. The driver has no publish command,
no credential route, no install step and no approval step. Human-only steps are
listed so the plan is complete, and refused when a driver tries to run them. The
agent executes a fixed argv list; it never supplies a command string.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DRIVER_SCHEMA = "contentops.agent-driver/v1"
HOST_BINARIES = ("claude", "codex", "opencode")

AUTHORITY_READ = "READ"
AUTHORITY_PRODUCE = "PRODUCE"
AUTHORITY_HUMAN = "HUMAN_ONLY"

#: Tokens that must never appear in a driver step. A future step that tries to
#: smuggle one in fails at construction rather than at run time.
FORBIDDEN_TOKENS = (
    "publish", "login", "logout", "credential", "credentials", "secret",
    "token", "password", "install", "upgrade", "serve",
)


class DriverError(ValueError):
    """The driver cannot build or run a step, with a stable reason code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Step:
    id: str
    label: str
    argv: Tuple[str, ...]
    receipts: Tuple[str, ...]
    authority: str
    requires: Tuple[str, ...] = ()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def detect_hosts() -> Dict[str, bool]:
    """Which coding-agent hosts exist on PATH. Names only; no paths are recorded."""
    return {name: shutil.which(name) is not None for name in HOST_BINARIES}


def _assert_allowed(step: Step) -> None:
    joined = " ".join(step.argv).lower()
    for token in FORBIDDEN_TOKENS:
        if token in joined:
            raise DriverError(
                "STEP_NOT_ALLOWED",
                f"{step.id} contains {token!r}; the driver has no such authority")


def _steps(project: str, fmt: str) -> List[Step]:
    steps = [Step(
        id="host-status",
        label="Report the guarded host state",
        argv=("python", "scripts/easel_host.py", "status"),
        receipts=(),
        authority=AUTHORITY_READ,
    )]
    if fmt == "VIDEO":
        steps += [
            Step(
                id="produce-video",
                label="Run the evidence-first M5 chain",
                argv=("python", "scripts/m5_production.py", project),
                receipts=("receipts/m5-run.json",
                          "receipts/bundle-handoff-video.json"),
                authority=AUTHORITY_PRODUCE,
                requires=("host-status",),
            ),
            Step(
                id="qc-video",
                label="Run QC on the rendered video",
                argv=("python", "scripts/qc_video.py", project),
                receipts=("receipts/qc-report.json",),
                authority=AUTHORITY_READ,
                requires=("produce-video",),
            ),
        ]
    elif fmt == "GRAPHIC_TEXT":
        steps += [
            Step(
                id="produce-graphic",
                label="Build the manual graphic package",
                argv=("python", "scripts/graphic_package.py",
                      "--project", project,
                      "--handoff", f"{project}/receipts/bundle-handoff-graphic_text.json",
                      "--input", f"{project}/graphic-input.json"),
                receipts=("receipts/graphic-package.json",),
                authority=AUTHORITY_PRODUCE,
                requires=("host-status",),
            ),
        ]
    else:
        raise DriverError("FORMAT_UNKNOWN", f"{fmt!r} is not VIDEO or GRAPHIC_TEXT")

    steps.append(Step(
        id="human-review",
        label="A named person reviews and signs the artifact",
        argv=(),
        receipts=(),
        authority=AUTHORITY_HUMAN,
        requires=(steps[-1].id,),
    ))
    return steps


def _receipt_path(root: Path, project_rel: str, receipt: str) -> Path:
    """A step receipt lives under the *project* directory, not the repo root.

    ``_steps`` records repo-style paths such as ``receipts/m5-run.json``; every
    real receipt is written under ``<repo>/<project>/receipts/``. Resolving the
    receipt against the repo root made ``ready`` permanently false for every
    step and produced wrong plan states.
    """
    return Path(root).resolve() / project_rel / receipt


def _receipt_is_valid(path: Path) -> bool:
    """A receipt file must say `status: OK` to count as evidence of completion.

    Merely existing is not completion: a failed step also writes its receipt.
    The schema stability of the receipt fields is the driver's own, so the
    load is trusted to be JSON here; a corrupt file reads as incomplete.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    return data.get("status") == "OK" \
        and data.get("executed") is True \
        and data.get("production_ready") is False


def _requirements_met(plan: Dict[str, Any], step: Dict[str, Any], *,
                      root: Path) -> Tuple[bool, str]:
    """A step may only run after every step it requires has completed.

    Completion is judged by that predecessor's *own driver receipt* being a
    recorded OK, not by its step output, and never by the presence of this
    step's own receipts. The receipt lives under the predecessor's project.
    """
    if not step.get("requires"):
        return True, ""
    project_rel = plan["project"]
    for required_id in step["requires"]:
        required = next((item for item in plan["steps"] if item["id"] == required_id), None)
        if required is None:
            return False, f"required step {required_id!r} is not in the plan"
        if required["authority"] == AUTHORITY_HUMAN:
            return False, f"required step {required_id!r} is human-only"
        receipt_rel = f"receipts/agent-driver-{required_id}.json"
        receipt = _receipt_path(root, project_rel, receipt_rel)
        if not _receipt_is_valid(receipt):
            return False, f"required step {required_id!r} has no validated OK receipt"
    return True, ""


def detect_format(project: Path) -> str:
    if (project / "project.yaml").is_file():
        return "VIDEO"
    if (project / "graphic-input.json").is_file():
        return "GRAPHIC_TEXT"
    raise DriverError("PROJECT_FORMAT_UNKNOWN",
                      f"{project.name} has neither project.yaml nor graphic-input.json")


def _resolve_project(project: Path, root: Path) -> Tuple[Path, str]:
    root = Path(root).resolve()
    candidate = Path(project)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    if not candidate.is_dir():
        raise DriverError("PROJECT_MISSING", candidate.as_posix())
    if root not in candidate.parents:
        raise DriverError("PROJECT_OUTSIDE_REPO",
                          "a driver step may only run inside the repository")
    return candidate, candidate.relative_to(root).as_posix()


def build_plan(project: Path, root: Path) -> Dict[str, Any]:
    """An ordered, read-only description of what a coding agent may run."""
    resolved, relative = _resolve_project(Path(project), Path(root))
    fmt = detect_format(resolved)
    steps = _steps(relative, fmt)

    described = []
    for step in steps:
        _assert_allowed(step)
        if step.authority == AUTHORITY_HUMAN:
            runnable, ready = False, False
        else:
            runnable = True
            # A step's own receipts describe whether its *work* already
            # exists. They live under the project, not the repo root.
            ready = all(_receipt_path(Path(root), relative, receipt).is_file()
                        for receipt in step.receipts) if step.receipts else True
        described.append({
            "id": step.id,
            "label": step.label,
            "argv": list(step.argv),
            "receipts": list(step.receipts),
            "authority": step.authority,
            "requires": list(step.requires),
            "runnable": runnable,
            "ready": ready,
        })

    return {
        "schema": DRIVER_SCHEMA,
        "project": relative,
        "format": fmt,
        "agent_hosts": detect_hosts(),
        "steps": described,
        "production_ready": False,
        "human_review": "NOT_STARTED",
        "publish_authorized": False,
        "note": "A plan is not an execution, an approval or a publication.",
    }


def _runner():
    try:
        from process_utils import hidden_run
    except ImportError:
        raise DriverError("PROCESS_UTILS_MISSING",
                          "scripts/ must be on sys.path to execute a step") from None
    return hidden_run


def _tail(value: str, limit: int = 4000) -> str:
    text = (value or "").strip()
    return text[-limit:]


def _scrub(value: str, root: Path) -> str:
    """Keep host paths out of a receipt; a receipt is portable or it is not one."""
    text = value or ""
    for form in {str(Path(root).resolve()), Path(root).resolve().as_posix()}:
        if form:
            text = re.sub(re.escape(form), "<repo>", text, flags=re.IGNORECASE)
    return _tail(text)


def run_step(project: Path, step_id: str, *, root: Path,
             execute: bool = False, timeout: int = 1800) -> Dict[str, Any]:
    """Run one allowlisted step. Without ``execute`` this only resolves argv."""
    plan = build_plan(project, root)
    step = next((item for item in plan["steps"] if item["id"] == step_id), None)
    if step is None:
        raise DriverError("STEP_UNKNOWN", f"{step_id!r} is not in the plan")
    if not step["runnable"]:
        raise DriverError("HUMAN_REQUIRED",
                          f"{step_id} is a human decision; a driver cannot perform it")
    root_resolved = Path(root).resolve()
    met, reason = _requirements_met(plan, step, root=root_resolved)
    if not met and execute:
        raise DriverError("PREREQUISITE_MISSING", reason)
    if not execute:
        return {"executed": False, "step": step["id"], "argv": step["argv"],
                "cwd": plan["project"]}

    hidden_run = _runner()
    started = _now()
    proc = hidden_run(list(step["argv"]), cwd=str(Path(root).resolve()), timeout=timeout)
    finished = _now()
    receipt = {
        "schema": "contentops.agent-driver-receipt/v1",
        "step": step["id"],
        "project": plan["project"],
        "argv": step["argv"],
        "cwd": ".",
        "executed": True,
        "returncode": proc.returncode,
        "status": "OK" if proc.returncode == 0 else "FAILED",
        "started_at": started,
        "finished_at": finished,
        "stdout_tail": _scrub(proc.stdout, Path(root)),
        "stderr_tail": _scrub(proc.stderr, Path(root)),
        "production_ready": False,
        "publish_authorized": False,
    }
    target = Path(root).resolve() / plan["project"] / "receipts" / f"agent-driver-{step['id']}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    receipt["receipt"] = target.relative_to(Path(root).resolve()).as_posix()
    return receipt


def next_step(plan: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The first runnable step whose receipts are still missing.

    A step with no receipts is a read (a status probe); it does not gate the
    loop, so an agent may run it whenever it wants without stalling progress.
    """
    for step in plan.get("steps", []):
        if not step.get("runnable"):
            continue
        if not step.get("ready"):
            return step
    return None
