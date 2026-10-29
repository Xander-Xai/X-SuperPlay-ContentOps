"""Tests for the capabilities absorbed from dy_x1024.

Run: python tests/test_absorbed_workflow_docs.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.workflow import feedback, human_forecast, improvement, platform, provenance, rights, topics  # noqa: E402
from contentops.workflow.validators import publish_plan_validator, validators_for  # noqa: E402

SHA = "a" * 64


# --- topics -------------------------------------------------------------

def _backlog(**overrides):
    document = {
        "schema": "contentops.topic-backlog/v1",
        "topics": [{
            "topic_id": "T-001", "title": "测一个新模型", "shelf": "ai_tool_validation",
            "content_type": "tool_test", "status": "backlog",
        }],
    }
    document.update(overrides)
    return document


def _candidate(**overrides):
    document = {
        "schema": "contentops.content-candidate/v1",
        "candidate_id": "C-001",
        "title": "这个模型值得用吗",
        "thesis": "先看真实任务，再决定投入",
        "audience_segment": "capability_decider",
        "decision": "ACCEPT",
        "positioning_alignment": "ALIGNED",
        "trust_level": "HIGH",
        "need_scores": {key: 3 for key in topics.DEFAULT_NEED_WEIGHTS},
        "value_scores": {key: 3 for key in topics.DEFAULT_VALUE_WEIGHTS},
    }
    document.update(overrides)
    return document


def test_a_well_formed_backlog_passes():
    assert topics.validate_backlog(_backlog()) == []


def test_a_duplicate_topic_id_fails():
    document = _backlog()
    document["topics"].append(dict(document["topics"][0]))
    errors = topics.validate_backlog(document)
    assert any("duplicates" in message for message in errors), errors


def test_an_unknown_shelf_or_status_fails():
    errors = topics.validate_backlog(_backlog(topics=[{
        "topic_id": "T-1", "title": "x", "shelf": "random", "content_type": "tool_test",
        "status": "someday"}]))
    assert any("shelf" in message for message in errors), errors
    assert any("status" in message for message in errors), errors


def test_candidate_scoring_is_the_weighted_average():
    result = topics.score_candidate(_candidate())
    assert result["combined"] == 3.0, result
    assert result["errors"] == []


def test_weights_must_sum_to_one_hundred():
    try:
        topics.score_candidate(_candidate(), need_weights={"problem_frequency": 1})
    except ValueError:
        return
    raise AssertionError("weights that do not sum to 100 must be refused")


def test_an_off_positioning_candidate_cannot_be_accepted():
    errors = topics.validate_candidate(_candidate(positioning_alignment="OFF_POSITIONING"))
    assert any("OFF_POSITIONING" in message for message in errors), errors


def test_a_broad_audience_term_fails_candidate_validation():
    errors = topics.validate_candidate(_candidate(audience_segment="所有人"))
    assert any("broad audience term" in message for message in errors), errors


def test_candidates_rank_highest_first():
    high = _candidate(candidate_id="C-HIGH")
    high["need_scores"] = {key: 5 for key in topics.DEFAULT_NEED_WEIGHTS}
    high["value_scores"] = {key: 5 for key in topics.DEFAULT_VALUE_WEIGHTS}
    ranked = topics.rank_candidates([_candidate(), high])
    assert ranked[0]["candidate_id"] == "C-HIGH"


# --- evidence feasibility ----------------------------------------------

def _forecast(**overrides):
    document = {
        "schema": "contentops.evidence-feasibility/v1",
        "topic_id": "T-001",
        "assessment_basis": "这条选题需要一次真实终端运行和官方文档",
        "failure_plan": "change_claim",
        "evidence": [
            {"kind": "terminal_capture", "required": True, "owner": "human", "available": True},
            {"kind": "real_document", "required": False, "owner": "human", "available": False},
        ],
    }
    document.update(overrides)
    return document


def test_a_feasible_forecast_passes():
    assert human_forecast.validate_forecast(_forecast()) == []
    assert human_forecast.forecast_verdict(_forecast()) == "FEASIBLE"


def test_missing_required_evidence_blocks_unless_degraded():
    blocked = _forecast(evidence=[
        {"kind": "terminal_capture", "required": True, "owner": "human", "available": False}])
    assert human_forecast.forecast_verdict(blocked) == "BLOCKED"
    degraded = dict(blocked, failure_plan="degrade_and_declare", degrade_note="只做文档引用卡")
    assert human_forecast.forecast_verdict(degraded) == "DEGRADED"


def test_degrades_without_a_note_fail():
    errors = human_forecast.validate_forecast(_forecast(
        failure_plan="degrade_and_declare",
        evidence=[{"kind": "terminal_capture", "required": True,
                   "owner": "human", "available": False}]))
    assert any("degrade_note" in message for message in errors), errors


def test_required_evidence_of_kind_none_fails():
    errors = human_forecast.validate_forecast(_forecast(evidence=[
        {"kind": "none", "required": True, "owner": "human", "available": True}]))
    assert any("kind 'none'" in message for message in errors), errors


# --- platform -----------------------------------------------------------

def _plan(**overrides):
    document = {
        "schema": "contentops.publish-plan/v1",
        "platform": "douyin",
        "title": "这个模型到底值不值得用",
        "hashtags": ["AI", "实测"],
        "cta": "评论区说你的任务",
        "cta_count": 1,
        "contains_generated_media": False,
        "commercial": False,
        "rights_status": "owned",
        "evidence_plan": "两条真实终端录屏",
    }
    document.update(overrides)
    return document


def test_a_safe_publish_plan_passes():
    assert platform.validate_plan(_plan()) == []
    assert platform.plan_verdict(_plan()) == "READY_FOR_APPROVAL"


def test_two_ctas_fail():
    errors = platform.validate_plan(_plan(cta_count=2))
    assert any("cta_count" in message for message in errors), errors


def test_generated_media_without_ai_disclosure_fails():
    errors = platform.validate_plan(_plan(contains_generated_media=True))
    assert any("ai_disclosure" in message for message in errors), errors


def test_unknown_rights_cannot_be_published():
    errors = platform.validate_plan(_plan(rights_status="unknown"))
    assert any("not publishable" in message for message in errors), errors


def test_a_forbidden_claim_phrase_fails():
    errors = platform.validate_plan(_plan(title="全网最值得用的模型"))
    assert any("forbidden claim phrase" in message for message in errors), errors


# --- rights -------------------------------------------------------------

def _ledger(**overrides):
    document = {
        "schema": "contentops.rights-ledger/v1",
        "assets": [{
            "asset_id": "A-1", "owner": "Founder", "license": "owned",
            "permission_scope": "publishable", "source_url": "project://work/cap.mp4",
            "attribution": "X•超玩1024", "license_url": "https://example.com/licence",
        }],
    }
    document.update(overrides)
    return document


def test_a_clean_rights_ledger_passes():
    assert rights.validate_ledger(_ledger()) == []


def test_a_publishable_asset_needs_a_licence_and_attribution():
    errors = rights.validate_ledger(_ledger(assets=[{
        "asset_id": "A-1", "owner": "someone", "license": "unknown",
        "permission_scope": "publishable", "source_url": "https://example.com/x",
        "attribution": ""}]))
    assert any("licence is unknown" in message or "license is unknown" in message for message in errors), errors
    assert any("attribution" in message for message in errors), errors


def test_an_internal_asset_may_have_an_unknown_licence():
    errors = rights.validate_ledger(_ledger(assets=[{
        "asset_id": "A-1", "owner": "someone", "license": "unknown",
        "permission_scope": "internal", "source_url": "https://example.com/x"}]))
    assert errors == [], errors


# --- improvement log ----------------------------------------------------

def _log():
    return {"schema": "contentops.workflow-improvement-log/v1", "entries": []}


def _entry(**overrides):
    entry = improvement.new_entry(
        entry_id="W-001", stage="quality", category="gate", severity="high",
        summary="quality read a stale path", observed="read 05_publish",
        expected="read 07_quality", reproduction="run the gate", evidence=[],
    )
    entry.update(overrides)
    return entry


def test_an_empty_log_is_valid_and_entries_can_be_appended():
    document = improvement.append_entry(_log(), _entry())
    assert improvement.validate_log(document) == []


def test_a_duplicate_entry_id_fails():
    document = improvement.append_entry(_log(), _entry())
    try:
        improvement.append_entry(document, _entry())
    except ValueError:
        return
    raise AssertionError("duplicate entry_id must be refused")


def test_status_transitions_are_enforced():
    document = improvement.append_entry(_log(), _entry())
    improvement.advance(document, "W-001", "triaged")
    try:
        improvement.advance(document, "W-001", "verified")
    except ValueError:
        return
    raise AssertionError("triaged -> verified must be refused")


def test_wont_fix_requires_a_reason():
    document = improvement.append_entry(_log(), _entry())
    try:
        improvement.advance(document, "W-001", "wont_fix")
    except ValueError:
        return
    raise AssertionError("wont_fix without a reason must be refused")


def test_evidence_must_carry_a_sha256():
    try:
        improvement.append_entry(_log(), _entry(
            evidence=[{"path": "a.json", "sha256": "not-a-sha"}]))
    except ValueError as exc:
        assert "sha256" in str(exc), exc
        return
    raise AssertionError("evidence without a valid sha256 must be refused")


# --- feedback -----------------------------------------------------------

def _feedback(**overrides):
    document = {
        "schema": "contentops.feedback/v1",
        "content_id": "VID-001", "platform": "douyin", "status": "published",
        "published_url": "https://example.com/v", "published_at": "2026-10-28T10:00:00Z",
        "metrics": {"views": 100, "likes": 5}, "signals": ["评论复述了具体处境"],
    }
    document.update(overrides)
    return document


def test_a_published_feedback_record_passes():
    assert feedback.validate_feedback(_feedback()) == []


def test_a_published_record_needs_a_url():
    errors = feedback.validate_feedback(_feedback(published_url=""))
    assert any("published_url" in message for message in errors), errors


def test_a_negative_metric_fails():
    errors = feedback.validate_feedback(_feedback(metrics={"views": -1}))
    assert any("non-negative" in message for message in errors), errors


def test_metrics_merge_does_not_mutate_the_original():
    original = _feedback()
    merged = feedback.merge_metrics(original, {"content_id": "VID-001",
                                               "metrics": {"saves": 9}})
    assert "saves" not in original["metrics"]
    assert merged["metrics"]["saves"] == 9


def test_a_metrics_import_requires_rows():
    errors = feedback.validate_metrics_import({
        "schema": "contentops.metrics-import/v1", "rows": []})
    assert any("non-empty" in message for message in errors), errors


# --- provenance ---------------------------------------------------------

def _skill_dir(td: Path) -> Path:
    root = td / "skill"
    (root / "references").mkdir(parents=True)
    (root / "SKILL.md").write_text("---\nname: demo\n---\n", encoding="utf-8")
    (root / "references" / "a.md").write_text("body\n", encoding="utf-8")
    return root


def test_a_bound_run_validates():
    with tempfile.TemporaryDirectory() as td:
        root = _skill_dir(Path(td))
        document = provenance.bind_run(
            skill="demo", skill_dir=root, command="python x.py", exit_code=0,
            started_at="2026-10-28T10:00:00Z", finished_at="2026-10-28T10:01:00Z",
            inputs=[{"path": "in.json", "sha256": SHA}],
            outputs=[{"path": "out.mp4", "sha256": SHA}])
        assert provenance.validate_provenance(document) == []


def test_changing_a_skill_file_changes_its_fingerprint():
    with tempfile.TemporaryDirectory() as td:
        root = _skill_dir(Path(td))
        before = provenance.skill_tree_fingerprint(root)["skill_sha256"]
        (root / "references" / "a.md").write_text("changed\n", encoding="utf-8")
        after = provenance.skill_tree_fingerprint(root)["skill_sha256"]
        assert before != after


def test_a_failed_run_may_have_no_outputs():
    with tempfile.TemporaryDirectory() as td:
        root = _skill_dir(Path(td))
        document = provenance.bind_run(
            skill="demo", skill_dir=root, command="python x.py", exit_code=1,
            started_at="2026-10-28T10:00:00Z", finished_at="2026-10-28T10:01:00Z",
            inputs=[], outputs=[])
        assert provenance.validate_provenance(document) == []


# --- stage wiring -------------------------------------------------------

def test_assets_stage_reads_a_sibling_rights_ledger():
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td)
        (folder / "asset-ledger.json").write_text("{}", encoding="utf-8")
        (folder / "rights-ledger.json").write_text(json.dumps(_ledger()), encoding="utf-8")
        # Name the validator, do not index the list: an index silently tests
        # whatever happens to sit at [0] after a reorder.
        from contentops.workflow.validators import rights_validator

        assert rights_validator in validators_for("assets")
        assert rights_validator(folder / "asset-ledger.json") == []


def _manifest(**overrides):
    document = {
        "schema": "contentops.delivery-manifest/v1",
        "content_id": "douyin-20261028-001-topic-a1b2c3",
        "platform": "douyin",
        "files": [{"path": "video.mp4", "sha256": "a" * 64, "role": "video"}],
        "gate": {"contract": "contentops.copy-to-video/v1", "stages_current": True},
        "human_review": "PENDING",
    }
    document.update(overrides)
    return document


def test_delivery_stage_reads_a_sibling_publish_plan():
    # The delivery stage runs two validators: the manifest itself and the
    # publish plan beside it. Asserting every validator passes proves the
    # sibling wiring is live, not just that the manifest shape is accepted.
    assert publish_plan_validator in validators_for("delivery")
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td)
        (folder / "delivery-manifest.json").write_text(json.dumps(_manifest()), encoding="utf-8")
        (folder / "publish-plan.json").write_text(json.dumps(_plan()), encoding="utf-8")
        for validator in validators_for("delivery"):
            errors = validator(folder / "delivery-manifest.json")
            assert errors == [], f"{validator.__name__}: {errors}"


def test_delivery_stage_refuses_a_bad_sibling_publish_plan():
    with tempfile.TemporaryDirectory() as td:
        folder = Path(td)
        (folder / "delivery-manifest.json").write_text(json.dumps(_manifest()), encoding="utf-8")
        (folder / "publish-plan.json").write_text(
            json.dumps(_plan(cta_count=2)), encoding="utf-8")
        errors = publish_plan_validator(folder / "delivery-manifest.json")
        assert any("cta_count" in message for message in errors), errors


def main() -> int:
    tests = (
        test_a_well_formed_backlog_passes,
        test_a_duplicate_topic_id_fails,
        test_an_unknown_shelf_or_status_fails,
        test_candidate_scoring_is_the_weighted_average,
        test_weights_must_sum_to_one_hundred,
        test_an_off_positioning_candidate_cannot_be_accepted,
        test_a_broad_audience_term_fails_candidate_validation,
        test_candidates_rank_highest_first,
        test_a_feasible_forecast_passes,
        test_missing_required_evidence_blocks_unless_degraded,
        test_degrades_without_a_note_fail,
        test_required_evidence_of_kind_none_fails,
        test_a_safe_publish_plan_passes,
        test_two_ctas_fail,
        test_generated_media_without_ai_disclosure_fails,
        test_unknown_rights_cannot_be_published,
        test_a_forbidden_claim_phrase_fails,
        test_a_clean_rights_ledger_passes,
        test_a_publishable_asset_needs_a_licence_and_attribution,
        test_an_internal_asset_may_have_an_unknown_licence,
        test_an_empty_log_is_valid_and_entries_can_be_appended,
        test_a_duplicate_entry_id_fails,
        test_status_transitions_are_enforced,
        test_wont_fix_requires_a_reason,
        test_evidence_must_carry_a_sha256,
        test_a_published_feedback_record_passes,
        test_a_published_record_needs_a_url,
        test_a_negative_metric_fails,
        test_metrics_merge_does_not_mutate_the_original,
        test_a_metrics_import_requires_rows,
        test_a_bound_run_validates,
        test_changing_a_skill_file_changes_its_fingerprint,
        test_a_failed_run_may_have_no_outputs,
        test_assets_stage_reads_a_sibling_rights_ledger,
        test_delivery_stage_reads_a_sibling_publish_plan,
        test_delivery_stage_refuses_a_bad_sibling_publish_plan,
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
    print("\nAll absorbed workflow-document tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
