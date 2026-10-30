"""Regression tests for full-film huashu composition.

Run: python tests/test_code_animation_composition.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_code_animation_sample import _storyboard_shots  # noqa: E402
from package_code_animation_sample import _runtime_receipt  # noqa: E402


SEGMENTS = [
    {"type": "beat", "path": Path("clip-a.mp4"), "duration": 2.5},
    {"type": "beat", "path": Path("clip-b.mp4"), "duration": 3.0},
]


def test_composer_rechecks_copy_approval_before_final_assembly():
    builder = _builder()
    assert hasattr(builder, "_require_unchanged_copy_approval")
    class Review:
        class CopyReviewRequired(Exception):
            pass
        @staticmethod
        def require_approved(project):
            return {"copy_sha256": "new"}
    try:
        builder._require_unchanged_copy_approval(Review, Path("project"), "old")
    except Review.CopyReviewRequired as exc:
        assert "changed" in str(exc).lower()
    else:
        raise AssertionError("copy changed after approval was allowed to compose")


def test_full_film_is_the_only_visual_shot():
    """A huashu eras render must not be re-cut into hard-joined beat clips."""
    film = Path("whole-film.mp4")
    shots = _storyboard_shots(SEGMENTS, film)
    assert shots == [{"video": str(film), "duration": 5.5}], shots


def test_beat_clips_remain_the_explicit_fallback():
    shots = _storyboard_shots(SEGMENTS, None)
    assert shots == [
        {"video": "clip-a.mp4", "duration": 2.5},
        {"video": "clip-b.mp4", "duration": 3.0},
    ], shots


def test_runtime_receipt_uses_the_measured_film_duration():
    receipt = _runtime_receipt("easel-fi-what-is-agent", {"timeline": {"total_s": 37.9}})
    assert "37.9 s" in receipt, receipt
    assert "20 s below" not in receipt, receipt


def _builder():
    import importlib.util

    path = ROOT / "scripts" / "build_code_animation_sample.py"
    spec = importlib.util.spec_from_file_location("build_code_animation_presenter", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PRESENTER = {"text": "这条视频，只讲一个问题。",
             "path": "project://assets/voice/presenter-opening.wav",
             "duration_s": 1.91, "voice": "minimax_h3_ref2va"}
VOICE_DOC = {"lines": [{"line": 1, "text": "一", "path": "project://a.wav",
                        "duration_s": 2.0}]}


def test_presenter_belongs_only_to_the_eras_variant():
    """The baseline keeps its twelve-line manifest; the opening is eras-only."""
    builder = _builder()
    assert sorted(builder._voice_lines(VOICE_DOC, "easel")) == [1]
    eras = builder._voice_lines({**VOICE_DOC, "presenter": PRESENTER}, "eras")
    assert sorted(eras) == [0, 1]
    assert eras[0]["line"] == 0, eras[0]
    assert eras[0]["duration_s"] == 1.91, eras[0]


def test_a_presenter_segment_must_declare_its_variant():
    """Untagged, it would enter the baseline timeline and speak a line nobody wrote."""
    builder = _builder()
    segments = [{"type": "presenter", "clip": "p00", "line": 0, "duration": 2.6}]
    try:
        builder._validate_segments(segments, 1)
    except SystemExit as exc:
        assert "variant" in str(exc), str(exc)
    else:
        raise AssertionError("an untagged presenter segment must be refused")


def test_the_baseline_timeline_does_not_carry_the_presenter():
    builder = _builder()
    project = ROOT / "projects" / "easel-fi-what-is-agent"
    eras = builder._timeline(project, 12, "eras")
    baseline = builder._timeline(project, 12, "easel")
    assert (eras[0]["type"], eras[0]["clip"]) == ("presenter", "p00"), eras[0]
    assert all(segment["type"] != "presenter" for segment in baseline), baseline
    assert [segment["clip"] for segment in baseline] == (
        [f"p{index:02d}" for index in range(1, 9)] + ["insert-video"]
        + [f"p{index:02d}" for index in range(9, 13)]
    ), baseline


def test_eras_durations_match_the_canonical_voice_timeline():
    import json
    import re

    project = ROOT / "projects" / "easel-fi-what-is-agent"
    timeline = json.loads((project / "motion" / "timeline.json").read_text(encoding="utf-8"))["segments"]
    eras = (project / "motion" / "film" / "eras.js").read_text(encoding="utf-8")
    actual = [(clip, float(duration)) for clip, duration in re.findall(
        r'id: "([^"]+)", dur: ([0-9.]+)', eras
    )]
    # eras.js is the eras film: a shared segment belongs to it, an eras-only one
    # is laid in front of the shared timeline.
    expected = [(segment["clip"], float(segment["duration"])) for segment in timeline
                if segment.get("variant", "eras") == "eras"]
    assert actual == expected, (actual, expected)


def test_eras_adapter_pads_a_short_source_with_its_final_frame():
    import importlib.util
    import tempfile

    renderer_path = ROOT / "projects" / "easel-fi-what-is-agent" / "motion" / "film" / "render.py"
    spec = importlib.util.spec_from_file_location("eras_render", renderer_path)
    assert spec and spec.loader
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    assert hasattr(renderer, "_pad_tail_frames")
    with tempfile.TemporaryDirectory() as temp:
        frames = Path(temp)
        (frames / "0001.jpg").write_bytes(b"first")
        (frames / "0002.jpg").write_bytes(b"last")
        renderer._pad_tail_frames(frames, 4)
        assert [(frames / f"{index:04d}.jpg").read_bytes() for index in range(1, 5)] == [
            b"first", b"last", b"last", b"last"
        ]


def test_every_clip_era_declares_its_drawer():
    """A clip era without an inline drawer makes scenes/index.js demand a scene file."""
    eras = (ROOT / "projects" / "easel-fi-what-is-agent" / "motion" / "film" / "eras.js").read_text(
        encoding="utf-8"
    )
    clip_lines = [line for line in eras.splitlines() if "clip:" in line]
    assert clip_lines, "expected the clip-driven eras table"
    missing = [line.strip() for line in clip_lines if "draw:" not in line]
    assert not missing, missing


def test_film_page_satisfies_the_engine_boot_contract():
    """engine.js binds #scrub/#tt/#play at load time and boots after scenes/index.js."""
    page = (ROOT / "projects" / "easel-fi-what-is-agent" / "motion" / "film" / "index.html").read_text(
        encoding="utf-8"
    )
    for element_id in ("scrub", "tt", "play"):
        assert f'id="{element_id}"' in page, element_id
    assert page.index("/engine/scenes/index.js") < page.index("/engine/engine.js")


