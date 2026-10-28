"""OpenClaw bridge tests.

Guards the behaviours that broke or would break on this machine:

1. ``agent exec`` interleaves ANSI log lines around the JSON envelope, so a
   naive ``json.loads(stdout)`` never parses.
2. CLI output bytes can be the OEM codepage, so undecodable bytes fall back to
   GBK instead of becoming replacement characters.
3. Every path leaves a receipt — a failed turn is evidence, not an exception.
4. Committed receipts carry no absolute paths, and ``skill_route`` is the
   account DNA's declaration, not a guess.

Run: python tests/test_openclaw_agent.py
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import openclaw_agent  # noqa: E402
from openclaw_agent import (  # noqa: E402
    _decode,
    _logical,
    _parse_envelope,
    _receipt_route,
    declared_route,
    run_agent,
)

ENVELOPE = ('{"ok": true, "status": "ok", "final": "PONG", "sessionId": "s1",'
            ' "model": "m", "usage": {"input": 1}}')


def test_decode_utf8() -> None:
    assert _decode("中文".encode("utf-8")) == "中文"


def test_decode_falls_back_to_gbk_for_non_utf8_bytes() -> None:
    # 中 in CP936 is b'\xd6\xd0'; 0xd0 is not a valid UTF-8 continuation after
    # the 0xd6 lead, so strict UTF-8 rejects it and the GBK fallback runs.
    raw = "中".encode("gbk")
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    else:  # pragma: no cover - guards the test's own premise
        raise AssertionError("fixture bytes are valid UTF-8; test is meaningless")
    assert _decode(raw) == "中"


def test_decode_empty() -> None:
    assert _decode(None) == ""
    assert _decode(b"") == ""


def test_parse_envelope_ignores_ansi_and_trailing_logs() -> None:
    stdout = (
        "\x1b[33m[agent/embedded]\x1b[39m tool-search: cataloged 39 tools\n"
        + ENVELOPE
        + "\n\x1b[34m[session-sqlite]\x1b[39m reclamation worker retired\n"
    )
    parsed = _parse_envelope(stdout)
    assert parsed is not None
    assert parsed["final"] == "PONG"


def test_parse_envelope_skips_non_envelope_objects() -> None:
    parsed = _parse_envelope('{"not": "an envelope"}\n' + ENVELOPE)
    assert parsed is not None and parsed["sessionId"] == "s1"


def test_parse_envelope_returns_none_when_absent() -> None:
    assert _parse_envelope("[warn] nothing here\n") is None


def _route_bases_available() -> bool:
    """A clean checkout has no Easel runtime (gitignored) or shared store.

    Route resolution legitimately cannot be tested there, so those tests no-op
    rather than fail; the suite still exits 0, which is this repo's contract for
    a suite that skips for an absent fixture.
    """
    bases = openclaw_agent._route_bases()
    return bases.get("catalog") is not None and bases.get("shared") is not None


def test_logical_never_returns_an_absolute_path() -> None:
    assert _logical(ROOT / "docs" / "INDEX.md") == "repo://docs/INDEX.md"
    assert _logical(ROOT, None) == "repo://"
    outside = _logical(Path("C:/Windows/System32/notepad.exe"), None)
    assert not re.match(r"^[A-Za-z]:", outside or ""), outside
    assert outside == "external://notepad.exe"


def test_receipt_route_uses_the_documented_keys() -> None:
    route = {"step": "captions", "skill": "auto-subtitle",
             "script": "skills/shared/scripts/subtitle_ops.py",
             "path_base": "catalog", "resolved": True, "why": "owns the burn"}
    doc = _receipt_route(route, None)
    assert doc["name"] == "auto-subtitle"
    assert doc["script"] == "skills/shared/scripts/subtitle_ops.py"
    assert doc["why"] == "owns the burn"


def test_receipt_route_records_why_a_route_is_missing() -> None:
    doc = _receipt_route(None, "account 'x' declares no skill_route for step 'nope'")
    assert doc["name"] is None
    assert "declares no skill_route" in doc["why"]


def test_declared_route_resolves_the_caption_owner() -> None:
    if not _route_bases_available():
        return
    route = declared_route("x-superplay-1024", "captions")
    assert route is not None, "the 1024 DNA must declare a captions route"
    # The declaration must name the script that actually burns captions, not the
    # upstream auto-subtitle skill this pipeline never calls.
    assert route["skill"] == "assemble_easel"
    assert route["script"] == "scripts/assemble_easel.py"
    assert route["path_base"] == "repo"
    assert route["resolved"] is True, route["remedy"]


def test_declared_route_covers_every_path_base() -> None:
    if not _route_bases_available():
        return
    seen = set()
    for step in ("captions", "compose", "qc", "copy_orchestration", "broll_plan"):
        route = declared_route("x-superplay-1024", step)
        assert route is not None, f"no declared route for {step}"
        assert route["resolved"] is True, (step, route["remedy"])
        seen.add(route["path_base"])
    assert seen == {"catalog", "repo", "shared"}, seen


def test_declared_route_returns_none_for_an_undeclared_step() -> None:
    assert declared_route("x-superplay-1024", "no-such-step") is None


def test_missing_account_blocks_without_running_an_agent() -> None:
    with tempfile.TemporaryDirectory() as td:
        project = Path(td)
        res = run_agent("hi", stage="captions", project=project,
                        account="no-such-account")
        assert res["status"] == "BLOCKED", res
        assert "account DNA not found" in res["reason"]
        assert res["skill_route"]["name"] is None
        receipt = project / "receipts" / "openclaw-captions.json"
        assert receipt.is_file(), "a bad DNA must still leave a receipt"


def test_missing_openclaw_writes_blocked_receipt() -> None:
    original = openclaw_agent._openclaw_cmd

    def boom() -> list[str]:
        raise FileNotFoundError("openclaw CLI not found")

    openclaw_agent._openclaw_cmd = boom
    try:
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            res = run_agent("hi", stage="unit", project=project)
            assert res["status"] == "BLOCKED", res
            assert "openclaw CLI not found" in res["reason"]
            receipt_path = project / "receipts" / "openclaw-unit.json"
            assert receipt_path.is_file(), "a failed turn must still leave a receipt"
            text = receipt_path.read_text(encoding="utf-8")
            receipt = json.loads(text)
            assert receipt["human_review"] == "required"
            assert receipt["harness"]["profile"] == "easel"
            assert receipt["skill_route"]["name"] is None
            assert not re.search(r'"[A-Za-z]:[\\/]', text), \
                "committed receipts must not contain absolute paths"
    finally:
        openclaw_agent._openclaw_cmd = original


def test_receipts_without_a_project_stay_out_of_the_repo_root() -> None:
    with tempfile.TemporaryDirectory() as td:
        cwd = Path(td)
        original = openclaw_agent._openclaw_cmd
        openclaw_agent._openclaw_cmd = lambda: (_ for _ in ()).throw(FileNotFoundError("x"))
        try:
            run_agent("hi", stage="unit", cwd=cwd)
        finally:
            openclaw_agent._openclaw_cmd = original
        assert (cwd / ".openclaw" / "receipts" / "openclaw-unit.json").is_file()
        assert not (cwd / "receipts").exists(), "no-project runs must not create a root receipts/"


def main() -> int:
    failures = 0
    names = sorted(n for n in dir(sys.modules[__name__]) if n.startswith("test_"))
    for name in names:
        try:
            globals()[name]()
            print(f"PASS {name}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {name}: {exc}")
        except Exception as exc:  # noqa: BLE001 - report, never mask
            failures += 1
            print(f"ERROR {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(names)} tests, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
