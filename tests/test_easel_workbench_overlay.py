#!/usr/bin/env python3
"""Tests for the Easel workbench overlay verifier and the DNA→profile projection.

Two things are pinned here:

* **The overlay verifier must still fail an unrecorded difference.** The whole
  point of overlay mode is that tuning is *declared*, not that comparison got
  weaker. A test that only shows the overlay files pass would not prove that.
* **The profile projection must not invent or hand-maintain account facts.** It
  reads the DNA and renders actual values Easel can use; it must not project
  episode-level fields (`title`/`description`) into a permanent profile.

Run: python tests/test_easel_workbench_overlay.py
"""

from __future__ import annotations

import json
import hashlib
import io
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import verify_easel_runtime as ver  # noqa: E402
import easel_profile as prof  # noqa: E402


# --- overlay verifier --------------------------------------------------------

def _fake_upstream(monkeypatch_upstream: dict):
    """Replace the network fetch with a fixed tree."""
    original = ver.fetch_upstream_tree

    def fake(repo, commit):
        return dict(monkeypatch_upstream)

    ver.fetch_upstream_tree = fake
    return original


def _write(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _source_archive(members: list[tuple[str, bytes, str]]) -> io.BytesIO:
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:gz") as bundle:
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
    archive.seek(0)
    return archive


def test_commit_archive_builds_git_blob_tree_and_skips_generated_paths():
    archive = _source_archive([
        ("Easel-commit/", b"", "dir"),
        ("Easel-commit/pyproject.toml", b"[project]\n", "file"),
        ("Easel-commit/__pycache__/cached.pyc", b"cache", "file"),
    ])
    tree = ver._tree_from_commit_archive(
        archive, "bb3c8ff0463f36c202454d74171682ba6e470cb1")
    assert tree == {
        "pyproject.toml": hashlib.sha1(b"blob 10\0[project]\n").hexdigest(),
    }


def test_commit_archive_rejects_path_traversal_and_links():
    commit = "bb3c8ff0463f36c202454d74171682ba6e470cb1"
    for members in (
        [("Easel-commit/../escape", b"x", "file")],
        [("Easel-commit/a:b", b"x", "file")],
        [("Easel-commit/link", b"target", "symlink")],
    ):
        try:
            ver._tree_from_commit_archive(_source_archive(members), commit)
        except RuntimeError as exc:
            assert "unsafe path" in str(exc) or "link or special" in str(exc)
        else:
            raise AssertionError("unsafe archive member must be rejected")


def test_commit_archive_streaming_enforces_member_and_expansion_limits():
    commit = "bb3c8ff0463f36c202454d74171682ba6e470cb1"
    original_members = ver.MAX_UPSTREAM_ARCHIVE_MEMBERS
    original_size = ver.MAX_UPSTREAM_EXTRACTED_BYTES
    try:
        ver.MAX_UPSTREAM_ARCHIVE_MEMBERS = 1
        try:
            ver._tree_from_commit_archive(_source_archive([
                ("Easel-commit/a", b"a", "file"),
                ("Easel-commit/b", b"b", "file"),
            ]), commit)
        except RuntimeError as exc:
            assert "too many members" in str(exc)
        else:
            raise AssertionError("archive member limit was ignored")

        ver.MAX_UPSTREAM_ARCHIVE_MEMBERS = original_members
        ver.MAX_UPSTREAM_EXTRACTED_BYTES = 1
        try:
            ver._tree_from_commit_archive(_source_archive([
                ("Easel-commit/a", b"ab", "file"),
            ]), commit)
        except RuntimeError as exc:
            assert "expanded size limit" in str(exc)
        else:
            raise AssertionError("archive expansion limit was ignored")
    finally:
        ver.MAX_UPSTREAM_ARCHIVE_MEMBERS = original_members
        ver.MAX_UPSTREAM_EXTRACTED_BYTES = original_size


def test_commit_archive_fetch_is_anonymous_and_bound_to_the_exact_commit():
    commit = "bb3c8ff0463f36c202454d74171682ba6e470cb1"
    archive = _source_archive([
        ("Easel-commit/", b"", "dir"),
        ("Easel-commit/pyproject.toml", b"[project]\n", "file"),
    ]).getvalue()

    class Response:
        status = 200

        def __init__(self, payload: bytes, url: str):
            self.payload = io.BytesIO(payload)
            self.url = url

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, size=-1):
            return self.payload.read(size)

        def geturl(self):
            return self.url

    class Opener:
        def __init__(self, response):
            self.response = response
            self.request = None

        def open(self, request, timeout):
            self.request = request
            assert timeout == 180
            return self.response

    expected_url = f"https://codeload.github.com/ZJU-REAL/Easel/tar.gz/{commit}"
    opener = Opener(Response(archive, expected_url))
    with mock.patch.object(urllib.request, "build_opener", return_value=opener):
        tree = ver.fetch_upstream_archive_tree("ZJU-REAL/Easel", commit)
    assert opener.request.full_url == expected_url
    assert opener.request.get_header("Authorization") is None
    assert tree["pyproject.toml"] == hashlib.sha1(b"blob 10\0[project]\n").hexdigest()

    opener.response = Response(archive, f"https://codeload.github.com/ZJU-REAL/Easel/tar.gz/{'0' * 40}")
    with mock.patch.object(urllib.request, "build_opener", return_value=opener):
        try:
            ver.fetch_upstream_archive_tree("ZJU-REAL/Easel", commit)
        except RuntimeError as exc:
            assert "redirected" in str(exc)
        else:
            raise AssertionError("archive redirect to another commit was accepted")


