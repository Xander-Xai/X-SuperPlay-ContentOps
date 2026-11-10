"""The Huashu Motion managed-execution gate. Default deny, verified offline.

Run: python tests/test_huashu_execution_gate.py

Nothing here renders. The upstream invocation is an injected mock runner, the
runtime is a temporary directory whose Git state is answered by an injected
probe, and the approval record is a fixture written by the test into its own
temporary project. Every test asserts what the runner was called with *and*
that it was not called on any refusal path.
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

from contentops.media import huashu_motion  # noqa: E402
from contentops.skills import huashu_execution  # noqa: E402
from contentops_video_local import LocalHuashuRunner, RunnerError  # noqa: E402
from contentops.skills.authorization import (  # noqa: E402
    REASON_OPERATION_NOT_GRANTED,
    REASON_VERSION_MISMATCH,
    ExecutionGrant,
    evaluate,
)

NOW = "2026-11-06T12:00:00+00:00"


def _approval(project: Path, **overrides) -> Path:
    """Write the project's own approval record. A fixture, not a real grant."""
    payload = {
        "schema": "contentops.skill-execution-approval/v1",
        "purpose": "skill_execution",
        "approval_id": "huashu-motion-test",
        "issuer": "owner",
        "subject": "owner",
        "skill_id": "huashu-motion",
        "skill_version": "0.3.1",
        "account": "x-superplay-1024",
        "pipeline": "M5",
        "stage": "motion",
        "operations": ["render"],
        "issued_at": "2026-11-06T00:00:00+00:00",
        "expires_at": "2026-11-07T00:00:00+00:00",
        "max_units": 1,
        "max_uses": 1,
    }
    payload.update(overrides)
    path = project / "receipts" / "skill-execution-approval.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _fake_runtime(root: Path) -> Path:
    """A directory that satisfies the verifier. No upstream bytes, no render."""
    runtime = root / "runtime"
    (runtime / "skills" / "huashu-motion" / "bin").mkdir(parents=True)
    (runtime / "skills" / "huashu-motion" / "bin" / "om").write_text(
        "#!/bin/sh\n", encoding="utf-8")
    (runtime / "cli").mkdir(parents=True)
    (runtime / "cli" / "om.js").write_text("// pinned dispatcher\n", encoding="utf-8")
    (runtime / "LICENSE").write_text("MIT\n", encoding="utf-8")
    return runtime


def _git_probe_ok(root: Path, *args: str):
    values = {
        ("rev-parse", "HEAD"): huashu_motion.COMMIT,
        ("remote", "get-url", "origin"): huashu_motion.REPOSITORY,
        ("status", "--porcelain", "--untracked-files=all"): "",
    }
    return 0, values[tuple(args)]


def test_local_runner_builds_a_fixed_render_argv_and_keeps_output_in_project():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        projects_root = root / "projects"
        project = projects_root / "account-sample"
        project.mkdir(parents=True)
        runtime = root / "runtime"
        runner = LocalHuashuRunner(
            project_dir=project,
            projects_root=projects_root,
            runtime_root=runtime,
            node_executable=root / "node.exe",
        )
        argv = runner.build_argv("render", "request-123", {})
        assert argv[:3] == [str(root / "node.exe"), str(runtime / "cli" / "om.js"), "render"]
        assert "--format" in argv and argv[argv.index("--format") + 1] == "mp4"
        assert "--fps" in argv and argv[argv.index("--fps") + 1] == "30"
        assert "--workers" in argv and argv[argv.index("--workers") + 1] == "2"
        assert "--silent" in argv
        output = Path(argv[argv.index("--out") + 1])
        assert output == project / "out" / "contentops-request-123.mp4"
        assert output.resolve().is_relative_to(project.resolve())


def test_local_runner_qa_uses_only_the_upstream_qa_contract():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        projects_root = root / "projects"
        project = projects_root / "sample"
        project.mkdir(parents=True)
        runner = LocalHuashuRunner(
            project_dir=project, projects_root=projects_root,
            runtime_root=root / "runtime", node_executable=root / "node.exe",
        )
        argv = runner.build_argv("qa", "request-123", {})
        assert argv == [str(root / "node.exe"), str(root / "runtime" / "cli" / "om.js"),
                        "qa", str(project)]


