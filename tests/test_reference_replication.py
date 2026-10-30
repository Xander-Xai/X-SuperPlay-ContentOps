"""Reference-replication tests: an observation is not a transcript, a plan is not a cut.

Run: python tests/test_reference_replication.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from contentops.workflow import replication  # noqa: E402

ACCOUNT = "x-superplay-1024"
DNA = replication.load_dna(ACCOUNT)


def _seconds(shots):
    return [s["end_s"] - s["start_s"] for s in shots]


def _observed_shots():
    """A 47.2 s film whose beats map onto the 1024 template."""
    return [
        {"index": 1, "start_s": 0.0, "end_s": 3.2, "function": "hook",
         "evidence": "FRAME_VIEWED", "visual": "结论先行 + 数字"},
        {"index": 2, "start_s": 3.2, "end_s": 10.4, "function": "measured_process",
         "evidence": "FRAME_VIEWED", "visual": "终端实录"},
        {"index": 3, "start_s": 10.4, "end_s": 15.9, "function": "measured_process",
         "evidence": "FRAME_VIEWED", "visual": "切到报错行"},
        {"index": 4, "start_s": 15.9, "end_s": 24.4, "function": "failure_or_boundary",
         "evidence": "FRAME_VIEWED", "visual": "红色失败项放大"},
        {"index": 5, "start_s": 24.4, "end_s": 31.2, "function": "measured_process",
         "evidence": "FRAME_VIEWED", "visual": "修复后重跑"},
        {"index": 6, "start_s": 31.2, "end_s": 38.0, "function": "who_its_for",
         "evidence": "FRAME_VIEWED", "visual": "对比卡"},
        {"index": 7, "start_s": 38.0, "end_s": 47.2, "function": "next_validation",
         "evidence": "FRAME_VIEWED", "visual": "下一轮验证"},
    ]


def _make_film(path, duration):
    """A real, decodable film when ffmpeg is here; otherwise bytes to hash.

    The gate probes the reference, so a file that is only bytes would be refused
    for the wrong reason. A tiny 1 fps clip is enough to be decodable and long
    enough to match the record.
    """
    try:
        from process_utils import hidden_run

        proc = hidden_run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i",
             f"color=c=black:s=32x32:r=1:d={duration:.3f}", "-pix_fmt", "yuv420p", str(path)],
            timeout=120)
        if proc.returncode == 0 and path.is_file() and path.stat().st_size > 0:
            return
    except Exception:  # noqa: BLE001
        pass
    path.write_bytes(b"reference film bytes" * 400)


#: Every fixture film of a given length is the same black clip, so its frames are
#: the same bytes. Caching them keeps the suite from cutting 200 identical frames.
_FRAME_CACHE = {}


def _with_frames(project, duration=47.2):
    """Give every observed shot the frame ``extract_frames`` would have cut.

    The bytes come from the fixture film itself, so ``probe_reference`` can
    re-extract and match them; only the accounting is shortcut, never the pixels.
    """
    path = project / replication.OBSERVATION
    document = json.loads(path.read_text(encoding="utf-8"))
    film = project / "reference" / "ref.mp4"
    for position, shot in enumerate(document["shots"]):
        start, end = float(shot["start_s"]), float(shot["end_s"])
        key = (round(float(duration), 3), start, end)
        if key not in _FRAME_CACHE:
            _FRAME_CACHE[key] = replication.cut_frame(film, start, end, duration)
        gray, at = _FRAME_CACHE[key]
        number = shot.get("index") if isinstance(shot.get("index"), int) else position + 1
        gray_rel = (replication.FRAMES / f"{number:03d}.gray").as_posix()
        png_rel = (replication.FRAMES / f"{number:03d}.png").as_posix()
        (project / gray_rel).parent.mkdir(parents=True, exist_ok=True)
        (project / gray_rel).write_bytes(gray)
        (project / png_rel).write_bytes(b"\x89PNG\r\n\x1a\n")
        shot.update(frame=png_rel, frame_gray=gray_rel,
                    frame_sha256=replication._sha256(gray), frame_at_s=at)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")


def _project(where, *, mode="FRAME_VIEWED", shots=None, slug=ACCOUNT,
             duration=47.2):
    project = Path(where) / "proj"
    (project / "reference").mkdir(parents=True)
    (project / "script").mkdir(parents=True)
    # project.yaml is the episode's canonical account identity; the gates read
    # the DNA from here and require the observation to agree with it.
    (project / "project.yaml").write_text(
        f"slug: proj\naccount_slug: {slug}\n", encoding="utf-8")
    film = project / "reference" / "ref.mp4"
    _make_film(film, duration)
    document = {
        "schema": replication.SCHEMA_OBSERVATION,
        "reference_id": "xiaotian-2026-10-27",
        "account_slug": slug,
        "source": {
            "path": "reference/ref.mp4",
            "sha256": replication._file_sha256(film),
            "duration_s": duration,
            "url": "https://example.com/reference",
        },
        "observation": {"mode": mode, "observer": "Founder",
                        "observed_at": "2026-10-29T00:00:00Z"},
        "rights": {"cleared_by": "Founder", "decided_at": "2026-10-29",
                   "scope": "study_only",
                   "basis": "research/video-replication/verification-round-2026-10-28.md"},
        "shots": _observed_shots() if shots is None else shots,
    }
    (project / "reference" / "observation.json").write_text(
        json.dumps(document, ensure_ascii=False), encoding="utf-8")
    if mode == "FRAME_VIEWED":
        _with_frames(project, duration)
    return project


def _render(project, seconds):
    """A film whose pixels move, so the measured freeze gate has something to read.

    A black clip of the right length is exactly the render the contract must
    refuse: correct duration, no cut, no motion.
    """
    final = project / "final" / "easel.mp4"
    final.parent.mkdir(parents=True, exist_ok=True)
    try:
        from process_utils import hidden_run

        hidden_run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                    f"testsrc=size=1080x1920:rate=2:duration={seconds:.3f}",
                    "-pix_fmt", "yuv420p", str(final)], timeout=180)
    except Exception:  # noqa: BLE001
        final.write_bytes(b"not a film")
    return final


def _storyboard(project, shots):
    (project / "script" / "storyboard.json").write_text(
        json.dumps({"size": "1080x1920", "shots": shots}, ensure_ascii=False), encoding="utf-8")


def _conforming_shots():
    """47.2 s at 70/25/5, hooks in 2.5 s, no hold above 10 s, template order."""
    rows = [
        (2.5, "hook", "vector_animation"),
        (8.0, "measured_process", "screen_recording_evidence"),
        (8.0, "measured_process", "screen_recording_evidence"),
        (9.04, "measured_process", "screen_recording_evidence"),
        (8.0, "failure_or_boundary", "screen_recording_evidence"),
        (2.36, "cost_and_limits", "comparison_card"),
        (9.3, "who_its_for", "vector_animation"),
    ]
    return [{"duration": duration, "function": function, "dna_role": role,
             "source_type": "real_recording" if role == "screen_recording_evidence" else "generated",
             "source": f"project://captures/{index:02d}.png"}
            for index, (duration, function, role) in enumerate(rows)]


def _failed(result):
    return [row["id"] for row in result["checks"] if not row["ok"]]


# --- the observation ----------------------------------------------------

def test_an_observation_of_a_missing_file_is_blocked():
    with tempfile.TemporaryDirectory() as td:
        project = _project(td)
        (project / "reference" / "ref.mp4").unlink()
        errors = replication.validate_observation(project)
    assert any("REFERENCE_NOT_PRESENT" in e for e in errors), errors


def test_changed_bytes_are_blocked():
    with tempfile.TemporaryDirectory() as td:
        project = _project(td)
        (project / "reference" / "ref.mp4").write_bytes(b"a different film")
        errors = replication.validate_observation(project)
    assert any("REFERENCE_CHANGED" in e for e in errors), errors


def test_a_transcript_cannot_carry_cut_points():
    shots = [{"index": 1, "start_s": 0.0, "end_s": 3.2, "function": "hook",
              "evidence": "FRAME_VIEWED"}]
    with tempfile.TemporaryDirectory() as td:
        project = _project(td, mode="TRANSCRIPT_ONLY", shots=shots)
        errors = replication.validate_observation(project)
    assert any("transcript-only" in e for e in errors), errors


def test_a_timing_from_a_menu_beats_overlap_is_refused():
    shots = [
        {"index": 1, "start_s": 0.0, "end_s": 4.0, "function": "hook", "evidence": "FRAME_VIEWED"},
        {"index": 2, "start_s": 3.0, "end_s": 9.0, "function": "measured_process",
         "evidence": "FRAME_VIEWED"},
    ]
    with tempfile.TemporaryDirectory() as td:
        project = _project(td, shots=shots, duration=9.0)
        errors = replication.validate_observation(project)
    assert any("before the previous shot ends" in e for e in errors), errors


def test_a_verified_observation_yields_a_budget_that_adds_up():
    with tempfile.TemporaryDirectory() as td:
        project = _project(td)
        plan = replication.derive_plan(project, DNA)

    assert [beat["template_beat"] for beat in plan["beats"]] == DNA["narrative"]["template"]
    total = round(sum(beat["target_s"] for beat in plan["beats"]), 2)
    assert abs(total - plan["pacing"]["target_s"]) < 0.05, (total, plan["pacing"]["target_s"])
    assert plan["pacing"]["target_s"] == 47.2
    assert plan["reuse_reference_media"] is False
    for beat in plan["beats"]:
        assert beat["function"] in replication.FUNCTIONS, beat
        assert beat["visual_duty"] in {"evidence", "abstraction", "comparison"}, beat


def test_a_reference_that_shares_no_beat_is_refused():
    shots = [{"index": i, "start_s": float(i), "end_s": float(i + 1),
              "function": "transition", "evidence": "FRAME_VIEWED"} for i in range(6)]
    with tempfile.TemporaryDirectory() as td:
        project = _project(td, shots=shots, duration=6.0)
        try:
            replication.derive_plan(project, DNA)
        except replication.ReplicationError as exc:
            assert "shares no beat" in str(exc), exc
            return
    raise AssertionError("a reference with no template beat must not derive a plan")


def test_the_budget_is_clamped_into_the_account_window():
    """--target-seconds may move the episode inside the DNA window, not out of it.

    An override of 20 s used to be honoured verbatim, so an episode could be
    planned at a length the account never publishes. The window belongs to the
    account; the flag only picks a point in it.
    """
    shots = _observed_shots()
    with tempfile.TemporaryDirectory() as td:
        project = _project(td, shots=shots, duration=47.2)
        low = replication.derive_plan(project, DNA, target_s=20.0)
        high = replication.derive_plan(project, DNA, target_s=90.0)
        inside = replication.derive_plan(project, DNA, target_s=47.2)
    assert low["pacing"]["target_s"] == 45.0, low["pacing"]
    assert abs(sum(b["target_s"] for b in low["beats"]) - 45.0) < 0.05
    assert high["pacing"]["target_s"] == 60.0, high["pacing"]
    assert abs(sum(b["target_s"] for b in high["beats"]) - 60.0) < 0.05
    assert inside["pacing"]["target_s"] == 47.2, inside["pacing"]


# --- the frames the observer saw -----------------------------------------

def test_a_frame_viewed_shot_without_its_frame_is_refused():
    """A typed shot list is not an observation, so a missing frame is fatal."""
    with tempfile.TemporaryDirectory() as td:
        project = _project(td)
        path = project / replication.OBSERVATION
        document = json.loads(path.read_text(encoding="utf-8"))
        document["shots"][2].pop("frame_gray")
        document["shots"][2].pop("frame_sha256")
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        errors = replication.validate_observation(project)
    assert any("FRAME_MISSING" in e for e in errors), errors


def test_a_frame_that_does_not_come_out_of_the_film_is_refused():
    """Pixels nobody can re-extract from the film are not evidence of watching it."""
    with tempfile.TemporaryDirectory() as td:
        project = _project(td)
        path = project / replication.OBSERVATION
        document = json.loads(path.read_text(encoding="utf-8"))
        shot = document["shots"][3]
        white = b"\xff" * (replication.FRAME_SIZE * replication.FRAME_SIZE)
        (project / shot["frame_gray"]).write_bytes(white)
        shot["frame_sha256"] = replication._sha256(white)
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        # The record is internally consistent — the digest matches the file —
        # and still refused, because the film does not contain that frame.
        assert replication.validate_observation(project) == []
        errors = replication.probe_reference(project)
    assert any("FRAME_NOT_FROM_REFERENCE" in e for e in errors), errors


def test_an_audio_only_reference_is_not_a_film():
    """A decodable audio file whose digest matches proves nothing was watched."""
    with tempfile.TemporaryDirectory() as td:
        project = _project(td)
        audio = project / "reference" / "ref.mp4"
        from process_utils import hidden_run

        hidden_run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=47.2", "-c:a", "aac", str(audio)],
                   timeout=120)
        path = project / replication.OBSERVATION
        document = json.loads(path.read_text(encoding="utf-8"))
        document["source"]["sha256"] = replication._file_sha256(audio)
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        errors = replication.probe_reference(project)
    assert any("REFERENCE_NOT_A_FILM" in e for e in errors), errors


def test_the_entrypoint_cuts_and_reverifies_the_frames():
    with tempfile.TemporaryDirectory() as td:
        project = _project(td)
        path = project / replication.OBSERVATION
        document = json.loads(path.read_text(encoding="utf-8"))
        for shot in document["shots"]:
            for key in ("frame", "frame_gray", "frame_sha256", "frame_at_s"):
                shot.pop(key, None)
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        for stale in (project / replication.FRAMES).glob("*"):
            stale.unlink()
        assert _run([str(project), "--plan"]) == 4, "a plan may not precede the frames"
        assert _run([str(project), "--frames"]) == 0
        framed = json.loads(path.read_text(encoding="utf-8"))["shots"]
        assert all(shot.get("frame_sha256") for shot in framed), framed
        assert (project / framed[0]["frame_gray"]).is_file()
        assert (project / framed[0]["frame"]).stat().st_size > 100, "a viewable frame"
        assert _run([str(project), "--observe"]) == 0
    print("[ok] the entrypoint cuts frames from the film and re-verifies them")


# --- the finished cut ---------------------------------------------------

def test_the_check_refuses_a_cut_with_no_plan():
    with tempfile.TemporaryDirectory() as td:
        project = _project(td)
        _storyboard(project, _conforming_shots())
        result = replication.check(project, DNA, require_render=False)
    assert "plan_present" in _failed(result), _failed(result)


def test_a_cut_that_draws_on_the_reference_is_refused():
    with tempfile.TemporaryDirectory() as td:
        project = _project(td)
        replication.write_plan(project, replication.derive_plan(project, DNA))
        shots = _conforming_shots()
        shots[1]["image"] = "reference/ref.mp4"
        _storyboard(project, shots)
        result = replication.check(project, DNA, require_render=False)
    assert "no_reference_asset_in_cut" in _failed(result), _failed(result)


def test_a_cut_off_the_account_composition_is_refused():
    with tempfile.TemporaryDirectory() as td:
        project = _project(td)
        replication.write_plan(project, replication.derive_plan(project, DNA))
        shots = _conforming_shots()
        shots[-1]["dna_role"] = "comparison_card"
        _storyboard(project, shots)
        result = replication.check(project, DNA, require_render=False)
    failed = _failed(result)
    assert "composition_matches_dna" in failed, failed


def test_a_cut_that_does_not_declare_its_roles_is_refused():
    with tempfile.TemporaryDirectory() as td:
        project = _project(td)
        replication.write_plan(project, replication.derive_plan(project, DNA))
        shots = _conforming_shots()
        for shot in shots:
            shot.pop("dna_role")
        _storyboard(project, shots)
        result = replication.check(project, DNA, require_render=False)
    assert "dna_roles_declared" in _failed(result), _failed(result)


def test_a_cut_shorter_than_the_budget_is_refused():
    with tempfile.TemporaryDirectory() as td:
        project = _project(td)
        replication.write_plan(project, replication.derive_plan(project, DNA))
        shots = _conforming_shots()[:3]
        _storyboard(project, shots)
        result = replication.check(project, DNA, require_render=False)
    assert "duration_within_budget" in _failed(result), _failed(result)


def test_a_hook_longer_than_the_account_allows_is_refused():
    with tempfile.TemporaryDirectory() as td:
        project = _project(td)
        replication.write_plan(project, replication.derive_plan(project, DNA))
        shots = _conforming_shots()
        shots[0]["duration"] = 6.0
        shots[1]["duration"] = shots[1]["duration"] - 3.5
        _storyboard(project, shots)
        result = replication.check(project, DNA, require_render=False)
    assert "hook_within_limit" in _failed(result), _failed(result)


def test_a_conforming_cut_passes_the_contract():
    with tempfile.TemporaryDirectory() as td:
        project = _project(td)
        replication.write_plan(project, replication.derive_plan(project, DNA))
        _storyboard(project, _conforming_shots())
        result = replication.check(project, DNA, require_render=False)
    assert result["overall"] == "PASS", _failed(result)


def test_a_hand_edited_plan_is_refused():
    """The plan carries every threshold, so the plan may not be what gets audited."""
    with tempfile.TemporaryDirectory() as td:
        project = _project(td)
        plan = replication.derive_plan(project, DNA)
        plan["pacing"]["max_hook_s"] = 999
        plan["pacing"]["max_static_hold_s"] = 999
        plan["pacing"]["target_s"] = 60.0
        plan["composition"]["segments"] = [{"role": "vector_animation", "pct": 100}]
        replication.write_plan(project, plan)
        _storyboard(project, _conforming_shots())
        result = replication.check(project, DNA, require_render=False)
    failed = _failed(result)
    assert "plan_matches_derivation" in failed, failed
    assert result["overall"] == "FAIL", result["overall"]


def test_an_evidence_role_on_a_generated_source_is_refused():
    """The role is a label; without the source it is a way to fake the mix."""
    with tempfile.TemporaryDirectory() as td:
        project = _project(td)
        replication.write_plan(project, replication.derive_plan(project, DNA))
        shots = _conforming_shots()
        for shot in shots:
            if shot["dna_role"] == "screen_recording_evidence":
                shot["source_type"] = "generated"
        _storyboard(project, shots)
        result = replication.check(project, DNA, require_render=False)
    failed = _failed(result)
    # The composition still reads 70% "screen recording"; only the source check
    # can see that nothing was recorded.
    assert "dna_role_matches_source" in failed, failed
    assert "composition_matches_dna" not in failed, failed


def test_a_shot_with_no_duration_is_not_a_short_hook():
    """0.0 used to pass "first shot <= 3 s" for a shot that declares nothing."""
    with tempfile.TemporaryDirectory() as td:
        project = _project(td)
        replication.write_plan(project, replication.derive_plan(project, DNA))
        shots = _conforming_shots()
        shots[0].pop("duration")
        _storyboard(project, shots)
        result = replication.check(project, DNA, require_render=False)
    assert "hook_within_limit" in _failed(result), _failed(result)


def test_a_reference_frame_reappearing_in_the_cut_is_refused():
    """A repointed path hides a copy; the pixels do not."""
    import shutil

    from process_utils import hidden_run

    with tempfile.TemporaryDirectory() as td:
        project = _project(td)
        film = project / "reference" / "ref.mp4"
        # A static, structured pattern: every sampled frame equals the stored
        # frames, so a cut that copies the film is caught deterministically.
        result = hidden_run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i",
             "smptebars=size=320x180:rate=10:duration=47.2",
             "-pix_fmt", "yuv420p", str(film)], timeout=180)
        assert result.returncode == 0, result.stderr
        path = project / replication.OBSERVATION
        document = json.loads(path.read_text(encoding="utf-8"))
        document["source"]["sha256"] = replication._file_sha256(film)
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        for stale in (project / replication.FRAMES).glob("*"):
            stale.unlink()
        assert replication.extract_frames(project) == []
        _storyboard(project, _conforming_shots())
        replication.write_plan(project, replication.derive_plan(project, DNA))
        final = project / "final" / "easel.mp4"
        final.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(film, final)
        result = replication.check(project, DNA)
    rows = {row["id"]: row for row in result["checks"]}
    assert not rows["reference_frames_not_in_cut"]["ok"], rows["reference_frames_not_in_cut"]
    assert result["overall"] == "FAIL", result["overall"]


def test_a_cut_is_not_called_clean_when_no_reference_frame_was_captured():
    """An empty comparison is not a clean comparison.

    With no stored frame there is nothing to compare the cut against, so the
    honest outcome is "never measured", not "nothing reappears". Reporting the
    latter would be the same self-certification the rest of this contract
    refuses: a gate passing on evidence it never looked at.
    """
    with tempfile.TemporaryDirectory() as td:
        project = _project(td)
        _storyboard(project, _conforming_shots())
        replication.write_plan(project, replication.derive_plan(project, DNA))
        _render(project, 47.2)
        # The observation still declares its frames, but the files are gone:
        # nothing can be compared, and the check must say so.
        for frame in (project / replication.FRAMES).glob("*.gray"):
            frame.unlink()
        result = replication.check(project, DNA)
    rows = {row["id"]: row for row in result["checks"]}
    row = rows["reference_frames_not_in_cut"]
    assert not row["ok"], row
    assert "never measured" in row["detail"], row["detail"]
    assert result["overall"] == "FAIL", result["overall"]


def test_a_near_uniform_reference_is_reported_rather_than_called_clean():
    """A reference of blank frames cannot be compared, so it is not a pass.

    The distinction matters: captured-but-flat is a limit of the measurement
    (WARN, still shipped to eyes), while never-captured is an unmet contract
    (FAIL). Both refuse to print "nothing reappears", which would be a claim
    about evidence nobody looked at.
    """
    with tempfile.TemporaryDirectory() as td:
        project = _project(td)  # its reference is a black clip: all frames flat
        _storyboard(project, _conforming_shots())
        replication.write_plan(project, replication.derive_plan(project, DNA))
        _render(project, 47.2)
        result = replication.check(project, DNA)
    rows = {row["id"]: row for row in result["checks"]}
    row = rows["reference_frames_not_in_cut"]
    assert not row["ok"], row
    assert row["severity"] == "WARN", row
    assert "not measured" in row["detail"], row["detail"]
    assert result["overall"] == "PASS", _failed(result)


def test_a_reference_with_no_rights_decision_is_refused():
    """Someone must have said what the film may be used for before it is studied."""
    with tempfile.TemporaryDirectory() as td:
        project = _project(td)
        path = project / replication.OBSERVATION
        document = json.loads(path.read_text(encoding="utf-8"))
        document.pop("rights", None)
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        errors = replication.probe_reference(project)
        assert any("RIGHTS_MISSING" in e for e in errors), errors

        document["rights"] = {"cleared_by": "Founder", "decided_at": "2026-10-29",
                              "scope": "whatever the algorithm says"}
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
        errors = replication.probe_reference(project)
    assert any("RIGHTS_SCOPE" in e for e in errors), errors


def test_a_claim_may_not_be_evidenced_by_the_reference_film():
    """The film is a style reference, never a source for what this episode says."""
    with tempfile.TemporaryDirectory() as td:
        project = _project(td)
        replication.write_plan(project, replication.derive_plan(project, DNA))
        _storyboard(project, _conforming_shots())
        document = json.loads((project / replication.OBSERVATION).read_text(encoding="utf-8"))
        (project / "script" / "claim-map.json").write_text(json.dumps({
            "schema": "contentops.claim-map/v1", "map_id": "M-1", "package_id": "proj",
            "claims": [{
                "claim_id": "C-1", "revision": 1, "text": "测试通过。",
                "kind": "runtime", "assertion_about": "cli",
                "support_status": "SUPPORTED", "permission_scope": "internal",
                "limitation": "",
                "evidence": [{"evidence_id": "E-1", "kind": "terminal_recording",
                              "sha256": document["source"]["sha256"],
                              "logical_path": "reference/ref.mp4",
                              "time_range": None, "permission_scope": "internal"}],
                "appearances": [],
            }],
        }, ensure_ascii=False), encoding="utf-8")
        result = replication.check(project, DNA, require_render=False)
    assert "claims_do_not_cite_the_reference" in _failed(result), _failed(result)


def test_a_plan_with_no_render_is_not_a_pass():
    """A conforming storyboard is a plan, not a replication. Nothing shipped."""
    with tempfile.TemporaryDirectory() as td:
        project = _project(td)
        replication.write_plan(project, replication.derive_plan(project, DNA))
        _storyboard(project, _conforming_shots())
        result = replication.check(project, DNA)
    failed = _failed(result)
    assert "render_present" in failed, failed
    assert result["overall"] == "FAIL", result["overall"]


def test_the_shipped_film_is_what_the_budget_is_measured_against():
    """The storyboard says 47.2 s and the film is 2 s. The film is what ships."""
    with tempfile.TemporaryDirectory() as td:
        project = _project(td)
        replication.write_plan(project, replication.derive_plan(project, DNA))
        _storyboard(project, _conforming_shots())
        _render(project, 2.0)
        result = replication.check(project, DNA)
    rows = {row["id"]: row for row in result["checks"]}
    assert rows["render_present"]["ok"], rows["render_present"]
    assert not rows["duration_within_budget"]["ok"], rows["duration_within_budget"]
    assert "rendered film" in rows["duration_within_budget"]["detail"], rows
    assert result["overall"] == "FAIL", result["overall"]


# --- the production gate --------------------------------------------------

def _graded_project(where, shots, seconds=47.2):
    """A project qc_video can grade: a 1080x1920 render, a plan, a storyboard."""
    project = _project(where)
    replication.write_plan(project, replication.derive_plan(project, DNA))
    _storyboard(project, shots)
    _render(project, seconds)
    return project


def test_qc_video_grades_a_replication_against_its_plan():
    """A plan is only worth writing if the production gate reads it.

    Without this the contract could be satisfied by hand and the shipped
    storyboard could drift from the plan that justified its budget.
    """
    import qc_video

    with tempfile.TemporaryDirectory() as td:
        conforming = qc_video.qc(_graded_project(td, _conforming_shots()))
    ids = {row["id"]: row for row in conforming["checks"]}
    assert ids["replication_plan_present"]["ok"], ids["replication_plan_present"]
    assert ids["replication_composition_matches_dna"]["ok"], ids["replication_composition_matches_dna"]

    drifted = [dict(shot) for shot in _conforming_shots()]
    # The two split closing shots together carry the vector share; moving both
    # out is a drift the ±8pp tolerance must refuse, not absorb.
    drifted[-1]["dna_role"] = "generated"
    drifted[-1]["source_type"] = "generated"
    drifted[-2]["dna_role"] = "generated"
    drifted[-2]["source_type"] = "generated"
    with tempfile.TemporaryDirectory() as td:
        result = qc_video.qc(_graded_project(td, drifted))
    ids = {row["id"]: row for row in result["checks"]}
    assert not ids["replication_composition_matches_dna"]["ok"], ids["replication_composition_matches_dna"]
    assert result["overall"] == "FAIL", result["overall"]
    print("[ok] qc_video grades a replication against the plan it was derived from")


def test_qc_video_fails_closed_when_evidence_led_share_is_unmeasured():
    """Unknown evidence share is not a pass for a capture-led account."""
    import qc_video

    shots = [{"function": "measured_process", "dna_role": "screen_recording_evidence"}]
    with tempfile.TemporaryDirectory() as td:
        result = qc_video.qc(_graded_project(td, shots))
    rows = {row["id"]: row for row in result["checks"]}
    assert rows["real_source_ratio"]["value"] is None, rows["real_source_ratio"]
    assert rows["real_source_ratio"]["severity"] == "FAIL", rows["real_source_ratio"]
    assert rows["generated_ratio"]["severity"] == "FAIL", rows["generated_ratio"]
    assert result["overall"] == "FAIL", result["overall"]


def test_a_project_without_a_plan_is_not_graded_as_a_replication():
    """An ordinary episode must not suddenly owe a reference contract."""
    import qc_video

    with tempfile.TemporaryDirectory() as td:
        project = _project(td)
        _storyboard(project, _conforming_shots())
        _render(project, 2.0)
        result = qc_video.qc(project)
    ids = {row["id"] for row in result["checks"]}
    assert not [i for i in ids if i.startswith("replication_")], sorted(ids)
    print("[ok] a project with no plan is not graded as a replication")


def test_qc_video_measures_the_film_not_the_storyboard():
    """A 47.2 s storyboard rendered as 2 s must not pass the replication gate."""
    import qc_video

    with tempfile.TemporaryDirectory() as td:
        result = qc_video.qc(_graded_project(td, _conforming_shots(), seconds=2.0))
    ids = {row["id"]: row for row in result["checks"]}
    assert not ids["replication_duration_within_budget"]["ok"], ids["replication_duration_within_budget"]
    assert ids["replication_render_present"]["ok"], ids["replication_render_present"]
    assert result["overall"] == "FAIL", result["overall"]
    print("[ok] qc_video measures the shipped film, not the storyboard")


def test_a_producer_gate_is_silent_without_a_plan_and_speaks_with_one():
    """Producers call stage_gate: [] for an ordinary episode, errors for a cut off plan."""
    with tempfile.TemporaryDirectory() as td:
        project = _project(td)
        _storyboard(project, _conforming_shots())
        assert replication.stage_gate(project) == [], "no plan must not block a build"
        replication.write_plan(project, replication.derive_plan(project, DNA))
        assert replication.stage_gate(project) == [], "a conforming cut must pass"
        _storyboard(project, _conforming_shots()[:3])
        blocked = replication.stage_gate(project)
        assert blocked, "a cut that left its plan must block the producer"
        assert any("duration_within_budget" in row for row in blocked), blocked
    print("[ok] producers are gated only when a plan exists")


def test_every_producer_runs_the_replication_gate():
    """The contract must bind the builders, not just whoever calls qc_video."""
    for name, needle in (("run_v1.py", "replication_gate(project)"),
                         ("build_evidence_package.py", "replication.stage_gate(")):
        text = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        assert needle in text, f"{name} no longer runs the replication gate"
    print("[ok] run_v1 and the evidence package run the replication gate")


# --- the entrypoint -----------------------------------------------------

def _run(argv):
    import replicate_reference

    saved = sys.argv
    sys.argv = ["replicate_reference.py"] + argv
    try:
        return replicate_reference.main()
    finally:
        sys.argv = saved


def test_the_entrypoint_blocks_before_a_plan_exists():
    with tempfile.TemporaryDirectory() as td:
        project = _project(td)
        _storyboard(project, _conforming_shots())
        assert _run([str(project), "--check"]) == 1
        assert _run([str(project), "--observe"]) == 0
        assert _run([str(project), "--plan"]) == 0
        # A plan with no film behind it is not a pass: the receipt may not claim
        # a replication nothing rendered.
        assert _run([str(project), "--check"]) == 1, "a plan with no render must block"
        receipt = json.loads((project / "receipts" / "replication.json").read_text("utf-8"))
        assert receipt["render_present"] is False, receipt
        _render(project, 47.2)
        assert _run([str(project), "--check"]) == 0
        receipt = json.loads((project / "receipts" / "replication.json").read_text("utf-8"))
        assert receipt["skill_route"]["name"], receipt
        assert receipt["status"] == "PASS", receipt
        assert receipt["render_present"] is True, receipt
        # The check must not erase the derivation it inherits: the plan digest
        # and reference digest are what tie this PASS to a verified observation.
        assert receipt.get("plan_sha256"), receipt
        assert receipt.get("reference_video_sha256"), receipt


def test_the_check_receipt_names_the_plan_it_actually_graded():
    """A receipt's digest must come from the plan file, not from its predecessor.

    Inheriting the previous digest let a PASS name a plan that was no longer on
    disk — re-derived at another target, restored from another branch — and a
    deleted receipt produced a PASS with no plan binding at all.
    """
    with tempfile.TemporaryDirectory() as td:
        project = _project(td)
        _storyboard(project, _conforming_shots())
        assert _run([str(project), "--observe"]) == 0
        assert _run([str(project), "--plan"]) == 0
        _render(project, 47.2)
        # No prior receipt at all: the PASS must still bind itself to the plan.
        (project / "receipts" / "replication.json").unlink()
        assert _run([str(project), "--check"]) == 0
        plan_bytes = (project / replication.PLAN).read_bytes()
        receipt = json.loads((project / "receipts" / "replication.json").read_text("utf-8"))
        assert receipt.get("plan_sha256") == replication._sha256(plan_bytes), receipt
        assert receipt.get("reference_video_sha256"), receipt

        # A stale digest in a prior receipt must be replaced, not carried.
        receipt["plan_sha256"] = "deadbeef"
        receipt["derived_at"] = "2020-01-01T00:00:00Z"
        (project / "receipts" / "replication.json").write_text(
            json.dumps(receipt, ensure_ascii=False), encoding="utf-8")
        assert _run([str(project), "--check"]) == 0
        again = json.loads((project / "receipts" / "replication.json").read_text("utf-8"))
    assert again["plan_sha256"] == replication._sha256(plan_bytes), again
    assert again["derived_at"] == "2020-01-01T00:00:00Z", again


def test_cutting_frames_does_not_destroy_the_derivation_receipt():
    """Frames are a stage, not a replacement for the plan's provenance."""
    with tempfile.TemporaryDirectory() as td:
        project = _project(td)
        assert _run([str(project), "--observe"]) == 0
        assert _run([str(project), "--plan"]) == 0
        derived = json.loads((project / "receipts" / "replication.json").read_text("utf-8"))
        assert _run([str(project), "--frames"]) == 0
        frames = json.loads(
            (project / "receipts" / "replication-frames.json").read_text("utf-8"))
        kept = json.loads((project / "receipts" / "replication.json").read_text("utf-8"))
    assert frames["stage"] == "frames", frames
    assert kept["plan_sha256"] == derived["plan_sha256"], kept
    assert kept["reference_video_sha256"] == derived["reference_video_sha256"], kept