class _JsonResponse:
    def __init__(self, value):
        self.payload = json.dumps(value).encode("utf-8")
        self.status = 200
        self.url = "https://api.github.com/"

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload

    def geturl(self):
        return self.url


class _FakeOpener:
    def __init__(self, response):
        self.response = response
        self.request = None
        self.timeout = None

    def open(self, request, timeout):
        self.request = request
        self.timeout = timeout
        self.response.url = request.full_url
        return self.response


def test_upstream_tree_fetch_is_anonymous_direct_https_and_fail_closed():
    opener = _FakeOpener(_JsonResponse({"truncated": False, "tree": [
        {"path": "README.md", "sha": "a" * 40, "type": "blob"},
        {"path": "outputs/demo.mp4", "sha": "b" * 40, "type": "blob"},
        {"path": "subtree", "sha": "c" * 40, "type": "tree"},
    ]}))
    original_builder = urllib.request.build_opener

    def fake_builder(*handlers):
        assert len(handlers) == 1
        assert isinstance(handlers[0], urllib.request.ProxyHandler)
        assert handlers[0].proxies == {}, "public verifier must not use env/system proxy credentials"
        return opener

    urllib.request.build_opener = fake_builder
    try:
        tree = ver.fetch_upstream_tree("ZJU-REAL/Easel", "b" * 40)
    finally:
        urllib.request.build_opener = original_builder

    assert tree == {"README.md": "a" * 40}
    assert opener.request.full_url == (
        "https://api.github.com/repos/ZJU-REAL/Easel/git/trees/" + "b" * 40 + "?recursive=1"
    )
    assert opener.request.get_header("Authorization") is None
    assert opener.request.get_header("Accept") == "application/vnd.github+json"
    assert opener.timeout == 120


def test_upstream_tree_fetch_rejects_truncated_or_malformed_api_responses():
    original_builder = urllib.request.build_opener
    responses = iter([
        _JsonResponse({"truncated": True, "tree": []}),
        _JsonResponse({"truncated": False, "tree": [
            {"path": "../escape", "sha": "a" * 40, "type": "blob"},
        ]}),
    ])
    urllib.request.build_opener = lambda *_handlers: _FakeOpener(next(responses))
    try:
        for _ in range(2):
            try:
                ver.fetch_upstream_tree("ZJU-REAL/Easel", "b" * 40)
            except RuntimeError:
                pass
            else:
                raise AssertionError("partial or unsafe upstream data was accepted")
    finally:
        urllib.request.build_opener = original_builder


def test_tag_resolution_uses_public_api_and_peels_annotated_tags():
    opener = _FakeOpener(_JsonResponse({
        "object": {"sha": "c" * 40, "type": "tag"},
    }))
    original_builder = urllib.request.build_opener
    calls = []

    class SequenceOpener:
        def open(self, request, timeout):
            calls.append((request, timeout))
            response = opener.response if len(calls) == 1 else _JsonResponse({
                "object": {"sha": "d" * 40, "type": "commit"},
            })
            response.url = request.full_url
            return response

    urllib.request.build_opener = lambda *_handlers: SequenceOpener()
    try:
        commit = ver.resolve_tag_commit("ZJU-REAL/Easel", "v0.3.0")
    finally:
        urllib.request.build_opener = original_builder

    assert commit == "d" * 40
    assert [request.full_url for request, _ in calls] == [
        "https://api.github.com/repos/ZJU-REAL/Easel/git/ref/tags/v0.3.0",
        "https://api.github.com/repos/ZJU-REAL/Easel/git/tags/" + "c" * 40,
    ]
    assert all(request.get_header("Authorization") is None for request, _ in calls)


def test_upstream_verifier_rejects_redirects_outside_github_api():
    response = _JsonResponse({"truncated": False, "tree": []})
    response.url = "https://example.invalid/tree.json"

    class RedirectOpener:
        def open(self, _request, timeout):
            return response

    original_builder = urllib.request.build_opener
    urllib.request.build_opener = lambda *_handlers: RedirectOpener()
    try:
        try:
            ver.fetch_upstream_tree("ZJU-REAL/Easel", "b" * 40)
        except RuntimeError as exc:
            assert "redirected outside api.github.com" in str(exc)
        else:
            raise AssertionError("redirect outside GitHub was accepted")
    finally:
        urllib.request.build_opener = original_builder


