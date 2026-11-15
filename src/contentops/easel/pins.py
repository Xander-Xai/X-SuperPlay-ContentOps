"""The single registry of Easel engine identity.

Why this module exists
----------------------
The pinned commit used to live in five code constants plus three JSON records.
Every one of them was a separate truth: a change that updated four of five left
the repository claiming one engine while verifying another, and nothing failed
loudly. That is the failure mode this module removes. `runtime/easel-pins.json`
is now the only place an engine's identity is written down; everything else
reads it.

What an identity is
-------------------
A commit plus, when it was measured, a tree digest. **A tag is a comment, never
an identity.** Upstream released v0.3.0 and then replaced the tag while keeping
the version number, so a tag that resolves today is not evidence of what resolves
tomorrow. Any engine entry without a commit is rejected at load time; an entry
whose digest was never measured must say so rather than leave the field blank.

What this module does not do
----------------------------
It does not verify bytes, download anything, or decide that an engine is safe to
run. It reads a record and refuses to guess. `scripts/verify_easel_runtime.py`
proves content; `scripts/resolve_easel.py` picks a directory. Neither of them
invents an identity when this registry is unreadable — they report `BLOCKED`.

Rules
-----
1. No fallback. A missing or invalid registry raises :class:`PinError`; callers
   must fail closed, not quietly use a hardcoded commit.
2. One commit, one engine. Two entries sharing a commit is a configuration
   error, because it makes "which engine produced this receipt" unanswerable.
3. Unknown fields are preserved in :attr:`Engine.raw` so a later consumer can
   read an extension without this module knowing about it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "Engine",
    "PinError",
    "Registry",
    "SCHEMA",
    "active",
    "get",
    "identity",
    "load",
    "registry_path",
    "workbench",
]

SCHEMA = "contentops.easel-pins/v1"
REGISTRY_REL = Path("runtime") / "easel-pins.json"

_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_LAYOUTS = ("openclaw", "builtin")


class PinError(RuntimeError):
    """The registry is missing, unreadable, or internally inconsistent."""


@dataclass(frozen=True)
class Engine:
    """One engine entry, validated. It is a claim about identity, not a grant."""

    engine_id: str
    role: str
    repo: str
    tag: str
    commit: str
    layout: str
    skill_root: str
    root: str | None
    installed: bool
    tree_sha256: str | None
    blob_count: int | None
    blob_count_basis: str
    license_spdx: str
    agpl_vendored: tuple[str, ...]
    note: str
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def identity(self) -> str:
        """A short, unambiguous label for receipts: tag plus commit prefix."""
        return f"{self.tag}@{self.commit[:12]}"

    @property
    def digest_recorded(self) -> bool:
        return bool(self.tree_sha256)


@dataclass(frozen=True)
class Registry:
    active_id: str
    engines: dict[str, Engine]
    note: str
    path: Path
    workbench_id: str | None = None

    @property
    def active(self) -> Engine:
        return self.engines[self.active_id]


def registry_path(root: Path | str | None = None) -> Path:
    """The registry location for a repository root (default: this checkout)."""
    base = Path(root) if root is not None else Path(__file__).resolve().parents[3]
    return base / REGISTRY_REL


def _require(entry: dict[str, Any], key: str, engine_id: str, errors: list[str]) -> Any:
    value = entry.get(key)
    if value in (None, ""):
        errors.append(f"{engine_id}: missing {key}")
    return value


def _parse_engine(engine_id: str, entry: Any) -> tuple[Engine | None, list[str]]:
    errors: list[str] = []
    if not isinstance(entry, dict):
        return None, [f"{engine_id}: entry must be an object"]

    role = _require(entry, "role", engine_id, errors)
    repo = _require(entry, "repo", engine_id, errors)
    tag = _require(entry, "tag", engine_id, errors)
    commit = _require(entry, "commit", engine_id, errors)
    layout = _require(entry, "layout", engine_id, errors)
    skill_root = _require(entry, "skill_root", engine_id, errors)

    if commit and not isinstance(commit, str):
        errors.append(f"{engine_id}: commit must be a string")
    elif commit and not _HEX40.match(str(commit)):
        errors.append(
            f"{engine_id}: commit {str(commit)[:20]!r} is not a 40-character git object id. "
            "A tag is not an identity; record the commit."
        )

    if layout and layout not in _LAYOUTS:
        errors.append(f"{engine_id}: layout {layout!r} not in {_LAYOUTS}")

    if skill_root and not str(skill_root).startswith("skills/"):
        errors.append(f"{engine_id}: skill_root {skill_root!r} must live under skills/")

    digest = entry.get("tree_sha256")
    if digest is not None and not _HEX64.match(str(digest)):
        errors.append(f"{engine_id}: tree_sha256 is not a 64-character sha256 digest")

    blob_count = entry.get("blob_count")
    if blob_count is not None and not isinstance(blob_count, int):
        errors.append(f"{engine_id}: blob_count must be an integer or null")

    root = entry.get("root")
    if root is not None and Path(str(root)).is_absolute():
        errors.append(
            f"{engine_id}: root {root!r} must be repository-relative; "
            "an absolute path cannot be committed"
        )

    if errors:
        return None, errors

    return (
        Engine(
            engine_id=engine_id,
            role=str(role),
            repo=str(repo),
            tag=str(tag),
            commit=str(commit),
            layout=str(layout),
            skill_root=str(skill_root),
            root=str(root) if root is not None else None,
            installed=bool(entry.get("installed", False)),
            tree_sha256=str(digest) if digest else None,
            blob_count=blob_count,
            blob_count_basis=str(entry.get("blob_count_basis") or ""),
            license_spdx=str(entry.get("license") or ""),
            agpl_vendored=tuple(entry.get("agpl_vendored") or ()),
            note=str(entry.get("note") or ""),
            raw=dict(entry),
        ),
        [],
    )


def load(root: Path | str | None = None) -> Registry:
    """Read and validate the registry. Raises :class:`PinError` on any problem."""
    path = registry_path(root)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PinError(
            f"pin registry missing: {path}. There is no fallback commit: "
            "restore the file instead of hardcoding a version."
        ) from exc
    except (OSError, ValueError) as exc:
        raise PinError(f"pin registry unreadable: {path}: {type(exc).__name__}") from exc

    if not isinstance(data, dict):
        raise PinError(f"pin registry root must be an object: {path}")
    if data.get("schema") != SCHEMA:
        raise PinError(f"pin registry schema mismatch: {data.get('schema')!r} != {SCHEMA!r}")

    entries = data.get("engines")
    if not isinstance(entries, dict) or not entries:
        raise PinError("pin registry must declare a non-empty engines object")

    engines: dict[str, Engine] = {}
    errors: list[str] = []
    for engine_id, entry in entries.items():
        engine, problems = _parse_engine(str(engine_id), entry)
        errors.extend(problems)
        if engine is not None:
            engines[str(engine_id)] = engine

    seen: dict[str, str] = {}
    for engine in engines.values():
        if engine.commit in seen:
            errors.append(
                f"{engine.engine_id}: commit {engine.commit[:12]} already declared by "
                f"{seen[engine.commit]}; one commit must map to one engine"
            )
        seen[engine.commit] = engine.engine_id

    active_id = data.get("active")
    if active_id not in engines:
        errors.append(f"active {active_id!r} is not a declared engine")

    workbench_id = data.get("workbench_engine")
    if workbench_id is not None and workbench_id not in engines:
        errors.append(f"workbench_engine {workbench_id!r} is not a declared engine")

    if errors:
        raise PinError("pin registry invalid: " + "; ".join(errors))

    return Registry(
        active_id=str(active_id),
        engines=engines,
        note=str(data.get("note") or ""),
        path=path,
        workbench_id=str(workbench_id) if workbench_id else None,
    )


def active(root: Path | str | None = None) -> Engine:
    """The engine production resolves. Raises :class:`PinError` if undecidable."""
    return load(root).active


def get(engine_id: str, root: Path | str | None = None) -> Engine:
    """One declared engine by id. Raises :class:`PinError` if it is not declared."""
    registry = load(root)
    try:
        return registry.engines[engine_id]
    except KeyError as exc:
        declared = ", ".join(sorted(registry.engines)) or "none"
        raise PinError(f"engine {engine_id!r} is not declared (declared: {declared})") from exc


def identity(engine_id: str | None = None, root: Path | str | None = None) -> str:
    """`tag@commit12` for one engine, or for the active engine."""
    engine = active(root) if engine_id is None else get(engine_id, root)
    return engine.identity


def workbench(root: Path | str | None = None) -> Engine:
    """The engine declared as the workbench. Raises :class:`PinError` if none is."""
    registry = load(root)
    if not registry.workbench_id:
        raise PinError("no workbench_engine is declared in the pin registry")
    return registry.engines[registry.workbench_id]
