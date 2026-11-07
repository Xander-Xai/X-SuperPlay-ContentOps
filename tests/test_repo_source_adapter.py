"""Offline contract checks for immutable GitHub source snapshots."""

from __future__ import annotations

import io
import json
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.evidence import (  # noqa: E402
    CLAIM_SCHEMA, ClaimLedger, RepoSourceAdapter, RepoSourceError,
    SourceArtifactError, build_artifacts,
)


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def _opener_for(license_id="Apache-2.0"):
    commit = "a" * 40
    paths = ["README.md", "LICENSE", "docs/ARCHITECTURE.md",
             "src/contentops/engine.py", "media/demo.mp4"]

    def opener(request, timeout=None):
        url = request.full_url
        parsed = urlparse(url)
        if parsed.netloc == "api.github.com":
            path = parsed.path
            if path == "/repos/acme/widget":
                payload = {"full_name": "acme/widget", "default_branch": "main",
                           "license": {"spdx_id": license_id} if license_id else None}
            elif path == "/repos/acme/widget/commits/main":
                payload = {"sha": commit}
            elif path == f"/repos/acme/widget/git/trees/{commit}":
                payload = {"tree": [{"type": "blob", "path": p} for p in paths]}
            else:
                raise AssertionError(f"unexpected API URL: {url}")
            return Response(json.dumps(payload).encode())
        if parsed.netloc == "raw.githubusercontent.com":
            path = parsed.path.rsplit("/", 1)[-1]
            contents = {
                "README.md": b"# Widget\nThe widget handles event replay.\n",
                "LICENSE": b"Apache License Version 2.0\n",
                "ARCHITECTURE.md": b"Events pass through a bounded queue.\n",
                "engine.py": b"def run_pipeline():\n    return 'compose'\n",
            }
            if path not in contents:
                raise AssertionError(f"unexpected raw URL: {url}")
            return Response(contents[path])
        raise AssertionError(f"unexpected host: {parsed.netloc}")

    return opener


def test_fetch_pins_selected_files_and_hashes_under_declared_license():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        output = root / "project" / "sources" / "repo"
        snapshot = RepoSourceAdapter(opener=_opener_for()).fetch(
            "https://github.com/acme/widget", output_dir=output, repo_root=root)
        assert snapshot.repository == "acme/widget"
        assert snapshot.commit == "a" * 40
        assert snapshot.license_permission == "LICENSED"
        assert {row["title"] for row in snapshot.files} == {
            "acme/widget/LICENSE", "acme/widget/README.md",
            "acme/widget/docs/ARCHITECTURE.md", "acme/widget/src/contentops/engine.py",
        }
        assert all(len(row["sha256"]) == 64 for row in snapshot.files)
        assert all(row["source_commit"] == snapshot.commit for row in snapshot.files)
        manifest = json.loads((root / snapshot.manifest_path).read_text(encoding="utf-8"))
        assert manifest["license_permission"] == "LICENSED"
        assert all(row["evidence_capable"] for row in manifest["files"])
        sidecar = json.loads((root / "project" / "sources" / "source-refs.json")
                             .read_text(encoding="utf-8"))
        artifacts = build_artifacts(sidecar["refs"], repo_root=root)
        readme_id = next(key for key, value in artifacts.items()
                         if value.title.endswith("/README.md"))
        ledger = ClaimLedger.from_payload({"schema": CLAIM_SCHEMA, "claims": [{
            "id": "C1", "text": "The widget handles event replay.",
            "artifacts": [readme_id], "quotes": ["The widget handles event replay."],
        }]})
        assert ledger.verify(artifacts, root) == []
        readme = next(row for row in sidecar["refs"] if row["title"].endswith("/README.md"))
        (root / readme["path"]).write_text("tampered bytes\n", encoding="utf-8")
        try:
            build_artifacts(sidecar["refs"], repo_root=root)
        except SourceArtifactError as exc:
            assert "declared sha256" in str(exc)
        else:
            raise AssertionError("modified repository snapshot must fail its pinned hash")


def test_public_visibility_without_recognized_license_cannot_back_claims():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        snapshot = RepoSourceAdapter(opener=_opener_for(None)).fetch(
            "https://github.com/acme/widget", output_dir=root / "snapshot", repo_root=root)
        assert snapshot.license_permission == "NONE"
        assert all(not row["evidence_capable"] for row in snapshot.files)


def test_rejects_non_repository_urls_and_nonempty_destination():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        adapter = RepoSourceAdapter(opener=_opener_for())
        try:
            adapter.fetch("https://github.com/acme/widget/issues/1",
                          output_dir=root / "snapshot", repo_root=root)
        except RepoSourceError as exc:
            assert "source URL" in str(exc)
        else:
            raise AssertionError("non-repository URL should be rejected")
        output = root / "existing"
        output.mkdir()
        (output / "preserve.txt").write_text("keep", encoding="utf-8")
        try:
            adapter.fetch("https://github.com/acme/widget",
                          output_dir=output, repo_root=root)
        except RepoSourceError as exc:
            assert "not empty" in str(exc)
        else:
            raise AssertionError("nonempty destination should be rejected")
        assert (output / "preserve.txt").read_text(encoding="utf-8") == "keep"


if __name__ == "__main__":
    tests = [value for name, value in globals().copy().items()
             if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print(f"[ok] {test.__name__}")
    print(f"PASS: {len(tests)} GitHub source adapter checks")