def test_overlay_accepts_a_declared_tuning_file():
    """A file the record names as ours may differ from upstream."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        wb = tmp / "wb"
        _write(wb / "upstream.py", "same")
        _write(wb / "profiles" / "acct" / "identity.md", "tuned")

        upstream = {"upstream.py": ver.blob_sha1(wb / "upstream.py")}
        original = _fake_upstream(upstream)
        try:
            record = tmp / "overlay.json"
            record.write_text(json.dumps({
                "upstream": {"commit": "abc123", "tag": "v0.3.0"},
                "instance": {"path": str(wb)},
                "overlay": {"directories": ["profiles/acct"], "files": [], "digests": {
                    "profiles/acct/identity.md": hashlib.sha256(b"tuned").hexdigest(),
                }},
                "generated": {"directories": []},
            }), encoding="utf-8")
            res = ver.verify_overlay(record)
        finally:
            ver.fetch_upstream_tree = original

    assert res["status"] == "VERIFIED", res.get("reason")
    assert res["overlay_present_count"] == 1
    assert res["overlay_unexpected_count"] == 0


def test_overlay_uses_commit_archive_only_when_recorded_tree_digest_matches():
    commit = "bb3c8ff0463f36c202454d74171682ba6e470cb1"
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        wb = tmp / "wb"
        _write(wb / "upstream.py", "same")
        upstream = {"upstream.py": ver.blob_sha1(wb / "upstream.py")}
        tree_digest = ver.upstream_tree_sha256(upstream)
        record = tmp / "overlay.json"
        record.write_text(json.dumps({
            "upstream": {"commit": commit, "tag": "v0.3.0",
                         "tree_sha256": tree_digest},
            "instance": {"path": str(wb)},
            "overlay": {"directories": [], "files": [], "digests": {}},
            "generated": {"directories": []},
        }), encoding="utf-8")
        with mock.patch.object(ver, "fetch_upstream_tree",
                               side_effect=RuntimeError("HTTP 403")), \
                mock.patch.object(ver, "fetch_upstream_archive_tree",
                                  return_value=upstream):
            accepted = ver.verify_overlay(record)
        assert accepted["status"] == "VERIFIED", accepted
        assert accepted["upstream_source"] == "codeload_commit_archive"

        record_data = json.loads(record.read_text(encoding="utf-8"))
        record_data["upstream"]["tree_sha256"] = "0" * 64
        record.write_text(json.dumps(record_data), encoding="utf-8")
        with mock.patch.object(ver, "fetch_upstream_tree",
                               side_effect=RuntimeError("HTTP 403")), \
                mock.patch.object(ver, "fetch_upstream_archive_tree",
                                  return_value=upstream):
            refused = ver.verify_overlay(record)
        assert refused["status"] == "MISMATCH"
        assert "tree summary" in refused["reason"]


def test_overlay_rejects_an_unrecorded_difference():
    """A changed file the record does NOT name is still a failure.

    This is the test that proves overlay mode did not become a rubber stamp.
    """
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        wb = tmp / "wb"
        _write(wb / "upstream.py", "tampered")

        upstream = {"upstream.py": "0" * 40}  # deliberately not the local hash
        original = _fake_upstream(upstream)
        try:
            record = tmp / "overlay.json"
            record.write_text(json.dumps({
                "upstream": {"commit": "abc123"},
                "instance": {"path": str(wb)},
                "overlay": {"directories": [], "files": []},
                "generated": {"directories": []},
            }), encoding="utf-8")
            res = ver.verify_overlay(record)
        finally:
            ver.fetch_upstream_tree = original

    assert res["status"] == "MISMATCH", res
    assert res["mismatch_count"] == 1
    assert "upstream.py" in res["mismatch"]


def test_overlay_reports_a_recorded_file_that_vanished():
    """A file the record says we ship but which is absent is a failure."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        wb = tmp / "wb"
        _write(wb / "upstream.py", "same")

        upstream = {"upstream.py": ver.blob_sha1(wb / "upstream.py")}
        original = _fake_upstream(upstream)
        try:
            record = tmp / "overlay.json"
            record.write_text(json.dumps({
                "upstream": {"commit": "abc123"},
                "instance": {"path": str(wb)},
                "overlay": {"files": ["skills/builtin/video-script/SKILL.md"],
                            "digests": {"skills/builtin/video-script/SKILL.md": "0" * 64}},
                "generated": {"directories": []},
            }), encoding="utf-8")
            res = ver.verify_overlay(record)
        finally:
            ver.fetch_upstream_tree = original

    assert res["status"] == "MISMATCH"
    assert res["recorded_missing_count"] == 1


def test_overlay_ignores_generated_directories():
    """node_modules, dist and the venv are never compared against upstream."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        wb = tmp / "wb"
        _write(wb / "upstream.py", "same")
        _write(wb / "node_modules" / "pkg" / "index.js", "generated")
        _write(wb / "web" / "frontend" / "dist" / "index.html", "built")

        upstream = {"upstream.py": ver.blob_sha1(wb / "upstream.py")}
        original = _fake_upstream(upstream)
        try:
            record = tmp / "overlay.json"
            record.write_text(json.dumps({
                "upstream": {"commit": "abc123"},
                "instance": {"path": str(wb)},
                "overlay": {"files": [], "directories": []},
                "generated": {"directories": ["node_modules", "dist", ".venv"]},
            }), encoding="utf-8")
            res = ver.verify_overlay(record)
        finally:
            ver.fetch_upstream_tree = original

    assert res["status"] == "VERIFIED", res.get("reason")
    assert res["extra_count"] == 0


def test_recorded_overlay_digests_must_match_and_files_must_exist():
    import hashlib
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        wb = tmp / "wb"
        _write(wb / "upstream.py", "same")
        _write(wb / "profiles/acct/identity.md", "modified")
        record = tmp / "overlay.json"
        record.write_text(json.dumps({
            "upstream": {"commit": "abc123"}, "instance": {"path": str(wb)},
            "overlay": {"directories": ["profiles/acct"], "files": [], "digests": {
                "profiles/acct/identity.md": hashlib.sha256(b"original").hexdigest(),
                "profiles/acct/style.md": hashlib.sha256(b"style").hexdigest(),
            }}, "generated": {"directories": []},
        }), encoding="utf-8")
        original = _fake_upstream({"upstream.py": ver.blob_sha1(wb / "upstream.py")})
        try:
            res = ver.verify_overlay(record)
        finally:
            ver.fetch_upstream_tree = original
    assert res["status"] == "MISMATCH", res
    assert "profiles/acct/identity.md" in res["digest_mismatch"]
    assert "profiles/acct/style.md" in res["recorded_missing"]


def test_declared_overlay_without_digests_is_not_verified():
    """A declared tuning path cannot become an unhashed blind spot."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        wb = tmp / "wb"
        _write(wb / "profiles/acct/identity.md", "tuned")
        record = tmp / "overlay.json"
        record.write_text(json.dumps({
            "upstream": {"commit": "abc123"}, "instance": {"path": str(wb)},
            "overlay": {"directories": ["profiles/acct"], "files": [], "digests": {}},
            "generated": {"directories": []},
        }), encoding="utf-8")
        original = _fake_upstream({})
        try:
            res = ver.verify_overlay(record)
        finally:
            ver.fetch_upstream_tree = original
    assert res["status"] == "UNVERIFIED", res
    assert "per-file SHA-256" in res["reason"]


