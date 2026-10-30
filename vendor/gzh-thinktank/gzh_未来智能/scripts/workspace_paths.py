#!/usr/bin/env python3
"""Canonical paths and numbering for external article workspaces.

The workflow repository contains code, skills, contracts and tests.  Article
workspaces live in a sibling artifact root so generated evidence, images,
previews and receipts never become part of the workflow source tree.
"""
from __future__ import annotations

import json
import os
import re
import time
from contextlib import contextmanager, nullcontext
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT_ENV = "GZH_ARTIFACT_ROOT"
# The checked-out workflow lives under the project wrapper directory while
# production artifacts live in the wrapper's dedicated production directory.
# This keeps source code and generated works separate without creating a
# second sibling workspace root.
DEFAULT_ARTIFACT_ROOT = ROOT.parent / "production"
WORKSPACE_SCHEMA = "article-workspace-v1"
WORKSPACE_ID_PREFIX = "THK"
WORKSPACE_ID_RE = re.compile(r"^THK-(?P<date>\d{8})-(?P<seq>\d{3})$")
LIFECYCLE_DIRS = ("active", "delivered", "archive", "quarantine")
REGISTRY_DIRS = ("registry", "registry/routes", "registry/locks")
WORKSPACE_DIRS = ("work", "exports", "snapshots")


def _test_mode() -> bool:
    return os.environ.get("WORKFLOW_TEST_MODE") == "1"


