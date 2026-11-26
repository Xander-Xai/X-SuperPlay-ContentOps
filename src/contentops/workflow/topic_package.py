"""Shared, medium-neutral topic package and fail-closed format handoffs.

The topic package is the authority for routed intent, signed pre-copy research,
canonical copy and its current human review. VIDEO and GRAPHIC_TEXT projects are
sibling outputs that reference the authority by slug and digest; copied files are
never trusted as an authority.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

from . import canonical_copy, copy_review, preresearch

PACKAGE_SCHEMA = "contentops.shared-topic-package/v1"
REFERENCE_SCHEMA = "contentops.shared-topic-package-ref/v1"
MANIFEST = Path("topic-package.json")
REFERENCE = Path("receipts") / "topic-package-ref.json"
HANDOFF_RECEIPT = Path("receipts") / "topic-package-handoff.json"
FORMATS = ("VIDEO", "GRAPHIC_TEXT")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,80}$")


class TopicPackageError(ValueError):
    """A shared topic package or one of its consumer bindings is invalid."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _project_file(project: Path, relative: Path) -> Path:
    """Resolve a project-owned path without allowing symlink/junction escape."""
    root = Path(project).resolve()
    candidate = root
    for part in relative.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise TopicPackageError("PROJECT_SYMLINK_REFUSED",
                                    f"project path {relative.as_posix()} contains a symlink")
        try:
            candidate.resolve().relative_to(root)
        except ValueError:
            raise TopicPackageError("PROJECT_PATH_ESCAPE",
                                    f"project path {relative.as_posix()} escapes its root") from None
    return candidate


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") == data:
            return
        raise TopicPackageError("TOPIC_PACKAGE_EXISTS", f"refusing to overwrite {path.name}")
    path.write_text(data, encoding="utf-8", newline="\n")


def _yaml_value(project: Path, name: str) -> Optional[str]:
    try:
        text = _project_file(project, Path("project.yaml")).read_text(encoding="utf-8")
    except (OSError, TopicPackageError):
        return None
    match = re.search(rf"^{re.escape(name)}\s*:\s*(.*?)\s*$", text, re.MULTILINE)
    return match.group(1).strip().strip("\"'") if match else None


def _set_yaml_values(project: Path, values: Dict[str, str]) -> None:
    path = _project_file(project, Path("project.yaml"))
    if not path.is_file():
        raise TopicPackageError("PROJECT_YAML_MISSING", "project.yaml is required")
    text = path.read_text(encoding="utf-8")
    additions = []
    for name, value in values.items():
        current = _yaml_value(project, name)
        if current is not None and current != value:
            raise TopicPackageError("PROJECT_TOPIC_PACKAGE_CONFLICT",
                                    f"project.yaml {name}={current!r}, expected {value!r}")
        if current is None:
            additions.append(f"{name}: {value}")
    if additions:
        path.write_text(text.rstrip() + "\n\n# Bound by the shared topic-package workflow\n"
                        + "\n".join(additions) + "\n", encoding="utf-8", newline="\n")


def _package_id(intent_sha: str, research_sha: str, account: Any, topic: Any) -> str:
    seed = _canonical({"intent_sha256": intent_sha, "research_sha256": research_sha,
                       "account": account, "topic": topic})
    return "TP-" + _sha(seed)[:20].upper()


