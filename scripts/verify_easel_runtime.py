#!/usr/bin/env python3
"""Prove the local Easel runtime is byte-identical to upstream at the pinned commit.

A GitHub release archive carries no `.git`, so `git rev-parse HEAD` cannot answer
"which commit is this?" for `.runtime/easel`. This script answers the question
from content instead: every local file is hashed the way git hashes a blob
(sha1 of `"blob <len>\\0" + bytes`) and compared against the upstream tree API
for the pinned commit.

That keeps the pin falsifiable without .git metadata. A swapped, patched or
half-extracted tree yields MISSING / MISMATCH / EXTRA entries instead of a
silent pass — which matters because AGENTS.md §1.6 pins Easel at v0.2.1 and
forbids upgrading it without the Founder's explicit consent.

Exit codes:  0 verified   1 not verified   3 could not verify (offline / API unavailable)

Overlay mode (`--overlay runtime/easel-workbench-overlay.json`)
-----------------------------------------------------------------
A workbench instance is Easel plus local tuning: account profiles, an
overridden skill. The strict comparison above cannot express that, because
"any local difference" means MISMATCH — so a tuned instance could never be
proved.

Overlay mode separates the two layers instead of weakening the comparison:

* the **upstream baseline** must match the upstream commit byte for byte;
* the **overlay** differs from upstream and, when digests are recorded, must
  match the declared SHA-256 values;
* anything else that differs is still a failure.

Generated files, including frontend build output, are excluded and are not
proven by this comparison.
"""

import argparse
import hashlib
import importlib.util
import io
import json
import os
import re
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
from contentops.easel.path_safety import is_linklike as _linklike  # noqa: E402
RUNTIME = ROOT / ".runtime" / "easel"
OVERLAY_RECORD = ROOT / "runtime" / "easel-workbench-overlay.json"
WORKBENCH_TREE_CACHE = ROOT / "runtime" / "easel-workbench-upstream-tree.json"
FRONTEND_BUILD_POLICY = ROOT / "runtime" / "easel-workbench-build-policy.json"
REPO = "ZJU-REAL/Easel"
PINNED_TAG = "v0.2.1"
PINNED_COMMIT = "3fe2d9904c1619281ef57f81d9ee0b7854998399"

# Paths the pipeline itself writes into the runtime tree. They are expected to
# differ from upstream and are excluded from the comparison; everything else
# must match exactly.
GENERATED_PREFIXES = ("outputs/",)
GENERATED_NAMES = {".DS_Store"}
GENERATED_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache"}
UNSAFE_LINK_BLOB = "UNSAFE_LINK"
MAX_UPSTREAM_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_UPSTREAM_ARCHIVE_MEMBERS = 20_000
MAX_UPSTREAM_EXTRACTED_BYTES = 2 * 1024 * 1024 * 1024


def blob_sha1(path: Path) -> str:
    """git's blob object id: sha1('blob <size>\\0' + content)."""
    if _linklike(path):
        raise OSError(f"refusing to hash linked path: {path}")
    data = path.read_bytes()
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


def upstream_tree_sha256(tree: dict[str, str]) -> str:
    """Stable digest of the sorted path-to-Git-blob map for one source tree."""
    serialized = "".join(f"{path}\0{tree[path]}\n" for path in sorted(tree))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def verify_upstream_license(instance_root: Path, metadata: dict) -> dict:
    """Verify the recorded SPDX license file without following linked paths."""
    if not isinstance(metadata, dict):
        return {"status": "MISMATCH", "spdx": None, "file": None,
                "sha256": None, "detected_spdx": None, "unsafe": True}
    rel = metadata.get("file")
    if not isinstance(rel, str) or "\\" in rel or ":" in rel:
        return {"status": "MISMATCH", "spdx": metadata.get("spdx"),
                "file": rel, "sha256": None, "detected_spdx": None, "unsafe": True}
    pure = PurePosixPath(rel)
    if (pure.is_absolute() or not pure.parts
            or any(part in ("", ".", "..") for part in pure.parts)):
        return {"status": "MISMATCH", "spdx": metadata.get("spdx"),
                "file": rel, "sha256": None, "detected_spdx": None, "unsafe": True}
    candidate = Path(instance_root)
    if _linklike(candidate):
        return {"status": "MISMATCH", "spdx": metadata.get("spdx"),
                "file": rel, "sha256": None, "detected_spdx": None, "unsafe": True}
    try:
        candidate = candidate.resolve(strict=True)
        for part in pure.parts:
            candidate = candidate / part
            if _linklike(candidate):
                return {"status": "MISMATCH", "spdx": metadata.get("spdx"),
                        "file": rel, "sha256": None, "detected_spdx": None, "unsafe": True}
        if not candidate.is_file():
            return {"status": "MISMATCH", "spdx": metadata.get("spdx"),
                    "file": rel, "sha256": None, "detected_spdx": None, "unsafe": False}
        content = candidate.read_bytes()
        actual = hashlib.sha256(content).hexdigest()
    except OSError:
        return {"status": "MISMATCH", "spdx": metadata.get("spdx"),
                "file": rel, "sha256": None, "detected_spdx": None, "unsafe": False}
    header = content[:4096].decode("utf-8", errors="replace")
    detected = ("Apache-2.0" if re.search(
        r"\bApache\s+License\b[\s\S]{0,256}\bVersion\s+2\.0\b",
        header, re.IGNORECASE) else None)
    matches = actual == metadata.get("sha256") and detected == metadata.get("spdx")
    return {"status": "VERIFIED" if matches else "MISMATCH",
            "spdx": metadata.get("spdx"), "file": rel,
            "sha256": actual, "detected_spdx": detected, "unsafe": False}


