"""Capture-plan tests: the recording brief exists and cannot contradict policy.

Run: python tests/test_capture_plan.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from contentops.workflow.capture_plan import (  # noqa: E402
    plan,
    recommend_mode,
    validate_capture_plan,
)
import recording_plan  # noqa: E402


def _beat(**overrides):
    beat = {
        "beat_id": "B01",
        "unit_id": "U01",
        "claim_ids": ["C1"],
        "spoken_text": "在终端里跑一次 doctor",
        "evidence_need": "direct_observation",
        "start_ms": 0,
        "end_ms": 4000,
        "redaction_required": True,
    }
    beat.update(overrides)
    return beat


def _planned(policy="ALLOWED_CROPPED", **overrides):
    return plan([_beat(**overrides)], account="x-superplay-1024", recording_policy=policy)


def _codes(errors):
    return " | ".join(errors)


def test_planner_routes_a_command_to_the_terminal():
    recommendation = recommend_mode({"spoken_text": "在终端里跑 npm install", "evidence_need": "direct_observation"})
    assert recommendation["mode"] == "terminal_evidence", recommendation
    assert recommendation["reasons"], "a recommendation must say why"


def test_planner_routes_a_repository_to_the_browser():
    recommendation = recommend_mode({"spoken_text": "打开 github 仓库", "evidence_need": "direct_observation"})
    assert recommendation["mode"] == "browser_evidence", recommendation


def test_planner_routes_an_explanation_to_a_card():
    recommendation = recommend_mode({"spoken_text": "区别在于谁做决策", "evidence_need": "explanation"})
    assert recommendation["mode"] == "card_only", recommendation


def test_an_explicit_route_wins_over_keywords():
    recommendation = recommend_mode({"route": "whiteboard", "spoken_text": "终端", "evidence_need": "direct_observation"})
    assert recommendation["mode"] == "whiteboard_excalidraw", recommendation


def test_a_valid_plan_passes():
    document = _planned()
    assert validate_capture_plan(document) == []


def test_forbidden_recording_never_reaches_a_recording_surface():
    document = _planned(policy="FORBIDDEN")
    beats = document["beats"]
    assert beats[0]["capture"]["surface"] == "card", beats[0]["capture"]
    # The beat still demands a direct observation, which a card cannot show.
    # The planner does not pretend otherwise.
    errors = validate_capture_plan(document)
    assert any("direct observation" in message for message in errors), _codes(errors)


def test_a_card_cannot_satisfy_a_direct_observation():
    document = _planned()
    document["beats"][0]["capture"]["surface"] = "card"
    errors = validate_capture_plan(document)
    assert any("direct observation" in message for message in errors), _codes(errors)


def test_a_capture_must_name_what_the_viewer_will_see():
    document = _planned()
    document["beats"][0]["capture"]["must_show"] = ["结果"]
    errors = validate_capture_plan(document)
    assert any("at least 2" in message for message in errors), _codes(errors)


def test_recording_on_a_forbidden_account_is_refused():
    document = _planned()
    document["recording_policy"] = "FORBIDDEN"
    errors = validate_capture_plan(document)
    assert any("forbids recording" in message for message in errors), _codes(errors)


def test_redaction_must_be_an_explicit_decision():
    document = _planned()
    del document["beats"][0]["redaction_required"]
    errors = validate_capture_plan(document)
    assert any("redaction_required" in message for message in errors), _codes(errors)


def test_declared_redaction_must_reach_the_capture():
    document = _planned()
    document["beats"][0]["capture"]["redaction"] = "none"
    errors = validate_capture_plan(document)
    assert any("does not require it" in message for message in errors), _codes(errors)


def test_overlapping_beats_are_refused():
    document = plan(
        [_beat(), _beat(beat_id="B02", start_ms=3000, end_ms=6000)],
        account="x-superplay-1024",
        recording_policy="ALLOWED_CROPPED",
    )
    errors = validate_capture_plan(document)
    assert any("before the previous beat ends" in message for message in errors), _codes(errors)


def test_duplicate_beat_ids_are_refused():
    document = plan(
        [_beat(), _beat(start_ms=4000, end_ms=8000)],
        account="x-superplay-1024",
        recording_policy="ALLOWED_CROPPED",
    )
    errors = validate_capture_plan(document)
    assert any("duplicate beat_id" in message for message in errors), _codes(errors)


def test_unknown_schema_and_policy_are_refused():
    document = _planned()
    document["schema"] = "something/else"
    document["recording_policy"] = "SOMETIMES"
    errors = validate_capture_plan(document)
    assert any("schema" in message for message in errors), _codes(errors)
    assert any("recording_policy" in message for message in errors), _codes(errors)


def _project(td, account="x-superplay-1024"):
    folder = Path(td)
    (folder / "script").mkdir(parents=True, exist_ok=True)
    (folder / "project.yaml").write_text(f"slug: demo\naccount_slug: {account}\n", encoding="utf-8")
    storyboard = {
        "size": "1080x1920",
        "shots": [
            {"source": "project://a.png", "source_type": "real_screenshot",
             "narration": "在终端里跑 doctor", "unit": "U01", "placement": "shot_00", "duration": 4.0},
            {"source": "project://b.png", "source_type": "designed_card",
             "narration": "区别在于谁做决策", "unit": "U02", "placement": "shot_01", "duration": 3.0},
        ],
    }
    (folder / "script" / "storyboard.json").write_text(json.dumps(storyboard, ensure_ascii=False), encoding="utf-8")
    return folder


def test_cli_writes_a_valid_plan_beside_the_storyboard():
    with tempfile.TemporaryDirectory() as td:
        folder = _project(td)
        code = recording_plan.main([str(folder)])
        assert code == 0, code
        written = folder / "script" / "capture-plan.json"
        assert written.is_file()
        document = json.loads(written.read_text(encoding="utf-8"))
        assert document["recording_policy"] == "ALLOWED_CROPPED"
        assert document["beats"][0]["capture"]["surface"] == "terminal"
        assert validate_capture_plan(document) == []
        assert recording_plan.main([str(folder), "--check"]) == 0


def test_cli_refuses_an_account_that_forbids_recording():
    with tempfile.TemporaryDirectory() as td:
        folder = _project(td, account="x-superplay-future-intelligence")
        code = recording_plan.main([str(folder)])
        # The plan is written only when valid; a beat that demands a direct
        # observation cannot be satisfied on an account that forbids recording.
        assert code == 1, code
        assert not (folder / "script" / "capture-plan.json").exists()


def main() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
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
    print("\nAll capture-plan tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
