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


def test_eras_durations_match_the_canonical_voice_timeline():
    import json
    import re

    project = ROOT / "projects" / "easel-fi-what-is-agent"
    timeline = json.loads((project / "motion" / "timeline.json").read_text(encoding="utf-8"))["segments"]
    eras = (project / "motion" / "film" / "eras.js").read_text(encoding="utf-8")
    actual = [(clip, float(duration)) for clip, duration in re.findall(
        r'id: "([^"]+)", dur: ([0-9.]+)', eras
    )]
    expected = [(segment["clip"], float(segment["duration"])) for segment in timeline]
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


def main() -> int:
    tests = (
        test_full_film_is_the_only_visual_shot,
        test_beat_clips_remain_the_explicit_fallback,
        test_runtime_receipt_uses_the_measured_film_duration,
        test_eras_durations_match_the_canonical_voice_timeline,
        test_eras_adapter_pads_a_short_source_with_its_final_frame,
        test_every_clip_era_declares_its_drawer,
        test_film_page_satisfies_the_engine_boot_contract,
        test_film_page_resolves_engine_relative_assets,
        test_eras_clip_override_keeps_the_baseline_clip_untouched,
        test_variant_paths_never_point_at_baseline_artifacts,
        test_variant_qc_grades_its_own_captions_and_storyboard,
        test_packaging_keeps_variant_receipts_out_of_the_baseline,
        test_timing_reconciliation_proves_the_film_arithmetic,
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
