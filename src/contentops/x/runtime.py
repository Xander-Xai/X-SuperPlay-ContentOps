"""X editorial workflow as an in-repository, manual-only adapter.

The X track is ContentOps's own code (``src/contentops/publish/`` and
``scripts/x_post.py``), not an external tree. This adapter reports whether the
local workspace is present and consistent and describes the manual operations.
It never calls the X API, reads a credential, drafts on the platform or
publishes.

A missing account, project or gate code is a named refusal. A verified
workspace still reports ``publish_mode: MANUAL_ONLY``, ``api_used: false`` and
all authority flags false.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

SCHEMA = "contentops.x-runtime/v1"
STATUS_SCHEMA = "contentops.x-status/v1"
PLAN_SCHEMA = "contentops.x-plan/v1"

DEFAULT_ACCOUNT = Path("config") / "accounts" / "x-superplay-english.json"
DEFAULT_PROJECT = Path("projects") / "x-growth-en"
GATE_CODE = Path("scripts") / "x_post.py"
PUBLISHER_CODE = Path("src") / "contentops" / "publish" / "publisher.py"

#: Both account contracts are real: the X editorial track uses
#: ``contentops.x-account/v1``; the shared content account DNA uses
#: ``contentops.account-dna/v2``.
ACCOUNT_SCHEMAS = ("contentops.x-account/v1", "contentops.account-dna/v2")
VERIFIED = "VERIFIED"
BLOCKED = "BLOCKED"

#: Manual operations only. None is executed here; none publishes through an API.
OPERATIONS = (
    {"name": "new", "authority": "OPERATOR",
     "command": "python scripts/x_post.py <project> --new --id <id> --topic <topic>"},
    {"name": "check", "authority": "READ_ONLY",
     "command": "python scripts/x_post.py <project> --check --id <id>"},
    {"name": "package", "authority": "OPERATOR",
     "command": "python scripts/x_post.py <project> --package --id <id>"},
    {"name": "mark_published", "authority": "OPERATOR",
     "command": "python scripts/x_post.py <project> --mark-published --id <id> --url <url>"},
    {"name": "verify_log", "authority": "READ_ONLY",
     "command": "python scripts/x_post.py <project> --verify-log"},
)


class XBlocked(Exception):
    """The X workspace cannot be used, and this is the named reason."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _resolve(repo_root: Optional[Path], relative: Path) -> Path:
    root = Path(repo_root) if repo_root else _repo_root()
    return (root / relative).resolve()


def verify(*, repo_root: Optional[Path] = None,
           account: Optional[Path] = None,
           project: Optional[Path] = None) -> Dict[str, Any]:
    """Verify the local X workspace; never call the platform."""
    root = (Path(repo_root) if repo_root else _repo_root()).resolve()
    account_path = Path(account) if account else _resolve(root, DEFAULT_ACCOUNT)
    project_path = Path(project) if project else _resolve(root, DEFAULT_PROJECT)

    if not account_path.is_file():
        raise XBlocked("ACCOUNT_MISSING", str(account_path))
    try:
        document = json.loads(account_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise XBlocked("ACCOUNT_SCHEMA", f"{account_path}: {exc}") from None
    if not isinstance(document, dict) or document.get("schema") not in ACCOUNT_SCHEMAS:
        raise XBlocked("ACCOUNT_SCHEMA",
                       f"{account_path} must declare one of {', '.join(ACCOUNT_SCHEMAS)}")
    slug = str(document.get("slug") or "").strip()
    if not slug:
        raise XBlocked("ACCOUNT_SCHEMA", f"{account_path} has no slug")

    if not project_path.is_dir() or not (project_path / "project.yaml").is_file():
        raise XBlocked("PROJECT_MISSING", str(project_path))

    gate = _resolve(root, GATE_CODE)
    publisher = _resolve(root, PUBLISHER_CODE)
    if not gate.is_file():
        raise XBlocked("GATE_CODE_MISSING", str(gate))
    if not publisher.is_file():
        raise XBlocked("GATE_CODE_MISSING", str(publisher))

    return {
        "schema": STATUS_SCHEMA,
        "state": VERIFIED,
        "workflow_id": "x-editorial",
        "account_slug": slug,
        "account_path": str(account_path),
        "project": str(project_path),
        "publish_mode": "MANUAL_ONLY",
        "api_used": False,
        "execution_authorized": False,
        "publish_authorized": False,
        "production_ready": False,
        "note": "offline editorial gate only; a real status URL is recorded manually after publication",
    }


def status(*, repo_root: Optional[Path] = None,
           account: Optional[Path] = None,
           project: Optional[Path] = None) -> Dict[str, Any]:
    """Verify or return a BLOCKED result; never raise for a missing workspace."""
    try:
        return verify(repo_root=repo_root, account=account, project=project)
    except XBlocked as blocked:
        return {"schema": STATUS_SCHEMA, "state": BLOCKED,
                "code": blocked.code, "detail": blocked.detail}


def plan(*, repo_root: Optional[Path] = None,
         account: Optional[Path] = None,
         project: Optional[Path] = None) -> Dict[str, Any]:
    """Describe the manual operations; grant nothing."""
    result = status(repo_root=repo_root, account=account, project=project)
    return {
        "schema": PLAN_SCHEMA,
        "state": result["state"],
        "workflow_id": "x-editorial",
        "account_slug": result.get("account_slug"),
        "project": result.get("project"),
        "publish_mode": "MANUAL_ONLY",
        "api_used": False,
        "operations": [dict(item) for item in OPERATIONS],
        "execution_authorized": False,
        "publish_authorized": False,
        "production_ready": False,
        "code": result.get("code"),
        "detail": result.get("detail"),
    }