def test_film_page_resolves_engine_relative_assets():
    """Engine fonts are declared as relative lib/fonts/*.woff, so the base must be the engine."""
    page = (ROOT / "projects" / "easel-fi-what-is-agent" / "motion" / "film" / "index.html").read_text(
        encoding="utf-8"
    )
    assert '<base href="/engine/">' in page
    assert 'src="/project/motion/film/eras.js"' in page
    assert '<script src="eras.js">' not in page


def test_eras_clip_override_keeps_the_baseline_clip_untouched():
    """An eras-only re-render must not require overwriting work/clips/<beat>.mp4."""
    import importlib.util
    import tempfile

    renderer_path = ROOT / "projects" / "easel-fi-what-is-agent" / "motion" / "film" / "render.py"
    spec = importlib.util.spec_from_file_location("eras_render_override", renderer_path)
    assert spec and spec.loader
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        baseline = project / "work" / "clips" / "p02.mp4"
        override = project / "work" / "eras" / "clips" / "p02.mp4"
        baseline.parent.mkdir(parents=True)
        baseline.write_bytes(b"baseline")
        assert renderer._source(project, "p02") == baseline
        override.parent.mkdir(parents=True)
        override.write_bytes(b"variant")
        assert renderer._source(project, "p02") == override


def test_variant_paths_never_point_at_baseline_artifacts():
    import importlib.util

    builder_path = ROOT / "scripts" / "build_code_animation_sample.py"
    spec = importlib.util.spec_from_file_location("build_code_animation_builder", builder_path)
    assert spec and spec.loader
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    eras = builder._variant_paths("eras")
    assert eras["srt"] == Path("assets/captions/eras.srt")
    assert eras["work"] == Path("work/eras")
    assert eras["receipt"] == Path("receipts/eras/sample.json")
    baseline = builder._variant_paths("easel")
    assert baseline["srt"] == Path("assets/captions/default.srt")
    assert baseline["work"] == Path("work")
    assert baseline["receipt"] == Path("receipts/sample.json")