def test_overlay_rejects_hashes_outside_the_declared_overlay():
    import hashlib
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        wb = tmp / "wb"
        _write(wb / "profiles/acct/identity.md", "tuned")
        _write(wb / "upstream.py", "same")
        record = tmp / "overlay.json"
        record.write_text(json.dumps({
            "upstream": {"commit": "abc123"}, "instance": {"path": str(wb)},
            "overlay": {"directories": ["profiles/acct"], "files": [], "digests": {
                "upstream.py": hashlib.sha256(b"same").hexdigest(),
                "profiles/acct/identity.md": hashlib.sha256(b"tuned").hexdigest(),
            }}, "generated": {"directories": []},
        }), encoding="utf-8")
        original = _fake_upstream({"upstream.py": ver.blob_sha1(wb / "upstream.py")})
        try:
            res = ver.verify_overlay(record)
        finally:
            ver.fetch_upstream_tree = original
    assert res["status"] == "MISMATCH", res
    assert res["digest_undeclared"] == ["upstream.py"]


def test_overlay_reports_missing_workbench():
    """No instance is MISSING, not a pass."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        record = tmp / "overlay.json"
        record.write_text(json.dumps({
            "upstream": {"commit": "abc123"},
            "instance": {"path": str(tmp / "absent")},
            "overlay": {"files": [], "directories": []},
            "generated": {"directories": []},
        }), encoding="utf-8")
        res = ver.verify_overlay(record)

    assert res["status"] == "MISSING"


def test_overlay_reports_an_unreadable_record():
    with tempfile.TemporaryDirectory() as tmp:
        missing = Path(tmp) / "nope.json"
        res = ver.verify_overlay(missing)
    assert res["status"] == "UNVERIFIED"
    assert res["record_readable"] is False


def test_overlay_rejects_a_linked_baseline_file_even_when_bytes_match():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        wb = tmp / "wb"
        _write(wb / "upstream.py", "same")
        record = tmp / "overlay.json"
        record.write_text(json.dumps({
            "upstream": {"commit": "abc123"},
            "instance": {"path": str(wb)},
            "overlay": {"directories": [], "files": []},
            "generated": {"directories": []},
        }), encoding="utf-8")
        original_fetch = _fake_upstream({"upstream.py": ver.blob_sha1(wb / "upstream.py")})
        original_linklike = ver._linklike
        ver._linklike = lambda path: Path(path) == wb / "upstream.py" or original_linklike(path)
        try:
            res = ver.verify_overlay(record)
        finally:
            ver.fetch_upstream_tree = original_fetch
            ver._linklike = original_linklike

    assert res["status"] == "MISMATCH", res
    assert res["unsafe_links"] == ["upstream.py"]


def test_overlay_record_symlink_is_not_read_as_a_proof():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        record = tmp / "overlay.json"
        record.write_text(json.dumps({"upstream": {"commit": "abc123"}}), encoding="utf-8")
        original_linklike = ver._linklike
        ver._linklike = lambda path: Path(path) == record or original_linklike(path)
        try:
            result = ver.load_overlay(record)
        finally:
            ver._linklike = original_linklike
    assert result["readable"] is False
    assert "link" in result["reason"].lower()


def _frontend_fixture(root: Path) -> tuple[Path, Path, Path, str]:
    frontend = root / "web" / "frontend"
    _write(frontend / "package-lock.json", '{"lockfileVersion":3}\n')
    _write(frontend / "dist" / "index.html", "<main>built</main>")
    _write(frontend / "dist" / "assets" / "app.js", "console.log('built')")
    files = {
        path.relative_to(frontend / "dist").as_posix(): hashlib.sha256(
            path.read_bytes()).hexdigest()
        for path in (frontend / "dist").rglob("*") if path.is_file()
    }
    tree_sha256 = hashlib.sha256(json.dumps(
        files, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    manifest = root / "frontend-build.json"
    lock_sha256 = hashlib.sha256((frontend / "package-lock.json").read_bytes()).hexdigest()
    policy = root / "frontend-build-policy.json"
    policy.write_text(json.dumps({
        "schema": "contentops.easel-frontend-build-policy/v1",
        "package_lock_sha256": lock_sha256,
        "toolchain": {"node": "v24.16.0", "npm": "11.13.0"},
        "build_command": ["npm", "run", "build"],
    }), encoding="utf-8")
    manifest.write_text(json.dumps({
        "schema": "contentops.easel-frontend-build/v1",
        "source_commit": "abc123",
        "destination": str(frontend),
        "package_lock_sha256": lock_sha256,
        "toolchain": {"node": "v24.16.0", "npm": "11.13.0"},
        "build_command": ["npm", "run", "build"],
        "files": files,
        "tree_sha256": tree_sha256,
    }), encoding="utf-8")
    return frontend, manifest, policy, tree_sha256


def test_frontend_build_manifest_verifies_lock_and_entire_dist_tree():
    with tempfile.TemporaryDirectory() as tmp:
        frontend, manifest, policy, tree_sha256 = _frontend_fixture(Path(tmp))
        result = ver.verify_frontend_build(frontend, manifest, "abc123", policy)
    assert result["status"] == "VERIFIED", result
    assert result["file_count"] == 2
    assert result["tree_sha256"] == tree_sha256


def test_frontend_build_rejects_a_manifest_for_a_different_destination():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        frontend, manifest, policy, _ = _frontend_fixture(root)
        other = root / "other" / "web" / "frontend"
        shutil.copytree(frontend, other)
        result = ver.verify_frontend_build(other, manifest, "abc123", policy)
    assert result["status"] == "MISMATCH", result
    assert "destination" in result["reason"].lower(), result


def test_frontend_build_rejects_tampered_and_extra_dist_files():
    with tempfile.TemporaryDirectory() as tmp:
        frontend, manifest, policy, _ = _frontend_fixture(Path(tmp))
        _write(frontend / "dist" / "assets" / "app.js", "changed")
        _write(frontend / "dist" / "extra.js", "unrecorded")
        result = ver.verify_frontend_build(frontend, manifest, "abc123", policy)
    assert result["status"] == "MISMATCH", result
    assert result["mismatched"] == ["assets/app.js"]
    assert result["extra"] == ["extra.js"]


def test_frontend_build_rejects_wrong_commit_lock_or_missing_manifest():
    with tempfile.TemporaryDirectory() as tmp:
        frontend, manifest, policy, _ = _frontend_fixture(Path(tmp))
        wrong_commit = ver.verify_frontend_build(frontend, manifest, "other", policy)
        _write(frontend / "package-lock.json", "changed lock")
        wrong_lock = ver.verify_frontend_build(frontend, manifest, "abc123", policy)
        missing = ver.verify_frontend_build(frontend, manifest.with_name("absent.json"), "abc123", policy)
    assert wrong_commit["status"] == "UNVERIFIED"
    assert wrong_lock["status"] == "UNVERIFIED"
    assert missing["status"] == "UNVERIFIED"


def test_frontend_build_rejects_an_unpinned_toolchain():
    with tempfile.TemporaryDirectory() as tmp:
        frontend, manifest, policy, _ = _frontend_fixture(Path(tmp))
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        payload["toolchain"]["node"] = "v22.0.0"
        manifest.write_text(json.dumps(payload), encoding="utf-8")
        result = ver.verify_frontend_build(frontend, manifest, "abc123", policy)
    assert result["status"] == "UNVERIFIED", result
    assert "toolchain" in result["reason"]


def test_frontend_build_rejects_linked_manifest_policy_and_source_directories():
    with tempfile.TemporaryDirectory() as tmp:
        frontend, manifest, policy, _ = _frontend_fixture(Path(tmp))
        linked_paths = (manifest, policy, frontend, frontend.parent,
                        frontend.parent.parent)
        original = getattr(ver, "_linklike", lambda path: False)
        try:
            for linked in linked_paths:
                ver._linklike = lambda path, target=linked: (
                    Path(path) == target or original(path))
                result = ver.verify_frontend_build(frontend, manifest, "abc123", policy)
                assert result["status"] == "UNVERIFIED", (linked, result)
                assert "link" in result["reason"].lower(), (linked, result)
        finally:
            if hasattr(ver, "_linklike"):
                ver._linklike = original


# --- profile projection ------------------------------------------------------

def _sample_dna() -> dict:
    return {
        "schema": "contentops.account-dna/v2",
        "slug": "acct",
        "account": "X超玩·测试",
        "role": "Explore",
        "title": "这一期的标题",
        "description": "这一期的描述",
        "promise": "承诺",
        "mission": "使命",
        "tagline": "一句话",
        "decision_question": "值不值得用",
        "core_audience": ["独立开发者"],
        "audience_layers": {"reach": "广", "core": "核心", "buyer": "买"},
        "forbidden": ["invented numbers"],
        "non_negotiable": [
            "没有真实 URL 不得宣称发布成功", "不伪造数据", "保留人工审核",
            "不绕过授权", "明确失败边界",
        ],
        "not_doing": ["AI 暴富叙事"],
        "platforms": ["douyin"],
        "platform_roles": {"douyin": "Discovery"},
        "platform_note": "抖音适配说明",
        "benchmarks": {"primary": "小天fotos"},
        "narrative": {
            "mode": "RESULT_FIRST",
            "opening": "CONFLICT",
            "pace": "fast",
            "speech_rate_cpm": 220,
            "target_duration_s": [45, 60],
            "template": ["HOOK_3S_CONFLICT"],
            "cta": "先把 CLI 跑一遍",
        },
        "visual": {
            "accent": "#38BDF8",
            "composition": {"segments": [
                {"role": "screen_recording_evidence", "pct": 70},
                {"role": "vector_animation", "pct": 25},
                {"role": "comparison_card", "pct": 5},
            ]},
            "caption_style": {
                "font": "Noto Sans CJK SC", "size_px": 47,
                "primary": "#18232B", "highlight": "#38BDF8",
                "max_chars_per_line": 18,
                "safe_zone": {"margin_v_px": 120, "side_margin_ratio": 0.07},
            },
            "cover": {"composition": "居中实测主体", "title_lines": 1},
            "motion": {"allowed": ["fade_in", "crossfade"]},
        },
        "brand": {},
        "evidence": {"mode": "EVIDENCE_LED"},
        "evidence_ladder": {"L1": "可复现"},
        "acceptance_metrics": {"primary": ["留存"]},
    }


def test_profile_writes_exactly_the_six_upstream_files():
    files = prof.build_profile("acct", _sample_dna())
    assert set(files) == set(prof.PROFILE_FILES)
    assert len(files) == 6


def test_profile_does_not_project_episode_level_fields():
    """`title`/`description` describe one episode, not the account."""
    dna = _sample_dna()
    files = prof.build_profile("acct", dna)
    joined = "\n".join(files.values())
    assert dna["title"] not in joined
    assert dna["description"] not in joined


def test_profile_projects_executable_narrative_and_visual_values():
    """The Agent must receive DNA values, not unresolved field references."""
    files = prof.build_profile("acct", _sample_dna())
    style = files["style.md"]
    preferences = files["preferences.md"]

    assert "220 字/分钟" in style
    assert "45–60 秒" in style
    assert "HOOK_3S_CONFLICT" in style
    assert "#38BDF8" in style
    assert "screen_recording_evidence：70%" in style
    assert "vector_animation：25%" in style
    assert "comparison_card：5%" in style
    assert "Noto Sans CJK SC" in style
    assert "47 px" in style
    assert "底部安全区 120 px" in style
    assert "居中实测主体" in style
    assert "先把 CLI 跑一遍" in preferences
    assert "narrative.speech_rate_cpm" not in style
    assert "narrative.target_duration_s" not in style


def test_profile_carries_the_red_lines():
    files = prof.build_profile("acct", _sample_dna())
    assert "没有真实 URL 不得宣称发布成功" in files["preferences.md"]
    assert "invented numbers" in files["preferences.md"]


def test_profile_memory_is_account_specific():
    """Two accounts with different evidence rules must get different memory.

    A shared-only memory file would look complete while telling both accounts
    the same thing — the failure this projection exists to avoid.
    """
    a = _sample_dna()
    b = _sample_dna()
    b["slug"] = "acct2"
    b["evidence"] = {"mode": "EXPLANATORY",
                     "rules": ["no screen recording"],
                     "forbidden": ["mouse pointer"]}
    fa = prof.build_profile("acct", a)["memory.md"]
    fb = prof.build_profile("acct2", b)["memory.md"]
    assert fa != fb
    assert "EVIDENCE_LED" in fa
    assert "EXPLANATORY" in fb
    assert "no screen recording" in fb


def test_profile_degrades_when_a_field_is_absent():
    """A missing field is declared, not silently dropped."""
    files = prof.build_profile("acct", {"slug": "acct"})
    assert "DNA 未声明" in files["identity.md"]


def test_profile_validation_rejects_incomplete_or_cross_account_dna():
    try:
        prof.validate_profile_dna("acct", {"slug": "other"})
    except ValueError as exc:
        assert "schema" in str(exc)
        assert "slug matches selected account" in str(exc)
    else:
        raise AssertionError("incomplete or cross-account DNA was accepted")


def test_tracked_accounts_satisfy_profile_requirements():
    for slug in ("x-superplay-1024", "x-superplay-future-intelligence"):
        dna = prof.load_account(slug)
        prof.validate_profile_dna(slug, dna)


def test_profile_snapshot_is_bound_to_current_dna_and_all_six_files():
    with tempfile.TemporaryDirectory() as tmp:
        workbench = Path(tmp)
        dna = _sample_dna()
        files = prof.build_profile("acct", dna)
        prof.write_profile("acct", files, workbench)
        current = prof.verify_profile("acct", dna, workbench)
        assert current["status"] == "VERIFIED", current
        assert len(current["dna_sha256"]) == 64
        assert set(current["profile_sha256"]) == set(prof.PROFILE_FILES)

        changed_dna = dict(dna, tagline="更新过的定位")
        stale = prof.verify_profile("acct", changed_dna, workbench)
    assert stale["status"] == "STALE", stale
    assert stale["mismatched"] == ["identity.md"]
    assert (stale["actual_profile_sha256"]["identity.md"]
            != stale["profile_sha256"]["identity.md"])


def test_profile_snapshot_rejects_a_missing_contract_file():
    with tempfile.TemporaryDirectory() as tmp:
        workbench = Path(tmp)
        prof.write_profile("acct", prof.build_profile("acct", _sample_dna()), workbench)
        (workbench / "profiles" / "acct" / "memory.md").unlink()
        result = prof.verify_profile("acct", _sample_dna(), workbench)
    assert result["status"] == "STALE", result
    assert result["missing"] == ["memory.md"]


def test_profile_snapshot_rejects_linked_profile_files():
    with tempfile.TemporaryDirectory() as tmp:
        workbench = Path(tmp)
        prof.write_profile("acct", prof.build_profile("acct", _sample_dna()), workbench)
        original = prof._path_is_linklike
        prof._path_is_linklike = lambda path: path.name == "identity.md"
        try:
            result = prof.verify_profile("acct", _sample_dna(), workbench)
        finally:
            prof._path_is_linklike = original
    assert result["status"] == "STALE", result
    assert result["unsafe"] == ["identity.md"]


def test_profile_writer_rejects_a_linked_profiles_directory():
    with tempfile.TemporaryDirectory() as tmp:
        workbench = Path(tmp)
        (workbench / "profiles").mkdir()
        original = prof._path_is_linklike
        prof._path_is_linklike = lambda path: path.name == "profiles"
        try:
            try:
                prof.write_profile("acct", prof.build_profile("acct", _sample_dna()), workbench)
            except ValueError as exc:
                assert "symlink or junction" in str(exc)
            else:
                raise AssertionError("linked profiles directory was accepted")
        finally:
            prof._path_is_linklike = original


def test_profile_rejects_path_traversal_slugs():
    try:
        prof.load_account("../secret")
    except ValueError as exc:
        assert "account slug" in str(exc)
    else:
        raise AssertionError("path traversal account slug was accepted")


def test_recorded_skill_overlays_have_reproducible_repository_sources():
    record = json.loads((ROOT / "runtime" / "easel-workbench-overlay.json").read_text(
        encoding="utf-8"))
    overlay = record["overlay"]
    sources = overlay.get("source_files")
    assert isinstance(sources, dict), "skill overlay sources are not recorded"
    assert set(sources) == set(overlay["files"]), "every skill overlay needs one source"
    for target, source_rel in sources.items():
        source = (ROOT / source_rel).resolve(strict=True)
        assert source.is_relative_to(ROOT.resolve()), f"source escapes repository: {source_rel}"
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        assert digest == overlay["digests"][target], f"source digest drift: {target}"


def test_recorded_profile_digests_match_current_dna_projection():
    record = json.loads((ROOT / "runtime" / "easel-workbench-overlay.json").read_text(
        encoding="utf-8"))
    digests = record["generated_profiles"]["digests"]
    for slug in ("x-superplay-1024", "x-superplay-future-intelligence"):
        projected = prof.build_profile(slug, prof.load_account(slug))
        for name, content in projected.items():
            target = f"profiles/{slug}/{name}"
            expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
            assert digests.get(target) == expected, f"profile digest must track DNA output: {target}"


def test_overlay_verifier_can_check_rebuilt_profiles_separately_from_observed_snapshot():
    """A clean rebuild uses DNA outputs while the existing snapshot stays auditable."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        wb = tmp / "wb"
        _write(wb / "upstream.py", "same")
        profile_names = ("identity.md", "style.md", "audience.md", "platforms.md",
                         "preferences.md", "memory.md")
        for name in profile_names:
            _write(wb / "profiles" / "acct" / name, "generated")
        upstream = {"upstream.py": ver.blob_sha1(wb / "upstream.py")}
        original = _fake_upstream(upstream)
        try:
            record = tmp / "overlay.json"
            observed_digests = {
                f"profiles/acct/{name}": hashlib.sha256(
                    (b"observed" if name == "identity.md" else b"generated")).hexdigest()
                for name in profile_names
            }
            record.write_text(json.dumps({
                "upstream": {"commit": "abc123"},
                "instance": {"path": str(wb)},
                "overlay": {"directories": ["profiles/acct"], "files": [],
                            "digests": observed_digests},
                "generated_profiles": {"accounts": ["acct"], "digests": {
                    f"profiles/acct/{name}": hashlib.sha256(b"generated").hexdigest()
                    for name in profile_names}},
                "generated": {"directories": []},
            }), encoding="utf-8")
            observed = ver.verify_overlay(record)
            rebuilt = ver.verify_overlay(record, profile_mode="generated")
            incomplete = json.loads(record.read_text(encoding="utf-8"))
            incomplete["generated_profiles"]["digests"].pop("profiles/acct/memory.md")
            record.write_text(json.dumps(incomplete), encoding="utf-8")
            incomplete_result = ver.verify_overlay(record, profile_mode="generated")
        finally:
            ver.fetch_upstream_tree = original

    assert observed["status"] == "MISMATCH"
    assert observed["profile_mode"] == "observed"
    # Generated mode now also proves the installed profiles still match a fresh
    # projection of current account DNA (ADR-022 D3). This fixture uses a made-up
    # account, so the verifier cannot project DNA for it and refuses: the verdict
    # is MISMATCH, not VERIFIED. Recording that here keeps the stricter contract
    # visible; a DNA-backed VERIFIED case belongs to M2 acceptance, because a
    # fake account may not stand in for a real projection.
    assert rebuilt["status"] == "MISMATCH", rebuilt.get("reason")
    assert rebuilt["profile_freshness"]["status"] == "UNVERIFIED", rebuilt["profile_freshness"]
    assert rebuilt["profile_mode"] == "generated"
    assert incomplete_result["status"] == "UNVERIFIED"
    assert "all six files" in incomplete_result["reason"]