def test_timeout_is_reported_with_captured_output_and_receipt():
    import subprocess
    import contentops_video_local as local_runner

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        projects_root = root / "projects"
        project = projects_root / "sample"
        project.mkdir(parents=True)
        runner = LocalHuashuRunner(
            project_dir=project, projects_root=projects_root,
            runtime_root=root / "runtime", node_executable=root / "node.exe",
        )
        runner.preflight = lambda *args: None
        runner.build_argv = lambda *args: ["node", "om.js", "render"]
        original_hidden_run = local_runner.hidden_run
        def timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired(["node", "om.js"], 1,
                                             output="partial out", stderr="partial err")
        local_runner.hidden_run = timeout
        try:
            result = runner("render", type("Request", (), {"request_id": "request-123"})())
        finally:
            local_runner.hidden_run = original_hidden_run

    assert result["ok"] is False
    assert result["receipt"]["process_status"] == "TIMEOUT"
    assert result["receipt"]["stdout_tail"] == "partial out"
    assert result["receipt"]["stderr_tail"] == "partial err"


def test_full_decode_uses_ffmpeg_error_exit_and_reports_nonzero():
    import contentops_video_local as local_runner

    original_hidden_run = local_runner.hidden_run
    captured = []
    def fake_run(argv, **kwargs):
        captured.append((argv, kwargs))
        return type("Completed", (), {"returncode": 1, "stderr": "decode error"})()
    local_runner.hidden_run = fake_run
    try:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "project"
            project.mkdir()
            video = project / "out.mp4"
            video.write_bytes(b"sample")
            result = local_runner._decode_video(video, project.resolve())
    finally:
        local_runner.hidden_run = original_hidden_run

    argv, kwargs = captured[0]
    assert argv[0] == str(local_runner.FFMPEG_EXE)
    assert "-xerror" in argv
    assert argv[argv.index("-f") + 1] == "null"
    assert argv[-1] == __import__("os").devnull
    assert kwargs["timeout"] == 180
    assert result["state"] == "FAIL" and result["returncode"] == 1
    assert result["stderr_tail"] == "decode error"