def test_variant_qc_grades_its_own_captions_and_storyboard():
    import importlib.util
    import tempfile

    qc_path = ROOT / "scripts" / "qc_video.py"
    spec = importlib.util.spec_from_file_location("qc_video_variant", qc_path)
    assert spec and spec.loader
    qc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(qc)
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        (project / "assets" / "captions").mkdir(parents=True)
        (project / "script").mkdir(parents=True)
        (project / "script" / "storyboard.json").write_text("{}", encoding="utf-8")
        (project / "assets" / "captions" / "default.srt").write_text("", encoding="utf-8")
        srt, storyboard = qc._graded_inputs(project, "eras")
        assert srt == project / "assets" / "captions" / "default.srt"
        assert storyboard == project / "script" / "storyboard.json"
        (project / "assets" / "captions" / "eras.srt").write_text("", encoding="utf-8")
        (project / "work" / "eras").mkdir(parents=True)
        (project / "work" / "eras" / "storyboard.json").write_text("{}", encoding="utf-8")
        srt, storyboard = qc._graded_inputs(project, "eras")
        assert srt == project / "assets" / "captions" / "eras.srt"
        assert storyboard == project / "work" / "eras" / "storyboard.json"


def test_qc_grades_the_storyboard_the_build_actually_rendered():
    """An evidence film has no script/storyboard.json, only work/storyboard.json.

    Grading it against the absent canonical path reported "no storyboard" for a
    render that had eight shots, and then measured its real/generated ratio over
    zero shots — a FAIL for the wrong reason is as misleading as a false PASS.
    """
    import importlib.util
    import tempfile

    qc_path = ROOT / "scripts" / "qc_video.py"
    spec = importlib.util.spec_from_file_location("qc_video_workfallback", qc_path)
    assert spec and spec.loader
    qc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(qc)
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        (project / "work").mkdir(parents=True)
        (project / "work" / "storyboard.json").write_text("{}", encoding="utf-8")
        _, storyboard = qc._graded_inputs(project, "easel")
        assert storyboard == project / "work" / "storyboard.json"
        # The canonical script/ document still wins when both exist.
        (project / "script").mkdir(parents=True)
        (project / "script" / "storyboard.json").write_text("{}", encoding="utf-8")
        _, storyboard = qc._graded_inputs(project, "easel")
        assert storyboard == project / "script" / "storyboard.json"


def test_subtitle_sampling_lands_on_cues_not_on_gaps():
    """Five sparse cues over 44 s cover none of the six fixed sample points.

    The old scan reported "nothing burned in" for the 1024 evidence film whose
    captions were all present; sampling the declared cue midpoints sees them.
    """
    import importlib.util
    import tempfile

    qc_path = ROOT / "scripts" / "qc_video.py"
    spec = importlib.util.spec_from_file_location("qc_video_cues", qc_path)
    assert spec and spec.loader
    qc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(qc)

    srt_text = (
        "1\n00:00:02,000 --> 00:00:05,878\n这次验证的修订是 4efd5930。\n\n"
        "2\n00:00:08,000 --> 00:00:11,065\ndoctor 的七项核心检查，返回 0。\n\n"
        "3\n00:00:34,000 --> 00:00:37,750\n边界：工具链可用，Web 还不能算交付。\n"
    )
    with tempfile.TemporaryDirectory() as temp:
        srt = Path(temp) / "cut.srt"
        srt.write_text(srt_text, encoding="utf-8")
        moments = qc._cue_moments(srt, 44.0)
        assert len(moments) == 3, moments
        assert abs(moments[0] - 3.939) < 0.01, moments
        assert abs(moments[2] - 35.875) < 0.01, moments
        # No caption file: fall back to fixed fractions of the film.
        fallback = qc._cue_moments(None, 44.0)
        assert len(fallback) == 6 and abs(fallback[0] - 6.6) < 0.01, fallback