def walk_local(runtime_dir: Path, skip: Optional[set[str]] = None) -> dict[str, str]:
    """Map repo-relative posix path -> blob sha1 for every tracked-worthy file.

    ``skip`` names extra directories/prefixes that are install or build output.
    A workbench instance passes its overlay's generated set so a full
    ``node_modules`` tree is never hashed — neither useful nor fast.
    """
    out: dict[str, str] = {}
    skip = skip or set()
    root = Path(runtime_dir)
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in sorted(entries, key=lambda item: item.name):
                path = Path(entry.path)
                rel = path.relative_to(root).as_posix()
                if _is_generated(rel) or rel.endswith(".pyc"):
                    continue
                # `pip install -e .` writes an <pkg>.egg-info/ directory of
                # metadata. Exclude files inside it, as before.
                if any(part.endswith(".egg-info") for part in rel.split("/")):
                    continue
                if skip and _in_generated(rel, skip):
                    continue
                if _linklike(path):
                    # Keep a sentinel so comparisons fail without following a
                    # link and reading bytes outside this tree.
                    out[rel] = UNSAFE_LINK_BLOB
                    continue
                if entry.is_dir(follow_symlinks=False):
                    pending.append(path)
                elif entry.is_file(follow_symlinks=False):
                    out[rel] = blob_sha1(path)
    return out