def test_successful_render_validates_the_file_it_just_created():
    import contentops_video_local as local_runner

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        projects_root = root / "projects"
        project = projects_root / "sample"
        project.mkdir(parents=True)
        runner = LocalHuashuRunner(
            project_dir=project, projects_root=projects_root,
            runtime_root=root / "runtime", node_executable=root / "node.exe",
        )
        runner.preflight = lambda *args: None
        original_hidden_run = local_runner.hidden_run
        original_probe = local_runner._probe_video
        original_decode = local_runner._decode_video
        def run(argv, **kwargs):
            output = Path(argv[argv.index("--out") + 1])
            output.write_bytes(b"rendered")
            return type("Completed", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()
        local_runner.hidden_run = run
        local_runner._probe_video = lambda *args: {"has_audio": False}
        local_runner._decode_video = lambda *args: {"state": "PASS"}
        from contentops.media import motion_sample
        original_clip_check = motion_sample.check_motion_clip
        motion_sample.check_motion_clip = lambda *args, **kwargs: {
            "state": "TECHNICALLY_CHECKED", "sha256": "a" * 64
        }
        try:
            result = runner("render", type("Request", (), {"request_id": "request-123"})())
        finally:
            local_runner.hidden_run = original_hidden_run
            local_runner._probe_video = original_probe
            local_runner._decode_video = original_decode
            motion_sample.check_motion_clip = original_clip_check

    assert result["ok"] is True, result
    assert result["receipt"]["output"] == "out/contentops-request-123.mp4"
    assert result["receipt"]["output_sha256"]


def test_runner_cli_exposes_only_the_nine_fixed_operations():
    from contentops_video_local import ALLOWED_TASKS, build_parser

    assert ALLOWED_TASKS == {
        "runtime-status", "motion-check", "motion-still", "motion-render",
        "motion-qa", "motion-validate", "manifest-register", "easel-compose",
        "video-qc",
    }
    args = build_parser().parse_args(["runtime-status"])
    assert args.task == "runtime-status"
    try:
        build_parser().parse_args(["arbitrary-command", "--", "echo", "unsafe"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("the CLI must reject arbitrary command forwarding")


def test_local_runner_rejects_unknown_operations_and_unexpected_options():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        projects_root = root / "projects"
        project = projects_root / "sample"
        project.mkdir(parents=True)
        runner = LocalHuashuRunner(
            project_dir=project, projects_root=projects_root,
            runtime_root=root / "runtime", node_executable=root / "node.exe",
        )
        for operation, options in (("install", {}), ("render", {"shell": True}),
                                   ("still", {"out": "../../evil.png"})):
            try:
                runner.build_argv(operation, "request-123", options)
            except RunnerError:
                continue
            raise AssertionError(f"unsafe operation or option accepted: {operation}, {options}")


def test_local_runner_rejects_project_paths_outside_the_projects_root():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        projects_root = root / "projects"
        projects_root.mkdir()
        outside = root / "outside"
        outside.mkdir()
        try:
            LocalHuashuRunner(
                project_dir=outside, projects_root=projects_root,
                runtime_root=root / "runtime", node_executable=root / "node.exe",
            )
        except RunnerError:
            return
        raise AssertionError("a project outside the projects root was accepted")


def _request(operation: str = "render"):
    return huashu_execution.build_request(
        request_id=f"req-{operation}",
        operation=operation,
        account="x-superplay-1024",
        pipeline="M5",
        stage="motion",
        subject="owner",
    )


class _Recorder:
    def __init__(self) -> None:
        self.calls = []

    def __call__(self, operation, request):
        self.calls.append((operation, request))
        return {"ok": True, "health": True, "receipt": {"rendered": True}}


def test_without_an_approval_record_nothing_runs():
    recorder = _Recorder()
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "project"
        (project / "receipts").mkdir(parents=True)
        runtime = _fake_runtime(Path(temp))
        result = huashu_execution.execute_huashu(
            _request(), project_dir=project, owner_identities=["owner"],
            runtime_root=runtime, runner=recorder, git_probe=_git_probe_ok,
            now=NOW,
        )
    assert result.decision.state == "BLOCKED", result.decision
    assert result.decision.reason == "NO_TRUSTED_GRANT", result.decision
    assert result.execution["state"] == "NOT_EXECUTED", result.execution
    assert recorder.calls == []


def test_an_unusable_runtime_costs_no_approval_use():
    recorder = _Recorder()
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "project"
        (project / "receipts").mkdir(parents=True)
        _approval(project)
        missing = Path(temp) / "not-installed"
        result = huashu_execution.execute_huashu(
            _request(), project_dir=project, owner_identities=["owner"],
            runtime_root=missing, runner=recorder, git_probe=_git_probe_ok,
            now=NOW,
        )
        consumed = sorted((project / "receipts" / "grants").glob("*/*"))
    assert result.decision.state == "BLOCKED", result.decision
    assert result.decision.reason == huashu_execution.REASON_RUNTIME_NOT_TRUSTED
    assert result.execution["state"] == "NOT_EXECUTED", result.execution
    assert recorder.calls == []
    assert consumed == [], "an unusable runtime must not spend an approved use"


def test_an_approval_naming_another_skill_is_refused():
    recorder = _Recorder()
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "project"
        (project / "receipts").mkdir(parents=True)
        _approval(project, skill_id="media-use")
        runtime = _fake_runtime(Path(temp))
        result = huashu_execution.execute_huashu(
            _request(), project_dir=project, owner_identities=["owner"],
            runtime_root=runtime, runner=recorder, git_probe=_git_probe_ok,
            now=NOW,
        )
    assert result.decision.state == "BLOCKED", result.decision
    assert recorder.calls == []


def test_an_approval_that_does_not_name_the_operation_is_refused():
    recorder = _Recorder()
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "project"
        (project / "receipts").mkdir(parents=True)
        _approval(project, operations=["check"])
        runtime = _fake_runtime(Path(temp))
        result = huashu_execution.execute_huashu(
            _request("render"), project_dir=project, owner_identities=["owner"],
            runtime_root=runtime, runner=recorder, git_probe=_git_probe_ok,
            now=NOW,
        )
    assert result.decision.state == "BLOCKED", result.decision
    assert recorder.calls == []


def test_an_approval_from_an_unknown_issuer_is_refused():
    recorder = _Recorder()
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "project"
        (project / "receipts").mkdir(parents=True)
        _approval(project, issuer="someone-else")
        runtime = _fake_runtime(Path(temp))
        result = huashu_execution.execute_huashu(
            _request(), project_dir=project, owner_identities=["owner"],
            runtime_root=runtime, runner=recorder, git_probe=_git_probe_ok,
            now=NOW,
        )
    assert result.decision.state == "BLOCKED", result.decision
    assert recorder.calls == []


def test_a_matching_approval_and_a_trusted_runtime_call_the_runner_once():
    recorder = _Recorder()
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "project"
        (project / "receipts").mkdir(parents=True)
        _approval(project)
        runtime = _fake_runtime(Path(temp))
        request = _request()
        result = huashu_execution.execute_huashu(
            request, project_dir=project, owner_identities=["owner"],
            runtime_root=runtime, runner=recorder, git_probe=_git_probe_ok,
            now=NOW,
        )
        receipt_path = Path(result.receipt_path) if result.receipt_path else None
        assert receipt_path is not None and receipt_path.is_file()
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert result.decision.state == "AUTHORIZED", result.decision
    assert result.execution["state"] == "EXECUTED", result.execution
    assert len(recorder.calls) == 1, recorder.calls
    operation, seen_request = recorder.calls[0]
    assert operation == "render"
    assert seen_request.skill_id == "huashu-motion"
    assert seen_request.skill_version == "0.3.1"
    assert seen_request.operations == ("render",)
    assert receipt["skill"] == {"id": "huashu-motion", "version": "0.3.1"}
    assert receipt["execution"]["state"] == "EXECUTED"
    assert receipt["grant_id"] == "huashu-motion-test"
    assert receipt["consumed_use"] == 1
    assert receipt["request_id"] == request.request_id


def test_local_runner_preflight_failure_does_not_consume_an_approval():
    class MissingRunner:
        def preflight(self, operation, request):
            raise RunnerError("pinned Node executable is missing")

        def __call__(self, operation, request):
            raise AssertionError("runner must not be called")

    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "project"
        (project / "receipts").mkdir(parents=True)
        _approval(project)
        result = huashu_execution.execute_huashu(
            _request(), project_dir=project, owner_identities=["owner"],
            runtime_root=_fake_runtime(Path(temp)), runner=MissingRunner(),
            git_probe=_git_probe_ok, now=NOW,
        )
        consumed = sorted((project / "receipts" / "grants").glob("*/*"))
    assert result.decision.state == "BLOCKED", result.decision
    assert result.execution["state"] == "NOT_EXECUTED", result.execution
    assert consumed == [], "preflight failure must not spend an approved use"


def test_the_executor_refuses_when_no_upstream_invocation_is_configured():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "project"
        (project / "receipts").mkdir(parents=True)
        _approval(project)
        runtime = _fake_runtime(Path(temp))
        result = huashu_execution.execute_huashu(
            _request(), project_dir=project, owner_identities=["owner"],
            runtime_root=runtime, runner=None, git_probe=_git_probe_ok,
            now=NOW,
        )
    assert result.decision.state == "BLOCKED", result.decision
    assert result.decision.reason == huashu_execution.REASON_NO_RUNNER
    assert result.execution["state"] == "NOT_EXECUTED"
    assert sorted((project / "receipts" / "grants").glob("*/*")) == []


def test_the_module_never_builds_an_upstream_command_line():
    source = Path(huashu_execution.__file__).read_text(encoding="utf-8")
    for forbidden in ("subprocess", "os.system", "shell=True", "hidden_run"):
        assert forbidden not in source, forbidden


def test_the_resolution_record_never_claims_execution_authority():
    runtime = {"status": "TRUSTED_RUNTIME", "runtime_root": "x",
               "version": "0.3.1", "commit": huashu_motion.COMMIT}
    verdict = huashu_execution.build_verdict(runtime)
    assert verdict["verdict"] == "RESOLVABLE"
    assert verdict["execution_authorized"] is False
    # The authorization module refuses a verdict that claims authority.
    decision = evaluate(
        huashu_execution.build_request(
            request_id="r", operation="render", account="a", pipeline="M5",
            stage="motion", subject="owner"),
        verdict={**verdict, "execution_authorized": True},
        registry_entry=huashu_execution.build_registry_entry(),
        grant=None,
        now=NOW,
    )
    assert decision.state == "BLOCKED"
    assert decision.reason == "UNTRUSTED_VERDICT"


def test_the_registry_entry_is_the_committed_pin():
    entry = huashu_execution.build_registry_entry()
    assert entry["id"] == "huashu-motion"
    assert entry["source"]["version"] == "0.3.1"
    assert entry["source"]["source_commit"] == huashu_motion.COMMIT
    request = huashu_execution.build_request(
        request_id="r", operation="render", account="a", pipeline="M5",
        stage="motion", subject="owner")
    decision = evaluate(request, verdict=huashu_execution.build_verdict(
        {"status": "TRUSTED_RUNTIME"}), registry_entry=entry, grant=None, now=NOW)
    assert decision.reason == "NO_GRANT", decision.reason


def test_a_version_mismatch_between_request_and_pin_is_refused():
    entry = huashu_execution.build_registry_entry()
    request = huashu_execution.build_request(
        request_id="r", operation="render", account="a", pipeline="M5",
        stage="motion", subject="owner", version="0.0.1")
    decision = evaluate(request, verdict=huashu_execution.build_verdict(
        {"status": "TRUSTED_RUNTIME"}), registry_entry=entry, grant=None, now=NOW)
    assert decision.reason == REASON_VERSION_MISMATCH, decision.reason


def test_an_operation_the_approval_does_not_name_is_refused_by_the_decision():
    entry = huashu_execution.build_registry_entry()
    verdict = huashu_execution.build_verdict({"status": "TRUSTED_RUNTIME"})
    grant = ExecutionGrant(
        grant_id="g", issuer="owner", subject="owner", skill_id="huashu-motion",
        skill_version="0.3.1", account="x-superplay-1024", pipeline="M5",
        stage="motion", operations=("check",), issued_at="2026-11-06T00:00:00+00:00",
        expires_at="2026-11-07T00:00:00+00:00", provenance="sha256:" + "0" * 64,
    )
    decision = evaluate(_request("render"), verdict=verdict, registry_entry=entry,
                        grant=grant, now=NOW)
    assert decision.reason == REASON_OPERATION_NOT_GRANTED, decision.reason


def test_the_lock_records_the_upstream_cli_syntax_and_the_real_paths():
    lock = json.loads((ROOT / "runtime" / "huashu-motion.lock.json")
                      .read_text(encoding="utf-8"))
    assert lock["entrypoint"] == "skills/huashu-motion/bin/om"
    assert lock["dispatcher"] == "cli/om.js"
    assert lock["execution_authorized"] is False
    contracts = lock["operation_contracts"]
    assert "om check" in contracts["check"]
    assert "--samples" in contracts["check"]
    assert "--out" in contracts["still"]
    assert "--format" in contracts["render"]
    assert "out/" in contracts["render"]
    assert "om qa" in contracts["qa"]
    # The licence exception is the upstream's own wording, not a paraphrase.
    assert any("toon.js" in item for item in lock["license"]["excluded_without_separate_permission"])


def test_the_operation_table_matches_the_upstream_commands():
    for operation in ("check", "still", "render", "qa"):
        plan = huashu_motion.describe_operation(operation)
        assert plan["command"].startswith(f"om {operation} ")
        assert plan["state"] == "BLOCKED"
        assert plan["execution_status"] == "NOT_EXECUTED"
        assert plan["execution_authorized"] is False


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