def test_overlay_source_verifier_rejects_drift_and_unsafe_paths():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "skill.md"
        source.write_bytes(b"reviewed source")
        expected = hashlib.sha256(source.read_bytes()).hexdigest()
        overlay = {"overlay": {
            "files": ["skills/video-script/SKILL.md"],
            "digests": {"skills/video-script/SKILL.md": expected},
            "source_files": {
                "skills/video-script/SKILL.md": "skill.md",
            },
        }}
        result = ver.verify_overlay_sources(overlay, root)
        assert result["status"] == "VERIFIED", result

        source.write_bytes(b"changed after review")
        result = ver.verify_overlay_sources(overlay, root)
        assert result["status"] == "MISMATCH", result
        assert result["mismatched"] == ["skills/video-script/SKILL.md"]

        overlay["overlay"]["source_files"]["skills/video-script/SKILL.md"] = "../escape.md"
        result = ver.verify_overlay_sources(overlay, root)
        assert result["status"] == "MISMATCH", result
        assert result["unsafe"] == ["skills/video-script/SKILL.md"]

        overlay["overlay"]["source_files"]["skills/video-script/SKILL.md"] = "skill.md"
        original = ver._linklike
        ver._linklike = lambda path: Path(path).name == "skill.md"
        try:
            result = ver.verify_overlay_sources(overlay, root)
        finally:
            ver._linklike = original
        assert result["status"] == "MISMATCH", result
        assert result["unsafe"] == ["skills/video-script/SKILL.md"]


