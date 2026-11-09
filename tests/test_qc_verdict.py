"""QC receipts keep their original verdict and share one release rule.

Account-bound projects stop on WARN or FAIL. A historical sample with no
account may keep WARN, but the receipt must say so. Nothing here can approve
or publish a video.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from contentops.media.qc_verdict import judge_technical_qc  # noqa: E402

import m5_production  # noqa: E402

TESTS = []


def test(fn):
    TESTS.append(fn)
    return fn


def _report(overall: str, target: str = "project://final/demo.mp4") -> dict:
    return {"overall": overall, "graded_target": target, "checks": []}


@test
def test_pass_keeps_pass_and_cannot_approve():
    decision = judge_technical_qc(
        _report("PASS"), has_audio=True, account_bound=True,
        graded_target="project://final/demo.mp4",
    )
    assert decision["blocked"] is False, decision
    assert decision["overall"] == "PASS"
    assert decision["production_ready"] is False
    assert decision["publish_authorized"] is False
    print("[ok] PASS stays PASS and cannot approve")


@test
def test_account_warn_stays_warn_and_blocks():
    decision = judge_technical_qc(
        _report("WARN"), has_audio=True, account_bound=True,
        graded_target="project://final/demo.mp4",
    )
    assert decision["blocked"] is True, decision
    assert decision["overall"] == "WARN"
    assert decision["overall"] != "PASS"
    assert decision["historical_exception"] is False
    print("[ok] account WARN is not rewritten to PASS")


@test
def test_fail_blocks_without_rewriting():
    decision = judge_technical_qc(
        _report("FAIL"), has_audio=True, account_bound=False,
        graded_target="project://final/demo.mp4",
    )
    assert decision["blocked"] is True, decision
    assert decision["overall"] == "FAIL"
    print("[ok] FAIL blocks a historical sample too")


@test
def test_missing_audio_blocks_even_when_overall_is_pass():
    decision = judge_technical_qc(
        _report("PASS"), has_audio=False, account_bound=False,
        graded_target="project://final/demo.mp4",
    )
    assert decision["blocked"] is True, decision
    assert decision["reason"] == "MISSING_AUDIO", decision
    print("[ok] missing audio blocks")


@test
def test_a_report_for_another_render_blocks():
    decision = judge_technical_qc(
        _report("PASS", "project://final/other.mp4"), has_audio=True,
        account_bound=False, graded_target="project://final/demo.mp4",
    )
    assert decision["blocked"] is True, decision
    assert decision["reason"] == "REPORT_TARGET_MISMATCH", decision
    print("[ok] a mismatched graded target blocks")


@test
def test_historical_warn_is_kept_and_named():
    decision = judge_technical_qc(
        _report("WARN"), has_audio=True, account_bound=False,
        graded_target="project://final/demo.mp4",
    )
    assert decision["blocked"] is False, decision
    assert decision["overall"] == "WARN"
    assert decision["historical_exception"] is True
    assert decision["production_ready"] is False
    print("[ok] historical WARN stays WARN and is labeled")


@test
def test_stage_qc_blocks_an_account_warn_and_preserves_the_receipt():
    slug = "acct-warn"
    original_has_audio = m5_production._has_audio
    original_hidden_run = m5_production.hidden_run
    try:
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / slug
            (project / "receipts").mkdir(parents=True)
            (project / "final").mkdir()
            (project / "final" / f"{slug}.mp4").write_bytes(b"not-a-video")
            (project / "project.yaml").write_text(
                "account_slug: x-superplay-1024\n", encoding="utf-8",
            )
            report_path = project / "receipts" / f"qc-report-{slug}.json"
            report_path.write_text(
                json.dumps({"overall": "WARN", "checks": []}), encoding="utf-8",
            )
            m5_production._has_audio = lambda _video: True
            m5_production.hidden_run = lambda *_args, **_kwargs: type(
                "R", (), {"returncode": 0, "stdout": "", "stderr": ""},
            )()
            try:
                m5_production.stage_qc(project, slug)
            except m5_production.M5Blocked:
                saved = json.loads(report_path.read_text(encoding="utf-8"))
                assert saved["overall"] == "WARN", saved
                assert saved.get("production_ready") is not True
                assert saved.get("publish_authorized") is not True
                print("[ok] stage_qc blocks account WARN without rewriting it")
                return
            raise AssertionError("account WARN was released by stage_qc")
    finally:
        m5_production._has_audio = original_has_audio
        m5_production.hidden_run = original_hidden_run


def main() -> int:
    failures = []
    for fn in TESTS:
        try:
            fn()
        except AssertionError as exc:
            failures.append((fn.__name__, str(exc)))
            print(f"[FAIL] {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failures.append((fn.__name__, repr(exc)))
            print(f"[ERR ] {fn.__name__}: {exc!r}")
    if failures:
        print(f"\n{len(failures)} test(s) failed")
        return 1
    print(f"\nAll {len(TESTS)} QC verdict tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
