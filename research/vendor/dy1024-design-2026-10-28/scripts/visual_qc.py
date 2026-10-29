#!/usr/bin/env python3
"""Deterministic visual-semantic checks for a rendered Douyin video.

This is deliberately separate from codec/audio QC: it checks that the chosen
production route is visible in the storyboard and that the render has enough
evidence scenes to support the promise. Human visual approval remains a
separate artifact and cannot be synthesized by this command.
"""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from pathlib import Path
from typing import Any

try:
    from media_tools import ffprobe as resolve_ffprobe
except ImportError:
    from scripts.media_tools import ffprobe as resolve_ffprobe


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"JSON must contain an object: {path}")
    return value


def probe_duration(path: Path) -> float | None:
    try:
        executable = resolve_ffprobe()
        result = subprocess.run(
            [executable, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, check=True,
        )
        return float(result.stdout.strip())
    except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError):
        return None


def probe_video_stream(path: Path) -> dict[str, Any]:
    try:
        executable = resolve_ffprobe()
        result = subprocess.run(
            [executable, "-v", "error", "-show_entries", "stream=codec_type,width,height", "-of", "json", str(path)],
            capture_output=True, text=True, check=True,
        )
        payload = json.loads(result.stdout or "{}")
        streams = payload.get("streams", []) if isinstance(payload, dict) else []
        video_streams = [stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "video"]
        return {"has_video": bool(video_streams), "stream_count": len(video_streams)}
    except (OSError, RuntimeError, subprocess.CalledProcessError, ValueError, json.JSONDecodeError):
        return {"has_video": False, "stream_count": 0}


def main(args: argparse.Namespace) -> int:
    project = Path(args.project).expanduser().resolve() if args.project else None
    if project:
        manifest = load(project / "content.json")
        paths = manifest.get("paths", {}) if isinstance(manifest.get("paths"), dict) else {}
        video_value = str(paths.get("video", "04_video/video.json"))
        video_manifest = load(project / video_value)
        video_path = Path(str(video_manifest.get("preview_path") or ""))
        if not video_path.is_absolute():
            video_path = project / video_path
        storyboard_path = project / str(paths.get("storyboard", "04_video/storyboard.csv"))
        output = project / str(paths.get("visual_qc", "05_publish/visual-qc.json"))
        plan = load(project / str(paths.get("execution_plan", "00_brief/execution-plan.json")))
    else:
        if not args.input or not args.storyboard or not args.output:
            raise SystemExit("--input, --storyboard and --output are required without --project")
        video_path, storyboard_path, output = map(lambda value: Path(value).expanduser().resolve(), (args.input, args.storyboard, args.output))
        plan = {}
    errors: list[str] = []
    warnings: list[str] = []
    if not video_path.is_file():
        errors.append(f"rendered video does not exist: {video_path}")
    if not storyboard_path.is_file():
        errors.append(f"storyboard does not exist: {storyboard_path}")
        rows: list[dict[str, str]] = []
    else:
        with storyboard_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    if not rows:
        errors.append("storyboard has no scenes")
    card_markers = ("caption card", "caption-card", "designed card", "designed-card", "html", "hyperframes", "remotion", "full-frame vertical card")
    screen_markers = ("screen recording", "screen-recording", "app demo", "product demo", "terminal", "browser recording", "录屏", "界面演示")
    card_count = sum(any(marker in str(row.get(field, "")).lower() for field in ("visual", "shot", "visual_treatment", "source_or_prompt", "fallback_visual") for marker in card_markers) for row in rows)
    screen_count = sum(any(marker in str(row.get(field, "")).lower() for field in ("visual", "shot", "visual_treatment", "source_or_prompt", "fallback_visual") for marker in screen_markers) for row in rows)
    card_ratio = card_count / len(rows) if rows else 0.0
    screen_ratio = screen_count / len(rows) if rows else 0.0
    runtime_route = plan.get("video", {}).get("production_route", []) if isinstance(plan.get("video"), dict) else []
    runtime_evidence: dict[str, Any] = {}
    static_evidence = 0
    fresh_video_evidence = 0
    if project:
        evidence_value = str(paths.get("runtime_demo_evidence", "04_video/analysis/runtime-demo-evidence.json"))
        evidence_path = project / evidence_value
        if not evidence_path.is_file():
            errors.append("runtime demo evidence report is missing")
        else:
            runtime_evidence = load(evidence_path)
            evidence_paths = runtime_evidence.get("evidence_paths", []) if isinstance(runtime_evidence.get("evidence_paths"), list) else []
            static_evidence = 0
            fresh_video_evidence = 0
            for value in evidence_paths:
                evidence_file = Path(str(value)).expanduser()
                if not evidence_file.is_absolute():
                    evidence_file = project / evidence_file
                if not evidence_file.is_file():
                    errors.append(f"runtime evidence asset does not exist: {evidence_file}")
                    continue
                if evidence_file.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".ps1", ".txt", ".md"}:
                    static_evidence += 1
                    continue
                stream = probe_video_stream(evidence_file)
                if stream.get("has_video"):
                    fresh_video_evidence += 1
                else:
                    static_evidence += 1
    if card_ratio > 0.45:
        errors.append(f"static card/html scene ratio {card_ratio:.0%} exceeds 45% visual limit")
    duration = probe_duration(video_path) if video_path.is_file() else None
    if duration is None and video_path.is_file():
        warnings.append("ffprobe unavailable; rendered duration was not measured")
    report = {
        "schema_version": 1,
        "status": "ready" if not errors else "blocked",
        "passed": not errors,
        "input": str(video_path),
        "storyboard": str(storyboard_path),
        "metrics": {"scene_count": len(rows), "card_scene_count": card_count, "card_scene_ratio": round(card_ratio, 4), "screen_recording_scene_count": screen_count, "screen_recording_ratio": round(screen_ratio, 4), "runtime_evidence_ratio": runtime_evidence.get("screen_recording_ratio") if runtime_evidence else None, "duration_seconds": duration, "fresh_capture": runtime_evidence.get("fresh_capture") if runtime_evidence else None, "fresh_video_evidence_count": fresh_video_evidence, "static_evidence_count": static_evidence},
        "production_route": runtime_route,
        "recording_policy": "claim-driven; ratio is descriptive only",
        "errors": errors,
        "warnings": warnings,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] or not args.strict else 1


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Run deterministic visual-semantic checks for a Douyin render.")
    root.add_argument("--project", default="")
    root.add_argument("--input", default="")
    root.add_argument("--storyboard", default="")
    root.add_argument("--output", default="")
    root.add_argument("--strict", action="store_true")
    root.set_defaults(handler=main)
    return root


if __name__ == "__main__":
    arguments = parser().parse_args()
    raise SystemExit(arguments.handler(arguments))
