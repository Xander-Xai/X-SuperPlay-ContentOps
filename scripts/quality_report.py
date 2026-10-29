#!/usr/bin/env python3
"""Produce the canonical quality report for one graded target.

    python scripts/quality_report.py --project projects/<slug> --target final.mp4 \
        --script 02_script/script.json --srt assets/captions/default.srt

The report is written to ``07_quality/quality-report.json`` by default and is
deterministic: the same inputs produce the same bytes. It carries one verdict
for one target, and it never reports ``production_ready`` -- human review is a
separate artifact.

Refusing to write an empty report is deliberate. A report with no checks is
indistinguishable from a report where every check passed, and that ambiguity is
how a green run stops meaning anything.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from contentops.quality import CheckResult, build_report, validate_script_rhythm, validate_srt  # noqa: E402
from contentops.quality.script_rhythm import measure_script_rhythm  # noqa: E402
from contentops.quality.subtitle import measure_srt  # noqa: E402

DEFAULT_OUTPUT = "07_quality/quality-report.json"


def _relative(project: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else project / path


def _script_check(path: Path) -> CheckResult:
    errors = validate_script_rhythm(path)
    measured = {}
    try:
        measured = measure_script_rhythm(json.loads(path.read_text(encoding="utf-8")))
    except Exception:  # measurement is soft; validation already reported the failure
        pass
    return CheckResult(
        check_id="script_rhythm",
        ok=not errors,
        severity="FAIL",
        detail="; ".join(errors),
        measured=measured,
    )


def _subtitle_check(path: Path, max_chars: int) -> CheckResult:
    errors = validate_srt(path, max_chars_per_line=max_chars)
    return CheckResult(
        check_id="subtitle",
        ok=not errors,
        severity="FAIL",
        detail="; ".join(errors),
        measured=measure_srt(path),
    )


def _qc_video_check(path: Path) -> CheckResult:
    """Fold an existing qc_video report in as one more check, not as the verdict."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return CheckResult("qc_video", False, "FAIL", f"qc report unreadable: {exc}")
    overall = document.get("overall") or document.get("verdict")
    if overall not in ("PASS", "WARN", "FAIL"):
        return CheckResult("qc_video", False, "FAIL", "qc report carries no overall verdict")
    return CheckResult(
        check_id="qc_video",
        ok=overall == "PASS",
        severity="WARN" if overall == "WARN" else "FAIL",
        detail="" if overall == "PASS" else f"qc_video overall={overall}",
        measured={"overall": overall},
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the canonical quality report")
    parser.add_argument("--project", required=True)
    parser.add_argument("--target", required=True, help="the artifact this verdict grades")
    parser.add_argument("--script", help="script JSON (contentops.script-rhythm/v1)")
    parser.add_argument("--srt", help="subtitle file")
    parser.add_argument("--qc-json", help="existing qc_video JSON to fold in")
    parser.add_argument("--max-caption-chars", type=int, default=22)
    parser.add_argument("--out", default=DEFAULT_OUTPUT)
    parser.add_argument("--currency", choices=("CURRENT", "STALE"), default="CURRENT")
    args = parser.parse_args(argv)

    project = Path(args.project).resolve()
    if not project.is_dir():
        print(f"project not found: {project}", file=sys.stderr)
        return 2

    checks = []
    if args.script:
        path = _relative(project, args.script)
        if not path.is_file():
            print(f"script not found: {path}", file=sys.stderr)
            return 2
        checks.append(_script_check(path))
    if args.srt:
        path = _relative(project, args.srt)
        if not path.is_file():
            print(f"subtitle not found: {path}", file=sys.stderr)
            return 2
        checks.append(_subtitle_check(path, args.max_caption_chars))
    if args.qc_json:
        path = _relative(project, args.qc_json)
        if not path.is_file():
            print(f"qc report not found: {path}", file=sys.stderr)
            return 2
        checks.append(_qc_video_check(path))

    if not checks:
        print("refusing to write a report with no checks; pass --script, --srt or --qc-json",
              file=sys.stderr)
        return 2

    report = build_report(args.target, checks, currency=args.currency)
    out = _relative(project, args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"[{report['verdict']}] {args.target}")
    for check in report["checks"]:
        flag = "ok" if check["ok"] else check["severity"]
        print(f"  {check['check_id']:<16} {flag}")
        if check["detail"]:
            print(f"    - {check['detail']}")
    print(f"written: {out}")
    return 0 if report["verdict"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
