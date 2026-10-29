#!/usr/bin/env python3
"""Fail-closed checks for the canonical storyboard, visual routes and provenance."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any


CORE_REAL_ROUTES = {
    "hyperframes", "remotion", "remotion-captions", "open-design", "penpot",
    "beautiful-mermaid", "playwright", "index-tts",
    "openchatcut",
}

ROUTE_FORBIDDEN_SUBSTITUTES = {
    "remotion": ("visual_card_renderer.py", "production/media_delivery.py render"),
    "remotion-captions": ("production/media_delivery.py render", "video_pipeline.py render"),
    "open-design": ("visual_card_renderer.py",),
    "penpot": ("visual_card_renderer.py",),
    "beautiful-mermaid": ("visual_card_renderer.py",),
    "playwright": ("render_project_visual_cards_fallback", "Playwright render unavailable"),
}


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalized(value: Any) -> str:
    return "".join(str(value or "").split()).casefold()


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def storyboard(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {str(row.get("scene_id", "")): row for row in csv.DictReader(handle) if row.get("scene_id")}


def run(args: argparse.Namespace) -> int:
    project = Path(args.project).expanduser().resolve()
    manifest = load(project / "content.json")
    paths = manifest.get("paths", {}) if isinstance(manifest.get("paths"), dict) else {}
    errors: list[str] = []
    warnings: list[str] = []

    outer_storyboard_path = project / str(paths.get("storyboard", "04_video/storyboard.csv"))
    outer_video_path = project / str(paths.get("video", "04_video/video.json"))
    outer = load(outer_video_path)
    nested_path = Path(str(outer.get("project_path", "")))
    if not nested_path.is_absolute():
        nested_path = project / nested_path
    nested_video_path = nested_path / "video.json"
    outer_rows = storyboard(outer_storyboard_path) if outer_storyboard_path.is_file() else {}
    if not outer_rows:
        errors.append(f"canonical storyboard is missing or empty: {outer_storyboard_path}")
    if not nested_video_path.is_file():
        errors.append(f"nested video manifest is missing: {nested_video_path}")
        nested = {}
    else:
        nested = load(nested_video_path)

    nested_scenes = {str(item.get("id", "")): item for item in nested.get("scenes", []) if isinstance(item, dict) and item.get("id")}
    if set(outer_rows) != set(nested_scenes):
        errors.append("outer storyboard scene IDs and nested video.json scene IDs must match exactly")
    for scene_id in sorted(set(outer_rows) & set(nested_scenes)):
        outer_row = outer_rows[scene_id]
        nested_scene = nested_scenes[scene_id]
        if normalized(outer_row.get("voice")) != normalized(nested_scene.get("voice")):
            errors.append(f"scene {scene_id} voice differs between outer storyboard and nested video.json")
        try:
            outer_in, outer_out = float(outer_row.get("in", 0)), float(outer_row.get("out", 0))
            nested_duration = float(nested_scene.get("duration", 0))
        except (TypeError, ValueError):
            errors.append(f"scene {scene_id} has invalid timing")
            continue
        if abs((outer_out - outer_in) - nested_duration) > 0.05:
            errors.append(f"scene {scene_id} duration differs between outer storyboard and nested video.json")

    visual_value = paths.get("visual_route", "04_video/visual-route.json")
    visual_path = project / str(visual_value)
    visual = load(visual_path) if visual_path.is_file() else {}
    routes = visual.get("routes", []) if isinstance(visual.get("routes", []), list) else []
    for route in routes:
        if not isinstance(route, dict):
            errors.append("visual route contains a non-object scene")
            continue
        if route.get("status") != "executed":
            errors.append(f"visual route {route.get('scene_id', '?')} is not executed")
        asset = Path(str(route.get("rendered_asset", "")))
        if not asset.is_absolute():
            asset = project / asset
        if not asset.is_file():
            errors.append(f"visual route {route.get('scene_id', '?')} has no executed artifact")
        if str(route.get("execution", {}).get("renderer", "")) == "local-cs-board-stream":
            review = Path(str(route.get("review_asset", "")))
            if not review.is_absolute():
                review = project / review
            if not review.is_file():
                errors.append(f"visual route {route.get('scene_id', '?')} has no CS Board review PNG")
            else:
                expected_review = str(route.get("execution", {}).get("review_output_sha256", ""))
                if not expected_review or digest(review) != expected_review:
                    renderer = str(route.get("execution", {}).get("renderer", ""))
                    errors.append(f"visual route {route.get('scene_id', '?')} {renderer} review PNG fingerprint is stale")

    provenance_value = paths.get("skill_provenance", "05_publish/skill-provenance.json")
    provenance_path = project / str(provenance_value)
    provenance = load(provenance_path) if provenance_path.is_file() else {}
    provenance_records = provenance.get("records", []) if isinstance(provenance.get("records"), list) else []
    # Receipts are append-only. A later prepare/render legitimately rewrites
    # the same output and makes an older receipt stale; validate only the
    # latest receipt for each core renderer so historical fingerprints do not
    # veto a newer successful execution.
    latest_core_records: dict[str, dict[str, Any]] = {}
    for candidate in provenance_records:
        if isinstance(candidate, dict):
            route_key = str(candidate.get("route", "")).strip().lower()
            if route_key in CORE_REAL_ROUTES:
                latest_core_records[route_key] = candidate
    for record in provenance_records:
        if not isinstance(record, dict):
            continue
        route = str(record.get("route", "")).strip().lower()
        if route in CORE_REAL_ROUTES and latest_core_records.get(route) is not record:
            continue
        mode = str(record.get("execution_mode", "declarative")).strip().lower()
        command = str(record.get("command", ""))
        evidence_command = str(record.get("real_command", command))
        outputs = record.get("outputs", []) if isinstance(record.get("outputs"), list) else []
        if route in CORE_REAL_ROUTES and mode != "real":
            errors.append(f"core route {route} is recorded as {mode}, not real")
        if route in CORE_REAL_ROUTES and mode == "real":
            try:
                exit_code = int(record.get("exit_code", 1))
            except (TypeError, ValueError):
                exit_code = 1
            if not command.strip() or exit_code != 0:
                errors.append(f"core route {route} has no successful command evidence")
            for output in outputs:
                if not isinstance(output, dict):
                    continue
                output_path = Path(str(output.get("path", "")))
                if not output_path.is_file() or digest(output_path) != str(output.get("sha256", "")):
                    errors.append(f"core route {route} output fingerprint is stale or missing")
            for substitute in ROUTE_FORBIDDEN_SUBSTITUTES.get(route, ()):
                if substitute.lower() in evidence_command.lower():
                    errors.append(f"core route {route} is backed by a substitute command, not its declared renderer")
            if route == "openchatcut" and mode == "real":
                bridge = next((item for item in outputs if isinstance(item, dict) and str(item.get("path", "")).endswith("openchatcut-bridge.json")), None)
                if bridge:
                    bridge_path = Path(str(bridge.get("path")))
                    try:
                        bridge_payload = load(bridge_path)
                    except (FileNotFoundError, json.JSONDecodeError, OSError):
                        bridge_payload = {}
                    native_project_path = str(bridge_payload.get("native_project_path", "")).strip() if isinstance(bridge_payload, dict) else ""
                    if not native_project_path:
                        errors.append("OpenChatCut provenance must point to a saved native project; FCPXML bridge alone is not execution")

    report = {
        "schema_version": 1,
        "content_id": manifest.get("content_id", ""),
        "status": "ready" if not errors else "blocked",
        "passed": not errors,
        "canonical_storyboard": str(outer_storyboard_path),
        "nested_video_manifest": str(nested_video_path),
        "outer_scene_count": len(outer_rows),
        "nested_scene_count": len(nested_scenes),
        "errors": errors,
        "warnings": warnings,
    }
    output = project / str(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] or not args.strict else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check canonical storyboard and real execution evidence.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--output", default="05_publish/pipeline-integrity-qc.json")
    parser.add_argument("--strict", action="store_true")
    parser.set_defaults(handler=run)
    return parser


if __name__ == "__main__":
    arguments = build_parser().parse_args()
    raise SystemExit(arguments.handler(arguments))
