"""Gate tests: check, approve, and the refusal to keep a stale approval.

Run: python tests/test_workflow_gate.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.workflow import (  # noqa: E402
    WorkflowError,
    approve_stage,
    artifact_path,
    check_stage,
    current_stage,
    is_current,
    new_workflow,
    reconcile,
)


def _expect_error(code, fn):
    try:
        fn()
    except WorkflowError as exc:
        assert exc.code == code, f"expected {code}, got {exc.code}: {exc}"
        return
    raise AssertionError(f"expected WorkflowError {code}, nothing was raised")


def _write(project: Path, relative: str, payload=None) -> Path:
    path = project / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload or {"ok": True}, ensure_ascii=False), encoding="utf-8")
    return path


def _stage(document, stage_id):
    return next(item for item in document["stages"] if item["id"] == stage_id)


def _approve(project, document, stage_id):
    result = check_stage(project, document, stage_id)
    assert result["ok"], (stage_id, result["errors"])
    approve_stage(project, document, stage_id, "Founder", confirm=True)
    assert _stage(document, stage_id)["status"] == "approved"


def test_check_fails_closed_when_the_artifact_is_missing():
    with tempfile.TemporaryDirectory() as td:
        project = Path(td)
        document = new_workflow("demo")
        result = check_stage(project, document, "brief")
        assert not result["ok"]
        assert any("missing" in message for message in result["errors"])
        assert document["stages"][0]["status"] == "blocked"


def test_check_passes_on_a_valid_json_artifact():
    with tempfile.TemporaryDirectory() as td:
        project = Path(td)
        document = new_workflow("demo")
        _write(project, "00_brief/brief.json", {"title": "t"})
        result = check_stage(project, document, "brief")
        assert result["ok"], result["errors"]
        assert document["stages"][0]["status"] == "ready_for_review"
        assert len(result["artifact_sha256"]) == 64


def test_check_refuses_unparsable_json():
    with tempfile.TemporaryDirectory() as td:
        project = Path(td)
        document = new_workflow("demo")
        path = project / "00_brief" / "brief.json"
        path.parent.mkdir(parents=True)
        path.write_text("{not json", encoding="utf-8")
        result = check_stage(project, document, "brief")
        assert not result["ok"]
        assert any("valid JSON" in message for message in result["errors"])


def test_approve_requires_confirmation_and_a_fresh_check():
    with tempfile.TemporaryDirectory() as td:
        project = Path(td)
        document = new_workflow("demo")
        _write(project, "00_brief/brief.json")
        _expect_error("CHECK_REQUIRED",
                      lambda: approve_stage(project, document, "brief", "Founder", confirm=True))
        check_stage(project, document, "brief")
        _expect_error("CONFIRMATION_REQUIRED",
                      lambda: approve_stage(project, document, "brief", "Founder"))


def test_check_requires_an_approved_upstream():
    with tempfile.TemporaryDirectory() as td:
        project = Path(td)
        document = new_workflow("demo")
        _write(project, "00_brief/brief.json")
        _write(project, "00_brief/audience-insight.json")
        result = check_stage(project, document, "audience")
        assert not result["ok"]
        assert any("upstream" in message for message in result["errors"])


def test_a_full_chain_approves_in_order():
    with tempfile.TemporaryDirectory() as td:
        project = Path(td)
        document = new_workflow("demo")
        _write(project, "00_brief/brief.json")
        _approve(project, document, "brief")
        _write(project, "00_brief/audience-insight.json")
        _approve(project, document, "audience")
        assert current_stage(document) == "research"


def test_editing_an_artifact_retires_its_approval_and_blocks_the_next_stage():
    with tempfile.TemporaryDirectory() as td:
        project = Path(td)
        document = new_workflow("demo")
        _write(project, "00_brief/brief.json")
        _approve(project, document, "brief")
        _write(project, "00_brief/audience-insight.json")
        _approve(project, document, "audience")
        assert is_current(project, document, "audience")[0]

        # Change the upstream brief after both approvals.
        _write(project, "00_brief/brief.json", {"title": "changed"})
        reconcile(project, document)
        assert document["stages"][0]["stale"] is True
        assert document["stages"][1]["stale"] is True

        ok, reason = is_current(project, document, "audience")
        assert not ok and "upstream" in reason
        _expect_error("CHECK_REQUIRED",
                      lambda: approve_stage(project, document, "audience", "Founder", confirm=True))


def test_a_check_that_sees_new_bytes_retires_the_old_approval():
    with tempfile.TemporaryDirectory() as td:
        project = Path(td)
        document = new_workflow("demo")
        _write(project, "00_brief/brief.json")
        _approve(project, document, "brief")
        # The check itself notices the file changed and drops the approval.
        _write(project, "00_brief/brief.json", {"title": "v2"})
        result = check_stage(project, document, "brief")
        assert result["ok"]
        assert document["stages"][0]["approval"] is None
        assert document["stages"][0]["status"] == "ready_for_review"
        assert any("retired" in message for message in result["warnings"])


def test_rechecking_unchanged_bytes_keeps_the_approval():
    with tempfile.TemporaryDirectory() as td:
        project = Path(td)
        document = new_workflow("demo")
        _write(project, "00_brief/brief.json")
        _approve(project, document, "brief")
        result = check_stage(project, document, "brief")
        assert result["ok"]
        assert _stage(document, "brief")["status"] == "approved"
        assert document["stages"][0]["approval"] is not None


def test_an_artifact_path_may_not_escape_the_project():
    with tempfile.TemporaryDirectory() as td:
        project = Path(td) / "pkg"
        project.mkdir()
        document = new_workflow("demo")
        document["stages"][0]["artifact"] = "../outside.json"
        _expect_error("ARTIFACT_ESCAPES_PROJECT",
                      lambda: artifact_path(project, document, "brief"))


def test_a_crashing_validator_fails_closed():
    with tempfile.TemporaryDirectory() as td:
        project = Path(td)
        document = new_workflow("demo")
        _write(project, "00_brief/brief.json")

        def boom(_path):
            raise RuntimeError("validator exploded")

        result = check_stage(project, document, "brief", validators=[boom])
        assert not result["ok"]
        assert any("raised" in message for message in result["errors"])


def main() -> int:
    tests = (
        test_check_fails_closed_when_the_artifact_is_missing,
        test_check_passes_on_a_valid_json_artifact,
        test_check_refuses_unparsable_json,
        test_approve_requires_confirmation_and_a_fresh_check,
        test_check_requires_an_approved_upstream,
        test_a_full_chain_approves_in_order,
        test_editing_an_artifact_retires_its_approval_and_blocks_the_next_stage,
        test_a_check_that_sees_new_bytes_retires_the_old_approval,
        test_rechecking_unchanged_bytes_keeps_the_approval,
        test_an_artifact_path_may_not_escape_the_project,
        test_a_crashing_validator_fails_closed,
    )
    failures = []
    for fn in tests:
        try:
            fn()
            print(f"[ok] {fn.__name__}")
        except AssertionError as exc:
            failures.append((fn.__name__, str(exc)))
            print(f"[FAIL] {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append((fn.__name__, repr(exc)))
            print(f"[ERR ] {fn.__name__}: {exc!r}")
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print("\nAll workflow gate tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
