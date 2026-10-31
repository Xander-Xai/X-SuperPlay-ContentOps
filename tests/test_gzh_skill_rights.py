from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "scripts"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import check_gzh_skill_rights as checker  # noqa: E402


def _entry(path: str, cls: str = "OWNED_AND_CLEARED",
           dispatch: str = "allowed", distribution: str = "allowed",
           notice: bool = False) -> dict:
    return {
        "path": path,
        "class": cls,
        "source": "test",
        "license": "test",
        "dispatch": dispatch,
        "distribution": distribution,
        "notice_required": notice,
        "decision": "test",
    }


def _root(raw: str, skills: dict[str, dict], selected: str | None = None,
          notice: bool = False) -> Path:
    root = Path(raw)
    base = root / "vendor" / "gzh-thinktank" / "gzh_未来智能" / "skills"
    for name in skills:
        path = base / skills[name]["path"] / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("---\nname: test\n---\n", encoding="utf-8")
    if notice:
        (root / "vendor" / "gzh-thinktank" / "THIRD_PARTY_NOTICES.md").write_text(
            "notice\n", encoding="utf-8")
    config = root / "config" / "gzh-skill-rights.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps({
        "schema": checker.SCHEMA,
        "classes": {},
        "skills": skills,
    }), encoding="utf-8")
    if selected is not None:
        route = root / "projects" / "demo" / "routing.yaml"
        route.parent.mkdir(parents=True, exist_ok=True)
        route.write_text(
            "topic_route:\n  selected_skill: " + selected + "\n", encoding="utf-8")
    return root


class GzhSkillRightsTests(unittest.TestCase):
    def test_an_allowed_selection_passes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = _root(raw, {"owned": _entry("owned")}, selected="owned")
            result = checker.check(root)
            self.assertTrue(result["ok"], result)

    def test_a_blocked_selection_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = _root(raw, {"unknown": _entry(
                "unknown", "RIGHTS_UNKNOWN", "blocked", "hold")}, selected="unknown")
            result = checker.check(root)
            self.assertFalse(result["ok"])
            self.assertEqual(result["failures"][0]["id"], "route_blocked_skill")

    def test_an_unlisted_skill_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = _root(raw, {"owned": _entry("owned")})
            extra = root / "vendor" / "gzh-thinktank" / "gzh_未来智能" / "skills" / "extra"
            extra.mkdir(parents=True)
            (extra / "SKILL.md").write_text("---\nname: extra\n---\n", encoding="utf-8")
            result = checker.check(root)
            self.assertFalse(result["ok"])
            self.assertEqual(result["failures"][0]["id"], "unlisted_skill")

    def test_a_missing_notice_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = _root(raw, {"mit": _entry(
                "mit", "THIRD_PARTY_LICENSE_VERIFIED", notice=True)})
            result = checker.check(root)
            self.assertFalse(result["ok"])
            self.assertEqual(result["failures"][0]["id"], "notice_missing")

    def test_a_notice_satisfies_the_requirement(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = _root(raw, {"mit": _entry(
                "mit", "THIRD_PARTY_LICENSE_VERIFIED", notice=True)}, notice=True)
            result = checker.check(root)
            self.assertTrue(result["ok"], result)

    def test_a_missing_config_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            with self.assertRaises(checker.RightsError) as caught:
                checker.check(root, root / "config" / "gzh-skill-rights.json")
            self.assertEqual(str(caught.exception), "CONFIG_MISSING")

    def test_the_committed_config_covers_every_vendored_skill(self) -> None:
        config = checker.load_config(checker.CONFIG)
        actual = checker.skill_paths(checker.ROOT)
        self.assertEqual(set(actual) - set(config["skills"]), set())
        self.assertEqual(set(config["skills"]) - set(actual), set())


class GzhCallsiteAndRepackagingTests(unittest.TestCase):
    """A blocked skill must not be reachable outside a routing.yaml selection."""

    def test_a_callsite_referencing_a_blocked_skill_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = _root(raw, {"unknown": _entry(
                "unknown", "RIGHTS_UNKNOWN", "blocked", "hold")})
            runner = root / "scripts" / "runner.py"
            runner.parent.mkdir(parents=True, exist_ok=True)
            runner.write_text('cmd = ["skills/unknown/run.py"]\n', encoding="utf-8")
            result = checker.check(root)
            self.assertFalse(result["ok"])
            self.assertIn("callsite_blocked_skill", {f["id"] for f in result["failures"]})

    def test_a_callsite_referencing_an_allowed_skill_passes(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = _root(raw, {"owned": _entry("owned")})
            runner = root / "scripts" / "runner.py"
            runner.parent.mkdir(parents=True, exist_ok=True)
            runner.write_text('cmd = ["skills/owned/run.py"]\n', encoding="utf-8")
            self.assertTrue(checker.check(root)["ok"])

    def test_a_repackaged_held_skill_outside_vendor_fails(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = _root(raw, {"attested": _entry(
                "attested", "OWNER_ATTESTED", "allowed", "hold")})
            src = (root / "vendor" / "gzh-thinktank" / "gzh_未来智能" / "skills"
                   / "attested" / "SKILL.md")
            src.write_text("---\nname: attested\n---\nunique-body\n", encoding="utf-8")
            copy = root / "skills" / "copy" / "SKILL.md"
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_bytes(src.read_bytes())
            result = checker.check(root)
            self.assertFalse(result["ok"])
            self.assertIn("repackaged_skill", {f["id"] for f in result["failures"]})

    def test_a_copy_under_research_is_not_a_repackage(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = _root(raw, {"attested": _entry(
                "attested", "OWNER_ATTESTED", "allowed", "hold")})
            src = (root / "vendor" / "gzh-thinktank" / "gzh_未来智能" / "skills"
                   / "attested" / "SKILL.md")
            src.write_text("---\nname: attested\n---\nunique-body\n", encoding="utf-8")
            copy = root / "research" / "archive" / "x" / "SKILL.md"
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_bytes(src.read_bytes())
            self.assertTrue(checker.check(root)["ok"])

    def test_the_committed_gate_passes_on_the_real_tree(self) -> None:
        result = checker.check(checker.ROOT)
        self.assertTrue(result["ok"], result)


if __name__ == "__main__":
    unittest.main()
