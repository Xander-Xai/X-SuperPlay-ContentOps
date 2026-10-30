from __future__ import annotations

import sys
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


if __name__ == "__main__":
    unittest.main()