def test_upstream_license_verifier_checks_file_bytes_and_path_safety():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        license_path = root / "LICENSE"
        license_path.write_bytes(b"Apache License\nVersion 2.0, January 2004\n")
        metadata = {
            "spdx": "Apache-2.0", "file": "LICENSE",
            "sha256": hashlib.sha256(license_path.read_bytes()).hexdigest(),
        }
        result = ver.verify_upstream_license(root, metadata)
        assert result["status"] == "VERIFIED", result
        assert result["detected_spdx"] == "Apache-2.0", result

        metadata["spdx"] = "MIT"
        result = ver.verify_upstream_license(root, metadata)
        assert result["status"] == "MISMATCH", result
        assert result["detected_spdx"] == "Apache-2.0", result
        metadata["spdx"] = "Apache-2.0"

        metadata["sha256"] = "0" * 64
        result = ver.verify_upstream_license(root, metadata)
        assert result["status"] == "MISMATCH", result

        metadata["file"] = "../LICENSE"
        result = ver.verify_upstream_license(root, metadata)
        assert result["status"] == "MISMATCH", result
        assert result["unsafe"] is True

        metadata["file"] = "LICENSE"
        metadata["sha256"] = hashlib.sha256(license_path.read_bytes()).hexdigest()
        original = ver._linklike
        ver._linklike = lambda path: Path(path).name == "LICENSE"
        try:
            result = ver.verify_upstream_license(root, metadata)
        finally:
            ver._linklike = original
        assert result["status"] == "MISMATCH", result
        assert result["unsafe"] is True


