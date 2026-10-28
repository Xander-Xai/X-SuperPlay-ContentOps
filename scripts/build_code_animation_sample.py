#!/usr/bin/env python3
"""Compose a code-animation sample from external-skill clips.

The animation is rendered by an external skill (huashu-art-motion's engine);
this driver owns the parts that belong to ContentOps:

1. **Narration placement** — place each synthesised line at its placement start,
   so the voice and the picture share one timeline (audio-first).
2. **Captions** — write an SRT from the measured line durations and burn it with
   the account DNA style through ``assemble_easel``.
3. **Receipts** — spec/mp4 hashes, engine provenance, ffprobe facts and a
   technical QC report. It never claims production readiness.

Usage::

    python scripts/build_code_animation_sample.py projects/easel-fi-what-is-agent
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from contentops.media.transport import ffprobe_json  # noqa: E402
from contentops.media.video_qc import measure_video  # noqa: E402

CLIP_SECONDS = 4.0
SAMPLE_SCHEMA = "contentops.code-animation-sample/v1"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _yaml(path: Path) -> Dict[str, str]:
    data = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        data[key.strip()] = value.strip().strip('"')
    return data


def _caption_style(slug: str) -> Dict[str, Any]:
    dna = json.loads((ROOT / "config" / "accounts" / f"{slug}.json").read_text(
        encoding="utf-8"))
    caption = dna["visual"]["caption_style"]
    style: Dict[str, str] = {}
    for part in caption["burn_style"].split(","):
        key, _, value = part.partition("=")
        key = key.strip()
        if key and key not in ("Fontsize", "MarginV", "Alignment"):
            style[key] = value.strip()
    return {"style": style, "font_size": int(caption["size_px"]),
            "margin_v": int(caption["safe_zone"]["margin_v_px"])}


def _place_narration(project: Path, lines: List[Dict[str, Any]]) -> Path:
    """Write one PCM track with each line at its placement start."""
    sources = [project / row["path"].replace("project://", "") for row in lines]
    with wave.open(str(sources[0]), "rb") as first:
        rate, channels, width = first.getframerate(), first.getnchannels(), first.getsampwidth()
    total = int(round(CLIP_SECONDS * len(lines) * rate))
    buffer = bytearray(total * channels * width)
    for index, (source, row) in enumerate(zip(sources, lines)):
        with wave.open(str(source), "rb") as handle:
            if (handle.getframerate(), handle.getnchannels(), handle.getsampwidth()) != (rate, channels, width):
                raise SystemExit(f"sample format differs: {source}")
            frames = handle.readframes(handle.getnframes())
        offset = int(round(index * CLIP_SECONDS * rate)) * channels * width
        buffer[offset:offset + len(frames)] = frames
    target = project / "work" / "narration.wav"
    target.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(target), "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(width)
        out.setframerate(rate)
        out.writeframes(bytes(buffer))
    return target


def _write_srt(project: Path, lines: List[Dict[str, Any]]) -> Path:
    target = project / "assets" / "captions" / "cut.srt"
    target.parent.mkdir(parents=True, exist_ok=True)

    def ts(ms: int) -> str:
        h, rem = divmod(ms, 3600000)
        m, rem = divmod(rem, 60000)
        s, ms = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    rows = []
    for index, row in enumerate(lines):
        start = int(round(index * CLIP_SECONDS * 1000))
        end = min(start + int(round(row["duration_s"] * 1000)), start + 3900)
        rows.append(f"{index + 1}\n{ts(start)} --> {ts(end)}\n{row['text']}\n")
    target.write_text("\n".join(rows), encoding="utf-8")
    return target


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("project")
    parser.add_argument("--out-name", default="easel")
    args = parser.parse_args()

    project = Path(args.project)
    if not project.is_absolute():
        project = ROOT / project
    project = project.resolve()
    config = _yaml(project / "project.yaml")
    voice = json.loads((project / "receipts" / "voice-lines.json").read_text(encoding="utf-8"))
    lines = voice["lines"]

    clips = sorted((project / "work" / "clips").glob("p*.mp4"))
    if len(clips) != len(lines):
        print(json.dumps({"status": "BLOCKED", "reason":
                          f"{len(clips)} clips for {len(lines)} lines"}, ensure_ascii=False))
        return 4

    narration = _place_narration(project, lines)
    srt = _write_srt(project, lines)

    storyboard = {
        "size": config.get("format", "1080x1920"),
        "engine": "easel",
        "pad_mode": "trim",
        "narration": str(narration),
        "subtitle": str(srt),
        "voice_provider": "minimax-mplan",
        "shots": [{"video": str(clip), "duration": CLIP_SECONDS} for clip in clips],
    }
    storyboard_path = project / "work" / "storyboard.json"
    storyboard_path.write_text(json.dumps(storyboard, indent=2, ensure_ascii=False),
                               encoding="utf-8")

    style = _caption_style(config["account_slug"])
    from assemble_easel import run as assemble
    result = assemble(project, out_name=args.out_name, strict_captions=True,
                      storyboard_path=storyboard_path,
                      caption_style=style["style"],
                      caption_font_size=style["font_size"],
                      caption_margin_v=style["margin_v"])
    if result.get("status") != "OK":
        print(json.dumps(result, ensure_ascii=False))
        return 5

    output = Path(result["video"])
    measured = measure_video(output)
    meta = ffprobe_json(output)
    audio = next((s for s in meta.get("streams", []) if s.get("codec_type") == "audio"), {})
    visual = next((s for s in meta.get("streams", []) if s.get("codec_type") == "video"), {})

    clip_rows = []
    grammars = set()
    for clip, spec in zip(clips, sorted((project / "motion" / "specs").glob("p*.json"))):
        spec_doc = json.loads(spec.read_text(encoding="utf-8"))
        grammars.add(spec_doc.get("grammar", ""))
        clip_rows.append({
            "spec": f"project://motion/specs/{spec.name}",
            "grammar": spec_doc.get("grammar"),
            "spec_sha256": _sha(spec),
            "clip": f"project://work/clips/{clip.name}",
            "clip_sha256": _sha(clip),
            "duration_s": float(ffprobe_json(clip)["format"]["duration"]),
        })

    receipt = {
        "schema": SAMPLE_SCHEMA,
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "package_id": project.name,
        "content_type": "DEFINITIONAL_EXPLAINER",
        "claim_bearing": False,
        "external_skill": {
            "name": "huashu-art-motion",
            "version": "1.2.0",
            "license": "MIT",
            "engine": "scripts/engine/render.py",
            "grammar": sorted(g for g in grammars if g),
            "windows_adapter": "Playwright channel fallback (chrome/msedge) and PYTHONUTF8=1 for spec JSON",
        },
        "timeline": {"clip_seconds": CLIP_SECONDS, "clips": len(clips),
                     "narration_s": float(ffprobe_json(narration)["format"]["duration"])},
        "clips": clip_rows,
        "voice": {"provider": voice.get("voice", "speech-2.8-hd"),
                  "lines": lines, "receipts": "project://receipts/voice-lines.json"},
        "captions": {"path": f"project://assets/captions/cut.srt", "sha256": _sha(srt),
                     "style_source": f"config/accounts/{config['account_slug']}.json",
                     "cues": len(lines)},
        "output": {"path": f"project://{output.relative_to(project).as_posix()}",
                   "sha256": _sha(output),
                   "duration_s": float(meta["format"]["duration"]),
                   "width": visual.get("width"), "height": visual.get("height"),
                   "video_codec": visual.get("codec_name"),
                   "audio_codec": audio.get("codec_name") or None},
        "technical_qc": {
            "decodable": measured.decodable,
            "longest_black_run_s": measured.longest_black_run_s,
            "longest_freeze_run_s": measured.longest_freeze_run_s,
            "analysed_frames": measured.analysed_frames,
            "notes": list(measured.notes),
            "reasons": list(measured.reasons),
        },
        "red_lines": {
            "manual_recording": "none — pure code animation",
            "mouse_or_desktop": "none",
            "ai_generated_footage": "none",
            "platform_url_claimed": False,
        },
        "production_ready": False,
        "human_review": "PENDING_FOUNDER_REVIEW",
    }
    (project / "receipts" / "sample.json").write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": "OK", "output": receipt["output"],
                      "qc": {"decodable": measured.decodable,
                             "freeze_s": measured.longest_freeze_run_s,
                             "black_s": measured.longest_black_run_s},
                      "receipt": "receipts/sample.json"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
