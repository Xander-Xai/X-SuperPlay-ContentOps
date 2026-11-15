#!/usr/bin/env python3
"""Tests for the engine switcher: what it refuses, and what it records.

A switch tool that only proves the happy path is worse than no tool: the damage
comes from the paths where it proceeds when it should not. So these tests are
weighted towards refusals — an engine that is not installed, one that fails
verification, a dry run that must not write, and an install that would overwrite
something already there.

Everything runs against a temporary repository root; nothing here touches the
real `runtime/easel-pins.json`, and no network call is made.

Run: python tests/test_easel_engine.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import easel_engine as engine_tool  # noqa: E402
from contentops.easel import pins  # noqa: E402

COMMIT_A = "a" * 40
COMMIT_B = "b" * 40

# Captured before any patching: the patched loader must not call itself.
_REAL_LOAD = pins.load


def _engine(engine_id: str, commit: str, role: str, root: str, layout: str) -> pins.Engine:
    return pins.Engine(
        engine_id=engine_id, role=role, repo="https://github.com/ZJU-REAL/Easel.git",
        tag=engine_id, commit=commit, layout=layout, skill_root=f"skills/{layout}",
        root=root, installed=True, tree_sha256=None, blob_count=None,
        blob_count_basis="", license_spdx="Apache-2.0", repo_id="ZJU-REAL/Easel",
        agpl_vendored=(), note="", raw={},
    )


class _Fixture:
    """A temporary repository root with a registry, a lock and two trees."""

    def __init__(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "runtime").mkdir()
        self.a = _engine("v0.2.1", COMMIT_A, "rollback", ".runtime/a", "openclaw")
        self.b = _engine("v0.3.0", COMMIT_B, "production", ".runtime/b", "builtin")
        self.registry_path = self.root / "runtime" / "easel-pins.json"
        self.lock_path = self.root / "runtime" / "easel.lock.json"
        self.receipt_path = self.root / "runtime" / "easel-engine-switch.json"
        self._write_registry("v0.3.0")

    def _write_registry(self, active: str) -> None:
        self.registry_path.write_text(json.dumps({
            "schema": pins.SCHEMA,
            "active": active,
            "workbench_engine": "v0.3.0",
            "engines": {e.engine_id: {"role": e.role, "repo": e.repo, "tag": e.tag,
                                      "commit": e.commit, "layout": e.layout,
                                      "skill_root": e.skill_root, "root": e.root,
                                      "repo_id": e.repo_id} for e in (self.a, self.b)},
        }, indent=2), encoding="utf-8")
        self.lock_path.write_text(json.dumps({
            "repo": self.a.repo, "tag": self.a.tag, "commit": self.a.commit,
        }, indent=2), encoding="utf-8")

    def make_tree(self, engine: pins.Engine) -> None:
        (self.root / engine.root).mkdir(parents=True, exist_ok=True)

    def registry(self) -> pins.Registry:
        return _REAL_LOAD(self.root)

    def patched(self):
        fixture = self

        class _Ctx:
            def __enter__(self):
                self._stack = []
                for target, attr, value in [
                    (engine_tool, "ROOT", fixture.root),
                    (engine_tool, "REGISTRY", fixture.registry_path),
                    (engine_tool, "LOCK", fixture.lock_path),
                    (engine_tool, "SWITCH_RECEIPT", fixture.receipt_path),
                    (engine_tool.pins, "load",
                     lambda root=None: _REAL_LOAD(fixture.root)),
                    (engine_tool.pins, "get",
                     lambda engine_id, root=None: _REAL_LOAD(fixture.root).engines[engine_id]),
                ]:
                    patcher = mock.patch.object(target, attr, value)
                    patcher.start()
                    self._stack.append(patcher)
                return fixture

            def __exit__(self, *exc):
                for patcher in reversed(self._stack):
                    patcher.stop()
                return False

        return _Ctx()

    def close(self) -> None:
        self.tmp.cleanup()


def _args(**kwargs):
    base = {"engine": None, "json": True, "dry_run": False, "source": None}
    base.update(kwargs)
    return mock.Mock(**base)


# --- switch refusals ---------------------------------------------------------

def test_switch_refuses_an_engine_that_is_not_installed():
    fixture = _Fixture()
    try:
        with fixture.patched():
            code = engine_tool.cmd_switch(_args(engine="v0.2.1"))
        assert code == 4, code
        assert fixture.registry().active_id == "v0.3.0", "registry must not change"
        assert not fixture.receipt_path.exists(), "a refusal must leave no receipt"
    finally:
        fixture.close()


def test_switch_refuses_an_engine_that_fails_verification():
    fixture = _Fixture()
    try:
        fixture.make_tree(fixture.a)
        with fixture.patched(), mock.patch.object(
                engine_tool, "_verify", return_value={"status": "MISMATCH",
                                                      "reason": "one blob differs"}):
            code = engine_tool.cmd_switch(_args(engine="v0.2.1"))
        assert code == 5, code
        assert fixture.registry().active_id == "v0.3.0"
        assert not fixture.receipt_path.exists()
    finally:
        fixture.close()


def test_dry_run_writes_nothing():
    fixture = _Fixture()
    try:
        fixture.make_tree(fixture.a)
        before_lock = fixture.lock_path.read_text(encoding="utf-8")
        with fixture.patched(), mock.patch.object(
                engine_tool, "_verify", return_value={"status": "VERIFIED"}):
            code = engine_tool.cmd_switch(_args(engine="v0.2.1", dry_run=True))
        assert code == 0, code
        assert fixture.registry().active_id == "v0.3.0", "dry run must not switch"
        assert fixture.lock_path.read_text(encoding="utf-8") == before_lock
        assert not fixture.receipt_path.exists()
    finally:
        fixture.close()


def test_switching_to_the_active_engine_is_a_no_op():
    fixture = _Fixture()
    try:
        with fixture.patched():
            code = engine_tool.cmd_switch(_args(engine="v0.3.0"))
        assert code == 0, code
        assert not fixture.receipt_path.exists(), "a no-op is not a recorded switch"
    finally:
        fixture.close()


# --- switch success ----------------------------------------------------------

def test_switch_rewrites_the_pointer_derives_the_lock_and_records_it():
    fixture = _Fixture()
    try:
        fixture.make_tree(fixture.a)
        fixture.make_tree(fixture.b)
        with fixture.patched(), mock.patch.object(
                engine_tool, "_verify",
                return_value={"status": "VERIFIED", "method": "git_head",
                              "matched": None, "expected_commit": COMMIT_A}):
            code = engine_tool.cmd_switch(_args(engine="v0.2.1"))
            assert code == 0, code
            # A second switch back must append, not replace, the history.
            code = engine_tool.cmd_switch(_args(engine="v0.3.0"))
            assert code == 0, code
        registry = fixture.registry()
        assert registry.active_id == "v0.3.0"
        lock = json.loads(fixture.lock_path.read_text(encoding="utf-8"))
        assert lock["commit"] == COMMIT_B, lock
        assert lock["derived_from"] == "runtime/easel-pins.json"
        receipt = json.loads(fixture.receipt_path.read_text(encoding="utf-8"))
        assert receipt["current"] == "v0.3.0"
        assert [entry["to"] for entry in receipt["history"]] == ["v0.2.1", "v0.3.0"], receipt
        assert all(entry["verification"]["status"] == "VERIFIED"
                   for entry in receipt["history"])
    finally:
        fixture.close()


# --- install refusals --------------------------------------------------------

def test_install_refuses_a_non_empty_target():
    fixture = _Fixture()
    try:
        tree = fixture.root / fixture.a.root
        tree.mkdir(parents=True)
        (tree / "pyproject.toml").write_text("existing", encoding="utf-8")
        with fixture.patched():
            code = engine_tool.cmd_install(
                _args(engine="v0.2.1", source=str(fixture.root)))
        assert code == 4, code
        assert (tree / "pyproject.toml").read_text(encoding="utf-8") == "existing"
    finally:
        fixture.close()


def test_install_refuses_a_source_that_does_not_match_the_index():
    fixture = _Fixture()
    try:
        source = fixture.root / "source"
        source.mkdir()
        (source / "pyproject.toml").write_text("different bytes", encoding="utf-8")
        index = {"commit": COMMIT_A, "files": {"pyproject.toml": "0" * 40}}
        (fixture.root / "runtime" / "easel-workbench-upstream-tree.json").write_text(
            json.dumps(index), encoding="utf-8")
        with fixture.patched():
            code = engine_tool.cmd_install(
                _args(engine="v0.2.1", source=str(source)))
        assert code == 5, code
        assert not (fixture.root / fixture.a.root).exists(), "a refusal must not half-install"
    finally:
        fixture.close()


# --- runner ------------------------------------------------------------------

TESTS = [value for name, value in sorted(globals().items())
         if name.startswith("test_") and callable(value)]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
        except Exception as exc:  # noqa: BLE001 - a runner reports, it does not raise
            failures += 1
            print(f"FAIL {test.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"ok   {test.__name__}")
    print(f"{len(TESTS) - failures}/{len(TESTS)} ok")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
