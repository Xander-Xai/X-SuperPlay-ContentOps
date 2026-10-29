#!/usr/bin/env python3
"""Enforce the Douyin production best-practice contract.

This is deliberately independent from codec QC.  It checks the things that
used to look "green" while still being wrong: copy structure, duration,
asset provenance, final-audio ASR captions, voice parameters, motion ownership,
external HyperFrames/Remotion execution, debug-marker leakage and runtime
configuration disclosure.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
import wave
from pathlib import Path
from typing import Any

try:
    from duration_policy import (
        DEFAULT_TIERS,
        policy_from_profile,
        resolve_tier,
    )
except ImportError:  # imported as scripts.best_practice_qc in tests
    from scripts.duration_policy import (
        DEFAULT_TIERS,
        policy_from_profile,
        resolve_tier,
    )
try:
    import teaching_qc
except ImportError:  # imported as scripts.best_practice_qc in tests
    from scripts import teaching_qc
try:
    from voice_clone_policy import ASR_SIMILARITY_MIN, POLICY_VERSION, SPEAKER_SIMILARITY_MIN, T0_GENERATION, validate_t0_generation
except ImportError:  # imported as scripts.best_practice_qc in tests
    from scripts.voice_clone_policy import ASR_SIMILARITY_MIN, POLICY_VERSION, SPEAKER_SIMILARITY_MIN, T0_GENERATION, validate_t0_generation
try:
    from copy_strategy import validate_strategy
except ImportError:  # imported as scripts.best_practice_qc in tests
    from scripts.copy_strategy import validate_strategy

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = {
    "duration_seconds": [45, 330],
    "duration_policy": {
        "default_tier": "two_minute",
        "tiers": [dict(item) for item in DEFAULT_TIERS],
    },
    "hook_max_seconds": 5,
    "caption_max_chars": 38,
    "subtitle_script_match_min": 0.65,
    "asr_similarity_min": ASR_SIMILARITY_MIN,
    "speaker_similarity_min": SPEAKER_SIMILARITY_MIN,
    "tts_emotion_range": [T0_GENERATION["emotion"], T0_GENERATION["emotion"]],
    "tts_use_random": False,
    "tts_interval_silence_ms": [T0_GENERATION["interval_silence_ms"], T0_GENERATION["interval_silence_ms"]],
    "voice_policy": POLICY_VERSION,
    "forbidden_visual_markers": ["__DEBUG_OVERLAY__", "DESIGNED_CARD", "transition-wash"],
    "motion_contract": {"fps": 30, "primary_component": "remotion", "overlay_component": "hyperframes", "caption_source": "final-audio-asr", "integer_frame_timeline": True},
}


def load(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inside(project: Path, value: str | Path) -> Path:
    candidate = Path(value).expanduser()
    resolved = candidate.resolve() if candidate.is_absolute() else (project / candidate).resolve()
    resolved.relative_to(project.resolve())
    return resolved


def merge_policy(profile: dict[str, Any]) -> dict[str, Any]:
    video = profile.get("video", {}) if isinstance(profile.get("video"), dict) else {}
    value = video.get("best_practice_policy", {}) if isinstance(video.get("best_practice_policy"), dict) else {}
    policy = dict(DEFAULT_POLICY)
    policy.update(value)
    if "duration_seconds" not in value:
        policy["duration_seconds"] = video.get("duration_seconds", policy["duration_seconds"])
    policy["duration_policy"] = policy_from_profile(profile)
    contract = dict(DEFAULT_POLICY["motion_contract"])
    if isinstance(value.get("motion_contract"), dict):
        contract.update(value["motion_contract"])
    policy["motion_contract"] = contract
    return policy


def numbers(value: str) -> list[float]:
    return [float(item) for item in re.findall(r"\d+(?:\.\d+)?", value or "")]


def active_video_project(project: Path, manifest: dict[str, Any]) -> Path:
    video_path = inside(project, manifest.get("paths", {}).get("video", "04_video/video.json"))
    video = load(video_path, {}) or {}
    nested = str(video.get("project_path", "")).strip()
    if nested:
        return inside(project, nested)
    for name in ("render-project-clean", "render-project"):
        candidate = project / "04_video" / name
        if candidate.is_dir():
            return candidate.resolve()
    return project / "04_video" / "render-project-clean"


def _metadata_value(text: str, names: tuple[str, ...]) -> str | None:
    joined = "|".join(re.escape(name) for name in names)
    # Keep field parsing on one physical line. Using ``\s*`` after the
    # delimiter lets a blank value consume the newline and accidentally
    # capture the next metadata field (for example ``pillar`` as
    # ``content_type``).
    match = re.search(rf"(?im)^-[ \t]*(?:{joined})[ \t]*[:：][ \t]*([^\n]+)$", text)
    return match.group(1).strip() if match else None


def _parse_duration_range(raw: str | None) -> list[float] | None:
    if raw is None:
        return None
    match = re.fullmatch(r"(-?\d+(?:\.\d+)?)\s*[–—-]\s*(-?\d+(?:\.\d+)?)\s*s?", raw.strip(), flags=re.IGNORECASE)
    if not match:
        return None
    values = [float(match.group(1)), float(match.group(2))]
    if not all(math.isfinite(value) for value in values) or values[0] > values[1]:
        return None
    return values


def check_duration(
    project: Path,
    manifest: dict[str, Any],
    policy: dict[str, Any],
    errors: list[str],
    evidence: dict[str, Any],
    *,
    require_actual: bool = False,
    require_script_fields: bool = True,
) -> None:
    brief = (project / "00_brief" / "brief.md").read_text(encoding="utf-8", errors="replace") if (project / "00_brief" / "brief.md").is_file() else ""
    script = (project / "04_video" / "video-script.md").read_text(encoding="utf-8", errors="replace") if (project / "04_video" / "video-script.md").is_file() else ""
    brief_type = _metadata_value(brief, ("content_type", "内容类型"))
    script_type = _metadata_value(script, ("content_type", "内容类型"))
    brief_tier = _metadata_value(brief, ("duration_tier", "时长档位"))
    script_tier = _metadata_value(script, ("duration_tier", "时长档位"))
    content_type = (script_type or brief_type or "").strip().lower()
    requested_tier = (script_tier or brief_tier or "").strip().lower()
    if brief_type and script_type and brief_type.strip().lower() != script_type.strip().lower():
        errors.append("brief/script content_type values disagree")
    if brief_tier and script_tier and brief_tier.strip().lower() != script_tier.strip().lower():
        errors.append("brief/script duration_tier values disagree")
    duration_line = _metadata_value(brief, ("目标时长",))
    script_range_raw = _metadata_value(script, ("duration_range",))
    brief_range_match = re.search(r"允许\s*(-?\d+(?:\.\d+)?)\s*[–—-]\s*(-?\d+(?:\.\d+)?)\s*秒?", duration_line or "")
    brief_range_raw = f"{brief_range_match.group(1)}–{brief_range_match.group(2)}s" if brief_range_match else None
    range_values = _parse_duration_range(script_range_raw) if script_range_raw is not None else _parse_duration_range(brief_range_raw)
    if (script_range_raw is not None or brief_range_raw is not None) and range_values is None:
        errors.append("duration_range must be two finite numbers separated by a dash")
    target_raw = _metadata_value(script, ("target_seconds",))
    if target_raw is None and not require_script_fields:
        brief_target_match = re.search(r"(-?\d+(?:\.\d+)?)", duration_line or "")
        target_raw = brief_target_match.group(1) if brief_target_match else None
    target: float | None = None
    if target_raw is None:
        if require_script_fields:
            errors.append("script must declare target_seconds explicitly")
        else:
            errors.append("brief must declare a numeric target duration")
    elif not re.fullmatch(r"-?\d+(?:\.\d+)?", target_raw.strip()):
        errors.append("target_seconds must be a finite number")
    else:
        target = float(target_raw)
        if not math.isfinite(target) or target <= 0:
            errors.append("target_seconds must be a positive finite number")
    duration_policy = policy.get("duration_policy") if isinstance(policy.get("duration_policy"), dict) else {
        "tiers": [dict(item) for item in DEFAULT_TIERS],
        "default_tier": "two_minute",
        "content_type_defaults": {},
    }
    try:
        selected = resolve_tier(
            duration_policy,
            content_type=content_type,
            requested_tier=requested_tier,
            target_seconds=target,
        )
    except ValueError as error:
        errors.append(str(error))
        selected = next(iter({str(item["id"]): item for item in duration_policy.get("tiers", [])}.values()), dict(DEFAULT_TIERS[1]))
    lower, upper = [float(item) for item in selected.get("allowed_range_seconds", [45, 330])[:2]]
    if range_values is None:
        errors.append("brief/script must declare an explicit duration_range inside the selected duration tier")
    if target is not None and (target < lower or target > upper):
        errors.append(f"target duration {target:g}s is outside the selected {selected.get('label', selected.get('id'))} range {lower:g}–{upper:g}s")
    if range_values is not None:
        if target is not None and (range_values[0] > target or range_values[1] < target):
            errors.append("script/brief duration_range must include target_seconds")
        if range_values[0] < lower or range_values[1] > upper:
            errors.append("script/brief duration_range exceeds the selected duration tier")
    actual_duration: float | None = None
    if require_actual:
        video_qc_path = inside(project, manifest.get("paths", {}).get("video_qc", "05_publish/video-qc.json"))
        video_qc = load(video_qc_path, {}) or {}
        metrics = video_qc.get("metrics", {}) if isinstance(video_qc.get("metrics"), dict) else {}
        raw_actual = metrics.get("duration_seconds")
        if video_qc_path.is_file() and isinstance(raw_actual, (int, float)) and not isinstance(raw_actual, bool) and math.isfinite(float(raw_actual)) and float(raw_actual) > 0:
            actual_duration = float(raw_actual)
            if actual_duration < lower or actual_duration > upper:
                errors.append(f"actual media duration {actual_duration:g}s is outside the selected {selected.get('label', selected.get('id'))} range {lower:g}–{upper:g}s")
        else:
            errors.append("final video duration is missing from video-qc.json")
    evidence["duration"] = {
        "content_type": content_type,
        "duration_tier": selected.get("id"),
        "duration_label": selected.get("label"),
        "target_seconds": target,
        "actual_seconds": actual_duration,
        "declared_values": range_values,
        "required_range": [lower, upper],
        "selection_reason": selected.get("selection_reason", ""),
    }


def check_copy(project: Path, policy: dict[str, Any], errors: list[str], evidence: dict[str, Any]) -> None:
    script_path = project / "04_video" / "video-script.md"
    humanized = project / "04_video" / "render-project-clean" / "01_script" / "humanized-script.md"
    script = script_path.read_text(encoding="utf-8", errors="replace") if script_path.is_file() else ""
    human = humanized.read_text(encoding="utf-8", errors="replace") if humanized.is_file() else ""
    required = {
        "structure": ("structure_selected:", "narrative_route:", "hook-total-parts-total", "钩子", "总", "分"),
        "humanizer": ("humanizer_review: passed", "Status: passed", "人化文案"),
        "caption_source": ("caption_source: final-audio-asr", "最终旁白 ASR", "FunASR"),
        "visual_duty": ("visual_duty_contract: required", "画面任务", "每段绑定"),
    }
    asr_ready = (project / "04_video" / "render-project-clean" / "04_audio" / "asr-verification.json").is_file() and (project / "04_video" / "render-project-clean" / "04_audio" / "captions.srt").is_file()
    for label, markers in required.items():
        marker_found = any(marker.lower() in (script + "\n" + human).lower() for marker in markers)
        if label == "caption_source" and asr_ready:
            marker_found = True
        if not marker_found:
            errors.append(f"copy contract missing {label}: add an explicit {markers[0]}")
    strategy_path = project / "00_brief" / "copy-strategy.json"
    if strategy_path.is_file():
        strategy = load(strategy_path, {}) or {}
        strategy_errors = validate_strategy(strategy, require_ready=True)
        errors.extend(f"copy strategy: {item}" for item in strategy_errors)
        selected_angle = str(((strategy.get("angle_board") or {}).get("selected_angle_id", ""))).strip()
        selected_hook = str(((strategy.get("hook_packaging") or {}).get("selected_variant_id", ""))).strip()
        angle_match = re.search(r"(?m)^-\s*strategy_angle_id\s*:\s*(.+)$", script)
        hook_match = re.search(r"(?m)^-\s*strategy_hook_id\s*:\s*(.+)$", script)
        if angle_match and angle_match.group(1).strip() != selected_angle:
            errors.append("copy strategy selected angle is not reflected in the canonical script")
        if hook_match and hook_match.group(1).strip() != selected_hook:
            errors.append("copy strategy selected hook is not reflected in the canonical script")
    else:
        errors.append("copy strategy artifact is missing")
    evidence["copy"] = {"structure": policy.get("structure", "adaptive"), "humanized_script": str(humanized), "passed": not any("copy contract" in item for item in errors)}


def check_storyboard(project: Path, manifest: dict[str, Any], policy: dict[str, Any], errors: list[str], evidence: dict[str, Any]) -> None:
    path = inside(project, manifest.get("paths", {}).get("storyboard", "04_video/storyboard.csv"))
    rows: list[dict[str, str]] = []
    if path.is_file():
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    if not rows:
        errors.append("storyboard is empty; every scene needs a visual duty")
        return
    try:
        first_duration = float(rows[0].get("out", 0)) - float(rows[0].get("in", 0))
    except (TypeError, ValueError):
        first_duration = 999.0
    if first_duration > float(policy.get("hook_max_seconds", 5)):
        errors.append("first storyboard scene does not deliver a hook within five seconds")
    missing_duty = [str(row.get("scene_id", index)) for index, row in enumerate(rows, 1) if not str(row.get("visual", "")).strip() or not str(row.get("asset_id", "")).strip()]
    if missing_duty:
        errors.append("storyboard scenes missing visual/asset duty: " + ", ".join(missing_duty))
    evidence["storyboard"] = {"scene_count": len(rows), "hook_seconds": round(first_duration, 3), "missing_visual_duty": missing_duty}


def check_inventory(project: Path, manifest: dict[str, Any], errors: list[str], evidence: dict[str, Any]) -> None:
    value = manifest.get("paths", {}).get("asset_inventory", "01_research/asset-inventory.json")
    path = inside(project, value)
    payload = load(path)
    if not isinstance(payload, dict) or (payload.get("status") not in {"ready", "approved", None, ""}):
        errors.append("asset inventory is missing or not ready; every source file must have value/role/use/reason")
        return
    records = payload.get("records") if isinstance(payload.get("records"), list) else []
    required_fields = {"path", "role", "value", "use", "reason", "sha256"}
    invalid = [str(item.get("path", index)) for index, item in enumerate(records, 1) if not isinstance(item, dict) or not required_fields.issubset(item)]
    if invalid:
        errors.append("asset inventory records lack required fields: " + ", ".join(invalid[:8]))
    if not records:
        errors.append("asset inventory has no file records")
    evidence["asset_inventory"] = {"path": str(path), "total_files": payload.get("total_files", len(records)), "record_count": len(records), "invalid_records": invalid}


def check_runtime_card(project: Path, manifest: dict[str, Any], errors: list[str], evidence: dict[str, Any]) -> None:
    candidates = []
    for root in (project / "03_assets", project / "04_video"):
        if root.is_dir():
            candidates.extend(path for path in root.rglob("*") if path.is_file() and re.search(r"(config|配置|machine|runtime|model).*(card|config|配置|runtime|model)|card.*(config|配置|machine)", path.name, re.I))
    if not candidates:
        errors.append("runtime video requires a visible computer/model configuration card")
    evidence["computer_model_card"] = {"passed": bool(candidates), "files": [str(item.relative_to(project)).replace("\\", "/") for item in candidates]}


def check_audio_and_captions(project: Path, manifest: dict[str, Any], policy: dict[str, Any], errors: list[str], evidence: dict[str, Any]) -> None:
    nested = active_video_project(project, manifest)
    narration_path = nested / "04_audio" / "narration.json"
    narration = load(narration_path, {}) or {}
    voice_mode = str((manifest.get("production") or {}).get("voice_mode", ""))
    if voice_mode == "voice-clone":
        if narration.get("provider") != "index-tts-2.5" or narration.get("model") != "IndexTTS2.5":
            errors.append("voice-clone must record IndexTTS2.5 provider/model")
        if narration.get("policy_version") != POLICY_VERSION:
            errors.append("voice-clone must record the canonical T0 policy version")
        params = narration.get("generation_parameters") if isinstance(narration.get("generation_parameters"), dict) else {}
        core = {key: params.get(key) for key in T0_GENERATION if key in params}
        try:
            validate_t0_generation(core)
        except ValueError as error:
            errors.append(f"TTS generation parameters are not canonical T0: {error}")
        if params.get("use_random") not in (None, False):
            errors.append("legacy use_random=true is not allowed in the production voice path")
        cleanup = params.get("audio_cleanup_report") if isinstance(params.get("audio_cleanup_report"), dict) else {}
        if cleanup.get("passed") is not True:
            errors.append("voice-clone audio cleanup must pass before production quality")
        if float(narration.get("speaker_similarity", 0) or 0) < SPEAKER_SIMILARITY_MIN:
            errors.append("speaker similarity is below the locked threshold")
    asr_path = nested / "04_audio" / "asr-verification.json"
    asr = load(asr_path, {}) or {}
    if asr.get("status") != "verified" or asr.get("engine") != "funasr" or asr.get("generated_by") != "funasr":
        errors.append("captions must be generated and verified by FunASR from the final narration")
    if float(asr.get("similarity", 0) or 0) < ASR_SIMILARITY_MIN:
        errors.append("ASR similarity is below the locked threshold")
    if asr.get("missing_terms") not in ([], None):
        errors.append("ASR critical terms are missing")
    srt = nested / "04_audio" / "captions.srt"
    if not srt.is_file():
        errors.append("final-audio ASR captions.srt is missing")
    subtitle_path = inside(project, manifest.get("paths", {}).get("subtitle_qc", "05_publish/subtitle-qc.json"))
    subtitle = load(subtitle_path, {}) or {}
    if subtitle.get("passed") is not True:
        errors.append("subtitle QC must pass before production quality")
    if float(subtitle.get("script_match", 0) or 0) < float(policy.get("subtitle_script_match_min", 0.65)):
        errors.append("subtitle/script match is below the locked threshold")
    limits = subtitle.get("limits", {}) if isinstance(subtitle.get("limits"), dict) else {}
    if int(limits.get("max_chars", 999) or 999) > int(policy.get("caption_max_chars", 38)):
        errors.append("subtitle max_chars exceeds the mobile safe limit")
    evidence["audio_captions"] = {"narration": str(narration_path), "asr": str(asr_path), "subtitle_qc": str(subtitle_path), "cue_count": subtitle.get("cue_count", 0), "asr_similarity": asr.get("similarity"), "script_match": subtitle.get("script_match")}


def check_motion(project: Path, manifest: dict[str, Any], policy: dict[str, Any], errors: list[str], evidence: dict[str, Any]) -> None:
    report_path = inside(project, manifest.get("paths", {}).get("motion_render_report", "05_publish/motion-render-report.json"))
    report = load(report_path, {}) or {}
    audit_path = inside(project, manifest.get("paths", {}).get("motion_adversarial_audit", "05_publish/motion-adversarial-audit.json"))
    audit = load(audit_path, {}) or {}
    if report.get("passed") is not True or report.get("status") not in {"ready", "conditional"}:
        errors.append("motion render report is not passed")
    if bool(policy.get("require_external_motion_render", True)) and report.get("external_cli_invoked") is not True:
        errors.append("production requires actual HyperFrames and Remotion CLI execution; authoring-only is insufficient")
    if audit.get("passed") is not True or audit.get("status") not in {"ready", "conditional"}:
        errors.append("motion adversarial audit is missing or has not passed")
    if report.get("status") == "ready" and audit.get("status") != "ready":
        errors.append("an external motion render requires a ready adversarial audit")
    components = report.get("components", {}) if isinstance(report.get("components"), dict) else {}
    for component in ("hyperframes-render", "remotion-render"):
        item = components.get(component, {}) if isinstance(components.get(component), dict) else {}
        if item.get("exit_code") != 0:
            errors.append(f"{component} has no successful exit_code=0 evidence")
    html_path = inside(project, manifest.get("paths", {}).get("hyperframes_composition", "06_motion/hyperframes-native/index.html"))
    html = html_path.read_text(encoding="utf-8", errors="replace") if html_path.is_file() else ""
    for marker in policy.get("forbidden_visual_markers", []):
        if str(marker) in html:
            errors.append(f"forbidden visual/debug marker found in HyperFrames HTML: {marker}")
    root_path = project / "06_motion" / "remotion" / "src" / "Root.tsx"
    root_text = root_path.read_text(encoding="utf-8", errors="replace") if root_path.is_file() else ""
    for marker in list(policy.get("forbidden_visual_markers", [])) + ["scene.route_id"]:
        if str(marker) in root_text:
            errors.append(f"forbidden visual/debug marker found in Remotion source: {marker}")
    timeline = load(project / "04_video" / "timeline.json", {}) or {}
    motion_input = load(project / "06_motion" / "remotion" / "motion-input.json", {}) or {}
    contract = policy.get("motion_contract", {})
    if int(timeline.get("fps", 0) or 0) != int(contract.get("fps", 30)) or int(motion_input.get("fps", 0) or 0) != int(contract.get("fps", 30)):
        errors.append("motion fps must be the locked 30fps contract")
    if contract.get("integer_frame_timeline") and (not timeline.get("total_frames") or any("start_frame" not in item or "duration_frames" not in item for item in motion_input.get("scenes", []) if isinstance(item, dict))):
        errors.append("motion must use a canonical integer-frame timeline")
    caption_source = str(motion_input.get("caption_source", ""))
    caption_kind = str(motion_input.get("caption_source_kind", ""))
    if caption_kind != contract.get("caption_source") and not caption_source.replace("\\", "/").lower().endswith("captions.srt"):
        errors.append("Remotion caption_source must be final-audio-asr")
    evidence["motion"] = {"report": str(report_path), "adversarial_audit": str(audit_path), "adversarial_audit_status": audit.get("status"), "external_cli_invoked": report.get("external_cli_invoked"), "components": {key: components.get(key, {}).get("exit_code") for key in ("hyperframes-render", "remotion-render")}, "timeline_frames": timeline.get("total_frames"), "caption_source": caption_source, "caption_source_kind": caption_kind or ("final-audio-asr" if caption_source.replace("\\", "/").lower().endswith("captions.srt") else "")}


def check_avatar(project: Path, manifest: dict[str, Any], errors: list[str], evidence: dict[str, Any]) -> None:
    production = manifest.get("production", {}) if isinstance(manifest.get("production"), dict) else {}
    presenter_mode = str(production.get("presenter_mode", ""))
    nested = active_video_project(project, manifest)
    video = load(nested / "video.json", {}) or {}
    avatar = video.get("avatar", {}) if isinstance(video.get("avatar"), dict) else {}
    if presenter_mode == "digital-human":
        if avatar.get("enabled") is not True:
            errors.append("digital-human presenter mode requires avatar.enabled=true")
        sync = load(nested / "05_avatar" / "sync-metrics.json", {}) or {}
        if sync and sync.get("passed") is not True:
            errors.append("digital-human sync metrics did not pass")
    elif presenter_mode == "voiceover-only" and avatar.get("enabled") is True:
        errors.append("voiceover-only mode cannot silently enable avatar rendering")
    evidence["avatar"] = {"presenter_mode": presenter_mode, "avatar_enabled": avatar.get("enabled", False), "claim_policy": "exact-lipsync-required" if presenter_mode == "digital-human" else "no-avatar-claim"}


def run_checks(project: Path, *, enforce: bool = True, teaching_stage: str = "quality") -> dict[str, Any]:
    project = project.resolve()
    manifest = load(project / "content.json", {}) or {}
    profile = load(ROOT / "profiles" / "profile.json", {}) or {}
    policy = merge_policy(profile)
    errors: list[str] = []
    evidence: dict[str, Any] = {}
    check_duration(project, manifest, policy, errors, evidence, require_actual=True)
    check_copy(project, policy, errors, evidence)
    check_storyboard(project, manifest, policy, errors, evidence)
    if bool(policy.get("require_asset_inventory", True)):
        check_inventory(project, manifest, errors, evidence)
    if bool(manifest.get("runtime_required")) and bool(policy.get("require_computer_model_card_for_runtime", True)):
        check_runtime_card(project, manifest, errors, evidence)
    check_audio_and_captions(project, manifest, policy, errors, evidence)
    check_motion(project, manifest, policy, errors, evidence)
    check_avatar(project, manifest, errors, evidence)
    teaching_report = teaching_qc.run_checks(project, manifest, strict=True, stage=teaching_stage)
    evidence["teaching"] = teaching_report
    if teaching_report.get("required") and not teaching_report.get("passed"):
        errors.extend(f"teaching QC: {item}" for item in teaching_report.get("errors", []))
    return {"schema_version": 1, "content_id": manifest.get("content_id", ""), "account": manifest.get("account", ""), "status": "ready" if not errors else "blocked", "passed": not errors, "enforced": enforce, "policy": policy, "errors": sorted(set(errors)), "warnings": [], "evidence": evidence}


def main(args: argparse.Namespace) -> int:
    project = Path(args.project).expanduser().resolve()
    report = run_checks(project, enforce=args.enforce, teaching_stage=args.teaching_stage)
    manifest = load(project / "content.json", {}) or {}
    output = Path(args.output).expanduser().resolve() if args.output else inside(project, manifest.get("paths", {}).get("best_practice_qc", "05_publish/best-practice-qc.json"))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # The report is UTF-8 JSON. Keep diagnostics printable on Windows hosts
    # whose legacy console encoding is GBK, otherwise a valid failed QC can
    # crash before the caller receives the machine-readable result.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] or not args.strict else 1


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Enforce the locked Douyin best-practice production contract.")
    root.add_argument("--project", required=True)
    root.add_argument("--output")
    root.add_argument("--enforce", action="store_true", help="record this as a production-enforced check")
    root.add_argument("--strict", action="store_true")
    root.add_argument("--teaching-stage", choices=("review", "quality"), default="quality")
    root.set_defaults(handler=main)
    return root


if __name__ == "__main__":
    arguments = parser().parse_args()
    raise SystemExit(arguments.handler(arguments))
