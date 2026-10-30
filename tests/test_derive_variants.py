"""Deriving the other platforms' cuts is a mapping, not a re-encode of everything.

The rules this file pins:

- a platform whose frame the master already has gets no derivative (re-encoding a
  film to the size it already is creates a second thing to keep in sync);
- a platform with no declared frame is reported, never silently given the master;
- a derivative is refused when the master has no QC receipt, or when every
  receipt predates it -- a derivative inherits the master's verdict;
- the tool that ran is bound by digest, because the runtime's trust is decided by
  ``verify_easel_runtime.py`` and not by this receipt.

The pure planner is tested directly; the refusals use a real clip because
``derive`` probes the master before it plans anything.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import derive_variants as dv  # noqa: E402
from process_utils import hidden_run  # noqa: E402

TESTS: List = []


def test(fn):
    TESTS.append(fn)
    return fn


def _clip(path: Path, width: int = 1080, height: int = 1920, seconds: int = 1) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    result = hidden_run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"testsrc=size={width}x{height}:rate=10:duration={seconds}",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(path),
    ], timeout=180)
    return result.returncode == 0 and path.is_file()


def _project(root: Path, *, account: str = "x-superplay-1024",
             fmt: str = "1080x1920") -> Path:
    project = root / "project"
    (project / "script").mkdir(parents=True, exist_ok=True)
    (project / "receipts").mkdir(parents=True, exist_ok=True)
    (project / "project.yaml").write_text(
        f"slug: p\naccount_slug: {account}\nformat: {fmt}\nplatforms: [douyin, bilibili]\n",
        encoding="utf-8")
    return project


@test
def test_the_platform_that_already_has_the_master_gets_no_derivative():
    planned = dv.plan_variants((1080, 1920), ["douyin", "bilibili", "xiaohongshu"])
    actions = {item["platform"]: item["action"] for item in planned}
    assert actions == {"bilibili": "DERIVE", "douyin": "SKIP", "xiaohongshu": "SKIP"}, actions
    bilibili = [item for item in planned if item["platform"] == "bilibili"][0]
    assert (bilibili["width"], bilibili["height"]) == (1920, 1080), bilibili
    assert (bilibili["ratio"], bilibili["mode"]) == ("1920:1080", "blur"), bilibili
    print("[ok] 1. only the platform whose frame differs is derived")


@test
def test_a_horizontal_master_derives_the_vertical_cut():
    planned = dv.plan_variants((1920, 1080), ["bilibili", "douyin"])
    actions = {item["platform"]: item["action"] for item in planned}
    assert actions == {"bilibili": "SKIP", "douyin": "DERIVE"}, actions
    douyin = [item for item in planned if item["platform"] == "douyin"][0]
    assert (douyin["width"], douyin["height"]) == (1080, 1920), douyin
    print("[ok] 2. a horizontal master derives the vertical cut")


@test
def test_a_platform_with_no_declared_frame_is_reported_not_substituted():
    planned = dv.plan_variants((1080, 1920), ["zhihu"])
    assert len(planned) == 1, planned
    assert planned[0]["action"] == "SKIP", planned
    assert "no declared frame" in planned[0]["reason"], planned
    print("[ok] 3. an undeclared platform is skipped by name, never given the master")


@test
def test_an_ungraded_master_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        if not _clip(project / "final" / "easel.mp4"):
            print("[skip] 4. ungraded master refused (needs ffmpeg)")
            return
        try:
            dv.derive(project, dry_run=True)
        except SystemExit as exit_code:
            assert exit_code.code == 4, exit_code.code
        else:
            raise AssertionError("an ungraded master produced a derivative plan")
        print("[ok] 4. a derivative is refused when the master has no QC receipt")


@test
def test_a_receipt_older_than_the_master_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        master = project / "final" / "easel.mp4"
        if not _clip(master):
            print("[skip] 5. stale receipt refused (needs ffmpeg)")
            return
        receipt = project / "receipts" / "qc-report.json"
        receipt.write_text("{}", encoding="utf-8")
        # Age the receipt behind the master without depending on clock resolution.
        import os
        os.utime(receipt, (master.stat().st_mtime - 600, master.stat().st_mtime - 600))
        try:
            dv.derive(project, dry_run=True)
        except SystemExit as exit_code:
            assert exit_code.code == 4, exit_code.code
        else:
            raise AssertionError("a stale QC receipt allowed a derivative")
        print("[ok] 5. a receipt older than the master refuses the derivation")


@test
def test_a_fresh_receipt_plans_without_writing_in_dry_run():
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        master = project / "final" / "easel.mp4"
        if not _clip(master):
            print("[skip] 6. dry run writes nothing (needs ffmpeg)")
            return
        (project / "receipts" / "qc-report.json").write_text(
            json.dumps({"overall": "PASS"}), encoding="utf-8")
        receipt = dv.derive(project, dry_run=True)
        variants = receipt["variants"]
        assert [v["action"] for v in variants] == ["WOULD_DERIVE"], variants
        assert variants[0]["platform"] == "bilibili", variants
        assert not (project / "receipts" / "variants.json").exists(), "dry run wrote a receipt"
        assert not (project / "final" / "variants").exists(), "dry run wrote media"
        assert receipt["tool"]["sha256"] == dv._sha256(dv.RUNTIME_TOOL), receipt["tool"]
    print("[ok] 6. a dry run binds the tool digest and writes nothing")


@test
def test_a_failed_master_is_refused_before_it_is_multiplied():
    """Three shapes of a failing cut is the same failure, three times."""
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        master = project / "final" / "easel.mp4"
        if not _clip(master):
            print("[skip] 5b. failed master refused (needs ffmpeg)")
            return
        (project / "receipts" / "qc-report.json").write_text(
            json.dumps({"overall": "FAIL"}), encoding="utf-8")
        try:
            dv.derive(project, dry_run=True)
        except SystemExit as exit_code:
            assert exit_code.code == 4, exit_code.code
        else:
            raise AssertionError("a FAILing master was re-framed")
    print("[ok] 5b. a master whose own QC failed is refused")


@test
def test_one_failing_gate_is_not_overridden_by_a_newer_passing_one():
    """qc_video and cut_qc check different things; a PASS from one is not a veto."""
    with tempfile.TemporaryDirectory() as temp:
        project = _project(Path(temp))
        master = project / "final" / "easel.mp4"
        if not _clip(master):
            print("[skip] 5c. cross-gate failure honoured (needs ffmpeg)")
            return
        (project / "receipts" / "qc-report-easel.json").write_text(
            json.dumps({"overall": "PASS"}), encoding="utf-8")
        (project / "receipts" / "qc-report.json").write_text(
            json.dumps({"overall": "FAIL"}), encoding="utf-8")
        try:
            dv.derive(project, dry_run=True)
        except SystemExit as exit_code:
            assert exit_code.code == 4, exit_code.code
        else:
            raise AssertionError("a FAIL from one gate was overridden by a PASS from another")
    print("[ok] 5c. one FAIL among the fresh receipts refuses the derivation")


@test
def test_a_project_without_an_account_is_refused():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "project"
        (project / "final").mkdir(parents=True)
        (project / "project.yaml").write_text("slug: p\nformat: 1080x1920\n", encoding="utf-8")
        if not _clip(project / "final" / "easel.mp4"):
            print("[skip] 7. account refused (needs ffmpeg)")
            return
        try:
            dv.derive(project, dry_run=True)
        except SystemExit as exit_code:
            assert exit_code.code == 4, exit_code.code
        else:
            raise AssertionError("a project with no account produced a plan")
    print("[ok] 7. a project that names no account is refused")


@test
def test_covers_are_reported_at_their_own_frame_never_cropped_into_one():
    """A 3:4 crop of a 9:16 card cuts the type laid out for it, so report, don't convert."""
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp) / "project"
        covers = project / "assets" / "covers"
        covers.mkdir(parents=True)
        rows = {r["platform"]: r for r in dv.cover_status(
            project, ["douyin", "bilibili", "zhihu"], {})}
        assert rows["douyin"]["status"] == "ABSENT", rows["douyin"]
        assert rows["douyin"]["expected"] == "1080x1440", rows["douyin"]
        assert rows["zhihu"]["status"] == "NO_DECLARED_COVER", rows["zhihu"]

        made = hidden_run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=red:s=1080x1440", "-frames:v", "1",
            str(covers / "douyin.png")], timeout=120)
        if made.returncode != 0:
            print("[skip] 8. cover frames reported (needs ffmpeg)")
            return
        wrong = hidden_run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=c=blue:s=1080x1920", "-frames:v", "1",
            str(covers / "bilibili.png")], timeout=120)
        assert wrong.returncode == 0, wrong.stderr

        rows = {r["platform"]: r for r in dv.cover_status(
            project, ["douyin", "bilibili"], {})}
        assert rows["douyin"]["status"] == "PRESENT", rows["douyin"]
        assert (rows["douyin"]["width"], rows["douyin"]["height"]) == (1080, 1440)
        assert rows["bilibili"]["status"] == "WRONG_FRAME", rows["bilibili"]
    print("[ok] 8. covers are reported at their platform's frame")


def main() -> int:
    failures = []
    planner_only = {
        "test_the_platform_that_already_has_the_master_gets_no_derivative",
        "test_a_horizontal_master_derives_the_vertical_cut",
        "test_a_platform_with_no_declared_frame_is_reported_not_substituted",
    }
    if not dv.RUNTIME_TOOL.is_file():
        tests = [fn for fn in TESTS if fn.__name__ in planner_only]
        print("[skip] pinned runtime reframe.py absent; running planner tests only")
    else:
        tests = list(TESTS)
    for fn in tests:
        try:
            fn()
        except AssertionError as exc:
            failures.append((fn.__name__, str(exc)))
            print(f"[FAIL] {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append((fn.__name__, repr(exc)))
            print(f"[ERR ] {fn.__name__}: {exc!r}")
    print()
    if failures:
        print(f"{len(failures)} of {len(tests)} test(s) failed")
        return 1
    if len(tests) != len(TESTS):
        print(f"All {len(tests)} planner tests passed; derive tests skipped (runtime absent).")
    else:
        print(f"All {len(TESTS)} variant-derivation tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
