#!/usr/bin/env python3
"""Tests for the offline governance ledger consistency check.

Pure Python, no network, no subprocess into the runtime. The suite builds a
throwaway repository tree so every failure mode is exercised against real
files rather than mocked strings in memory.
"""
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "check_governance_ledger", ROOT / "scripts" / "check_governance_ledger.py")
ledger = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ledger)

EN_TMPL = """# Current State

[English](CURRENT-STATE.md) | [简体中文](CURRENT-STATE.zh-CN.md)

> Last verified: {date} on `main` at `{sha}` (PR #154).

## Git

### Git — verified {section_date} (governance round 4)

| Property | Verified value |
|---|---|
| Default branch | `main` — protected @ `{section_sha}` (PR #154) |

### Git — verified 2026-11-10 evening

| Property | Verified value |
|---|---|
| Default branch | `main` @ `9bb66cee` |
"""

ZH_TMPL = """---
translation_of: docs/CURRENT-STATE.md
language: zh-CN
translation_status: synced
---

# 当前状态

[English](CURRENT-STATE.md) | [简体中文](CURRENT-STATE.zh-CN.md)

> 最后验证：{zh_date}，`main` 的 `{zh_sha}`（PR #154）。

## Git

### Git — {zh_section_date} 复核（治理第 4 轮）

| 属性 | 核验值 |
|---|---|
| 默认分支 | `main` @ `{zh_section_sha}`（PR #154） |

### Git — 2026-11-04 历史快照

| 属性 | 值 |
|---|---|
| 默认分支 | `main` @ `218c91d` |
"""

DEFAULTS = {
    "date": "2026-11-11",
    "sha": "bcd5dd1",
    "section_date": "2026-11-11",
    "section_sha": "bcd5dd1",
    "zh_date": "2026-11-11",
    "zh_sha": "bcd5dd1",
    "zh_section_date": "2026-11-11",
    "zh_section_sha": "bcd5dd1",
    "reg_date": "2026-11-11",
    "zh_snapshot": True,
}


def build(root, **overrides):
    cfg = dict(DEFAULTS)
    cfg.update(overrides)
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "config" / "governance").mkdir(parents=True, exist_ok=True)
    (root / "docs" / "CURRENT-STATE.md").write_text(EN_TMPL.format(**cfg), encoding="utf-8")
    zh = ZH_TMPL.format(**cfg)
    if not cfg["zh_snapshot"]:
        zh = "\n".join(line for line in zh.splitlines() if not line.startswith("### Git"))
    (root / "docs" / "CURRENT-STATE.zh-CN.md").write_text(zh, encoding="utf-8")
    (root / "config" / "governance" / "branch-registry.json").write_text(
        json.dumps({"verified_at": cfg["reg_date"] + "T02:10:00+08:00"}), encoding="utf-8")
    return root


class TestGovernanceLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def errors(self, **overrides):
        return ledger.validate(build(self.root, **overrides))

    def test_valid_ledger_passes(self):
        self.assertEqual(self.errors(), [])

    def test_header_sha_mismatch_with_snapshot_fails(self):
        errs = self.errors(section_sha="aaaaaaa")
        self.assertTrue(any("EN header SHA" in e for e in errs), errs)

    def test_zh_header_sha_mismatch_with_snapshot_fails(self):
        errs = self.errors(zh_section_sha="cafebabe")
        self.assertTrue(any("ZH header SHA" in e for e in errs), errs)

    def test_bilingual_date_mismatch_fails(self):
        errs = self.errors(zh_date="2026-11-10", zh_section_date="2026-11-10")
        self.assertTrue(any("verification date differs" in e for e in errs), errs)

    def test_bilingual_sha_mismatch_fails(self):
        errs = self.errors(zh_sha="deadbeef")
        self.assertTrue(any("header SHA differs" in e for e in errs), errs)

    def test_en_header_date_vs_snapshot_date_fails(self):
        errs = self.errors(section_date="2026-11-10")
        self.assertTrue(any("EN header date" in e for e in errs), errs)

    def test_missing_zh_snapshot_fails(self):
        errs = self.errors(zh_snapshot=False)
        self.assertTrue(any("ZH" in e and "snapshot" in e for e in errs), errs)

    def test_registry_date_mismatch_fails(self):
        errs = self.errors(reg_date="2026-11-10")
        self.assertTrue(any("registry verified_at date" in e for e in errs), errs)

    def test_missing_file_fails(self):
        (self.root / "docs").mkdir(parents=True, exist_ok=True)
        errs = ledger.validate(self.root)
        self.assertTrue(any("missing" in e for e in errs), errs)

    def test_cli_exit_codes(self):
        build(self.root)
        with mock.patch.object(sys, "argv", ["check_governance_ledger.py", "--root", str(self.root)]):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(ledger.main(), 0)
            self.assertIn("live GitHub state NOT verified", out.getvalue())
        build(self.root, reg_date="2026-11-10")
        with mock.patch.object(sys, "argv", ["check_governance_ledger.py", "--root", str(self.root)]):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(ledger.main(), 1)


class TestCompareHead(unittest.TestCase):
    """--compare-head is local and report-only: it never changes the exit code."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _git(self, sha):
        (self.root / ".git" / "refs" / "heads").mkdir(parents=True, exist_ok=True)
        (self.root / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        (self.root / ".git" / "refs" / "heads" / "main").write_text(sha + "\n", encoding="utf-8")

    def test_in_sync(self):
        build(self.root)
        self._git("bcd5dd1" + "0" * 33)
        _, ledger_sha, verdict = ledger.compare_head(self.root)
        self.assertEqual(ledger_sha, "bcd5dd1")
        self.assertEqual(verdict, "in sync")

    def test_differs(self):
        build(self.root)
        self._git("3" * 40)
        _, _, verdict = ledger.compare_head(self.root)
        self.assertIn("differs", verdict)

    def test_no_git_dir(self):
        build(self.root)
        _, _, verdict = ledger.compare_head(self.root)
        self.assertIn("unavailable", verdict)

    def test_cli_compare_head_is_report_only(self):
        build(self.root)
        self._git("4" * 40)
        with mock.patch.object(sys, "argv", [
                "check_governance_ledger.py", "--root", str(self.root), "--compare-head"]):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(ledger.main(), 0)
            self.assertIn("compare-head (local, report-only)", out.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
