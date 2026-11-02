"""A coding agent drives the pipeline through a fixed, allowlisted plan.

These tests pin the driver's boundary: it may read state and run production
steps, it may not approve, publish, install or touch credentials, and every
execution leaves a receipt.

Run: python tests/test_agent_driver.py
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


def test_receipt_output_is_scrubbed_of_host_paths():
    text = f"wrote {ROOT}/projects/x and {Path(ROOT).as_posix()}/y"
    scrubbed = driver._scrub(text, ROOT)
    assert str(ROOT) not in scrubbed
    assert "<repo>" in scrubbed


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
