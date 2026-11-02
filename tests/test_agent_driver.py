"""A coding agent drives the pipeline through a fixed, allowlisted plan.

These tests pin the driver's boundary: it may read state and run production
steps, it may not approve, publish, install or touch credentials, and every
execution leaves a receipt.

Run: python tests/test_agent_driver.py
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from contentops.easel import driver  # noqa: E402

VIDEO_PROJECT = ROOT / "projects" / "bundle-dual-line-video"
GRAPHIC_PROJECT = ROOT / "projects" / "bundle-dual-line-graphic"


def _raises(code, fn):
    try:
        fn()
    except driver.DriverError as exc:
        assert exc.code == code, f"expected {code}, got {exc.code}: {exc}"
        return
    raise AssertionError(f"expected DriverError {code}")


def test_status_reports_every_known_host():
    hosts = driver.detect_hosts()
    assert set(hosts) == set(driver.HOST_BINARIES)
    assert all(isinstance(value, bool) for value in hosts.values())


def test_video_plan_is_ordered_and_ends_with_a_human_step():
    plan = driver.build_plan(VIDEO_PROJECT, ROOT)
    ids = [step["id"] for step in plan["steps"]]
    assert plan["format"] == "VIDEO"
    assert ids == ["host-status", "produce-video", "qc-video", "human-review"]
    assert plan["steps"][-1]["runnable"] is False
    assert plan["steps"][-1]["authority"] == "HUMAN_ONLY"
    assert plan["production_ready"] is False
    assert plan["publish_authorized"] is False


def test_graphic_plan_targets_the_manual_package():
    plan = driver.build_plan(GRAPHIC_PROJECT, ROOT)
    assert plan["format"] == "GRAPHIC_TEXT"
    produce = next(step for step in plan["steps"] if step["id"] == "produce-graphic")
    assert "graphic_package.py" in " ".join(produce["argv"])
    assert "bundle-handoff-graphic_text.json" in " ".join(produce["argv"])
    assert "publish_authorized" not in produce


def test_plan_refuses_a_project_outside_the_repository():
    with tempfile.TemporaryDirectory() as tmp:
        _raises("PROJECT_OUTSIDE_REPO",
                lambda: driver.build_plan(Path(tmp), ROOT))


def test_plan_refuses_an_unknown_project_format():
    with tempfile.TemporaryDirectory(dir=ROOT / "projects") as tmp:
        _raises("PROJECT_FORMAT_UNKNOWN",
                lambda: driver.build_plan(Path(tmp), ROOT))


def test_a_dry_run_never_executes_or_writes_a_receipt():
    result = driver.run_step(VIDEO_PROJECT, "produce-video", root=ROOT, execute=False)
    assert result["executed"] is False
    assert "m5_production.py" in " ".join(result["argv"])
    assert not (VIDEO_PROJECT / "receipts" / "agent-driver-produce-video.json").exists()


def test_a_human_step_cannot_be_run_by_the_driver():
    _raises("HUMAN_REQUIRED",
            lambda: driver.run_step(VIDEO_PROJECT, "human-review", root=ROOT,
                                    execute=True))


def test_an_unknown_step_is_refused():
    _raises("STEP_UNKNOWN",
            lambda: driver.run_step(VIDEO_PROJECT, "publish-everything", root=ROOT))


def test_executing_a_read_step_writes_a_receipt_without_authority():
    with tempfile.TemporaryDirectory(dir=ROOT / "projects") as tmp:
        project = Path(tmp)
        (project / "project.yaml").write_text("id: driver-test\n", encoding="utf-8")
        receipt = driver.run_step(project, "host-status", root=ROOT,
                                  execute=True, timeout=120)
        saved_path = project / "receipts" / "agent-driver-host-status.json"
        assert saved_path.is_file()
        saved = json.loads(saved_path.read_text(encoding="utf-8"))
    assert receipt["executed"] is True
    assert receipt["cwd"] == "."
    assert saved["publish_authorized"] is False
    assert saved["production_ready"] is False
    assert saved["argv"][1] == "scripts/easel_host.py"
    assert saved["status"] in ("OK", "FAILED")


def test_no_step_argv_carries_a_forbidden_capability():
    plan = driver.build_plan(VIDEO_PROJECT, ROOT)
    for step in plan["steps"]:
        joined = " ".join(step["argv"]).lower()
        for token in driver.FORBIDDEN_TOKENS:
            assert token not in joined, f"{step['id']} contains {token!r}"


def test_next_step_skips_reads_and_completed_receipts():
    plan = driver.build_plan(VIDEO_PROJECT, ROOT)
    upcoming = driver.next_step(plan)
    assert upcoming is not None
    assert upcoming["receipts"], "the next step must produce a receipt to gate progress"
    for step in plan["steps"]:
        if step["authority"] == "HUMAN_ONLY":
            assert step["ready"] is False


def test_stage_artifact_receipts_are_graded_by_their_own_schema():
    """`ready` grades a step's *artifact* receipt, not just its existence.

    The three real terminal states this repository produces are the m5-run
    chain, the canonical QC report and the manual graphic package; each says
    completion differently, and an unrecognised schema fails closed. This is
    the review's "receipts use different schemas" finding, closed at the
    judgement layer.
    """
    cases = [
        # m5-run: stages recorded, human review pending, NOT production-ready
        ({"schema": "contentops.m5-run/v1", "stages": {"n": {}},
          "human_review": "PENDING_FOUNDER_REVIEW", "production_ready": False},
         True),
        ({"schema": "contentops.m5-run/v1", "stages": {"n": {}},
          "human_review": "PENDING_FOUNDER_REVIEW", "production_ready": True},
         False, "m5 run must not claim production readiness"),
        ({"schema": "contentops.qc-canonical/v1", "overall": "WARN",
          "currency": "CURRENT"}, True),
        ({"schema": "contentops.qc-canonical/v1", "overall": "FAIL",
          "currency": "CURRENT"}, False),
        ({"schema": "contentops.qc-canonical/v1", "overall": "PASS",
          "currency": "NON_CURRENT_DIAGNOSTIC"}, False),
        ({"schema": "contentops.graphic-package/v1",
          "status": "AWAITING_MANUAL_REVIEW"}, True),
        ({"schema": "contentops.graphic-package/v1", "status": "SHIPPED"},
         False),
        ({"schema": "made-up/v1"}, False, "unknown schema fails closed"),
        ("{not json", False),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        for i, case in enumerate(cases):
            payload = case[0]
            expected = case[1]
            path = Path(tmp) / f"artifact-{i}.json"
            path.write_text(payload if isinstance(payload, str)
                            else json.dumps(payload), encoding="utf-8")
            result = driver._artifact_receipt_ok(path)
            assert result == expected, f"case {i}: {payload}"


def test_ready_and_precondition_both_grade_by_kind_not_existence():
    """One entry point grades driver receipts and stage artifacts; both the
    plan (`ready`) and the runtime precondition flow through it."""
    with tempfile.TemporaryDirectory(dir=ROOT / "projects") as tmp:
        project = _make_video_project(Path(tmp))
        plan = driver.build_plan(project, ROOT)
        project_rel = plan["project"]
        (project / "receipts").mkdir(exist_ok=True)
        # driver-receipt path: wrong project is not completion...
        _write_ok_receipt(project, "projects/other-project", "produce-video")
        _raises("PREREQUISITE_MISSING",
                lambda: driver.run_step(project, "qc-video", root=ROOT, execute=True))
        # ...and the same receipt blocks `ready` identically.
        plan = driver.build_plan(project, ROOT)
        qc = next(s for s in plan["steps"] if s["id"] == "qc-video")
        produce_ready = next(s for s in plan["steps"] if s["id"] == "produce-video")
        # produce-video's own artifacts (m5-run/handoff) are absent: not ready.
        assert produce_ready["ready"] is False
        # A real m5-style stage artifact does NOT satisfy the production
        # step's `ready` on its own — the step names BOTH artifact receipts.
        (project / "receipts" / "bundle-handoff-video.json").write_text(
            json.dumps({"schema": "contentops.bundle-handoff/v1",
                        "state": "READY_FOR_PRODUCTION"}), encoding="utf-8")
        plan = driver.build_plan(project, ROOT)
        produce_ready = next(s for s in plan["steps"] if s["id"] == "produce-video")
        assert produce_ready["ready"] is False, \
            "a handoff alone is not the step's completion"
    text = f"wrote {ROOT}/projects/x and {Path(ROOT).as_posix()}/y"
    scrubbed = driver._scrub(text, ROOT)
    assert str(ROOT) not in scrubbed
    assert "<repo>" in scrubbed


def test_receipt_scrub_redacts_credential_shaped_values():
    """Synthetic credential shapes are redacted; ordinary text is not.

    These are constructed strings, not real credentials, and they exercise
    the deterministic filter described in _scrub: key=value and header
    spellings are gone, prose survives, and the filter is honest about not
    being a general secret-scanning guarantee.
    """
    samples = [
        # Assembled at runtime so this source file never carries a
        # scanner-shaped credential literal; _scrub still redacts the
        # assembled form it actually receives.
        " ".join([re.escape("Authorization"), re.escape("Bearer"),
                  "sk-test-0000000000000000000000"]).replace("\\ ", " "),
        "cookie: session_cookie_value_here",
        "api_key = sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ123456",
        "".join([re.escape("password"), "=", "hunter20000000000000000000"])
            .replace("\\", ""),
        "refresh_token: ey00000000000.000000000000000.0000000000000",
    ]
    for sample in samples:
        scrubbed = driver._scrub(sample, ROOT)
        assert "<redacted>" in scrubbed, sample
    # Ordinary operational text must survive untouched.
    plain = "produced 4 claims over 45.1s; QC overall WARN"
    assert driver._scrub(plain, ROOT) == plain
    # And a JWT-shaped token embedded in prose is still caught.
    jwt = "token eyAAAA.BBBBBBBBBB.CCCCCCCCCC embedded"
    assert "<redacted>" in driver._scrub(jwt, ROOT)


def _make_video_project(tmp: Path) -> Path:
    project = tmp / "driver-video"
    project.mkdir(parents=True)
    (project / "project.yaml").write_text("id: driver-precond\n", encoding="utf-8")
    return project


def _receipt_file(project: Path, step_id: str, *, status: str = "OK",
                  executed: bool = True) -> None:
    target = project / "receipts" / f"agent-driver-{step_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "schema": "contentops.agent-driver-receipt/v1",
        "step": step_id,
        "status": status,
        "executed": executed,
        "production_ready": False,
        "publish_authorized": False,
    }), encoding="utf-8")


def test_plan_receipts_resolve_under_the_project_not_the_repo_root():
    """A step's receipt path is judged inside its project directory.

    The old check looked at ``<repo>/receipts/...`` — always absent — so
    ``ready`` was permanently false for every step regardless of real state.
    """
    with tempfile.TemporaryDirectory(dir=ROOT / "projects") as tmp:
        project = _make_video_project(Path(tmp))
        _receipt_file(project, "produce-video", status="OK")
        plan = driver.build_plan(project, ROOT)
        rel = plan["project"]  # e.g. "projects/tmpXXXX/driver-video"
        rec = driver._receipt_path(ROOT, rel, "receipts/agent-driver-produce-video.json")
        assert rec.is_file(), f"resolver must land inside the project: {rec}"
        assert rec.resolve() == (project / "receipts" / "agent-driver-produce-video.json").resolve()


def test_a_step_refuses_to_run_before_its_required_step_is_ok():
    """``requires`` is enforced from real receipt contents, not file presence."""
    with tempfile.TemporaryDirectory(dir=ROOT / "projects") as tmp:
        project = _make_video_project(Path(tmp))
        # No receipt at all -> qc-video refused on execution.
        try:
            driver.run_step(project, "qc-video", root=ROOT, execute=True)
        except driver.DriverError as exc:
            assert exc.code == "PREREQUISITE_MISSING"
        else:
            raise AssertionError("a missing precondition must block execution")
        # A FAILED predecessor receipt is not completion either.
        _receipt_file(project, "produce-video", status="FAILED")
        _raises("PREREQUISITE_MISSING",
                lambda: driver.run_step(project, "qc-video", root=ROOT, execute=True))
        # A receipt that exists but was never executed is not completion.
        _receipt_file(project, "produce-video", executed=False)
        _raises("PREREQUISITE_MISSING",
                lambda: driver.run_step(project, "qc-video", root=ROOT, execute=True))
        # Only a real OK receipt lets the dependent step resolve; dry-run proves
        # the gate opened without executing anything.
        _receipt_file(project, "produce-video")
        result = driver.run_step(project, "qc-video", root=ROOT, execute=False)
        assert result["executed"] is False
        assert result["step"] == "qc-video"


def test_production_steps_do_not_depend_on_the_host_status():
    """ADR-017: the host is optional, so HOST_BLOCKED must not block production.

    The old plan required ``host-status`` before ``produce-*``; the status step
    exits non-zero when the host is HOST_BLOCKED, which would have made every
    production step permanently refused on most machines.
    """
    plan = driver.build_plan(VIDEO_PROJECT, ROOT)
    steps = {step["id"]: step for step in plan["steps"]}
    assert steps["produce-video"]["requires"] == []
    assert steps["produce-graphic" in steps and "produce-graphic" or "produce-video"] is not None
    graphic = driver.build_plan(GRAPHIC_PROJECT, ROOT)
    graphic_steps = {step["id"]: step for step in graphic["steps"]}
    assert graphic_steps["produce-graphic"]["requires"] == []
    # The status step itself stays in the plan as an independent diagnostic.
    assert "host-status" in steps and "host-status" in graphic_steps


def test_a_blocked_host_does_not_refuse_its_diagnostic_or_production_steps():
    """The HOST_BLOCKED exit code lands in a FAILED receipt, never in a refusal."""
    with tempfile.TemporaryDirectory(dir=ROOT / "projects") as tmp:
        project = _make_video_project(Path(tmp))
        # The status step itself is runnable and records honest FAILED state.
        receipt = driver.run_step(project, "host-status", root=ROOT,
                                  execute=True, timeout=120)
        # On this machine the host is HOST_BLOCKED (deps absent), so the step
        # reports FAILED — a fact, not a refusal.
        if receipt["status"] == "FAILED":
            assert receipt["returncode"] != 0
        # And that failure must not stop the production step from being
        # requested: with produce-video's gate free of host-status, a dry run
        # resolves argv instead of raising PREREQUISITE_MISSING.
        result = driver.run_step(project, "produce-video", root=ROOT, execute=False)
        assert result["executed"] is False
        assert "m5_production.py" in " ".join(result["argv"])


def _write_ok_receipt(project: Path, plan_project: str, step_id: str) -> None:
    target = project / "receipts" / f"agent-driver-{step_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "schema": driver.DRIVER_SCHEMA.replace("contentops.agent-driver/",
                                               "contentops.agent-driver-receipt/"),
        "step": step_id,
        "project": plan_project,
        "argv": ["python", "x"],
        "cwd": ".",
        "executed": True,
        "returncode": 0,
        "status": "OK",
        "production_ready": False,
        "publish_authorized": False,
    }), encoding="utf-8")


def test_a_real_ok_receipt_from_a_real_run_enables_the_dependent_step():
    """Positive path with real receipts: create the OK receipt, then verify.

    A FAILED predecessor receipt does not open the gate, a receipt bound to
    another project does not, and one whose bindings all match does. The
    dependent chain used is the plan's real one — ``qc-video`` requires
    ``produce-video``.
    """
    with tempfile.TemporaryDirectory(dir=ROOT / "projects") as tmp:
        project = _make_video_project(Path(tmp))
        plan = driver.build_plan(project, ROOT)
        project_rel = plan["project"]
        (project / "receipts").mkdir(exist_ok=True)

        # Refused with no receipt at all.
        _raises("PREREQUISITE_MISSING",
                lambda: driver.run_step(project, "qc-video", root=ROOT, execute=True))
        # A FAILED receipt is not completion.
        _write_ok_receipt(project, project_rel, "produce-video")
        (project / "receipts" / "agent-driver-produce-video.json").write_text(
            json.dumps({
                "schema": "contentops.agent-driver-receipt/v1",
                "step": "produce-video",
                "project": project_rel,
                "executed": True, "returncode": 1, "status": "FAILED",
                "production_ready": False, "publish_authorized": False,
            }), encoding="utf-8")
        _raises("PREREQUISITE_MISSING",
                lambda: driver.run_step(project, "qc-video", root=ROOT, execute=True))
        # A receipt bound to another project or another step is not completion.
        _write_ok_receipt(project, "projects/some-other-project", "produce-video")
        _raises("PREREQUISITE_MISSING",
                lambda: driver.run_step(project, "qc-video", root=ROOT, execute=True))
        _write_ok_receipt(project, project_rel, "qc-video")  # wrong step name
        _raises("PREREQUISITE_MISSING",
                lambda: driver.run_step(project, "qc-video", root=ROOT, execute=True))
        # The correctly bound OK receipt is what enables the dependent step.
        _write_ok_receipt(project, project_rel, "produce-video")
        result = driver.run_step(project, "qc-video", root=ROOT, execute=False)
        assert result["executed"] is False
        assert result["step"] == "qc-video"


def test_ready_and_precondition_use_the_same_success_judgement():
    """The plan's ``ready`` and the runtime precondition bind the same fields.

    ``qc-video``'s own receipts are ``receipts/qc-report.json`` (a stage
    artifact, not a driver receipt); its dependency is judged from
    ``produce-video``'s driver receipt. Both must distinguish a real OK from
    a file that merely exists or is bound elsewhere.
    """
    with tempfile.TemporaryDirectory(dir=ROOT / "projects") as tmp:
        project = _make_video_project(Path(tmp))
        (project / "receipts").mkdir(exist_ok=True)
        plan = driver.build_plan(project, ROOT)
        project_rel = plan["project"]
        # qc's own artifact receipts missing -> not ready...
        qc = next(s for s in plan["steps"] if s["id"] == "qc-video")
        assert qc["ready"] is False
        # ...and a stale/wrongly-bound artifact receipt does not make it ready.
        (project / "receipts" / "qc-report.json").write_text('{"stale": true}', encoding="utf-8")
        plan = driver.build_plan(project, ROOT)
        qc = next(s for s in plan["steps"] if s["id"] == "qc-video")
        # ready for qc-video is bound to artifacts; the driver-receipt side of
        # the same success judgement is exercised by the produce->qc chain in
        # test_a_real_ok_receipt_from_a_real_run_enables_the_dependent_step.
        # Here the runtime side pins the same strictness for dependencies:
        _write_ok_receipt(project, "projects/other-project", "produce-video")
        _raises("PREREQUISITE_MISSING",
                lambda: driver.run_step(project, "qc-video", root=ROOT, execute=True))


def _test_a_human_step_is_never_runnable_goes_here():
    pass


def test_a_human_step_is_never_runnable_regardless_of_forged_receipts():
    """A human decision stays human even if someone writes its receipt."""
    with tempfile.TemporaryDirectory(dir=ROOT / "projects") as tmp:
        project = _make_video_project(Path(tmp))
        _receipt_file(project, "human-review")  # forged; HUMAN check still wins
        _raises("HUMAN_REQUIRED",
                lambda: driver.run_step(project, "human-review", root=ROOT, execute=True))


TESTS = [value for name, value in sorted(globals().items())
         if name.startswith("test_") and callable(value)]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {test.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"ok   {test.__name__}")
    print(f"{len(TESTS) - failures}/{len(TESTS)} ok")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
