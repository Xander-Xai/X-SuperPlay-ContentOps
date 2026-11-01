"""Reliability tests for motion render reuse and composer envelopes."""
from __future__ import annotations

import hashlib
import inspect
import json
import tempfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_motion_film as motion  # noqa: E402


def test_unverified_cache_never_skips_render():
    source = inspect.getsource(motion.build)
    assert "cache unverified; rendering again" in source
    assert "_render_is_reusable" not in source
    assert "staged.unlink" not in source


def test_compose_envelope_must_be_success_json():
    envelope = {"status": "OK", "output": {"path": "film.mp4"}}
    assert motion._compose_outcome("notice\n" + json.dumps(envelope, indent=2)) == (True, envelope)
    assert motion._compose_outcome("ffmpeg notice\nnot json") == (False, None)
    assert motion._compose_outcome('{"status":"BLOCKED"}') == (False, {"status": "BLOCKED"})
    assert motion._compose_outcome(json.dumps(envelope) + "\ntrailing error") == (False, None)


def test_composer_output_is_bound_to_the_actual_file():
    with tempfile.TemporaryDirectory() as temp:
        project = Path(temp)
        output = project / "final" / "easel.mp4"
        output.parent.mkdir()
        output.write_bytes(b"actual render")
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        result = {"output": {"path": "project://final/easel.mp4", "sha256": digest}}
        assert motion._compose_output_matches(project, result)
        output.write_bytes(b"modified render")
        assert not motion._compose_output_matches(project, result)
        assert not motion._compose_output_matches(project, {"output": {"path": "project://../outside", "sha256": digest}})


def main() -> int:
    tests = (test_unverified_cache_never_skips_render,
             test_compose_envelope_must_be_success_json,
             test_composer_output_is_bound_to_the_actual_file)
    for test in tests:
        test()
        print(f"[ok] {test.__name__}")
    print(f"All {len(tests)} motion reliability tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