def test_qc_measures_provenance_from_the_cut_plan_when_there_is_one():
    """A cut plan declares which captured asset each placement shows.

    The storyboard of an evidence film carries only video+duration, so grading
    it there reported 0% real for a film that was 72.7% recordings, and the
    capture folder probe looked in a directory no builder writes.
    """
    import importlib.util
    import json
    import tempfile

    qc_path = ROOT / "scripts" / "qc_video.py"
    spec = importlib.util.spec_from_file_location("qc_video_plan", qc_path)
    assert spec and spec.loader
    qc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(qc)

    def placement(pid, start, end, asset):
        return {"placement_id": pid, "start_ms": start, "end_ms": end,
                "asset_id": asset, "source_time_range": "00:00.000-00:04.500",
                "crop": {"x": 0, "y": 0, "width": 1080, "height": 1920,
                         "source_width": 1080, "source_height": 1920},
                "reading_class": "reading", "semantic_progress": "shows it",
                "claim_ids": [], "caption_cue_ids": [], "claim_bearing": False,
                "context_first": False, "context_placement_id": None,
                "transition": "cut"}

    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        (project / "script").mkdir(parents=True)
        (project / "script" / "assets.json").write_text(json.dumps({
            "schema": "contentops.asset-map/v1",
            "assets": {
                "A-REV": {"kind": "recording", "path": "repo://cap.mp4",
                          "sha256": "a" * 64},
                "A-CARD": {"kind": "card", "html": "project://c.html",
                           "png": "project://c.png"},
                "A-BARE": {"kind": "recording"},
            },
        }), encoding="utf-8")
        (project / "script" / "cut-plan.json").write_text(json.dumps({
            "schema": "contentops.cut-plan/v1", "package_id": "p",
            "target": {"width": 1080, "height": 1920,
                       "duration_ms_range": [3000, 6000],
                       "caption_safe_area": {"x": 0, "y": 1600,
                                             "width": 1080, "height": 300}},
            "placements": [
                placement("P-1", 0, 4000, "A-REV"),
                placement("P-2", 4000, 5000, "A-CARD"),
                placement("P-3", 5000, 5500, "A-BARE"),
            ],
        }), encoding="utf-8")
        shares = qc._cut_plan_shares(project)
        # None when the project declares no plan at all.
        (project / "script" / "cut-plan.json").unlink()
        assert qc._cut_plan_shares(project) is None

    assert shares is not None
    # 4.5 s recording + 1 s card; the unproven recording still counts as
    # recording time in the share, but never as presentable evidence.
    assert abs(shares["real_ratio"] - 4.5 / 5.5) < 0.01, shares
    assert shares["real_assets"] == ["A-REV"], shares
    assert shares["unproven_assets"] == ["A-BARE"], shares