def _identity(project: Path) -> tuple[Dict[str, Any], bytes, Dict[str, Any]]:
    for _, relative in preresearch.ARTIFACTS:
        _project_file(project, relative)
    _project_file(project, preresearch.RECEIPT)
    intent_path = _project_file(project, preresearch.INTENT_FILE)
    try:
        intent_raw = intent_path.read_bytes()
        intent = json.loads(intent_raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        raise TopicPackageError("TOPIC_INTENT_INVALID", "signed ContentIntent is missing or invalid")
    if not isinstance(intent, dict) or intent.get("target_pipeline") != "TOPIC":
        raise TopicPackageError("TOPIC_INTENT_REQUIRED",
                                "shared topic packages require a medium-neutral TOPIC intent")
    report = preresearch.check(project)
    if not report.get("ok"):
        raise TopicPackageError("PRECOPY_RESEARCH_REQUIRED",
                                str(report.get("detail") or report.get("state")))
    return intent, intent_raw, report


def initialize(project: Path) -> Dict[str, Any]:
    """Mark a routed TOPIC project as the authority for its shared copy package."""
    project_input = Path(project)
    if project_input.is_symlink():
        raise TopicPackageError("PROJECT_SYMLINK_REFUSED", "topic package authority must not be a symlink")
    project = project_input.resolve()
    if not project.is_dir() or not SLUG_RE.fullmatch(project.name):
        raise TopicPackageError("PROJECT_ID_INVALID", "topic package must be a direct project with a safe slug")
    intent, intent_raw, research = _identity(project)
    copy_path = _project_file(project, canonical_copy.CANONICAL_FILE)
    document = _read_json(copy_path)
    if document is None:
        raise TopicPackageError("CANONICAL_COPY_MISSING", canonical_copy.CANONICAL_FILE.as_posix())
    failures = canonical_copy.validate(document)
    if failures:
        raise TopicPackageError("CANONICAL_COPY_INVALID", "; ".join(failures))
    if document.get("intent_sha256") != _sha(intent_raw):
        raise TopicPackageError("INTENT_MISMATCH", "canonical copy does not bind the topic intent")
    if document.get("research_sha256") != research.get("artifacts_sha256"):
        raise TopicPackageError("RESEARCH_MISMATCH", "canonical copy does not bind signed research")
    if document.get("account") != intent.get("account_id") or document.get("topic") != intent.get("topic"):
        raise TopicPackageError("INTENT_MISMATCH", "canonical copy account/topic differs from intent")
    if _yaml_value(project, "account_slug") != intent.get("account_id"):
        raise TopicPackageError("ACCOUNT_MISMATCH", "topic project account_slug must match the routed intent")

    intent_sha = _sha(intent_raw)
    research_sha = str(research["artifacts_sha256"])
    package_id = _package_id(intent_sha, research_sha,
                             intent.get("account_id"), intent.get("topic"))
    manifest = {
        "schema": PACKAGE_SCHEMA,
        "package_id": package_id,
        "package_slug": project.name,
        "account": intent["account_id"],
        "topic": intent["topic"],
        "formats": list(FORMATS),
        "intent_sha256": _sha(intent_raw),
        "research_sha256": research["artifacts_sha256"],
        "canonical_copy_sha256": canonical_copy.digest(document),
    }
    _set_yaml_values(project, {"topic_package_mode": "owner",
                               "topic_package_id": package_id})
    _write_json(_project_file(project, MANIFEST), manifest)
    return {"ok": True, "package_id": package_id, "package_sha256": package_digest(project),
            "production_ready": False, "publish_authorized": False}


def _package_state(project: Path, *, require_review: bool = True) -> Dict[str, Any]:
    project = Path(project).resolve()
    try:
        manifest = _read_json(_project_file(project, MANIFEST))
    except TopicPackageError as exc:
        return {"ok": False, "state": exc.code, "detail": exc.detail}
    if manifest is None or manifest.get("schema") != PACKAGE_SCHEMA:
        return {"ok": False, "state": "TOPIC_PACKAGE_INVALID",
                "detail": "topic-package.json is missing or malformed"}
    if _yaml_value(project, "topic_package_mode") != "owner" or \
            _yaml_value(project, "topic_package_id") != manifest.get("package_id"):
        return {"ok": False, "state": "TOPIC_PACKAGE_MARKER_INVALID",
                "detail": "project.yaml does not bind this topic-package authority"}
    try:
        intent, intent_raw, research = _identity(project)
    except TopicPackageError as exc:
        return {"ok": False, "state": exc.code, "detail": exc.detail}
    try:
        copy_doc = _read_json(_project_file(project, canonical_copy.CANONICAL_FILE))
    except TopicPackageError as exc:
        return {"ok": False, "state": exc.code, "detail": exc.detail}
    if copy_doc is None:
        return {"ok": False, "state": "CANONICAL_COPY_MISSING",
                "detail": canonical_copy.CANONICAL_FILE.as_posix()}
    failures = canonical_copy.validate(copy_doc)
    if failures:
        return {"ok": False, "state": "CANONICAL_COPY_INVALID", "detail": "; ".join(failures)}
    intent_sha = _sha(intent_raw)
    research_sha = str(research.get("artifacts_sha256") or "")
    copy_sha = canonical_copy.digest(copy_doc)
    expected_package_id = _package_id(intent_sha, research_sha,
                                      intent.get("account_id"), intent.get("topic"))
    if (manifest.get("package_slug") != project.name
            or manifest.get("account") != intent.get("account_id")
            or manifest.get("topic") != intent.get("topic")
            or manifest.get("formats") != list(FORMATS)
            or manifest.get("package_id") != expected_package_id):
        return {"ok": False, "state": "TOPIC_PACKAGE_MANIFEST_MISMATCH",
                "detail": "package identity or supported formats do not match the signed topic intent"}
    expected = (manifest.get("intent_sha256"), manifest.get("research_sha256"),
                manifest.get("canonical_copy_sha256"))
    if expected != (intent_sha, research_sha, copy_sha):
        return {"ok": False, "state": "TOPIC_PACKAGE_STALE",
                "detail": "intent, signed research or canonical copy changed after package initialization"}
    if copy_doc.get("intent_sha256") != intent_sha or copy_doc.get("research_sha256") != research_sha:
        return {"ok": False, "state": "CANONICAL_COPY_STALE",
                "detail": "canonical copy is not bound to the current intent and signed research"}
    if copy_doc.get("account") != intent.get("account_id") or copy_doc.get("topic") != intent.get("topic"):
        return {"ok": False, "state": "INTENT_MISMATCH",
                "detail": "canonical copy account/topic differs from the routed topic"}
    if _yaml_value(project, "account_slug") != intent.get("account_id"):
        return {"ok": False, "state": "ACCOUNT_MISMATCH",
                "detail": "topic project account_slug differs from the routed intent"}
    if require_review:
        review = copy_review.status(project)
        if not review.get("ok"):
            return {"ok": False, "state": "CANONICAL_COPY_NOT_APPROVED",
                    "detail": str(review.get("detail") or review.get("state"))}
    return {"ok": True, "state": "TOPIC_PACKAGE_CURRENT",
            "package_id": manifest["package_id"], "package_slug": project.name,
            "package_sha256": package_digest(project), "canonical_copy": copy_doc,
            "canonical_copy_sha256": copy_sha, "research_sha256": research_sha,
            "account": intent.get("account_id"), "topic": intent.get("topic"),
            "detail": "shared topic package and canonical approval are current",
            "production_ready": False, "publish_authorized": False}


def check_package(project: Path) -> Dict[str, Any]:
    """Read-only check for the shared authority package."""
    return _package_state(project)


def package_digest(project: Path) -> str:
    """Digest manifest, signed research, canonical copy and canonical review."""
    project = Path(project).resolve()
    _identity(project)  # also rejects linked research inputs before fingerprinting
    manifest_path = _project_file(project, MANIFEST)
    manifest = _read_json(manifest_path)
    if manifest is None:
        raise TopicPackageError("TOPIC_PACKAGE_INVALID", "topic-package.json is missing or malformed")
    research_sha = preresearch.fingerprint(project)
    copy_path = _project_file(project, canonical_copy.CANONICAL_FILE)
    review_path = _project_file(project, copy_review.RECORD)
    if not research_sha or not copy_path.is_file():
        raise TopicPackageError("TOPIC_PACKAGE_INCOMPLETE", "research and canonical copy are required")
    document = {"manifest_sha256": _sha(manifest_path.read_bytes()),
                "research_sha256": research_sha,
                "canonical_copy_sha256": _sha(copy_path.read_bytes()),
                # Initialization precedes canonical approval. The missing review
                # is represented explicitly; handoff checks always require it.
                "review_sha256": _sha(review_path.read_bytes()) if review_path.is_file() else None}
    return _sha(_canonical(document))


def bind_child(package_project: Path, child_project: Path, content_format: str, *,
               projects_root: Path) -> Dict[str, Any]:
    """Bind a sibling production project to a current shared topic authority."""
    package_input = Path(package_project)
    child_input = Path(child_project)
    root_input = Path(projects_root)
    if package_input.is_symlink() or child_input.is_symlink():
        raise TopicPackageError("PROJECT_SYMLINK_REFUSED", "shared package and child must not be symlinks")
    if root_input.is_symlink():
        raise TopicPackageError("PROJECT_ROOT_INVALID", "projects_root must not be a symlink")
    package_project = package_input.resolve()
    child_project = child_input.resolve()
    root = root_input.resolve()
    if content_format not in FORMATS:
        raise TopicPackageError("FORMAT_UNKNOWN", f"format must be one of {FORMATS}")
    if package_project.is_symlink() or child_project.is_symlink():
        raise TopicPackageError("PROJECT_SYMLINK_REFUSED", "shared package and child must not be symlinks")
    if package_project.parent != root or child_project.parent != root:
        raise TopicPackageError("PROJECT_ROOT_INVALID", "package and output projects must be direct children of projects_root")
    if not SLUG_RE.fullmatch(package_project.name) or not SLUG_RE.fullmatch(child_project.name):
        raise TopicPackageError("PROJECT_ID_INVALID", "project directories must use safe kebab-case slugs")
    if not package_project.is_dir() or not child_project.is_dir():
        raise TopicPackageError("PROJECT_MISSING", "both topic package and output project must exist")
    state = _package_state(package_project)
    if not state["ok"]:
        raise TopicPackageError(str(state["state"]), str(state["detail"]))
    child_account = _yaml_value(child_project, "account_slug")
    if child_account != state["account"]:
        raise TopicPackageError("ACCOUNT_MISMATCH", "child project account_slug must match topic package account")
    reference = {
        "schema": REFERENCE_SCHEMA,
        "package_slug": package_project.name,
        "package_id": state["package_id"],
        "package_sha256": state["package_sha256"],
        "content_format": content_format,
        "project_slug": child_project.name,
    }
    _set_yaml_values(child_project, {"topic_package_mode": "required",
                                     "topic_package_id": state["package_id"],
                                     "topic_package_format": content_format})
    _write_json(_project_file(child_project, REFERENCE), reference)
    _write_json(_project_file(child_project, HANDOFF_RECEIPT),
                {**reference, "schema": "contentops.topic-package-handoff/v1",
                 "production_ready": False, "publish_authorized": False})
    return {"ok": True, **reference, "production_ready": False,
            "publish_authorized": False}


def _infer_projects_root(project: Path) -> Optional[Path]:
    """Infer only known repository/workspace roots; never read .env here."""
    resolved = Path(project).resolve()
    repo_root = Path(__file__).resolve().parents[3]
    candidates = [repo_root / "projects", repo_root / "projects" / "_local"]
    raw_output_root = os.environ.get("CONTENTOPS_OUTPUT_ROOT", "").strip()
    if raw_output_root:
        candidates.append(Path(raw_output_root).expanduser().resolve() / "workspace")
    for root in candidates:
        root = Path(root).resolve()
        if resolved.parent == root:
            return root
    return None


def is_declared_consumer(project: Path) -> bool:
    """Whether any persisted signal says this project consumes a shared package.

    This intentionally catches partial markers so deleting only one binding file
    cannot silently restore the legacy path. Erasing every marker remains outside
    the tamper-resistance guarantees of ordinary project filesystems.
    """
    project = Path(project)
    mode = _yaml_value(project, "topic_package_mode")
    package_id = _yaml_value(project, "topic_package_id")
    ref = project / REFERENCE
    handoff = project / HANDOFF_RECEIPT
    has_ref = any(path.exists() or path.is_symlink() for path in (ref, handoff))
    if has_ref or mode not in (None, "owner"):
        return True
    return package_id is not None and not (project / MANIFEST).is_file()


def status_child(child_project: Path, *, content_format: Optional[str] = None,
                 projects_root: Optional[Path] = None) -> Dict[str, Any]:
    """Re-read and verify a child binding at each copy/production gate.

    Projects without any shared-package marker or ref remain legacy. A partial
    marker, an orphaned local derivative, or an invalid shared reference blocks
    instead of silently reverting to legacy behavior.
    """
    child_input = Path(child_project)
    if child_input.is_symlink():
        return {"ok": False, "applicable": True, "state": "PROJECT_SYMLINK_REFUSED",
                "detail": "bound child project must not be a symlink"}
    child = child_input.resolve()
    try:
        ref_path = _project_file(child, REFERENCE)
        handoff_path = _project_file(child, HANDOFF_RECEIPT)
    except TopicPackageError as exc:
        return {"ok": False, "applicable": True, "state": exc.code,
                "detail": exc.detail}
    mode = _yaml_value(child, "topic_package_mode")
    package_id_marker = _yaml_value(child, "topic_package_id")
    if mode is None and package_id_marker is None and not ref_path.exists() \
            and not handoff_path.exists():
        return {"ok": True, "applicable": False, "state": "LEGACY",
                "detail": "project is not declared as a shared-topic consumer"}
    if mode != "required" or package_id_marker is None:
        return {"ok": False, "applicable": True, "state": "TOPIC_PACKAGE_MARKER_INVALID",
                "detail": "topic-package mode marker is partial or invalid"}
    if not ref_path.is_file() or not handoff_path.is_file():
        return {"ok": False, "applicable": True, "state": "TOPIC_PACKAGE_REFERENCE_MISSING",
                "detail": "bound project is missing its topic package reference or handoff receipt"}
    reference = _read_json(ref_path)
    receipt = _read_json(handoff_path)
    if reference is None or reference.get("schema") != REFERENCE_SCHEMA or receipt is None:
        return {"ok": False, "applicable": True, "state": "TOPIC_PACKAGE_REFERENCE_INVALID",
                "detail": "topic package reference or handoff receipt is malformed"}
    if receipt.get("schema") != "contentops.topic-package-handoff/v1":
        return {"ok": False, "applicable": True, "state": "TOPIC_PACKAGE_HANDOFF_INVALID",
                "detail": "topic package handoff receipt has the wrong schema"}
    if receipt.get("package_sha256") != reference.get("package_sha256") or \
            receipt.get("package_id") != reference.get("package_id"):
        return {"ok": False, "applicable": True, "state": "TOPIC_PACKAGE_HANDOFF_INVALID",
                "detail": "handoff receipt and package reference disagree"}
    package_slug = str(reference.get("package_slug") or "")
    if not SLUG_RE.fullmatch(package_slug):
        return {"ok": False, "applicable": True, "state": "TOPIC_PACKAGE_PATH_INVALID",
                "detail": "package_slug must be a safe kebab-case project id"}
    root = Path(projects_root).resolve() if projects_root is not None else _infer_projects_root(child)
    if root is None or child.parent != root:
        return {"ok": False, "applicable": True, "state": "PROJECT_ROOT_INVALID",
                "detail": "child is not a direct child of an approved projects root"}
    package_path = root / package_slug
    if package_path.is_symlink() or package_path.resolve().parent != root or not package_path.is_dir():
        return {"ok": False, "applicable": True, "state": "TOPIC_PACKAGE_PATH_INVALID",
                "detail": "shared topic package is missing, linked, or outside the trusted projects root"}
    state = _package_state(package_path)
    if not state.get("ok"):
        return {"ok": False, "applicable": True, "state": state.get("state"),
                "detail": state.get("detail")}
    content_format = reference.get("content_format")
    if (reference.get("package_id") != state.get("package_id")
            or reference.get("package_sha256") != state.get("package_sha256")
            or reference.get("project_slug") != child.name
            or content_format not in FORMATS
            or content_format != _yaml_value(child, "topic_package_format")
            or content_format != receipt.get("content_format")
            or reference.get("package_id") != package_id_marker):
        return {"ok": False, "applicable": True, "state": "TOPIC_PACKAGE_STALE",
                "detail": "child reference no longer matches the current topic package or project marker"}
    if content_format is not None and reference.get("content_format") != content_format:
        return {"ok": False, "applicable": True, "state": "FORMAT_MISMATCH",
                "detail": f"reference format is {reference.get('content_format')!r}, expected {content_format!r}"}
    if _yaml_value(child, "account_slug") != state.get("account"):
        return {"ok": False, "applicable": True, "state": "ACCOUNT_MISMATCH",
                "detail": "child account differs from the shared topic package"}

    try:
        derivative_path = _project_file(child, canonical_copy.DERIVATIVE_FILE)
        derivative = _read_json(derivative_path)
    except TopicPackageError as exc:
        return {"ok": False, "applicable": True, "state": exc.code,
                "detail": exc.detail}
    if derivative is None:
        return {"ok": False, "applicable": True, "state": "DERIVATIVE_MISSING",
                "detail": canonical_copy.DERIVATIVE_FILE.as_posix()}
    failures = canonical_copy.validate_derivative(state["canonical_copy"], derivative)
    if derivative.get("format") != reference.get("content_format"):
        failures.append("derivative format differs from topic-package handoff")
    if failures:
        return {"ok": False, "applicable": True, "state": "DERIVATIVE_INVALID",
                "detail": "; ".join(failures)}
    output_relative = Path("draft.md" if reference["content_format"] == "GRAPHIC_TEXT"
                           else "script/master.md")
    try:
        output = _project_file(child, output_relative)
        output_text = output.read_text(encoding="utf-8")
    except TopicPackageError as exc:
        return {"ok": False, "applicable": True, "state": exc.code,
                "detail": exc.detail}
    except OSError:
        return {"ok": False, "applicable": True, "state": "FORMAT_COPY_MISSING",
                "detail": output_relative.as_posix()}
    missing = [segment["text"] for segment in derivative["segments"]
               if segment["text"] not in output_text]
    if missing:
        return {"ok": False, "applicable": True, "state": "FORMAT_COPY_DIVERGED",
                "detail": "output is missing one or more derivative segments"}
    return {"ok": True, "applicable": True, "state": "TOPIC_PACKAGE_CURRENT",
            "package_id": state["package_id"], "package_sha256": state["package_sha256"],
            "canonical_copy_sha256": state["canonical_copy_sha256"],
            "content_format": reference["content_format"], "account": state["account"],
            "topic": state["topic"],
            "detail": "shared package is current; derivative and format output are structurally bound"}
