#!/usr/bin/env python3
"""Hermetic tests for the GZH article renderer (contentops.graphic.articles).

No test contacts the network, spawns a real process, or needs the Easel
runtime: the upstream tools are faked with empty files inside a temp
runtime root (existence is all `ArticleTools.resolve` checks), and `run()`
drives an injected fake runner. The single live-ish concern — whether real
upstream scripts behave — is out of scope here by design; the receipt says
what ran and what it cannot claim.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT / "src", ROOT / "scripts"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from contentops.graphic.articles import (  # noqa: E402
    INPUT_SCHEMA,
    RECEIPT_SCHEMA,
    ArticleError,
    build_receipt,
    parse_validator_output,
    plan,
    run,
    verify_receipt,
    write_receipt,
)

VALID_HTML = (
    "<section><h2>标题</h2><p>段落一</p>"
    '<img src="../images/figure0.png">'
    "<p>段落二</p></section>"
)
PASSING_VALIDATOR_OUTPUT = (
    "✅ 检查完成\n"
    "span leaf 包裹: 3 处\n"
)


class FakeResult:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _expect_error(fn, code: str):
    try:
        fn()
    except ArticleError as exc:
        assert exc.code == code, f"expected {code}, got {exc.code}: {exc.detail}"
    else:
        raise AssertionError(f"expected ArticleError {code}, nothing raised")


def _fake_runtime(tmp: Path) -> Path:
    """A runtime root whose gzh-design tools exist but are empty stubs."""
    scripts = tmp / "easel" / "skills" / "openclaw" / "gzh-design" / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    for name in ("validate_gzh_html.py", "wrap_preview.py", "component_lint.py"):
        (scripts / name).write_text("# stub\n", encoding="utf-8")
    return tmp / "easel"


def _project(tmp: Path, *, html: str = VALID_HTML, images: int = 1) -> Path:
    """A minimal project: article HTML plus the local images it references."""
    project = tmp / "proj"
    (project / "assets" / "article").mkdir(parents=True, exist_ok=True)
    (project / "assets" / "images").mkdir(parents=True, exist_ok=True)
    for i in range(images):
        (project / "assets" / "images" / f"figure{i}.png").write_bytes(b"\x89PNG fake%d" % i)
    src = html
    (project / "assets" / "article" / "article.html").write_text(src, encoding="utf-8")
    return project


def _planned(tmp: Path):
    runtime = _fake_runtime(tmp)
    project = _project(tmp)
    return plan(project, runtime_root=runtime), project, runtime


# --- plan(): refusal paths ---------------------------------------------------


def test_plan_refuses_a_missing_project():
    with tempfile.TemporaryDirectory() as d:
        _expect_error(lambda: plan(Path(d) / "nope", runtime_root=_fake_runtime(Path(d))),
                      "PROJECT_MISSING")


def test_plan_refuses_missing_upstream_tools():
    with tempfile.TemporaryDirectory() as d:
        empty = Path(d) / "empty-runtime"
        empty.mkdir()
        _expect_error(lambda: plan(_project(Path(d)), runtime_root=empty),
                      "ARTICLE_UPSTREAM_TOOL_MISSING")


def test_plan_refuses_a_missing_html():
    with tempfile.TemporaryDirectory() as d:
        runtime = _fake_runtime(Path(d))
        project = Path(d) / "proj"
        project.mkdir()
        _expect_error(lambda: plan(project, runtime_root=runtime), "ARTICLE_HTML_MISSING")


def test_plan_refuses_html_outside_the_project():
    with tempfile.TemporaryDirectory() as d:
        runtime = _fake_runtime(Path(d))
        project = _project(Path(d))
        outside = Path(d) / "outside.html"
        outside.write_text(VALID_HTML, encoding="utf-8")
        _expect_error(lambda: plan(project, html_path=outside, runtime_root=runtime),
                      "ARTICLE_HTML_OUTSIDE_PROJECT")


def test_plan_refuses_an_empty_html():
    with tempfile.TemporaryDirectory() as d:
        runtime = _fake_runtime(Path(d))
        project = _project(Path(d))
        html = project / "assets" / "article" / "article.html"
        html.write_text("   \n  ", encoding="utf-8")
        _expect_error(lambda: plan(project, runtime_root=runtime), "ARTICLE_EMPTY")


def test_plan_refuses_html_without_a_section():
    with tempfile.TemporaryDirectory() as d:
        runtime = _fake_runtime(Path(d))
        project = _project(Path(d), html="<p>no section here</p>")
        _expect_error(lambda: plan(project, runtime_root=runtime), "ARTICLE_COMPONENT_INVALID")


def test_plan_refuses_active_content():
    with tempfile.TemporaryDirectory() as d:
        runtime = _fake_runtime(Path(d))
        project = _project(Path(d), html="<section><script>alert(1)</script></section>")
        _expect_error(lambda: plan(project, runtime_root=runtime), "ARTICLE_COMPONENT_INVALID")


def test_plan_refuses_a_legacy_card_input_schema():
    with tempfile.TemporaryDirectory() as d:
        runtime = _fake_runtime(Path(d))
        project = _project(Path(d))
        (project / "article-input.json").write_text(
            json.dumps({"schema": "contentops.card-plan/v1", "sources": []}), encoding="utf-8")
        _expect_error(lambda: plan(project, runtime_root=runtime), "ARTICLE_INPUT_SCHEMA_MISMATCH")


def test_plan_refuses_a_remote_image():
    with tempfile.TemporaryDirectory() as d:
        runtime = _fake_runtime(Path(d))
        project = _project(Path(d), html='<section><img src="https://cdn.example.com/x.png"></section>')
        _expect_error(lambda: plan(project, runtime_root=runtime), "ARTICLE_IMAGE_UNAUTHORIZED")


def test_plan_refuses_an_image_outside_the_project():
    with tempfile.TemporaryDirectory() as d:
        runtime = _fake_runtime(Path(d))
        project = _project(Path(d), html='<section><img src="../../../outside.png"></section>')
        (Path(d) / "outside.png").write_bytes(b"\x89PNG")
        _expect_error(lambda: plan(project, runtime_root=runtime), "ARTICLE_IMAGE_OUTSIDE_PROJECT")


def test_plan_refuses_a_missing_image():
    with tempfile.TemporaryDirectory() as d:
        runtime = _fake_runtime(Path(d))
        project = _project(Path(d), images=0)
        _expect_error(lambda: plan(project, runtime_root=runtime), "ARTICLE_IMAGE_MISSING")


def test_plan_refuses_a_preview_that_overwrites_the_html():
    with tempfile.TemporaryDirectory() as d:
        runtime = _fake_runtime(Path(d))
        project = _project(Path(d))
        html = project / "assets" / "article" / "article.html"
        _expect_error(lambda: plan(project, preview_path=html, runtime_root=runtime),
                      "ARTICLE_PREVIEW_OVERWRITES_HTML")


def test_plan_refuses_an_oversized_title():
    with tempfile.TemporaryDirectory() as d:
        runtime = _fake_runtime(Path(d))
        project = _project(Path(d))
        _expect_error(lambda: plan(project, title="字" * 65, runtime_root=runtime),
                      "ARTICLE_TITLE_INVALID")


def test_plan_refuses_non_string_sources():
    with tempfile.TemporaryDirectory() as d:
        runtime = _fake_runtime(Path(d))
        project = _project(Path(d))
        _expect_error(lambda: plan(project, sources=["ok", 3], runtime_root=runtime),
                      "ARTICLE_SOURCES_INVALID")


# --- plan(): the data-URI fix ------------------------------------------------


def test_data_uri_matching_a_verified_local_image_is_accepted():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        runtime = _fake_runtime(tmp)
        project = _project(tmp)
        png = project / "assets" / "images" / "figure0.png"
        embedded = base64.b64encode(png.read_bytes()).decode()
        html = ('<section><img src="../images/figure0.png">'
                f'<img src="data:image/png;base64,{embedded}"></section>')
        (project / "assets" / "article" / "article.html").write_text(html, encoding="utf-8")
        p = plan(project, runtime_root=runtime)
        # The data URI is an inline copy of the verified image, not an
        # additional image entry.
        assert len(p.images) == 1
        assert p.images[0]["path"] == "project://assets/images/figure0.png"


def test_data_uri_with_unmatched_bytes_is_refused():
    with tempfile.TemporaryDirectory() as d:
        runtime = _fake_runtime(Path(d))
        project = _project(Path(d))
        rogue = base64.b64encode(b"\x89PNG not the verified image").decode()
        html = ('<section><img src="../images/figure0.png">'
                f'<img src="data:image/png;base64,{rogue}"></section>')
        (project / "assets" / "article" / "article.html").write_text(html, encoding="utf-8")
        _expect_error(lambda: plan(project, runtime_root=runtime), "ARTICLE_IMAGE_UNAUTHORIZED")


def test_malformed_data_uri_is_refused():
    with tempfile.TemporaryDirectory() as d:
        runtime = _fake_runtime(Path(d))
        project = _project(Path(d))
        html = '<section><img src="data:text/html;base64,PGI+aGk8L2I+"></section>'
        (project / "assets" / "article" / "article.html").write_text(html, encoding="utf-8")
        _expect_error(lambda: plan(project, runtime_root=runtime), "ARTICLE_IMAGE_UNAUTHORIZED")


# --- run(): fake-runner paths ------------------------------------------------


def _successful_runner(preview_path: Path):
    def runner(argv, timeout=120):
        if "validate_gzh_html.py" in argv[1]:
            return FakeResult(0, PASSING_VALIDATOR_OUTPUT, "")
        assert "wrap_preview.py" in argv[1]
        preview_path.write_text("<html>preview</html>", encoding="utf-8")
        return FakeResult(0, "wrapped", "")
    return runner


def test_run_passes_and_never_claims_approval():
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        p, project, _ = _planned(tmp)
        receipt = run(p, runner=_successful_runner(p.preview_out))
        assert receipt["schema"] == RECEIPT_SCHEMA
        assert receipt["validation"]["status"] == "PASS"
        assert receipt["status"] == "AWAITING_MANUAL_REVIEW"
        assert receipt["production_ready"] is False
        assert receipt["publish_authorized"] is False
        assert receipt["human_review"] == "NOT_STARTED"
        assert "WECHAT_PUBLISH_UNAUTHORIZED" in receipt["blockers"]
        assert p.preview_out.is_file()


def test_a_failing_validator_blocks_the_run():
    with tempfile.TemporaryDirectory() as d:
        p, _, _ = _planned(Path(d))
        runner = lambda argv, timeout=120: FakeResult(0, "❌ ERROR:\n  • bad tag\n", "")
        _expect_error(lambda: run(p, runner=runner), "ARTICLE_VALIDATION_FAILED")


def test_a_validator_warning_is_not_a_pass():
    with tempfile.TemporaryDirectory() as d:
        p, _, _ = _planned(Path(d))
        runner = lambda argv, timeout=120: FakeResult(0, "⚠️ WARNING:\n  • risky style\n", "")
        _expect_error(lambda: run(p, runner=runner), "ARTICLE_VALIDATION_FAILED")


def test_a_nonzero_validator_exit_blocks_the_run():
    with tempfile.TemporaryDirectory() as d:
        p, _, _ = _planned(Path(d))
        runner = lambda argv, timeout=120: FakeResult(1, "boom", "")
        _expect_error(lambda: run(p, runner=runner), "ARTICLE_VALIDATION_FAILED")


def test_a_failing_wrapper_blocks_the_run():
    with tempfile.TemporaryDirectory() as d:
        p, _, _ = _planned(Path(d))
        def runner(argv, timeout=120):
            if "validate_gzh_html.py" in argv[1]:
                return FakeResult(0, PASSING_VALIDATOR_OUTPUT, "")
            return FakeResult(2, "", "wrapper exploded")
        _expect_error(lambda: run(p, runner=runner), "ARTICLE_PREVIEW_FAILED")


def test_a_missing_preview_file_is_reported():
    with tempfile.TemporaryDirectory() as d:
        p, _, _ = _planned(Path(d))
        runner = lambda argv, timeout=120: FakeResult(0, PASSING_VALIDATOR_OUTPUT, "")
        _expect_error(lambda: run(p, runner=runner), "ARTICLE_PREVIEW_MISSING")


def test_an_unlaunchable_interpreter_is_reported_as_unavailable():
    with tempfile.TemporaryDirectory() as d:
        p, _, _ = _planned(Path(d))
        def runner(argv, timeout=120):
            raise OSError("no such interpreter")
        _expect_error(lambda: run(p, runner=runner, article_python="definitely-missing"),
                      "ARTICLE_PYTHON_UNAVAILABLE")


# --- parse_validator_output --------------------------------------------------


def test_parse_extracts_leaf_count_errors_and_warnings():
    text = ("✅ 检查完成\n"
            "span leaf 包裹: 7 处\n"
            "❌ ERROR (2):\n"
            "  • bad tag <b>\n"
            "  • inline style found\n"
            "⚠️ WARNING (1):\n"
            "  • heading level jump\n")
    m = parse_validator_output(text)
    assert m["span_leaf_count"] == 7
    assert m["errors"] == ["bad tag <b>", "inline style found"]
    assert m["warnings"] == ["heading level jump"]


def test_parse_of_noise_is_zeros_not_guesses():
    m = parse_validator_output("hello world, nothing structured here")
    assert m["span_leaf_count"] == 0
    assert m["errors"] == []
    assert m["warnings"] == []


# --- receipts: write, verify, tamper -----------------------------------------


def _receipt(tmp: Path):
    p, project, _ = _planned(tmp)
    receipt = run(p, runner=_successful_runner(p.preview_out))
    return p, project, receipt


def test_write_receipt_lands_in_receipts_and_verifies():
    with tempfile.TemporaryDirectory() as d:
        p, project, receipt = _receipt(Path(d))
        target = write_receipt(receipt, project)
        assert target == project / "receipts" / "gzh-article.json"
        assert target.is_file()
        assert verify_receipt(json.loads(target.read_text(encoding="utf-8")), project) is True


def test_write_receipt_refuses_to_mix_schemas():
    with tempfile.TemporaryDirectory() as d:
        p, project, receipt = _receipt(Path(d))
        legacy = project / "receipts" / "gzh-article.json"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text(json.dumps({"schema": "contentops.card-plan/v1"}), encoding="utf-8")
        _expect_error(lambda: write_receipt(receipt, project), "RECEIPT_SCHEMA_MISMATCH")


def test_verify_rejects_a_tampered_html():
    with tempfile.TemporaryDirectory() as d:
        p, project, receipt = _receipt(Path(d))
        target = write_receipt(receipt, project)
        html = project / "assets" / "article" / "article.html"
        html.write_text(html.read_text(encoding="utf-8") + "<!-- tampered -->", encoding="utf-8")
        assert verify_receipt(json.loads(target.read_text(encoding="utf-8")), project) is False


def test_verify_rejects_a_tampered_fingerprint():
    with tempfile.TemporaryDirectory() as d:
        p, project, receipt = _receipt(Path(d))
        receipt["article_fingerprint"] = "0" * 64
        assert verify_receipt(receipt, project) is False


def test_verify_rejects_a_wrong_schema():
    with tempfile.TemporaryDirectory() as d:
        _, project, receipt = _receipt(Path(d))
        receipt["schema"] = "something/else"
        assert verify_receipt(receipt, project) is False


def test_the_fingerprint_is_deterministic():
    with tempfile.TemporaryDirectory() as d:
        p, project, _ = _planned(Path(d))
        p.preview_out.write_text("<html>preview</html>", encoding="utf-8")
        metrics = parse_validator_output(PASSING_VALIDATOR_OUTPUT)
        r1 = build_receipt(p, validation_metrics=metrics, article_python="python.exe")
        r2 = build_receipt(p, validation_metrics=metrics, article_python="python.exe")
        assert r1["article_fingerprint"] == r2["article_fingerprint"]


# --- runner ------------------------------------------------------------------


def main() -> int:
    failures = 0
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    for test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001 - a runner reports, it does not raise
            failures += 1
            print(f"FAIL {test.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"ok   {test.__name__}")
    print(f"{len(tests) - failures}/{len(tests)} ok")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
