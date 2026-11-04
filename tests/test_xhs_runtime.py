"""XHS runtime adapter: locate, hash-verify and describe; never execute or publish.

Run: python tests/test_xhs_runtime.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.xhs import runtime  # noqa: E402


def _fixture(tmp: str):
    base = Path(tmp)
    repo = base / "repo"
    repo.mkdir()
    root = base / "xhs"
    (root / "contracts").mkdir(parents=True)
    files = {
        "WORKSPACE_CONTRACT.md": b"# workspace contract\n",
        "LICENSE": b"Apache License\nVersion 2.0\n",
        "contracts/publication-package.schema.json": b"{}\n",
    }
    entries = []
    for relative, data in files.items():
        target = root / relative
        target.write_bytes(data)
        entries.append({"path": relative, "sha256": hashlib.sha256(data).hexdigest()})
    lock = {
        "schema": runtime.SCHEMA,
        "tool": "xhs-fa",
        "identity": {
            "workflow_id": "xhs-fa",
            "account_id": "thinktank",
            "content_medium": "xiaohongshu_image",
        },
        "rights": {
            "status": "PARTIALLY_CLEARED",
            "note": "root Apache-2.0; exclude the AGPL skill; local internal use only",
            "evidence": ["reports/audits/rights-audit-2026-11-04.md"],
        },
        "files": entries,
    }
    lock_path = base / "lock.json"
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    return root, repo, lock, lock_path


def _raises(code, fn):
    try:
        fn()
    except runtime.XhsBlocked as exc:
        assert exc.code == code, f"expected {code}, got {exc.code}: {exc}"
        return
    raise AssertionError(f"expected XhsBlocked {code}")


def test_a_valid_root_verifies_every_locked_byte():
    with tempfile.TemporaryDirectory() as tmp:
        root, repo, lock, _ = _fixture(tmp)
        result = runtime.verify(root, lock, repo_root=repo)
    assert result["state"] == "VERIFIED"
    assert result["files_verified"] == 3
    assert result["rights_status"] == "PARTIALLY_CLEARED"
    assert result["workflow_id"] == "xhs-fa"
    assert result["production_ready"] is False
    assert result["publish_authorized"] is False


def test_a_changed_file_is_hash_drift():
    with tempfile.TemporaryDirectory() as tmp:
        root, repo, lock, _ = _fixture(tmp)
        (root / "LICENSE").write_bytes(b"changed")
        _raises("HASH_DRIFT", lambda: runtime.verify(root, lock, repo_root=repo))


def test_a_missing_file_is_hash_drift():
    with tempfile.TemporaryDirectory() as tmp:
        root, repo, lock, _ = _fixture(tmp)
        (root / "WORKSPACE_CONTRACT.md").unlink()
        _raises("HASH_DRIFT", lambda: runtime.verify(root, lock, repo_root=repo))


def test_unexpected_identity_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        root, repo, lock, _ = _fixture(tmp)
        lock["identity"]["account_id"] = "someone-else"
        _raises("IDENTITY_UNEXPECTED", lambda: runtime.verify(root, lock, repo_root=repo))


def test_a_root_inside_the_public_repository_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        root, repo, lock, _ = _fixture(tmp)
        inside = repo / "vendor-xhs"
        inside.mkdir()
        _raises("ROOT_INSIDE_REPO", lambda: runtime.locate_root(inside, repo_root=repo))


def test_a_root_under_the_gitignored_runtime_tree_is_allowed():
    with tempfile.TemporaryDirectory() as tmp:
        root, repo, lock, _ = _fixture(tmp)
        target = repo / ".runtime" / "workflows" / "xhs"
        target.parent.mkdir(parents=True)
        root.rename(target)
        assert runtime.locate_root(target, repo_root=repo) == target.resolve()


def test_a_lock_path_escape_is_refused():
    with tempfile.TemporaryDirectory() as tmp:
        root, repo, lock, _ = _fixture(tmp)
        lock["files"][0]["path"] = "../escape.md"
        _raises("LOCK_PATH_ILLEGAL", lambda: runtime.verify(root, lock, repo_root=repo))


def test_plan_describes_operations_and_grants_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        root, repo, lock, lock_path = _fixture(tmp)
        result = runtime.plan(root, lock_path=lock_path, repo_root=repo)
    assert result["state"] == "VERIFIED"
    assert result["execution_authorized"] is False
    assert result["publish_authorized"] is False
    assert result["production_ready"] is False
    assert result["easel_surface"] == "graphic_text_manual_package"
    names = [item["name"] for item in result["operations"]]
    assert names == ["workspace_new", "gate", "finalize", "publication_package"]
    for item in result["operations"]:
        assert "publish" not in item["command"].lower()
        assert item["authority"] in ("OPERATOR", "READ_ONLY")


def test_missing_root_is_blocked_not_a_pass():
    with tempfile.TemporaryDirectory() as tmp:
        _, repo, _, lock_path = _fixture(tmp)
        result = runtime.status(Path(tmp) / "absent", lock_path=lock_path, repo_root=repo)
    assert result["state"] == "BLOCKED"
    assert result["code"] == "MISSING_RUNTIME"


def test_missing_lock_is_blocked_not_a_pass():
    with tempfile.TemporaryDirectory() as tmp:
        root, repo, _, _ = _fixture(tmp)
        result = runtime.status(root, lock_path=Path(tmp) / "absent.json", repo_root=repo)
    assert result["state"] == "BLOCKED"
    assert result["code"] == "LOCK_MISSING"


TESTS = [value for name, value in sorted(globals().items())
         if name.startswith("test_") and callable(value)]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
            print(f"ok   {test.__name__}")
        except Exception as exc:  # noqa: BLE001 - a runner reports, it does not hide
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
    total = len(TESTS)
    print(f"{total - failures}/{total} ok")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
