#!/usr/bin/env python3
"""Rebuild a v0.3.0 workbench from its exact upstream commit and repo overlay.

This is deliberately opt-in. It writes only to a new, absent destination,
checks upstream bytes against the full commit tree, applies reviewed repo-owned
skill sources and DNA-generated profiles, then verifies the complete overlay.
It does not install frontend packages, run a build, start a host, or call Easel.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from contentops.easel.path_safety import is_linklike

OVERLAY_RECORD = ROOT / "runtime" / "easel-workbench-overlay.json"
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_EXTRACTED_BYTES = 2 * 1024 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 20_000


class RebuildError(RuntimeError):
    """A clean rebuild failed closed before or during verification."""


def _linklike(path: Path) -> bool:
    return is_linklike(path)


def _has_link_component(path: Path, *, root: Path = ROOT) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    current = root
    if _linklike(current):
        return True
    for part in relative.parts:
        current = current / part
        if _linklike(current):
            return True
    return False


def _safe_destination(value: str | Path) -> tuple[Path, Path]:
    target = Path(value).expanduser()
    if not target.is_absolute():
        raise RebuildError("destination must be an absolute path")
    if ".." in target.parts:
        raise RebuildError("destination path may not contain parent traversal")
    if target.exists() or _linklike(target):
        raise RebuildError("destination already exists; rebuild never overwrites")
    parent = target.parent
    if not parent.is_dir():
        raise RebuildError("destination parent must already exist")
    current = Path(target.anchor)
    for part in target.parts[1:-1]:
        current = current / part
        if _linklike(current):
            raise RebuildError("destination path may not contain a symlink or junction")
    if _linklike(parent):
        raise RebuildError("destination parent may not be a symlink or junction")
    return target, parent.resolve(strict=True)


def _safe_member_path(name: str, top: str) -> PurePosixPath:
    if "\\" in name or "\x00" in name:
        raise RebuildError("archive contains an invalid path")
    member = PurePosixPath(name)
    if member.is_absolute() or not member.parts or any(p in ("", ".", "..") for p in member.parts):
        raise RebuildError("archive contains an unsafe path")
    if member.parts[0] != top:
        raise RebuildError("archive does not have one consistent root directory")
    relative = PurePosixPath(*member.parts[1:])
    if not relative.parts:
        return relative
    return relative


def extract_commit_archive(archive: Path, destination: Path) -> None:
    """Extract regular files/directories only; reject links and traversal."""
    archive = Path(archive)
    destination = Path(destination)
    if destination.exists() or _linklike(destination):
        raise RebuildError("archive extraction destination must not exist")
    destination.mkdir()
    try:
        with tarfile.open(archive, mode="r:gz") as bundle:
            members = bundle.getmembers()
            if not members:
                raise RebuildError("upstream archive is empty")
            if len(members) > MAX_ARCHIVE_MEMBERS:
                raise RebuildError("upstream archive has too many members")
            roots = set()
            for member in members:
                normalized = member.name.rstrip("/")
                if not normalized:
                    raise RebuildError("archive contains an empty member path")
                roots.add(normalized.split("/", 1)[0])
                if not (member.isdir() or member.isfile()):
                    raise RebuildError("archive contains a link or special file")
            if len(roots) != 1:
                raise RebuildError("archive must contain exactly one top-level directory")
            top = next(iter(roots))
            total_size = 0
            for member in members:
                relative = _safe_member_path(member.name.rstrip("/"), top)
                if not relative.parts:
                    continue
                total_size += member.size if member.isfile() else 0
                if total_size > MAX_EXTRACTED_BYTES:
                    raise RebuildError("upstream archive exceeds the extraction size limit")
                target = destination.joinpath(*relative.parts)
                resolved_parent = target.parent.resolve(strict=False)
                if destination.resolve(strict=True) not in (resolved_parent, *resolved_parent.parents):
                    raise RebuildError("archive member escapes the extraction directory")
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                if _linklike(target) or target.exists():
                    raise RebuildError("archive contains a duplicate or linked path")
                source = bundle.extractfile(member)
                if source is None:
                    raise RebuildError("archive file could not be read")
                with source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
    except (OSError, tarfile.TarError) as exc:
        if isinstance(exc, RebuildError):
            raise
        raise RebuildError(f"upstream archive could not be extracted: {exc}") from None


def _download_commit_archive(commit: str, destination: Path) -> None:
    urls = (f"https://api.github.com/repos/ZJU-REAL/Easel/tarball/{commit}",
            f"https://codeload.github.com/ZJU-REAL/Easel/tar.gz/{commit}")
    for index, url in enumerate(urls):
        request = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "X-SuperPlay-ContentOps-Easel-rebuild",
        })
        # Both names are inside the fresh rebuild temporary directory.
        output_path = destination if index == 0 else destination.with_name("upstream-fallback.tar.gz")
        size = 0
        try:
            with urllib.request.urlopen(request, timeout=120) as response, output_path.open("xb") as output:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > MAX_ARCHIVE_BYTES:
                        raise RebuildError("upstream archive exceeds the download size limit")
                    output.write(chunk)
            if not size:
                raise RebuildError("upstream archive download was empty")
            if index:
                os.replace(output_path, destination)
            return
        except RebuildError:
            raise
        except Exception:  # noqa: BLE001 - do not expose response or credentials
            if index:
                raise RebuildError("could not download the pinned public upstream archive") from None


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RebuildError(f"required repository module is unavailable: {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _apply_overlay(instance: Path, record: dict) -> dict[str, str]:
    body = record.get("overlay") or {}
    sources = body.get("source_files")
    expected_sources = set(body.get("files") or [])
    if not isinstance(sources, dict) or set(sources) != expected_sources:
        raise RebuildError("every declared skill overlay must have one repository source")
    for target_rel, source_rel in sources.items():
        target = instance / target_rel
        source = ROOT / source_rel
        if (not isinstance(target_rel, str) or not isinstance(source_rel, str)
                or Path(target_rel).is_absolute() or "\\" in target_rel or ":" in target_rel
                or ".." in Path(target_rel).parts
                or Path(source_rel).is_absolute() or "\\" in source_rel or ":" in source_rel
                or ".." in Path(source_rel).parts):
            raise RebuildError("overlay record contains an unsafe path")
        if _has_link_component(source) or _has_link_component(target, root=instance):
            raise RebuildError("overlay source or target path contains a link")
        if not source.is_file():
            raise RebuildError(f"repository overlay source is missing: {source_rel}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)

    profile_record = record.get("generated_profiles") or {}
    if not isinstance(profile_record, dict):
        raise RebuildError("generated profile record is invalid")
    accounts = profile_record.get("accounts")
    profile_digests = profile_record.get("digests")
    if not isinstance(accounts, list) or not accounts or not all(isinstance(a, str) for a in accounts):
        raise RebuildError("generated profile accounts are not declared")
    if not isinstance(profile_digests, dict):
        raise RebuildError("generated profile digests are not declared")
    profile_tool = _load_module("contentops_easel_rebuild_profile", ROOT / "scripts" / "easel_profile.py")
    for account in accounts:
        dna_path = ROOT / "config" / "accounts" / f"{account}.json"
        if _linklike(dna_path) or not dna_path.is_file():
            raise RebuildError(f"account DNA is missing or linked: {account}")
        dna = json.loads(dna_path.read_text(encoding="utf-8"))
        profile_tool.validate_profile_dna(account, dna)
        profile_tool.write_profile(account, profile_tool.build_profile(account, dna), instance)

    digests: dict[str, str] = {}
    for rel in sorted(set(sources) | set(profile_digests)):
        path = instance / rel
        if _linklike(path) or not path.is_file():
            raise RebuildError(f"rebuilt overlay output is missing or linked: {rel}")
        digests[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


def rebuild(destination: str | Path, *, download=_download_commit_archive) -> dict:
    target, parent = _safe_destination(destination)
    if _has_link_component(OVERLAY_RECORD) or not OVERLAY_RECORD.is_file():
        raise RebuildError("repository overlay record is missing or linked")
    record = json.loads(OVERLAY_RECORD.read_text(encoding="utf-8"))
    if not isinstance(record, dict) or not isinstance(record.get("upstream"), dict):
        raise RebuildError("repository overlay record is invalid")
    commit = record["upstream"]["commit"]
    with tempfile.TemporaryDirectory(prefix=".easel-v030-rebuild-", dir=parent) as temp_name:
        temp = Path(temp_name)
        archive = temp / "upstream.tar.gz"
        source = temp / "source"
        staging = temp / "workbench"
        download(commit, archive)
        extract_commit_archive(archive, source)

        # Compare the archive to the pinned complete tree, without requiring a
        # live tree API when the digest-bound local index is available.
        verifier = _load_module("contentops_easel_rebuild_verifier",
                                ROOT / "scripts" / "verify_easel_runtime.py")
        source_tree = verifier.walk_local(source)
        metadata = record["upstream"]
        expected_digest = metadata.get("tree_sha256")
        expected_count = metadata.get("tree_blob_count")
        if (verifier.upstream_tree_sha256(source_tree) != expected_digest
                or len(source_tree) != expected_count):
            raise RebuildError("archive tree does not match the pinned digest and count")
        try:
            upstream = verifier.load_workbench_tree_cache(
                verifier.WORKBENCH_TREE_CACHE, commit=commit,
                tree_sha256=expected_digest, expected_count=expected_count)
        except (OSError, ValueError, TypeError):
            try:
                upstream = verifier.fetch_upstream_tree(verifier.REPO, commit)
            except RuntimeError:
                # The archive's own complete path/blob map already matches the
                # previously pinned digest; overlay verification follows below.
                upstream = source_tree
        mismatch = sorted(path for path, digest in upstream.items()
                          if source_tree.get(path) != digest)
        missing = sorted(set(upstream) - set(source_tree))
        extra = sorted(set(source_tree) - set(upstream))
        if mismatch or missing or extra:
            raise RebuildError(f"archive does not match pinned upstream tree: {len(mismatch)} changed, "
                               f"{len(missing)} missing, {len(extra)} extra")

        shutil.move(str(source), str(staging))
        overlay_digests = _apply_overlay(staging, record)
        check_record = json.loads(json.dumps(record))
        check_record["instance"]["path"] = str(staging)
        check_record["instance"]["path_env"] = ""
        temporary_record = temp / "overlay-check.json"
        temporary_record.write_text(json.dumps(check_record, ensure_ascii=False, indent=2) + "\n",
                                    encoding="utf-8")
        result = verifier.verify_overlay(temporary_record, profile_mode="generated")
        if result.get("status") != "VERIFIED":
            raise RebuildError(f"rebuilt source and overlay did not verify: {result.get('reason', result.get('status'))}")
        if target.exists() or _linklike(target):
            raise RebuildError("destination appeared during rebuild; refusing to overwrite")
        os.replace(staging, target)
        return {
            "status": "VERIFIED",
            "destination": str(target),
            "upstream_commit": commit,
            "upstream_tree_sha256": result.get("upstream_tree_sha256"),
            "baseline_blobs_matched": result.get("matched"),
            "overlay_file_count": len(overlay_digests),
            "frontend_build": "NOT_RUN",
            "dependencies_installed": False,
            "host_started": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", required=True,
                        help="absolute path to a new, absent workbench directory")
    args = parser.parse_args()
    try:
        result = rebuild(args.destination)
    except (RebuildError, OSError, KeyError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
