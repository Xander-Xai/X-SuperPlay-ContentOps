#!/usr/bin/env python3
"""Hermetic safety tests for the opt-in Easel v0.3.0 rebuild command."""

from __future__ import annotations

import io
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import rebuild_easel_workbench as rebuild  # noqa: E402


def _archive(path: Path, members: list[tuple[str, bytes, str]]) -> None:
    with tarfile.open(path, "w:gz") as bundle:
        for name, data, kind in members:
            info = tarfile.TarInfo(name)
            if kind == "dir":
                info.type = tarfile.DIRTYPE
                bundle.addfile(info)
            elif kind == "symlink":
                info.type = tarfile.SYMTYPE
                info.linkname = data.decode("utf-8")
                bundle.addfile(info)
            else:
                info.size = len(data)
                bundle.addfile(info, io.BytesIO(data))


def test_extract_commit_archive_copies_regular_files_from_one_root():
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)
        archive, destination = temp / "upstream.tar.gz", temp / "source"
        _archive(archive, [
            ("Easel-commit/", b"", "dir"),
            ("Easel-commit/pyproject.toml", b"[project]\n", "file"),
            ("Easel-commit/src/module.py", b"pass\n", "file"),
        ])
        rebuild.extract_commit_archive(archive, destination)
        assert (destination / "pyproject.toml").read_bytes() == b"[project]\n"
        assert (destination / "src" / "module.py").read_bytes() == b"pass\n"


def test_extract_commit_archive_rejects_path_traversal():
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)
        archive, destination = temp / "upstream.tar.gz", temp / "source"
        _archive(archive, [("Easel-commit/../escape.txt", b"unsafe", "file")])
        try:
            rebuild.extract_commit_archive(archive, destination)
        except rebuild.RebuildError as exc:
            assert "unsafe path" in str(exc)
        else:
            raise AssertionError("archive traversal was accepted")
        assert not (temp / "escape.txt").exists()


def test_extract_commit_archive_rejects_symlinks_and_multiple_roots():
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)
        archive, destination = temp / "linked.tar.gz", temp / "linked"
        _archive(archive, [("Easel-commit/link", b"../outside", "symlink")])
        try:
            rebuild.extract_commit_archive(archive, destination)
        except rebuild.RebuildError as exc:
            assert "link or special file" in str(exc)
        else:
            raise AssertionError("archive symlink was accepted")

        archive, destination = temp / "roots.tar.gz", temp / "roots"
        _archive(archive, [("one/file", b"a", "file"), ("two/file", b"b", "file")])
        try:
            rebuild.extract_commit_archive(archive, destination)
        except rebuild.RebuildError as exc:
            assert "one top-level" in str(exc)
        else:
            raise AssertionError("multiple archive roots were accepted")


def test_rebuild_target_must_be_absolute_and_absent():
    with tempfile.TemporaryDirectory() as temp:
        parent = Path(temp)
        target = parent / "new-workbench"
        resolved, resolved_parent = rebuild._safe_destination(target)
        assert resolved == target and resolved_parent == parent.resolve()
        try:
            rebuild._safe_destination("relative-workbench")
        except rebuild.RebuildError as exc:
            assert "absolute" in str(exc)
        else:
            raise AssertionError("relative destination was accepted")
        try:
            rebuild._safe_destination(parent / ".." / "escaped")
        except rebuild.RebuildError as exc:
            assert "parent traversal" in str(exc)
        else:
            raise AssertionError("traversal destination was accepted")
        target.mkdir()
        try:
            rebuild._safe_destination(target)
        except rebuild.RebuildError as exc:
            assert "already exists" in str(exc)
        else:
            raise AssertionError("existing destination was accepted")


def test_rebuild_rejects_invalid_destination_before_download():
    downloader_called = False

    def download(commit: str, archive: Path) -> None:
        nonlocal downloader_called
        downloader_called = True
        raise AssertionError("download must not run for an invalid target")

    try:
        rebuild.rebuild("relative-workbench", download=download)
    except rebuild.RebuildError as exc:
        assert "absolute" in str(exc)
    else:
        raise AssertionError("invalid destination was accepted")
    assert not downloader_called


TESTS = [value for name, value in sorted(globals().items())
         if name.startswith("test_") and callable(value)]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
        except Exception as exc:  # noqa: BLE001 - report the failure without hiding it
            failures += 1
            print(f"FAIL {test.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"ok   {test.__name__}")
    print(f"{len(TESTS) - failures}/{len(TESTS)} ok")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
