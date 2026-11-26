"""Default narration is the founder clone in both prompt and scripted paths.

Regression: a scripted `make_content answer` used to leave narration empty when
`--narration` was omitted, failing NARRATION_INVALID even though the interactive
default and every video account DNA already named the MiniMax founder clone.
SAPI is an explicit diagnostic opt-in, never a silent substitute.

Run: python tests/test_default_narration.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import make_content  # noqa: E402
import production_gates as gates  # noqa: E402


def test_default_constant_is_clone():
    assert make_content.DEFAULT_NARRATION == "minimax-clone"
    assert "minimax-clone" in gates.NARRATION_CHOICES


def test_scripted_video_answer_defaults_to_clone():
    args = SimpleNamespace(
        interactive=False, account=None, asset_policy=None, avatar_intro=None,
        avatar_outro=None, narration=None, motion=None, bgm=None,
        reviewer="Founder", opinion="reason", avatar_quota_budget=None,
    )
    project = ROOT / "projects" / "agentguide-learning-roadmap"
    answers = make_content._answers_from_args(args, project)
    assert answers["narration"] == "minimax-clone"


def test_explicit_sapi_is_preserved():
    args = SimpleNamespace(
        interactive=False, account=None, asset_policy=None, avatar_intro=None,
        avatar_outro=None, narration="sapi", motion=None, bgm=None,
        reviewer="Founder", opinion="reason", avatar_quota_budget=None,
    )
    project = ROOT / "projects" / "agentguide-learning-roadmap"
    answers = make_content._answers_from_args(args, project)
    assert answers["narration"] == "sapi"


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"{len(tests)} tests passed")