def test_an_empty_caption_file_does_not_beat_one_with_cues():
    """A zero-byte easel.srt used to win on existence and report "no captions".

    The file was present, so it was chosen, and a film whose cues lived in
    default.srt was graded as having none.
    """
    import importlib.util
    import tempfile

    spec = importlib.util.spec_from_file_location(
        "qc_video_empty_srt", ROOT / "scripts" / "qc_video.py")
    assert spec and spec.loader
    qc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(qc)
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        captions = project / "assets" / "captions"
        captions.mkdir(parents=True)
        (project / "script").mkdir(parents=True)
        (project / "script" / "storyboard.json").write_text("{}", encoding="utf-8")
        (captions / "easel.srt").write_text("", encoding="utf-8")
        (captions / "default.srt").write_text(
            "1\n00:00:00,500 --> 00:00:02,000\n有字幕。\n", encoding="utf-8")
        srt, _ = qc._graded_inputs(project, "easel")
        assert srt == captions / "default.srt", srt
        # With no candidate carrying a cue, the placeholder is still named, so the
        # report points at the file the author has to fix.
        (captions / "default.srt").write_text("", encoding="utf-8")
        srt, _ = qc._graded_inputs(project, "easel")
        assert srt == captions / "easel.srt", srt


def test_a_storyboard_without_captures_reports_the_ratio_as_unmeasured():
    """vector_animation is in neither source set, so its share was published as 0%.

    That artefact turned "this storyboard declares no capture" into "0% of this
    film is real", and for an evidence-led account into a FAIL. It has to read
    as unmeasured: a different statement, with a different severity.
    """
    import importlib.util
    import json
    import tempfile

    from process_utils import hidden_run

    spec = importlib.util.spec_from_file_location(
        "qc_video_unmeasured", ROOT / "scripts" / "qc_video.py")
    assert spec and spec.loader
    qc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(qc)
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        (project / "final").mkdir(parents=True)
        render = project / "final" / "easel.mp4"
        result = hidden_run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=1080x1920:rate=15:duration=4",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
            "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-shortest", str(render),
        ], timeout=180)
        assert result.returncode == 0 and render.exists(), result.stderr
        (project / "project.yaml").write_text(
            "slug: qc\naccount_slug: x-superplay-1024\n", encoding="utf-8")
        (project / "script").mkdir(parents=True)
        (project / "script" / "storyboard.json").write_text(json.dumps({
            "shots": [{"source_type": "vector_animation", "duration_s": 2.0},
                      {"source_type": "vector_animation", "duration_s": 2.0}]}),
            encoding="utf-8")
        report = qc.qc(project)
    rows = {c["id"]: c for c in report["checks"]}
    assert rows["real_source_ratio"]["value"] is None, rows["real_source_ratio"]
    assert rows["real_source_ratio"]["severity"] == "FAIL", rows["real_source_ratio"]
    assert "not measured" in rows["real_source_ratio"]["note"], rows["real_source_ratio"]
    assert rows["generated_ratio"]["value"] is None, rows["generated_ratio"]
    assert rows["generated_ratio"]["severity"] == "FAIL", rows["generated_ratio"]


def test_packaging_refuses_to_overwrite_a_human_decision():
    import json
    import tempfile

    pack = __import__("package_code_animation_sample")
    with tempfile.TemporaryDirectory() as temp:
        receipts = Path(temp)
        (receipts / "human-review.json").write_text(json.dumps({
            "status": "APPROVED", "review_bundle_fingerprint": "old",
            "scores": {"visual_quality": 90},
        }), encoding="utf-8")
        try:
            pack._assert_review_is_pending(receipts, "new")
        except SystemExit as exc:
            assert "refusing overwrite" in str(exc).lower(), str(exc)
        else:
            raise AssertionError("packaging overwrote an existing human decision")


def test_packaging_keeps_variant_receipts_out_of_the_baseline():
    import importlib.util

    pack_path = ROOT / "scripts" / "package_code_animation_sample.py"
    spec = importlib.util.spec_from_file_location("package_variant", pack_path)
    assert spec and spec.loader
    pack = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pack)
    eras = pack._variant_io("eras")
    assert eras["sample"] == Path("receipts/eras/sample.json")
    assert eras["receipts"] == Path("receipts/eras")
    assert eras["cover_png"] == Path("assets/covers/cover-eras.png")
    baseline = pack._variant_io("easel")
    assert baseline["sample"] == Path("receipts/sample.json")
    assert baseline["receipts"] == Path("receipts")


