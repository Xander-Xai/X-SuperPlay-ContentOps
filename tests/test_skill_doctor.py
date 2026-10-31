from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "scripts", ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import skill_route as sr  # noqa: E402


class SkillDoctorTests(unittest.TestCase):
    def test_doctor_reports_a_usable_catalog(self) -> None:
        report = sr.doctor()
        self.assertEqual(report["schema"], "contentops.skill-doctor/v1")
        self.assertTrue(report["ok"], report)
        self.assertGreater(report["total"], 0)
        self.assertEqual(report["unsafe_paths"], [])
        self.assertEqual(report["permission_declarations"]["total"], report["total"])

    def test_duplicates_are_reported_not_hidden(self) -> None:
        report = sr.doctor()
        for duplicate in report["duplicates"]:
            self.assertGreater(len(duplicate["copies"]), 1, duplicate)
            self.assertTrue(duplicate["name"])

    def test_resolve_returns_every_copy(self) -> None:
        entries = sr._all_skill_entries()
        self.assertTrue(entries)
        name = entries[0]["name"]
        found = sr.resolve_skill(name)
        self.assertTrue(found, name)
        for item in found:
            self.assertTrue(Path(item["resolved"]).exists(), item)

    def test_resolve_refuses_an_unknown_name(self) -> None:
        self.assertEqual(sr.resolve_skill("__contentops_missing_skill__"), [])
        self.assertEqual(sr.resolve_skill(""), [])

    def test_shared_entries_are_not_flagged_as_unsafe(self) -> None:
        report = sr.doctor()
        shared = report["shared"]
        if shared["exists"] and shared["skills"]:
            self.assertEqual(report["unsafe_paths"], [],
                             "a shared-store link is not an unsafe path")


def _write_skill(root: Path, rel: str, name: str, *, license: str = "",
                 body: str = "", tools: bool = False) -> Path:
    directory = root / rel
    directory.mkdir(parents=True, exist_ok=True)
    front = f"---\nname: {name}\ndescription: demo skill\n"
    if license:
        front += f"license: {license}\n"
    if tools:
        front += "allowed-tools: [read]\n"
    front += "---\n" + body
    path = directory / "SKILL.md"
    path.write_text(front, encoding="utf-8")
    return path


class SkillDoctorScopeTests(unittest.TestCase):
    def test_rights_archive_credentials_and_duplicates_are_reported(self) -> None:
        from unittest import mock
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            r1 = root / "r1"
            r2 = root / "r2"
            _write_skill(r1, "alpha", "alpha")
            _write_skill(r2, "alpha", "alpha")
            _write_skill(r1, "beta", "beta", license="AGPL-3.0")
            _write_skill(r1, "_archive/old", "old")
            _write_skill(r1, "gamma", "gamma", tools=True,
                         body="uses api_key and a subscription price\n")
            with mock.patch.object(sr, "CATALOG_ROOTS", (r1, r2)), \
                 mock.patch.object(sr, "SHARED_SKILL_ROOT", root / "absent"):
                report = sr.doctor()
            self.assertIn("alpha", report["rights"]["unknown"])
            self.assertIn("beta", report["rights"]["restricted"])
            self.assertIn("old", report["archived"])
            self.assertIn("gamma", report["credential_hints"])
            self.assertIn("gamma", report["paid_hints"])
            self.assertTrue(any(d["name"] == "alpha" for d in report["duplicates"]))
            self.assertFalse(report["execution"]["authorized"])
            self.assertEqual(report["execution"]["remaining_gate"], "#57")
            self.assertGreater(report["permission_declarations"]["declared"], 0)
            self.assertLess(report["permission_declarations"]["declared"], report["total"],
                            "the missing-permission case must not read as fully declared")

    def test_a_symlink_that_leaves_the_root_is_unsafe(self) -> None:
        import os
        from unittest import mock
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            r1 = root / "r1"
            outside = root / "outside"
            _write_skill(outside, "", "escape")
            try:
                os.symlink(outside, r1 / "escape", target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks are not available on this host")
            if not (r1 / "escape" / "SKILL.md").exists():
                self.skipTest("the host does not follow directory symlinks")
            with mock.patch.object(sr, "CATALOG_ROOTS", (r1,)), \
                 mock.patch.object(sr, "SHARED_SKILL_ROOT", root / "absent"):
                report = sr.doctor()
            self.assertTrue(report["unsafe_paths"], report)
            self.assertFalse(report["execution"]["authorized"])


if __name__ == "__main__":
    unittest.main()
