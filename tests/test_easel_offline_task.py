"""Contract tests for the deterministic, offline-only Easel task path."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from process_utils import hidden_popen  # noqa: E402

from contentops.easel.offline_task import (  # noqa: E402
    OfflineTaskError,
    run_offline_draft_task,
)
import contentops.easel.offline_task as offline_task  # noqa: E402
from contentops.easel.guard import GuardMiddleware, HostPolicy  # noqa: E402
from contentops.easel.offline_api import OfflineTaskAPI, SUBMIT_PATH  # noqa: E402


def _project_root(account: str = "x-superplay-1024") -> tuple[tempfile.TemporaryDirectory, Path, Path]:
    tmp = tempfile.TemporaryDirectory()
    root = Path(tmp.name)
    project = root / "projects" / "offline-test"
    project.mkdir(parents=True)
    # ADR-022 D3: an offline task is bound to one account, and the project must
    # say which. An unbound project is rejected with PROJECT_ACCOUNT_MISSING, so
    # every fixture that expects a draft to be written declares its account.
    (project / "project.yaml").write_text(f"account_slug: {account}\n", encoding="utf-8")
    accounts = root / "config" / "accounts"
    accounts.mkdir(parents=True)
    for account in ("x-superplay-1024", "x-superplay-future-intelligence",
                    "x-superplay-english"):
        shutil.copyfile(ROOT / "config" / "accounts" / f"{account}.json",
                        accounts / f"{account}.json")
    scripts = root / "scripts"
    scripts.mkdir()
    shutil.copyfile(ROOT / "scripts" / "easel_profile.py",
                    scripts / "easel_profile.py")
    return tmp, root, root / "projects" / "offline-test"


def _frontend_proof_fixture(root: Path) -> Path:
    """Create a synthetic pinned frontend receipt entirely inside ``root``."""
    runtime = root / "runtime"
    runtime.mkdir(exist_ok=True)
    workbench = root / "synthetic-workbench"
    frontend = workbench / "web" / "frontend"
    lock = b'{"lockfileVersion":3}\n'
    (frontend / "package-lock.json").parent.mkdir(parents=True, exist_ok=True)
    (frontend / "package-lock.json").write_bytes(lock)
    dist = frontend / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<main>synthetic</main>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('synthetic')", encoding="utf-8")
    files = {
        path.relative_to(dist).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in dist.rglob("*") if path.is_file()
    }
    tree_sha = hashlib.sha256(json.dumps(
        files, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    lock_sha = hashlib.sha256(lock).hexdigest()
    toolchain = {"node": "v24.16.0", "npm": "11.13.0"}
    build_command = ["npm", "run", "build"]
    (runtime / "easel-workbench-overlay.json").write_text(json.dumps({
        "instance": {"path": str(workbench)},
        "upstream": {"commit": "synthetic-commit"},
    }), encoding="utf-8")
    (runtime / "easel-workbench-build-policy.json").write_text(json.dumps({
        "schema": "contentops.easel-frontend-build-policy/v1",
        "package_lock_sha256": lock_sha,
        "toolchain": toolchain,
        "build_command": build_command,
    }), encoding="utf-8")
    (runtime / "easel-workbench-frontend-build.json").write_text(json.dumps({
        "schema": "contentops.easel-frontend-build/v1",
        "source_commit": "synthetic-commit",
        "package_lock_sha256": lock_sha,
        "toolchain": toolchain,
        "build_command": build_command,
        "files": files,
        "tree_sha256": tree_sha,
    }), encoding="utf-8")
    shutil.copyfile(ROOT / "scripts" / "verify_easel_runtime.py",
                    root / "scripts" / "verify_easel_runtime.py")
    return runtime / "easel-workbench-overlay.json"


def _call_api(app, method: str, path: str, *, body: bytes = b"",
              query: bytes = b"", content_type: str = "application/json",
              origin: str | None = "http://127.0.0.1:7861"):
    # A browser request that reaches this API carries a loopback Origin, and the
    # guard requires the Origin to match the Host for state-changing routes
    # (ADR-022 D3). Defaulting to the matching origin keeps every caller honest
    # about what a real request looks like; a test that wants the refusal passes
    # a different origin explicitly.
    sent = []
    messages = [{"type": "http.request", "body": body, "more_body": False}]

    async def receive():
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    headers = [(b"host", b"127.0.0.1:7861"),
               (b"content-type", content_type.encode("ascii"))]
    if origin is not None:
        headers.append((b"origin", origin.encode("ascii")))
    scope = {
        "type": "http", "method": method, "path": path,
        "raw_path": path.encode("ascii"), "query_string": query,
        "headers": headers,
        "scheme": "http", "server": ("127.0.0.1", 7861),
        "client": ("127.0.0.1", 50000),
    }
    import asyncio
    asyncio.run(app(scope, receive, send))
    status = next(item["status"] for item in sent if item["type"] == "http.response.start")
    response = b"".join(item.get("body", b"") for item in sent
                        if item["type"] == "http.response.body")
    try:
        payload = json.loads(response.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        payload = response
    return status, payload, sent


def test_offline_task_writes_profile_bound_draft_and_receipt():
    tmp, root, project = _project_root()
    with tmp:
        result = run_offline_draft_task(
            repo_root=root,
            account="x-superplay-1024", project_slug="offline-test",
            brief="验证一个明确标注离线的工作台任务。", idempotency_key="first",
        )
        draft = project / result["artifact"]["path"]
        receipt = project / result["receipt"]
        assert result["execution"] == "OFFLINE_ONLY"
        assert result["status"] == "OFFLINE_DRAFT_ONLY"
        assert result["production_ready"] is False
        assert result["publish_authorized"] is False
        assert result["human_review"] == "PENDING"
        assert result["frontend_build"] == "UNVERIFIED"
        assert result["frontend_dist_tree_sha256"] is None
        assert draft.is_file() and receipt.is_file()
        draft_bytes = draft.read_bytes()
        assert hashlib.sha256(draft_bytes).hexdigest() == result["artifact"]["sha256"]
        text = draft_bytes.decode("utf-8")
        assert "尚未由 Agent 或人工撰写" in text
        assert "220 字/分钟" in text
        stored = json.loads(receipt.read_text(encoding="utf-8"))
        assert stored["task_id"] == result["task_id"]
        assert stored["dna_sha256"] == result["dna_sha256"]


def test_offline_receipts_never_promote_a_corrupt_overlay_or_frontend():
    for corruption, expected_overlay, expected_frontend in (
        ("overlay", "UNAVAILABLE", "UNVERIFIED"),
        ("dist", "PRESENT_UNVERIFIED", "MISMATCH"),
    ):
        tmp, root, _ = _project_root()
        with tmp:
            overlay = _frontend_proof_fixture(root)
            if corruption == "overlay":
                overlay.write_text("{broken json", encoding="utf-8")
            else:
                dist_file = root / "synthetic-workbench" / "web" / "frontend" / "dist" / "assets" / "app.js"
                dist_file.write_text("tampered", encoding="utf-8")
            receipt = run_offline_draft_task(
                repo_root=root, account="x-superplay-1024", project_slug="offline-test",
                brief=f"检测 {corruption} 完整性失败时的降级", idempotency_key=f"bad-{corruption}",
            )
            assert receipt["overlay_verification"] == expected_overlay, receipt
            assert receipt["frontend_build"] == expected_frontend, receipt
            assert receipt["frontend_dist_tree_sha256"] is None
            assert receipt["frontend_file_count"] is None
            assert receipt["production_ready"] is False
            assert receipt["publish_authorized"] is False
            assert receipt["human_review"] == "PENDING"


def test_same_idempotency_key_returns_same_receipt_without_second_artifact():
    tmp, root, project = _project_root()
    with tmp:
        kwargs = dict(repo_root=root,
                      account="x-superplay-1024", project_slug="offline-test",
                      brief="相同输入", idempotency_key="stable-key")
        first = run_offline_draft_task(**kwargs)
        second = run_offline_draft_task(**kwargs)
        assert second["task_id"] == first["task_id"]
        assert second["receipt"] == first["receipt"]
        assert len(list((project / "drafts").glob("easel-offline-*.md"))) == 1


def test_user_brief_cannot_inject_html_into_the_generated_markdown():
    tmp, root, project = _project_root()
    with tmp:
        result = run_offline_draft_task(
            repo_root=root, account="x-superplay-1024", project_slug="offline-test",
            brief="主题 <img src=x onerror=alert(1)>", idempotency_key="html-safe",
        )
        content = (project / result["artifact"]["path"]).read_text(encoding="utf-8")
        assert "<img" not in content
        assert "&lt;img" in content


def test_idempotency_key_cannot_be_reused_for_different_input():
    tmp, root, _ = _project_root()
    with tmp:
        base = dict(repo_root=root,
                    account="x-superplay-1024", project_slug="offline-test",
                    idempotency_key="stable-key")
        run_offline_draft_task(**base, brief="原始任务")
        try:
            run_offline_draft_task(**base, brief="替换后的任务")
        except OfflineTaskError as exc:
            assert exc.code == "IDEMPOTENCY_CONFLICT" and exc.status == 409
        else:
            raise AssertionError("same key with different input was accepted")


def test_idempotent_replay_refuses_a_tampered_draft():
    tmp, root, project = _project_root()
    with tmp:
        kwargs = dict(repo_root=root, account="x-superplay-1024",
                      project_slug="offline-test", brief="不可静默替换",
                      idempotency_key="tamper-check")
        first = run_offline_draft_task(**kwargs)
        (project / first["artifact"]["path"]).write_text("tampered", encoding="utf-8")
        try:
            run_offline_draft_task(**kwargs)
        except OfflineTaskError as exc:
            assert exc.code == "IDEMPOTENCY_STATE_INVALID" and exc.status == 409
        else:
            raise AssertionError("tampered output was returned as an idempotent success")


def test_second_account_changes_the_profile_binding_and_constraints():
    tmp, root, project = _project_root("x-superplay-future-intelligence")
    with tmp:
        result = run_offline_draft_task(
            repo_root=root,
            account="x-superplay-future-intelligence", project_slug="offline-test",
            brief="检查未来智能画像", idempotency_key="fi",
        )
        assert result["dna_sha256"]
        text = (project / result["artifact"]["path"]).read_text(encoding="utf-8")
        assert "30, 300" in text
        assert "ENGINEERING_WALKTHROUGH" in text


def test_invalid_project_account_brief_and_key_fail_closed():
    tmp, root, _ = _project_root()
    with tmp:
        common = dict(repo_root=root,
                      account="x-superplay-1024", project_slug="offline-test",
                      brief="valid", idempotency_key="valid")
        for changed, code in [
            ({"project_slug": "../escape"}, "PROJECT_INVALID"),
            # The binding is checked before the DNA lookup, so an account that is
            # not the project's is a mismatch here. A *missing* DNA for the bound
            # account is covered separately below.
            ({"account": "unknown"}, "PROJECT_ACCOUNT_MISMATCH"),
            ({"account": 42}, "ACCOUNT_INVALID"),
            ({"brief": " "}, "INPUT_INVALID"),
            ({"brief": "\ud800"}, "INPUT_INVALID"),
            ({"brief": "x" * 8_001}, "INPUT_INVALID"),
            ({"idempotency_key": "bad key"}, "IDEMPOTENCY_KEY_INVALID"),
        ]:
            try:
                run_offline_draft_task(**(common | changed))
            except OfflineTaskError as exc:
                assert exc.code == code, (code, exc.code)
            else:
                raise AssertionError(f"invalid request accepted: {changed}")


def test_missing_dna_for_the_bound_account_is_account_missing():
    """A project bound to an account whose DNA is absent fails as ACCOUNT_MISSING.

    Kept separate from the request-validation table: there the failure is a
    mismatch between two known values, here it is a value the repository cannot
    resolve at all, and the two are different facts about the request.
    """
    tmp, root, _ = _project_root("x-superplay-absent")
    with tmp:
        try:
            run_offline_draft_task(
                repo_root=root, account="x-superplay-absent", project_slug="offline-test",
                brief="valid", idempotency_key="valid",
            )
        except OfflineTaskError as exc:
            assert exc.code == "ACCOUNT_MISSING", exc.code
        else:
            raise AssertionError("a project bound to an absent account was accepted")


def test_active_project_lock_blocks_a_second_task():
    tmp, root, project = _project_root()
    with tmp:
        lock_fd = offline_task._acquire_project_lock(project / ".easel-offline-task.lock")
        try:
            try:
                run_offline_draft_task(
                    repo_root=root,
                    account="x-superplay-1024", project_slug="offline-test",
                    brief="一个任务", idempotency_key="key",
                )
            except OfflineTaskError as exc:
                assert exc.code == "TASK_BUSY" and exc.status == 409
            else:
                raise AssertionError("concurrent task was accepted")
        finally:
            offline_task._release_project_lock(lock_fd)


def test_interrupted_write_resumes_the_same_idempotent_task():
    tmp, root, project = _project_root()
    with tmp:
        original = offline_task._atomic_write
        failed = False

        def fail_once(path: Path, data: bytes) -> None:
            nonlocal failed
            if (path.name.startswith("easel-offline-") and "idempotency" not in path.name
                    and path.suffix == ".json" and not failed):
                failed = True
                raise OSError("simulated interruption before receipt write")
            original(path, data)

        offline_task._atomic_write = fail_once
        try:
            run_offline_draft_task(
                repo_root=root, account="x-superplay-1024", project_slug="offline-test",
                brief="可恢复任务", idempotency_key="recoverable",
            )
        except OfflineTaskError as exc:
            # An interruption is reported as a task failure with its own redacted
            # receipt (ADR-022 D3), not as a bare OSError escaping the API.
            assert exc.code == "TASK_INTERNAL_ERROR", exc.code
            assert exc.failure_receipt, exc
            assert (root / "projects" / "offline-test" / exc.failure_receipt).is_file()
        else:
            raise AssertionError("interruption injection did not run")
        finally:
            offline_task._atomic_write = original

        result = run_offline_draft_task(
            repo_root=root, account="x-superplay-1024", project_slug="offline-test",
            brief="可恢复任务", idempotency_key="recoverable",
        )
        assert result["task_id"]
        assert len(list((project / "drafts").glob("easel-offline-*.md"))) == 1
        completed = [p for p in (project / "receipts").glob("easel-offline-*.json")
                     if "idempotency" not in p.name and "-failure-" not in p.name]
        assert len(completed) == 1, completed
        # The interrupted attempt left exactly one redacted failure receipt, and
        # the resume did not add a second one.
        failed_attempts = list((project / "receipts").glob("easel-offline-failure-*.json"))
        assert len(failed_attempts) == 1, failed_attempts


def test_linked_projects_directory_is_refused():
    tmp, root, _ = _project_root()
    with tmp:
        original = offline_task._linklike
        projects = root / "projects"
        # Compare resolved paths: the task resolves its roots, and a Windows runner
        # hands the same directory back in another form (8.3 short name).
        offline_task._linklike = (
            lambda path: Path(path).resolve() == projects.resolve())
        try:
            try:
                run_offline_draft_task(
                    repo_root=root, account="x-superplay-1024", project_slug="offline-test",
                    brief="不能越过链接目录", idempotency_key="safe-path",
                )
            except OfflineTaskError as exc:
                assert exc.code == "PROJECT_UNSAFE" and exc.status == 403
            else:
                raise AssertionError("linked projects directory was accepted")
        finally:
            offline_task._linklike = original


def _run_stdin_cli(payload: bytes) -> tuple[int, bytes]:
    """Run the CLI with ``payload`` on stdin, through the shared process layer.

    ``hidden_popen`` is the sanctioned way to start a child here: a bare
    ``subprocess.run`` flashes a console window on Windows, which
    ``check_subprocess_policy.py`` refuses. Bytes go in and out so the JSON is
    compared exactly as the tool printed it.
    """
    proc = hidden_popen([sys.executable, str(ROOT / "scripts" / "easel_offline_task.py")],
                        stdin=subprocess.PIPE, text=False)
    out, _ = proc.communicate(payload, timeout=60)
    return proc.returncode, out


def test_stdin_cli_rejects_unknown_fields_before_execution():
    code, out = _run_stdin_cli(
        b'{"account":"x-superplay-1024","project":"offline-test",'
        b'"brief":"x","idempotency_key":"a","extra":"reject"}')
    assert code == 2, code
    response = json.loads(out.decode("utf-8"))
    assert response["error"] == "INPUT_SCHEMA_INVALID", response
    code, _ = _run_stdin_cli(
        b'{"account":"x-superplay-1024","project":"offline-test",'
        b'"brief":"x","idempotency_key":"a","account":"other"}')
    assert code == 2, code


def test_guarded_api_submits_offline_task_and_reads_its_project_receipt():
    tmp, root, _ = _project_root()
    with tmp:
        upstream = lambda scope, receive, send: None
        app = GuardMiddleware(OfflineTaskAPI(upstream, root),
                              HostPolicy(allow_offline_tasks=True))
        request = {"account": "x-superplay-1024", "project": "offline-test",
                   "brief": "通过窄接口完成离线任务闭环", "idempotency_key": "http-e2e"}
        status, submitted, sent = _call_api(
            app, "POST", SUBMIT_PATH, body=json.dumps(request, ensure_ascii=False).encode("utf-8"))
        assert status == 200, submitted
        assert submitted["execution"] == "OFFLINE_ONLY"
        assert any(k.lower() == b"x-contentops-host-guard" for k, _ in sent[0]["headers"])
        task_path = f"/api/contentops/draft-task/{submitted['task_id']}"
        query = b"account=x-superplay-1024&project=offline-test"
        status_code, readback, _ = _call_api(app, "GET", task_path, query=query)
        assert status_code == 200, readback
        assert readback["task_id"] == submitted["task_id"]
        assert readback["artifact"] == submitted["artifact"]
        status_code, draft, _ = _call_api(app, "GET", task_path + "/draft", query=query)
        assert status_code == 200, draft
        assert "OFFLINE_SCAFFOLD_ONLY" in draft["content"]
        assert draft["artifact"] == submitted["artifact"]


def test_profile_selector_api_returns_only_validated_dna_values():
    tmp, root, _ = _project_root()
    with tmp:
        app = GuardMiddleware(OfflineTaskAPI(lambda scope, receive, send: None, root),
                              HostPolicy(allow_offline_tasks=True))
        status, result, _ = _call_api(app, "GET", "/api/contentops/profiles")
        assert status == 200, result
        profiles = {item["slug"]: item for item in result["profiles"]}
        assert set(profiles) == {"x-superplay-1024", "x-superplay-future-intelligence"}
        assert result["excluded_accounts"] == [
            {"slug": "x-superplay-english", "reason": "ACCOUNT_DNA_INVALID"}
        ]
        assert profiles["x-superplay-1024"]["narrative"]["speech_rate_cpm"] == 220
        assert profiles["x-superplay-future-intelligence"]["narrative"]["target_duration_s"] == [30, 300]
        assert "api_key" not in json.dumps(result).lower()


def test_profile_projector_failure_blocks_selector_instead_of_excluding_accounts():
    tmp, root, _ = _project_root()
    with tmp:
        (root / "scripts" / "easel_profile.py").unlink()
        app = GuardMiddleware(OfflineTaskAPI(lambda scope, receive, send: None, root),
                              HostPolicy(allow_offline_tasks=True))
        status, result, _ = _call_api(app, "GET", "/api/contentops/profiles")
        assert status == 500
        assert result == {"error": "PROFILE_PROJECTOR_UNAVAILABLE",
                          "detail": "Easel profile projector is unavailable"}


def test_offline_task_ui_serves_only_hash_pinned_assets_with_csp():
    from contentops.easel import offline_api

    tmp, root, _ = _project_root()
    with tmp:
        app = GuardMiddleware(OfflineTaskAPI(lambda scope, receive, send: None, root),
                              HostPolicy(allow_offline_tasks=True))
        status, page, messages = _call_api(app, "GET", "/contentops/offline-task")
        assert status == 200 and "Easel 离线草稿任务".encode("utf-8") in page
        headers = dict(messages[0]["headers"])
        assert b"content-security-policy" in headers
        for path, marker in (("/contentops/offline-task.js", b"/api/contentops/draft-task"),
                             ("/contentops/offline-task.css", b".panel")):
            status, content, _ = _call_api(app, "GET", path)
            assert status == 200 and marker in content

        original = offline_api.UI_ASSETS["/contentops/offline-task.js"]
        offline_api.UI_ASSETS["/contentops/offline-task.js"] = (original[0], original[1], "0" * 64)
        try:
            status, error, _ = _call_api(app, "GET", "/contentops/offline-task.js")
            assert status == 503 and error["error"] == "OFFLINE_UI_UNVERIFIED"
        finally:
            offline_api.UI_ASSETS["/contentops/offline-task.js"] = original


def test_guarded_status_route_refuses_cross_account_and_bad_query():
    tmp, root, _ = _project_root()
    with tmp:
        app = GuardMiddleware(OfflineTaskAPI(lambda scope, receive, send: None, root),
                              HostPolicy(allow_offline_tasks=True))
        request = {"account": "x-superplay-1024", "project": "offline-test",
                   "brief": "账号绑定", "idempotency_key": "binding"}
        _, submitted, _ = _call_api(app, "POST", SUBMIT_PATH,
                                    body=json.dumps(request).encode("utf-8"))
        task_path = f"/api/contentops/draft-task/{submitted['task_id']}"
        # A read that names a different account is refused against the project
        # binding before any receipt is opened, which is earlier (403, mismatch)
        # than the receipt check this used to expect (409, TASK_RECEIPT_INVALID).
        status, error, _ = _call_api(
            app, "GET", task_path,
            query=b"account=x-superplay-future-intelligence&project=offline-test")
        assert status == 403 and error["error"] == "PROJECT_ACCOUNT_MISMATCH", (status, error)
        status, error, _ = _call_api(app, "GET", task_path, query=b"account=x-superplay-1024")
        assert status == 400 and error["error"] == "REQUEST_SCHEMA_INVALID", (status, error)


def test_guarded_api_enforces_body_size_and_never_forwards_chat():
    tmp, root, _ = _project_root()
    with tmp:
        called = []
        async def upstream(scope, receive, send):
            called.append(scope["path"])
        app = GuardMiddleware(OfflineTaskAPI(upstream, root),
                              HostPolicy(allow_offline_tasks=True))
        status, error, _ = _call_api(app, "POST", SUBMIT_PATH, body=b"x" * 32_769)
        assert status == 413 and error["error"] == "REQUEST_TOO_LARGE"
        duplicate = (b'{"account":"x-superplay-1024","project":"offline-test",'
                     b'"brief":"x","idempotency_key":"a","account":"other"}')
        status, error, _ = _call_api(app, "POST", SUBMIT_PATH, body=duplicate)
        assert status == 400 and error["error"] == "REQUEST_INVALID", (status, error)
        status, error, _ = _call_api(app, "POST", "/api/chat", body=b"{}")
        assert status == 403 and error["error"] == "HOST_ROUTE_DENIED"
        status, error, _ = _call_api(app, "POST", SUBMIT_PATH, body=b"{}",
                                     origin="https://evil.example")
        assert status == 403 and error["error"] == "HOST_ORIGIN_INVALID"
        assert called == []


def main() -> int:
    tests = [value for name, value in globals().items()
             if name.startswith("test_") and callable(value)]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"ok   {test.__name__}")
        except Exception as exc:  # noqa: BLE001 - show all contract failures
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
    print(f"{len(tests) - failed}/{len(tests)} ok")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
