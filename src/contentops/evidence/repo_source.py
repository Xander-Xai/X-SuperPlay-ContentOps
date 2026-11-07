"""Fetch a bounded, immutable evidence snapshot from a public GitHub repository.

The adapter stores only selected text files. It pins every byte to a commit,
records the canonical source URL and digest, and never treats repository
visibility as a usage licence. A source without a recognized SPDX licence is
still captured, but its artifacts use permission ``NONE`` and cannot back a
claim in :class:`ClaimLedger`.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .source_artifact import SourceArtifact, SourceArtifactError

GITHUB_API = "https://api.github.com"
USER_AGENT = "ContentOps/1.0 (+https://github.com/Xander-Xai/X-SuperPlay-ContentOps)"
MAX_FILES = 16
MAX_FILE_BYTES = 128 * 1024
MAX_TOTAL_BYTES = 512 * 1024
LICENSED_SPDX = frozenset({"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC"})
_REPO_URL = re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/?$", re.I)
_SELECTED_NAMES = {
    "readme.md", "license", "license.md", "copying", "pyproject.toml",
    "package.json", "architecture.md", "current-state.md", "prd.md",
    "runbook.md", "quality-standard.md", "motion-workflow-spec.zh-cn.md",
}
_PRIORITY_PATHS = {
    "scripts/produce_video.py", "scripts/m5_production.py",
    "scripts/build_motion_film.py",
    "src/contentops/routing/router.py", "src/contentops/evidence/source_artifact.py",
    "src/contentops/evidence/claim_ledger.py", "src/contentops/media/motion_handoff.py",
    "src/contentops/media/storyboard_adapter.py",
}
_PRIORITY_DOCS = {
    "docs/architecture.md", "docs/current-state.md", "docs/prd.md",
    "docs/runbook.md", "docs/quality-standard.md",
}


class RepoSourceError(ValueError):
    """A repository URL, GitHub response, or snapshot destination was invalid."""


@dataclass(frozen=True)
class RepoSnapshot:
    repository: str
    source_url: str
    commit: str
    default_branch: str
    spdx_license: Optional[str]
    license_permission: str
    files: List[Dict[str, Any]]
    manifest_path: str

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema": "contentops.repo-source-snapshot/v1",
            "repository": self.repository,
            "source_url": self.source_url,
            "commit": self.commit,
            "default_branch": self.default_branch,
            "spdx_license": self.spdx_license,
            "license_permission": self.license_permission,
            "files": self.files,
            "manifest_path": self.manifest_path,
        }


def _request(url: str, *, timeout: float = 20.0,
             opener: Optional[Callable[..., Any]] = None) -> bytes:
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": USER_AGENT,
    })
    open_url = opener or urllib.request.urlopen
    try:
        with open_url(req, timeout=timeout) as response:
            body = response.read(MAX_TOTAL_BYTES + 1)
    except urllib.error.HTTPError as exc:
        detail = "not found" if exc.code == 404 else f"HTTP {exc.code}"
        raise RepoSourceError(f"GitHub source request failed: {detail}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RepoSourceError(f"GitHub source request failed: {type(exc).__name__}") from None
    if len(body) > MAX_TOTAL_BYTES:
        raise RepoSourceError("GitHub response exceeded the 512 KiB request limit")
    return body


def _json(url: str, *, opener: Optional[Callable[..., Any]]) -> Dict[str, Any]:
    try:
        value = json.loads(_request(url, opener=opener).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RepoSourceError("GitHub returned malformed JSON") from None
    if not isinstance(value, dict):
        raise RepoSourceError("GitHub returned an unexpected JSON shape")
    return value


def _choose_files(paths: List[str]) -> List[str]:
    selected = []
    for path in paths:
        parts = path.split("/")
        name = parts[-1].casefold()
        if name in {"license", "license.md", "copying"}:
            selected.append(path)
        elif len(parts) == 1 and name in _SELECTED_NAMES:
            selected.append(path)
        elif path.casefold() in _PRIORITY_PATHS or path.casefold() in _PRIORITY_DOCS:
            selected.append(path)
        elif parts[0].casefold() in {"docs", "src", "config", "runtime"} and (
                name in _SELECTED_NAMES or name.endswith((".py", ".json", ".yaml", ".yml"))):
            selected.append(path)
    # Prefer load-bearing project claims and pipeline code over alphabetically
    # early but generic configuration files.
    def rank(path: str) -> tuple:
        folded = path.casefold()
        name = path.split("/")[-1].casefold()
        if name.startswith(("license", "copying")):
            return (0, folded)
        if folded == "readme.md":
            return (1, folded)
        if folded in _PRIORITY_DOCS:
            return (2, folded)
        if folded in _PRIORITY_PATHS:
            return (3, folded)
        if folded.startswith("config/accounts/"):
            return (4, folded)
        return (5, folded)
    selected = sorted(set(selected), key=lambda p: (
        rank(p)
    ))
    return selected[:MAX_FILES]


class RepoSourceAdapter:
    """Read a public repository and materialize a bounded text evidence pack."""

    def __init__(self, *, opener: Optional[Callable[..., Any]] = None) -> None:
        self._opener = opener

    def fetch(self, source_url: str, *, output_dir: Path,
              repo_root: Path) -> RepoSnapshot:
        match = _REPO_URL.fullmatch(source_url.strip())
        if not match:
            raise RepoSourceError("source URL must be https://github.com/<owner>/<repo>")
        owner, repo = match.groups()
        repo = repo.removesuffix(".git")
        if not repo:
            raise RepoSourceError("repository name is empty")
        canonical = f"https://github.com/{owner}/{repo}"
        source_key = hashlib.sha256(canonical.casefold().encode("utf-8")).hexdigest()[:8]
        api_repo = f"{GITHUB_API}/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}"
        metadata = _json(api_repo, opener=self._opener)
        full_name = str(metadata.get("full_name") or "")
        branch = str(metadata.get("default_branch") or "")
        if full_name.casefold() != f"{owner}/{repo}".casefold() or not branch:
            raise RepoSourceError("GitHub repository metadata did not match the requested repository")
        commit_data = _json(f"{api_repo}/commits/{urllib.parse.quote(branch, safe='')}",
                            opener=self._opener)
        commit = str((commit_data.get("sha") or "")).strip()
        if not re.fullmatch(r"[0-9a-f]{40,64}", commit):
            raise RepoSourceError("GitHub did not provide an immutable commit SHA")
        tree_data = _json(f"{GITHUB_API}/repos/{urllib.parse.quote(owner)}/"
                          f"{urllib.parse.quote(repo)}/git/trees/{commit}?recursive=1",
                          opener=self._opener)
        rows = tree_data.get("tree")
        if not isinstance(rows, list):
            raise RepoSourceError("GitHub tree response did not contain a file list")
        paths = [str(row.get("path")) for row in rows
                 if isinstance(row, dict) and row.get("type") == "blob"
                 and isinstance(row.get("path"), str)]
        selected = _choose_files(paths)
        if not selected:
            raise RepoSourceError("repository contains no supported documentation or source files")

        destination = output_dir.resolve()
        root = repo_root.resolve()
        try:
            destination.relative_to(root)
        except ValueError:
            raise RepoSourceError("snapshot destination must be inside the project repository") from None
        if destination.exists() and any(destination.iterdir()):
            raise RepoSourceError(f"snapshot destination is not empty: {output_dir}")
        license_info = metadata.get("license") or {}
        spdx = str(license_info.get("spdx_id") or "") or None
        permission = "LICENSED" if spdx in LICENSED_SPDX else "NONE"
        refs_path = destination.parent / "source-refs.json"
        existing_refs: List[Dict[str, Any]] = []
        if refs_path.is_file():
            try:
                refs_doc = json.loads(refs_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raise RepoSourceError("existing source-refs.json is unreadable") from None
            if refs_doc.get("schema") != "contentops.m5-source-refs/v1" \
                    or not isinstance(refs_doc.get("refs"), list):
                raise RepoSourceError("existing source-refs.json has an unsupported schema")
            existing_refs = list(refs_doc["refs"])
        existing_ids = {str(item.get("id")) for item in existing_refs
                        if isinstance(item, dict)}
        prospective_ids = {f"repo-{source_key}-{index:02d}"
                           for index in range(1, len(selected) + 1)}
        if existing_ids & prospective_ids:
            raise RepoSourceError("source artifact id conflicts with existing source refs")
        temp_files: List[tuple[str, bytes]] = []
        total = 0
        for path in selected:
            encoded_path = "/".join(urllib.parse.quote(part, safe="") for part in path.split("/"))
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{commit}/{encoded_path}"
            body = self._raw(raw_url)
            if len(body) > MAX_FILE_BYTES:
                continue
            try:
                body.decode("utf-8")
            except UnicodeDecodeError:
                continue
            total += len(body)
            if total > MAX_TOTAL_BYTES:
                break
            temp_files.append((path, body))
        if not temp_files:
            raise RepoSourceError("selected repository files were empty or not UTF-8 text")

        artifacts: List[Dict[str, Any]] = []
        refs: List[Dict[str, Any]] = []
        for index, (path, body) in enumerate(temp_files, start=1):
            target = destination / "files" / path
            try:
                target.resolve().relative_to(destination)
            except ValueError:
                raise RepoSourceError("repository path escaped snapshot destination") from None
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
            artifact = SourceArtifact.from_path(
                id=f"repo-{source_key}-{index:02d}", source_type="github_repo_file",
                title=f"{full_name}/{path}", path=target, repo_root=root,
                permission=permission,
                notes=f"source={canonical}/blob/{commit}/{path}; SPDX={spdx or 'NOASSERTION'}",
            )
            artifacts.append({
                **artifact.as_dict(),
                "type": artifact.source_type,
                "source_url": f"{canonical}/blob/{commit}/{path}",
                "source_repository": full_name,
                "source_commit": commit,
            })
            refs.append({
                "id": artifact.id,
                "type": artifact.source_type,
                "title": artifact.title,
                "path": artifact.path,
                "sha256": artifact.sha256,
                "bytes": artifact.bytes,
                "permission": artifact.permission,
                "notes": artifact.notes,
                "source_url": f"{canonical}/blob/{commit}/{path}",
                "source_commit": commit,
            })
        manifest = {
            "schema": "contentops.repo-source-snapshot/v1",
            "repository": full_name,
            "source_url": canonical,
            "commit": commit,
            "default_branch": branch,
            "spdx_license": spdx,
            "license_permission": permission,
            "files": artifacts,
            "source_refs": refs,
        }
        manifest_path = destination / "source-manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
        combined_refs = existing_refs + refs
        refs_path.write_text(json.dumps({
            "schema": "contentops.m5-source-refs/v1", "refs": combined_refs,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return RepoSnapshot(full_name, canonical, commit, branch, spdx, permission,
                            artifacts, manifest_path.relative_to(root).as_posix())

    def _raw(self, url: str) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        opener = self._opener or urllib.request.urlopen
        try:
            with opener(request, timeout=20.0) as response:
                return response.read(MAX_FILE_BYTES + 1)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RepoSourceError(f"GitHub file request failed: {type(exc).__name__}") from None


__all__ = ["RepoSnapshot", "RepoSourceAdapter", "RepoSourceError"]
