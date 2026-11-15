#!/usr/bin/env python3
"""Tests for the single pin registry.

What this pins down
-------------------
* **One truth.** ``runtime/easel-pins.json`` is the only place an engine's
  identity is written. No Python file under ``scripts/`` or ``src/`` may carry
  either engine's commit, so a future edit cannot reintroduce the drift that
  produced five separate records of one version.
* **A tag is not an identity.** An entry without a commit is rejected, because
  upstream replaced the v0.3.0 tag without changing the version number.
* **No fallback.** An unreadable registry makes resolution ``BLOCKED``. A
  fallback commit is exactly what let a stale constant verify the wrong tree.
* **The lock is a projection.** ``runtime/easel.lock.json`` must agree with the
  active engine; disagreeing is a failure, not a preference.

Run: python tests/test_easel_pins.py
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from contentops.easel import pins  # noqa: E402
import resolve_easel as rez  # noqa: E402
import verify_easel_runtime as ver  # noqa: E402

HEX40 = re.compile(r"^[0-9a-f]{40}$")

#: Files allowed to mention an engine commit without reading the registry.
#: They describe what a recorded screenshot visibly shows, so the value is a
#: historical fact about an image, not a source of the pin.
HISTORICAL_COMMIT_MENTIONS = {
    "scripts/audit_baseline_reproducibility.py",
}


def _write_registry(root: Path, engines: dict, **top) -> Path:
    path = pins.registry_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": pins.SCHEMA, "engines": engines, **top}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _engine(**over) -> dict:
    entry = {
        "role": "production",
        "repo": "https://github.com/ZJU-REAL/Easel.git",
        "tag": "v0.0.1",
        "commit": "a" * 40,
        "layout": "openclaw",
        "skill_root": "skills/openclaw",
        "root": ".runtime/easel",
    }
    entry.update(over)
    return entry


# --- registry shape ----------------------------------------------------------

def test_registry_loads_and_declares_two_engines():
    registry = pins.load()
    assert registry.path.name == "easel-pins.json", registry.path
    assert registry.active_id == "v0.2.1", registry.active_id
    assert set(registry.engines) == {"v0.2.1", "v0.3.0"}, sorted(registry.engines)
    assert registry.workbench_id == "v0.3.0", registry.workbench_id
    assert registry.active.role == "production"
    assert registry.engines["v0.3.0"].role == "candidate"


def test_every_engine_declares_a_full_commit():
    for engine in pins.load().engines.values():
        assert HEX40.match(engine.commit), (engine.engine_id, engine.commit)
        assert engine.commit != engine.tag, engine.engine_id
        assert engine.identity.endswith(engine.commit[:12]), engine.identity


def test_engine_without_a_commit_is_rejected():
    with tempfile.TemporaryDirectory() as td:
        _write_registry(Path(td), {"v9": _engine(commit="")}, active="v9")
        try:
            pins.load(td)
        except pins.PinError as exc:
            assert "missing commit" in str(exc), str(exc)
        else:
            raise AssertionError("a tag-only entry was accepted as an identity")


def test_duplicate_commit_is_rejected():
    with tempfile.TemporaryDirectory() as td:
        _write_registry(
            Path(td),
            {"a": _engine(), "b": _engine(tag="v0.0.2")},
            active="a",
        )
        try:
            pins.load(td)
        except pins.PinError as exc:
            assert "one commit must map to one engine" in str(exc), str(exc)
        else:
            raise AssertionError("two engines sharing a commit were accepted")


def test_absolute_root_is_rejected():
    with tempfile.TemporaryDirectory() as td:
        _write_registry(
            Path(td),
            {"a": _engine(root="D:/somewhere/easel")},
            active="a",
        )
        try:
            pins.load(td)
        except pins.PinError as exc:
            assert "repository-relative" in str(exc), str(exc)
        else:
            raise AssertionError("an absolute install root was committed")


def test_undeclared_active_and_workbench_are_rejected():
    with tempfile.TemporaryDirectory() as td:
        _write_registry(Path(td), {"a": _engine()}, active="nope")
        try:
            pins.load(td)
        except pins.PinError as exc:
            assert "active 'nope'" in str(exc), str(exc)
        else:
            raise AssertionError("an undeclared active engine was accepted")

    with tempfile.TemporaryDirectory() as td:
        _write_registry(Path(td), {"a": _engine()}, active="a", workbench_engine="b")
        try:
            pins.load(td)
        except pins.PinError as exc:
            assert "workbench_engine 'b'" in str(exc), str(exc)
        else:
            raise AssertionError("an undeclared workbench engine was accepted")


def test_missing_registry_raises_instead_of_defaulting():
    with tempfile.TemporaryDirectory() as td:
        try:
            pins.load(td)
        except pins.PinError as exc:
            assert "pin registry missing" in str(exc), str(exc)
            assert "no fallback" in str(exc) or "fallback commit" in str(exc), str(exc)
        else:
            raise AssertionError("a missing registry produced a default pin")


# --- single source in code ---------------------------------------------------

def test_no_engine_commit_is_hardcoded_in_code():
    engine_commits = {e.commit for e in pins.load().engines.values()}
    offenders: list[str] = []
    for sub in ("scripts", "src"):
        for path in (ROOT / sub).rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if rel in HISTORICAL_COMMIT_MENTIONS:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for commit in engine_commits:
                if commit in text:
                    offenders.append(f"{rel} carries {commit[:12]}")
    assert not offenders, "hardcoded engine identity: " + "; ".join(sorted(offenders))


def test_verifier_defaults_follow_the_registry():
    active = pins.active()
    assert ver.PINNED_COMMIT == active.commit, (ver.PINNED_COMMIT, active.commit)
    assert ver.PINNED_TAG == active.tag, (ver.PINNED_TAG, active.tag)


def test_workbench_identity_follows_the_registry():
    from contentops.easel import agent_workspace

    declared = pins.workbench()
    assert agent_workspace.WORKBENCH_COMMIT == declared.commit
    assert agent_workspace.WORKBENCH_REPO == declared.repo


# --- the lock is a projection ------------------------------------------------

def test_lock_projects_the_active_engine():
    lock = json.loads((ROOT / "runtime" / "easel.lock.json").read_text(encoding="utf-8"))
    active = pins.active()
    assert lock["tag"] == active.tag, (lock["tag"], active.tag)
    assert lock["commit"] == active.commit, (lock["commit"], active.commit)
    assert lock.get("derived_from") == "runtime/easel-pins.json", lock.get("derived_from")


# --- fail closed at the resolution boundary ----------------------------------

def test_unreadable_registry_blocks_resolution():
    def explode(*_args, **_kwargs):
        raise pins.PinError("pin registry missing: fixture")

    with mock.patch.object(rez, "load_pin", explode):
        result = rez.resolve_easel()
    assert result["status"] == "BLOCKED", result
    assert any("PINS_UNREADABLE" in r for r in result["reasons"]), result["reasons"]
    assert "no fallback pin" in result["remedy"], result["remedy"]


def test_resolution_reports_the_engine_it_used():
    result = rez.resolve_easel()
    assert result["status"] == "OK", result
    active = pins.active()
    assert result["engine_id"] == active.engine_id, result
    assert result["commit"] == active.commit, result
    assert result["layout"] == active.layout, result


def test_verifier_refuses_without_a_pin():
    with mock.patch.object(ver, "PINNED_COMMIT", None):
        result = ver.verify(ROOT / ".runtime" / "easel", commit=None)
    assert result["status"] == "UNVERIFIED", result
    assert "pin registry unreadable" in result["reason"], result["reason"]


# --- runner ------------------------------------------------------------------

TESTS = [value for name, value in sorted(globals().items())
         if name.startswith("test_") and callable(value)]


def main() -> int:
    failures = 0
    for test in TESTS:
        try:
            test()
        except Exception as exc:  # noqa: BLE001 - a test runner reports, it does not raise
            failures += 1
            print(f"FAIL {test.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"ok   {test.__name__}")
    print(f"{len(TESTS) - failures}/{len(TESTS)} ok")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
