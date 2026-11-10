#!/usr/bin/env python3
"""Tests for the D7 governance guardrails. Pure Python, no subprocess/network."""
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


registry_check = load("check_branch_registry")
pr_size = load("check_pr_size")


class TestBranchRegistry(unittest.TestCase):
    def setUp(self):
        self.good = {
            "schema": "contentops.branch-registry/v1",
            "policy": {"persistent": ["main"], "max_age_days": 30},
            "branches": [
                {"name": "main", "pr": None, "created": None, "purpose": "default",
                 "status": "persistent", "expires": None},
                {"name": "feat/example", "pr": 999, "created": "2026-11-01",
                 "purpose": "example work", "status": "active_draft", "expires": "2026-12-31"},
            ],
        }

    def test_valid_registry_passes(self):
        self.assertEqual(registry_check.validate(self.good, date(2026, 11, 10)), [])

    def test_missing_pr_for_non_persistent_fails(self):
        self.good["branches"][1]["pr"] = None
        self.assertTrue(any("missing pr" in e for e in registry_check.validate(self.good, date(2026, 11, 10))))

    def test_expired_entry_fails(self):
        self.assertTrue(any("EXPIRED" in e for e in registry_check.validate(self.good, date(2027, 1, 1))))

    def test_archived_entry_needs_no_pr(self):
        self.good["branches"].append({
            "name": "archive/example", "pr": None, "created": "2026-11-10",
            "purpose": "worktree salvage", "status": "archived", "expires": "2026-12-31",
        })
        self.assertEqual(registry_check.validate(self.good, date(2026, 11, 11)), [])

    def test_archived_entry_still_needs_expiry(self):
        self.good["branches"].append({
            "name": "archive/example", "pr": None, "created": "2026-11-10",
            "purpose": "worktree salvage", "status": "archived", "expires": None,
        })
        self.assertTrue(any("missing expires" in e for e in
                            registry_check.validate(self.good, date(2026, 11, 11))))

    def test_wrong_persistent_policy_fails(self):
        self.good["policy"]["persistent"] = ["develop"]
        self.assertTrue(any("persistent" in e for e in registry_check.validate(self.good, date(2026, 11, 10))))

    def test_duplicate_and_main_missing(self):
        self.good["branches"].append(dict(self.good["branches"][1]))
        self.assertTrue(any("duplicate" in e for e in registry_check.validate(self.good, date(2026, 11, 10))))
        self.good["branches"] = [self.good["branches"][1]]
        self.assertTrue(any("main is not registered" in e for e in registry_check.validate(self.good, date(2026, 11, 10))))

    def test_cli_exit_code(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "registry.json"
            p.write_text(json.dumps(self.good), encoding="utf-8")
            result = registry_check.validate(json.loads(p.read_text(encoding="utf-8")), date(2026, 11, 10))
            self.assertEqual(result, [])


class TestPrSize(unittest.TestCase):
    LOG = """@@@aaa111
scripts/m5_production.py
tests/test_a.py
@@@bbb222
scripts/m5_production.py
@@@ccc333
docs/README.md
"""

    def test_metrics(self):
        m = pr_size.analyze(self.LOG)
        self.assertEqual(m["commits"], 3)
        self.assertEqual(m["unique_files"], 3)
        self.assertEqual(m["cross_group_commits"], 1)
        self.assertEqual(m["hot_file_max"], 2)
        self.assertEqual(m["hot_file"], "scripts/m5_production.py")

    def test_empty_stream(self):
        self.assertEqual(pr_size.analyze("")["commits"], 0)

    def test_threshold_breach_detected(self):
        big = {"commits": 75, "unique_files": 157, "cross_group_ratio": 0.76, "hot_file_max": 35}
        self.assertEqual(len(pr_size.breaches(big)), 4)
        self.assertEqual(pr_size.breaches({"commits": 2, "unique_files": 3,
                                           "cross_group_ratio": 0.0, "hot_file_max": 1}), [])

    def test_group_mapping(self):
        self.assertEqual(pr_size.group_of("tests/test_x.py"), "TESTS")
        self.assertEqual(pr_size.group_of(".github/workflows/ci.yml"), "CI")
        self.assertEqual(pr_size.group_of("README.md"), "OTHER")


if __name__ == "__main__":
    unittest.main(verbosity=2)
