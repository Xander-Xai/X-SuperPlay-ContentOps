"""Ordered production stages, canonical hand-offs and fingerprint invalidation.

Why this exists
---------------
The repository already produced receipts, but nothing stopped a build from
skipping a step, reusing a stale hand-off, or treating a plan as evidence. Those
are not code defects; they are *sequence* defects, and a receipt cannot catch
one because a receipt only describes what ran.

So the contract is deliberately small and declarative:

- a fixed, ordered list of stages, each owning exactly one hand-off artifact;
- five stage states, never a free-form status string;
- an approval that names both the **artifact digest** and the **upstream
  digest**, so changing either one makes the approval stop applying;
- no force/bypass flag anywhere.

The module is stdlib-only and has no provider knowledge. A provider may write a
receipt; it may not change this contract.

What is deliberately not claimed
--------------------------------
This proves *ordering and freshness*, not quality. A stage can be approved and
still be wrong about the world. Quality is a separate gate, and the human
review is a separate artifact.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

CONTRACT_ID = "contentops.copy-to-video/v1"
WORKFLOW_SCHEMA = "contentops.workflow/v1"
WORKFLOW_FILE = "workflow.json"

STAGE_STATUSES = ("pending", "running", "ready_for_review", "approved", "blocked")


class WorkflowError(ValueError):
    """A workflow document is valid JSON but violates the contract."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Stage:
    """One ordered stage and the artifact it hands to the next stage."""

    id: str
    label: str
    artifact: str
    requires: Tuple[str, ...] = ()


#: The chain this repository actually runs, in order. It is deliberately shorter
#: than a general-purpose video pipeline: every stage here has a producer and a
#: consumer in `src/` or `scripts/`, and nothing is listed "for completeness".
STAGES: Tuple[Stage, ...] = (
    Stage("brief", "Brief", "00_brief/brief.json"),
    Stage("audience", "Audience", "00_brief/audience-insight.json", ("brief",)),
    Stage("research", "Research", "01_research/claims.json", ("audience",)),
    Stage("script", "Script", "02_script/script.json", ("research",)),
    Stage("audio", "Audio", "03_audio/audio-handoff.json", ("script",)),
    Stage("storyboard", "Storyboard", "04_visual/cut-plan.json", ("audio",)),
    Stage("assets", "Assets", "05_assets/asset-ledger.json", ("storyboard",)),
    Stage("compose", "Compose", "06_edit/master-timeline.json", ("assets",)),
    Stage("quality", "Quality", "07_quality/quality-report.json", ("compose",)),
    Stage("delivery", "Delivery", "08_delivery/delivery-manifest.json", ("quality",)),
)

STAGE_IDS: Tuple[str, ...] = tuple(stage.id for stage in STAGES)
_BY_ID: Dict[str, Stage] = {stage.id: stage for stage in STAGES}


def stage_by_id(stage_id: str) -> Stage:
    stage = _BY_ID.get(stage_id)
    if stage is None:
        raise WorkflowError("UNKNOWN_STAGE",
                            f"unknown stage {stage_id!r}; known: {', '.join(STAGE_IDS)}")
    return stage


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical(value: Any) -> str:
    if isinstance(value, dict):
        value = {k: value[k] for k in sorted(value)}
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def new_workflow(slug: str, account: str = "", contract: str = CONTRACT_ID) -> Dict[str, Any]:
    """A fresh workflow document. Every stage starts `pending`, never approved."""
    if not isinstance(slug, str) or not slug.strip():
        raise WorkflowError("MISSING_FIELD", "slug must be a non-empty string")
    if contract != CONTRACT_ID:
        raise WorkflowError("UNSUPPORTED_CONTRACT",
                            f"this repository runs {CONTRACT_ID}, not {contract!r}")
    return {
        "schema": WORKFLOW_SCHEMA,
        "contract": contract,
        "slug": slug.strip(),
        "account": account,
        "created_at": _now(),
        "stages": [
            {
                "id": stage.id,
                "status": "pending",
                "artifact": stage.artifact,
                "approval": None,
                "check": None,
                "stale": False,
                "stale_reason": "",
                "notes": "",
            }
            for stage in STAGES
        ],
    }


def validate_workflow(document: Any) -> Dict[str, Any]:
    """Structural validation. Never upgrades a status or invents an approval."""
    if not isinstance(document, dict):
        raise WorkflowError("MALFORMED_DOCUMENT", "workflow must be a JSON object")
    if document.get("schema") != WORKFLOW_SCHEMA:
        raise WorkflowError("UNSUPPORTED_SCHEMA",
                            f"expected {WORKFLOW_SCHEMA!r}, got {document.get('schema')!r}")
    if document.get("contract") != CONTRACT_ID:
        raise WorkflowError("UNSUPPORTED_CONTRACT",
                            f"expected {CONTRACT_ID!r}, got {document.get('contract')!r}")
    stages = document.get("stages")
    if not isinstance(stages, list):
        raise WorkflowError("MISSING_FIELD", "stages must be a list")
    if [item.get("id") for item in stages if isinstance(item, dict)] != list(STAGE_IDS):
        raise WorkflowError("STAGE_ORDER",
                            "stages must be exactly the contract stages in contract order")
    for item in stages:
        status = item.get("status")
        if status not in STAGE_STATUSES:
            raise WorkflowError("INVALID_STATUS",
                                f"{item.get('id')}: {status!r} is not one of {STAGE_STATUSES}")
        approval = item.get("approval")
        if approval is not None:
            if not isinstance(approval, dict):
                raise WorkflowError("INVALID_APPROVAL", f"{item.get('id')}: approval must be an object or null")
            for key in ("reviewer", "approved_at", "artifact_sha256", "inputs_sha256"):
                if not isinstance(approval.get(key), str) or not approval.get(key).strip():
                    raise WorkflowError("INVALID_APPROVAL",
                                        f"{item.get('id')}: approval.{key} must be a non-empty string")
            if status != "approved":
                raise WorkflowError("APPROVAL_WITHOUT_STATUS",
                                    f"{item.get('id')}: an approval requires status 'approved'")
        if status == "approved" and approval is None:
            raise WorkflowError("APPROVAL_MISSING",
                                f"{item.get('id')}: status 'approved' requires an approval record")
    return document


