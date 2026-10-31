"""A source a claim may cite: what it is, where it is, and who may use it.

The point of this record is to make "the video says X" traceable to a file whose
bytes are pinned. It deliberately carries no judgement about truth — only
provenance, permission and a content hash.

`evidence_capable` is derived, never asserted: an artifact can carry a factual
claim only when its permission is one that allows it. Generated media, stock
footage with no recorded licence, and anything with `permission: NONE` are
timestamped and hashed but cannot back a claim.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

ARTIFACT_SCHEMA = "contentops.source-artifact/v1"

#: A permission that permits an artifact to back a factual claim. `NONE` means
#: "owned copy exists but rights are unclear" — useful as material, never as
#: evidence.
EVIDENCE_CAPABLE_PERMISSIONS = frozenset({"OWNED", "CREATED_BY_OWNER", "LICENSED"})
PERMISSIONS = EVIDENCE_CAPABLE_PERMISSIONS | {"NONE"}

TEXT_SUFFIXES = frozenset({".md", ".txt", ".json", ".yaml", ".yml", ".py", ".csv"})


class SourceArtifactError(ValueError):
    """A source artifact is missing, unreadable or misdeclared."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class SourceArtifact:
    id: str
    source_type: str
    title: str
    path: str
    sha256: str
    bytes: int
    permission: str
    captured_at: str
    evidence_capable: bool
    notes: str = ""
    locators: tuple = field(default_factory=tuple)

    @classmethod
    def from_path(
        cls,
        *,
        id: str,
        source_type: str,
        title: str,
        path: Path,
        repo_root: Path,
        permission: str,
        notes: str = "",
        captured_at: Optional[str] = None,
    ) -> "SourceArtifact":
        if permission not in PERMISSIONS:
            raise SourceArtifactError(f"{id}: unknown permission {permission!r}")
        resolved = path.resolve()
        if not resolved.is_file():
            raise SourceArtifactError(f"{id}: source is not a file: {path}")
        try:
            relative = resolved.relative_to(repo_root.resolve()).as_posix()
        except ValueError as exc:
            raise SourceArtifactError(f"{id}: source lies outside the repository: {path}") from exc
        return cls(
            id=id,
            source_type=source_type,
            title=title,
            path=relative,
            sha256=_sha256(resolved),
            bytes=resolved.stat().st_size,
            permission=permission,
            captured_at=captured_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            evidence_capable=permission in EVIDENCE_CAPABLE_PERMISSIONS,
            notes=notes,
        )

    def text(self, repo_root: Path) -> Optional[str]:
        """The artifact's text, when it is a text file this verifier may read."""
        if Path(self.path).suffix.lower() not in TEXT_SUFFIXES:
            return None
        try:
            return (repo_root / self.path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def verify_bytes(self, repo_root: Path) -> bool:
        target = repo_root / self.path
        return target.is_file() and _sha256(target) == self.sha256

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_type": self.source_type,
            "title": self.title,
            "path": self.path,
            "sha256": self.sha256,
            "bytes": self.bytes,
            "permission": self.permission,
            "captured_at": self.captured_at,
            "evidence_capable": self.evidence_capable,
            "notes": self.notes,
        }


def build_artifacts(
    refs: Iterable[Mapping[str, Any]], *, repo_root: Path
) -> Dict[str, SourceArtifact]:
    """Build artifacts from a project's `source_refs`, rejecting duplicates."""
    artifacts: Dict[str, SourceArtifact] = {}
    for ref in refs:
        missing = {"id", "type", "title", "path", "permission"} - set(ref)
        if missing:
            raise SourceArtifactError(f"source ref misses {sorted(missing)}: {dict(ref)}")
        artifact = SourceArtifact.from_path(
            id=str(ref["id"]),
            source_type=str(ref["type"]),
            title=str(ref["title"]),
            path=repo_root / str(ref["path"]),
            repo_root=repo_root,
            permission=str(ref["permission"]),
            notes=str(ref.get("notes") or ""),
        )
        if artifact.id in artifacts:
            raise SourceArtifactError(f"duplicate source id: {artifact.id}")
        artifacts[artifact.id] = artifact
    return artifacts
