#!/usr/bin/env python3
"""Tests for the documentation freshness mechanism.

Two things are covered:

* ``scripts/check_doc_freshness.py`` — marker parsing, staleness verdicts and
  Tier-1 coverage, driven through ``evaluate()`` with injected inputs (no git,
  no network), plus one run against the real tree.
* the README direction switch in ``scripts/check_i18n.py`` — README is the
  Chinese original and ``README.en.md`` is its English mirror, and a second
  Chinese copy is rejected.

Pure Python, no network, no paid call.
"""

import contextlib
import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves annotations through sys.modules[cls.__module__], so the
    # module has to be registered before exec_module runs.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


freshness = _load("check_doc_freshness")
i18n = _load("check_i18n")


def reader(mapping):
    return lambda rel: mapping.get(rel)


def plain_mirror(rel):
    return {"README.md": "README.en.md"}.get(rel, "")


def changes(mapping):
    """mapping: tuple(paths) -> list of (sha, date, subject)."""
    return lambda paths, since: mapping.get(tuple(paths), [])


TRACK = [{"doc": "docs/X.md", "code": ["src/"]}]


class MarkerParsingTests(unittest.TestCase):
    def test_english_marker(self):
        self.assertEqual(
            freshness.parse_marker("# X\n\n> Last verified: 2026-11-12 on `main`."),
            "2026-11-12")

    def test_chinese_marker_with_fullwidth_colon(self):
        self.assertEqual(
            freshness.parse_marker("# X\n\n> 最后验证：2026-11-12，`main` 的 `c1da6dd`。"),
            "2026-11-12")

    def test_status_verified_and_last_updated(self):
        self.assertEqual(freshness.parse_marker("> Status verified: 2026-11-01 on main"), "2026-11-01")
        self.assertEqual(freshness.parse_marker("> Last updated: 2026-10-31"), "2026-10-31")

    def test_regenerated_form_with_prose_between_colon(self):
        self.assertEqual(
            freshness.parse_marker("> Last regenerated from the registry: 2026-11-12, main."),
            "2026-11-12")
        self.assertEqual(
            freshness.parse_marker("> 最后按注册表重生成：2026-11-12，`main`。"),
            "2026-11-12")

    def test_missing_marker(self):
        self.assertIsNone(freshness.parse_marker("# X\n\nNo date here.\n"))

    def test_marker_below_the_scan_window_is_ignored(self):
        text = "\n".join(["# X", ""] + ["filler"] * 60 + ["> Last verified: 2026-11-12"])
        self.assertIsNone(freshness.parse_marker(text))

    def test_invalid_date_rejected(self):
        self.assertFalse(freshness.is_valid_date("2026-13-01"))
        self.assertFalse(freshness.is_valid_date("12-11-2026"))
        self.assertTrue(freshness.is_valid_date("2026-11-12"))


