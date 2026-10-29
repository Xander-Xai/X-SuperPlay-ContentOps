"""Repository policy tests for generated media.

A rendered cut belongs outside this repo; the repo keeps the system that makes
one. ``.gitignore`` covers ``projects/*/final/``, but an ignore rule cannot
un-track a file that was already committed, so the index itself is checked.

Run: python tests/test_repo_policy.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_repo_policy  # noqa: E402


def _with(files):
    original = check_repo_policy._git_files
    check_repo_policy._git_files = lambda: files
    try:
        return check_repo_policy.check_tracked_media()
    finally:
        check_repo_policy._git_files = original


def test_the_shipped_repository_passes():
    assert check_repo_policy.check_tracked_media() == []


def test_a_tracked_final_is_reported():
    failures = _with(["projects/demo/final/cut.mp4"])
    assert failures == ["TRACKED RENDERED OUTPUT: projects/demo/final/cut.mp4"], failures


def test_a_tracked_video_outside_final_is_reported():
    failures = _with(["projects/demo/work/raw.mp4"])
    assert failures == ["TRACKED VIDEO CONTAINER: projects/demo/work/raw.mp4"], failures


def test_the_allowlisted_exception_is_respected():
    assert _with(["projects/easel-review/final/final.mp4"]) == []


def test_source_code_is_not_media():
    assert _with(["src/app.py", "docs/README.md", "projects/a/script/master.md"]) == []


def main() -> int:
    failures = []
    tests = (
        test_the_shipped_repository_passes,
        test_a_tracked_final_is_reported,
        test_a_tracked_video_outside_final_is_reported,
        test_the_allowlisted_exception_is_respected,
        test_source_code_is_not_media,
    )
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
    print("\nAll repository policy tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
