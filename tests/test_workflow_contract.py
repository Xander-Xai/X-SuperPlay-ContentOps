"""Production-contract tests: ordering, staleness and the policy lock.

Run: python tests/test_workflow_contract.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.workflow import (  # noqa: E402
    CONTRACT_ID,
    STAGES,
    STAGE_IDS,
    WorkflowError,
    is_current,
    load_workflow,
    new_workflow,
    policy_lock,
    reconcile,
    save_workflow,
    stage_by_id,
    validate_workflow,
)


def _expect_error(code, fn):
    try:
        fn()
    except WorkflowError as exc:
        assert exc.code == code, f"expected {code}, got {exc.code}: {exc}"
        return
    raise AssertionError(f"expected WorkflowError {code}, nothing was raised")


def test_stage_graph_is_ordered_and_acyclic():
    seen = []
    for stage in STAGES:
        for dependency in stage.requires:
            assert dependency in seen, f"{stage.id} depends on {dependency}, which comes later"
        seen.append(stage.id)
    assert list(STAGE_IDS) == [stage.id for stage in STAGES]
    assert len(set(STAGE_IDS)) == len(STAGE_IDS)


def test_every_stage_owns_one_artifact_path():
    artifacts = [stage.artifact for stage in STAGES]
    assert len(set(artifacts)) == len(artifacts)


def test_new_workflow_starts_pending_and_unapproved():
    document = new_workflow("demo", "x-superplay-1024")
    validate_workflow(document)
    assert document["contract"] == CONTRACT_ID
    assert all(item["status"] == "pending" for item in document["stages"])
    assert all(item["approval"] is None for item in document["stages"])
    assert stage_by_id("brief").artifact == "00_brief/brief.json"


def test_validate_refuses_an_unknown_status():
    document = new_workflow("demo")
    document["stages"][0]["status"] = "done-ish"
    _expect_error("INVALID_STATUS", lambda: validate_workflow(document))


def test_validate_refuses_approved_without_approval_record():
    document = new_workflow("demo")
    document["stages"][0]["status"] = "approved"
    _expect_error("APPROVAL_MISSING", lambda: validate_workflow(document))


def test_save_and_load_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        document = new_workflow("demo")
        target = Path(td) / "workflow.json"
        save_workflow(target, document)
        assert load_workflow(target) == document


def test_policy_lock_is_stable_and_names_the_contract():
    document = new_workflow("demo")
    first = policy_lock(document)
    assert first == policy_lock(document)
    assert first["contract"] == CONTRACT_ID
    assert first["stage_count"] == len(STAGES)
    assert len(first["stages_sha256"]) == 64


def test_editing_an_artifact_marks_its_approval_stale():
    with tempfile.TemporaryDirectory() as td:
        project = Path(td)
        document = new_workflow("demo")
        artifact = project / "00_brief" / "brief.json"
        artifact.parent.mkdir(parents=True)
        artifact.write_text(json.dumps({"schema": "x", "title": "t"}), encoding="utf-8")

        document["stages"][0].update({
            "status": "approved",
            "approval": {
                "reviewer": "Founder",
                "approved_at": "2026-10-28T00:00:00Z",
                # Deliberately not the file's digest: freshness must fail on
                # content, not on trust in the record.
                "artifact_sha256": "a" * 64,
                "inputs_sha256": "b" * 64,
            },
        })
        ok, reason = is_current(project, document, "brief")
        assert not ok and "changed" in reason, (ok, reason)

        changes = reconcile(project, document)
        assert document["stages"][0]["stale"] is True
        assert any(change["stage"] == "brief" and change["stale"] for change in changes)


def main() -> int:
    tests = (
        test_stage_graph_is_ordered_and_acyclic,
        test_every_stage_owns_one_artifact_path,
        test_new_workflow_starts_pending_and_unapproved,
        test_validate_refuses_an_unknown_status,
        test_validate_refuses_approved_without_approval_record,
        test_save_and_load_roundtrip,
        test_policy_lock_is_stable_and_names_the_contract,
        test_editing_an_artifact_marks_its_approval_stale,
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
    print("\nAll workflow contract tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