def test_overlay_verification_fails_when_repository_source_drifts():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        workbench = Path(tmp) / "workbench"
        _write(root / "extensions" / "skill.md", "reviewed source")
        _write(workbench / "baseline.txt", "same upstream")
        _write(workbench / "skills" / "video-script" / "SKILL.md", "reviewed source")
        source_digest = hashlib.sha256(b"reviewed source").hexdigest()
        record_path = root / "runtime" / "overlay.json"
        record_path.parent.mkdir(parents=True)
        upstream_tree = {
            "baseline.txt": ver.blob_sha1(workbench / "baseline.txt"),
        }
        record_path.write_text(json.dumps({
            "upstream": {"commit": "abc123", "tag": "v0.3.0",
                         "tree_sha256": ver.upstream_tree_sha256(upstream_tree)},
            "instance": {"path": str(workbench)},
            "overlay": {
                "files": ["skills/video-script/SKILL.md"],
                "directories": [],
                "digests": {"skills/video-script/SKILL.md": source_digest},
                "source_files": {"skills/video-script/SKILL.md": "extensions/skill.md"},
            },
            "generated": {"directories": []},
        }), encoding="utf-8")
        original_root = ver.ROOT
        original_fetch = _fake_upstream(upstream_tree)
        ver.ROOT = root
        try:
            valid = ver.verify_overlay(record_path, "fixture")
            assert valid["status"] == "VERIFIED", valid
            assert valid["overlay_sources"]["status"] == "VERIFIED"

            (root / "extensions" / "skill.md").write_text("changed", encoding="utf-8")
            drift = ver.verify_overlay(record_path, "fixture")

            data = json.loads(record_path.read_text(encoding="utf-8"))
            data["upstream"]["tree_sha256"] = "0" * 64
            record_path.write_text(json.dumps(data), encoding="utf-8")
            bad_tree = ver.verify_overlay(record_path, "fixture")
        finally:
            ver.ROOT = original_root
            ver.fetch_upstream_tree = original_fetch
        assert drift["status"] == "MISMATCH", drift
        assert drift["overlay_sources"]["mismatched"] == ["skills/video-script/SKILL.md"]
        assert bad_tree["status"] == "MISMATCH", bad_tree
        assert "tree summary" in bad_tree["reason"]


