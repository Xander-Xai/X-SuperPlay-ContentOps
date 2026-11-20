"""M5 technical QC stage (Issue #140 slice)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict


def stage_qc(
    project: Path,
    slug: str,
    *,
    repo_root: Path,
    python_executable: Callable[[], str],
    hidden_run: Callable[..., Any],
    has_audio: Callable[[Path], bool],
    write_json: Callable[[Path, Dict[str, Any]], None],
    blocked_error: type[Exception],
) -> Dict[str, Any]:
    """Run technical QC, persist the canonical verdict, and refuse blockers."""
    from contentops.media.qc_canonical import (
        CURRENCY_CURRENT,
        canonical_qc_report,
        render_canonical_qc_markdown,
    )
    from contentops.media.qc_verdict import judge_technical_qc, project_is_account_bound

    proc = hidden_run(
        [python_executable(), str(repo_root / "scripts" / "qc_video.py"), str(project),
         "--video", f"{slug}.mp4"],
        cwd=str(repo_root), timeout=900,
    )
    report_path = project / "receipts" / f"qc-report-{slug}.json"
    legacy_path = project / "receipts" / "qc-report.json"
    if not report_path.is_file() and legacy_path.is_file():
        report_path = legacy_path
    if not report_path.is_file():
        raise blocked_error(f"qc produced no report: {(proc.stderr or proc.stdout)[-300:]}")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    video = project / "final" / f"{slug}.mp4"
    graded_target = f"project://final/{slug}.mp4"
    audio = has_audio(video)
    canonical = canonical_qc_report(
        report, repo_root=repo_root, project_root=project,
        graded_target=graded_target, currency=CURRENCY_CURRENT,
    )
    canonical["project"] = (
        project.relative_to(repo_root).as_posix() if project.is_relative_to(repo_root) else "project://"
    )
    judged = dict(canonical)
    declared = report.get("graded_target")
    if declared not in (None, "", graded_target):
        judged["graded_target"] = declared
    decision = judge_technical_qc(
        judged, has_audio=audio,
        account_bound=project_is_account_bound(project),
        graded_target=graded_target,
    )
    canonical["m5_checks"] = {
        "audio_stream": audio,
        "overall": decision["overall"],
        "blocked": decision["blocked"],
        "reason": decision["reason"],
        "historical_exception": decision["historical_exception"],
        "production_ready": False,
        "publish_authorized": False,
    }
    canonical["production_ready"] = False
    canonical["publish_authorized"] = False
    write_json(report_path, canonical)
    (project / "receipts" / f"qc-report-{slug}.md").write_text(
        render_canonical_qc_markdown(canonical, project_name=project.name), encoding="utf-8"
    )
    if decision["blocked"]:
        raise blocked_error("QC failed: " + json.dumps(canonical["m5_checks"]))
    return {"report": canonical, "video": str(video)}
