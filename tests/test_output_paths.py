#!/usr/bin/env python3
"""Tests for the output-root resolution.

Two properties matter, and they pull in opposite directions:

1. With ``CONTENTOPS_OUTPUT_ROOT`` unset -- which is what CI sees -- the
   product roots must be exactly where they were before this module existed.
   Anything else would silently relocate every receipt in the repository.
2. With it set, the products must leave the checkout, and the short
   ``projects/_local/<slug>`` form must keep resolving to the experiment it
   names.

Pure Python, no network, no subprocess.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops import paths  # noqa: E402


class DefaultLayoutTests(unittest.TestCase):
    """Unset means unchanged."""

    def setUp(self):
        patcher = mock.patch.dict(os.environ, {}, clear=False)
        patcher.start()
        os.environ.pop(paths.OUTPUT_ROOT_ENV, None)
        self.addCleanup(patcher.stop)
        # Keep the repository's own .env out of it: this suite is about the
        # environment, not about what the operator configured.
        previous = paths._env_loaded
        paths._env_loaded = True
        self.addCleanup(setattr, paths, "_env_loaded", previous)

    def test_roots_stay_inside_the_repository(self):
        self.assertEqual(paths.output_root(), None)
        self.assertFalse(paths.is_external())
        self.assertEqual(paths.workspace_root(), ROOT / "projects" / "_local")
        self.assertEqual(paths.deliverables_root(), ROOT / "outputs")
        self.assertEqual(paths.tmp_root(), ROOT / ".verify-tmp")

    def test_resolve_project_keeps_repository_paths(self):
        resolved = paths.resolve_project("projects/_local/demo")
        self.assertEqual(resolved, (ROOT / "projects" / "_local" / "demo").resolve())

    def test_relative_label_stays_relative_to_the_repository(self):
        label = paths.relative_label(ROOT / "projects" / "demo" / "receipts" / "x.json")
        self.assertEqual(label, "projects/demo/receipts/x.json")

    def test_scratch_candidates_names_the_historical_spelling_only(self):
        self.assertEqual(paths.scratch_candidates("m2/ab/a.wav"),
                         [".verify-tmp/m2/ab/a.wav"])

    def test_the_trusted_roots_are_the_repository_and_the_sandbox(self):
        self.assertEqual(paths.project_roots(),
                         [ROOT / "projects", ROOT / "projects" / "_local"])

    def test_a_baseline_belongs_to_the_repository(self):
        self.assertEqual(paths.trusted_project_root(ROOT / "projects" / "demo"),
                         (ROOT / "projects").resolve())


class TrustedRootTests(unittest.TestCase):
    """Which directories a project may live in.

    A guard that only knew about the repository would refuse every
    experiment once the sandbox moves out of the checkout, which is the
    whole point of moving it out.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        patcher = mock.patch.dict(
            os.environ, {paths.OUTPUT_ROOT_ENV: str(self.root)}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        previous = paths._env_loaded
        paths._env_loaded = True
        self.addCleanup(setattr, paths, "_env_loaded", previous)

    def test_project_roots_name_the_repository_and_the_workspace(self):
        self.assertEqual(paths.project_roots(),
                         [ROOT / "projects", self.root / "workspace"])

    def test_a_baseline_belongs_to_the_repository(self):
        self.assertEqual(paths.trusted_project_root(ROOT / "projects" / "demo"),
                         (ROOT / "projects").resolve())

    def test_an_experiment_belongs_to_the_workspace(self):
        project = self.root / "workspace" / "demo-experiment"
        project.mkdir(parents=True)
        self.assertEqual(paths.trusted_project_root(project),
                         (self.root / "workspace").resolve())

    def test_an_unrelated_directory_belongs_to_nothing(self):
        outside = Path(self.tmp.name).resolve().parent / "elsewhere"
        self.assertIsNone(paths.trusted_project_root(outside))

    def test_the_checkout_root_can_be_overridden(self):
        """A test that patches the checkout root must see its own roots."""
        fake = Path(self.tmp.name).resolve() / "repo"
        (fake / "projects").mkdir(parents=True)
        self.assertEqual(paths.project_roots(fake),
                         [fake / "projects", self.root / "workspace"])
        self.assertEqual(paths.trusted_project_root(fake / "projects" / "x", fake),
                         (fake / "projects").resolve())


class ExternalRootTests(unittest.TestCase):
    """Configured means outside the checkout."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        patcher = mock.patch.dict(
            os.environ, {paths.OUTPUT_ROOT_ENV: str(self.root)}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        previous = paths._env_loaded
        paths._env_loaded = True
        self.addCleanup(setattr, paths, "_env_loaded", previous)

    def test_roots_follow_the_configured_root(self):
        self.assertEqual(paths.output_root(), self.root)
        self.assertTrue(paths.is_external())
        self.assertEqual(paths.workspace_root(), self.root / "workspace")
        self.assertEqual(paths.deliverables_root(), self.root / "deliverables")
        self.assertEqual(paths.tmp_root(), self.root / "_tmp")

    def test_every_product_root_is_outside_the_repository(self):
        for candidate in (paths.workspace_root(), paths.deliverables_root(),
                          paths.tmp_root()):
            self.assertFalse(candidate.is_relative_to(ROOT),
                             f"{candidate} is still inside the checkout")

    def test_resolve_project_redirects_the_short_form(self):
        slug = "demo-experiment"
        (self.root / "workspace" / slug).mkdir(parents=True)
        resolved = paths.resolve_project(f"projects/_local/{slug}")
        self.assertEqual(resolved, (self.root / "workspace" / slug).resolve())

    def test_resolve_project_leaves_a_missing_slug_alone(self):
        resolved = paths.resolve_project("projects/_local/not-there")
        self.assertEqual(resolved, (ROOT / "projects" / "_local" / "not-there").resolve())

    def test_resolve_project_keeps_absolute_paths(self):
        target = self.root / "workspace" / "absolute-demo"
        target.mkdir(parents=True)
        self.assertEqual(paths.resolve_project(str(target)), target.resolve())

    def test_relative_label_is_relative_to_the_output_root(self):
        label = paths.relative_label(self.root / "workspace" / "demo" / "final.mp4")
        self.assertEqual(label, "workspace/demo/final.mp4")

    def test_relative_label_falls_back_to_absolute_outside_both_roots(self):
        outside = Path(self.tmp.name).resolve().parent / "elsewhere.txt"
        self.assertEqual(paths.relative_label(outside), outside.as_posix())

    def test_scratch_candidates_adds_the_configured_root(self):
        candidates = paths.scratch_candidates("m2/ab/a.wav")
        self.assertEqual(candidates[0], ".verify-tmp/m2/ab/a.wav")
        self.assertEqual(candidates[1],
                         (self.root / "_tmp" / "m2" / "ab" / "a.wav").as_posix())


if __name__ == "__main__":
    unittest.main()