def test_timing_reconciliation_proves_the_film_arithmetic():
    import importlib.util

    builder_path = ROOT / "scripts" / "build_code_animation_sample.py"
    spec = importlib.util.spec_from_file_location("build_code_animation_recon", builder_path)
    assert spec and spec.loader
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    segments = [
        {"type": "beat", "clip": "p01", "line": 1, "duration": 2.37},
        {"type": "insert", "clip": "insert-video", "duration": 2.5},
        {"type": "beat", "clip": "p02", "line": 2, "duration": 2.904},
    ]
    lines = {1: {"duration_s": 2.02}, 2: {"duration_s": 2.554}}
    placed = [{"line": 1, "start_s": 0.0, "duration_s": 2.02},
              {"line": 2, "start_s": 4.87, "duration_s": 2.554}]
    result = builder._reconciliation(segments, placed, lines, 7.424, 7.774)
    assert result["film_seconds"] == 7.774
    assert result["voice_seconds"] == 4.574
    assert result["tail_seconds"] == 0.7
    assert result["silent_bridge_seconds"] == 2.5
    assert all(result["checks"].values()), result["checks"]


def test_reconciliation_counts_the_presenter_as_voice_not_as_a_tail():
    """The opening speaks; its silence-free 2.6 s window is voice plus tail."""
    builder = _builder()
    segments = [
        {"type": "presenter", "clip": "p00", "line": 0, "duration": 2.6},
        {"type": "beat", "clip": "p01", "line": 1, "duration": 2.37},
        {"type": "insert", "clip": "insert-video", "duration": 2.5},
    ]
    lines = {0: {"duration_s": 1.91}, 1: {"duration_s": 2.02}}
    placed = [{"line": 0, "start_s": 0.0, "duration_s": 1.91},
              {"line": 1, "start_s": 2.6, "duration_s": 2.02}]
    result = builder._reconciliation(segments, placed, lines, 4.62, 7.47)
    assert result["voice_seconds"] == 3.93, result["voice_seconds"]
    assert result["tail_seconds"] == 1.04, result["tail_seconds"]
    assert result["silent_bridge_seconds"] == 2.5, result["silent_bridge_seconds"]
    assert all(result["checks"].values()), result["checks"]


def test_the_build_reads_an_eras_only_clip_from_its_own_directory():
    """The presenter lives in work/eras/clips; the baseline clip is never replaced."""
    import tempfile

    builder = _builder()
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        baseline = project / "work" / "clips" / "p01.mp4"
        override = project / "work" / "eras" / "clips" / "p00.mp4"
        baseline.parent.mkdir(parents=True)
        baseline.write_bytes(b"baseline")
        assert builder._clip_path(project, "p01", "eras") == baseline
        assert builder._clip_path(project, "p00", "eras").is_file() is False
        override.parent.mkdir(parents=True)
        override.write_bytes(b"presenter")
        assert builder._clip_path(project, "p00", "eras") == override
        # The baseline variant never reaches into the eras directory.
        assert builder._clip_path(project, "p00", "easel") == project / "work" / "clips" / "p00.mp4"


def test_variant_cannot_overwrite_the_baseline_video():
    builder = _builder()
    assert builder._output_name("eras", None) == "eras"
    try:
        builder._output_name("eras", "easel")
    except ValueError:
        pass
    else:
        raise AssertionError("ERAS output could overwrite the baseline")


