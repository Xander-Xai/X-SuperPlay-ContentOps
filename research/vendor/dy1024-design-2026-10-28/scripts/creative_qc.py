#!/usr/bin/env python3
"""Creative and editorial checks that codec QC cannot see.

The report is intentionally conservative: a technically valid slideshow is not
treated as a finished Douyin video unless it has a usable hook, scene rhythm,
readable evidence and an explicit sound-design decision.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Any

try:
    import teaching_qc
except ImportError:  # imported as scripts.creative_qc in tests
    from scripts import teaching_qc

try:
    from voice_clone_policy import voice_reference_required
except ImportError:  # imported as scripts.creative_qc in tests
    from scripts.voice_clone_policy import voice_reference_required


STATIC_MARKERS = ("screenshot", "architecture", "diagram", "dashboard", "static", "png", "jpg", "card")
MOTION_MARKERS = ("recording", "demo", "video", "tracking", "pan", "zoom", "reveal", "type-on", "cut")
ALLOWED_AVATAR_WINDOWS = {"none", "hook", "transition", "verdict", "cta", "caution", "explainer"}


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"JSON must contain an object: {path}")
    return value


def main(args: argparse.Namespace) -> int:
    project = Path(args.project).expanduser().resolve()
    manifest = load(project / "content.json")
    paths = manifest.get("paths", {}) if isinstance(manifest.get("paths"), dict) else {}
    storyboard_path = project / str(paths.get("storyboard", "04_video/storyboard.csv"))
    ledger_path = project / str(paths.get("asset_ledger", "03_assets/asset-ledger.csv"))
    profile_path = project / str(paths.get("production_profile", "04_video/production-profile.json"))
    output = project / str(paths.get("creative_qc", "05_publish/creative-qc.json"))
    errors: list[str] = []
    warnings: list[str] = []
    rows: list[dict[str, str]] = []
    if not storyboard_path.is_file():
        errors.append(f"storyboard does not exist: {storyboard_path}")
    else:
        with storyboard_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    if not rows:
        errors.append("storyboard has no scenes")

    ledger: dict[str, dict[str, str]] = {}
    if ledger_path.is_file():
        with ledger_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("asset_id"):
                    ledger[str(row["asset_id"])] = row

    def combined(row: dict[str, str]) -> str:
        return " ".join(str(row.get(field, "")) for field in ("visual", "shot", "visual_treatment", "motion", "source_or_prompt")).lower()

    hook_ok = False
    # ``subtitle`` is the complete spoken transcript and may span multiple
    # timed caption cues.  Only the optional ``overlay_text`` graphic layer is
    # subject to the short mobile readability limit.
    overlay_overflow_count = sum(len(str(row.get("overlay_text", "")).strip()) > 24 for row in rows)
    if overlay_overflow_count:
        errors.append(f"{overlay_overflow_count} storyboard overlay_text values exceed 24 mobile-readable characters")
    caption_mismatch_count = 0
    for row in rows:
        voice = re.sub(r"\s+", "", str(row.get("voice", "")).casefold())
        subtitle = re.sub(r"\s+", "", str(row.get("subtitle", "")).casefold())
        if voice and subtitle and voice != subtitle:
            caption_mismatch_count += 1
    if caption_mismatch_count:
        errors.append(f"{caption_mismatch_count} storyboard subtitle rows do not match voice transcript")
    if rows:
        first = rows[0]
        try:
            hook_duration = float(first.get("out", 0) or 0) - float(first.get("in", 0) or 0)
        except (TypeError, ValueError):
            hook_duration = 99.0
        hook_ok = bool(str(first.get("voice", "")).strip() or str(first.get("subtitle", "")).strip()) and hook_duration <= 5.0
        if not hook_ok:
            errors.append("the first scene needs a spoken/on-screen hook within five seconds")

    def is_static(row: dict[str, str]) -> bool:
        asset = ledger.get(str(row.get("asset_id", "")), {})
        asset_path = str(asset.get("filename_or_url", "")).lower()
        extension_static = asset_path.endswith((".png", ".jpg", ".jpeg", ".webp", ".ps1", ".md", ".txt"))
        semantic_static = any(marker in combined(row) for marker in STATIC_MARKERS) and not any(marker in combined(row) for marker in MOTION_MARKERS)
        return extension_static or semantic_static

    static_count = sum(is_static(row) for row in rows)
    static_ratio = static_count / len(rows) if rows else 1.0
    if static_ratio > 0.5:
        errors.append(f"static-scene ratio {static_ratio:.0%} exceeds 50%; add real motion or screen capture")

    longest_static_streak = 0
    streak = 0
    for row in rows:
        streak = streak + 1 if is_static(row) else 0
        longest_static_streak = max(longest_static_streak, streak)
    if longest_static_streak > 2:
        errors.append(f"static scenes run for {longest_static_streak} consecutive shots; maximum is two")

    audio_design = [str(row.get("bgm", "")).strip().lower() for row in rows] + [str(row.get("sfx", "")).strip().lower() for row in rows]
    if audio_design and all(value in {"", "none", "无", "n/a"} for value in audio_design):
        errors.append("storyboard has no BGM or SFX; record an explicit sound-design choice before delivery")

    production = load(profile_path) if profile_path.is_file() else {}
    presenter_mode = str(production.get("presenter_mode", ""))
    voice_mode = str(production.get("voice_mode", ""))
    avatar_windows: list[str] = []
    for row in rows:
        value = str(row.get("avatar_window", row.get("avatar", ""))).strip().lower()
        if not value:
            value = "none"
        if value not in ALLOWED_AVATAR_WINDOWS:
            errors.append(f"scene {row.get('scene_id', '?')} has invalid avatar_window: {value}")
            value = "none"
        elif value != "none" and not str(row.get("avatar_driving_audio", "")).strip():
            errors.append(f"scene {row.get('scene_id', '?')} avatar window '{value}' requires avatar_driving_audio")
        avatar_windows.append(value)
    avatar_scenes = sum(value != "none" for value in avatar_windows)
    avatar_visible_seconds = 0.0
    total_storyboard_seconds = 0.0
    for row, window in zip(rows, avatar_windows):
        try:
            start = float(row.get("in", 0) or 0)
            end = float(row.get("out", start) or start)
            duration = max(0.0, end - start)
        except (TypeError, ValueError):
            duration = 0.0
        total_storyboard_seconds += duration
        if window != "none":
            avatar_visible_seconds += duration
    avatar_visible_share = avatar_visible_seconds / total_storyboard_seconds if total_storyboard_seconds else 0.0
    if presenter_mode == "digital-human" and avatar_visible_share > 0.30:
        warnings.append(f"avatar visible share {avatar_visible_share:.0%} exceeds the project guideline of 30%")
    if presenter_mode == "digital-human" and avatar_scenes == 0:
        errors.append("digital-human mode requires at least one storyboard avatar window")
    if voice_reference_required(voice_mode, presenter_mode) and not str(production.get("voice_reference", "")).strip():
        errors.append("selected voice/presenter mode requires a voice reference in the production profile")

    teaching_report = teaching_qc.run_checks(project, manifest, strict=args.strict, stage="quality")
    teaching_output = project / str(paths.get("teaching_qc", "05_publish/teaching-qc.json"))
    teaching_output.parent.mkdir(parents=True, exist_ok=True)
    teaching_output.write_text(json.dumps(teaching_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if teaching_report.get("required") and not teaching_report.get("passed"):
        errors.extend(f"teaching QC: {item}" for item in teaching_report.get("errors", []))
    warnings.extend(f"teaching QC: {item}" for item in teaching_report.get("warnings", []))

    report = {
        "schema_version": 1,
        "status": "ready" if not errors else "blocked",
        "passed": not errors,
        "input": str(storyboard_path),
        "metrics": {
            "scene_count": len(rows),
            "hook_within_five_seconds": hook_ok,
            "static_scene_count": static_count,
            "static_scene_ratio": round(static_ratio, 4),
            "longest_static_streak": longest_static_streak,
            "avatar_scene_count": avatar_scenes,
            "avatar_visible_seconds": round(avatar_visible_seconds, 3),
            "avatar_visible_share": round(avatar_visible_share, 4),
            "subtitle_overflow_count": 0,
            "overlay_text_overflow_count": overlay_overflow_count,
            "caption_mismatch_count": caption_mismatch_count,
            "presenter_mode": presenter_mode,
            "voice_mode": voice_mode,
            "teaching_required": bool(teaching_report.get("required")),
            "teaching_claim_count": teaching_report.get("metrics", {}).get("claim_count", 0),
            "teaching_proof_scene_count": teaching_report.get("metrics", {}).get("proof_scene_count", 0),
            "teaching_max_theory_streak_seconds": teaching_report.get("metrics", {}).get("max_theory_streak_seconds", 0),
            "teaching_max_evidence_gap_seconds": teaching_report.get("metrics", {}).get("max_evidence_gap_seconds", 0),
        },
        "errors": errors,
        "warnings": warnings,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] or not args.strict else 1


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Run creative/editorial QC for a Douyin video package.")
    root.add_argument("--project", required=True)
    root.add_argument("--strict", action="store_true")
    root.set_defaults(handler=main)
    return root


if __name__ == "__main__":
    arguments = parser().parse_args()
    raise SystemExit(arguments.handler(arguments))
