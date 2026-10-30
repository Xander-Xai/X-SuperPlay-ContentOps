"""Target-aware evidence QC tests.

Run: python tests/test_evidence_cut_qc.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from contentops.media.cut_qc import MIN_REAL_SOURCE_RATIO, _looser, qc_cut, source_shares  # noqa: E402
from process_utils import hidden_run  # noqa: E402

SHA = "a" * 64


def _clip(path: Path, width=320, height=180, seconds=4.5) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    result = hidden_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc=size={width}x{height}:rate=15:duration={seconds}",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(path),
    ], timeout=120)
    assert result.returncode == 0 and path.exists(), result.stderr


def _sha(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _placement(pid, start, end, asset, claims=None, bearing=True):
    return {
        "placement_id": pid, "start_ms": start, "end_ms": end,
        "asset_id": asset, "source_time_range": "00:00.000-00:04.500",
        "crop": {"x": 0, "y": 0, "width": 320, "height": 180,
                 "source_width": 320, "source_height": 180},
        "reading_class": "reading", "semantic_progress": "shows the result",
        "claim_ids": claims or [], "caption_cue_ids": [],
        "claim_bearing": bearing, "context_first": False,
        "context_placement_id": None, "transition": "cut",
    }


def make_project(td: Path, *, generated: bool = False, width=320, height=180,
                 max_hold=5000) -> Path:
    project = td / "project"
    clip = project / "work" / "raw" / "cap.mp4"
    _clip(clip, width=width, height=height)
    final = project / "final" / "easel.mp4"
    final.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(clip, final)

    assets = {
        "A-REAL": {"kind": "recording",
                   "path": "project://work/raw/cap.mp4", "sha256": _sha(clip)},
    }
    placements = [_placement("P-1", 0, 2000 if generated else 4500,
                             "A-REAL", ["C-1"])]
    if generated:
        assets["A-GEN"] = {"kind": "generated_video",
                           "path": "project://work/raw/cap.mp4",
                           "sha256": _sha(clip)}
        placements.append(_placement("P-2", 2000, 4000, "A-GEN", [], bearing=False))
    (project / "script").mkdir(parents=True, exist_ok=True)
    (project / "script" / "assets.json").write_text(
        json.dumps({"schema": "contentops.asset-map/v1", "assets": assets}), encoding="utf-8")
    (project / "script" / "cut-plan.json").write_text(json.dumps({
        "schema": "contentops.cut-plan/v1", "package_id": "qc-fixture",
        "target": {"width": width, "height": height,
                   "duration_ms_range": [4000, 5000],
                   **({"max_visual_hold_ms": max_hold} if max_hold else {}),
                   "caption_safe_area": {"x": 10, "y": 120, "width": 300, "height": 50}},
        "placements": placements,
    }), encoding="utf-8")
    (project / "script" / "claim-map.json").write_text(json.dumps({
        "schema": "contentops.claim-map/v1", "map_id": "MAP-QC", "package_id": "qc-fixture",
        "claims": [{
            "claim_id": "C-1", "revision": 1, "text": "测试通过。",
            "kind": "runtime", "assertion_about": "cli",
            "support_status": "SUPPORTED", "permission_scope": "internal",
            "limitation": "",
            "evidence": [{"evidence_id": "E-1", "kind": "terminal_recording",
                          "sha256": _sha(clip), "logical_path": "project://work/raw/cap.mp4",
                          "time_range": None, "permission_scope": "internal"}],
            "appearances": [
                {"surface": "narration", "text": "测试通过。", "time_range": "00:00.000-00:02.000"},
                {"surface": "caption", "text": "测试通过。", "time_range": "00:00.000-00:02.000"}],
        }],
    }), encoding="utf-8")
    captions = project / "assets" / "captions" / "cut.srt"
    captions.parent.mkdir(parents=True, exist_ok=True)
    captions.write_text("1\n00:00:00,000 --> 00:00:02,000\n测试通过。\n", encoding="utf-8")
    cover = project / "assets" / "covers" / "cover.png"
    cover.parent.mkdir(parents=True, exist_ok=True)
    hidden_run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", f"color=c=0xF2EDE4:s={width}x{height}",
                "-frames:v", "1", str(cover)], timeout=60)
    (project / "receipts").mkdir(parents=True, exist_ok=True)
    (project / "receipts" / "cover.json").write_text(json.dumps({
        "schema": "contentops.cover-receipt/v1",
        "png": {"path": "project://assets/covers/cover.png", "sha256": _sha(cover)},
    }), encoding="utf-8")
    return project


def test_overlapping_intervals_count_once():
    shares = source_shares(
        SimpleNamespace(placements=[
            SimpleNamespace(asset_id="R1", start_ms=0, end_ms=3000),
            SimpleNamespace(asset_id="R1", start_ms=1000, end_ms=5000),
        ]),
        {"R1": {"kind": "recording"}},
    )
    assert abs(shares["real_s"] - 5.0) < 0.01, shares
    print("[ok] 1. overlapping real intervals are counted once")


def test_duration_weighting_defeats_the_shot_count_trick():
    shares = source_shares(
        SimpleNamespace(placements=[
            SimpleNamespace(asset_id="R1", start_ms=0, end_ms=2000),
            SimpleNamespace(asset_id="G1", start_ms=2000, end_ms=12000),
        ]),
        {"R1": {"kind": "recording"}, "G1": {"kind": "generated_video"}},
    )
    assert shares["real_ratio"] < MIN_REAL_SOURCE_RATIO, shares
    assert shares["generated_ratio"] > 0.10, shares
    print("[ok] 2. 2 s real + 10 s generated fails on duration, not shot count")


def test_a_shot_level_asset_swap_is_attributed_to_the_shot():
    """A placement that switches to a generated view is not a recording for it.

    Counting by placement credited the whole interval to the recording, so a cut
    could hide generated seconds behind a real first frame. The renderer honours
    the swap, so the gate has to as well.
    """
    shares = source_shares(
        SimpleNamespace(placements=[
            SimpleNamespace(asset_id="R1", start_ms=0, end_ms=4000, shots=[
                SimpleNamespace(asset_id=None, start_ms=0, end_ms=1000),
                SimpleNamespace(asset_id="G1", start_ms=1000, end_ms=4000),
            ]),
        ]),
        {"R1": {"kind": "recording"}, "G1": {"kind": "generated_video"}},
    )
    assert abs(shares["real_s"] - 1.0) < 0.01, shares
    assert abs(shares["generated_s"] - 3.0) < 0.01, shares
    print("[ok] 2b. a generated shot inside a recording placement is counted as generated")


def test_a_valid_target_passes_and_a_wrong_size_fails():
    with tempfile.TemporaryDirectory() as td:
        project = make_project(Path(td))
        report = qc_cut(project)
        assert report["overall"] == "PASS", report["checks"]

        # Replace the render with a different size; the target, not a constant,
        # decides.
        _clip(project / "final" / "easel.mp4", width=640, height=360)
        report = qc_cut(project)
        bad = [c for c in report["checks"] if c["id"] == "resolution"]
        assert bad and not bad[0]["ok"], bad
        assert report["overall"] == "FAIL"
    print("[ok] 3. target dimensions are enforced from the CutPlan")


def test_a_long_generated_interval_fails_the_cut():
    with tempfile.TemporaryDirectory() as td:
        project = make_project(Path(td), generated=True)
        report = qc_cut(project)
        gen = [c for c in report["checks"] if c["id"] == "generated_ratio"][0]
        assert not gen["ok"], gen
        assert report["overall"] == "FAIL"
    print("[ok] 4. a generated interval above 10% fails the cut")


def test_missing_captions_fail_closed():
    with tempfile.TemporaryDirectory() as td:
        project = make_project(Path(td))
        (project / "assets" / "captions" / "cut.srt").unlink()
        report = qc_cut(project)
        captions = [c for c in report["checks"] if c["id"] == "captions_present"][0]
        assert not captions["ok"], captions
        assert report["overall"] == "FAIL"
    print("[ok] 5. missing captions fail the gate")


def test_a_long_undeclared_static_view_fails():
    with tempfile.TemporaryDirectory() as td:
        project = make_project(Path(td), max_hold=None)  # default 2000ms
        report = qc_cut(project)
        views = [c for c in report["checks"] if c["id"] == "views_declared"][0]
        assert not views["ok"], views
        assert report["overall"] == "FAIL"
    print("[ok] 6. a placement over the hold limit must declare its views")


def test_a_frozen_render_fails_the_static_hold_gate():
    with tempfile.TemporaryDirectory() as td:
        project = make_project(Path(td), max_hold=2000)
        plan_path = project / "script" / "cut-plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        plan["placements"] = [
            _placement("P-1", 0, 2000, "A-REAL", ["C-1"]),
            _placement("P-1b", 2000, 4000, "A-REAL", ["C-1"]),
        ]
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        # Two 2 s placements satisfy the structure, but the render itself is one
        # frozen image for four seconds: the measured gate must still catch it.
        frozen = project / "final" / "easel.mp4"
        result = hidden_run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=0x101010:s=320x180:r=15:d=4",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(frozen),
        ], timeout=120)
        assert result.returncode == 0, result.stderr
        report = qc_cut(project)
        hold = [c for c in report["checks"] if c["id"] == "static_hold_within_limit"][0]
        assert not hold["ok"], hold
        assert report["overall"] == "FAIL"
    print("[ok] 7. a frozen render fails even when the plan declares its views")


def _rewrite(project: Path, **target) -> None:
    plan_path = project / "script" / "cut-plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    plan["target"].update(target)
    plan_path.write_text(json.dumps(plan), encoding="utf-8")


def test_a_no_recording_account_refuses_a_recording_asset():
    with tempfile.TemporaryDirectory() as td:
        project = make_project(Path(td), max_hold=5000)
        _rewrite(project, manual_recording="FORBIDDEN", evidence_mode="EXPLANATORY")
        report = qc_cut(project)
        check = [c for c in report["checks"]
                 if c["id"] == "manual_recording_forbidden"][0]
        assert not check["ok"], check
        assert report["overall"] == "FAIL"
    print("[ok] 8. a no-recording account refuses a recording asset")


def test_composition_drift_fails_the_declared_ratio():
    with tempfile.TemporaryDirectory() as td:
        project = make_project(Path(td), max_hold=5000)
        assets_path = project / "script" / "assets.json"
        assets = json.loads(assets_path.read_text(encoding="utf-8"))
        assets["assets"]["A-REAL"]["role"] = "vector_animation"
        assets_path.write_text(json.dumps(assets), encoding="utf-8")
        _rewrite(project, evidence_mode="EXPLANATORY", composition=[
            {"role": "vector_animation", "pct": 50},
            {"role": "code_snapshot", "pct": 50},
        ])
        report = qc_cut(project)
        check = [c for c in report["checks"] if c["id"] == "composition_ratio"][0]
        assert not check["ok"], check
        assert report["overall"] == "FAIL"
    print("[ok] 9. a composition outside the declared ratio fails")


def _account(project: Path, slug: str) -> None:
    (project / "project.yaml").write_text(f"slug: qc-fixture\naccount_slug: {slug}\n",
                                          encoding="utf-8")


def test_an_episode_cannot_switch_off_its_accounts_evidence_mode():
    """target.evidence_mode=EXPLANATORY retired the very ratio gate it would fail."""
    with tempfile.TemporaryDirectory() as td:
        project = make_project(Path(td), generated=True)  # 50% of the cut is generated
        _account(project, "x-superplay-1024")
        _rewrite(project, evidence_mode="EXPLANATORY")
        report = qc_cut(project)
    rows = {c["id"]: c for c in report["checks"]}
    assert not rows["account_policy"]["ok"], rows["account_policy"]
    # The account's EVIDENCE_LED mode governs again: the 50%-real cut is refused
    # by the floor, where EXPLANATORY had made the same number INFO.
    assert rows["real_source_ratio"]["severity"] == "FAIL", rows["real_source_ratio"]
    assert report["overall"] == "FAIL", report["overall"]
    print("[ok] 10. an episode cannot switch off the account's evidence mode")


def test_an_episode_cannot_allow_recordings_its_account_forbids():
    """manual_recording=ALLOWED used to cancel the ban the account declares."""
    with tempfile.TemporaryDirectory() as td:
        project = make_project(Path(td), max_hold=5000)  # a recording asset is used
        _account(project, "x-superplay-future-intelligence")
        _rewrite(project, manual_recording="ALLOWED")
        report = qc_cut(project)
    rows = {c["id"]: c for c in report["checks"]}
    assert not rows["account_policy"]["ok"], rows["account_policy"]
    assert not rows["manual_recording_forbidden"]["ok"], rows["manual_recording_forbidden"]
    assert report["overall"] == "FAIL"
    print("[ok] 11. an episode cannot allow recordings its account forbids")


def test_an_evidence_role_on_a_generated_asset_is_refused():
    """A role is a label; without a source it buys evidence the cut never shot."""
    with tempfile.TemporaryDirectory() as td:
        project = make_project(Path(td), max_hold=5000)
        assets_path = project / "script" / "assets.json"
        assets = json.loads(assets_path.read_text(encoding="utf-8"))
        assets["assets"]["A-GEN"] = {
            "kind": "generated_video", "role": "screen_recording_evidence",
            "path": "project://work/raw/cap.mp4", "sha256": _sha(
                project / "work" / "raw" / "cap.mp4"),
        }
        assets_path.write_text(json.dumps(assets), encoding="utf-8")
        report = qc_cut(project)
    rows = {c["id"]: c for c in report["checks"]}
    assert not rows["role_matches_source"]["ok"], rows["role_matches_source"]
    assert report["overall"] == "FAIL"
    print("[ok] 12. an evidence role on a generated asset is refused")


def test_a_cut_outside_the_accounts_duration_window_fails():
    """A length window an episode derives from its own output is not a contract.

    ``audio_first_plan`` sizes ``target.duration_ms_range`` from the narration it has
    just measured, so a cut declares the window it happens to occupy and satisfies its
    own duration check. A 25-second Future Intelligence prototype therefore passed
    while the account's DNA asks for 90--120 s. The account's window is graded against
    the measured media, and the episode's declaration cannot satisfy it.
    """
    with tempfile.TemporaryDirectory() as td:
        project = make_project(Path(td), max_hold=5000)  # 4.5 s of real capture
        rows = {c["id"]: c for c in qc_cut(project)["checks"]}
        assert "account_duration" not in rows, rows.get("account_duration")
        assert rows["duration"]["ok"], rows["duration"]

        for slug, span in (("x-superplay-1024", "45-60"),
                           ("x-superplay-future-intelligence", "90-120")):
            _account(project, slug)
            report = qc_cut(project)
            rows = {c["id"]: c for c in report["checks"]}
            assert not rows["account_duration"]["ok"], rows["account_duration"]
            assert rows["account_duration"]["severity"] == "FAIL"
            assert span in rows["account_duration"]["detail"], rows["account_duration"]
            # The episode's own window still matches: this is not a duration bug.
            assert rows["duration"]["ok"], rows["duration"]
            assert report["overall"] == "FAIL"
    print("[ok] 13b. a cut outside its account's duration window fails")


def test_an_episode_may_be_stricter_than_its_account():
    """The account is a floor, not a ceiling: a stricter episode keeps its rule.

    Copying the account's value over the episode's used to discard a deliberate
    ban, so an episode that forbade recordings it could still shoot was graded
    as if it allowed them.
    """
    with tempfile.TemporaryDirectory() as td:
        project = make_project(Path(td), max_hold=5000)  # the cut uses a recording
        _account(project, "x-superplay-1024")  # the account allows cropped recordings
        _rewrite(project, manual_recording="FORBIDDEN")
        report = qc_cut(project)
    rows = {c["id"]: c for c in report["checks"]}
    assert rows["account_policy"]["ok"], rows["account_policy"]
    # The episode's own ban binds, and its own cut breaks it.
    assert not rows["manual_recording_forbidden"]["ok"], rows["manual_recording_forbidden"]
    assert report["overall"] == "FAIL"
    print("[ok] 13. an episode may be stricter than its account")


def test_a_small_surface_the_dna_never_names_is_a_residual_not_a_violation():
    """A 4% title card used to fail as "has no DNA budget" on its own.

    The DNA names the surfaces it pays for and leaves the rest to the tolerance
    its budgets already carry. Anything inside that tolerance is residual.
    """
    with tempfile.TemporaryDirectory() as td:
        project = make_project(Path(td), max_hold=5000)
        assets_path = project / "script" / "assets.json"
        assets = json.loads(assets_path.read_text(encoding="utf-8"))
        clip_sha = _sha(project / "work" / "raw" / "cap.mp4")
        assets["assets"]["A-GEN"] = {"kind": "generated_video",
                                     "path": "project://work/raw/cap.mp4",
                                     "sha256": clip_sha}
        assets["assets"]["A-CARD"] = {"kind": "card", "role": "comparison_card"}
        assets["assets"]["A-TITLE"] = {"kind": "card", "role": "title_card"}
        assets_path.write_text(json.dumps(assets), encoding="utf-8")
        plan_path = project / "script" / "cut-plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        # 70 / 23 / 3 / 4 of 4 s: the title card is the surface 1024's DNA never names.
        plan["placements"] = [
            _placement("P-1", 0, 2800, "A-REAL", ["C-1"]),
            _placement("P-2", 2800, 3720, "A-GEN", [], bearing=False),
            _placement("P-3", 3720, 3840, "A-CARD", [], bearing=False),
            _placement("P-4", 3840, 4000, "A-TITLE", [], bearing=False),
        ]
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        _account(project, "x-superplay-1024")
        report = qc_cut(project)
    rows = {c["id"]: c for c in report["checks"]}
    assert rows["account_composition"]["ok"], rows["account_composition"]
    assert "has no DNA budget" not in rows["account_composition"]["detail"]
    failing = [c for c in report["checks"] if not c["ok"] and c["severity"] == "FAIL"]
    # This four-second synthetic cut is far below 1024's declared 45--60 s window.
    # That finding is real and must appear; the other gates are what this test is about.
    assert [c["id"] for c in failing] == ["account_duration"], failing
    print("[ok] 14. a small unlisted surface is residual, not a violation")


def test_the_generated_ceiling_follows_the_accounts_composition_budget():
    """1024's DNA spends 30% of the frame on non-captures; a flat 10% refused it.

    Without a DNA the flat floor still applies, so the loosening is scoped to an
    account that actually declares the budget.
    """
    with tempfile.TemporaryDirectory() as td:
        project = make_project(Path(td), max_hold=5000)
        plan_path = project / "script" / "cut-plan.json"
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        clip_sha = _sha(project / "work" / "raw" / "cap.mp4")
        assets_path = project / "script" / "assets.json"
        assets = json.loads(assets_path.read_text(encoding="utf-8"))
        assets["assets"]["A-GEN"] = {"kind": "generated_video",
                                     "path": "project://work/raw/cap.mp4",
                                     "sha256": clip_sha}
        assets_path.write_text(json.dumps(assets), encoding="utf-8")
        plan["placements"] = [
            _placement("P-1", 0, 3000, "A-REAL", ["C-1"]),
            _placement("P-2", 3000, 4000, "A-GEN", [], bearing=False),
        ]
        plan_path.write_text(json.dumps(plan), encoding="utf-8")

        # No account: the flat 10% cap refuses 25% generated time.
        rows = {c["id"]: c for c in qc_cut(project)["checks"]}
        assert not rows["generated_ratio"]["ok"], rows["generated_ratio"]
        assert "max 10%" in rows["generated_ratio"]["detail"], rows["generated_ratio"]

        # 1024 declares 70/25/5, so its own budget allows the 25%.
        _account(project, "x-superplay-1024")
        report = qc_cut(project)
        rows = {c["id"]: c for c in report["checks"]}
        assert rows["generated_ratio"]["ok"], rows["generated_ratio"]
        assert "max 30%" in rows["generated_ratio"]["detail"], rows["generated_ratio"]
        # The only finding left is the four-second cut missing 1024's 45--60 s window.
        failing = [c["id"] for c in report["checks"] if not c["ok"]]
        assert failing == ["account_duration"], failing
    print("[ok] 15. the generated ceiling follows the account's own budget")


def test_evidence_modes_cannot_replace_incomparable_guards():
    assert _looser("EVIDENCE_LED", "CLAIM_LED", "evidence_mode")
    assert _looser("CLAIM_LED", "EVIDENCE_LED", "evidence_mode")
    assert not _looser("EVIDENCE_LED", "EVIDENCE_LED", "evidence_mode")


def main() -> int:
    tests = (
        test_evidence_modes_cannot_replace_incomparable_guards,
        test_overlapping_intervals_count_once,
        test_duration_weighting_defeats_the_shot_count_trick,
        test_a_shot_level_asset_swap_is_attributed_to_the_shot,
        test_a_valid_target_passes_and_a_wrong_size_fails,
        test_a_long_generated_interval_fails_the_cut,
        test_missing_captions_fail_closed,
        test_a_long_undeclared_static_view_fails,
        test_a_frozen_render_fails_the_static_hold_gate,
        test_a_no_recording_account_refuses_a_recording_asset,
        test_composition_drift_fails_the_declared_ratio,
        test_an_episode_cannot_switch_off_its_accounts_evidence_mode,
        test_an_episode_cannot_allow_recordings_its_account_forbids,
        test_an_evidence_role_on_a_generated_asset_is_refused,
        test_a_cut_outside_the_accounts_duration_window_fails,
        test_an_episode_may_be_stricter_than_its_account,
        test_a_small_surface_the_dna_never_names_is_a_residual_not_a_violation,
        test_the_generated_ceiling_follows_the_accounts_composition_budget,
    )
    failures = []
    for fn in tests:
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
    print(f"\nAll {len(tests)} cut-QC tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
