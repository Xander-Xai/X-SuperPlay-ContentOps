"""M5 subtitle generation stage (Issue #140 slice)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict


def stage_subtitles(
    project: Path,
    script: Dict[str, Any],
    narration: Dict[str, Any],
    *,
    format_time: Callable[[float], str],
    blocked_error: type[Exception],
    write_json: Callable[[Path, Dict[str, Any]], None],
) -> Dict[str, Any]:
    """Write caption SRT and its historical receipt, then enforce coverage."""
    lines = script["lines"]
    cues = []
    for line, timing in zip(lines, narration["lines"]):
        start = timing["start"]
        end = start + timing["duration"]
        cues.append(
            f"{len(cues) + 1}\n{format_time(start)} --> {format_time(end)}\n"
            f"{line['caption']}\n"
        )
    srt = project / "assets" / "captions" / "default.srt"
    srt.parent.mkdir(parents=True, exist_ok=True)
    srt.write_text("\n".join(cues), encoding="utf-8")
    covered = sum(timing["duration"] for timing in narration["lines"])
    ratio = covered / narration["duration_s"] if narration["duration_s"] else 0.0
    payload = {
        "schema": "contentops.m5-subtitles/v1",
        "path": srt.relative_to(project).as_posix(),
        "cues": len(cues),
        "coverage_ratio": round(ratio, 3),
        "audio_duration_s": narration["duration_s"],
    }
    write_json(project / "receipts" / "subtitles.json", payload)
    if ratio < 0.8:
        raise blocked_error(f"subtitle coverage {ratio:.2f} is below 0.8")
    return payload
