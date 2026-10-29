#!/usr/bin/env python3
"""Check controlled colloquial copy without weakening the evidence contract.

The check is intentionally small and deterministic.  It does not try to score
whether prose is "human".  It verifies the production decisions that make a
technical script sound less like a report: a bounded number of human touches,
varied transitions, explicit delivery notes, and protected facts that survive
the humanizer pass.
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
except ImportError:  # imported as scripts.naturalness_qc
    from scripts import teaching_qc


HUMAN_TOUCHES = {"none", "direct_address", "reaction", "aside", "short_pause"}
CLAIM_MODES = {"fact", "method", "result", "boundary", "opinion", "transition", "question", "action", ""}
REPEATED_FILLERS = ("其实", "说白了", "你看", "简单来说", "我跟你说", "大家都知道")
TRANSITIONS = ("先看", "再看", "最后", "所以", "换句话说", "先把话说清楚")


def load_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def inside(project: Path, value: str) -> Path:
    candidate = (project / value).resolve()
    candidate.relative_to(project.resolve())
    return candidate


def _metadata(text: str, key: str) -> str:
    match = re.search(rf"(?im)^-\s*{re.escape(key)}\s*[:：]\s*([^\n]+)$", text)
    return match.group(1).strip() if match else ""


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def _int(value: Any, fallback: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return fallback


def _split_tokens(value: Any) -> list[str]:
    if isinstance(value, list):
        values = value
    else:
        values = str(value or "").split(",")
    return [str(item).strip() for item in values if str(item).strip()]


def _touch_plan(value: str) -> dict[str, str]:
    plan: dict[str, str] = {}
    for item in str(value or "").split(";"):
        if "=" not in item:
            continue
        scene, touch = item.split("=", 1)
        if scene.strip() and touch.strip():
            plan[scene.strip()] = touch.strip().lower()
    return plan


def run_checks(project: Path, manifest: dict[str, Any] | None = None, *, strict: bool = True) -> dict[str, Any]:
    project = project.resolve()
    manifest = manifest if isinstance(manifest, dict) else (load_json(project / "content.json", {}) or {})
    paths = manifest.get("paths", {}) if isinstance(manifest.get("paths"), dict) else {}
    script_path = inside(project, str(paths.get("video_script", "04_video/video-script.md")))
    storyboard_path = inside(project, str(paths.get("storyboard", "04_video/storyboard.csv")))
    contract_path = inside(project, str(paths.get("teaching_contract", "04_video/teaching-contract.json")))
    script = script_path.read_text(encoding="utf-8", errors="replace") if script_path.is_file() else ""
    contract = load_json(contract_path, {})
    voice = contract.get("narrative_voice") if isinstance(contract, dict) and isinstance(contract.get("narrative_voice"), dict) else {}
    mode = str(_metadata(script, "narrative_voice") or voice.get("mode", "")).strip().lower()
    if not mode:
        return {
            "schema_version": 1,
            "status": "not_required",
            "passed": True,
            "required": False,
            "errors": [],
            "warnings": ["narrative_voice is not declared; copy package metadata is incomplete"],
            "metrics": {},
        }

    errors: list[str] = []
    warnings: list[str] = []
    rows = _rows(storyboard_path)
    if not rows:
        errors.append("naturalness QC requires a non-empty storyboard")
    if mode not in {"neutral-technical", "controlled-colloquial", "formal"}:
        errors.append(f"invalid narrative_voice mode: {mode}")

    budget = _int(voice.get("colloquial_budget"), _int(_metadata(script, "colloquial_budget"), 0))
    max_per_scene = _int(voice.get("max_per_scene"), _int(_metadata(script, "max_colloquial_per_scene"), 1))
    max_consecutive = _int(voice.get("max_consecutive"), _int(_metadata(script, "max_consecutive_colloquial"), 2))
    allowed = set(_split_tokens(voice.get("allowed_moves"))) or set(_split_tokens(_metadata(script, "allowed_human_touches")))
    if mode == "controlled-colloquial" and not allowed:
        errors.append("controlled-colloquial mode must declare allowed human-touch types")
    unknown_allowed = sorted(allowed - HUMAN_TOUCHES)
    if unknown_allowed:
        errors.append("narrative_voice allowed_moves contains unknown types: " + ", ".join(unknown_allowed))

    touch_count = 0
    touch_scenes: list[str] = []
    max_scene_touch = 0
    consecutive = 0
    max_consecutive_seen = 0
    voice_text: list[str] = []
    planned_touches = _touch_plan(_metadata(script, "human_touch_plan"))
    scene_lengths: list[int] = []
    invalid_touch_scenes: list[str] = []
    invalid_claim_modes: list[str] = []
    for row in rows:
        scene_id = str(row.get("scene_id", "?")).strip() or "?"
        touch = str(row.get("human_touch", "")).strip().lower() or planned_touches.get(scene_id, "none")
        if touch not in HUMAN_TOUCHES or (touch != "none" and touch not in allowed):
            invalid_touch_scenes.append(f"{scene_id}:{touch}")
        has_touch = touch != "none"
        if has_touch:
            touch_count += 1
            touch_scenes.append(scene_id)
            consecutive += 1
        else:
            consecutive = 0
        max_consecutive_seen = max(max_consecutive_seen, consecutive)
        max_scene_touch = max(max_scene_touch, 1 if has_touch else 0)
        claim_mode = str(row.get("claim_mode", "")).strip().lower()
        if claim_mode not in CLAIM_MODES:
            invalid_claim_modes.append(f"{scene_id}:{claim_mode}")
        text = str(row.get("voice", "")).strip()
        if text:
            voice_text.append(text)
            scene_lengths.append(max((len(part.strip()) for part in re.split(r"[。！？!?；;]", text) if part.strip()), default=0))
        if has_touch and not str(row.get("delivery_note", "")).strip():
            errors.append(f"scene {scene_id} has human_touch={touch} but no delivery_note")

    if invalid_touch_scenes:
        errors.append("invalid or undeclared human-touch types: " + ", ".join(invalid_touch_scenes))
    if invalid_claim_modes:
        errors.append("invalid storyboard claim_mode values: " + ", ".join(invalid_claim_modes))
    if touch_count > budget:
        errors.append(f"colloquial touch count {touch_count} exceeds budget {budget}")
    if max_scene_touch > max_per_scene:
        errors.append(f"scene colloquial touch count exceeds max_per_scene {max_per_scene}")
    if max_consecutive_seen > max_consecutive:
        errors.append(f"consecutive colloquial scenes {max_consecutive_seen} exceeds max_consecutive {max_consecutive}")

    combined_voice = " ".join(voice_text)
    filler_counts = {phrase: combined_voice.count(phrase) for phrase in REPEATED_FILLERS if combined_voice.count(phrase)}
    repeated = {phrase: count for phrase, count in filler_counts.items() if count > 2}
    if repeated:
        errors.append("repeated filler phrases exceed two uses: " + ", ".join(f"{key}={value}" for key, value in sorted(repeated.items())))
    transition_counts = {phrase: sum(text.startswith(phrase) for text in voice_text) for phrase in TRANSITIONS}
    transition_repeats = {phrase: count for phrase, count in transition_counts.items() if count > 2}
    if transition_repeats:
        warnings.append("transition repetition may make the script sound templated: " + ", ".join(f"{key}={value}" for key, value in sorted(transition_repeats.items())))
    if scene_lengths and max(scene_lengths) > 70:
        warnings.append(f"longest spoken sentence is {max(scene_lengths)} characters; consider a short beat before the next fact")

    # A humanizer pass may change connective wording, but it must not remove
    # explicitly protected experiment terms or numbers.
    humanized = project / "04_video" / "render-project-clean" / "01_script" / "humanized-script.md"
    protected = _split_tokens(voice.get("fact_lock_tokens"))
    if protected and humanized.is_file():
        human_text = humanized.read_text(encoding="utf-8", errors="replace")
        missing = [token for token in protected if token not in human_text]
        if missing:
            errors.append("humanized script is missing fact-lock tokens: " + ", ".join(missing))
    elif protected and not humanized.is_file():
        warnings.append("fact-lock tokens declared but humanized script is not present yet")

    metrics = {
        "narrative_voice": mode,
        "colloquial_budget": budget,
        "colloquial_touch_count": touch_count,
        "colloquial_touch_scenes": touch_scenes,
        "max_consecutive_colloquial": max_consecutive_seen,
        "max_sentence_chars": max(scene_lengths, default=0),
        "fact_lock_token_count": len(protected),
        "fact_lock_checked": bool(protected and humanized.is_file()),
    }
    return {
        "schema_version": 1,
        "status": "ready" if not errors else "blocked",
        "passed": not errors,
        "required": True,
        "script": str(script_path),
        "storyboard": str(storyboard_path),
        "contract": str(contract_path),
        "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "metrics": metrics,
    }


def main(args: argparse.Namespace) -> int:
    project = Path(args.project).expanduser().resolve()
    manifest = load_json(project / "content.json", {}) or {}
    report = run_checks(project, manifest, strict=args.strict)
    paths = manifest.get("paths", {}) if isinstance(manifest.get("paths"), dict) else {}
    output = project / str(paths.get("naturalness_qc", "05_publish/naturalness-qc.json"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] or not args.strict else 1


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Check controlled-colloquial copy, rhythm variation and fact locks.")
    root.add_argument("--project", required=True)
    root.add_argument("--strict", action="store_true")
    root.set_defaults(handler=main)
    return root


if __name__ == "__main__":
    arguments = parser().parse_args()
    raise SystemExit(arguments.handler(arguments))
