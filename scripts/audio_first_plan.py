#!/usr/bin/env python3
"""Plan a cut from the voice, not the other way round.

The benchmark's confirmed production rule is audio-first: write the script,
synthesise it, measure each line, and only then size the shots. This driver
does exactly that and writes two receipts:

- ``receipts/audio-first-plan.json`` — measured speech, the window derived from
  it, and the voice that produced it;
- ``script/cut-plan.json`` — placements whose windows come from those
  measurements, each split into views no longer than the hold limit.

It does not compose anything; run ``build_evidence_package.py`` afterwards.
The narration cache is shared with ``build_evidence_cut`` so the later build
makes no second provider request.

The evidence mode and the recording policy come from the account DNA, resolved
through ``account_slug``; ``lines.json`` may repeat them only to agree. Whether
an account needs recordings at all is its own decision, not a per-episode one.

Usage::

    python scripts/audio_first_plan.py projects/easel-fi-audio-first
    python scripts/audio_first_plan.py projects/easel-fi-audio-first --replan
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from process_utils import hidden_run, python_executable  # noqa: E402
from contentops.evidence._common import sha256_file  # noqa: E402
from contentops.media.claim_coverage import composition_policy_errors  # noqa: E402
from contentops.media.transport import ffprobe_json  # noqa: E402

NARRATION = ROOT / "scripts" / "synthesize_narration.py"
PLAN_SCHEMA = "contentops.audio-first-plan/v1"
VOICE = "speech-2.8-hd"

#: V2 engineering-cut limits. A view may not stand still past MAX_HOLD, and a
#: key-evidence view may not be shorter than MIN_READING.
MAX_HOLD_MS = 3000
MIN_READING_MS = 2500
TAIL_MS = 400


def _fail(code: str, detail: str) -> None:
    raise SystemExit(json.dumps({"status": "BLOCKED", "code": code,
                                 "reason": detail}, ensure_ascii=False, indent=2))


def _yaml(path: Path) -> Dict[str, str]:
    data = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        data[key.strip()] = value.strip().strip('"')
    return data


def _track_provider_receipt(project: Path, digest: str) -> str | None:
    """Point at the provider receipt without copying it.

    ``projects/*/assets/voice/`` is ignored, and the provider receipt records
    absolute output paths and plan-quota percentages, so it stays host-local
    with the audio it describes. The plan receipt records the logical reference.
    """
    source = project / "assets" / "voice" / "tts" / f"{digest}.provider.json"
    if not source.is_file():
        return None
    return f"project://{source.relative_to(project).as_posix()}"


def _account_policy(config: Dict[str, str], lines: Dict[str, Any]) -> Dict[str, Any]:
    """The account owns the evidence mode and the recording policy, not the episode.

    ``lines.json`` used to carry both, and defaulted ``manual_recording`` to
    ``ALLOWED_CROPPED`` -- so an account that forbids recording silently became
    one that allows it as soon as the field was left out, and the
    ``manual_recording_forbidden`` gate stopped applying at the same moment.
    These two fields are account identity: an episode may repeat them, but only
    to agree.

    The composition is per-episode, so ``lines.json`` may declare its own; with
    no declaration the account default applies. Either way it has to satisfy the
    mode that governs it, which is the comparison nothing used to make.
    """
    slug = config.get("account_slug")
    if not slug:
        _fail("ACCOUNT_SLUG_MISSING",
              "project.yaml declares no account_slug, so no account DNA resolves")
    dna_path = ROOT / "config" / "accounts" / f"{slug}.json"
    if not dna_path.is_file():
        _fail("ACCOUNT_DNA_MISSING", str(dna_path))
    dna = json.loads(dna_path.read_text(encoding="utf-8"))
    evidence = dna["evidence"]
    mode = evidence.get("mode")
    recording = evidence.get("manual_recording")
    for field, owned in (("evidence_mode", mode), ("manual_recording", recording)):
        declared = lines.get(field)
        if declared is not None and declared != owned:
            _fail("ACCOUNT_POLICY_OVERRIDE",
                  f"lines.json declares {field}={declared!r} but {slug} owns "
                  f"{owned!r}; fix the DNA or drop the field from lines.json")
    composition = lines.get("composition") or dna["visual"]["composition"]["segments"]
    problems = composition_policy_errors(mode, composition)
    if problems:
        _fail("COMPOSITION_OUT_OF_POLICY", f"{slug}: " + "; ".join(problems))
    return {"evidence_mode": mode, "manual_recording": recording,
            "composition": composition}


def _crop(crop: Dict[str, int], assets: Dict[str, Any], asset_id: str,
          width: int, height: int) -> Dict[str, int]:
    """Fill source dimensions a card author does not repeat in lines.json."""
    asset = assets.get(asset_id, {})
    source = asset.get("source_dimensions") or {}
    return {
        **crop,
        "source_width": crop.get("source_width")
        or source.get("width") or asset.get("width") or width,
        "source_height": crop.get("source_height")
        or source.get("height") or asset.get("height") or height,
    }


def _cache(project: Path, text: str) -> Dict[str, Any]:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    wav = project / "assets" / "voice" / f"{digest}.wav"
    receipt_path = wav.with_suffix(".receipt.json")
    if wav.is_file() and receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        return {"path": wav, "duration_s": float(receipt["asset"]["duration_s"]),
                "cached": True,
                "provider_receipt": _track_provider_receipt(project, digest)}

    wav.parent.mkdir(parents=True, exist_ok=True)
    provider_dir = wav.parent / "tts"
    provider_receipt = provider_dir / f"{digest}.provider.json"
    provider_dir.mkdir(parents=True, exist_ok=True)
    result = hidden_run(
        [python_executable(), str(NARRATION), "--text", text,
         "--language", "zh", "--out-dir", str(provider_dir),
         "--receipt", str(provider_receipt)],
        cwd=str(ROOT), timeout=600,
    )
    if result.returncode != 0 or not provider_receipt.is_file():
        _fail("TTS_FAILED", (result.stderr or result.stdout or "")[-600:])
    provider = json.loads(provider_receipt.read_text(encoding="utf-8"))
    produced = Path(provider["asset"]["normalized_path"])
    if not produced.is_file():
        _fail("TTS_OUTPUT_MISSING", str(produced))
    shutil.copy2(produced, wav)
    duration = float(provider["asset"]["duration_s"])
    receipt = {
        "schema": "contentops.narration-asset/v1",
        "voice_quality": "minimax_mplan_subscription",
        "voice_provider": "miniMax/speech-2.8-hd",
        "voice": VOICE,
        "asset": {
            "normalized_path": str(wav),
            "sha256": sha256_file(wav),
            "duration_s": duration,
        },
        "provider_receipt": str(provider_receipt),
        "production_ready": False,
        "human_review": "PENDING_FOUNDER_REVIEW",
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False),
                            encoding="utf-8")
    return {"path": wav, "duration_s": duration, "cached": False,
            "provider_receipt": _track_provider_receipt(project, digest)}


def _window_ms(speech_s: float) -> int:
    needed_ms = (speech_s * 1000.0) + TAIL_MS
    if needed_ms > 6000:
        _fail("LINE_TOO_LONG",
              f"{speech_s:.2f}s of speech needs more than 6.0s; split the line "
              f"instead of holding one view longer")
    window = max(5000, int(math.ceil(needed_ms / 500.0) * 500))
    return window


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("project")
    parser.add_argument("--force", action="store_true", help="re-synthesise")
    parser.add_argument("--replan", action="store_true",
                        help="rewrite the cut plan from the existing audio")
    args = parser.parse_args()

    project = Path(args.project)
    if not project.is_absolute():
        project = ROOT / project
    project = project.resolve()

    config = _yaml(project / "project.yaml")
    lines = json.loads((project / "script" / "lines.json").read_text(encoding="utf-8"))
    assets = json.loads((project / "script" / "assets.json").read_text(
        encoding="utf-8"))["assets"]
    width, height = (int(x) for x in config.get("format", "1080x1920").split("x"))
    # Resolved before the first provider call: a wrong policy must not spend.
    policy = _account_policy(config, lines)

    beats: List[Dict[str, Any]] = []
    placements: List[Dict[str, Any]] = []
    cursor = 0
    for beat in lines["beats"]:
        audio = _cache(project, beat["text"])
        speech = audio["duration_s"]
        window_ms = _window_ms(speech)
        views = beat["views"]
        if not views:
            _fail("NO_VIEWS", f"{beat['placement_id']} declares no view")
        share = window_ms // len(views)
        if share < MIN_READING_MS or share > MAX_HOLD_MS:
            _fail("VIEW_OUT_OF_RANGE",
                  f"{beat['placement_id']}: {len(views)} views over {window_ms}ms "
                  f"gives {share}ms each, outside {MIN_READING_MS}-{MAX_HOLD_MS}ms")

        shots = []
        for index, view in enumerate(views):
            start = cursor + index * share
            end = cursor + window_ms if index == len(views) - 1 else start + share
            previous = shots[-1]["shot_id"] if shots else None
            shots.append({
                "shot_id": f"{beat['placement_id']}-V{index + 1}",
                "start_ms": start,
                "end_ms": end,
                "source_time_range": view.get("source_time_range",
                                              "00:00.000-00:00.500"),
                "crop": _crop(view["crop"], assets, view["asset_id"], width, height),
                "semantic_progress": view["semantic_progress"],
                # A detail view may only cite its own asset's context view; the
                # validator refuses a cross-asset enlargement.
                "context_shot_id": previous if view.get("context") else None,
                **({"asset_id": view["asset_id"]} if view.get("asset_id") else {}),
            })
        placements.append({
            "placement_id": beat["placement_id"],
            "start_ms": cursor,
            "end_ms": cursor + window_ms,
            "asset_id": views[0]["asset_id"],
            "source_time_range": shots[0]["source_time_range"],
            "crop": shots[0]["crop"],
            "reading_class": "reading",
            "semantic_progress": beat["semantic_progress"],
            "claim_ids": [beat["claim_id"]],
            "caption_cue_ids": [],
            "claim_bearing": True,
            "context_first": False,
            "context_placement_id": None,
            "transition": "cut",
            "shots": shots,
        })
        beats.append({
            "placement_id": beat["placement_id"],
            "claim_id": beat["claim_id"],
            "text": beat["text"],
            "speech_s": round(speech, 3),
            "window_s": round(window_ms / 1000.0, 3),
            "views": [s["shot_id"] for s in shots],
            "cached": audio["cached"],
            "provider_receipt": audio.get("provider_receipt"),
        })
        cursor += window_ms

    target = {
        "width": width,
        "height": height,
        "duration_ms_range": [cursor - 500, cursor + 500],
        "caption_safe_area": {"x": 54, "y": 1480, "width": 972, "height": 360},
        "min_reading_hold_ms": MIN_READING_MS,
        "max_visual_hold_ms": MAX_HOLD_MS,
        "min_visual_hold_ms": 2000,
        "evidence_mode": policy["evidence_mode"],
        "manual_recording": policy["manual_recording"],
        "composition": policy["composition"],
    }
    plan = {
        "schema": "contentops.cut-plan/v1",
        "package_id": project.name,
        "target": target,
        "placements": placements,
    }
    (project / "script" / "cut-plan.json").write_text(
        json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    receipt = {
        "schema": PLAN_SCHEMA,
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "package_id": project.name,
        "method": "audio-first: synthesise, measure, then size the windows",
        "voice_provider": "miniMax/speech-2.8-hd",
        "voice_quality": "minimax_mplan_subscription",
        "voice": VOICE,
        "rules": {"max_visual_hold_ms": MAX_HOLD_MS,
                  "min_reading_hold_ms": MIN_READING_MS,
                  "tail_ms": TAIL_MS},
        "beats": beats,
        "total_s": cursor / 1000.0,
        "production_ready": False,
        "human_review": "PENDING_FOUNDER_REVIEW",
    }
    (project / "receipts").mkdir(parents=True, exist_ok=True)
    (project / "receipts" / "audio-first-plan.json").write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # build_evidence_cut refuses a plan whose last placement disagrees with
    # project.yaml, so the measured total is written back rather than guessed.
    yaml_path = project / "project.yaml"
    lines_out = []
    seconds = f"{cursor / 1000.0:.1f}"
    for line in yaml_path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("duration_sec:"):
            line = f"duration_sec: {seconds}"
        lines_out.append(line)
    yaml_path.write_text("\n".join(lines_out) + "\n", encoding="utf-8")

    print(json.dumps({"status": "OK", "total_s": receipt["total_s"],
                      "beats": len(beats)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