def test_overlay_explicit_workbench_override_ignores_stale_recorded_instance():
    """A rebuilt candidate can be checked without rewriting the tracked record."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        recorded = root / "recorded"
        candidate = root / "candidate"
        _write(recorded / "extra.txt", "must not be inspected")
        _write(candidate / "upstream.py", "same")
        upstream = {"upstream.py": ver.blob_sha1(candidate / "upstream.py")}
        record = root / "overlay.json"
        record.write_text(json.dumps({
            "upstream": {"commit": "abc123", "tag": "v0.3.0"},
            "instance": {"path": str(recorded)},
            "overlay": {"directories": [], "files": [], "digests": {}},
            "generated": {"directories": []},
        }), encoding="utf-8")
        original = _fake_upstream(upstream)
        try:
            result = ver.verify_overlay(record, "fixture", workbench_override=candidate)
        finally:
            ver.fetch_upstream_tree = original
    assert result["status"] == "VERIFIED", result
    assert Path(result["workbench_path"]) == candidate


# --- runner ------------------------------------------------------------------

TESTS = [value for name, value in sorted(globals().items())
         if name.startswith("test_") and callable(value)]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
        except Exception as exc:  # noqa: BLE001 - a test runner reports, it does not raise
            failures += 1
            print(f"FAIL {test.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"ok   {test.__name__}")
    print(f"{len(TESTS) - failures}/{len(TESTS)} ok")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