def test_motion_qc_uses_the_rendered_storyboard_not_the_legacy_script():
    import importlib.util
    import tempfile

    path = ROOT / "scripts" / "qc_video.py"
    spec = importlib.util.spec_from_file_location("qc_rendered_storyboard", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        source = project / "script" / "storyboard.json"
        rendered = project / "work" / "storyboard.json"
        source.parent.mkdir(parents=True)
        rendered.parent.mkdir(parents=True)
        source.write_text('{"shots":[{"source_type":"real_screenshot"}]}', encoding="utf-8")
        rendered.write_text('{"shots":[{"source_type":"motion"}]}', encoding="utf-8")
        _, selected = module._graded_inputs(project, "easel", rendered)
        assert selected == rendered
        motion_builder = (ROOT / "scripts" / "build_motion_film.py").read_text(encoding="utf-8")
        assert '"--storyboard", str(project / "work" / "storyboard.json")' in motion_builder


def test_long_narration_caption_reaches_the_end_of_speech():
    import tempfile

    builder = _builder()
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        srt = builder._write_srt(
            project,
            {2: {"text": "这句超过四秒", "duration_s": 5.927}},
            [{"line": 2, "start_s": 4.458, "duration_s": 5.927}],
        ).read_text(encoding="utf-8")
        assert "00:00:04,458 --> 00:00:10,385" in srt, srt


def test_motion_qc_does_not_trust_a_stale_report_or_failed_child():
    import importlib.util
    from types import SimpleNamespace

    path = ROOT / "scripts" / "build_motion_film.py"
    spec = importlib.util.spec_from_file_location("motion_build_gate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module._qc_outcome(SimpleNamespace(returncode=1, stdout='{"overall":"PASS"}')) == "FAIL"
    assert module._qc_outcome(SimpleNamespace(returncode=0, stdout="")) == "FAIL"
    assert module._qc_outcome(SimpleNamespace(returncode=0, stdout="[]")) == "FAIL"
    assert module._qc_outcome(SimpleNamespace(returncode=0, stdout='{"overall":"WARN"}')) == "WARN"


def main() -> int:
    tests = (
        test_composer_rechecks_copy_approval_before_final_assembly,
        test_full_film_is_the_only_visual_shot,
        test_beat_clips_remain_the_explicit_fallback,
        test_runtime_receipt_uses_the_measured_film_duration,
        test_presenter_belongs_only_to_the_eras_variant,
        test_a_presenter_segment_must_declare_its_variant,
        test_the_baseline_timeline_does_not_carry_the_presenter,
        test_eras_durations_match_the_canonical_voice_timeline,
        test_eras_adapter_pads_a_short_source_with_its_final_frame,
        test_every_clip_era_declares_its_drawer,
        test_film_page_satisfies_the_engine_boot_contract,
        test_film_page_resolves_engine_relative_assets,
        test_eras_clip_override_keeps_the_baseline_clip_untouched,
        test_variant_paths_never_point_at_baseline_artifacts,
        test_variant_qc_grades_its_own_captions_and_storyboard,
        test_qc_grades_the_storyboard_the_build_actually_rendered,
        test_subtitle_sampling_lands_on_cues_not_on_gaps,
        test_qc_measures_provenance_from_the_cut_plan_when_there_is_one,
        test_an_empty_caption_file_does_not_beat_one_with_cues,
        test_a_storyboard_without_captures_reports_the_ratio_as_unmeasured,
        test_packaging_refuses_to_overwrite_a_human_decision,
        test_packaging_keeps_variant_receipts_out_of_the_baseline,
        test_timing_reconciliation_proves_the_film_arithmetic,
        test_reconciliation_counts_the_presenter_as_voice_not_as_a_tail,
        test_the_build_reads_an_eras_only_clip_from_its_own_directory,
        test_variant_cannot_overwrite_the_baseline_video,
        test_motion_qc_uses_the_rendered_storyboard_not_the_legacy_script,
        test_long_narration_caption_reaches_the_end_of_speech,
        test_motion_qc_does_not_trust_a_stale_report_or_failed_child,
    )
    failures = []
    for test in tests:
        try:
            test()
            print(f"[ok] {test.__name__}")
        except AssertionError as exc:
            failures.append((test.__name__, str(exc)))
            print(f"[FAIL] {test.__name__}: {exc}")
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print(f"\nAll {len(tests)} composition tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
