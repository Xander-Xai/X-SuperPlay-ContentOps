"""The account decides the pipeline, and the router has to say so out loud.

Two accounts, two production methods:

- 1024 is ``EVIDENCE_LED``: capture contracts, captures, an evidence cut.
- Future Intelligence is ``EXPLANATORY`` and forbids manual recording: audio-first
  planning, then the same packager, and no capture step at all.

Before this router existed the mapping lived in the runbook and in whoever
remembered it. These tests pin the two things that were implicit: the *mode* is
what chooses the chain, and the probe commands must be real scripts.

The pure function is tested directly so a mode the repository has not implemented
can be refused without inventing a fake account file under ``config/accounts``.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import account_route as ar  # noqa: E402
from process_utils import hidden_run  # noqa: E402

TESTS: List = []

EVIDENCE_ACCOUNT = "x-superplay-1024"
EXPLANATORY_ACCOUNT = "x-superplay-future-intelligence"
X_ACCOUNT = "x-superplay-english"


def test(fn):
    TESTS.append(fn)
    return fn


def _route(slug: str):
    return ar.route_for(ar.load_dna(slug))


@test
def test_the_two_accounts_do_not_get_the_same_pipeline():
    """The whole point: asking for the wrong account must not look the same."""
    evidence = _route(EVIDENCE_ACCOUNT)
    explanatory = _route(EXPLANATORY_ACCOUNT)
    assert evidence["evidence_mode"] == "EVIDENCE_LED"
    assert explanatory["evidence_mode"] == "EXPLANATORY"
    assert evidence["manual_recording"] == "ALLOWED_CROPPED"
    assert explanatory["manual_recording"] == "FORBIDDEN"
    assert (evidence["duration_s"], explanatory["duration_s"]) == ([45, 60], [90, 120])
    assert [step["step"] for step in evidence["pipeline"]] != [
        step["step"] for step in explanatory["pipeline"]]
    print("[ok] 1. the two accounts resolve to different pipelines")


@test
def test_the_evidence_account_plans_captures_before_it_builds():
    steps = [step["step"] for step in _route(EVIDENCE_ACCOUNT)["pipeline"]]
    assert steps == ["cut-plan", "capture-plan", "capture", "build", "qc"], steps
    assert "audio_first_plan.py" in _route(EVIDENCE_ACCOUNT)["pipeline"][0]["command"]
    print("[ok] 2. the evidence account plans its cut, then its captures")


@test
def test_the_explanatory_account_never_gets_a_capture_step():
    """A recording ban that leaves a capture command in the pipeline is decoration."""
    route = _route(EXPLANATORY_ACCOUNT)
    steps = [step["step"] for step in route["pipeline"]]
    assert steps == ["plan", "build", "qc"], steps
    commands = " ".join(step["command"] for step in route["pipeline"])
    assert "capture" not in commands, commands
    assert steps[0] == "plan", steps
    print("[ok] 3. the explanatory account has no capture step")


@test
def test_both_accounts_converge_on_the_same_packager_and_qc():
    """Different producers, one receipt substrate: that is why the gates are shared."""
    for slug in (EVIDENCE_ACCOUNT, EXPLANATORY_ACCOUNT):
        commands = " ".join(step["command"] for step in _route(slug)["pipeline"])
        assert "build_evidence_package.py" in commands, (slug, commands)
        assert "qc_video.py" in commands, (slug, commands)
    print("[ok] 4. both pipelines end at the shared packager and QC")


@test
def test_a_mode_with_no_declared_pipeline_is_refused():
    fake = {"slug": "x-test-sales", "evidence": {"mode": "SALES_PITCH"},
            "narrative": {}, "visual": {}, "skill_route": []}
    try:
        ar.route_for(fake)
    except ar.RouteBlocked as blocked:
        assert blocked.code == "EVIDENCE_MODE_UNMAPPED", blocked.code
        assert "EVIDENCE_LED" in blocked.detail, blocked.detail
    else:
        raise AssertionError("an unimplemented mode produced a pipeline")

    no_mode = {"slug": "x-test-none", "evidence": {}, "narrative": {}, "visual": {}}
    try:
        ar.route_for(no_mode)
    except ar.RouteBlocked as blocked:
        assert blocked.code == "EVIDENCE_MODE_MISSING", blocked.code
    else:
        raise AssertionError("a DNA without an evidence mode produced a pipeline")
    print("[ok] 5. an undeclared or unimplemented mode is refused, not guessed")


@test
def test_every_route_command_names_a_script_that_exists():
    """A route that points at a deleted script is a runbook, not a router."""
    for slug in (EVIDENCE_ACCOUNT, EXPLANATORY_ACCOUNT, X_ACCOUNT):
        route = _route(slug)
        for group in ("pipeline", "alternatives"):
            for step in route[group]:
                words = step["command"].split()
                assert words[0] == "python", step["command"]
                script = ROOT / words[1]
                assert script.is_file(), f"{slug}: {step['command']}"
    print("[ok] 6. every route command points at a real script")


@test
def test_a_project_without_an_account_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        (project / "project.yaml").write_text("slug: x\n", encoding="utf-8")
        try:
            ar.resolve(project)
        except ar.RouteBlocked as blocked:
            assert blocked.code == "ACCOUNT_SLUG_MISSING", blocked.code
        else:
            raise AssertionError("a project with no account got a pipeline")
    print("[ok] 7. a project that names no account is refused")


@test
def test_a_project_naming_an_unknown_account_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        (project / "project.yaml").write_text(
            "slug: x\naccount_slug: x-superplay-nosuch\n", encoding="utf-8")
        try:
            ar.resolve(project)
        except ar.RouteBlocked as blocked:
            assert blocked.code == "ACCOUNT_DNA_MISSING", blocked.code
            assert "x-superplay-nosuch" in blocked.detail, blocked.detail
        else:
            raise AssertionError("an unknown account produced a pipeline")
    print("[ok] 8. a project naming an unknown account is refused")


@test
def test_missing_producer_inputs_are_named_before_anything_runs():
    """A correct route is not a ready project, and the router must not imply it is."""
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        (project / "project.yaml").write_text(
            f"slug: x\naccount_slug: {EVIDENCE_ACCOUNT}\n", encoding="utf-8")
        route = ar.resolve(project)
        warnings = " ".join(route["warnings"])
        assert "script/lines.json" in warnings, warnings
        assert "script/storyboard.json" in warnings, warnings

        (project / "script").mkdir()
        (project / "script" / "lines.json").write_text("{}", encoding="utf-8")
        (project / "script" / "storyboard.json").write_text("{}", encoding="utf-8")
        route = ar.resolve(project)
        warnings = " ".join(route["warnings"])
        assert "script/lines.json" not in warnings, warnings
        assert "script/storyboard.json" not in warnings, warnings
    print("[ok] 9b. inputs the producers need but the router cannot create are named")


@test
def test_the_cli_resolves_a_real_project_and_echoes_the_creative_owners():
    result = hidden_run(
        [sys.executable, str(ROOT / "scripts" / "account_route.py"),
         str(ROOT / "projects" / "easel-fi-audio-first"), "--json"],
        cwd=str(ROOT), timeout=120)
    assert result.returncode == 0, (result.stdout or "") + (result.stderr or "")
    route = json.loads(result.stdout)
    assert route["schema"] == ar.SCHEMA
    assert route["account_slug"] == EXPLANATORY_ACCOUNT
    assert route["pipeline"][0]["command"].endswith("projects/easel-fi-audio-first")
    assert [entry["step"] for entry in route["skills"]][0] == "script"
    assert all(entry["skill"] for entry in route["skills"])
    assert any("90-120" in warning for warning in route["warnings"]), route["warnings"]
    print("[ok] 9. the CLI resolves a real project and echoes its skill owners")


@test
def test_a_declared_pipeline_beats_an_evidence_mode():
    """A text account has no film, so it names its chain instead of a mode."""
    route = _route(X_ACCOUNT)
    assert route["pipeline_source"] == "pipeline", route["pipeline_source"]
    assert route["pipeline_name"] == "X_EDITORIAL"
    assert route["evidence_mode"] is None, route["evidence_mode"]

    decoy = {"slug": "x-test-decoy", "pipeline": "X_EDITORIAL",
             "evidence": {"mode": "EVIDENCE_LED"}, "visual": {}, "narrative": {}}
    assert ar.route_for(decoy)["pipeline_name"] == "X_EDITORIAL"
    print("[ok] 10. a declared pipeline wins over an evidence mode")


@test
def test_the_x_chain_ends_at_measurement_and_has_no_render_step():
    steps = [step["step"] for step in _route(X_ACCOUNT)["pipeline"]]
    assert steps == ["research", "editorial", "visual", "package", "publish", "measure"], steps
    for forbidden in ("build", "qc", "capture", "cut-plan"):
        assert forbidden not in steps, (forbidden, steps)
    commands = " ".join(step["command"] for step in _route(X_ACCOUNT)["pipeline"])
    assert "vendor/x-growth-os/scripts/x_growth_report.py" in commands, commands
    assert "--root" in commands, commands
    print("[ok] 11. the X chain measures with the vendored script and renders no film")


@test
def test_every_x_step_says_what_it_cannot_do():
    """Each step names its producer; the publish step must be a person's."""
    for step in _route(X_ACCOUNT)["pipeline"]:
        for key in ("step", "command", "produces", "why"):
            assert step.get(key), (key, step)
    publish = next(step for step in _route(X_ACCOUNT)["pipeline"]
                   if step["step"] == "publish")
    assert "manual" in publish["why"].lower(), publish["why"]
    print("[ok] 12. every X step has a producer and the publish step is manual")