def fetch_upstream_tree(repo: str, commit: str) -> dict[str, str]:
    """Fetch {path: blob_sha} for a commit via the GitHub API.

    This is an unauthenticated direct HTTPS request to public repository data.
    It deliberately bypasses CLI credentials and environment/system proxies.
    Raises RuntimeError when the tree cannot be fetched. Callers must treat
    that as "could not verify", never as a pass.
    """
    if not isinstance(repo, str) or not re.fullmatch(
            r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise RuntimeError("invalid GitHub repository identifier")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        raise RuntimeError("invalid upstream commit identifier")
    data = _github_public_json(
        f"repos/{repo}/git/trees/{commit}?recursive=1", timeout=120)
    if data.get("truncated"):
        raise RuntimeError("upstream tree response was truncated — refusing a partial compare")
    entries = data.get("tree")
    if not isinstance(entries, list):
        raise RuntimeError("upstream tree response has no file list")
    # Apply the same exclusions as walk_local so the two sides stay symmetric:
    # an asymmetry here reports excluded files as spurious "missing" entries.
    result = {}
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("type") != "blob":
            continue
        path, sha = entry.get("path"), entry.get("sha")
        pure = PurePosixPath(path) if isinstance(path, str) else None
        if (pure is None or pure.is_absolute() or "\\" in path or ":" in path
                or any(part in ("", ".", "..") for part in pure.parts)
                or not re.fullmatch(r"[0-9a-fA-F]{40}", str(sha or ""))):
            raise RuntimeError("upstream tree response contains an unsafe file entry")
        if not _is_generated(path):
            result[path] = sha
    return result


def _tree_from_commit_archive(archive: io.BufferedIOBase | io.BytesIO,
                              commit: str) -> dict[str, str]:
    """Build Git blob IDs from a safe source archive for a fixed commit."""
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        raise RuntimeError("invalid upstream commit identifier")
    try:
        with tarfile.open(fileobj=archive, mode="r|gz") as bundle:
            result: dict[str, str] = {}
            total = 0
            count = 0
            root: str | None = None
            seen: set[str] = set()
            for member in bundle:
                count += 1
                if count > MAX_UPSTREAM_ARCHIVE_MEMBERS:
                    raise RuntimeError("upstream archive has too many members")
                name = member.name.rstrip("/")
                raw_parts = name.split("/")
                pure = PurePosixPath(name)
                if ("\\" in name or "\x00" in name or ":" in name
                        or pure.is_absolute() or not raw_parts
                        or any(part in ("", ".", "..") for part in raw_parts)):
                    raise RuntimeError("upstream archive contains an unsafe path")
                if root is None:
                    root = raw_parts[0]
                elif raw_parts[0] != root:
                    raise RuntimeError("upstream archive does not have one root directory")
                if not (member.isdir() or member.isfile()):
                    raise RuntimeError("upstream archive contains a link or special file")
                if member.isdir():
                    continue
                rel = "/".join(raw_parts[1:])
                if not rel or rel in seen:
                    raise RuntimeError("upstream archive contains an empty or duplicate file path")
                seen.add(rel)
                total += member.size
                if total > MAX_UPSTREAM_EXTRACTED_BYTES:
                    raise RuntimeError("upstream archive exceeds the expanded size limit")
                source = bundle.extractfile(member)
                if source is None:
                    raise RuntimeError("upstream archive file could not be read")
                with source:
                    digest = hashlib.sha1()
                    digest.update(b"blob %d\0" % member.size)
                    remaining = member.size
                    while remaining:
                        chunk = source.read(min(1024 * 1024, remaining))
                        if not chunk:
                            raise RuntimeError("upstream archive file was truncated")
                        digest.update(chunk)
                        remaining -= len(chunk)
                    if source.read(1):
                        raise RuntimeError("upstream archive file exceeded its declared size")
                if not _is_generated(rel):
                    result[rel] = digest.hexdigest()
            if root is None:
                raise RuntimeError("upstream archive is empty")
            return result
    except (OSError, tarfile.TarError) as exc:
        raise RuntimeError(f"upstream archive could not be parsed ({type(exc).__name__})") from None


def fetch_upstream_archive_tree(repo: str, commit: str) -> dict[str, str]:
    """Fetch codeload's exact commit archive without auth or ambient proxies."""
    if not isinstance(repo, str) or not re.fullmatch(
            r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise RuntimeError("invalid GitHub repository identifier")
    if not isinstance(commit, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", commit):
        raise RuntimeError("invalid upstream commit identifier")
    request = urllib.request.Request(
        f"https://codeload.github.com/{repo}/tar.gz/{commit}",
        headers={"User-Agent": "ContentOps-Easel-runtime-verifier",
                 "Accept": "application/vnd.github+json"},
        method="GET",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=180) as response:
            final = urllib.parse.urlsplit(response.geturl())
            if (final.scheme != "https" or final.netloc.lower() != "codeload.github.com"
                    or final.path != f"/{repo}/tar.gz/{commit}"):
                raise RuntimeError("commit archive redirected outside codeload.github.com")
            with tempfile.SpooledTemporaryFile(max_size=16 * 1024 * 1024) as archive:
                total = 0
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_UPSTREAM_ARCHIVE_BYTES:
                        raise RuntimeError("upstream archive exceeds the download size limit")
                    archive.write(chunk)
                if not total:
                    raise RuntimeError("upstream archive download was empty")
                archive.seek(0)
                return _tree_from_commit_archive(archive, commit)
    except RuntimeError:
        raise
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GitHub commit archive returned HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"GitHub commit archive request failed ({type(exc).__name__})") from None


def _github_public_json(endpoint: str, timeout: int) -> dict:
    """Read public GitHub JSON without auth headers, CLI state or proxy env."""
    if (not isinstance(endpoint, str) or endpoint.startswith("/")
            or "\\" in endpoint or any(part == ".." for part in endpoint.split("/"))):
        raise RuntimeError("invalid public GitHub API endpoint")
    request = urllib.request.Request(
        "https://api.github.com/" + endpoint,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ContentOps-Easel-runtime-verifier",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="GET",
    )
    # Do not let urllib consult HTTP(S)_PROXY or Windows proxy settings: an
    # ambient proxy may itself be credentialed. If direct HTTPS is unavailable,
    # verification fails closed and the caller must not serve.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            final_url = urllib.parse.urlsplit(response.geturl())
            if final_url.scheme != "https" or final_url.netloc.lower() != "api.github.com":
                raise RuntimeError("GitHub public API redirected outside api.github.com")
            if getattr(response, "status", 200) != 200:
                raise RuntimeError("GitHub public API returned a non-success status")
            payload = response.read()
    except RuntimeError:
        raise
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"GitHub public API returned HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(
            f"GitHub public API request failed ({type(exc).__name__})") from None
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError("GitHub public API returned invalid JSON") from None
    if not isinstance(data, dict):
        raise RuntimeError("GitHub public API returned an unexpected JSON shape")
    return data


def _is_generated(rel: str) -> bool:
    parts = rel.split("/")
    if any(part in GENERATED_DIRS for part in parts):
        return True
    if parts[-1] in GENERATED_NAMES:
        return True
    # outputs/ is the pipeline's write area, but the shipped outputs/.gitkeep is
    # a real upstream file — keep it in the comparison so the blob count covers
    # the entire upstream tree (982 for v0.2.1).
    return rel.startswith(GENERATED_PREFIXES) and rel != "outputs/.gitkeep"


def resolve_tag_commit(repo: str, tag: str) -> str:
    """Peel a public lightweight or annotated tag to its commit."""
    if not isinstance(repo, str) or not re.fullmatch(
            r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise RuntimeError("invalid GitHub repository identifier")
    if (not isinstance(tag, str) or not tag
            or not re.fullmatch(r"[A-Za-z0-9_./-]+", tag)
            or any(part in ("", ".", "..") for part in tag.split("/"))):
        raise RuntimeError("invalid upstream tag identifier")
    quoted_tag = urllib.parse.quote(tag, safe="/-_.")
    data = _github_public_json(f"repos/{repo}/git/ref/tags/{quoted_tag}", timeout=60)
    target = data.get("object")
    if not isinstance(target, dict):
        raise RuntimeError("GitHub tag response has no object")
    sha, kind = target.get("sha"), target.get("type")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", sha):
        raise RuntimeError("GitHub tag response has an invalid object identifier")
    if kind == "tag":  # annotated: one more hop to the commit
        peeled = _github_public_json(f"repos/{repo}/git/tags/{sha}", timeout=60)
        target = peeled.get("object")
        sha = target.get("sha") if isinstance(target, dict) else None
        kind = target.get("type") if isinstance(target, dict) else None
    if kind != "commit" or not isinstance(sha, str) or not re.fullmatch(
            r"[0-9a-fA-F]{40}", sha):
        raise RuntimeError("GitHub tag does not resolve to a commit")
    return sha


def verify(runtime_dir: Path = RUNTIME, repo: str = REPO,
           commit: str = PINNED_COMMIT) -> dict:
    """Compare the local runtime tree against upstream at `commit`."""
    result: dict = {
        "runtime_dir": str(runtime_dir),
        "repo": repo,
        "expected_commit": commit,
        "expected_tag": PINNED_TAG,
    }
    if not runtime_dir.is_dir():
        return {**result, "status": "MISSING",
                "reason": f"no runtime at {runtime_dir}"}
    if _linklike(runtime_dir):
        return {**result, "status": "MISMATCH",
                "reason": "runtime root may not be a symlink or junction"}

    if (runtime_dir / ".git").exists():
        # A .git dir means this is not the archive layout; content compare still
        # works, but record it so the provenance file is not misleading.
        result["has_git_metadata"] = True

    try:
        upstream = fetch_upstream_tree(repo, commit)
    except RuntimeError as e:
        return {**result, "status": "UNVERIFIED", "reason": str(e),
                "note": "content identity could not be confirmed; this is not a pass"}

    local = walk_local(runtime_dir)
    unsafe_links = sorted(path for path, digest in local.items()
                          if digest == UNSAFE_LINK_BLOB)

    missing = sorted(set(upstream) - set(local))
    extra = sorted(set(local) - set(upstream))
    mismatch = sorted(p for p in (set(local) & set(upstream)) if local[p] != upstream[p])

    ok = not (missing or extra or mismatch or unsafe_links)
    result.update({
        "status": "VERIFIED" if ok else "MISMATCH",
        "upstream_blob_count": len(upstream),
        "local_blob_count": len(local),
        "matched": len(set(local) & set(upstream)) - len(mismatch),
        "missing": missing[:20],
        "missing_count": len(missing),
        "mismatch": mismatch[:20],
        "mismatch_count": len(mismatch),
        "extra": extra[:20],
        "extra_count": len(extra),
        "unsafe_links": unsafe_links,
        "unsafe_link_count": len(unsafe_links),
        "method": "blob_sha1_tree_compare",
    })
    if not ok:
        result["reason"] = (f"{len(mismatch)} mismatched / {len(missing)} missing / "
                            f"{len(extra)} extra vs upstream {commit[:7]}")
    return result


def load_overlay(path: Path = OVERLAY_RECORD) -> dict:
    """Read the overlay record. A missing or malformed record is an empty
    declaration rather than a crash: the caller decides what that means."""
    target = Path(path)
    if _linklike(target) or _linklike(target.parent):
        return {"readable": False, "path": str(target),
                "reason": "overlay record path contains a link"}
    if not target.is_file():
        return {"readable": False, "path": str(target)}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"readable": False, "path": str(target)}
    if not isinstance(data, dict):
        return {"readable": False, "path": str(target)}
    data["readable"] = True
    return data


def workbench_path(overlay: dict) -> Path:
    """Where the workbench instance lives. The environment variable wins so a
    machine with a different layout can point at it without editing the
    tracked record."""
    instance = overlay.get("instance") or {}
    if not isinstance(instance, dict):
        raise ValueError("workbench instance must be an object")
    env_name = instance.get("path_env") or ""
    if not isinstance(env_name, str):
        raise ValueError("workbench path environment variable name must be text")
    if env_name:
        value = os.environ.get(env_name, "").strip()
        if value:
            path = Path(value).expanduser()
            if not path.is_absolute():
                raise ValueError("workbench path must be absolute")
            return path
    raw = instance.get("path") or ""
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("workbench path is missing")
    path = Path(raw.strip()).expanduser()
    if not path.is_absolute():
        raise ValueError("workbench path must be absolute")
    return path


def _overlay_rules(overlay: dict) -> tuple[set[str], set[str], set[str]]:
    """The three path sets the overlay record declares.

    Returns (overlay files, overlay directories, generated directories).
    """
    body = overlay.get("overlay") or {}
    files = {str(p).replace("\\", "/").strip("/")
             for p in (body.get("files") or [])}
    dirs = {str(p).replace("\\", "/").strip("/")
            for p in (body.get("directories") or [])}
    generated = {str(p).replace("\\", "/").strip("/")
                 for p in ((overlay.get("generated") or {}).get("directories") or [])}
    return files, dirs, generated


def _in_overlay(rel: str, files: set[str], dirs: set[str]) -> bool:
    if rel in files:
        return True
    for directory in dirs:
        if rel == directory or rel.startswith(directory + "/"):
            return True
    return False


def _in_generated(rel: str, generated: set[str]) -> bool:
    """Whether a path is install/build output, never compared against upstream.

    Entries may be a single segment (``node_modules`` matches at any depth) or a
    path prefix (``web/frontend/dist`` matches the directory and everything
    under it). The prefix form is needed because a build output like the React
    bundle is not a top-level directory name.
    """
    parts = rel.split("/")
    if any(part in generated for part in parts):
        return True
    for entry in generated:
        if "/" in entry and (rel == entry or rel.startswith(entry + "/")):
            return True
    return False


def verify_overlay_sources(overlay: dict, source_root: Path = ROOT) -> dict:
    """Verify repository-owned source copies for declared overlay files.

    The workbench digest proves what is installed; this second binding proves
    that reviewed source exists in the repository from which a later rebuild
    can be made. Profiles are generated from DNA and are not source_files.
    """
    body = overlay.get("overlay") or {}
    sources = body.get("source_files")
    if sources is None:
        return {"status": "NOT_DECLARED", "checked": [], "missing": [],
                "mismatched": [], "unsafe": []}
    if not isinstance(sources, dict):
        return {"status": "MISMATCH", "checked": [], "missing": [],
                "mismatched": [], "unsafe": ["source_files"]}

    files = {str(p).replace("\\", "/").strip("/")
             for p in (body.get("files") or [])}
    digests = body.get("digests") or {}
    if not isinstance(digests, dict):
        digests = {}
    missing: list[str] = []
    mismatched: list[str] = []
    unsafe: list[str] = []
    checked: list[str] = []
    try:
        root = Path(source_root)
        if _linklike(root):
            raise ValueError("source root is a link")
        root = root.resolve(strict=True)
    except (OSError, ValueError):
        return {"status": "MISMATCH", "checked": [], "missing": [],
                "mismatched": [], "unsafe": sorted(files or {"source_root"})}

    if set(sources) != files:
        unsafe.extend(sorted(files.symmetric_difference(sources)))
    for target in sorted(set(sources) & files):
        source_rel = sources[target]
        if not isinstance(source_rel, str) or "\\" in source_rel or ":" in source_rel:
            unsafe.append(target)
            continue
        pure = PurePosixPath(source_rel)
        if (pure.is_absolute() or not pure.parts
                or any(part in ("", ".", "..") for part in pure.parts)):
            unsafe.append(target)
            continue
        candidate = root
        for part in pure.parts:
            candidate = candidate / part
            if _linklike(candidate):
                unsafe.append(target)
                break
        else:
            if not candidate.is_file():
                missing.append(target)
                continue
            try:
                actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
            except OSError:
                missing.append(target)
                continue
            checked.append(target)
            if actual != digests.get(target):
                mismatched.append(target)

    return {"status": "VERIFIED" if not (missing or mismatched or unsafe) else "MISMATCH",
            "checked": checked, "missing": sorted(missing),
            "mismatched": sorted(mismatched), "unsafe": sorted(unsafe)}


def load_workbench_tree_cache(path: Path, *, commit: str, tree_sha256: str,
                              expected_count: int | None) -> dict[str, str]:
    """Load an exhaustive tree only if its digest matches the pinned record."""
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate cache key")
            result[key] = value
        return result

    if _linklike(path) or _linklike(path.parent) or not path.is_file() or path.stat().st_size > 2_000_000:
        raise ValueError("upstream tree cache is unavailable or unsafe")
    data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    if (not isinstance(data, dict) or data.get("schema") != "contentops.easel-upstream-tree/v1"
            or data.get("commit") != commit or not isinstance(data.get("files"), dict)):
        raise ValueError("upstream tree cache identity is invalid")
    files = data["files"]
    for name, digest in files.items():
        pure = PurePosixPath(name)
        if (not name or pure.is_absolute() or "\\" in name or ":" in name
                or any(part in ("", ".", "..") for part in name.split("/"))
                or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{40}", digest)
                or _is_generated(name)):
            raise ValueError("upstream tree cache contains an invalid entry")
    if (not re.fullmatch(r"[0-9a-f]{64}", str(tree_sha256 or ""))
            or upstream_tree_sha256(files) != tree_sha256
            or (expected_count is not None and len(files) != expected_count)):
        raise ValueError("upstream tree cache does not match pinned tree digest")
    return files


def verify_overlay(record_path: Path = OVERLAY_RECORD,
                   repo: str = REPO,
                   profile_mode: str = "observed",
                   workbench_override: Path | None = None) -> dict:
    """Verify a workbench instance: upstream baseline + recorded tuning.

    The upstream files must match the upstream commit. The files and
    directories the record names as ours are reported separately. Everything
    else must match upstream, so an unrecorded edit is still a failure.
    """
    overlay = load_overlay(record_path)
    result: dict = {
        "mode": "overlay",
        "record": str(record_path),
        "record_readable": bool(overlay.get("readable")),
        "profile_mode": profile_mode,
    }
    if profile_mode not in {"observed", "generated"}:
        result["status"] = "UNVERIFIED"
        result["reason"] = "profile mode must be observed or generated"
        return result
    if not overlay.get("readable"):
        result["status"] = "UNVERIFIED"
        result["reason"] = f"overlay record not readable: {record_path}"
        return result

    upstream_meta = overlay.get("upstream") or {}
    commit = upstream_meta.get("commit") or ""
    if not commit:
        result["status"] = "UNVERIFIED"
        result["reason"] = "overlay record names no upstream commit"
        return result

    try:
        instance = Path(workbench_override).expanduser() if workbench_override else workbench_path(overlay)
        if not instance.is_absolute():
            raise ValueError("workbench path must be absolute")
    except (TypeError, ValueError, OSError) as exc:
        result["status"] = "UNVERIFIED"
        result["reason"] = str(exc)
        return result
    result["workbench_path"] = str(instance)
    result["expected_commit"] = commit
    result["expected_tag"] = upstream_meta.get("tag")

    if not instance.is_dir():
        result["status"] = "MISSING"
        result["reason"] = f"no workbench instance at {instance}"
        return result
    if _linklike(instance):
        result["status"] = "MISMATCH"
        result["reason"] = "workbench root may not be a symlink or junction"
        return result

    expected_tree_digest = upstream_meta.get("tree_sha256")
    try:
        upstream = load_workbench_tree_cache(
            WORKBENCH_TREE_CACHE, commit=commit, tree_sha256=expected_tree_digest,
            expected_count=upstream_meta.get("tree_blob_count"))
        result["upstream_source"] = "pinned_local_tree_cache"
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        upstream = None
    if upstream is None:
        try:
            upstream = fetch_upstream_tree(repo, commit)
            result["upstream_source"] = "github_tree_api"
        except RuntimeError as api_error:
            # A commit archive is accepted only against the pinned tree digest.
            if not isinstance(expected_tree_digest, str) or not re.fullmatch(
                    r"[0-9a-f]{64}", expected_tree_digest):
                result["status"] = "UNVERIFIED"
                result["reason"] = str(api_error)
                result["note"] = "content identity could not be confirmed; this is not a pass"
                return result
            try:
                upstream = fetch_upstream_archive_tree(repo, commit)
            except RuntimeError as archive_error:
                result["status"] = "UNVERIFIED"
                result["reason"] = (f"GitHub tree API unavailable ({api_error}); "
                                    f"commit archive unavailable ({archive_error})")
                result["note"] = "content identity could not be confirmed; this is not a pass"
                return result
            result["upstream_source"] = "codeload_commit_archive"

    tree_digest = upstream_tree_sha256(upstream)
    result["upstream_tree_blob_count"] = len(upstream)
    result["upstream_tree_sha256"] = tree_digest
    license_meta = upstream_meta.get("license")
    license_check = (verify_upstream_license(instance, license_meta)
                     if license_meta is not None else {"status": "NOT_DECLARED"})
    result["upstream_license"] = license_check
    if expected_tree_digest and expected_tree_digest != tree_digest:
        result["status"] = "MISMATCH"
        result["reason"] = "upstream path/blob tree summary does not match the recorded digest"
        return result

    files, dirs, generated = _overlay_rules(overlay)
    result["overlay_files"] = sorted(files)
    result["overlay_directories"] = sorted(dirs)

    local = walk_local(instance, skip=generated)
    unsafe_links = sorted(path for path, digest in local.items()
                          if digest == UNSAFE_LINK_BLOB)

    # The upstream baseline is compared with the overlay and generated paths
    # taken out of BOTH sides, so the two sides stay symmetric.
    def baseline(path: str) -> bool:
        return not _in_overlay(path, files, dirs) and not _in_generated(path, generated)

    baseline_upstream = {p: sha for p, sha in upstream.items() if baseline(p)}
    baseline_local = {p: sha for p, sha in local.items() if baseline(p)}

    missing = sorted(set(baseline_upstream) - set(baseline_local))
    extra = sorted(set(baseline_local) - set(baseline_upstream))
    mismatch = sorted(p for p in (set(baseline_local) & set(baseline_upstream))
                      if baseline_local[p] != baseline_upstream[p])

    # The tuning layer, reported as what it is rather than as a failure.
    overlay_present = sorted(p for p in local if _in_overlay(p, files, dirs))
    digests = (overlay.get("overlay") or {}).get("digests") or {}
    if not isinstance(digests, dict):
        return {**result, "status": "UNVERIFIED", "reason": "overlay digests must be an object"}
    if (files or dirs) and not digests:
        return {**result, "status": "UNVERIFIED",
                "reason": "every declared overlay must have per-file SHA-256 digests"}
    expected_digests = dict(digests)
    profile_freshness = {"status": "NOT_CHECKED", "accounts": {}}
    if profile_mode == "generated":
        generated_profiles = overlay.get("generated_profiles") or {}
        generated_digests = generated_profiles.get("digests")
        if not isinstance(generated_digests, dict) or not generated_digests:
            return {**result, "status": "UNVERIFIED",
                    "reason": "generated profile digests are missing"}
        accounts = generated_profiles.get("accounts")
        required_profile_names = {
            "identity.md", "style.md", "audience.md", "platforms.md",
            "preferences.md", "memory.md",
        }
        if (not isinstance(accounts, list) or not accounts
                or any(not isinstance(account, str)
                       or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", account)
                       for account in accounts)):
            return {**result, "status": "UNVERIFIED",
                    "reason": "generated profile accounts are missing or invalid"}
        expected_profile_paths = {
            f"profiles/{account}/{name}"
            for account in accounts for name in required_profile_names
        }
        if set(generated_digests) != expected_profile_paths:
            return {**result, "status": "UNVERIFIED",
                    "reason": "generated profile digests must cover all six files for every account"}
        profile_dirs = {d for d in dirs if d.startswith("profiles/")}
        if any(not _in_overlay(str(path), set(), profile_dirs)
               for path in generated_digests):
            return {**result, "status": "UNVERIFIED",
                    "reason": "generated profile digest is outside a declared profile directory"}
        expected_digests.update(generated_digests)
        # Recorded hashes alone only describe a historical projection. Compare
        # the installed files to a fresh projection of current account DNA.
        profile_script = ROOT / "scripts" / "easel_profile.py"
        account_root = ROOT / "config" / "accounts"
        try:
            if (_linklike(profile_script) or _linklike(profile_script.parent)
                    or _linklike(account_root) or _linklike(account_root.parent)
                    or not profile_script.is_file() or not account_root.is_dir()):
                raise ValueError("profile projector or DNA directory is unavailable")
            spec = importlib.util.spec_from_file_location("contentops_easel_profile_verifier", profile_script)
            if spec is None or spec.loader is None:
                raise ValueError("profile projector cannot be loaded")
            profile_tool = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(profile_tool)
            checks = {}
            for account in accounts:
                dna_path = account_root / f"{account}.json"
                if (_linklike(dna_path) or not dna_path.is_file()
                        or dna_path.resolve(strict=True).parent != account_root.resolve(strict=True)):
                    raise ValueError("account DNA is unavailable or linked")
                dna = json.loads(dna_path.read_text(encoding="utf-8"))
                verified = profile_tool.verify_profile(account, dna, instance)
                recorded = {name: generated_digests[f"profiles/{account}/{name}"]
                            for name in required_profile_names}
                checks[account] = {
                    "status": verified.get("status"),
                    "dna_sha256": verified.get("dna_sha256"),
                    "record_matches_current_dna": verified.get("profile_sha256") == recorded,
                }
            profile_freshness = {
                "status": ("VERIFIED" if all(item["status"] == "VERIFIED"
                                               and item["record_matches_current_dna"]
                                               for item in checks.values()) else "MISMATCH"),
                "accounts": checks,
            }
        except Exception:  # noqa: BLE001 - an uncheckable profile must fail closed
            profile_freshness = {"status": "UNVERIFIED", "accounts": {},
                                 "reason": "current account DNA projection could not be verified"}
    digest_undeclared = sorted(
        p for p in expected_digests if not _in_overlay(str(p), files, dirs)
    )
    recorded_missing = sorted((files | set(expected_digests)) - set(local))
    digest_mismatch = sorted(
        p for p, expected in expected_digests.items()
        if p in local and (local[p] == UNSAFE_LINK_BLOB
                           or hashlib.sha256((instance / p).read_bytes()).hexdigest() != expected)
    )
    # Hash coverage is mandatory even when a record accidentally supplies an
    # empty digest map. Otherwise a broad overlay directory silently exempts
    # every file below it from byte verification.
    overlay_unexpected = sorted(p for p in overlay_present if p not in expected_digests)

    source_check = verify_overlay_sources(overlay, ROOT)
    source_required = "source_files" in (overlay.get("overlay") or {})
    source_problem = source_required and source_check["status"] != "VERIFIED"
    license_problem = license_meta is not None and license_check["status"] != "VERIFIED"

    ok = not (missing or extra or mismatch or recorded_missing or digest_mismatch
              or overlay_unexpected or digest_undeclared or unsafe_links
              or source_problem or license_problem
              or (profile_mode == "generated" and profile_freshness["status"] != "VERIFIED"))
    result.update({
        "status": "VERIFIED" if ok else "MISMATCH",
        "method": "blob_sha1_tree_compare_with_overlay",
        "upstream_blob_count": len(baseline_upstream),
        "baseline_blob_count": len(baseline_local),
        "matched": len(set(baseline_local) & set(baseline_upstream)) - len(mismatch),
        "missing": missing[:20],
        "missing_count": len(missing),
        "mismatch": mismatch[:20],
        "mismatch_count": len(mismatch),
        "extra": extra[:20],
        "extra_count": len(extra),
        "overlay_present": overlay_present,
        "overlay_present_count": len(overlay_present),
        "unsafe_links": unsafe_links,
        "unsafe_link_count": len(unsafe_links),
        "recorded_missing": recorded_missing,
        "recorded_missing_count": len(recorded_missing),
        "digest_mismatch": digest_mismatch,
        "digest_mismatch_count": len(digest_mismatch),
        "overlay_unexpected": overlay_unexpected,
        "overlay_unexpected_count": len(overlay_unexpected),
        "digest_undeclared": digest_undeclared,
        "digest_undeclared_count": len(digest_undeclared),
        "overlay_sources": source_check,
        "upstream_license": license_check,
        "profile_freshness": profile_freshness,
        "note": "Baseline files are compared to upstream; declared tuning with "
                "recorded SHA-256 digests must also match. Declared repository source copies "
                "are verified too. Generated files are excluded.",
    })
    if not ok:
        result["reason"] = (f"{len(mismatch)} mismatched / {len(missing)} missing / "
                            f"{len(extra)} extra vs upstream {commit[:7]}; "
                            f"{len(recorded_missing)} recorded overlay files absent; "
                            f"{len(digest_mismatch)} overlay digest mismatches; "
                            f"{len(overlay_unexpected)} unrecorded overlay files; "
                            f"{len(digest_undeclared)} digests outside overlay; "
                            f"{len(source_check['missing'])} source files missing; "
                            f"{len(source_check['mismatched'])} source digests mismatched; "
                            f"{len(source_check['unsafe'])} unsafe source paths; "
                            f"license status {license_check['status']}; "
                            f"profile freshness {profile_freshness['status']}")
    return result


def verify_frontend_build(frontend_dir: Path, manifest_path: Path,
                          expected_commit: str,
                          policy_path: Path = FRONTEND_BUILD_POLICY) -> dict:
    """Verify a recorded, reproducible frontend build and its complete dist tree.

    The manifest is an integrity record, not a signature. A clean build must
    create it only after the pinned source, lockfile and declared command have
    been verified. Missing provenance is a block; hashing an existing dist
    tree after the fact does not establish where it came from.
    """
    frontend_dir = Path(frontend_dir)
    manifest_path = Path(manifest_path)
    policy_path = Path(policy_path)
    result = {"status": "UNVERIFIED", "manifest": str(manifest_path),
              "frontend_dir": str(frontend_dir), "expected_commit": expected_commit}
    path_chain = (manifest_path, manifest_path.parent, policy_path, policy_path.parent,
                  frontend_dir, frontend_dir.parent, frontend_dir.parent.parent)
    if any(_linklike(path) for path in path_chain):
        result["reason"] = "frontend manifest, policy, or source path contains a link"
        return result
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        result["reason"] = "frontend build manifest missing or unreadable"
        return result
    if not isinstance(manifest, dict) or manifest.get("schema") != "contentops.easel-frontend-build/v1":
        result["reason"] = "frontend build manifest schema invalid"
        return result
    if manifest.get("source_commit") != expected_commit:
        result["reason"] = "frontend source commit does not match the workbench pin"
        return result
    if not expected_commit:
        result["reason"] = "workbench upstream commit is not pinned"
        return result

    destination = manifest.get("destination")
    if not isinstance(destination, str) or not destination.strip():
        result["status"] = "MISMATCH"
        result["reason"] = "frontend build destination is missing from manifest"
        return result
    try:
        recorded_destination = Path(destination)
        actual_destination = frontend_dir.resolve(strict=True)
        if (not recorded_destination.is_absolute()
                or recorded_destination.resolve(strict=True) != actual_destination):
            result["status"] = "MISMATCH"
            result["reason"] = "frontend build destination does not match the verified path"
            return result
    except (OSError, RuntimeError):
        result["status"] = "MISMATCH"
        result["reason"] = "frontend build destination is invalid or unavailable"
        return result

    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        result["reason"] = "frontend build policy missing or unreadable"
        return result
    if (not isinstance(policy, dict)
            or policy.get("schema") != "contentops.easel-frontend-build-policy/v1"):
        result["reason"] = "frontend build policy schema invalid"
        return result

    lock_path = frontend_dir / "package-lock.json"
    if not lock_path.is_file() or _linklike(lock_path):
        result["reason"] = "frontend package-lock.json missing"
        return result
    lock_digest = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    if lock_digest != policy.get("package_lock_sha256"):
        result["reason"] = "frontend lockfile does not match the reviewed build policy"
        return result
    if manifest.get("package_lock_sha256") != lock_digest:
        result["reason"] = "frontend lockfile digest mismatch"
        return result
    toolchain = manifest.get("toolchain")
    if (not isinstance(toolchain, dict)
            or not all(isinstance(toolchain.get(name), str) and toolchain[name].strip()
                       for name in ("node", "npm"))):
        result["reason"] = "frontend Node and npm versions are required"
        return result
    expected_toolchain = policy.get("toolchain")
    if not isinstance(expected_toolchain, dict) or toolchain != expected_toolchain:
        result["reason"] = "frontend toolchain does not match the reviewed build policy"
        return result
    expected_command = policy.get("build_command")
    if not isinstance(expected_command, list) or manifest.get("build_command") != expected_command:
        result["reason"] = "frontend build command is not the reviewed package build"
        return result

    recorded = manifest.get("files")
    if not isinstance(recorded, dict) or not recorded:
        result["reason"] = "frontend dist file inventory missing"
        return result
    if any(not isinstance(path, str) or path.startswith("/") or "\\" in path
           or any(part in ("", ".", "..") for part in path.split("/"))
           or not isinstance(digest, str) or len(digest) != 64
           or any(c not in "0123456789abcdef" for c in digest)
           for path, digest in recorded.items()):
        result["reason"] = "frontend dist inventory contains an invalid path or SHA-256"
        return result
    tree_digest = hashlib.sha256(json.dumps(
        recorded, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    if manifest.get("tree_sha256") != tree_digest:
        result["reason"] = "frontend dist inventory digest is inconsistent"
        return result

    dist = frontend_dir / "dist"
    if not dist.is_dir() or _linklike(dist):
        result["reason"] = "frontend dist directory missing"
        return result
    actual: dict[str, str] = {}
    for path in sorted(dist.rglob("*")):
        if _linklike(path):
            result["reason"] = f"frontend dist contains a link: {path.relative_to(dist).as_posix()}"
            return result
        if path.is_file():
            rel = path.relative_to(dist).as_posix()
            actual[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    missing = sorted(set(recorded) - set(actual))
    extra = sorted(set(actual) - set(recorded))
    mismatched = sorted(p for p in set(actual) & set(recorded) if actual[p] != recorded[p])
    result.update({"missing": missing, "extra": extra, "mismatched": mismatched,
                   "file_count": len(actual), "package_lock_sha256": lock_digest,
                   "tree_sha256": tree_digest})
    result["status"] = "VERIFIED" if not missing and not extra and not mismatched else "MISMATCH"
    if result["status"] != "VERIFIED":
        result["reason"] = "frontend dist inventory does not match the recorded build"
    return result


def record_content_verification(result: dict) -> bool:
    """Merge a content proof into the provenance file.

    Provenance written by acquisition can only prove a commit (git HEAD) or an
    archive. Recording the blob comparison separately keeps "the tree is what we
    pinned" distinguishable from "HEAD says so".
    """
    provenance = ROOT / "runtime" / "easel-runtime.json"
    try:
        data = (json.loads(provenance.read_text(encoding="utf-8"))
                if provenance.is_file() else {})
    except (OSError, json.JSONDecodeError):
        return False
    data.update({
        "content_verified": True,
        "content_verification_method": result.get("method"),
        "content_verified_files": result.get("matched"),
        "content_verified_commit": result.get("expected_commit"),
        "content_verified_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    })
    provenance.parent.mkdir(parents=True, exist_ok=True)
    provenance.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                          encoding="utf-8")
    return True


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--runtime", default=str(RUNTIME))
    p.add_argument("--repo", default=REPO)
    p.add_argument("--commit", default=PINNED_COMMIT)
    p.add_argument("--resolve-tag", action="store_true",
                   help="confirm --commit is the commit the pinned tag points at")
    p.add_argument("--json", action="store_true")
    p.add_argument("--record", action="store_true",
                   help="merge a VERIFIED content result into runtime/easel-runtime.json")
    p.add_argument("--overlay", action="store_true",
                   help="verify the workbench instance against the overlay record "
                        "(upstream baseline proven; recorded tuning reported)")
    p.add_argument("--generated-profiles", action="store_true",
                   help="verify account profile files against current DNA projections "
                        "instead of the observed installed snapshot")
    p.add_argument("--overlay-record", default=str(OVERLAY_RECORD),
                   help="overlay record to read (default runtime/easel-workbench-overlay.json)")
    p.add_argument("--workbench",
                   help="explicit workbench directory for overlay verification; overrides the recorded path")
    p.add_argument("--frontend-build", action="store_true",
                   help="verify the recorded web/frontend/dist build and lockfile")
    p.add_argument("--frontend-dir",
                   help="frontend source directory (default: selected workbench/web/frontend)")
    p.add_argument("--frontend-manifest",
                   default=str(ROOT / "runtime" / "easel-workbench-frontend-build.json"),
                   help="frontend build receipt path")
    args = p.parse_args()

    if args.frontend_build:
        overlay = load_overlay(Path(args.overlay_record))
        if not overlay.get("readable"):
            res = {"status": "UNVERIFIED", "reason": "overlay record unreadable"}
        else:
            source_commit = str((overlay.get("upstream") or {}).get("commit") or "")
            try:
                frontend_dir = (Path(args.frontend_dir) if args.frontend_dir
                                else workbench_path(overlay) / "web" / "frontend")
                res = verify_frontend_build(
                    frontend_dir, Path(args.frontend_manifest), source_commit)
            except (TypeError, ValueError, OSError) as exc:
                res = {"status": "UNVERIFIED", "reason": str(exc)}
        print(json.dumps(res, indent=2, ensure_ascii=False))
        if res.get("status") == "VERIFIED":
            return 0
        if res.get("status") == "UNVERIFIED":
            return 3
        return 1

    if args.overlay:
        res = verify_overlay(Path(args.overlay_record), args.repo,
                             profile_mode="generated" if args.generated_profiles else "observed",
                             workbench_override=Path(args.workbench) if args.workbench else None)
        print(json.dumps(res, indent=2, ensure_ascii=False))
        if res.get("status") == "VERIFIED":
            return 0
        if res.get("status") in ("UNVERIFIED", "MISSING"):
            return 3
        return 1

    res = verify(Path(args.runtime), args.repo, args.commit)

    if args.resolve_tag and res.get("status") != "MISSING":
        try:
            peeled = resolve_tag_commit(args.repo, PINNED_TAG)
            res["tag_resolved_commit"] = peeled
            res["tag_matches_commit"] = (peeled == args.commit)
            if peeled != args.commit:
                res["status"] = "MISMATCH"
                res["reason"] = (f"tag {PINNED_TAG} points at {peeled}, "
                                 f"but the pin expects {args.commit}")
        except RuntimeError as e:
            res["tag_resolve_error"] = str(e)

    if args.record and res["status"] == "VERIFIED":
        recorded = record_content_verification(res)
        if recorded:
            res["recorded_to"] = "runtime/easel-runtime.json"

    print(json.dumps(res, indent=2, ensure_ascii=False))
    if res["status"] == "VERIFIED":
        return 0
    if res["status"] == "UNVERIFIED":
        return 3
    return 1


if __name__ == "__main__":
    sys.exit(main())