def test_the_entrypoint_refuses_to_plan_without_a_declared_skill_route():
    with tempfile.TemporaryDirectory() as td:
        project = _project(td)
        stripped = dict(DNA)
        stripped["skill_route"] = [row for row in DNA["skill_route"]
                                   if row.get("step") != "script"]
        saved = replication.load_dna
        replication.load_dna = lambda slug, root=None: stripped
        try:
            assert _run([str(project), "--plan"]) == 2
        finally:
            replication.load_dna = saved


def main() -> int:
    tests = (
        test_an_observation_of_a_missing_file_is_blocked,
        test_changed_bytes_are_blocked,
        test_a_transcript_cannot_carry_cut_points,
        test_a_timing_from_a_menu_beats_overlap_is_refused,
        test_a_verified_observation_yields_a_budget_that_adds_up,
        test_a_reference_that_shares_no_beat_is_refused,
        test_the_budget_is_clamped_into_the_account_window,
        test_a_frame_viewed_shot_without_its_frame_is_refused,
        test_a_frame_that_does_not_come_out_of_the_film_is_refused,
        test_an_audio_only_reference_is_not_a_film,
        test_a_reference_with_no_rights_decision_is_refused,
        test_the_entrypoint_cuts_and_reverifies_the_frames,
        test_the_check_refuses_a_cut_with_no_plan,
        test_a_cut_that_draws_on_the_reference_is_refused,
        test_a_cut_off_the_account_composition_is_refused,
        test_a_cut_that_does_not_declare_its_roles_is_refused,
        test_a_cut_shorter_than_the_budget_is_refused,
        test_a_hook_longer_than_the_account_allows_is_refused,
        test_a_conforming_cut_passes_the_contract,
        test_a_hand_edited_plan_is_refused,
        test_an_evidence_role_on_a_generated_source_is_refused,
        test_a_shot_with_no_duration_is_not_a_short_hook,
        test_a_reference_frame_reappearing_in_the_cut_is_refused,
        test_a_cut_is_not_called_clean_when_no_reference_frame_was_captured,
        test_a_claim_may_not_be_evidenced_by_the_reference_film,
        test_a_plan_with_no_render_is_not_a_pass,
        test_the_shipped_film_is_what_the_budget_is_measured_against,
        test_qc_video_grades_a_replication_against_its_plan,
        test_qc_video_fails_closed_when_evidence_led_share_is_unmeasured,
        test_a_project_without_a_plan_is_not_graded_as_a_replication,
        test_qc_video_measures_the_film_not_the_storyboard,
        test_a_producer_gate_is_silent_without_a_plan_and_speaks_with_one,
        test_every_producer_runs_the_replication_gate,
        test_the_entrypoint_blocks_before_a_plan_exists,
        test_the_check_receipt_names_the_plan_it_actually_graded,
        test_cutting_frames_does_not_destroy_the_derivation_receipt,
        test_the_entrypoint_refuses_to_plan_without_a_declared_skill_route,
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
    print("\nAll reference-replication tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