def artifact_root(*, create: bool = False) -> Path:
    raw = os.environ.get(ARTIFACT_ROOT_ENV, "").strip()
    path = Path(raw).expanduser() if raw else DEFAULT_ARTIFACT_ROOT
    path = path.resolve()
    if path == ROOT.resolve() or ROOT.resolve() in path.parents:
        raise ValueError(
            f"{ARTIFACT_ROOT_ENV} must be outside workflow repository: {path}"
        )
    if create:
        path.mkdir(parents=True, exist_ok=True)
        for relative in (*LIFECYCLE_DIRS, *REGISTRY_DIRS, "inbox", "tmp"):
            (path / relative).mkdir(parents=True, exist_ok=True)
        readme = path / "README.md"
        if not readme.exists():
            readme.write_text(
                "# X超玩•未来智能作品工作区\n\n"
                "此目录位于工作流仓库之外，保存文章工作区、过程证据、预览、发布回执和归档。\n"
                "工作流源代码位于 `gzh_未来智能`，作品统一写入 `production`，不要写回源仓库。\n",
                encoding="utf-8",
            )
        registry = path / "registry" / "workspace-index.json"
        if not registry.exists():
            registry.write_text(
                json.dumps({"schema_version": 1, "contract": "workspace-index-v1", "workspaces": []}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
    return path


def _inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def resolve_workspace_root(candidate: Path | str | None = None, *, create: bool = False) -> Path:
    """Resolve the parent under which a new article workspace is created."""
    base = artifact_root(create=create)
    if candidate is None:
        return base / "active"
    raw = Path(candidate).expanduser()
    raw_text = raw.as_posix().strip("/").lower()
    if raw_text in {"drafts", "draft"} or raw_text.startswith("drafts/"):
        raise ValueError(
            "legacy drafts/ root is blocked; use artifact-root/active or set "
            f"{ARTIFACT_ROOT_ENV}"
        )
    if not raw.is_absolute():
        raw = base / raw
    resolved = raw.resolve()
    if resolved == base:
        resolved = base / "active"
    if _inside(resolved, ROOT):
        raise ValueError(
            "article root must stay outside workflow repository; "
            "use the configured artifact root (GZH_ARTIFACT_ROOT)"
        )
    if not _inside(resolved, base):
        if _test_mode():
            resolved.mkdir(parents=True, exist_ok=True)
            return resolved
        raise ValueError(
            "article root must stay inside configured artifact root; "
            f"expected under {base}"
        )
    if resolved.name not in LIFECYCLE_DIRS and resolved != base / "active":
        # A caller may pass an existing article workspace only to processing
        # commands; matrix_init itself always creates under active.
        if resolved.parent.name not in LIFECYCLE_DIRS:
            raise ValueError("new article root must be artifact-root/active")
    if create:
        resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def resolve_article_workspace(candidate: Path | str, *, allow_test_fixture: bool = True) -> Path:
    """Resolve a production article path, allowing only external workspaces."""
    raw = Path(candidate).expanduser()
    base = artifact_root(create=False)
    if not raw.is_absolute():
        text = raw.as_posix().lstrip("./")
        if text.startswith("drafts/") or text == "drafts":
            raise ValueError(
                "legacy drafts/ path is blocked; initialize under external artifact root"
            )
        if text.startswith(("active/", "delivered/", "archive/", "quarantine/")):
            raw = base / text
        else:
            raw = ROOT / raw
    resolved = raw.resolve()
    if _inside(resolved, base):
        try:
            relative = resolved.relative_to(base.resolve())
        except ValueError:
            relative = Path()
        parts = relative.parts
        if len(parts) < 2 or parts[0] not in LIFECYCLE_DIRS:
            raise ValueError(
                "article workspace must be under artifact-root/active, delivered, archive, or quarantine"
            )
        if not re.match(r"^THK-\d{8}-\d{3}-.+", parts[1]):
            raise ValueError("article workspace directory must use THK-YYYYMMDD-NNN-slug")
        if not _test_mode():
            relative_text = relative.as_posix()
            registry = _read_registry(base)
            workspace_id = "-".join(parts[1].split("-", 3)[:3])
            registered = any(
                isinstance(item, dict)
                and str(item.get("relative_path", "")) == relative_text
                and str(item.get("workspace_id", "")) == workspace_id
                for item in registry.get("workspaces", [])
            )
            if not registered:
                raise ValueError("workspace is not registered in registry/workspace-index.json")
            if not (resolved / "workspace-manifest.json").is_file():
                raise ValueError("workspace-manifest.json is required")
        return resolved
    if allow_test_fixture and _test_mode() and not _inside(resolved, ROOT):
        return resolved
    raise ValueError(
        "article workspace must be outside workflow repository and inside "
        f"{base} (set {ARTIFACT_ROOT_ENV} to override)"
    )


def resolve_route_path(candidate: Path | str, *, allow_test_fixture: bool = True, allow_repo: bool = False) -> Path:
    """Resolve a routing control file in the repo or external registry.

    Route files are control-plane records, not article output.  New routes
    live in ``<artifact-root>/registry/routes``; repository-local paths remain
    readable only for migration/backward compatibility.
    """
    raw = Path(candidate).expanduser()
    base = artifact_root(create=False)
    if not raw.is_absolute():
        text = raw.as_posix().lstrip("./")
        if text.startswith("registry/routes/"):
            raw = base / text
        else:
            raw = ROOT / raw
    resolved = raw.resolve()
    if _inside(resolved, base) or (allow_repo and _inside(resolved, ROOT)):
        return resolved
    if allow_test_fixture and _test_mode() and not _inside(resolved, ROOT):
        return resolved
    raise ValueError(
        "route path must be inside workflow repository or external artifact registry"
    )


def slugify(value: str) -> str:
    value = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", value).strip("-").lower()
    return value[:80] or "untitled"


def _registry_path(root: Path) -> Path:
    return root / "registry" / "workspace-index.json"


def _read_registry(root: Path) -> dict[str, Any]:
    path = _registry_path(root)
    if not path.is_file():
        return {"schema_version": 1, "contract": "workspace-index-v1", "workspaces": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    if not isinstance(data, dict) or not isinstance(data.get("workspaces"), list):
        return {"schema_version": 1, "contract": "workspace-index-v1", "workspaces": []}
    return data


def _write_registry(root: Path, data: dict[str, Any]) -> None:
    path = _registry_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


@contextmanager
def registry_lock(root: Path, *, timeout: float = 15.0) -> Iterator[None]:
    lock_dir = root / "registry" / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock = lock_dir / "workspace-index.lock"
    deadline = time.monotonic() + timeout
    handle = None
    while handle is None:
        try:
            handle = lock.open("x", encoding="utf-8")
        except FileExistsError:
            if time.monotonic() >= deadline:
                raise TimeoutError(f"workspace registry lock timed out: {lock}")
            time.sleep(0.05)
    try:
        handle.write(str(os.getpid()),)
        handle.flush()
        yield
    finally:
        handle.close()
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def allocate_workspace(title: str, *, date_value: str | None = None,
                       requested_slug: str | None = None,
                       root: Path | str | None = None) -> tuple[Path, str, int]:
    """Reserve a daily sequence number and create an external workspace."""
    base = artifact_root(create=True)
    parent = resolve_workspace_root(root, create=True)
    day = date_value or datetime.now().strftime("%Y%m%d")
    if not re.fullmatch(r"\d{8}", day):
        raise ValueError("date must use YYYYMMDD")
    slug = slugify(requested_slug or title)
    # Production allocations are serialized in the shared registry.  A test
    # fixture may pass an arbitrary temporary parent; keeping that registry
    # local avoids mutating a developer's real artifact root during tests.
    if parent != base / "active" and not _test_mode():
        raise ValueError("matrix_init must create new workspaces under artifact-root/active")
    lock_context = registry_lock(base) if parent == base / "active" else nullcontext()
    with lock_context:
        registry = _read_registry(base) if parent == base / "active" else {"workspaces": []}
        entries = [item for item in registry.get("workspaces", []) if isinstance(item, dict)]
        used = []
        for item in entries:
            match = WORKSPACE_ID_RE.match(str(item.get("workspace_id", "")))
            if match and match.group("date") == day:
                used.append(int(match.group("seq")))
        # Test fixtures also consider existing directory names so repeated
        # tests cannot collide even without a registry file.
        for candidate in parent.glob(f"{WORKSPACE_ID_PREFIX}-{day}-*-*"):
            match = WORKSPACE_ID_RE.match("-".join(candidate.name.split("-")[:3]))
            if match and match.group("date") == day:
                used.append(int(match.group("seq")))
        sequence = max(used, default=0) + 1
        workspace_id = f"{WORKSPACE_ID_PREFIX}-{day}-{sequence:03d}"
        directory = parent / f"{workspace_id}-{slug}"
        if directory.exists():
            raise FileExistsError(f"workspace allocation collision: {directory}")
        directory.mkdir(parents=True)
        for relative in WORKSPACE_DIRS:
            (directory / relative).mkdir(parents=True, exist_ok=True)
        # Reserve a complete, auditable workspace atomically with its registry
        # entry.  matrix_init enriches this manifest after route validation.
        (directory / "workspace-manifest.json").write_text(
            json.dumps(workspace_manifest(directory, workspace_id, title, slug), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if parent == base / "active":
            entry = {
                "workspace_id": workspace_id,
                "account_id": "thinktank",
                "title": title,
                "slug": slug,
                "lifecycle": "active",
                "relative_path": directory.relative_to(base).as_posix(),
                "created_at": datetime.now().astimezone().isoformat(),
            }
            registry.setdefault("schema_version", 1)
            registry.setdefault("contract", "workspace-index-v1")
            registry.setdefault("workspaces", []).append(entry)
            _write_registry(base, registry)
    return directory, workspace_id, sequence


def workspace_manifest(workspace: Path, workspace_id: str, title: str, slug: str) -> dict[str, Any]:
    base = artifact_root(create=False)
    try:
        relative_path = workspace.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        relative_path = "test-fixture/" + workspace.name
    return {
        "schema_version": 1,
        "contract": WORKSPACE_SCHEMA,
        "workspace_id": workspace_id,
        "account_id": "thinktank",
        "content_medium": "wechat_article",
        "title": title,
        "slug": slug,
        "lifecycle": "active",
        # Keep the manifest portable: local absolute paths belong in operator
        # logs, never in the article contract that may be copied or published.
        "workspace_root": "<GZH_ARTIFACT_ROOT>",
        "relative_path": relative_path,
        "standard_artifacts_at_root": True,
        "process_files_dir": "work",
        "deliverable_dir": "exports",
        "checkpoint_dir": "snapshots",
        "created_at": datetime.now().astimezone().isoformat(),
    }
