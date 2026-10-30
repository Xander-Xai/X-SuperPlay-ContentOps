"""The copy gate: a film does not render from copy nobody reviewed.

Two properties matter more than the happy path:

- a review must survive the pipeline's own writes. ``run_easel`` rewrites
  ``storyboard.json`` with ``narration``/``subtitle``/``runtime``; if those counted,
  every build would invalidate the review that authorised it.
- a review must not survive a copy change. Editing the master, a caption line or
  a shot's wording has to invalidate it.

Run: python tests/test_copy_review.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.workflow import copy_review  # noqa: E402


def _project(base: Path) -> Path:
    script = base / "script"
    script.mkdir(parents=True)
    (script / "master.md").write_text("# 文案\n第一句。\n", encoding="utf-8")
    (script / "1024.srt").write_text("1\n00:00:00,000 --> 00:00:02,000\n第一句。\n",
                                     encoding="utf-8")
    (script / "storyboard.json").write_text(json.dumps({
        "size": "1080x1920",
        "narration": None,
        "subtitle": None,
        "shots": [{"unit": "U01", "narration": "第一句。", "image": "a.png",
                   "duration": 2.0}],
    }, ensure_ascii=False), encoding="utf-8")
    return base


def _approve(project: Path) -> dict:
    return copy_review.decide(project, status_value="APPROVED", reviewer="Founder",
                              opinion="钩子够硬，第二句删掉", reviewed_at="2026-10-29T00:00:00Z")


def test_no_review_blocks() -> None:
    with tempfile.TemporaryDirectory() as td:
        project = _project(Path(td))
        gate = copy_review.status(project)
        assert gate["ok"] is False and gate["state"] == "NOT_REVIEWED", gate
        try:
            copy_review.require_approved(project)
        except copy_review.CopyReviewRequired as exc:
            assert "NOT_REVIEWED" in exc.reason
            assert "copy_review.py" in exc.remedy
        else:
            raise AssertionError("an unreviewed copy was allowed through")


def test_approval_unlocks() -> None:
    with tempfile.TemporaryDirectory() as td:
        project = _project(Path(td))
        _approve(project)
        gate = copy_review.require_approved(project)
        assert gate["state"] == "APPROVED" and gate["reviewer"] == "Founder"


def test_build_metadata_does_not_invalidate() -> None:
    with tempfile.TemporaryDirectory() as td:
        project = _project(Path(td))
        _approve(project)
        board = project / "script" / "storyboard.json"
        document = json.loads(board.read_text(encoding="utf-8"))
        document.update({"narration": "projects/x/assets/voice/n.wav",
                         "subtitle": "projects/x/script/1024.srt",
                         "engine": "easel", "runtime": {"commit": "abc"}})
        board.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        assert copy_review.status(project)["ok"] is True, \
            "the pipeline's own storyboard writes invalidated the review"


def test_copy_change_invalidates() -> None:
    for mutate in ("master", "srt", "shot"):
        with tempfile.TemporaryDirectory() as td:
            project = _project(Path(td))
            _approve(project)
            if mutate == "master":
                (project / "script" / "master.md").write_text("# 文案\n改过的句子。\n",
                                                              encoding="utf-8")
            elif mutate == "srt":
                (project / "script" / "1024.srt").write_text(
                    "1\n00:00:00,000 --> 00:00:02,500\n改过的字幕。\n", encoding="utf-8")
            else:
                board = project / "script" / "storyboard.json"
                document = json.loads(board.read_text(encoding="utf-8"))
                document["shots"][0]["narration"] = "改过的分镜口播"
                board.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
            gate = copy_review.status(project)
            assert gate["ok"] is False and gate["state"] == "STALE", (mutate, gate)


def test_changes_requested_blocks() -> None:
    with tempfile.TemporaryDirectory() as td:
        project = _project(Path(td))
        copy_review.decide(project, status_value="CHANGES_REQUESTED", reviewer="Founder",
                           opinion="开场太慢，重写前三句", reviewed_at="2026-10-29T00:00:00Z")
        gate = copy_review.status(project)
        assert gate["ok"] is False and gate["state"] == "CHANGES_REQUESTED", gate
        assert "开场太慢" in gate["opinion"]


def test_review_needs_a_reviewer_and_an_opinion() -> None:
    with tempfile.TemporaryDirectory() as td:
        project = _project(Path(td))
        for kwargs in ({"reviewer": "", "opinion": "ok"},
                       {"reviewer": "Founder", "opinion": "   "}):
            try:
                copy_review.decide(project, status_value="APPROVED",
                                   reviewed_at="2026-10-29T00:00:00Z", **kwargs)
            except ValueError:
                continue
            raise AssertionError(f"accepted an incomplete review: {kwargs}")


def test_run_v1_gate_reports_blocked() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    from run_v1 import copy_gate
    with tempfile.TemporaryDirectory() as td:
        project = _project(Path(td))
        result = copy_gate(project, engine="easel")
        assert result and result["status"] == "BLOCKED", result
        assert result["stage"] == "copy_review"
        _approve(project)
        assert copy_gate(project, engine="easel") is None


def test_both_accounts_are_gated() -> None:
    """The rule is per account: both ship only with their own review."""
    states = {}
    for slug in ("x-superplay-1024", "x-superplay-future-intelligence"):
        project = ROOT / "projects" / slug
        if not (project / "script").is_dir():
            continue
        states[slug] = copy_review.status(project)["ok"]
    assert states, "no account project found to check"
    print(f"      current gate: {states}")


def test_semantic_shot_fields_invalidate_review() -> None:
    for field in ("function", "dna_role"):
        with tempfile.TemporaryDirectory() as td:
            project = _project(Path(td))
            _approve(project)
            board = project / "script" / "storyboard.json"
            document = json.loads(board.read_text(encoding="utf-8"))
            document["shots"][0][field] = "changed-semantic-label"
            board.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
            assert copy_review.status(project)["state"] == "STALE", field


def test_evidence_copy_inputs_invalidate_review() -> None:
    for name in ("lines.json", "claim-map.json"):
        with tempfile.TemporaryDirectory() as td:
            project = _project(Path(td))
            path = project / "script" / name
            path.write_text('{"text":"第一句。"}', encoding="utf-8")
            _approve(project)
            path.write_text('{"text":"另一句。"}', encoding="utf-8")
            assert copy_review.status(project)["state"] == "STALE", name


def test_evidence_producers_block_before_reading_inputs_or_synthesis() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_evidence_cut
    import build_evidence_package
    import audio_first_plan

    with tempfile.TemporaryDirectory() as td:
        project = Path(td)
        try:
            build_evidence_cut.build(project)
        except copy_review.CopyReviewRequired as exc:
            assert "NOT_REVIEWED" in exc.reason, exc.reason
        else:
            raise AssertionError("evidence cut reached inputs without copy approval")
        assert _audio_first(project, audio_first_plan) == 4
        assert _audio_first(project, build_evidence_package) == 4


def _audio_first(project: Path, module) -> int:
    previous = sys.argv
    try:
        sys.argv = ["audio_first_plan.py", str(project)]
        return module.main()
    finally:
        sys.argv = previous


def test_no_producer_wires_a_second_gate() -> None:
    """One enforced gate, deliberately.

    The ten-stage contract in ``contentops.workflow.contract`` names canonical
    artefacts (``02_script/script.json``) that no project has, and it was never
    enforced. Wiring it now would put a second, competing approval in front of
    every build. The decision of 2026-10-29 is that the copy review is the single
    enforced gate; this test fails if a producer starts importing the other one,
    so the choice is visible instead of quietly reversed.
    """
    producers = ["run_v1.py", "build_code_animation_sample.py",
                 "build_motion_film.py", "build_account_variants.py"]
    offenders = []
    for name in producers:
        text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        for forbidden in ("workflow.gate", "workflow.contract", "workflow_gate"):
            if forbidden in text:
                # copy_review is the intended gate; only other workflow imports count
                offenders.append((name, forbidden))
    assert not offenders, f"a second gate was wired into a producer: {offenders}"


def main() -> int:
    failures = 0
    names = sorted(n for n in dir(sys.modules[__name__]) if n.startswith("test_"))
    for name in names:
        try:
            globals()[name]()
            print(f"PASS {name}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {name}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"ERROR {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(names)} tests, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
