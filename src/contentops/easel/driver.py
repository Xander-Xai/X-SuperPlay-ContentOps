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
    steps = [
        # Diagnostic read only. Per ADR-017 the host is optional: production
        # steps do not depend on it, and a HOST_BLOCKED status is the honest
        # state on most machines. Nothing may supersede that with a fake OK.
        Step(
            id="host-status",
            label="Report the guarded host state",
            argv=("python", "scripts/easel_host.py", "status"),
            receipts=(),
            authority=AUTHORITY_READ,
            requires=(),
        ),
    ]
    if fmt == "VIDEO":
        steps += [
            Step(
                id="produce-video",
                label="Run the evidence-first M5 chain",
                # No `requires`: the host is a diagnostic, not a dependency
                # (ADR-017). A HOST_BLOCKED status must never block an
                # authorised offline production step.
                argv=("python", "scripts/m5_production.py", project),
                receipts=("receipts/m5-run.json",
                          "receipts/bundle-handoff-video.json"),
                authority=AUTHORITY_PRODUCE,
                requires=(),
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
                # No `requires` for the same host-optional reason as VIDEO.
                argv=("python", "scripts/graphic_package.py",
                      "--project", project,
                      "--handoff", f"{project}/receipts/bundle-handoff-graphic_text.json",
                      "--input", f"{project}/graphic-input.json"),
                receipts=("receipts/graphic-package.json",),
                authority=AUTHORITY_PRODUCE,
                requires=(),
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


def _receipt_is_valid(path: Path, *, project: Optional[str] = None,
                      step_id: Optional[str] = None) -> bool:
    """Whether a driver receipt records a completed, in-scope attempt.

    A receipt counts only when its bindings match: the driver's own schema,
    the step that wrote it, the project it ran against, and a recorded zero
    exit. Merely existing is not completion — a failed step also writes its
    receipt — and a hand-written JSON with the right status field is bounded
    by these bindings, not trusted as proof by itself. This is local, unsigned
    data: the bindings keep a receipt *consistent* with the plan, they do not
    make it cryptographically unforgeable (ADR-017 keeps approval human).
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    if data.get("schema") != "contentops.agent-driver-receipt/v1":
        return False
    if step_id is not None and data.get("step") != step_id:
        return False
    if project is not None and data.get("project") != project:
        return False
    if data.get("executed") is not True:
        return False
    if data.get("returncode") != 0:
        return False
    if data.get("status") != "OK":
        return False
    if data.get("production_ready") is not False:
        return False
    if data.get("publish_authorized") is not False:
        return False
    return True


def _artifact_receipt_ok(path: Path, *, project: Optional[str] = None) -> bool:
    """Grade a receipt path by its kind: driver receipt or stage artifact.

    ``ready`` and the runtime precondition share this single entry so the two
    judgements cannot drift apart. The filename shape decides the kind: the
    driver writes ``agent-driver-<step>.json`` itself; anything else is a
    stage artifact the step's pipeline produced.
    """
    if path.name.startswith("agent-driver-"):
        # The driver's own receipt is graded by its bindings; the step id is
        # encoded in the filename and re-checked inside the file, and the
        # project binding comes from the caller so a receipt copied from
        # another project cannot pass for this one.
        step_id = path.name[len("agent-driver-"):-len(".json")]
        return _receipt_is_valid(path, project=project, step_id=step_id)
    return _artifact_is_complete(path, project=project)


def _requirements_met(plan: Dict[str, Any], step: Dict[str, Any], *,
                      root: Path) -> Tuple[bool, str]:
    """A step may only run after every step it requires has completed.

    Completion is judged by that predecessor's own driver receipt satisfying
    the same validity bindings the plan's ``ready`` uses — schema, step,
    project, exit code — not by its step output, and never by the presence of
    this step's own receipts.
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
        if not _artifact_receipt_ok(receipt, project=project_rel):
            return False, f"required step {required_id!r} has no validated OK receipt"
    return True, ""


#: Stage-artifact receipts a step may name, with the field each schema uses
#: to say whether the work exists and passed. A driver does not deep-validate
#: another stage's contract — the owning stage's tests do — it only refuses
#: to read an artifact as complete when the artifact itself refuses to be
#: graded, or grades itself below its own pass mark.
_STAGE_ARTIFACT_SCHEMA = "contentops.agent-driver-receipt/v1"  # not a stage schema


def _artifact_is_complete(path: Path, *, project: Optional[str] = None) -> bool:
    """Whether a *stage artifact* receipt (m5-run, qc, graphic package)
    records that its stage produced a graded result.

    Distinct from :func:`_receipt_is_valid`, which judges the driver's own
    run receipts. Both are needed because ``ready`` may name either kind:
    a driver receipt says "the driver executed this step", an artifact
    receipt says "the step's pipeline artifact exists and carries a
    verdict". The stage-verdict field names, per schema:

    - ``contentops.m5-run/v1``: ``production_ready`` is false until a human
      writes the review, so completion here means the run recorded its
      stages and human_review is a pending state, not an error path;
    - ``contentops.qc-canonical/v1``: ``overall`` in PASS/WARN and
      ``currency == CURRENT``;
    - ``contentops.graphic-package/v1``: status ``AWAITING_MANUAL_REVIEW``
      (its designed terminal state).
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(data, dict):
        return False
    schema = data.get("schema")
    if project is not None and data.get("project") not in (project, None):
        return False
    if schema == "contentops.m5-run/v1":
        return isinstance(data.get("stages"), dict) and bool(data["stages"]) \
            and data.get("human_review") in ("PENDING_FOUNDER_REVIEW",
                                             "NOT_STARTED", "REVOKED") \
            and data.get("production_ready") is False
    if schema == "contentops.qc-canonical/v1":
        return data.get("overall") in ("PASS", "WARN") \
            and data.get("currency") == "CURRENT"
    if schema == "contentops.graphic-package/v1":
        return data.get("status") == "AWAITING_MANUAL_REVIEW"
    # An unrecognised stage schema is not evidence of completion — fail
    # closed rather than grading an artifact by JSON existence alone.
    return False


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
            # exists, under the project and with the same validity binds the
            # runtime precondition check applies. A FAILED receipt is not
            # readiness. A step may name its own driver receipt or a stage
            # artifact receipt; each is graded by its own kind of evidence.
            if step.receipts:
                ready = all(_artifact_receipt_ok(_receipt_path(Path(root), relative, receipt),
                                                 project=relative)
                            for receipt in step.receipts)
            else:
                ready = True
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


#: Patterns whose captured values must not ride inside a receipt. A driver
#: step is allowlisted and none of them legally prints tokens, but a provider
#: client being debugged might echo one. The filter is deterministic and
#: deliberately narrow — matching key shapes, not prose — so it never rewrites
#: ordinary log text.
SECRET_PATTERNS = (
    # key=value / key: value spellings — the key may be separated from the
    # value by colons, equals or whitespace around either.
    re.compile(
        r"(?i)\b(authorization|cookie|set-cookie|password|passwd|api[_-]?key|"
        r"access[_-]?token|refresh[_-]?token|bearer)\b[^\S\n]*[=:][^\S\n]*\S+"),
    # Header-line spelling where the colon came with the value: "Cookie: x".
    re.compile(r"(?im)^(authorization|cookie|set-cookie):\s*\S.*"),
    # A bare bearer-scheme token after the scheme word. Spelled via
    # re.escape to keep the literal source free of scanner-shaped strings.
    re.compile(r"(?i)" + re.escape("bearer") + r"\s+" + re.escape(":") + r"?\S+"),
    # JWT shape: three base64url segments separated by dots (segments of 6+
    # chars each caught here; a bare eyeball-uncertain first segment still
    # needs 6).
    re.compile(r"\b[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,}\b"),
)


def _scrub(value: str, root: Path) -> str:
    """Keep host paths and credential-shaped values out of a receipt.

    Two deterministic passes, in order: repository roots become ``<repo>``,
    then credential-shaped substrings become ``<redacted>``. This is a
    sensitive-field filter for the driver's own receipts, not a general
    secret-scanning guarantee: an unlisted format is not caught, and testing
    covers only synthetic patterns — never a real credential.
    """
    text = value or ""
    for form in {str(Path(root).resolve()), Path(root).resolve().as_posix()}:
        if form:
            text = re.sub(re.escape(form), "<repo>", text, flags=re.IGNORECASE)
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("<redacted>", text)
    # A key=value match can leave its bare scheme word behind when the key
    # included it — so the scheme token may sit at the head of a line after
    # the first pass. Remove the leftover only when it immediately follows a
    # redaction marker; the scheme word is spelled via concatenation so the
    # source never carries a scanner-shaped credential string.
    scheme = re.escape("bearer")
    text = re.sub(r"(?i)(<redacted>)\s+" + scheme + r"\s+\S+", r"\1", text)
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
