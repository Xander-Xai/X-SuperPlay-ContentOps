from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "scripts", ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import skill_route as sr  # noqa: E402


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


class SkillDoctorTests(unittest.TestCase):
    def test_doctor_on_this_checkout_is_honest_about_what_exists(self) -> None:
        report = sr.doctor()
        self.assertEqual(report["schema"], "contentops.skill-doctor/v1")
        # A clean CI checkout has no Easel runtime and no shared store. The
        # doctor must report that, not crash and not pretend a catalog exists.
        self.assertEqual(report["unsafe_paths"], [])
        self.assertIn("roots", report)
        self.assertEqual(len(report["roots"]), len(sr.CATALOG_ROOTS))
        if not report["total"]:
            self.assertFalse(report["ok"])
            self.assertIn("no catalog or shared skill was found", report["warnings"])

    def test_duplicates_are_reported_not_hidden(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            r1, r2 = root / "r1", root / "r2"
            _write_skill(r1, "alpha", "alpha")
            _write_skill(r2, "alpha", "alpha")
            with mock.patch.object(sr, "CATALOG_ROOTS", (r1, r2)), \
                 mock.patch.object(sr, "SHARED_SKILL_ROOT", root / "absent"):
                report = sr.doctor()
        self.assertEqual(len(report["duplicates"]), 1)
        self.assertEqual(report["duplicates"][0]["name"], "alpha")
        self.assertEqual({copy["source"] for copy in report["duplicates"][0]["copies"]},
                         {"r1", "r2"})
        self.assertTrue(report["ok"], report)

    def test_resolve_returns_every_copy(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            r1, r2 = root / "r1", root / "r2"
            _write_skill(r1, "alpha", "alpha")
            _write_skill(r2, "alpha", "alpha")
            with mock.patch.object(sr, "CATALOG_ROOTS", (r1, r2)), \
                 mock.patch.object(sr, "SHARED_SKILL_ROOT", root / "absent"):
                found = sr.resolve_skill("alpha")
                self.assertEqual(len(found), 2)
                for item in found:
                    self.assertTrue(Path(item["resolved"]).exists(), item)

    def test_resolve_refuses_an_unknown_name(self) -> None:
        self.assertEqual(sr.resolve_skill("__contentops_missing_skill__"), [])
        self.assertEqual(sr.resolve_skill(""), [])

    def test_shared_entries_are_not_flagged_as_unsafe(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            shared = root / "shared"
            _write_skill(shared, "delta", "delta")
            with mock.patch.object(sr, "CATALOG_ROOTS", ()), \
                 mock.patch.object(sr, "SHARED_SKILL_ROOT", shared):
                report = sr.doctor()
        self.assertEqual(report["unsafe_paths"], [])
        self.assertEqual(report["total"], 1)
        self.assertTrue(report["shared"]["exists"])


class SkillDoctorScopeTests(unittest.TestCase):
    def test_rights_archive_credentials_and_duplicates_are_reported(self) -> None:
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

    def test_a_duplicate_name_is_an_ambiguity_for_capability_resolution(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            r1, r2 = root / "r1", root / "r2"
            _write_skill(r1, "alpha", "alpha")
            _write_skill(r2, "alpha", "alpha")
            registry = {"schema": sr.REGISTRY_SCHEMA, "skills": [
                {"id": "alpha", "name": "alpha"},
                {"id": "alpha", "name": "alpha"},
            ]}
            with mock.patch.object(sr, "CATALOG_ROOTS", (r1, r2)), \
                 mock.patch.object(sr, "SHARED_SKILL_ROOT", root / "absent"):
                result = sr.resolve_capability("alpha", registry=registry)
        self.assertEqual(result["verdict"], sr.VERDICT_BLOCKED)
        self.assertEqual(result["reason"], sr.REASON_DUPLICATE_AMBIGUITY)


if __name__ == "__main__":
    unittest.main()
