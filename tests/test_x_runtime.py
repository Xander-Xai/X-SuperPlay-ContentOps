"""X editorial runtime adapter: verify the local gate and describe the manual operations.

Run: python tests/test_x_runtime.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.x import runtime  # noqa: E402


def _fixture(tmp: str):
    repo = Path(tmp) / "repo"
    (repo / "config" / "accounts").mkdir(parents=True)
    (repo / "projects" / "x-growth-en").mkdir(parents=True)
    (repo / "scripts").mkdir()
    (repo / "src" / "contentops" / "publish").mkdir(parents=True)
    account = {
        "schema": "contentops.account-dna/v2",
        "slug": "x-superplay-english",
        "account": "X SuperPlay English",
    }
    (repo / "config" / "accounts" / "x-superplay-english.json").write_text(
        json.dumps(account), encoding="utf-8")
    (repo / "projects" / "x-growth-en" / "project.yaml").write_text(
        "id: x-growth-en\n", encoding="utf-8")
    (repo / "scripts" / "x_post.py").write_text("# gate\n", encoding="utf-8")
    (repo / "src" / "contentops" / "publish" / "publisher.py").write_text(
        "# publisher\n", encoding="utf-8")
    return repo


def _raises(code, fn):
    try:
        fn()
    except runtime.XBlocked as exc:
        assert exc.code == code, f"expected {code}, got {exc.code}: {exc}"
        return
    raise AssertionError(f"expected XBlocked {code}")


def test_a_valid_x_workspace_is_verified_manual_only():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _fixture(tmp)
        result = runtime.verify(repo_root=repo)
    assert result["state"] == "VERIFIED"
    assert result["workflow_id"] == "x-editorial"
    assert result["account_slug"] == "x-superplay-english"
    assert result["publish_mode"] == "MANUAL_ONLY"
    assert result["api_used"] is False
    assert result["execution_authorized"] is False
    assert result["publish_authorized"] is False
    assert result["production_ready"] is False


def test_missing_account_is_blocked():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _fixture(tmp)
        (repo / "config" / "accounts" / "x-superplay-english.json").unlink()
        _raises("ACCOUNT_MISSING", lambda: runtime.verify(repo_root=repo))


def test_wrong_account_schema_is_blocked():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _fixture(tmp)
        path = repo / "config" / "accounts" / "x-superplay-english.json"
        path.write_text(json.dumps({"schema": "something/else", "slug": "x"}), encoding="utf-8")
        _raises("ACCOUNT_SCHEMA", lambda: runtime.verify(repo_root=repo))


def test_the_x_editorial_account_contract_is_also_accepted():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _fixture(tmp)
        path = repo / "config" / "accounts" / "x-superplay-english.json"
        path.write_text(json.dumps({
            "schema": "contentops.x-account/v1",
            "slug": "x-superplay-english",
        }), encoding="utf-8")
        result = runtime.verify(repo_root=repo)
    assert result["state"] == "VERIFIED"
    assert result["account_slug"] == "x-superplay-english"


def test_missing_project_or_gate_code_is_blocked():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _fixture(tmp)
        (repo / "projects" / "x-growth-en" / "project.yaml").unlink()
        _raises("PROJECT_MISSING", lambda: runtime.verify(repo_root=repo))
        repo = _fixture(tmp + "/b")
        (repo / "scripts" / "x_post.py").unlink()
        _raises("GATE_CODE_MISSING", lambda: runtime.verify(repo_root=repo))


def test_plan_describes_manual_operations_and_grants_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _fixture(tmp)
        result = runtime.plan(repo_root=repo)
    assert result["state"] == "VERIFIED"
    assert result["execution_authorized"] is False
    assert result["publish_authorized"] is False
    assert result["production_ready"] is False
    assert result["api_used"] is False
    names = [item["name"] for item in result["operations"]]
    assert names == ["new", "check", "package", "mark_published", "verify_log"]
    for item in result["operations"]:
        assert item["authority"] in ("OPERATOR", "READ_ONLY")
        assert "api" not in item["command"].lower()


def test_status_missing_workspace_is_blocked_not_a_pass():
    with tempfile.TemporaryDirectory() as tmp:
        repo = _fixture(tmp)
        (repo / "projects" / "x-growth-en" / "project.yaml").unlink()
        result = runtime.status(repo_root=repo)
    assert result["state"] == "BLOCKED"
    assert result["code"] == "PROJECT_MISSING"


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
