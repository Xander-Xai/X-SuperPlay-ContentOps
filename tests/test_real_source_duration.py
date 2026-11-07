"""The measured real-source gate: seconds the viewer actually sees, not shot count.

The cases that matter are the ones the old shot-count ratio let through:

- a few seconds of real screenshots followed by one long diagram;
- an overlay that repeats the same real second twice;
- a cut whose rendered file is longer than its storyboard;
- an unknown source kind treated as if it were evidence.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.media.real_source_duration import (  # noqa: E402
    BLOCKED,
    FAIL,
    MIN_REAL_DURATION_RATIO,
    PASS,
    check,
    measure,
)

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def _shot(shot_id: str, duration: float, kind: str, source: str = "projects/x/real.png",
          start=None) -> dict:
    shot = {"shot_id": shot_id, "duration": duration, "source": source,
            "source_type": kind}
    if start is not None:
        shot["start"] = start
    return shot


def _assets(*paths: str, permission: str = "CREATED_BY_OWNER") -> dict:
    return {"schema": "contentops.m5-assets/v1",
            "assets": [{"id": f"a{i}", "repo_path": path, "permission": permission}
                       for i, path in enumerate(paths)]}


def _measure(shots, duration, assets=None, require_permission=True) -> dict:
    return measure({"shots": shots}, output_duration_s=duration,
                   assets=assets or _assets("projects/x/real.png"),
                   require_permission=require_permission)


@test
def test_a_ninety_five_second_cut_needs_sixty_six_and_a_half_seconds_of_material():
    real = [ _shot(f"r{i}", 1.0, "real_screenshot") for i in range(66) ]
    real.append(_shot("r66", 0.5, "real_screenshot"))
    diagram = _shot("d1", 28.5, "diagram", "projects/x/d.png")
    result = _measure(real + [diagram], 95.0,
                      _assets("projects/x/real.png", "projects/x/d.png"))
    assert result["state"] == PASS, result
    assert result["real_seconds"] == 66.5, result
    assert result["real_source_duration_ratio"] == round(66.5 / 95.0, 4)

    result = _measure(real[:66] + [_shot("r66", 0.4, "real_screenshot")] + [diagram],
                      95.0, _assets("projects/x/real.png", "projects/x/d.png"))
    assert result["state"] == FAIL, result
    print("[ok] 1. 95 s needs 66.5 s, and 66.4 s fails")


@test
def test_explanatory_motion_can_be_primary_without_claiming_to_be_evidence():
    shots = [_shot("m1", 10.0, "generated_video", "projects/x/motion.mp4")]
    result = measure({"shots": shots}, output_duration_s=10.0,
                     assets=_assets("projects/x/motion.mp4"), min_ratio=0.0)
    assert result["state"] == PASS, result
    assert result["real_source_duration_ratio"] == 0.0
    assert result["min"] == 0.0
    # It still blocks when provenance is absent, even with a zero real-capture floor.
    missing = measure({"shots": [_shot("m1", 10.0, "generated_video", "")]},
                      output_duration_s=10.0, min_ratio=0.0)
    assert missing["state"] == BLOCKED and missing["code"] == "SOURCE_MISSING", missing
    print("[ok] explanatory visuals may dominate; source traceability is still required")


@test
def test_a_hundred_and_ten_second_cut_needs_seventy_seven_seconds():
    shots = [_shot(f"r{i}", 1.0, "real_recording") for i in range(77)]
    shots.append(_shot("d1", 33.0, "diagram", "projects/x/d.png"))
    ok = _measure(shots, 110.0, _assets("projects/x/real.png", "projects/x/d.png"))
    assert ok["state"] == PASS, ok
    assert ok["real_seconds"] == 77.0

    short = [_shot(f"r{i}", 1.0, "real_recording") for i in range(76)]
    short.append(_shot("d1", 34.0, "diagram", "projects/x/d.png"))
    bad = _measure(short, 110.0, _assets("projects/x/real.png", "projects/x/d.png"))
    assert bad["state"] == FAIL, bad
    print("[ok] 2. 110 s needs 77 s")


@test
def test_a_long_diagram_cannot_hide_behind_many_short_real_shots():
    shots = [_shot(f"r{i}", 1.0, "real_screenshot") for i in range(19)]
    shots.append(_shot("d1", 76.0, "diagram", "projects/x/d.png"))
    result = _measure(shots, 95.0, _assets("projects/x/real.png", "projects/x/d.png"))
    assert result["state"] == FAIL, result
    assert result["real_source_duration_ratio"] < 0.25, result
    # The old diagnostic would have counted 19 of 20 shots as real.
    assert 19 / 20 >= 0.70
    print("[ok] 3. shot count would pass; visible seconds do not")


@test
def test_an_overlay_counts_its_second_once():
    shots = [
        _shot("r1", 2.0, "real_screenshot", start=0.0),
        _shot("r1-overlay", 2.0, "real_screenshot", start=0.0),
        _shot("d1", 1.0, "diagram", "projects/x/d.png", start=2.0),
    ]
    result = _measure(shots, 3.0, _assets("projects/x/real.png", "projects/x/d.png"))
    assert result["real_seconds"] == 2.0, result
    assert result["real_source_duration_ratio"] == round(2.0 / 3.0, 4)
    print("[ok] 4. overlapping intervals are unioned")


@test
def test_the_rendered_file_is_the_denominator_not_the_storyboard_sum():
    shots = [_shot(f"r{i}", 1.0, "real_screenshot") for i in range(70)]
    result = _measure(shots, 100.0, _assets("projects/x/real.png"))
    assert result["state"] == PASS
    assert result["undeclared_tail_s"] == 30.0, result
    # The same material in a 100 s file is 70%, not 100%.
    assert result["real_source_duration_ratio"] == 0.7, result
    print("[ok] 5. undeclared time counts against the ratio")


@test
def test_generated_and_motion_do_not_count():
    shots = [
        _shot("g1", 8.0, "generated_video", "projects/x/gen.mp4"),
        _shot("m1", 7.0, "motion", "projects/x/motion.mp4"),
        _shot("t1", 5.0, "title_card", "projects/x/card.png"),
        _shot("r1", 10.0, "real_recording"),
    ]
    result = _measure(shots, 30.0,
                      _assets("projects/x/gen.mp4", "projects/x/motion.mp4",
                              "projects/x/card.png", "projects/x/real.png"))
    assert result["state"] == FAIL, result
    assert result["real_seconds"] == 10.0
    print("[ok] 6. generated, motion and cards do not count")


@test
def test_an_unknown_kind_is_not_evidence():
    shots = [_shot("u1", 8.0, "something_new"), _shot("r1", 2.0, "real_screenshot")]
    result = _measure(shots, 10.0, _assets("projects/x/real.png"))
    assert result["real_seconds"] == 2.0, result
    assert any(iv["reason"].startswith("unclassified") for iv in result["intervals"])
    print("[ok] 7. an unclassified source is counted as non-real")


@test
def test_a_real_shot_without_a_rights_record_blocks():
    shots = [_shot("r1", 5.0, "real_screenshot")]
    result = _measure(shots, 5.0, {"assets": [{"id": "a", "repo_path": "projects/x/real.png"}]})
    assert result["state"] == BLOCKED, result
    assert result["code"] == "SOURCE_PERMISSION_MISSING", result
    print("[ok] 8. a real shot with no permission blocks instead of counting")


@test
def test_a_shot_with_no_source_blocks():
    result = _measure([_shot("r1", 5.0, "real_screenshot", source="")], 5.0, {"assets": []})
    assert result["state"] == BLOCKED, result
    assert result["code"] == "SOURCE_MISSING", result
    print("[ok] 9. a shot with no source blocks")


@test
def test_missing_output_duration_is_blocked_not_assumed():
    result = measure({"shots": [_shot("r1", 5.0, "real_screenshot")]},
                     output_duration_s=0.0, assets=_assets("projects/x/real.png"))
    assert result["state"] == BLOCKED, result
    assert result["code"] == "OUTPUT_DURATION_MISSING", result
    print("[ok] 10. no measured denominator means BLOCKED")


@test
def test_a_shot_with_no_duration_blocks():
    result = _measure([{"shot_id": "r1", "source": "projects/x/real.png",
                        "source_type": "real_screenshot"}], 5.0)
    assert result["state"] == BLOCKED, result
    assert result["code"] == "SHOT_DURATION_MISSING", result
    print("[ok] 11. a shot with no duration blocks")


@test
def test_check_reads_the_project_and_blocks_a_missing_storyboard():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        result = check(project, output_duration_s=10.0)
        assert result["state"] == BLOCKED
        assert result["code"] == "STORYBOARD_MISSING", result

    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        (project / "script").mkdir(parents=True)
        (project / "sources").mkdir(parents=True)
        (project / "script" / "storyboard.json").write_text(json.dumps({
            "shots": [_shot("r1", 7.0, "real_screenshot"),
                      _shot("d1", 3.0, "diagram", "projects/x/d.png")]}),
            encoding="utf-8")
        (project / "sources" / "assets.json").write_text(json.dumps(
            _assets("projects/x/real.png", "projects/x/d.png")), encoding="utf-8")
        result = check(project, output_duration_s=10.0)
        assert result["state"] == PASS, result
        assert result["real_seconds"] == 7.0
        print("[ok] 12. check reads storyboard and assets from the project")


@test
def test_the_threshold_is_the_documented_seventy_percent():
    assert MIN_REAL_DURATION_RATIO == 0.70
    print("[ok] 13. the floor is 0.70")


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
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print(f"\nAll {len(TESTS)} real-source duration tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
