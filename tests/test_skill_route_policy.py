"""Skill-first routing policy tests.

The failure this guards against: composing a deliverable with the low-level
compositor before asking which project skill owns it. The rule is stated in both
agent instruction files and made executable by ``scripts/skill_route.py``.

Run: python tests/test_skill_route_policy.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from skill_route import (  # noqa: E402
    CATALOG_ROOTS,
    RULE_MARKER,
    catalog,
    rank,
    shared_catalog,
)


def test_rule_is_in_both_agent_files():
    for name in ("CLAUDE.md", "AGENTS.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert RULE_MARKER in text, f"{name} lost the {RULE_MARKER!r} section"
        assert "scripts/skill_route.py" in text, f"{name} does not name the helper"


def test_rule_names_the_failure_it_prevents():
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert "assemble.py" in text
    assert "skill_route" in text


def test_helper_exists():
    assert (ROOT / "scripts" / "skill_route.py").is_file()


def _easel_catalog_present() -> bool:
    """Whether the gitignored Easel runtime/checkout is available.

    The gzh vendor is a catalog root too, but it is not the Easel catalog these
    assertions are about. A clean CI checkout has the vendor and no Easel, so
    "some catalog exists" is the wrong gate.
    """
    return any(path.is_dir() for path in CATALOG_ROOTS if path.name == "openclaw")


def test_catalog_is_discoverable_when_present():
    skills, root = catalog()
    if not _easel_catalog_present():
        # The runtime is gitignored, so a clean checkout cannot enumerate it.
        # The rule text above still applies; this half is host-local by design.
        print("Easel catalog absent on this checkout; skipping catalog assertions")
        return
    assert skills, f"catalog root {root} contains no SKILL.md"
    names = {skill["name"] for skill in skills}
    for expected in ("card-design", "slideshow-video", "auto-short-video"):
        assert expected in names, f"{expected} missing from the catalog"


def test_ranking_sends_a_card_request_to_card_design():
    skills, root = catalog()
    if not _easel_catalog_present():
        print("Easel catalog absent on this checkout; skipping ranking assertion")
        return
    top = rank(skills, "card design poster layout")[:3]
    assert top, "no skill matched a card request"
    assert top[0]["name"] == "card-design", [skill["name"] for skill in top]


def test_ranking_sends_a_slideshow_request_to_slideshow_video():
    skills, root = catalog()
    if not _easel_catalog_present():
        print("Easel catalog absent on this checkout; skipping ranking assertion")
        return
    top = rank(skills, "图片做成视频 相册 幻灯片")[:3]
    assert top, "no skill matched a slideshow request"
    assert top[0]["name"] == "slideshow-video", [skill["name"] for skill in top]


def test_expected_catalog_roots_are_declared():
    assert any(path.name == "openclaw" for path in CATALOG_ROOTS)


def test_a_shared_store_skill_is_reachable_by_routing():
    """An adopted skill that --match cannot find is adopted in name only."""
    shared = shared_catalog()
    if not shared:
        print("shared store absent on this checkout; skipping shared routing")
        return
    names = {skill["name"] for skill in shared}
    if "b-roll-finder" not in names:
        print("b-roll-finder not installed in the shared store; skipping")
        return
    top = rank(shared, "b-roll sourcing clips")[:3]
    assert top, "the shared store matched nothing for a b-roll request"
    assert top[0]["name"] in {"b-roll-finder", "x-superplay-broll-production"}, \
        [skill["name"] for skill in top]


def test_routing_still_answers_when_no_catalog_exists():
    """A clean checkout has no Easel runtime; the shared store must still route."""
    import tempfile
    from unittest import mock

    import skill_route

    with tempfile.TemporaryDirectory() as td:
        store = Path(td) / "skills"
        skill = store / "demo-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(
            "---\nname: demo-skill\ndescription: b-roll sourcing demo\n---\n# demo\n",
            encoding="utf-8")
        with mock.patch.object(skill_route, "CATALOG_ROOTS", (Path(td) / "absent",)), \
             mock.patch.object(skill_route, "SHARED_SKILL_ROOT", store), \
             mock.patch.object(sys, "argv", ["skill_route.py", "--match", "b-roll"]):
            assert skill_route.main() == 0


def main() -> int:
    failures = []
    tests = (
        test_rule_is_in_both_agent_files,
        test_rule_names_the_failure_it_prevents,
        test_helper_exists,
        test_catalog_is_discoverable_when_present,
        test_ranking_sends_a_card_request_to_card_design,
        test_ranking_sends_a_slideshow_request_to_slideshow_video,
        test_expected_catalog_roots_are_declared,
        test_a_shared_store_skill_is_reachable_by_routing,
        test_routing_still_answers_when_no_catalog_exists,
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
    print("\nAll skill-route policy tests passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
