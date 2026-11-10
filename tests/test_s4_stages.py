"""S4 workflow stage policies: audience, duration, strategy, platform, delivery, visual.

Run: python tests/test_s4_stages.py
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

from contentops.workflow import audience, copy_strategy, delivery, duration, platform, visual_route  # noqa: E402
from contentops.workflow.contract import WorkflowError  # noqa: E402

import design_router  # noqa: E402
import copy_strategy as copy_strategy_cli  # noqa: E402
import workflow_docs  # noqa: E402


def _raises(code, fn):
    try:
        fn()
    except WorkflowError as exc:
        assert exc.code == code, f"expected {code}, got {exc.code}: {exc}"
        return
    raise AssertionError(f"expected WorkflowError {code}")


def test_audience_is_derived_and_fails_closed():
    account = {"account_id": "x-1", "profile": {"audience_segment": "operator", "language": "zh-CN"}}
    brief = {"intent": {"topic": "如何做权利审计", "evidence_status": "verification_required"}}
    record = audience.validate_audience(audience.plan_audience(account, brief))
    assert record["segment"] == "operator"
    assert record["evidence_need"] == "direct_observation"
    assert record["production_ready"] is False
    _raises("AUDIENCE_SEGMENT_UNKNOWN",
            lambda: audience.plan_audience({"profile": {"audience_segment": "alien"}}, brief))
    _raises("AUDIENCE_TOPIC_MISSING",
            lambda: audience.plan_audience(account, {"intent": {}}))


def test_duration_divides_within_bounds_and_refuses_impossible_budgets():
    plan = duration.validate_duration(duration.plan_duration(40, 7))
    assert abs(sum(s["duration_s"] for s in plan["shots"]) - 40) < 0.002
    _raises("DURATION_UNSATISFIABLE", lambda: duration.plan_duration(5, 10))
    _raises("DURATION_UNSATISFIABLE", lambda: duration.plan_duration(500, 5))
    bad = dict(plan)
    bad["target_s"] = 41
    _raises("DURATION_SUM", lambda: duration.validate_duration(bad))


def test_copy_strategy_never_concludes_before_verification():
    assert copy_strategy.choose_strategy("HOTSPOT_DISCOVERY", "verification_required")["strategy"] == "news_brief"
    assert copy_strategy.choose_strategy("USER_TOPIC", "verification_required")["strategy"] == "tutorial"
    assert copy_strategy.choose_strategy("USER_TOPIC", "verified", has_real_material=True)["strategy"] == "case_study"
    assert copy_strategy.choose_strategy("USER_TOPIC", "verified")["strategy"] == "evidence_walkthrough"
    _raises("COPY_ROUTE_UNKNOWN", lambda: copy_strategy.choose_strategy("SOMEWHERE", "verified"))
    _raises("COPY_EVIDENCE_UNKNOWN", lambda: copy_strategy.choose_strategy("USER_TOPIC", "probably"))


def test_copy_strategy_cli_delegates_and_remains_pending_owner_review():
    record = copy_strategy_cli.build_strategy_record(
        route_mode="USER_TOPIC", evidence_status="verified", has_real_material=False)
    assert record["strategy"] == "evidence_walkthrough"
    assert record["production_ready"] is False
    assert record["review_status"] == "PENDING_OWNER_REVIEW"


def test_platform_constraints_are_local_and_refuse_mismatch():
    c = platform.constraints_for("douyin")
    assert c["aspect_ratio"] == "9:16"
    assert platform.validate_target({"aspect_ratio": "9:16", "duration_target_sec": 40}, c)["duration_target_sec"] == 40
    _raises("PLATFORM_UNKNOWN", lambda: platform.constraints_for("myspace"))
    _raises("PLATFORM_ASPECT_MISMATCH",
            lambda: platform.validate_target({"aspect_ratio": "16:9", "duration_target_sec": 40}, c))
    _raises("PLATFORM_DURATION",
            lambda: platform.validate_target({"aspect_ratio": "9:16", "duration_target_sec": 9999}, c))


def test_delivery_starts_awaiting_review_and_grants_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        package = Path(tmp) / "package.zip"
        package.write_bytes(b"package")
        manifest = delivery.build_manifest("p", package, platform="douyin")
        assert manifest["status"] == "AWAITING_MANUAL_REVIEW"
        assert manifest["publish_authorized"] is False and manifest["production_ready"] is False
        delivery.validate_manifest(manifest)
        _raises("DELIVERY_REVIEW_RECEIPT",
                lambda: delivery.build_manifest("p", package, platform="douyin", reviewer="owner"))
        reviewed = delivery.build_manifest("p", package, platform="douyin",
                                           reviewer="owner", review_receipt="receipts/review.json")
        assert reviewed["status"] == "REVIEWED"
        recorded = delivery.record_reported_publication(reviewed, "https://example.invalid/post/1")
        assert recorded["publication_state"] == "REPORTED_PUBLISHED"
        assert recorded["publish_authorized"] is False
        _raises("DELIVERY_NOT_REVIEWED",
                lambda: delivery.record_reported_publication(manifest, "https://example.invalid/post/1"))


def test_visual_route_refuses_generated_evidence():
    observed = visual_route.validate_visual_route(visual_route.choose_visual_route({
        "beat_id": "b1", "evidence_need": "direct_observation",
        "available": ["SCREENSHOT"], "rights_ok": True,
    }))
    assert observed["route"] == "SCREENSHOT" and observed["evidence_capable"] is True
    _raises("VISUAL_EVIDENCE_REQUIRED", lambda: visual_route.choose_visual_route({
        "beat_id": "b2", "evidence_need": "direct_observation",
        "available": ["GENERATED_SUPPORT"], "rights_ok": True,
    }))
    generated = visual_route.choose_visual_route({
        "beat_id": "b3", "evidence_need": "explanation",
        "available": ["GENERATED_SUPPORT"], "rights_ok": True,
    })
    assert generated["evidence_capable"] is False
    _raises("VISUAL_GENERATED_EVIDENCE", lambda: visual_route.validate_visual_route(
        {**generated, "evidence_capable": True}))


def test_design_router_refuses_automation_approval_and_builds_a_plan():
    account = {"account_id": "x-1", "profile": {"audience_segment": "operator", "language": "zh-CN"}}
    base = {
        "brief_id": "BRIEF-1",
        "intent": {"topic": "权利审计", "evidence_status": "verification_required",
                   "approval_status": "approved", "approved_by": "automation"},
    }
    _raises("BRIEF_AUTOMATION_APPROVAL",
            lambda: design_router.build_design(brief=base, account=account, platform="douyin",
                                               target_sec=40, line_count=7))
    base["intent"]["approved_by"] = "owner"
    plan = design_router.build_design(brief=base, account=account, platform="douyin",
                                      target_sec=40, line_count=7)
    assert plan["schema"] == design_router.SCHEMA
    assert plan["audience"]["segment"] == "operator"
    assert plan["copy_strategy"]["strategy"] == "tutorial"
    assert plan["production_ready"] is False


def test_workflow_docs_render_the_contract():
    data = workflow_docs.as_dict()
    ids = [stage["id"] for stage in data["stages"]]
    assert ids[0] == "brief" and ids[-1] == "delivery"
    text = workflow_docs.as_markdown()
    assert "| 1 | `brief` |" in text
    assert "contentops.copy-to-video/v1" in text
    assert "contentops.copy-to-graphic/v1" in text


TESTS = [value for name, value in sorted(globals().items())
         if name.startswith("test_") and callable(value)]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
            print(f"ok   {test.__name__}")
        except Exception as exc:  # noqa: BLE001 - a test runner reports, it does not hide
            failures += 1
            print(f"FAIL {test.__name__}: {exc}")
    total = len(TESTS)
    print(f"{total - failures}/{total} ok")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