@test
def test_a_declared_pipeline_with_no_chain_is_refused():
    fake = {"slug": "x-test-text", "pipeline": "TEXT_SOMEWHERE",
            "evidence": {"mode": "EVIDENCE_LED"}, "narrative": {}, "visual": {}}
    try:
        ar.route_for(fake)
    except ar.RouteBlocked as blocked:
        assert blocked.code == "PIPELINE_UNMAPPED", blocked.code
        assert "X_EDITORIAL" in blocked.detail, blocked.detail
    else:
        raise AssertionError("an unimplemented declared pipeline produced a chain")
    print("[ok] 13. an undeclared pipeline is refused even when a mode would resolve")


@test
def test_a_manual_only_project_is_told_it_cannot_publish_itself():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        (project / "project.yaml").write_text(
            f"slug: x-growth-en\naccount_slug: {X_ACCOUNT}\n", encoding="utf-8")
        route = ar.resolve(project)
        warnings = " ".join(route["warnings"])
        assert "MANUAL_ONLY" in warnings, warnings
        assert "AWAITING_MANUAL_PUBLISH" in warnings, warnings
        # The X account has no duration window, so no cut warning may appear.
        assert "window" not in warnings, warnings
        assert route["publication_mode"] == "MANUAL_ONLY"
    print("[ok] 14. a MANUAL_ONLY project is told it cannot publish itself")


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
    print()
    if failures:
        print(f"{len(failures)} of {len(TESTS)} test(s) failed")
        return 1
    print(f"All {len(TESTS)} account-route tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