class EvaluateTests(unittest.TestCase):
    def test_clean_when_no_later_commits(self):
        findings = freshness.evaluate(
            TRACK, reader({"docs/X.md": "> Last verified: 2026-11-12"}),
            plain_mirror, changes({}), "2026-11-12")
        self.assertEqual(findings, [])

    def test_stale_when_code_moved_after_the_date(self):
        findings = freshness.evaluate(
            TRACK, reader({"docs/X.md": "> Last verified: 2026-11-01"}),
            plain_mirror,
            changes({("src/",): [("abc1234", "2026-11-11", "feat: add delivery")]}),
            "2026-11-12")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].level, "STALE")
        # The failure must name the commit: a bare "stale" invites a date bump.
        self.assertIn("abc1234", findings[0].detail)
        self.assertIn("feat: add delivery", findings[0].detail)

    def test_missing_marker_is_an_error(self):
        findings = freshness.evaluate(
            TRACK, reader({"docs/X.md": "# X\n\nno date\n"}),
            plain_mirror, changes({}), "2026-11-12")
        self.assertEqual(findings[0].level, "ERROR")
        self.assertIn("verification line", findings[0].detail)

    def test_far_future_date_is_an_error(self):
        findings = freshness.evaluate(
            TRACK, reader({"docs/X.md": "> Last verified: 2027-01-01"}),
            plain_mirror, changes({}), "2026-11-12")
        self.assertEqual(findings[0].level, "ERROR")
        self.assertIn("ahead of the runner date", findings[0].detail)

    def test_one_day_of_local_clock_skew_is_tolerated(self):
        # An author in UTC+8 writing at 04:00 local time is one calendar day ahead
        # of the UTC runner. That is a real date, not a time bomb.
        findings = freshness.evaluate(
            TRACK, reader({"docs/X.md": "> Last verified: 2026-11-12"}),
            plain_mirror, changes({}), "2026-11-11")
        self.assertEqual(findings, [])

    def test_two_days_ahead_is_still_rejected(self):
        findings = freshness.evaluate(
            TRACK, reader({"docs/X.md": "> Last verified: 2026-11-13"}),
            plain_mirror, changes({}), "2026-11-11")
        self.assertEqual(findings[0].level, "ERROR")

    def test_pair_date_mismatch_is_an_error(self):
        findings = freshness.evaluate(
            TRACK,
            reader({"docs/X.md": "> Last verified: 2026-11-12",
                    "docs/X.zh-CN.md": "> 最后验证：2026-11-10"}),
            lambda rel: "docs/X.zh-CN.md" if rel == "docs/X.md" else "",
            changes({}), "2026-11-12")
        self.assertEqual(len(findings), 1)
        self.assertIn("pair date mismatch", findings[0].detail)

    def test_mirror_without_marker_is_tolerated(self):
        findings = freshness.evaluate(
            TRACK,
            reader({"docs/X.md": "> Last verified: 2026-11-12",
                    "docs/X.zh-CN.md": "# X (no marker)"}),
            lambda rel: "docs/X.zh-CN.md" if rel == "docs/X.md" else "",
            changes({}), "2026-11-12")
        self.assertEqual(findings, [])

    def test_missing_tracked_doc_is_an_error(self):
        findings = freshness.evaluate(
            TRACK, reader({}), plain_mirror, changes({}), "2026-11-12")
        self.assertEqual(findings[0].level, "ERROR")
        self.assertIn("missing", findings[0].detail)

    def test_track_without_code_paths_is_only_date_checked(self):
        findings = freshness.evaluate(
            [{"doc": "docs/X.md", "code": []}],
            reader({"docs/X.md": "> Last verified: 2026-11-01"}),
            plain_mirror, changes({}), "2026-11-12")
        self.assertEqual(findings, [])


class CoverageTests(unittest.TestCase):
    def test_unclassified_tier1_doc_is_reported(self):
        gaps = freshness.coverage_gaps(
            ["docs/A.md", "docs/B.md"], [{"doc": "docs/A.md", "code": []}], [])
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0].doc, "docs/B.md")

    def test_exempt_doc_counts_as_classified(self):
        gaps = freshness.coverage_gaps(
            ["docs/B.md"], [], [{"doc": "docs/B.md", "reason": "navigation only"}])
        self.assertEqual(gaps, [])


class RealRepositoryTests(unittest.TestCase):
    def _silent(self, fn, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = fn(*args)
        return code, buf.getvalue()

    def test_config_covers_every_tier1_doc(self):
        config = freshness.load_config()
        gaps = freshness.coverage_gaps(
            i18n.TIER1_DOCS, config.get("tracks") or [], config.get("exempt") or [])
        self.assertEqual(gaps, [])

    def test_every_tracked_doc_exists_and_declares_a_date(self):
        config = freshness.load_config()
        for track in config.get("tracks") or []:
            doc = ROOT / track["doc"]
            self.assertTrue(doc.is_file(), f"tracked doc missing: {track['doc']}")
            self.assertIsNotNone(
                freshness.parse_marker(doc.read_text(encoding="utf-8")),
                f"no verification line: {track['doc']}")

    def test_exemptions_carry_a_reason(self):
        config = freshness.load_config()
        for entry in config.get("exempt") or []:
            self.assertTrue(str(entry.get("reason", "")).strip(),
                            f"exemption without a reason: {entry.get('doc')}")

    def test_repository_is_current(self):
        code, out = self._silent(freshness.main, [])
        self.assertEqual(code, 0, out)

    def test_readme_is_chinese_primary(self):
        self.assertEqual(i18n._mirror_rel("README.md"), "README.en.md")
        self.assertFalse((ROOT / "README.zh-CN.md").exists(),
                         "a second Chinese copy must not come back")
        self.assertTrue((ROOT / "README.en.md").is_file())
        code, out = self._silent(i18n.main)
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
