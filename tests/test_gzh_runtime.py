"""The GZH adapter: verify a locally installed workflow, grant nothing.

The vendored workflow is not in this repository (Issue #56), so every test
builds a synthetic root outside the repository. What is pinned here:

- a missing root or lock is BLOCKED, never a pass;
- a root inside the public repository is refused;
- one changed byte, a wrong identity or an escaping lock path is refused;
- the plan never grants execution or publication, and an unresolved rights
  status keeps ``production_ready`` false even when every file verifies.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from contentops.gzh.runtime import (  # noqa: E402
    BLOCKED,
    LOCK_PATH,
    SCHEMA,
    VERIFIED,
    GzhBlocked,
    plan,
    status,
    verify,
)

TESTS = []

IDENTITY = """\
workflow_id: gzh-thinktank
account_id: thinktank
display_name: X超玩•未来智能
content_medium: wechat_article
"""
CONTRACT = """\
schema_version: 1
contract: article-workspace-governance-v1
account_id: thinktank
content_medium: wechat_article
artifact_root:
  env: GZH_ARTIFACT_ROOT
  default: "../production"
  must_be_outside_workflow_root: true
"""


def test(fn):
    TESTS.append(fn)
    return fn


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _root(temp: str, *, identity: str = IDENTITY, contract: str = CONTRACT) -> Path:
    root = Path(temp) / "gzh-workflow"
    root.mkdir(parents=True)
    (root / "workflow-identity.yaml").write_text(identity, encoding="utf-8")
    (root / "workspace-contract.yaml").write_text(contract, encoding="utf-8")
    return root


def _lock(root: Path, *, rights: str = "UNRESOLVED",
          files=None) -> Path:
    document = {
        "schema": SCHEMA,
        "tool": "gzh-thinktank",
        "identity": {
            "workflow_id": "gzh-thinktank",
            "account_id": "thinktank",
            "content_medium": "wechat_article",
        },
        "rights": {"status": rights, "note": "Issue #56"},
        "files": files if files is not None else [
            {"path": "workflow-identity.yaml",
             "sha256": _sha(root / "workflow-identity.yaml")},
            {"path": "workspace-contract.yaml",
             "sha256": _sha(root / "workspace-contract.yaml")},
        ],
    }
    path = root.parent / "lock.json"
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return path


def _code(root: Path, lock: Path, **kwargs) -> str:
    try:
        verify(root, json.loads(lock.read_text(encoding="utf-8")),
               repo_root=ROOT, **kwargs)
    except GzhBlocked as blocked:
        return blocked.code
    return ""


@test
def test_a_verified_root_is_verified_not_production_ready():
    with tempfile.TemporaryDirectory() as temp:
        root = _root(temp)
        lock = _lock(root)
        result = status(root, lock_path=lock, repo_root=ROOT)
        assert result["state"] == VERIFIED, result
        assert result["files_verified"] == 2
        assert result["rights_status"] == "UNRESOLVED"
        plan_result = plan(root, lock_path=lock, repo_root=ROOT)
        assert plan_result["execution_authorized"] is False
        assert plan_result["publish_authorized"] is False
        assert plan_result["production_ready"] is False, plan_result
        print("[ok] 1. verified files do not grant production")


@test
def test_cleared_rights_change_readiness_but_never_authority():
    with tempfile.TemporaryDirectory() as temp:
        root = _root(temp)
        lock = _lock(root, rights="CLEARED")
        result = plan(root, lock_path=lock, repo_root=ROOT)
        assert result["production_ready"] is True, result
        assert result["execution_authorized"] is False
        assert result["publish_authorized"] is False
        print("[ok] 2. cleared rights still do not authorize execution or publish")


@test
def test_a_missing_root_is_blocked():
    with tempfile.TemporaryDirectory() as temp:
        result = status(Path(temp) / "no-such-root", lock_path=LOCK_PATH,
                        repo_root=ROOT)
        assert result["state"] == BLOCKED, result
        assert result["code"] in ("MISSING_RUNTIME", "LOCK_MISSING"), result
        print("[ok] 3. no runtime is BLOCKED")


@test
def test_a_root_inside_the_repository_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        root = _root(temp)
        result = status(root, lock_path=_lock(root), repo_root=root.parent)
        assert result["state"] == BLOCKED, result
        assert result["code"] == "ROOT_INSIDE_REPO", result
        print("[ok] 4. a root inside the declared repository boundary is refused")


@test
def test_a_missing_lock_is_blocked():
    with tempfile.TemporaryDirectory() as temp:
        root = _root(temp)
        result = status(root, lock_path=Path(temp) / "nope.json", repo_root=ROOT)
        assert result["state"] == BLOCKED
        assert result["code"] == "LOCK_MISSING", result
        print("[ok] 5. a missing lock is BLOCKED")


@test
def test_one_changed_byte_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        root = _root(temp)
        lock = _lock(root)
        (root / "workspace-contract.yaml").write_text(CONTRACT.replace("1", "2"), encoding="utf-8")
        assert _code(root, lock) == "HASH_DRIFT"
        print("[ok] 6. hash drift is refused")


@test
def test_a_wrong_identity_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        root = _root(temp, identity=IDENTITY.replace("account_id: thinktank",
                                                     "account_id: explorer"))
        lock = _lock(root)
        assert _code(root, lock) == "IDENTITY_MISMATCH"
        print("[ok] 7. a live identity mismatch is refused")


@test
def test_a_lock_naming_another_identity_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        root = _root(temp)
        lock = _lock(root)
        document = json.loads(lock.read_text(encoding="utf-8"))
        document["identity"]["account_id"] = "explorer"
        lock.write_text(json.dumps(document), encoding="utf-8")
        result = status(root, lock_path=lock, repo_root=ROOT)
        assert result["state"] == BLOCKED
        assert result["code"] == "IDENTITY_UNEXPECTED", result
        print("[ok] 8. a lock for another account is refused")


@test
def test_a_lock_path_that_escapes_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        root = _root(temp)
        lock = _lock(root, files=[{"path": "../outside.yaml", "sha256": "0" * 64}])
        assert _code(root, lock) == "LOCK_PATH_ILLEGAL"
        print("[ok] 9. an escaping lock path is refused")


@test
def test_a_missing_contract_file_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        root = _root(temp)
        (root / "workspace-contract.yaml").unlink()
        lock = _lock(root, files=[{"path": "workflow-identity.yaml",
                                   "sha256": _sha(root / "workflow-identity.yaml")}])
        assert _code(root, lock) == "CONTRACT_INCOMPLETE"
        print("[ok] 10. a root without the workspace contract is refused")


@test
def test_the_lock_must_state_a_rights_status():
    with tempfile.TemporaryDirectory() as temp:
        root = _root(temp)
        lock = _lock(root)
        document = json.loads(lock.read_text(encoding="utf-8"))
        document.pop("rights")
        lock.write_text(json.dumps(document), encoding="utf-8")
        result = status(root, lock_path=lock, repo_root=ROOT)
        assert result["state"] == BLOCKED
        assert result["code"] == "LOCK_MALFORMED", result
        print("[ok] 11. an unstated rights status is not 'cleared'")


@test
def test_the_cli_has_no_execute_or_publish_command():
    import gzh_runtime

    for forbidden in ("execute", "publish", "approve"):
        try:
            gzh_runtime.main([forbidden])
        except SystemExit as exc:
            assert exc.code != 0, f"{forbidden!r} was accepted"
        else:
            raise AssertionError(f"{forbidden!r} was accepted as a command")
    print("[ok] 12. the CLI refuses execute/publish/approve")


def main() -> int:
    failures = []
    for fn in TESTS:
        try:
            fn()
        except AssertionError as exc:
            failures.append((fn.__name__, str(exc)))
            print(f"[FAIL] {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append((fn.__name__, repr(exc)))
            print(f"[ERR ] {fn.__name__}: {exc!r}")
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print(f"\nAll {len(TESTS)} GZH runtime tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
