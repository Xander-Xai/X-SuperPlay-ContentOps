"""M5 automated visual-QC stage (Issue #140 slice)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Optional


def stage_visual_qc(
    project: Path,
    slug: str,
    *,
    repo_root: Path,
    python_executable: Callable[[], str],
    hidden_run: Callable[..., Any],
    file_sha256: Callable[[Path], str],
    read_json_or_none: Callable[[Path], Optional[Dict[str, Any]]],
    write_json: Callable[[Path, Dict[str, Any]], None],
    blocked_error: type[Exception],
) -> Dict[str, Any]:
    """Sample fixed-interval frames and run the local Huashu motion gate."""
    from contentops.media.huashu_runtime import find_runtime
    from contentops.media.visual_gate import evaluate_film_gate

    video = project / "final" / f"{slug}.mp4"
    if not video.is_file():
        raise blocked_error("visual QC requires the composed final video")
    video_sha = file_sha256(video)
    receipts = project / "receipts"
    visual_receipt_path = receipts / "visual-gate.json"
    contact_sheet = receipts / "visual-contact-sheet.png"
    visual_qc_path = receipts / "visual-qc.json"

    sample = hidden_run(
        [python_executable(), str(repo_root / "scripts" / "qc_visual.py"), str(project),
         "--video", f"{slug}.mp4"], cwd=str(repo_root), timeout=300,
    )
    visual_qc = read_json_or_none(visual_qc_path)
    if visual_qc is not None:
        recorded_video = visual_qc.get("video")
        try:
            same_video = bool(recorded_video) and Path(recorded_video).resolve() == video.resolve()
        except (OSError, RuntimeError):
            same_video = False
        if not same_video:
            visual_qc = None
    if visual_qc is not None:
        if visual_qc.get("contact_sheet") and contact_sheet.is_file():
            visual_qc["contact_sheet"] = "project://receipts/visual-contact-sheet.png"
        visual_qc.pop("project", None)
        visual_qc.pop("video", None)
        visual_qc["video_sha256"] = video_sha
        write_json(visual_qc_path, visual_qc)
    frame_summary = (visual_qc or {}).get("summary") or {}
    frame_sampling_valid = (
        sample.returncode == 0
        and visual_qc is not None
        and visual_qc.get("status") in {"PASS", "WARN"}
        and contact_sheet.is_file()
        and frame_summary.get("extraction_failures", 10) <= 3
    )

    try:
        runtime = find_runtime(repo_root)
    except (OSError, RuntimeError):
        result = {
            "schema": "contentops.visual-gate/v1", "state": "BLOCKED",
            "reason": "no supported local Huashu Art Motion installation was found",
            "video_sha256": video_sha,
            "contact_sheet": "project://receipts/visual-contact-sheet.png"
            if contact_sheet.is_file() else None,
            "frame_sampling": visual_qc.get("status") if visual_qc else "BLOCKED",
            "production_ready": False, "publish_authorized": False,
            "human_review": "PENDING_FOUNDER_REVIEW",
        }
        write_json(visual_receipt_path, result)
        raise blocked_error("visual motion gate blocked: Huashu film_gate.py unavailable") from None

    gate_script = runtime / "scripts" / "film_gate.py"
    if not gate_script.is_file():
        result = {
            "schema": "contentops.visual-gate/v1", "state": "BLOCKED",
            "reason": "Huashu installation has no scripts/film_gate.py",
            "video_sha256": video_sha,
            "contact_sheet": "project://receipts/visual-contact-sheet.png"
            if contact_sheet.is_file() else None,
            "production_ready": False, "publish_authorized": False,
            "human_review": "PENDING_FOUNDER_REVIEW",
        }
        write_json(visual_receipt_path, result)
        raise blocked_error("visual motion gate blocked: film_gate.py missing")

    proc = hidden_run(
        [python_executable(), str(gate_script), str(video), "--json",
         "--vertical", "yes", "--no-template"], cwd=str(repo_root), timeout=900,
    )
    try:
        payload = json.loads(proc.stdout or "")
    except (TypeError, ValueError):
        payload = {}
    result = evaluate_film_gate(payload, proc.returncode)
    sampling_block_reason = None
    if not frame_sampling_valid and result["state"] not in {"FAIL", "BLOCKED"}:
        result["state"] = "BLOCKED"
        sampling_block_reason = "fixed-interval frame sampling or contact sheet is incomplete"
    result.update({
        "video_sha256": video_sha,
        "frame_sampling": visual_qc.get("status") if visual_qc else "BLOCKED",
        "frame_sampling_failures": (visual_qc.get("summary") or {}).get("extraction_failures")
        if visual_qc else None,
        "contact_sheet": "project://receipts/visual-contact-sheet.png"
        if contact_sheet.is_file() else None,
        "reason": sampling_block_reason or (
            None if result["state"] in {"PASS", "WARN"}
            else ((payload.get("summary") if isinstance(payload, dict) else None)
                  or (result.get("metrics") or {}).get("explain")
                  or "Huashu film gate returned an unrecognized result")
        ),
    })
    write_json(visual_receipt_path, result)
    if result["state"] in {"BLOCKED", "FAIL"}:
        raise blocked_error(
            f"visual motion gate {result['state']}: "
            f"{result.get('reason') or result.get('gate_light')}"
        )
    return result