def load_workflow(path: Path) -> Dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        raise WorkflowError("WORKFLOW_MISSING", f"{path} does not exist")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WorkflowError("MALFORMED_JSON", f"{path}: {exc}") from None
    return validate_workflow(document)


def save_workflow(path: Path, document: Dict[str, Any]) -> None:
    """Atomic write. A half-written workflow is worse than no workflow."""
    validate_workflow(document)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(prefix=".workflow-", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _stage(document: Dict[str, Any], stage_id: str) -> Dict[str, Any]:
    stage_by_id(stage_id)
    for item in document.get("stages", []):
        if item.get("id") == stage_id:
            return item
    raise WorkflowError("UNKNOWN_STAGE", f"{stage_id} is not in the workflow document")


def artifact_path(project: Path, document: Dict[str, Any], stage_id: str) -> Path:
    """Resolve a stage artifact. A stage may override the default path."""
    item = _stage(document, stage_id)
    relative = item.get("artifact") or stage_by_id(stage_id).artifact
    path = (Path(project) / relative).resolve()
    root = Path(project).resolve()
    if root not in path.parents and path != root:
        raise WorkflowError("ARTIFACT_ESCAPES_PROJECT",
                            f"{stage_id}: {relative!r} resolves outside the project")
    return path


def artifact_sha256(project: Path, document: Dict[str, Any], stage_id: str) -> Optional[str]:
    path = artifact_path(project, document, stage_id)
    if not path.is_file():
        return None
    return _sha_file(path)


def input_fingerprint(project: Path, document: Dict[str, Any], stage_id: str) -> str:
    """Digest of every upstream artifact this stage consumes.

    Only content digests are included. Approval timestamps are deliberately not:
    re-approving an unchanged file must not churn every downstream fingerprint.
    Freshness of the upstream *approval* is enforced by :func:`is_current`.
    """
    stage = stage_by_id(stage_id)
    payload = {}
    for dependency in stage.requires:
        payload[dependency] = artifact_sha256(project, document, dependency)
    return _sha_bytes(_canonical(payload).encode("utf-8"))


def is_current(project: Path, document: Dict[str, Any],
               stage_id: str, _seen: Optional[Iterable[str]] = None) -> Tuple[bool, str]:
    """Whether an approval still applies to the bytes and upstream it named."""
    stage = stage_by_id(stage_id)
    item = _stage(document, stage_id)
    status = item.get("status")
    if status != "approved":
        return False, f"{stage_id} status is {status!r}, not 'approved'"
    approval = item.get("approval")
    if not isinstance(approval, dict):
        return False, f"{stage_id} has no approval record"
    actual = artifact_sha256(project, document, stage_id)
    if actual is None:
        return False, f"{stage_id} artifact is missing"
    if actual != approval.get("artifact_sha256"):
        return False, f"{stage_id} artifact changed after approval"
    current_inputs = input_fingerprint(project, document, stage_id)
    if current_inputs != approval.get("inputs_sha256"):
        return False, f"{stage_id} upstream artifacts changed after approval"
    seen = set(_seen or ())
    seen.add(stage_id)
    for dependency in stage.requires:
        if dependency in seen:
            continue
        ok, reason = is_current(project, document, dependency, seen)
        if not ok:
            return False, f"upstream {reason}"
    return True, ""


def reconcile(project: Path, document: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Recompute staleness for every stage and record it in the document.

    A stage is never silently downgraded from `approved`; its approval record
    stays, but `stale` becomes true and it stops satisfying its dependants. The
    next `check` is what changes the status.
    """
    changes: List[Dict[str, Any]] = []
    for stage in STAGES:
        item = _stage(document, stage.id)
        was_stale = bool(item.get("stale"))
        if item.get("status") == "approved":
            ok, reason = is_current(project, document, stage.id)
            item["stale"] = not ok
            item["stale_reason"] = "" if ok else reason
        else:
            item["stale"] = False
            item["stale_reason"] = ""
        if was_stale != bool(item["stale"]):
            changes.append({"stage": stage.id, "stale": item["stale"], "reason": item["stale_reason"]})
    return changes


def pending_stages(document: Dict[str, Any]) -> List[str]:
    """Stages that are not approved, in contract order."""
    return [item["id"] for item in document.get("stages", [])
            if item.get("status") != "approved"]


def policy_lock(document: Dict[str, Any]) -> Dict[str, Any]:
    """A stable description of the contract a package was created under."""
    payload = [
        {"id": stage.id, "artifact": stage.artifact, "requires": list(stage.requires),
         "override": _stage(document, stage.id).get("artifact")}
        for stage in STAGES
    ]
    return {
        "contract": document.get("contract"),
        "stage_count": len(STAGES),
        "stages_sha256": _sha_bytes(_canonical(payload).encode("utf-8")),
    }
