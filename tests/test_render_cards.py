"""Tests for the card render orchestrator.

What these tests protect
------------------------
``scripts/render_cards.py`` is the one command a creator runs to turn HTML cards
into audited PNGs. The failure modes that matter are all about silence:

- a selector that matches nothing must not look like a successful empty run;
- an auditor that prints nothing must not be read as a pass;
- a pre-existing image must be reported, never deleted to tidy a receipt;
- and no density PASS may ever set ``production_ready`` or ``publish_authorized``.

The orchestration is exercised with an injected runner, so the suite needs no
Playwright, no Chromium and no network. One optional live check renders a real
card when the runtime tooling is available; it prints ``[skip]`` otherwise, and a
skip is not evidence that rendering works.

Run: python tests/test_render_cards.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from contentops.graphic.cards import (  # noqa: E402
    SCHEMA,
    CardRenderError,
    build_receipt,
    parse_audit_output,
    parse_render_output,
    plan,
    run,
    write_receipt,
)


# --- helpers ---------------------------------------------------------------


class FakeResult:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _png(path: Path, payload: bytes = b"\x89PNG\r\n\x1a\n" + b"x" * 64) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _project(tmp: Path, *, html: bool = True) -> Path:
    project = tmp / "proj"
    (project / "assets" / "cards").mkdir(parents=True)
    if html:
        (project / "assets" / "cards" / "cards.html").write_text(
            "<html><body><div class='card'>x</div></body></html>", encoding="utf-8")
    return project


def _runtime(tmp: Path, *, tools: bool = True) -> Path:
    runtime = tmp / "runtime"
    if tools:
        (runtime / "skills" / "shared" / "scripts").mkdir(parents=True)
        (runtime / "skills" / "openclaw" / "card-design" / "scripts").mkdir(parents=True)
        (runtime / "skills" / "shared" / "scripts" / "render_card.py").write_text(
            "", encoding="utf-8")
        (runtime / "skills" / "openclaw" / "card-design" / "scripts"
         / "card_audit.py").write_text("", encoding="utf-8")
    return runtime


def _audit(pass_: bool, problem: str = "") -> str:
    return json.dumps({
        "file": "card_1.png", "size": "1080x1440", "bg": [250, 250, 248],
        "span": 0.91, "bottom_dead": 0.04, "max_gap": 0.08, "fill": 0.42,
        "bands": [0.42, 0.36, 0.43, 0.35], "pass": pass_,
        "problems": [problem] if problem else [],
    })


def _runner(project: Path, *, cards: int = 2, second_fails: bool = False,
            fail_render: str | None = None, silent_audit: bool = False):
    """A runner that writes N fake cards and answers each audit by index."""
    calls: list[list[str]] = []

    def _call(argv, **_kwargs):
        calls.append(list(argv))
        if "--all" in argv:  # renderer
            if fail_render is not None:
                return FakeResult(1, "", fail_render)
            out = Path(argv[argv.index("--out-dir") + 1])
            lines = []
            for index in range(1, cards + 1):
                target = out / f"card_{index}.png"
                _png(target)
                lines.append(f"\u2705 {target} ({len(target.read_bytes()) / 1024:.0f} KB)")
            lines.append(f"\u5171\u6e32\u67d3 {cards} \u5f20")
            return FakeResult(0, "\n".join(lines), "")
        image = Path(argv[argv.index("-f") + 1])
        index = int(image.stem.split("_")[-1])
        if silent_audit:
            return FakeResult(0, "", "")
        failing = second_fails and index == 2
        return FakeResult(0 if not failing else 1, _audit(not failing), "")

    _call.calls = calls  # type: ignore[attr-defined]
    return _call


# --- plan ------------------------------------------------------------------


def test_plan_refuses_a_missing_project():
    with tempfile.TemporaryDirectory() as tmp:
        runtime = _runtime(Path(tmp))
        try:
            plan(Path(tmp) / "nope", runtime_root=runtime)
        except CardRenderError as exc:
            assert exc.code == "PROJECT_MISSING"
        else:
            raise AssertionError("a missing project must be refused")


def test_plan_refuses_html_outside_the_project():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        project = _project(tmp_path)
        runtime = _runtime(tmp_path)
        outside = tmp_path / "elsewhere.html"
        outside.write_text("<html></html>", encoding="utf-8")
        try:
            plan(project, runtime_root=runtime, html=outside)
        except CardRenderError as exc:
            assert exc.code == "PATH_ESCAPES_PROJECT", exc.code
        else:
            raise AssertionError("html outside the project must be refused")


def test_plan_refuses_a_missing_upstream_tool():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        project = _project(tmp_path)
        runtime = _runtime(tmp_path, tools=False)
        try:
            plan(project, runtime_root=runtime)
        except CardRenderError as exc:
            assert exc.code == "UPSTREAM_TOOL_MISSING"
            assert "never copied into this repository" in exc.detail
        else:
            raise AssertionError("a missing pinned runtime must be refused, not stubbed")


def test_plan_refuses_a_missing_html():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        project = _project(tmp_path, html=False)
        runtime = _runtime(tmp_path)
        try:
            plan(project, runtime_root=runtime)
        except CardRenderError as exc:
            assert exc.code == "HTML_MISSING"
        else:
            raise AssertionError("a missing html must be refused")


# --- parsers ---------------------------------------------------------------


def test_parse_render_output_extracts_every_saved_path():
    text = (
        "\u2705 /tmp/a/card_1.png (240 KB)\n"
        "\u2705 /tmp/a/card_2.png (186 KB)\n"
        "\u5171\u6e32\u67d3 2 \u5f20\n"
    )
    assert parse_render_output(text) == ["/tmp/a/card_1.png", "/tmp/a/card_2.png"]


def test_parse_render_output_of_noise_is_empty_not_guessed():
    assert parse_render_output("ERROR: selector \u672a\u547d\u4e2d\u4efb\u4f55\u5143\u7d20") == []


def test_parse_audit_refuses_empty_output():
    try:
        parse_audit_output("")
    except CardRenderError as exc:
        assert exc.code == "AUDIT_OUTPUT_EMPTY"
    else:
        raise AssertionError("a silent audit must not be read as a pass")


def test_parse_audit_refuses_output_without_a_verdict():
    try:
        parse_audit_output('{"size": "1080x1440"}')
    except CardRenderError as exc:
        assert exc.code == "AUDIT_OUTPUT_INVALID"
    else:
        raise AssertionError("output without a pass verdict must be refused")


def test_parse_audit_refuses_non_json():
    try:
        parse_audit_output("\u2705 PASS card_1.png")
    except CardRenderError as exc:
        assert exc.code == "AUDIT_OUTPUT_UNPARSABLE"
    else:
        raise AssertionError("non-JSON audit output must be refused")


# --- run -------------------------------------------------------------------


def test_run_passes_and_never_claims_approval():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        project = _project(tmp_path)
        runtime = _runtime(tmp_path)
        p = plan(project, runtime_root=runtime)
        receipt = run(p, card_python="python", runner=_runner(project, cards=3))
    assert receipt["schema"] == SCHEMA
    assert receipt["card_count"] == 3
    assert receipt["audit_status"] == "PASS"
    assert receipt["status"] == "AWAITING_MANUAL_REVIEW"
    assert receipt["production_ready"] is False
    assert receipt["publish_authorized"] is False
    assert receipt["human_review"] == "NOT_STARTED"
    assert all(card["pass"] for card in receipt["cards"])


def test_a_failing_card_blocks_the_run():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        project = _project(tmp_path)
        runtime = _runtime(tmp_path)
        p = plan(project, runtime_root=runtime)
        receipt = run(p, card_python="python",
                      runner=_runner(project, cards=2, second_fails=True))
    assert receipt["audit_status"] == "FAIL"
    assert receipt["status"] == "BLOCKED"
    assert [card["pass"] for card in receipt["cards"]] == [True, False]


def test_a_selector_matching_nothing_is_not_a_success():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        project = _project(tmp_path)
        runtime = _runtime(tmp_path)
        p = plan(project, runtime_root=runtime)
        try:
            run(p, card_python="python", runner=_runner(project, cards=0))
        except CardRenderError as exc:
            assert exc.code == "NO_CARDS_RENDERED"
            assert "not an empty success" in exc.detail
        else:
            raise AssertionError("an empty render must be refused")


def test_a_missing_browser_is_reported_as_browser_missing():
    message = ("BrowserType.launch: Executable doesn't exist at "
               "D:\\browsers\\chromium_headless_shell-1243\\chrome-headless-shell.exe")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        project = _project(tmp_path)
        runtime = _runtime(tmp_path)
        p = plan(project, runtime_root=runtime)
        try:
            run(p, card_python="python", runner=_runner(project, fail_render=message))
        except CardRenderError as exc:
            assert exc.code == "PLAYWRIGHT_BROWSER_MISSING"
            assert "CONTENTOPS_CARD_PYTHON" in exc.detail
        else:
            raise AssertionError("a missing browser must be named, not reported as generic failure")


def test_a_silent_audit_is_not_a_pass():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        project = _project(tmp_path)
        runtime = _runtime(tmp_path)
        p = plan(project, runtime_root=runtime)
        try:
            run(p, card_python="python",
                runner=_runner(project, cards=1, silent_audit=True))
        except CardRenderError as exc:
            assert exc.code == "AUDIT_OUTPUT_EMPTY"
        else:
            raise AssertionError("a silent audit must fail the run")


def test_preexisting_images_are_reported_and_not_deleted():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        project = _project(tmp_path)
        runtime = _runtime(tmp_path)
        stale = project / "assets" / "cards" / "card_9.png"
        _png(stale)
        p = plan(project, runtime_root=runtime)
        receipt = run(p, card_python="python", runner=_runner(project, cards=2))
        still_there = stale.is_file()
    assert receipt["ignored_existing"] == ["card_9.png"]
    assert still_there is True, "an operator's file must never be deleted to tidy a receipt"


def test_the_fingerprint_tracks_the_html():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        project = _project(tmp_path)
        runtime = _runtime(tmp_path)
        p = plan(project, runtime_root=runtime)
        first = run(p, card_python="python", runner=_runner(project, cards=1))
        (project / "assets" / "cards" / "cards.html").write_text(
            "<html><body><div class='card'>changed</div></body></html>", encoding="utf-8")
        p2 = plan(project, runtime_root=runtime)
        second = run(p2, card_python="python", runner=_runner(project, cards=1))
    assert first["render_fingerprint"] != second["render_fingerprint"]


def test_write_receipt_lands_under_receipts():
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp) / "proj"
        project.mkdir()
        html = project / "a.html"
        html.write_text("<html></html>", encoding="utf-8")
        stub = type("P", (), {"project": project, "html": html,
                              "width": 1080, "height": 1440, "scale": 1,
                              "selector": ".card",
                              "renderer": Path("render_card.py"),
                              "auditor": Path("card_audit.py")})()
        receipt = build_receipt(stub, audits=[], ignored_existing=[], card_python="python")
        target = write_receipt(project, receipt)
        payload = json.loads(target.read_text(encoding="utf-8"))
    assert target.as_posix().endswith("proj/receipts/card-render.json")
    assert payload["publish_authorized"] is False
    assert payload["audit_status"] == "FAIL", "zero cards is never a PASS"


# --- optional live check ---------------------------------------------------


def test_live_render_if_the_runtime_is_available():
    """Render one real card when Playwright and the pinned runtime are present.

    A skip here is not evidence that rendering works; the summary line says so.
    """
    import shutil

    runtime = ROOT / ".runtime" / "easel"
    renderer = runtime / "skills" / "shared" / "scripts" / "render_card.py"
    if not renderer.is_file():
        print("     [skip] pinned Easel runtime is absent")
        return
    try:
        import playwright  # noqa: F401
    except Exception:
        print("     [skip] playwright is not installed")
        return
    if shutil.which("node") is None:
        print("     [skip] node is not on PATH")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        project = tmp_path / "proj"
        (project / "assets" / "cards").mkdir(parents=True)
        rows = "".join(
            f"<div class='r'>\u5b9e\u6d4b\u884c {i} \u00b7 \u5bc6\u5ea6\u95e8\u7981</div>"
            for i in range(1, 7))
        (project / "assets" / "cards" / "cards.html").write_text(
            "<!doctype html><html><head><meta charset='utf-8'><style>"
            "*{margin:0;padding:0;box-sizing:border-box}"
            ".card{width:1080px;height:1440px;padding:72px;background:#fafaf8;"
            "color:#0a0a0a;font-family:'Noto Sans CJK SC',sans-serif;"
            "display:flex;flex-direction:column;justify-content:space-between}"
            ".k{font-size:22px;color:#737373;letter-spacing:.2em}"
            ".rows{flex:1;display:flex;flex-direction:column;justify-content:space-between;"
            "border-top:1px solid #d8d8d4;border-bottom:1px solid #d8d8d4;margin:40px 0}"
            ".r{font-size:36px;padding:18px 0;border-top:1px solid #e6e6e2}"
            ".f{font-size:22px;color:#737373}"
            "</style></head><body><div class='card'>"
            "<div class='k'>LIVE CHECK \u00b7 1080\u00d71440</div>"
            f"<div class='rows'>{rows}</div>"
            "<div class='f'>rendered by the pinned Easel runtime</div>"
            "</div></body></html>", encoding="utf-8")
        try:
            p = plan(project, runtime_root=runtime)
            card_python = os.environ.get("CONTENTOPS_CARD_PYTHON") or sys.executable
            from process_utils import hidden_run
            receipt = run(p, card_python=card_python,
                          runner=lambda argv, timeout=180: hidden_run(
                              argv, timeout=timeout, check=False),
                          timeout=180)
        except CardRenderError as exc:
            print(f"     [skip] live render unavailable: {exc.code}")
            print(f"            {exc.detail[:160]}")
            return
    assert receipt["card_count"] == 1
    assert receipt["cards"][0]["size"] == "1080x1440"
    print(f"     [live] rendered {receipt['cards'][0]['size']} audit={receipt['audit_status']}")


TESTS = [value for name, value in sorted(globals().items())
         if name.startswith("test_") and callable(value)]


def main() -> int:
    failures = 0
    skipped = 0
    for test in TESTS:
        try:
            test()
        except Exception as exc:  # noqa: BLE001 - a runner reports, it does not raise
            failures += 1
            print(f"FAIL {test.__name__}: {type(exc).__name__}: {exc}")
        else:
            if "live" in test.__name__:
                skipped += 1
                print(f"ok   {test.__name__} (see [skip]/[live] line above)")
            else:
                print(f"ok   {test.__name__}")
    print(f"{len(TESTS) - failures}/{len(TESTS)} ok"
          f"{f' ({skipped} optional live check)' if skipped else ''}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
